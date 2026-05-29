/**
 * Auth sidebar — load real platform config only (no fabricated metrics).
 */
(function (global) {
  async function apiOrigin() {
    if (typeof API_BASE !== 'undefined') return API_BASE;
    return global.location.origin;
  }

  async function loadPublicConfig() {
    try {
      const res = await fetch(`${await apiOrigin()}/public/config`, {
        headers: { Accept: 'application/json' },
      });
      if (!res.ok) return;
      const cfg = await res.json();
      const confirms = document.getElementById('authConfirms');
      const network = document.getElementById('authNetwork');
      if (confirms && cfg.required_confirmations != null) {
        confirms.textContent = String(cfg.required_confirmations);
      }
      if (network && cfg.network) {
        network.textContent = cfg.network;
      }
    } catch (_) {
      /* leave placeholders */
    }
  }

  global.initAuthPanel = loadPublicConfig;
  document.addEventListener('DOMContentLoaded', loadPublicConfig);
})(window);
