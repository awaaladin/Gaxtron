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
    Accept: 'application/json',
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
    err.status = 0;
    throw err;
  }

  const data = await res.json().catch(() => ({}));
  const detail = data.detail;
  const message =
    typeof detail === 'string'
      ? detail
      : Array.isArray(detail)
        ? detail[0]?.msg
        : `HTTP ${res.status}`;

  if (res.status === 401) {
    clearToken();
    const err = new Error(message || 'Session expired');
    err.status = 401;
    if (window.GaxtronErrors) {
      const resolved = GaxtronErrors.resolveError(err);
      err.message = resolved.message;
    }
    if (!window.location.pathname.includes('login')) {
      window.location.href = '/login.html';
    }
    throw err;
  }

  if (!res.ok) {
    const err = new Error(message || `HTTP ${res.status}`);
    err.status = res.status;
    err.data = data;
    if (window.GaxtronErrors) {
      const resolved = GaxtronErrors.resolveError(err);
      err.message = resolved.message;
      err.title = resolved.title;
    }
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
    if (!res.ok) {
      const err = new Error(data.detail || 'Login failed');
      err.status = res.status;
      if (window.GaxtronErrors) {
        const resolved = GaxtronErrors.resolveError(err);
        err.message = resolved.message;
      }
      throw err;
    }
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
  walletNonce: () => apiFetch('/auth/wallet/nonce'),
  walletVerify: (body) =>
    apiFetch('/auth/wallet/verify', { method: 'POST', body }),
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
  let host = document.getElementById('cp-toast-host');
  if (!host) {
    host = document.createElement('div');
    host.id = 'cp-toast-host';
    document.body.appendChild(host);
  }

  const toneMap = { success: 'success', error: 'error', warning: 'warning', info: 'neutral' };
  const tone = toneMap[type] || 'neutral';

  let html;
  if (window.GaxtronErrors && (type === 'error' || type === 'warning')) {
    const t = GaxtronErrors.toastHtml(message);
    html = t.html.replace(`cp-toast--${t.error.tone}`, `cp-toast--${tone === 'error' ? t.error.tone : tone}`);
  } else {
    const icons = { success: 'check_circle', error: 'error', warning: 'warning', info: 'info' };
    html = `
      <div class="cp-toast cp-toast--${tone}">
        <div class="cp-toast-icon"><span class="material-symbols-outlined">${icons[type] || icons.info}</span></div>
        <div class="cp-toast-body">
          <p class="cp-toast-title">${type === 'success' ? 'Success' : type === 'warning' ? 'Notice' : 'Info'}</p>
          <p class="cp-toast-message">${message}</p>
        </div>
        <button type="button" class="cp-toast-close" aria-label="Close">&times;</button>
      </div>`;
  }

  const el = document.createElement('div');
  el.innerHTML = html;
  const toast = el.firstElementChild;
  toast.querySelector('.cp-toast-close')?.addEventListener('click', () => toast.remove());
  host.appendChild(toast);
  setTimeout(() => toast.remove(), 5200);
}

function showAlert(container, err, opts) {
  if (window.GaxtronErrors) {
    GaxtronErrors.showAlert(container, err, opts);
    return;
  }
  if (!container) return;
  container.className = 'mb-4';
  container.innerHTML = `<p class="text-sm text-red-400">${typeof err === 'string' ? err : err.message}</p>`;
  container.classList.remove('hidden');
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
  const labels = {
    confirmed: 'Confirmed',
    pending: 'Pending',
    failed: 'Failed',
    delivered: 'Delivered',
    expired: 'Expired',
    retrying: 'Retrying',
  };
  // Flat, bordered pill matching the Premium Editorial Fintech design system —
  // confirmed/delivered use the accent color, pending/retrying are neutral, failed/expired are error.
  const tones = {
    confirmed: 'bg-primary/10 text-primary border-primary/20',
    delivered: 'bg-primary/10 text-primary border-primary/20',
    pending: 'bg-outline-variant/40 text-on-surface-variant border-outline-variant',
    retrying: 'bg-outline-variant/40 text-on-surface-variant border-outline-variant',
    failed: 'bg-error-container/20 text-error border-error/30',
    expired: 'bg-error-container/20 text-error border-error/30',
  };
  const label = labels[status] || status;
  const tone = tones[status] || tones.pending;
  return `<span class="inline-block px-2 py-0.5 text-[10px] font-bold uppercase border ${tone}">${label}</span>`;
}

