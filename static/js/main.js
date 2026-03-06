// static/main.js
window.__categoryCache = [];

(function () {
  const API = {
    categories:   '/api/categories/',
    transactions: '/api/transactions/',
    balances:     '/api/balances/',
    transfer:     '/api/transfer/',
  };

  function getCookie(name) {
    const v = document.cookie.split('; ').find(r => r.startsWith(name + '='));
    return v ? decodeURIComponent(v.split('=')[1]) : null;
  }
  const CSRF = getCookie('csrftoken');

  function fmt(n) {
    return '\u20b9' + Number(n).toLocaleString('en-IN', {
      minimumFractionDigits: 2, maximumFractionDigits: 2,
    });
  }

  // ── Inject Add-Transaction modal HTML (once) ─────────────────────
  function injectModalHTML() {
    if (document.getElementById('txn-modal')) return;

    const css = `
    .category-list {
      display:flex; flex-direction:column; gap:8px; max-height:180px;
      overflow:auto; padding:6px; border:1px solid #eef2f6;
      border-radius:8px; background:#fff;
    }
    .cat-item {
      display:flex; align-items:center; justify-content:space-between;
      gap:8px; padding:8px 10px; border-radius:8px;
      border:1px solid transparent; cursor:pointer;
      transition:background .12s,border-color .12s;
    }
    .cat-item:focus  { outline:none; border-color:#c7d2fe; background:#f8fafc; }
    .cat-item:hover  { background:#fafafa; }
    .cat-item.selected { background:#eef2ff; border-color:#c7d2fe; }
    .cat-name {
      flex:1; min-width:0; overflow:hidden; text-overflow:ellipsis;
      white-space:nowrap; font-size:14px; color:#111827;
    }
    .trash-btn {
      background:transparent; border:none; padding:6px; cursor:pointer;
      border-radius:6px; color:#9ca3af; display:flex; align-items:center;
    }
    .trash-btn:hover  { background:#fee2e2; color:#dc2626; }
    .trash-btn:active { transform:scale(.92); }

    #txn-modal {
      position:fixed; inset:0; background:rgba(15,23,42,.45);
      display:flex; align-items:center; justify-content:center;
      z-index:9999; backdrop-filter:blur(6px);
    }
    #txn-modal[aria-hidden="true"] { display:none; }
    .txn-dialog {
      background:#fff; width:520px; max-width:95%; border-radius:16px;
      padding:30px 28px; position:relative;
      box-shadow:0 25px 70px rgba(0,0,0,.15),0 10px 30px rgba(0,0,0,.08);
      font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
      animation:modalFade .18s ease-out;
      max-height:90vh; overflow-y:auto;
    }
    @keyframes modalFade {
      from{opacity:0;transform:translateY(10px) scale(.98)}
      to  {opacity:1;transform:translateY(0)    scale(1) }
    }
    .txn-dialog h3 { margin:0 0 24px; font-size:20px; font-weight:600; color:#111827; }
    .close-x {
      position:absolute; right:18px; top:18px; border:none;
      background:transparent; font-size:20px; cursor:pointer; color:#6b7280;
    }
    .close-x:hover { color:#111827; }
    .txn-row { display:flex; flex-direction:column; gap:6px; margin-bottom:18px; }
    .txn-row label { font-size:13px; font-weight:500; color:#374151; }
    .txn-row input,.txn-row select {
      padding:11px 12px; border-radius:8px; border:1px solid #d1d5db; font-size:14px;
    }
    .txn-row input:focus,.txn-row select:focus {
      outline:none; border-color:#2563eb; box-shadow:0 0 0 3px rgba(37,99,235,.12);
    }
    .amount-type-row { display:flex; gap:16px; }
    .amount-field { flex:1; display:flex; flex-direction:column; gap:6px; }
    .type-field { width:130px; display:flex; flex-direction:column; gap:6px; justify-content:flex-end; }
    .type-toggle {
      padding:11px 12px; border-radius:8px; font-weight:600; cursor:pointer;
      border:1px solid #e5e7eb; display:flex; align-items:center; justify-content:center; gap:6px;
    }
    .type-toggle.income  { background:#ecfdf5; color:#047857; border-color:#a7f3d0; }
    .type-toggle.expense { background:#fef2f2; color:#b91c1c; border-color:#fecaca; }
    .create-category-row { display:flex; gap:10px; margin-top:8px; }
    .create-category-row input { flex:1; }
    .modal-btn {
      padding:10px 14px; border-radius:8px; cursor:pointer;
      border:1px solid #d1d5db; background:#f3f4f6; font-weight:500;
    }
    .modal-btn:hover { background:#e5e7eb; }
    .modal-btn-primary { background:#2563eb; color:#fff; border:none; }
    .modal-btn-primary:hover { background:#1d4ed8; }
    .txn-actions { display:flex; justify-content:flex-end; gap:10px; margin-top:14px; }
    .errorspan { font-size:12px; color:#b91c1c; min-height:14px; display:block; }
    .balance-pill {
      display:inline-flex; align-items:center; gap:6px;
      padding:5px 10px; border-radius:20px; font-size:12px; font-weight:600; margin-bottom:4px;
    }
    .balance-pill.positive { background:#e6f7ec; color:#0a7d35; }
    .balance-pill.negative { background:#ffe6e9; color:#b00020; }
    .balance-pill.neutral  { background:#f3f4f6; color:#374151; }
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

          <div id="txn-balance-bar" style="margin-bottom:12px;display:none;">
            <span id="txn-balance-pill" class="balance-pill neutral">
              Account balance: <span id="txn-balance-val">—</span>
            </span>
          </div>

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
            <div id="category-list" class="category-list"
                 aria-live="polite" role="list" style="margin-top:8px;"></div>
            <span id="category-error" class="errorspan"></span>
          </div>

          <div class="txn-row">
            <label for="account">Account</label>
            <select id="account">
              <option value="">-- choose account --</option>
              <option value="cash">Cash</option>
              <option value="bank">Bank</option>
              <option value="savings">Savings</option>
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
    modal.addEventListener('click', e => { if (e.target === modal) closeAddModal(); });
    document.body.appendChild(modal);
  }

  function closeAddModal() {
    const m = document.getElementById('txn-modal');
    if (m) m.setAttribute('aria-hidden', 'true');
  }

  // ── Append a new row to the table ────────────────────────────────
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

  // ── Category helpers ─────────────────────────────────────────────
  async function loadCategoriesToSelect() {
    window.__categoryCache = [];
    try {
      const res = await fetch(API.categories);
      if (!res.ok) throw new Error();
      const data = await res.json();
      window.__categoryCache = data.map(c => ({ id: c.id, name: c.name }));
    } catch {
      const cats = new Set();
      document.querySelectorAll('#txTable tbody tr td:nth-child(2)')
              .forEach(td => cats.add(td.textContent.trim()));
      window.__categoryCache = Array.from(cats).map(name => ({ id: name, name }));
    }
    renderCategoryList();
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
    window.__categoryCache.unshift({ id: created.id, name: created.name });
    setSelectedCategory(String(created.id));
    renderCategoryList();
    return created;
  }

  function renderCategoryList() {
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

      item.onclick  = e => { if (!e.target.closest('.trash-btn')) setSelectedCategory(id); };
      item.onkeydown = e => {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setSelectedCategory(id); }
      };
      btn.onclick = async e => {
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
    renderCategoryList();
  }

  // ── Open "Add Transaction" modal ─────────────────────────────────
  async function openTransactionModal() {
    injectModalHTML();
    const modal = document.getElementById('txn-modal');
    if (!modal) return;

    // Reset
    document.getElementById('amount').value               = '';
    document.getElementById('date').value                 = new Date().toISOString().slice(0, 10);
    document.getElementById('account').value              = '';
    document.getElementById('selected-category-id').value = '';
    document.getElementById('new-category-name').value    = '';
    ['amount-error','category-error','account-error','date-error','form-message'].forEach(id => {
      const el = document.getElementById(id);
      if (el) { el.textContent = ''; el.style.color = ''; }
    });

    modal.setAttribute('aria-hidden', 'false');
    await loadCategoriesToSelect();

    // Fetch balances for live balance display
    let balances = {};
    try {
      const r = await fetch(API.balances);
      if (r.ok) balances = await r.json();
    } catch { /* ignore */ }

    let currentType = 'expense';

    function updateBalanceBar() {
      const bar        = document.getElementById('txn-balance-bar');
      const pill       = document.getElementById('txn-balance-pill');
      const val        = document.getElementById('txn-balance-val');
      const accountSel = document.getElementById('account');
      if (!bar || !accountSel) return;

      const selectedAcc = accountSel.value;
      if (currentType === 'expense' && selectedAcc && balances[selectedAcc] !== undefined) {
        const bal = balances[selectedAcc];
        bar.style.display = '';
        val.textContent   = fmt(bal);
        pill.className    = 'balance-pill ' + (bal >= 0 ? 'positive' : 'negative');
      } else {
        bar.style.display = 'none';
      }
    }

    function updateTypeUI() {
      const toggle = document.getElementById('txn-type-toggle');
      const symbol = document.getElementById('txn-type-symbol');
      const lbl    = document.getElementById('txn-type-label');
      if (!toggle) return;
      toggle.className   = 'type-toggle ' + currentType;
      symbol.textContent = currentType === 'income' ? '+' : '\u2212';
      lbl.textContent    = currentType === 'income' ? 'Income' : 'Expense';
      updateBalanceBar();
    }
    updateTypeUI();

    // Wire account select to update balance bar on change
    const accountSel = document.getElementById('account');
    if (accountSel) {
      accountSel.onchange = updateBalanceBar;
    }

    function rebind(id, handler) {
      const old = document.getElementById(id);
      if (!old) return null;
      const fresh = old.cloneNode(true);
      old.parentNode.replaceChild(fresh, old);
      fresh.addEventListener('click', handler);
      return fresh;
    }

    rebind('txn-type-toggle', () => {
      currentType = currentType === 'income' ? 'expense' : 'income';
      updateTypeUI();
    });
    rebind('modal-close-x', closeAddModal);
    rebind('done',          closeAddModal);

    rebind('save-category', async function () {
      const name = (document.getElementById('new-category-name').value || '').trim();
      const err  = document.getElementById('category-error');
      err.textContent = '';
      if (!name) { err.textContent = 'Enter a name'; return; }
      this.disabled = true;
      try {
        await createCategory(name, currentType);
        document.getElementById('new-category-name').value = '';
      } catch (e) {
        err.textContent = e.message || 'Failed';
      } finally { this.disabled = false; }
    });

    rebind('submit-txn', async function () {
      ['amount-error','category-error','account-error','date-error','form-message'].forEach(id => {
        const el = document.getElementById(id);
        if (el) { el.textContent = ''; el.style.color = ''; }
      });

      const amount   = Math.abs(parseFloat(document.getElementById('amount').value));
      const category = document.getElementById('selected-category-id').value;
      const account  = document.getElementById('account').value;
      const date     = document.getElementById('date').value;

      let valid = true;
      if (!Number.isFinite(amount) || amount <= 0) {
        document.getElementById('amount-error').textContent = 'Enter a positive amount'; valid = false;
      }
      if (!category) {
        document.getElementById('category-error').textContent = 'Pick a category'; valid = false;
      }
      if (!account) {
        document.getElementById('account-error').textContent = 'Pick an account'; valid = false;
      }
      if (!date) {
        document.getElementById('date-error').textContent = 'Pick a date'; valid = false;
      }
      if (!valid) return;

      this.disabled    = true;
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
          if (msg) { msg.style.color = 'green'; msg.textContent = 'Saved! Refreshing\u2026'; }
          setTimeout(() => location.reload(), 500);
        } else {
          throw new Error(data.message || 'Server error');
        }
      } catch (err) {
        const msg = document.getElementById('form-message');
        if (msg) { msg.style.color = 'red'; msg.textContent = err.message; }
        const btn = document.getElementById('submit-txn');
        if (btn) { btn.disabled = false; btn.textContent = 'Add'; }
      }
    });
  }

  // ── Transfer modal helpers ────────────────────────────────────────
  function closeTransferModal() {
    const m = document.getElementById('transfer-modal');
    if (m) m.setAttribute('aria-hidden', 'true');
  }

  async function openTransferModal() {
    const modal = document.getElementById('transfer-modal');
    if (!modal) return;

    ['t-from','t-to','t-amount'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.value = '';
    });
    const tDate = document.getElementById('t-date');
    if (tDate) tDate.value = new Date().toISOString().slice(0, 10);
    ['t-from-err','t-to-err','t-amount-err','t-date-err','transfer-msg'].forEach(id => {
      const el = document.getElementById(id);
      if (el) { el.textContent = ''; el.style.color = ''; }
    });

    modal.setAttribute('aria-hidden', 'false');
    await refreshTransferBalances();
  }

  async function refreshTransferBalances() {
    const cashEl    = document.getElementById('t-cash-balance');
    const bankEl    = document.getElementById('t-bank-balance');
    const savingsEl = document.getElementById('t-savings-balance');
    const els = [cashEl, bankEl, savingsEl].filter(Boolean);
    els.forEach(el => el.textContent = '…');

    try {
      const r = await fetch(API.balances);
      if (!r.ok) throw new Error();
      const d = await r.json();
      if (cashEl)    { cashEl.textContent    = fmt(d.cash);    cashEl.style.color    = d.cash    >= 0 ? '#0a7d35' : '#b00020'; }
      if (bankEl)    { bankEl.textContent    = fmt(d.bank);    bankEl.style.color    = d.bank    >= 0 ? '#0a7d35' : '#b00020'; }
      if (savingsEl) { savingsEl.textContent = fmt(d.savings); savingsEl.style.color = d.savings >= 0 ? '#0a7d35' : '#b00020'; }
    } catch {
      els.forEach(el => el.textContent = 'N/A');
    }
  }

  // Transfer modal button delegation
  document.addEventListener('click', async e => {
    if (e.target.id === 'transfer-close' || e.target.id === 'transfer-cancel') {
      closeTransferModal(); return;
    }
    if (e.target.id === 'transfer-modal') {
      closeTransferModal(); return;
    }

    if (e.target.id === 'transfer-submit') {
      const fromAccount = document.getElementById('t-from')?.value;
      const toAccount   = document.getElementById('t-to')?.value;
      const amount      = Math.abs(parseFloat(document.getElementById('t-amount')?.value));
      const date        = document.getElementById('t-date')?.value;

      ['t-from-err','t-to-err','t-amount-err','t-date-err'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.textContent = '';
      });

      let valid = true;
      if (!fromAccount) { document.getElementById('t-from-err').textContent   = 'Select source account';      valid = false; }
      if (!toAccount)   { document.getElementById('t-to-err').textContent     = 'Select destination account'; valid = false; }
      if (fromAccount && toAccount && fromAccount === toAccount) {
                          document.getElementById('t-to-err').textContent     = 'Must differ from source';    valid = false; }
      if (!Number.isFinite(amount) || amount <= 0) {
                          document.getElementById('t-amount-err').textContent = 'Enter a positive amount';    valid = false; }
      if (!date)        { document.getElementById('t-date-err').textContent   = 'Pick a date';                valid = false; }
      if (!valid) return;

      const btn = document.getElementById('transfer-submit');
      btn.disabled    = true;
      btn.textContent = 'Transferring\u2026';

      try {
        const resp = await fetch(API.transfer, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
          body: JSON.stringify({ from_account: fromAccount, to_account: toAccount, amount, date })
        });
        const data = await resp.json();
        if (resp.ok) {
          const msg = document.getElementById('transfer-msg');
          if (msg) { msg.style.color = 'green'; msg.textContent = data.message + ' Refreshing\u2026'; }
          setTimeout(() => location.reload(), 700);
        } else {
          throw new Error(data.message || 'Transfer failed');
        }
      } catch (err) {
        const msg = document.getElementById('transfer-msg');
        if (msg) { msg.style.color = 'red'; msg.textContent = err.message; }
        btn.disabled    = false;
        btn.textContent = 'Transfer';
      }
    }
  });

  // ── Table checkbox + delete ───────────────────────────────────────
  const txTable = document.getElementById('txTable');
  if (txTable) {
    txTable.addEventListener('change', e => {
      const t = e.target;
      if (t.id === 'selectAllVisible') {
        document.querySelectorAll('.row-checkbox').forEach(cb => { cb.checked = t.checked; });
      }
      if (t.classList.contains('row-checkbox') || t.id === 'selectAllVisible') {
        const n   = document.querySelectorAll('.row-checkbox:checked').length;
        const btn = document.getElementById('deleteBtn');
        if (btn) {
          btn.disabled  = n === 0;
          btn.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24"><path fill="currentColor" d="M9 3v1H4v2h16V4h-5V3H9zm2 6v7h2V9h-2zM7 9v7h2V9H7zm8 0v7h2V9h-2z"/></svg> ${n > 0 ? 'Delete (' + n + ')' : 'Delete'}`;
        }
      }
    });
  }

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
        else alert('Delete failed. Please try again.');
      } catch (err) { console.error('Delete error:', err); }
    });
  }

  // ── Button click delegation ───────────────────────────────────────
  document.addEventListener('click', e => {
    if (e.target.closest('#addNewBtn'))   openTransactionModal();
    if (e.target.closest('#transferBtn')) openTransferModal();
  });

  // ── Dropdown filter ───────────────────────────────────────────────
  const dropdownBtn   = document.getElementById('dropdownBtn');
  const dropdownList  = document.getElementById('accountsList');
  const selectedLabel = document.getElementById('selectedLabel');

  if (dropdownBtn && dropdownList) {
    dropdownBtn.addEventListener('click', e => {
      e.stopPropagation();
      const open = dropdownList.classList.toggle('show');
      dropdownBtn.setAttribute('aria-expanded', String(open));
    });

    document.addEventListener('click', e => {
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