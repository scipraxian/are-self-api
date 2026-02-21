const POLL_INTERVAL_MS = 2500;
let sessionId;
let svg, g, simulation;
let linkGroup, nodeGroup;
let currentData = {nodes: [], links: []};
let selectedNodeId = null;
let selectedNodeHash = null;
let pollTimer;
let liveTimerInterval = null;

function flattenTreeToGraph(sessionData, oldData) {
    const nodes = [];
    const links = [];

    let firstTurnId = null;
    if (sessionData.turns && sessionData.turns.length > 0) {
        // Assuming turns are sorted, index 0 is the first turn
        firstTurnId = `turn-${sessionData.turns[0].id}`;
    }

    // 1. Process Goals
    if (sessionData.goals) {
        sessionData.goals.forEach(goal => {
            const goalNodeId = `goal-${goal.id}`;
            nodes.push({
                id: goalNodeId,
                type: 'goal',
                label: `Goal ${goal.id}`,
                status: goal.status_name,
                rendered_goal: goal.rendered_goal,
                created: goal.created,
                delta: goal.delta
            });
            if (firstTurnId) {
                links.push({
                    source: firstTurnId,
                    target: goalNodeId,
                    type: 'goal_anchor'
                });
            }
        });
    }

    // 2. Process Turns & Tools
    if (sessionData.turns) {
        sessionData.turns.forEach((turn, index) => {
            const turnNodeId = `turn-${turn.id}`;

            nodes.push({
                id: turnNodeId,
                type: 'turn',
                label: `Turn ${turn.turn_number}`,
                turn_number: turn.turn_number,
                status: turn.status_name,
                thought_process: turn.thought_process,
                request_payload: turn.request_payload,
                tokens_input: turn.tokens_input,
                tokens_output: turn.tokens_output,
                inference_time: turn.inference_time,
                created: turn.created,
                delta: turn.delta
            });

            // Sequence Links (The Timeline)
            if (index > 0) {
                links.push({
                    source: `turn-${sessionData.turns[index - 1].id}`,
                    target: turnNodeId,
                    type: 'sequence'
                });
            }

            // --- GRAVITY FIX: Turn -> Goal links removed so it doesn't clump ---

            // --- TREE FIX: Make tool nodes unique per call so they branch outward ---
            if (turn.tool_calls) {
                turn.tool_calls.forEach((call, callIdx) => {
                    const toolNodeId = `tool-${turn.id}-${call.tool_name}-${callIdx}`;

                    nodes.push({
                        id: toolNodeId,
                        type: 'tool',
                        label: call.tool_name,
                        is_async: call.is_async
                    });

                    links.push({
                        source: turnNodeId,
                        target: toolNodeId,
                        type: 'uses_tool',
                        call_id: call.call_id,
                        arguments: call.arguments,
                        result: call.result_payload,
                        traceback: call.traceback
                    });
                });
            }
        });
    }

    // 3. Process Engrams
    if (sessionData.engrams) {
        sessionData.engrams.forEach(engram => {
            const engramNodeId = `engram-${engram.id}`;
            nodes.push({
                id: engramNodeId,
                type: 'engram',
                label: `Engram ${engram.id}`,
                name: engram.name,
                description: engram.description,
                relevance: engram.relevance_score
            });

            if (engram.source_turns) {
                engram.source_turns.forEach(turnId => {
                    links.push({
                        source: `turn-${turnId}`,
                        target: engramNodeId,
                        type: 'created_in'
                    });
                });
            }
        });
    }

    // Preserve Physics & Spawn gracefully
    if (oldData && oldData.nodes) {
        const oldNodeMap = new Map(oldData.nodes.map(n => [n.id, n]));
        nodes.forEach(n => {
            if (oldNodeMap.has(n.id)) {
                const old = oldNodeMap.get(n.id);
                n.x = old.x;
                n.y = old.y;
                n.vx = old.vx;
                n.vy = old.vy;
            } else if (n.type === 'turn') {
                // If a new turn spawns, put it near the previous turn so it doesn't fly across the screen
                const prevTurn = nodes.find(prev => prev.type === 'turn' && prev.turn_number === n.turn_number - 1);
                if (prevTurn && oldNodeMap.has(prevTurn.id)) {
                    const oldPrev = oldNodeMap.get(prevTurn.id);
                    n.x = oldPrev.x + 50;
                    n.y = oldPrev.y + 50;
                }
            }
        });
    }
    return {nodes, links};
}

document.addEventListener('DOMContentLoaded', () => {
    sessionId = document.getElementById('lcars-data').dataset.sessionId;
    initGraphContainer();
    fetchData();
});

function fetchData() {
    // --- CACHE BUSTER FIX: Forces the browser to actually get new turns ---
    const url = `/api/v1/reasoning_sessions/${sessionId}/graph_data/?_ts=${Date.now()}`;

    fetch(url)
        .then(response => {
            if (!response.ok) throw new Error('Network response was not ok');
            return response.json();
        })
        .then(sessionData => {
            if (typeof updateSessionInfo === 'function') {
                updateSessionInfo(sessionData);
            }

            const graphPayload = flattenTreeToGraph(sessionData, typeof currentData !== 'undefined' ? currentData : null);

            let shouldUpdateInspector = false;
            if (selectedNodeId) {
                const rawNode = graphPayload.nodes.find(n => n.id === selectedNodeId);
                const rawLinks = graphPayload.links.filter(l => (l.target.id || l.target) === selectedNodeId || (l.source.id || l.source) === selectedNodeId);

                if (rawNode) {
                    // --- SCROLL/JITTER FIX: Create a clean hash without timers or physics ---
                    const cleanNode = {...rawNode};
                    delete cleanNode.x;
                    delete cleanNode.y;
                    delete cleanNode.vx;
                    delete cleanNode.vy;
                    delete cleanNode.index;
                    delete cleanNode.delta;
                    delete cleanNode.inference_time;

                    const currentStateHash = JSON.stringify({node: cleanNode, linkCount: rawLinks.length});

                    if (selectedNodeHash !== currentStateHash) {
                        shouldUpdateInspector = true;
                        selectedNodeHash = currentStateHash;
                    }
                }
            }

            updateGraph(graphPayload);

            if (shouldUpdateInspector) {
                const updatedNode = graphPayload.nodes.find(n => n.id === selectedNodeId);
                if (updatedNode) showDetails(updatedNode);
            }

            const isFinished = ['Completed', 'Error', 'Maxed Out', 'Stopped'].includes(sessionData.status_name);
            if (!isFinished) {
                pollTimer = setTimeout(fetchData, POLL_INTERVAL_MS);
            }
        })
        .catch(error => console.error('Graph Data Fetch Error:', error));
}

function updateSessionInfo(session) {
    document.getElementById('session-status').textContent = session.status_name;
}

function initGraphContainer() {
    const width = document.getElementById('graph-container').clientWidth;
    const height = document.getElementById('graph-container').clientHeight;

    svg = d3.select("#graph-container").append("svg")
        .attr("width", width)
        .attr("height", height)
        .call(d3.zoom().scaleExtent([0.1, 4]).on("zoom", (event) => {
            g.attr("transform", event.transform);
        }));

    g = svg.append("g");
    linkGroup = g.append("g").attr("class", "links");
    nodeGroup = g.append("g").attr("class", "nodes");

    simulation = d3.forceSimulation()
        .force("link", d3.forceLink().id(d => d.id).distance(120))
        .force("charge", d3.forceManyBody().strength(-400))
        .force("center", d3.forceCenter(width / 2, height / 2))
        .force("collide", d3.forceCollide().radius(40));
}

function updateGraph(newData) {
    const validNodeIds = new Set(newData.nodes.map(n => n.id));
    newData.links = newData.links.filter(l => {
        const sourceId = l.source.id || l.source;
        const targetId = l.target.id || l.target;
        return validNodeIds.has(sourceId) && validNodeIds.has(targetId);
    });

    const topologyChanged = (newData.nodes.length !== currentData.nodes.length) ||
        (newData.links.length !== currentData.links.length);

    const oldNodeMap = new Map(currentData.nodes.map(n => [n.id, n]));
    const mergedNodes = newData.nodes.map(n => {
        return oldNodeMap.has(n.id) ? Object.assign(oldNodeMap.get(n.id), n) : n;
    });

    currentData.nodes = mergedNodes;
    currentData.links = newData.links;

    const links = linkGroup.selectAll("line")
        .data(currentData.links, d => `${d.source.id || d.source}-${d.target.id || d.target}-${d.type}`);

    const linksEnter = links.enter().append("line")
        .attr("stroke", d => {
            if (d.type === 'uses_tool') return "#cc3333";
            if (d.type === 'goal_anchor') return "#f99f1b"; // Gold tether
            return "#999";
        })
        .attr("stroke-width", d => d.type === 'sequence' ? 4 : 2)
        // Make the tether highly transparent
        .attr("stroke-opacity", d => d.type === 'goal_anchor' ? 0.2 : 0.6)
        // Make the tether dotted
        .attr("stroke-dasharray", d => (d.type === 'created_in' || d.type === 'goal_anchor') ? "5,5" : "none");

    links.exit().remove();
    const allLinks = linksEnter.merge(links);

    const nodes = nodeGroup.selectAll("g")
        .data(currentData.nodes, d => d.id);

    const nodesEnter = nodes.enter().append("g")
        .call(drag(simulation))
        .on("click", (event, d) => {
            selectedNodeId = d.id;
            selectedNodeHash = null;
            nodeGroup.selectAll("g").classed("selected", false);
            d3.select(event.currentTarget).classed("selected", true);
            showDetails(d);
        });

    nodesEnter.each(function (d) {
        const el = d3.select(this);

        // 1. SHAPE & COLOR
        if (d.type === 'turn') {
            el.append("circle").attr("r", 18).attr("fill", "#f99f1b"); // LCARS Orange
        } else if (d.type === 'tool') {
            el.append("rect").attr("width", 24).attr("height", 24).attr("x", -12).attr("y", -12).attr("fill", "#cc3333").attr("rx", 6); // Red Square
        } else if (d.type === 'goal') {
            // New Shape: Larger LCARS Blue Diamond for Strategic Goals
            el.append("polygon").attr("points", "0,-22 22,0 0,22 -22,0").attr("fill", "#38bdf8");
        } else {
            // Engrams: Standard Purple Diamond
            el.append("polygon").attr("points", "0,-15 15,0 0,15 -15,0").attr("fill", "#cc99cc");
        }

        // 2. TEXT LABEL
        el.append("text")
            .attr("dy", 32)
            .attr("text-anchor", "middle")
            .text(d => {
                if (d.type === 'turn') return `T${d.turn_number}`;
                if (d.type === 'tool') return d.label;
                if (d.type === 'goal') return `G${d.id.split('-')[1].substring(0, 4)}`; // G-Prefix for Goal
                return `M${d.id.split('-')[1].substring(0, 4)}`; // M-Prefix for Memory/Engram
            })
            .attr("fill", "#99ccff")
            .style("font-size", "11px")
            .style("font-weight", "bold");
    });

    nodes.exit().remove();
    const allNodes = nodesEnter.merge(nodes);

    const activeStates = ['Active', 'Pending', 'Running'];
    allNodes.classed("active-node", d => d.type === 'turn' && activeStates.includes(d.status));

    simulation.nodes(currentData.nodes);
    simulation.force("link").links(currentData.links);

    if (topologyChanged) {
        simulation.alpha(0.3).restart();
    }

    simulation.on("tick", () => {
        allLinks
            .attr("x1", d => d.source.x)
            .attr("y1", d => d.source.y)
            .attr("x2", d => d.target.x)
            .attr("y2", d => d.target.y);
        allNodes.attr("transform", d => `translate(${d.x},${d.y})`);
    });
}

function showDetails(d) {
    const panel = document.getElementById('details-content');
    const scrollContainer = document.getElementById('details-panel');
    const prevScrollTop = scrollContainer.scrollTop;

    if (liveTimerInterval) {
        clearInterval(liveTimerInterval);
        liveTimerInterval = null;
    }

    const dbId = d.id.split('-').slice(1).join('-');
    let adminUrl = '#';

    if (d.type === 'turn') adminUrl = `/admin/talos_reasoning/reasoningturn/${dbId}/change/`;
    else if (d.type === 'goal') adminUrl = `/admin/talos_reasoning/reasoninggoal/${dbId}/change/`;
    else if (d.type === 'session') adminUrl = `/admin/talos_reasoning/reasoningsession/${dbId}/change/`;
    else if (d.type === 'engram') adminUrl = `/admin/talos_hippocampus/talosengram/${dbId}/change/`;
    // We appended an index to tools to separate them, so safely extract the original DB name for the search link
    else if (d.type === 'tool') {
        const toolName = d.id.split('-')[2];
        adminUrl = `/admin/talos_parietal/tooldefinition/?q=${toolName}`;
    }

    let html = `<div class="detail-header">${d.type.toUpperCase()}: ${d.label || d.id}</div>`;

    html += `
        <div class="detail-row" style="align-items: center;">
            <div class="detail-label">Database Record</div>
            <div class="detail-value">
                <a href="${adminUrl}" target="_blank" style="color: #1a1a1a; background-color: #f99f1b; text-decoration: none; font-size: 11px; font-weight: bold; padding: 4px 8px; border-radius: 3px; display: inline-block; letter-spacing: 1px;">OPEN IN ADMIN ↗</a>
            </div>
        </div>
    `;

    if (d.type === 'goal') {
        html += `
            <div class="detail-row"><div class="detail-label">Status</div><div class="detail-value" style="color:#f99f1b">${d.status}</div></div>
            <div class="detail-row"><div class="detail-label">Duration</div><div class="detail-value" style="color:#99ccff; font-family: monospace;">${d.delta || '0s'}</div></div>
            <div class="detail-row"><div class="detail-label">Objective</div><div class="detail-value text-content">${d.rendered_goal || 'No goal text provided.'}</div></div>
        `;
    } else if (d.type === 'engram') {
        html += `
            <div class="detail-row"><div class="detail-label">Memory Key</div><div class="detail-value code-block">${d.name || 'Unnamed Hash'}</div></div>
            <div class="detail-row"><div class="detail-label">Relevance Score</div><div class="detail-value">${d.relevance}</div></div>
            <div class="detail-row"><div class="detail-label">Fact/Memory</div><div class="detail-value text-content">${d.description}</div></div>
        `;
    } else if (d.type === 'turn') {
        const activeStates = ['Active', 'Pending', 'Running', 'Thinking'];
        const isLive = activeStates.includes(d.status);

        let tps = "0.0";
        if (d.inference_time && d.tokens_output) {
            let seconds = parseFloat(d.inference_time.replace('s', ''));
            if (seconds > 0) tps = (d.tokens_output / seconds).toFixed(1);
        }

        html += `
            <div class="detail-row"><div class="detail-label">Status</div><div class="detail-value" style="color:#f99f1b">${d.status}</div></div>
            <div class="detail-row">
                <div class="detail-label">Turn Duration</div>
                <div class="detail-value" id="node-duration" style="color:#99ccff; font-family: monospace;">${isLive ? '⏱ Calculating...' : (d.delta || '0s')}</div>
            </div>
            <div class="detail-row">
                <div class="detail-label">Cognitive Load</div>
                <div class="detail-value" style="color:#cc99cc; font-family: monospace;">[ IN: ${d.tokens_input || 0} ] -> [ OUT: ${d.tokens_output || 0} ]</div>
            </div>
            <div class="detail-row"><div class="detail-label">Inference Speed</div><div class="detail-value" style="color:#4ade80; font-family: monospace;">${d.inference_time || '0s'} (${tps} tokens/sec)</div></div>
            <div class="detail-row"><div class="detail-label">Thought Process</div><div class="detail-value text-content">${d.thought_process || 'Executing without monologue...'}</div></div>
            <div class="detail-row">
                <div class="detail-label">Request Payload</div>
                <div class="detail-value code-block" style="padding: 5px;">
                    ${d.request_payload ? renderJsonTree(d.request_payload) : '<span style="color:#666; font-style:italic;">No Payload Recorded.</span>'}
                </div>
            </div>
        `;

        if (isLive && d.created) {
            const startTime = new Date(d.created).getTime();
            liveTimerInterval = setInterval(() => {
                const clockEl = document.getElementById('node-duration');
                if (clockEl) {
                    const diffMs = Date.now() - startTime;
                    clockEl.textContent = `⏱ ${(diffMs / 1000).toFixed(1)}s`;
                } else {
                    clearInterval(liveTimerInterval);
                }
            }, 100);
        }
    } else if (d.type === 'tool') {
        const calls = currentData.links.filter(l => (l.target.id || l.target) === d.id && l.type === 'uses_tool');

        calls.forEach((call, idx) => {
            html += `
                <div class="tool-call-block">
                    <div style="color: #99ccff; font-weight: bold; margin-bottom: 5px;">Call Payload</div>
                    <div class="detail-label">Arguments</div>
                    <div class="detail-value code-block" style="padding: 5px;">
                        ${call.arguments ? renderJsonTree(call.arguments) : '{}'}
                    </div>
                    <div class="detail-label">Result Payload</div>
                    <div class="detail-value code-block ${call.traceback ? 'error-text' : 'success-text'}">${call.result || 'Pending...'}</div>
                    ${call.traceback ? `<div class="detail-label" style="color:#cc3333;">Traceback</div><div class="detail-value code-block error-text">${call.traceback}</div>` : ''}
                </div>
            `;
        });
    }

    panel.innerHTML = html;
    scrollContainer.scrollTop = prevScrollTop;
}

document.getElementById('btn-expand').addEventListener('click', () => {
    const panel = document.getElementById('details-panel');
    panel.classList.toggle('expanded');
    document.getElementById('btn-expand').textContent = panel.classList.contains('expanded') ? 'COLLAPSE' : 'EXPAND';
});

function drag(simulation) {
    function dragstarted(event) {
        if (!event.active) simulation.alphaTarget(0.3).restart();
        event.subject.fx = event.subject.x;
        event.subject.fy = event.subject.y;
    }

    function dragged(event) {
        event.subject.fx = event.x;
        event.subject.fy = event.y;
    }

    function dragended(event) {
        if (!event.active) simulation.alphaTarget(0);
        event.subject.fx = null;
        event.subject.fy = null;
    }

    return d3.drag().on("start", dragstarted).on("drag", dragged).on("end", dragended);
}

function renderJsonTree(data) {
    if (typeof data === 'string') {
        try {
            data = JSON.parse(data);
        } catch (e) {
            return `<div class="json-value string">${data}</div>`;
        }
    }

    if (data === null) return '<span class="json-value null">null</span>';
    if (typeof data !== 'object') return `<span class="json-value ${typeof data}">${data}</span>`;

    const isArray = Array.isArray(data);
    const isEmpty = isArray ? data.length === 0 : Object.keys(data).length === 0;

    if (isEmpty) return `<span class="json-value string">${isArray ? '[]' : '{}'}</span>`;

    // ALL HTML MUST BE ON ONE LINE to prevent pre-wrap from rendering tabs/newlines
    let html = `<details open class="json-node" style="margin:0;"><summary class="json-summary" style="margin:0;">${isArray ? 'Array [' + data.length + ']' : 'Object'}</summary><div class="json-children">`;

    for (const key in data) {
        html += `<div class="json-row"><span class="json-key">"${key}":</span><div style="flex: 1;">${renderJsonTree(data[key])}</div></div>`;
    }

    html += `</div></details>`;
    return html;
}

// --- CSRF Helper ---
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

// --- Reboot Cortex Logic ---
document.addEventListener('DOMContentLoaded', () => {
    const rebootBtn = document.getElementById('btn-reboot');
    if (rebootBtn) {
        rebootBtn.addEventListener('click', () => {
            if (confirm("WARNING: Rebooting the Cortex will re-cast the original spell and begin a completely new memory session. Proceed?")) {

                rebootBtn.style.opacity = '0.5';
                rebootBtn.textContent = 'REBOOTING...';

                fetch(`/api/v1/reasoning_sessions/${sessionId}/rerun/`, {
                    method: 'POST',
                    headers: {
                        'X-CSRFToken': getCookie('csrftoken'),
                        'Content-Type': 'application/json'
                    }
                })
                    .then(response => response.json())
                    .then(data => {
                        if (data.spawn_id) {
                            // Redirect to the Hydra Monitor to watch the new process spin up
                            window.location.href = `/hydra/graph/spawn/${data.spawn_id}/?full=True`;
                        } else {
                            alert("Reboot triggered, but failed to find Spawn ID.");
                        }
                    })
                    .catch(err => {
                        console.error(err);
                        rebootBtn.style.opacity = '1';
                        rebootBtn.textContent = 'REBOOT CORTEX';
                    });
            }
        });
    }
});