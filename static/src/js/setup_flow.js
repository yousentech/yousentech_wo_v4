/** @odoo-module **/

import { Component, onMounted, onWillStart, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

const MODEL = "wof.company.profile";

// UI steps; operations is split into short screens that all map to the server step "operations".
const STEPS = [
    { key: "activity", name: "الأنشطة", kind: "main", server: "activity" },
    { key: "sizes", name: "أحجام السيارات", kind: "main", server: "sizes" },
    { key: "tint", name: "درجات اللون", kind: "main", server: "services", tintOnly: true },
    { key: "ops", name: "التشغيل", kind: "head" },
    { key: "fields", name: "بيانات أمر التركيب", kind: "sub", server: "operations" },
    { key: "tax", name: "الضريبة والأسعار", kind: "sub", server: "operations" },
    { key: "invoice", name: "الفوترة", kind: "sub", server: "operations" },
    { key: "discount", name: "الخصومات", kind: "sub", server: "operations" },
    { key: "tech", name: "الفنيون والعمولة", kind: "sub", server: "operations" },
    { key: "review", name: "المراجعة والتفعيل", kind: "main", server: "review" },
];
const OPS = ["fields", "tax", "invoice", "discount", "tech"];
const ISSUE_STEP = {
    SETUP_ACTIVITY_REQUIRED: "activity",
    SETUP_SIZE_REQUIRED: "sizes",
    SETUP_TINT_METHOD_REQUIRED: "tint",
    SETUP_TINT_SHADE_REQUIRED: "tint",
    SETUP_OPERATION_TAX_REQUIRED: "tax",
};
const TINT_SAMPLES = {
    sequential: ["00", "01", "02", "03", "04"],
    percentage: ["00", "30", "50", "75", "100"],
};

const num = (value) => {
    const normalized = String(value ?? "")
        .replace(/[٠-٩]/g, (d) => String("٠١٢٣٤٥٦٧٨٩".indexOf(d)))
        .replace(/٫/g, ".")
        .replace(/[,\s%]/g, "");
    const parsed = parseFloat(normalized);
    return Number.isFinite(parsed) ? parsed : null;
};
const fmt = (value) => Number(value || 0).toLocaleString("en-US", { maximumFractionDigits: 2 });

export class WofSetupFlow extends Component {
    static template = "yousentech_wo_v4.SetupFlow";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.root = useRef("root");
        const params = (this.props.action && this.props.action.params) || {};
        this.profileId = params.profile_id;
        this.state = useState({
            data: null,
            step: "activity",
            visited: [],
            busy: false,
            adding: null,
            draft: { name: "", code: "" },
            editing: null,
            editValue: "",
            discount: { limit: "", reason: "" },
        });
        this.fmt = fmt;
        onWillStart(async () => {
            const data = await this.orm.call(MODEL, "wof_flow_load", [[this.profileId]]);
            this.setData(data);
            const start = this.uiStepFromServer(data.step);
            const flow = this.flow;
            this.state.step = start;
            this.state.visited = flow.slice(0, flow.indexOf(start) + 1);
        });
        onMounted(() => {
            // The guided screen has its own footer; hide the dialog's default "Ok" bar.
            const content = this.root.el && this.root.el.closest(".modal-content");
            const footer = content && content.querySelector(":scope > .modal-footer");
            if (footer) {
                footer.classList.add("d-none");
            }
        });
    }

    setData(data) {
        this.state.data = data;
        this.state.discount = {
            limit: fmt(data.discount.limit),
            reason: fmt(data.discount.reason_from),
        };
    }

    // ---------------------------------------------------------------- server
    async apply(op, payload = {}) {
        if (this.state.busy) {
            return false;
        }
        this.state.busy = true;
        try {
            const data = await this.orm.call(MODEL, "wof_flow_apply", [[this.profileId], op, payload]);
            this.setData(data);
            return true;
        } catch (error) {
            const message = (error && error.data && error.data.message) || (error && error.message) || _t("تعذر حفظ التغيير.");
            this.notification.add(message, { type: "danger" });
            return false;
        } finally {
            this.state.busy = false;
        }
    }

    // ------------------------------------------------------------------ flow
    get hasTint() {
        return this.state.data.activities.some((a) => a.type === "tint" && a.selected);
    }

    get steps() {
        return STEPS.filter((s) => !s.tintOnly || this.hasTint);
    }

    get flow() {
        return this.steps.filter((s) => s.kind !== "head").map((s) => s.key);
    }

    get current() {
        return this.flow.includes(this.state.step) ? this.state.step : "activity";
    }

    uiStepFromServer(step) {
        if (step === "services") {
            return this.hasTint ? "tint" : "fields";
        }
        if (step === "operations") {
            return "fields";
        }
        return ["activity", "sizes", "review"].includes(step) ? step : "activity";
    }

    stepOf(key) {
        return STEPS.find((s) => s.key === key);
    }

    async go(key) {
        if (!this.flow.includes(key) || this.state.busy) {
            return;
        }
        this.state.adding = null;
        this.state.editing = null;
        const target = this.stepOf(key).server;
        if (target !== this.state.data.step) {
            if (!(await this.apply("goto", { step: target }))) {
                return;
            }
        }
        this.state.step = key;
        if (!this.state.visited.includes(key)) {
            this.state.visited.push(key);
        }
        const body = this.root.el && this.root.el.querySelector(".wof_sf_main");
        if (body) {
            body.scrollTop = 0;
        }
    }

    get nextKey() {
        const flow = this.flow;
        return flow[flow.indexOf(this.current) + 1];
    }

    get prevKey() {
        const flow = this.flow;
        return flow[flow.indexOf(this.current) - 1];
    }

    next() {
        if (!this.info[this.current].block && this.nextKey) {
            this.go(this.nextKey);
        }
    }

    prev() {
        if (this.prevKey) {
            this.go(this.prevKey);
        }
    }

    close() {
        this.action.doAction({ type: "ir.actions.act_window_close" });
    }

    // ------------------------------------------------------------ readiness
    get issues() {
        return (this.state.data.issues || []).map((issue) => ({
            ...issue,
            step: ISSUE_STEP[issue.code] || "review",
        })).filter((issue) => issue.step !== "tint" || this.hasTint);
    }

    get info() {
        const d = this.state.data;
        const acts = d.activities.filter((a) => a.selected).length;
        const sizes = d.sizes.filter((s) => s.selected).length;
        const shades = d.tint.shades.filter((s) => s.selected).length;
        const count = (state) => d.fields.filter((f) => f.state === state).length;
        const tax = this.selectedTax;
        const issueFor = (step) => this.issues.find((i) => i.step === step);
        const entry = (step, sub, block) => {
            const issue = issueFor(step);
            return { ok: !issue, sub, issue: issue ? issue.message : "", block: !!block };
        };
        return {
            activity: entry("activity", acts ? (acts === 1 ? _t("نشاط واحد") : `${acts} ${_t("أنشطة")}`) : _t("لم تختر نشاطًا"), !acts),
            sizes: entry("sizes", `${sizes} ${_t("أحجام")}`, !sizes),
            tint: entry("tint", `${shades} ${_t("درجات")} · ${d.tint.method === "percentage" ? _t("بالنسب") : _t("تسلسلي")}`, !shades),
            fields: entry("fields", `${count("req")} ${_t("إجبارية")} · ${count("hid")} ${_t("مخفية")}`),
            tax: entry("tax", !d.tax.enabled ? _t("بدون ضريبة") : (tax ? tax.name : _t("اختر الضريبة"))),
            invoice: entry("invoice", { manual: _t("يدويًا"), auto: _t("عند التأكيد"), after: _t("بعد اكتمال الدفع") }[d.invoice]),
            discount: entry("discount", d.discount.enabled ? `${_t("حتى")} ${fmt(d.discount.limit)}%` : _t("موقوف")),
            tech: entry("tech", d.tech.event === "invoice" ? _t("العمولة عند الفاتورة") : _t("العمولة عند الإنجاز")),
            review: {
                ok: !this.issues.length,
                sub: d.state === "ready" ? _t("مفعّل") : (this.issues.length ? `${_t("ينقص")} ${this.issues.length}` : _t("جاهز للتفعيل")),
                issue: "",
                block: false,
            },
        };
    }

    get rail() {
        const info = this.info;
        const cur = this.current;
        const visited = this.state.visited;
        let n = 0;
        return this.steps.map((s) => {
            if (s.kind === "head") {
                n += 1;
                const inOps = OPS.includes(cur);
                const warn = OPS.some((k) => !info[k].ok) && !inOps;
                const done = OPS.every((k) => info[k].ok && visited.includes(k)) && !inOps;
                return {
                    key: s.key, name: s.name, sub: "", num: n, kind: "head", isCur: false, target: "fields",
                    dot: warn ? "warn" : (done ? "done" : (inOps ? "cur" : "todo")),
                };
            }
            if (s.kind === "main") {
                n += 1;
            }
            const isCur = s.key === cur;
            const seen = visited.includes(s.key);
            const ok = info[s.key].ok;
            const warn = !ok && (seen || s.key === "tax") && !isCur;
            const done = ok && seen && !isCur && s.key !== "review";
            return {
                key: s.key, name: s.name, sub: info[s.key].sub, num: n, kind: s.kind, isCur, target: s.key,
                warnSub: !ok && (seen || s.key === "tax"),
                dot: isCur ? "cur" : (warn ? "warn" : (done ? "done" : "todo")),
            };
        });
    }

    get progress() {
        const keys = this.flow.filter((k) => k !== "review");
        const done = keys.filter((k) => this.info[k].ok && this.state.visited.includes(k)).length;
        return { done, total: keys.length, pct: Math.round((done / keys.length) * 100) };
    }

    get footer() {
        const d = this.state.data;
        const cur = this.current;
        if (cur === "review") {
            if (d.state === "ready") {
                return { warn: false, text: _t("النظام مفعّل") };
            }
            return this.issues.length
                ? { warn: true, text: `${_t("أكمل")} ${this.issues.length} ${_t("قبل التفعيل")}` }
                : { warn: false, text: _t("جاهز للتفعيل") };
        }
        const info = this.info[cur];
        return info.ok ? { warn: false, text: _t("هذه الخطوة مكتملة") } : { warn: true, text: info.issue };
    }

    get nextLabel() {
        const step = this.stepOf(this.nextKey);
        return step ? `${_t("التالي:")} ${step.name}` : "";
    }

    // ------------------------------------------------------------ add / edit
    startAdd(kind) {
        this.state.editing = null;
        this.state.adding = kind;
        this.state.draft = { name: "", code: "" };
    }

    cancelAdd() {
        this.state.adding = null;
    }

    async confirmAdd() {
        const kind = this.state.adding;
        const name = (this.state.draft.name || "").trim();
        if (!name) {
            this.notification.add(_t("اكتب الاسم أولًا."), { type: "warning" });
            return;
        }
        const ok = kind === "activity"
            ? await this.apply("activity_add", { name })
            : await this.apply("size_add", { name, code: (this.state.draft.code || "").trim() });
        if (ok) {
            this.state.adding = null;
        }
    }

    onDraft(field, ev) {
        let value = ev.target.value;
        if (field === "code") {
            value = value.toUpperCase().replace(/[^A-Z0-9._-]/g, "");
            ev.target.value = value;
        }
        this.state.draft[field] = value;
    }

    startEdit(kind, id, value) {
        this.state.adding = null;
        this.state.editing = `${kind}:${id}`;
        this.state.editValue = value;
    }

    isEditing(kind, id) {
        return this.state.editing === `${kind}:${id}`;
    }

    async confirmEdit(kind, id) {
        const value = (this.state.editValue || "").trim();
        const ok = kind === "shade"
            ? await this.apply("shade", { id, value })
            : await this.apply(kind, { id, name: value });
        if (ok) {
            this.state.editing = null;
        }
    }

    onKey(ev, submit, cancel) {
        if (ev.key === "Enter") {
            ev.preventDefault();
            submit();
        } else if (ev.key === "Escape") {
            ev.preventDefault();
            ev.stopPropagation();
            cancel();
        }
    }

    // --------------------------------------------------------------- steps
    toggleActivity(a) {
        return this.apply("activity", { id: a.id, selected: !a.selected });
    }

    get activityEffects() {
        const d = this.state.data;
        const effects = [];
        effects.push(this.hasTint
            ? _t("ستظهر خطوة «درجات اللون» لتحدد الدرجات المعتمدة في محلك.")
            : _t("لن تظهر خطوة «درجات اللون» لأن العزل الحراري غير مفعّل."));
        if (d.activities.some((a) => a.type === "general" && a.is_default && a.selected)) {
            effects.push(_t("تضيف تحت «نشاط عام» أفلام الحماية والنانو والخدمات بدون ألوان."));
        }
        for (const a of d.activities.filter((x) => !x.is_default && x.selected)) {
            effects.push(`«${a.name}» ${_t("يظهر كقسم مستقل في بوابة الأنشطة.")}`);
        }
        if (!d.activities.some((a) => a.selected)) {
            effects.push(_t("اختر نشاطًا واحدًا على الأقل للمتابعة."));
        }
        return effects;
    }

    toggleSize(s) {
        return this.apply("size", { id: s.id, selected: !s.selected });
    }

    get activeSizes() {
        return this.state.data.sizes.filter((s) => s.selected);
    }

    setTintMethod(method) {
        if (this.state.data.tint.locked || method === this.state.data.tint.method) {
            return;
        }
        return this.apply("tint_method", { method });
    }

    get tintMethods() {
        const cur = this.state.data.tint.method;
        return [
            { key: "sequential", name: _t("ترقيم تسلسلي") },
            { key: "percentage", name: _t("ترقيم بالنسب") },
        ].map((m) => ({
            ...m,
            on: m.key === cur,
            sample: TINT_SAMPLES[m.key].map((v, i) => ({ v, style: this.shadeStyle(m.key, v, i) })),
        }));
    }

    shadeStyle(method, value, index) {
        const t = method === "percentage" ? parseInt(value, 10) / 100 : index / 4;
        // 00 is clear (light), higher numbers are darker film.
        const light = Math.round(92 - (Number.isFinite(t) ? t : 0.5) * 78);
        return `background: hsl(190, 8%, ${light}%)`;
    }

    shadeStyleAt(shade, index) {
        return this.shadeStyle(this.state.data.tint.method, shade.value, index);
    }

    get shadeCount() {
        const shades = this.state.data.tint.shades;
        return { on: shades.filter((s) => s.selected).length, total: shades.length };
    }

    toggleShade(s) {
        return this.apply("shade", { id: s.id, selected: !s.selected });
    }

    setField(f, state) {
        if (f.state !== state) {
            return this.apply("field", { id: f.id, state });
        }
    }

    get visibleFields() {
        return this.state.data.fields.filter((f) => f.state !== "hid");
    }

    get hiddenFieldNames() {
        return this.state.data.fields.filter((f) => f.state === "hid").map((f) => f.label).join("، ");
    }

    get selectedTax() {
        const tax = this.state.data.tax;
        return tax.enabled && tax.tax_id ? tax.options.find((o) => o.id === tax.tax_id) : null;
    }

    get taxPreview() {
        const tax = this.selectedTax;
        if (!tax) {
            return null;
        }
        const rate = tax.amount_type === "percent" ? tax.amount : null;
        if (rate === null) {
            return { title: tax.price_include ? _t("تكتب السعر شاملًا الضريبة") : _t("تكتب السعر قبل الضريبة"), flow: [] };
        }
        if (tax.price_include) {
            const net = 1000 / (1 + rate / 100);
            return {
                title: _t("تكتب السعر شاملًا الضريبة"),
                flow: [
                    { k: _t("تكتب السعر"), v: fmt(1000) },
                    { k: `${_t("منه ضريبة")} ${fmt(rate)}%`, v: fmt(1000 - net) },
                    { k: _t("يدفع العميل"), v: fmt(1000) },
                ],
            };
        }
        return {
            title: _t("تكتب السعر قبل الضريبة"),
            flow: [
                { k: _t("تكتب السعر"), v: fmt(1000) },
                { k: `${_t("تُضاف ضريبة")} ${fmt(rate)}%`, v: fmt((1000 * rate) / 100) },
                { k: _t("يدفع العميل"), v: fmt(1000 + (1000 * rate) / 100) },
            ],
        };
    }

    setScalar(name, value) {
        return this.apply("set", { [name]: value });
    }

    onTaxChange(ev) {
        const id = parseInt(ev.target.value, 10);
        return this.setScalar("operation_tax_id", Number.isFinite(id) ? id : false);
    }

    get pricingOptions() {
        const sizes = this.activeSizes.slice(0, 3);
        const example = sizes.length
            ? sizes.map((s, i) => `${s.name} ${350 + i * 50}`).join(" · ")
            : _t("فعّل الأحجام أولًا");
        return [
            {
                key: "fixed", name: _t("سعر موحد لكل الأحجام"),
                desc: _t("نفس السعر لأي سيارة. الأسهل إذا لم يختلف سعرك حسب الحجم."),
                ex: `${_t("مثال:")} ${_t("الزجاج الأمامي 400 لكل السيارات")}`,
            },
            {
                key: "by_size", name: _t("سعر حسب حجم السيارة"),
                desc: _t("سعر لكل حجم فعّلته في خطوة أحجام السيارات."),
                ex: `${_t("مثال:")} ${example}`,
            },
        ];
    }

    get invoiceOptions() {
        return [
            { key: "manual", name: _t("يدويًا"), desc: _t("الموظف ينشئ الفاتورة عند الحاجة من أمر التركيب.") },
            { key: "auto", name: _t("تلقائيًا عند تأكيد الأمر"), desc: _t("تُنشأ الفاتورة فور تأكيد أمر التركيب.") },
            { key: "after", name: _t("بعد اكتمال الدفع فقط"), desc: _t("لا يمكن إنشاء الفاتورة قبل سداد المبلغ كاملًا.") },
        ];
    }

    get journey() {
        const at = { manual: -1, auto: 0, after: 2 }[this.state.data.invoice];
        return [_t("تأكيد الأمر"), _t("التركيب والتسليم"), _t("اكتمال الدفع")].map((name, i) => ({
            name,
            pin: at === i ? "here" : (at === -1 ? "any" : "none"),
        }));
    }

    setInvoice(mode) {
        if (mode !== this.state.data.invoice) {
            return this.apply("invoice", { mode });
        }
    }

    onDiscountInput(field, ev) {
        this.state.discount[field] = ev.target.value;
    }

    async commitDiscount(field) {
        const value = num(this.state.discount[field]);
        const name = field === "limit" ? "discount_default_limit" : "discount_reason_required_from";
        const current = field === "limit" ? this.state.data.discount.limit : this.state.data.discount.reason_from;
        if (value === null || value < 0 || value > 100) {
            this.notification.add(_t("النسبة يجب أن تكون بين 0 و100."), { type: "warning" });
            this.state.discount[field] = fmt(current);
            return;
        }
        if (value !== current) {
            await this.setScalar(name, value);
        }
    }

    get discountZones() {
        const d = this.state.data.discount;
        const limit = Math.max(0, d.limit || 0);
        const reason = Math.min(Math.max(0, d.reason_from || 0), limit);
        const scale = Math.max(limit * 1.5, limit + 5, 10);
        const pct = (v) => Math.max(0, (v / scale) * 100);
        return [
            { cls: "ok", w: pct(reason), range: `0% – ${fmt(reason)}%`, text: _t("خصم مباشر بدون سبب") },
            { cls: "warn", w: pct(limit - reason), range: `${fmt(reason)}% – ${fmt(limit)}%`, text: _t("مسموح مع كتابة السبب") },
            {
                cls: d.override ? "lock" : "off", w: 100 - pct(limit), range: `${_t("أكثر من")} ${fmt(limit)}%`,
                text: d.override ? _t("يحتاج موافقة من لديه صلاحية تجاوز السعر") : _t("غير مسموح"),
            },
        ].filter((z) => z.w > 0.01);
    }

    get eventOptions() {
        return [
            { key: "delivery", name: _t("عند إنجاز أمر التركيب"), desc: _t("يستحق الفني عمولته بمجرد إنجاز العمل، حتى قبل ترحيل الفاتورة.") },
            { key: "invoice", name: _t("عند ترحيل الفاتورة"), desc: _t("لا تُحتسب العمولة إلا بعد ترحيل الفاتورة.") },
        ];
    }

    // --------------------------------------------------------------- review
    get summary() {
        const d = this.state.data;
        const info = this.info;
        return this.flow.filter((k) => k !== "review").map((k) => {
            let text = info[k].sub;
            if (k === "activity") {
                text = d.activities.filter((a) => a.selected).map((a) => a.name).join("، ") || _t("لا يوجد");
            } else if (k === "sizes") {
                text = this.activeSizes.map((s) => s.name).join("، ") || _t("لا يوجد");
            }
            return { key: k, name: this.stepOf(k).name, text, ok: info[k].ok };
        });
    }

    get locked() {
        const d = this.state.data;
        const rows = [`${_t("أكواد الأحجام:")} ${this.activeSizes.map((s) => s.code).join(" · ") || "—"}`];
        if (this.hasTint) {
            const shades = d.tint.shades.filter((s) => s.selected).map((s) => s.value).join(" · ");
            rows.push(`${_t("ترقيم درجات اللون:")} ${d.tint.method === "percentage" ? _t("بالنسب") : _t("تسلسلي")} (${shades})`);
        }
        return rows;
    }

    async activate() {
        if (this.issues.length) {
            return;
        }
        if (await this.apply("activate")) {
            this.notification.add(_t("تم تفعيل النظام."), { type: "success" });
        }
    }

    async openActivities() {
        const action = await this.orm.call(MODEL, "action_go_to_activities", [[this.profileId]]);
        return this.action.doAction(action);
    }
}

registry.category("actions").add("wof_setup_flow", WofSetupFlow);
