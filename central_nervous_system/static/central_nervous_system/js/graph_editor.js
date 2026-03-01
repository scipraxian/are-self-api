/**
 * Talos Graph Editor Logic
 * Built by Antigravity - Senior Frontend Engineer Refactor
 * 100% DDD Compliant (Neuron, Axon, SpikeTrain)
 */

class GraphEditor {
    constructor() {
        this.neurons = [];
        this.connections = [];

        // Context from Django
        this.pathwayId = window.djangoContext?.pathwayId;
        this.spikeTrainId = window.djangoContext?.spikeTrainId;
        this.mode = window.djangoContext?.mode || 'edit';
        this.csrfToken =
            window.djangoContext?.csrfToken ||
            document.querySelector('[name=csrfmiddlewaretoken]')?.value;
        this.apiUrl = `/central_nervous_system/graph/${this.pathwayId}/`;

        // Monitor Mode State
        this.isMonitorMode = !!this.spikeTrainId;

        // DOM Elements
        this.container = document.getElementById('editor-container');
        this.neuronsLayer = document.getElementById('neurons-layer');
        this.svgLayer = document.getElementById('svg-layer');
        this.connGroup = document.getElementById('connections-group');
        this.grid = document.getElementById('canvas-grid');
        this.tempLine = document.getElementById('temp-line');
        this.libraryContainer = document.getElementById('neuron-library');
        this.searchInput = document.getElementById('neuron-search');

        // Inspector
        this.inspector = document.getElementById('inspector');
        this.inspectorHeaderSub = this.inspector ? this.inspector.querySelector('.sub-id') : null;
        this.inspectorContent = this.inspector ? this.inspector.querySelector('.inspector-content') : null;
        this.activeNeuronId = null;

        // State
        this.panX = 0;
        this.panY = 0;
        this.zoom = 1;
        this.isPanning = false;
        this.isDraggingNeuron = null;
        this.activeWire = null;

        this.dragOffset = {x: 0, y: 0};
        this.lastMousePos = {x: 0, y: 0};

        // Execution State
        this.executionState = 'ready'; // ready, running, error, finished
        this.isViewOnly = false;

        this.init();
    }

    async init() {
        if (!this.pathwayId) {
            console.error("GraphEditor: Missing Pathway ID.");
            return;
        }

        this.setupEventListeners();
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

    async updatePathwayName(name) {
        const result = await this.apiFetch('update_pathway', {
            method: 'POST',
            body: JSON.stringify({name: name})
        });
        if (result && result.status === 'updated') {
            document.title = `${result.name} | Talos Graph Editor`;
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
        data.library.forEach(effector => {
            const cat = effector.category || 'Spells';
            if (!categories[cat]) categories[cat] = [];
            categories[cat].push(effector);
        });

        for (const [name, effectors] of Object.entries(categories)) {
            const catDiv = document.createElement('div');
            catDiv.className = 'category';
            catDiv.innerHTML = `<span>${name}</span>`;

            effectors.forEach(effector => {
                const item = document.createElement('div');
                item.className = 'library-item';
                item.draggable = true;
                item.innerText = effector.name;
                item.dataset.spellId = effector.id;

                item.addEventListener('dragstart', (e) => {
                    if (this.isMonitorMode) {
                        e.preventDefault();
                        return;
                    }
                    if (effector.is_book) {
                        e.dataTransfer.setData('invoked-pathway-id', effector.id);
                        e.dataTransfer.setData('type', 'subgraph');
                    } else {
                        e.dataTransfer.setData('effector-id', effector.id);
                        e.dataTransfer.setData('type', 'effector');
                    }
                    e.dataTransfer.setData('effector-name', effector.name);
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
        this.neurons = [];
        this.connections = [];
        this.neuronsLayer.innerHTML = '';
        this.connGroup.innerHTML = '';

        // Add Neurons
        if (data.neurons) {
            data.neurons.forEach(n => {
                this.addNeuron(n.title, n.x, n.y, {
                    id: n.id,
                    effector_id: n.effector_id,
                    invoked_pathway_id: n.invoked_pathway_id,
                    isRoot: n.is_root,
                    skipApi: true
                });
            });
        }

        // Add Axons (Connections)
        if (data.axons) {
            data.axons.forEach(c => {
                let color = 'rgba(255, 255, 255, 0.8)';
                if (c.status_id === 'success') color = 'rgba(76, 175, 80, 0.8)';
                if (c.status_id === 'fail') color = 'rgba(244, 67, 54, 0.8)';

                this.connections.push({
                    fromNeuron: c.source_neuron_id,
                    fromPort: this.getPortIndexFromStatus(c.status_id),
                    toNeuron: c.target_neuron_id,
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

    getSelectedNeurons() {
        return this.neurons.filter(n => {
            const el = document.getElementById(n.id);
            return el && el.classList.contains('selected');
        });
    }

    updateEyeballState() {
        const btn = document.getElementById('view-toggle');
        const selected = this.getSelectedNeurons();
        if (this.isMonitorMode && selected.length === 2) {
            btn.style.color = '#a855f7';
            btn.title = "Open Multihead Comparison";
            btn.style.transform = "scale(1.2)";
        } else {
            btn.style.color = '';
            btn.title = "Toggle View Mode";
            btn.style.transform = "";
        }
    }

    setupEventListeners() {
        // Panning logic
        this.container.addEventListener('mousedown', (e) => {
            if (e.button === 1 || (e.button === 0 && e.target === this.container)) {
                this.isPanning = true;
                this.container.style.cursor = 'grabbing';
                if (e.target === this.container) {
                    this.neurons.forEach(n => {
                        const el = document.getElementById(n.id);
                        if (el) el.classList.remove('selected');
                    });
                    this.updateEyeballState();
                    this.closeInspector();
                }
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
            const dx = e.clientX - this.lastMousePos.x;
            const dy = e.clientY - this.lastMousePos.y;

            if (this.isPanning) {
                this.panX += dx;
                this.panY += dy;
                this.updateCanvasTransform();
            }

            if (this.isDraggingNeuron && !this.isMonitorMode) {
                const neuron = this.isDraggingNeuron;
                const coords = this.toCanvasCoords(e.clientX, e.clientY);
                neuron.x = coords.x - (this.dragOffset.x / this.zoom);
                neuron.y = coords.y - (this.dragOffset.y / this.zoom);
                this.updateNeuronDOM(neuron);
                this.updateWiresForNeuron(neuron.id);
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

            if (this.isDraggingNeuron) {
                const neuron = this.isDraggingNeuron;
                const el = document.getElementById(neuron.id);
                if (el) el.style.zIndex = 'auto';

                if (!this.isMonitorMode && !neuron.id.toString().startsWith('temp_')) {
                    await this.apiFetch('move_neuron', {
                        method: 'POST',
                        body: JSON.stringify({
                            neuron_id: neuron.id,
                            x: Math.round(neuron.x),
                            y: Math.round(neuron.y)
                        })
                    });
                }
            }
            this.isDraggingNeuron = null;
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

        const titleInput = document.getElementById('pathway-name');
        if (titleInput && !this.isMonitorMode) {
            titleInput.addEventListener('change', (e) => {
                const newName = e.target.value.trim();
                if (newName) {
                    this.updatePathwayName(newName);
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
            const selected = this.getSelectedNeurons();

            if (this.isMonitorMode && selected.length === 2) {
                // BATTLE MODE
                const s1 = selected[0].spike_id;
                const s2 = selected[1].spike_id;

                if (s1 && s2) {
                    const url = `/central_nervous_system/battle/${this.spikeTrainId}/?s1=${s1}&s2=${s2}`;
                    window.location.href = url;
                } else {
                    alert("One or more selected neurons have not run yet (No Spike ID).");
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
            const effectorId = e.dataTransfer.getData('effector-id');
            const invokedPathwayId = e.dataTransfer.getData('invoked-pathway-id');
            const effectorName = e.dataTransfer.getData('effector-name');

            if (effectorId || invokedPathwayId) {
                const coords = this.toCanvasCoords(e.clientX, e.clientY);
                this.addNeuron(effectorName, coords.x - 100, coords.y - 40, {
                    effector_id: effectorId,
                    invoked_pathway_id: invokedPathwayId || null
                });
            }
        });
    }

    updateCanvasTransform() {
        const transform = `translate(${this.panX}px, ${this.panY}px) scale(${this.zoom})`;
        this.grid.style.transform = transform;
        this.neuronsLayer.style.transform = transform;
        this.svgLayer.style.transform = transform;
    }

    async addNeuron(title, x, y, options = {}) {
        if (this.isMonitorMode && !options.skipApi) return;

        const tempId = options.id || 'temp_' + Math.random().toString(36).substr(2, 9);
        const isDelegated = !!options.invoked_pathway_id;
        const isRoot = options.isRoot || (options.effector_id === 1 && !isDelegated);

        const neuron = {
            id: tempId,
            title,
            x,
            y,
            effector_id: options.effector_id,
            invoked_pathway_id: options.invoked_pathway_id,
            spike_id: null,
            child_spike_train_id: null,
            inputs: isRoot ? 0 : (options.inputs !== undefined ? options.inputs : 1),
            outputs: options.outputs !== undefined ? options.outputs : 3,
            canDelete: options.canDelete !== undefined ? options.canDelete : true,
            isRoot: options.isRoot || false
        };

        this.neurons.push(neuron);
        this.createNeuronDOM(neuron);
        this.updateCounts();

        if (!options.skipApi && (options.effector_id || options.invoked_pathway_id)) {
            const neuronEl = document.getElementById(tempId);
            neuronEl.classList.add('pending');

            const result = await this.apiFetch('add_neuron', {
                method: 'POST',
                body: JSON.stringify({
                    effector_id: options.effector_id,
                    invoked_pathway_id: options.invoked_pathway_id,
                    x: Math.round(x),
                    y: Math.round(y)
                })
            });

            if (result && result.id) {
                neuronEl.id = result.id;
                neuron.id = result.id;
                neuronEl.querySelectorAll('.pin').forEach(pin => {
                    pin.dataset.neuronId = result.id;
                });
                neuronEl.classList.remove('pending');
            } else {
                this.deleteNeuron(tempId, true);
            }
        }
        return neuron;
    }

    createNeuronDOM(neuron) {
        const neuronEl = document.createElement('div');
        neuronEl.className = 'neuron';
        neuronEl.id = neuron.id;
        neuronEl.style.left = `${neuron.x}px`;
        neuronEl.style.top = `${neuron.y}px`;

        const eyeTitle = this.mode === 'monitor' ? 'Flight Recorder' : 'Edit Spell';
        const isDelegated = !!neuron.invoked_pathway_id;

        neuronEl.innerHTML = `
            <div class="neuron-header ${neuron.isRoot ? 'root-header' : ''} ${isDelegated ? 'delegated-gradient' : ''}">
                <h4>${isDelegated ? '🌀 ' + neuron.title : neuron.title}</h4>
                <div class="neuron-controls">
                    <button class="mini-btn view" title="${eyeTitle}">👁️</button>
                    ${neuron.isRoot && !this.isMonitorMode ? `
                        <button class="mini-btn play" title="Start from here">▶️</button>
                    ` : ''}
                    ${neuron.canDelete && !this.isMonitorMode ? '<button class="delete-btn">&times;</button>' : ''}
                </div>
            </div>
            <div class="neuron-body">
                <div class="ports-column port-input-wrapper">
                    ${neuron.inputs > 0 ? `
                    <div class="port-item">
                        <div class="pin input" data-neuron-id="${neuron.id}" data-port-index="0" data-port-type="input"></div>
                        <span>Input</span>
                    </div>` : ''}
                </div>
                <div class="ports-column port-output-wrapper">
                    <div class="port-item">
                        <div class="pin output-white" data-neuron-id="${neuron.id}" data-port-index="0" data-port-type="output"></div>
                        <span>${neuron.isRoot ? '' : 'Flow'}</span>
                    </div>
                    ${!neuron.isRoot ? `
                    <div class="port-item">
                        <div class="pin output-success" data-neuron-id="${neuron.id}" data-port-index="1" data-port-type="output"></div>
                        <span>Success</span>
                    </div>
                    <div class="port-item">
                        <div class="pin output-error" data-neuron-id="${neuron.id}" data-port-index="2" data-port-type="output"></div>
                        <span>Fail</span>
                    </div>` : ''}
                </div>
            </div>
        `;

        // Selection
        neuronEl.addEventListener('mousedown', (e) => {
            e.stopPropagation();

            if (e.shiftKey) {
                if (neuronEl.classList.contains('selected')) {
                    neuronEl.classList.remove('selected');
                } else {
                    neuronEl.classList.add('selected');
                }
            } else {
                this.neurons.forEach(n => {
                    const el = document.getElementById(n.id);
                    if (el) el.classList.remove('selected');
                });
                neuronEl.classList.add('selected');
            }

            this.updateEyeballState();

            if (!e.shiftKey) {
                this.openInspector(neuron);
            }
        });

        // Dragging
        const header = neuronEl.querySelector('.neuron-header');
        header.addEventListener('mousedown', (e) => {
            if (this.isMonitorMode) return;
            if (e.target.closest('.neuron-controls') || e.target.closest('.mini-btn') || e.target.closest('.delete-btn')) return;
            if (neuronEl.classList.contains('pending')) return;
            e.stopPropagation();

            neuronEl.style.zIndex = 1000;
            this.neuronsLayer.appendChild(neuronEl);
            this.isDraggingNeuron = neuron;
            this.lastMousePos = {x: e.clientX, y: e.clientY};

            const rect = neuronEl.getBoundingClientRect();
            this.dragOffset = {
                x: e.clientX - rect.left,
                y: e.clientY - rect.top
            };
        });

        // Eye Button
        neuronEl.querySelector('.mini-btn.view').addEventListener('mousedown', (e) => e.stopPropagation());
        neuronEl.querySelector('.mini-btn.view').addEventListener('click', (e) => {
            e.stopPropagation();
            if (this.mode === 'monitor') {
                if (neuron.child_spike_train_id) {
                    window.location.href = `/central_nervous_system/monitor/${neuron.child_spike_train_id}/?full=True`;
                } else if (neuron.spike_id) {
                    window.open(`/central_nervous_system/spike/${neuron.spike_id}/`, '_self');
                } else {
                    alert('Has not run yet');
                }
            } else {
                if (neuron.invoked_pathway_id) {
                    window.open(`/central_nervous_system/graph/editor/${neuron.invoked_pathway_id}/`, '_self');
                } else {
                    window.open(`/admin/central_nervous_system/neuron/${neuron.id}/change/`);
                }
            }
        });

        // Play Button
        const playBtn = neuronEl.querySelector('.mini-btn.play');
        if (playBtn) {
            playBtn.addEventListener('mousedown', (e) => e.stopPropagation());
            playBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                this.startExecution();
            });
        }

        // Delete Button
        const delBtn = neuronEl.querySelector('.delete-btn');
        if (delBtn) {
            delBtn.addEventListener('mousedown', (e) => e.stopPropagation());
            delBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                this.deleteNeuron(neuron.id);
            });
        }

        // Wire Creation
        neuronEl.querySelectorAll('.pin.output-white, .pin.output-success, .pin.output-error').forEach(pin => {
            pin.addEventListener('mousedown', (e) => {
                if (this.isMonitorMode) return;
                if (neuronEl.classList.contains('pending')) return;
                e.stopPropagation();
                this.startWire(pin);
            });
        });

        if (this.isMonitorMode) {
            const viewBtn = neuronEl.querySelector('.mini-btn.view');
            if (viewBtn) {
                viewBtn.disabled = true;
                viewBtn.style.opacity = '0.3';
            }
        }

        this.neuronsLayer.appendChild(neuronEl);
    }

    updateNeuronDOM(neuron) {
        const el = document.getElementById(neuron.id);
        if (el) {
            el.style.left = `${neuron.x}px`;
            el.style.top = `${neuron.y}px`;
        }
    }

    async deleteNeuron(neuronId, localOnly = false) {
        if (this.isMonitorMode && !localOnly) return;

        const targetId = String(neuronId);
        const neuron = this.neurons.find(n => String(n.id) === targetId);
        if (!neuron) return;

        this.neurons = this.neurons.filter(n => String(n.id) !== targetId);
        this.connections = this.connections.filter(c => String(c.fromNeuron) !== targetId && String(c.toNeuron) !== targetId);

        const el = document.getElementById(targetId);
        if (el) el.remove();

        this.renderConnections();
        this.updateCounts();

        if (!localOnly && !targetId.startsWith('temp_')) {
            await this.apiFetch('delete_neuron', {
                method: 'POST',
                body: JSON.stringify({neuron_id: targetId})
            });
        }
    }

    // --- Axon (Wire) Logic ---
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
            fromNeuron: pin.dataset.neuronId,
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
            const toNeuronId = target.dataset.neuronId;
            const toPortIdx = parseInt(target.dataset.portIndex);
            const exists = this.connections.some(c =>
                c.fromNeuron === this.activeWire.fromNeuron &&
                c.fromPort === this.activeWire.fromPort &&
                c.toNeuron === toNeuronId &&
                c.toPort === toPortIdx
            );

            if (!exists && toNeuronId !== this.activeWire.fromNeuron) {
                const type = this.getStatusFromColor(this.activeWire.color);
                const connection = {
                    fromNeuron: this.activeWire.fromNeuron,
                    fromPort: this.activeWire.fromPort,
                    toNeuron: toNeuronId,
                    toPort: toPortIdx,
                    color: this.activeWire.color
                };

                this.connections.push(connection);
                this.renderConnections();
                this.updateCounts();

                await this.apiFetch('connect', {
                    method: 'POST',
                    body: JSON.stringify({
                        source_neuron_id: connection.fromNeuron,
                        target_neuron_id: connection.toNeuron,
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
            const startPin = this.getPinElement(conn.fromNeuron, 'output', conn.fromPort);
            const endPin = this.getPinElement(conn.toNeuron, 'input', conn.toPort);

            if (startPin && endPin) {
                const sRect = startPin.getBoundingClientRect();
                const eRect = endPin.getBoundingClientRect();

                const start = this.toCanvasCoords(sRect.left + sRect.width / 2, sRect.top + sRect.height / 2);
                const end = this.toCanvasCoords(eRect.left + eRect.width / 2, eRect.top + eRect.height / 2);

                const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
                path.setAttribute('d', this.calculateBezierPath(start.x, start.y, end.x, end.y));
                path.setAttribute('stroke', conn.color);

                let strokeWidth = 2;
                if (this.isMonitorMode) {
                    const srcNeuron = this.neurons.find(n => n.id === conn.fromNeuron);
                    if (srcNeuron && srcNeuron.status_id) {
                        if ((conn.fromPort === 0 || conn.fromPort === 1) && srcNeuron.status_id === 4) strokeWidth = 5;
                        if (conn.fromPort === 2 && srcNeuron.status_id === 5) strokeWidth = 5;
                        if (conn.fromPort === 0 && (srcNeuron.status_id === 2 || srcNeuron.status_id === 3)) strokeWidth = 3;
                    }
                }
                path.setAttribute('stroke-width', strokeWidth);

                path.setAttribute('class', 'wire');

                if (!this.isMonitorMode) {
                    path.addEventListener('contextmenu', (e) => {
                        e.preventDefault();
                        this.removeConnection(index);
                    });
                }
                this.connGroup.appendChild(path);
            }
        });
    }

    updateWiresForNeuron(neuronId) {
        const targetStr = String(neuronId);
        const involved = this.connections.some(c => String(c.fromNeuron) === targetStr || String(c.toNeuron) === targetStr);
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
                source_neuron_id: conn.fromNeuron,
                target_neuron_id: conn.toNeuron
            })
        });
    }

    getPinElement(neuronId, type, index) {
        const neuronEl = document.getElementById(neuronId);
        if (!neuronEl) return null;
        let selector = `.pin[data-port-type="${type}"][data-port-index="${index}"]`;
        return neuronEl.querySelector(selector);
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
        document.getElementById('neuron-count').innerText = this.neurons.length;
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
            body: JSON.stringify({pathway_id: this.pathwayId})
        });
        if (result && result.status === 'started') {
            window.location.href = `/central_nervous_system/monitor/${result.spike_train_id}/?full=True`;
        } else {
            this.setExecutionStatus('error', 'SpikeTrain Failed');
        }
    }

    stopExecution(errorMsg = null) {
        this.executionState = errorMsg ? 'error' : 'ready';
        this.setExecutionStatus(this.executionState, errorMsg);
    }

    // --- Auto Layout ---
    autoLayout() {
        if (this.neurons.length === 0) return;
        this.neurons.forEach(n => {
            const el = document.getElementById(n.id);
            if (el) el.classList.add('neuron-auto-layout');
        });

        const startNeuron = this.neurons.find(n => n.isRoot) || this.neurons[0];
        const levels = new Map();
        const visited = new Set();
        const queue = [{id: startNeuron.id, level: 0}];

        while (queue.length > 0) {
            const {id, level} = queue.shift();
            if (visited.has(id)) continue;
            visited.add(id);
            levels.set(id, Math.max(levels.get(id) || 0, level));
            const children = this.connections.filter(c => c.fromNeuron === id).map(c => c.toNeuron);
            children.forEach(childId => queue.push({id: childId, level: level + 1}));
        }

        this.neurons.forEach(neuron => {
            if (!levels.has(neuron.id)) levels.set(neuron.id, 0);
        });

        const columnMap = new Map();
        levels.forEach((level, neuronId) => {
            if (!columnMap.has(level)) columnMap.set(level, []);
            columnMap.get(level).push(neuronId);
        });

        const COL_SPACING = 350;
        const ROW_SPACING = 180;
        const OFFSET_X = 100;
        const OFFSET_Y = 100;

        columnMap.forEach((neuronIds, level) => {
            neuronIds.forEach((neuronId, index) => {
                const neuron = this.neurons.find(n => n.id === neuronId);
                if (neuron) {
                    neuron.x = OFFSET_X + level * COL_SPACING;
                    neuron.y = OFFSET_Y + index * ROW_SPACING;
                    this.updateNeuronDOM(neuron);
                    if (!this.isMonitorMode) {
                        this.apiFetch('move_neuron', {
                            method: 'POST',
                            body: JSON.stringify({neuron_id: neuron.id, x: neuron.x, y: neuron.y})
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
                this.neurons.forEach(n => {
                    const el = document.getElementById(n.id);
                    if (el) el.classList.remove('neuron-auto-layout');
                });
            }
        };
        requestAnimationFrame(animateWires);
    }

    // --- MONITORING LOGIC ---
    startPolling() {
        this.pollingInterval = setInterval(async () => {
            const data = await this.apiFetch(`status?spike_train_id=${this.spikeTrainId}&t=${Date.now()}`);
            if (data) {
                this.updateNeuronStatuses(data.neurons || {});

                if (data.status === 'Success' || data.status === 'Failed' || data.status === 'Aborted') {
                    console.log(`[MONITOR] SpikeTrain reached terminal state (${data.status}). Stopping poll.`);
                    clearInterval(this.pollingInterval);
                    this.setExecutionStatus(data.status.toLowerCase());
                }
            }
        }, 1000);
    }

    updateNeuronStatuses(statusMap) {
        let isAnyRunning = false;
        this.neurons.forEach(neuron => {
            const status = statusMap[neuron.id];
            const dom = document.getElementById(neuron.id);
            if (!dom || !status) return;

            neuron.spike_id = status.spike_id;
            neuron.child_spike_train_id = status.child_spike_train_id;
            neuron.status_id = status.status_id;

            const header = dom.querySelector('.neuron-header');
            if (header) {
                header.classList.remove('running', 'success', 'failed');
                dom.classList.remove('status-delegated');
                header.classList.remove('delegated-gradient');
                header.style.background = '';

                if (status.status_id === 2 || status.status_id === 3) {
                    header.classList.add('running');
                    isAnyRunning = true;
                }
                if (status.status_id === 4) header.classList.add('success');
                if (status.status_id === 5) header.classList.add('failed');

                if (status.status_id === 7) {
                    dom.classList.add('status-delegated');
                    header.classList.add('delegated-gradient');
                    isAnyRunning = true;
                }
            }

            const viewBtn = dom.querySelector('.mini-btn.view');
            if (viewBtn && this.isMonitorMode) {
                if (neuron.spike_id) {
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

    async openInspector(neuron) {
        if (!this.inspector) return;

        this.activeNeuronId = neuron.id;
        this.inspector.classList.remove('hidden');

        // Set Header
        const isDelegated = !!neuron.invoked_pathway_id;
        const inspectorTitle = this.inspector.querySelector('h2');
        if (inspectorTitle) {
            inspectorTitle.innerHTML = `
                <span style="color: ${isDelegated ? '#a855f7' : '#f8fafc'}">
                    ${isDelegated ? '🌀 ' : ''}${neuron.title}
                </span>
            `;
        }

        if (this.inspectorHeaderSub) {
            this.inspectorHeaderSub.innerText = `ID: ${neuron.id}`;
        }

        if (this.inspectorContent) {
            this.inspectorContent.innerHTML = '<div style="text-align: center; color: #64748b; margin-top: 20px;">Loading details...</div>';
        }

        if (this.isMonitorMode) {
            await this.fetchNeuronTelemetry(neuron.id);
        } else {
            await this.fetchNeuronDetails(neuron.id);
        }
    }

    closeInspector() {
        if (!this.inspector) return;
        this.inspector.classList.add('hidden');
        this.activeNeuronId = null;
    }

    async fetchNeuronDetails(neuronId) {
        const data = await this.apiFetch(`neuron_details?neuron_id=${neuronId}`);
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
                onclick="window.app.promptAddVariable('${data.neuron_id}')" title="Add Override">+</button>
        </div>`;

        if (data.context_matrix && data.context_matrix.length > 0) {
            html += `<table class="smart-table">`;
            html += `<thead><tr><th style="width: 40%">Variable</th><th>Value</th></tr></thead>`;
            html += `<tbody>`;

            data.context_matrix.forEach(item => {
                const sourceClass = `source-${item.source}`;
                const inputClass = item.source === 'override' ? 'input-override' : (item.source === 'global' ? 'input-global' : '');

                const isLong = item.display_value.length > 50 || item.key.toLowerCase().includes('prompt') || item.key.toLowerCase().includes('script');
                const uniqueId = `ctx-${item.key}-${data.neuron_id}`;

                let inputHtml = '';
                if (isLong) {
                    inputHtml = `<textarea 
                        id="${uniqueId}"
                        class="var-input ${inputClass}" 
                        placeholder="${item.source === 'global' ? 'Global Value' : 'Default'}"
                        ${item.is_readonly ? 'readonly' : ''}
                        rows="3"
                        style="resize: vertical; min-height: 60px;"
                        onblur="window.app.handleContextChange('${data.neuron_id}', '${item.key}', this.value)"
                    >${item.value}</textarea>`;
                } else {
                    inputHtml = `<input type="text" 
                        id="${uniqueId}"
                        class="var-input ${inputClass}" 
                        value="${item.value}" 
                        placeholder="${item.source === 'global' ? 'Global Value' : 'Default'}"
                        ${item.is_readonly ? 'readonly' : ''}
                        onchange="window.app.handleContextChange('${data.neuron_id}', '${item.key}', this.value)"
                    >`;
                }

                let actionsHtml = '';
                if (item.source === 'override') {
                    actionsHtml = `<div style="position: absolute; right: 8px; top: 50%; transform: translateY(-50%); cursor: pointer; color: #ef4444; opacity: 0.7;" 
                        onclick="window.app.handleContextChange('${data.neuron_id}', '${item.key}', '')" title="Reset to Default">✕</div>`;

                    if (isLong) {
                        actionsHtml = `<div style="position: absolute; right: 8px; top: 12px; cursor: pointer; color: #ef4444; opacity: 0.7;" 
                        onclick="window.app.handleContextChange('${data.neuron_id}', '${item.key}', '')" title="Reset to Default">✕</div>`;
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
             <a href="/admin/central_nervous_system/neuron/${data.neuron_id}/change/" target="_blank" class="action-btn" style="text-decoration: none; justify-content: center;">
                ⚙️ Advanced Edit
            </a>
            <button class="action-btn" style="color: #ef4444; border-color: #ef4444;" onclick="window.app.deleteNeuron('${data.neuron_id}')">
                🗑 Delete Neuron
            </button>
        </div>`;

        // Instructions
        html += `
         <div style="margin-top: 20px; font-size: 0.7rem; color: #475569; line-height: 1.4; background: #0f172a; padding: 10px; border-radius: 4px;">
            <div style="margin-bottom: 4px; font-weight: 600; color: #64748b;">COLOR LEGEND</div>
            <div style="display: flex; align-items: center; gap: 6px; margin-bottom: 2px;"><span style="color: #4ade80">●</span> Default (Spell)</div>
            <div style="display: flex; align-items: center; gap: 6px; margin-bottom: 2px;"><span style="color: #facc15">●</span> Override (Neuron)</div>
            <div style="display: flex; align-items: center; gap: 6px;"><span style="color: #3b82f6">●</span> Global (Env)</div>
        </div>`;

        this.inspectorContent.innerHTML = html;
    }

    async fetchNeuronTelemetry(neuronId) {
        if (this.activeNeuronId !== neuronId) return;

        const neuron = this.neurons.find(n => n.id === neuronId);
        if (!neuron) return;

        if (neuron.spike_id) {
            const data = await this.apiFetch(`neuron_telemetry?neuron_id=${neuronId}&spike_train_id=${this.spikeTrainId}`);
            if (data) {
                this.renderInspectorMonitor(neuronId, data);
            }
        } else {
            this.inspectorContent.innerHTML = '<div style="text-align: center; color: #64748b; margin-top: 40px;">Waiting for execution...</div>';

            if (this.isMonitorMode && !document.hidden && this.activeNeuronId === neuronId) {
                setTimeout(() => this.fetchNeuronTelemetry(neuronId), 1000);
            }
        }
    }

    renderInspectorMonitor(neuronId, data) {
        if (!this.inspectorContent) return;
        const getStatusClass = () => {
            const sName = data.status_name ? data.status_name.toLowerCase() : '';
            if (sName === 'success') return 'status-success';
            if (sName === 'failed') return 'status-failed';
            if (sName === 'running') return 'status-running';
            return 'status-pending';
        };

        const statusClass = getStatusClass();
        const isRunning = data.status_name === 'Running';

        let configHtml = '';

        configHtml += `<div style="margin-bottom: 12px;">
            <div class="var-key" style="color: #a5b4fc; margin-bottom: 4px;">Executed Command</div>
            <div class="var-input" style="font-size: 0.7rem; color: #cbd5e1; user-select: text; white-space: pre-wrap; word-break: break-all;">${data.command || 'N/A'}</div>
        </div>`;

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

        if (data.blackboard && Object.keys(data.blackboard).length > 0) {
            configHtml += `<div class="section-title" style="margin-top: 12px;">Blackboard (Runtime)</div>`;
            configHtml += `<div class="peep-hole" style="max-height: 150px;">${JSON.stringify(data.blackboard, null, 2)}</div>`;
        }

        let html = `
        <div class="telemetry-card">
            <div class="monitor-header">
                <div class="pulse-status ${statusClass}">
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
                 <a href="/admin/central_nervous_system/neuron/${neuronId}/change/" target="_blank" class="action-btn" style="text-decoration: none; flex: 1; justify-content: center;">
                    ⚙️ Edit Neuron
                </a>
                <a href="/central_nervous_system/spike/${data.spike_id}/" target="_blank" class="action-btn primary" style="text-decoration: none; flex: 1; justify-content: center;">
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

        this.initXterm('inspector-term-tool', data.logs);
        this.initXterm('inspector-term-system', data.exec_logs);

        if (
            isRunning &&
            this.activeNeuronId === neuronId &&
            !document.hidden &&
            this.isMonitorMode
        ) {
            setTimeout(() => this.fetchNeuronTelemetry(neuronId), 2000);
        }
    }

    initXterm(containerId, content) {
        const container = document.getElementById(containerId);
        if (!container) return;

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
    }

    async promptAddVariable(neuronId) {
        const key = prompt("Enter variable name (e.g. MY_VAR):");
        if (key && key.trim()) {
            await this.handleContextChange(neuronId, key.trim().toUpperCase(), '');
        }
    }

    async handleContextChange(neuronId, key, value) {
        await this.apiFetch('save_neuron_context', {
            method: 'POST',
            body: JSON.stringify({
                neuron_id: neuronId,
                updates: [{key: key, value: value}]
            })
        });

        this.fetchNeuronDetails(neuronId);
    }
}

window.app = new GraphEditor();