class DispatcherController {
    constructor(rootId) {
        this.root = document.getElementById(rootId);
        // Note: Future feature - poll the DRF endpoint for NEW spawn UUIDs
        // that aren't currently in the DOM, fetch their HTML template, inject,
        // and call mountHydraComponents(newElement).
    }

    init() {
        console.log("[Dispatcher] Sandbox initialized. Mounting components...");
        // This function is defined in hydra_spawn.js
        mountHydraComponents(this.root);
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const dispatcher = new DispatcherController('spawns-dispatcher-root');
    dispatcher.init();
});