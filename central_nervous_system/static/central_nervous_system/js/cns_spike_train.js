class SpikeTrainController {
    constructor(element) {
        this.el = element;
        this.spikeTrainId = this.el.dataset.spikeTrainId;
        this.isActive = this.el.dataset.isActive === 'true';
        this.pollInterval = null;

        this.statusEl = this.el.querySelector('.js-spike_train-status-text');
        this.controlCardEl = this.el.querySelector('.js-cns-control-card');
        this.trackEl = this.el.querySelector('.js-spike_train-track');
        this.nestedSpawnsEl = this.el.closest('.js-cns-spike_train-wrapper').querySelector('.js-nested-spike_trains');

        this.leftBtn = this.el.querySelector('.js-scroll-left');
        this.rightBtn = this.el.querySelector('.js-scroll-right');

        if (this.controlCardEl) {
            this.controlCard = new SpikeTrainControlCardController(this.controlCardEl, this.spikeTrainId, this.el.dataset.pathwayId);
        }

        this.initTrackObservers();
        this.initializeState();
    }

    static populateTemplate(clone, data) {
        const spikeTrainEl = clone.querySelector('.js-cns-spike_train');
        // FIX: Set correctly for dataset extraction
        spikeTrainEl.dataset.spikeTrainId = data.id;
        spikeTrainEl.dataset.pathwayId = data.pathway;

        const statusStr = data.status_name || data.status_label || 'Pending';
        const isAlive = ['Created', 'Pending', 'Running', 'Stopping'].includes(statusStr);
        spikeTrainEl.dataset.isActive = isAlive ? 'true' : 'false';

        if (isAlive) spikeTrainEl.classList.add('active-lane');
        else if (statusStr === 'Failed' || statusStr === 'Aborted') spikeTrainEl.classList.add('failed-lane');

        clone.querySelector('.js-spike_train-title').textContent = data.pathway_name || 'Unknown Protocol';
        clone.querySelector('.js-spike_train-id').textContent = `#${data.id.substring(0, 8)}`;

        const statusText = clone.querySelector('.js-spike_train-status-text');
        statusText.textContent = statusStr;
        statusText.className = `status-text js-spike_train-status-text status-${statusStr.toLowerCase()}`;

        const timeEl = clone.querySelector('.js-spike_train-time');
        if (timeEl && data.modified) timeEl.textContent = `${timeSince(data.modified)} ago`;

        clone.querySelector('.js-btn-monitor').href = `/central_nervous_system/graph/spike_train/${data.id}/?full=True`;
        clone.querySelector('.js-btn-edit').href = `/central_nervous_system/graph/editor/${data.pathway}/`;
    }

    initTrackObservers() {
        if (!this.trackEl) return;

        this.resizeObserver = new ResizeObserver(() => {
            window.requestAnimationFrame(() => this.checkOverflow());
        });
        this.resizeObserver.observe(this.el);

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
        await this.syncSpikes();
        await this.fetchState();
        if (this.isActive) this.startPolling();
    }

    startPolling() {
        this.pollInterval = setInterval(() => {
            this.syncSpikes();
            this.fetchState();
        }, 1500);
    }

    stopPolling() {
        if (this.pollInterval) {
            clearInterval(this.pollInterval);
            this.pollInterval = null;
        }
    }

    async syncSpikes() {
        try {
            const response = await fetch(`/api/v1/spikes/?spike_train_id=${this.spikeTrainId}`);
            if (!response.ok) return;

            const data = await response.json();
            const spikes = data.results || data;

            const mySpikes = spikes.filter(h => String(h.spike_train) === String(this.spikeTrainId));

            for (const spikeData of mySpikes) {
                // FIX: Use standard data-spike-id
                const existingEl = this.trackEl.querySelector(`.js-cns-spike[data-spike-id="${spikeData.id}"]`);

                if (existingEl) {
                    SpikeController.populateTemplate({querySelector: (sel) => existingEl.querySelector(sel) || existingEl}, spikeData);
                } else {
                    const tpl = document.getElementById('tpl-cns-spike');
                    const clone = tpl.content.cloneNode(true);
                    SpikeController.populateTemplate(clone, spikeData);
                    this.trackEl.appendChild(clone);
                }
            }
        } catch (error) {
            console.error(`[SpikeTrain ${this.spikeTrainId}] Spike sync failed:`, error);
        }
    }

    async fetchState() {
        try {
            const response = await fetch(`/api/v1/spike_trains/${this.spikeTrainId}/live_status/`);
            if (!response.ok) return;
            const data = await response.json();

            await this.updateDOM(data);

            if (!data.is_active) {
                this.stopPolling();
                this.el.dataset.isActive = 'false';
                this.syncSpikes();
            }
        } catch (error) {
            console.error(`[SpikeTrain] Status fetch failed:`, error);
        }
    }

    async updateDOM(data) {
        const statusStr = data.status_label || data.status_name || 'Pending';

        if (this.statusEl) {
            this.statusEl.textContent = statusStr;
            this.statusEl.className = `status-text js-spike_train-status-text status-${statusStr.toLowerCase()}`;
        }

        this.el.classList.remove('active-lane', 'failed-lane');
        if (data.is_active) this.el.classList.add('active-lane');
        else if (statusStr === 'Failed' || statusStr === 'Aborted') this.el.classList.add('failed-lane');

        if (this.controlCard) this.controlCard.setMode(data.is_active);

        if (data.neurons) {
            for (const node of Object.values(data.neurons)) {
                if (node.child_spike_train_id) {
                    await this.ensureChildSpikeTrainExists(node.child_spike_train_id);
                }
            }
        }
    }

    async ensureChildSpikeTrainExists(childSpikeTrainId) {
        // FIX: Match standard html selector
        if (this.nestedSpawnsEl.querySelector(`.js-cns-spike_train-wrapper > .js-cns-spike_train[data-spike-train-id="${childSpikeTrainId}"]`)) return;

        try {
            const response = await fetch(`/api/v1/spike_trains/${childSpikeTrainId}/`);
            if (!response.ok) return;
            const spikeTrainData = await response.json();

            const tpl = document.getElementById('tpl-cns-spike_train');
            const clone = tpl.content.cloneNode(true);

            SpikeTrainController.populateTemplate(clone, spikeTrainData);
            this.nestedSpawnsEl.appendChild(clone.firstElementChild);

            const newEl = this.nestedSpawnsEl.lastElementChild.querySelector('.js-cns-spike_train');
            new SpikeTrainController(newEl);
        } catch (error) {
            console.error(`Failed to inject SubGraph ${childSpikeTrainId}:`, error);
        }
    }
}