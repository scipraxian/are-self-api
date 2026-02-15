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
        this.initializeState();
    }

    static populateTemplate(clone, data) {
        const spawnEl = clone.querySelector('.js-hydra-spawn');
        spawnEl.dataset.spawnId = data.id;
        spawnEl.dataset.spellbookId = data.spellbook;

        // Bulletproof status matching
        const statusStr = data.status_name || data.status_label || 'Pending';
        const isAlive = ['Created', 'Pending', 'Running', 'Stopping'].includes(statusStr);
        spawnEl.dataset.isActive = isAlive ? 'true' : 'false';

        if (isAlive) spawnEl.classList.add('active-lane');
        else if (statusStr === 'Failed' || statusStr === 'Aborted') spawnEl.classList.add('failed-lane');

        clone.querySelector('.js-spawn-title').textContent = data.spellbook_name || 'Unknown Protocol';
        clone.querySelector('.js-spawn-id').textContent = `#${data.id.substring(0, 8)}`;

        const statusText = clone.querySelector('.js-spawn-status-text');
        statusText.textContent = statusStr;
        statusText.className = `status-text js-spawn-status-text status-${statusStr.toLowerCase()}`;

        const timeEl = clone.querySelector('.js-spawn-time');
        if (timeEl && data.modified) timeEl.textContent = `${timeSince(data.modified)} ago`;

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

        // CRITICAL NESTING FIX: Force a state fetch on mount to check for subgraphs
        await this.fetchState();

        if (this.isActive) this.startPolling();
    }

    async loadAllHeads() {
        try {
            const response = await fetch(`/api/v1/spawns/${this.spawnId}/heads/`);
            if (!response.ok) return;
            const heads = await response.json();

            for (const head of heads) {
                if (!this.trackEl.querySelector(`.js-hydra-head[data-head-id="${head.id}"]`)) {
                    this.injectHeadDOM(head);
                }
            }
            this.checkOverflow();
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
            const response = await fetch(`/api/v1/spawns/${this.spawnId}/live_status/`);
            if (!response.ok) return;
            const data = await response.json();

            await this.updateDOM(data);

            if (!data.is_active) {
                this.stopPolling();
                this.el.dataset.isActive = 'false';
                this.loadAllHeads();
            }
        } catch (error) {
            console.error(`[HydraSpawn] Fetch failed for ${this.spawnId}:`, error);
        }
    }

    async updateDOM(data) {
        const statusStr = data.status_label || data.status_name || 'Pending';

        if (this.statusEl) {
            this.statusEl.textContent = statusStr;
            this.statusEl.className = `status-text js-spawn-status-text status-${statusStr.toLowerCase()}`;
        }

        this.el.classList.remove('active-lane', 'failed-lane');
        if (data.is_active) this.el.classList.add('active-lane');
        else if (statusStr === 'Failed' || statusStr === 'Aborted') this.el.classList.add('failed-lane');

        if (this.controlCard) this.controlCard.setMode(data.is_active);

        // DISCOVER AND INJECT HEADS & SUBGRAPHS
        if (data.nodes) {
            for (const node of Object.values(data.nodes)) {
                if (node.head_id) await this.ensureHeadExists(node.head_id);
                if (node.child_spawn_id) await this.ensureChildSpawnExists(node.child_spawn_id);
            }
        }
    }

    async ensureHeadExists(headId) {
        if (this.trackEl.querySelector(`.js-hydra-head[data-head-id="${headId}"]`)) return;
        try {
            const response = await fetch(`/api/v1/heads/${headId}/status/`);
            if (!response.ok) return;
            const headData = await response.json();
            this.injectHeadDOM(headData);
            this.checkOverflow();
        } catch (error) {
            console.error(`Failed to inject Head ${headId}:`, error);
        }
    }

    async ensureChildSpawnExists(childSpawnId) {
        if (this.nestedSpawnsEl.querySelector(`.js-hydra-spawn-wrapper > .js-hydra-spawn[data-spawn-id="${childSpawnId}"]`)) return;

        try {
            const response = await fetch(`/api/v1/spawns/${childSpawnId}/?fields=id,spellbook,spellbook_name,status_name,modified,is_active,parent_head`);
            if (!response.ok) return;
            const spawnData = await response.json();

            const tpl = document.getElementById('tpl-hydra-spawn');
            const clone = tpl.content.cloneNode(true);

            HydraSpawnController.populateTemplate(clone, spawnData);
            this.nestedSpawnsEl.appendChild(clone.firstElementChild);

            const newEl = this.nestedSpawnsEl.lastElementChild.querySelector('.js-hydra-spawn');
            new HydraSpawnController(newEl);
        } catch (error) {
            console.error(`Failed to inject SubGraph ${childSpawnId}:`, error);
        }
    }
}