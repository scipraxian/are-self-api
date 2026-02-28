/**
 * Talos CNS Spike Controller
 * Refactored for High-Density LCARS UI
 */

class SpikeController {
    constructor(element) {
        this.el = element;
    }

    static populateTemplate(clone, data) {
        const headEl = clone.querySelector('.js-cns-spike');
        if (!headEl) return;

        headEl.dataset.headId = data.id;
        const statusStr = data.status_name || 'Pending';
        const isAlive = ['Created', 'Pending', 'Running', 'Delegated', 'Stopping'].includes(statusStr);

        headEl.href = `/central_nervous_system/spike/${data.id}/`;

        // Visual State Reset
        headEl.className = 'cns-spike-card js-cns-spike';
        headEl.classList.add(`status-${statusStr.toLowerCase()}`);
        if (data.effector === 1) headEl.classList.add('is-begin-play');

        // 1. Repair Timestamp (Parse ISO from "created")
        const timeEl = clone.querySelector('.js-spike-time');
        if (timeEl && data.created) {
            const dt = new Date(data.created);
            timeEl.textContent = dt.toTimeString().split(' ')[0];
        }

        // 2. Performance & Trend Logic (▲/▼)
        const deltaEl = clone.querySelector('.js-spike-delta');
        const avgEl = clone.querySelector('.js-spike-delta-avg');
        const trendEl = clone.querySelector('.js-spike-trend');

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
        clone.querySelector('.js-spike-name').textContent = data.spell_name || "NODE";
        clone.querySelector('.js-spike-target').textContent = data.target_name || "LOCAL";
        clone.querySelector('.js-spike-status-pill').textContent = statusStr.toUpperCase();

        // 4. Blackboard [BB] Logic (Static Indicator)
        const hasBB = data.blackboard && Object.keys(data.blackboard).length > 0;
        const bbIndicator = clone.querySelector('.js-spike-bb-indicator');
        if (bbIndicator) {
            bbIndicator.style.display = hasBB ? 'inline' : 'none';
        }

        // 5. Footer Clean-up
        const logEl = clone.querySelector('.js-spike-log');
        if (logEl) {
            logEl.textContent = ['Running', 'Stopping'].includes(statusStr) ? '...' : '';
        }
    }
}