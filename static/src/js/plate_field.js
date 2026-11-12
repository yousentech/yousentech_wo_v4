/** @odoo-module **/

// Saudi plate field: shows the plate like the real one (Arabic row above the
// Latin row, digits on the left, letters on the right, KSA band) and opens a
// picker where letters and digits are chosen by clicking. Stored as capital
// Latin letters then digits: «ABJ 1234».

import { Component, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Dialog } from "@web/core/dialog/dialog";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { _t } from "@web/core/l10n/translation";

export const PLATE_LETTERS = [
    ["ا", "A"], ["ب", "B"], ["ح", "J"], ["د", "D"], ["ر", "R"], ["س", "S"],
    ["ص", "X"], ["ط", "T"], ["ع", "E"], ["ق", "G"], ["ك", "K"], ["ل", "L"],
    ["م", "Z"], ["ن", "N"], ["هـ", "H"], ["و", "U"], ["ى", "V"],
];
const AR_OF = Object.fromEntries(PLATE_LETTERS.map(([ar, en]) => [en, ar]));
const AR_DIGITS = "٠١٢٣٤٥٦٧٨٩";
const MAX_LETTERS = 3;
const MAX_DIGITS = 4;

export function parsePlate(value) {
    const text = (value || "").toUpperCase();
    const letters = [...text.replace(/[^A-Z]/g, "")].filter((ch) => AR_OF[ch]).slice(0, MAX_LETTERS);
    const digits = [...text.replace(/[^0-9]/g, "")].slice(0, MAX_DIGITS);
    return { letters, digits };
}

export function isSaudiPlate(value) {
    return /^[ABJDRSXTEGKLZNHUV]{1,3} \d{1,4}$/.test((value || "").toUpperCase().trim());
}

export function plateView(value) {
    const { letters, digits } = parsePlate(value);
    return {
        // Drawn as a Saudi plate only when it really is one; other plates show as text.
        valid: isSaudiPlate(value),
        lettersEn: letters,
        lettersAr: letters.map((ch) => AR_OF[ch]),
        digitsEn: digits,
        digitsAr: digits.map((d) => AR_DIGITS[Number(d)]),
    };
}

export class WofPlateDialog extends Component {
    static template = "yousentech_wo_v4.PlateDialog";
    static components = { Dialog };
    static props = ["value", "onConfirm", "close"];

    setup() {
        const parsed = parsePlate(this.props.value);
        this.state = useState({ letters: parsed.letters, digits: parsed.digits });
        this.letters = PLATE_LETTERS;
        this.digitKeys = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"];
        this.AR_DIGITS = AR_DIGITS;
        this.maxLetters = MAX_LETTERS;
        this.maxDigits = MAX_DIGITS;
    }

    get value() {
        const letters = this.state.letters.join("");
        const digits = this.state.digits.join("");
        return [letters, digits].filter(Boolean).join(" ");
    }

    get preview() {
        return plateView(this.value);
    }

    get letterSlots() {
        return Array.from({ length: MAX_LETTERS }, (_, i) => this.state.letters[i] || "");
    }

    get digitSlots() {
        return Array.from({ length: MAX_DIGITS }, (_, i) => this.state.digits[i] || "");
    }

    addLetter(en) {
        if (this.state.letters.length < MAX_LETTERS) {
            this.state.letters.push(en);
        }
    }

    addDigit(d) {
        if (this.state.digits.length < MAX_DIGITS) {
            this.state.digits.push(d);
        }
    }

    backLetter() {
        this.state.letters.pop();
    }

    backDigit() {
        this.state.digits.pop();
    }

    clear() {
        this.state.letters.splice(0);
        this.state.digits.splice(0);
    }

    confirm() {
        this.props.onConfirm(this.value);
        this.props.close();
    }
}

export class WofPlateField extends Component {
    static template = "yousentech_wo_v4.PlateField";
    static props = { ...standardFieldProps };

    setup() {
        this.dialog = useService("dialog");
    }

    get value() {
        return this.props.record.data[this.props.name] || "";
    }

    get plate() {
        return plateView(this.value);
    }

    get isReadonly() {
        return this.props.readonly;
    }

    open() {
        if (this.isReadonly) {
            return;
        }
        this.dialog.add(WofPlateDialog, {
            value: this.value,
            onConfirm: (value) => this.props.record.update({ [this.props.name]: value || false }),
        });
    }

    onInput(ev) {
        this.props.record.update({ [this.props.name]: (ev.target.value || "").toUpperCase() || false });
    }
}

export const wofPlateField = {
    component: WofPlateField,
    displayName: _t("لوحة سعودية"),
    supportedTypes: ["char"],
};

registry.category("fields").add("wof_plate", wofPlateField);
