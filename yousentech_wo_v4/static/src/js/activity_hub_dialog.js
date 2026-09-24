/** @odoo-module **/

/**
 * Activity Hub dialog sizing hook.
 *
 * Odoo/Bootstrap owns the outer .modal-dialog element, while the Activity Hub
 * class lives inside the rendered form.  CSS on the inner form cannot change
 * Bootstrap's max-width.  Tag only the dialog that actually contains the hub
 * shell, so no other wizard/dialog is affected.
 */
function tagActivityHubDialog(root = document) {
    const hubs = [];
    if (root instanceof Element && root.matches('.wof_hub_shell')) {
        hubs.push(root);
    }
    if (root.querySelectorAll) {
        hubs.push(...root.querySelectorAll('.wof_hub_shell'));
    }
    for (const hub of hubs) {
        const dialog = hub.closest('.modal-dialog');
        if (dialog) {
            dialog.classList.add('wof_activity_hub_modal');
        }
    }
}

function startActivityHubDialogObserver() {
    tagActivityHubDialog();
    const observer = new MutationObserver((mutations) => {
        for (const mutation of mutations) {
            for (const node of mutation.addedNodes) {
                if (node instanceof Element) {
                    tagActivityHubDialog(node);
                }
            }
        }
    });
    observer.observe(document.body, {childList: true, subtree: true});
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', startActivityHubDialogObserver, {once: true});
} else {
    startActivityHubDialogObserver();
}
