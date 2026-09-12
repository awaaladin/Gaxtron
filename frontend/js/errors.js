/** Gaxtron — designer error messages mapped from HTTP codes & API responses */
(function (global) {
  const CATALOG = {
    400: {
      title: 'Invalid request',
      message: 'The information sent couldn’t be processed. Check your inputs and try again.',
      hint: 'Review the highlighted fields below.',
      icon: 'warning',
      tone: 'warning',
    },
    401: {
      title: 'Session expired',
      message: 'Your credentials are no longer valid. Sign in again to continue.',
      hint: 'This can happen after a long idle period.',
      icon: 'lock',
      tone: 'error',
    },
    403: {
      title: 'Access denied',
      message: 'You don’t have permission to perform this action.',
      hint: 'Contact your account administrator if you believe this is a mistake.',
      icon: 'gpp_bad',
      tone: 'error',
    },
    404: {
      title: 'Not found',
      message: 'The resource you’re looking for doesn’t exist or was removed.',
      hint: 'Double-check the URL or payment ID.',
      icon: 'search_off',
      tone: 'neutral',
    },
    409: {
      title: 'Already exists',
      message: 'An account or resource with these details already exists.',
      hint: 'Try signing in or use a different email address.',
      icon: 'content_copy',
      tone: 'warning',
    },
    422: {
      title: 'Validation failed',
      message: 'Some fields didn’t pass validation. Correct them and resubmit.',
      hint: 'Passwords must be at least 8 characters.',
      icon: 'error',
      tone: 'warning',
    },
    429: {
      title: 'Too many requests',
      message: 'You’ve hit the rate limit. Wait a moment before trying again.',
      hint: 'This protects the network from abuse.',
      icon: 'timer',
      tone: 'warning',
    },
    500: {
      title: 'Server error',
      message: 'Something went wrong on our end. The team has been notified.',
      hint: 'Try again in a few minutes.',
      icon: 'cloud_off',
      tone: 'error',
    },
    502: {
      title: 'Gateway error',
      message: 'The payment gateway is temporarily unreachable.',
      hint: 'Blockchain RPC may be syncing — retry shortly.',
      icon: 'wifi_off',
      tone: 'error',
    },
    503: {
      title: 'Service unavailable',
      message: 'Gaxtron is undergoing maintenance or is at capacity.',
      hint: 'Check status or try again later.',
      icon: 'construction',
      tone: 'warning',
    },
    network: {
      title: 'Connection lost',
      message: 'Unable to reach the Gaxtron API. Check your network or server status.',
      hint: 'Locally: run .\\scripts\\start_gaxtron.ps1',
      icon: 'power_off',
      tone: 'error',
    },
    default: {
      title: 'Something went wrong',
      message: 'An unexpected error occurred. Please try again.',
      hint: null,
      icon: 'error',
      tone: 'error',
    },
  };

  const MESSAGE_OVERRIDES = [
    { match: /invalid credentials|incorrect password|wrong password/i, key: 401, message: 'Email or password is incorrect.' },
    { match: /already registered|email.*exists|duplicate/i, key: 409, message: 'This email is already registered.' },
    { match: /username.*taken/i, key: 409, message: 'This business name is already in use.' },
    { match: /payment not found/i, key: 404, message: 'This payment link is invalid or has expired.' },
    { match: /api key/i, key: 403, message: 'A valid API key is required for this operation.' },
    { match: /too many authentication|rate limit/i, key: 429, message: 'Too many sign-up attempts from your network. Wait 5 minutes and try again.' },
    { match: /unauthorized/i, key: 401 },
  ];

  function resolveError(input) {
    let status = null;
    let raw = '';

    if (typeof input === 'string') {
      raw = input;
    } else if (input && typeof input === 'object') {
      status = input.status || input.statusCode || null;
      raw = input.message || input.detail || '';
      if (input.title) {
        const base = CATALOG[status] || CATALOG.default;
        return { ...base, title: input.title, message: raw || base.message, raw, status };
      }
      if (typeof raw !== 'string') raw = JSON.stringify(raw);
    }

    for (const rule of MESSAGE_OVERRIDES) {
      if (rule.match.test(raw)) {
        const base = CATALOG[rule.key] || CATALOG.default;
        return {
          ...base,
          ...(rule.message ? { message: rule.message } : {}),
          raw,
          status: typeof rule.key === 'number' ? rule.key : status,
        };
      }
    }

    const base = CATALOG[status] || CATALOG.default;
    if (raw && raw !== base.message && !raw.startsWith('HTTP')) {
      return { ...base, message: raw, raw, status };
    }
    return { ...base, raw, status };
  }

  function alertHtml(err, { compact = false } = {}) {
    const e = resolveError(err);
    const toneClass = `cp-alert--${e.tone}`;
    const hint = e.hint && !compact
      ? `<p class="cp-alert-hint">${e.hint}</p>`
      : '';
    return `
      <div class="cp-alert ${toneClass}" role="alert">
        <div class="cp-alert-icon"><span class="material-symbols-outlined">${e.icon}</span></div>
        <div class="cp-alert-body">
          <p class="cp-alert-title">${e.title}</p>
          <p class="cp-alert-message">${e.message}</p>
          ${hint}
        </div>
        <button type="button" class="cp-alert-dismiss" aria-label="Dismiss">&times;</button>
      </div>`;
  }

  function showAlert(container, err, opts) {
    if (!container) return;
    container.innerHTML = alertHtml(err, opts);
    container.classList.remove('hidden');
    container.querySelector('.cp-alert-dismiss')?.addEventListener('click', () => {
      container.classList.add('hidden');
      container.innerHTML = '';
    });
  }

  function toastHtml(err) {
    const e = resolveError(err);
    return {
      html: `
        <div class="cp-toast cp-toast--${e.tone}">
          <div class="cp-toast-icon"><span class="material-symbols-outlined">${e.icon}</span></div>
          <div class="cp-toast-body">
            <p class="cp-toast-title">${e.title}</p>
            <p class="cp-toast-message">${e.message}</p>
          </div>
          <button type="button" class="cp-toast-close" aria-label="Close">&times;</button>
        </div>`,
      error: e,
    };
  }

  global.GaxtronErrors = { resolveError, alertHtml, showAlert, toastHtml, CATALOG };
})(window);
