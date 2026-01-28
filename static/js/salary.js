// Salary Page JavaScript - Monthly Breakdown

let salaryData = null;
let pendingBaseSalaryWorkers = [];

document.addEventListener('DOMContentLoaded', function() {
    loadMonthlySalaries();
    document.getElementById('exportBtn').addEventListener('click', exportExcel);
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

                        <!-- Desktop Table View -->
                        <div class="workers-table desktop-only">
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

                        <!-- Mobile Card View -->
                        <div class="salary-cards mobile-only">
                            ${workers.map(w => `
                                <div class="salary-card worker-row ${!w.base_salary_per_day ? 'needs-salary' : ''}"
                                    data-worker-id="${w.worker_id}"
                                    data-year="${month.year}"
                                    data-month="${month.month_num}"
                                    data-worker-name="${w.name}">
                                    <div class="salary-card-header">
                                        <div class="salary-card-name">${w.name}</div>
                                        <div class="salary-card-total">${formatCurrency(w.total_salary)}</div>
                                    </div>
                                    <div class="salary-card-designation">${w.designation || '-'}</div>
                                    <div class="salary-card-details">
                                        <div class="salary-card-item">
                                            <span class="label">Base/Day</span>
                                            <span class="value">${w.base_salary_per_day ? formatCurrency(w.base_salary_per_day) : '<span class="warning">Not set</span>'}</span>
                                        </div>
                                        <div class="salary-card-item">
                                            <span class="label">Days</span>
                                            <span class="value">${w.working_days}</span>
                                        </div>
                                        <div class="salary-card-item">
                                            <span class="label">OT Hrs</span>
                                            <span class="value">${w.ot_hours}</span>
                                        </div>
                                    </div>
                                    <div class="salary-card-footer">
                                        <div class="salary-card-item">
                                            <span class="label">Base Pay</span>
                                            <span class="value">${formatCurrency(w.base_pay)}</span>
                                        </div>
                                        <div class="salary-card-item">
                                            <span class="label">OT Pay</span>
                                            <span class="value">${formatCurrency(w.ot_pay)}</span>
                                        </div>
                                    </div>
                                </div>
                            `).join('')}
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

async function exportExcel() {
    if (!salaryData || salaryData.length === 0) {
        alert('No data to export');
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
        // Fetch attendance data
        const attendanceResponse = await fetch('/api/attendance/export');
        const attendanceData = await attendanceResponse.json();

        // Create workbook
        const wb = XLSX.utils.book_new();

        // Process each month separately
        for (const month of salaryData) {
            const monthAbbr = month.month_name.split(' ')[0].toUpperCase().substring(0, 3); // e.g., "JAN"
            const year = month.year;
            const yearShort = String(year).slice(-2); // e.g., "25"
            const monthNum = month.month_num;
            const sheetName = `${monthAbbr}-${yearShort}`; // e.g., "JAN-25"

            // Get days in this month
            const daysInMonth = new Date(year, monthNum, 0).getDate();

            // Filter attendance for this month
            const monthAttendance = attendanceData.filter(a => {
                const d = new Date(a.date);
                return d.getFullYear() === year && (d.getMonth() + 1) === monthNum;
            });

            // Build attendance map: worker_id -> day -> {status, ot, project}
            const attendanceMap = {};
            monthAttendance.forEach(a => {
                const day = new Date(a.date).getDate();
                if (!attendanceMap[a.worker_id]) {
                    attendanceMap[a.worker_id] = {};
                }
                attendanceMap[a.worker_id][day] = {
                    status: a.status,
                    ot: a.ot_hours || '',
                    project: a.project || ''
                };
            });

            // Build header rows
            const titleRow = [`LABOUR ATTENDANCE FOR ${sheetName}`];

            // First header row: S.No, Name, DESIGNATION, TEAM, then day numbers
            const headerRow1 = ['S. No', 'Name', 'DESIGNATION', 'TEAM'];
            const headerRow2 = ['', '', '', '']; // Sub-headers for OT, Pr

            for (let day = 1; day <= daysInMonth; day++) {
                const date = new Date(year, monthNum - 1, day);
                const dayName = date.toLocaleDateString('en-US', { weekday: 'short' }).toUpperCase();
                const isSunday = date.getDay() === 0;

                if (isSunday) {
                    headerRow1.push(`${day} SUNDAY`, '', '');
                } else {
                    headerRow1.push(day, '', '');
                }
                headerRow2.push('', 'OT', 'Pr');
            }

            // Add summary columns
            headerRow1.push(`${sheetName} MONTH LABOUR ATTENDANCE & PAYMENT`, '', '', '', '', '');
            headerRow2.push('TOTAL PRESENT', 'TOTAL OT', 'BASE SALARY', 'BASE PAY', 'OT PAY', 'TOTAL SALARY');

            // Build data rows
            const dataRows = [];
            let sNo = 1;

            // Group workers by team
            const teams = {};
            month.workers.forEach(w => {
                const team = w.team || 'Unassigned';
                if (!teams[team]) teams[team] = [];
                teams[team].push(w);
            });

            for (const [team, workers] of Object.entries(teams)) {
                workers.forEach(w => {
                    const row = [sNo++, w.name, w.designation || '', w.team || ''];

                    // Add daily attendance
                    for (let day = 1; day <= daysInMonth; day++) {
                        const att = attendanceMap[w.worker_id]?.[day];
                        if (att) {
                            row.push(att.status, att.ot || '', att.project || '');
                        } else {
                            row.push('', '', '');
                        }
                    }

                    // Add summary columns
                    row.push(
                        w.working_days,             // TOTAL PRESENT
                        w.ot_hours,                 // TOTAL OT
                        w.base_salary_per_day || 0, // BASE SALARY (per day)
                        w.base_pay || 0,            // BASE PAY
                        w.ot_pay || 0,              // OT PAY
                        w.total_salary              // TOTAL SALARY
                    );

                    dataRows.push(row);
                });
            }

            // Combine all rows
            const sheetData = [titleRow, headerRow1, headerRow2, ...dataRows];

            // Create sheet
            const sheet = XLSX.utils.aoa_to_sheet(sheetData);

            // Set column widths
            const cols = [
                { wch: 5 },   // S.No
                { wch: 20 },  // Name
                { wch: 12 },  // Designation
                { wch: 10 }   // Team
            ];

            // Day columns (3 per day)
            for (let day = 1; day <= daysInMonth; day++) {
                cols.push({ wch: 3 }, { wch: 3 }, { wch: 8 }); // Status, OT, Project
            }

            // Summary columns
            cols.push(
                { wch: 13 }, // TOTAL PRESENT
                { wch: 10 }, // TOTAL OT
                { wch: 12 }, // BASE SALARY
                { wch: 10 }, // BASE PAY
                { wch: 10 }, // OT PAY
                { wch: 12 }  // TOTAL SALARY
            );

            sheet['!cols'] = cols;

            // Merge title cell
            sheet['!merges'] = [
                { s: { r: 0, c: 0 }, e: { r: 0, c: 3 } } // Merge title across first 4 columns
            ];

            XLSX.utils.book_append_sheet(wb, sheet, sheetName);
        }

        // Generate and download file
        const fileName = `salary_report_${new Date().toISOString().split('T')[0]}.xlsx`;
        XLSX.writeFile(wb, fileName);

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
