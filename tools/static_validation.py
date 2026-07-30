#!/usr/bin/env python3
"""Dependency-free static checks for the Odoo addon.

This complements, but never replaces, installing/upgrading the module on an
Odoo 17 database. Run from any directory with Python 3.9+.
"""

from __future__ import annotations

import ast
import csv
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE = "yousentech_wo_v4"
EXTERNAL_PREFIXES = {
    "account",
    "base",
    "mail",
    "product",
    "sale",
    "stock",
}
XML_MOJIBAKE_MARKERS = (
    "\ufffd",
    "ط§",
    "ط£",
    "ط¥",
    "ط©",
    "ط±",
    "ط¹",
    "ط³",
    "ط´",
    "ظ„",
    "ظ…",
)


class Validation:
    def __init__(self):
        self.errors: list[str] = []
        self.counts: Counter = Counter()

    def require(self, condition, message):
        if not condition:
            self.errors.append(message)


def literal_assignment(tree, name):
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    try:
                        return ast.literal_eval(node.value)
                    except (ValueError, TypeError):
                        return None
    return None


def accepts_odoo_default_call(function):
    """Return whether Odoo can call a local default with a model recordset."""
    arguments = function.args
    positional = len(arguments.posonlyargs) + len(arguments.args)
    required_positional = positional - len(arguments.defaults)
    required_keyword_only = sum(
        default is None for default in arguments.kw_defaults
    )
    accepts_one_positional = (
        required_positional <= 1
        and (positional >= 1 or arguments.vararg is not None)
    )
    return accepts_one_positional and required_keyword_only == 0


def validate_field_default(
    validation, path, model_name, field_name, expression,
    module_functions, class_functions,
):
    """Validate local field default callables against Odoo's call convention."""
    function = None
    callable_name = None

    if isinstance(expression, ast.Lambda):
        function = expression
        callable_name = "lambda"
    elif isinstance(expression, ast.Name):
        callable_name = expression.id
        function = class_functions.get(callable_name) or module_functions.get(
            callable_name
        )
        if function is None:
            validation.counts["external_callable_defaults"] += 1
            return
    elif isinstance(expression, ast.Attribute):
        # Framework defaults such as fields.Datetime.now are maintained by
        # Odoo itself. Count them, while limiting signature checks to code
        # owned by this addon.
        validation.counts["external_callable_defaults"] += 1
        return
    else:
        return

    validation.counts["local_callable_defaults"] += 1
    validation.require(
        not isinstance(function, ast.AsyncFunctionDef)
        and accepts_odoo_default_call(function),
        f"Invalid callable default signature "
        f"{path.relative_to(ROOT)}:{model_name}.{field_name} "
        f"default={callable_name}; Odoo passes one model recordset argument",
    )


def parse_python(validation):
    models = {}
    inherited_models = set()
    model_inherits = defaultdict(list)
    methods = defaultdict(set)
    fields = defaultdict(dict)
    relations = []

    for path in sorted(ROOT.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        source = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=str(path))
            compile(tree, str(path), "exec")
        except SyntaxError as exc:
            validation.errors.append(f"Python syntax: {path.relative_to(ROOT)}: {exc}")
            continue
        validation.counts["python_files"] += 1
        module_functions = {
            node.name: node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }

        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            class_functions = {
                item.name: item
                for item in node.body
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
            model_name = literal_assignment(node, "_name")
            inherited = literal_assignment(node, "_inherit")
            if isinstance(inherited, str):
                inherited_models.add(inherited)
            elif isinstance(inherited, list):
                inherited_models.update(inherited)
            if not isinstance(model_name, str):
                if isinstance(inherited, str):
                    model_name = inherited
                else:
                    continue
            models[model_name] = path
            if isinstance(inherited, str):
                model_inherits[model_name].append(inherited)
            elif isinstance(inherited, list):
                model_inherits[model_name].extend(inherited)
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    methods[model_name].add(item.name)
                if not isinstance(item, ast.Assign) or len(item.targets) != 1:
                    continue
                target = item.targets[0]
                if not isinstance(target, ast.Name):
                    continue
                call = item.value
                if not (
                    isinstance(call, ast.Call)
                    and isinstance(call.func, ast.Attribute)
                    and isinstance(call.func.value, ast.Name)
                    and call.func.value.id == "fields"
                ):
                    continue
                kind = call.func.attr
                info = {"type": kind, "keywords": {}}
                for keyword in call.keywords:
                    if keyword.arg:
                        if keyword.arg == "default":
                            validate_field_default(
                                validation,
                                path,
                                model_name,
                                target.id,
                                keyword.value,
                                module_functions,
                                class_functions,
                            )
                        try:
                            info["keywords"][keyword.arg] = ast.literal_eval(keyword.value)
                        except (ValueError, TypeError):
                            info["keywords"][keyword.arg] = None
                if call.args:
                    try:
                        info["relation"] = ast.literal_eval(call.args[0])
                    except (ValueError, TypeError):
                        pass
                if len(call.args) > 1:
                    try:
                        info["inverse"] = ast.literal_eval(call.args[1])
                    except (ValueError, TypeError):
                        pass
                fields[model_name][target.id] = info
                if kind in {"Many2one", "One2many", "Many2many"} and info.get("relation"):
                    relations.append((path, model_name, target.id, info))

    # Merge fields/methods from local abstract and classical parents so view
    # checks understand mixins such as wof.api.mixin without requiring fields
    # to be redeclared on every business model.
    for _iteration in range(len(models) + 1):
        changed = False
        for model_name, parents in model_inherits.items():
            for parent in parents:
                if parent == model_name or parent not in fields:
                    continue
                for field_name, info in fields[parent].items():
                    if field_name not in fields[model_name]:
                        fields[model_name][field_name] = info
                        changed = True
                before = len(methods[model_name])
                methods[model_name].update(methods[parent])
                changed = changed or len(methods[model_name]) != before
        if not changed:
            break

    custom_models = {name for name in models if name.startswith("wof.")}
    for path, model, field_name, info in relations:
        relation = info["relation"]
        if relation.startswith("wof."):
            validation.require(
                relation in custom_models or relation == "wof.api.mixin",
                f"Undefined relation {model}.{field_name} -> {relation}",
            )
        if info["type"] == "One2many" and relation in fields:
            inverse = info.get("inverse")
            validation.require(
                inverse in fields[relation],
                f"Missing inverse {relation}.{inverse} for {model}.{field_name}",
            )

    for model, model_fields in fields.items():
        for field_name, info in model_fields.items():
            if info["type"] == "Monetary":
                currency = info["keywords"].get("currency_field", "currency_id")
                validation.require(
                    currency in model_fields,
                    f"Monetary field {model}.{field_name} lacks {currency}",
                )
            related = info["keywords"].get("related")
            if isinstance(related, str):
                first = related.split(".", 1)[0]
                validation.require(
                    first in model_fields,
                    f"Related field {model}.{field_name} starts with missing {first}",
                )

    validation.counts["models"] = len(models)
    validation.counts["custom_models"] = len(custom_models)
    return models, methods, fields


def parse_manifest(validation):
    manifest_path = ROOT / "__manifest__.py"
    manifest = ast.literal_eval(manifest_path.read_text(encoding="utf-8"))
    validation.require(manifest.get("installable") is True, "Manifest is not installable")
    validation.require(
        str(manifest.get("version", "")).startswith("17.0."),
        "Manifest version is not for Odoo 17",
    )
    validation.require(
        {"product", "account"}.issubset(set(manifest.get("depends", []))),
        "Manifest misses a direct required dependency",
    )
    paths = []
    for relative in manifest.get("data", []):
        path = ROOT / relative
        validation.require(path.is_file(), f"Missing manifest data file: {relative}")
        if path.is_file() and path.suffix == ".xml":
            paths.append(path)
    for bundle_files in manifest.get("assets", {}).values():
        for asset in bundle_files:
            prefix = MODULE + "/"
            relative = asset[len(prefix):] if asset.startswith(prefix) else asset
            validation.require((ROOT / relative).is_file(), f"Missing asset: {asset}")
    return manifest, paths


def check_xml_encoding(validation):
    """Reject non-UTF-8 XML and common double-decoded Arabic text."""
    for path in sorted(ROOT.rglob("*.xml")):
        try:
            source = path.read_bytes().decode("utf-8")
        except UnicodeDecodeError as exc:
            validation.errors.append(
                f"XML is not valid UTF-8: {path.relative_to(ROOT)}: {exc}"
            )
            continue
        declaration = re.match(r"<\?xml[^>]*encoding=['\"]([^'\"]+)", source)
        if declaration:
            validation.require(
                declaration.group(1).lower().replace("_", "-") == "utf-8",
                f"XML declaration is not UTF-8: {path.relative_to(ROOT)}",
            )
        found_markers = [
            marker for marker in XML_MOJIBAKE_MARKERS if marker in source
        ]
        validation.require(
            not found_markers,
            f"Possible Arabic mojibake in {path.relative_to(ROOT)}: "
            + ", ".join(repr(marker) for marker in found_markers),
        )
        validation.counts["xml_utf8_files"] += 1


def check_python_import_wiring(validation):
    """Ensure every addon Python module is loaded by its package."""
    for init_path in sorted(ROOT.rglob("__init__.py")):
        if "__pycache__" in init_path.parts:
            continue
        package_dir = init_path.parent
        tree = ast.parse(
            init_path.read_text(encoding="utf-8"), filename=str(init_path)
        )
        imported = set()
        for node in tree.body:
            if not isinstance(node, ast.ImportFrom) or node.level != 1:
                continue
            if node.module:
                imported.add(node.module.split(".", 1)[0])
            else:
                imported.update(alias.name for alias in node.names)
        expected = {
            path.stem
            for path in package_dir.glob("*.py")
            if path.name not in {"__init__.py", "__manifest__.py"}
        }
        missing = expected - imported
        validation.require(
            not missing,
            f"Python modules are not imported by "
            f"{init_path.relative_to(ROOT)}: {', '.join(sorted(missing))}",
        )
        validation.counts["python_modules_wired"] += len(expected)


def parse_xml(validation, paths, methods, fields):
    declared = {}
    ordered_ids = set()
    pending_local_refs = []
    action_models = {}
    action_buttons = []
    rule_models = []

    for path in paths:
        try:
            tree = ET.parse(path)
        except ET.ParseError as exc:
            validation.errors.append(f"XML parse: {path.relative_to(ROOT)}: {exc}")
            continue
        validation.counts["xml_files"] += 1
        root = tree.getroot()
        validation.require(root.tag == "odoo", f"{path.relative_to(ROOT)} root is not <odoo>")
        source = path.read_text(encoding="utf-8")
        validation.require(
            not re.search(r"\b(?:attrs|states)\s*=", source),
            f"Legacy attrs/states syntax in {path.relative_to(ROOT)}",
        )

        for element in root.iter():
            for attribute in (
                "invisible", "readonly", "required", "column_invisible",
                "domain", "context",
            ):
                expression = element.get(attribute)
                if not expression or expression in {"0", "1", "True", "False"}:
                    continue
                try:
                    ast.parse(expression, mode="eval")
                except SyntaxError as exc:
                    validation.errors.append(
                        f"Invalid {attribute} expression in "
                        f"{path.relative_to(ROOT)}: {expression}: {exc.msg}"
                    )
            external_id = element.get("id")
            if external_id and element.tag in {"record", "menuitem", "template"}:
                full_id = external_id if "." in external_id else f"{MODULE}.{external_id}"
                if full_id in declared:
                    validation.errors.append(
                        f"Duplicate XML ID {full_id}: "
                        f"{declared[full_id].relative_to(ROOT)} and {path.relative_to(ROOT)}"
                    )
                declared[full_id] = path

            for attribute in ("ref", "parent", "action", "groups"):
                raw = element.get(attribute)
                if not raw:
                    continue
                values = raw.split(",") if attribute == "groups" else [raw]
                for value in values:
                    value = value.strip().lstrip("!")
                    if not value or value.startswith("("):
                        continue
                    if "." not in value:
                        value = f"{MODULE}.{value}"
                    short_value = value.split(".", 1)[-1]
                    if (
                        value.split(".", 1)[0] not in EXTERNAL_PREFIXES
                        and not short_value.startswith("model_")
                    ):
                        pending_local_refs.append((path, value))

        for record in root.findall(".//record"):
            record_id = record.get("id")
            model = record.get("model")
            field_values = {
                field.get("name"): (field.text or "").strip()
                for field in record.findall("./field")
            }
            if model == "ir.actions.act_window":
                action_models[record_id] = field_values.get("res_model")
            if model == "ir.rule":
                model_ref = next(
                    (field.get("ref") for field in record.findall("./field")
                     if field.get("name") == "model_id"),
                    None,
                )
                if model_ref:
                    rule_models.append((path, model_ref))
            if model == "ir.ui.view":
                view_model = field_values.get("model")
                arch = next(
                    (field for field in record.findall("./field") if field.get("name") == "arch"),
                    None,
                )
                if arch is not None and view_model and view_model in fields:
                    def validate_arch(node, active_model):
                        for child in node:
                            child_model = active_model
                            if child.tag == "field":
                                name = child.get("name")
                                if name:
                                    validation.require(
                                        name in fields.get(active_model, {}),
                                        f"View {record_id} uses missing {active_model}.{name}",
                                    )
                                    info = fields.get(active_model, {}).get(name, {})
                                    if info.get("type") in {"One2many", "Many2many"}:
                                        child_model = info.get("relation", active_model)
                            validate_arch(child, child_model)

                    validate_arch(arch, view_model)

                    def validate_check_company_scope(scope, active_model):
                        company_field_available = False
                        check_company_fields = []

                        def walk(node, restricted_by_groups=False):
                            nonlocal company_field_available
                            for child in node:
                                restricted = (
                                    restricted_by_groups
                                    or bool(child.get("groups"))
                                )
                                if child.tag != "field":
                                    walk(child, restricted)
                                    continue
                                name = child.get("name")
                                info = fields.get(active_model, {}).get(name, {})
                                if name == "company_id" and not restricted:
                                    company_field_available = True
                                if info.get("keywords", {}).get("check_company") is True:
                                    check_company_fields.append(name)

                                relation = info.get("relation")
                                nested_views = [
                                    nested
                                    for nested in child
                                    if nested.tag in {
                                        "form", "list", "tree", "kanban"
                                    }
                                ]
                                for nested in nested_views:
                                    if relation in fields:
                                        validate_check_company_scope(
                                            nested, relation
                                        )
                                for nested in child:
                                    if nested not in nested_views:
                                        walk(nested, restricted)

                        walk(scope)
                        if check_company_fields:
                            validation.counts[
                                "check_company_view_scopes"
                            ] += 1
                            validation.require(
                                company_field_available,
                                f"View {record_id} exposes check_company field(s) "
                                f"{', '.join(sorted(set(check_company_fields)))} "
                                f"for {active_model} without an unrestricted "
                                f"technical company_id",
                            )

                    for view_root in arch:
                        validate_check_company_scope(view_root, view_model)
                    for button in arch.findall(".//button[@type='object']"):
                        action_buttons.append((path, record_id, view_model, button.get("name")))
        ordered_ids.update(
            key for key, value in declared.items() if value == path
        )

    for path, reference in pending_local_refs:
        validation.require(
            reference in declared,
            f"Missing local XML reference {reference} in {path.relative_to(ROOT)}",
        )
    for path, view_id, model, method in action_buttons:
        validation.require(
            method in methods.get(model, set()) or method in {"toggle_active"},
            f"Button {view_id} calls missing {model}.{method}",
        )
    for path, model_ref in rule_models:
        model_name = model_ref.removeprefix("model_").replace("_", ".")
        validation.require(
            "company_id" in fields.get(model_name, {}),
            f"Company record rule targets model without company_id: {model_name}",
        )
    validation.counts["xml_ids"] = len(declared)
    validation.counts["object_buttons"] = len(action_buttons)
    return declared


def check_xml_load_order(validation, paths):
    seen = set()

    def full_id(value):
        return value if "." in value else f"{MODULE}.{value}"

    def walk_data_nodes(root):
        for child in root:
            if child.tag == "data":
                yield from child
            else:
                yield child

    for path in paths:
        root = ET.parse(path).getroot()
        for element in walk_data_nodes(root):
            own_id = element.get("id")
            if own_id and element.tag in {"record", "menuitem", "template"}:
                seen.add(full_id(own_id))
            for node in element.iter():
                refs = []
                for attribute in ("ref", "parent", "action", "groups"):
                    raw = node.get(attribute)
                    if raw:
                        refs.extend(raw.split(",") if attribute == "groups" else [raw])
                eval_source = node.get("eval")
                if eval_source:
                    refs.extend(re.findall(r"ref\(['\"]([^'\"]+)['\"]\)", eval_source))
                for raw_ref in refs:
                    reference = full_id(raw_ref.strip().lstrip("!"))
                    short = reference.split(".", 1)[-1]
                    if (
                        reference.split(".", 1)[0] in EXTERNAL_PREFIXES
                        or short.startswith("model_")
                    ):
                        continue
                    validation.require(
                        reference in seen,
                        f"Local XML reference is loaded too late: {reference} "
                        f"in {path.relative_to(ROOT)}",
                    )

            if element.get("model") == "ir.actions.server":
                code = next(
                    (
                        (field.text or "")
                        for field in element.findall("./field")
                        if field.get("name") == "code"
                    ),
                    "",
                )
                if code.strip():
                    try:
                        compile(code, str(path), "exec")
                    except SyntaxError as exc:
                        validation.errors.append(
                            f"Server action syntax in {path.relative_to(ROOT)}: {exc}"
                        )


def parse_acl(validation, declared, models):
    path = ROOT / "security" / "ir.model.access.csv"
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    validation.require(bool(rows), "ACL CSV has no rows")
    ids = [row["id"] for row in rows]
    validation.require(len(ids) == len(set(ids)), "Duplicate ACL IDs")
    for row in rows:
        model_ref = row["model_id:id"].split(".")[-1]
        model_name = model_ref.removeprefix("model_").replace("_", ".")
        validation.require(
            model_name in models or model_name in {
                "product.template", "product.product", "account.tax",
            },
            f"ACL {row['id']} targets undefined model {model_name}",
        )
        group_ref = row["group_id:id"]
        if group_ref and group_ref.startswith(MODULE + "."):
            validation.require(
                group_ref in declared,
                f"ACL {row['id']} targets undefined group {group_ref}",
            )
        for permission in ("perm_read", "perm_write", "perm_create", "perm_unlink"):
            validation.require(
                row[permission] in {"0", "1"},
                f"ACL {row['id']} has invalid {permission}",
            )
    by_id = {row["id"]: row for row in rows}
    for access_id in (
        "access_setup_size_line_settings",
        "access_setup_service_line_settings",
    ):
        validation.require(
            by_id.get(access_id, {}).get("perm_unlink") == "0",
            f"{access_id} must preserve setup history",
        )
    event_rows = [
        row for row in rows
        if row["model_id:id"].split(".")[-1]
        == "model_wof_installation_order_event"
    ]
    validation.require(bool(event_rows), "Installation order events lack read ACL")
    for row in event_rows:
        validation.require(
            row["perm_create"] == row["perm_write"] == row["perm_unlink"] == "0",
            "Installation order timeline must remain append-only",
        )
    validation.require(
        by_id.get("access_company_profile_employee", {}).get("perm_read") == "1",
        "Operational employees cannot read company readiness",
    )
    validation.counts["acl_rows"] = len(rows)


def parse_docs_and_contract(validation):
    required_docs = [
        "docs/ROADMAP_AR.md",
        "docs/SCREEN_INDEX_AR.md",
        "docs/API_ARCHITECTURE_AR.md",
        "docs/FOUNDATION_AUDIT_AR.md",
        "docs/INSTALLATION_ORDER_AUDIT_AR.md",
        "docs/api/openapi.yaml",
    ]
    for relative in required_docs:
        validation.require((ROOT / relative).is_file(), f"Missing documentation: {relative}")

    screen_docs = sorted((ROOT / "docs" / "screens").glob("*_AR.md"))
    validation.require(bool(screen_docs), "No per-screen documentation")
    for path in screen_docs:
        text = path.read_text(encoding="utf-8")
        validation.require("Flutter" in text, f"Missing Flutter contract: {path.name}")
    validation.counts["screen_docs"] = len(screen_docs)

    index = (ROOT / "docs" / "SCREEN_INDEX_AR.md").read_text(encoding="utf-8")
    indexed_screen_docs = set()
    for match in re.finditer(r"`(screens/[^`]+\.md)`", index):
        relative = match.group(1)
        indexed_screen_docs.add((ROOT / "docs" / relative).resolve())
        validation.require(
            (ROOT / "docs" / relative).is_file(),
            f"Broken screen doc link: {relative}",
        )
    validation.require(
        indexed_screen_docs == {path.resolve() for path in screen_docs},
        "Screen index and per-screen documentation are out of sync",
    )

    openapi = (ROOT / "docs" / "api" / "openapi.yaml").read_text(encoding="utf-8")
    yaml_stack = []
    yaml_seen = {}
    yaml_sequence_counts = Counter()

    def check_mapping(line_number, indent, text):
        match = re.match(r"^([^:#][^:]*):(?:\s*(.*))?$", text)
        if not match:
            return
        key = match.group(1).strip().strip("'\"")
        value = (match.group(2) or "").strip()
        while yaml_stack and yaml_stack[-1][0] >= indent:
            yaml_stack.pop()
        parent = tuple(item[1] for item in yaml_stack)
        signature = (parent, indent, key)
        validation.require(
            signature not in yaml_seen,
            f"OpenAPI duplicate mapping key {key!r} at line {line_number}",
        )
        yaml_seen[signature] = line_number
        if not value:
            yaml_stack.append((indent, key))

    for line_number, raw in enumerate(openapi.splitlines(), start=1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        validation.require(
            indent % 2 == 0,
            f"OpenAPI odd indentation at line {line_number}",
        )
        stripped = raw.strip()
        if stripped.startswith("- "):
            while yaml_stack and yaml_stack[-1][0] >= indent:
                yaml_stack.pop()
            parent = tuple(item[1] for item in yaml_stack)
            counter_key = (parent, indent)
            yaml_sequence_counts[counter_key] += 1
            yaml_stack.append(
                (indent, f"[{yaml_sequence_counts[counter_key]}]")
            )
            remainder = stripped[2:].strip()
            if ":" in remainder:
                check_mapping(line_number, indent + 2, remainder)
        else:
            check_mapping(line_number, indent, stripped)
    validation.require(
        openapi.lstrip().startswith("openapi: 3."),
        "OpenAPI document is not 3.x",
    )
    operation_ids = re.findall(r"^\s+operationId:\s*(\S+)\s*$", openapi, re.MULTILINE)
    validation.require(
        len(operation_ids) == len(set(operation_ids)),
        "Duplicate OpenAPI operationId",
    )
    definitions = set(re.findall(r"^    ([A-Za-z0-9_]+):\s*$", openapi, re.MULTILINE))
    references = set(re.findall(r"#/components/schemas/([A-Za-z0-9_]+)", openapi))
    validation.require(
        references.issubset(definitions),
        "Unresolved OpenAPI schema refs: " + ", ".join(sorted(references - definitions)),
    )
    validation.require(
        re.search(r"SetupProfile:[\s\S]*?\n        company_uuid:", openapi) is not None,
        "SetupProfile contract misses company_uuid",
    )
    for path in (
        "/installation-orders:",
        "/installation-orders/{orderUuid}:",
        "/installation-orders/{orderUuid}/actions/start-execution:",
        "/installation-orders/{orderUuid}/actions/pass-quality:",
        "/installation-orders/{orderUuid}/actions/deliver:",
        "/installation-orders/{orderUuid}/actions/cancel:",
    ):
        validation.require(path in openapi, f"OpenAPI misses planned path {path}")
    validation.counts["openapi_operations"] = len(operation_ids)


def check_installation_order(validation, models, methods, fields):
    required_models = {
        "wof.installation.order",
        "wof.installation.order.line",
        "wof.installation.material.line",
        "wof.installation.order.event",
    }
    validation.require(
        required_models.issubset(models),
        "Installation order models are incomplete: "
        + ", ".join(sorted(required_models - set(models))),
    )
    required_fields = {
        "wof.installation.order": {
            "public_uuid", "operation_source", "company_id", "state",
            "idempotency_key", "line_ids", "event_ids", "amount_total",
            "technician_ids", "sale_order_id", "invoice_id",
        },
        "wof.installation.order.line": {
            "public_uuid", "company_id", "service_type_id",
            "film_category_id", "car_part_id", "price_source",
            "unit_price", "execution_progress",
        },
        "wof.installation.order.event": {
            "public_uuid", "operation_source", "company_id",
            "event_code", "user_id", "occurred_at",
        },
        "res.partner": {"wof_public_uuid"},
    }
    for model, expected in required_fields.items():
        missing = expected - set(fields.get(model, {}))
        validation.require(
            not missing,
            f"{model} misses API/workflow fields: {', '.join(sorted(missing))}",
        )
    transition_methods = {
        "action_confirm_arrival",
        "action_complete_intake",
        "action_start_execution",
        "action_submit_quality",
        "action_return_to_execution",
        "action_pass_quality",
        "action_deliver",
        "action_cancel",
        "create_idempotent",
    }
    missing_methods = transition_methods - methods.get(
        "wof.installation.order", set()
    )
    validation.require(
        not missing_methods,
        "Installation order service methods are incomplete: "
        + ", ".join(sorted(missing_methods)),
    )
    source = "\n".join(
        (ROOT / "models" / filename).read_text(encoding="utf-8")
        for filename in (
            "installation_order.py",
            "installation_order_workflow.py",
            "installation_order_line.py",
            "installation_material.py",
            "installation_event.py",
        )
    )
    for state in (
        "draft", "scheduled", "intake", "in_progress",
        "quality", "ready", "delivered", "cancelled",
    ):
        validation.require(
            f"('{state}'," in source,
            f"Installation order state code missing: {state}",
        )
    validation.require(
        "wof_order_transition_token" in source
        and "ORDER_TRANSITION_TOKEN" in source,
        "Installation order state writes are not token-protected",
    )


def check_policy(validation):
    implementation = "\n".join(
        path.read_text(encoding="utf-8")
        for suffix in ("*.py", "*.xml", "*.csv")
        for path in ROOT.rglob(suffix)
        if "__pycache__" not in path.parts and "tools" not in path.parts
    )
    validation.require("base.group_system" not in implementation, "Technical settings group leaked")
    validation.require("res.config.settings" not in implementation, "Technical settings model leaked")
    validation.require("setup_completed" not in implementation, "Legacy global setup flag remains")
    validation.require("models.TransientModel" not in (
        ROOT / "setup_wizard" / "setup_wizard.py"
    ).read_text(encoding="utf-8"), "Persistent setup uses TransientModel")
    validation.require(
        not (ROOT / "controllers").exists(),
        "REST controllers exist before authentication/security approval",
    )
    sudo_calls = []
    for path in ROOT.rglob("*.py"):
        if "tools" in path.parts or "__pycache__" in path.parts:
            continue
        for lineno, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if ".sudo(" in line:
                sudo_calls.append((path.relative_to(ROOT).as_posix(), lineno))
    allowed_sudo_files = {
        "models/api_foundation.py",
        "models/installation_order_workflow.py",
    }
    validation.require(
        len(sudo_calls) == 2
        and {path for path, _line in sudo_calls} == allowed_sudo_files,
        "sudo use expanded beyond the two reviewed append-only inserts: "
        + ", ".join(f"{path}:{line}" for path, line in sudo_calls),
    )


def main():
    validation = Validation()
    manifest, xml_paths = parse_manifest(validation)
    check_xml_encoding(validation)
    check_python_import_wiring(validation)
    models, methods, fields = parse_python(validation)
    declared = parse_xml(validation, xml_paths, methods, fields)
    check_xml_load_order(validation, xml_paths)
    parse_acl(validation, declared, models)
    parse_docs_and_contract(validation)
    check_installation_order(validation, models, methods, fields)
    check_policy(validation)

    if validation.errors:
        print("STATIC_VALIDATION_FAILED")
        for error in validation.errors:
            print(f"- {error}")
        return 1
    rendered = " ".join(f"{key}={value}" for key, value in sorted(validation.counts.items()))
    print(f"STATIC_VALIDATION_PASS {rendered}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
