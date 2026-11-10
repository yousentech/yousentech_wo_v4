/** @odoo-module **/

// "Add service" window of the installation order: activity -> film -> component.
// Reads the ready catalog priced for the order's car size, then adds the chosen
// components through the order (normal line creation, so every rule applies).

import { Component, onMounted, onWillStart, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { activityColor } from "./hero_nav";

const fmt = (value) => Number(value || 0).toLocaleString("en-US", { maximumFractionDigits: 2 });

export class WofOrderAddServices extends Component {
    static template = "yousentech_wo_v4.OrderAddServices";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.root = useRef("root");
        const params = (this.props.action && this.props.action.params) || {};
        this.orderId = params.order_id;
        this.fmt = fmt;
        this.state = useState({ data: null, act: null, film: null, picked: {}, templates: {}, busy: false, added: 0 });
        onWillStart(() => this.load());
        onMounted(() => {
            // The window has its own footer; hide the dialog's default one.
            const content = this.root.el && this.root.el.closest(".modal-content");
            const footer = content && content.querySelector(":scope > .modal-footer");
            if (footer) {
                footer.classList.add("d-none");
            }
        });
    }

    async load() {
        const data = await this.orm.call("wof.installation.order", "wof_service_catalog", [[this.orderId]]);
        this.state.data = data;
        const first = data.activities[0];
        if (!this.state.act || !data.activities.some((a) => a.id === this.state.act)) {
            this.state.act = first ? first.id : null;
            this.state.film = first && first.films.length ? first.films[0].id : null;
        }
    }

    // ------------------------------------------------------------ getters
    get activities() {
        return this.state.data.activities.map((a) => ({ ...a, color: activityColor(a.type), on: a.id === this.state.act }));
    }

    get activity() {
        return this.state.data.activities.find((a) => a.id === this.state.act);
    }

    get films() {
        const act = this.activity;
        return act ? act.films.map((f) => ({ ...f, on: f.id === this.state.film })) : [];
    }

    get film() {
        const act = this.activity;
        return act && act.films.find((f) => f.id === this.state.film);
    }

    key(filmId, partId) {
        return `${filmId}:${partId}`;
    }

    get comps() {
        const film = this.film;
        if (!film) {
            return [];
        }
        return film.comps.map((c) => ({ ...c, on: Boolean(this.state.picked[this.key(film.id, c.id)]) }));
    }

    get chosen() {
        const rows = [];
        for (const act of this.state.data.activities) {
            for (const film of act.films) {
                for (const comp of film.comps) {
                    if (this.state.picked[this.key(film.id, comp.id)]) {
                        const tplId = this.state.templates[this.key(film.id, comp.id)] || comp.default_template;
                        const tpl = comp.templates.find((t) => t.id === tplId);
                        rows.push({ key: this.key(film.id, comp.id), film, comp, tpl });
                    }
                }
            }
        }
        return rows;
    }

    get chosenAreas() {
        return this.chosen.filter((row) => row.comp.area && row.comp.templates.length);
    }

    get total() {
        return this.chosen.reduce((sum, row) => sum + (row.comp.price || 0), 0);
    }

    get summary() {
        const rows = this.chosen;
        if (!rows.length) {
            return _t("اختر مكوّنًا واحدًا على الأقل");
        }
        return rows.map((row) => `${row.film.name} · ${row.comp.name}`).join("، ");
    }

    // ------------------------------------------------------------ actions
    pickActivity(act) {
        this.state.act = act.id;
        this.state.film = act.films.length ? act.films[0].id : null;
    }

    pickFilm(film) {
        this.state.film = film.id;
    }

    toggleComp(comp) {
        if (comp.added || comp.price === null) {
            return;
        }
        const key = this.key(this.state.film, comp.id);
        if (this.state.picked[key]) {
            delete this.state.picked[key];
        } else {
            this.state.picked[key] = true;
        }
    }

    pickTemplate(row, tpl) {
        this.state.templates[row.key] = tpl.id;
    }

    async submit(again = false) {
        const rows = this.chosen;
        if (!rows.length || this.state.busy) {
            return;
        }
        this.state.busy = true;
        try {
            await this.orm.call("wof.installation.order", "wof_add_services", [[this.orderId], rows.map((row) => ({
                film_id: row.film.id, part_id: row.comp.id, template_id: row.tpl ? row.tpl.id : false,
            }))]);
            this.state.added += rows.length;
            this.state.picked = {};
            this.state.templates = {};
            if (again) {
                this.notification.add(_t("أُضيفت الخدمات للأمر. اختر التالية."), { type: "success" });
                await this.load();
            } else {
                this.close();
            }
        } catch (error) {
            const message = (error && error.data && error.data.message) || (error && error.message) || _t("تعذرت إضافة الخدمة.");
            this.notification.add(message, { type: "danger" });
        } finally {
            this.state.busy = false;
        }
    }

    close() {
        return this.action.doAction({ type: "ir.actions.act_window_close" });
    }
}

registry.category("actions").add("wof_order_add_services", WofOrderAddServices);
