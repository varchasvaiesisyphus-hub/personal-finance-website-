// static/main.js
window.__categoryCache = [];

(function () {
  const API = {
    categories: '/api/categories/',
    transactions: '/api/transactions/'
  };

  function getCookie(name) {
    const v = document.cookie.split('; ').find(row => row.startsWith(name + '='));
    return v ? decodeURIComponent(v.split('=')[1]) : null;
  }
  const CSRF = getCookie('csrftoken');

  function injectModalHTML() {
    if (document.getElementById('txn-modal')) return;

    const css = `
    .category-list {
      display: flex; flex-direction: column; gap: 8px; max-height: 180px;
      overflow: auto; padding: 6px; border: 1px solid #eef2f6;
      border-radius: 8px; background: #ffffff;
    }
    .cat-item {
      display: flex; align-items: center; justify-content: space-between;
      gap: 8px; padding: 8px 10px; border-radius: 8px;
      border: 1px solid transparent; cursor: pointer;
      transition: background 0.12s, border-color 0.12s;
    }
    .cat-item:focus  { outline: none; border-color: #c7d2fe; background: #f8fafc; }
    .cat-item:hover  { background: #fafafa; }
    .cat-item.selected { background: #eef2ff; border-color: #c7d2fe; }
    .cat-name {
      flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis;
      white-space: nowrap; font-size: 14px; color: #111827;
    }
    .trash-btn {
      background: transparent; border: none; padding: 6px; cursor: pointer;
      border-radius: 6px; color: #9ca3af; display: flex; align-items: center;
    }
    .trash-btn:hover { background: #fee2e2; color: #dc2626; }
    .trash-btn:active { transform: scale(0.92); }

    #txn-modal {
      position: fixed; inset: 0; background: rgba(15,23,42,0.45);
      display: flex; align-items: center; justify-content: center;
      z-index: 9999; backdrop-filter: blur(6px);
    }
    #txn-modal[aria-hidden="true"] { display: none; }
    .txn-dialog {
      background: #fff; width: 520px; max-width: 95%; border-radius: 16px;
      padding: 30px 28px; position: relative;
      box-shadow: 0 25px 70px rgba(0,0,0,0.15), 0 10px 30px rgba(0,0,0,0.08);
      font-family: system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
      animation: modalFade 0.18s ease-out;
    }
    @keyframes modalFade {
      from { opacity:0; transform:translateY(10px) scale(0.98); }
      to   { opacity:1; transform:translateY(0) scale(1); }
    }
    .txn-dialog h3 { margin: 0 0 24px; font-size: 20px; font-weight: 600; color: #111827; }
    .close-x {
      position: absolute; right: 18px; top: 18px; border: none;
      background: transparent; font-size: 20px; cursor: pointer; color: #6b7280;
    }
    .close-x:hover { color: #111827; }
    .txn-row { display: flex; flex-direction: column; gap: 6px; margin-bottom: 18px; }
    .txn-row label { font-size: 13px; font-weight: 500; color: #374151; }
    .txn-row input, .txn-row select {
      padding: 11px 12px; border-radius: 8px; border: 1px solid #d1d5db; font-size: 14px;
    }
    .txn-row input:focus, .txn-row select:focus {
      outline: none; border-color: #2563eb; box-shadow: 0 0 0 3px rgba(37,99,235,0.12);
    }
    .amount-type-row { display: flex; gap: 16px; }
    .amount-field { flex: 1; }
    .type-field { width: 130px; display: flex; flex-direction: column; justify-content: flex-end; }
    .type-toggle {
      padding: 11px 12px; border-radius: 8px; font-weight: 600; cursor: pointer;
      border: 1px solid #e5e7eb; display: flex; align-items: center; justify-content: center; gap: 6px;
    }
    .type-toggle.income  { background: #ecfdf5; color: #047857; border-color: #a7f3d0; }
    .type-toggle.expense { background: #fef2f2; color: #b91c1c; border-color: #fecaca; }
    .create-category-row { display: flex; gap: 10px; margin-top: 8px; }
    .create-category-row input { flex: 1; }
    .modal-btn {
      padding: 10px 14px; border-radius: 8px; cursor: pointer;
      border: 1px solid #d1d5db; background: #f3f4f6; font-weight: 500;
    }
    .modal-btn:hover { background: #e5e7eb; }
    .modal-btn-primary { background: #2563eb; color: #fff; border: none; }
    .modal-btn-primary:hover { background: #1d4ed8; }
    .txn-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 14px; }
    .errorspan { font-size: 12px; color: #b91c1c; min-height: 14px; display: block; }
    `;
    const style = document.createElement('style');
    style.textContent = css;
    document.head.appendChild(style);

    const modal = document.createElement('div');
    modal.id = 'txn-modal';
    modal.setAttribute('aria-hidden', 'true');
    modal.innerHTML = `
      <div class="txn-dialog">
        <button id="modal-close-x" class="close-x" type="button">&times;</button>
        <h3>Add Transaction</h3>
        <form id="txn-form" novalidate>
          <div class="txn-row amount-type-row">
            <div class="amount-field">
              <label for="amount">Amount</label>
              <input id="amount" type="number" step="0.01" placeholder="0.00" />
              <span id="amount-error" class="errorspan"></span>
            </div>
            <div class="type-field">
              <label>Type</label>
              <button id="txn-type-toggle" type="button" class="type-toggle expense">
                <span id="txn-type-symbol">&#8722;</span>
                <span id="txn-type-label">Expense</span>
              </button>
            </div>
          </div>

          <div class="txn-row">
            <label>Category</label>
            <input type="hidden" id="selected-category-id" value="">
            <div class="create-category-row">
              <input id="new-category-name" type="text" placeholder="New category name" />
              <button type="button" id="save-category" class="modal-btn">Save</button>
            </div>
            <div id="category-list" class="category-list" aria-live="polite" role="list" style="margin-top:8px;"></div>
            <span id="category-error" class="errorspan"></span>
          </div>

          <div class="txn-row">
            <label for="account">Account</label>
            <select id="account">
              <option value="">-- choose account --</option>
              <option value="cash">Cash</option>
              <option value="bank">Bank</option>
            </select>
            <span id="account-error" class="errorspan"></span>
          </div>

          <div class="txn-row">
            <label for="date">Date</label>
            <input id="date" type="date" />
            <span id="date-error" class="errorspan"></span>
          </div>

          <div id="form-message" style="min-height:16px;margin-bottom:6px;font-size:13px;"></div>

          <div class="txn-actions">
            <button type="button" id="submit-txn" class="modal-btn modal-btn-primary">Add</button>
            <button type="button" id="done" class="modal-btn">Done</button>
          </div>
        </form>
      </div>
    `;

    modal.addEventListener('click', (e) => {
      if (e.target === modal) modal.setAttribute('aria-hidden', 'true');
    });
    document.body.appendChild(modal);
  }

  function appendRowToTable({ id, date, category, amount, account, type }) {
    const table = document.getElementById('txTable');
    if (!table) return;
    const tbody = table.querySelector('tbody') || table.appendChild(document.createElement('tbody'));
    const tr = document.createElement('tr');
    tr.setAttribute('data-type', type);
    const sign = type === 'income' ? '+' : '\u2212';
    tr.innerHTML = `
      <td>${date}</td>
      <td>${category}</td>
      <td><span class="amount-cell">${sign}${Number(amount).toFixed(2)}</span></td>
      <td>${account.charAt(0).toUpperCase() + account.slice(1)}</td>
      <td class="select-cell"><input type="checkbox" class="row-checkbox" data-id="${id}"></td>
    `;
    tbody.prepend(tr);
  }

  async function loadCategoriesToSelect() {
    window.__categoryCache = [];
    try {
      const res = await fetch(API.categories);
      if (!res.ok) throw new Error();
      const data = await res.json();
      window.__categoryCache = data.map(c => ({ id: c.id, name: c.name }));
    } catch {
      const cats = new Set();
      document.querySelectorAll('#txTable tbody tr td:nth-child(2)').forEach(td => cats.add(td.textContent.trim()));
      window.__categoryCache = Array.from(cats).map(name => ({ id: name, name }));
    }
    renderCategoryListFromSelect();
  }

  async function createCategory(name, type) {
    const res = await fetch(API.categories, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF },
      body: JSON.stringify({ name, type })
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.message || 'Failed to create');
    }
    const created = await res.json();
    window.__categoryCache = window.__categoryCache || [];
    window.__categoryCache.push({ id: created.id, name: created.name });
    setSelectedCategory(String(created.id));
    renderCategoryListFromSelect();
    return created;
  }

  function renderCategoryListFromSelect() {
    const list = document.getElementById('category-list');
    if (!list) return;
    list.innerHTML = '';
    const selectedId = document.getElementById('selected-category-id')?.value || '';

    (window.__categoryCache || []).forEach(cat => {
      const id = String(cat.id);
      const item = document.createElement('div');
      item.className = 'cat-item' + (id === selectedId ? ' selected' : '');
      item.setAttribute('role', 'button');
      item.setAttribute('tabindex', '0');
      item.dataset.id = id;

      const nameSpan = document.createElement('div');
      nameSpan.className = 'cat-name';
      nameSpan.textContent = cat.name;

      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'trash-btn';
      btn.title = 'Delete category';
      btn.innerHTML = `<svg viewBox="0 0 24 24" width="16" height="16"><path fill="currentColor" d="M9 3v1H4v2h16V4h-5V3H9zm2 6v7h2V9h-2zM7 9v7h2V9H7zm8 0v7h2V9h-2z"/></svg>`;

      item.onclick = (e) => { if (!e.target.closest('.trash-btn')) setSelectedCategory(id); };
      item.onkeydown = (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setSelectedCategory(id); } };
      btn.onclick = async (e) => {
        e.stopPropagation();
        btn.disabled = true;
        try { await deleteCategoryByValue(id, cat.name); } finally { btn.disabled = false; }
      };

      item.appendChild(nameSpan);
      item.appendChild(btn);
      list.appendChild(item);
    });
  }

  function setSelectedCategory(id) {
    const hid = document.getElementById('selected-category-id');
    if (hid) hid.value = id || '';
    const list = document.getElementById('category-list');
    if (!list) return;
    list.querySelectorAll('.cat-item.selected').forEach(el => el.classList.remove('selected'));
    if (id) {
      const matched = list.querySelector(`.cat-item[data-id="${CSS.escape(id)}"]`);
      if (matched) { matched.classList.add('selected'); matched.scrollIntoView({ block: 'nearest' }); }
    }
  }

  async function deleteCategoryByValue(val, displayName) {
    if (!val || !confirm(`Delete category "${displayName}"? This cannot be undone.`)) return;
    const res = await fetch(API.categories + encodeURIComponent(val) + '/', {
      method: 'DELETE',
      headers: { 'X-CSRFToken': CSRF }
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.message || 'Failed to delete');
    }
    window.__categoryCache = (window.__categoryCache || []).filter(c => String(c.id) !== String(val));
    const sel = document.getElementById('selected-category-id');
    if (sel && sel.value === String(val)) sel.value = '';
    renderCategoryListFromSelect();
  }

  async function openTransactionModal() {
    injectModalHTML();
    const modal = document.getElementById('txn-modal');
    if (!modal) return;
    modal.setAttribute('aria-hidden', 'false');

    document.getElementById('date').value = new Date().toISOString().slice(0, 10);
    await loadCategoriesToSelect();

    let currentType = 'expense';
    const typeToggle = document.getElementById('txn-type-toggle');

    function updateTypeUI() {
      typeToggle.className = 'type-toggle ' + currentType;
      document.getElementById('txn-type-symbol').textContent = currentType === 'income' ? '+' : '\u2212';
      document.getElementById('txn-type-label').textContent  = currentType === 'income' ? 'Income' : 'Expense';
    }
    updateTypeUI();

    // Clone nodes to clear any stale listeners from a previous modal open
    function refreshBtn(id) {
      const old = document.getElementById(id);
      const fresh = old.cloneNode(true);
      old.parentNode.replaceChild(fresh, old);
      return fresh;
    }

    refreshBtn('txn-type-toggle').onclick = () => {
      currentType = currentType === 'income' ? 'expense' : 'income';
      updateTypeUI();
    };
    refreshBtn('modal-close-x').onclick = () => modal.setAttribute('aria-hidden', 'true');
    refreshBtn('done').onclick           = () => modal.setAttribute('aria-hidden', 'true');

    refreshBtn('save-category').onclick = async function () {
      const name = (document.getElementById('new-category-name').value || '').trim();
      const err  = document.getElementById('category-error');
      err.textContent = '';
      if (!name) { err.textContent = 'Enter a name'; return; }
      this.disabled = true;
      try {
        await createCategory(name, currentType);
        document.getElementById('new-category-name').value = '';
      } catch (e) { err.textContent = e.message || 'Failed'; }
      finally { this.disabled = false; }
    };

    refreshBtn('submit-txn').onclick = async function () {
      ['amount-error','category-error','account-error','date-error','form-message'].forEach(id => {
        const el = document.getElementById(id);
        if (el) { el.textContent = ''; el.style.color = ''; }
      });

      const amount   = Math.abs(parseFloat(document.getElementById('amount').value));
      const category = document.getElementById('selected-category-id').value;
      const account  = document.getElementById('account').value;
      const date     = document.getElementById('date').value;

      let valid = true;
      if (!Number.isFinite(amount) || amount <= 0) { document.getElementById('amount-error').textContent   = 'Enter a positive amount'; valid = false; }
      if (!category)                                { document.getElementById('category-error').textContent = 'Pick a category';          valid = false; }
      if (!account)                                 { document.getElementById('account-error').textContent  = 'Pick an account';           valid = false; }
      if (!date)                                    { document.getElementById('date-error').textContent     = 'Pick a date';               valid = false; }
      if (!valid) return;

      this.disabled = true;
      this.textContent = 'Saving\u2026';

      try {
        const resp = await fetch(API.transactions, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
          body: JSON.stringify({ amount, category, account, date, type: currentType })
        });
        const data = await resp.json();
        if (resp.ok) {
          const msg = document.getElementById('form-message');
          msg.style.color = 'green';
          msg.textContent = 'Saved! Refreshing\u2026';
          setTimeout(() => location.reload(), 500);
        } else {
          throw new Error(data.message || 'Server error');
        }
      } catch (err) {
        const msg = document.getElementById('form-message');
        if (msg) { msg.style.color = 'red'; msg.textContent = err.message; }
        this.disabled = false;
        this.textContent = 'Add';
      }
    };
  }

  // -------------------------------------------------------
  // Unified table change handler (checkboxes + select-all)
  // FIX: previously split across two listeners, second one
  // was inside DOMContentLoaded which never fires for a
  // deferred script (the event has already fired by then).
  // -------------------------------------------------------
  const txTable = document.getElementById('txTable');
  if (txTable) {
    txTable.addEventListener('change', (e) => {
      const t = e.target;

      // Master "select all" checkbox
      if (t.id === 'selectAllVisible') {
        document.querySelectorAll('.row-checkbox').forEach(cb => { cb.checked = t.checked; });
      }

      // Sync delete button label + disabled state
      if (t.classList.contains('row-checkbox') || t.id === 'selectAllVisible') {
        const n = document.querySelectorAll('.row-checkbox:checked').length;
        const btn = document.getElementById('deleteBtn');
        if (btn) {
          btn.disabled = n === 0;
          btn.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24"><path fill="currentColor" d="M9 3v1H4v2h16V4h-5V3H9zm2 6v7h2V9h-2zM7 9v7h2V9H7zm8 0v7h2V9h-2z"/></svg> ${n > 0 ? 'Delete (' + n + ')' : 'Delete'}`;
        }
      }
    });
  }

  // Delete handler
  const deleteBtn = document.getElementById('deleteBtn');
  if (deleteBtn) {
    deleteBtn.addEventListener('click', async () => {
      const ids = Array.from(document.querySelectorAll('.row-checkbox:checked')).map(cb => cb.dataset.id);
      if (!ids.length || !confirm('Delete selected transactions?')) return;
      try {
        const resp = await fetch('/api/transactions/delete/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
          body: JSON.stringify({ ids })
        });
        if (resp.ok) location.reload();
        else alert('Delete failed.');
      } catch (err) { console.error('Delete error:', err); }
    });
  }

  // Open modal
  document.addEventListener('click', (e) => {
    if (e.target.closest && e.target.closest('#addNewBtn')) openTransactionModal();
  });

  // -------------------------------------------------------
  // Dropdown filter
  // FIX: was inside DOMContentLoaded — moved to run directly.
  // -------------------------------------------------------
  const dropdownBtn   = document.getElementById('dropdownBtn');
  const dropdownList  = document.getElementById('accountsList');
  const selectedLabel = document.getElementById('selectedLabel');

  if (dropdownBtn && dropdownList) {
    dropdownBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      const open = dropdownList.classList.toggle('show');
      dropdownBtn.setAttribute('aria-expanded', String(open));
    });

    document.addEventListener('click', (e) => {
      if (!e.target.closest('#accountsDropdown')) {
        dropdownList.classList.remove('show');
        dropdownBtn.setAttribute('aria-expanded', 'false');
      }
    });

    dropdownList.querySelectorAll('.dropdown__option').forEach(opt => {
      opt.addEventListener('click', () => {
        if (selectedLabel) selectedLabel.textContent = opt.textContent.trim();
        filterTransactions(opt.dataset.value);
        dropdownList.classList.remove('show');
        dropdownBtn.setAttribute('aria-expanded', 'false');
      });
    });
  }

  function filterTransactions(filterType) {
    document.querySelectorAll('#txTable tbody tr').forEach(row => {
      row.style.display = (filterType === 'all' || row.dataset.type === filterType) ? '' : 'none';
    });
  }

})();