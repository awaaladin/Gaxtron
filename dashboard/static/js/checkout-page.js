/**
 * Hosted checkout — QR, manual copy, MetaMask pay, status polling (backend authoritative).
 */
(function (global) {
  const POLL_MS = 3000;
  const SEPOLIA_CHAIN_ID = 11155111;

  let paymentId = null;
  let paymentData = null;
  let userAddress = null;
  let pollTimer = null;
  let paying = false;

  function apiBase() {
    return global.CHECKOUT_API_BASE || global.location.origin;
  }

  function $(id) {
    return document.getElementById(id);
  }

  function ethWeiHex(amountEth) {
    if (global.GaxtronWallet && global.GaxtronWallet.ethToWeiHex) {
      return global.GaxtronWallet.ethToWeiHex(amountEth);
    }
    const parts = String(amountEth).split('.');
    const whole = BigInt(parts[0] || '0');
    const frac = (parts[1] || '').padEnd(18, '0').slice(0, 18);
    const wei = whole * BigInt('1000000000000000000') + BigInt(frac);
    return '0x' + wei.toString(16);
  }

  function payUri(address, amountEth) {
    const weiValue = ethWeiHex(amountEth);
    return `ethereum:${address}@${SEPOLIA_CHAIN_ID}?value=${weiValue}`;
  }

  function setSteps(phase) {
    ['pending', 'confirming', 'confirmed'].forEach((p) => {
      const el = document.querySelector('.checkout-step[data-step="' + p + '"]');
      if (!el) return;
      el.classList.remove('active', 'done');
      if (p === phase) el.classList.add('active');
      if (
        (phase === 'confirming' && p === 'pending') ||
        (phase === 'confirmed' && (p === 'pending' || p === 'confirming'))
      ) {
        el.classList.add('done');
      }
    });
    if (phase === 'confirmed') {
      document.querySelectorAll('.checkout-step').forEach((el) => {
        el.classList.remove('active');
        el.classList.add('done');
      });
    }
  }

  function showPanel(phase) {
    $('panelPending').classList.toggle('hidden', phase !== 'pending');
    $('panelConfirming').classList.toggle('hidden', phase !== 'confirming');
    $('panelConfirmed').classList.toggle('hidden', phase !== 'confirmed');
    $('panelFailed').classList.toggle('hidden', phase !== 'failed');
    setSteps(phase === 'failed' ? 'pending' : phase);
  }

  function phaseFrom(data) {
    if (data.status === 'confirmed') return 'confirmed';
    if (data.status === 'failed') return 'failed';
    if (data.tx_hash && data.confirmations < data.required_confirmations) return 'confirming';
    return 'pending';
  }

  function statusLabel(phase) {
    return {
      pending: 'Awaiting payment',
      confirming: 'Confirming…',
      confirmed: 'Paid',
      failed: 'Expired',
    }[phase] || '—';
  }

  function normalizePayment(data) {
    return {
      ...data,
      address: data.address || data.wallet_address,
    };
  }

  function generateQR(address, amountEth) {
    const uri = payUri(address, amountEth);
    const canvas = $('qrcode');
    const img = $('qrCode');

    if (canvas && global.QRCode) {
      global.QRCode.toCanvas(canvas, uri, { width: 200, margin: 2 }, (err) => {
        if (err) {
          console.error('QR generation failed', err);
          if (img) {
            img.src = 'https://api.qrserver.com/v1/create-qr-code/?size=220x220&margin=10&data=' + encodeURIComponent(uri);
            img.classList.remove('hidden');
          }
          return;
        }
        if (img) img.classList.add('hidden');
      });
      return;
    }

    if (img) {
      img.src = 'https://api.qrserver.com/v1/create-qr-code/?size=220x220&margin=10&data=' + encodeURIComponent(uri);
      img.classList.remove('hidden');
      if (canvas) canvas.classList.add('hidden');
    }
  }

  function render(data) {
    paymentData = normalizePayment(data);
    const amount = parseFloat(paymentData.amount);
    const amountStr = amount.toFixed(6) + ' ETH';
    const address = paymentData.address;

    $('summaryAmount').textContent = amount.toFixed(6);
    $('summaryTotal').textContent = amountStr;
    $('summaryPaymentId').textContent = paymentData.public_token || ('#' + paymentData.id);
    $('summaryNetwork').textContent = 'Ethereum · ' + (paymentData.network || 'sepolia');
    $('footerNetwork').textContent = (paymentData.network || 'sepolia') + ' testnet';
    $('instructionAmount').textContent = amountStr;
    $('walletAddress').textContent = address;
    $('confRequired').textContent = paymentData.required_confirmations;

    generateQR(address, paymentData.amount);

    const phase = phaseFrom(paymentData);
    showPanel(phase);
    $('summaryStatus').textContent = statusLabel(phase);

    if ($('paymentAmount')) {
      $('paymentAmount').textContent = amountStr + ' to ' + address.slice(0, 10) + '…';
    }
    if ($('modalAmount')) {
      $('modalAmount').textContent = amountStr;
    }
    if ($('modalAddress')) {
      $('modalAddress').textContent = address;
    }

    if (phase === 'confirming') {
      const pct = Math.min(100, (paymentData.confirmations / paymentData.required_confirmations) * 100);
      $('confCount').textContent = paymentData.confirmations;
      $('confProgressBar').style.width = pct + '%';
      $('txHashConfirming').textContent = paymentData.tx_hash || '';
    }
    if (phase === 'confirmed') {
      $('txHashConfirmed').textContent = paymentData.tx_hash ? 'Transaction: ' + paymentData.tx_hash : '';
      closeModal();
    }
  }

  function showError(title, text) {
    $('loadingView').classList.add('hidden');
    $('checkoutView').classList.add('hidden');
    $('errorView').classList.remove('hidden');
    $('errorTitle').textContent = title;
    $('errorText').textContent = text;
  }

  function setWalletStatus(text, ok) {
    const el = $('walletStatus');
    if (!el) return;
    el.textContent = text;
    el.classList.remove('hidden', 'checkout-wallet-status--ok', 'checkout-wallet-status--err');
    el.classList.add(ok ? 'checkout-wallet-status--ok' : 'checkout-wallet-status--err');
  }

  function openModal() {
    $('paymentModal')?.classList.remove('hidden');
    document.body.classList.add('checkout-modal-open');
  }

  function closeModal() {
    $('paymentModal')?.classList.add('hidden');
    document.body.classList.remove('checkout-modal-open');
  }

  async function loadPayment() {
    const res = await fetch(apiBase() + '/payment/' + encodeURIComponent(paymentId), {
      headers: { Accept: 'application/json' },
    });
    if (!res.ok) {
      const err = new Error('not found');
      err.status = res.status;
      throw err;
    }
    return normalizePayment(await res.json());
  }

  async function poll() {
    let httpStatus = null;
    try {
      const data = await loadPayment();
      $('loadingView').classList.add('hidden');
      $('errorView').classList.add('hidden');
      $('checkoutView').classList.remove('hidden');
      render(data);
      if (data.status === 'confirmed' || data.status === 'failed') {
        if (pollTimer) clearInterval(pollTimer);
        return;
      }
    } catch (e) {
      httpStatus = e.status;
      if ($('checkoutView').classList.contains('hidden') && !$('errorView').classList.contains('hidden')) {
        /* already showing error */
      } else if ($('checkoutView').classList.contains('hidden')) {
        showError(
          httpStatus === 404 ? 'Payment not found' : 'Connection issue',
          httpStatus === 404
            ? 'This payment link is invalid or has expired. Contact the merchant for a new link.'
            : 'Unable to load payment details. Check your connection and refresh.'
        );
      }
    }
  }

  function copyText(text, btn, label) {
    navigator.clipboard.writeText(text).then(() => {
      const orig = btn.textContent;
      btn.textContent = label || 'Copied!';
      setTimeout(() => { btn.textContent = orig; }, 2000);
    });
  }

  async function onConnectWallet() {
    try {
      userAddress = await global.GaxtronWallet.connectWallet();
      if (!userAddress) return;
      setWalletStatus('Connected: ' + userAddress.slice(0, 6) + '…' + userAddress.slice(-4), true);
      openModal();
    } catch (err) {
      setWalletStatus(err.message || 'Could not connect wallet', false);
    }
  }

  async function onConfirmPay() {
    if (!paymentData || paying) return;
    const btn = $('confirmPayBtn');
    paying = true;
    if (btn) {
      btn.disabled = true;
      btn.textContent = 'Confirm in MetaMask…';
    }
    try {
      if (!userAddress) {
        userAddress = await global.GaxtronWallet.connectWallet();
      }
      const txHash = await global.GaxtronWallet.sendPayment(
        paymentData.address,
        paymentData.amount,
        userAddress
      );
      setWalletStatus('Transaction sent — waiting for confirmation', true);
      closeModal();
      showPanel('confirming');
      $('txHashConfirming').textContent = txHash ? 'Submitted: ' + txHash : '';
      await poll();
    } catch (err) {
      setWalletStatus(err.message || 'Payment failed', false);
      if (btn) btn.textContent = 'Pay now';
    } finally {
      paying = false;
      if (btn) btn.disabled = false;
    }
  }

  function bindEvents() {
    $('copyAddrBtn')?.addEventListener('click', () => {
      if (paymentData) copyText(paymentData.address, $('copyAddrBtn'), 'Copied!');
    });
    $('copyAmountBtn')?.addEventListener('click', () => {
      const amountStr = paymentData ? parseFloat(paymentData.amount).toFixed(6) + ' ETH' : '';
      copyText(amountStr, $('copyAmountBtn'), 'Copied!');
    });
    $('openWalletBtn')?.addEventListener('click', () => {
      if (paymentData) {
        global.location.href = payUri(paymentData.address, paymentData.amount);
      }
    });
    $('connectWalletBtn')?.addEventListener('click', onConnectWallet);
    $('confirmPayBtn')?.addEventListener('click', onConfirmPay);
    $('modalCancelBtn')?.addEventListener('click', closeModal);
    $('paymentModal')?.addEventListener('click', (e) => {
      if (e.target.classList.contains('checkout-modal-backdrop')) closeModal();
    });
  }

  function init(ref) {
    paymentId = ref;
    if (!paymentId) {
      showError('Invalid link', 'This payment URL is missing a payment reference.');
      return;
    }
    bindEvents();
    poll();
    pollTimer = setInterval(poll, POLL_MS);
  }

  function resolvePaymentRef() {
    if (global.CHECKOUT_PAYMENT_REF) {
      return String(global.CHECKOUT_PAYMENT_REF);
    }
    const path = global.location.pathname;
    const patterns = [
      /\/pay\/([^/?#]+)/,
      /\/checkout\/([^/?#]+)/,
      /\/link\/([^/?#]+)/,
    ];
    for (const re of patterns) {
      const m = path.match(re);
      if (m) return decodeURIComponent(m[1]);
    }
    const qs = new URLSearchParams(global.location.search);
    return qs.get('ref') || qs.get('token') || qs.get('payment') || null;
  }

  function initFromPath() {
    init(resolvePaymentRef());
  }

  global.GaxtronCheckout = {
    init,
    initFromPath,
    openModal,
    closeModal,
    poll,
  };

  document.addEventListener('DOMContentLoaded', () => {
    if (global.CHECKOUT_PAYMENT_REF && global.GaxtronCheckout) {
      global.GaxtronCheckout.init(global.CHECKOUT_PAYMENT_REF);
      return;
    }
    initFromPath();
  });
})(window);
