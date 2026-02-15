// Quick helper for time formatting
function timeSince(dateString) {
    if (!dateString) return "0s";
    const seconds = Math.floor((new Date() - new Date(dateString)) / 1000);
    let interval = seconds / 31536000;
    if (interval > 1) return Math.floor(interval) + " years";
    interval = seconds / 2592000;
    if (interval > 1) return Math.floor(interval) + " months";
    interval = seconds / 86400;
    if (interval > 1) return Math.floor(interval) + " days";
    interval = seconds / 3600;
    if (interval > 1) return Math.floor(interval) + "h";
    interval = seconds / 60;
    if (interval > 1) return Math.floor(interval) + "m";
    return Math.floor(seconds) + "s";
}

class DispatcherController {
    constructor(rootId) {
        this.root = document.getElementById(rootId);
        this.pollInterval = null;
        window.talosGlobalSpawns = []; // Global cache for Sub-Graph lookups
    }

    init() {
        console.log("[Dispatcher] Online. Fetching missions...");
        this.fetchActiveSpawns();
        this.startPolling();
    }

    startPolling() {
        this.pollInterval = setInterval(() => this.fetchActiveSpawns(), 3000);
    }

    async fetchActiveSpawns() {
        try {
            // Hit the raw endpoint (No hallucinated limits)
            const response = await fetch('/api/v1/spawns/', {
                headers: {'Accept': 'application/json'}
            });
            if (!response.ok) return;

            const data = await response.json();
            const spawns = data.results ? data.results : data;

            // Cache for recursive child lookups
            window.talosGlobalSpawns = spawns;

            // Isolate Root Spawns (parent_head === null)
            const rootSpawns = spawns.filter(s => s.parent_head === null);

            // Slice to top 15 to prevent browser DOM overload, iterate backwards for top-down insertion
            const displaySpawns = rootSpawns.slice(0, 15);
            for (let i = displaySpawns.length - 1; i >= 0; i--) {
                this.ensureSpawnExists(displaySpawns[i], this.root);
            }
        } catch (error) {
            console.error("[Dispatcher] Fetch failed:", error);
        }
    }

    ensureSpawnExists(spawnData, container) {
        if (container.querySelector(`.js-hydra-spawn-wrapper > .js-hydra-spawn[data-spawn-id="${spawnData.id}"]`)) return;

        console.log(`[Dispatcher] Injecting Root Spawn: ${spawnData.id}`);
        const tpl = document.getElementById('tpl-hydra-spawn');
        const clone = tpl.content.cloneNode(true);

        HydraSpawnController.populateTemplate(clone, spawnData);

        container.insertAdjacentElement('afterbegin', clone.firstElementChild);
        const newEl = container.firstElementChild.querySelector('.js-hydra-spawn');

        const emptyState = this.root.querySelector('.empty-state');
        if (emptyState) emptyState.remove();

        new HydraSpawnController(newEl);
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const dispatcher = new DispatcherController('spawns-dispatcher-root');
    dispatcher.init();
});