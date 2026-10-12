// App-wide date display: always DD-MM-YYYY.
//
// A native <input type="date"> renders in the viewer's OS locale (mm/dd/yyyy on
// a US phone), and that can't be overridden. So every date input is upgraded
// in place to a text field that shows DD-MM-YYYY, with a hidden native date
// input behind it that still supplies the calendar picker.
//
// The upgraded field's .value keeps speaking YYYY-MM-DD, so page scripts (and
// API query strings) read and write it exactly as before — only what the user
// sees changes. Typing a date by hand also works (DD-MM-YYYY, "/" or "." too).

// "2026-10-12" (or an ISO datetime) -> "12-10-2026". Built from the literal
// Y-M-D so it never drifts with the viewer's timezone.
function formatDMY(dateStr) {
    if (!dateStr) return '';
    const [y, m, d] = String(dateStr).split('T')[0].split('-');
    if (!y || !m || !d) return String(dateStr);
    return `${d.padStart(2, '0')}-${m.padStart(2, '0')}-${y}`;
}

// "12-10-2026" / "12/10/2026" / "12.10.2026" -> "2026-10-12"; null if invalid.
function parseDMY(text) {
    const match = String(text).trim().match(/^(\d{1,2})[-\/.](\d{1,2})[-\/.](\d{4})$/);
    if (!match) return null;
    const [, d, m, y] = match.map(Number);
    const dt = new Date(y, m - 1, d);
    if (dt.getFullYear() !== y || dt.getMonth() !== m - 1 || dt.getDate() !== d) return null;
    return `${y}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
}

(function () {
    const valueProp = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value');

    function upgrade(input) {
        // Hidden native input that only exists to open the calendar.
        const picker = document.createElement('input');
        picker.type = 'date';
        picker.tabIndex = -1;
        picker.setAttribute('aria-hidden', 'true');
        picker.className = 'dmy-picker';
        valueProp.set.call(picker, valueProp.get.call(input));

        let iso = valueProp.get.call(input);
        input.type = 'text';
        input.inputMode = 'numeric';
        input.autocomplete = 'off';
        input.placeholder = 'dd-mm-yyyy';
        input.classList.add('dmy-input');
        valueProp.set.call(input, formatDMY(iso));
        input.after(picker);

        Object.defineProperty(input, 'value', {
            configurable: true,
            get: () => iso,
            set: (v) => {
                iso = v ? String(v).split('T')[0] : '';
                valueProp.set.call(input, formatDMY(iso));
                valueProp.set.call(picker, iso);
            },
        });

        // Typed text is committed on change. Capture phase runs before the
        // page's own change handlers, so they only ever see a valid date —
        // garbage reverts to the last good value and the event is swallowed.
        let fromPicker = false;
        input.addEventListener('change', (e) => {
            if (fromPicker) return;  // already committed by the picker below
            const typed = valueProp.get.call(input);
            const parsed = typed.trim() === '' ? '' : parseDMY(typed);
            if (parsed === null || parsed === iso) {
                valueProp.set.call(input, formatDMY(iso));
                e.stopImmediatePropagation();
                return;
            }
            input.value = parsed;
        }, true);

        function openPicker() {
            if (typeof picker.showPicker !== 'function') return;  // typing still works
            try { picker.showPicker(); } catch (_) { /* needs a user gesture */ }
        }
        input.addEventListener('click', openPicker);
        input.addEventListener('keydown', (e) => {
            if ((e.key === 'ArrowDown' && e.altKey) || e.key === 'F4') { e.preventDefault(); openPicker(); }
        });

        picker.addEventListener('change', () => {
            const picked = valueProp.get.call(picker);
            if (picked === iso) return;
            input.value = picked;
            fromPicker = true;
            try { input.dispatchEvent(new Event('change', { bubbles: true })); }
            finally { fromPicker = false; }
        });
    }

    function upgradeAll(root) {
        root.querySelectorAll('input[type="date"]:not(.dmy-picker)').forEach(upgrade);
    }

    window.upgradeDateInputs = upgradeAll;
    upgradeAll(document);
})();
