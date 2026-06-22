// Mark Attendance Page — supervisor-driven flow
//
// Flow: pick a supervisor -> add workers one at a time (worker + work +
// project + P/A + OT) -> they collect in a list -> Finish Attendance commits
// everything. The worker's role is its fixed designation (shown beside the
// name in the picker and editable only on the worker's edit page); only work
// is elastic and chosen per entry.
// Marking targets today by default, with a one-day buffer (Today/Yesterday
// toggle) so late-reported OT can be recorded; the backend rejects older dates.

let supervisors = [];
let selectedSupervisorId = null;
let allWorkers = [];                  // from /api/labours
let projectsList = [];                // [{id, value}] from the live VISMA registry
let projectValues = new Set();        // canonical "{id} - {stem_name}" strings, for validation
let projectRegistryError = null;      // message when the registry DB is unreachable
let projectRegistryStale = false;     // true when serving a cached (not live) list
let comboActiveIndex = -1;            // highlighted option in the open list
let markedWorkerIds = new Set();      // workers marked on the selected day by ANY supervisor
let initialPersistedIds = new Set();  // workers this supervisor already had saved for the selected day
let entries = [];                     // working list: {worker_id, name, role, work, project, status, ot_hours}
let entryStatus = null;               // 'P' | 'A' currently chosen in the entry form
let markDateStr = '';                 // the day being marked (today or yesterday)

document.addEventListener('DOMContentLoaded', async function () {
    markDateStr = isoForDaysAgo(0);
    updateMarkDateLabel(0);

    document.querySelectorAll('#markDayToggle .day-btn').forEach(btn => {
        btn.addEventListener('click', () => onMarkDayChange(btn));
    });

    await Promise.all([loadSupervisors(), loadWorkers(), loadProjects()]);

    document.getElementById('supervisorSelect').addEventListener('change', onSupervisorChange);
    document.getElementById('addSupervisorBtn').addEventListener('click', openSupervisorModal);
    document.getElementById('supervisorForm').addEventListener('submit', addSupervisor);
    document.getElementById('addEntryBtn').addEventListener('click', addEntry);
    document.getElementById('finishBtn').addEventListener('click', finishAttendance);
    initProjectCombo();

    // Present / Absent toggle
    document.querySelectorAll('#entryStatusToggle .status-btn').forEach(btn => {
        btn.addEventListener('click', function () {
            document.querySelectorAll('#entryStatusToggle .status-btn').forEach(b => b.classList.remove('active'));
            this.classList.add('active');
            entryStatus = this.dataset.status;
        });
    });

    // Add Labour (existing worker management)
    document.getElementById('addLabourBtn').addEventListener('click', () => {
        document.getElementById('addModal').style.display = 'flex';
    });
    document.getElementById('addLabourForm').addEventListener('submit', addNewLabour);

    document.getElementById('supervisorModal').addEventListener('click', function (e) {
        if (e.target === this) closeSupervisorModal();
    });
});

// Today's IST calendar date as a Date anchored at local midnight, regardless of
// the browser's actual timezone. Attendance is always reckoned in IST (the
// backend agrees), so day math here must not drift with the viewer's locale.
// Only the date matters for marking, so we don't carry a time component.
function istNow() {
    // en-CA formats as YYYY-MM-DD for the requested zone.
    const ymd = new Intl.DateTimeFormat('en-CA', {
        timeZone: 'Asia/Kolkata',
        year: 'numeric', month: '2-digit', day: '2-digit',
    }).format(new Date());
    return new Date(`${ymd}T00:00:00`);
}

// Date string (YYYY-MM-DD) for `n` days ago in IST, matching how the rest of the
// app derives "today" so today/yesterday stay consistent with each other.
function isoForDaysAgo(n) {
    const d = istNow();
    d.setDate(d.getDate() - n);
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
}

function updateMarkDateLabel(offset) {
    const d = istNow();
    d.setDate(d.getDate() - offset);
    const days = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    const prefix = offset === 0 ? 'Today' : 'Yesterday';
    const label = document.getElementById('markDateLabel');
    if (label) label.textContent = `${prefix} — ${days[d.getDay()]}, ${d.getDate()} ${months[d.getMonth()]}`;
}

async function onMarkDayChange(btn) {
    document.querySelectorAll('#markDayToggle .day-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');

    const offset = parseInt(btn.dataset.offset) || 0;
    markDateStr = isoForDaysAgo(offset);
    updateMarkDateLabel(offset);

    // Re-sync the roster/entries for the newly selected day.
    if (selectedSupervisorId) {
        await loadRoster();
        resetEntryForm();
    }
}

// ============================================
// DATA LOADING
// ============================================

async function loadSupervisors() {
    try {
        const res = await fetch('/api/supervisors');
        supervisors = await res.json();
    } catch (e) {
        supervisors = [];
        console.error('Failed to load supervisors:', e);
    }
    populateSupervisorSelect();
}

async function loadWorkers() {
    try {
        const res = await fetch('/api/labours');
        allWorkers = await res.json();
    } catch (e) {
        allWorkers = [];
        console.error('Failed to load workers:', e);
    }
}

// Load the selectable projects live from the shared VISMA registry. On failure
// we surface a clear error (and keep whatever was last loaded) — we never fall
// back to free text.
async function loadProjects() {
    try {
        const res = await fetch('/api/projects/registry');
        const data = await res.json().catch(() => ({}));

        if (res.ok) {
            projectsList = Array.isArray(data.projects) ? data.projects : [];
            projectValues = new Set(projectsList.map(p => p.value));
            projectRegistryStale = !!data.stale;
            projectRegistryError = null;
        } else {
            // 503 with no cache available: registry truly unreachable.
            projectRegistryError = data.error || 'Project registry unavailable.';
            if (!projectsList.length) projectValues = new Set();
        }
    } catch (e) {
        projectRegistryError = 'Could not reach the project registry.';
        console.error('Failed to load projects:', e);
    }
    updateProjectComboState();
}

function populateSupervisorSelect() {
    const sel = document.getElementById('supervisorSelect');
    const current = selectedSupervisorId;
    sel.innerHTML = '<option value="">-- Select supervisor --</option>' +
        supervisors.map(s => `<option value="${s.id}">${escapeHtml(s.name)}</option>`).join('');
    if (current && supervisors.some(s => s.id === current)) {
        sel.value = current;
    }
}

// ============================================
// SUPERVISOR SELECTION + ROSTER
// ============================================

async function onSupervisorChange() {
    const sel = document.getElementById('supervisorSelect');
    selectedSupervisorId = sel.value ? parseInt(sel.value) : null;
    const component = document.getElementById('markComponent');

    if (!selectedSupervisorId) {
        component.style.display = 'none';
        entries = [];
        return;
    }

    component.style.display = 'block';
    await loadRoster();
    resetEntryForm();
}

async function loadRoster() {
    try {
        const res = await fetch(`/api/attendance/day-roster/${markDateStr}?supervisor_id=${selectedSupervisorId}`);
        const data = await res.json();

        markedWorkerIds = new Set(data.marked_worker_ids || []);
        entries = (data.marked_by_supervisor || []).map(r => ({
            worker_id: r.worker_id,
            name: r.name,
            role: r.role || '',
            work: r.work || '',
            project: r.project || '',
            status: r.status === 'P' ? 'P' : 'A',
            ot_hours: r.ot_hours || 0
        }));
        initialPersistedIds = new Set(entries.map(e => e.worker_id));

        populateWorkerSelect();
        updateProjectComboState();
        renderEntries();
    } catch (e) {
        console.error('Failed to load roster:', e);
    }
}

function populateWorkerSelect() {
    const sel = document.getElementById('entryWorker');
    // Exclude workers marked on the selected day by anyone, plus anyone already in the list.
    const excluded = new Set(markedWorkerIds);
    entries.forEach(e => excluded.add(e.worker_id));

    const available = allWorkers.filter(w => !excluded.has(w.worker_id));
    // Show the worker's fixed designation next to the name so two workers who
    // share a name can be told apart. The designation IS the role — there is no
    // separate role choice. It's a fixed property of the worker (editable only
    // on the worker's edit page). data-name carries the plain name and
    // data-designation the role, both copied into the saved entry on Add.
    sel.innerHTML = '<option value="">-- Select worker --</option>' +
        available.map(w => {
            const label = w.designation
                ? `${escapeHtml(w.name)} — ${escapeHtml(w.designation)}`
                : escapeHtml(w.name);
            return `<option value="${w.worker_id}" data-name="${escapeHtml(w.name)}" `
                + `data-designation="${escapeHtml(w.designation || '')}">${label}</option>`;
        }).join('');
}

// ============================================
// PROJECT COMBOBOX (searchable, selection-only)
//
// A text input filters the live registry list; a value is only committed by
// picking a list item (click / Enter). The hidden #entryProject holds the
// canonical "{id} - {stem_name}" string. Typing never stores free text.
// ============================================

function initProjectCombo() {
    const search = document.getElementById('projectSearch');
    const combo = document.getElementById('projectCombo');

    // Note element for stale / unavailable messages.
    const note = document.createElement('div');
    note.id = 'projectComboNote';
    note.className = 'combo-note';
    note.style.display = 'none';
    combo.appendChild(note);

    search.addEventListener('focus', () => openProjectList());
    search.addEventListener('input', () => {
        // Any edit invalidates a prior selection until a list item is chosen.
        setProjectValue('');
        openProjectList();
    });
    search.addEventListener('keydown', onProjectComboKeydown);

    // Delegated selection — mousedown fires before the input's blur so the
    // pick lands before the list would otherwise close.
    document.getElementById('projectComboList').addEventListener('mousedown', (e) => {
        const opt = e.target.closest('.combo-option');
        if (!opt) return;
        e.preventDefault();
        selectProject(opt.dataset.value);
    });

    // Close when clicking outside the combo.
    document.addEventListener('click', (e) => {
        if (!combo.contains(e.target)) closeProjectList(true);
    });

    updateProjectComboState();
}

// Reflect registry availability in the combo: disable + message when the
// registry is unreachable with nothing cached; subtle note when stale.
function updateProjectComboState() {
    const search = document.getElementById('projectSearch');
    const note = document.getElementById('projectComboNote');
    if (!search || !note) return;

    const unavailable = !!projectRegistryError && projectsList.length === 0;

    search.disabled = unavailable;
    search.placeholder = unavailable ? 'Project registry unavailable' : '-- Select project --';

    if (unavailable) {
        note.textContent = projectRegistryError;
        note.className = 'combo-note error';
        note.style.display = 'block';
    } else if (projectRegistryError) {
        note.textContent = 'Registry unreachable — showing last cached list.';
        note.className = 'combo-note error';
        note.style.display = 'block';
    } else if (projectRegistryStale) {
        note.textContent = 'Showing cached project list.';
        note.className = 'combo-note';
        note.style.display = 'block';
    } else {
        note.style.display = 'none';
    }
}

function openProjectList() {
    if (document.getElementById('projectSearch').disabled) return;
    renderProjectOptions();
    document.getElementById('projectComboList').style.display = 'block';
    document.getElementById('projectSearch').setAttribute('aria-expanded', 'true');
}

// resetText: when true, snap the search box back to the selected value (or
// blank) so a half-typed, uncommitted query never lingers on screen.
function closeProjectList(resetText) {
    const list = document.getElementById('projectComboList');
    list.style.display = 'none';
    comboActiveIndex = -1;
    document.getElementById('projectSearch').setAttribute('aria-expanded', 'false');
    if (resetText) {
        const selected = document.getElementById('entryProject').value;
        document.getElementById('projectSearch').value = selected;
    }
}

function filteredProjects() {
    const q = document.getElementById('projectSearch').value.trim().toLowerCase();
    if (!q) return projectsList;
    return projectsList.filter(p => p.value.toLowerCase().includes(q));
}

function renderProjectOptions() {
    const list = document.getElementById('projectComboList');
    const matches = filteredProjects();
    comboActiveIndex = -1;

    if (projectRegistryError && projectsList.length === 0) {
        list.innerHTML = `<div class="combo-empty error">${escapeHtml(projectRegistryError)}</div>`;
        return;
    }
    if (matches.length === 0) {
        list.innerHTML = '<div class="combo-empty">No matching projects.</div>';
        return;
    }

    list.innerHTML = matches.map((p, i) =>
        `<div class="combo-option" role="option" data-value="${escapeAttr(p.value)}" data-index="${i}">${escapeHtml(p.value)}</div>`
    ).join('');
}

function selectProject(value) {
    setProjectValue(value);
    document.getElementById('projectSearch').value = value;
    closeProjectList(false);
}

// Single source of truth for the committed value (the hidden input).
function setProjectValue(value) {
    document.getElementById('entryProject').value = value || '';
    document.getElementById('projectCombo').classList.remove('is-invalid');
}

function onProjectComboKeydown(e) {
    const list = document.getElementById('projectComboList');
    if (list.style.display === 'none' && ['ArrowDown', 'ArrowUp'].includes(e.key)) {
        openProjectList();
        return;
    }
    const options = Array.from(list.querySelectorAll('.combo-option'));

    if (e.key === 'ArrowDown') {
        e.preventDefault();
        comboActiveIndex = Math.min(comboActiveIndex + 1, options.length - 1);
        highlightActiveOption(options);
    } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        comboActiveIndex = Math.max(comboActiveIndex - 1, 0);
        highlightActiveOption(options);
    } else if (e.key === 'Enter') {
        if (comboActiveIndex >= 0 && options[comboActiveIndex]) {
            e.preventDefault();
            selectProject(options[comboActiveIndex].dataset.value);
        }
    } else if (e.key === 'Escape') {
        closeProjectList(true);
    }
}

function highlightActiveOption(options) {
    options.forEach((o, i) => o.classList.toggle('active', i === comboActiveIndex));
    if (options[comboActiveIndex]) {
        options[comboActiveIndex].scrollIntoView({ block: 'nearest' });
    }
}

function escapeAttr(str) {
    return String(str).replace(/&/g, '&amp;').replace(/"/g, '&quot;');
}

// ============================================
// ENTRY LIST
// ============================================

function addEntry() {
    const wSel = document.getElementById('entryWorker');
    const workerId = wSel.value ? parseInt(wSel.value) : null;
    const work = document.getElementById('entryWork').value;
    const project = document.getElementById('entryProject').value;
    const projectSearch = document.getElementById('projectSearch').value.trim();
    let ot = parseFloat(document.getElementById('entryOT').value) || 0;
    ot = Math.min(8, Math.max(0, ot));

    if (!workerId) { showMessage('Please choose a worker.', 'error'); return; }
    if (!work) { showMessage('Please choose the work done.', 'error'); return; }
    if (!entryStatus) { showMessage('Please mark Present (P) or Absent (A).', 'error'); return; }
    // A typed-but-not-selected query is not allowed — it would otherwise be
    // silently dropped. Force the user to pick from the list.
    if (!project && projectSearch) {
        document.getElementById('projectCombo').classList.add('is-invalid');
        showMessage('Please select a project from the list.', 'error');
        return;
    }
    // A present worker must be assigned to a project so their labor cost can be
    // attributed; absent workers don't need one.
    if (entryStatus === 'P' && !project) {
        document.getElementById('projectCombo').classList.add('is-invalid');
        showMessage('Please select a project for a present worker.', 'error');
        return;
    }

    const opt = wSel.options[wSel.selectedIndex];
    entries.push({
        worker_id: workerId,
        name: opt.dataset.name,
        // Role is the worker's fixed designation, not a per-day choice.
        role: opt.dataset.designation || '',
        work: work,
        project: project || '',
        status: entryStatus,
        ot_hours: ot
    });

    hideMessage();
    populateWorkerSelect();
    renderEntries();
    resetEntryForm();
}

function removeEntry(index) {
    entries.splice(index, 1);
    populateWorkerSelect();
    renderEntries();
}

function editEntry(index) {
    const e = entries[index];
    // Remove from the list so the worker becomes selectable again, then
    // preload the entry form with its values for re-adding.
    entries.splice(index, 1);
    populateWorkerSelect();
    renderEntries();

    document.getElementById('entryWorker').value = e.worker_id;
    document.getElementById('entryWork').value = e.work || '';
    // Preselect only if the stored value still exists in the registry; a
    // legacy/unmatched value is cleared so the user re-picks a canonical one.
    const known = projectValues.has(e.project) ? e.project : '';
    setProjectValue(known);
    document.getElementById('projectSearch').value = known;
    document.getElementById('entryOT').value = e.ot_hours;
    entryStatus = e.status;
    document.querySelectorAll('#entryStatusToggle .status-btn').forEach(b => {
        b.classList.toggle('active', b.dataset.status === e.status);
    });

    document.querySelector('.mark-entry-card').scrollIntoView({ behavior: 'smooth', block: 'center' });
}

function resetEntryForm() {
    document.getElementById('entryWorker').value = '';
    document.getElementById('entryWork').value = '';
    setProjectValue('');
    document.getElementById('projectSearch').value = '';
    closeProjectList(false);
    document.getElementById('entryOT').value = 0;
    entryStatus = null;
    document.querySelectorAll('#entryStatusToggle .status-btn').forEach(b => b.classList.remove('active'));
}

function renderEntries() {
    const list = document.getElementById('markedList');
    const count = document.getElementById('markedCount');
    count.textContent = `(${entries.length})`;

    if (entries.length === 0) {
        list.innerHTML = '<div class="empty-state">No workers added yet. Choose a worker above and click Add.</div>';
        return;
    }

    // Work and OT are editable straight from the list: supervisors adjusting a
    // saved day (esp. OT) shouldn't have to round-trip each row through the
    // entry form at the top. The inline controls write back into `entries`
    // on change; worker / project / status still go through Edit.
    list.innerHTML = entries.map((e, i) => `
        <div class="marked-row">
            <div class="mr-main">
                <span class="mr-name">${escapeHtml(e.name)}</span>
                <span class="mr-role">${escapeHtml(e.role || '—')}</span>
            </div>
            <div class="mr-inline">
                <label class="mr-inline-field">
                    <span class="mr-inline-label">Work</span>
                    <select class="mr-work-input" onchange="updateEntryWork(${i}, this.value)">
                        ${workOptionsHtml(e.work)}
                    </select>
                </label>
                <label class="mr-inline-field">
                    <span class="mr-inline-label">OT</span>
                    <input type="number" class="mr-ot-input" min="0" max="8" step="0.5"
                           value="${e.ot_hours}" onchange="updateEntryOT(${i}, this)">
                </label>
            </div>
            <div class="mr-meta">
                <span class="mr-project" title="Project">${e.project ? escapeHtml(e.project) : 'No project'}</span>
                <span class="status-pill ${e.status}">${e.status === 'P' ? 'Present' : 'Absent'}</span>
            </div>
            <div class="mr-actions">
                <button class="mr-edit" type="button" onclick="editEntry(${i})">Edit</button>
                <button class="mr-remove" type="button" onclick="removeEntry(${i})" title="Remove">&times;</button>
            </div>
        </div>
    `).join('');
}

// Build <option>s for the inline Work picker, mirroring the entry-form select
// (single source of truth) so the choices never drift apart.
function workOptionsHtml(selected) {
    const src = document.getElementById('entryWork');
    let html = '<option value="">-- Work --</option>';
    if (src) {
        Array.from(src.options).forEach(o => {
            if (!o.value) return;  // skip the form's placeholder
            const sel = o.value === selected ? ' selected' : '';
            html += `<option value="${escapeAttr(o.value)}"${sel}>${escapeHtml(o.value)}</option>`;
        });
    }
    return html;
}

// Inline edits write straight back into `entries`; no re-render (which would
// drop focus / collapse open selects). The committed list is what Finish saves.
function updateEntryWork(index, value) {
    if (entries[index]) entries[index].work = value;
}

// Takes the input element so it can clamp and echo the corrected value back —
// inline handlers can't reach the script-scoped `entries`, so the write-back
// has to happen here rather than in the onchange attribute.
function updateEntryOT(index, el) {
    if (!entries[index]) return;
    let ot = parseFloat(el.value) || 0;
    ot = Math.min(8, Math.max(0, ot));
    entries[index].ot_hours = ot;
    el.value = ot;
}

// ============================================
// SHARE TO WHATSAPP
//
// After Finish, the day's roster is rendered as plain WhatsApp-friendly text the
// supervisor can either copy to the clipboard or one-tap share via wa.me. We do
// not auto-post to any group (no official API supports that and unofficial
// automation risks a ban) — the supervisor picks the group and hits send.
// ============================================

let shareMessageText = '';

function currentSupervisorName() {
    const s = supervisors.find(x => x.id === selectedSupervisorId);
    return s ? s.name : '';
}

// "2026-06-22" -> "22 Jun 2026". Built from the literal Y-M-D so it never drifts
// with the viewer's timezone (the rest of the app reckons dates in IST).
function formatShareDate(dateStr) {
    const [y, m, d] = dateStr.split('-').map(Number);
    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    return `${d} ${months[m - 1]} ${y}`;
}

// Build the plain-text attendance report. *bold* markers render as bold in
// WhatsApp; on any other surface they're harmless asterisks.
function buildAttendanceMessage(list) {
    const present = list.filter(e => e.status === 'P').sort((a, b) => a.name.localeCompare(b.name));
    const absent = list.filter(e => e.status === 'A').sort((a, b) => a.name.localeCompare(b.name));
    const totalOT = present.reduce((s, e) => s + (parseFloat(e.ot_hours) || 0), 0);

    const lines = [];
    lines.push(`📋 *Attendance — ${formatShareDate(markDateStr)}*`);
    const sup = currentSupervisorName();
    if (sup) lines.push(`👷 Supervisor: ${sup}`);
    lines.push('');

    lines.push(`✅ *Present (${present.length})*`);
    if (present.length) {
        // Group present workers under their project. Workers without a project
        // fall under "No project", listed last; projects otherwise alphabetical.
        const groups = {};
        present.forEach(e => {
            const proj = e.project || 'No project';
            (groups[proj] = groups[proj] || []).push(e);
        });
        const projectNames = Object.keys(groups).sort((a, b) => {
            if (a === 'No project') return 1;
            if (b === 'No project') return -1;
            return a.localeCompare(b);
        });
        projectNames.forEach(proj => {
            lines.push('');
            lines.push(`*${proj}*`);
            groups[proj].forEach((e, i) => {
                const work = e.work ? ` — ${e.work}` : '';
                const ot = (parseFloat(e.ot_hours) || 0) > 0 ? ` (+${e.ot_hours} OT)` : '';
                lines.push(`${i + 1}. ${e.name}${work}${ot}`);
            });
        });
    } else {
        lines.push('—');
    }
    lines.push('');

    lines.push(`❌ *Absent (${absent.length})*`);
    if (absent.length) {
        absent.forEach((e, i) => lines.push(`${i + 1}. ${e.name}`));
    } else {
        lines.push('—');
    }
    lines.push('');

    lines.push(`🕐 Total OT: ${Math.round(totalOT * 10) / 10} hrs`);

    return lines.join('\n');
}

function openShareModal(list) {
    shareMessageText = buildAttendanceMessage(list);
    document.getElementById('sharePreview').textContent = shareMessageText;
    document.getElementById('waShareBtn').href = `https://wa.me/?text=${encodeURIComponent(shareMessageText)}`;
    document.getElementById('copyShareBtn').textContent = '📋 Copy';
    document.getElementById('shareModal').style.display = 'flex';
}

function closeShareModal() {
    document.getElementById('shareModal').style.display = 'none';
}

async function copyAttendanceText() {
    const btn = document.getElementById('copyShareBtn');
    const ok = () => { btn.textContent = '✓ Copied!'; setTimeout(() => { btn.textContent = '📋 Copy'; }, 2000); };

    // navigator.clipboard needs a secure context; fall back to execCommand otherwise.
    if (navigator.clipboard && window.isSecureContext) {
        try { await navigator.clipboard.writeText(shareMessageText); ok(); return; }
        catch (e) { /* fall through to legacy path */ }
    }
    const ta = document.createElement('textarea');
    ta.value = shareMessageText;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand('copy'); ok(); }
    catch (e) { btn.textContent = 'Copy failed'; }
    document.body.removeChild(ta);
}

// Close the share modal when the backdrop is clicked.
document.getElementById('shareModal')?.addEventListener('click', function (e) {
    if (e.target === this) closeShareModal();
});

// ============================================
// COMMIT
// ============================================

async function finishAttendance() {
    if (!selectedSupervisorId) { showMessage('Select a supervisor first.', 'error'); return; }

    const btn = document.getElementById('finishBtn');
    const original = btn.textContent;
    btn.disabled = true;
    btn.textContent = 'Saving...';
    hideMessage();

    try {
        // Delete records this supervisor had saved earlier but removed from the list.
        const currentIds = new Set(entries.map(e => e.worker_id));
        const toDelete = [...initialPersistedIds].filter(id => !currentIds.has(id));
        for (const wid of toDelete) {
            await fetch(`/api/attendance/${wid}/${markDateStr}`, { method: 'DELETE' });
        }

        // Upsert everything currently in the list.
        if (entries.length > 0) {
            const records = entries.map(e => ({
                worker_id: e.worker_id,
                date: markDateStr,
                status: e.status,
                ot_hours: e.ot_hours,
                project: e.project || null,
                role: e.role || null,
                work: e.work || null,
                supervisor_id: selectedSupervisorId
            }));
            const res = await fetch('/api/attendance', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(records)
            });
            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                throw new Error(err.error || 'Failed to save');
            }
        }

        showMessage(`Attendance updated for ${entries.length} worker(s).`, 'success');
        window.summaryLoaded = false;

        // Snapshot the saved roster before loadRoster() reassigns `entries`, so
        // the WhatsApp share reflects exactly what was just committed.
        const savedEntries = entries.slice();

        await loadProjects();  // pick up any newly created project
        await loadRoster();    // re-sync persisted state for this supervisor

        // Offer to post the day's attendance to WhatsApp (copy / share as text).
        if (savedEntries.length > 0) openShareModal(savedEntries);
    } catch (e) {
        showMessage(e.message || 'Failed to update attendance.', 'error');
        console.error(e);
    } finally {
        btn.disabled = false;
        btn.textContent = original;
    }
}

// ============================================
// ADD SUPERVISOR
// ============================================

function openSupervisorModal() {
    document.getElementById('supervisorModal').style.display = 'flex';
    setTimeout(() => document.getElementById('newSupervisorName').focus(), 50);
}

function closeSupervisorModal() {
    document.getElementById('supervisorModal').style.display = 'none';
}

async function addSupervisor(e) {
    e.preventDefault();
    const name = document.getElementById('newSupervisorName').value.trim();
    if (!name) return;

    try {
        const res = await fetch('/api/supervisors', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name })
        });
        const data = await res.json();

        if (!res.ok && res.status !== 409) {
            throw new Error(data.error || 'Failed to add supervisor');
        }

        await loadSupervisors();
        // Select the new (or existing) supervisor.
        const match = supervisors.find(s => s.name.toLowerCase() === name.toLowerCase());
        if (match) {
            document.getElementById('supervisorSelect').value = match.id;
            await onSupervisorChange();
        }

        closeSupervisorModal();
        document.getElementById('supervisorForm').reset();
    } catch (err) {
        alert(err.message || 'Error adding supervisor');
        console.error(err);
    }
}

// ============================================
// ADD LABOUR (worker)
// ============================================

async function addNewLabour(e) {
    e.preventDefault();

    const name = document.getElementById('newName').value.trim();
    const designation = document.getElementById('newDesignation').value;
    const baseSalary = parseFloat(document.getElementById('newSalary').value) || 0;

    if (!name) {
        alert('Name is required');
        return;
    }

    try {
        const response = await fetch('/api/labours', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name: name,
                designation: designation,
                base_salary_per_day: baseSalary
            })
        });

        if (!response.ok) {
            const err = await response.json();
            alert(err.error || 'Failed to add labour');
            return;
        }

        closeAddModal();
        document.getElementById('addLabourForm').reset();

        await loadWorkers();
        if (selectedSupervisorId) populateWorkerSelect();

        showMessage(`Labour "${name}" added successfully!`, 'success');
    } catch (error) {
        alert('Error adding labour');
        console.error(error);
    }
}

function closeAddModal() {
    document.getElementById('addModal').style.display = 'none';
}

document.getElementById('addModal')?.addEventListener('click', function (e) {
    if (e.target === this) closeAddModal();
});

// ============================================
// MESSAGES
// ============================================

function showMessage(text, type) {
    const msg = document.getElementById('message');
    msg.textContent = text;
    msg.className = `message ${type}`;
    msg.style.display = 'block';
}

function hideMessage() {
    const msg = document.getElementById('message');
    if (msg) msg.style.display = 'none';
}
