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
        console.log("[Dispatcher] Online. Fetching root missions...");
        this.fetchActiveSpawns();
        this.startPolling();
    }

    startPolling() {
        this.pollInterval = setInterval(() => this.fetchActiveSpawns(), 3000);
    }

    async fetchActiveSpawns() {
        try {
            // Base URL with DRF filters
            let url = '/api/v1/spike_trains/?is_root=true&ordering=-created';

            // Apply Delta Cursor if we have one
            if (this.lastDataSeen) {
                url += `&modified__gt=${encodeURIComponent(this.lastDataSeen)}`;
            }

            const response = await fetch(url, {headers: {'Accept': 'application/json'}});
            if (!response.ok) return;

            const data = await response.json();
            const spike_trains = data.results || data;

            // ONLY UPDATE CURSOR & DOM IF WE GOT DATA
            if (spike_trains.length > 0) {
                this.lastDataSeen = new Date().toISOString();

                // Double check root status locally just in case, then cap to 15
                const rootSpikeTrains = spike_trains.filter(s => s.parent_spike === null);
                const displaySpikeTrains = rootSpikeTrains.slice(0, 15);

                // Render backwards for top-down insertion
                for (let i = displaySpikeTrains.length - 1; i >= 0; i--) {
                    this.ensureSpawnExists(displaySpikeTrains[i], this.root);
                }
            }
        } catch (error) {
            console.error("[Dispatcher] Fetch failed:", error);
        }
    }

    ensureSpawnExists(spawnData, container) {
        // FIX: Matched standard CSS selector binding to data-spike-train-id
        if (container.querySelector(`.js-cns-spike_train-wrapper > .js-cns-spike_train[data-spike-train-id="${spawnData.id}"]`)) return;

        const tpl = document.getElementById('tpl-cns-spike_train');
        const clone = tpl.content.cloneNode(true);

        SpikeTrainController.populateTemplate(clone, spawnData);

        container.insertAdjacentElement('afterbegin', clone.firstElementChild);
        const newEl = container.firstElementChild.querySelector('.js-cns-spike_train');

        const emptyState = this.root.querySelector('.empty-state');
        if (emptyState) emptyState.remove();

        new SpikeTrainController(newEl);
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const dispatcher = new DispatcherController('spike_trains-dispatcher-root');
    dispatcher.init();
});