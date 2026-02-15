class HydraHeadController {
    constructor(element) {
        this.el = element;
        this.headId = this.el.dataset.headId;
        this.isAlive = this.el.dataset.isAlive === 'true';
        this.pollInterval = null;

        // DOM Targets
        this.targetEl = this.el.querySelector('.js-head-target');
        this.logEl = this.el.querySelector('.js-head-log');
        this.durationEl = this.el.querySelector('.js-head-duration');

        // Terminal states where polling should permanently cease
        this.terminalStates = ['Success', 'Failed', 'Stopped', 'Aborted'];

        if (this.isAlive) {
            this.startPolling();
        }
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
            const response = await fetch(`/api/v1/heads/${this.headId}/`, {
                headers: {'Accept': 'application/json'}
            });

            if (!response.ok) return;
            const data = await response.json();
            this.updateDOM(data);

            if (this.terminalStates.includes(data.status_name)) {
                this.stopPolling();
                this.el.dataset.isAlive = 'false';
            }
        } catch (error) {
            console.error(`[HydraHead] Fetch failed for ${this.headId}:`, error);
        }
    }

    updateDOM(data) {
        // Surgical Class Updates
        this.el.className = `hydra-head-card js-hydra-head status-${data.status_name.toLowerCase()}`;

        // Surgical Text Updates
        if (this.targetEl) this.targetEl.innerText = data.agent;
        if (this.durationEl) this.durationEl.innerText = `⏱ ${data.duration}`;

        if (this.logEl) {
            if (data.status_name === 'Created' || data.status_name === 'Pending') {
                this.logEl.innerText = 'Waiting...';
            } else if (data.status_name === 'Success' || data.status_name === 'Failed') {
                this.logEl.innerText = `RC: ${data.result_code !== null ? data.result_code : data.status_name}`;
            } else {
                this.logEl.innerText = data.status_name;
            }
        }
    }
}