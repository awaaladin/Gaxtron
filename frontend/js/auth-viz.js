/**
 * Decorative settlement chart for auth pages — canvas, no external deps.
 */
(function (global) {
  const BARS = [
    { label: 'Init', h: 0.42 },
    { label: 'Route', h: 0.68 },
    { label: 'Settle', h: 0.88 },
    { label: 'Confirm', h: 1.0 },
    { label: 'Notify', h: 0.72 },
    { label: 'Done', h: 0.55 },
  ];

  function initAuthViz(canvasId) {
    const canvas = document.getElementById(canvasId || 'authViz');
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    const dpr = Math.min(global.devicePixelRatio || 1, 2);
    let w = 0;
    let h = 0;
    let t0 = performance.now();

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
      ctx.clearRect(0, 0, w, h);

      const padX = 28;
      const padY = 24;
      const chartH = h - padY - 36;
      const chartW = w - padX * 2;
      const barW = chartW / BARS.length;
      const gap = barW * 0.28;
      const innerW = barW - gap;

      const grad = ctx.createLinearGradient(0, padY, 0, h - 36);
      grad.addColorStop(0, 'rgba(0, 212, 255, 0.15)');
      grad.addColorStop(1, 'rgba(124, 58, 237, 0.04)');
      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.roundRect(padX - 8, padY - 8, chartW + 16, chartH + 16, 12);
      ctx.fill();

      const points = [];

      BARS.forEach((bar, i) => {
        const pulse = 0.06 * Math.sin(t * 1.4 + i * 0.9);
        const bh = (bar.h + pulse) * chartH * 0.85;
        const x = padX + i * barW + gap / 2;
        const y = padY + chartH - bh;

        const g = ctx.createLinearGradient(x, y, x, padY + chartH);
        g.addColorStop(0, '#00d4ff');
        g.addColorStop(0.45, '#7c3aed');
        g.addColorStop(1, 'rgba(124, 58, 237, 0.25)');

        ctx.fillStyle = g;
        ctx.beginPath();
        if (ctx.roundRect) {
          ctx.roundRect(x, y, innerW, bh, [6, 6, 2, 2]);
        } else {
          ctx.rect(x, y, innerW, bh);
        }
        ctx.fill();

        ctx.fillStyle = 'rgba(255,255,255,0.85)';
        ctx.beginPath();
        ctx.arc(x + innerW / 2, y - 4, 3, 0, Math.PI * 2);
        ctx.fill();

        ctx.font = '600 9px Inter, system-ui, sans-serif';
        ctx.fillStyle = 'rgba(139, 156, 176, 0.9)';
        ctx.textAlign = 'center';
        ctx.fillText(bar.label, x + innerW / 2, h - 14);

        points.push({ x: x + innerW / 2, y: y - 6 });
      });

      if (points.length > 1) {
        ctx.strokeStyle = 'rgba(0, 212, 255, 0.55)';
        ctx.lineWidth = 2;
        ctx.setLineDash([4, 6]);
        ctx.lineDashOffset = -t * 24;
        ctx.beginPath();
        ctx.moveTo(points[0].x, points[0].y);
        for (let i = 1; i < points.length; i++) {
          const mx = (points[i - 1].x + points[i].x) / 2;
          ctx.quadraticCurveTo(mx, points[i - 1].y - 12, points[i].x, points[i].y);
        }
        ctx.stroke();
        ctx.setLineDash([]);
      }

      ctx.font = '500 10px Inter, system-ui, sans-serif';
      ctx.fillStyle = 'rgba(90, 112, 128, 0.85)';
      ctx.textAlign = 'left';
      ctx.fillText('Settlement pipeline · Sepolia', padX, 12);

      requestAnimationFrame(draw);
    }

    resize();
    global.addEventListener('resize', resize);
    requestAnimationFrame(draw);
  }

  global.initAuthViz = initAuthViz;
  document.addEventListener('DOMContentLoaded', () => initAuthViz('authViz'));
})(window);
