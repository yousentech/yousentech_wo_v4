/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

const MODEL = "wof.film.category";
const MISSING = { components: "المكوّنات", tint: "درجات اللون", prices: "الأسعار" };
const COPY_PARTS = [
    ["components", "المكوّنات وترتيبها"], ["tint", "درجات اللون"], ["policies", "السياسات"],
    ["prices", "الأسعار"], ["commissions", "العمولات"],
];

const editorAction = (filmId) => ({
    type: "ir.actions.client",
    tag: "wof_film_editor",
    target: "new",
    params: { film_id: filmId },
    context: { dialog_size: "extra-large" },
});

export class WofFilmsHub extends Component {
    static template = "yousentech_wo_v4.FilmsHub";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({
            data: null, tab: null, query: "", busy: false,
            dialog: null,
        });
        this.copyParts = COPY_PARTS;
        onWillStart(() => this.load());
    }

    async load() {
        const data = await this.orm.call(MODEL, "wof_films_hub_load", []);
        this.state.data = data;
        if (!data.activities.some((a) => a.id === this.state.tab)) {
            this.state.tab = data.activities.length ? data.activities[0].id : null;
        }
    }

    // --------------------------------------------------------------- tabs
    get tabs() {
        const films = this.state.data.films;
        return this.state.data.activities.map((a) => ({ ...a, count: films.filter((f) => f.activity_id === a.id).length }));
    }

    get activity() {
        return this.state.data.activities.find((a) => a.id === this.state.tab) || null;
    }

    get films() {
        const q = (this.state.query || "").trim().toLowerCase();
        return this.state.data.films
            .filter((f) => f.activity_id === this.state.tab)
            .filter((f) => !q || f.name.toLowerCase().includes(q) || (f.code || "").toLowerCase().includes(q))
            .map((f) => ({
                ...f,
                // Incomplete wins over inactive: new drafts are inactive but need finishing.
                state: !f.ready ? "pending" : (f.active ? "ready" : "off"),
                missingText: f.missing.map((m) => MISSING[m]).join("، "),
            }));
    }

    get counts() {
        const all = this.state.data.films.filter((f) => f.activity_id === this.state.tab);
        return {
            total: all.length,
            ready: all.filter((f) => f.active && f.ready).length,
            pending: all.filter((f) => !f.ready).length,
            off: all.filter((f) => f.ready && !f.active).length,
        };
    }

    // ------------------------------------------------------------ actions
    openEditor(film) {
        return this.action.doAction(editorAction(film.id), { onClose: () => this.load() });
    }

    openMatrix(film) {
        return this.action.doAction({
            type: "ir.actions.client", tag: "wof_pricing_matrix", target: "current",
            params: { film_id: film.id },
        });
    }

    openNew(source = null) {
        this.state.dialog = {
            mode: source ? "copy" : "blank",
            source: source ? source.id : null,
            name: source ? `${source.name} ${_t("(نسخة)")}` : "",
            itemType: "film",
            parts: { components: true, tint: true, policies: true, prices: true, commissions: false },
        };
    }

    closeNew() {
        this.state.dialog = null;
    }

    get sources() {
        const names = Object.fromEntries(this.state.data.activities.map((a) => [a.id, a.name]));
        return this.state.data.films.map((f) => ({ ...f, activityName: names[f.activity_id] || "" }));
    }

    get canCreate() {
        const d = this.state.dialog;
        return d && (d.name || "").trim() && (d.mode === "blank" || d.source) && !this.state.busy;
    }

    async create() {
        if (!this.canCreate) {
            return;
        }
        const d = this.state.dialog;
        this.state.busy = true;
        try {
            const filmId = d.mode === "copy"
                ? await this.orm.call(MODEL, "wof_film_copy", [d.source, this.state.tab, d.name.trim(), d.parts])
                : await this.orm.call(MODEL, "wof_film_create", [this.state.tab, d.name.trim(), d.itemType]);
            this.state.dialog = null;
            await this.load();
            this.openEditor({ id: filmId });
        } catch (error) {
            const message = (error && error.data && error.data.message) || (error && error.message) || _t("تعذر إنشاء الفيلم.");
            this.notification.add(message, { type: "danger" });
        } finally {
            this.state.busy = false;
        }
    }

    onDialogKey(ev) {
        if (ev.key === "Escape") {
            ev.stopPropagation();
            this.closeNew();
        } else if (ev.key === "Enter" && ev.target.tagName === "INPUT") {
            this.create();
        }
    }
}

registry.category("actions").add("wof_films_hub", WofFilmsHub);
