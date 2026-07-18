// hr_reports.js – Handles HR report UI interactions with persisted filter settings

document.addEventListener('DOMContentLoaded', function() {
  // ---------- Initialise date pickers (Flatpickr) ----------
  flatpickr('#dateFrom', { dateFormat: 'Y-m-d' });
  flatpickr('#dateTo',   { dateFormat: 'Y-m-d' });
  flatpickr('#projDateFrom', { dateFormat: 'Y-m-d' });
  flatpickr('#projDateTo',   { dateFormat: 'Y-m-d' });

  // ---------- Helper utilities ----------
  function downloadBlob(blob, filename) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  // Persisted filter storage key
  const STORAGE_KEY = 'hr_report_filters';

  // Load any previously stored filters and populate the form fields
  function loadFilters() {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return;
    let data;
    try { data = JSON.parse(raw); } catch (_) { return; }
    // Employee report filters
    if (data.employee) {
      const { id, category, dateFrom, dateTo, project_ids } = data.employee;
      if (id) document.getElementById('employeeSelect').value = id;
      const catSel = document.getElementById('categorySelect');
      if (catSel && category) catSel.value = category;
      if (dateFrom) document.getElementById('dateFrom').value = dateFrom;
      if (dateTo) document.getElementById('dateTo').value = dateTo;
      if (Array.isArray(project_ids)) {
        const sel = document.getElementById('projectSelect');
        for (const opt of sel.options) {
          opt.selected = project_ids.includes(opt.value);
        }
      }
    }
    // Project report filters
    if (data.project) {
      const { id, category, dateFrom, dateTo } = data.project;
      if (id) document.getElementById('projectSelectReport').value = id;
      const projCatSel = document.getElementById('projCategorySelect');
      if (projCatSel && category) projCatSel.value = category;
      if (dateFrom) document.getElementById('projDateFrom').value = dateFrom;
      if (dateTo) document.getElementById('projDateTo').value = dateTo;
    }
  }

  // Save a shallow copy of the provided filter object under the global storage key
  function saveFilters(partial) {
    const raw = localStorage.getItem(STORAGE_KEY);
    let existing = {};
    try { existing = JSON.parse(raw); } catch (_) {}
    const merged = Object.assign({}, existing, partial);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(merged));
  }

  // Attach change listeners to keep the storage in sync as the user modifies fields
  // Employee report fields
  const employeeSelect = document.getElementById('employeeSelect');
  const categorySelect = document.getElementById('categorySelect');
  const dateFromEmp = document.getElementById('dateFrom');
  const dateToEmp = document.getElementById('dateTo');
  const projectSelect = document.getElementById('projectSelect');

  if (employeeSelect) employeeSelect.addEventListener('change', function() {
    const stored = (JSON.parse(localStorage.getItem(STORAGE_KEY)) || {});
    const emp = stored.employee || {};
    emp.id = this.value;
    stored.employee = emp;
    localStorage.setItem(STORAGE_KEY, JSON.stringify(stored));
  });
  if (categorySelect) categorySelect.addEventListener('change', function() {
    const stored = (JSON.parse(localStorage.getItem(STORAGE_KEY)) || {});
    const emp = stored.employee || {};
    emp.category = this.value;
    stored.employee = emp;
    localStorage.setItem(STORAGE_KEY, JSON.stringify(stored));
  });
  if (dateFromEmp) dateFromEmp.addEventListener('change', function() {
    const stored = (JSON.parse(localStorage.getItem(STORAGE_KEY)) || {});
    const emp = stored.employee || {};
    emp.dateFrom = this.value;
    stored.employee = emp;
    localStorage.setItem(STORAGE_KEY, JSON.stringify(stored));
  });
  if (dateToEmp) dateToEmp.addEventListener('change', function() {
    const stored = (JSON.parse(localStorage.getItem(STORAGE_KEY)) || {});
    const emp = stored.employee || {};
    emp.dateTo = this.value;
    stored.employee = emp;
    localStorage.setItem(STORAGE_KEY, JSON.stringify(stored));
  });
  if (projectSelect) projectSelect.addEventListener('change', function() {
    const stored = (JSON.parse(localStorage.getItem(STORAGE_KEY)) || {});
    const emp = stored.employee || {};
    emp.project_ids = Array.from(this.selectedOptions).map(o => o.value);
    stored.employee = emp;
    localStorage.setItem(STORAGE_KEY, JSON.stringify(stored));
  });

  // Project report fields
  const projectSelectReport = document.getElementById('projectSelectReport');
  const projCategorySelect = document.getElementById('projCategorySelect');
  const dateFromProj = document.getElementById('projDateFrom');
  const dateToProj = document.getElementById('projDateTo');

  if (projectSelectReport) projectSelectReport.addEventListener('change', function() {
    const stored = (JSON.parse(localStorage.getItem(STORAGE_KEY)) || {});
    const proj = stored.project || {};
    proj.id = this.value;
    stored.project = proj;
    localStorage.setItem(STORAGE_KEY, JSON.stringify(stored));
  });
  if (projCategorySelect) projCategorySelect.addEventListener('change', function() {
    const stored = (JSON.parse(localStorage.getItem(STORAGE_KEY)) || {});
    const proj = stored.project || {};
    proj.category = this.value;
    stored.project = proj;
    localStorage.setItem(STORAGE_KEY, JSON.stringify(stored));
  });
  if (dateFromProj) dateFromProj.addEventListener('change', function() {
    const stored = (JSON.parse(localStorage.getItem(STORAGE_KEY)) || {});
    const proj = stored.project || {};
    proj.dateFrom = this.value;
    stored.project = proj;
    localStorage.setItem(STORAGE_KEY, JSON.stringify(stored));
  });
  if (dateToProj) dateToProj.addEventListener('change', function() {
    const stored = (JSON.parse(localStorage.getItem(STORAGE_KEY)) || {});
    const proj = stored.project || {};
    proj.dateTo = this.value;
    stored.project = proj;
    localStorage.setItem(STORAGE_KEY, JSON.stringify(stored));
  });

  // ---------- Export employee report ----------
  const exportEmployeeBtn = document.getElementById('exportEmployeeBtn');
  if (exportEmployeeBtn) {
    exportEmployeeBtn.addEventListener('click', function() {
      const employeeId = employeeSelect.value;
      const category = categorySelect ? categorySelect.value : null;
      const dateFrom = dateFromEmp.value;
      const dateTo = dateToEmp.value;
      const projectIds = Array.from(projectSelect.selectedOptions).map(o => o.value);

      if (!employeeId || !dateFrom || !dateTo) {
        alert('Please fill out all required fields (*)');
        return;
      }

      // Ensure current filters are saved
      saveFilters({ employee: { id: employeeId, category, dateFrom, dateTo, project_ids: projectIds } });

      fetch('/hr/export', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          type: 'employee',
          employee_id: employeeId,
          category: category || null,
          date_from: dateFrom,
          date_to: dateTo,
          project_ids: projectIds
        })
      })
        .then(res => {
          if (!res.ok) throw new Error('Network response was not ok');
          const disposition = res.headers.get('Content-Disposition');
          let filename = 'employee_report.xlsx';
          if (disposition && disposition.includes('filename=')) {
            filename = disposition.split('filename=')[1].replace(/"|'/g, '');
          }
          return res.blob().then(blob => downloadBlob(blob, filename));
        })
        .catch(err => alert('Export failed: ' + err));
    });
  }

  // ---------- Print employee report ----------
  const printEmployeeBtn = document.getElementById('printEmployeeBtn');
  if (printEmployeeBtn) {
    printEmployeeBtn.addEventListener('click', function() {
      const employeeId = employeeSelect.value;
      const category = categorySelect ? categorySelect.value : null;
      const dateFrom = dateFromEmp.value;
      const dateTo = dateToEmp.value;
      const projectIds = Array.from(projectSelect.selectedOptions).map(o => o.value);

      if (!employeeId || !dateFrom || !dateTo) {
        alert('Please fill out all required fields (*)');
        return;
      }

      saveFilters({ employee: { id: employeeId, category, dateFrom, dateTo, project_ids: projectIds } });

      let url = `/hr/reports/print?type=employee&employee_id=${employeeId}&date_from=${dateFrom}&date_to=${dateTo}`;
      if (category) url += `&category=${category}`;
      if (projectIds.length > 0) {
        projectIds.forEach(pid => {
          url += `&project_ids=${pid}`;
        });
      }
      window.open(url, '_blank');
    });
  }

  // ---------- Export project report ----------
  const exportProjectBtn = document.getElementById('exportProjectBtn');
  if (exportProjectBtn) {
    exportProjectBtn.addEventListener('click', function() {
      const projectId = projectSelectReport.value;
      const category = projCategorySelect ? projCategorySelect.value : null;
      const dateFrom = dateFromProj.value;
      const dateTo = dateToProj.value;

      if (!dateFrom || !dateTo) {
        alert('Please fill out all required fields (*)');
        return;
      }

      // Persist project‑report filter values
      saveFilters({ project: { id: projectId, category, dateFrom, dateTo } });

      fetch('/hr/export', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          type: 'project',
          project_id: projectId || null,
          category: category || null,
          date_from: dateFrom,
          date_to: dateTo
        })
      })
        .then(res => {
          if (!res.ok) throw new Error('Network response was not ok');
          const disposition = res.headers.get('Content-Disposition');
          let filename = 'project_report.xlsx';
          if (disposition && disposition.includes('filename=')) {
            filename = disposition.split('filename=')[1].replace(/"|'/g, '');
          }
          return res.blob().then(blob => downloadBlob(blob, filename));
        })
        .catch(err => alert('Export failed: ' + err));
    });
  }

  // ---------- Print project report ----------
  const printProjectBtn = document.getElementById('printProjectBtn');
  if (printProjectBtn) {
    printProjectBtn.addEventListener('click', function() {
      const projectId = projectSelectReport.value;
      const category = projCategorySelect ? projCategorySelect.value : null;
      const dateFrom = dateFromProj.value;
      const dateTo = dateToProj.value;

      if (!dateFrom || !dateTo) {
        alert('Please fill out all required fields (*)');
        return;
      }

      saveFilters({ project: { id: projectId, category, dateFrom, dateTo } });

      let url = `/hr/reports/print?type=project&date_from=${dateFrom}&date_to=${dateTo}`;
      if (projectId) url += `&project_id=${projectId}`;
      if (category) url += `&category=${category}`;
      window.open(url, '_blank');
    });
  }

  // Finally, load any stored values so the UI reflects previous selections
  loadFilters();
});
