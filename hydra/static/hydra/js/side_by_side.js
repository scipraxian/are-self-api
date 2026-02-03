// Counter for unique IDs
let termCount = 0;
// Track read offsets for each terminal to allow "streaming" effect
const cursors = {};

/**
 * Creates a new Terminal instance and adds it to the DOM
 */
function addTerminal(title, url, active = true) {
    termCount++;
    const id = termCount;
    cursors[id] = 0;

    const container = document.getElementById('terminal-container');
    const sourceName = title || `Stream #${id}`;

    // 1. Create Wrapper
    const wrapper = document.createElement('div');
    wrapper.className = 'term-wrapper';
    wrapper.id = `wrapper-${id}`;

    // Flex styling to ensure it takes width in the flex-row container
    wrapper.style.flex = "1";
    wrapper.style.minWidth = "400px";
    wrapper.style.maxWidth = "50%"; // Default split for 2 windows

    wrapper.innerHTML = `
        <div class="term-header">
            <span><strong>${sourceName}</strong></span>
            <div style="display:flex; gap: 5px;">
                <button class="action-btn" onclick="copyTerminal(${id})" title="Copy">Copy</button>
                <button class="remove" onclick="removeTerminal(${id})" title="Close">X</button>
            </div>
        </div>
        <div class="term-body" id="term-${id}" style="flex:1; background: #000;"></div>
    `;

    container.appendChild(wrapper);

    // 2. Initialize Xterm.js
    const term = new Terminal({
        theme: {
            background: '#1e1e1e',
            foreground: '#d4d4d4',
            cursor: '#ffffff'
        },
        fontSize: 13,
        fontFamily: 'Consolas, "Courier New", monospace',
        cursorBlink: true,
        disableStdin: true,
        convertEol: true
    });

    const fitAddon = new FitAddon.FitAddon();
    term.loadAddon(fitAddon);

    term.open(document.getElementById(`term-${id}`));
    fitAddon.fit();

    wrapper.termInstance = term;

    // Handle Window Resize
    window.addEventListener('resize', () => fitAddon.fit());

    if (url) {
        term.writeln(`\x1b[1;30m[SYSTEM] Initializing connection to ${sourceName}...\x1b[0m`);
        startPolling(term, url, id, active);
    } else {
        term.writeln(`\x1b[1;33m[SYSTEM] Ready (No Source)\x1b[0m`);
    }
}

function removeTerminal(id) {
    const wrapper = document.getElementById(`wrapper-${id}`);
    if (wrapper) wrapper.remove();
    delete cursors[id];
}

function copyTerminal(id) {
    const wrapper = document.getElementById(`wrapper-${id}`);
    if (!wrapper || !wrapper.termInstance) return;
    wrapper.termInstance.selectAll();
    const text = wrapper.termInstance.getSelection();
    wrapper.termInstance.clearSelection();

    navigator.clipboard.writeText(text);
}

async function startPolling(term, url, id, active) {
    // Initial Fetch
    await fetchAndWrite(term, url, id);

    if (active) {
        const pollInterval = setInterval(async () => {
            if (!document.getElementById(`wrapper-${id}`)) {
                clearInterval(pollInterval);
                return;
            }
            await fetchAndWrite(term, url, id);
        }, 1000);
    }
}

async function fetchAndWrite(term, url, id) {
    try {
        const response = await fetch(url);
        if (!response.ok) return;

        const fullText = await response.text();
        const currentLen = cursors[id] || 0;

        if (fullText.length > currentLen) {
            const newContent = fullText.substring(currentLen);
            term.write(newContent);
            cursors[id] = fullText.length;
        } else if (fullText.length === 0 && currentLen === 0) {
            // Only show waiting on first empty check
            term.write('\x1b[2m[Waiting for output...]\x1b[0m\r');
            cursors[id] = 0; // Don't advance, overwrite this line next time
        }

    } catch (err) {
        term.writeln(`\n\x1b[1;31m[CONNECTION ERROR]\x1b[0m ${err.message}`);
    }
}