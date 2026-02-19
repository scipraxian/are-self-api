document.addEventListener('DOMContentLoaded', () => {
    const sessionId = document.getElementById('lcars-data').dataset.sessionId;

    // Fetch Data
    fetch(`/api/v1/reasoning_sessions/${sessionId}/graph_data/`)
        .then(response => response.json())
        .then(data => {
            initGraph(data);
            updateSessionInfo(data.session);
        });

    function updateSessionInfo(session) {
        document.getElementById('session-id').textContent = session.id.substring(0, 8);
        document.getElementById('session-status').textContent = session.status;
    }
});

function initGraph(data) {
    const width = document.getElementById('graph-container').clientWidth;
    const height = document.getElementById('graph-container').clientHeight;

    const svg = d3.select("#graph-container").append("svg")
        .attr("width", width)
        .attr("height", height)
        .call(d3.zoom().on("zoom", (event) => {
            g.attr("transform", event.transform);
        }));

    const g = svg.append("g");

    const simulation = d3.forceSimulation(data.nodes)
        .force("link", d3.forceLink(data.links).id(d => d.id).distance(100))
        .force("charge", d3.forceManyBody().strength(-300))
        .force("center", d3.forceCenter(width / 2, height / 2))
        .force("collide", d3.forceCollide().radius(30));

    // Links
    const link = g.append("g")
        .attr("class", "links")
        .selectAll("line")
        .data(data.links)
        .join("line")
        .attr("stroke", "#999")
        .attr("stroke-width", 2)
        .attr("stroke-opacity", 0.6);

    // Nodes
    const node = g.append("g")
        .attr("class", "nodes")
        .selectAll("g")
        .data(data.nodes)
        .join("g")
        .call(drag(simulation))
        .on("click", (event, d) => showDetails(d));

    // Node Shapes
    node.each(function (d) {
        const el = d3.select(this);
        if (d.type === 'turn') {
            el.append("circle")
                .attr("r", 15)
                .attr("fill", "#f99f1b"); // Gold
        } else if (d.type === 'tool') {
            el.append("rect")
                .attr("width", 16)
                .attr("height", 16)
                .attr("x", -8)
                .attr("y", -8)
                .attr("fill", "#cc3333") // Red
                .attr("rx", 4);
        } else {
            el.append("rect")
                .attr("width", 20)
                .attr("height", 20)
                .attr("x", -10)
                .attr("y", -10)
                .attr("fill", "#cc99cc"); // Purple
        }
    });

    // Labels
    node.append("text")
        .attr("dy", 25)
        .attr("text-anchor", "middle")
        .text(d => {
            if (d.type === 'turn') return `T${d.turn_number}`;
            if (d.type === 'tool') return d.label;
            return `#${d.id.split('-')[1].substring(0, 4)}`;
        })
        .attr("fill", "#99ccff")
        .style("font-size", "10px")
        .style("font-family", "sans-serif");


    simulation.on("tick", () => {
        link
            .attr("x1", d => d.source.x)
            .attr("y1", d => d.source.y)
            .attr("x2", d => d.target.x)
            .attr("y2", d => d.target.y);

        node
            .attr("transform", d => `translate(${d.x},${d.y})`);
    });

    function showDetails(d) {
        const panel = document.getElementById('details-content');
        let html = `<div class="detail-header">${d.type.toUpperCase()}</div>`;

        if (d.type === 'turn') {
            html += `
                <div class="detail-row">
                    <div class="detail-label">Turn Number</div>
                    <div class="detail-value">${d.turn_number}</div>
                </div>
                <div class="detail-row">
                    <div class="detail-label">Status</div>
                    <div class="detail-value">${d.status}</div>
                </div>
                <div class="detail-row">
                    <div class="detail-label">Thought Process</div>
                    <div class="detail-value text-content">${d.thought_process || 'N/A'}</div>
                </div>
            `;
        } else if (d.type === 'tool') {
            html += `
                <div class="detail-row">
                    <div class="detail-label">Tool Name</div>
                    <div class="detail-value">${d.label}</div>
                </div>
                <div class="detail-row">
                    <div class="detail-label">Async</div>
                    <div class="detail-value">${d.is_async}</div>
                </div>
            `;
        } else {
            html += `
                <div class="detail-row">
                    <div class="detail-label">Relevance</div>
                    <div class="detail-value">${d.relevance}</div>
                </div>
                <div class="detail-row">
                    <div class="detail-label">Description</div>
                    <div class="detail-value text-content">${d.description}</div>
                </div>
            `;
        }

        panel.innerHTML = html;

        // If clicked tool is linked from a Turn, show arguments?
        // That data is on the link, not the node really, unless we aggregate.
        // For now, simpler is better.
    }
}

// Expand Handler
document.getElementById('btn-expand').addEventListener('click', () => {
    const panel = document.getElementById('details-panel');
    panel.classList.toggle('expanded');
    const btn = document.getElementById('btn-expand');
    btn.textContent = panel.classList.contains('expanded') ? 'COLLAPSE' : 'EXPAND';
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

    return d3.drag()
        .on("start", dragstarted)
        .on("drag", dragged)
        .on("end", dragended);
}
