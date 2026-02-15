class HydraSpawnController {
    constructor(element) {
        this.el = element;
        this.spawnId = this.el.dataset.spawnId;
        this.isActive = this.el.dataset.isActive === 'true';
        this.pollInterval = null;

        this.statusEl = this.el.querySelector('.js-spawn-status-text');
        this.controlCardEl = this.el.querySelector('.js-hydra-control-card');
        this.trackEl = this.el.querySelector('.js-spawn-track');
        this.nestedSpawnsEl = this.el.closest('.js-hydra-spawn-wrapper').querySelector('.js-nested-spawns');

        if (this.controlCardEl) {
            this.controlCard = new HydraSpawnControlCardController(this.controlCardEl, this.spawnId, this.el.dataset.spellbookId);
        }

        this.initTrackObservers();

        // Fetch heads and discover subgraphs immediately
        this.initializeState();
    }

    static populateTemplate(clone, data) {
        const spawnEl = clone.querySelector('.js-hydra-spawn');
        spawnEl.dataset.spawnId = data.id;
        spawnEl.dataset.spellbookId = data.spellbook;

        // Determine Alive State
        const isAlive = ['Created', 'Pending', 'Running', 'Stopping'].includes(data.status_name);
        spawnEl.dataset.isActive = isAlive ? 'true' : 'false';

        if (isAlive) spawnEl.classList.add('active-lane');
        else if (data.status_name === 'Failed' || data.status_name === 'Aborted') spawnEl.classList.add('failed-lane');

        // MAP EXACT DRF FIELDS
        clone.querySelector('.js-spawn-title').textContent = data.spellbook_name || 'Unknown Protocol';
        clone.querySelector('.js-spawn-id').textContent = `#${data.id.substring(0, 8)}`;

        const statusText = clone.querySelector('.js-spawn-status-text');
        statusText.textContent = data.status_name;
        statusText.classList.add(`status-${data.status_name.toLowerCase()}`);

        clone.querySelector('.js-spawn-time').textContent = `${timeSince(data.modified)} ago`;

        clone.querySelector('.js-btn-monitor').href = `/hydra/graph/spawn/${data.id}/?full=True`;
        clone.querySelector('.js-btn-edit').href = `/hydra/graph/editor/${data.spellbook}/`;
    }

    initTrackObservers() {
        if (!this.trackEl) return;
        this.observer = new ResizeObserver(() => this.checkOverflow());
        this.observer.observe(this.trackEl);

        const leftBtn = this.el.querySelector('.js-scroll-left');
        const rightBtn = this.el.querySelector('.js-scroll-right');
        if (leftBtn) leftBtn.addEventListener('click', () => this.trackEl.scrollBy({left: -300, behavior: 'smooth'}));
        if (rightBtn) rightBtn.addEventListener('click', () => this.trackEl.scrollBy({left: 300, behavior: 'smooth'}));
    }

    checkOverflow() {
        const hasOverflow = this.trackEl.scrollWidth > (this.trackEl.clientWidth + 1);
        const btns = this.el.querySelectorAll('.scroll-btn');
        btns.forEach(btn => btn.style.display = hasOverflow ? 'flex' : 'none');
    }

    async initializeState() {
        await this.loadAllHeads();
        if (this.isActive) this.startPolling();
    }

    async loadAllHeads() {
        try {
            // Fetch all heads for this specific spawn
            const response = await fetch(`/api/v1/spawns/${this.spawnId}/heads/`);
            if (!response.ok) return;
            const heads = await response.json();

            const headIds = [];

            for (const head of heads) {
                headIds.push(head.id);
                if (!this.trackEl.querySelector(`.js-hydra-head[data-head-id="${head.id}"]`)) {
                    this.injectHeadDOM(head);
                }
            }
            this.checkOverflow();

            // SUB-GRAPH DISCOVERY:
            // Look at the global spawn list. Do any spawns claim one of our Heads as a parent?
            if (window.talosGlobalSpawns && this.nestedSpawnsEl) {
                const childSpawns = window.talosGlobalSpawns.filter(s => headIds.includes(s.parent_head));

                // Sort chronologically and inject
                childSpawns.sort((a, b) => new Date(a.created) - new Date(b.created));
                for (const childSpawn of childSpawns) {
                    this.injectChildSpawnDOM(childSpawn);
                }
            }

        } catch (error) {
            console.error(`[HydraSpawn] Failed to load heads for ${this.spawnId}:`, error);
        }
    }

    injectHeadDOM(headData) {
        const tpl = document.getElementById('tpl-hydra-head');
        const clone = tpl.content.cloneNode(true);
        HydraHeadController.populateTemplate(clone, headData);
        this.trackEl.appendChild(clone);
        const newEl = this.trackEl.lastElementChild;
        new HydraHeadController(newEl);
    }

    injectChildSpawnDOM(spawnData) {
        if (this.nestedSpawnsEl.querySelector(`.js-hydra-spawn-wrapper > .js-hydra-spawn[data-spawn-id="${spawnData.id}"]`)) return;

        const tpl = document.getElementById('tpl-hydra-spawn');
        const clone = tpl.content.cloneNode(true);

        HydraSpawnController.populateTemplate(clone, spawnData);
        this.nestedSpawnsEl.appendChild(clone.firstElementChild);

        const newEl = this.nestedSpawnsEl.lastElementChild.querySelector('.js-hydra-spawn');
        new HydraSpawnController(newEl); // Recursive magic starts here
    }

    startPolling() {
        this.pollInterval = setInterval(() => this.fetchState(), 1500);
    }

    stopPolling() {
        if (this.pollInterval) {
            clearInterval(this.pollInterval);
            this.pollInterval = null;
        }
    }

    async fetchState() {
        try {
            // live_status gives us updated status and child links for ACTIVE jobs
            const response = await fetch(`/api/v1/spawns/${this.spawnId}/live_status/`, {
                headers: {'Accept': 'application/json'}
            });
            if (!response.ok) return;
            const data = await response.json();

            await this.updateDOM(data);

            if (!data.is_active) {
                this.stopPolling();
                this.el.dataset.isActive = 'false';
                // Trigger one final head refresh to catch exact final states
                this.loadAllHeads();
            }
        } catch (error) {
            console.error(`[HydraSpawn] Fetch failed for ${this.spawnId}:`, error);
        }
    }

    async updateDOM(data) {
        if (this.statusEl) {
            this.statusEl.textContent = data.status_label;
            this.statusEl.className = `status-text js-spawn-status-text status-${data.status_label.toLowerCase()}`;
        }

        this.el.classList.remove('active-lane', 'failed-lane');
        if (data.is_active) this.el.classList.add('active-lane');
        else if (data.status_label === 'Failed' || data.status_label === 'Aborted') this.el.classList.add('failed-lane');

        if (this.controlCard) this.controlCard.setMode(data.is_active);

        // Fetch newly born children dynamically
        if (data.nodes) {
            for (const node of Object.values(data.nodes)) {
                if (node.head_id) {
                    // Check if head exists, if not, trigger a full refresh to get its data
                    if (!this.trackEl.querySelector(`.js-hydra-head[data-head-id="${node.head_id}"]`)) {
                        this.loadAllHeads();
                    }
                }
            }
        }
    }
}