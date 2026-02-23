/**
 * Talos Hydra Head Controller
 * Refactored for High-Density LCARS UI
 */

class HydraHeadController {
    constructor(element) {
        this.el = element;
    }

    static populateTemplate(clone, data) {
        const headEl = clone.querySelector('.js-hydra-head');
        if (!headEl) return;

        headEl.dataset.headId = data.id;
        const statusStr = data.status_name || 'Pending';
        const isAlive = ['Created', 'Pending', 'Running', 'Delegated', 'Stopping'].includes(statusStr);

        headEl.href = `/hydra/head/${data.id}/`;

        // Visual State Reset
        headEl.className = 'hydra-head-card js-hydra-head';
        headEl.classList.add(`status-${statusStr.toLowerCase()}`);
        if (data.spell === 1) headEl.classList.add('is-begin-play');

        // 1. Repair Timestamp (Parse ISO from "created")
        const timeEl = clone.querySelector('.js-head-time');
        if (timeEl && data.created) {
            const dt = new Date(data.created);
            timeEl.textContent = dt.toTimeString().split(' ')[0];
        }

        // 2. Performance & Trend Logic (▲/▼)
        const deltaEl = clone.querySelector('.js-head-delta');
        const avgEl = clone.querySelector('.js-head-delta-avg');
        const trendEl = clone.querySelector('.js-head-trend');

        const currentSec = data.delta ? parseFloat(data.delta.split(':')[2]) : 0;
        const avgSec = data.average_delta ? parseFloat(data.average_delta) : 0;

        if (deltaEl) {
            deltaEl.textContent = currentSec.toFixed(1) + 's';

            if (avgSec > 0) {
                if (currentSec > (avgSec * 1.2)) {
                    deltaEl.style.color = '#ef4444'; // Slower
                    if (trendEl) {
                        trendEl.textContent = '▲';
                        trendEl.style.color = '#ef4444';
                    }
                } else if (currentSec < (avgSec * 0.8)) {
                    deltaEl.style.color = '#4ade80'; // Faster
                    if (trendEl) {
                        trendEl.textContent = '▼';
                        trendEl.style.color = '#4ade80';
                    }
                } else {
                    deltaEl.style.color = 'var(--lcars-blue)';
                    if (trendEl) {
                        trendEl.textContent = '■';
                        trendEl.style.color = '#666';
                    }
                }
            }
        }

        if (avgEl) {
            avgEl.textContent = avgSec > 0 ? `AVG: ${avgSec.toFixed(1)}s` : '';
            avgEl.style.color = '#666'; // Neutral Grey
        }

        // 3. Status & Identity
        clone.querySelector('.js-head-name').textContent = data.spell_name || "NODE";
        clone.querySelector('.js-head-target').textContent = data.target_name || "LOCAL";
        clone.querySelector('.js-head-status-pill').textContent = statusStr.toUpperCase();

        // 4. Blackboard [BB] Logic (Static Indicator)
        const hasBB = data.blackboard && Object.keys(data.blackboard).length > 0;
        const bbIndicator = clone.querySelector('.js-head-bb-indicator');
        if (bbIndicator) {
            bbIndicator.style.display = hasBB ? 'inline' : 'none';
        }

        // 5. Footer Clean-up
        const logEl = clone.querySelector('.js-head-log');
        if (logEl) {
            logEl.textContent = ['Running', 'Stopping'].includes(statusStr) ? '...' : '';
        }
    }
}