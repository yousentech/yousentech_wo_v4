/** @odoo-module **/

import { Component, xml } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { useService } from "@web/core/utils/hooks";

class FilmPartActionWidget extends Component {
    static template = xml`
        <button type="button"
                class="btn btn-link o_film_part_action_btn p-0"
                t-att-title="buttonTitle"
                t-on-click.stop.prevent="openAction">
            <i t-att-class="'fa ' + iconClass"/>
            <span class="ms-1" t-esc="buttonTitle"/>
        </button>
    `;

    static props = {
        ...standardFieldProps,
        options: { type: Object, optional: true },
    };

    setup() {
        this.action = useService("action");
        this.notification = useService("notification");
    }

    get widgetOptions() {
        return this.props.options || {};
    }

    get buttonTitle() {
        return this.widgetOptions.title || "فتح";
    }

    get iconClass() {
        return this.widgetOptions.icon || "fa-external-link";
    }

    get targetModel() {
        return this.widgetOptions.model;
    }

    get actionName() {
        return this.widgetOptions.action_name || this.buttonTitle;
    }

    get target() {
        return this.widgetOptions.target || "current";
    }

    get resId() {
        const resId = this.props.record.resId;
        return Number.isInteger(resId) ? resId : false;
    }

    openAction() {
        if (!this.resId) {
            this.notification.add(
                "احفظ سطر الجزء أولاً، ثم افتح التسعيرات أو العمولات.",
                {
                    title: "تنبيه",
                    type: "warning",
                }
            );
            return;
        }

        if (!this.targetModel) {
            this.notification.add(
                "لم يتم تحديد الموديل في خيارات الزر.",
                {
                    title: "خطأ",
                    type: "danger",
                }
            );
            return;
        }

        this.action.doAction({
            type: "ir.actions.act_window",
            name: this.actionName,
            res_model: this.targetModel,
            views: [[false, "list"], [false, "form"]],
            domain: [["part_line_id", "=", this.resId]],
            context: {
                default_part_line_id: this.resId,
            },
            target: this.target,
        });
    }
}

export const filmPartActionWidget = {
    component: FilmPartActionWidget,
    supportedTypes: ["char"],
    extractProps: ({ options }) => ({
        options,
    }),
};

registry.category("fields").add("film_part_action_widget", filmPartActionWidget);
