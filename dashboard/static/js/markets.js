/** Live crypto market data — via Gaxtron API proxy (reliable on production). */
(function (global) {
  const COINS = {
    bitcoin: { symbol: 'BTC', name: 'Bitcoin' },
    ethereum: { symbol: 'ETH', name: 'Ethereum' },
    solana: { symbol: 'SOL', name: 'Solana' },
    binancecoin: { symbol: 'BNB', name: 'BNB' },
    ripple: { symbol: 'XRP', name: 'XRP' },
    cardano: { symbol: 'ADA', name: 'Cardano' },
    dogecoin: { symbol: 'DOGE', name: 'Dogecoin' },
    polkadot: { symbol: 'DOT', name: 'Polkadot' },
  };

  const POLL_MS = 20000;
  let selectedId = 'ethereum';
  let chart = null;
  let pollTimer = null;
  let lastPrices = {};

  function apiBase() {
    if (typeof API_BASE !== 'undefined') return API_BASE;
    return global.location.origin;
  }

  function fmtUsd(n) {
    if (n >= 1000) return '$' + n.toLocaleString(undefined, { maximumFractionDigits: 2 });
    if (n >= 1) return '$' + n.toFixed(2);
    return '$' + n.toFixed(4);
  }

  function fmtPct(n) {
    const sign = n >= 0 ? '+' : '';
    return sign + n.toFixed(2) + '%';
  }

  function setLiveStatus(text, ok = true) {
    const el = document.getElementById('marketLiveStatus');
    if (!el) return;
    el.textContent = text;
    el.style.color = ok ? '#34D399' : '#D3C4B0';
  }

  async function parseApiError(res) {
    const data = await res.json().catch(() => ({}));
    return data.detail || `HTTP ${res.status}`;
  }

  async function fetchPrices() {
    const res = await fetch(apiBase() + '/markets/prices', { headers: { Accept: 'application/json' } });
    if (!res.ok) throw new Error(await parseApiError(res));
    return res.json();
  }

  async function fetchChart(coinId) {
    const res = await fetch(apiBase() + '/markets/chart/' + encodeURIComponent(coinId), {
      headers: { Accept: 'application/json' },
    });
    if (!res.ok) throw new Error(await parseApiError(res));
    const data = await res.json();
    const prices = data.prices || [];
    if (!prices.length) throw new Error('No chart data returned');
    return prices.map(([t, p]) => ({ x: t, y: p }));
  }

  function renderCoinList(prices) {
    const list = document.getElementById('coinList');
    if (!list) return;
    const html = Object.entries(COINS).map(([id, meta]) => {
      const p = prices[id];
      if (!p) return '';
      const change = p.usd_24h_change ?? 0;
      const up = change >= 0;
      const active = id === selectedId;
      return `
        <button type="button" class="w-full flex items-center justify-between px-6 py-4 divider-b font-mono-data transition-colors hover:bg-surface-container-low ${active ? 'bg-surface-container-low' : ''}" data-coin="${id}">
          <div class="text-left">
            <span class="font-label-caps text-label-caps text-on-surface mr-2">${meta.symbol}</span>
            <span class="text-on-surface-variant text-[13px]">${meta.name}</span>
          </div>
          <div class="flex items-center gap-stack-md">
            <span class="text-on-surface">${fmtUsd(p.usd)}</span>
            <span class="${up ? 'text-primary' : 'text-error'}">${fmtPct(change)}</span>
          </div>
        </button>`;
    }).join('');

    if (!html) {
      list.innerHTML = '<p class="px-6 py-8 text-center text-on-surface-variant font-body-md">No market data</p>';
      return;
    }
    list.innerHTML = html;
    list.querySelectorAll('.coin-row').forEach((btn) => {
      btn.addEventListener('click', () => selectCoin(btn.dataset.coin));
    });
    lastPrices = prices;
  }

  function updateHero(prices) {
    const meta = COINS[selectedId];
    const p = prices[selectedId];
    if (!meta || !p) return;
    const change = p.usd_24h_change ?? 0;
    const up = change >= 0;
    document.getElementById('marketCoinName').textContent = meta.name;
    document.getElementById('marketCoinSymbol').textContent = meta.symbol;
    document.getElementById('marketPrice').textContent = fmtUsd(p.usd);
    const changeEl = document.getElementById('marketChange');
    changeEl.textContent = fmtPct(change) + ' (24h)';
    changeEl.className = 'font-mono-data text-mono-data ' + (up ? 'text-primary' : 'text-error');
  }

  function buildChart(points) {
    const canvas = document.getElementById('marketChart');
    if (!canvas || !global.Chart || !points.length) return;

    const labels = points.map((pt) => new Date(pt.x).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }));
    const data = points.map((pt) => pt.y);
    const up = data.length > 1 && data[data.length - 1] >= data[0];
    const color = up ? '#34D399' : '#FFB4AB';
    const bg = up ? 'rgba(52, 211, 153, 0.12)' : 'rgba(255, 180, 171, 0.12)';

    if (chart) {
      chart.data.labels = labels;
      chart.data.datasets[0].data = data;
      chart.data.datasets[0].borderColor = color;
      chart.data.datasets[0].backgroundColor = bg;
      chart.update('none');
      return;
    }

    chart = new Chart(canvas, {
      type: 'line',
      data: {
        labels,
        datasets: [{
          data,
          borderColor: color,
          backgroundColor: bg,
          borderWidth: 2,
          fill: true,
          tension: 0.35,
          pointRadius: 0,
          pointHitRadius: 8,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 400 },
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: { label: (ctx) => fmtUsd(ctx.parsed.y) },
          },
        },
        scales: {
          x: {
            grid: { color: '#3A3833' },
            ticks: { color: '#9C8F7C', maxTicksLimit: 8, font: { size: 10 } },
          },
          y: {
            grid: { color: '#3A3833' },
            ticks: {
              color: '#9C8F7C',
              font: { size: 10 },
              callback: (v) => fmtUsd(v),
            },
          },
        },
      },
    });
  }

  async function loadChart() {
    try {
      const points = await fetchChart(selectedId);
      buildChart(points);
    } catch (e) {
      console.error('Chart load failed', e);
      setLiveStatus('Chart unavailable — retrying…', false);
    }
  }

  async function refresh() {
    try {
      const prices = await fetchPrices();
      renderCoinList(prices);
      updateHero(prices);
      const suffix = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      setLiveStatus('Live · ' + suffix);
    } catch (e) {
      console.error('Market refresh failed', e);
      setLiveStatus('Market feed reconnecting…', false);
    }
  }

  async function selectCoin(id) {
    if (!COINS[id]) return;
    selectedId = id;
    const sel = document.getElementById('coinSelect');
    if (sel) sel.value = id;
    await refresh();
    await loadChart();
  }

  function initMarkets() {
    const select = document.getElementById('coinSelect');
    if (select) {
      select.innerHTML = Object.entries(COINS).map(([id, m]) =>
        `<option value="${id}">${m.name} (${m.symbol})</option>`
      ).join('');
      select.value = selectedId;
      select.addEventListener('change', (e) => selectCoin(e.target.value));
    }

    refresh().then(loadChart);
    pollTimer = setInterval(async () => {
      await refresh();
      await loadChart();
    }, POLL_MS);
  }

  global.initMarkets = initMarkets;
  global.selectCoin = selectCoin;

  document.addEventListener('DOMContentLoaded', () => {
    if (document.getElementById('marketChart')) initMarkets();
  });
})(window);
