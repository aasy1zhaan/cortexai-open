// CortexAI risk engine in the browser: same trained model as the server (exported by ml/export_browser_model.py).
(function () {
  let M = null;
  async function load() { if (!M) M = await (await fetch("assets/model.json")).json(); return M; }

  function raw(fold, x) {
    let s = fold.baseline;
    for (const t of fold.trees) {
      let i = 0;
      while (!t[i][5]) {
        const v = x[t[i][0]], n = t[i];
        i = (Number.isNaN(v) ? n[2] : v <= n[1]) ? n[3] : n[4];
      }
      s += t[i][6];
    }
    return s;
  }
  function interp(v, xs, ys) {
    if (v <= xs[0]) return ys[0];
    if (v >= xs[xs.length - 1]) return ys[ys.length - 1];
    let lo = 0, hi = xs.length - 1;
    while (hi - lo > 1) { const mid = (lo + hi) >> 1; if (xs[mid] <= v) lo = mid; else hi = mid; }
    return ys[lo] + (ys[hi] - ys[lo]) * (v - xs[lo]) / (xs[hi] - xs[lo] || 1);
  }
  function predictVec(x) { return M.folds.reduce((a, f) => a + interp(raw(f, x), f.cal_x, f.cal_y), 0) / M.folds.length; }
  const vec = o => M.features.map(f => (o[f] === null || o[f] === undefined || o[f] === "") ? NaN : +o[f]);

  function ckdEpi2021(scrMgDl, age, sex) {
    const f = sex === "F", k = f ? 0.7 : 0.9, a = f ? -0.241 : -0.302, r = scrMgDl / k;
    return 142 * Math.pow(Math.min(r, 1), a) * Math.pow(Math.max(r, 1), -1.2) * Math.pow(0.9938, age) * (f ? 1.012 : 1);
  }

  window.CortexEngine = {
    load, ckdEpi2021,
    get features() { return M.features; }, get labels() { return M.labels; },
    predict(o) { return predictVec(vec(o)); },
    explain(o, top = 6) {
      const x = vec(o), base = predictVec(x), out = [];
      M.features.forEach((f, i) => {
        if (f === "months_since_tx") return;
        const alt = x.slice(); alt[i] = M.reference[f];
        const d = (base - predictVec(alt)) * 100;
        if (Math.abs(d) >= 0.3) out.push({ feature: f, label: M.labels[f], value: x[i], pp: d });
      });
      return out.sort((a, b) => Math.abs(b.pp) - Math.abs(a.pp)).slice(0, top);
    },
  };
})();
