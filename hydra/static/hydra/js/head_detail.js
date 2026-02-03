/**
 * Talos Head Detail - Terminal Manager
 */

const cursors = {};

function initTerminal(containerId, title, url, active = true) {
    const container = document.getElementById('terminal-container');
    const id = containerId;
    cursors[id] = 0;

    const wrapper = document.createElement('div');
    wrapper.className = 'term-wrapper';
    wrapper.id = `wrapper-${id}`;

    wrapper.innerHTML = `
        <div class="term-header">
            <span class="term-title">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 17l6-6-6-6M12 19h8"></path></svg>
                ${title}
            </span>
            <div class="term-actions">
                <button class="icon-btn" onclick="copyTerminal('${id}')" title="Copy All">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
                </button>
                <button class="icon-btn" onclick="downloadLog('${id}', '${title}')" title="Download">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
                </button>
            </div>
        </div>
        <div class="term-body" id="term-mount-${id}"></div>
    `;

    container.appendChild(wrapper);

    const term = new Terminal({
        theme: {
            background: '#0d1117',
            foreground: '#c9d1d9',
            cursor: '#58a6ff',
            selection: '#58a6ff33',
            black: '#0d1117',
            red: '#ff7b72',
            green: '#3fb950',
            yellow: '#d29922',
            blue: '#58a6ff',
            magenta: '#bc8cff',
            cyan: '#39c5cf',
            white: '#b1bac4',
            brightBlack: '#484f58',
            brightRed: '#ffa198',
            brightGreen: '#56d364',
            brightYellow: '#e3b341',
            brightBlue: '#79c0ff',
            brightMagenta: '#d2a8ff',
            brightCyan: '#56d4dd',
            brightWhite: '#f0f6fc'
        },
        fontSize: 13,
        fontFamily: 'Menlo, Monaco, "Courier New", monospace',
        cursorBlink: true,
        disableStdin: true,
        convertEol: true,
        scrollback: 5000,
        allowTransparency: true
    });

    const fitAddon = new FitAddon.FitAddon();
    term.loadAddon(fitAddon);

    term.open(document.getElementById(`term-mount-${id}`));
    fitAddon.fit();

    wrapper.termInstance = term;
    wrapper.fullContent = "";

    window.addEventListener('resize', () => fitAddon.fit());

    if (url) {
        term.writeln(`\x1b[1;34m[SYSTEM]\x1b[0m Connecting to ${title}...`);
        startPolling(term, url, id, active, wrapper);
    }
}

function copyTerminal(id) {
    const wrapper = document.getElementById(`wrapper-${id}`);
    if (!wrapper || !wrapper.termInstance) return;

    const term = wrapper.termInstance;
    let text = term.getSelection();

    if (!text) {
        term.selectAll();
        text = term.getSelection();
        term.clearSelection();
    }

    navigator.clipboard.writeText(text);
}

function downloadLog(id, title) {
    const wrapper = document.getElementById(`wrapper-${id}`);
    if (!wrapper || !wrapper.fullContent) {
        alert("No content to download.");
        return;
    }

    const blob = new Blob([wrapper.fullContent], {type: "text/plain"});
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;

    const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
    a.download = `${title.replace(/\s+/g, '_')}_${timestamp}.log`;

    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
}

async function startPolling(term, url, id, active, wrapper) {
    // Initial fetch to populate data immediately
    await fetchAndWrite(term, url, id, wrapper);

    if (active) {
        const pollInterval = setInterval(async () => {
            // 1. Check if Element Removed
            if (!document.getElementById(`wrapper-${id}`)) {
                clearInterval(pollInterval);
                return;
            }

            // 2. SMART STOP: Check the Status Pill
            // This DOM element is updated by HTMX independently.
            // We read its text to determine if we should kill the JS polling loop.
            const statusPill = document.getElementById('head-status-pill');
            if (statusPill) {
                const statusText = statusPill.innerText.trim().toUpperCase();
                const terminalStates = ['SUCCESS', 'FAILED', 'ABORTED', 'STOPPED'];

                if (terminalStates.includes(statusText)) {
                    // One final fetch to ensure we have the tail
                    await fetchAndWrite(term, url, id, wrapper);

                    term.writeln(`\n\x1b[1;30m[SYSTEM] Process finished (${statusText}). Stream closed.\x1b[0m`);
                    clearInterval(pollInterval);
                    return;
                }
            }

            await fetchAndWrite(term, url, id, wrapper);
        }, 1500);
    }
}

async function fetchAndWrite(term, url, id, wrapper) {
    try {
        const response = await fetch(url);
        if (!response.ok) return;

        const fullText = await response.text();
        const currentLen = cursors[id] || 0;

        if (fullText.length > currentLen) {
            const newContent = fullText.substring(currentLen);
            term.write(newContent);
            wrapper.fullContent = fullText;
            cursors[id] = fullText.length;
        } else if (fullText.length === 0 && currentLen === 0) {
            term.write('\x1b[90m[Waiting for output...]\x1b[0m\r');
            cursors[id] = 0;
        }

    } catch (err) {
        term.write(`\n\x1b[31m[CONNECTION ERROR] ${err.message}\x1b[0m`);
    }
}