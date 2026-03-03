(function () {
    const API = {
        categories: '/api/categories/',
        transactions: '/api/transactions/',
        deleteTransactions: '/api/transactions/delete/'
    };

    // --- State & Helpers ---
    window.__categoryCache = [];
    let currentType = 'expense';

    function getCookie(name) {
        const v = document.cookie.split('; ').find(row => row.startsWith(name + '='));
        return v ? decodeURIComponent(v.split('=')[1]) : null;
    }
    const CSRF = getCookie('csrftoken');

    // --- Core Functions ---
    async function loadCategories() {
        try {
            const res = await fetch(API.categories);
            if (!res.ok) throw new Error('Could not fetch categories');
            const data = await res.json();
            window.__categoryCache = data.map(c => ({ id: c.id, name: c.name }));
            renderCategoryList();
        } catch (err) {
            window.__categoryCache = extractCategoriesFromTable();
            renderCategoryList();
        }
    }

    function extractCategoriesFromTable() {
        const cats = new Set();
        document.querySelectorAll('#txTable tbody tr').forEach(r => {
            const td = r.querySelectorAll('td')[1];
            if (td) cats.add(td.textContent.trim());
        });
        return Array.from(cats).map(name => ({ id: name, name }));
    }

    function renderCategoryList() {
        const list = document.getElementById('category-list');
        const selectedId = document.getElementById('selected-category-id')?.value || '';
        if (!list) return;
        list.innerHTML = '';
        window.__categoryCache.forEach(cat => {
            const item = document.createElement('div');
            item.className = `cat-item ${String(cat.id) === selectedId ? 'selected' : ''}`;
            item.innerHTML = `<div class="cat-name">${cat.name}</div><button type="button" class="trash-btn">🗑</button>`;
            item.onclick = (e) => {
                if (e.target.closest('.trash-btn')) {
                    handleCategoryDelete(cat.id, cat.name);
                } else {
                    const hiddenInput = document.getElementById('selected-category-id');
                    if (hiddenInput) hiddenInput.value = String(cat.id);
                    renderCategoryList();
                }
            };
            list.appendChild(item);
        });
    }

    async function handleCategoryDelete(id, name) {
        if (!confirm(`Delete category "${name}"?`)) return;
        try {
            await fetch(`${API.categories}${encodeURIComponent(id)}/`, { method: 'DELETE', headers: { 'X-CSRFToken': CSRF } });
            window.__categoryCache = window.__categoryCache.filter(c => String(c.id) !== String(id));
            renderCategoryList();
        } catch (err) { alert(err.message); }
    }

    function updateTypeUI() {
        const toggle = document.getElementById('txn-type-toggle');
        const isIncome = currentType === 'income';
        if (toggle) {
            toggle.className = `type-toggle ${currentType}`;
            document.getElementById('txn-type-symbol').textContent = isIncome ? '+' : '−';
            document.getElementById('txn-type-label').textContent = isIncome ? 'Income' : 'Expense';
        }
    }

    function updateDeleteButton() {
        const checked = document.querySelectorAll('.row-checkbox:checked').length;
        const btn = document.getElementById('deleteBtn');
        if (btn) {
            btn.disabled = checked === 0;
            btn.innerHTML = checked > 0 ? `Delete (${checked})` : 'Delete';
        }
    }

    // --- Initialization ---
    document.addEventListener('DOMContentLoaded', () => {
        const dropdownBtn = document.getElementById('dropdownBtn');
        const dropdownContainer = document.getElementById('accountsDropdown');
        const options = document.querySelectorAll('.dropdown__option');
        const selectedLabel = document.getElementById('selectedLabel');
        const modal = document.getElementById('txn-modal');

        // 1. Dropdown Toggle
        dropdownBtn?.addEventListener('click', (e) => {
            e.stopPropagation();
            const isOpen = dropdownContainer.classList.toggle('is-open');
            dropdownBtn.setAttribute('aria-expanded', isOpen);
        });

        // 2. Selection & Filtering
        options.forEach(option => {
            option.addEventListener('click', function() {
                const val = this.getAttribute('data-value');
                selectedLabel.textContent = this.textContent.trim();
                dropdownContainer.classList.remove('is-open');
                
                document.querySelectorAll('#txTable tbody tr').forEach(row => {
                    const type = row.getAttribute('data-type');
                    row.style.display = (val === 'all' || type === val) ? '' : 'none';
                });
            });
        });

        // 3. Modal & Form Controls
        document.getElementById('addNewBtn')?.addEventListener('click', () => {
            modal.setAttribute('aria-hidden', 'false');
            document.getElementById('date').value = new Date().toISOString().slice(0, 10);
            loadCategories();
            updateTypeUI();
        });

        document.getElementById('modal-close-x')?.addEventListener('click', () => modal.setAttribute('aria-hidden', 'true'));
        
        document.getElementById('txn-type-toggle')?.addEventListener('click', () => {
            currentType = currentType === 'income' ? 'expense' : 'income';
            updateTypeUI();
        });

        // 4. Bulk Actions
        document.getElementById('selectAllVisible')?.addEventListener('change', (e) => {
            document.querySelectorAll('.row-checkbox').forEach(cb => {
                if (cb.closest('tr').style.display !== 'none') cb.checked = e.target.checked;
            });
            updateDeleteButton();
        });

        document.getElementById('txTable')?.addEventListener('change', (e) => {
            if (e.target.classList.contains('row-checkbox')) updateDeleteButton();
        });

        // Close dropdown on outside click
        document.addEventListener('click', () => {
            dropdownContainer?.classList.remove('is-open');
            dropdownBtn?.setAttribute('aria-expanded', 'false');
        });
    });
})();