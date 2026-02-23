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
        this.spawnId = window.djangoContext?.spawnId;
        this.mode = window.djangoContext?.mode || 'edit';
        this.csrfToken =
            window.djangoContext?.csrfToken ||
            document.querySelector('[name=csrfmiddlewaretoken]')?.value;
        this.apiUrl = `/hydra/graph/${this.bookId}/`;

        // Monitor Mode State
        this.isMonitorMode = !!this.spawnId;
        this.nodeHeadMap = {}; // node_id -> head_id

        // DOM Elements
        this.container = document.getElementById('editor-container');
        this.nodesLayer = document.getElementById('nodes-layer');
        this.svgLayer = document.getElementById('svg-layer');
        this.connGroup = document.getElementById('connections-group');
        this.grid = document.getElementById('canvas-grid');
        this.tempLine = document.getElementById('temp-line');
        this.libraryContainer = document.getElementById('node-library');
        this.searchInput = document.getElementById('node-search');

        // Inspector
        this.inspector = document.getElementById('inspector');
        this.inspectorHeaderSub = this.inspector ? this.inspector.querySelector('.sub-id') : null;
        this.inspectorContent = this.inspector ? this.inspector.querySelector('.inspector-content') : null;
        this.activeNodeId = null;
        this.contextSaveTimer = null;

        // Resize handles
        this.resizeHandleLeft = document.getElementById('resize-handle-left');
        this.resizeHandleRight = document.getElementById('resize-handle-right');

        // State
        this.panX = 0;
        this.panY = 0;
        this.zoom = 1;
        this.isPanning = false;
        this.panButton = null;
        this.isDraggingNode = null;
        this.activeWire = null;

        this.dragOffset = {x: 0, y: 0};
        this.lastMousePos = {x: 0, y: 0};
        this.resizing = {side: null};

        // Execution State
        this.executionState = 'ready'; // ready, running, error, finished
        this.isViewOnly = false;

        this.init();
    }

    async init() {
        // Safety Check
        if (!this.bookId) {
            console.error("GraphEditor: Missing Book ID.");
            return;
        }

        this.setupEventListeners();
        this.applySavedSidebarWidths();
        this.render();

        if (this.mode === 'edit') {
            await this.loadLibrary();
        }

        // Load Graph State
        await this.loadGraph();

        if (this.isMonitorMode) {
            this.container.classList.add('monitor-mode');
            this.startPolling();
        }

        this.updateCounts();
    }

    // --- API Interactions ---

    async updateBookName(name) {
        const result = await this.apiFetch('update_book', {
            method: 'POST',
            body: JSON.stringify({name: name})
        });
        if (result && result.status === 'updated') {
            document.title = `${result.name} | Talos Graph Editor`;
        } else {
            console.error("Failed to update name");
        }
    }

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

    filterLibrary(query) {
        if (!this.libraryContainer) return;
        const q = query.toLowerCase();

        const categories = this.libraryContainer.querySelectorAll('.category');
        categories.forEach(cat => {
            let hasVisible = false;
            const items = cat.querySelectorAll('.library-item');
            items.forEach(item => {
                const text = item.innerText.toLowerCase();
                if (text.includes(q)) {
                    item.style.display = '';
                    hasVisible = true;
                } else {
                    item.style.display = 'none';
                }
            });

            cat.style.display = hasVisible ? '' : 'none';
        });
    }

    async loadLibrary() {
        const data = await this.apiFetch('library');
        if (!data || !data.library) return;

        this.libraryContainer.innerHTML = '';

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
                    if (this.isMonitorMode) {
                        e.preventDefault();
                        return;
                    }
                    if (spell.is_book) {
                        e.dataTransfer.setData('invoked-book-id', spell.id);
                        e.dataTransfer.setData('type', 'subgraph');
                    } else {
                        e.dataTransfer.setData('spell-id', spell.id);
                        e.dataTransfer.setData('type', 'spell');
                    }
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
                    invoked_spellbook_id: n.invoked_spellbook_id,
                    isRoot: n.is_root, // Trust Server Logic
                    skipApi: true // IMPORTANT: This flag allows bypassing the monitor lock
                });
            });
        }

        // Add Connections
        if (data.connections) {
            data.connections.forEach(c => {
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

    getSelectedNodes() {
        return this.nodes.filter(n => {
            const el = document.getElementById(n.id);
            return el && el.classList.contains('selected');
        });
    }

    updateEyeballState() {
        const btn = document.getElementById('view-toggle');
        const selected = this.getSelectedNodes();
        if (this.isMonitorMode && selected.length === 2) {
            btn.style.color = '#a855f7'; // Purple for Battle Mode
            btn.title = "Open Multihead Comparison";
            btn.style.transform = "scale(1.2)";
        } else {
            btn.style.color = ''; // Default
            btn.title = "Toggle View Mode";
            btn.style.transform = "";
        }
    }

    setupEventListeners() {
        // Panning logic
        this.container.addEventListener('mousedown', (e) => {
            // Start pan on left-drag over canvas (container or any layer), but not on nodes
            if (e.button === 0 && this.container.contains(e.target) && !e.target.closest('.node')) {
                this.isPanning = true;
                this.panButton = 0;
                this.container.style.cursor = 'grabbing';
                this.nodes.forEach(n => {
                    const el = document.getElementById(n.id);
                    if (el) el.classList.remove('selected');
                });
                this.updateEyeballState();
                this.closeInspector();
            }
        });

        // Zoom logic
        this.container.addEventListener('wheel', (e) => {
            e.preventDefault();
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
            if (this.resizing.side) {
                const deltaX = e.clientX - this.resizing.startX;
                const root = document.documentElement;
                if (this.resizing.side === 'left') {
                    const minW = 180;
                    const maxW = 500;
                    const newW = Math.min(maxW, Math.max(minW, this.resizing.startWidth + deltaX));
                    root.style.setProperty('--sidebar-left-width', `${newW}px`);
                } else {
                    const minW = 280;
                    const maxW = 600;
                    const newW = Math.min(maxW, Math.max(minW, this.resizing.startWidth - deltaX));
                    root.style.setProperty('--inspector-width', `${newW}px`);
                }
                this.lastMousePos = {x: e.clientX, y: e.clientY};
                return;
            }

            const dx = e.clientX - this.lastMousePos.x;
            const dy = e.clientY - this.lastMousePos.y;

            if (this.isPanning) {
                this.panX += dx;
                this.panY += dy;
                this.updateCanvasTransform();
            }

            // [FIX] Disable Dragging in Monitor Mode
            if (this.isDraggingNode && !this.isMonitorMode) {
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
            if (this.resizing.side) {
                this.saveSidebarWidths();
                this.resizing.side = null;
                document.body.style.cursor = '';
                document.body.style.userSelect = '';
            }

            if (this.isPanning && e.button === this.panButton) {
                this.isPanning = false;
                this.panButton = null;
                this.container.style.cursor = '';
            }

            if (this.activeWire) {
                this.completeWire(e.target);
            }

            if (this.isDraggingNode) {
                const node = this.isDraggingNode;
                const el = document.getElementById(node.id);
                if (el) el.style.zIndex = 'auto';

                if (!this.isMonitorMode && !node.id.toString().startsWith('temp_')) {
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


        const autoLayoutBtn = document.getElementById('auto-layout-btn');
        if (autoLayoutBtn) {
            autoLayoutBtn.addEventListener('click', () => this.autoLayout());
        }

        if (this.searchInput) {
            this.searchInput.addEventListener('input', (e) => {
                this.filterLibrary(e.target.value);
            });
        }

        // Title Edit Logic
        const titleInput = document.getElementById('spellbook-name');
        if (titleInput && !this.isMonitorMode) {
            titleInput.addEventListener('change', (e) => {
                const newName = e.target.value.trim();
                if (newName) {
                    this.updateBookName(newName);
                    titleInput.blur();
                }
            });
            titleInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') titleInput.blur();
            });
        }

        const startBtn = document.getElementById('start-btn');
        if (startBtn) {
            startBtn.addEventListener('click', () => this.startExecution());
        }

        // Stop Button Logic
        const stopBtn = document.getElementById('stop-btn');
        if (stopBtn) {
            stopBtn.addEventListener('click', () => {
                if (this.isMonitorMode && window.djangoContext.terminateUrl) {
                    if (confirm("WARNING: Force Stop this Operation?")) {
                        fetch(window.djangoContext.terminateUrl, {
                            method: 'POST',
                            headers: {'X-CSRFToken': this.csrfToken}
                        }).then(() => {
                            window.location.reload();
                        });
                    }
                } else {
                    this.stopExecution();
                }
            });
        }

        document.getElementById('view-toggle').addEventListener('click', () => {
            const selected = this.getSelectedNodes();

            if (this.isMonitorMode && selected.length === 2) {
                // BATTLE MODE
                const h1 = selected[0].head_id;
                const h2 = selected[1].head_id;

                if (h1 && h2) {
                    const url = `/hydra/battle/${this.spawnId}/?h1=${h1}&h2=${h2}`;
                    window.location.href = url;
                } else {
                    alert("One or more selected nodes have not run yet (No Head ID).");
                }
            } else {
                this.isViewOnly = !this.isViewOnly;
                this.container.classList.toggle('view-only', this.isViewOnly);
            }
        });

        this.container.addEventListener('dragover', (e) => {
            if (this.isMonitorMode) return;
            e.preventDefault();
        });

        this.container.addEventListener('drop', (e) => {
            if (this.isMonitorMode) return;
            e.preventDefault();
            const spellId = e.dataTransfer.getData('spell-id');
            const invokedBookId = e.dataTransfer.getData('invoked-book-id');
            const spellName = e.dataTransfer.getData('spell-name');

            if (spellId || invokedBookId) {
                const coords = this.toCanvasCoords(e.clientX, e.clientY);
                this.addNode(spellName, coords.x - 100, coords.y - 40, {
                    spell_id: spellId,
                    invoked_spellbook_id: invokedBookId || null
                });
            }
        });

        this.setupResizeHandles();
    }

    setupResizeHandles() {
        const root = document.documentElement;
        const SIDEBAR_DEFAULT = 250;
        const INSPECTOR_DEFAULT = 380;

        const startResize = (side, e) => {
            if (e.button !== 0) return;
            e.preventDefault();
            const leftW = parseFloat(getComputedStyle(root).getPropertyValue('--sidebar-left-width')) || SIDEBAR_DEFAULT;
            const rightW = parseFloat(getComputedStyle(root).getPropertyValue('--inspector-width')) || INSPECTOR_DEFAULT;
            this.resizing = {
                side,
                startX: e.clientX,
                startWidth: side === 'left' ? leftW : rightW
            };
            document.body.style.cursor = 'col-resize';
            document.body.style.userSelect = 'none';
        };

        const resetWidth = (side) => {
            if (side === 'left') {
                root.style.setProperty('--sidebar-left-width', `${SIDEBAR_DEFAULT}px`);
            } else {
                root.style.setProperty('--inspector-width', `${INSPECTOR_DEFAULT}px`);
            }
            this.saveSidebarWidths();
        };

        if (this.resizeHandleLeft) {
            this.resizeHandleLeft.addEventListener('mousedown', (e) => {
                startResize('left', e);
            });
            this.resizeHandleLeft.addEventListener('dblclick', () => resetWidth('left'));
        }
        if (this.resizeHandleRight) {
            this.resizeHandleRight.addEventListener('mousedown', (e) => {
                if (this.inspector && this.inspector.classList.contains('hidden')) return;
                startResize('right', e);
            });
            this.resizeHandleRight.addEventListener('dblclick', () => resetWidth('right'));
        }
    }

    saveSidebarWidths() {
        try {
            const root = document.documentElement;
            const left = getComputedStyle(root).getPropertyValue('--sidebar-left-width').trim();
            const right = getComputedStyle(root).getPropertyValue('--inspector-width').trim();
            if (left) localStorage.setItem('graphEditor.sidebarLeftWidth', left);
            if (right) localStorage.setItem('graphEditor.inspectorWidth', right);
        } catch (e) {
            // ignore
        }
    }

    applySavedSidebarWidths() {
        try {
            const root = document.documentElement;
            const left = localStorage.getItem('graphEditor.sidebarLeftWidth');
            const right = localStorage.getItem('graphEditor.inspectorWidth');
            const minLeft = 180;
            const maxLeft = 500;
            const minRight = 280;
            const maxRight = 600;
            if (left) {
                const px = parseFloat(left);
                if (!isNaN(px)) {
                    root.style.setProperty('--sidebar-left-width', `${Math.min(maxLeft, Math.max(minLeft, px))}px`);
                }
            }
            if (right) {
                const px = parseFloat(right);
                if (!isNaN(px)) {
                    root.style.setProperty('--inspector-width', `${Math.min(maxRight, Math.max(minRight, px))}px`);
                }
            }
        } catch (e) {
            // ignore
        }
    }

    updateCanvasTransform() {
        const transform = `translate(${this.panX}px, ${this.panY}px) scale(${this.zoom})`;
        this.grid.style.transform = transform;
        this.nodesLayer.style.transform = transform;
        this.svgLayer.style.transform = transform;
    }

    async addNode(title, x, y, options = {}) {
        // [FIX] Allow nodes if skipApi is true (loading from server), otherwise block user actions
        if (this.isMonitorMode && !options.skipApi) return;

        const tempId = options.id || 'temp_' + Math.random().toString(36).substr(2, 9);
        const isDelegated = !!options.invoked_spellbook_id;
        const isRoot = options.isRoot || (options.spell_id === 1 && !isDelegated);

        const node = {
            id: tempId,
            title,
            x,
            y,
            spell_id: options.spell_id,
            invoked_spellbook_id: options.invoked_spellbook_id,
            head_id: null,
            child_spawn_id: null,
            inputs: isRoot ? 0 : (options.inputs !== undefined ? options.inputs : 1),
            outputs: options.outputs !== undefined ? options.outputs : 3,
            canDelete: options.canDelete !== undefined ? options.canDelete : true,
            isRoot: options.isRoot || false
        };

        this.nodes.push(node);
        this.createNodeDOM(node);
        this.updateCounts();

        if (!options.skipApi && (options.spell_id || options.invoked_spellbook_id)) {
            const nodeEl = document.getElementById(tempId);
            nodeEl.classList.add('pending');

            const result = await this.apiFetch('add_node', {
                method: 'POST',
                body: JSON.stringify({
                    spell_id: options.spell_id,
                    invoked_spellbook_id: options.invoked_spellbook_id,
                    x: Math.round(x),
                    y: Math.round(y)
                })
            });

            if (result && result.id) {
                nodeEl.id = result.id;
                node.id = result.id;
                nodeEl.querySelectorAll('.pin').forEach(pin => {
                    pin.dataset.nodeId = result.id;
                });
                nodeEl.classList.remove('pending');
            } else {
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

        const eyeTitle = this.mode === 'monitor' ? 'Flight Recorder' : 'Edit Spell';
        const isDelegated = !!node.invoked_spellbook_id;
        nodeEl.innerHTML = `
            <div class="node-header ${node.isRoot ? 'root-header' : ''} ${isDelegated ? 'delegated-gradient' : ''}">
                <h4>${isDelegated ? '🌀 ' + node.title : node.title}</h4>
                <div class="node-controls">
                    <button class="mini-btn view" title="${eyeTitle}">👁️</button>
                    ${node.isRoot && !this.isMonitorMode ? `
                        <button class="mini-btn play" title="Start from here">▶️</button>
                    ` : ''}
                    ${node.canDelete && !this.isMonitorMode ? '<button class="delete-btn">&times;</button>' : ''}
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
            e.stopPropagation(); // Prevent container click

            // Multi-Select Logic
            if (e.shiftKey) {
                if (nodeEl.classList.contains('selected')) {
                    nodeEl.classList.remove('selected');
                } else {
                    nodeEl.classList.add('selected');
                }
            } else {
                // Standard Single Select
                this.nodes.forEach(n => {
                    const el = document.getElementById(n.id);
                    if (el) el.classList.remove('selected');
                });
                nodeEl.classList.add('selected');
            }

            // Update "Big Eyeball" State
            this.updateEyeballState();

            // Inspector Logic
            if (!e.shiftKey) {
                this.openInspector(node);
            }
        });

        // Dragging (Disable in Monitor Mode)
        const header = nodeEl.querySelector('.node-header');
        header.addEventListener('mousedown', (e) => {
            if (this.isMonitorMode) return;
            if (e.target.closest('.node-controls') || e.target.closest('.mini-btn') || e.target.closest('.delete-btn')) return;
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

        // Eye Button
        nodeEl.querySelector('.mini-btn.view').addEventListener('mousedown', (e) => e.stopPropagation());
        nodeEl.querySelector('.mini-btn.view').addEventListener('click', (e) => {
            e.stopPropagation();
            if (this.mode === 'monitor') {
                if (node.child_spawn_id) {
                    window.location.href = `/hydra/monitor/${node.child_spawn_id}/?full=True`;
                } else if (node.head_id) {
                    window.open(`/hydra/head/${node.head_id}/`, '_self');
                } else {
                    alert('Has not run yet');
                }
            } else {
                if (node.invoked_spellbook_id) {
                    window.open(`/hydra/graph/editor/${node.invoked_spellbook_id}/`, '_self');
                } else {
                    window.open(`/admin/hydra/hydraspellbooknode/${node.id}/change/`);
                }
            }
        });

        // Play Button
        const playBtn = nodeEl.querySelector('.mini-btn.play');
        if (playBtn) {
            playBtn.addEventListener('mousedown', (e) => e.stopPropagation());
            playBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                this.startExecution();
            });
        }

        // Delete Button
        const delBtn = nodeEl.querySelector('.delete-btn');
        if (delBtn) {
            delBtn.addEventListener('mousedown', (e) => e.stopPropagation());
            delBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                this.deleteNode(node.id);
            });
        }

        // Wire Creation (Disable in Monitor Mode)
        nodeEl.querySelectorAll('.pin.output-white, .pin.output-success, .pin.output-error').forEach(pin => {
            pin.addEventListener('mousedown', (e) => {
                if (this.isMonitorMode) return;
                if (nodeEl.classList.contains('pending')) return;
                e.stopPropagation();
                this.startWire(pin);
            });
        });

        if (this.isMonitorMode) {
            const viewBtn = nodeEl.querySelector('.mini-btn.view');
            if (viewBtn) {
                viewBtn.disabled = true;
                viewBtn.style.opacity = '0.3';
            }
        }

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
        // [FIX] Allow deleting if localOnly (used during redraw), otherwise block
        if (this.isMonitorMode && !localOnly) return;

        // Ensure stricter string comparison just in case
        const targetId = String(nodeId);
        const node = this.nodes.find(n => String(n.id) === targetId);
        if (!node) return;

        this.nodes = this.nodes.filter(n => String(n.id) !== targetId);
        this.connections = this.connections.filter(c => String(c.fromNode) !== targetId && String(c.toNode) !== targetId);

        const el = document.getElementById(targetId);
        if (el) el.remove();

        this.renderConnections();
        this.updateCounts();

        if (!localOnly && !targetId.startsWith('temp_')) {
            await this.apiFetch('delete_node', {
                method: 'POST',
                body: JSON.stringify({node_id: targetId})
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
        const path = this.calculateBezierPath(this.activeWire.startX, this.activeWire.startY, coords.x, coords.y);
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

                // [VISUAL] Highlight active wires
                let strokeWidth = 2;
                if (this.isMonitorMode) {
                    const srcNode = this.nodes.find(n => n.id === conn.fromNode);
                    if (srcNode && srcNode.status_id) {
                        // Flow (0) or Success (1) -> Thick if Success (4)
                        if ((conn.fromPort === 0 || conn.fromPort === 1) && srcNode.status_id === 4) strokeWidth = 5;
                        // Failure (2) -> Thick if Failed (5)
                        if (conn.fromPort === 2 && srcNode.status_id === 5) strokeWidth = 5;
                        // Running (2/3) -> Medium thickness for Flow
                        if (conn.fromPort === 0 && (srcNode.status_id === 2 || srcNode.status_id === 3)) strokeWidth = 3;
                    }
                }
                path.setAttribute('stroke-width', strokeWidth);

                path.setAttribute('class', 'wire');

                // Allow deleting wires only in edit mode
                if (!this.isMonitorMode) {
                    // [FIX] Listen for 'contextmenu' instead of 'dblclick'
                    path.addEventListener('contextmenu', (e) => {
                        e.preventDefault(); // Stop Browser Menu
                        this.removeConnection(index);
                    });
                }
                this.connGroup.appendChild(path);
            }
        });
    }

    updateWiresForNode(nodeId) {
        // [FIX] Coerce to string to ensure matching works even if data types differ (Int vs String)
        const targetStr = String(nodeId);
        const involved = this.connections.some(c => String(c.fromNode) === targetStr || String(c.toNode) === targetStr);
        if (involved) this.renderConnections();
    }

    async removeConnection(index) {
        if (this.isMonitorMode) return;
        const conn = this.connections[index];
        if (!conn) return;

        this.connections.splice(index, 1);
        this.renderConnections();
        this.updateCounts();

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
        let selector = `.pin[data-port-type="${type}"][data-port-index="${index}"]`;
        return nodeEl.querySelector(selector);
    }

    calculateBezierPath(x1, y1, x2, y2) {
        let dx = Math.abs(x1 - x2) * 0.5;
        const minHandle = 50;
        dx = x1 > x2 ? Math.max(dx, minHandle) + (x1 - x2) * 0.2 : Math.max(dx, minHandle);
        const cp1x = x1 + dx;
        const cp1y = y1;
        const cp2x = x2 - dx;
        const cp2y = y2;
        return `M ${x1} ${y1} C ${cp1x} ${cp1y}, ${cp2x} ${cp2y}, ${x2} ${y2}`;
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
        if (startBtn) startBtn.disabled = (status === 'running');
    }

    async startExecution() {
        if (this.executionState === 'running') return;
        this.setExecutionStatus('running', 'Spawning Process...');
        const result = await this.apiFetch('launch/', {
            method: 'POST',
            body: JSON.stringify({book_id: this.bookId})
        });
        if (result && result.status === 'started') {
            // this.setExecutionStatus('running', 'Process Active');
            window.location.href = `/hydra/monitor/${result.spawn_id}/?full=True`;
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
            const children = this.connections.filter(c => c.fromNode === id).map(c => c.toNode);
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
                    if (!this.isMonitorMode) {
                        this.apiFetch('move_node', {
                            method: 'POST',
                            body: JSON.stringify({node_id: node.id, x: node.x, y: node.y})
                        });
                    }
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

    // --- MONITORING LOGIC ---
    startPolling() {
        // Store the interval ID so we can kill it later
        this.pollingInterval = setInterval(async () => {
            const data = await this.apiFetch(`status?spawn_id=${this.spawnId}&t=${Date.now()}`);
            if (data) {
                this.updateNodeStatuses(data.nodes || {});

                // [FIX]: Stop polling if the overall spawn is no longer active
                if (data.status === 'Success' || data.status === 'Failed' || data.status === 'Aborted') {
                    console.log(`[MONITOR] Spawn reached terminal state (${data.status}). Stopping poll.`);
                    clearInterval(this.pollingInterval);
                    this.setExecutionStatus(data.status.toLowerCase());
                }
            }
        }, 1000);
    }

    updateNodeStatuses(statusMap) {
        let isAnyRunning = false;
        this.nodes.forEach(node => {
            const status = statusMap[node.id];
            const dom = document.getElementById(node.id);
            if (!dom || !status) return;

            node.head_id = status.head_id;
            node.child_spawn_id = status.child_spawn_id; // Capture Child Spawn ID

            node.status_id = status.status_id; // Store for wire logic

            const header = dom.querySelector('.node-header');
            if (header) {
                header.classList.remove('running', 'success', 'failed');
                // CLEANUP: Reset ALL visual states
                dom.classList.remove('status-delegated');
                header.classList.remove('delegated-gradient'); // Remove initial delegated look
                header.style.background = ''; // Clear inline if any

                if (status.status_id === 2 || status.status_id === 3) {
                    header.classList.add('running');
                    isAnyRunning = true;
                }
                if (status.status_id === 4) header.classList.add('success');
                if (status.status_id === 5) header.classList.add('failed');

                // DELEGATED STATUS (7)
                if (status.status_id === 7) {
                    dom.classList.add('status-delegated');
                    header.classList.add('delegated-gradient'); // Re-apply if still delegated
                    // Ensure view button is active
                    isAnyRunning = true;
                }
            }

            const viewBtn = dom.querySelector('.mini-btn.view');
            if (viewBtn && this.isMonitorMode) {
                if (node.head_id) {
                    viewBtn.disabled = false;
                    viewBtn.style.opacity = '1';
                    viewBtn.style.cursor = 'pointer';
                } else {
                    viewBtn.disabled = true;
                    viewBtn.style.opacity = '0.3';
                    viewBtn.style.cursor = 'not-allowed';
                }
            }
        });

        // [FIX] Ensure wires update color based on node status changes (e.g. Success -> Green Wire)
        this.renderConnections();

        const stopBtn = document.getElementById('stop-btn');
        if (stopBtn && this.isMonitorMode) {
            stopBtn.disabled = !isAnyRunning;
            if (isAnyRunning) {
                stopBtn.style.opacity = '1';
                stopBtn.style.cursor = 'pointer';
                stopBtn.style.backgroundColor = '#ef4444';
            } else {
                stopBtn.style.opacity = '0.3';
                stopBtn.style.cursor = 'not-allowed';
                stopBtn.style.backgroundColor = '#333';
            }
        }
    }

    render() {
        this.updateCanvasTransform();
    }

    // --- Inspector Logic ---

    async openInspector(node) {
        if (!this.inspector) return;

        this.activeNodeId = node.id;
        this.inspector.classList.remove('hidden');

        // Set Header
        const isDelegated = !!node.invoked_spellbook_id;
        const inspectorTitle = this.inspector.querySelector('h2');
        if (inspectorTitle) {
            inspectorTitle.innerHTML = `
                <span style="color: ${isDelegated ? '#a855f7' : '#f8fafc'}">
                    ${isDelegated ? '🌀 ' : ''}${node.title}
                </span>
            `;
        }

        if (this.inspectorHeaderSub) {
            this.inspectorHeaderSub.innerText = `ID: ${node.id}`;
        }

        if (this.inspectorContent) {
            this.inspectorContent.innerHTML = '<div style="text-align: center; color: #64748b; margin-top: 20px;">Loading details...</div>';
        }

        if (this.isMonitorMode) {
            await this.fetchNodeTelemetry(node.id);
        } else {
            await this.fetchNodeDetails(node.id);
        }
    }

    closeInspector() {
        if (!this.inspector) return;
        this.inspector.classList.add('hidden');
        this.activeNodeId = null;
    }

    async fetchNodeDetails(nodeId) {
        const data = await this.apiFetch(`node_details?node_id=${nodeId}`);
        if (data) {
            this.renderInspectorEdit(data);
        }
    }

    renderInspectorEdit(data) {
        if (!this.inspectorContent) return;
        let html = '';

        // Header
        html += `<div class="inspector-section-header" style="margin-bottom: 20px;">
            <div style="font-size: 0.8rem; color: #94a3b8; margin-bottom: 4px;">SPELL</div>
            <div style="font-size: 1.1rem; color: #f1f5f9; font-weight: 600;">${data.name || 'Unknown'}</div>
            <div style="font-size: 0.8rem; color: #64748b; margin-top: 4px; font-style: italic;">
                ${data.description || 'No description'}
            </div>
        </div>`;

        // Context Variables
        html += `<div class="section-title" style="display: flex; align-items: center; justify-content: space-between;">
            <span>Context Variables</span>
            <button class="mini-btn" style="padding: 2px 8px; font-size: 1rem; color: #cbd5e1; border: 1px solid #334155; background: #1e293b; cursor: pointer; border-radius: 4px;" 
                onclick="window.app.promptAddVariable('${data.node_id}')" title="Add Override">+</button>
        </div>`;

        if (data.context_matrix && data.context_matrix.length > 0) {
            html += `<table class="smart-table">`;
            html += `<thead><tr><th style="width: 40%">Variable</th><th>Value</th></tr></thead>`;
            html += `<tbody>`;

            data.context_matrix.forEach(item => {
                const sourceClass = `source-${item.source}`;
                const inputClass = item.source === 'override' ? 'input-override' : (item.source === 'global' ? 'input-global' : '');

                // Determine if we need a textarea
                const isLong = item.display_value.length > 50 || item.key.toLowerCase().includes('prompt') || item.key.toLowerCase().includes('script');
                const uniqueId = `ctx-${item.key}-${data.node_id}`;

                let inputHtml = '';
                if (isLong) {
                    inputHtml = `<textarea 
                        id="${uniqueId}"
                        class="var-input ${inputClass}" 
                        placeholder="${item.source === 'global' ? 'Global Value' : 'Default'}"
                        ${item.is_readonly ? 'readonly' : ''}
                        rows="3"
                        style="resize: vertical; min-height: 60px;"
                        onblur="window.app.handleContextChange('${data.node_id}', '${item.key}', this.value)"
                    >${item.value}</textarea>`;
                } else {
                    inputHtml = `<input type="text" 
                        id="${uniqueId}"
                        class="var-input ${inputClass}" 
                        value="${item.value}" 
                        placeholder="${item.source === 'global' ? 'Global Value' : 'Default'}"
                        ${item.is_readonly ? 'readonly' : ''}
                        onchange="window.app.handleContextChange('${data.node_id}', '${item.key}', this.value)"
                    >`;
                }

                // add clear button if override
                let actionsHtml = '';
                if (item.source === 'override') {
                    // X button to clear override
                    actionsHtml = `<div style="position: absolute; right: 8px; top: 50%; transform: translateY(-50%); cursor: pointer; color: #ef4444; opacity: 0.7;" 
                        onclick="window.app.handleContextChange('${data.node_id}', '${item.key}', '')" title="Reset to Default">✕</div>`;

                    if (isLong) {
                        actionsHtml = `<div style="position: absolute; right: 8px; top: 12px; cursor: pointer; color: #ef4444; opacity: 0.7;" 
                        onclick="window.app.handleContextChange('${data.node_id}', '${item.key}', '')" title="Reset to Default">✕</div>`;
                    }
                }

                html += `<tr class="var-row">
                    <td>
                        <label for="${uniqueId}" class="var-key" style="cursor: pointer;">${item.key}</label>
                        <div style="font-size: 0.7rem; color: #64748b; display: flex; align-items: center; gap: 4px;">
                            <div class="source-indicator ${sourceClass}" style="position: static;"></div>
                            ${item.source}
                        </div>
                    </td>
                    <td>
                        <div class="var-input-wrapper" style="${isLong ? 'align-items: flex-start;' : ''}">
                            ${inputHtml}
                            ${actionsHtml}
                        </div>
                    </td>
                </tr>`;
            });

            html += `</tbody></table>`;
        } else {
            html += `<div style="font-style: italic; color: #64748b; padding: 10px; text-align: center; border: 1px dashed #334155; border-radius: 6px;">No variables detected in Spell.</div>`;
        }

        // Action Bar
        html += `
        <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #1e293b; display: flex; gap: 10px;">
             <a href="/admin/hydra/hydraspellbooknode/${data.node_id}/change/" target="_blank" class="action-btn" style="text-decoration: none; justify-content: center;">
                ⚙️ Advanced Edit
            </a>
            <button class="action-btn" style="color: #ef4444; border-color: #ef4444;" onclick="window.app.deleteNode('${data.node_id}')">
                🗑 Delete Node
            </button>
        </div>`;

        // Instructions
        html += `
         <div style="margin-top: 20px; font-size: 0.7rem; color: #475569; line-height: 1.4; background: #0f172a; padding: 10px; border-radius: 4px;">
            <div style="margin-bottom: 4px; font-weight: 600; color: #64748b;">COLOR LEGEND</div>
            <div style="display: flex; align-items: center; gap: 6px; margin-bottom: 2px;"><span style="color: #4ade80">●</span> Default (Spell)</div>
            <div style="display: flex; align-items: center; gap: 6px; margin-bottom: 2px;"><span style="color: #facc15">●</span> Override (Node)</div>
            <div style="display: flex; align-items: center; gap: 6px;"><span style="color: #3b82f6">●</span> Global (Env)</div>
        </div>`;

        this.inspectorContent.innerHTML = html;
    }

    async fetchNodeTelemetry(nodeId) {
        // Only fetch if this is still the active node (avoid race conditions)
        if (this.activeNodeId !== nodeId) return;

        // Try to find the Head ID from the local model (updated by polling)
        const node = this.nodes.find(n => n.id === nodeId);
        if (!node) return;

        if (node.head_id) {
            const data = await this.apiFetch(`/api/v1/heads/${node.head_id}/`);
            if (data) {
                // Ensure we pass the node ID for reference, although data has head ID
                this.renderInspectorMonitor(nodeId, data);
            }
        } else {
            this.inspectorContent.innerHTML = '<div style="text-align: center; color: #64748b; margin-top: 40px;">Waiting for execution...</div>';

            // Keep polling if monitor mode
            if (this.isMonitorMode && !document.hidden && this.activeNodeId === nodeId) {
                setTimeout(() => this.fetchNodeTelemetry(nodeId), 1000);
            }
        }
    }

    renderInspectorMonitor(nodeId, data) {
        if (!this.inspectorContent) return;
        const getStatusClass = (s) => {
            // Map data.status or data.status_name to CSS class
            // The serializer returns 'status' as ID/PK or string?
            // HydraHeadSerializer: status is ID. HydraNodeTelemetrySerializer: fields include 'status' (ID) and 'status_name'
            // Let's use status_name for display, status (ID) for logic if needed. 
            // The serializer uses `status` field which is relation -> ID by default in DRF unless nested.
            // Wait, ModelSerializer default for ForeignKey is ID.
            // Let's rely on status_name if available string.
            const sName = data.status_name ? data.status_name.toLowerCase() : '';
            if (sName === 'success') return 'status-success';
            if (sName === 'failed') return 'status-failed';
            if (sName === 'running') return 'status-running';
            return 'status-pending';
        };

        const statusClass = getStatusClass(data.status_id); // Fallback logic or use status_name mapping
        const isRunning = data.status_name === 'Running';

        // --- UNIFIED CONFIGURATION LIST ---
        let configHtml = '';

        // 1. Command
        configHtml += `<div style="margin-bottom: 12px;">
            <div class="var-key" style="color: #a5b4fc; margin-bottom: 4px;">Executed Command</div>
            <div class="var-input" style="font-size: 0.7rem; color: #cbd5e1; user-select: text; white-space: pre-wrap; word-break: break-all;">${data.command || 'N/A'}</div>
        </div>`;

        // 2. Context Matrix
        if (data.context_matrix && data.context_matrix.length > 0) {
            configHtml += `<table class="smart-table" style="margin-bottom: 12px;">`;
            data.context_matrix.forEach(item => {
                const sourceClass = `source-${item.source}`;
                configHtml += `
               <tr class="var-row">
                    <td>
                        <span class="var-key">${item.key}</span>
                        <div style="font-size: 0.7rem; color: #64748b;">${item.source}</div>
                    </td>
                    <td>
                        <div class="var-input-wrapper">
                            <div class="source-indicator ${sourceClass}"></div>
                            <span class="var-input" style="border: none; background: transparent; padding-left: 20px;">
                                ${item.value}
                            </span>
                        </div>
                    </td>
                </tr>`;
            });
            configHtml += `</table>`;
        }

        // 3. Blackboard
        if (data.blackboard && Object.keys(data.blackboard).length > 0) {
            configHtml += `<div class="section-title" style="margin-top: 12px;">Blackboard (Runtime)</div>`;
            configHtml += `<div class="peep-hole" style="max-height: 150px;">${JSON.stringify(data.blackboard, null, 2)}</div>`;
        }

        // --- HTML ASSEMBLY ---
        let html = `
        <div class="telemetry-card">
            <div class="monitor-header">
                <div class="pulse-status ${getStatusClass()}">
                    <div class="pulse-dot"></div>
                    ${data.status_name || 'Unknown'}
                </div>
                 <div style="text-align: right;">
                    <span class="vital-value" style="font-size: 1.2rem; color: ${data.result_code === 0 ? '#4ade80' : '#f87171'};">
                        RC: ${data.result_code !== null ? data.result_code : '--'}
                    </span>
                </div>
            </div>
            
            <div class="vital-grid">
                <div class="vital-item">
                    <span class="vital-label">Delta</span>
                    <span class="vital-value">${data.delta || '0s'}</span>
                </div>
                 <div class="vital-item">
                    <span class="vital-label">Avg Delta</span>
                    <span class="vital-value" style="color: #94a3b8;">${data.average_delta ? parseFloat(data.average_delta).toFixed(2) + 's' : '--'}</span>
                </div>
                <div class="vital-item" style="grid-column: span 2;">
                    <span class="vital-label">Agent</span>
                    <span class="vital-value">${data.agent}</span>
                </div>
            </div>

            <div style="display: flex; gap: 8px; margin-top: 12px;">
                 <a href="/admin/hydra/hydraspellbooknode/${nodeId}/change/" target="_blank" class="action-btn" style="text-decoration: none; flex: 1; justify-content: center;">
                    ⚙️ Edit Node
                </a>
                <a href="/hydra/head/${data.id}/" target="_blank" class="action-btn primary" style="text-decoration: none; flex: 1; justify-content: center;">
                    🚀 War Room
                </a>
                ${data.reasoning_session_id ? `
                <a href="/reasoning/lcars/${data.reasoning_session_id}/" target="_blank" class="action-btn" style="text-decoration: none; flex: 1; justify-content: center; background: linear-gradient(135deg, #f99f1b 0%, #d97706 100%); border-color: #f99f1b; color: #020617; font-weight: 800; box-shadow: 0 2px 5px rgba(249, 159, 27, 0.3);">
                    🧠 Cortex
                </a>
                ` : ''}
            </div>
        </div>

        <div class="section-title">Configuration & State</div>
        <div style="background: #1e293b; padding: 10px; border-radius: 6px; border: 1px solid #334155;">
            ${configHtml}
        </div>

        <div class="section-title">Tool Output</div>
        <div id="inspector-term-tool" style="height: 200px; background: #000; padding: 4px; border-radius: 4px; overflow: hidden;"></div>
        
        <div class="section-title">System Log</div>
        <div id="inspector-term-system" style="height: 150px; background: #000; padding: 4px; border-radius: 4px; overflow: hidden;"></div>
        `;

        this.inspectorContent.innerHTML = html;

        // --- XTERM INITIALIZATION ---
        this.initXterm('inspector-term-tool', data.logs);
        this.initXterm('inspector-term-system', data.exec_logs);

        // Auto-refresh if running
        if (
            isRunning &&
            this.activeNodeId === nodeId &&
            !document.hidden &&
            this.isMonitorMode
        ) {
            setTimeout(() => this.fetchNodeTelemetry(nodeId), 2000);
        }
    }

    initXterm(containerId, content) {
        const container = document.getElementById(containerId);
        if (!container) return;

        // Cleanup existing if any (simplistic approach: clear innerHTML handled by render)
        // Check if Terminal is defined
        if (typeof Terminal === 'undefined') {
            container.innerHTML = `<pre style="color: #fff; font-size: 0.7rem; white-space: pre-wrap;">${content || ''}</pre>`;
            return;
        }

        const term = new Terminal({
            fontFamily: '"JetBrains Mono", monospace',
            fontSize: 10,
            theme: {
                background: '#000000',
                foreground: '#cbd5e1'
            },
            disableStdin: true,
            cursorBlink: false,
            convertEol: true
        });

        const fitAddon = new FitAddon.FitAddon();
        term.loadAddon(fitAddon);

        term.open(container);

        try {
            fitAddon.fit();
        } catch (e) {
            console.warn("Xterm fit failed", e);
        }

        term.write(content || '\x1b[38;5;240m[No Output]\x1b[0m');

        // Handle Resize Observer to refit
        // Optional for now as sidebar width is fixed/transitioned
    }

    async promptAddVariable(nodeId) {
        const key = prompt("Enter variable name (e.g. MY_VAR):");
        if (key && key.trim()) {
            await this.handleContextChange(nodeId, key.trim().toUpperCase(), '');
        }
    }

    async handleContextChange(nodeId, key, value) {
        // Debounce or immediate? Immediate for now, usually user stops typing when clicking away.
        // Actually, onchange fires on blur.

        // Optimistic UI Update
        // Re-render handled by full refresh? No, let's just send API request.

        await this.apiFetch('save_node_context', {
            method: 'POST',
            body: JSON.stringify({
                node_id: nodeId,
                updates: [{key: key, value: value}]
            })
        });

        // Refresh to get correct colors/states
        this.fetchNodeDetails(nodeId);
    }
}

window.app = new GraphEditor();