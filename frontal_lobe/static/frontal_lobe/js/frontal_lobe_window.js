function scrollToBottom() {
    const feed = document.getElementById('cortex-feed');
    if (feed) {
        // Only auto-scroll if user was already near the bottom
        // or just brute force it for the "Situation Room" feel
        feed.scrollTop = feed.scrollHeight;
    }
}

// Initial scroll
document.addEventListener('DOMContentLoaded', scrollToBottom);