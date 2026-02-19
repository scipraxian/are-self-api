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
    const toolMap = new Set();

    // 1. Process Goals
    if (sessionData.goals) {
        sessionData.goals.forEach(goal => {
            nodes.push({
                id: `goal-${goal.id}`,
                type: 'goal',
                label: `Goal ${goal.id}`,
                // If you want to stop the infinite pulsing, you can artificially map the status here:
                // status: goal.status_name === 'Active' ? 'Goal_Active' : goal.status_name,
                status: goal.status_name,
                rendered_goal: goal.rendered_goal,
                created: goal.created,
                delta: goal.delta
            });
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

            // Sequence Links
            if (index > 0) {
                links.push({
                    source: `turn-${sessionData.turns[index - 1].id}`,
                    target: turnNodeId,
                    type: 'sequence'
                });
            }

            // Many-to-Many Link (Turn -> Goals)
            if (turn.turn_goals) {
                turn.turn_goals.forEach(goalId => {
                    const targetGoalId = goalId.id ? goalId.id : goalId;
                    links.push({
                        source: turnNodeId,
                        target: `goal-${targetGoalId}`,
                        type: 'addresses_goal'
                    });
                });
            }

            // Tool Links (Turn -> Tool)
            if (turn.tool_calls) {
                turn.tool_calls.forEach(call => {
                    const toolNodeId = `tool-${call.tool_name}`;

                    if (!toolMap.has(toolNodeId)) {
                        toolMap.add(toolNodeId);
                        nodes.push({
                            id: toolNodeId,
                            type: 'tool',
                            label: call.tool_name,
                            is_async: call.is_async
                        });
                    }

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
    if (oldData && oldData.nodes) {
        const oldNodeMap = new Map(oldData.nodes.map(n => [n.id, n]));
        nodes.forEach(n => {
            if (oldNodeMap.has(n.id)) {
                const old = oldNodeMap.get(n.id);
                // Copy the physics state so D3 doesn't reset them
                n.x = old.x;
                n.y = old.y;
                n.vx = old.vx;
                n.vy = old.vy;
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
    fetch(`/api/v1/reasoning_sessions/${sessionId}/graph_data/`)
        .then(response => {
            if (!response.ok) throw new Error('Network response was not ok');
            return response.json();
        })
        .then(sessionData => {
            if (typeof updateSessionInfo === 'function') {
                updateSessionInfo(sessionData);
            }

            // --- PASS currentData TO RETAIN PHYSICS ---
            const graphPayload = flattenTreeToGraph(sessionData, typeof currentData !== 'undefined' ? currentData : null);

            currentData = graphPayload;

            let shouldUpdateInspector = false;
            if (selectedNodeId) {
                const rawNode = graphPayload.nodes.find(n => n.id === selectedNodeId);
                const rawLinks = graphPayload.links.filter(l => l.target === selectedNodeId || l.source === selectedNodeId);
                const currentStateHash = JSON.stringify({node: rawNode, links: rawLinks});

                if (selectedNodeHash !== currentStateHash) {
                    shouldUpdateInspector = true;
                    selectedNodeHash = currentStateHash;
                }
            }

            updateGraph(graphPayload);

            if (shouldUpdateInspector) {
                const updatedNode = graphPayload.nodes.find(n => n.id === selectedNodeId);
                if (updatedNode) showDetails(updatedNode);
            }

            // --- THE POLLING FIX: Stop polling if the session is done ---
            // Notice we are checking status_name now!
            const isFinished = ['Completed', 'Error', 'Maxed Out', 'Stopped'].includes(sessionData.status_name);
            if (!isFinished) {
                // Safely wait for the previous call to finish before queuing the next one
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
// --- SHIELD: Drop dangling links immediately to prevent physics crash ---
    const validNodeIds = new Set(newData.nodes.map(n => n.id));
    newData.links = newData.links.filter(l => {
        const sourceId = l.source.id || l.source;
        const targetId = l.target.id || l.target;
        return validNodeIds.has(sourceId) && validNodeIds.has(targetId);
    });

    const topologyChanged = (newData.nodes.length !== currentData.nodes.length) ||
        (newData.links.length !== currentData.links.length);

    // Merge nodes to preserve X/Y coordinates
    const oldNodeMap = new Map(currentData.nodes.map(n => [n.id, n]));
    const mergedNodes = newData.nodes.map(n => {
        return oldNodeMap.has(n.id) ? Object.assign(oldNodeMap.get(n.id), n) : n;
    });

    currentData.nodes = mergedNodes;
    currentData.links = newData.links;

    // --- DATA JOIN: LINKS ---
    const links = linkGroup.selectAll("line")
        .data(currentData.links, d => `${d.source.id || d.source}-${d.target.id || d.target}`);

    const linksEnter = links.enter().append("line")
        .attr("stroke", d => d.type === 'uses_tool' ? "#cc3333" : "#999")
        .attr("stroke-width", d => d.type === 'sequence' ? 4 : 2)
        .attr("stroke-opacity", 0.6)
        .attr("stroke-dasharray", d => d.type === 'created_in' ? "5,5" : "none");

    links.exit().remove();
    const allLinks = linksEnter.merge(links);

    // --- DATA JOIN: NODES ---
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
        if (d.type === 'turn') {
            el.append("circle").attr("r", 18).attr("fill", "#f99f1b");
        } else if (d.type === 'tool') {
            el.append("rect").attr("width", 24).attr("height", 24).attr("x", -12).attr("y", -12).attr("fill", "#cc3333").attr("rx", 6);
        } else {
            el.append("polygon").attr("points", "0,-15 15,0 0,15 -15,0").attr("fill", "#cc99cc");
        }

        el.append("text")
            .attr("dy", 30)
            .attr("text-anchor", "middle")
            .text(d => d.type === 'turn' ? `T${d.turn_number}` : (d.type === 'tool' ? d.label : `M${d.id.split('-')[1].substring(0, 4)}`))
            .attr("fill", "#99ccff")
            .style("font-size", "11px")
            .style("font-weight", "bold");
    });

    nodes.exit().remove();
    const allNodes = nodesEnter.merge(nodes);

    const activeStates = ['Active', 'Pending', 'Running'];
    allNodes.classed("active-node", d => d.type === 'turn' && activeStates.includes(d.status));

    // --- EXECUTE SIMULATION ---
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

    // --- PRESERVE SCROLL STATE ---
    const prevScrollTop = scrollContainer.scrollTop;

    // Clear any existing live timer from a previous click
    if (liveTimerInterval) {
        clearInterval(liveTimerInterval);
        liveTimerInterval = null;
    }

    let html = `<div class="detail-header">${d.type.toUpperCase()}: ${d.label || d.id}</div>`;

    if (d.type === 'turn') {
        const activeStates = ['Active', 'Pending', 'Running', 'Thinking'];
        const isLive = activeStates.includes(d.status);

        // Calculate Tokens Per Second (TPS)
        let tps = "0.0";
        if (d.inference_time && d.tokens_output) {
            let seconds = parseFloat(d.inference_time.replace('s', ''));
            if (seconds > 0) tps = (d.tokens_output / seconds).toFixed(1);
        }

        html += `
            <div class="detail-row">
                <div class="detail-label">Status</div>
                <div class="detail-value" style="color:#f99f1b">${d.status}</div>
            </div>
            <div class="detail-row">
                <div class="detail-label">Turn Duration</div>
                <div class="detail-value" id="node-duration" style="color:#99ccff; font-family: monospace;">
                    ${isLive ? '⏱ Calculating...' : (d.delta || '0s')}
                </div>
            </div>
            <div class="detail-row">
                <div class="detail-label">Cognitive Load (LLM)</div>
                <div class="detail-value" style="color:#cc99cc; font-family: monospace;">
                    [ IN: ${d.tokens_input || 0} ] -> [ OUT: ${d.tokens_output || 0} ]
                </div>
            </div>
            <div class="detail-row">
                <div class="detail-label">Inference Speed</div>
                <div class="detail-value" style="color:#4ade80; font-family: monospace;">
                    ${d.inference_time || '0s'} (${tps} tokens/sec)
                </div>
            </div>
            <div class="detail-row">
                <div class="detail-label">Thought Process</div>
                <div class="detail-value text-content">${d.thought_process || 'Executing without monologue...'}</div>
            </div>
            <div class="detail-row">
                <div class="detail-label">Request Payload (JSON)</div>
                <div class="detail-value code-block">${d.request_payload ? JSON.stringify(d.request_payload, null, 2) : 'No Payload Recorded.'}</div>
            </div>
        `;

        // If the turn is currently active, run a high-frame-rate local timer
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
        const calls = currentData.links.filter(l => l.target.id === d.id && l.type === 'uses_tool');
        html += `<div class="detail-row"><div class="detail-label">Total Invocations</div><div class="detail-value">${calls.length}</div></div>`;

        calls.forEach((call, idx) => {
            const turnNum = call.source.turn_number ? call.source.turn_number : call.source.split('-')[1];
            html += `
                <div class="tool-call-block">
                    <div style="color: #99ccff; font-weight: bold; margin-bottom: 5px;">Call ${idx + 1} (Triggered by Turn ${turnNum})</div>
                    <div class="detail-label">Arguments</div>
                    <div class="detail-value code-block">${call.arguments || '{}'}</div>
                    <div class="detail-label">Result Payload</div>
                    <div class="detail-value code-block ${call.traceback ? 'error-text' : 'success-text'}">${call.result || 'Pending...'}</div>
                    ${call.traceback ? `<div class="detail-label" style="color:#cc3333;">Traceback</div><div class="detail-value code-block error-text">${call.traceback}</div>` : ''}
                </div>
            `;
        });
    } else if (d.type === 'engram') {
        html += `
            <div class="detail-row"><div class="detail-label">Relevance Score</div><div class="detail-value">${d.relevance}</div></div>
            <div class="detail-row"><div class="detail-label">Fact/Memory</div><div class="detail-value text-content">${d.description}</div></div>
        `;
    }

    panel.innerHTML = html;

    // --- RESTORE SCROLL STATE ---
    scrollContainer.scrollTop = prevScrollTop;
}

// UI Handlers
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