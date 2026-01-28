// Salary Page JavaScript - Monthly Breakdown

let salaryData = null;
let pendingBaseSalaryWorkers = [];

document.addEventListener('DOMContentLoaded', function() {
    loadMonthlySalaries();
    document.getElementById('exportBtn').addEventListener('click', exportCSV);
});

async function loadMonthlySalaries() {
    const container = document.getElementById('salaryContainer');
    container.innerHTML = '<div class="loading">Loading salary data...</div>';

    try {
        const response = await fetch('/api/salary/monthly');
        if (!response.ok) throw new Error('Failed to load');

        salaryData = await response.json();

        if (!salaryData || salaryData.length === 0) {
            container.innerHTML = '<div class="empty-state">No salary data found. Mark attendance first.</div>';
            return;
        }

        // Check for workers without base salary
        const allWorkers = salaryData.flatMap(m => m.workers);
        const uniqueWorkers = new Map();
        allWorkers.forEach(w => {
            if (!uniqueWorkers.has(w.worker_id) && (!w.base_salary_per_day || w.base_salary_per_day === 0)) {
                uniqueWorkers.set(w.worker_id, w);
            }
        });
        pendingBaseSalaryWorkers = Array.from(uniqueWorkers.values());

        // Render monthly sections
        container.innerHTML = salaryData.map(month => renderMonthSection(month)).join('');

        // Attach click listeners to worker rows
        attachWorkerRowListeners();

        // Show base salary prompt if needed
        if (pendingBaseSalaryWorkers.length > 0) {
            promptForBaseSalary();
        }

    } catch (error) {
        container.innerHTML = '<div class="error">Error loading data. Is the server running?</div>';
        console.error(error);
    }
}

function renderMonthSection(month) {
    // Group workers by team
    const teams = {};
    month.workers.forEach(w => {
        const team = w.team || 'Unassigned';
        if (!teams[team]) teams[team] = [];
        teams[team].push(w);
    });

    return `
        <div class="month-section">
            <div class="month-header">
                <h2 class="month-title">${month.month_name}</h2>
                <div class="month-total">Total: ${formatCurrency(month.total_salary)}</div>
            </div>
            <div class="month-content">
                ${Object.entries(teams).map(([team, workers]) => `
                    <div class="team-group">
                        <div class="team-label">${team}</div>
                        <div class="workers-table">
                            <table>
                                <thead>
                                    <tr>
                                        <th>Name</th>
                                        <th>Designation</th>
                                        <th class="right">Base/Day</th>
                                        <th class="right">Days</th>
                                        <th class="right">OT Hrs</th>
                                        <th class="right">Base Pay</th>
                                        <th class="right">OT Pay</th>
                                        <th class="right">Total</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    ${workers.map(w => `
                                        <tr class="worker-row ${!w.base_salary_per_day ? 'needs-salary' : ''}"
                                            data-worker-id="${w.worker_id}"
                                            data-year="${month.year}"
                                            data-month="${month.month_num}"
                                            data-worker-name="${w.name}">
                                            <td class="worker-name">${w.name}</td>
                                            <td>${w.designation || '-'}</td>
                                            <td class="right">${w.base_salary_per_day ? formatCurrency(w.base_salary_per_day) : '<span class="warning">Not set</span>'}</td>
                                            <td class="right">${w.working_days}</td>
                                            <td class="right">${w.ot_hours}</td>
                                            <td class="right">${formatCurrency(w.base_pay)}</td>
                                            <td class="right">${formatCurrency(w.ot_pay)}</td>
                                            <td class="right total-cell">${formatCurrency(w.total_salary)}</td>
                                        </tr>
                                    `).join('')}
                                </tbody>
                            </table>
                        </div>
                    </div>
                `).join('')}
            </div>
        </div>
    `;
}

function formatCurrency(amount) {
    return new Intl.NumberFormat('en-IN', {
        style: 'currency',
        currency: 'INR',
        minimumFractionDigits: 0,
        maximumFractionDigits: 0
    }).format(amount || 0);
}

function exportCSV() {
    if (!salaryData || salaryData.length === 0) {
        alert('No data to export');
        return;
    }

    const headers = ['Month', 'Name', 'Designation', 'Team', 'Base/Day', 'Working Days', 'OT Hours', 'Base Pay', 'OT Pay', 'Total Salary'];
    const rows = [];

    salaryData.forEach(month => {
        month.workers.forEach(w => {
            rows.push([
                month.month_name,
                w.name,
                w.designation || '',
                w.team || '',
                w.base_salary_per_day,
                w.working_days,
                w.ot_hours,
                w.base_pay,
                w.ot_pay,
                w.total_salary
            ]);
        });
        // Add month total row
        rows.push([
            month.month_name,
            'MONTH TOTAL',
            '', '', '', '', '', '', '',
            month.total_salary
        ]);
        rows.push([]); // Empty row between months
    });

    const csvContent = [
        headers.join(','),
        ...rows.map(row => row.map(cell => `"${cell}"`).join(','))
    ].join('\n');

    const blob = new Blob([csvContent], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `monthly_salary_report_${new Date().toISOString().split('T')[0]}.csv`;
    a.click();
    window.URL.revokeObjectURL(url);
}

function promptForBaseSalary() {
    if (pendingBaseSalaryWorkers.length === 0) return;

    const worker = pendingBaseSalaryWorkers[0];

    let modal = document.getElementById('baseSalaryModal');
    if (!modal) {
        modal = document.createElement('div');
        modal.id = 'baseSalaryModal';
        modal.className = 'modal';
        modal.innerHTML = `
            <div class="modal-content modal-small">
                <div class="modal-header">
                    <h2>Set Base Salary</h2>
                </div>
                <div class="modal-body">
                    <p id="baseSalaryWorkerInfo" style="margin-bottom: 20px;"></p>
                    <form id="baseSalaryForm">
                        <div class="form-group">
                            <label for="baseSalaryInput">Base Salary Per Day (₹)</label>
                            <input type="number" id="baseSalaryInput" min="1" step="1" required>
                        </div>
                        <button type="submit" class="submit-btn">Save & Calculate</button>
                    </form>
                </div>
            </div>
        `;
        document.body.appendChild(modal);
        document.getElementById('baseSalaryForm').addEventListener('submit', saveBaseSalary);
    }

    document.getElementById('baseSalaryWorkerInfo').innerHTML =
        `<strong>${worker.name}</strong> (${worker.designation || 'No designation'}) - ${worker.team || 'No team'}`;
    document.getElementById('baseSalaryInput').value = '';
    document.getElementById('baseSalaryInput').focus();
    modal.style.display = 'flex';
}

async function saveBaseSalary(e) {
    e.preventDefault();

    const worker = pendingBaseSalaryWorkers[0];
    const baseSalary = parseFloat(document.getElementById('baseSalaryInput').value);

    if (!baseSalary || baseSalary <= 0) {
        alert('Please enter a valid base salary');
        return;
    }

    try {
        const response = await fetch(`/api/salary/worker/${worker.worker_id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ base_salary_per_day: baseSalary })
        });

        if (!response.ok) throw new Error('Failed to update');

        pendingBaseSalaryWorkers.shift();

        if (pendingBaseSalaryWorkers.length > 0) {
            promptForBaseSalary();
        } else {
            document.getElementById('baseSalaryModal').style.display = 'none';
            loadMonthlySalaries();
        }

    } catch (error) {
        alert('Failed to save base salary');
        console.error(error);
    }
}

function attachWorkerRowListeners() {
    document.querySelectorAll('.worker-row').forEach(row => {
        row.style.cursor = 'pointer';
        row.addEventListener('click', function() {
            const workerId = parseInt(this.dataset.workerId);
            const year = parseInt(this.dataset.year);
            const month = parseInt(this.dataset.month);
            const workerName = this.dataset.workerName;
            showAttendanceHistory(workerId, year, month, workerName);
        });
    });
}

async function showAttendanceHistory(workerId, year, month, workerName) {
    const modal = document.getElementById('historyModal');
    const title = document.getElementById('historyModalTitle');
    const body = document.getElementById('historyModalBody');

    modal.style.display = 'flex';
    title.textContent = `${workerName} - ${getMonthName(year, month)}`;
    body.innerHTML = '<div class="loading">Loading attendance history...</div>';

    try {
        const response = await fetch(`/api/labours/${workerId}/history`);
        const data = await response.json();

        // Filter attendance records for the specific month
        const monthRecords = data.attendance.filter(a => {
            const date = new Date(a.date);
            return date.getFullYear() === year && (date.getMonth() + 1) === month;
        });

        // Sort by date ascending
        monthRecords.sort((a, b) => new Date(a.date) - new Date(b.date));

        // Calculate stats
        let presentDays = 0, absentDays = 0, holidays = 0, totalOT = 0;
        monthRecords.forEach(a => {
            if (a.status === 'P') presentDays++;
            else if (a.status === 'A') absentDays++;
            else if (a.status === 'H') holidays++;
            totalOT += parseFloat(a.ot_hours) || 0;
        });

        if (monthRecords.length === 0) {
            body.innerHTML = `
                <div class="worker-info-bar">
                    <span class="info-chip"><strong>ID:</strong> ${data.worker_id}</span>
                    <span class="info-chip"><strong>Designation:</strong> ${data.designation || 'N/A'}</span>
                    <span class="info-chip"><strong>Team:</strong> ${data.team || 'N/A'}</span>
                </div>
                <div class="empty-state">No attendance records for this month.</div>
            `;
            return;
        }

        body.innerHTML = `
            <div class="worker-info-bar">
                <span class="info-chip"><strong>ID:</strong> ${data.worker_id}</span>
                <span class="info-chip"><strong>Designation:</strong> ${data.designation || 'N/A'}</span>
                <span class="info-chip"><strong>Team:</strong> ${data.team || 'N/A'}</span>
            </div>

            <div class="history-months">
                <div class="history-month-section">
                    <div class="history-month-header">
                        <h3 class="history-month-title">${getMonthName(year, month)}</h3>
                        <div class="month-stats">
                            <span class="stat present">${presentDays}P</span>
                            <span class="stat absent">${absentDays}A</span>
                            <span class="stat holiday">${holidays}H</span>
                            <span class="stat ot">${totalOT} OT</span>
                        </div>
                    </div>
                    <div class="calendar-grid">
                        ${monthRecords.map(a => {
                            const day = new Date(a.date).getDate();
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
