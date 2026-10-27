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
    async search(query) {
        const results = await this.orm.call(MODEL, "wof_film_parts_search", [[this.filmId]], { query: query || "" });
        this.state.picker.results = results || [];
    }

    openPicker() {
        this.state.picker.open = true;
        this.state.tintEdit = null;
        this.search(this.state.picker.query);
    }

    onPickerInput(ev) {
        this.state.picker.query = ev.target.value;
        this.state.picker.open = true;
        this.search(ev.target.value);
    }

    onPickerKey(ev) {
        if (ev.key === "Escape") {
            ev.stopPropagation();
            this.state.picker.open = false;
        }
    }

    async addPart(part) {
        if (await this.apply("comp_add", { part_id: part.id })) {
            this.state.picker.query = "";
            this.state.picker.open = false;
        }
    }

    newComponent() {
        this.state.picker.open = false;
        return this.action.doAction({
            type: "ir.actions.act_window", name: _t("مكوّن جديد"), res_model: "wof.car.parts",
            views: [[false, "form"]], target: "new",
        }, {
            onClose: async () => this.setData(await this.orm.call(MODEL, "wof_film_load", [[this.filmId]])),
        });
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

    startTint(c) {
        this.state.picker.open = false;
        this.state.tintEdit = { line_id: c.line_id, default_grade_id: c.default_grade_id || false, allowed_ids: [...c.allowed_ids] };
    }

    toggleAllowed(id) {
        const edit = this.state.tintEdit;
        edit.allowed_ids = edit.allowed_ids.includes(id) ? edit.allowed_ids.filter((x) => x !== id) : [...edit.allowed_ids, id];
    }

    async saveTint() {
        if (await this.apply("comp_tint", this.state.tintEdit)) {
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
