// dashboard/static/dashboard/js/swimlanes.js

const API_SUMMARY_URL = '/api/v1/dashboard/summary/';
const POLL_INTERVAL_MS = 2000;

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

async function stopSpawn(spawnId) {
    if (confirm("Signal Graceful Stop for this operation?")) {
        try {
            await fetch(`/api/v1/spawns/${spawnId}/stop/`, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': getCookie('csrftoken'),
                    'Content-Type': 'application/json'
                }
            });
            // Force an immediate UI update
            pollMissionControl();
        } catch (e) {
            console.error("Failed to stop spawn:", e);
        }
    }
}

function buildHeadHTML(head, isHistory) {
    let stateClass = '';
    let logText = '';
    let target = head.target_name || 'LOCAL';

    if (isHistory) {
        stateClass = head.status_id === 4 ? 'success' : 'failed';
        logText = head.status_name;
    } else {
        const isPending = head.status_id === 1 || head.status_id === 2;
        stateClass = isPending ? 'pending' : 'active';
        logText = isPending ? 'Waiting...' : 'Processing...';
    }

    return `
        <a href="/hydra/head/${head.id}/" class="head-card ${stateClass}" style="text-decoration: none;">
            <div class="head-name" style="color: ${isHistory ? '#ddd' : '#fff'};">${head.spell_name || 'Node'}</div>
            <div class="head-target" style="color: ${isHistory ? (head.status_id === 5 ? '#ef4444' : '#888') : 'var(--lcars-elbow)'};">
                ${target}
            </div>
            ${!isHistory ? `<div class="head-log" style="font-size:0.55rem; color:#888;">${logText}</div>` : ''}
            <div class="card-drill-btn" title="View Logs">☍</div>
        </a>
    `;
}

function buildSwimlaneHTML(mission) {
    let stateClass = '';
    if (mission.is_alive) stateClass = 'active-lane';
    else if (mission.ended_badly) stateClass = 'failed-lane';

    const statusColor = mission.is_alive ? '#f99f1b' : (mission.ended_badly ? '#ef4444' : '#666');

    let headsHtml = '';
    if (mission.live_children) {
        mission.live_children.forEach(h => headsHtml += buildHeadHTML(h, false));
    }
    if (mission.history) {
        mission.history.forEach(h => headsHtml += buildHeadHTML(h, true));
    }

    return `
        <div class="lane-wrapper" id="lane-wrapper-${mission.id}">
            <div class="swimlane ${stateClass}">
                <div class="lane-header">
                    <div class="lane-title" title="${mission.spellbook_name}">${mission.spellbook_name}</div>
                    <div class="lane-status">
                        <span>#${mission.id.substring(0, 8)}</span>
                        <span style="color: ${statusColor}; margin-left: 5px;">${mission.status_name}</span>
                    </div>
                </div>
                
                <div class="control-card ${mission.is_alive ? 'active-state' : ''}">
                    <a href="/hydra/graph/spawn/${mission.id}/" class="btn-control" title="Monitor Graph">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path>
                            <circle cx="12" cy="12" r="3"></circle>
                        </svg>
                    </a>
                    ${mission.is_alive ? `
                        <button class="btn-control stop" onclick="stopSpawn('${mission.id}')" title="Stop">
                            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="6" y="6" width="12" height="12" rx="2" ry="2"></rect></svg>
                        </button>
                    ` : ''}
                </div>

                <button class="lane-scroll-btn left" onclick="this.nextElementSibling.scrollBy({left: -300, behavior: 'smooth'})">◄</button>
                <div class="lane-scroll-area">
                    ${headsHtml}
                </div>
                <button class="lane-scroll-btn right" onclick="this.previousElementSibling.scrollBy({left: 300, behavior: 'smooth'})">►</button>
            </div>
        </div>
    `;
}

async function pollMissionControl() {
    try {
        const response = await fetch(API_SUMMARY_URL, {
            method: 'GET',
            headers: {
                'X-CSRFToken': getCookie('csrftoken'),
                'Accept': 'application/json'
            },
            credentials: 'same-origin' // CRITICAL: Ensures session cookies are sent
        });

        if (!response.ok) {
            // If we still get a 403, we log it for debugging
            if (response.status === 403) {
                console.error('API Forbidden: Are you logged in? CSRF valid?');
            }
            throw new Error(`API Error: ${response.status}`);
        }

        const data = await response.json();

        const container = document.getElementById('mission-monitor');
        if (!container) return;

        if (!data.recent_missions || data.recent_missions.length === 0) {
            container.innerHTML = '<div style="text-align:center; padding:50px; color:#444;">NO ACTIVE MISSIONS</div>';
        } else {
            container.innerHTML = data.recent_missions.map(buildSwimlaneHTML).join('');

            // Re-trigger the overflow observer from your legacy mission_control.js
            if (typeof initSwimlaneObservers === 'function') {
                initSwimlaneObservers(container);
            }
        }
    } catch (e) {
        console.error('Failed to sync missions:', e);
    } finally {
        setTimeout(pollMissionControl, POLL_INTERVAL_MS);
    }
}

document.addEventListener('DOMContentLoaded', pollMissionControl);