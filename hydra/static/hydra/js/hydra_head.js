// Minimal JS footprint. HTMX handles the lifecycle.
// Reserved for future WebSocket initialization or micro-animations.
document.addEventListener('htmx:afterSettle', function (evt) {
    if (evt.target.classList.contains('hydra-head-card')) {
        // e.g., trigger a flash animation on log update
    }
});