// Data layer. "live" talks to the FastAPI backend; "demo" serves the bundled synthetic cohort
// when no backend is reachable (static preview).
(function () {
  const S = { mode: null, demo: null, reviews: {} };
  const ss = {
    get(k) { try { return sessionStorage.getItem(k); } catch { return null; } },
    set(k, v) { try { sessionStorage.setItem(k, v); } catch {} },
    del(k) { try { sessionStorage.removeItem(k); } catch {} },
  };

  async function j(url, opt = {}) {
    const r = await fetch(url, { credentials: "same-origin", headers: { "Content-Type": "application/json" }, ...opt });
    let body = null;
    try { body = await r.json(); } catch {}
    if (!r.ok) { const e = new Error((body && body.detail && (typeof body.detail === "string" ? body.detail : "Check the values you entered.")) || `Request failed (${r.status})`); e.status = r.status; throw e; }
    return body;
  }

  async function loadDemo() {
    if (!S.demo) S.demo = await (await fetch("assets/demo-data.json")).json();
    return S.demo;
  }

  const Cortex = {
    async init() {
      if (S.mode) return S.mode;
      try {
        const r = await fetch("/api/health", { cache: "no-store" });
        const b = r.ok ? await r.json() : null;
        S.mode = b && b.status === "ok" ? "live" : "demo";
      } catch { S.mode = "demo"; }
      return S.mode;
    },
    get mode() { return S.mode; },
    demoLogin() { ss.set("cx_demo_user", JSON.stringify({ name: "Demo clinician", role: "admin", email: "demo@preview" })); },
    async login(email, password) {
      if (S.mode === "demo") { Cortex.demoLogin(); return; }
      return j("/api/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
    },
    async logout() {
      if (S.mode === "demo") { ss.del("cx_demo_user"); return; }
      await j("/api/auth/logout", { method: "POST" });
    },
    async me() {
      if (S.mode === "demo") {
        const u = ss.get("cx_demo_user"); if (!u) { const e = new Error("Not signed in"); e.status = 401; throw e; }
        return JSON.parse(u);
      }
      return j("/api/auth/me");
    },
    async worklist() {
      if (S.mode === "live") return j("/api/worklist");
      const d = await loadDemo();
      const rows = d.patients.map(({ patient: p, summary: s }) => {
        const last = p.visits[p.visits.length - 1] || {};
        const rv = (S.reviews[p.id] || [])[0];
        return { id: p.id, name: p.display_name, sex: p.sex, age: p.age, months_since_tx: p.follow_up_months,
          donor_type: p.donor_type, risk_12m: s.risk_12m, risk_delta: s.risk_delta, band: s.band, alerts: s.alerts,
          egfr: last.egfr, ddcfdna: last.ddcfdna, dsa_mfi_max: last.dsa_mfi_max, tac_trough: last.tac_trough,
          spark: s.trajectory.map(t => t.risk).slice(-8), last_review: rv ? { by: rv.by, at: rv.at, decision: rv.decision } : null };
      });
      rows.sort((a, b) => (b.alerts.filter(x => x.severity === "high").length - a.alerts.filter(x => x.severity === "high").length) || (b.risk_12m - a.risk_12m));
      return { thresholds: d.thresholds, patients: rows };
    },
    async patient(id) {
      if (S.mode === "live") return j(`/api/patients/${encodeURIComponent(id)}`);
      const d = await loadDemo();
      const hit = d.patients.find(x => x.patient.id === id);
      if (!hit) { const e = new Error("Patient not found"); e.status = 404; throw e; }
      return { patient: hit.patient, summary: hit.summary, reviews: S.reviews[id] || [] };
    },
    async review(id, decision, note) {
      if (S.mode === "live") return j(`/api/patients/${encodeURIComponent(id)}/reviews`, { method: "POST", body: JSON.stringify({ decision, note }) });
      const u = await Cortex.me();
      (S.reviews[id] = S.reviews[id] || []).unshift({ by: u.name, at: new Date().toISOString(), decision, note });
    },
    async addVisit(id, v) {
      if (S.mode !== "live") throw new Error("Adding lab results needs the full deployment with the API server.");
      return j(`/api/patients/${encodeURIComponent(id)}/visits`, { method: "POST", body: JSON.stringify(v) });
    },
    async thresholds() {
      if (S.mode === "live") return j("/api/settings/thresholds");
      const d = await loadDemo(); return { values: d.thresholds, defaults: d.thresholds, info: d.threshold_info };
    },
    async saveThresholds(v) {
      if (S.mode !== "live") throw new Error("Saving thresholds needs the full deployment with the API server.");
      return j("/api/settings/thresholds", { method: "PUT", body: JSON.stringify(v) });
    },
    async model() { if (S.mode === "live") return j("/api/model"); return (await loadDemo()).model; },
    async audit() {
      if (S.mode === "live") return j("/api/audit");
      const out = [];
      Object.entries(S.reviews).forEach(([id, rs]) => rs.forEach(r => out.push({ at: r.at, user: r.by, action: "review", target: id, detail: r.decision })));
      return out.sort((a, b) => b.at.localeCompare(a.at));
    },
    async users() { if (S.mode === "live") return j("/api/users"); return [{ id: 1, email: "demo@preview", name: "Demo clinician", role: "admin" }]; },
    async createUser(u) {
      if (S.mode !== "live") throw new Error("Creating accounts needs the full deployment with the API server.");
      return j("/api/users", { method: "POST", body: JSON.stringify(u) });
    },
  };
  window.Cortex = Cortex;
})();
