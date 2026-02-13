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

async function stopSpawn(spawnId) {
    if (confirm("Signal Graceful Stop for this operation?")) {
        try {
            await fetch(`/api/v1/spawns/${spawnId}/stop/`, {
                method: 'POST',
                headers: {'X-CSRFToken': getCookie('csrftoken'), 'Content-Type': 'application/json'}
            });
            // Force an immediate UI update
            triggerInstantSync();
        } catch (e) {
            console.error("Failed to stop spawn:", e);
        }
    }
}

async function rerunSpawn(spellbookId) {
    try {
        await fetch(`/api/v1/spawns/`, {
            method: 'POST',
            headers: {'X-CSRFToken': getCookie('csrftoken'), 'Content-Type': 'application/json'},
            body: JSON.stringify({spellbook_id: spellbookId})
        });
        triggerInstantSync();
    } catch (e) {
        console.error("Failed to rerun:", e);
    }
}

function buildHeadDOM(head, isHistory) {
    const template = document.getElementById('tpl-head-card');
    const clone = template.content.cloneNode(true);
    const card = clone.querySelector('.head-card');

    card.href = `/hydra/head/${head.id}/`;
    card.querySelector('.head-name').textContent = head.spell_name || 'Node';

    const targetEl = card.querySelector('.head-target');
    const logEl = card.querySelector('.head-log');

    if (isHistory) {
        // [FIX] Correct LCARS color mapping for history blocks
        let stateClass = 'stopped';
        let targetColor = '#888';

        if (head.status_id === 4) {
            stateClass = 'success';
            targetColor = '#4ade80';
        } else if (head.status_id === 5 || head.status_id === 6) {
            stateClass = 'failed';
            targetColor = '#ef4444';
        }

        card.classList.add(stateClass);
        card.querySelector('.head-name').style.color = '#ddd';
        targetEl.style.color = targetColor;
        targetEl.textContent = (head.result_code !== null) ? `RC: ${head.result_code}` : head.status_name;
        logEl.style.display = 'none';
    } else {
        const isPending = head.status_id === 1 || head.status_id === 2;
        if (isPending) {
            card.classList.add('pending');
            card.querySelector('.head-name').style.color = '#888';
            targetEl.style.color = '#666';
            targetEl.textContent = 'QUEUED';
            logEl.textContent = 'Waiting...';
        } else {
            card.classList.add('active');
            card.querySelector('.head-name').style.color = '#fff';
            targetEl.style.color = 'var(--lcars-elbow)';
            targetEl.textContent = head.target_name || 'LOCAL';
            logEl.textContent = head.status_name;
        }
    }
    return clone;
}

function buildSwimlaneDOM(mission, isSubgraph = false) {
    const template = document.getElementById('tpl-swimlane');
    const clone = template.content.cloneNode(true);
    const wrapper = clone.querySelector('.lane-wrapper');
    const swimlane = clone.querySelector('.swimlane');

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
    const titleEl = clone.querySelector('.lane-title');
    titleEl.textContent = mission.spellbook_name || 'Unknown Protocol';
    titleEl.title = mission.spellbook_name || '';

    clone.querySelector('.spawn-id').textContent = `#${mission.id.substring(0, 8)}`;

    const statusEl = clone.querySelector('.lane-status-text');
    statusEl.textContent = mission.status_name;
    statusEl.style.color = statusColor;
    // statusEl.classList.add(`status-${mission.status_name.toLowerCase()}`);

    clone.querySelector('.lane-time').textContent = `${timeSince(mission.modified)} ago`;

    // Controls
    clone.querySelector('.btn-monitor').href = `/hydra/graph/spawn/${mission.id}/?full=True`;
    clone.querySelector('.btn-edit').href = `/hydra/graph/editor/${mission.spellbook}/`;

    if (mission.is_alive) {
        clone.querySelector('.control-card').classList.add('active-state');
        const stopBtn = clone.querySelector('.btn-stop');
        stopBtn.style.display = 'flex';
        stopBtn.onclick = () => stopSpawn(mission.id);
    } else {
        const rerunBtn = clone.querySelector('.btn-rerun');
        rerunBtn.style.display = 'flex';
        rerunBtn.onclick = () => rerunSpawn(mission.spellbook);
    }

    // Scroll Area (Heads)
    const scrollArea = clone.querySelector('.lane-scroll-area');
    if (mission.live_children) {
        mission.live_children.forEach(h => scrollArea.appendChild(buildHeadDOM(h, false)));
    }
    if (mission.history) {
        mission.history.forEach(h => scrollArea.appendChild(buildHeadDOM(h, true)));
    }

    // Scroll Buttons
    clone.querySelector('.left').onclick = function () {
        this.nextElementSibling.scrollBy({left: -300, behavior: 'smooth'});
    };
    clone.querySelector('.right').onclick = function () {
        this.previousElementSibling.scrollBy({left: 300, behavior: 'smooth'});
    };

    // Subgraphs
    const subContainer = clone.querySelector('.subgraphs-container');
    if (mission.subgraphs && mission.subgraphs.length > 0) {
        mission.subgraphs.forEach(sub => subContainer.appendChild(buildSwimlaneDOM(sub, true)));
    }

    return clone;
}

async function pollMissionControl() {
    try {
        let fetchUrl = isFirstLoad ? API_SUMMARY_URL : `${API_SUMMARY_URL}?static=false`;

        if (lastSyncTime) {
            fetchUrl += `&last_sync=${encodeURIComponent(lastSyncTime)}`;
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

// [FIX] Listen for the exact event your Launch buttons broadcast!
document.body.addEventListener('monitor-update', triggerInstantSync);

document.addEventListener('DOMContentLoaded', pollMissionControl);