/* WorkPulse – Global JS
   ─ Sortable tables (smart cell parsing)
   ─ Count-up metrics
   ─ Ripple effect on click
   ─ Typewriter title
*/

/* ═══════════════════════════════════════════════════════════
   1.  SMART SORTABLE TABLES
   ═══════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  /**
   * Extract a sort-key from a table cell.
   * Handles:
   *  - Badge text like "Not Work" → treated as 0
   *  - Plain numbers / duration strings "2h 15m 30s"
   *  - Date strings YYYY-MM-DD or DD/MM/YYYY HH:MM
   *  - Fallback: lowercase string
   */
  function cellValue(cell) {
    let txt = '';
    cell.childNodes.forEach(n => {
      if (n.nodeType === Node.TEXT_NODE) txt += n.textContent;
      else if (n.classList && !n.classList.contains('spinner-grow') && !n.classList.contains('sort-arrow')) {
        txt += n.textContent;
      }
    });
    txt = txt.trim();

    // Known status words → numeric sentinel so they sort together
    const STATUS_ORDER = { 'not work': 0, 'pause': 1, 'running': 2, 'finish': 3 };
    const lower = txt.toLowerCase();
    if (STATUS_ORDER[lower] !== undefined) return STATUS_ORDER[lower];

    // Duration "2h 15m 30s"
    const dur = txt.match(/^(?:(\d+)h\s*)?(?:(\d+)m\s*)?(?:(\d+)s)?$/);
    if (dur && txt.length > 0 && (dur[1] || dur[2] || dur[3])) {
      return (parseInt(dur[1] || 0) * 3600) + (parseInt(dur[2] || 0) * 60) + parseInt(dur[3] || 0);
    }

    // Date YYYY-MM-DD (possibly with time)
    const d1 = txt.match(/^(\d{4})[/-](\d{2})[/-](\d{2})/);
    if (d1) { const t = new Date(txt).getTime(); if (!isNaN(t)) return t; }

    // Date DD/MM/YYYY
    const d2 = txt.match(/^(\d{2})[/-](\d{2})[/-](\d{4})/);
    if (d2) { const t = new Date(`${d2[3]}-${d2[2]}-${d2[1]}`).getTime(); if (!isNaN(t)) return t; }

    // Plain number
    const n = parseFloat(txt.replace(/,/g, ''));
    if (!isNaN(n)) return n;

    // Fallback: lowercase string
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

        // Arrange rows
        rows.forEach(r => tbody.appendChild(r));
      });
    });
  }

  window.makeSortable = makeSortable;
  window.initSortableTables = function () {
    document.querySelectorAll('table[data-sortable], table.table-sortable').forEach(makeSortable);
  };

  document.addEventListener('DOMContentLoaded', window.initSortableTables);

  // Re-init when live sections refresh via polling
  const mo = new MutationObserver(() => window.initSortableTables());
  document.addEventListener('DOMContentLoaded', () => {
    ['subordinate-live-tasks-wrapper', 'summary-wrapper'].forEach(id => {
      const el = document.getElementById(id);
      if (el) mo.observe(el, { childList: true, subtree: true });
    });
  });
})();


/* ═══════════════════════════════════════════════════════════
   2.  COUNT-UP ANIMATION
   ═══════════════════════════════════════════════════════════ */
(function () {
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
  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.metric-number[data-count-up]').forEach(el => {
      const target = parseInt(el.dataset.countUp, 10);
      if (!isNaN(target)) animateCount(el, target, 1000);
    });
  });
})();


/* ═══════════════════════════════════════════════════════════
   3.  RIPPLE EFFECT
   ═══════════════════════════════════════════════════════════ */
(function () {
  const style = document.createElement('style');
  style.textContent = '@keyframes rippleAnim { to { transform:scale(3); opacity:0; } }';
  document.head.appendChild(style);

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
  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.btn').forEach(b => b.addEventListener('click', addRipple));
  });
})();


/* ═══════════════════════════════════════════════════════════
   4.  TYPEWRITER EFFECT on page-title
   ═══════════════════════════════════════════════════════════ */
(function () {
  document.addEventListener('DOMContentLoaded', () => {
    const title = document.querySelector('h1.page-title');
    if (!title) return;
    const original = title.textContent.trim();
    if (original.length > 32) return;
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
  });
})();
