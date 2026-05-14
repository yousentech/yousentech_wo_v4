/** @odoo-module **/

import { Component, xml } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { useService } from "@web/core/utils/hooks";

class FilmPartActionWidget extends Component {
    static template = xml`
        <button type="button"
                class="btn btn-link o_film_part_action_btn"
                t-on-click.stop.prevent="openAction">
            <i t-att-class="'fa ' + iconClass"/>
            <span class="ms-1" t-esc="buttonTitle"/>
        </button>
    `;

    static props = {
        ...standardFieldProps,
    };

    setup() {
        this.action = useService("action");
        this.notification = useService("notification");
    }

    get buttonTitle() {
        return this.props.options.title || "فتح";
    }

    get iconClass() {
        return this.props.options.icon || "fa-external-link";
    }

    get targetModel() {
        return this.props.options.model;
    }

    get actionName() {
        return this.props.options.action_name || this.buttonTitle;
    }

    openAction() {
        const resId = this.props.record.resId;

        if (!resId || typeof resId !== "number") {
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
            domain: [["part_line_id", "=", resId]],
            context: {
                default_part_line_id: resId,
            },
            target: "current",
        });
    }
}

export const filmPartActionWidget = {
    component: FilmPartActionWidget,
};

registry.category("fields").add("film_part_action_widget", filmPartActionWidget);