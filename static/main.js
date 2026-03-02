// static/main.js
// Handles: modal create, category create, POST transaction, append row, keep modal open,
// and the top-right close "×" button. Requires endpoints:
// GET/POST /api/categories  and  POST /api/transactions
window.__categoryCache = [];
(function () {
  const API = {
    categories: '/api/categories/',
    transactions: '/api/transactions/'
  };

  // --- CSRF helper for Django ---
  function getCookie(name) {
    const v = document.cookie.split('; ').find(row => row.startsWith(name + '='));
    return v ? decodeURIComponent(v.split('=')[1]) : null;
  }
  const CSRF = getCookie('csrftoken');

  // --- inject modal UI (only if not present) ---
  function injectModalHTML() {
    if (document.getElementById('txn-modal')) return;

    const css = `

    /* scrollable selectable category list */
  .category-list {
    display: flex;
    flex-direction: column;
    gap: 8px;
    max-height: 180px;
    overflow: auto;
    padding: 6px;
    border: 1px solid #eef2f6;
    border-radius: 8px;
    background: #ffffff;
  }

  .cat-item {
    display:flex;
    align-items:center;
    justify-content:space-between;
    gap:8px;
    padding:8px 10px;
    border-radius:8px;
    border: 1px solid transparent;
    cursor: pointer;
    transition: background 0.12s, border-color 0.12s, transform 0.06s;
  }

  .cat-item:focus {
    outline: none;
    border-color: #c7d2fe;
    background: #f8fafc;
  }

  .cat-item:hover {
    background: #fafafa;
  }

  .cat-item.selected {
    background: #eef2ff;
    border-color: #c7d2fe;
  }

  .cat-name {
    flex: 1;
    min-width: 0; /* allow ellipsis */
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: 14px;
    color: #111827;
  }

  /* Trash button (already present) */
  .trash-btn {
    background: transparent;
    border: none;
    padding: 6px;
    cursor: pointer;
    border-radius: 6px;
    color: #9ca3af;
  }
  .trash-btn svg { width:16px; height:16px; }
  .trash-btn:hover { background:#fee2e2; color:#dc2626; }

    /* Overlay */
    #txn-modal {
      position: fixed;
      inset: 0;
      background: rgba(15, 23, 42, 0.45);
      display: flex;
      align-items: center;
      justify-content: center;
      z-index: 9999;
      backdrop-filter: blur(6px);
    }

    #txn-modal[aria-hidden="true"] {
      display: none;
    }

    /* Modal Card */
    .txn-dialog {
      background: #ffffff;
      width: 520px;
      max-width: 95%;
      border-radius: 16px;
      padding: 30px 28px;
      position: relative;

      /* Professional layered shadow */
      box-shadow:
        0 25px 70px rgba(0, 0, 0, 0.15),
        0 10px 30px rgba(0, 0, 0, 0.08);

      font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;

      animation: modalFade 0.18s ease-out;
    }

    /* Smooth entry animation */
    @keyframes modalFade {
      from {
        opacity: 0;
        transform: translateY(10px) scale(0.98);
      }
      to {
        opacity: 1;
        transform: translateY(0) scale(1);
      }
    }

    /* Header */
    .txn-dialog h3 {
      margin: 0 0 24px 0;
      font-size: 20px;
      font-weight: 600;
      color: #111827;
    }

    /* Close button */
    .close-x {
      position: absolute;
      right: 18px;
      top: 18px;
      border: none;
      background: transparent;
      font-size: 20px;
      cursor: pointer;
      color: #6b7280;
      transition: 0.2s;
    }

    .close-x:hover {
      color: #111827;
    }

    /* Form layout */
    .txn-row {
      display: flex;
      flex-direction: column;
      gap: 6px;
      margin-bottom: 18px;
    }

    .txn-row label {
      font-size: 13px;
      font-weight: 500;
      color: #374151;
    }

    /* Inputs */
    .txn-row input,
    .txn-row select {
      padding: 11px 12px;
      border-radius: 8px;
      border: 1px solid #d1d5db;
      font-size: 14px;
      transition: 0.2s;
    }

    .txn-row input:focus,
    .txn-row select:focus {
      outline: none;
      border-color: #2563eb;
      box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12);
    }

    /* Amount + Type inline row */
    .amount-type-row {
      display: flex;
      gap: 16px;
    }

    .amount-field {
      flex: 1;
    }

    .type-field {
      width: 130px;
      display: flex;
      flex-direction: column;
      justify-content: flex-end;
    }

    /* Toggle Button */
    .type-toggle {
      padding: 11px 12px;
      border-radius: 8px;
      font-weight: 600;
      cursor: pointer;
      border: 1px solid #e5e7eb;
      background: #f9fafb;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      transition: 0.2s ease;
    }

    .type-toggle.income {
      background: #ecfdf5;
      color: #047857;
      border-color: #a7f3d0;
    }

    .type-toggle.expense {
      background: #fef2f2;
      color: #b91c1c;
      border-color: #fecaca;
    }

    /* Category create row */
    .create-category-row {
      display: flex;
      gap: 10px;
      margin-top: 8px;
    }

    .create-category-row input {
      flex: 1;
    }

    /* Buttons */
    .btn {
      padding: 10px 14px;
      border-radius: 8px;
      cursor: pointer;
      border: 1px solid #d1d5db;
      background: #f3f4f6;
      font-weight: 500;
      transition: 0.2s;
    }

    .btn:hover {
      background: #e5e7eb;
    }

    .btn-primary {
      background: #2563eb;
      color: white;
      border: none;
    }

    .btn-primary:hover {
      background: #1d4ed8;
    }

    /* Footer */
    .txn-actions {
      display: flex;
      justify-content: flex-end;
      gap: 10px;
      margin-top: 14px;
    }

    /* Errors */
    .errorspan {
      font-size: 12px;
      color: #b91c1c;
      min-height: 14px;
    }


    /* Category item row */
    .cat-item {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 6px 8px;
      border-radius: 8px;
      transition: 0.2s ease;
    }

    .cat-item:hover {
      background: #f9fafb;
    }

    /* Dustbin button */
    .trash-btn {
      background: transparent;
      border: none;
      padding: 6px;
      cursor: pointer;
      border-radius: 6px;
      display: flex;
      align-items: center;
      justify-content: center;
      color: #9ca3af; /* soft gray */
      transition: 0.2s ease;
    }

    /* Make the SVG icon visible */
    .trash-btn svg {
      width: 16px;
      height: 16px;
    }

    /* Hover effect */
    .trash-btn:hover {
      background: #fee2e2;
      color: #dc2626; /* red */
    }

    /* Optional click effect */
    .trash-btn:active {
      transform: scale(0.92);
    }
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
                <span id="txn-type-symbol">−</span>
                <span id="txn-type-label">Expense</span>
              </button>
            </div>
          </div>

          <div class="txn-row">
            <label for="category">Category</label>

            <!-- Hidden holder for selected category id (used by submit) -->
            <input type="hidden" id="selected-category-id" value="">

            <!-- top controls: name input + save button -->
            <div class="create-category-row">
              <input id="new-category-name" type="text" placeholder="New category name" />
              <button type="button" id="save-category" class="btn">Save</button>
            </div>

            <!-- Scrollable category list used for selection + deletion -->
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

          <div id="form-message" class="small" style="min-height:16px;margin-bottom:6px;"></div>

          <div class="txn-actions">
            <button type="button" id="submit-txn" class="btn btn-primary">Add</button>
            <button type="button" id="done" class="btn">Done</button>
          </div>
        </form>
      </div>
    `;

    // background click closes
    modal.addEventListener('click', (e) => {
      if (e.target === modal) modal.setAttribute('aria-hidden', 'true');
    });

    document.body.appendChild(modal);
  }

  // --- append new row to table (client-side) ---
// Change the function signature to include 'id'
function appendRowToTable({ id, date, category, amount, account, type }) {
  const table = document.getElementById('txTable');
  if (!table) return;
  const tbody = table.querySelector('tbody') || table.appendChild(document.createElement('tbody'));
  const tr = document.createElement('tr');
  
  // 1. Set the data-type attribute so CSS styling kicks in
  tr.setAttribute('data-type', type); 

  const sign = type === 'income' ? '+' : '−';
  
  tr.innerHTML = `
    <td>${date}</td>
    <td>${category}</td>
    <td><span class="amount-cell">${sign}${Number(amount).toFixed(2)}</span></td>
    <td>${account.charAt(0).toUpperCase() + account.slice(1)}</td>
    <td class="select-cell">
      <input type="checkbox" class="row-checkbox" data-id="${id}">
    </td>
  `;
  tbody.prepend(tr);
}

  // --- load categories (GET) ---
  async function loadCategoriesToSelect() {
    window.__categoryCache = [];
    try {
      const res = await fetch(API.categories);
      if (!res.ok) throw new Error('no categories');
      const data = await res.json();
      // cache for renderCategoryListFromSelect
      window.__categoryCache = data.map(c => ({ id: c.id, name: c.name }));
      // if you still have a select element (fallback), update it too
      const sel = document.getElementById('category');
      if (sel) {
        sel.innerHTML = '<option value="">-- Select category --</option>';
        data.forEach(c => {
          const opt = document.createElement('option');
          opt.value = String(c.id);
          opt.textContent = c.name;
          sel.appendChild(opt);
        });
      }
      renderCategoryListFromSelect();
    } catch (err) {
      // fallback: try extract from table
      const fallback = extractCategoriesFromTable();
      window.__categoryCache = fallback.map(c => ({ id: c.id, name: c.name }));
      renderCategoryListFromSelect();
    }
  }

  function extractCategoriesFromTable() {
    const cats = new Set();
    const table = document.getElementById('txTable');
    if (!table) return [];
    const rows = table.querySelectorAll('tbody tr');
    rows.forEach(r => {
      const td = r.querySelectorAll('td')[1];
      if (td) cats.add(td.textContent.trim());
    });
    return Array.from(cats).map(name => ({ id: name, name }));
  }

  // --- create category (POST) ---
  async function createCategory(name, type) {
    try {
      const res = await fetch(API.categories, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF },
        body: JSON.stringify({ 
          name: name,
          type: type
        })
      });
      if (!res.ok) {
        const body = await res.json().catch(()=>({message:'error'}));
        throw new Error(body.message || 'Failed to create');
      }
      const created = await res.json();
      // Add to cache
      if (!window.__categoryCache) window.__categoryCache = [];
      window.__categoryCache.push({
          id: created.id,
          name: created.name
      });

      // Auto-select newly created category
      setSelectedCategory(String(created.id));

      // Re-render list
      renderCategoryListFromSelect();
      return created;
    } catch (err) {
      throw err;
    }
  }

  // Render the list of categories as selectable rows (used for selection + deletion)
 function renderCategoryListFromSelect() {
  const list = document.getElementById('category-list');
  if (!list) return;

  list.innerHTML = '';

  const categories = window.__categoryCache || [];
  const selectedId = document.getElementById('selected-category-id')?.value || '';

  categories.forEach(cat => {
    const id = String(cat.id);
    const name = cat.name;

    const item = document.createElement('div');
    item.className = 'cat-item';
    item.setAttribute('role', 'button');
    item.setAttribute('tabindex', '0');
    item.dataset.id = id;

    const nameSpan = document.createElement('div');
    nameSpan.className = 'cat-name';
    nameSpan.textContent = name;

    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'trash-btn';
    btn.dataset.val = id;
    btn.innerHTML = `🗑`;

    item.onclick = (e) => {
      if (e.target.closest('.trash-btn')) return;
      setSelectedCategory(id);
    };

    item.onkeydown = (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        setSelectedCategory(id);
      }
    };

    btn.onclick = async (e) => {
      e.stopPropagation();
      await deleteCategoryByValue(id, name);
    };

    item.appendChild(nameSpan);
    item.appendChild(btn);

    if (id === selectedId) item.classList.add('selected');

    list.appendChild(item);
  });
}

  function setSelectedCategory(id) {
    const hid = document.getElementById('selected-category-id');
    const list = document.getElementById('category-list');
    if (hid) hid.value = id || '';

    if (!list) return;

    // Remove previous selection
    list.querySelectorAll('.cat-item.selected')
        .forEach(el => el.classList.remove('selected'));

    if (!id) return;

    const matched = list.querySelector(
        `.cat-item[data-id="${CSS.escape(id)}"]`
    );

    if (matched) {
        matched.classList.add('selected');
        matched.scrollIntoView({ block: 'nearest' });
    }
  }

  // Delete category by the option value (id or unique name)
  async function deleteCategoryByValue(val, displayName) {
    if (!val) return;
    if (!confirm(`Delete category "${displayName}"? This cannot be undone.`)) return;
    const url = API.categories + encodeURIComponent(val) + '/';
    try {
      const res = await fetch(url, {
        method: 'DELETE',
        headers: { 'X-CSRFToken': CSRF }
      });
      if (!res.ok) {
        const body = await res.json().catch(()=>({message:'Delete failed'}));
        throw new Error(body.message || 'Failed to delete');
      }
      // remove option from select
      // Remove from cache
      window.__categoryCache = window.__categoryCache.filter(c => String(c.id) !== String(val));

      // Clear selection if deleted category was selected
      const selectedInput = document.getElementById('selected-category-id');
      if (selectedInput.value === String(val)) {
          selectedInput.value = '';
      }

      // Re-render list
      renderCategoryListFromSelect();
    } catch (err) {
      console.error('Category delete error:', err);
      alert('Failed to delete category: ' + (err.message || 'unknown'));
    }
  }

  // Delegated click handler for trash buttons
  document.addEventListener('click', (e) => {
    const btn = e.target.closest && e.target.closest('.trash-btn');
    if (!btn) return;
    const val = btn.getAttribute('data-val');
    const name = btn.parentElement && btn.parentElement.querySelector('.cat-name')?.textContent;
    // disable while deleting
    btn.disabled = true;
    deleteCategoryByValue(val, name).finally(() => { btn.disabled = false; });
  });

  // --- submit transaction (POST) ---
  async function submitTransaction(payload) {
    const res = await fetch(API.transactions, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF },
      body: JSON.stringify(payload)
    });
    if (!res.ok) {
      const body = await res.json().catch(()=>({message:'error'}));
      throw new Error(body.message || 'Failed to add');
    }
    return await res.json();
  }

  // --- open modal and wire UI ---
  async function openTransactionModal() {
    injectModalHTML();
    const modal = document.getElementById('txn-modal');
    if (!modal) return;
    modal.setAttribute('aria-hidden', 'false');

    // set default date
    const dateInput = document.getElementById('date');
    dateInput.value = new Date().toISOString().slice(0,10);

    // populate categories
    await loadCategoriesToSelect();

    // default type: expense
    let currentType = 'expense';

    // ensure toggle exists (we created it in the modal HTML above)
    const typeToggle = document.getElementById('txn-type-toggle');
    const typeSymbol = document.getElementById('txn-type-symbol');
    const typeLabel = document.getElementById('txn-type-label');

    function updateTypeUI() {
      if (!typeToggle) return;
      if (currentType === 'income') {
        typeToggle.classList.remove('expense');
        typeToggle.classList.add('income');
        typeToggle.setAttribute('aria-pressed', 'true');
        typeSymbol.textContent = '+'; // plus sign for income
        typeLabel.textContent = 'Income';
      } else {
        typeToggle.classList.remove('income');
        typeToggle.classList.add('expense');
        typeToggle.setAttribute('aria-pressed', 'false');
        typeSymbol.textContent = '−'; // minus sign for expense
        typeLabel.textContent = 'Expense';
      }
    }
    // initialize UI
    updateTypeUI();

    // toggle handler
    if (typeToggle) {
      typeToggle.onclick = () => {
        currentType = currentType === 'income' ? 'expense' : 'income';
        updateTypeUI();
        // optional: focus amount input after toggle
        const amt = document.getElementById('amount');
        if (amt) amt.focus();
      };
    }

    // show trash icons list
    renderCategoryListFromSelect();

    // wire small handlers (idempotent)
    document.getElementById('modal-close-x').onclick = () => modal.setAttribute('aria-hidden','true');
    document.getElementById('done').onclick = () => modal.setAttribute('aria-hidden','true');

    // create category save
    const saveCatBtn = document.getElementById('save-category');
    saveCatBtn.onclick = async () => {
      const name = (document.getElementById('new-category-name').value || '').trim();
      const errSpan = document.getElementById('category-error');
      errSpan.textContent = '';
      if (!name) { errSpan.textContent = 'Enter a name'; return; }
      saveCatBtn.disabled = true;
      try {
        await createCategory(name, currentType);
        document.getElementById('new-category-name').value = '';
      } catch (err) {
        errSpan.textContent = err.message || 'Failed';
      } finally { saveCatBtn.disabled = false; }
    };

    // submit handler
    const submitBtn = document.getElementById('submit-txn');
// --- Updated submit handler in static/main.js ---
    submitBtn.onclick = async () => {
        // 1. Clear previous error messages
        ['amount-error', 'category-error', 'account-error', 'date-error', 'form-message'].forEach(id => {
            const el = document.getElementById(id); 
            if (el) el.textContent = '';
        });

        // 2. Collect and validate data
        let rawAmount = document.getElementById('amount').value;
        const amount = Math.abs(parseFloat(rawAmount));
        const category = document.getElementById('selected-category-id').value;
        const account = document.getElementById('account').value;
        const date = document.getElementById('date').value;
        const type = currentType; // 'income'|'expense'

        let isValid = true;
        if (!Number.isFinite(amount) || amount <= 0) { document.getElementById('amount-error').textContent = 'Enter a positive amount'; isValid = false; }
        if (!category) { document.getElementById('category-error').textContent = 'Pick category'; isValid = false; }
        if (!account) { document.getElementById('account-error').textContent = 'Pick account'; isValid = false; }
        if (!date) { document.getElementById('date-error').textContent = 'Pick date'; isValid = false; }
        if (!isValid) return;


        // 3. UI Feedback: Disable button to prevent double-clicks
        submitBtn.disabled = true;
        submitBtn.textContent = 'Saving...';

        try {
          const response = await fetch(API.transactions, {
              method: 'POST',
              headers: {
                  'Content-Type': 'application/json',
                  'X-CSRFToken': getCookie('csrftoken')
              },
              body: JSON.stringify({ 
                  amount, 
                  category, 
                  account, 
                  date, 
                  type   // <-- THIS WAS MISSING
              })
          });

            const data = await response.json();

            if (response.ok) {
                // SUCCESS: Only reload once we have the confirmation from Django
                console.log("Transaction saved:", data);
                document.getElementById('form-message').style.color = "green";
                document.getElementById('form-message').textContent = "Saved! Refreshing...";
                
                // Short delay so the user see the success message
                setTimeout(() => {
                    location.reload(); 
                }, 500);
            } else {
                // SERVER ERROR: Show the error message from your views.py
                throw new Error(data.message || "Server rejected the transaction");
            }

        } catch (error) {
            console.error("Submission failed:", error);
            const msgEl = document.getElementById('form-message');
            if (msgEl) {
                msgEl.style.color = "red";
                msgEl.textContent = error.message;
            }
            // Re-enable button so the user can fix the error and try again
            submitBtn.disabled = false;
            submitBtn.textContent = 'Add';
        }
    };
  }

  // 1. Handle enabling/disabling the Delete button
  document.getElementById('txTable').addEventListener('change', (e) => {
      if (e.target.classList.contains('row-checkbox') || e.target.id === 'selectAllVisible') {
          const checkedCount = document.querySelectorAll('.row-checkbox:checked').length;
          const deleteBtn = document.getElementById('deleteBtn');
          deleteBtn.disabled = checkedCount === 0;
          deleteBtn.innerHTML = checkedCount > 0 ? `Delete (${checkedCount})` : 'Delete';
      }
  });

  // 2. Handle the actual Delete API call
  document.getElementById('deleteBtn').onclick = async () => {
      const selectedCbs = document.querySelectorAll('.row-checkbox:checked');
      const idsToDelete = Array.from(selectedCbs).map(cb => cb.getAttribute('data-id'));

      if (!idsToDelete.length || !confirm("Are you sure you want to delete these?")) return;

      try {
          // You'll need an endpoint in views.py like 'api/transactions/delete/'
          const response = await fetch('/api/transactions/delete/', {
              method: 'POST',
              headers: {
                  'Content-Type': 'application/json',
                  'X-CSRFToken': getCookie('csrftoken')
              },
              body: JSON.stringify({ ids: idsToDelete })
          });

          if (response.ok) {
              location.reload(); // Refresh to show updated list from DB
          } else {
              alert("Failed to delete. Check console.");
          }
      } catch (err) {
          console.error("Delete error:", err);
      }
  };

  // open on button click (delegated to support icons/text inside button)
  document.addEventListener('click', (e) => {
      if (e.target.closest && e.target.closest('#addNewBtn')) {
      openTransactionModal();
      }
    });

    // Initialize: no heavy load required
    document.addEventListener('DOMContentLoaded', () => {
      // nothing to do yet
    });

  // Add this inside your (function() { ... })()
  document.getElementById('txTable').addEventListener('change', (e) => {
      if (e.target.id === 'selectAllVisible') {
          const isChecked = e.target.checked;
          document.querySelectorAll('.row-checkbox').forEach(cb => {
              cb.checked = isChecked;
              // Manually trigger change for the delete button listener
              cb.dispatchEvent(new Event('change', { bubbles: true }));
          });
      }
  });

  // -----------------------------
  // Dropdown Filter (Income/Expense)
  // -----------------------------

  document.addEventListener('DOMContentLoaded', () => {
    const dropdownBtn = document.getElementById('dropdownBtn');
    const dropdownList = document.getElementById('accountsList');
    const selectedLabel = document.getElementById('selectedLabel');

    if (!dropdownBtn || !dropdownList) return;

    // Toggle dropdown open/close
    dropdownBtn.addEventListener('click', () => {
      const isOpen = dropdownList.classList.toggle('show');
      dropdownBtn.setAttribute('aria-expanded', isOpen);
    });

    // Close if clicked outside
    document.addEventListener('click', (e) => {
      if (!e.target.closest('#accountsDropdown')) {
        dropdownList.classList.remove('show');
        dropdownBtn.setAttribute('aria-expanded', 'false');
      }
    });

    // Option selection
    dropdownList.querySelectorAll('.dropdown__option').forEach(option => {
      option.addEventListener('click', () => {
        const value = option.dataset.value;
        const label = option.textContent;

        selectedLabel.textContent = label;

        filterTransactions(value);

        dropdownList.classList.remove('show');
        dropdownBtn.setAttribute('aria-expanded', 'false');
      });
    });
  });

  function filterTransactions(filterType) {
    const rows = document.querySelectorAll('#txTable tbody tr');

    rows.forEach(row => {
      const rowType = row.getAttribute('data-type'); // 'income' or 'expense'

      if (filterType === 'all') {
        row.style.display = '';
      } else {
        // Direct comparison is much faster and safer than parsing text
        row.style.display = (rowType === filterType) ? '' : 'none';
      }
    });
  }
})();