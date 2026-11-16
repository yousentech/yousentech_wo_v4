/** @odoo-module **/
// «مهامي»: the technician's touch screen. His tasks grouped by car; one tap marks a task done.

import { Component, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { deserializeDateTime, formatDateTime } from "@web/core/l10n/dates";

const MODEL = "wof.technician.task";
const TABS = [
    { key: "now", label: "قيد العمل", icon: "fa-wrench" },
    { key: "next", label: "قادمة", icon: "fa-clock-o" },
    { key: "done", label: "أنجزتها", icon: "fa-check-circle" },
];

export class WofMyTasks extends Component {
    static template = "yousentech_wo_v4.MyTasks";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.tabs = TABS;
        this.state = useState({ data: null, tab: "now", busy: 0, loading: true });
        onWillStart(() => this.load());
        // Keep the screen fresh on a shared workshop display.
        this.timer = setInterval(() => !this.state.busy && this.load(true), 60000);
        onWillUnmount(() => clearInterval(this.timer));
    }

    async load(silent) {
        try {
            this.apply(await this.orm.call(MODEL, "wof_my_tasks_load", []));
        } catch (error) {
            if (!silent) {
                throw error;
            }
        }
        this.state.loading = false;
    }

    apply(data) {
        this.state.data = data;
        if (!data.groups[this.state.tab].length) {
            const first = TABS.find((tab) => data.groups[tab.key].length);
            if (first && this.state.tab === "now") {
                this.state.tab = first.key;
            }
        }
    }

    get orders() {
        return this.state.data ? this.state.data.groups[this.state.tab] : [];
    }

    count(key) {
        return this.state.data ? this.state.data.groups[key].length : 0;
    }

    percent(order) {
        return order.total ? Math.round((100 * order.done_count) / order.total) : 0;
    }

    when(value) {
        return value ? formatDateTime(deserializeDateTime(value), { format: "dd/MM HH:mm" }) : "";
    }

    async toggle(order, task) {
        if (!order.can_work || this.state.busy) {
            return;
        }
        this.state.busy = task.id;
        try {
            this.apply(await this.orm.call(MODEL, "wof_my_task_set", [[task.id], !task.done]));
        } catch (error) {
            const message = (error.data && error.data.message) || error.message || "تعذر تسجيل المهمة.";
            this.notification.add(message, { type: "danger" });
            await this.load(true);
        } finally {
            this.state.busy = 0;
        }
    }
}

registry.category("actions").add("wof_my_tasks", WofMyTasks);
