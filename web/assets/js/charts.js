// Minimal SVG charts: line/area with threshold lines, shaded target bands and event markers.
(function () {
  const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  function niceTicks(min, max, n = 4) {
    const span = max - min || 1, step0 = span / n, mag = Math.pow(10, Math.floor(Math.log10(step0)));
    const step = [1, 2, 2.5, 5, 10].map(m => m * mag).find(s => span / s <= n) || step0;
    const out = []; for (let v = Math.ceil(min / step) * step; v <= max + 1e-9; v += step) out.push(+v.toFixed(6));
    return out;
  }
  function fmt(v, unit) {
    if (unit === "%") return (Math.abs(v) < 10 && v % 1 ? v.toFixed(1) : Math.round(v)) + "%";
    if (Math.abs(v) >= 1000) return (v / 1000).toFixed(v % 1000 ? 1 : 0) + "k";
    return Math.abs(v) < 10 && v % 1 ? v.toFixed(1) : Math.round(v) + "";
  }

  window.CXChart = function (o) {
    const W = o.width || 520, H = o.height || 170, P = { l: 42, r: 14, t: 12, b: 24 };
    const all = o.series.flatMap(s => s.points);
    if (!all.length) return `<div class="empty">No measurements</div>`;
    const xs = all.map(p => p.x), ys = all.map(p => p.y);
    const xMin = o.xMin ?? Math.min(...xs), xMax = o.xMax ?? Math.max(...xs, xMin + 1);
    let yMin = o.yMin ?? Math.min(...ys, ...(o.thresholds || []).map(t => t.y), ...(o.bands || []).map(b => b.y0));
    let yMax = o.yMax ?? Math.max(...ys, ...(o.thresholds || []).map(t => t.y), ...(o.bands || []).map(b => b.y1));
    if (o.yMin === undefined) yMin = Math.min(yMin, 0) === 0 && o.zero !== false ? 0 : yMin - (yMax - yMin) * 0.1;
    yMax = yMax + (yMax - yMin) * 0.12 || 1;
    const X = x => P.l + (x - xMin) / (xMax - xMin || 1) * (W - P.l - P.r);
    const Y = y => H - P.b - (y - yMin) / (yMax - yMin || 1) * (H - P.t - P.b);
    let g = "";
    // grid + y labels
    niceTicks(yMin, yMax, 3).forEach(t => {
      g += `<line x1="${P.l}" x2="${W - P.r}" y1="${Y(t)}" y2="${Y(t)}" class="cx-grid"/>`;
      g += `<text x="${P.l - 6}" y="${Y(t) + 3.5}" class="cx-ylab" text-anchor="end">${fmt(t, o.yUnit)}</text>`;
    });
    niceTicks(xMin, xMax, 5).forEach(t => {
      g += `<text x="${X(t)}" y="${H - 6}" class="cx-xlab" text-anchor="middle">${o.xFmt ? o.xFmt(t) : (t === 0 ? "Tx" : "M" + fmt(t))}</text>`;
    });
    // target bands (piecewise in x)
    (o.bands || []).forEach(b => {
      const x0 = X(Math.max(b.x0 ?? xMin, xMin)), x1 = X(Math.min(b.x1 ?? xMax, xMax));
      if (x1 > x0) g += `<rect x="${x0}" y="${Y(b.y1)}" width="${x1 - x0}" height="${Y(b.y0) - Y(b.y1)}" class="cx-band"/>`;
    });
    (o.zones || []).forEach(z => {
      g += `<rect x="${P.l}" y="${Y(Math.min(z.y1, yMax))}" width="${W - P.l - P.r}" height="${Y(z.y0) - Y(Math.min(z.y1, yMax))}" fill="${z.color}" opacity="${z.opacity || 0.08}"/>`;
    });
    (o.thresholds || []).forEach(t => {
      g += `<line x1="${P.l}" x2="${W - P.r}" y1="${Y(t.y)}" y2="${Y(t.y)}" class="cx-th" stroke="${t.color || "var(--ember)"}"/>`;
      g += `<text x="${W - P.r - 2}" y="${Y(t.y) - 4}" class="cx-thlab" text-anchor="end" fill="${t.color || "var(--ember)"}">${esc(t.label)}</text>`;
    });
    (o.events || []).forEach(e => {
      g += `<line x1="${X(e.x)}" x2="${X(e.x)}" y1="${P.t}" y2="${H - P.b}" class="cx-ev" stroke="${e.color}"/>`;
      g += `<circle cx="${X(e.x)}" cy="${P.t + 3}" r="3.5" fill="${e.color}"><title>${esc(e.label)}</title></circle>`;
    });
    o.series.forEach((s, si) => {
      const pts = s.points.filter(p => p.y != null).sort((a, b) => a.x - b.x);
      if (!pts.length) return;
      const d = pts.map((p, i) => `${i ? "L" : "M"}${X(p.x).toFixed(1)},${Y(p.y).toFixed(1)}`).join("");
      if (s.area) g += `<path d="${d}L${X(pts[pts.length - 1].x)},${H - P.b}L${X(pts[0].x)},${H - P.b}Z" fill="${s.color}" opacity=".12"/>`;
      g += `<path d="${d}" fill="none" stroke="${s.color}" stroke-width="${s.width || 2}" ${s.dashed ? 'stroke-dasharray="4 4"' : ""} stroke-linejoin="round" stroke-linecap="round"/>`;
      if (!s.noDots) pts.forEach((p, i) => {
        const last = i === pts.length - 1, flag = p.flag;
        g += `<circle cx="${X(p.x)}" cy="${Y(p.y)}" r="${last ? 4.5 : flag ? 3.5 : 2.2}" fill="${flag ? "var(--crit)" : last ? s.color : "var(--ink)"}" stroke="${flag ? "var(--crit)" : s.color}" stroke-width="1.5"><title>Month ${p.x}: ${esc(p.label ?? p.y)}</title></circle>`;
      });
      const lp = pts[pts.length - 1];
      if (o.endLabel !== false && si === 0) g += `<text x="${Math.min(X(lp.x) + 0, W - P.r)}" y="${Y(lp.y) - 9}" class="cx-end" text-anchor="end">${esc(lp.label ?? fmt(lp.y, o.yUnit))}</text>`;
    });
    return `<svg viewBox="0 0 ${W} ${H}" class="cx-chart" role="img" aria-label="${esc(o.aria || "chart")}" preserveAspectRatio="none">${g}</svg>`;
  };

  window.CXSpark = function (vals, color) {
    if (!vals || vals.length < 2) return "";
    const W = 72, H = 22, mn = Math.min(...vals), mx = Math.max(...vals), r = mx - mn || 0.01;
    const pts = vals.map((v, i) => [i / (vals.length - 1) * (W - 4) + 2, H - 3 - (v - mn) / r * (H - 6)]);
    return `<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" aria-hidden="true"><path d="${pts.map((p, i) => (i ? "L" : "M") + p.join(",")).join("")}" fill="none" stroke="${color}" stroke-width="1.6"/><circle cx="${pts.at(-1)[0]}" cy="${pts.at(-1)[1]}" r="2.4" fill="${color}"/></svg>`;
  };
})();
