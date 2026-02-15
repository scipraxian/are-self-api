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
            const url = '/api/v1/spawns/?is_root=true&fields=id,spellbook,spellbook_name,status_name,modified,is_active,parent_head';

            const response = await fetch(url, {
                headers: {'Accept': 'application/json'}
            });
            if (!response.ok) return;

            const data = await response.json();
            const rootSpawns = data.results ? data.results : data;

            window.talosGlobalSpawns = rootSpawns;

            // Render, iterating backwards for top-down insertion
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