class HydraSpawnControlCardController {
    constructor(element) {
        this.el = element;
        this.spawnId = this.el.dataset.spawnId;
        this.spellbookId = this.el.dataset.spellbookId;
        this.csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value || window.djangoContext?.csrfToken;

        this.stopBtn = this.el.querySelector('.stop');
        this.rerunBtn = this.el.querySelector('.rerun');

        this.attachListeners();
    }

    attachListeners() {
        if (this.stopBtn) {
            this.stopBtn.addEventListener('click', () => this.handleStop());
        }
        if (this.rerunBtn) {
            this.rerunBtn.addEventListener('click', () => this.handleRerun());
        }
    }

    async handleStop() {
        if (!confirm("Signal Graceful Stop for this operation?")) return;

        this.stopBtn.style.opacity = '0.5';
        this.stopBtn.style.pointerEvents = 'none';

        try {
            await fetch(`/api/v1/spawns/${this.spawnId}/stop/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.csrfToken
                }
            });
            // The SpawnController will naturally pick up the "STOPPING" state on its next tick
        } catch (error) {
            console.error(`[ControlCard] Stop failed for ${this.spawnId}:`, error);
        }
    }

    async handleRerun() {
        try {
            await fetch(`/hydra/launch/${this.spellbookId}/?no_redirect=true`, {
                method: 'POST',
                headers: {'X-CSRFToken': this.csrfToken}
            });
            // A higher-level Mission Control dispatcher will need to detect the new spawn and inject it.
        } catch (error) {
            console.error(`[ControlCard] Rerun failed for ${this.spellbookId}:`, error);
        }
    }

    // Called by the parent SpawnController to flip UI states
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