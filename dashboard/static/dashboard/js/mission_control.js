/**
 * Talos Mission Control - Interactions
 */

// --- LCARS Menu ---
function toggleMenu() {
    const menu = document.getElementById('system-menu');
    if (menu) menu.classList.toggle('open');
}

// --- Frontal Lobe Chat ---
function toggleChat() {
    const chat = document.getElementById('chat-sidebar');
    if (chat) chat.classList.toggle('open');
}

// --- Launch Pad Search ---
function initSearch() {
    const searchInput = document.getElementById('protocol-search');

    if (searchInput) {
        // Remove old listener to prevent duplicates if re-initializing
        // (Note: anonymous functions can't be removed easily, but ensuring
        // this runs once per page load/swap is usually sufficient)

        searchInput.addEventListener('input', (e) => {
            const term = e.target.value.toLowerCase();
            const groups = document.querySelectorAll('.launch-group');
            const ungrouped = document.querySelectorAll('.launch-row.uncategorized');

            // Helper to check and hide/show a row
            const filterRow = (row) => {
                const btn = row.querySelector('.launch-btn');
                const text = btn ? btn.textContent.toLowerCase() : '';

                // Flexible matching
                if (text.includes(term)) {
                    row.style.display = 'flex';
                    return true;
                } else {
                    row.style.display = 'none';
                    return false;
                }
            };

            // 1. Filter Tag Groups
            groups.forEach(group => {
                // FIX: Do not hide the group containing the search input itself
                if (group.contains(searchInput)) return;

                const rows = group.querySelectorAll('.launch-row');
                let hasVisible = false;
                rows.forEach(row => {
                    if (filterRow(row)) hasVisible = true;
                });
                // Hide entire group header if no children match
                group.style.display = hasVisible ? 'block' : 'none';
            });

            // 2. Filter Uncategorized
            ungrouped.forEach(row => filterRow(row));
        });
    }
}

// --- Swimlane Overflow Observer ---
const swimlaneObserver = new ResizeObserver(entries => {
    for (let entry of entries) {
        checkSwimlaneOverflow(entry.target);
    }
});

function checkSwimlaneOverflow(scrollArea) {
    const swimlane = scrollArea.closest('.swimlane');
    if (!swimlane) return;

    // Tolerance of 1px to handle sub-pixel rendering differences
    const hasOverflow = scrollArea.scrollWidth > (scrollArea.clientWidth + 1);

    if (hasOverflow) {
        swimlane.classList.add('has-overflow');
    } else {
        swimlane.classList.remove('has-overflow');
    }
}

function initSwimlaneObservers(contentElement) {
    // Find all scroll areas within the new content (or the whole document)
    const scrollAreas = contentElement.querySelectorAll('.lane-scroll-area');

    scrollAreas.forEach(area => {
        // Initial check
        checkSwimlaneOverflow(area);
        // Observe for resize (window resize or content changes)
        swimlaneObserver.observe(area);
    });
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    // Initialize search if function exists
    if (typeof initSearch === 'function') {
        initSearch();
    }
    initSwimlaneObservers(document.body);
});

// Re-initialize when HTMX swaps content (e.g. swimlane refresh)
if (typeof htmx !== 'undefined') {
    htmx.onLoad(function (content) {
        initSwimlaneObservers(content);
    });
}