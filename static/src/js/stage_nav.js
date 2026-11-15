/** @odoo-module **/
// Keeps the section menu of the installation order on the current stage:
// when a button moves the order to another stage, the menu follows it.

import { Component, onMounted, useEffect, useRef } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

const SECTION_OF_STATE = {
    draft: "customer",
    scheduled: "intake",
    intake: "execution",
    in_progress: "execution",
    quality: "quality_delivery",
    ready: "quality_delivery",
    delivered: "billing",
};

export class WofStageNav extends Component {
    static template = "yousentech_wo_v4.StageNav";
    static props = { ...standardFieldProps };

    setup() {
        this.root = useRef("root");
        let previous = null;
        onMounted(() => this.ensureVisibleSection());
        useEffect(
            (state, id) => {
                const key = `${id}:${state}`;
                if (previous && previous.split(":")[0] === String(id) && previous !== key) {
                    this.select(SECTION_OF_STATE[state]);
                }
                previous = key;
            },
            () => [this.props.record.data[this.props.name], this.props.record.resId]
        );
    }

    ensureVisibleSection() {
        // The default section may be hidden (setup or technician view): open the first shown.
        const form = this.root.el && this.root.el.closest(".o_form_view");
        if (form && !form.querySelector('input[name="wof_order_section"]:checked')) {
            const first = form.querySelector('.wof_steps_opt:not(.is-all) input[name="wof_order_section"]');
            if (first) {
                first.checked = true;
            }
        }
    }

    select(section) {
        const form = this.root.el && this.root.el.closest(".o_form_view");
        const input = section && form && form.querySelector(`input[name="wof_order_section"][value="${section}"]`);
        if (input && !input.checked) {
            input.checked = true;
            const sheet = form.querySelector(".o_content") || form;
            sheet.scrollTo({ top: 0, behavior: "smooth" });
        }
    }
}

registry.category("fields").add("wof_stage_nav", { component: WofStageNav, supportedTypes: ["selection"] });
