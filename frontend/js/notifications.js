/** Real-time payment notifications via polling */
(function (global) {
  const STORAGE_KEY = 'gaxtron_payment_states';
  const POLL_MS = 20000;
  let pollTimer = null;
  let notifications = [];

  function loadStates() {
    try {
      return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
    } catch {
      return {};
    }
  }

  function saveStates(states) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(states));
  }

  function paymentKey(p) {
    return String(p.public_token || p.payment_token || p.id);
  }

  function statusLabel(status) {
    const map = {
      confirmed: 'Payment confirmed',
      pending: 'Payment pending',
      failed: 'Payment failed',
      expired: 'Payment expired',
      delivered: 'Webhook delivered',
    };
    return map[status] || `Payment ${status}`;
  }

  function statusTone(status) {
    if (status === 'confirmed' || status === 'delivered') return 'success';
    if (status === 'failed' || status === 'expired') return 'error';
    return 'warning';
  }

  function formatAmount(p) {
    const n = parseFloat(p.amount);
    return `${isNaN(n) ? p.amount : n.toFixed(6)} ETH`;
  }

  function addNotification(item) {
    notifications.unshift(item);
    notifications = notifications.slice(0, 20);
    renderNotifications();
    showToastModal(item);
    updateBadge();
  }

  function updateBadge() {
    const badge = document.getElementById('notifBadge');
    const unread = notifications.filter((n) => !n.read).length;
    if (!badge) return;
    if (unread > 0) {
      badge.textContent = unread > 9 ? '9+' : String(unread);
      badge.classList.remove('hidden');
    } else {
      badge.classList.add('hidden');
    }
  }

  function renderNotifications() {
    const list = document.getElementById('notifList');
    if (!list) return;
    if (!notifications.length) {
      list.innerHTML = '<p class="notif-empty">No notifications yet. Payment updates will appear here.</p>';
      return;
    }
    list.innerHTML = notifications.map((n, i) => `
      <div class="notif-item notif-item--${n.tone}${n.read ? ' notif-item--read' : ''}" data-idx="${i}">
        <div class="notif-item-dot"></div>
        <div class="notif-item-body">
          <p class="notif-item-title">${n.title}</p>
          <p class="notif-item-msg">${n.message}</p>
          <p class="notif-item-time">${n.time}</p>
        </div>
      </div>
    `).join('');
    list.querySelectorAll('.notif-item').forEach((el) => {
      el.addEventListener('click', () => {
        const idx = Number(el.dataset.idx);
        if (notifications[idx]) notifications[idx].read = true;
        updateBadge();
        el.classList.add('notif-item--read');
      });
    });
  }

  function showToastModal(item) {
    const toast = document.getElementById('notifToast');
    if (!toast) return;
    toast.className = `notif-toast notif-toast--${item.tone} notif-toast--show`;
    toast.innerHTML = `
      <div class="notif-toast-icon"><i data-lucide="${item.tone === 'success' ? 'check-circle' : item.tone === 'error' ? 'x-circle' : 'clock'}"></i></div>
      <div>
        <p class="notif-toast-title">${item.title}</p>
        <p class="notif-toast-msg">${item.message}</p>
      </div>
      <button type="button" class="notif-toast-close" aria-label="Dismiss">&times;</button>
    `;
    toast.querySelector('.notif-toast-close')?.addEventListener('click', () => {
      toast.classList.remove('notif-toast--show');
    });
    if (global.lucide) lucide.createIcons();
    clearTimeout(toast._timer);
    toast._timer = setTimeout(() => toast.classList.remove('notif-toast--show'), 6000);
  }

  function togglePanel() {
    const panel = document.getElementById('notifPanel');
    const backdrop = document.getElementById('notifBackdrop');
    if (!panel) return;
    const open = panel.classList.toggle('notif-panel--open');
    backdrop?.classList.toggle('notif-backdrop--open', open);
    if (open) {
      notifications.forEach((n) => { n.read = true; });
      updateBadge();
      renderNotifications();
    }
  }

  async function poll() {
    if (typeof Dashboard === 'undefined' || !getToken()) return;
    try {
      const rows = await Dashboard.payments();
      if (!Array.isArray(rows)) return;
      const prev = loadStates();
      const next = { ...prev };

      rows.forEach((p) => {
        const key = paymentKey(p);
        const status = p.status || 'pending';
        const prevStatus = prev[key];

        if (!prevStatus) {
          if (Object.keys(prev).length > 0) {
            addNotification({
              title: 'New payment created',
              message: `${formatAmount(p)} · ${key.slice(0, 16)}…`,
              time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
              tone: 'warning',
              read: false,
            });
          }
        } else if (prevStatus !== status) {
          addNotification({
            title: statusLabel(status),
            message: `${formatAmount(p)} · ${key.slice(0, 16)}…`,
            time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
            tone: statusTone(status),
            read: false,
          });
        }
        next[key] = status;
      });

      saveStates(next);
    } catch (_) {}
  }

  function initNotifications() {
    const btn = document.getElementById('notifBtn');
    const close = document.getElementById('notifClose');
    btn?.addEventListener('click', togglePanel);
    close?.addEventListener('click', togglePanel);
    document.getElementById('notifBackdrop')?.addEventListener('click', togglePanel);
    renderNotifications();
    poll();
    pollTimer = setInterval(poll, POLL_MS);
  }

  global.initNotifications = initNotifications;
  global.toggleNotifPanel = togglePanel;

  document.addEventListener('DOMContentLoaded', () => {
    if (document.getElementById('notifBtn')) initNotifications();
  });
})(window);
