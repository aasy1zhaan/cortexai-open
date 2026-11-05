// Procedural point-cloud kidney graft with glowing "risk hotspots".
// Usage: const k = KidneyCloud(canvas, { onHotspot(screenXY) {} }); k.setLayer(0|1|2)
(function () {
  function rnd(seed) { let s = seed >>> 0; return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296); }

  function buildPoints() {
    const r = rnd(7), pts = [];
    const A = 0.56, B = 1.0, C = 0.36;
    const shape = (x, y, z) => {
      // bean: concave medial side (hilum at +x), gentle curvature
      const hil = 0.34 * Math.exp(-(y * y) / 0.16) * Math.pow(Math.max(0, x / A), 1.4);
      return [x - hil + 0.13 * y * y - 0.06, y, z];
    };
    // surface
    for (let i = 0; i < 7200; i++) {
      const u = r() * Math.PI * 2, v = Math.acos(2 * r() - 1);
      const x = A * Math.sin(v) * Math.cos(u), y = B * Math.cos(v), z = C * Math.sin(v) * Math.sin(u);
      const [sx, sy, sz] = shape(x, y, z);
      pts.push({ x: sx, y: sy, z: sz, k: 0, s: 0.8 + r() * 0.8 });
    }
    // inner structure (medulla pyramids) — sparser
    for (let i = 0; i < 2200; i++) {
      const u = r() * Math.PI * 2, v = Math.acos(2 * r() - 1), f = 0.35 + r() * 0.5;
      const x = A * f * Math.sin(v) * Math.cos(u), y = B * f * Math.cos(v), z = C * f * Math.sin(v) * Math.sin(u);
      const [sx, sy, sz] = shape(x, y, z);
      pts.push({ x: sx, y: sy, z: sz, k: 1, s: 1.3 + r() * 1.6 });
    }
    // vessels + ureter from hilum
    const tube = (p0, p1, p2, p3, n, kind, rad) => {
      for (let i = 0; i < n; i++) {
        const t = r(), mt = 1 - t;
        const bx = mt*mt*mt*p0[0] + 3*mt*mt*t*p1[0] + 3*mt*t*t*p2[0] + t*t*t*p3[0];
        const by = mt*mt*mt*p0[1] + 3*mt*mt*t*p1[1] + 3*mt*t*t*p2[1] + t*t*t*p3[1];
        const bz = mt*mt*mt*p0[2] + 3*mt*mt*t*p1[2] + 3*mt*t*t*p2[2] + t*t*t*p3[2];
        const a = r() * Math.PI * 2, rr = rad * (0.7 + 0.3 * r());
        pts.push({ x: bx + Math.cos(a) * rr, y: by + Math.sin(a) * rr * 0.6, z: bz + Math.sin(a) * rr, k: kind, s: 0.7 + r() * 0.5 });
      }
    };
    tube([0.18, 0.08, 0], [0.55, 0.12, 0.05], [0.8, 0.35, 0.1], [1.25, 0.55, 0.1], 520, 2, 0.045); // artery
    tube([0.18, -0.04, 0.03], [0.6, -0.05, -0.05], [0.95, 0.15, -0.1], [1.35, 0.25, -0.12], 520, 3, 0.06); // vein
    tube([0.14, -0.18, 0], [0.4, -0.5, 0], [0.25, -0.95, 0.05], [0.35, -1.5, 0.05], 420, 4, 0.03); // ureter
    return pts;
  }

  // three hotspot clusters, one per signal layer
  const HOT = [
    { c: [-0.38, 0.52, 0.12], label: "Immunogenetics" },   // 01 upper pole
    { c: [-0.52, -0.05, 0.18], label: "Drug exposure" },   // 02 lateral cortex
    { c: [-0.2, -0.62, 0.16], label: "Graft injury" },     // 03 lower pole
  ];

  window.KidneyCloud = function (canvas, opts = {}) {
    const ctx = canvas.getContext("2d");
    const pts = buildPoints();
    pts.forEach(p => {
      p.h = HOT.map(h => Math.exp(-(((p.x - h.c[0]) ** 2 + (p.y - h.c[1]) ** 2 + (p.z - h.c[2]) ** 2) / 0.055)));
    });
    const embers = Array.from({ length: 70 }, (_, i) => ({ x: Math.random(), y: Math.random(), v: 0.0004 + Math.random() * 0.0009, s: 0.6 + Math.random() * 2.2, o: Math.random() }));
    let W = 0, H = 0, dpr = 1, theta = -0.5, layer = 0, layerMix = [1, 0.25, 0.25], t0 = performance.now();
    const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;

    function resize() {
      dpr = Math.min(devicePixelRatio || 1, 2);
      W = canvas.clientWidth; H = canvas.clientHeight;
      canvas.width = W * dpr; canvas.height = H * dpr; ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }
    new ResizeObserver(resize).observe(canvas); resize();

    const off = document.createElement("canvas"), octx = off.getContext("2d");
    function frame(now) {
      const t = (now - t0) / 1000;
      if (!reduce) theta += 0.0032;
      for (let i = 0; i < 3; i++) layerMix[i] += ((i === layer ? 1 : 0.22) - layerMix[i]) * 0.05;
      ctx.clearRect(0, 0, W, H);
      const scale = Math.min(W * (opts.widthFrac || 0.36), H * 0.42), cx = W / 2 + (opts.offsetX || 0), cy = H * (opts.cy || 0.5);
      const ct = Math.cos(theta), st = Math.sin(theta), tilt = 0.28, cti = Math.cos(tilt), sti = Math.sin(tilt);
      ctx.globalCompositeOperation = "lighter";
      const pulse = 0.75 + 0.25 * Math.sin(t * 2.2);
      let hotScreen = null, best = -1;
      for (const p of pts) {
        let x = p.x * ct + p.z * st, z = -p.x * st + p.z * ct, y = p.y;
        const y2 = y * cti - z * sti, z2 = y * sti + z * cti;
        const persp = 2.6 / (2.6 + z2), sx = cx + x * scale * persp, sy = cy - y2 * scale * persp;
        const depth = (1 - z2) * 0.5;                  // 0 back .. 1 front
        const heat = p.k < 2 ? (p.h[0] * layerMix[0] + p.h[1] * layerMix[1] + p.h[2] * layerMix[2]) * pulse : 0;
        let rC, gC, bC, a;
        if (p.k === 2) { rC = 255; gC = 120; bC = 60; a = 0.35 + 0.3 * depth; }
        else if (p.k === 3) { rC = 60; gC = 150; bC = 255; a = 0.35 + 0.3 * depth; }
        else if (p.k === 4) { rC = 150; gC = 200; bC = 255; a = 0.25 + 0.25 * depth; }
        else if (p.k === 1) {
          // inner medulla glows like embers through the cortex shell
          const h2 = Math.min(1, 0.45 + heat);
          rC = 255; gC = 105 + 50 * h2; bC = 25; a = 0.22 + 0.6 * heat + 0.15 * depth;
        } else {
          const base = 0.42 + 0.5 * depth;
          rC = 40 + 215 * heat; gC = 140 + 0 * heat; bC = 255 - 215 * heat; a = Math.min(1, base + heat * 0.6);
        }
        ctx.fillStyle = `rgba(${rC | 0},${gC | 0},${bC | 0},${a.toFixed(3)})`;
        const sz = p.s * persp * (1 + heat * 2.2) * (W < 600 ? 0.8 : 1) * (W > 1200 ? 1.25 : 1);
        ctx.fillRect(sx, sy, sz, sz);
        if (p.k === 0 && p.h[layer] > best && z2 < -0.05) { best = p.h[layer]; hotScreen = [sx, sy]; }
      }
      // embers
      for (const e of embers) {
        if (!reduce) { e.y -= e.v; e.x += Math.sin(t * 0.6 + e.o * 10) * 0.0003; if (e.y < -0.02) { e.y = 1.02; e.x = Math.random(); } }
        const fl = 0.35 + 0.35 * Math.sin(t * 3 + e.o * 20);
        ctx.fillStyle = `rgba(255,${130 + (e.o * 60) | 0},40,${fl.toFixed(3)})`;
        ctx.beginPath(); ctx.arc(e.x * W, e.y * H, e.s, 0, 7); ctx.fill();
      }
      ctx.globalCompositeOperation = "source-over";
      // bloom pass
      if (off.width !== canvas.width) { off.width = canvas.width / 3; off.height = canvas.height / 3; }
      octx.clearRect(0, 0, off.width, off.height);
      octx.drawImage(canvas, 0, 0, off.width, off.height);
      ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.globalCompositeOperation = "lighter";
      ctx.filter = "blur(14px)"; ctx.globalAlpha = 1; ctx.drawImage(off, 0, 0, canvas.width, canvas.height);
      ctx.filter = "blur(4px)"; ctx.globalAlpha = 0.7; ctx.drawImage(off, 0, 0, canvas.width, canvas.height);
      ctx.restore();
      if (opts.onHotspot && hotScreen) opts.onHotspot(hotScreen, HOT[layer].label);
      if (!reduce) requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
    return {
      setLayer(i) { layer = i; if (reduce) requestAnimationFrame(frame); },
      labels: HOT.map(h => h.label),
    };
  };
})();
