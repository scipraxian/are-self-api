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
        // Fetch heads and discover subgraphs immediately
        await this.syncHeads();
        await this.fetchState();

        if (this.isActive) this.startPolling();
    }

    startPolling() {
        this.pollInterval = setInterval(() => {
            this.syncHeads();
            this.fetchState();
        }, 1500);
    }

    stopPolling() {
        if (this.pollInterval) {
            clearInterval(this.pollInterval);
            this.pollInterval = null;
        }
    }

    async syncHeads() {
        try {
            // One call gets all heads for this spawn. Eliminates the N+1 fetch crash.
            const response = await fetch(`/api/v1/heads/?spawn_id=${this.spawnId}`);
            if (!response.ok) return;

            const data = await response.json();
            const heads = data.results || data;

            // CIRCUIT BREAKER 2: Hard verify the heads belong to this exact spawn
            const myHeads = heads.filter(h => String(h.spawn) === String(this.spawnId) || String(h.spawn_id) === String(this.spawnId));

            for (const headData of myHeads) {
                const existingEl = this.trackEl.querySelector(`.js-hydra-head[data-head-id="${headData.id}"]`);

                if (existingEl) {
                    // Update existing DOM inline
                    HydraHeadController.populateTemplate({querySelector: (sel) => existingEl.querySelector(sel) || existingEl}, headData);
                } else {
                    // Inject new
                    const tpl = document.getElementById('tpl-hydra-head');
                    const clone = tpl.content.cloneNode(true);
                    HydraHeadController.populateTemplate(clone, headData);
                    this.trackEl.appendChild(clone);
                }
            }
            this.checkOverflow();
        } catch (error) {
            console.error(`[HydraSpawn ${this.spawnId}] Head sync failed:`, error);
        }
    }

    async fetchState() {
        try {
            // live_status returns exact child_spawn_id map.
            const response = await fetch(`/api/v1/spawns/${this.spawnId}/live_status/`);
            if (!response.ok) return;
            const data = await response.json();

            await this.updateDOM(data);

            if (!data.is_active) {
                this.stopPolling();
                this.el.dataset.isActive = 'false';
                this.syncHeads();
            }
        } catch (error) {
            console.error(`[HydraSpawn] Status fetch failed:`, error);
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

        // CIRCUIT BREAKER 3: Explicit child injection from literal map. No array looping queries.
        if (data.nodes) {
            for (const node of Object.values(data.nodes)) {
                if (node.child_spawn_id) {
                    await this.ensureChildSpawnExists(node.child_spawn_id);
                }
            }
        }
    }

    async ensureChildSpawnExists(childSpawnId) {
        if (this.nestedSpawnsEl.querySelector(`.js-hydra-spawn-wrapper > .js-hydra-spawn[data-spawn-id="${childSpawnId}"]`)) return;

        try {
            // Exact UUID lookup. Zero chance of returning a recursive list.
            const response = await fetch(`/api/v1/spawns/${childSpawnId}/`);
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