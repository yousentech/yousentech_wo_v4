/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { browser } from "@web/core/browser/browser";
import { activityColor, previousCrumbs } from "./hero_nav";

const num = (value) => {
    if (value === null || value === undefined || value === "") {
        return null;
    }
    const normalized = String(value)
        .replace(/[٠-٩]/g, (d) => String("٠١٢٣٤٥٦٧٨٩".indexOf(d)))
        .replace(/٫/g, ".")
        .replace(/[,\s]/g, "");
    const parsed = parseFloat(normalized);
    return Number.isFinite(parsed) && parsed >= 0 ? parsed : null;
};

const fmt = (value) =>
    value === null || value === undefined
        ? "—"
        : Number(value).toLocaleString("en-US", { maximumFractionDigits: 2 });

export class WofPricingMatrix extends Component {
    static template = "yousentech_wo_v4.PricingMatrix";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.dialog = useService("dialog");
        this.notification = useService("notification");
        const params = (this.props.action && this.props.action.params) || {};
        this.filmId = params.film_id;
        this.wizardId = params.wizard_id || false;
        this.returnToEditor = !!params.editor;
        this.state = useState({
            loading: true,
            saving: false,
            dim: params.dim || "price",
            data: null,
            sel: null,
            sizeId: null,
            dirty: false,
            query: "",
            onlyMissing: false,
            side: "props",
        });
        this.fmt = fmt;
        onWillStart(async () => {
            await this.load();
            if (this.env.config && this.env.config.setDisplayName) {
                this.env.config.setDisplayName(_t("التسعير والعمولة"));
            }
        });
    }

    // ------------------------------------------------------------------ data
    async load() {
        const data = await this.orm.call("wof.film.category", "wof_matrix_load", [[this.filmId]]);
        this.applyData(data);
    }

    applyData(data) {
        for (const line of data.lines) {
            line.price.general = line.price.general || { amount: null, free: false, readonly: false };
            line.children = line.children || [];
        }
        this.state.data = data;
        this.state.loading = false;
        this.state.dirty = false;
        if (!this.state.sel || !this.findRow(this.state.sel)) {
            this.state.sel = data.lines.length ? `l:${data.lines[0].id}` : null;
        }
        if (!this.state.sizeId && data.sizes.length) {
            this.state.sizeId = data.sizes[Math.min(1, data.sizes.length - 1)].id;
        }
    }

    get data() {
        return this.state.data;
    }

    get sizes() {
        return this.data ? this.data.sizes : [];
    }

    get isBySize() {
        return this.data && this.data.film.pricing_policy === "by_size";
    }

    get currency() {
        return (this.data && this.data.film.currency) || "";
    }

    markDirty() {
        this.state.dirty = true;
    }

    // ------------------------------------------------------------- selection
    rowKey(line, child) {
        return child ? `c:${line.id}:${child.part_id}` : `l:${line.id}`;
    }

    findRow(key) {
        if (!this.data || !key) {
            return null;
        }
        const [kind, lineId, partId] = key.split(":");
        const line = this.data.lines.find((rec) => String(rec.id) === lineId);
        if (!line) {
            return null;
        }
        if (kind === "c") {
            const child = line.children.find((rec) => String(rec.part_id) === partId);
            return child ? { line, child } : null;
        }
        return { line, child: null };
    }

    get selected() {
        return this.findRow(this.state.sel) || (this.data && this.data.lines.length ? { line: this.data.lines[0], child: null } : null);
    }

    isSelected(line, child = null) {
        return this.state.sel === this.rowKey(line, child);
    }

    setDim(dim) {
        this.state.dim = dim;
        const sel = this.selected;
        if (dim === "price" && sel && sel.child) {
            this.state.sel = this.rowKey(sel.line);
        }
    }

    // ----------------------------------------------------------------- price
    priceMode(line) {
        const mode = line.price.mode;
        if (!this.isBySize) {
            return mode === "free" ? "free" : "uniform";
        }
        return mode;
    }

    priceModeOptions() {
        return this.isBySize
            ? [
                  ["size", _t("سعر لكل حجم")],
                  ["uniform", _t("نفس السعر لكل الأحجام")],
                  ["free", _t("مجاني لكل الأحجام")],
              ]
            : [
                  ["uniform", _t("سعر موحد")],
                  ["free", _t("مجاني")],
              ];
    }

    priceCell(line, size) {
        const key = String(size.id);
        if (!line.price.sizes[key]) {
            line.price.sizes[key] = { amount: null, free: false, readonly: false };
        }
        return line.price.sizes[key];
    }

    priceAt(line, sizeId) {
        const mode = this.priceMode(line);
        if (mode === "free") {
            return 0;
        }
        if (mode === "uniform") {
            return line.price.general.amount;
        }
        const cell = line.price.sizes[String(sizeId)] || {};
        return cell.free ? 0 : cell.amount === undefined ? null : cell.amount;
    }

    // A price of 0 is not a price: only the "free" flag makes a line cost nothing.
    isPriced(amount) {
        return amount !== null && amount !== undefined && amount > 0;
    }

    isZero(amount) {
        return amount === 0;
    }

    priceProblem(line) {
        const mode = this.priceMode(line);
        if (mode === "free") {
            return null;
        }
        const amounts = mode === "uniform"
            ? [line.price.general.amount]
            : this.sizes.map((size) => this.priceCell(line, size)).filter((cell) => !cell.free).map((cell) => cell.amount);
        if (amounts.some((a) => this.isZero(a))) {
            return "zero";
        }
        if (amounts.some((a) => !this.isPriced(a))) {
            return "missing";
        }
        return null;
    }

    priceComplete(line) {
        return !this.priceProblem(line);
    }

    priceKind(line, sizeId) {
        const mode = this.priceMode(line);
        if (mode === "free") {
            return "free";
        }
        if (mode !== "uniform") {
            const cell = line.price.sizes[String(sizeId)] || {};
            if (cell.free) {
                return "free";
            }
        }
        const amount = this.priceAt(line, sizeId);
        if (this.isZero(amount)) {
            return "zero";
        }
        return this.isPriced(amount) ? "price" : "missing";
    }

    // Switching the method carries forward exactly what the user sees, never
    // older values hidden in the other method's cells.
    onPriceMode(line, ev) {
        const mode = ev.target.value;
        const prev = this.priceMode(line);
        if (mode === prev) {
            return;
        }
        const general = line.price.general;
        const cells = this.sizes.map((size) => this.priceCell(line, size));
        if (mode === "uniform") {
            const first = prev === "size" ? cells.find((cell) => !cell.free && cell.amount !== null && cell.amount !== undefined) : null;
            general.amount = first ? first.amount : null;
            general.readonly = first ? Boolean(first.readonly) : false;
        } else if (mode === "size") {
            for (const cell of cells) {
                cell.free = false;
                cell.amount = prev === "uniform" ? general.amount : null;
                cell.readonly = prev === "uniform" ? Boolean(general.readonly) : false;
            }
        }
        line.price.mode = mode;
        general.free = mode === "free";
        this.markDirty();
    }

    onPriceCell(line, size, ev) {
        this.priceCell(line, size).amount = num(ev.target.value);
        this.markDirty();
    }

    onPriceGeneral(line, ev) {
        line.price.general.amount = num(ev.target.value);
        this.markDirty();
    }

    toggleFree(line, size) {
        const cell = this.priceCell(line, size);
        cell.free = !cell.free;
        if (cell.free) {
            cell.readonly = false;
        }
        this.markDirty();
    }

    toggleReadonly(line, size) {
        const cell = this.priceCell(line, size);
        if (!cell.free) {
            cell.readonly = !cell.readonly;
            this.markDirty();
        }
    }

    toggleGeneralReadonly(line) {
        line.price.general.readonly = !line.price.general.readonly;
        this.markDirty();
    }

    setPolicy(policy) {
        if (!this.data || this.data.film.pricing_policy === policy) {
            return;
        }
        if (policy === "by_size" && !this.sizes.length) {
            this.notification.add(_t("لا توجد أحجام سيارات مفعلة لهذا الفيلم."), { type: "warning" });
            return;
        }
        for (const line of this.data.lines) {
            const cells = this.sizes.map((size) => this.priceCell(line, size));
            if (policy === "fixed" && line.price.mode === "size") {
                // Per-size prices become one price: keep the first one the user entered.
                const first = cells.find((cell) => !cell.free && cell.amount !== null && cell.amount !== undefined);
                line.price.general.amount = first ? first.amount : null;
                line.price.general.readonly = first ? Boolean(first.readonly) : false;
                line.price.general.free = false;
                line.price.mode = "uniform";
            }
            if (policy === "by_size") {
                // One price becomes "same price for all sizes"; the cells mirror it.
                for (const cell of cells) {
                    cell.free = line.price.mode === "free";
                    cell.amount = line.price.mode === "free" ? 0 : line.price.general.amount;
                    cell.readonly = line.price.mode === "free" ? false : Boolean(line.price.general.readonly);
                }
            }
        }
        this.data.film.pricing_policy = policy;
        this.markDirty();
    }

    setDiscount(line, policy) {
        line.discount_policy = policy;
        this.markDirty();
    }

    onDiscountLimit(line, ev) {
        line.discount_limit = num(ev.target.value) || 0;
        this.markDirty();
    }

    // ------------------------------------------------------------ commission
    isArea(line) {
        return line.type === "service_area";
    }

    fromParts(line) {
        return this.isArea(line) && line.commission.source === "from_parts";
    }

    commMethod(line, child = null) {
        const comm = child ? child.commission : line.commission;
        if (!child && this.fromParts(line)) {
            return "parts";
        }
        return comm.policy === "by_size" ? "by_size" : "fixed";
    }

    commMethodOptions(line, child = null) {
        const base = [
            ["fixed", _t("عمولة موحدة")],
            ["by_size", _t("لكل حجم")],
        ];
        return !child && this.isArea(line) ? [["parts", _t("من أجزاء النموذج")], ...base] : base;
    }

    onCommMethod(line, child, ev) {
        const value = ev.target.value;
        const comm = child ? child.commission : line.commission;
        if (value === "parts") {
            if (!this.isArea(line) || child) {
                return;
            }
            comm.source = "from_parts";
            comm.distribution = "by_part";
        } else {
            if (!child && this.isArea(line)) {
                comm.source = "independent";
                if (comm.distribution === "by_part") {
                    comm.distribution = "equal";
                }
            }
            const prev = comm.policy === "by_size" ? "by_size" : "fixed";
            if (value === "by_size" && prev !== "by_size") {
                for (const size of this.sizes) {
                    comm.sizes[String(size.id)] = comm.general ?? null;
                }
            } else if (value === "fixed" && prev !== "fixed") {
                comm.general = this.sizes.map((size) => comm.sizes[String(size.id)]).find((v) => v !== null && v !== undefined) ?? null;
            }
            comm.policy = value;
        }
        this.markDirty();
    }

    onCommGeneral(comm, ev) {
        comm.general = num(ev.target.value);
        this.markDirty();
    }

    onCommCell(comm, size, ev) {
        comm.sizes[String(size.id)] = num(ev.target.value);
        this.markDirty();
    }

    setCommType(comm, type) {
        comm.type = type;
        this.markDirty();
    }

    setDistribution(comm, value) {
        comm.distribution = value;
        this.markDirty();
    }

    toggleCommReadonly(comm) {
        comm.readonly = !comm.readonly;
        this.markDirty();
    }

    setSource(line, source) {
        if (!this.isArea(line)) {
            return;
        }
        line.commission.source = source;
        line.commission.distribution = source === "from_parts" ? "by_part" : line.commission.distribution === "by_part" ? "equal" : line.commission.distribution;
        this.markDirty();
    }

    childValue(child, sizeId) {
        const comm = child.commission;
        const value = comm.policy === "by_size" ? comm.sizes[String(sizeId)] : comm.general;
        return value === undefined ? null : value;
    }

    commAt(line, sizeId, child = null) {
        if (child) {
            return this.childValue(child, sizeId);
        }
        if (this.fromParts(line)) {
            if (!line.children.length) {
                return null;
            }
            let total = 0;
            for (const rec of line.children) {
                const value = this.childValue(rec, sizeId);
                if (value === null) {
                    return null;
                }
                total += value;
            }
            return total;
        }
        const comm = line.commission;
        const value = comm.policy === "by_size" ? comm.sizes[String(sizeId)] : comm.general;
        if (value === null || value === undefined) {
            return null;
        }
        if (comm.type === "percent") {
            const price = this.priceAt(line, sizeId);
            return price === null ? null : (price * value) / 100;
        }
        return value;
    }

    derivedBySize(line) {
        return line.children.some((child) => child.commission.policy === "by_size");
    }

    commComplete(line) {
        if (this.fromParts(line)) {
            return line.children.length > 0 && line.children.every((child) => this.sizes.every((size) => this.childValue(child, size.id) !== null));
        }
        const comm = line.commission;
        if (comm.policy === "by_size") {
            return this.sizes.every((size) => comm.sizes[String(size.id)] !== null && comm.sizes[String(size.id)] !== undefined);
        }
        return comm.general !== null && comm.general !== undefined;
    }

    distributionOptions(line) {
        const base = [
            ["equal", _t("بالتساوي")],
            ["by_technician_ratio", _t("حسب نسبة الفني")],
        ];
        return this.fromParts(line) ? [...base, ["by_part", _t("حسب الجزء المنفذ")]] : base;
    }

    // -------------------------------------------------------------- summary
    // Long films: filter rows by name/code and by what is still missing.
    get visibleLines() {
        const lines = this.data ? this.data.lines : [];
        const q = (this.state.query || "").trim().toLowerCase();
        return lines.filter((line) => {
            if (q && !`${line.name} ${line.code || ""}`.toLowerCase().includes(q)) {
                return false;
            }
            if (this.state.onlyMissing) {
                return this.state.dim === "price" ? !this.priceComplete(line) : !this.commComplete(line);
            }
            return true;
        });
    }

    get missingCount() {
        const lines = this.data ? this.data.lines : [];
        return lines.filter((line) => (this.state.dim === "price" ? !this.priceComplete(line) : !this.commComplete(line))).length;
    }

    select(line, child = null, side = null) {
        this.state.sel = this.rowKey(line, child);
        if (side) {
            this.state.side = side;
        }
    }

    get readiness() {
        const lines = this.data ? this.data.lines : [];
        const priced = lines.filter((line) => this.priceComplete(line)).length;
        const commissioned = lines.filter((line) => this.commComplete(line)).length;
        const pct = (n) => (lines.length ? Math.round((n * 100) / lines.length) : 0);
        return { total: lines.length, priced, commissioned, pricedPct: pct(priced), commPct: pct(commissioned) };
    }

    get receipt() {
        const sizeId = this.state.sizeId;
        const rate = this.data.film.tax_rate || 0;
        let subtotal = 0;
        let commission = 0;
        const gaps = [];
        const rows = this.data.lines.map((line) => {
            const price = this.priceAt(line, sizeId);
            const comm = this.commAt(line, sizeId);
            const kind = this.priceKind(line, sizeId);
            if (kind === "missing" || kind === "zero") {
                gaps.push(line.name);
            } else {
                subtotal += price || 0;
            }
            if (comm !== null) {
                commission += comm;
            }
            return { id: line.id, name: line.name, price, kind };
        });
        let vat;
        let total;
        if (this.data.film.price_included) {
            total = subtotal;
            vat = rate ? subtotal - subtotal / (1 + rate) : 0;
        } else {
            vat = subtotal * rate;
            total = subtotal + vat;
        }
        return { rows, vat, total, commission, gaps };
    }

    setReceiptSize(size) {
        this.state.sizeId = size.id;
    }

    // ----------------------------------------------------------------- save
    payload() {
        return {
            pricing_policy: this.data.film.pricing_policy,
            lines: this.data.lines.map((line) => ({
                id: line.id,
                price: { mode: this.priceMode(line), general: line.price.general, sizes: line.price.sizes },
                discount_policy: line.discount_policy,
                discount_limit: line.discount_limit,
                commission: line.commission,
                children: line.children.map((child) => ({ part_id: child.part_id, commission: child.commission })),
            })),
        };
    }

    async save() {
        if (this.state.saving) {
            return false;
        }
        this.state.saving = true;
        try {
            const data = await this.orm.call("wof.film.category", "wof_matrix_save", [[this.filmId], this.payload()]);
            this.applyData(data);
            this.notification.add(_t("تم حفظ الأسعار والعمولات."), { type: "success" });
            return true;
        } finally {
            this.state.saving = false;
        }
    }

    async leave() {
        if (this.wizardId) {
            const step = this.state.dim === "commission" ? "commission" : "pricing";
            const action = await this.orm.call("wof.film.setup.wizard", "action_return_from_matrix", [[this.wizardId]], { step });
            return this.action.doAction(action);
        }
        const crumbs = (this.env.config && this.env.config.breadcrumbs) || [];
        const previous = crumbs.length > 1 ? crumbs[crumbs.length - 2] : null;
        const canGoBack = Boolean(previous && previous.jsId);
        if (this.returnToEditor) {
            // Opened from the film editor page: going back shows it again on its price step.
            if (canGoBack) {
                return this.action.restore(previous.jsId);
            }
            return this.action.doAction({
                type: "ir.actions.client", tag: "wof_film_editor", target: "current",
                params: { film_id: this.filmId, step: "price" },
            });
        }
        if (canGoBack) {
            return this.action.restore(previous.jsId);
        }
        return this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "wof.film.category",
            res_id: this.filmId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    async saveAndLeave() {
        if (await this.save()) {
            await this.leave();
        }
    }

    back() {
        if (!this.state.dirty) {
            return this.leave();
        }
        this.dialog.add(ConfirmationDialog, {
            title: _t("تغييرات غير محفوظة"),
            body: _t("لديك تغييرات لم تُحفظ. هل تريد حفظها قبل الرجوع؟"),
            confirmLabel: _t("حفظ والرجوع"),
            // Let the confirmation close first: navigating while it is still open
            // made the film editor fail to reopen.
            confirm: () => {
                browser.setTimeout(() => this.saveAndLeave());
            },
            cancelLabel: _t("رجوع بدون حفظ"),
            cancel: () => {
                browser.setTimeout(() => this.leave());
            },
        });
    }

    // ------------------------------------------------------------ hero trail
    get heroCrumbs() {
        return previousCrumbs(this.env);
    }

    goCrumb(crumb) {
        return this.action.restore(crumb.jsId);
    }

    actColor(type) {
        return activityColor(type);
    }
}

registry.category("actions").add("wof_pricing_matrix", WofPricingMatrix);
