const POLL_INTERVAL_MS = 2500;
let sessionId;
let svg, g, simulation;
let linkGroup, nodeGroup;
let currentData = { nodes: [], links: [] };
let selectedNodeId = null;
let selectedNodeHash = null;
let pollTimer;
let liveTimerInterval = null;
let currentSessionData = null;
let globalHudTimer = null;

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

    // 4. Process Conclusion
    if (sessionData.conclusion) {
        const conclusionNodeId = `conclusion-${sessionData.conclusion.id}`;
        nodes.push({
            id: conclusionNodeId,
            type: 'conclusion',
            label: 'Final Report',
            status: sessionData.conclusion.status_name,
            summary: sessionData.conclusion.summary,
            reasoning_trace: sessionData.conclusion.reasoning_trace,
            outcome_status: sessionData.conclusion.outcome_status,
            recommended_action: sessionData.conclusion.recommended_action,
            next_goal_suggestion: sessionData.conclusion.next_goal_suggestion,
        });

        // Link it to the last turn
        if (sessionData.turns && sessionData.turns.length > 0) {
            const lastTurnId = sessionData.turns[sessionData.turns.length - 1].id;
            links.push({
                source: `turn-${lastTurnId}`,
                target: conclusionNodeId,
                type: 'sequence' // Treat it like the final sequence step
            });
        }
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
    return { nodes, links };
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
            currentSessionData = sessionData;
            if (typeof updateSessionInfo === 'function') {
                updateSessionInfo(sessionData);
            }
            if (typeof updateTalosHUD === 'function') {
                let latestTurn = null;
                if (sessionData.turns && sessionData.turns.length > 0) {
                    latestTurn = sessionData.turns[sessionData.turns.length - 1];
                }
                updateTalosHUD(sessionData, latestTurn);
            }

            const graphPayload = flattenTreeToGraph(sessionData, typeof currentData !== 'undefined' ? currentData : null);

            let shouldUpdateInspector = false;
            if (selectedNodeId) {
                const rawNode = graphPayload.nodes.find(n => n.id === selectedNodeId);
                const rawLinks = graphPayload.links.filter(l => (l.target.id || l.target) === selectedNodeId || (l.source.id || l.source) === selectedNodeId);

                if (rawNode) {
                    // --- SCROLL/JITTER FIX: Create a clean hash without timers or physics ---
                    const cleanNode = { ...rawNode };
                    delete cleanNode.x;
                    delete cleanNode.y;
                    delete cleanNode.vx;
                    delete cleanNode.vy;
                    delete cleanNode.index;
                    delete cleanNode.delta;
                    delete cleanNode.inference_time;

                    const currentStateHash = JSON.stringify({ node: cleanNode, linkCount: rawLinks.length });

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

            // Toggle Halt / Download Buttons
            const haltBtn = document.getElementById('btn-halt');
            const downloadBtn = document.getElementById('btn-download');
            if (isFinished) {
                if (haltBtn) haltBtn.style.display = 'none';
                if (downloadBtn) downloadBtn.style.display = 'flex';
            } else {
                if (haltBtn) haltBtn.style.display = 'flex';
                if (downloadBtn) downloadBtn.style.display = 'none';
            }

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
            // Node circles are initialized with a base size 18, and updated later.
            el.append("circle").attr("r", 18).attr("fill", "#f99f1b"); // LCARS Orange
        } else if (d.type === 'tool') {
            el.append("rect").attr("width", 24).attr("height", 24).attr("x", -12).attr("y", -12).attr("fill", "#cc3333").attr("rx", 6); // Red Square
        } else if (d.type === 'goal') {
            // New Shape: Larger LCARS Blue Diamond for Strategic Goals
            el.append("polygon").attr("points", "0,-22 22,0 0,22 -22,0").attr("fill", "#38bdf8");
        } else if (d.type === 'conclusion') {
            // Hexagon for the Final Conclusion
            el.append("polygon").attr("points", "0,-25 22,-12 22,12 0,25 -22,12 -22,-12").attr("fill", "#4ade80");
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
                if (d.type === 'conclusion') return 'REPORT';
                if (d.type === 'goal') return `G${d.id.split('-')[1].substring(0, 4)}`; // G-Prefix for Goal
                return `M${d.id.split('-')[1].substring(0, 4)}`; // M-Prefix for Memory/Engram
            })
            .attr("fill", "#99ccff")
            .style("font-size", "11px")
            .style("font-weight", "bold");
    });

    nodes.exit().remove();
    const allNodes = nodesEnter.merge(nodes);

    // Helper to parse Django duration string (e.g. "00:00:23.456" or "1.23s") to total seconds
    function parseDurationToSeconds(str) {
        if (!str) return 0;
        let sStr = String(str).replace('s', '').trim();
        if (sStr.includes(':')) {
            let parts = sStr.split(':');
            let h = 0, m = 0, s = 0;
            if (parts.length === 3) {
                // Check if days are prepended like "1 00:00:00"
                let days = 0;
                if (parts[0].includes(' ')) {
                    let dParts = parts[0].split(' ');
                    days = parseFloat(dParts[0]) || 0;
                    h = parseFloat(dParts[1]) || 0;
                } else {
                    h = parseFloat(parts[0]) || 0;
                }
                m = parseFloat(parts[1]) || 0;
                s = parseFloat(parts[2]) || 0;
                return (days * 86400) + (h * 3600) + (m * 60) + s;
            } else if (parts.length === 2) {
                m = parseFloat(parts[0]) || 0;
                s = parseFloat(parts[1]) || 0;
                return (m * 60) + s;
            }
        }
        return parseFloat(sStr) || 0;
    }

    // Apply Dynamic Scales to All Turn Nodes (New and Existing)
    let avgDelta = 1.0;
    let validTurns = currentData.nodes.filter(n => n.type === 'turn' && n.delta);
    if (validTurns.length > 0) {
        let totalSeconds = validTurns.reduce((sum, n) => sum + parseDurationToSeconds(n.delta), 0);
        avgDelta = totalSeconds / validTurns.length;
    }

    const activeStates = ['Active', 'Pending', 'Running', 'Thinking'];

    allNodes.filter(d => d.type === 'turn').select("circle").attr("r", d => {
        let baseRadius = 18;
        let isLive = activeStates.includes(d.status);
        let seconds = 0;

        if (isLive && d.created) {
            let startTime = new Date(d.created).getTime();
            seconds = (Date.now() - startTime) / 1000;
        } else if (d.delta) {
            seconds = parseDurationToSeconds(d.delta);
        }

        if (seconds > 0 && avgDelta > 0) {
            // Scale between 0.3x and 3.0x of base radius linearly to make it much more pronounced
            let ratio = seconds / avgDelta;
            ratio = Math.max(0.3, Math.min(ratio, 4.0)); // Allowed to get a bit bigger for active
            baseRadius = 18 * ratio;
        }
        return baseRadius;
    });

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
    const titleEl = document.getElementById('details-title');
    const terminalEl = document.getElementById('details-terminal');
    const scrollContainer = document.getElementById('details-panel');
    const prevScrollTop = scrollContainer.scrollTop;

    if (liveTimerInterval) {
        clearInterval(liveTimerInterval);
        liveTimerInterval = null;
    }

    const dbId = d.id.split('-').slice(1).join('-');
    let adminUrl = '#';

    if (d.type === 'turn') adminUrl = `/admin/frontal_lobe/reasoningturn/${dbId}/change/`;
    else if (d.type === 'goal') adminUrl = `/admin/frontal_lobe/reasoninggoal/${dbId}/change/`;
    else if (d.type === 'session') adminUrl = `/admin/frontal_lobe/reasoningsession/${dbId}/change/`;
    else if (d.type === 'engram') adminUrl = `/admin/hippocampus/talosengram/${dbId}/change/`;
    else if (d.type === 'conclusion') adminUrl = `/admin/frontal_lobe/sessionconclusion/${dbId}/change/`;
    else if (d.type === 'tool') {
        const toolName = d.id.split('-')[2];
        adminUrl = `/admin/parietal_lobe/tooldefinition/?q=${toolName}`;
    }

    // Clear previous
    terminalEl.innerHTML = '';

    if (d.type === 'turn') {
        titleEl.textContent = `Turn ${d.turn_number} Execution Log`;

        const activeStates = ['Active', 'Pending', 'Running', 'Thinking'];
        const isLive = activeStates.includes(d.status);

        let tps = "0.0";
        if (d.inference_time && d.tokens_output) {
            // Helper parsing for robust conversion of Django duration
            let str = String(d.inference_time).replace('s', '').trim();
            let seconds = parseFloat(str);
            if (str.includes(':')) {
                let parts = str.split(':');
                if (parts.length === 3) {
                    seconds = (parseFloat(parts[0] || 0) * 3600) + (parseFloat(parts[1] || 0) * 60) + parseFloat(parts[2] || 0);
                } else if (parts.length === 2) {
                    seconds = (parseFloat(parts[0] || 0) * 60) + parseFloat(parts[1] || 0);
                }
            }
            if (seconds > 0) tps = (d.tokens_output / seconds).toFixed(1);
        }

        let statsHtml = `
            <div style="display: flex; gap: 10px; margin-top: 10px; margin-bottom: 20px; font-family: 'Antonio', sans-serif;">
                <div style="flex: 1; padding: 8px; text-align: center; background-color: #f99f1b; color: black; font-weight: bold; border-radius: 20px; font-size: 1.2rem;">TURN ${d.turn_number}</div>
                <div style="flex: 1; padding: 8px; text-align: center; background-color: #cc99cc; color: black; font-weight: bold; border-radius: 20px; font-size: 1.2rem;">IN ${d.tokens_input || 0}</div>
                <div style="flex: 1; padding: 8px; text-align: center; background-color: #38bdf8; color: black; font-weight: bold; border-radius: 20px; font-size: 1.2rem;">OUT ${d.tokens_output || 0}</div>
                <div style="flex: 1; padding: 8px; text-align: center; background-color: #4ade80; color: black; font-weight: bold; border-radius: 20px; font-size: 1.2rem;" id="node-duration">${isLive ? '⏱ --' : (d.inference_time || d.delta || '0s')}</div>
            </div>
        `;
        let statusColor = d.status === 'Error' ? 'term-fizzle' : (d.status === 'Completed' ? 'term-success' : 'term-thought');

        terminalEl.innerHTML += statsHtml;
        terminalEl.innerHTML += `<div class="${statusColor}" style="margin-bottom: 10px; font-weight: bold; font-size: 1.1rem;">Status: ${d.status}</div>`;

        // 1. Render the Thought Process Bubble FIRST
        if (d.thought_process) {
            let thought = d.thought_process.replace(/^(THOUGHT:\s*)+/i, '').trim();
            terminalEl.innerHTML += `
                <details open class="lcars-accordion" style="margin-top: 15px; border: 2px solid #cc99cc; border-radius: 12px; background: rgba(204,153,204,0.15);">
                    <summary class="lcars-accordion-summary" style="background-color:rgba(204,153,204,0.3); color:#cc99cc; padding: 8px 15px; font-family: 'Antonio', sans-serif; font-size: 1.2rem; text-transform: uppercase;">▼ THOUGHT PROCESS</summary>
                    <div style="padding: 15px; white-space: pre-wrap; word-wrap: break-word; font-family: 'JetBrains Mono', monospace; color: #e2e8f0; font-size: 13px; line-height: 1.5;">${thought}</div>
                </details>
            `;
        } else {
            terminalEl.innerHTML += `<div class="term-thought" style="margin-top: 15px; font-style: italic;">" Executing without monologue... "</div>`;
        }

        if (d.request_payload) {
            let payloadHtml = "";
            let reqObj = d.request_payload;
            try {
                if (typeof reqObj === 'string') {
                    reqObj = JSON.parse(reqObj);
                }
            } catch (e) { }

            if (reqObj && typeof reqObj === 'object' && reqObj.messages && Array.isArray(reqObj.messages)) {
                payloadHtml += `<div class="term-result" style="margin-top: 15px;">
                    <details class="lcars-accordion">
                        <summary class="lcars-accordion-summary" style="background-color:#f99f1b; color:black;">► VIEW REQUEST PAYLOAD</summary>
                        <div style="padding: 10px;">`;

                reqObj.messages.forEach(msg => {
                    let roleStr = String(msg.role).toUpperCase();
                    let roleColor = msg.role === 'system' ? '#cc99cc' : (msg.role === 'user' ? '#99ccff' : '#4ade80');

                    payloadHtml += `<details class="lcars-accordion" style="border: 1px solid ${roleColor};">
                        <summary class="lcars-accordion-summary" style="background-color:${roleColor}33; color:${roleColor};">► [${roleStr}] PROMPT</summary>
                        <div style="padding: 10px;">`;

                    let content = msg.content || "";

                    if (msg.role === 'system') {
                        let sections = content.split(/^(?=[A-Z0-9\s/()_-]+:$)/m);
                        sections.forEach(sec => {
                            if (!sec.trim()) return;
                            let lines = sec.trim().split('\n');
                            let headerMatch = lines[0].match(/^([A-Z0-9\s/()_-]+):$/);
                            if (headerMatch) {
                                payloadHtml += `<div class="lcars-sys-block">
                                    <div class="lcars-sys-header">${headerMatch[1]}</div>
                                    <div class="lcars-payload-text">${lines.slice(1).join('\n').trim()}</div>
                                </div>`;
                            } else {
                                payloadHtml += `<div class="lcars-payload-text" style="margin-bottom: 10px;">${sec.trim()}</div>`;
                            }
                        });
                    } else if (msg.role === 'user') {
                        let sections = content.split(/^(?=\[[A-Z0-9\s:()-]+\])/m);
                        sections.forEach(sec => {
                            if (!sec.trim()) return;

                            if (sec.trim().startsWith("[YOUR MOVE]")) {
                                payloadHtml += `<div class="lcars-move-block">${sec.trim()}</div>`;
                                return;
                            }

                            let lines = sec.trim().split('\n');
                            let headerMatch = lines[0].match(/^\[([^\]]+)\](.*)$/);

                            if (headerMatch) {
                                let title = headerMatch[1];
                                let restOfFirstLine = headerMatch[2].trim();
                                let bodyText = restOfFirstLine ? restOfFirstLine + '\n' + lines.slice(1).join('\n') : lines.slice(1).join('\n');
                                bodyText = bodyText.trim();

                                if (title.includes("HISTORICAL LOG")) {
                                    payloadHtml += `<details class="lcars-accordion" style="margin-top:10px; border: 1px solid #f99f1b;">
                                        <summary class="lcars-accordion-summary" style="background-color:rgba(249,159,27,0.2); color:#f99f1b; font-size: 0.95rem;">► ${title}</summary>
                                        <div style="padding: 10px;">`;

                                    let turns = bodyText.split(/^(?=Turn \d+ \[)/m);
                                    turns.forEach(turnData => {
                                        if (!turnData.trim()) return;
                                        let tLines = turnData.trim().split('\n');
                                        let tHeaderMatch = tLines[0].match(/^(Turn \d+ \[.*?\]):$/);

                                        if (tHeaderMatch) {
                                            let tTitle = tHeaderMatch[1];
                                            let tBody = tLines.slice(1).join('\n').trim();

                                            tBody = tBody.replace(/^(\[SYSTEM RECORD - TOOL EXECUTED.*?\])$/gm, '<div class="lcars-hist-tool">$1</div>');
                                            tBody = tBody.replace(/^THOUGHT:/gm, '<span style="color:#cc99cc; font-weight:bold;">THOUGHT:</span>');
                                            tBody = tBody.replace(/^(\[DATA EVICTED FROM L1 CACHE.*?\])$/gm, '<div style="color:#ff3333; font-size:0.8rem; margin-top:2px;">$1</div>');
                                            tBody = tBody.replace(/^(\[SYSTEM WARNING:.*?\])$/gm, '<div style="color:#ff9900; font-weight:bold; margin-top:5px; margin-bottom: 5px;">$1</div>');
                                            tBody = tBody.replace(/^(--- ENGRAM .*? ---)$/gm, '<div style="color:#99ccff; font-weight:bold; margin-top:5px; border-bottom:1px solid #99ccff;">$1</div>');

                                            payloadHtml += `<details class="lcars-accordion" style="margin-top: 5px; border: 1px solid #4ade80;">
                                                <summary class="lcars-accordion-summary" style="background-color:rgba(74,222,128,0.2); color:#4ade80; font-size: 0.85rem; padding: 4px 10px;">▼ ${tTitle}</summary>
                                                <div style="padding: 10px; font-family: 'JetBrains Mono', monospace; font-size: 0.8rem; color: #ccc; white-space: pre-wrap;">${tBody}</div>
                                            </details>`;
                                        } else {
                                            payloadHtml += `<div class="lcars-payload-text">${turnData.trim()}</div>`;
                                        }
                                    });
                                    payloadHtml += `</div></details>`;
                                } else if (title.includes("SYSTEM DIAGNOSTICS") || title.includes("WAKING STATE") || title.includes("CARD CATALOG")) {
                                    let accColor = title.includes("DIAGNOSTICS") ? "#cc3333" : (title.includes("WAKING") ? "#f99f1b" : "#cc99cc");
                                    let innerClass = title.includes("WAKING") ? "lcars-goal-block" : "lcars-payload-text";

                                    payloadHtml += `<details class="lcars-accordion" style="margin-top:10px; border: 1px solid ${accColor};">
                                        <summary class="lcars-accordion-summary" style="background-color:${accColor}33; color:${accColor}; font-size: 0.95rem;">► ${title}</summary>
                                        <div style="padding: 10px;" class="${innerClass}">${bodyText}</div>
                                    </details>`;
                                } else {
                                    payloadHtml += `<details class="lcars-accordion" style="margin-top:10px; border: 1px solid var(--lcars-blue);">
                                        <summary class="lcars-accordion-summary" style="background-color:rgba(153,204,255,0.2); color:var(--lcars-blue); font-size: 0.95rem;">► ${title}</summary>
                                        <div style="padding: 10px;" class="lcars-payload-text">${bodyText}</div>
                                    </details>`;
                                }
                            } else {
                                payloadHtml += `<div class="lcars-payload-text" style="margin-bottom: 10px;">${sec.trim()}</div>`;
                            }
                        });
                    } else {
                        payloadHtml += `<div class="lcars-payload-text">${content}</div>`;
                    }

                    payloadHtml += `</div></details>`;
                });

                payloadHtml += `</div></details></div>`;
            } else {
                let reqStr = "";
                try {
                    reqStr = JSON.stringify(reqObj, null, 2);
                } catch (e) {
                    reqStr = String(reqObj);
                }
                payloadHtml = `
                    <div class="term-result" style="margin-top: 15px;">
                        <details>
                            <summary style="cursor:pointer; color:#f99f1b; font-weight: bold; border-bottom: 1px solid #f99f1b; padding-bottom: 5px; margin-bottom: 10px;">► View Raw Request Payload</summary>
                            <div class="code-block" style="margin-top:5px; padding:10px; background-color: rgba(0,0,0,0.5); border: 1px solid #f99f1b; border-radius: 4px; overflow-x: auto;">
                                <pre style="margin: 0; white-space: pre-wrap; word-wrap: break-word; font-family: 'JetBrains Mono', monospace; font-size: 11px; color: #99ccff;">${reqStr}</pre>
                            </div>
                        </details>
                    </div>
                `;
            }

            terminalEl.innerHTML += payloadHtml;
        }



        // 2. Render the Tool Calls
        const calls = currentData.links.filter(l => (l.source.id || l.source) === d.id && l.type === 'uses_tool');
        if (calls && calls.length > 0) {
            let spellsHtml = `
                <div class="term-result" style="margin-top: 15px;">
                    <details class="lcars-accordion" style="border: 1px solid #4ade80;">
                        <summary class="lcars-accordion-summary" style="background-color:rgba(74,222,128,0.2); color:#4ade80;">► TOOL CALLS (${calls.length})</summary>
                        <div style="padding: 10px;">
            `;

            calls.forEach((call, i) => {
                let args = call.arguments || {};
                let parsedArgs = null;
                let argHtml = "";
                try {
                    parsedArgs = typeof args === 'string' ? JSON.parse(args) : args;
                    if (parsedArgs && typeof parsedArgs === 'object' && !Array.isArray(parsedArgs)) {
                        argHtml = `<div class="lcars-kv-grid">`;
                        for (let [k, v] of Object.entries(parsedArgs)) {
                            let valStr = typeof v === 'object' ? JSON.stringify(v, null, 2) : String(v);
                            argHtml += `<div class="lcars-kv-key" style="color: #99ccff;">${k}</div><div class="lcars-kv-val">${valStr}</div>`;
                        }
                        argHtml += `</div>`;
                    } else {
                        argHtml = `<pre style="margin: 0; white-space: pre-wrap; word-wrap: break-word; font-family: 'JetBrains Mono', monospace; font-size: 11px; color:#99ccff;">${JSON.stringify(parsedArgs, null, 2)}</pre>`;
                    }
                } catch (e) {
                    argHtml = `<pre style="margin: 0; white-space: pre-wrap; word-wrap: break-word; font-family: 'JetBrains Mono', monospace; font-size: 11px; color:#99ccff;">${String(args)}</pre>`;
                }

                let targetId = call.target.id || call.target;
                let toolNode = currentData.nodes.find(n => n.id === targetId);
                let toolName = toolNode ? toolNode.label : "unknown_spell";

                let resultClass = 'term-result';
                let resultText = call.result || call.traceback || "No result.";
                let resObj = null;
                let resHtml = "";

                if (resultText && resultText.toString().includes("FIZZLE") || call.traceback) {
                    resultClass += ' term-fizzle';
                } else if (resultText && resultText.toString().toLowerCase().includes("success")) {
                    resultClass += ' term-success';
                }

                try {
                    resObj = typeof resultText === 'string' ? JSON.parse(resultText) : resultText;
                    if (resObj && typeof resObj === 'object' && !Array.isArray(resObj)) {
                        resHtml = `<div class="lcars-kv-grid">`;
                        for (let [k, v] of Object.entries(resObj)) {
                            let valStr = typeof v === 'object' ? JSON.stringify(v, null, 2) : String(v);
                            resHtml += `<div class="lcars-kv-key" style="color: #ccc;">${k}</div><div class="lcars-kv-val ${resultClass}">${valStr}</div>`;
                        }
                        resHtml += `</div>`;
                    } else if (Array.isArray(resObj)) {
                        resHtml = `<div style="display: flex; flex-direction: column; gap: 5px;">`;
                        resObj.forEach((item, idx) => {
                            let iStr = typeof item === 'object' ? JSON.stringify(item, null, 2) : String(item);
                            resHtml += `<div style="padding: 5px; background: rgba(255,255,255,0.05); border-left: 2px solid #ccc; font-family: 'JetBrains Mono', monospace; font-size: 0.85rem;"><strong style="color: #ccc;">[${idx}]</strong> <span style="white-space: pre-wrap; color: #e2e8f0; word-break: break-all;">${iStr}</span></div>`;
                        });
                        resHtml += `</div>`;
                    } else {
                        resHtml = `<pre class="${resultClass}" style="margin: 0; white-space: pre-wrap; word-wrap: break-word; font-family: 'JetBrains Mono', monospace; font-size: 11px;">${JSON.stringify(resObj, null, 2)}</pre>`;
                    }
                } catch (e) {
                    resHtml = `<pre class="${resultClass}" style="margin: 0; white-space: pre-wrap; word-wrap: break-word; font-family: 'JetBrains Mono', monospace; font-size: 11px;">${String(resultText)}</pre>`;
                }

                spellsHtml += `
                    <div style="margin-bottom: 15px; border: 1px solid #4ade80; border-radius: 4px; padding: 10px; background-color: rgba(0,0,0,0.3);">
                        <div class="term-spell" style="font-weight: bold; color: #4ade80; margin-bottom: 10px;">> CALL [${i + 1}]: ${toolName}</div>
                        <details class="lcars-accordion" style="margin-bottom: 10px; border: 1px solid rgba(153,204,255,0.4);">
                            <summary class="lcars-accordion-summary" style="background-color:rgba(153,204,255,0.15); color:#99ccff; font-size: 0.9rem; padding: 6px 15px;">► Arguments</summary>
                            <div style="padding: 10px;">${argHtml}</div>
                        </details>
                        <details class="lcars-accordion" style="border: 1px solid rgba(204,204,204,0.4);">
                            <summary class="lcars-accordion-summary" style="background-color:rgba(204,204,204,0.15); color:#ccc; font-size: 0.9rem; padding: 6px 15px;">► Result</summary>
                            <div style="padding: 10px; overflow-x: auto;">${resHtml}</div>
                        </details>
                    </div>
                `;
            });
            spellsHtml += `</div></details></div>`;
            terminalEl.innerHTML += spellsHtml;
        } else {
            terminalEl.innerHTML += `<div class="term-result" style="margin-top: 15px; font-style: italic;">No tools used this turn. Sleep initiated.</div>`;
        }

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
    } else if (d.type === 'goal') {
        titleEl.textContent = `Goal ${d.id.split('-')[1]}`;
        terminalEl.innerHTML += `<div class="term-spell">> OBJECTIVE:</div>`;
        terminalEl.innerHTML += `<div class="term-thought">"${d.rendered_goal || 'No goal text provided.'}"</div>`;
        terminalEl.innerHTML += `<div class="term-result">Status: ${d.status}</div>`;
    } else if (d.type === 'engram') {
        titleEl.textContent = `Engram ${d.id.split('-')[1]}`;
        terminalEl.innerHTML += `<div class="term-spell">> MEMORY RECALLED:: ${d.name || 'Unnamed Hash'}</div>`;
        terminalEl.innerHTML += `<div class="term-thought">"${d.description}"</div>`;
        terminalEl.innerHTML += `<div class="term-result">Relevance: ${d.relevance}</div>`;
    } else if (d.type === 'conclusion') {
        titleEl.textContent = `Mission Conclusion Report`;
        terminalEl.innerHTML += `<div class="term-result" style="margin-top: 15px;">
            <details open>
                <summary style="cursor:pointer; color:#4ade80; font-weight: bold; border-bottom: 1px solid #4ade80; padding-bottom: 5px; margin-bottom: 10px;">► Executive Summary</summary>
                <div style="margin-top: 5px; padding: 10px; border-left: 3px solid #4ade80; white-space: pre-wrap; word-wrap: break-word; font-family: 'JetBrains Mono', monospace; color: #4ade80; font-size: 13px; line-height: 1.5;">${d.summary || 'No summary available.'}</div>
            </details>
        </div>`;

        terminalEl.innerHTML += `<div class="term-result" style="margin-top: 15px;">
            <details>
                <summary style="cursor:pointer; color:#cc99cc; font-weight: bold; border-bottom: 1px solid #cc99cc; padding-bottom: 5px; margin-bottom: 10px;">► Reasoning Trace</summary>
                <div style="margin-top: 5px; padding: 10px; background-color: rgba(204, 153, 204, 0.1); border-left: 3px solid #cc99cc; white-space: pre-wrap; font-family: 'JetBrains Mono', monospace; color: #cc99cc; font-size: 12px; line-height: 1.4;">${d.reasoning_trace || 'No trace available.'}</div>
            </details>
        </div>`;

        terminalEl.innerHTML += `
            <div style="display: flex; gap: 10px; margin-top: 20px;">
                <div style="flex: 1; padding: 10px; background-color: rgba(0,0,0,0.5); border: 1px solid #38bdf8; border-radius: 5px;">
                    <div style="color: #38bdf8; font-weight: bold; margin-bottom: 5px; font-size: 0.9rem; text-transform: uppercase;">Outcome Status</div>
                    <div style="color: white; font-size: 1.1rem;">${d.outcome_status || 'N/A'}</div>
                </div>
                <div style="flex: 1; padding: 10px; background-color: rgba(0,0,0,0.5); border: 1px solid #f99f1b; border-radius: 5px;">
                    <div style="color: #f99f1b; font-weight: bold; margin-bottom: 5px; font-size: 0.9rem; text-transform: uppercase;">Recommended Action</div>
                    <div style="color: white; font-size: 1.1rem;">${d.recommended_action || 'N/A'}</div>
                </div>
            </div>
        `;

        if (d.next_goal_suggestion) {
            terminalEl.innerHTML += `<div class="term-result" style="margin-top: 15px;">
                <details open>
                    <summary style="cursor:pointer; color:#99ccff; font-weight: bold; border-bottom: 1px solid #99ccff; padding-bottom: 5px; margin-bottom: 10px;">► Next Goal Suggestion</summary>
                    <div style="margin-top: 5px; padding: 10px; font-style: italic; color: #99ccff; font-size: 12px; line-height: 1.4;">"${d.next_goal_suggestion}"</div>
                </details>
            </div>`;
        }
    } else if (d.type === 'tool') {
        titleEl.textContent = `Tool: ${d.label}`;
        terminalEl.innerHTML += `<div class="term-spell">> INSPECTING TOOL CALL</div>`;
        const calls = currentData.links.filter(l => (l.target.id || l.target) === d.id && l.type === 'uses_tool');
        calls.forEach((call) => {
            let resultText = call.result || call.traceback || "Pending...";
            let argsText = call.arguments ? (typeof call.arguments === 'object' ? JSON.stringify(call.arguments) : call.arguments) : '{}';
            terminalEl.innerHTML += `<div class="term-result">Arguments: ${argsText}</div>`;
            terminalEl.innerHTML += `<div class="term-result ${call.traceback ? 'term-fizzle' : 'term-success'}">Result: ${resultText}</div>`;
        });
    } else {
        titleEl.textContent = d.type ? d.type.toUpperCase() + ": " + (d.label || d.id) : 'Node Details';
        terminalEl.innerHTML = `<div class="term-result">Select a Turn node to view the action log.</div>`;
    }


    terminalEl.innerHTML += `
        <div style="margin-top: 20px; text-align: center;">
            <a href="${adminUrl}" target="_blank" style="display: inline-block; padding: 10px 20px; background-color: #cc3333; color: black; font-family: 'Antonio', sans-serif; font-weight: bold; font-size: 1.2rem; text-decoration: none; border-radius: 20px; cursor: pointer; border: 2px solid #ff4444; width: 80%;">ACCESS DB RECORD ↗</a>
        </div>
    `;

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
                            window.location.href = `/central_nervous_system/graph/spawn/${data.spawn_id}/?full=True`;
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

const haltBtn = document.getElementById('btn-halt');
if (haltBtn) {
    haltBtn.addEventListener('click', () => {
        haltBtn.style.opacity = '0.5';
        haltBtn.textContent = 'HALTING...';

        fetch(`/api/v1/reasoning_sessions/${sessionId}/stop/`, {
            method: 'POST',
            headers: {
                'X-CSRFToken': getCookie('csrftoken'),
                'Content-Type': 'application/json'
            }
        })
            .then(() => alert("Halt signal sent. The AI will stop after finishing its current thought."))
            .catch(err => console.error(err));
    });
}

const downloadBtn = document.getElementById('btn-download');
if (downloadBtn) {
    downloadBtn.addEventListener('click', () => {
        if (!currentSessionData) return;
        const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(currentSessionData, null, 2));
        const downloadAnchorNode = document.createElement('a');
        downloadAnchorNode.setAttribute("href", dataStr);
        downloadAnchorNode.setAttribute("download", `talos_cortex_dump_${sessionId}.json`);
        document.body.appendChild(downloadAnchorNode); // required for firefox
        downloadAnchorNode.click();
        downloadAnchorNode.remove();
    });
}

function updateTalosHUD(sessionData, latestTurnData) {
    if (!sessionData) return;

    let elLevel = document.getElementById('hud-level');
    if (elLevel) elLevel.textContent = sessionData.current_level || 1;
    let elXp = document.getElementById('hud-xp');
    if (elXp) elXp.textContent = sessionData.total_xp || 0;
    let elFocus = document.getElementById('hud-focus');
    if (elFocus) elFocus.textContent = `${sessionData.current_focus || 0} / ${sessionData.max_focus || 10}`;

    if (globalHudTimer) {
        clearInterval(globalHudTimer);
        globalHudTimer = null;
    }

    if (latestTurnData) {
        let elTurn = document.getElementById('hud-turn');
        if (elTurn) elTurn.textContent = latestTurnData.turn_number;

        let lastNodeTimeStr = "--";
        if (sessionData.turns && sessionData.turns.length > 1) {
            let latestIndex = sessionData.turns.findIndex(t => t.id === latestTurnData.id);
            if (latestIndex > 0) {
                let prevTurn = sessionData.turns[latestIndex - 1];
                lastNodeTimeStr = prevTurn.inference_time || prevTurn.delta || '0s';
            } else {
                lastNodeTimeStr = sessionData.turns[0].inference_time || sessionData.turns[0].delta || '0s';
            }
        } else if (sessionData.turns && sessionData.turns.length === 1) {
            lastNodeTimeStr = "N/A";
        }
        let elLastTime = document.getElementById('hud-last-time');
        if (elLastTime) elLastTime.textContent = lastNodeTimeStr;

        const activeStates = ['Active', 'Pending', 'Running', 'Thinking'];
        const isLive = activeStates.includes(latestTurnData.status_name);
        const sessionFinished = ['Completed', 'Error', 'Maxed Out', 'Stopped'].includes(sessionData.status_name);

        const clockEl = document.getElementById('hud-clock');
        const totalClockEl = document.getElementById('hud-total-clock');

        // Parse Session Created for Total Time
        let sessionStartTime = null;
        if (sessionData.created) sessionStartTime = new Date(sessionData.created).getTime();

        if (isLive && latestTurnData.created) {
            const turnStartTime = new Date(latestTurnData.created).getTime();

            globalHudTimer = setInterval(() => {
                const now = Date.now();
                if (clockEl) {
                    clockEl.textContent = `⏱ ${((now - turnStartTime) / 1000).toFixed(1)}s`;
                }

                if (totalClockEl && !sessionFinished && sessionStartTime) {
                    totalClockEl.textContent = `⏱ ${((now - sessionStartTime) / 1000).toFixed(1)}s`;
                }
            }, 100);
        } else {
            if (clockEl) clockEl.textContent = latestTurnData.inference_time || latestTurnData.delta || '0s';

            // If the turn is dead but session isn't finished and we don't have a turn running, start a timer just for the total clock
            if (!sessionFinished && sessionStartTime) {
                globalHudTimer = setInterval(() => {
                    const now = Date.now();
                    if (totalClockEl) totalClockEl.textContent = `⏱ ${((now - sessionStartTime) / 1000).toFixed(1)}s`;
                }, 100);
            }
        }

        // Final fallback for total time if session is finished or not ticking
        if (sessionFinished && totalClockEl) {
            totalClockEl.textContent = sessionData.delta || '0s';
        } else if (!sessionFinished && !globalHudTimer && totalClockEl && sessionStartTime) {
            totalClockEl.textContent = `⏱ ${((Date.now() - sessionStartTime) / 1000).toFixed(1)}s`;
        }

        // Try to find the latest thought by walking backwards from the current turns array
        let thoughtText = "Awaiting cortex synchronization...";
        if (sessionData.turns && sessionData.turns.length > 0) {
            for (let i = sessionData.turns.length - 1; i >= 0; i--) {
                let t = sessionData.turns[i];
                if (t.thought_process && t.thought_process.trim() !== "") {
                    thoughtText = t.thought_process.replace(/^(THOUGHT:\s*)+/i, '').trim();
                    break;
                } else if (t.request_payload) {
                    try {
                        let parsedReq = typeof t.request_payload === 'string' ? JSON.parse(t.request_payload) : t.request_payload;
                        if (parsedReq && parsedReq.thought_process) {
                            thoughtText = parsedReq.thought_process.replace(/^(THOUGHT:\s*)+/i, '').trim();
                            break;
                        }
                    } catch (e) {
                    }
                }
            }
        }

        let elThought = document.getElementById('hud-thought');
        if (elThought) elThought.textContent = `"${thoughtText}"`;
    }
}

