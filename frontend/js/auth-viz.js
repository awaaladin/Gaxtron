/**
 * Auth panel chart — understated settlement volume (area + line, no external deps).
 */
(function (global) {
  const POINTS = 72;

  function themeColors() {
    const light = document.documentElement.getAttribute('data-theme') === 'light';
    if (light) {
      return {
        panel: 'rgba(255, 255, 255, 0.6)',
        grid: 'rgba(15, 25, 35, 0.06)',
        gridStrong: 'rgba(15, 25, 35, 0.1)',
        line: 'rgba(2, 132, 199, 0.85)',
        lineGlow: 'rgba(2, 132, 199, 0.12)',
        areaTop: 'rgba(2, 132, 199, 0.14)',
        areaMid: 'rgba(79, 70, 229, 0.06)',
        areaBottom: 'rgba(255, 255, 255, 0)',
        dot: 'rgba(2, 132, 199, 1)',
        label: 'rgba(90, 112, 128, 0.85)',
        muted: 'rgba(148, 163, 184, 0.9)',
        badge: 'rgba(2, 132, 199, 0.1)',
        badgeText: 'rgba(2, 132, 199, 0.9)',
      };
    }
    return {
      panel: 'rgba(13, 17, 24, 0.45)',
      grid: 'rgba(139, 156, 176, 0.06)',
      gridStrong: 'rgba(139, 156, 176, 0.1)',
      line: 'rgba(0, 212, 255, 0.72)',
      lineGlow: 'rgba(0, 212, 255, 0.08)',
      areaTop: 'rgba(0, 212, 255, 0.1)',
      areaMid: 'rgba(124, 58, 237, 0.05)',
      areaBottom: 'rgba(8, 12, 18, 0)',
      dot: 'rgba(0, 212, 255, 0.95)',
      label: 'rgba(139, 156, 176, 0.9)',
      muted: 'rgba(90, 112, 128, 0.85)',
      badge: 'rgba(0, 212, 255, 0.08)',
      badgeText: 'rgba(0, 212, 255, 0.85)',
    };
  }

  function buildSeries(t) {
    const out = [];
    const drift = t * 0.22;
    for (let i = 0; i < POINTS; i++) {
      const x = i / (POINTS - 1);
      const base =
        0.38 +
        0.22 * Math.sin(x * Math.PI * 1.6 + drift) +
        0.12 * Math.sin(x * Math.PI * 3.8 - drift * 0.7) +
        0.06 * Math.sin(x * Math.PI * 7 + t * 0.35);
      const edge = Math.sin(x * Math.PI);
      const v = base * (0.72 + 0.28 * edge);
      out.push(Math.max(0.14, Math.min(0.88, v)));
    }
    return out;
  }

  function smoothPath(ctx, pts, closeToBaseline, baselineY) {
    if (pts.length < 2) return;
    ctx.beginPath();
    ctx.moveTo(pts[0].x, pts[0].y);
    for (let i = 1; i < pts.length; i++) {
      const prev = pts[i - 1];
      const curr = pts[i];
      const cpx = (prev.x + curr.x) / 2;
      ctx.quadraticCurveTo(cpx, prev.y, curr.x, curr.y);
    }
    if (closeToBaseline) {
      const last = pts[pts.length - 1];
      const first = pts[0];
      ctx.lineTo(last.x, baselineY);
      ctx.lineTo(first.x, baselineY);
      ctx.closePath();
    }
  }

  function initAuthViz(canvasId) {
    const canvas = document.getElementById(canvasId || 'authViz');
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    const dpr = Math.min(global.devicePixelRatio || 1, 2);
    let w = 0;
    let h = 0;
    let t0 = performance.now();
    let raf = 0;

    function resize() {
      const rect = canvas.getBoundingClientRect();
      w = Math.max(rect.width, 280);
      h = Math.max(rect.height, 200);
      canvas.width = w * dpr;
      canvas.height = h * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }

    function draw(now) {
      const t = (now - t0) / 1000;
      const c = themeColors();
      const series = buildSeries(t);

      ctx.clearRect(0, 0, w, h);

      const pad = { top: 36, right: 16, bottom: 28, left: 44 };
      const chartW = w - pad.left - pad.right;
      const chartH = h - pad.top - pad.bottom;
      const baseY = pad.top + chartH;

      ctx.fillStyle = c.panel;
      ctx.beginPath();
      if (ctx.roundRect) {
        ctx.roundRect(8, 8, w - 16, h - 16, 10);
      } else {
        ctx.rect(8, 8, w - 16, h - 16);
      }
      ctx.fill();

      const gridLines = 4;
      ctx.font = '500 9px "JetBrains Mono", ui-monospace, monospace';
      ctx.textAlign = 'right';
      ctx.textBaseline = 'middle';
      for (let g = 0; g <= gridLines; g++) {
        const gy = pad.top + (chartH * g) / gridLines;
        ctx.strokeStyle = g === gridLines ? c.gridStrong : c.grid;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(pad.left, gy);
        ctx.lineTo(pad.left + chartW, gy);
        ctx.stroke();
        const pct = Math.round(100 - (g / gridLines) * 100);
        ctx.fillStyle = c.muted;
        ctx.fillText(pct + '%', pad.left - 8, gy);
      }

      const pts = series.map((v, i) => ({
        x: pad.left + (i / (POINTS - 1)) * chartW,
        y: pad.top + chartH - v * chartH,
      }));

      const areaGrad = ctx.createLinearGradient(0, pad.top, 0, baseY);
      areaGrad.addColorStop(0, c.areaTop);
      areaGrad.addColorStop(0.55, c.areaMid);
      areaGrad.addColorStop(1, c.areaBottom);
      ctx.fillStyle = areaGrad;
      smoothPath(ctx, pts, true, baseY);
      ctx.fill();

      ctx.strokeStyle = c.lineGlow;
      ctx.lineWidth = 4;
      ctx.lineJoin = 'round';
      ctx.lineCap = 'round';
      smoothPath(ctx, pts, false);
      ctx.stroke();

      ctx.strokeStyle = c.line;
      ctx.lineWidth = 1.5;
      smoothPath(ctx, pts, false);
      ctx.stroke();

      const end = pts[pts.length - 1];
      const pulse = 0.35 + 0.35 * Math.sin(t * 2.2);
      ctx.fillStyle = c.lineGlow;
      ctx.beginPath();
      ctx.arc(end.x, end.y, 6 + pulse, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = c.dot;
      ctx.beginPath();
      ctx.arc(end.x, end.y, 2.5, 0, Math.PI * 2);
      ctx.fill();

      ctx.font = '600 10px Inter, system-ui, sans-serif';
      ctx.textAlign = 'left';
      ctx.textBaseline = 'top';
      ctx.fillStyle = c.label;
      ctx.fillText('Settlement throughput', pad.left, 14);

      const badgeW = 34;
      const badgeH = 16;
      const bx = pad.left + 128;
      const by = 13;
      ctx.fillStyle = c.badge;
      ctx.beginPath();
      if (ctx.roundRect) {
        ctx.roundRect(bx, by, badgeW, badgeH, 4);
      } else {
        ctx.rect(bx, by, badgeW, badgeH);
      }
      ctx.fill();
      ctx.font = '600 8px Inter, system-ui, sans-serif';
      ctx.fillStyle = c.badgeText;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText('LIVE', bx + badgeW / 2, by + badgeH / 2 + 0.5);

      ctx.font = '500 9px "JetBrains Mono", ui-monospace, monospace';
      ctx.textAlign = 'right';
      ctx.textBaseline = 'bottom';
      ctx.fillStyle = c.muted;
      ctx.fillText('24h · Sepolia', w - pad.right, h - 12);

      const hours = 6;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'top';
      ctx.font = '500 8px "JetBrains Mono", ui-monospace, monospace';
      for (let i = 0; i <= hours; i++) {
        const lx = pad.left + (i / hours) * chartW;
        const label = i === hours ? 'now' : '-' + (hours - i) * 4 + 'h';
        ctx.fillStyle = c.muted;
        ctx.fillText(label, lx, baseY + 6);
      }

      raf = requestAnimationFrame(draw);
    }

    resize();
    const onResize = () => resize();
    global.addEventListener('resize', onResize);

    const observer = new MutationObserver(() => {
      /* redraw picks up theme on next frame */
    });
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });

    raf = requestAnimationFrame(draw);

    return () => {
      cancelAnimationFrame(raf);
      global.removeEventListener('resize', onResize);
      observer.disconnect();
    };
  }

  global.initAuthViz = initAuthViz;
  document.addEventListener('DOMContentLoaded', () => initAuthViz('authViz'));
})(window);
