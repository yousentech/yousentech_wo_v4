/** @odoo-module **/

// Services of the installation order as compact rows (one line per service).
// A service area row opens a table of its template parts where the grade,
// stock product, quantity, technicians and progress are set per part.

import { Component, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { _t } from "@web/core/l10n/translation";
import { activityColor } from "./hero_nav";

const fmt = (value) => Number(value || 0).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export class WofServiceRows extends Component {
    static template = "yousentech_wo_v4.ServiceRows";
    static props = { ...standardFieldProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.fmt = fmt;
        this.state = useState({ open: {}, areas: {}, busy: false, techFor: null });
    }

    get order() {
        return this.props.record;
    }

    get rows() {
        return this.props.record.data[this.props.name].records.map((rec) => {
            const d = rec.data;
            const area = d.part_kind === "service_area";
            const many2 = (v) => (Array.isArray(v) ? v[1] : v && v.display_name) || "";
            return {
                rec,
                id: rec.resId,
                area,
                color: activityColor(d.activity_type || "others"),
                letter: (many2(d.service_type_id) || "؟").trim().charAt(0),
                title: many2(d.car_part_id),
                film: many2(d.film_category_id),
                activity: many2(d.service_type_id),
                template: many2(d.service_area_template_id),
                partCount: d.part_count || 0,
                grade: area ? d.part_grade_summary || "—" : many2(d.film_category_line_id) || "—",
                usesInventory: d.film_uses_inventory,
                product: many2(d.film_product_id),
                productQty: d.film_product_qty,
                missing: d.part_missing_product || 0,
                team: d.technician_names || "",
                price: d.unit_price,
                discount: d.discount_amount,
                progress: d.execution_progress || 0,
                open: Boolean(this.state.open[rec.resId]),
            };
        });
    }

    get currency() {
        const c = this.order.data.currency_id;
        return (c && (c[1] || c.display_name)) || "";
    }

    get editable() {
        return ["draft", "scheduled"].includes(this.order.data.state);
    }

    // ---------------------------------------------------------- helpers
    async ensureSaved() {
        if (this.order.isDirty || this.order.isNew) {
            const ok = await this.order.save();
            if (!ok) {
                return false;
            }
        }
        return true;
    }

    async reloadOrder() {
        await this.order.load();
    }

    notifyError(error) {
        const message = (error && error.data && error.data.message) || (error && error.message) || _t("تعذر الحفظ.");
        this.notification.add(message, { type: "danger" });
    }

    // ------------------------------------------------------------- rows
    async openDetails(row) {
        if (!(await this.ensureSaved()) || !row.id) {
            return;
        }
        await this.action.doAction(
            {
                type: "ir.actions.act_window",
                name: _t("تفاصيل الخدمة"),
                res_model: "wof.installation.order.line",
                res_id: row.id,
                views: [[false, "form"]],
                target: "new",
            },
            { onClose: () => this.reloadOrder() }
        );
    }

    async removeRow(row) {
        if (!(await this.ensureSaved()) || !row.id) {
            return;
        }
        try {
            await this.orm.unlink("wof.installation.order.line", [row.id]);
            await this.reloadOrder();
        } catch (error) {
            this.notifyError(error);
        }
    }

    async toggle(row) {
        if (this.state.open[row.id]) {
            delete this.state.open[row.id];
            return;
        }
        if (!(await this.ensureSaved())) {
            return;
        }
        this.state.open[row.id] = true;
        this.state.techFor = null;
        await this.loadArea(row.id);
    }

    async loadArea(lineId) {
        try {
            this.state.areas[lineId] = await this.orm.call("wof.installation.order.line", "wof_line_load", [[lineId]]);
        } catch (error) {
            this.notifyError(error);
        }
    }

    // ------------------------------------------------------------ parts
    async run(lineId, method, args) {
        if (this.state.busy) {
            return;
        }
        this.state.busy = true;
        try {
            this.state.areas[lineId] = await this.orm.call("wof.installation.order.line", method, [[lineId], ...args]);
            await this.reloadOrder();
        } catch (error) {
            this.notifyError(error);
            await this.loadArea(lineId);
        } finally {
            this.state.busy = false;
        }
    }

    setTemplate(lineId, templateId) {
        return this.run(lineId, "wof_area_set_template", [templateId]);
    }

    updatePart(lineId, part, vals) {
        return this.run(lineId, "wof_area_update", [[part.id], vals]);
    }

    applyAll(lineId, key, ev) {
        const area = this.state.areas[lineId];
        const raw = ev.target.value;
        ev.target.value = "";
        if (!raw || !area) {
            return;
        }
        const ids = area.parts.map((p) => p.id);
        const vals = key === "technician_ids" ? { technician_ids: [Number(raw)] } : { [key]: Number(raw) };
        return this.run(lineId, "wof_area_update", [ids, vals]);
    }

    // ------------------------------------------------- single service row
    updateLine(lineId, vals) {
        return this.run(lineId, "wof_line_update", [vals]);
    }

    onLineSelect(lineId, key, ev) {
        return this.updateLine(lineId, { [key]: ev.target.value ? Number(ev.target.value) : false });
    }

    onLineQty(lineId, ev) {
        return this.updateLine(lineId, { film_product_qty: Number(ev.target.value || 0) });
    }

    onLineProgress(lineId, ev) {
        return this.updateLine(lineId, { execution_progress: Math.max(0, Math.min(100, Number(ev.target.value || 0))) });
    }

    onDiscountType(lineId, ev) {
        return this.updateLine(lineId, { discount_type: ev.target.value });
    }

    onDiscountValue(lineId, ev) {
        // An emptied box clears the discount.
        return this.updateLine(lineId, { discount_value: ev.target.value === "" ? 0 : Number(ev.target.value) });
    }

    toggleLineTech(lineId, data, techId) {
        const ids = data.technician_ids.includes(techId)
            ? data.technician_ids.filter((i) => i !== techId)
            : [...data.technician_ids, techId];
        return this.updateLine(lineId, { technician_ids: ids });
    }

    /** Tags shown for a service or a part: removable ones (current branch team)
     * and names only (e.g. a technician who moved to another branch). */
    techTags(data, holder) {
        const tags = holder.technician_ids
            .map((id) => ({ id, name: this.techName(data, id) }))
            .filter((t) => t.name);
        const known = new Set(tags.map((t) => t.name));
        for (const name of (holder.technician_names || "").split("، ")) {
            if (name && !known.has(name)) {
                tags.push({ id: null, name });
            }
        }
        return tags;
    }

    onTeamToggle(lineId, part, techId) {
        if (part) {
            return this.toggleTech(lineId, part, techId);
        }
        return this.toggleLineTech(lineId, this.state.areas[lineId], techId);
    }

    pickerKey(lineId, part) {
        return `${lineId}:${part ? part.id : "line"}`;
    }

    openPicker(lineId, part) {
        const key = this.pickerKey(lineId, part);
        this.state.techFor = this.state.techFor === key ? null : key;
    }

    isPickerOpen(lineId, part) {
        return this.state.techFor === this.pickerKey(lineId, part);
    }

    onSelect(lineId, part, key, ev) {
        return this.updatePart(lineId, part, { [key]: ev.target.value ? Number(ev.target.value) : false });
    }

    onQty(lineId, part, ev) {
        return this.updatePart(lineId, part, { product_qty: Number(ev.target.value || 0) });
    }

    onProgress(lineId, part, ev) {
        const value = Math.max(0, Math.min(100, Number(ev.target.value || 0)));
        return this.updatePart(lineId, part, { progress: value });
    }

    toggleTech(lineId, part, techId) {
        const ids = part.technician_ids.includes(techId)
            ? part.technician_ids.filter((i) => i !== techId)
            : [...part.technician_ids, techId];
        return this.updatePart(lineId, part, { technician_ids: ids });
    }

    canToggleTech(area, techId) {
        return area.can_team && (area.can_setup || area.my_employee_ids.includes(techId));
    }

    techName(area, id) {
        const tech = area.technicians.find((t) => t.id === id);
        return tech ? tech.name : "";
    }
}

registry.category("fields").add("wof_service_rows", {
    component: WofServiceRows,
    displayName: _t("خدمات أمر التركيب"),
    supportedTypes: ["one2many"],
    useSubView: true,
});
