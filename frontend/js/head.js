/** Shared head tags for all Gaxtron pages */
(function () {
  const base = document.querySelector('base')?.href || '';
  const tags = `
    <link rel="icon" type="image/svg+xml" href="/favicon.svg" />
    <link rel="manifest" href="/site.webmanifest" />
    <meta name="theme-color" content="#0f172a" />
    <meta name="description" content="Gaxtron — secure crypto payment gateway for ETH and USDT" />
  `;
  document.head.insertAdjacentHTML('afterbegin', tags);
})();
