// Confirmation dialogs are handled natively by hx-confirm.
// Post-action visual feedback (e.g., dimming the stop button immediately on click)
document.addEventListener('htmx:beforeRequest', function (evt) {
    if (evt.target.classList.contains('stop')) {
        evt.target.style.opacity = '0.5';
        evt.target.style.pointerEvents = 'none';
    }
});