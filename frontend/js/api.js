// Gaxtron Merchant API client — UI and API share port 8002 in local dev
function resolveApiBase() {
  if (window.API_BASE_URL) return window.API_BASE_URL;
  const port = window.location.port;
  const sameOriginPorts = ['8002', '8000', ''];
  if (sameOriginPorts.includes(port) || window.location.pathname.startsWith('/app')) {
    return window.location.origin;
  }
  return localStorage.getItem('gaxtron_api_base') || 'http://127.0.0.1:8002';
}
const API_BASE = resolveApiBase();

const getToken = () => localStorage.getItem('gaxtron_token') || localStorage.getItem('chainpay_token');
const setToken = (t) => {
  localStorage.setItem('gaxtron_token', t);
  localStorage.removeItem('chainpay_token');
};
const clearToken = () => {
  localStorage.removeItem('gaxtron_token');
  localStorage.removeItem('chainpay_token');
};
const getApiKey = () => localStorage.getItem('gaxtron_api_key') || localStorage.getItem('chainpay_api_key');
const setApiKey = (k) => {
  localStorage.setItem('gaxtron_api_key', k);
  localStorage.removeItem('chainpay_api_key');
};
const getUser = () => JSON.parse(localStorage.getItem('gaxtron_user') || localStorage.getItem('chainpay_user') || 'null');
const setUser = (u) => {
  localStorage.setItem('gaxtron_user', JSON.stringify(u));
  localStorage.removeItem('chainpay_user');
};

async function apiFetch(endpoint, options = {}) {
  const token = getToken();
  const apiKey = getApiKey();
  const headers = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(options.useApiKey && apiKey ? { 'X-API-Key': apiKey } : {}),
    ...(options.headers || {}),
  };

  const config = {
    method: options.method || 'GET',
    headers,
    ...(options.body ? { body: JSON.stringify(options.body) } : {}),
  };

  let res;
  try {
    res = await fetch(`${API_BASE}${endpoint}`, config);
  } catch (networkErr) {
    const err = new Error(
      `Cannot reach Gaxtron API at ${API_BASE}. Run: .\\scripts\\start_gaxtron.ps1`
    );
    err.cause = networkErr;
    throw err;
  }

  if (res.status === 401) {
    clearToken();
    if (!window.location.pathname.includes('login')) {
      window.location.href = '/login.html';
    }
    return;
  }

  const data = await res.json().catch(() => ({}));
  const detail = data.detail;
  const message =
    typeof detail === 'string'
      ? detail
      : Array.isArray(detail)
        ? detail[0]?.msg
        : `HTTP ${res.status}`;

  if (!res.ok) {
    const err = new Error(message || `HTTP ${res.status}`);
    err.status = res.status;
    err.data = data;
    throw err;
  }
  return data;
}

async function checkApiHealth() {
  try {
    const r = await fetch(`${API_BASE}/health/live`, { method: 'GET' });
    return r.ok;
  } catch {
    return false;
  }
}

const Auth = {
  async login(body) {
    const form = new URLSearchParams();
    form.append('username', body.email);
    form.append('password', body.password);
    let res;
    try {
      res = await fetch(`${API_BASE}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: form,
      });
    } catch (e) {
      throw new Error(`Cannot reach Gaxtron API at ${API_BASE}. Run: .\\scripts\\start_gaxtron.ps1`);
    }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || 'Login failed');
    return data;
  },
  register: (body) =>
    apiFetch('/auth/register', {
      method: 'POST',
      body: {
        email: body.email,
        username: body.username || body.business_name || body.email.split('@')[0],
        password: body.password,
      },
    }),
  me: () => apiFetch('/auth/me'),
  logout() {
    clearToken();
    localStorage.removeItem('gaxtron_user');
    localStorage.removeItem('gaxtron_api_key');
    window.location.href = '/login.html';
  },
};

const Dashboard = {
  stats: () => apiFetch('/dashboard/stats'),
  payments: () => apiFetch('/dashboard/payments'),
};

const Payments = {
  create: (body) => {
    const payload = {
      amount: body.amount,
      callback_url: body.callback_url,
      ...(body.idempotency_key ? { idempotency_key: body.idempotency_key } : {}),
    };
    return apiFetch('/create-payment', { method: 'POST', body: payload, useApiKey: true });
  },
  getStatus: (id) => apiFetch(`/verify-payment/${id}`, { useApiKey: true }),
};

const Transactions = {
  list: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return apiFetch(`/dashboard/transactions${qs ? '?' + qs : ''}`);
  },
};

const ApiKeys = {
  list: () => apiFetch('/api-keys'),
  create: (name = 'default') => apiFetch('/api-keys', { method: 'POST', body: { name } }),
  regenerate: (id) => apiFetch(`/api-keys/${id}/regenerate`, { method: 'POST' }),
};

const Webhooks = {
  logs: () => apiFetch('/dashboard/webhooks/logs'),
};

function showToast(message, type = 'success') {
  const existing = document.getElementById('gaxtron-toast');
  if (existing) existing.remove();

  const colors = {
    success: 'bg-emerald-700',
    error: 'bg-red-600',
    info: 'bg-slate-800',
    warning: 'bg-amber-600',
  };

  const toast = document.createElement('div');
  toast.id = 'gaxtron-toast';
  toast.className = `fixed top-5 right-5 z-[100] flex items-center gap-3 px-4 py-3 rounded-lg shadow-lg text-white text-sm font-medium ${colors[type] || colors.info}`;
  toast.innerHTML = `<span>${message}</span><button type="button" class="opacity-80 hover:opacity-100 ml-2" aria-label="Close">&times;</button>`;
  toast.querySelector('button').onclick = () => toast.remove();
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 4200);
}

function setLoading(btn, loading, text = 'Loading…') {
  if (!btn) return;
  if (loading) {
    btn.dataset.originalText = btn.innerHTML;
    btn.innerHTML = `<span class="spinner"></span>${text}`;
    btn.disabled = true;
  } else {
    btn.innerHTML = btn.dataset.originalText || text;
    btn.disabled = false;
  }
}

function requireAuth() {
  if (!getToken()) {
    window.location.href = '/login.html';
    return false;
  }
  return true;
}

function copyToClipboard(text, btn) {
  navigator.clipboard.writeText(text).then(() => {
    const orig = btn.innerHTML;
    btn.innerHTML = 'Copied';
    btn.classList.add('text-emerald-600');
    setTimeout(() => {
      btn.innerHTML = orig;
      btn.classList.remove('text-emerald-600');
    }, 2000);
  });
}

function formatCurrency(amount, symbol = '') {
  const n = parseFloat(amount);
  return `${symbol}${isNaN(n) ? '0' : n.toFixed(6)}`;
}

function formatDate(dateStr) {
  if (!dateStr) return '—';
  return new Date(dateStr).toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function statusBadge(status) {
  const map = {
    confirmed: 'bg-emerald-50 text-emerald-800 border-emerald-200',
    pending: 'bg-amber-50 text-amber-800 border-amber-200',
    failed: 'bg-red-50 text-red-800 border-red-200',
    delivered: 'bg-emerald-50 text-emerald-800 border-emerald-200',
    expired: 'bg-slate-100 text-slate-600 border-slate-200',
  };
  const cls = map[status] || map.pending;
  return `<span class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md text-xs font-medium border ${cls}">${status}</span>`;
}

function initLucide() {
  if (window.lucide) lucide.createIcons();
}

document.addEventListener('DOMContentLoaded', initLucide);
