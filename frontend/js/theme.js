/** Gaxtron theme — light / dark with localStorage persistence */
(function (global) {
  const KEY = 'gaxtron-theme';

  function apply(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem(KEY, theme);
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.content = theme === 'dark' ? '#1a1630' : '#faf5ff';
    document.querySelectorAll('[data-theme-icon]').forEach((el) => {
      el.setAttribute('data-lucide', theme === 'dark' ? 'sun' : 'moon');
    });
    if (global.lucide) lucide.createIcons();
  }

  function toggleTheme() {
    const cur = document.documentElement.getAttribute('data-theme') || 'light';
    apply(cur === 'dark' ? 'light' : 'dark');
  }

  function initTheme() {
    const saved = localStorage.getItem(KEY);
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    apply(saved || (prefersDark ? 'dark' : 'light'));
  }

  global.toggleTheme = toggleTheme;
  global.initTheme = initTheme;

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initTheme);
  } else {
    initTheme();
  }
})(window);
