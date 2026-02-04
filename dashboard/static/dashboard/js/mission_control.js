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
document.addEventListener('DOMContentLoaded', () => {
    const searchInput = document.getElementById('protocol-search');

    if (searchInput) {
        searchInput.addEventListener('input', (e) => {
            const term = e.target.value.toLowerCase();
            const groups = document.querySelectorAll('.launch-group');
            const ungrouped = document.querySelectorAll('.launch-row.uncategorized');

            // Helper to check and hide/show a row
            const filterRow = (row) => {
                const btn = row.querySelector('.launch-btn');
                const text = btn ? btn.textContent.toLowerCase() : '';
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
});