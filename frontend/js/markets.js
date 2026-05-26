/** Live crypto market data — CoinGecko public API */
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

  const POLL_MS = 15000;
  let selectedId = 'ethereum';
  let chart = null;
  let pollTimer = null;
  let lastPrices = {};

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
    el.style.color = ok ? 'var(--green)' : 'var(--amber)';
  }

  async function fetchPrices() {
    const ids = Object.keys(COINS).join(',');
    const url = `https://api.coingecko.com/api/v3/simple/price?ids=${ids}&vs_currencies=usd&include_24hr_change=true`;
    const res = await fetch(url);
    if (!res.ok) throw new Error('Market data unavailable');
    return res.json();
  }

  async function fetchChart(coinId) {
    const url = `https://api.coingecko.com/api/v3/coins/${coinId}/market_chart?vs_currency=usd&days=1`;
    const res = await fetch(url);
    if (!res.ok) throw new Error('Chart data unavailable');
    const data = await res.json();
    return data.prices.map(([t, p]) => ({ x: t, y: p }));
  }

  function renderCoinList(prices) {
    const list = document.getElementById('coinList');
    if (!list) return;
    list.innerHTML = Object.entries(COINS).map(([id, meta]) => {
      const p = prices[id];
      if (!p) return '';
      const change = p.usd_24h_change ?? 0;
      const up = change >= 0;
      const prev = lastPrices[id]?.usd;
      const flash = prev != null && p.usd !== prev ? (p.usd > prev ? ' coin-row--up' : ' coin-row--down') : '';
      return `
        <button type="button" class="coin-row${id === selectedId ? ' coin-row--active' : ''}${flash}" data-coin="${id}">
          <div>
            <span class="coin-symbol">${meta.symbol}</span>
            <span class="coin-name">${meta.name}</span>
          </div>
          <div class="coin-row-right">
            <span class="coin-price">${fmtUsd(p.usd)}</span>
            <span class="coin-change coin-change--${up ? 'up' : 'down'}">${fmtPct(change)}</span>
          </div>
        </button>`;
    }).join('');

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
    changeEl.className = 'market-change market-change--' + (up ? 'up' : 'down');
  }

  function buildChart(points) {
    const canvas = document.getElementById('marketChart');
    if (!canvas || !global.Chart) return;

    const labels = points.map((pt) => new Date(pt.x).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }));
    const data = points.map((pt) => pt.y);
    const up = data.length > 1 && data[data.length - 1] >= data[0];
    const color = up ? '#22c55e' : '#f87171';
    const bg = up ? 'rgba(34, 197, 94, 0.12)' : 'rgba(248, 113, 113, 0.12)';

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
            callbacks: {
              label: (ctx) => fmtUsd(ctx.parsed.y),
            },
          },
        },
        scales: {
          x: {
            grid: { color: 'rgba(255,255,255,0.04)' },
            ticks: { color: '#64748b', maxTicksLimit: 8, font: { size: 10 } },
          },
          y: {
            grid: { color: 'rgba(255,255,255,0.04)' },
            ticks: {
              color: '#64748b',
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
    } catch (_) {
      setLiveStatus('Chart refresh failed', false);
    }
  }

  async function refresh() {
    try {
      const prices = await fetchPrices();
      renderCoinList(prices);
      updateHero(prices);
      setLiveStatus('Live · updated ' + new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }));
    } catch (_) {
      setLiveStatus('Reconnecting to market feed…', false);
    }
  }

  async function selectCoin(id) {
    if (!COINS[id]) return;
    selectedId = id;
    document.getElementById('coinSelect').value = id;
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

    refresh();
    loadChart();
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
