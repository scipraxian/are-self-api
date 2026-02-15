class HydraHeadController {
    constructor(element) {
        this.el = element;
        this.headId = this.el.dataset.headId;
        this.isAlive = this.el.dataset.isAlive === 'true';
        this.pollInterval = null;

        this.targetEl = this.el.querySelector('.js-head-target');
        this.logEl = this.el.querySelector('.js-head-log');
        this.durationEl = this.el.querySelector('.js-head-duration');

        this.terminalStates = ['Success', 'Failed', 'Stopped', 'Aborted'];

        if (this.isAlive) this.startPolling();
    }

    static populateTemplate(clone, data) {
        const headEl = clone.querySelector('.js-hydra-head');
        headEl.dataset.headId = data.id;

        // Determine Alive State
        const isAlive = ['Created', 'Pending', 'Running', 'Delegated', 'Stopping'].includes(data.status_name);
        headEl.dataset.isAlive = isAlive ? 'true' : 'false';

        headEl.href = `/hydra/head/${data.id}/`;
        headEl.classList.add(`status-${data.status_name.toLowerCase()}`);

        // MAP EXACT DRF FIELDS
        clone.querySelector('.js-head-name').textContent = data.spell_name || "Unknown Node";
        clone.querySelector('.js-head-target').textContent = data.target_name || "LOCAL";
        clone.querySelector('.js-head-time').textContent = data.timestamp_str || "--:--:--";
        clone.querySelector('.js-head-duration').textContent = `⏱ ${data.duration || '0s'}`;

        const logEl = clone.querySelector('.js-head-log');
        if (data.status_name === 'Created' || data.status_name === 'Pending') {
            logEl.textContent = 'Waiting...';
        } else if (data.status_name === 'Success' || data.status_name === 'Failed') {
            logEl.textContent = `RC: ${data.result_code !== null ? data.result_code : data.status_name}`;
        } else {
            logEl.textContent = data.status_name;
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
            const response = await fetch(`/api/v1/heads/${this.headId}/`);
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
        this.el.className = `hydra-head-card js-hydra-head status-${data.status_name.toLowerCase()}`;

        if (this.targetEl) this.targetEl.textContent = data.target_name || "LOCAL";
        if (this.durationEl) this.durationEl.textContent = `⏱ ${data.duration}`;

        if (this.logEl) {
            if (data.status_name === 'Created' || data.status_name === 'Pending') {
                this.logEl.textContent = 'Waiting...';
            } else if (data.status_name === 'Success' || data.status_name === 'Failed') {
                this.logEl.textContent = `RC: ${data.result_code !== null ? data.result_code : data.status_name}`;
            } else {
                this.logEl.textContent = data.status_name;
            }
        }
    }
}