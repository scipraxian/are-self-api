/**
 * Talos Graph Editor Logic
 * Built by Antigravity
 */

class GraphEditor {
    constructor() {
        this.nodes = [];
        this.connections = [];

        // DOM Elements
        this.container = document.getElementById('editor-container');
        this.nodesLayer = document.getElementById('nodes-layer');
        this.svgLayer = document.getElementById('svg-layer');
        this.connGroup = document.getElementById('connections-group');
        this.grid = document.getElementById('canvas-grid');
        this.tempLine = document.getElementById('temp-line');

        // State
        this.panX = 0;
        this.panY = 0;
        this.zoom = 1;
        this.isPanning = false;
        this.isDraggingNode = null;
        this.activeWire = null;

        this.dragOffset = { x: 0, y: 0 };
        this.lastMousePos = { x: 0, y: 0 };

        // Execution State
        this.executionState = 'ready'; // ready, running, error, finished
        this.activeExecutionNodes = new Set();
        this.isViewOnly = false;

        this.init();
    }

    init() {
        this.setupEventListeners();
        this.render();

        // Root Node (Permanent)
        this.addNode("BeginPlay", 100, 250, {
            canDelete: false,
            inputs: 0,
            outputs: 1,
            isRoot: true
        });

        // Initial example nodes
        this.addNode("Logic Branch", 450, 150);
        this.addNode("Process Data", 450, 400);

        this.updateCounts();
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

            // Zoom relative to mouse position
            const mouseX = e.clientX - this.panX;
            const mouseY = e.clientY - this.panY;

            this.panX -= mouseX * (newZoom / this.zoom - 1);
            this.panY -= mouseY * (newZoom / this.zoom - 1);

            this.zoom = newZoom;
            this.updateCanvasTransform();
        }, { passive: false });

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
                // Use absolute positioning relative to container for robustness
                const coords = this.toCanvasCoords(e.clientX, e.clientY);
                node.x = coords.x - (this.dragOffset.x / this.zoom);
                node.y = coords.y - (this.dragOffset.y / this.zoom);

                this.updateNodeDOM(node);
                this.updateWiresForNode(node.id);
            }

            if (this.activeWire) {
                this.updateTempWire(e.clientX, e.clientY);
            }

            this.lastMousePos = { x: e.clientX, y: e.clientY };
        });

        window.addEventListener('mouseup', (e) => {
            if (this.isPanning) {
                this.isPanning = false;
                this.container.style.cursor = 'grab';
            }

            if (this.activeWire) {
                this.completeWire(e.target);
            }

            if (this.isDraggingNode) {
                const el = document.getElementById(this.isDraggingNode.id);
                if (el) el.style.zIndex = 'auto';
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
        const libraryItems = document.querySelectorAll('.library-item');
        libraryItems.forEach(item => {
            item.addEventListener('dragstart', (e) => {
                e.dataTransfer.setData('node-type', item.dataset.type);
            });
        });

        this.container.addEventListener('dragover', (e) => {
            e.preventDefault();
        });

        this.container.addEventListener('drop', (e) => {
            e.preventDefault();
            const type = e.dataTransfer.getData('node-type');
            if (type) {
                const coords = this.toCanvasCoords(e.clientX, e.clientY);
                this.addNode(type, coords.x - 100, coords.y - 40);
            }
        });

        // Search Filtering
        document.getElementById('node-search').addEventListener('input', (e) => {
            const query = e.target.value.toLowerCase();
            document.querySelectorAll('.library-item').forEach(item => {
                const text = item.innerText.toLowerCase();
                item.style.display = text.includes(query) ? 'block' : 'none';
            });
            // Hide categories with no visible items
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

    addNode(title, x, y, options = {}) {
        const id = options.id || 'node_' + Math.random().toString(36).substr(2, 9);
        const node = {
            id,
            title,
            x,
            y,
            inputs: options.inputs !== undefined ? options.inputs : 1,
            outputs: options.outputs !== undefined ? options.outputs : 3,
            canDelete: options.canDelete !== undefined ? options.canDelete : true,
            isRoot: options.isRoot || false
        };
        this.nodes.push(node);

        this.createNodeDOM(node);
        this.updateCounts();
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
            this.nodes.forEach(n => document.getElementById(n.id).classList.remove('selected'));
            nodeEl.classList.add('selected');
        });

        // Dragging
        const header = nodeEl.querySelector('.node-header');
        header.addEventListener('mousedown', (e) => {
            if (e.target.classList.contains('delete-btn')) return;
            e.stopPropagation();

            // Bring to front
            nodeEl.style.zIndex = 1000;
            this.nodesLayer.appendChild(nodeEl);

            this.isDraggingNode = node;
            this.lastMousePos = { x: e.clientX, y: e.clientY };

            // Calculate where we grabbed the node relative to its top-left, 
            // but in "view" space so it scale correctly
            const rect = nodeEl.getBoundingClientRect();
            this.dragOffset = {
                x: e.clientX - rect.left,
                y: e.clientY - rect.top
            };
        });

        // View Log Button
        nodeEl.querySelector('.mini-btn.view').addEventListener('click', (e) => {
            e.stopPropagation();
            this.showNodeLog(node.id, node.title);
        });

        // Delete
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

        // Wire creation starts here
        nodeEl.querySelectorAll('.pin.output-white, .pin.output-success, .pin.output-error').forEach(pin => {
            pin.addEventListener('mousedown', (e) => {
                e.stopPropagation();
                this.startWire(pin);
            });
        });

        this.nodesLayer.appendChild(nodeEl);
    }

    updateNodeDOM(node) {
        const el = document.getElementById(node.id);
        el.style.left = `${node.x}px`;
        el.style.top = `${node.y}px`;
    }

    deleteNode(nodeId) {
        this.nodes = this.nodes.filter(n => n.id !== nodeId);
        this.connections = this.connections.filter(c => c.fromNode !== nodeId && c.toNode !== nodeId);

        const el = document.getElementById(nodeId);
        if (el) el.remove();

        this.renderConnections();
        this.updateCounts();
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

    completeWire(target) {
        this.tempLine.style.display = 'none';

        if (target && target.classList.contains('pin') && target.dataset.portType === 'input') {
            const toNodeId = target.dataset.nodeId;
            const toPortIdx = parseInt(target.dataset.portIndex);

            // Check if connection already exists
            const exists = this.connections.some(c =>
                c.fromNode === this.activeWire.fromNode &&
                c.fromPort === this.activeWire.fromPort &&
                c.toNode === toNodeId &&
                c.toPort === toPortIdx
            );

            if (!exists && toNodeId !== this.activeWire.fromNode) {
                this.connections.push({
                    fromNode: this.activeWire.fromNode,
                    fromPort: this.activeWire.fromPort,
                    toNode: toNodeId,
                    toPort: toPortIdx,
                    color: this.activeWire.color
                });
                this.renderConnections();
                this.updateCounts();
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

                // Context menu to delete
                path.addEventListener('contextmenu', (e) => {
                    e.preventDefault();
                    this.removeConnection(index);
                });

                // Double click to delete
                path.addEventListener('dblclick', (e) => {
                    this.removeConnection(index);
                });

                this.connGroup.appendChild(path);
            }
        });
    }

    updateWiresForNode(nodeId) {
        // Optimization: only re-render if node is involved in a connection
        const involved = this.connections.some(c => c.fromNode === nodeId || c.toNode === nodeId);
        if (involved) {
            this.renderConnections();
        }
    }

    removeConnection(index) {
        this.connections.splice(index, 1);
        this.renderConnections();
        this.updateCounts();
    }

    getPinElement(nodeId, type, index) {
        const nodeEl = document.getElementById(nodeId);
        if (!nodeEl) return null;
        return nodeEl.querySelector(`.pin[data-port-type="${type}"][data-port-index="${index}"]`);
    }

    calculateBezierPath(x1, y1, x2, y2) {
        // Tension: how far the handles extend from the pins
        let dx = Math.abs(x1 - x2) * 0.5;

        // Minimum handle length to ensure a nice curve even when close
        const minHandle = 50;

        // If nodes are "backwards" (output to the right of input), 
        // we create a larger 'U' loop to avoid the wire cutting through the node
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
                position: { x: n.x, y: n.y }
            })),
            connections: this.connections.map(c => ({
                from: { nodeId: c.fromNode, port: c.fromPort },
                to: { nodeId: c.toNode, port: c.toPort },
                type: c.color.includes('255, 255, 255') ? 'flow' : (c.color.includes('76, 175, 80') ? 'success' : 'error')
            }))
        };
    }

    updateCounts() {
        document.getElementById('node-count').innerText = this.nodes.length;
        document.getElementById('conn-count').innerText = this.connections.length;
    }

    showExportModal() {
        const json = JSON.stringify(this.getGraphJSON(), null, 4);
        document.getElementById('json-preview').innerText = json;
        document.getElementById('modal-container').style.display = 'flex';
    }

    // --- Execution Engine (Mock) ---

    setExecutionStatus(status, message = null) {
        this.executionState = status;
        const textEl = document.getElementById('execution-status-text');
        const indicatorEl = document.getElementById('execution-status-indicator');

        indicatorEl.className = status;

        let statusText = status.toUpperCase();
        if (message) statusText = message;
        else if (status === 'finished') {
            const time = new Date().toLocaleTimeString();
            statusText = `Finished at ${time}`;
        }

        textEl.innerText = statusText;

        // Update global buttons
        document.getElementById('start-btn').disabled = (status === 'running');
        document.getElementById('stop-btn').disabled = (status !== 'running');
    }

    async startExecution() {
        if (this.executionState === 'running') return;

        this.setExecutionStatus('running', 'Running...');
        this.resetNodeHighlights();

        // Find BeginPlay
        const rootNode = this.nodes.find(n => n.isRoot);
        if (!rootNode) return this.stopExecution('Error: No Root');

        try {
            await this.executeNodeStep(rootNode.id);
            this.setExecutionStatus('finished');
        } catch (err) {
            this.setExecutionStatus('error', 'Execution Halted');
        }
    }

    async executeNodeStep(nodeId) {
        if (this.executionState !== 'running') return;

        const nodeEl = document.getElementById(nodeId);
        nodeEl.classList.add('running');

        // Mock processing time
        await new Promise(resolve => setTimeout(resolve, 800 + Math.random() * 1000));

        nodeEl.classList.remove('running');

        // Find outgoing connections
        const nextConns = this.connections.filter(c => c.fromNode === nodeId);

        // For simplicity, follow all flow/success paths
        for (const conn of nextConns) {
            await this.executeNodeStep(conn.toNode);
        }
    }

    stopExecution(errorMsg = null) {
        this.executionState = errorMsg ? 'error' : 'ready';
        this.setExecutionStatus(this.executionState, errorMsg);
        this.resetNodeHighlights();
    }

    resetNodeHighlights() {
        this.nodes.forEach(n => {
            const el = document.getElementById(n.id);
            if (el) el.classList.remove('running');
        });
    }

    // --- Auto Layout Algorithm ---

    autoLayout() {
        if (this.nodes.length === 0) return;

        // Add transition class for smooth movement
        this.nodes.forEach(n => {
            const el = document.getElementById(n.id);
            if (el) el.classList.add('node-auto-layout');
        });

        const startNode = this.nodes.find(n => n.isRoot) || this.nodes[0];
        const levels = new Map();
        const visited = new Set();
        const queue = [{ id: startNode.id, level: 0 }];

        // 1. Assign BFS levels
        while (queue.length > 0) {
            const { id, level } = queue.shift();
            if (visited.has(id)) continue;
            visited.add(id);

            levels.set(id, Math.max(levels.get(id) || 0, level));

            const children = this.connections
                .filter(c => c.fromNode === id)
                .map(c => c.toNode);

            children.forEach(childId => {
                queue.push({ id: childId, level: level + 1 });
            });
        }

        // Handle nodes not reachable from root
        this.nodes.forEach(node => {
            if (!levels.has(node.id)) {
                levels.set(node.id, 0);
            }
        });

        // 2. Group by level and calculate positions
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
                }
            });
        });

        // 3. Re-render wires after transition
        let frames = 0;
        const totalFrames = 60;
        const animateWires = () => {
            this.renderConnections();
            if (frames++ < totalFrames) {
                requestAnimationFrame(animateWires);
            } else {
                // Remove transition class after movement finishes so dragging stays instant
                this.nodes.forEach(n => {
                    const el = document.getElementById(n.id);
                    if (el) el.classList.remove('node-auto-layout');
                });
            }
        };
        requestAnimationFrame(animateWires);
    }

    showNodeLog(nodeId, title) {
        const modal = document.getElementById('modal-container');
        const headerText = modal.querySelector('h3');
        const preview = document.getElementById('json-preview');

        headerText.innerText = `Node Status: ${title}`;

        const mockLogs = [
            `[${new Date().toLocaleTimeString()}] Initializing ${title}...`,
            `[${new Date().toLocaleTimeString()}] Fetching Talos parameters...`,
            `[${new Date().toLocaleTimeString()}] Execution Lobe active.`,
            `[${new Date().toLocaleTimeString()}] Status: ${this.activeExecutionNodes.has(nodeId) ? 'RUNNING' : 'READY'}`
        ].join('\n');

        preview.innerText = mockLogs;
        modal.style.display = 'flex';
    }

    render() {
        this.updateCanvasTransform();
    }
}

// Global accessor for graph state
window.getGraphJSON = () => window.app.getGraphJSON();

// Initialize app
window.app = new GraphEditor();
