/**
 * Gaxtron merchant API client — Stripe-style server-side integration.
 * Use your secret API key only on the server; never in browser apps.
 */
(function (global) {
  class GaxtronError extends Error {
    constructor(message, status, data) {
      super(message);
      this.name = 'GaxtronError';
      this.status = status;
      this.data = data;
    }
  }

  class Gaxtron {
    constructor(apiKey, options = {}) {
      if (!apiKey || typeof apiKey !== 'string') {
        throw new Error('Gaxtron requires a valid API key (gax_…)');
      }
      this.apiKey = apiKey;
      this.baseUrl = (options.baseUrl || global.GAXTRON_API_BASE || global.location?.origin || '')
        .replace(/\/$/, '');
    }

    async request(method, path, body) {
      const res = await fetch(this.baseUrl + path, {
        method,
        headers: {
          'Content-Type': 'application/json',
          Accept: 'application/json',
          'X-API-Key': this.apiKey,
        },
        body: body !== undefined ? JSON.stringify(body) : undefined,
      });
      const data = await res.json().catch(() => ({}));
      const detail = data.detail;
      const message =
        typeof detail === 'string'
          ? detail
          : Array.isArray(detail)
            ? detail[0]?.msg
            : `HTTP ${res.status}`;
      if (!res.ok) throw new GaxtronError(message || `HTTP ${res.status}`, res.status, data);
      return data;
    }

    /** Create a hosted checkout payment (returns payment_url for your customer). */
    createPayment({ amount, callback_url, idempotency_key }) {
      return this.request('POST', '/create-payment', {
        amount: String(amount),
        callback_url,
        ...(idempotency_key ? { idempotency_key } : {}),
      });
    }

    /** Check payment status (pending / confirmed / failed). */
    verifyPayment(paymentId) {
      return this.request('GET', `/verify-payment/${paymentId}`);
    }

    /** Full payment record for your merchant account. */
    getPayment(paymentId) {
      return this.request('GET', `/payment/${paymentId}/merchant`);
    }

    /** List recent payments for this API key's merchant. */
    listPayments() {
      return this.request('GET', '/payments');
    }
  }

  global.Gaxtron = Gaxtron;
  global.GaxtronError = GaxtronError;
})(typeof window !== 'undefined' ? window : global);
