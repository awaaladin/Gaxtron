/**
 * Optional wallet login — sign nonce, verify on backend, receive JWT.
 */
(function (global) {
  function hasWallet() {
    return typeof global.ethereum !== 'undefined';
  }

  class WalletNotInstalledError extends Error {
    constructor() {
      super(
        'MetaMask is a browser extension that holds your crypto wallet. ' +
        'Install it from metamask.io, refresh this page, then try again — or sign in with email below.'
      );
      this.name = 'WalletNotInstalledError';
      this.code = 'NO_WALLET';
    }
  }

  async function loginWithWallet(opts = {}) {
    if (!hasWallet()) {
      throw new WalletNotInstalledError();
    }

    const accounts = await global.ethereum.request({ method: 'eth_requestAccounts' });
    const address = accounts[0];
    if (!address) throw new Error('No wallet account selected');

    const base = typeof API_BASE !== 'undefined' ? API_BASE : global.location.origin;
    const nonceRes = await fetch(base + '/auth/wallet/nonce', {
      headers: { Accept: 'application/json' },
    });
    const nonceData = await nonceRes.json().catch(() => ({}));
    if (!nonceRes.ok) {
      throw new Error(nonceData.detail || 'Could not start wallet sign-in');
    }

    const message = nonceData.message || ('Sign in to Gaxtron\n\nNonce: ' + nonceData.nonce + '\n');
    const signature = await global.ethereum.request({
      method: 'personal_sign',
      params: [message, address],
    });

    const verifyRes = await fetch(base + '/auth/wallet/verify', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({
        address,
        signature,
        nonce: nonceData.nonce,
      }),
    });
    const data = await verifyRes.json().catch(() => ({}));
    if (!verifyRes.ok) {
      const detail = data.detail;
      throw new Error(typeof detail === 'string' ? detail : 'Wallet sign-in failed');
    }

    const token = data.access_token || data.token;
    if (!token) throw new Error('No token returned from server');

    if (typeof setToken === 'function') setToken(token);
    if (data.user && typeof setUser === 'function') setUser(data.user);
    else if (typeof Auth !== 'undefined' && Auth.me) {
      try {
        if (typeof setUser === 'function') setUser(await Auth.me());
      } catch (_) {}
    }

    if (opts.redirect !== false) {
      global.location.href = opts.redirectTo || 'dashboard.html';
    }
    return data;
  }

  global.GaxtronWalletAuth = { loginWithWallet, hasWallet, WalletNotInstalledError };
})(window);
