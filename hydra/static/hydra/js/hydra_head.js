class HydraHeadController {
    constructor(element) {
        this.el = element;
        // No intervals! The parent spawn calls populateTemplate directly to sync data.
    }

    static populateTemplate(clone, data) {
        const headEl = clone.querySelector('.js-hydra-head');
        if (!headEl) return;

        headEl.dataset.headId = data.id;

        const statusStr = data.status_name || 'Pending';
        const isAlive = ['Created', 'Pending', 'Running', 'Delegated', 'Stopping'].includes(statusStr);
        headEl.dataset.isAlive = isAlive ? 'true' : 'false';

        headEl.href = `/hydra/head/${data.id}/`;
        headEl.className = `hydra-head-card js-hydra-head status-${statusStr.toLowerCase()}`;

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
                const rc = (data.result_code !== null && data.result_code !== undefined) ? data.result_code : statusStr;
                logEl.textContent = `RC: ${rc}`;
            } else {
                logEl.textContent = statusStr;
            }
        }
    }
}