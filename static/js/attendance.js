// Mark Attendance Page JavaScript

let attendanceData = {};
let workerTeams = {};  // Track team changes per worker
let projectsList = [];
let teamsList = [];

document.addEventListener('DOMContentLoaded', async function() {
    const dateInput = document.getElementById('dateInput');
    dateInput.value = new Date().toISOString().split('T')[0];

    // Load projects and teams for autocomplete
    await loadProjectsAndTeams();

    loadAttendance();

    dateInput.addEventListener('change', loadAttendance);
    document.getElementById('saveBtn').addEventListener('click', saveAllAttendance);
    document.getElementById('addLabourBtn').addEventListener('click', () => {
        document.getElementById('addModal').style.display = 'flex';
    });
    document.getElementById('addLabourForm').addEventListener('submit', addNewLabour);
});

async function loadProjectsAndTeams() {
    try {
        const [projectsRes, teamsRes] = await Promise.all([
            fetch('/api/projects'),
            fetch('/api/teams')
        ]);
        projectsList = await projectsRes.json();
        teamsList = await teamsRes.json();

        // Populate teams datalist in add modal
        const teamsDatalist = document.getElementById('teamsList');
        if (teamsDatalist) {
            teamsDatalist.innerHTML = teamsList.map(t => `<option value="${t}">`).join('');
        }
    } catch (error) {
        console.error('Failed to load projects/teams:', error);
    }
}

async function loadAttendance() {
    const date = document.getElementById('dateInput').value;
    const container = document.getElementById('workersContainer');

    container.innerHTML = '<div class="loading">Loading labours...</div>';
    hideMessage();

    try {
        const response = await fetch(`/api/attendance/date/${date}`);
        const workers = await response.json();

        if (workers.length === 0) {
            container.innerHTML = '<div class="empty-state">No labours found. Add labours or import data first.</div>';
            return;
        }

        // Group by team and track worker data
        const teams = {};
        workers.forEach(worker => {
            const team = worker.team || 'Unassigned';
            if (!teams[team]) teams[team] = [];
            teams[team].push(worker);

            attendanceData[worker.worker_id] = {
                worker_id: worker.worker_id,
                date: date,
                status: worker.attendance?.status || 'A',
                ot_hours: worker.attendance?.ot_hours || 0,
                project: worker.attendance?.project || ''
            };

            // Track current team for each worker
            workerTeams[worker.worker_id] = worker.team || '';
        });

        let html = '';
        for (const [team, teamWorkers] of Object.entries(teams)) {
            html += `
                <div class="team-section">
                    <h2 class="team-title">${team}</h2>
                    <div class="worker-grid">
                        ${teamWorkers.map(w => renderWorkerCard(w)).join('')}
                    </div>
                </div>
            `;
        }

        container.innerHTML = html;
        attachCardListeners();

    } catch (error) {
        container.innerHTML = '<div class="error">Error loading data. Is the server running?</div>';
        console.error(error);
    }
}

function renderWorkerCard(worker) {
    const att = attendanceData[worker.worker_id];
    const currentTeam = worker.team || '';

    // Build team options
    const teamOptions = teamsList.map(t =>
        `<option value="${t}" ${t === currentTeam ? 'selected' : ''}>${t}</option>`
    ).join('');

    return `
        <div class="worker-card" data-worker-id="${worker.worker_id}">
            <div class="worker-header">
                <div>
                    <h3 class="worker-name">${worker.name}</h3>
                    <p class="worker-designation">${worker.designation || ''}</p>
                </div>
                <div class="status-buttons">
                    <button class="status-btn P ${att.status === 'P' ? 'active' : ''}" data-status="P">P</button>
                    <button class="status-btn A ${att.status === 'A' ? 'active' : ''}" data-status="A">A</button>
                    <button class="status-btn H ${att.status === 'H' ? 'active' : ''}" data-status="H">H</button>
                </div>
            </div>
            <div class="worker-controls">
                <div class="input-group">
                    <label>Team</label>
                    <select class="team-select">
                        <option value="">-- Select --</option>
                        ${teamOptions}
                        <option value="__new__">+ Add New Team</option>
                    </select>
                </div>
                <div class="input-group">
                    <label>OT Hours</label>
                    <input type="number" min="0" max="8" step="0.5" value="${att.ot_hours}" class="ot-input">
                </div>
                <div class="input-group project-group">
                    <label>Project</label>
                    <select class="project-select">
                        <option value="">-- Select --</option>
                        ${projectsList.map(p =>
                            `<option value="${p}" ${p === att.project ? 'selected' : ''}>${p}</option>`
                        ).join('')}
                        <option value="__new__">+ Add New Project</option>
                    </select>
                </div>
            </div>
        </div>
    `;
}

function attachCardListeners() {
    document.querySelectorAll('.status-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            const card = this.closest('.worker-card');
            const workerId = parseInt(card.dataset.workerId);
            const status = this.dataset.status;

            card.querySelectorAll('.status-btn').forEach(b => b.classList.remove('active'));
            this.classList.add('active');

            attendanceData[workerId].status = status;
        });
    });

    document.querySelectorAll('.ot-input').forEach(input => {
        input.addEventListener('change', function() {
            const card = this.closest('.worker-card');
            const workerId = parseInt(card.dataset.workerId);
            let value = parseFloat(this.value) || 0;
            value = Math.min(8, Math.max(0, value));
            this.value = value;
            attendanceData[workerId].ot_hours = value;
        });
    });

    document.querySelectorAll('.project-select').forEach(select => {
        select.addEventListener('change', function() {
            const card = this.closest('.worker-card');
            const workerId = parseInt(card.dataset.workerId);

            if (this.value === '__new__') {
                const newProject = prompt('Enter new project name:');
                if (newProject && newProject.trim()) {
                    const trimmed = newProject.trim();
                    if (!projectsList.includes(trimmed)) {
                        projectsList.push(trimmed);
                    }
                    attendanceData[workerId].project = trimmed;
                    // Refresh the cards to update all dropdowns
                    loadAttendance();
                } else {
                    this.value = attendanceData[workerId].project || '';
                }
            } else {
                attendanceData[workerId].project = this.value;
            }
        });
    });

    document.querySelectorAll('.team-select').forEach(select => {
        select.addEventListener('change', function() {
            const card = this.closest('.worker-card');
            const workerId = parseInt(card.dataset.workerId);

            if (this.value === '__new__') {
                const newTeam = prompt('Enter new team name:');
                if (newTeam && newTeam.trim()) {
                    const trimmed = newTeam.trim();
                    if (!teamsList.includes(trimmed)) {
                        teamsList.push(trimmed);
                    }
                    workerTeams[workerId] = trimmed;
                    // Refresh the cards to update all dropdowns
                    loadAttendance();
                } else {
                    this.value = workerTeams[workerId] || '';
                }
            } else {
                workerTeams[workerId] = this.value;
            }
        });
    });
}

function updateTeamsDatalist() {
    // Update the modal datalist
    const modalDatalist = document.getElementById('teamsList');
    if (modalDatalist) {
        modalDatalist.innerHTML = teamsList.map(t => `<option value="${t}">`).join('');
    }
}

async function saveAllAttendance() {
    const btn = document.getElementById('saveBtn');
    btn.disabled = true;
    btn.textContent = 'Saving...';
    hideMessage();

    const date = document.getElementById('dateInput').value;
    const records = Object.values(attendanceData).map(att => ({
        worker_id: att.worker_id,
        date: date,
        status: att.status,
        ot_hours: att.ot_hours,
        project: att.project || null,
        team: workerTeams[att.worker_id] || null  // Include team in the request
    }));

    try {
        const response = await fetch('/api/attendance', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(records)
        });

        if (!response.ok) throw new Error('Failed to save');

        showMessage('Attendance saved successfully!', 'success');

        // Reload projects and teams list in case new ones were added
        await loadProjectsAndTeams();

    } catch (error) {
        showMessage('Failed to save attendance.', 'error');
        console.error(error);
    } finally {
        btn.disabled = false;
        btn.textContent = 'Save All';
    }
}

async function addNewLabour(e) {
    e.preventDefault();

    const name = document.getElementById('newName').value.trim();
    const designation = document.getElementById('newDesignation').value;
    const team = document.getElementById('newTeam').value.trim();
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
                team: team,
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

        // Reload teams if new team was added
        if (team && !teamsList.includes(team)) {
            await loadProjectsAndTeams();
        }

        loadAttendance();
        showMessage(`Labour "${name}" added successfully!`, 'success');

    } catch (error) {
        alert('Error adding labour');
        console.error(error);
    }
}

function closeAddModal() {
    document.getElementById('addModal').style.display = 'none';
}

document.getElementById('addModal')?.addEventListener('click', function(e) {
    if (e.target === this) closeAddModal();
});

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
