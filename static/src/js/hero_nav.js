/** @odoo-module **/

// Shared bits of the car-care page heroes: a clickable trail of the pages you
// came through, and one identity colour per activity type (used as a small dot
// or stripe next to the activity name, never as a meaning colour).

export const ACTIVITY_COLORS = {
    tint: "#EA580C", // heat / sun
    ppf: "#0284C7", // protection shield
    nano: "#DB2777",
    upholstery: "#A16207",
    floor_mats: "#475569",
    others: "#64748B",
};

export function activityColor(type) {
    return ACTIVITY_COLORS[type] || ACTIVITY_COLORS.others;
}

/** Pages before the current one, as {jsId, name}, skipping unnamed ones. */
export function previousCrumbs(env) {
    const crumbs = (env.config && env.config.breadcrumbs) || [];
    return crumbs.slice(0, -1).filter((crumb) => crumb && crumb.jsId && crumb.name);
}
