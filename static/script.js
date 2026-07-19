/* WorkPulse – Global Live & Dynamic Engine
   ─ Real-time DOM Diffing & Live Background Auto-Updates (Zero Page Refresh)
   ─ Live Running Task Timers (1s Ticks)
   ─ Smart Sortable Tables
   ─ Metric Count-Up Animations
   ─ Ripple Feedback & Typewriter Effects
*/

(function () {
  'use strict';

  /* ═══════════════════════════════════════════════════════════
     1.  LIVE RUNNING TASK TIMERS (1s Ticks)
     ═══════════════════════════════════════════════════════════ */
  function updateTimers() {
    const now = new Date();
    document.querySelectorAll('.duration-display').forEach(function (el) {
      if (el.getAttribute('data-status') !== 'Running') return;
      const lastStartedStr = el.getAttribute('data-last-started');
      if (!lastStartedStr) return;

      const lastStarted = new Date(lastStartedStr + 'Z');
      const accumulated = parseInt(el.getAttribute('data-accumulated') || '0', 10);
      const totalSeconds = accumulated + Math.max(0, Math.floor((now - lastStarted) / 1000));

      const h = Math.floor(totalSeconds / 3600);
      const m = Math.floor((totalSeconds % 3600) / 60);
      const s = totalSeconds % 60;

      const lang = document.documentElement.lang || 'ar';
      if (lang === 'ar') {
        el.textContent = (h > 0 ? h + 'س ' : '') + (m > 0 ? m + 'د ' : '') + s + 'ث';
      } else {
        el.textContent = (h > 0 ? h + 'h ' : '') + (m > 0 ? m + 'm ' : '') + s + 's';
      }
    });
  }

  /* ═══════════════════════════════════════════════════════════
     2.  GLOBAL REAL-TIME DOM AUTO-UPDATER (No Page Refresh)
     ═══════════════════════════════════════════════════════════ */
  const TARGET_CONTAINERS = [
    'metrics-wrapper',
    'live-tasks-wrapper',
    'summary-wrapper',
    'subordinate-live-tasks-wrapper',
    'my-tasks-card',
    'pending-approvals-card',
    'hr-pending-approvals-card'
  ];

  function pollLiveUpdates() {
    // Only poll if tab is active to save resources
    if (document.hidden) return;

    fetch(window.location.href, { cache: 'no-store' })
      .then(r => {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.text();
      })
      .then(html => {
        const doc = new DOMParser().parseFromString(html, 'text/html');

        // 1. Update Target Content Containers
        TARGET_CONTAINERS.forEach(id => {
          const currentEl = document.getElementById(id);
          const freshEl = doc.getElementById(id);

          if (currentEl && freshEl) {
            if (currentEl.innerHTML.trim() !== freshEl.innerHTML.trim()) {
              currentEl.innerHTML = freshEl.innerHTML;
              currentEl.classList.remove('live-update-flash');
              // Force reflow
              void currentEl.offsetWidth;
              currentEl.classList.add('live-update-flash');
            }
          }
        });

        // 2. Update Header Pending Approvals Badges in Real-Time
        const currentBadgeContainers = document.querySelectorAll('.nav-pending-badge-container');
        const freshBadgeContainers = doc.querySelectorAll('.nav-pending-badge-container');

        if (currentBadgeContainers.length > 0 && freshBadgeContainers.length > 0) {
          currentBadgeContainers.forEach((cur, idx) => {
            if (freshBadgeContainers[idx] && cur.innerHTML.trim() !== freshBadgeContainers[idx].innerHTML.trim()) {
              cur.innerHTML = freshBadgeContainers[idx].innerHTML;
            }
          });
        }

        // Re-init timers & sortable tables on updated content
        updateTimers();
        if (window.initSortableTables) window.initSortableTables();
      })
      .catch(err => {
        // Quietly log network errors without disturbing UX
        console.debug('WorkPulse live sync:', err);
      });
  }

  /* ═══════════════════════════════════════════════════════════
     3.  SMART SORTABLE TABLES ENGINE
     ═══════════════════════════════════════════════════════════ */
  function cellValue(cell) {
    let txt = '';
    cell.childNodes.forEach(n => {
      if (n.nodeType === Node.TEXT_NODE) txt += n.textContent;
      else if (n.classList && !n.classList.contains('spinner-grow') && !n.classList.contains('sort-arrow')) {
        txt += n.textContent;
      }
    });
    txt = txt.trim();

    const STATUS_ORDER = { 'not work': 0, 'pause': 1, 'running': 2, 'finish': 3 };
    const lower = txt.toLowerCase();
    if (STATUS_ORDER[lower] !== undefined) return STATUS_ORDER[lower];

    const dur = txt.match(/^(?:(\d+)h\s*)?(?:(\d+)m\s*)?(?:(\d+)s)?$/);
    if (dur && txt.length > 0 && (dur[1] || dur[2] || dur[3])) {
      return (parseInt(dur[1] || 0) * 3600) + (parseInt(dur[2] || 0) * 60) + parseInt(dur[3] || 0);
    }

    const d1 = txt.match(/^(\d{4})[/-](\d{2})[/-](\d{2})/);
    if (d1) { const t = new Date(txt).getTime(); if (!isNaN(t)) return t; }

    const d2 = txt.match(/^(\d{2})[/-](\d{2})[/-](\d{4})/);
    if (d2) { const t = new Date(`${d2[3]}-${d2[2]}-${d2[1]}`).getTime(); if (!isNaN(t)) return t; }

    const n = parseFloat(txt.replace(/,/g, ''));
    if (!isNaN(n)) return n;

    return lower;
  }

  function compare(a, b) {
    if (a === b) return 0;
    return a < b ? -1 : 1;
  }

  function makeSortable(table) {
    if (!table || table._sortable) return;
    table._sortable = true;

    const thead = table.querySelector('thead');
    const tbody = table.querySelector('tbody');
    if (!thead || !tbody) return;

    const ths = thead.querySelectorAll('th');
    let sortCol = -1, sortAsc = true;

    ths.forEach((th, colIdx) => {
      if (th.dataset.nosort !== undefined) return;

      th.style.cursor = 'pointer';
      th.style.userSelect = 'none';
      th.style.position = 'relative';
      th.style.whiteSpace = 'nowrap';

      const arrow = document.createElement('span');
      arrow.className = 'sort-arrow';
      arrow.style.cssText = 'font-size:.7em;opacity:.38;margin-left:4px;display:inline-block;transition:opacity .2s,color .2s;';
      arrow.textContent = '⇅';
      th.appendChild(arrow);

      th.addEventListener('click', () => {
        if (sortCol === colIdx) { sortAsc = !sortAsc; }
        else { sortCol = colIdx; sortAsc = true; }

        ths.forEach(t => {
          const a = t.querySelector('.sort-arrow');
          if (a) { a.textContent = '⇅'; a.style.opacity = '.38'; a.style.color = ''; }
        });

        arrow.textContent = sortAsc ? '↑' : '↓';
        arrow.style.opacity = '1';
        arrow.style.color = 'var(--accent, #4f46e5)';

        const rows = Array.from(tbody.querySelectorAll('tr'));
        rows.sort((ra, rb) => {
          const ca = ra.cells[colIdx], cb = rb.cells[colIdx];
          if (!ca || !cb) return 0;
          const va = cellValue(ca), vb = cellValue(cb);
          if (typeof va !== typeof vb) return typeof va === 'number' ? -1 : 1;
          return sortAsc ? compare(va, vb) : compare(vb, va);
        });

        rows.forEach(r => tbody.appendChild(r));
      });
    });
  }

  window.makeSortable = makeSortable;
  window.initSortableTables = function () {
    document.querySelectorAll('table[data-sortable], table.table-sortable').forEach(makeSortable);
  };

  /* ═══════════════════════════════════════════════════════════
     4.  MICRO-ANIMATIONS & INTERACTIVES
     ═══════════════════════════════════════════════════════════ */
  function animateCount(el, target, duration) {
    const startTime = performance.now();
    function step(now) {
      const p = Math.min((now - startTime) / duration, 1);
      const eased = 1 - Math.pow(1 - p, 3);
      el.textContent = Math.round(target * eased);
      if (p < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  }

  function addRipple(e) {
    const btn = e.currentTarget;
    const old = btn.querySelector('.wp-ripple');
    if (old) old.remove();
    const d = Math.max(btn.clientWidth, btn.clientHeight);
    const rect = btn.getBoundingClientRect();
    const span = document.createElement('span');
    span.className = 'wp-ripple';
    span.style.cssText = `position:absolute;border-radius:50%;background:rgba(255,255,255,.3);
      width:${d}px;height:${d}px;
      left:${e.clientX - rect.left - d/2}px;top:${e.clientY - rect.top - d/2}px;
      transform:scale(0);animation:rippleAnim .6s linear forwards;pointer-events:none;`;
    btn.style.overflow = 'hidden';
    btn.style.position = 'relative';
    btn.appendChild(span);
    setTimeout(() => span.remove(), 650);
  }

  /* ═══════════════════════════════════════════════════════════
     5.  INITIALIZATION ON DOM LOAD
     ═══════════════════════════════════════════════════════════ */
  document.addEventListener('DOMContentLoaded', () => {
    // 1. Initialise Live Timers
    updateTimers();
    setInterval(updateTimers, 1000);

    // 2. Initialise Global Real-Time Background Sync (Every 5 seconds)
    setInterval(pollLiveUpdates, 5000);

    // 3. Initialise Sortable Tables
    window.initSortableTables();

    // 4. Initialise Metric Count-Up Animations
    document.querySelectorAll('.metric-number[data-count-up]').forEach(el => {
      const target = parseInt(el.dataset.countUp, 10);
      if (!isNaN(target)) animateCount(el, target, 1000);
    });

    // 5. Ripple Effect on Buttons
    document.querySelectorAll('.btn').forEach(b => b.addEventListener('click', addRipple));

    // 6. Typewriter Effect on Page Titles
    const title = document.querySelector('h1.page-title');
    if (title) {
      const original = title.textContent.trim();
      if (original.length <= 32) {
        title.textContent = '';
        title.style.borderRight = '2px solid var(--accent,#4f46e5)';
        title.style.whiteSpace = 'nowrap';
        title.style.overflow = 'hidden';
        title.style.display = 'inline-block';

        let i = 0;
        const interval = setInterval(() => {
          title.textContent = original.slice(0, ++i);
          if (i >= original.length) {
            clearInterval(interval);
            setTimeout(() => { title.style.borderRight = 'none'; }, 800);
          }
        }, 45);
      }
    }
  });
})();
