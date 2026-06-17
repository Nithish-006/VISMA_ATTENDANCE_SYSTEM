// Salary Page JavaScript

let salaryData = null;

// All dates in this app are reckoned in IST, independent of the viewer's
// timezone. These helpers keep "today", date parsing, and formatting from
// drifting with the browser locale: toISOString() shifts to UTC, and parsing a
// bare "YYYY-MM-DD" treats it as UTC midnight — both roll the day backwards for
// viewers behind UTC.

// Parse a date string ("YYYY-MM-DD" or ISO datetime) as a literal calendar date
// in local time, so year/month/day/weekday read back exactly as written.
function parseDate(dateStr) {
    const [y, m, d] = dateStr.split('T')[0].split('-').map(Number);
    return new Date(y, m - 1, d);
}

// Today's IST calendar date, as a Date at local midnight.
function istToday() {
    const ymd = new Intl.DateTimeFormat('en-CA', {
        timeZone: 'Asia/Kolkata',
        year: 'numeric', month: '2-digit', day: '2-digit',
    }).format(new Date());
    return parseDate(ymd);
}

// Format a Date's local fields as YYYY-MM-DD (no toISOString/UTC shift).
function isoDate(d) {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
}

// True when both YYYY-MM-DD strings fall in the same calendar month — salary is
// computed per month, so the dashboard/export only accept a single-month range.
function sameMonth(startStr, endStr) {
    return startStr.slice(0, 7) === endStr.slice(0, 7);
}

document.addEventListener('DOMContentLoaded', function() {
    loadSalaryData();
    document.getElementById('exportBtn').addEventListener('click', exportExcel);

    // Worker Pay tab: add-worker modal wiring
    document.getElementById('addWorkerBtn').addEventListener('click', function() {
        document.getElementById('addModal').style.display = 'flex';
        setTimeout(() => document.getElementById('newName').focus(), 50);
    });
    document.getElementById('addWorkerForm').addEventListener('submit', addNewWorker);
    document.getElementById('addModal').addEventListener('click', function(e) {
        if (e.target === this) closeAddModal();
    });
});

async function loadSalaryData() {
    try {
        const response = await fetch('/api/salary/monthly');
        if (!response.ok) throw new Error('Failed to load');
        salaryData = await response.json();
    } catch (error) {
        console.error('Error loading salary data:', error);
        salaryData = [];
    }

    // Render month pills and init filters
    renderMonthPills();
    initSalarySummary();
}

// Re-fetch monthly data (export source) and re-render the dashboard after a
// worker edit/delete, WITHOUT re-running initSalarySummary — that would re-bind
// the filter change-listeners and stack duplicate handlers.
async function refreshSalaryData() {
    try {
        const response = await fetch('/api/salary/monthly');
        if (response.ok) salaryData = await response.json();
    } catch (error) {
        console.error('Error refreshing salary data:', error);
    }
    renderMonthPills();
    loadSalarySummary();
}

// ============================================
// MONTH QUICK PILLS
// ============================================

function renderMonthPills() {
    const bar = document.getElementById('monthPillsBar');
    if (!salaryData || salaryData.length === 0) {
        bar.innerHTML = '';
        return;
    }

    // Build pills from salary months (chronological, oldest first)
    const months = [...salaryData].reverse();
    const pills = months.map(m => {
        const shortMonth = m.month_name.split(' ')[0].substring(0, 3);
        return { key: m.month, label: `${shortMonth}-${m.year}`, year: m.year, monthNum: m.month_num };
    });

    bar.innerHTML = pills.map(p =>
        `<button class="filter-pill" data-key="${p.key}" data-year="${p.year}" data-month="${p.monthNum}">${p.label}</button>`
    ).join('');

    bar.querySelectorAll('.filter-pill').forEach(btn => {
        btn.addEventListener('click', function() {
            // Remove active from all pills
            bar.querySelectorAll('.filter-pill').forEach(b => b.classList.remove('active'));
            this.classList.add('active');

            // Set date range to that month
            const year = parseInt(this.dataset.year);
            const month = parseInt(this.dataset.month);
            const firstDay = new Date(year, month - 1, 1);
            const lastDay = new Date(year, month, 0);

            document.getElementById('salaryStartDate').value = `${year}-${String(month).padStart(2,'0')}-01`;
            document.getElementById('salaryEndDate').value = `${year}-${String(month).padStart(2,'0')}-${String(lastDay.getDate()).padStart(2,'0')}`;

            // Reload summary
            loadSalarySummary();
        });
    });
}

// ============================================
// SUMMARY DASHBOARD
// ============================================

function initSalarySummary() {
    // Default to current week (Mon-Sun), matching attendance summary
    const today = istToday();
    const day = today.getDay();
    const monday = new Date(today);
    monday.setDate(today.getDate() - (day === 0 ? 6 : day - 1));
    const sunday = new Date(monday);
    sunday.setDate(monday.getDate() + 6);

    document.getElementById('salaryStartDate').value = isoDate(monday);
    document.getElementById('salaryEndDate').value = isoDate(sunday);

    loadSalaryFilters();
    loadSalarySummary();

    // Auto-load when any filter changes
    ['salaryStartDate', 'salaryEndDate', 'salaryProject', 'salaryWorker'].forEach(id => {
        document.getElementById(id).addEventListener('change', loadSalarySummary);
    });
}

async function loadSalaryFilters() {
    try {
        const [projectsRes, laboursRes] = await Promise.all([
            fetch('/api/projects'),
            fetch('/api/labours')
        ]);
        const projects = await projectsRes.json();
        const labours = await laboursRes.json();

        const projectSelect = document.getElementById('salaryProject');
        projectSelect.innerHTML = '<option value="">All Projects</option>';
        projects.forEach(p => {
            projectSelect.innerHTML += `<option value="${p}">${p}</option>`;
        });

        const workerSelect = document.getElementById('salaryWorker');
        workerSelect.innerHTML = '<option value="">All Labours</option>';
        labours.forEach(l => {
            workerSelect.innerHTML += `<option value="${l.worker_id}">${l.name}</option>`;
        });
    } catch (e) {
        console.error('Error loading salary filters:', e);
    }
}

function resetSalaryFilters() {
    // Reset dates to current week
    const today = istToday();
    const day = today.getDay();
    const monday = new Date(today);
    monday.setDate(today.getDate() - (day === 0 ? 6 : day - 1));
    const sunday = new Date(monday);
    sunday.setDate(monday.getDate() + 6);

    document.getElementById('salaryStartDate').value = isoDate(monday);
    document.getElementById('salaryEndDate').value = isoDate(sunday);
    document.getElementById('salaryProject').value = '';
    document.getElementById('salaryWorker').value = '';

    // Clear active month pill
    document.querySelectorAll('#monthPillsBar .filter-pill').forEach(b => b.classList.remove('active'));

    loadSalarySummary();
}

async function loadSalarySummary() {
    const startDate = document.getElementById('salaryStartDate').value;
    const endDate = document.getElementById('salaryEndDate').value;
    const project = document.getElementById('salaryProject').value;
    const workerId = document.getElementById('salaryWorker').value;
    const dashboard = document.getElementById('salarySummaryDashboard');

    if (!startDate || !endDate) {
        dashboard.innerHTML = '<div class="empty-state">Please select both start and end dates.</div>';
        return;
    }

    // Salary is reckoned one month at a time (each month has its own base
    // pay/day), so a range that straddles two months is ambiguous — block it.
    if (!sameMonth(startDate, endDate)) {
        dashboard.innerHTML = '<div class="empty-state">Please pick a date range within a single month — salary is calculated per month.</div>';
        return;
    }

    dashboard.innerHTML = '<div class="loading">Loading summary...</div>';

    try {
        let url = `/api/attendance/summary?start_date=${startDate}&end_date=${endDate}`;
        if (project) url += `&project=${encodeURIComponent(project)}`;
        if (workerId) url += `&worker_id=${workerId}`;

        const response = await fetch(url);
        const data = await response.json();

        if (!response.ok) {
            dashboard.innerHTML = `<div class="error">${data.error || 'Error loading summary.'}</div>`;
            return;
        }

        if (data.total_workers === 0) {
            dashboard.innerHTML = '<div class="empty-state">No attendance data found for the selected filters.</div>';
            return;
        }

        let html = `
            <div class="summary-stat-cards">
                <div class="summary-stat-card">
                    <div class="summary-stat-label">Workers</div>
                    <div class="summary-stat-value">${data.total_workers}</div>
                </div>
                <div class="summary-stat-card stat-success">
                    <div class="summary-stat-label">Total Salary</div>
                    <div class="summary-stat-value">${formatCurrency(data.total_salary)}</div>
                </div>
                <div class="summary-stat-card stat-accent">
                    <div class="summary-stat-label">OT Hours</div>
                    <div class="summary-stat-value">${data.total_ot_hours}</div>
                </div>
                <div class="summary-stat-card stat-info">
                    <div class="summary-stat-label">Working Days</div>
                    <div class="summary-stat-value">${data.working_days}</div>
                </div>
            </div>
        `;

        // Project breakdown
        if (data.projects.length > 0) {
            html += `<div class="summary-section-title">Project Breakdown</div>`;
            html += `<div class="project-breakdown">`;
            data.projects.forEach(p => {
                html += `
                    <div class="project-breakdown-card">
                        <div class="project-breakdown-name">${p.name}</div>
                        <div class="project-breakdown-stats">
                            <span class="pb-stat"><strong>${p.worker_count}</strong> workers</span>
                            <span class="pb-stat stat-present"><strong>${p.working_days}</strong> days</span>
                            <span class="pb-stat stat-ot"><strong>${p.ot_hours}</strong> OT hrs</span>
                            <span class="pb-stat stat-success"><strong>${formatCurrency(p.labor_cost)}</strong> labor cost</span>
                        </div>
                    </div>
                `;
            });
            html += `</div>`;
        }

        // Daily breakdown table
        if (data.daily_breakdown.length > 0) {
            html += `<div class="summary-section-title">Daily Breakdown</div>`;
            html += `
                <div class="daily-breakdown-table-wrap">
                    <table class="daily-breakdown-table">
                        <thead>
                            <tr>
                                <th>Date</th>
                                <th class="right">Present</th>
                                <th class="right">Absent</th>
                                <th class="right">Holiday</th>
                                <th class="right">OT Hours</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${data.daily_breakdown.map(d => `
                                <tr>
                                    <td data-label="Date">${formatDate(d.date)}</td>
                                    <td class="right" data-label="Present"><span class="stat-badge-sm present">${d.present}</span></td>
                                    <td class="right" data-label="Absent"><span class="stat-badge-sm absent">${d.absent}</span></td>
                                    <td class="right" data-label="Holiday"><span class="stat-badge-sm holiday">${d.holiday}</span></td>
                                    <td class="right" data-label="OT Hours">${d.ot_hours}</td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
            `;
        }

        // Worker summary table
        if (data.workers.length > 0) {
            html += `<div class="summary-section-title">Worker Summary</div>`;
            html += `
                <div class="worker-summary-table-wrap">
                    <table class="worker-summary-table">
                        <thead>
                            <tr>
                                <th>Name</th>
                                <th class="right">Present</th>
                                <th class="right">Absent</th>
                                <th class="right">OT Hours</th>
                                <th class="right">Salary</th>
                                <th>Projects</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${data.workers.map(w => `
                                <tr class="worker-row" data-worker-id="${w.worker_id}" data-worker-name="${w.name}" style="cursor:pointer;">
                                    <td class="worker-name" data-label="Name">${w.name}</td>
                                    <td class="right" data-label="Present"><span class="stat-badge-sm present">${w.present_days}</span></td>
                                    <td class="right" data-label="Absent"><span class="stat-badge-sm absent">${w.absent_days}</span></td>
                                    <td class="right" data-label="OT Hours">${w.ot_hours}</td>
                                    <td class="right total-cell" data-label="Salary">${formatCurrency(w.salary || 0)}</td>
                                    <td data-label="Projects">${w.projects.join(', ') || '-'}</td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
            `;
        }

        dashboard.innerHTML = html;

        // Attach click listeners to worker rows for history modal
        dashboard.querySelectorAll('.worker-row').forEach(row => {
            row.addEventListener('click', function() {
                const wId = parseInt(this.dataset.workerId);
                const wName = this.dataset.workerName;
                // Determine month from the date range
                const sd = parseDate(startDate);
                showAttendanceHistory(wId, sd.getFullYear(), sd.getMonth() + 1, wName);
            });
        });

    } catch (error) {
        dashboard.innerHTML = '<div class="error">Error loading summary data.</div>';
        console.error(error);
    }
}

function formatDate(dateStr) {
    const d = parseDate(dateStr);
    const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
    return `${days[d.getDay()]}, ${d.getDate()}/${d.getMonth() + 1}/${d.getFullYear()}`;
}

function formatCurrency(amount) {
    return new Intl.NumberFormat('en-IN', {
        style: 'currency',
        currency: 'INR',
        minimumFractionDigits: 0,
        maximumFractionDigits: 0
    }).format(amount || 0);
}

// ============================================
// EXCEL EXPORT
// ============================================

// The workbook is built entirely server-side (GET /api/salary/export) so every
// figure flows through compute_pay — the single source of truth shared with the
// dashboard and salary view. This avoids the report ever drifting from the
// on-screen numbers, which is what happened when the maths lived here in JS.
async function exportExcel() {
    if (!salaryData || salaryData.length === 0) {
        alert('No data to export');
        return;
    }

    // Match the dashboard: only a single-month range is allowed, since salary is
    // calculated per month.
    const exStart = document.getElementById('salaryStartDate')?.value || '';
    const exEnd = document.getElementById('salaryEndDate')?.value || '';
    if (exStart && exEnd && !sameMonth(exStart, exEnd)) {
        alert('Please pick a date range within a single month — salary is calculated per month.');
        return;
    }

    const btn = document.getElementById('exportBtn');
    btn.disabled = true;
    btn.innerHTML = `
        <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" class="spin">
            <circle cx="12" cy="12" r="10" stroke-dasharray="32" stroke-dashoffset="32"/>
        </svg>
        Exporting...
    `;

    try {
        // Scope the report to exactly the filters on screen — date range,
        // project and labour — so the workbook matches the dashboard and never
        // dumps every month. The server applies all of them.
        const startDate = document.getElementById('salaryStartDate')?.value || '';
        const endDate = document.getElementById('salaryEndDate')?.value || '';
        const selectedProject = document.getElementById('salaryProject')?.value || '';
        const selectedWorker = document.getElementById('salaryWorker')?.value || '';

        const params = new URLSearchParams();
        if (startDate) params.set('start_date', startDate);
        if (endDate) params.set('end_date', endDate);
        if (selectedProject) params.set('project', selectedProject);
        if (selectedWorker) params.set('worker_id', selectedWorker);
        const exportUrl = `/api/salary/export?${params.toString()}`;

        const response = await fetch(exportUrl);
        if (!response.ok) throw new Error(`Export failed: ${response.status}`);

        // Prefer the server-supplied filename, fall back to a sensible default.
        const disposition = response.headers.get('Content-Disposition') || '';
        const match = disposition.match(/filename="?([^"]+)"?/);
        const rangeSuffix = startDate && endDate ? `_${startDate}_to_${endDate}` : `_${isoDate(istToday())}`;
        const projectSuffix = selectedProject ? `_${selectedProject.replace(/\s+/g, '_')}` : '';
        const fileName = match ? match[1] : `salary_report${rangeSuffix}${projectSuffix}.xlsx`;

        // Stream the .xlsx bytes to a download.
        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = fileName;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);

    } catch (error) {
        console.error('Export failed:', error);
        alert('Failed to export. Please try again.');
    } finally {
        btn.disabled = false;
        btn.innerHTML = `
            <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                <polyline points="7 10 12 15 17 10"/>
                <line x1="12" y1="15" x2="12" y2="3"/>
            </svg>
            Export Excel
        `;
    }
}

// ============================================
// ATTENDANCE HISTORY MODAL
// ============================================

async function showAttendanceHistory(workerId, year, month, workerName) {
    const modal = document.getElementById('historyModal');
    const title = document.getElementById('historyModalTitle');
    const body = document.getElementById('historyModalBody');

    modal.style.display = 'flex';
    title.textContent = `${workerName}`;
    body.innerHTML = '<div class="loading">Loading attendance history...</div>';

    try {
        const response = await fetch(`/api/labours/${workerId}/history`);
        const data = await response.json();

        // Group attendance by month
        const monthlyData = {};
        data.attendance.forEach(a => {
            const date = parseDate(a.date);
            const monthKey = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`;
            if (!monthlyData[monthKey]) {
                monthlyData[monthKey] = {
                    records: [],
                    presentDays: 0,
                    absentDays: 0,
                    holidays: 0,
                    totalOT: 0
                };
            }
            monthlyData[monthKey].records.push(a);
            if (a.status === 'P') monthlyData[monthKey].presentDays++;
            else if (a.status === 'A') monthlyData[monthKey].absentDays++;
            else if (a.status === 'H') monthlyData[monthKey].holidays++;
            monthlyData[monthKey].totalOT += parseFloat(a.ot_hours) || 0;
        });

        const sortedMonths = Object.keys(monthlyData).sort().reverse();
        sortedMonths.forEach(monthKey => {
            monthlyData[monthKey].records.sort((a, b) => parseDate(a.date) - parseDate(b.date));
        });

        if (sortedMonths.length === 0) {
            body.innerHTML = `
                <div class="worker-info-bar">
                    <span class="info-chip"><strong>ID:</strong> ${data.worker_id}</span>
                    <span class="info-chip"><strong>Designation:</strong> ${data.designation || 'N/A'}</span>
                </div>
                <div class="empty-state">No attendance records found.</div>
            `;
            return;
        }

        body.innerHTML = `
            <div class="worker-info-bar">
                <span class="info-chip"><strong>ID:</strong> ${data.worker_id}</span>
                <span class="info-chip"><strong>Designation:</strong> ${data.designation || 'N/A'}</span>
            </div>

            <div class="history-months">
                ${sortedMonths.map(monthKey => {
                    const m = monthlyData[monthKey];
                    const [y, mo] = monthKey.split('-');
                    const monthName = getMonthName(parseInt(y), parseInt(mo));
                    return `
                        <div class="history-month-section">
                            <div class="history-month-header">
                                <h3 class="history-month-title">${monthName}</h3>
                                <div class="month-stats">
                                    <span class="stat present">${m.presentDays}P</span>
                                    <span class="stat absent">${m.absentDays}A</span>
                                    <span class="stat holiday">${m.holidays}H</span>
                                    <span class="stat ot">${m.totalOT} OT</span>
                                </div>
                            </div>
                            <div class="calendar-grid">
                                ${m.records.map(a => {
                                    const day = parseDate(a.date).getDate();
                                    return `
                                        <div class="day-cell ${a.status.toLowerCase()}" title="${a.date}${a.project ? ' - ' + a.project : ''}">
                                            <span class="day-num">${day}</span>
                                            <span class="day-status">${a.status}</span>
                                            ${a.ot_hours > 0 ? `<span class="day-ot">+${a.ot_hours}</span>` : ''}
                                        </div>
                                    `;
                                }).join('')}
                            </div>
                        </div>
                    `;
                }).join('')}
            </div>
        `;

    } catch (error) {
        body.innerHTML = '<div class="error">Error loading attendance history.</div>';
        console.error(error);
    }
}

function getMonthName(year, month) {
    const months = ['January', 'February', 'March', 'April', 'May', 'June',
                    'July', 'August', 'September', 'October', 'November', 'December'];
    return `${months[month - 1]} ${year}`;
}

function closeHistoryModal() {
    document.getElementById('historyModal').style.display = 'none';
}

// Close modal when clicking outside
document.addEventListener('click', function(e) {
    const modal = document.getElementById('historyModal');
    if (e.target === modal) {
        closeHistoryModal();
    }
});

// ============================================
// PANEL SWITCHING  (Salary Summary  /  Worker Pay)
// ============================================

let currentSalaryPanel = 'summary';
let workersLoaded = false;

function showSalaryPanel(panel) {
    if (panel === currentSalaryPanel) return;
    currentSalaryPanel = panel;

    const container = document.getElementById('salaryPanelsContainer');
    const tabSummary = document.getElementById('tabSummary');
    const tabWorkers = document.getElementById('tabWorkers');
    const summaryControls = document.getElementById('summaryControls');
    const workersControls = document.getElementById('workersControls');

    tabSummary.classList.remove('active');
    tabWorkers.classList.remove('active');

    if (panel === 'summary') {
        container.style.transform = 'translateX(0)';
        tabSummary.classList.add('active');
        summaryControls.style.display = 'flex';
        workersControls.style.display = 'none';
    } else if (panel === 'workers') {
        container.style.transform = 'translateX(-50%)';
        tabWorkers.classList.add('active');
        summaryControls.style.display = 'none';
        workersControls.style.display = 'flex';

        if (!workersLoaded) {
            loadWorkerEditor();
            workersLoaded = true;
        }
    }
}

// ============================================
// WORKER PAY  (base salary, designation, name, delete)
// ============================================

async function loadWorkerEditor() {
    const container = document.getElementById('workerEditorContainer');
    container.innerHTML = '<div class="loading">Loading worker details...</div>';

    try {
        const response = await fetch('/api/labours');
        const labours = await response.json();

        if (labours.length === 0) {
            container.innerHTML = '<div class="empty-state">No workers found.</div>';
            return;
        }

        container.innerHTML = `
            <div class="edit-section" style="margin-bottom: 24px;">
                <h2 class="edit-title">All Workers <span class="count">(${labours.length})</span></h2>
                <div class="edit-table-wrap">
                    <table class="edit-table">
                        <thead>
                            <tr>
                                <th>ID</th>
                                <th>Name</th>
                                <th>Designation</th>
                                <th>Base Pay/Day</th>
                                <th>Pay Type</th>
                                <th>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${labours.map(l => `
                                <tr data-worker-id="${l.worker_id}" id="editRow_${l.worker_id}">
                                    <td class="id-cell" data-label="ID">${l.worker_id}</td>
                                    <td data-label="Name"><input type="text" class="edit-input edit-name" value="${escapeHtml(l.name)}" data-original="${escapeHtml(l.name)}" style="text-transform: uppercase;" oninput="this.value = this.value.toUpperCase(); markEditChanged(this)"></td>
                                    <td data-label="Designation">
                                        <select class="edit-input edit-designation" data-original="${l.designation || ''}" onchange="markEditChanged(this)">
                                            <option value="">--</option>
                                            <option value="FITTER" ${l.designation === 'FITTER' ? 'selected' : ''}>FITTER</option>
                                            <option value="WELDER" ${l.designation === 'WELDER' ? 'selected' : ''}>WELDER</option>
                                            <option value="HELPER" ${l.designation === 'HELPER' ? 'selected' : ''}>HELPER</option>
                                            <option value="RIGGER" ${l.designation === 'RIGGER' ? 'selected' : ''}>RIGGER</option>
                                        </select>
                                    </td>
                                    <td data-label="Base Pay/Day"><input type="number" class="edit-input edit-base-pay" min="0" step="50" value="${l.base_salary_per_day || 0}" data-original="${l.base_salary_per_day || 0}" oninput="markEditChanged(this)"></td>
                                    <td data-label="Pay Type" class="monthly-cell">
                                        <div class="pay-type-toggle" id="payType_${l.worker_id}" data-original="${l.monthly_salaried ? 'monthly' : 'daily'}" data-value="${l.monthly_salaried ? 'monthly' : 'daily'}" title="Daily wages: overtime paid at hourly rate. Monthly wages: overtime tracked but NOT paid.">
                                            <button type="button" class="pay-type-opt ${l.monthly_salaried ? '' : 'active'}" data-val="daily" onclick="setPayType(${l.worker_id}, 'daily')">Daily</button>
                                            <button type="button" class="pay-type-opt ${l.monthly_salaried ? 'active' : ''}" data-val="monthly" onclick="setPayType(${l.worker_id}, 'monthly')">Monthly</button>
                                        </div>
                                    </td>
                                    <td class="edit-actions-cell" style="white-space: nowrap;">
                                        <button class="edit-save-btn" onclick="saveWorkerDetails(${l.worker_id})">Save</button>
                                        <button class="edit-delete-btn" onclick="deleteWorker(${l.worker_id}, '${escapeHtml(l.name)}')">Delete</button>
                                        <span class="edit-status" id="editStatus_${l.worker_id}"></span>
                                    </td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
            </div>
        `;
    } catch (error) {
        container.innerHTML = '<div class="error">Error loading worker details.</div>';
        console.error(error);
    }
}

function markEditChanged(input) {
    const current = input.type === 'checkbox' ? String(input.checked) : input.value;
    if (current !== input.dataset.original) {
        input.classList.add('changed');
    } else {
        input.classList.remove('changed');
    }
}

// Flip the segmented Daily/Monthly wages toggle for a worker row and mark it
// changed (vs the value loaded from the server) so unsaved edits stand out.
function setPayType(workerId, value) {
    const toggle = document.getElementById(`payType_${workerId}`);
    if (!toggle) return;
    toggle.dataset.value = value;
    toggle.querySelectorAll('.pay-type-opt').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.val === value);
    });
    toggle.classList.toggle('changed', value !== toggle.dataset.original);
}

async function saveWorkerDetails(workerId) {
    const row = document.getElementById(`editRow_${workerId}`);
    const status = document.getElementById(`editStatus_${workerId}`);

    const name = row.querySelector('.edit-name').value.trim().toUpperCase();
    const designation = row.querySelector('.edit-designation').value;
    const basePay = parseFloat(row.querySelector('.edit-base-pay').value) || 0;
    const toggle = document.getElementById(`payType_${workerId}`);
    const monthlySalaried = toggle.dataset.value === 'monthly';

    if (!name) {
        status.textContent = 'Name required';
        status.className = 'edit-status error';
        return;
    }

    // Did anything that changes pay actually change? (Name/designation are just
    // labels — they save silently and never re-price a month.) Pay-impacting
    // changes apply to this month and every later month; earlier months stay
    // frozen at what was already paid, so a quick confirm is enough.
    const baseChanged = basePay !== (parseFloat(row.querySelector('.edit-base-pay').dataset.original) || 0);
    const typeChanged = toggle.dataset.value !== toggle.dataset.original;

    if (baseChanged || typeChanged) {
        const rule = monthlySalaried
            ? 'paid monthly wages (overtime tracked but NOT paid)'
            : 'paid daily wages (overtime paid at the hourly rate)';
        const ok = confirm(
            `${name} will be ${rule}` +
            (baseChanged ? ` at ${formatCurrency(basePay)}/day` : '') +
            `.\n\nThis applies to the current month and going forward. ` +
            `Earlier months stay unchanged.`
        );
        if (!ok) return;
    }

    await submitWorkerDetails(workerId, {
        name, designation, base_salary_per_day: basePay,
        monthly_salaried: monthlySalaried
    });
}

// PUT the worker payload and reflect the result in the row. Pay-impacting
// changes re-price the current month and forward server-side; earlier months
// stay frozen.
async function submitWorkerDetails(workerId, payload) {
    const row = document.getElementById(`editRow_${workerId}`);
    const btn = row.querySelector('.edit-save-btn');
    const status = document.getElementById(`editStatus_${workerId}`);
    const toggle = document.getElementById(`payType_${workerId}`);

    btn.disabled = true;
    btn.textContent = 'Saving...';
    status.textContent = '';

    try {
        const response = await fetch(`/api/salary/worker/${workerId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.error || 'Failed to save');
        }

        // Update original values so changed highlighting clears
        row.querySelector('.edit-name').dataset.original = payload.name;
        row.querySelector('.edit-designation').dataset.original = payload.designation;
        row.querySelector('.edit-base-pay').dataset.original = payload.base_salary_per_day;
        const newType = payload.monthly_salaried ? 'monthly' : 'daily';
        toggle.dataset.original = newType;
        toggle.classList.remove('changed');
        row.querySelectorAll('.edit-input').forEach(inp => inp.classList.remove('changed'));

        btn.textContent = 'Saved';
        btn.classList.add('saved');
        status.textContent = '';
        status.className = 'edit-status success';

        // Re-priced months change monthly totals — refresh the summary.
        await refreshSalaryData();

        setTimeout(() => {
            btn.textContent = 'Save';
            btn.classList.remove('saved');
        }, 2000);

    } catch (error) {
        status.textContent = 'Error';
        status.className = 'edit-status error';
        console.error(error);
    } finally {
        btn.disabled = false;
    }
}

async function deleteWorker(workerId, workerName) {
    if (!confirm(`Are you sure you want to delete worker "${workerName}" (ID: ${workerId})?\n\nThis will permanently delete all attendance and salary records for this worker.`)) {
        return;
    }

    const row = document.getElementById(`editRow_${workerId}`);
    const status = document.getElementById(`editStatus_${workerId}`);
    const deleteBtn = row.querySelector('.edit-delete-btn');

    deleteBtn.disabled = true;
    deleteBtn.textContent = 'Deleting...';
    status.textContent = '';

    try {
        const response = await fetch(`/api/salary/worker/${workerId}`, {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json' }
        });

        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.error || 'Failed to delete');
        }

        row.style.transition = 'opacity 0.3s';
        row.style.opacity = '0';
        setTimeout(() => {
            row.remove();
            // Update the worker count in the section header
            document.querySelectorAll('.edit-section').forEach(section => {
                const rows = section.querySelectorAll('tbody tr');
                const countSpan = section.querySelector('.count');
                if (countSpan) countSpan.textContent = `(${rows.length})`;
            });
        }, 300);

        // Removing a worker drops their salary rows — refresh the summary.
        await refreshSalaryData();

    } catch (error) {
        status.textContent = 'Delete failed';
        status.className = 'edit-status error';
        deleteBtn.textContent = 'Delete';
        deleteBtn.disabled = false;
        console.error(error);
    }
}

// ============================================
// ADD WORKER
// ============================================

async function addNewWorker(e) {
    e.preventDefault();

    const name = document.getElementById('newName').value.trim().toUpperCase();
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
            alert(err.error || 'Failed to add worker');
            return;
        }

        closeAddModal();
        document.getElementById('addWorkerForm').reset();

        // Refresh the editor list (if loaded) and the summary filters/data.
        workersLoaded = false;
        if (currentSalaryPanel === 'workers') {
            loadWorkerEditor();
            workersLoaded = true;
        }
        loadSalaryFilters();

        showMessage(`Worker "${name}" added successfully!`, 'success');
    } catch (error) {
        alert('Error adding worker');
        console.error(error);
    }
}

function closeAddModal() {
    document.getElementById('addModal').style.display = 'none';
}

// ============================================
// HELPERS
// ============================================

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function showMessage(text, type) {
    const msg = document.getElementById('message');
    if (!msg) return;
    msg.textContent = text;
    msg.className = `message ${type}`;
    msg.style.display = 'block';
    setTimeout(() => { msg.style.display = 'none'; }, 4000);
}
