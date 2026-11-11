
let currentItems = [];
let currentSection = 'dashboard';
let salesChartInstance = null;
let pieChartInstance = null;
let salesPage = 1;
const SALES_PAGE_SIZE = 50;
let salesTotalCount = 0;
const salesDateFormatter = new Intl.DateTimeFormat(undefined, {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
});
let mlGraphObjectUrls = [];

function getAuthHeaders() {
    return {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${localStorage.getItem('inventory_token')}`
    };
}

function getAuthHeadersOnly() {
    return {
        'Authorization': `Bearer ${localStorage.getItem('inventory_token')}`
    };
}

document.addEventListener('DOMContentLoaded', () => {
    if (!localStorage.getItem('inventory_token')) {
        document.getElementById('login-overlay').classList.remove('hidden');
    } else {
        document.getElementById('login-overlay').classList.add('hidden');
        initDashboard();
    }

    document.getElementById('login-form').addEventListener('submit', async (e) => {
        e.preventDefault();

        const u = document.getElementById('login-username').value;
        const p = document.getElementById('login-password').value;

        try {
            const res = await fetch('/api/login', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({username: u, password: p})
            });

            if (res.ok) {
                const data = await res.json();

                localStorage.setItem('inventory_token', data.access_token);
                localStorage.setItem('inventory_role', data.role);

                document.getElementById('login-overlay').classList.add('hidden');
                initDashboard();
            } else {
                alert('Invalid credentials');
            }
        } catch (err) {
            console.error(err);
        }
    });

    document.getElementById('search-input').addEventListener('input', () => {
        if (currentSection === 'sales-history') {
            salesPage = 1;
            fetchGlobalSalesHistory();
        } else {
            fetchItems();
        }
    });
    document.getElementById('category-filter').addEventListener('change', () => {
        if (currentSection === 'sales-history') {
            salesPage = 1;
            fetchGlobalSalesHistory();
        } else {
            fetchItems();
        }
    });

    document.getElementById('add-form').addEventListener('submit', handleAdd);
    document.getElementById('edit-form').addEventListener('submit', handleEdit);
    document.getElementById('action-form').addEventListener('submit', handleAction);
    document.getElementById('add-user-form').addEventListener('submit', handleAddUser);
});

function logout() {
    localStorage.removeItem('inventory_token');
    localStorage.removeItem('inventory_role');
    location.reload();
}

function initDashboard() {
    const role = localStorage.getItem('inventory_role');

    if (role === 'admin') {
        document.getElementById('nav-users').style.display = 'block';
        document.getElementById('btn-add-item').style.display = 'inline-block';
        fetchUsers();
    } else {
        document.getElementById('nav-users').style.display = 'none';
        document.getElementById('btn-add-item').style.display = 'none';
    }

    fetchSummary();
    fetchItems();
}


function showSection(sectionId, e) {
    currentSection = sectionId;

    document.querySelectorAll('.nav-links li').forEach(li => {
        li.classList.remove('active');
    });

    if (e) {
        e.preventDefault();
        const li = e.currentTarget.closest('li');
        if (li) li.classList.add('active');
    } else {
        const link = document.querySelector(`.nav-links a[onclick*="'${sectionId}'"]`);
        if (link) {
            const li = link.closest('li');
            if (li) li.classList.add('active');
        }
    }

    const sections = {
        dashboard: 'dashboard-section',
        inventory: 'inventory-section',
        'sales-history': 'sales-history-section',
        users: 'users-section',
        'ml-evaluation': 'ml-evaluation-section'
    };

    Object.values(sections).forEach(id => {
        const section = document.getElementById(id);
        if (section) section.style.display = 'none';
    });

    const targetId = sections[sectionId];
    const target = targetId ? document.getElementById(targetId) : null;

    if (!target) {
        console.error('Section not found:', sectionId, targetId);
        return;
    }

    target.style.display = 'block';

    if (sectionId === 'sales-history') {
        fetchGlobalSalesHistory();
    }

    if (sectionId === 'ml-evaluation') {
        fetchMLEvaluation();
    }
}



function changeSalesPage(delta) {
    const totalPages = Math.max(1, Math.ceil(salesTotalCount / SALES_PAGE_SIZE));
    const nextPage = Math.min(totalPages, Math.max(1, salesPage + delta));
    if (nextPage !== salesPage) {
        salesPage = nextPage;
        fetchGlobalSalesHistory();
    }
}

async function fetchGlobalSalesHistory() {
    const tbody = document.getElementById('sales-history-body');

    if (!tbody) {
        console.error('sales-history-body element not found');
        return;
    }

    const search = document.getElementById('search-input')?.value.trim() || '';
    const category = document.getElementById('category-filter')?.value || 'All';

    tbody.innerHTML = `
        <tr>
            <td colspan="5" style="text-align:center;">Loading sales history...</td>
        </tr>
    `;

    try {
        const params = new URLSearchParams();
        if (search) params.set('search', search);
        if (category && category !== 'All') params.set('category', category);

        const summaryUrl = `/sales/summary?${params.toString()}`;
        params.set('skip', String((salesPage - 1) * SALES_PAGE_SIZE));
        params.set('limit', String(SALES_PAGE_SIZE));
        const listUrl = `/sales/?${params.toString()}`;

        const [summaryRes, listRes] = await Promise.all([
            fetch(summaryUrl, {method: 'GET', headers: getAuthHeadersOnly()}),
            fetch(listUrl, {method: 'GET', headers: getAuthHeadersOnly()})
        ]);

        if (summaryRes.status === 401 || listRes.status === 401) {
            logout();
            return;
        }

        if (!listRes.ok) {
            throw new Error(`Server error: ${listRes.status}`);
        }

        let sales = await listRes.json();

        if (!Array.isArray(sales)) {
            throw new Error('Invalid sales history response');
        }

        let totalUnits = 0;
        let totalRev = 0;

        if (summaryRes.ok) {
            const summary = await summaryRes.json();
            salesTotalCount = Number(summary.total_count ?? sales.length);
            totalUnits = Number(summary.total_units ?? 0);
            totalRev = Number(summary.total_revenue ?? 0);
        } else {
            // Fallback if backend hasn't been restarted with /sales/summary yet
            salesTotalCount = sales.length;
            sales.forEach(s => {
                totalUnits += Number(s.quantity_sold ?? 0);
                totalRev += Number(s.total_revenue ?? 0);
            });
            const start = (salesPage - 1) * SALES_PAGE_SIZE;
            sales = sales.slice(start, start + SALES_PAGE_SIZE);
        }

        const countEl = document.getElementById('sales-total-count');
        const unitsEl = document.getElementById('sales-total-units');
        const revEl = document.getElementById('sales-total-revenue');

        if (countEl) countEl.innerText = salesTotalCount.toLocaleString();
        if (unitsEl) unitsEl.innerText = totalUnits.toLocaleString();
        if (revEl) revEl.innerText = `₹${totalRev.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;

        const totalPages = Math.max(1, Math.ceil(salesTotalCount / SALES_PAGE_SIZE));
        const startIdx = salesTotalCount === 0 ? 0 : (salesPage - 1) * SALES_PAGE_SIZE + 1;
        const endIdx = Math.min(salesTotalCount, (salesPage - 1) * SALES_PAGE_SIZE + sales.length);

        const pageInfoEl = document.getElementById('sales-page-info');
        const pageNumEl = document.getElementById('sales-page-num');
        const prevBtn = document.getElementById('sales-prev-btn');
        const nextBtn = document.getElementById('sales-next-btn');

        if (pageInfoEl) pageInfoEl.innerText = `Showing ${startIdx}–${endIdx} of ${salesTotalCount.toLocaleString()} records`;
        if (pageNumEl) pageNumEl.innerText = `Page ${salesPage} of ${totalPages}`;
        if (prevBtn) prevBtn.disabled = salesPage <= 1;
        if (nextBtn) nextBtn.disabled = salesPage >= totalPages;

        tbody.innerHTML = '';

        if (sales.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="5" style="text-align:center; padding: 2rem;">
                        No sales records found${search ? ' matching "' + search + '"' : ''}.
                    </td>
                </tr>
            `;
            return;
        }

        const fragment = document.createDocumentFragment();
        sales.forEach(s => {
            const tr = document.createElement('tr');

            let formattedDate = '-';
            if (s.sale_date) {
                const safeDateStr = s.sale_date.includes('T') ? s.sale_date : s.sale_date.replace(' ', 'T');
                const parsed = new Date(safeDateStr);
                formattedDate = isNaN(parsed.getTime()) ? s.sale_date : salesDateFormatter.format(parsed);
            }

            const values = [
                `#${s.id ?? '-'}`,
                formattedDate,
                s.item_name ?? '-',
                s.quantity_sold ?? 0,
                `₹${Number(s.total_revenue ?? 0).toFixed(2)}`
            ];

            values.forEach(value => {
                const td = document.createElement('td');
                td.textContent = value;
                tr.appendChild(td);
            });

            fragment.appendChild(tr);
        });
        tbody.appendChild(fragment);

    } catch (error) {
        console.error('Sales History Error:', error);

        tbody.innerHTML = `
            <tr>
                <td colspan="5" style="text-align:center;color:red;">
                    Unable to load sales history. Please refresh and try again.
                </td>
            </tr>
        `;
    }
}


async function fetchSummary() {
    try {
        const res = await fetch('/summary/categories', {headers: getAuthHeadersOnly()});

        if (res.status === 401) {
            logout();
            return;
        }

        if (!res.ok) throw new Error('Unable to load summary');

        const data = await res.json();
        const container = document.getElementById('summary-cards');

        container.innerHTML = '';

        let totalVal = 0;
        let totalItems = 0;

        data.forEach(cat => {
            totalVal += Number(cat.total_value);
            totalItems += Number(cat.total_stock);
        });

        container.innerHTML += `
            <div class="card">
                <h4>Total Inventory Value</h4>
                <div class="val">₹${totalVal.toFixed(2)}</div>
            </div>
            <div class="card">
                <h4>Total Stock Items</h4>
                <div class="val">${totalItems}</div>
            </div>
        `;

        data.forEach(cat => {
            container.innerHTML += `
                <div class="card">
                    <h4>${cat.category}</h4>
                    <div class="val">${cat.total_stock}
                        <span style="font-size:0.9rem;color:#64748b;font-weight:400;">items</span>
                    </div>
                </div>
            `;
        });

        renderPieChart(
            data.map(c => c.category),
            data.map(c => c.total_stock)
        );
    } catch (e) {
        console.error(e);
    }
}

function renderPieChart(labels, data) {
    const canvas = document.getElementById('categoryPieChart');
    if (!canvas) return;

    const ctx = canvas.getContext('2d');

    if (pieChartInstance) pieChartInstance.destroy();

    pieChartInstance = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels,
            datasets: [{
                data,
                backgroundColor: ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6'],
                borderWidth: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {legend: {position: 'right'}}
        }
    });
}

async function fetchItems() {
    const search = document.getElementById('search-input').value;
    const category = document.getElementById('category-filter').value;

    let url = '/items/?limit=500';

    if (search) url += `&search=${encodeURIComponent(search)}`;
    if (category && category !== 'All') {
        url += `&category=${encodeURIComponent(category)}`;
    }

    try {
        const res = await fetch(url, {headers: getAuthHeadersOnly()});

        if (res.status === 401) {
            logout();
            return;
        }

        if (!res.ok) throw new Error('Unable to load inventory');

        currentItems = await res.json();
        renderTable();
    } catch (e) {
        console.error(e);
    }
}

function renderTable() {
    const tbody = document.getElementById('inventory-body');
    tbody.innerHTML = '';

    const role = localStorage.getItem('inventory_role');

    currentItems.forEach(item => {
        let statusBadge = '';

        if (item.stock_quantity === 0) {
            statusBadge = '<span class="badge badge-out">Out of Stock</span>';
        } else if (item.stock_quantity <= item.reorder_level) {
            statusBadge = '<span class="badge badge-low">Low Stock</span>';
        } else {
            statusBadge = '<span class="badge badge-ok">In Stock</span>';
        }

        const tr = document.createElement('tr');

        tr.onclick = (e) => {
            if (!e.target.closest('.btn')) loadChart(item.id, item.name);
        };

        tr.innerHTML = `
            <td><strong></strong></td>
            <td></td>
            <td></td>
            <td>₹${Number(item.price).toFixed(2)}</td>
            <td>${item.stock_quantity}</td>
            <td>${statusBadge}</td>
        `;

        const cells = tr.querySelectorAll('td');
        cells[0].querySelector('strong').textContent = item.sku;
        cells[1].textContent = item.name;
        cells[2].textContent = item.category;

        const actionsTd = document.createElement('td');
        actionsTd.className = 'action-cell';

        const aiBtn = document.createElement('button');
        aiBtn.className = 'btn btn-sm btn-primary';
        aiBtn.style.background = '#8b5cf6';
        aiBtn.textContent = '🤖 AI';
        aiBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            openAIInsights(item.id, item.name);
        });
        actionsTd.appendChild(aiBtn);

        if (role === 'admin') {
            const editBtn = document.createElement('button');
            editBtn.className = 'btn btn-sm btn-secondary';
            editBtn.textContent = 'Edit';
            editBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                openEdit(item.id);
            });
            actionsTd.appendChild(editBtn);
        }

        const sellBtn = document.createElement('button');
        sellBtn.className = 'btn btn-sm btn-danger';
        sellBtn.textContent = 'Sell';
        sellBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            openAction('sell', item.id, item.name);
        });
        actionsTd.appendChild(sellBtn);

        const refillBtn = document.createElement('button');
        refillBtn.className = 'btn btn-sm btn-success';
        refillBtn.textContent = 'Refill';
        refillBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            openAction('refill', item.id, item.name);
        });
        actionsTd.appendChild(refillBtn);

        tr.appendChild(actionsTd);

        tbody.appendChild(tr);
    });
}

function exportCSV() {
    const isSales = currentSection === 'sales-history';
    const endpoint = isSales ? '/export/sales-csv' : '/export/csv';
    const filename = isSales ? 'sales_history_export.csv' : 'inventory_export.csv';

    fetch(endpoint, {headers: getAuthHeadersOnly()})
        .then(res => {
            if (!res.ok) throw new Error('Export failed');
            return res.blob();
        })
        .then(blob => {
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');

            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            a.remove();

            window.URL.revokeObjectURL(url);
        })
        .catch(err => console.error(err));
}

function openModal(id) {
    document.getElementById(id).style.display = 'flex';
}

function closeModal(id) {
    document.getElementById(id).style.display = 'none';
}

async function openAIInsights(id, name) {
    document.getElementById('ai-item-name').innerText = name;
    document.getElementById('ai-segment').innerText = 'Loading...';
    document.getElementById('ai-demand').innerText = 'Loading...';

    openModal('ai-modal');

    try {
        const res = await fetch(`/api/ml/insights/${id}`, {
            headers: getAuthHeadersOnly()
        });

        if (res.status === 401) {
            logout();
            return;
        }

        if (!res.ok) throw new Error('Error loading AI');

        const data = await res.json();

        document.getElementById('ai-segment').innerText = data.segment;
        document.getElementById('ai-demand').innerText =
            `${data.predicted_demand_30d} Units`;
    } catch (err) {
        document.getElementById('ai-segment').innerText = 'Error loading AI';
        document.getElementById('ai-demand').innerText = 'Error loading AI';
        console.error(err);
    }
}

async function handleAdd(e) {
    e.preventDefault();

    const data = {
        sku: document.getElementById('add-sku').value,
        name: document.getElementById('add-name').value,
        category: document.getElementById('add-category').value,
        price: parseFloat(document.getElementById('add-price').value),
        stock_quantity: parseInt(document.getElementById('add-stock').value),
        reorder_level: parseInt(document.getElementById('add-reorder').value)
    };

    try {
        const res = await fetch('/items/', {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify(data)
        });

        if (!res.ok) {
            const err = await res.json();
            alert(err.detail);
            return;
        }

        closeModal('add-modal');
        document.getElementById('add-form').reset();

        fetchItems();
        fetchSummary();
    } catch (e) {
        console.error(e);
    }
}

function openEdit(id) {
    const item = currentItems.find(i => i.id === id);
    if (!item) return;

    document.getElementById('edit-id').value = id;
    document.getElementById('edit-name').value = item.name;
    document.getElementById('edit-price').value = item.price;
    document.getElementById('edit-reorder').value = item.reorder_level;

    openModal('edit-modal');
}

async function handleEdit(e) {
    e.preventDefault();

    const id = document.getElementById('edit-id').value;

    const data = {
        name: document.getElementById('edit-name').value,
        price: parseFloat(document.getElementById('edit-price').value),
        reorder_level: parseInt(document.getElementById('edit-reorder').value)
    };

    try {
        const res = await fetch(`/items/${id}`, {
            method: 'PUT',
            headers: getAuthHeaders(),
            body: JSON.stringify(data)
        });

        if (!res.ok) {
            const err = await res.json();
            alert(err.detail);
            return;
        }

        closeModal('edit-modal');
        fetchItems();
        fetchSummary();
    } catch (e) {
        console.error(e);
    }
}

function openAction(type, id, name) {
    document.getElementById('action-item-id').value = id;
    document.getElementById('action-type').value = type;

    document.getElementById('action-title').innerText =
        type === 'sell' ? 'Record Sale' : 'Refill Stock';

    document.getElementById('action-desc').innerText = `Item: ${name}`;

    document.getElementById('action-btn').innerText =
        type === 'sell' ? 'Process Sale' : 'Add Stock';

    document.getElementById('action-btn').className =
        `btn full-width ${type === 'sell' ? 'btn-danger' : 'btn-success'}`;

    document.getElementById('action-quantity').value = 1;

    openModal('action-modal');
}

async function handleAction(e) {
    e.preventDefault();

    const id = document.getElementById('action-item-id').value;
    const type = document.getElementById('action-type').value;
    const qty = parseInt(document.getElementById('action-quantity').value);

    if (!Number.isInteger(qty) || qty <= 0) {
        alert('Enter a valid positive quantity');
        return;
    }

    try {
        const res = await fetch(`/items/${id}/${type}`, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({quantity: qty})
        });

        if (!res.ok) {
            const err = await res.json();
            alert(err.detail);
            return;
        }

        closeModal('action-modal');

        fetchItems();
        fetchSummary();

        loadChart(
            id,
            document.getElementById('action-desc').innerText.replace('Item: ', '')
        );
    } catch (e) {
        console.error(e);
    }
}

async function loadChart(itemId, itemName) {
    try {
        const res = await fetch(`/items/${itemId}/sales`, {
            headers: getAuthHeadersOnly()
        });

        if (!res.ok) throw new Error('Unable to load sales chart');

        const sales = await res.json();

        // Sort sales chronologically by date
        sales.sort((a, b) => {
            const da = new Date(a.sale_date.includes('T') ? a.sale_date : a.sale_date.replace(' ', 'T'));
            const db = new Date(b.sale_date.includes('T') ? b.sale_date : b.sale_date.replace(' ', 'T'));
            return da - db;
        });

        const salesByMonth = {};

        sales.forEach(s => {
            const safeDateStr = s.sale_date.includes('T') ? s.sale_date : s.sale_date.replace(' ', 'T');
            const date = new Date(safeDateStr);
            const monthYear = isNaN(date.getTime())
                ? 'Unknown'
                : `${date.toLocaleString('default', {month: 'short'})} ${date.getFullYear()}`;

            salesByMonth[monthYear] =
                (salesByMonth[monthYear] || 0) + s.quantity_sold;
        });

        const labels = Object.keys(salesByMonth);
        const values = Object.values(salesByMonth);

        const ctx = document.getElementById('salesChart').getContext('2d');

        if (salesChartInstance) salesChartInstance.destroy();

        salesChartInstance = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels.length ? labels : ['No Data'],
                datasets: [{
                    label: `Units Sold - ${itemName}`,
                    data: values.length ? values : [0],
                    borderColor: '#3b82f6',
                    backgroundColor: 'rgba(59,130,246,0.1)',
                    borderWidth: 2,
                    fill: true,
                    tension: 0.3
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {beginAtZero: true, ticks: {stepSize: 1}}
                }
            }
        });

        showSection('dashboard');
    } catch (e) {
        console.error(e);
    }
}

async function fetchUsers() {
    try {
        const res = await fetch('/api/users', {
            headers: getAuthHeadersOnly()
        });

        if (res.ok) {
            const users = await res.json();
            const tbody = document.getElementById('users-body');

            tbody.innerHTML = '';

            users.forEach(u => {
                const roleBadge = u.role === 'admin'
                    ? '<span class="badge badge-out">Admin</span>'
                    : '<span class="badge badge-ok">Staff</span>';

                const tr = document.createElement('tr');

                tr.innerHTML = `
                    <td>${u.id}</td>
                    <td><strong>${u.username}</strong></td>
                    <td>${roleBadge}</td>
                `;

                tbody.appendChild(tr);
            });
        }
    } catch (err) {
        console.error(err);
    }
}

async function handleAddUser(e) {
    e.preventDefault();

    const u = document.getElementById('add-user-name').value;
    const p = document.getElementById('add-user-password').value;
    const r = document.getElementById('add-user-role').value;

    try {
        const res = await fetch('/api/users', {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({username: u, password: p, role: r})
        });

        if (!res.ok) {
            const err = await res.json();
            alert(err.detail);
            return;
        }

        closeModal('add-user-modal');
        document.getElementById('add-user-form').reset();

        fetchUsers();
    } catch (e) {
        console.error(e);
    }
}

async function fetchMLEvaluation() {
    const head = document.getElementById('ml-comparison-head');
    const body = document.getElementById('ml-comparison-body');

    if (head) head.innerHTML = '';
    if (body) {
        body.innerHTML = '<tr><td style="text-align:center;">Loading ML evaluation...</td></tr>';
    }

    try {
        const res = await fetch('/api/ml/evaluation', {
            headers: getAuthHeadersOnly()
        });

        if (res.status === 401) {
            logout();
            return;
        }

        if (!res.ok) {
            const error = await res.json().catch(() => ({}));
            const msg = error.detail || 'Unable to load ML evaluation';
            if (body) {
                body.innerHTML = `<tr><td style="text-align:center;color:red;">${msg}</td></tr>`;
            }
            return;
        }

        const data = await res.json();

        head.innerHTML = '';
        body.innerHTML = '';

        if (!data.models || data.models.length === 0) {
            body.innerHTML = '<tr><td style="text-align:center;">No evaluation results available.</td></tr>';
            return;
        }

        const columns = Object.keys(data.models[0]);

        const headerRow = document.createElement('tr');
        columns.forEach(column => {
            const th = document.createElement('th');
            th.textContent = column.replaceAll('_', ' ');
            headerRow.appendChild(th);
        });
        head.appendChild(headerRow);

        data.models.forEach(model => {
            const row = document.createElement('tr');

            columns.forEach(column => {
                const td = document.createElement('td');
                const rawVal = model[column];
                const numVal = Number(rawVal);
                if (column !== 'Model' && rawVal !== '' && !Number.isNaN(numVal)) {
                    td.textContent = numVal.toFixed(4);
                } else {
                    td.textContent = rawVal;
                }
                row.appendChild(td);
            });

            body.appendChild(row);
        });

        // Clean up any previously created blob URLs
        mlGraphObjectUrls.forEach(url => URL.revokeObjectURL(url));
        mlGraphObjectUrls = [];

        const graphElements = Array.from(document.querySelectorAll('.ml-graph'));
        await Promise.all(graphElements.map(async (img) => {
            const filename = img.dataset.graph;
            if (!filename) return;

            try {
                const imgRes = await fetch(`/api/ml/evaluation/graphs/${filename}?t=${Date.now()}`, {
                    headers: getAuthHeadersOnly()
                });
                if (!imgRes.ok) {
                    img.alt = `Failed to load ${filename} (${imgRes.status})`;
                    return;
                }
                const blob = await imgRes.blob();
                const blobUrl = URL.createObjectURL(blob);
                mlGraphObjectUrls.push(blobUrl);
                img.src = blobUrl;
            } catch (imgErr) {
                console.error(`Error loading graph ${filename}:`, imgErr);
                img.alt = `Unable to load ${filename}`;
            }
        }));

    } catch (error) {
        console.error('ML evaluation error:', error);
        if (body) {
            body.innerHTML = '<tr><td style="text-align:center;color:red;">Unable to load ML evaluation. Please try again.</td></tr>';
        }
    }
}
