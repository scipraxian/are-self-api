class CNSSpawnController {
    constructor(element) {
        this.el = element;
        this.spawnId = this.el.dataset.spawnId;
        this.isActive = this.el.dataset.isActive === 'true';
        this.pollInterval = null;

        this.statusEl = this.el.querySelector('.js-spawn-status-text');
        this.controlCardEl = this.el.querySelector('.js-cns-control-card');
        this.trackEl = this.el.querySelector('.js-spawn-track');
        this.nestedSpawnsEl = this.el.closest('.js-cns-spawn-wrapper').querySelector('.js-nested-spawns');

        this.leftBtn = this.el.querySelector('.js-scroll-left');
        this.rightBtn = this.el.querySelector('.js-scroll-right');

        if (this.controlCardEl) {
            this.controlCard = new CNSSpawnControlCardController(this.controlCardEl, this.spawnId, this.el.dataset.spellbookId);
        }

        this.initTrackObservers();
        this.initializeState();
    }

    static populateTemplate(clone, data) {
        const spawnEl = clone.querySelector('.js-cns-spawn');
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

        clone.querySelector('.js-btn-monitor').href = `/central_nervous_system/graph/spawn/${data.id}/?full=True`;
        clone.querySelector('.js-btn-edit').href = `/central_nervous_system/graph/editor/${data.spellbook}/`;
    }

    initTrackObservers() {
        if (!this.trackEl) return;

        // Observe the outer element. When the window resizes, this triggers.
        this.resizeObserver = new ResizeObserver(() => {
            window.requestAnimationFrame(() => this.checkOverflow());
        });
        this.resizeObserver.observe(this.el);

        // Observe the track. When a new card is injected via JS, this triggers.
        this.mutationObserver = new MutationObserver(() => {
            window.requestAnimationFrame(() => this.checkOverflow());
        });
        this.mutationObserver.observe(this.trackEl, {childList: true});

        if (this.leftBtn) this.leftBtn.addEventListener('click', () => this.trackEl.scrollBy({
            left: -300,
            behavior: 'smooth'
        }));
        if (this.rightBtn) this.rightBtn.addEventListener('click', () => this.trackEl.scrollBy({
            left: 300,
            behavior: 'smooth'
        }));

        setTimeout(() => this.checkOverflow(), 100);
    }

    checkOverflow() {
        if (!this.trackEl || !this.leftBtn || !this.rightBtn) return;

        const isShowing = this.leftBtn.style.display === 'flex';
        const scrollW = this.trackEl.scrollWidth;
        const clientW = this.trackEl.clientWidth;

        // MATH: When arrows are visible, the track is compressed by ~60px.
        // We add that back to calculate the "true" available space.
        const availableSpace = isShowing ? (clientW + 60) : clientW;

        const isOverflowing = scrollW > availableSpace;

        if (isOverflowing && !isShowing) {
            this.leftBtn.style.display = 'flex';
            this.rightBtn.style.display = 'flex';
        } else if (!isOverflowing && isShowing) {
            this.leftBtn.style.display = 'none';
            this.rightBtn.style.display = 'none';
        }
    }

    async initializeState() {
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
            const response = await fetch(`/api/v1/heads/?spawn_id=${this.spawnId}`);
            if (!response.ok) return;

            const data = await response.json();
            const heads = data.results || data;

            const myHeads = heads.filter(h => String(h.spawn) === String(this.spawnId) || String(h.spawn_id) === String(this.spawnId));

            for (const headData of myHeads) {
                const existingEl = this.trackEl.querySelector(`.js-cns-head[data-head-id="${headData.id}"]`);

                if (existingEl) {
                    CNSHeadController.populateTemplate({querySelector: (sel) => existingEl.querySelector(sel) || existingEl}, headData);
                } else {
                    const tpl = document.getElementById('tpl-cns-head');
                    const clone = tpl.content.cloneNode(true);
                    CNSHeadController.populateTemplate(clone, headData);
                    this.trackEl.appendChild(clone);
                    // Note: MutationObserver will automatically detect this appendChild and run checkOverflow()
                }
            }
        } catch (error) {
            console.error(`[CNSSpawn ${this.spawnId}] Head sync failed:`, error);
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
                this.syncHeads();
            }
        } catch (error) {
            console.error(`[CNSSpawn] Status fetch failed:`, error);
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

        if (data.nodes) {
            for (const node of Object.values(data.nodes)) {
                if (node.child_spawn_id) {
                    await this.ensureChildSpawnExists(node.child_spawn_id);
                }
            }
        }
    }

    async ensureChildSpawnExists(childSpawnId) {
        if (this.nestedSpawnsEl.querySelector(`.js-cns-spawn-wrapper > .js-cns-spawn[data-spawn-id="${childSpawnId}"]`)) return;

        try {
            const response = await fetch(`/api/v1/spawns/${childSpawnId}/`);
            if (!response.ok) return;
            const spawnData = await response.json();

            const tpl = document.getElementById('tpl-cns-spawn');
            const clone = tpl.content.cloneNode(true);

            CNSSpawnController.populateTemplate(clone, spawnData);
            this.nestedSpawnsEl.appendChild(clone.firstElementChild);

            const newEl = this.nestedSpawnsEl.lastElementChild.querySelector('.js-cns-spawn');
            new CNSSpawnController(newEl);
        } catch (error) {
            console.error(`Failed to inject SubGraph ${childSpawnId}:`, error);
        }
    }
}