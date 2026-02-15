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

        const statusStr = data.status_name || 'Pending';
        const isAlive = ['Created', 'Pending', 'Running', 'Delegated', 'Stopping'].includes(statusStr);
        headEl.dataset.isAlive = isAlive ? 'true' : 'false';

        headEl.href = `/hydra/head/${data.id}/`;
        headEl.className = `hydra-head-card js-hydra-head status-${statusStr.toLowerCase()}`;

        // Bulletproof DOM population
        const nameEl = clone.querySelector('.js-head-name');
        if (nameEl) nameEl.textContent = data.spell_name || "Unknown Node";

        const targetEl = clone.querySelector('.js-head-target');
        if (targetEl) targetEl.textContent = data.target_name || "LOCAL";

        const timeEl = clone.querySelector('.js-head-time');
        if (timeEl) timeEl.textContent = data.timestamp_str || "--:--:--";

        const durEl = clone.querySelector('.js-head-duration');
        if (durEl) durEl.textContent = `⏱ ${data.duration || '0s'}`;

        const logEl = clone.querySelector('.js-head-log');
        if (logEl) {
            if (statusStr === 'Created' || statusStr === 'Pending') {
                logEl.textContent = 'Waiting...';
            } else if (statusStr === 'Success' || statusStr === 'Failed') {
                // Strict check to prevent "RC: undefined"
                const rc = (data.result_code !== null && data.result_code !== undefined) ? data.result_code : statusStr;
                logEl.textContent = `RC: ${rc}`;
            } else {
                logEl.textContent = statusStr;
            }
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
            const response = await fetch(`/api/v1/heads/${this.headId}/status/`);
            if (!response.ok) return;
            const data = await response.json();

            this.updateDOM(data);

            const statusStr = data.status_name || 'Pending';
            if (this.terminalStates.includes(statusStr)) {
                this.stopPolling();
                this.el.dataset.isAlive = 'false';
            }
        } catch (error) {
            console.error(`[HydraHead] Fetch failed for ${this.headId}:`, error);
        }
    }

    updateDOM(data) {
        const statusStr = data.status_name || 'Pending';
        this.el.className = `hydra-head-card js-hydra-head status-${statusStr.toLowerCase()}`;

        if (this.targetEl) this.targetEl.textContent = data.target_name || "LOCAL";
        if (this.durationEl) this.durationEl.textContent = `⏱ ${data.duration || '0s'}`;

        if (this.logEl) {
            if (statusStr === 'Created' || statusStr === 'Pending') {
                this.logEl.textContent = 'Waiting...';
            } else if (statusStr === 'Success' || statusStr === 'Failed') {
                const rc = (data.result_code !== null && data.result_code !== undefined) ? data.result_code : statusStr;
                this.logEl.textContent = `RC: ${rc}`;
            } else {
                this.logEl.textContent = statusStr;
            }
        }
    }
}