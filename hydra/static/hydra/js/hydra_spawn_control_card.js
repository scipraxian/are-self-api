class HydraSpawnControlCardController {
    constructor(element, spawnId, spellbookId) {
        this.el = element;
        this.spawnId = spawnId;
        this.spellbookId = spellbookId;
        this.csrfToken = window.djangoContext?.csrfToken;

        this.stopBtn = this.el.querySelector('.js-btn-stop');
        this.rerunBtn = this.el.querySelector('.js-btn-rerun');

        this.attachListeners();
    }

    attachListeners() {
        if (this.stopBtn) this.stopBtn.addEventListener('click', () => this.handleStop());
        if (this.rerunBtn) this.rerunBtn.addEventListener('click', () => this.handleRerun());
    }

    async handleStop() {
        if (!confirm("Signal Graceful Stop for this operation?")) return;

        this.stopBtn.style.opacity = '0.5';
        this.stopBtn.style.pointerEvents = 'none';

        try {
            await fetch(`/api/v1/spawns/${this.spawnId}/stop/`, {
                method: 'POST',
                headers: {'X-CSRFToken': this.csrfToken}
            });
        } catch (error) {
            console.error(`Stop failed:`, error);
        }
    }

    async handleRerun() {
        try {
            await fetch(`/hydra/launch/${this.spellbookId}/?no_redirect=true`, {
                method: 'POST',
                headers: {'X-CSRFToken': this.csrfToken}
            });
            // The Root Dispatcher will natively discover the new spawn on its next poll
        } catch (error) {
            console.error(`Rerun failed:`, error);
        }
    }

    setMode(isActive) {
        if (isActive) {
            this.el.classList.add('active-state');
            this.stopBtn.style.display = 'flex';
            this.rerunBtn.style.display = 'none';
        } else {
            this.el.classList.remove('active-state');
            this.stopBtn.style.display = 'none';
            this.rerunBtn.style.display = 'flex';
        }
    }
}