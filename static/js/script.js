/* ====================================================
   PyCOBOL Lexical Analyzer — Frontend Logic
   ==================================================== */

// Global state
let currentData = null;
let allTokens = [];

// ── Color mapping for token distribution bars ──
const TOKEN_COLORS = {
    COBOL_KEYWORD:   '#4c8dff',
    COBOL_DIVISION:  '#a855f7',
    COBOL_SECTION:   '#c084fc',
    PYTHON_KEYWORD:  '#f59e0b',
    IDENTIFIER:      '#06b6d4',
    STRING_LITERAL:  '#22c55e',
    INTEGER:         '#ec4899',
    FLOAT:           '#ec4899',
    OPERATOR:        '#ef4444',
    PUNCTUATION:     '#6b6e85',
    COMMENT:         '#7a7d95',
    PICTURE_CLAUSE:  '#7aabff',
};

// ── Initialize ──────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
    const editor = document.getElementById('sourceCode');
    const fileSelect = document.getElementById('testFileSelect');

    // Update line numbers on input
    editor.addEventListener('input', updateLineNumbers);
    editor.addEventListener('scroll', syncScroll);
    updateLineNumbers();

    // Load file on select
    fileSelect.addEventListener('change', () => {
        if (fileSelect.value) loadTestFile(fileSelect.value);
    });

    // Ctrl+Enter to analyze
    editor.addEventListener('keydown', (e) => {
        if (e.ctrlKey && e.key === 'Enter') {
            e.preventDefault();
            analyzeCode();
        }
    });
});


// ── Line Numbers ────────────────────────────

function updateLineNumbers() {
    const editor = document.getElementById('sourceCode');
    const lineNums = document.getElementById('lineNumbers');
    const lineCount = document.getElementById('lineCount');

    const lines = editor.value.split('\n');
    const count = lines.length;

    lineNums.innerHTML = lines.map((_, i) => `<div>${i + 1}</div>`).join('');
    lineCount.textContent = `${count} line${count !== 1 ? 's' : ''}`;
}

function syncScroll() {
    const editor = document.getElementById('sourceCode');
    const lineNums = document.getElementById('lineNumbers');
    lineNums.scrollTop = editor.scrollTop;
}


// ── Load Test File ──────────────────────────

async function loadTestFile(filename) {
    try {
        const res = await fetch('/load_file', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ filename }),
        });
        const data = await res.json();

        if (data.error) {
            alert(data.error);
            return;
        }

        document.getElementById('sourceCode').value = data.content;
        updateLineNumbers();
    } catch (err) {
        alert('Failed to load file: ' + err.message);
    }
}


// ── Analyze Code ────────────────────────────

async function analyzeCode() {
    const source = document.getElementById('sourceCode').value;
    if (!source.trim()) {
        alert('Please enter some source code first!');
        return;
    }

    // Show loading
    document.getElementById('loadingOverlay').classList.remove('hidden');

    try {
        const res = await fetch('/analyze', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ source_code: source }),
        });
        const data = await res.json();

        if (data.error) {
            alert(data.error);
            return;
        }

        currentData = data;
        allTokens = data.tokens;
        renderDashboard(data);
        renderTokenTable(data.tokens);
        renderSymbolTable(data.symbols);
        renderErrors(data.errors);
        populateTokenFilter(data.analysis.summary);

        // Show dashboard
        document.getElementById('welcomeState').classList.add('hidden');
        document.getElementById('dashboardContent').classList.remove('hidden');
        switchTab('dashboard');

    } catch (err) {
        alert('Analysis failed: ' + err.message);
    } finally {
        document.getElementById('loadingOverlay').classList.add('hidden');
    }
}


// ── Dashboard ───────────────────────────────

function renderDashboard(data) {
    const a = data.analysis;

    // Stats cards
    animateValue('statLines', a.total_lines);
    animateValue('statTokens', a.total_tokens);
    animateValue('statSymbols', a.total_symbols);
    animateValue('statErrors', a.total_errors);

    // Error card styling
    const errorCard = document.getElementById('statErrorCard');
    if (a.total_errors > 0) {
        errorCard.classList.add('has-errors');
    } else {
        errorCard.classList.remove('has-errors');
    }

    // Error badge in tab
    const errorBadge = document.getElementById('errorBadge');
    if (a.total_errors > 0) {
        errorBadge.textContent = a.total_errors;
        errorBadge.classList.remove('hidden');
    } else {
        errorBadge.classList.add('hidden');
    }

    // Hybrid score
    setTimeout(() => {
        const cobolBar = document.getElementById('hybridCobol');
        const pythonBar = document.getElementById('hybridPython');

        cobolBar.style.width = a.cobol_pct + '%';
        pythonBar.style.width = a.python_pct + '%';

        if (a.cobol_pct > 15) cobolBar.textContent = a.cobol_pct + '%';
        else cobolBar.textContent = '';
        if (a.python_pct > 15) pythonBar.textContent = a.python_pct + '%';
        else pythonBar.textContent = '';

        document.getElementById('cobolPct').textContent = a.cobol_pct + '%';
        document.getElementById('pythonPct').textContent = a.python_pct + '%';
    }, 100);

    // Token distribution
    renderDistribution(a.summary, a.total_tokens);
}

function animateValue(elementId, target) {
    const el = document.getElementById(elementId);
    const duration = 600;
    const start = parseInt(el.textContent) || 0;
    const startTime = performance.now();

    function update(currentTime) {
        const elapsed = currentTime - startTime;
        const progress = Math.min(elapsed / duration, 1);
        const eased = 1 - Math.pow(1 - progress, 3);
        el.textContent = Math.round(start + (target - start) * eased);
        if (progress < 1) requestAnimationFrame(update);
    }
    requestAnimationFrame(update);
}

function renderDistribution(summary, total) {
    const container = document.getElementById('tokenDistribution');
    container.innerHTML = '';

    const sorted = Object.entries(summary).sort((a, b) => b[1] - a[1]);
    const maxCount = sorted.length > 0 ? sorted[0][1] : 1;

    sorted.forEach(([type, count], index) => {
        const pct = total > 0 ? ((count / total) * 100).toFixed(1) : 0;
        const barPct = ((count / maxCount) * 100).toFixed(1);
        const color = TOKEN_COLORS[type] || '#6b6e85';

        const row = document.createElement('div');
        row.className = 'dist-row';
        row.style.animation = `slideIn 0.3s ease ${index * 0.04}s both`;
        row.innerHTML = `
            <div class="dist-label">${type}</div>
            <div class="dist-bar-bg">
                <div class="dist-bar-fill" style="width: 0%; background: ${color};"></div>
            </div>
            <div class="dist-count">${count} (${pct}%)</div>
        `;
        container.appendChild(row);

        // Animate bar
        setTimeout(() => {
            row.querySelector('.dist-bar-fill').style.width = barPct + '%';
        }, 150 + index * 40);
    });
}


// ── Token Table ─────────────────────────────

function renderTokenTable(tokens) {
    const tbody = document.getElementById('tokenTableBody');
    const countEl = document.getElementById('tokenCount');
    countEl.textContent = `${tokens.length} tokens`;

    tbody.innerHTML = tokens.map((tok, i) => `
        <tr>
            <td>${i + 1}</td>
            <td><span class="token-badge ${tok.type}">${tok.type}</span></td>
            <td class="token-value">${escapeHtml(tok.value)}</td>
            <td class="line-col">${tok.line}</td>
            <td class="line-col">${tok.column}</td>
        </tr>
    `).join('');
}

function populateTokenFilter(summary) {
    const select = document.getElementById('tokenFilter');
    const currentVal = select.value;
    select.innerHTML = '<option value="">All Types</option>';
    Object.keys(summary).sort().forEach(type => {
        select.innerHTML += `<option value="${type}">${type} (${summary[type]})</option>`;
    });
    select.value = currentVal;
}

function filterTokens() {
    const search = document.getElementById('tokenSearch').value.toLowerCase();
    const typeFilter = document.getElementById('tokenFilter').value;

    let filtered = allTokens;
    if (typeFilter) filtered = filtered.filter(t => t.type === typeFilter);
    if (search) filtered = filtered.filter(t =>
        t.value.toLowerCase().includes(search) ||
        t.type.toLowerCase().includes(search)
    );

    renderTokenTable(filtered);
}


// ── Symbol Table ────────────────────────────

function renderSymbolTable(symbols) {
    const tbody = document.getElementById('symbolTableBody');
    const countEl = document.getElementById('symbolCount');
    countEl.textContent = `${symbols.length} symbols`;

    if (symbols.length === 0) {
        tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; color: var(--text-muted); padding: 30px;">No symbols found</td></tr>`;
        return;
    }

    tbody.innerHTML = symbols.map((sym, i) => `
        <tr>
            <td>${i + 1}</td>
            <td class="token-value">${escapeHtml(sym.name)}</td>
            <td><span class="symbol-badge ${sym.entry_type}">${sym.entry_type}</span></td>
            <td style="font-family: var(--font-mono); font-size: 12px;">${escapeHtml(sym.data_type)}</td>
            <td class="token-value">${escapeHtml(truncate(sym.value, 20))}</td>
            <td style="font-size: 12px; color: var(--text-muted);">${sym.scope}</td>
            <td class="line-col">${sym.line}</td>
        </tr>
    `).join('');
}


// ── Errors ──────────────────────────────────

function renderErrors(errors) {
    const noErrors = document.getElementById('noErrors');
    const errorList = document.getElementById('errorList');

    if (errors.length === 0) {
        noErrors.classList.remove('hidden');
        errorList.classList.add('hidden');
        return;
    }

    noErrors.classList.add('hidden');
    errorList.classList.remove('hidden');

    errorList.innerHTML = errors.map((err, i) => `
        <div class="error-card" style="animation-delay: ${i * 0.08}s">
            <div class="error-card-header">
                <span class="error-type-badge">${err.type}</span>
                <span class="error-location">Line ${err.line}, Col ${err.column}</span>
            </div>
            <div class="error-message">${escapeHtml(err.message)}</div>
            <code class="error-fragment">${escapeHtml(err.fragment)}</code>
        </div>
    `).join('');
}


// ── Tabs ────────────────────────────────────

function switchTab(tabName) {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));

    document.querySelector(`[data-tab="${tabName}"]`).classList.add('active');
    document.getElementById(`tab-${tabName}`).classList.add('active');
}


// ── Clear ───────────────────────────────────

function clearAll() {
    document.getElementById('sourceCode').value = '';
    document.getElementById('testFileSelect').value = '';
    document.getElementById('welcomeState').classList.remove('hidden');
    document.getElementById('dashboardContent').classList.add('hidden');
    document.getElementById('tokenTableBody').innerHTML = '';
    document.getElementById('symbolTableBody').innerHTML = '';
    document.getElementById('errorList').innerHTML = '';
    document.getElementById('errorBadge').classList.add('hidden');
    document.getElementById('noErrors').classList.remove('hidden');
    document.getElementById('errorList').classList.add('hidden');
    document.getElementById('tokenCount').textContent = '0 tokens';
    document.getElementById('symbolCount').textContent = '0 symbols';
    currentData = null;
    allTokens = [];
    updateLineNumbers();
    switchTab('dashboard');
}


// ── Utilities ───────────────────────────────

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function truncate(str, maxLen) {
    if (str.length <= maxLen) return str;
    return str.substring(0, maxLen) + '..';
}
