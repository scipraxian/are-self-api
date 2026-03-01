const API_SUMMARY_URL = '/api/v1/dashboard/summary/';
const POLL_INTERVAL_MS = 2000;
let isFirstLoad = true;
let pollTimer = null;
let lastSyncTime = null;

function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

function timeSince(dateString) {
    if (!dateString) return "0 minutes";
    const seconds = Math.floor((new Date() - new Date(dateString)) / 1000);
    let interval = seconds / 31536000;
    if (interval > 1) return Math.floor(interval) + " years";
    interval = seconds / 2592000;
    if (interval > 1) return Math.floor(interval) + " months";
    interval = seconds / 86400;
    if (interval > 1) return Math.floor(interval) + " days";
    interval = seconds / 3600;
    if (interval > 1) return Math.floor(interval) + " hours";
    interval = seconds / 60;
    if (interval > 1) return Math.floor(interval) + " minutes";
    return Math.floor(seconds) + " seconds";
}

async function stopSpawn(spikeTrainId) {
    if (confirm("Signal Graceful Stop for this operation?")) {
        try {
            await fetch(`/api/v1/spike_trains/${spikeTrainId}/stop/`, {
                method: 'POST',
                headers: {'X-CSRFToken': getCookie('csrftoken'), 'Content-Type': 'application/json'}
            });
            // Force an immediate UI update
            triggerInstantSync();
        } catch (e) {
            console.error("Failed to stop spike_train:", e);
        }
    }
}

async function rerunSpawn(pathwayId) {
    try {
        await fetch(`/api/v1/spike_trains/`, {
            method: 'POST',
            headers: {'X-CSRFToken': getCookie('csrftoken'), 'Content-Type': 'application/json'},
            body: JSON.stringify({pathway_id: pathwayId})
        });
        triggerInstantSync();
    } catch (e) {
        console.error("Failed to rerun:", e);
    }
}

function buildHeadDOM(spike) {
    // FIX: Using the correct updated template ID
    const template = document.getElementById('tpl-cns-spike');
    const clone = template.content.cloneNode(true);
    const card = clone.querySelector('.cns-spike-card');

    card.href = `/central_nervous_system/spike/${spike.id}/`;

    const nameEl = card.querySelector('.js-spike-name');
    const targetEl = card.querySelector('.js-spike-target');
    const logEl = card.querySelector('.js-spike-log');
    const timeEl = card.querySelector('.js-spike-time');
    const durationEl = card.querySelector('.js-spike-duration');

    if (nameEl) nameEl.textContent = spike.effector_name || 'Node';
    if (timeEl) timeEl.textContent = spike.timestamp_str || '--:--:--';
    if (durationEl) durationEl.textContent = `⏱ ${spike.duration || '0s'}`;

    const statusId = spike.status_id !== undefined ? spike.status_id : spike.status;

    // State Machine
    if (statusId === 1 || statusId === 2) {
        card.classList.add('status-pending');
        if (nameEl) nameEl.style.color = '#888';
        if (targetEl) {
            targetEl.style.color = '#666';
            targetEl.textContent = 'QUEUED';
        }
        if (logEl) {
            logEl.textContent = 'Waiting...';
            logEl.style.color = '#444';
            logEl.style.display = 'block';
        }
    } else if (statusId === 3 || statusId === 8) {
        card.classList.add('status-running');
        if (nameEl) nameEl.style.color = '#fff';
        if (targetEl) {
            targetEl.style.color = 'var(--lcars-elbow)';
            targetEl.textContent = spike.target_name || 'LOCAL';
        }
        if (logEl) {
            logEl.textContent = spike.status_name;
            logEl.style.color = '#888';
            logEl.style.display = 'block';
        }
    } else {
        if (nameEl) nameEl.style.color = '#ddd';
        if (logEl) logEl.style.display = 'none';

        if (statusId === 4) {
            card.classList.add('status-success');
            if (targetEl) targetEl.style.color = '#4ade80';
        } else if (statusId === 5 || statusId === 6) {
            card.classList.add('status-failed');
            if (targetEl) targetEl.style.color = '#ef4444';
        } else {
            card.classList.add('status-stopped');
            if (targetEl) targetEl.style.color = '#888';
        }

        if (targetEl) targetEl.textContent = (spike.result_code !== null) ? `RC: ${spike.result_code}` : spike.status_name;
    }

    return clone;
}

function buildSwimlaneDOM(mission, isSubgraph = false) {
    // FIX: Using the correct updated template ID
    const template = document.getElementById('tpl-cns-spike_train');
    const clone = template.content.cloneNode(true);
    const wrapper = clone.querySelector('.js-cns-spike_train-wrapper');
    const swimlane = clone.querySelector('.js-cns-spike_train');

    wrapper.id = `lane-wrapper-${mission.id}`;

    if (isSubgraph) swimlane.classList.add('subgraph');
    if (mission.is_alive) swimlane.classList.add('active-lane');
    else if (mission.ended_successfully) swimlane.classList.add('success-lane');
    else if (mission.ended_badly) swimlane.classList.add('failed-lane');


    let statusColor = '#666';
    if (mission.is_alive) statusColor = 'var(--lcars-elbow)';
    else if (mission.ended_successfully) statusColor = '#4ade80';
    else if (mission.ended_badly) statusColor = '#ef4444';

    // Header
    const titleEl = clone.querySelector('.js-spike_train-title');
    titleEl.textContent = mission.pathway_name || 'Unknown Protocol';
    titleEl.title = mission.pathway_name || '';

    clone.querySelector('.js-spike_train-id').textContent = `#${mission.id.substring(0, 8)}`;

    const statusEl = clone.querySelector('.js-spike_train-status-text');
    statusEl.textContent = mission.status_name;
    statusEl.style.color = statusColor;

    clone.querySelector('.js-spike_train-time').textContent = `${timeSince(mission.modified)} ago`;

    // Controls
    clone.querySelector('.js-btn-monitor').href = `/central_nervous_system/graph/spike_train/${mission.id}/?full=True`;
    clone.querySelector('.js-btn-edit').href = `/central_nervous_system/graph/editor/${mission.pathway}/`;

    if (mission.is_alive) {
        clone.querySelector('.js-cns-control-card').classList.add('active-state');
        const stopBtn = clone.querySelector('.js-btn-stop');
        stopBtn.style.display = 'flex';
        stopBtn.onclick = () => stopSpawn(mission.id);
    } else {
        const rerunBtn = clone.querySelector('.js-btn-rerun');
        rerunBtn.style.display = 'flex';
        rerunBtn.onclick = () => rerunSpawn(mission.pathway);
    }

    // Scroll Area (Heads)
    const scrollArea = clone.querySelector('.js-spike_train-track');
    if (mission.live_children) {
        mission.live_children.forEach(h => scrollArea.appendChild(buildHeadDOM(h)));
    }
    if (mission.history) {
        mission.history.forEach(h => scrollArea.appendChild(buildHeadDOM(h)));
    }

    // Scroll Buttons
    clone.querySelector('.js-scroll-left').onclick = function () {
        this.nextElementSibling.scrollBy({left: -300, behavior: 'smooth'});
    };
    clone.querySelector('.js-scroll-right').onclick = function () {
        this.previousElementSibling.scrollBy({left: 300, behavior: 'smooth'});
    };

    // Subgraphs
    const subContainer = clone.querySelector('.js-nested-spike_trains');
    if (mission.subgraphs && mission.subgraphs.length > 0) {
        mission.subgraphs.forEach(sub => subContainer.appendChild(buildSwimlaneDOM(sub, true)));
    }

    return clone;
}

async function pollMissionControl() {
    try {
        let fetchUrl = isFirstLoad ? API_SUMMARY_URL : `${API_SUMMARY_URL}?static=false`;

        if (lastSyncTime) {
            const separator = fetchUrl.includes('?') ? '&' : '?';
            fetchUrl += `${separator}last_sync=${encodeURIComponent(lastSyncTime)}`;
        }

        const response = await fetch(fetchUrl, {
            method: 'GET',
            headers: {
                'X-CSRFToken': getCookie('csrftoken'),
                'Accept': 'application/json'
            },
            credentials: 'same-origin'
        });

        if (!response.ok) throw new Error(`API Error: ${response.status}`);

        const data = await response.json();

        if (data.server_time) {
            lastSyncTime = data.server_time;
        }

        const container = document.getElementById('mission-monitor');
        if (!container) return;

        if (!data.recent_missions || data.recent_missions.length === 0) {
            if (isFirstLoad) {
                container.innerHTML = '<div style="text-align:center; padding:50px; color:#444;">NO ACTIVE MISSIONS</div>';
            }
        } else {
            // Remove the empty placeholder if a job arrives
            const emptyMsg = container.querySelector('div[style*="NO ACTIVE MISSIONS"]');
            if (emptyMsg) emptyMsg.remove();

            data.recent_missions.forEach(mission => {
                const existingLane = document.getElementById(`lane-wrapper-${mission.id}`);
                const newLane = buildSwimlaneDOM(mission, false);

                if (existingLane) {
                    existingLane.replaceWith(newLane); // Delta DOM Patch
                } else {
                    container.prepend(newLane); // Insert newly started jobs at the top
                }
            });

            if (typeof initSwimlaneObservers === 'function') {
                initSwimlaneObservers(container);
            }
        }

        isFirstLoad = false;

    } catch (e) {
        console.error('Failed to sync missions:', e);
    } finally {
        pollTimer = setTimeout(pollMissionControl, POLL_INTERVAL_MS);
    }
}

function triggerInstantSync() {
    console.log("[SYNC] Action detected. Bypassing timer.");
    clearTimeout(pollTimer);
    pollMissionControl();
}

// Listen for the exact event your Launch buttons broadcast!
document.body.addEventListener('monitor-update', triggerInstantSync);

document.addEventListener('DOMContentLoaded', pollMissionControl);