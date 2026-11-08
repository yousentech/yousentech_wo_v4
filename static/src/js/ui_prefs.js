/** @odoo-module **/

// Display preferences for the car-care screens (films hub, editor, pricing
// matrix, guided setup). They are a per-browser convenience, so they live in
// localStorage and every read/write tolerates storage being unavailable.

const KEY = "wof_ui_prefs_v1";

export const FONT_SCALES = { sm: 0.86, md: 0.92, lg: 1 };

export const UI_DEFAULTS = Object.freeze({
    view: "cards", // cards | list (films hub)
    font: "md", // sm | md | lg (all car-care screens)
    density: "comfy", // comfy | compact
    hero: true, // show the activity summary card on the films hub
});

export function loadUiPrefs() {
    let stored = {};
    try {
        stored = JSON.parse(window.localStorage.getItem(KEY) || "{}") || {};
    } catch {
        stored = {};
    }
    const prefs = { ...UI_DEFAULTS, ...stored };
    if (!FONT_SCALES[prefs.font]) {
        prefs.font = UI_DEFAULTS.font;
    }
    if (!["cards", "list"].includes(prefs.view)) {
        prefs.view = UI_DEFAULTS.view;
    }
    if (!["comfy", "compact"].includes(prefs.density)) {
        prefs.density = UI_DEFAULTS.density;
    }
    prefs.hero = prefs.hero !== false;
    return prefs;
}

export function applyUiPrefs(prefs) {
    const root = document.documentElement;
    root.style.setProperty("--wof-fs", String(FONT_SCALES[prefs.font] || FONT_SCALES.md));
    root.dataset.wofDensity = prefs.density;
}

export function saveUiPrefs(prefs) {
    applyUiPrefs(prefs);
    try {
        window.localStorage.setItem(KEY, JSON.stringify(prefs));
    } catch {
        // Private mode or blocked storage: the choice still applies to this page.
    }
}

applyUiPrefs(loadUiPrefs());
