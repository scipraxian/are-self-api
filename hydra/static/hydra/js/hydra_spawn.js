// Localized UI logic. No state fetching required.
class SpawnTrackManager {
    constructor() {
        this.observer = new ResizeObserver(entries => {
            for (let entry of entries) {
                this.checkOverflow(entry.target);
            }
        });
    }

    checkOverflow(track) {
        const wrapper = track.closest('.hydra-spawn');
        if (!wrapper) return;

        const hasOverflow = track.scrollWidth > (track.clientWidth + 1);
        const btns = wrapper.querySelectorAll('.scroll-btn');

        btns.forEach(btn => {
            btn.style.display = hasOverflow ? 'flex' : 'none';
        });
    }

    observe(container = document) {
        const tracks = container.querySelectorAll('.spawn-track');
        tracks.forEach(track => {
            this.checkOverflow(track);
            this.observer.observe(track);
        });
    }
}

const trackManager = new SpawnTrackManager();
document.addEventListener('DOMContentLoaded', () => trackManager.observe());
document.addEventListener('htmx:afterSettle', (e) => trackManager.observe(e.target));