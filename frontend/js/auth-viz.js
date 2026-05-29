/**
 * Auth panel — Stripe-style preview: static dashboard mock + slow sparkline + pipeline step.
 */
(function (global) {
  const SPARK_POINTS = 40;
  const SPARK_INTERVAL_MS = 180;

  function isLight() {
    return document.documentElement.getAttribute('data-theme') === 'light';
  }

  function sparkColors() {
    return isLight()
      ? { line: 'rgba(15, 25, 35, 0.4)', fill: 'rgba(15, 25, 35, 0.05)', grid: 'rgba(15, 25, 35, 0.06)' }
      : { line: 'rgba(232, 238, 244, 0.32)', fill: 'rgba(232, 238, 244, 0.04)', grid: 'rgba(139, 156, 176, 0.06)' };
  }

  function buildSpark(t) {
    const out = [];
    for (let i = 0; i < SPARK_POINTS; i++) {
      const x = i / (SPARK_POINTS - 1);
      const v =
        0.5 +
        0.1 * Math.sin(x * Math.PI * 1.8 + t * 0.12) +
        0.04 * Math.sin(x * Math.PI * 4 + t * 0.06);
      out.push(v);
    }
    return out;
  }

  function drawSpark(canvas, t) {
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    const dpr = Math.min(global.devicePixelRatio || 1, 2);
    const rect = canvas.getBoundingClientRect();
    const w = Math.max(rect.width, 200);
    const h = Math.max(rect.height, 36);
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    const c = sparkColors();
    const series = buildSpark(t);
    const pad = { t: 2, r: 2, b: 4, l: 2 };
    const cw = w - pad.l - pad.r;
    const ch = h - pad.t - pad.b;
    const base = pad.t + ch;

    ctx.clearRect(0, 0, w, h);
    ctx.strokeStyle = c.grid;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(pad.l, base);
    ctx.lineTo(pad.l + cw, base);
    ctx.stroke();

    const pts = series.map((v, i) => ({
      x: pad.l + (i / (SPARK_POINTS - 1)) * cw,
      y: pad.t + ch - v * ch,
    }));

    ctx.beginPath();
    ctx.moveTo(pts[0].x, base);
    ctx.lineTo(pts[0].x, pts[0].y);
    for (let i = 1; i < pts.length; i++) {
      const mx = (pts[i - 1].x + pts[i].x) / 2;
      ctx.quadraticCurveTo(mx, pts[i - 1].y, pts[i].x, pts[i].y);
    }
    ctx.lineTo(pts[pts.length - 1].x, base);
    ctx.closePath();
    ctx.fillStyle = c.fill;
    ctx.fill();

    ctx.beginPath();
    ctx.moveTo(pts[0].x, pts[0].y);
    for (let i = 1; i < pts.length; i++) {
      const mx = (pts[i - 1].x + pts[i].x) / 2;
      ctx.quadraticCurveTo(mx, pts[i - 1].y, pts[i].x, pts[i].y);
    }
    ctx.strokeStyle = c.line;
    ctx.lineWidth = 1.25;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.stroke();
  }

  function initPipeline() {
    const steps = document.querySelectorAll('.auth-preview-pipeline .auth-preview-step');
    if (!steps.length) return;

    let active = Array.from(steps).findIndex((s) => s.classList.contains('is-active'));
    if (active < 0) active = 0;

    setInterval(() => {
      steps.forEach((step, i) => {
        step.classList.remove('is-active', 'is-done');
        if (i < active) step.classList.add('is-done');
        else if (i === active) step.classList.add('is-active');
      });
      active = (active + 1) % steps.length;
    }, 5000);
  }

  function initAuthViz(canvasId) {
    const canvas = document.getElementById(canvasId || 'authViz');
    if (!canvas) return;

    const t0 = performance.now();
    let sparkTimer = null;

    function tick() {
      drawSpark(canvas, (performance.now() - t0) / 1000);
    }

    const onResize = tick;
    global.addEventListener('resize', onResize);
    const themeObs = new MutationObserver(onResize);
    themeObs.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-theme'],
    });

    tick();
    sparkTimer = setInterval(tick, SPARK_INTERVAL_MS);
    initPipeline();

    return () => {
      clearInterval(sparkTimer);
      global.removeEventListener('resize', onResize);
      themeObs.disconnect();
    };
  }

  global.initAuthViz = initAuthViz;
  document.addEventListener('DOMContentLoaded', () => initAuthViz('authViz'));
})(window);
