class HydraSpawnController {
    constructor(element) {
        this.el = element;
        this.spawnId = this.el.dataset.spawnId;
        this.isActive = this.el.dataset.isActive === 'true';
        this.pollInterval = null;

        // The Delta Cursors
        this.lastHeadModified = null;

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
        // Fetch ALL heads initially to populate the lane
        await this.syncHeads();
        if (this.isActive) this.startPolling();
    }

    startPolling() {
        this.pollInterval = setInterval(() => {
            this.fetchSpawnStatus();
            this.syncHeads();
        }, 1500);
    }

    stopPolling() {
        if (this.pollInterval) {
            clearInterval(this.pollInterval);
            this.pollInterval = null;
        }
    }

    async fetchSpawnStatus() {
        try {
            const response = await fetch(`/api/v1/spawns/${this.spawnId}/?fields=status_name,is_active`);
            if (!response.ok) return;
            const data = await response.json();

            if (this.statusEl) {
                this.statusEl.textContent = data.status_name;
                this.statusEl.className = `status-text js-spawn-status-text status-${data.status_name.toLowerCase()}`;
            }

            this.el.classList.remove('active-lane', 'failed-lane');
            if (data.is_active) this.el.classList.add('active-lane');
            else if (data.status_name === 'Failed' || data.status_name === 'Aborted') this.el.classList.add('failed-lane');

            if (this.controlCard) this.controlCard.setMode(data.is_active);

            if (!data.is_active) {
                this.stopPolling();
                this.el.dataset.isActive = 'false';
                // Final head sync to catch exact termination states
                this.syncHeads();
            }
        } catch (error) {
            console.error(`[HydraSpawn] Status fetch failed:`, error);
        }
    }

    async syncHeads() {
        try {
            // Ask DRF ONLY for heads that belong to this spawn, ordered by newest modification
            let url = `/api/v1/heads/?spawn=${this.spawnId}&ordering=-modified`;

            if (this.lastHeadModified) {
                url += `&modified__gt=${encodeURIComponent(this.lastHeadModified)}`;
            }

            const response = await fetch(url, {headers: {'Accept': 'application/json'}});
            if (!response.ok) return;

            const data = await response.json();
            const heads = data.results ? data.results : data;

            // ONLY UPDATE CURSOR IF WE GOT DATA
            if (heads.length > 0) {
                this.lastHeadModified = heads[0].modified;

                // Process the Upsert (Iterating backwards keeps chronological injection intact if appending)
                for (let i = heads.length - 1; i >= 0; i--) {
                    const headData = heads[i];
                    const existingEl = this.trackEl.querySelector(`.js-hydra-head[data-head-id="${headData.id}"]`);

                    if (existingEl) {
                        // Surgical DOM update (Delegating to the Head's static update method if we refactor, or simple manual mapping here)
                        HydraHeadController.populateTemplate({querySelector: (sel) => existingEl.querySelector(sel) || existingEl}, headData);
                    } else {
                        // Inject new head
                        this.injectHeadDOM(headData);
                    }
                }
                this.checkOverflow();
            }
        } catch (error) {
            console.error(`[HydraSpawn] Head sync failed:`, error);
        }
    }

    injectHeadDOM(headData) {
        const tpl = document.getElementById('tpl-hydra-head');
        const clone = tpl.content.cloneNode(true);
        HydraHeadController.populateTemplate(clone, headData);
        this.trackEl.appendChild(clone);
    }
}