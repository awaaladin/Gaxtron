/** Gaxtron — React Bits-inspired ambient animations (vanilla JS) */
(function (global) {
  function initAurora(container) {
    if (!container || container.dataset.auroraInit) return;
    container.dataset.auroraInit = '1';
    container.classList.add('gx-aurora');
    const layers = ['gx-aurora__a', 'gx-aurora__b', 'gx-aurora__c'];
    layers.forEach((cls) => {
      const el = document.createElement('div');
      el.className = cls;
      container.appendChild(el);
    });
  }

  function initParticles(canvas, opts = {}) {
    if (!canvas || canvas.dataset.particlesInit) return;
    canvas.dataset.particlesInit = '1';
    const ctx = canvas.getContext('2d');
    const count = opts.count || 48;
    const color = opts.color || 'rgba(34, 211, 238, 0.45)';
    let w, h, particles, raf;

    function resize() {
      w = canvas.width = canvas.offsetWidth * devicePixelRatio;
      h = canvas.height = canvas.offsetHeight * devicePixelRatio;
      canvas.style.width = canvas.offsetWidth + 'px';
      canvas.style.height = canvas.offsetHeight + 'px';
      ctx.scale(devicePixelRatio, devicePixelRatio);
      const cw = canvas.offsetWidth;
      const ch = canvas.offsetHeight;
      particles = Array.from({ length: count }, () => ({
        x: Math.random() * cw,
        y: Math.random() * ch,
        vx: (Math.random() - 0.5) * 0.35,
        vy: (Math.random() - 0.5) * 0.35,
        r: Math.random() * 1.8 + 0.4,
        a: Math.random() * 0.5 + 0.15,
      }));
    }

    function draw() {
      const cw = canvas.offsetWidth;
      const ch = canvas.offsetHeight;
      ctx.clearRect(0, 0, cw, ch);
      particles.forEach((p) => {
        p.x += p.vx;
        p.y += p.vy;
        if (p.x < 0 || p.x > cw) p.vx *= -1;
        if (p.y < 0 || p.y > ch) p.vy *= -1;
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fillStyle = color.replace(/[\d.]+\)$/, `${p.a})`);
        ctx.fill();
      });
      particles.forEach((a, i) => {
        for (let j = i + 1; j < particles.length; j++) {
          const b = particles[j];
          const dx = a.x - b.x;
          const dy = a.y - b.y;
          const dist = Math.sqrt(dx * dx + dy * dy);
          if (dist < 100) {
            ctx.beginPath();
            ctx.moveTo(a.x, a.y);
            ctx.lineTo(b.x, b.y);
            ctx.strokeStyle = `rgba(99, 102, 241, ${0.12 * (1 - dist / 100)})`;
            ctx.lineWidth = 0.5;
            ctx.stroke();
          }
        }
      });
      raf = requestAnimationFrame(draw);
    }

    resize();
    draw();
    window.addEventListener('resize', () => {
      cancelAnimationFrame(raf);
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      resize();
      draw();
    });
  }

  function initSpotlight(root) {
    if (!root || root.dataset.spotlightInit) return;
    root.dataset.spotlightInit = '1';
    root.classList.add('gx-spotlight-root');
    const spot = document.createElement('div');
    spot.className = 'gx-spotlight';
    root.prepend(spot);
    root.addEventListener('mousemove', (e) => {
      const rect = root.getBoundingClientRect();
      spot.style.setProperty('--sx', `${e.clientX - rect.left}px`);
      spot.style.setProperty('--sy', `${e.clientY - rect.top}px`);
    });
  }

  function initReveal() {
    const els = document.querySelectorAll('[data-reveal]');
    if (!els.length) return;
    const obs = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => {
          if (e.isIntersecting) {
            e.target.classList.add('is-revealed');
            obs.unobserve(e.target);
          }
        });
      },
      { threshold: 0.12, rootMargin: '0px 0px -40px 0px' }
    );
    els.forEach((el, i) => {
      el.style.setProperty('--reveal-delay', `${(i % 6) * 0.08}s`);
      obs.observe(el);
    });
  }

  function initShimmer(selector) {
    document.querySelectorAll(selector).forEach((el) => el.classList.add('gx-shimmer-text'));
  }

  function initCounter(el, target, duration = 1800) {
    if (!el || el.dataset.counterInit) return;
    el.dataset.counterInit = '1';
    const isFloat = String(target).includes('.');
    const end = parseFloat(target);
    const start = 0;
    const t0 = performance.now();
    function tick(now) {
      const p = Math.min(1, (now - t0) / duration);
      const eased = 1 - Math.pow(1 - p, 3);
      const val = start + (end - start) * eased;
      el.textContent = isFloat ? val.toFixed(3) : Math.round(val).toLocaleString();
      if (p < 1) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  }

  function initAll() {
    document.querySelectorAll('[data-aurora]').forEach((el) => initAurora(el));
    document.querySelectorAll('[data-particles]').forEach((el) => initParticles(el));
    document.querySelectorAll('[data-spotlight]').forEach((el) => initSpotlight(el));
    initReveal();
    initShimmer('[data-shimmer]');

    document.querySelectorAll('[data-counter]').forEach((el) => {
      const obs = new IntersectionObserver(([e]) => {
        if (e.isIntersecting) {
          initCounter(el, el.dataset.counter, 1600);
          obs.unobserve(el);
        }
      });
      obs.observe(el);
    });
  }

  global.GaxtronMotion = { initAll, initAurora, initParticles, initSpotlight, initReveal };
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initAll);
  } else {
    initAll();
  }
})(window);
