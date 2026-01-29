/**
 * Talos Graph Editor Logic
 * Built by Antigravity - Senior Frontend Engineer Refactor
 */

class GraphEditor {
    constructor() {
        this.nodes = [];
        this.connections = [];

        // Context from Django
        this.bookId = window.djangoContext?.bookId;
        this.csrfToken = window.djangoContext?.csrfToken || document.querySelector('[name=csrfmiddlewaretoken]')?.value;
        this.apiUrl = `/hydra/graph/${this.bookId}/`;

        // DOM Elements
        this.container = document.getElementById('editor-container');
        this.nodesLayer = document.getElementById('nodes-layer');
        this.svgLayer = document.getElementById('svg-layer');
        this.connGroup = document.getElementById('connections-group');
        this.grid = document.getElementById('canvas-grid');
        this.tempLine = document.getElementById('temp-line');
        this.libraryContainer = document.getElementById('node-library');

        // State
        this.panX = 0;
        this.panY = 0;
        this.zoom = 1;
        this.isPanning = false;
        this.isDraggingNode = null;
        this.activeWire = null;

        this.dragOffset = {x: 0, y: 0};
        this.lastMousePos = {x: 0, y: 0};

        // Execution State
        this.executionState = 'ready'; // ready, running, error, finished
        this.isViewOnly = false;

        this.init();
    }

    async init() {
        this.setupEventListeners();
        this.render();

        // Load Library first
        await this.loadLibrary();

        // Load Graph State
        await this.loadGraph();

        this.updateCounts();
    }

    // --- API Interactions ---

    async apiFetch(endpoint, options = {}) {
        const url = endpoint.startsWith('/') ? endpoint : `${this.apiUrl}${endpoint}`;
        const defaultHeaders = {
            'Content-Type': 'application/json',
            'X-CSRFToken': this.csrfToken
        };

        try {
            const response = await fetch(url, {
                ...options,
                headers: {...defaultHeaders, ...options.headers}
            });

            if (!response.ok) throw new Error(`API Error: ${response.statusText}`);
            return await response.json();
        } catch (error) {
            console.error(`Fetch error for ${url}:`, error);
            this.setExecutionStatus('error', `API Failure: ${error.message}`);
            return null;
        }
    }

    async loadLibrary() {
        const data = await this.apiFetch('library');
        if (!data || !data.library) return;

        this.libraryContainer.innerHTML = '';

        // Group by category if possible, or just list
        const categories = {};
        data.library.forEach(spell => {
            const cat = spell.category || 'Spells';
            if (!categories[cat]) categories[cat] = [];
            categories[cat].push(spell);
        });

        for (const [name, spells] of Object.entries(categories)) {
            const catDiv = document.createElement('div');
            catDiv.className = 'category';
            catDiv.innerHTML = `<span>${name}</span>`;

            spells.forEach(spell => {
                const item = document.createElement('div');
                item.className = 'library-item';
                item.draggable = true;
                item.innerText = spell.name;
                item.dataset.spellId = spell.id;

                item.addEventListener('dragstart', (e) => {
                    e.dataTransfer.setData('spell-id', spell.id);
                    e.dataTransfer.setData('spell-name', spell.name);
                });
                catDiv.appendChild(item);
            });
            this.libraryContainer.appendChild(catDiv);
        }
    }

    async loadGraph() {
        const data = await this.apiFetch('');
        if (!data) return;

        // Clear existing
        this.nodes = [];
        this.connections = [];
        this.nodesLayer.innerHTML = '';
        this.connGroup.innerHTML = '';

        // Add Nodes
        if (data.nodes) {
            data.nodes.forEach(n => {
                this.addNode(n.title, n.x, n.y, {
                    id: n.id,
                    spell_id: n.spell_id,
                    isRoot: n.is_root, // Assuming this convention for now
                    skipApi: true
                });
            });
        }

        // Add Connections
        if (data.connections) {
            data.connections.forEach(c => {
                // Map status_id to color logic
                let color = 'rgba(255, 255, 255, 0.8)';
                if (c.status_id === 'success') color = 'rgba(76, 175, 80, 0.8)';
                if (c.status_id === 'fail') color = 'rgba(244, 67, 54, 0.8)';

                this.connections.push({
                    fromNode: c.from_node_id,
                    fromPort: this.getPortIndexFromStatus(c.status_id),
                    toNode: c.to_node_id,
                    toPort: 0,
                    color: color
                });
            });
        }

        this.renderConnections();
        this.updateCounts();
    }

    getPortIndexFromStatus(status) {
        if (status === 'success') return 1;
        if (status === 'fail') return 2;
        return 0; // flow
    }

    getStatusFromColor(color) {
        if (color.includes('76, 175, 80')) return 'success';
        if (color.includes('244, 67, 54')) return 'fail';
        return 'flow';
    }

    setupEventListeners() {
        // Panning logic
        this.container.addEventListener('mousedown', (e) => {
            if (e.button === 1 || (e.button === 0 && e.target === this.container)) {
                this.isPanning = true;
                this.container.style.cursor = 'grabbing';
            }
        });

        // Zoom logic
        this.container.addEventListener('wheel', (e) => {
            e.preventDefault();
            const zoomSpeed = 0.001;
            const delta = -e.deltaY;
            const factor = Math.pow(1.1, delta / 100);

            const newZoom = Math.min(Math.max(this.zoom * factor, 0.2), 3);

            const mouseX = e.clientX - this.panX;
            const mouseY = e.clientY - this.panY;

            this.panX -= mouseX * (newZoom / this.zoom - 1);
            this.panY -= mouseY * (newZoom / this.zoom - 1);

            this.zoom = newZoom;
            this.updateCanvasTransform();
        }, {passive: false});

        window.addEventListener('mousemove', (e) => {
            const dx = e.clientX - this.lastMousePos.x;
            const dy = e.clientY - this.lastMousePos.y;

            if (this.isPanning) {
                this.panX += dx;
                this.panY += dy;
                this.updateCanvasTransform();
            }

            if (this.isDraggingNode) {
                const node = this.isDraggingNode;
                const coords = this.toCanvasCoords(e.clientX, e.clientY);
                node.x = coords.x - (this.dragOffset.x / this.zoom);
                node.y = coords.y - (this.dragOffset.y / this.zoom);

                this.updateNodeDOM(node);
                this.updateWiresForNode(node.id);
            }

            if (this.activeWire) {
                this.updateTempWire(e.clientX, e.clientY);
            }

            this.lastMousePos = {x: e.clientX, y: e.clientY};
        });

        window.addEventListener('mouseup', async (e) => {
            if (this.isPanning) {
                this.isPanning = false;
                this.container.style.cursor = 'grab';
            }

            if (this.activeWire) {
                this.completeWire(e.target);
            }

            if (this.isDraggingNode) {
                const node = this.isDraggingNode;
                const el = document.getElementById(node.id);
                if (el) el.style.zIndex = 'auto';

                // Persist move - Debounced/Delayed until mouseup
                if (!node.id.toString().startsWith('temp_')) {
                    await this.apiFetch('move_node', {
                        method: 'POST',
                        body: JSON.stringify({
                            node_id: node.id,
                            x: Math.round(node.x),
                            y: Math.round(node.y)
                        })
                    });
                }
            }

            this.isDraggingNode = null;
        });

        // Modal Controls
        document.getElementById('close-modal').addEventListener('click', () => {
            document.getElementById('modal-container').style.display = 'none';
        });

        document.getElementById('copy-json').addEventListener('click', () => {
            const json = JSON.stringify(this.getGraphJSON(), null, 4);
            navigator.clipboard.writeText(json);
            const btn = document.getElementById('copy-json');
            btn.innerText = "Copied!";
            setTimeout(() => btn.innerText = "Copy to Clipboard", 2000);
        });

        document.getElementById('auto-layout-btn').addEventListener('click', () => this.autoLayout());

        // Execution Events
        document.getElementById('start-btn').addEventListener('click', () => this.startExecution());
        document.getElementById('stop-btn').addEventListener('click', () => this.stopExecution());
        document.getElementById('view-toggle').addEventListener('click', () => {
            this.isViewOnly = !this.isViewOnly;
            document.getElementById('view-toggle').style.color = this.isViewOnly ? '#2196f3' : '#666';
            this.container.classList.toggle('view-only', this.isViewOnly);
        });

        // Sidebar Drag & Drop
        this.container.addEventListener('dragover', (e) => {
            e.preventDefault();
        });

        this.container.addEventListener('drop', (e) => {
            e.preventDefault();
            const spellId = e.dataTransfer.getData('spell-id');
            const spellName = e.dataTransfer.getData('spell-name');
            if (spellId) {
                const coords = this.toCanvasCoords(e.clientX, e.clientY);
                this.addNode(spellName, coords.x - 100, coords.y - 40, {spell_id: spellId});
            }
        });

        // Search Filtering
        document.getElementById('node-search').addEventListener('input', (e) => {
            const query = e.target.value.toLowerCase();
            document.querySelectorAll('.library-item').forEach(item => {
                const text = item.innerText.toLowerCase();
                item.style.display = text.includes(query) ? 'block' : 'none';
            });
            document.querySelectorAll('.category').forEach(cat => {
                const visible = Array.from(cat.querySelectorAll('.library-item')).some(i => i.style.display !== 'none');
                cat.style.display = visible ? 'block' : 'none';
            });
        });
    }

    updateCanvasTransform() {
        const transform = `translate(${this.panX}px, ${this.panY}px) scale(${this.zoom})`;
        this.grid.style.transform = transform;
        this.nodesLayer.style.transform = transform;
        this.svgLayer.style.transform = transform;
    }

    async addNode(title, x, y, options = {}) {
        // Temporary ID while we wait for DB
        const tempId = options.id || 'temp_' + Math.random().toString(36).substr(2, 9);

        const isRoot = options.isRoot || false;

        const node = {
            id: tempId,
            title,
            x,
            y,
            spell_id: options.spell_id,
            inputs: isRoot ? 0 : (options.inputs !== undefined ? options.inputs : 1),
            outputs: options.outputs !== undefined ? options.outputs : 3,
            canDelete: options.canDelete !== undefined ? options.canDelete : true,
            isRoot: options.isRoot || false
        };

        this.nodes.push(node);
        this.createNodeDOM(node);
        this.updateCounts();

        // Immediate persistence
        if (!options.skipApi && options.spell_id) {
            const nodeEl = document.getElementById(tempId);
            nodeEl.classList.add('pending'); // Visual feedback

            const result = await this.apiFetch('add_node', {
                method: 'POST',
                body: JSON.stringify({
                    spell_id: options.spell_id,
                    x: Math.round(x),
                    y: Math.round(y)
                })
            });

            if (result && result.id) {
                // SWAP ID
                nodeEl.id = result.id;
                node.id = result.id;

                // Update pins in DOM
                nodeEl.querySelectorAll('.pin').forEach(pin => {
                    pin.dataset.nodeId = result.id;
                });

                nodeEl.classList.remove('pending');
            } else {
                // Rollback if failed
                this.deleteNode(tempId, true);
            }
        }

        return node;
    }

    createNodeDOM(node) {
        const nodeEl = document.createElement('div');
        nodeEl.className = 'node';
        nodeEl.id = node.id;
        nodeEl.style.left = `${node.x}px`;
        nodeEl.style.top = `${node.y}px`;

        nodeEl.innerHTML = `
            <div class="node-header ${node.isRoot ? 'root-header' : ''}">
                <h4>${node.title}</h4>
                <div class="node-controls">
                    <button class="mini-btn view" title="View Node Log">👁</button>
                    ${node.isRoot ? `
                        <button class="mini-btn play" title="Start from here">▶</button>
                    ` : ''}
                    ${node.canDelete ? '<button class="delete-btn">&times;</button>' : ''}
                </div>
            </div>
            <div class="node-body">
                <div class="ports-column port-input-wrapper">
                    ${node.inputs > 0 ? `
                    <div class="port-item">
                        <div class="pin input" data-node-id="${node.id}" data-port-index="0" data-port-type="input"></div>
                        <span>Input</span>
                    </div>` : ''}
                </div>
                <div class="ports-column port-output-wrapper">
                    <div class="port-item">
                        <div class="pin output-white" data-node-id="${node.id}" data-port-index="0" data-port-type="output"></div>
                        <span>${node.isRoot ? '' : 'Flow'}</span>
                    </div>
                    ${!node.isRoot ? `
                    <div class="port-item">
                        <div class="pin output-success" data-node-id="${node.id}" data-port-index="1" data-port-type="output"></div>
                        <span>Success</span>
                    </div>
                    <div class="port-item">
                        <div class="pin output-error" data-node-id="${node.id}" data-port-index="2" data-port-type="output"></div>
                        <span>Fail</span>
                    </div>` : ''}
                </div>
            </div>
        `;

        // Selection
        nodeEl.addEventListener('mousedown', (e) => {
            this.nodes.forEach(n => {
                const el = document.getElementById(n.id);
                if (el) el.classList.remove('selected');
            });
            nodeEl.classList.add('selected');
        });

        // Dragging
        const header = nodeEl.querySelector('.node-header');
        header.addEventListener('mousedown', (e) => {
            if (e.target.classList.contains('delete-btn')) return;
            if (nodeEl.classList.contains('pending')) return;
            e.stopPropagation();

            nodeEl.style.zIndex = 1000;
            this.nodesLayer.appendChild(nodeEl);

            this.isDraggingNode = node;
            this.lastMousePos = {x: e.clientX, y: e.clientY};

            const rect = nodeEl.getBoundingClientRect();
            this.dragOffset = {
                x: e.clientX - rect.left,
                y: e.clientY - rect.top
            };
        });

        nodeEl.querySelector('.mini-btn.view').addEventListener('click', (e) => {
            e.stopPropagation();
            this.showNodeLog(node.id, node.title);
        });

        if (node.isRoot) {
            nodeEl.querySelector('.mini-btn.play').addEventListener('click', (e) => {
                e.stopPropagation();
                this.startExecution();
            });
        }

        if (node.canDelete) {
            nodeEl.querySelector('.delete-btn').addEventListener('click', (e) => {
                e.stopPropagation();
                this.deleteNode(node.id);
            });
        }

        nodeEl.querySelectorAll('.pin.output-white, .pin.output-success, .pin.output-error').forEach(pin => {
            pin.addEventListener('mousedown', (e) => {
                if (nodeEl.classList.contains('pending')) return;
                e.stopPropagation();
                this.startWire(pin);
            });
        });

        this.nodesLayer.appendChild(nodeEl);
    }

    updateNodeDOM(node) {
        const el = document.getElementById(node.id);
        if (el) {
            el.style.left = `${node.x}px`;
            el.style.top = `${node.y}px`;
        }
    }

    async deleteNode(nodeId, localOnly = false) {
        const node = this.nodes.find(n => n.id === nodeId);
        if (!node) return;

        this.nodes = this.nodes.filter(n => n.id !== nodeId);
        this.connections = this.connections.filter(c => c.fromNode !== nodeId && c.toNode !== nodeId);

        const el = document.getElementById(nodeId);
        if (el) el.remove();

        this.renderConnections();
        this.updateCounts();

        if (!localOnly && !nodeId.toString().startsWith('temp_')) {
            await this.apiFetch('delete_node', {
                method: 'POST',
                body: JSON.stringify({node_id: nodeId})
            });
        }
    }

    // --- Wire Logic ---

    toCanvasCoords(clientX, clientY) {
        const rect = this.container.getBoundingClientRect();
        return {
            x: (clientX - rect.left - this.panX) / this.zoom,
            y: (clientY - rect.top - this.panY) / this.zoom
        };
    }

    startWire(pin) {
        const rect = pin.getBoundingClientRect();
        const coords = this.toCanvasCoords(rect.left + rect.width / 2, rect.top + rect.height / 2);
        this.activeWire = {
            fromNode: pin.dataset.nodeId,
            fromPort: parseInt(pin.dataset.portIndex),
            color: window.getComputedStyle(pin).backgroundColor,
            startX: coords.x,
            startY: coords.y
        };

        this.tempLine.style.display = 'block';
        this.tempLine.style.stroke = this.activeWire.color;
    }

    updateTempWire(mouseX, mouseY) {
        const coords = this.toCanvasCoords(mouseX, mouseY);
        const path = this.calculateBezierPath(
            this.activeWire.startX, this.activeWire.startY,
            coords.x, coords.y
        );
        this.tempLine.setAttribute('d', path);
    }

    async completeWire(target) {
        this.tempLine.style.display = 'none';

        if (target && target.classList.contains('pin') && target.dataset.portType === 'input') {
            const toNodeId = target.dataset.nodeId;
            const toPortIdx = parseInt(target.dataset.portIndex);

            const exists = this.connections.some(c =>
                c.fromNode === this.activeWire.fromNode &&
                c.fromPort === this.activeWire.fromPort &&
                c.toNode === toNodeId &&
                c.toPort === toPortIdx
            );

            if (!exists && toNodeId !== this.activeWire.fromNode) {
                const type = this.getStatusFromColor(this.activeWire.color);

                const connection = {
                    fromNode: this.activeWire.fromNode,
                    fromPort: this.activeWire.fromPort,
                    toNode: toNodeId,
                    toPort: toPortIdx,
                    color: this.activeWire.color
                };

                this.connections.push(connection);
                this.renderConnections();
                this.updateCounts();

                // Persistence
                await this.apiFetch('connect', {
                    method: 'POST',
                    body: JSON.stringify({
                        source_node_id: connection.fromNode,
                        target_node_id: connection.toNode,
                        type: type
                    })
                });
            }
        }
        this.activeWire = null;
    }

    renderConnections() {
        this.connGroup.innerHTML = '';
        this.connections.forEach((conn, index) => {
            const startPin = this.getPinElement(conn.fromNode, 'output', conn.fromPort);
            const endPin = this.getPinElement(conn.toNode, 'input', conn.toPort);

            if (startPin && endPin) {
                const sRect = startPin.getBoundingClientRect();
                const eRect = endPin.getBoundingClientRect();

                const start = this.toCanvasCoords(sRect.left + sRect.width / 2, sRect.top + sRect.height / 2);
                const end = this.toCanvasCoords(eRect.left + eRect.width / 2, eRect.top + eRect.height / 2);

                const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
                path.setAttribute('d', this.calculateBezierPath(start.x, start.y, end.x, end.y));
                path.setAttribute('stroke', conn.color);
                path.setAttribute('class', 'wire');

                path.addEventListener('dblclick', (e) => {
                    this.removeConnection(index);
                });

                this.connGroup.appendChild(path);
            }
        });
    }

    updateWiresForNode(nodeId) {
        const involved = this.connections.some(c => c.fromNode === nodeId || c.toNode === nodeId);
        if (involved) {
            this.renderConnections();
        }
    }

    async removeConnection(index) {
        const conn = this.connections[index];
        if (!conn) return;

        this.connections.splice(index, 1);
        this.renderConnections();
        this.updateCounts();

        // Persistence
        await this.apiFetch('disconnect', {
            method: 'POST',
            body: JSON.stringify({
                source_node_id: conn.fromNode,
                target_node_id: conn.toNode
            })
        });
    }

    getPinElement(nodeId, type, index) {
        const nodeEl = document.getElementById(nodeId);
        if (!nodeEl) return null;
        // Adjust for "output" pins having different classes
        let selector = `.pin[data-port-type="${type}"][data-port-index="${index}"]`;
        return nodeEl.querySelector(selector);
    }

    calculateBezierPath(x1, y1, x2, y2) {
        let dx = Math.abs(x1 - x2) * 0.5;
        const minHandle = 50;
        if (x1 > x2) {
            dx = Math.max(dx, minHandle) + (x1 - x2) * 0.2;
        } else {
            dx = Math.max(dx, minHandle);
        }
        const cp1x = x1 + dx;
        const cp1y = y1;
        const cp2x = x2 - dx;
        const cp2y = y2;
        return `M ${x1} ${y1} C ${cp1x} ${cp1y}, ${cp2x} ${cp2y}, ${x2} ${y2}`;
    }

    // --- Data Model ---

    getGraphJSON() {
        return {
            nodes: this.nodes.map(n => ({
                id: n.id,
                title: n.title,
                position: {x: n.x, y: n.y}
            })),
            connections: this.connections.map(c => ({
                from: {nodeId: c.fromNode, port: c.fromPort},
                to: {nodeId: c.toNode, port: c.toPort},
                type: this.getStatusFromColor(c.color)
            }))
        };
    }

    updateCounts() {
        document.getElementById('node-count').innerText = this.nodes.length;
        document.getElementById('conn-count').innerText = this.connections.length;
    }

    // --- Execution Engine ---

    setExecutionStatus(status, message = null) {
        this.executionState = status;
        const textEl = document.getElementById('execution-status-text');
        const indicatorEl = document.getElementById('execution-status-indicator');

        if (indicatorEl) indicatorEl.className = status;

        let statusText = status.toUpperCase();
        if (message) statusText = message;
        else if (status === 'finished') {
            const time = new Date().toLocaleTimeString();
            statusText = `Finished at ${time}`;
        }

        if (textEl) textEl.innerText = statusText;

        const startBtn = document.getElementById('start-btn');
        const stopBtn = document.getElementById('stop-btn');
        if (startBtn) startBtn.disabled = (status === 'running');
        if (stopBtn) stopBtn.disabled = (status !== 'running');
    }

    async startExecution() {
        if (this.executionState === 'running') return;

        this.setExecutionStatus('running', 'Spawning Process...');

        const result = await this.apiFetch('launch/', {
            method: 'POST',
            body: JSON.stringify({book_id: this.bookId})
        });

        if (result && result.status === 'started') {
            this.setExecutionStatus('running', 'Process Active');
        } else {
            this.setExecutionStatus('error', 'Spawn Failed');
        }
    }

    stopExecution(errorMsg = null) {
        this.executionState = errorMsg ? 'error' : 'ready';
        this.setExecutionStatus(this.executionState, errorMsg);
    }

    // --- Auto Layout ---

    autoLayout() {
        if (this.nodes.length === 0) return;

        this.nodes.forEach(n => {
            const el = document.getElementById(n.id);
            if (el) el.classList.add('node-auto-layout');
        });

        const startNode = this.nodes.find(n => n.isRoot) || this.nodes[0];
        const levels = new Map();
        const visited = new Set();
        const queue = [{id: startNode.id, level: 0}];

        while (queue.length > 0) {
            const {id, level} = queue.shift();
            if (visited.has(id)) continue;
            visited.add(id);
            levels.set(id, Math.max(levels.get(id) || 0, level));
            const children = this.connections
                .filter(c => c.fromNode === id)
                .map(c => c.toNode);
            children.forEach(childId => queue.push({id: childId, level: level + 1}));
        }

        this.nodes.forEach(node => {
            if (!levels.has(node.id)) levels.set(node.id, 0);
        });

        const columnMap = new Map();
        levels.forEach((level, nodeId) => {
            if (!columnMap.has(level)) columnMap.set(level, []);
            columnMap.get(level).push(nodeId);
        });

        const COL_SPACING = 350;
        const ROW_SPACING = 180;
        const OFFSET_X = 100;
        const OFFSET_Y = 100;

        columnMap.forEach((nodeIds, level) => {
            nodeIds.forEach((nodeId, index) => {
                const node = this.nodes.find(n => n.id === nodeId);
                if (node) {
                    node.x = OFFSET_X + level * COL_SPACING;
                    node.y = OFFSET_Y + index * ROW_SPACING;
                    this.updateNodeDOM(node);
                    // Update DB for each node moved
                    this.apiFetch('move_node', {
                        method: 'POST',
                        body: JSON.stringify({node_id: node.id, x: node.x, y: node.y})
                    });
                }
            });
        });

        let frames = 0;
        const animateWires = () => {
            this.renderConnections();
            if (frames++ < 60) requestAnimationFrame(animateWires);
            else {
                this.nodes.forEach(n => {
                    const el = document.getElementById(n.id);
                    if (el) el.classList.remove('node-auto-layout');
                });
            }
        };
        requestAnimationFrame(animateWires);
    }

    async showNodeLog(nodeId, title) {
        const modal = document.getElementById('modal-container');
        const headerText = modal.querySelector('h3');
        const preview = document.getElementById('json-preview');

        headerText.innerText = `Node Log: ${title}`;
        preview.innerText = 'Fetching logs...';
        modal.style.display = 'flex';

        const data = await this.apiFetch(`log/${nodeId}`);
        if (data && data.log) {
            preview.innerText = data.log;
        } else {
            preview.innerText = 'No logs available for this node.';
        }
    }

    render() {
        this.updateCanvasTransform();
    }
}

// Initialize app
window.app = new GraphEditor();
