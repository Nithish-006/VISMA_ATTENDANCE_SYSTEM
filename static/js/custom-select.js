// ============================================================
// Inline custom dropdowns (progressive enhancement)
// ------------------------------------------------------------
// Replaces the OS-native <select> picker — which opens as a
// separate full-screen modal on mobile — with an inline, themed
// dropdown rendered in the page using the app's own accent/colours.
//
// The native <select> is KEPT in the DOM as the single source of
// truth: it still holds the options and the value, still fires
// `change`, and `select.value = x` still works. So every existing
// script that reads `.value`, sets `.value`, repopulates options,
// or listens for `change` keeps working untouched — this layer
// only swaps the *visual* control.
// ============================================================

(function () {
    'use strict';

    const ENHANCED = 'csEnhanced';
    let openInstance = null;   // only one panel open at a time

    function esc(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    // Keep the trigger label + caret in sync with the native select's value.
    function refreshTrigger(cs) {
        const sel = cs.select;
        const opt = sel.options[sel.selectedIndex];
        const label = opt ? opt.textContent : '';
        const isPlaceholder = !sel.value;
        cs.labelEl.textContent = label || (opt ? '' : '');
        cs.trigger.classList.toggle('cs-placeholder', isPlaceholder);
        cs.trigger.disabled = sel.disabled;
    }

    // Rebuild the option rows from the native <select> (called on open and
    // whenever the option list changes underneath us).
    function renderOptions(cs, filter) {
        const sel = cs.select;
        const q = (filter || '').trim().toLowerCase();
        cs.listEl.innerHTML = '';
        let shown = 0;

        Array.from(sel.options).forEach((o, i) => {
            const text = o.textContent;
            if (q && !text.toLowerCase().includes(q)) return;
            const row = document.createElement('div');
            row.className = 'cs-option';
            row.setAttribute('role', 'option');
            row.textContent = text;
            if (o.disabled) row.classList.add('cs-disabled');
            if (!o.value) row.classList.add('cs-option-placeholder');
            if (i === sel.selectedIndex) {
                row.classList.add('cs-selected');
                row.setAttribute('aria-selected', 'true');
            }
            row.addEventListener('mousedown', function (e) {
                // mousedown (not click) so the selection lands before the
                // panel's outside-click handler closes it.
                e.preventDefault();
                if (o.disabled) return;
                choose(cs, i);
            });
            cs.listEl.appendChild(row);
            shown++;
        });

        if (!shown) {
            const empty = document.createElement('div');
            empty.className = 'cs-empty';
            empty.textContent = 'No matches';
            cs.listEl.appendChild(empty);
        }
    }

    function choose(cs, index) {
        const sel = cs.select;
        const opt = sel.options[index];
        if (!opt || opt.disabled) return;
        if (sel.selectedIndex !== index) {
            sel.selectedIndex = index;
            // Notify every existing listener / inline onchange handler.
            sel.dispatchEvent(new Event('change', { bubbles: true }));
        }
        refreshTrigger(cs);
        close(cs);
        cs.trigger.focus();
    }

    function open(cs) {
        if (openInstance && openInstance !== cs) close(openInstance);
        openInstance = cs;
        cs.wrap.classList.add('cs-open');
        cs.trigger.setAttribute('aria-expanded', 'true');

        const many = cs.select.options.length > 10;
        cs.searchWrap.style.display = many ? 'block' : 'none';
        cs.searchEl.value = '';
        renderOptions(cs, '');

        cs.panel.style.display = 'block';
        // Flip above the trigger when there isn't room below.
        const rect = cs.trigger.getBoundingClientRect();
        const below = window.innerHeight - rect.bottom;
        cs.panel.classList.toggle('cs-panel-up', below < 300 && rect.top > below);

        // Bring the selected row into view.
        const selRow = cs.listEl.querySelector('.cs-selected');
        if (selRow) selRow.scrollIntoView({ block: 'nearest' });

        if (many) setTimeout(() => cs.searchEl.focus(), 0);
    }

    function close(cs) {
        cs.panel.style.display = 'none';
        cs.wrap.classList.remove('cs-open');
        cs.panel.classList.remove('cs-panel-up');
        cs.trigger.setAttribute('aria-expanded', 'false');
        if (openInstance === cs) openInstance = null;
    }

    function toggle(cs) {
        if (cs.select.disabled) return;
        (cs.wrap.classList.contains('cs-open')) ? close(cs) : open(cs);
    }

    // Move the visual highlight (does not commit) for keyboard nav.
    function moveActive(cs, dir) {
        const rows = Array.from(cs.listEl.querySelectorAll('.cs-option:not(.cs-disabled)'));
        if (!rows.length) return;
        let idx = rows.findIndex(r => r.classList.contains('cs-active'));
        rows.forEach(r => r.classList.remove('cs-active'));
        idx = idx < 0
            ? (dir > 0 ? 0 : rows.length - 1)
            : Math.min(rows.length - 1, Math.max(0, idx + dir));
        rows[idx].classList.add('cs-active');
        rows[idx].scrollIntoView({ block: 'nearest' });
    }

    function commitActive(cs) {
        const active = cs.listEl.querySelector('.cs-option.cs-active')
            || cs.listEl.querySelector('.cs-option:not(.cs-disabled)');
        if (!active) return;
        const all = Array.from(cs.select.options);
        const idx = all.findIndex(o => o.textContent === active.textContent);
        if (idx >= 0) choose(cs, idx);
    }

    function enhance(select) {
        if (select.dataset[ENHANCED] || select.classList.contains('cs-skip')) return;
        select.dataset[ENHANCED] = '1';

        const wrap = document.createElement('div');
        wrap.className = 'cs';

        const trigger = document.createElement('button');
        trigger.type = 'button';
        // Inherit the exact look of the select it replaces (.select-input,
        // .mr-work-input, etc.) so sizing/borders match its old slot.
        trigger.className = 'cs-trigger ' + select.className;
        trigger.setAttribute('aria-haspopup', 'listbox');
        trigger.setAttribute('aria-expanded', 'false');
        if (select.id) trigger.setAttribute('aria-controls', select.id + '-cs-panel');

        const labelEl = document.createElement('span');
        labelEl.className = 'cs-value';
        const caret = document.createElement('span');
        caret.className = 'cs-caret';
        caret.setAttribute('aria-hidden', 'true');
        caret.textContent = '▾';
        trigger.appendChild(labelEl);
        trigger.appendChild(caret);

        const panel = document.createElement('div');
        panel.className = 'cs-panel';
        if (select.id) panel.id = select.id + '-cs-panel';
        panel.style.display = 'none';
        panel.setAttribute('role', 'listbox');

        const searchWrap = document.createElement('div');
        searchWrap.className = 'cs-search-wrap';
        searchWrap.style.display = 'none';
        const searchEl = document.createElement('input');
        searchEl.type = 'text';
        searchEl.className = 'cs-search';
        searchEl.placeholder = 'Search…';
        searchEl.setAttribute('autocomplete', 'off');
        searchWrap.appendChild(searchEl);

        const listEl = document.createElement('div');
        listEl.className = 'cs-list';

        panel.appendChild(searchWrap);
        panel.appendChild(listEl);

        // Slot the wrapper where the select was, then tuck the (now hidden)
        // native select inside it as the source of truth.
        select.parentNode.insertBefore(wrap, select);
        wrap.appendChild(trigger);
        wrap.appendChild(panel);
        wrap.appendChild(select);
        select.classList.add('cs-native-hidden');

        const cs = { wrap, select, trigger, labelEl, panel, searchWrap, searchEl, listEl };
        wrap._cs = cs;

        trigger.addEventListener('click', () => toggle(cs));
        trigger.addEventListener('keydown', function (e) {
            if (e.key === 'ArrowDown' || e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                if (!wrap.classList.contains('cs-open')) open(cs);
                else if (e.key === 'Enter' || e.key === ' ') commitActive(cs);
                else moveActive(cs, 1);
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                if (!wrap.classList.contains('cs-open')) open(cs); else moveActive(cs, -1);
            }
        });

        searchEl.addEventListener('input', () => renderOptions(cs, searchEl.value));
        searchEl.addEventListener('keydown', function (e) {
            if (e.key === 'ArrowDown') { e.preventDefault(); moveActive(cs, 1); }
            else if (e.key === 'ArrowUp') { e.preventDefault(); moveActive(cs, -1); }
            else if (e.key === 'Enter') { e.preventDefault(); commitActive(cs); }
            else if (e.key === 'Escape') { e.preventDefault(); close(cs); cs.trigger.focus(); }
        });

        // Re-sync when the option list is rebuilt programmatically
        // (e.g. supervisor/worker lists loaded via fetch).
        const mo = new MutationObserver(() => {
            refreshTrigger(cs);
            if (wrap.classList.contains('cs-open')) renderOptions(cs, cs.searchEl.value);
        });
        mo.observe(select, { childList: true });

        // Catch programmatic `select.value = x` so the trigger label follows.
        // (MutationObserver doesn't see property writes.)
        const proto = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value');
        const idxProto = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'selectedIndex');
        if (proto && proto.set) {
            Object.defineProperty(select, 'value', {
                configurable: true,
                get() { return proto.get.call(this); },
                set(v) { proto.set.call(this, v); refreshTrigger(cs); }
            });
        }
        if (idxProto && idxProto.set) {
            Object.defineProperty(select, 'selectedIndex', {
                configurable: true,
                get() { return idxProto.get.call(this); },
                set(v) { idxProto.set.call(this, v); refreshTrigger(cs); }
            });
        }

        refreshTrigger(cs);
    }

    function enhanceAll(root) {
        (root || document).querySelectorAll('select').forEach(enhance);
    }

    // Close on outside click / Escape.
    document.addEventListener('mousedown', function (e) {
        if (openInstance && !openInstance.wrap.contains(e.target)) close(openInstance);
    });
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && openInstance) {
            const cs = openInstance; close(cs); cs.trigger.focus();
        }
    });

    // Initial pass + watch for selects added later (e.g. re-rendered rows).
    function init() {
        enhanceAll(document);
        new MutationObserver(function (muts) {
            muts.forEach(m => m.addedNodes.forEach(function (n) {
                if (n.nodeType !== 1) return;
                if (n.tagName === 'SELECT') enhance(n);
                else if (n.querySelectorAll) n.querySelectorAll('select').forEach(enhance);
            }));
        }).observe(document.body, { childList: true, subtree: true });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    // Expose for any code that wants to enhance on demand.
    window.CustomSelect = { enhance, enhanceAll };
})();
