class HydraSpawnController {
    constructor(element) {
        this.el = element;
        this.spawnId = this.el.dataset.spawnId;
        this.isActive = this.el.dataset.isActive === 'true';
        this.pollInterval = null;

        // DOM Targets
        this.statusEl = this.el.querySelector('.js-spawn-status');
        this.controlCardEl = this.el.querySelector('.js-hydra-control-card');
        this.trackEl = this.el.querySelector('.js-spawn-track');

        // Mount Child Controller
        if (this.controlCardEl) {
            this.controlCard = new HydraSpawnControlCardController(this.controlCardEl);
        }

        this.initTrackObservers();

        if (this.isActive) {
            this.startPolling();
        }
    }

    initTrackObservers() {
        if (!this.trackEl) return;

        this.observer = new ResizeObserver(() => this.checkOverflow());
        this.observer.observe(this.trackEl);
        this.checkOverflow();
    }

    checkOverflow() {
        const hasOverflow = this.trackEl.scrollWidth > (this.trackEl.clientWidth + 1);
        const btns = this.el.querySelectorAll('.scroll-btn');
        btns.forEach(btn => btn.style.display = hasOverflow ? 'flex' : 'none');
    }

    startPolling() {
        this.pollInterval = setInterval(() => this.fetchState(), 1500);
    }

    stopPolling() {
        if (this.pollInterval) {
            clearInterval(this.pollInterval);
            this.pollInterval = null;
        }
    }

    async fetchState() {
        try {
            const response = await fetch(`/api/v1/spawns/${this.spawnId}/live_status/`, {
                headers: {'Accept': 'application/json'}
            });

            if (!response.ok) return;
            const data = await response.json();
            this.updateDOM(data);

            if (!data.is_active) {
                this.stopPolling();
                this.el.dataset.isActive = 'false';
            }
        } catch (error) {
            console.error(`[HydraSpawn] Fetch failed for ${this.spawnId}:`, error);
        }
    }

    updateDOM(data) {
        // Update Status Text and Color
        if (this.statusEl) {
            this.statusEl.innerText = data.status_label;
            this.statusEl.className = `status-text js-spawn-status status-${data.status_label.toLowerCase()}`;
        }

        // Update Lane Colors
        this.el.classList.remove('active-lane', 'failed-lane');
        if (data.is_active) {
            this.el.classList.add('active-lane');
        } else if (data.status_label === 'Failed' || data.status_label === 'Aborted') {
            this.el.classList.add('failed-lane');
        }

        // Update Control Card Mode
        if (this.controlCard) {
            this.controlCard.setMode(data.is_active);
        }

        // Note: Injection of newly spawned Heads requires a slightly heavier API response
        // to return new Head IDs to append, which would be requested from a unified /sync/ endpoint.
        // For strict state tracking, this accomplishes the requested isolated architecture.
    }
}

// Global Initialization Registry
function mountHydraComponents(container = document) {
    container.querySelectorAll('.js-hydra-head:not([data-mounted])').forEach(el => {
        el.dataset.mounted = 'true';
        new HydraHeadController(el);
    });

    container.querySelectorAll('.js-hydra-spawn:not([data-mounted])').forEach(el => {
        el.dataset.mounted = 'true';
        new HydraSpawnController(el);
    });
}

// Mount on initial load
document.addEventListener('DOMContentLoaded', () => mountHydraComponents());