/** @odoo-module **/

import { Component, onMounted, onWillStart, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

const MODEL = "wof.film.category";
const UNITS = [["day", "يوم"], ["month", "شهر"], ["year", "سنة"]];
const CHECK_NAMES = { components: "المكوّنات", tint: "درجات اللون", prices: "الأسعار", commissions: "العمولات" };
const CHECK_STEP = { components: "comp", tint: "tint", prices: "price", commissions: "price" };

const digits = (value) => String(value ?? "").replace(/[٠-٩]/g, (d) => String("٠١٢٣٤٥٦٧٨٩".indexOf(d)));
const num = (value) => {
    const parsed = parseFloat(digits(value).replace(/[,\s%]/g, ""));
    return Number.isFinite(parsed) ? parsed : null;
};

export class WofFilmEditor extends Component {
    static template = "yousentech_wo_v4.FilmEditor";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.root = useRef("root");
        const params = (this.props.action && this.props.action.params) || {};
        this.filmId = params.film_id;
        this.state = useState({
            data: null, step: "basic", visited: [], busy: false,
            draft: {}, picker: { open: false, query: "", results: [] }, tintEdit: null,
            adder: null, form: null, expanded: {}, tplOpen: {}, drag: null,
            discountLimit: "",
        });
        onWillStart(async () => {
            this.setData(await this.orm.call(MODEL, "wof_film_load", [[this.filmId]]));
            const start = this.flow.includes(params.step) ? params.step : "basic";
            this.state.step = start;
            this.state.visited = this.flow.slice(0, this.flow.indexOf(start) + 1);
        });
        onMounted(() => {
            const content = this.root.el && this.root.el.closest(".modal-content");
            const footer = content && content.querySelector(":scope > .modal-footer");
            if (footer) {
                footer.classList.add("d-none");
            }
        });
    }

    setData(data) {
        const f = data.film;
        this.state.data = data;
        this.state.draft = {
            name: f.name, code: f.code, description: f.description,
            warning_msg: f.warning_msg, warranty_period: String(f.warranty_period ?? 0),
        };
        this.state.discountLimit = String(data.policies.discount.limit ?? 0);
    }

    async call(method, args, kwargs = {}) {
        if (this.state.busy) {
            return null;
        }
        this.state.busy = true;
        try {
            return await this.orm.call(MODEL, method, [[this.filmId], ...args], kwargs);
        } catch (error) {
            const message = (error && error.data && error.data.message) || (error && error.message) || _t("تعذر حفظ التغيير.");
            this.notification.add(message, { type: "danger" });
            return null;
        } finally {
            this.state.busy = false;
        }
    }

    async apply(op, payload = {}) {
        const data = await this.call("wof_film_apply", [op, payload]);
        if (data) {
            this.setData(data);
            return true;
        }
        return false;
    }

    // ------------------------------------------------------------- steps
    get film() {
        return this.state.data.film;
    }

    get isFilm() {
        return this.film.item_type === "film";
    }

    get needsTint() {
        return this.isFilm && this.film.activity.supports_grades;
    }

    get steps() {
        return [
            ["basic", "الأساسيات"], ["tint", "درجات اللون"], ["comp", "المكوّنات"],
            ["pol", "السياسات"], ["price", "الأسعار والعمولات"], ["rev", "المراجعة والتفعيل"],
        ].filter((s) => s[0] !== "tint" || this.needsTint);
    }

    get flow() {
        return this.steps.map((s) => s[0]);
    }

    get current() {
        return this.flow.includes(this.state.step) ? this.state.step : "basic";
    }

    go(key) {
        if (!this.flow.includes(key)) {
            return;
        }
        this.state.step = key;
        this.state.picker.open = false;
        this.state.tintEdit = null;
        this.state.adder = null;
        this.state.form = null;
        if (!this.state.visited.includes(key)) {
            this.state.visited.push(key);
        }
        const main = this.root.el && this.root.el.querySelector(".wof_sf_main");
        if (main) {
            main.scrollTop = 0;
        }
    }

    get nextKey() {
        return this.flow[this.flow.indexOf(this.current) + 1];
    }

    get prevKey() {
        return this.flow[this.flow.indexOf(this.current) - 1];
    }

    get nextLabel() {
        const step = this.steps.find((s) => s[0] === this.nextKey);
        return step ? `${_t("التالي:")} ${step[1]}` : "";
    }

    close() {
        this.action.doAction({ type: "ir.actions.act_window_close" });
    }

    // --------------------------------------------------------- readiness
    get readiness() {
        return this.state.data.readiness;
    }

    get checks() {
        return this.readiness.checks.filter((c) => c.key !== "tint" || this.needsTint).map((c) => ({
            ...c, name: CHECK_NAMES[c.key], step: CHECK_STEP[c.key],
            state: c.ok ? "ok" : (c.soft ? "soft" : "warn"),
        }));
    }

    get hardChecks() {
        return this.checks.filter((c) => !c.soft);
    }

    get missingText() {
        return this.hardChecks.filter((c) => !c.ok).map((c) => c.name).join("، ");
    }

    get stepWarn() {
        const bad = (key) => this.checks.some((c) => !c.ok && !c.soft && c.step === key);
        return { tint: bad("tint"), comp: bad("comp"), price: bad("price") };
    }

    get rail() {
        const warnOf = this.stepWarn;
        const policies = this.state.data.policies;
        const custom = Object.values(policies).filter((p) => p.custom).length;
        const r = this.readiness;
        const subs = {
            basic: `${this.isFilm ? _t("فيلم") : _t("خدمة")} · ${_t("ضمان")} ${this.warrantyLabel}`,
            tint: this.state.data.tint.use_all ? _t("كل الدرجات") : `${r.grades} ${_t("درجات محددة")}`,
            comp: `${r.components} ${_t("مكوّنات")}`,
            pol: custom ? `${custom} ${_t("مخصصة · الباقي من النظام")}` : _t("كلها من النظام"),
            price: `${_t("أسعار")} ${r.price_done}/${r.components} · ${_t("عمولات")} ${r.comm_done}/${r.components}`,
            rev: this.film.active ? _t("مفعّل") : (r.ready ? _t("جاهز للتفعيل") : `${_t("ينقص")} ${this.hardChecks.filter((c) => !c.ok).length}`),
        };
        return this.steps.map((s, i) => {
            const key = s[0];
            const isCur = key === this.current;
            const seen = this.state.visited.includes(key);
            const warn = !!warnOf[key];
            return {
                key, name: s[1], num: i + 1, sub: subs[key], isCur, warnSub: warn,
                dot: isCur ? "cur" : (warn ? "warn" : (seen && key !== "rev" ? "done" : "todo")),
            };
        });
    }

    get footer() {
        if (this.current === "rev") {
            if (this.film.active) {
                return { warn: !this.readiness.ready, text: this.readiness.ready ? _t("الفيلم مفعّل") : `${_t("مفعّل لكن ينقص:")} ${this.missingText}` };
            }
            return this.readiness.ready ? { warn: false, text: _t("جاهز للتفعيل") } : { warn: true, text: `${_t("ينقص:")} ${this.missingText}` };
        }
        const msg = { tint: _t("اختر درجة لون واحدة على الأقل"), comp: _t("أضف مكوّنًا واحدًا على الأقل"), price: _t("أكمل أسعار كل المكوّنات قبل التفعيل") };
        if (this.stepWarn[this.current]) {
            return { warn: true, text: msg[this.current] };
        }
        return { warn: false, text: _t("كل تغيير يُحفظ مباشرة") };
    }

    // ------------------------------------------------------------ basics
    get warrantyLabel() {
        const f = this.film;
        if (!f.warranty_period) {
            return _t("بدون");
        }
        return `${f.warranty_period} ${(UNITS.find((u) => u[0] === f.warranty_unit) || ["", ""])[1]}`;
    }

    get units() {
        return UNITS.map((u) => ({ key: u[0], name: u[1], on: this.film.warranty_unit === u[0] }));
    }

    get typeOptions() {
        return [
            { key: "film", name: _t("فيلم"), desc: _t("يُركَّب على أجزاء السيارة، وله درجات لون ومنتج مخزني.") },
            { key: "service", name: _t("خدمة"), desc: _t("عمل يُنفَّذ بدون فيلم، مثل التلميع أو التنظيف.") },
        ];
    }

    setType(key) {
        if (key !== this.film.item_type) {
            return this.apply("basic", { item_type: key });
        }
    }

    onDraft(field, ev) {
        let value = ev.target.value;
        if (field === "warranty_period") {
            value = digits(value).replace(/[^0-9]/g, "");
            ev.target.value = value;
        }
        this.state.draft[field] = value;
    }

    commit(field) {
        const value = this.state.draft[field];
        const current = field === "warranty_period" ? String(this.film.warranty_period ?? 0) : (this.film[field] ?? "");
        if (String(value ?? "") === String(current)) {
            return;
        }
        if (field === "name" && !(value || "").trim()) {
            this.notification.add(_t("الاسم مطلوب."), { type: "warning" });
            this.state.draft.name = this.film.name;
            return;
        }
        return this.apply("basic", { [field]: field === "warranty_period" ? parseInt(value || "0", 10) : value });
    }

    get warrantyNote() {
        const p = parseInt(this.state.draft.warranty_period || "0", 10);
        if (!p) {
            return _t("بدون ضمان.");
        }
        const unit = (UNITS.find((u) => u[0] === this.film.warranty_unit) || ["", ""])[1];
        return `${_t("يظهر في شهادة الضمان:")} ${p} ${unit} ${_t("من تاريخ التسليم.")}`;
    }

    // -------------------------------------------------------------- tint
    get tintOptions() {
        const n = this.state.data.tint.shades.length;
        return [
            { key: "all", name: `${_t("كل درجات النظام")} (${n})`, desc: _t("أي درجة تُضاف للنظام لاحقًا تظهر لهذا الفيلم تلقائيًا.") },
            { key: "specific", name: _t("درجات محددة"), desc: _t("اختر الدرجات التي يتوفر بها هذا الفيلم فقط.") },
        ];
    }

    get tintMode() {
        return this.state.data.tint.use_all ? "all" : "specific";
    }

    setTintMode(key) {
        if (key === this.tintMode) {
            return;
        }
        if (key === "all") {
            return this.apply("tint", { use_all: true });
        }
        // Start the specific selection from what the film has today.
        return this.apply("tint", { use_all: false });
    }

    toggleShade(shade) {
        if (this.state.data.tint.use_all) {
            return;
        }
        return this.apply("tint", { use_all: false, code: shade.code, selected: !shade.selected });
    }

    shadeStyle(shade, index) {
        const method = this.state.data.tint.method;
        const count = Math.max(this.state.data.tint.shades.length - 1, 1);
        const t = method === "percentage" ? parseInt(shade.value, 10) / 100 : index / count;
        const light = Math.round(92 - (Number.isFinite(t) ? t : 0.5) * 78);
        return `background: hsl(190, 8%, ${light}%)`;
    }

    get tintNote() {
        return this.state.data.tint.use_all
            ? _t("يستخدم الفيلم كل الدرجات المفعّلة في النظام، والدرجة الجديدة تُضاف له تلقائيًا.")
            : `${this.readiness.grades} ${_t("درجات متاحة لهذا الفيلم. الدرجات الأخرى لا تظهر له في أوامر التركيب.")}`;
    }

    // -------------------------------------------------------- components
    get componentSummary() {
        const comps = this.state.data.components;
        const areas = comps.filter((c) => c.type === "service_area");
        return {
            parts: comps.length - areas.length,
            areas: areas.length,
            inner: areas.reduce((n, c) => n + c.kids.length, 0),
        };
    }

    toggleExpand(c) {
        this.state.expanded[c.line_id] = !this.state.expanded[c.line_id];
    }

    // adder: pick existing masters, several at once
    async openAdder(type = "car_part") {
        this.state.form = null;
        this.state.tintEdit = null;
        this.state.adder = { type, query: "", results: [], selected: [] };
        await this.searchAdder();
    }

    async searchAdder() {
        const a = this.state.adder;
        if (!a) {
            return;
        }
        const results = await this.orm.call(MODEL, "wof_film_parts_search", [[this.filmId]], { query: a.query || "", part_type: a.type });
        if (this.state.adder === a) {
            a.results = results || [];
        }
    }

    setAdderType(type) {
        this.state.adder.type = type;
        this.state.adder.selected = [];
        return this.searchAdder();
    }

    onAdderQuery(ev) {
        this.state.adder.query = ev.target.value;
        return this.searchAdder();
    }

    toggleAdderPick(p) {
        if (!p.usable) {
            return;
        }
        const a = this.state.adder;
        a.selected = a.selected.includes(p.id) ? a.selected.filter((id) => id !== p.id) : [...a.selected, p.id];
    }

    selectAllAdder() {
        this.state.adder.selected = this.state.adder.results.filter((p) => p.usable).map((p) => p.id);
    }

    async addSelected() {
        const ids = this.state.adder.selected;
        if (!ids.length) {
            return;
        }
        if (await this.apply("comp_add_many", { part_ids: ids })) {
            this.notification.add(`${_t("أُضيف")} ${ids.length} ${_t("مكوّن للفيلم.")}`, { type: "success" });
            this.state.adder = null;
        }
    }

    // component form: create a new master or edit an existing one
    async openForm(type, c = null) {
        this.state.adder = null;
        this.state.tintEdit = null;
        const info = await this.orm.call(MODEL, "wof_component_load", [[this.filmId]], { part_id: c ? c.part_id : false });
        const part = info.part;
        const grades = this.state.data.grades.map((g) => g.id);
        const templates = part && part.templates.length ? part.templates : [{ id: false, name: _t("النموذج الأساسي"), is_default: true, component_ids: [] }];
        let key = 0;
        this.state.form = {
            id: part ? part.id : false,
            type: part ? part.type : type,
            name: part ? part.name : "",
            code: part ? part.code : "",
            autoProduct: !part,
            product: part ? part.product : false,
            productQuery: "", productResults: [],
            priority: String(part ? part.priority || 0 : 10),
            option_ids: part ? [...part.option_ids] : [],
            options_required: part ? part.options_required : false,
            notes: part ? part.notes : "",
            warning_msg: part ? part.warning_msg : "",
            other_films: part ? part.other_films : 0,
            templates: templates.map((t) => ({ ...t, key: ++key, component_ids: [...t.component_ids] })),
            nextKey: key,
            tint: c ? { default_grade_id: c.default_grade_id || false, allowed_ids: c.allowed_ids.length ? [...c.allowed_ids] : grades } : { default_grade_id: false, allowed_ids: grades },
            choices: info,
        };
        const main = this.root.el && this.root.el.querySelector(".wof_sf_main");
        if (main) {
            main.scrollTop = 0;
        }
    }

    closeForm() {
        this.state.form = null;
    }

    setFormType(type) {
        this.state.form.type = type;
    }

    onForm(field, ev) {
        this.state.form[field] = ev.target.value;
    }

    toggleFormOption(id) {
        const f = this.state.form;
        f.option_ids = f.option_ids.includes(id) ? f.option_ids.filter((x) => x !== id) : [...f.option_ids, id];
        if (!f.option_ids.length) {
            f.options_required = false;
        }
    }

    async searchProducts(ev) {
        const f = this.state.form;
        f.productQuery = ev.target.value;
        f.productResults = await this.orm.call(MODEL, "wof_service_products", [[this.filmId]], { query: f.productQuery });
    }

    pickProduct(p) {
        this.state.form.product = p;
        this.state.form.productResults = [];
        this.state.form.productQuery = "";
    }

    get formNeedsTint() {
        return this.state.form && this.state.form.type === "car_part" && this.needsTint;
    }

    onFormDefaultGrade(ev) {
        const id = parseInt(ev.target.value, 10);
        this.state.form.tint.default_grade_id = Number.isFinite(id) ? id : false;
    }

    toggleFormAllowed(id) {
        const tint = this.state.form.tint;
        if (tint.allowed_ids.includes(id)) {
            if (tint.allowed_ids.length === 1) {
                this.notification.add(_t("اترك درجة واحدة مسموحة على الأقل."), { type: "warning" });
                return;
            }
            tint.allowed_ids = tint.allowed_ids.filter((x) => x !== id);
            if (tint.default_grade_id === id) {
                tint.default_grade_id = false;
            }
        } else {
            tint.allowed_ids = [...tint.allowed_ids, id];
        }
    }

    // service-area templates
    addTemplate() {
        const f = this.state.form;
        f.nextKey += 1;
        f.templates.push({ id: false, key: f.nextKey, name: `${_t("نموذج")} ${f.templates.length + 1}`, is_default: false, component_ids: [] });
    }

    removeTemplate(t) {
        const f = this.state.form;
        if (f.templates.length === 1) {
            return;
        }
        f.templates = f.templates.filter((x) => x.key !== t.key);
        if (!f.templates.some((x) => x.is_default)) {
            f.templates[0].is_default = true;
        }
    }

    setDefaultTemplate(t) {
        for (const x of this.state.form.templates) {
            x.is_default = x.key === t.key;
        }
    }

    partName(id) {
        const p = this.state.form.choices.car_parts.find((x) => x.id === id);
        return p ? p.name : "";
    }

    templateChoices(t) {
        return this.state.form.choices.car_parts.filter((p) => !t.component_ids.includes(p.id));
    }

    addTemplatePart(t, ev) {
        const id = parseInt(ev.target.value, 10);
        if (Number.isFinite(id) && !t.component_ids.includes(id)) {
            t.component_ids.push(id);
        }
        ev.target.value = "";
    }

    removeTemplatePart(t, id) {
        t.component_ids = t.component_ids.filter((x) => x !== id);
    }

    async saveForm() {
        const f = this.state.form;
        if (!(f.name || "").trim()) {
            this.notification.add(_t("أدخل اسم المكوّن أولاً."), { type: "warning" });
            return;
        }
        const grades = this.state.data.grades.map((g) => g.id);
        const restricted = grades.some((id) => !f.tint.allowed_ids.includes(id));
        const payload = {
            id: f.id, type: f.type, name: f.name, code: f.code,
            auto_product: f.autoProduct, product_id: f.product ? f.product.id : false,
            priority: parseInt(digits(f.priority) || "0", 10),
            option_ids: f.option_ids, options_required: f.options_required,
            notes: f.notes, warning_msg: f.warning_msg,
            templates: f.type === "service_area"
                ? f.templates.map((t) => ({ id: t.id, name: t.name, is_default: t.is_default, component_ids: t.component_ids }))
                : [],
        };
        if (this.formNeedsTint) {
            payload.tint = { default_grade_id: f.tint.default_grade_id, allowed_ids: restricted ? f.tint.allowed_ids : [] };
        }
        const data = await this.call("wof_component_save", [payload]);
        if (data) {
            this.setData(data);
            this.notification.add(f.id ? _t("حُفظ تعديل المكوّن.") : _t("أُنشئ المكوّن وأُضيف للفيلم."), { type: "success" });
            this.state.form = null;
        }
    }

    gradeName(id) {
        const grade = this.state.data.grades.find((g) => g.id === id);
        return grade ? grade.name : "";
    }

    componentMeta(c) {
        if (c.type === "service_area") {
            return `${c.template || _t("بدون نموذج")} · ${c.kids.length} ${_t("أجزاء")}`;
        }
        if (!this.needsTint) {
            return c.code || "";
        }
        const def = c.default_grade_id ? `${_t("الدرجة الافتراضية")} ${this.gradeName(c.default_grade_id)}` : _t("بدون درجة افتراضية");
        const allowed = c.allowed_ids.length ? `${_t("مسموح:")} ${c.allowed_ids.map((id) => this.gradeName(id)).join(" · ")}` : _t("كل الدرجات مسموحة");
        return `${def} · ${allowed}`;
    }

    toggleTint(c) {
        if (this.state.tintEdit && this.state.tintEdit.line_id === c.line_id) {
            this.state.tintEdit = null;
            return;
        }
        this.startTint(c);
    }

    isTplOpen(c, tp) {
        const key = `${c.line_id}:${tp.id}`;
        return this.state.tplOpen[key] !== false;
    }

    toggleTpl(c, tp) {
        const key = `${c.line_id}:${tp.id}`;
        this.state.tplOpen[key] = !this.isTplOpen(c, tp);
    }

    // drag-and-drop ordering from the handle before the name
    onDragStart(c, ev) {
        this.state.drag = { id: c.line_id, over: null, after: false };
        if (ev.dataTransfer) {
            ev.dataTransfer.effectAllowed = "move";
            ev.dataTransfer.setData("text/plain", String(c.line_id));
            const row = ev.target.closest(".wof_fe_comp");
            if (row) {
                ev.dataTransfer.setDragImage(row, 40, 30);
            }
        }
    }

    onDragOver(c, ev) {
        const drag = this.state.drag;
        if (!drag) {
            return;
        }
        ev.preventDefault();
        const rect = ev.currentTarget.getBoundingClientRect();
        drag.over = c.line_id;
        drag.after = ev.clientY > rect.top + rect.height / 2;
    }

    dropClass(c) {
        const drag = this.state.drag;
        if (!drag || drag.over !== c.line_id || drag.id === c.line_id) {
            return "";
        }
        return drag.after ? " is-drop-after" : " is-drop-before";
    }

    async onDrop(ev) {
        ev.preventDefault();
        const drag = this.state.drag;
        this.state.drag = null;
        if (!drag || drag.over === null || drag.over === drag.id) {
            return;
        }
        const ids = this.state.data.components.map((x) => x.line_id).filter((id) => id !== drag.id);
        let index = ids.indexOf(drag.over);
        if (drag.after) {
            index += 1;
        }
        ids.splice(index, 0, drag.id);
        await this.apply("comp_reorder", { line_ids: ids });
    }

    onDragEnd() {
        this.state.drag = null;
    }

    onHandleKey(c, ev) {
        // Keyboard alternative to dragging.
        if (ev.key === "ArrowUp" || ev.key === "ArrowDown") {
            ev.preventDefault();
            return this.apply("comp_move", { line_id: c.line_id, direction: ev.key === "ArrowUp" ? "up" : "down" });
        }
    }

    startTint(c) {
        this.state.picker.open = false;
        const all = this.state.data.grades.map((g) => g.id);
        // No restriction is stored as an empty list: show it as every grade selected.
        const allowed = c.allowed_ids.length ? c.allowed_ids.filter((id) => all.includes(id)) : all;
        this.state.tintEdit = { line_id: c.line_id, default_grade_id: c.default_grade_id || false, allowed_ids: allowed };
    }

    onDefaultGrade(ev) {
        const id = parseInt(ev.target.value, 10);
        this.state.tintEdit.default_grade_id = Number.isFinite(id) ? id : false;
    }

    toggleAllowed(id) {
        const edit = this.state.tintEdit;
        if (edit.allowed_ids.includes(id)) {
            if (edit.allowed_ids.length === 1) {
                this.notification.add(_t("اترك درجة واحدة مسموحة على الأقل."), { type: "warning" });
                return;
            }
            edit.allowed_ids = edit.allowed_ids.filter((x) => x !== id);
            if (edit.default_grade_id === id) {
                edit.default_grade_id = false;
            }
        } else {
            edit.allowed_ids = [...edit.allowed_ids, id];
        }
    }

    async saveTint() {
        const edit = this.state.tintEdit;
        const all = this.state.data.grades.map((g) => g.id);
        const restricted = all.some((id) => !edit.allowed_ids.includes(id));
        const payload = { ...edit, allowed_ids: restricted ? edit.allowed_ids : [] };
        if (await this.apply("comp_tint", payload)) {
            this.state.tintEdit = null;
        }
    }

    // ---------------------------------------------------------- policies
    get policyCards() {
        const d = this.state.data;
        const p = d.policies;
        const sizeNames = (ids) => d.sizes.filter((s) => ids.includes(s.id)).map((s) => s.name).join("، ") || "—";
        const taxName = (enabled, id) => (!enabled ? _t("بدون ضريبة") : ((d.taxes.find((t) => t.id === id) || {}).name || _t("لم تُحدد ضريبة")));
        const ev = { delivery: _t("عند إنجاز الأمر"), invoice: _t("عند ترحيل الفاتورة") };
        const calc = { fixed: _t("موحدة"), by_size: _t("حسب الحجم") };
        const price = { fixed: _t("سعر موحد لكل الأحجام"), by_size: _t("سعر حسب حجم السيارة") };
        const disc = (enabled, limit) => (enabled ? `${_t("مسموح حتى")} ${limit}%` : _t("غير مسموح"));
        return [
            { key: "sizes", name: _t("أحجام السيارات"), custom: p.sizes.custom, system: sizeNames(p.sizes.system), value: sizeNames(p.sizes.value), hint: _t("الأحجام المختارة هي أعمدة المصفوفة لهذا الفيلم.") },
            { key: "pricing", name: _t("سياسة التسعير"), custom: p.pricing.custom, system: price[p.pricing.system], value: price[p.pricing.value], hint: _t("بعد تغيير السياسة راجع الأسعار في المصفوفة.") },
            { key: "tax", name: _t("الضريبة"), custom: p.tax.custom, system: taxName(p.tax.system_enabled, p.tax.system_tax_id), value: taxName(p.tax.enabled, p.tax.tax_id), hint: _t("الضريبة الشاملة تجعل السعر المدخل شاملًا الضريبة.") },
            { key: "commission", name: _t("العمولة"), custom: p.commission.custom, system: `${ev[p.commission.system_event]} · ${calc[p.commission.system_calc]}`, value: `${ev[p.commission.event]} · ${calc[p.commission.calc]}`, hint: _t("نوع وقيمة العمولة لكل مكوّن تُضبط في المصفوفة.") },
            { key: "discount", name: _t("الخصم"), custom: p.discount.custom, system: disc(p.discount.system_enabled, p.discount.system_limit), value: disc(p.discount.enabled, p.discount.limit), hint: _t("حد الخصم لكل مكوّن يمكن ضبطه في المصفوفة.") },
        ];
    }

    policyPayload(key, overrides = {}) {
        const p = this.state.data.policies;
        const base = {
            sizes: { size_ids: p.sizes.value },
            pricing: { value: p.pricing.value },
            tax: { enabled: p.tax.enabled, tax_id: p.tax.tax_id || p.tax.system_tax_id },
            commission: { event: p.commission.event, calc: p.commission.calc },
            discount: { enabled: p.discount.enabled, limit: p.discount.limit },
        }[key];
        return { key, custom: true, ...base, ...overrides };
    }

    togglePolicy(card) {
        if (card.custom) {
            return this.apply("policy", { key: card.key, custom: false });
        }
        return this.apply("policy", this.policyPayload(card.key));
    }

    setPolicy(key, overrides) {
        return this.apply("policy", this.policyPayload(key, overrides));
    }

    toggleSize(id) {
        const ids = this.state.data.policies.sizes.value;
        const next = ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id];
        if (!next.length) {
            this.notification.add(_t("اختر حجم سيارة واحدًا على الأقل."), { type: "warning" });
            return;
        }
        return this.setPolicy("sizes", { size_ids: next });
    }

    onTaxSelect(ev) {
        const id = parseInt(ev.target.value, 10);
        return this.setPolicy("tax", { enabled: true, tax_id: Number.isFinite(id) ? id : false });
    }

    commitDiscountLimit() {
        const value = num(this.state.discountLimit);
        if (value === null || value < 0 || value > 100) {
            this.notification.add(_t("حد الخصم يجب أن يكون بين 0 و100."), { type: "warning" });
            this.state.discountLimit = String(this.state.data.policies.discount.limit);
            return;
        }
        if (value !== this.state.data.policies.discount.limit) {
            return this.setPolicy("discount", { enabled: true, limit: value });
        }
    }

    // ------------------------------------------------------------- price
    openMatrix() {
        return this.action.doAction({
            type: "ir.actions.client", tag: "wof_pricing_matrix", target: "current",
            params: { film_id: this.filmId, editor: true },
        });
    }

    pct(done) {
        const total = this.readiness.components;
        return total ? Math.round((done / total) * 100) : 0;
    }

    // ------------------------------------------------------------ review
    activate() {
        if (this.readiness.ready) {
            return this.apply("activate").then((ok) => ok && this.notification.add(`${this.film.name} ${_t("أصبح جاهزًا في أوامر التركيب.")}`, { type: "success" }));
        }
    }

    deactivate() {
        return this.apply("deactivate");
    }
}

registry.category("actions").add("wof_film_editor", WofFilmEditor);
