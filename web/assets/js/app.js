// CortexAI Clinic — clinician workspace (worklist, patient chart, model card, settings, audit).
(function () {
  const $ = s => document.querySelector(s);
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const pct = (v, d = 0) => (v * 100).toFixed(d) + "%";
  const n0 = v => v == null ? "—" : Math.round(v).toLocaleString("en-US");
  const n1 = v => v == null ? "—" : (+v).toFixed(1);
  const n2 = v => v == null ? "—" : (+v).toFixed(2);
  const when = iso => { try { return new Date(iso).toLocaleString("en-GB", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }); } catch { return iso; } };
  const BAND = { high: ["High", "var(--crit)"], moderate: ["Moderate", "var(--warn)"], low: ["Low", "var(--ok)"] };
  const DECISIONS = { reviewed: "Reviewed, no change", repeat_tests: "Repeat tests ordered", biopsy_requested: "For-cause biopsy requested", escalate: "Escalated to MDT", no_action: "No action needed" };
  const LOCI = ["A", "B", "C", "DRB1", "DQB1"];
  const S = { user: null, wl: null, filter: "all", q: "", unit: (() => { try { return localStorage.getItem("cx_unit") || "umol"; } catch { return "umol"; } })() };
  const crea = v => v == null ? null : S.unit === "umol" ? (v.creatinine_umol ?? Math.round(v.creatinine * 88.42)) : v.creatinine;
  const creaUnit = () => S.unit === "umol" ? "µmol/L" : "mg/dL";
  const creaFmt = v => v == null ? "—" : S.unit === "umol" ? n0(crea(v)) : n2(crea(v));

  // lab tile in the style of a results card: big value, change vs previous, last values as dots against a reference line
  function labTile({ title, value, unit, prev, lowerIsBetter, ref, flag, values, status, warn, fmt }) {
    const c = flag ? "var(--crit)" : warn ? "var(--warn)" : "var(--sky)";
    let delta = "";
    if (prev != null && value != null && typeof value === "number") {
      const d = value - prev, rel = prev ? Math.abs(d / prev) : 0;
      const worse = lowerIsBetter === undefined ? null : (lowerIsBetter ? d > 0 : d < 0);
      const cls = rel < 0.03 ? "flat" : worse === null ? "flat" : worse ? "bad" : "good";
      const shown = Math.abs(d) >= 100 ? n0(Math.abs(d)) : Math.abs(d) >= 10 ? n1(Math.abs(d)) : n2(Math.abs(d));
      delta = `<span class="ld ${cls}">${d >= 0 ? "+" : "−"}${shown} vs previous</span>`;
    }
    const vals = (values || []).filter(x => x != null).slice(-6);
    let svg = "";
    if (vals.length) {
      const all = ref != null ? vals.concat([ref]) : vals, mn = Math.min(...all), mx = Math.max(...all), r = (mx - mn) || 1;
      const Y = v => 38 - (v - mn) / r * 30, X = i => 8 + i * (144 / Math.max(vals.length - 1, 1));
      svg = `<svg viewBox="0 0 160 44" aria-hidden="true">${ref != null ? `<line x1="0" x2="160" y1="${Y(ref)}" y2="${Y(ref)}" stroke="rgba(200,220,255,.35)" stroke-dasharray="3 3"/>` : ""}`
        + vals.map((v, i) => { const last = i === vals.length - 1, hot = ref != null && (lowerIsBetter === false ? v < ref : v >= ref);
          return last ? `<circle cx="${X(i)}" cy="${Y(v)}" r="5.5" fill="none" stroke="${hot ? "#ff8f86" : "#fff"}" stroke-width="1.5"/><circle cx="${X(i)}" cy="${Y(v)}" r="2.6" fill="${hot ? "#ff8f86" : "#fff"}"/>`
            : `<circle cx="${X(i)}" cy="${Y(v)}" r="2.6" fill="${hot ? "#ff8f86" : "rgba(220,232,255,.75)"}"/>`; }).join("") + "</svg>";
    }
    return `<div class="lab" style="--c:${c}"><div class="lt"><i></i>${title}</div><div class="lv"><b class="num">${value == null ? "—" : fmt ? fmt(value) : typeof value === "number" ? (Math.abs(value) >= 100 ? n0(value) : value % 1 ? (+value).toFixed(value < 10 ? 2 : 1) : value) : esc(value)}</b><small>${unit || ""}</small></div>${delta}${svg}<div class="ls">${esc(status || "")}</div></div>`;
  }

  const view = $("#view");
  function setTitle(t, crumb) { $("#title").textContent = t; $("#crumb").innerHTML = crumb || ""; document.title = `${t} · CortexAI Clinic`; }
  function navOn(name) { document.querySelectorAll(".rail a[data-v]").forEach(a => a.classList.toggle("on", a.dataset.v === name)); }
  function err(e) { view.innerHTML = `<div class="panel errbox"><b>Could not load this view.</b><p>${esc(e.message)}</p><a class="btn" href="#worklist">Back to worklist</a></div>`; }

  // ---------- worklist ----------
  async function renderWorklist() {
    navOn("worklist"); setTitle("Worklist", "Recipients ordered by high-severity alerts, then by predicted risk");
    view.innerHTML = `<div class="loading">Loading worklist…</div>`;
    S.wl = await Cortex.worklist();
    const P = S.wl.patients, th = S.wl.thresholds;
    const has = (p, c) => p.alerts.some(a => a.code === c);
    const needs = P.filter(p => p.alerts.some(a => a.severity === "high") && !p.last_review);
    const tiles = [
      ["Need review", needs.length, "High-severity alert, not yet reviewed", "var(--crit)", "unreviewed"],
      ["High risk", P.filter(p => p.band === "high").length, `Predicted 12-month risk ≥ ${pct(th.risk_high)}`, "var(--ember)", "high"],
      [`dd-cfDNA ≥ ${th.ddcfdna_pct}%`, P.filter(p => has(p, "ddcfdna")).length, "At the latest visit", "var(--warn)", "ddcfdna"],
      ["DSA positive", P.filter(p => has(p, "dsa")).length, `Immunodominant MFI ≥ ${n0(th.dsa_mfi)}`, "var(--blue)", "dsa"],
      ["Recipients", P.length, "Under active follow-up", "var(--muted)", "all"],
    ];
    view.innerHTML = `
      <div class="tiles">${tiles.map(([k, v, s, c, f]) => `<button class="tile${S.filter === f ? " on" : ""}" data-f="${f}" style="--c:${c}"><span class="tk">${k}</span><span class="tv num">${v}</span><span class="ts">${s}</span></button>`).join("")}</div>
      <div class="panel wl">
        <div class="wl-tools">
          <div class="chips" role="group" aria-label="Filter">${[["all", "All"], ["unreviewed", "Needs review"], ["high", "High risk"], ["ddcfdna", "dd-cfDNA"], ["dsa", "DSA+"], ["tac", "Tacrolimus"]].map(([f, l]) => `<button class="fchip${S.filter === f ? " on" : ""}" data-f="${f}">${l}</button>`).join("")}</div>
          <label class="search" for="q"><span class="sr">Search recipients</span><input id="q" placeholder="Search ID or name" value="${esc(S.q)}" autocomplete="off"></label>
        </div>
        <div class="tbl-wrap"><table class="tbl">
          <thead><tr><th class="sev-h"></th><th>Recipient</th><th>Post-Tx</th><th>12-mo risk</th><th class="r">eGFR</th><th class="r">dd-cfDNA</th><th class="r">DSA MFI</th><th class="r">Tac C0</th><th>Signals</th><th>Last review</th></tr></thead>
          <tbody id="rows"></tbody>
        </table></div>
      </div>`;
    const draw = () => {
      const q = S.q.toLowerCase();
      const rows = P.filter(p => {
        if (q && !(`${p.id} ${p.name}`.toLowerCase().includes(q))) return false;
        switch (S.filter) {
          case "unreviewed": return p.alerts.some(a => a.severity === "high") && !p.last_review;
          case "high": return p.band === "high";
          case "ddcfdna": return has(p, "ddcfdna");
          case "dsa": return has(p, "dsa");
          case "tac": return has(p, "tac_low") || has(p, "tac_cv");
          default: return true;
        }
      });
      $("#rows").innerHTML = rows.length ? rows.map(p => {
        const sev = p.alerts.some(a => a.severity === "high") ? "var(--crit)" : p.alerts.length ? "var(--warn)" : "var(--ok)";
        const [bl, bc] = BAND[p.band];
        const d = p.risk_delta, arrow = Math.abs(d) < 0.01 ? "" : `<span class="delta ${d > 0 ? "up" : "down"}">${d > 0 ? "▲" : "▼"} ${Math.abs(d * 100).toFixed(0)}</span>`;
        const shown = p.alerts.length > 1 ? p.alerts.filter(a => a.code !== "risk_high") : p.alerts;
        const chips = shown.slice(0, 3).map(a => `<span class="chip ${a.severity === "high" ? "hi" : "md"}">${esc(a.title)}</span>`).join("") + (shown.length > 3 ? `<span class="more">+${shown.length - 3}</span>` : "");
        return `<tr tabindex="0" data-id="${esc(p.id)}">
          <td><span class="sev" style="background:${sev}"></span></td>
          <td><b>${esc(p.name)}</b><div class="sub mono">${esc(p.id)} · ${p.sex} ${p.age}</div></td>
          <td class="num">${p.months_since_tx} mo<div class="sub">${p.donor_type}</div></td>
          <td><div class="riskcell"><span class="num rv" style="color:${bc}">${pct(p.risk_12m)}</span>${arrow}${CXSpark(p.spark, bc)}</div><div class="sub">${bl}</div></td>
          <td class="r num">${n0(p.egfr)}</td>
          <td class="r num ${p.ddcfdna >= th.ddcfdna_pct ? "hot" : ""}">${n2(p.ddcfdna)}%</td>
          <td class="r num ${p.dsa_mfi_max >= th.dsa_mfi ? "hot" : ""}">${p.dsa_mfi_max ? n0(p.dsa_mfi_max) : "—"}</td>
          <td class="r num">${n1(p.tac_trough)}</td>
          <td class="sig">${chips || '<span class="sub">No signals</span>'}</td>
          <td>${p.last_review ? `<span class="rv-ok">${esc(DECISIONS[p.last_review.decision] || p.last_review.decision)}</span><div class="sub">${esc(p.last_review.by)} · ${when(p.last_review.at)}</div>` : '<span class="sub">Not reviewed</span>'}</td>
        </tr>`;
      }).join("") : `<tr><td colspan="10" class="empty">No recipients match this filter.</td></tr>`;
    };
    draw();
    view.querySelectorAll("[data-f]").forEach(b => b.onclick = () => { S.filter = b.dataset.f; renderWorklist(); });
    $("#q").oninput = e => { S.q = e.target.value; draw(); };
    $("#rows").onclick = e => { const tr = e.target.closest("tr[data-id]"); if (tr) location.hash = "patient-" + tr.dataset.id; };
    $("#rows").onkeydown = e => { if (e.key === "Enter") { const tr = e.target.closest("tr[data-id]"); if (tr) location.hash = "patient-" + tr.dataset.id; } };
  }

  // ---------- patient ----------
  async function renderPatient(id) {
    navOn("worklist");
    view.innerHTML = `<div class="loading">Loading recipient…</div>`;
    const { patient: p, summary: s, reviews } = await Cortex.patient(id);
    const th = (S.wl && S.wl.thresholds) || (await Cortex.thresholds()).values;
    setTitle(p.display_name, `<a href="#worklist">Worklist</a> / <span class="mono">${esc(p.id)}</span>`);
    const V = p.visits, last = V[V.length - 1] || {};
    const [bl, bc] = BAND[s.band];
    const events = [...p.biopsies.map(b => ({ x: b.month, color: /reject|ABMR|TCMR/i.test(b.result) && !/No rejection/.test(b.result) ? "var(--crit)" : "var(--muted)", label: `Biopsy (${b.indication}): ${b.result}` }))];
    const series = (key, color, flag) => [{ color, area: true, points: V.map(v => ({ x: v.month, y: v[key], flag: flag && flag(v) })) }];
    const tacBands = [{ x0: 0, x1: 3, y0: 8, y1: 12 }, { x0: 3, x1: 999, y0: 5, y1: 8 }];
    const charts = [
      ["eGFR", "mL/min/1.73m²", `${n0(last.egfr)} · ${last.egfr_change_3m > 0 ? "+" : ""}${n0(last.egfr_change_3m)}% vs 3 mo`, CXChart({ series: series("egfr", "var(--blue)", v => v.egfr_change_3m <= -th.egfr_drop_pct), events, aria: "eGFR trend" })],
      ["Tacrolimus trough", "ng/mL · shaded = target", `CV ${last.tac_cv == null ? "—" : n0(last.tac_cv) + "%"} · TTR ${n0(last.tac_ttr)}%`, CXChart({ series: series("tac_trough", "#b48bff", v => v.tac_trough < v.tac_target_low), bands: tacBands, aria: "Tacrolimus trough trend" })],
      ["dd-cfDNA", "% of total cfDNA", `${n2(last.ddcfdna)}%`, CXChart({ series: series("ddcfdna", "var(--ember)", v => v.ddcfdna >= th.ddcfdna_pct), thresholds: [{ y: th.ddcfdna_pct, label: `${th.ddcfdna_pct}%` }], events, yUnit: "%", aria: "dd-cfDNA trend" })],
      ["DSA, immunodominant MFI", (last.dsa && last.dsa[0]) ? `anti-${last.dsa[0].spec} · class ${last.dsa[0].class}` : "Single-antigen beads", last.dsa_mfi_max ? n0(last.dsa_mfi_max) : "Negative", CXChart({ series: series("dsa_mfi_max", "#5ad1ff", v => v.dsa_mfi_max >= th.dsa_mfi), thresholds: [{ y: th.dsa_mfi, label: `MFI ${n0(th.dsa_mfi)}` }], aria: "DSA MFI trend" })],
      ["Proteinuria", "UPCR g/g", n2(last.upcr), CXChart({ series: series("upcr", "#ffd166", v => v.upcr >= th.upcr_g_g), thresholds: [{ y: th.upcr_g_g, label: `${th.upcr_g_g} g/g` }], aria: "UPCR trend" })],
      ["Creatinine", creaUnit(), creaFmt(last), CXChart({ series: [{ color: "#9fb4d6", area: true, points: V.map(v => ({ x: v.month, y: crea(v) })) }], events, zero: false, aria: "Creatinine trend" })],
    ];
    const maxAbs = Math.max(...s.drivers.map(d => Math.abs(d.contribution_pp)), 2);
    const unit = { egfr: " mL/min", upcr: " g/g", tac_trough: " ng/mL", tac_cv: "%", tac_ttr: "%", ddcfdna: "%", dsa_mfi_max: "", cpra: "%", months_since_tx: " mo", egfr_change_3m: "%", recipient_age: " y", donor_age: " y" };
    const fmtV = (f, v) => v == null ? "n/a" : ["donor_deceased", "retransplant", "induction_atg", "dgf", "bk_viremia", "prior_rejection", "dsa_class2"].includes(f) ? (v ? "Yes" : "No") : (Math.abs(v) >= 100 ? n0(v) : (+v).toFixed(v % 1 ? 2 : 0).replace(/\.?0+$/, "")) + (unit[f] || "");
    const mm = p.hla.mismatched;
    const hlaRows = LOCI.map(l => `<tr><th>${l}</th>
      <td>${p.hla.recipient[l].map(a => `<span class="al">${l}*${a}</span>`).join("")}</td>
      <td>${p.hla.donor[l].map(a => `<span class="al ${mm[l].includes(a) ? "mm" : ""}">${l}*${a}</span>`).join("")}</td>
      <td class="num">${mm[l].length}</td></tr>`).join("");
    const epletPct = Math.min(100, p.eplet_mm_class2 / 40 * 100), epletTh = th.eplet_class2 / 40 * 100;
    const isLive = Cortex.mode === "live";

    view.innerHTML = `
      <section class="pt-head panel">
        <div class="pt-id">
          <div class="pt-name"><h2>${esc(p.display_name)}</h2><span class="mono sub">${esc(p.id)} · ${p.sex === "F" ? "Female" : "Male"}, ${p.age} y</span></div>
          <dl class="facts">
            <div><dt>Post-transplant</dt><dd>${p.follow_up_months} months</dd></div>
            <div><dt>Donor</dt><dd>${p.donor_type === "living" ? "Living" : "Deceased"}, ${p.donor_age} y</dd></div>
            <div><dt>Induction</dt><dd>${esc(p.induction)}</dd></div>
            <div><dt>Maintenance</dt><dd>${esc(p.maintenance)}</dd></div>
            <div><dt>cPRA</dt><dd>${p.cpra}%</dd></div>
            <div><dt>DGF</dt><dd>${p.dgf ? "Yes" : "No"}${p.retransplant ? " · Re-Tx" : ""}</dd></div>
            <div><dt>CIT</dt><dd>${p.cold_ischemia_h} h</dd></div>
            <div><dt>Centre</dt><dd>${esc(p.centre)}</dd></div>
          </dl>
        </div>
        <div class="pt-risk" style="--c:${bc}">
          <span class="eyebrow">12-month rejection risk</span>
          <div class="big num">${pct(s.risk_12m)}</div>
          <div class="rk-row"><span class="band" style="background:${bc}">${bl}</span><span class="sub">${s.risk_delta >= 0 ? "+" : ""}${(s.risk_delta * 100).toFixed(0)} pts vs previous visit</span></div>
          <div class="acts"><a class="btn btn-blue" href="#review" id="toReview">Record review</a><button class="btn" id="addVisit" ${isLive ? "" : 'title="Needs the API server"'}>Add lab results</button></div>
        </div>
      </section>

      <div class="labs-h"><h3>Latest results · month ${last.month}</h3><span class="sub">Dots show the last six measurements; dashed line is the threshold or target</span></div>
      <div class="labs">${(() => { const pv = V.length > 1 ? V[V.length - 2] : null, series = k => V.map(v => v[k]);
        return [
          labTile({ title: "eGFR", value: last.egfr, unit: "mL/min/1.73m²", prev: pv && pv.egfr, lowerIsBetter: false, values: series("egfr"), flag: last.month >= 3 && last.egfr_change_3m <= -th.egfr_drop_pct, status: `${last.egfr_change_3m > 0 ? "+" : ""}${n0(last.egfr_change_3m)}% vs ~3 months · CKD-EPI 2021` }),
          labTile({ title: "Creatinine", value: crea(last), unit: creaUnit(), fmt: v => S.unit === "umol" ? n0(v) : n2(v), prev: pv && crea(pv), lowerIsBetter: true, values: V.map(crea), status: "Serum creatinine" }),
          labTile({ title: "Proteinuria", value: last.upcr, unit: "g/g", prev: pv && pv.upcr, lowerIsBetter: true, values: series("upcr"), ref: th.upcr_g_g, flag: last.upcr >= th.upcr_g_g, status: last.upcr >= th.upcr_g_g ? "Above threshold" : "Below threshold" }),
          labTile({ title: "Tacrolimus C0", value: last.tac_trough, unit: "ng/mL", prev: pv && pv.tac_trough, values: series("tac_trough"), ref: last.tac_target_low, warn: last.tac_trough < last.tac_target_low || last.tac_trough > last.tac_target_high, status: `Target ${last.tac_target_low}–${last.tac_target_high} · TTR ${n0(last.tac_ttr)}%` }),
          labTile({ title: "Tacrolimus variability", value: last.tac_cv, unit: last.tac_cv == null ? "" : "% CV", prev: pv && pv.tac_cv, lowerIsBetter: true, values: series("tac_cv"), ref: th.tac_cv_pct, warn: last.tac_cv != null && last.tac_cv > th.tac_cv_pct, status: last.tac_cv == null ? "Needs ≥ 3 stable-phase troughs" : "Stable phase, last 6 months" }),
          labTile({ title: "dd-cfDNA", value: last.ddcfdna, unit: "%", prev: pv && pv.ddcfdna, lowerIsBetter: true, values: series("ddcfdna"), ref: th.ddcfdna_pct, flag: last.month >= 1 && last.ddcfdna >= th.ddcfdna_pct, status: last.month < 1 ? "Physiologically raised in month 1" : last.ddcfdna >= th.ddcfdna_pct ? "Above threshold" : "Below threshold" }),
          labTile({ title: "DSA, immunodominant", value: last.dsa_mfi_max || "Negative", unit: last.dsa_mfi_max ? "MFI" : "", prev: pv && last.dsa_mfi_max ? pv.dsa_mfi_max : null, lowerIsBetter: true, values: series("dsa_mfi_max"), ref: th.dsa_mfi, flag: last.dsa_mfi_max >= th.dsa_mfi, status: last.dsa && last.dsa[0] ? `anti-${last.dsa[0].spec}, class ${last.dsa[0].class}` : "Single-antigen beads" }),
          labTile({ title: "BK virus PCR", value: last.bk_viremia ? "Detected" : "Not detected", warn: !!last.bk_viremia, status: "Plasma BK viremia" }),
        ].join(""); })()}</div>

      <div class="grid g-2-1">
        <section class="panel">
          <header class="ph"><h3>Risk trajectory</h3><span class="sub">Model estimate at each visit · red markers = rejection on biopsy</span></header>
          ${CXChart({ series: [{ color: bc, area: true, width: 2.4, points: s.trajectory.map(t => ({ x: t.month, y: t.risk * 100, label: pct(t.risk) })) }], yUnit: "%", yMin: 0, yMax: Math.max(60, s.risk_12m * 110),
            zones: [{ y0: th.risk_high * 100, y1: 100, color: "var(--crit)", opacity: .07 }, { y0: th.risk_moderate * 100, y1: th.risk_high * 100, color: "var(--warn)", opacity: .05 }],
            events: events.filter(e => e.color === "var(--crit)"), height: 230, width: 760, aria: "Risk trajectory" })}
          <h4 class="mini">Recent visits</h4>
          <div class="tbl-wrap"><table class="tbl compact vlog"><thead><tr><th>Month</th><th class="r">Risk</th><th class="r">Creat. <span style="text-transform:none">${creaUnit()}</span></th><th class="r">eGFR</th><th class="r">UPCR</th><th class="r">Tac C0</th><th class="r">dd-cfDNA</th><th class="r">DSA MFI</th></tr></thead><tbody>
          ${V.slice(-6).reverse().map(v => { const tr = s.trajectory.find(t => t.month === v.month); return `<tr><td class="mono">M${v.month}</td><td class="r num">${tr ? pct(tr.risk) : "—"}</td><td class="r num">${creaFmt(v)}</td><td class="r num">${n0(v.egfr)}</td><td class="r num ${v.upcr >= th.upcr_g_g ? "hot" : ""}">${n2(v.upcr)}</td><td class="r num ${v.tac_trough < v.tac_target_low ? "hot" : ""}">${n1(v.tac_trough)}</td><td class="r num ${v.ddcfdna >= th.ddcfdna_pct ? "hot" : ""}">${n2(v.ddcfdna)}%</td><td class="r num ${v.dsa_mfi_max >= th.dsa_mfi ? "hot" : ""}">${v.dsa_mfi_max ? n0(v.dsa_mfi_max) : "—"}</td></tr>`; }).join("")}
          </tbody></table></div>
        </section>
        <section class="panel">
          <header class="ph"><h3>Signals</h3><span class="sub">${s.alerts.length} active</span></header>
          <ul class="alerts">${s.alerts.length ? s.alerts.map(a => `<li class="${a.severity}"><b>${esc(a.title)}</b><span>${esc(a.detail)}</span></li>`).join("") : `<li class="none"><b>No active signals</b><span>All monitored markers within thresholds.</span></li>`}</ul>
          <h4 class="mini">Considerations for the treating team</h4>
          <ul class="cons">${s.considerations.map(c => `<li>${esc(c)}</li>`).join("")}</ul>
          <p class="disclaimer">Decision support only. Follow your centre's protocol; the treating clinician decides.</p>
        </section>
      </div>

      <div class="grid g-1-1">
        <section class="panel">
          <header class="ph"><h3>Why this estimate</h3><span class="sub">Contribution to 12-month risk, latest visit</span></header>
          <ul class="drivers">${s.drivers.length ? s.drivers.map(d => { const w = Math.abs(d.contribution_pp) / maxAbs * 50; const up = d.contribution_pp > 0; return `<li><span class="dl">${esc(d.label)}</span><span class="dv num">${esc(fmtV(d.feature, d.value))}</span><span class="bar"><i style="${up ? `left:50%;width:${w}%;background:var(--crit)` : `right:50%;width:${w}%;background:var(--ok)`}"></i></span><span class="dc num ${up ? "up" : "down"}">${up ? "+" : "−"}${Math.abs(d.contribution_pp).toFixed(1)} pp</span></li>`; }).join("") : '<li class="sub">No single factor moves the risk by more than 0.3 points.</li>'}</ul>
          <p class="disclaimer">Each factor is reset to a typical stable recipient and the patient is re-scored by the same model; the bar is the change in 12-month risk, in percentage points. Red raises risk, green lowers it.</p>
        </section>
        <section class="panel">
          <header class="ph"><h3>Immunogenetics</h3><span class="sub">Donor vs recipient, mismatched donor alleles highlighted</span></header>
          <div class="tbl-wrap"><table class="hla"><thead><tr><th>Locus</th><th>Recipient</th><th>Donor</th><th>MM</th></tr></thead><tbody>${hlaRows}</tbody></table></div>
          <div class="imm">
            <div><span>A/B/DR mismatch</span><b class="num">${p.hla_mismatch}/6</b></div>
            <div><span>PIRCHE-II</span><b class="num">${p.pirche_ii}</b></div>
            <div><span>Preformed DSA</span><b>${p.preformed_dsa ? "Yes" : "No"}</b></div>
          </div>
          <div class="sub">Current DSA (latest single-antigen bead test)</div>
          <div class="dsa-list">${(last.dsa || []).length ? last.dsa.map(d => `<span class="${d.mfi < th.dsa_mfi ? "lo" : ""}">anti-${esc(d.spec)} · class ${esc(d.class)} · MFI ${n0(d.mfi)}</span>`).join("") : '<span class="lo">No donor-specific antibodies detected</span>'}</div>
          <div class="eplet">
            <div class="el-h"><span>Class II eplet mismatch (DR+DQ)</span><b class="num ${s.eplet_flag ? "hotc" : ""}">${p.eplet_mm_class2}</b></div>
            <div class="el-bar"><i style="width:${epletPct}%"></i><em style="left:${epletTh}%" title="Threshold ${th.eplet_class2}"></em></div>
            <p class="disclaimer">${s.eplet_flag ? `At or above ${th.eplet_class2}: higher reported risk of de novo class II DSA.` : `Below ${th.eplet_class2}.`} Eplet and PIRCHE-II values in this demo are simulated.</p>
          </div>
        </section>
      </div>

      <section class="panel">
        <header class="ph"><h3>Trends since transplant</h3><span class="sub">Red points cross a threshold · vertical lines mark biopsies</span></header>
        <div class="trends">${charts.map(([t, u, v, svg]) => `<figure><figcaption><b>${t}</b><span class="num">${esc(v)}</span></figcaption><div class="u">${u}</div>${svg}</figure>`).join("")}</div>
      </section>

      <div class="grid g-1-1">
        <section class="panel">
          <header class="ph"><h3>Biopsies and episodes</h3><span class="sub">Banff classification</span></header>
          <ol class="bx">${p.biopsies.length ? p.biopsies.slice().reverse().map(b => { const rej = !/No rejection/.test(b.result); return `<li class="${rej ? "rej" : ""}"><span class="mono">M${b.month}</span><div><b>${esc(b.result)}</b><span>${b.indication === "protocol" ? "Protocol biopsy" : "For-cause biopsy"}</span></div></li>`; }).join("") : '<li class="none"><div><b>No biopsies yet</b></div></li>'}</ol>
        </section>
        <section class="panel" id="review">
          <header class="ph"><h3>Clinical review</h3><span class="sub">Recorded in the audit log</span></header>
          <form id="rvf" class="rvf">
            <label for="dec">Decision</label>
            <select id="dec">${Object.entries(DECISIONS).map(([k, v]) => `<option value="${k}">${v}</option>`).join("")}</select>
            <label for="note">Note</label>
            <textarea id="note" rows="3" maxlength="2000" placeholder="Reasoning, orders, follow-up date"></textarea>
            <div class="rv-actions"><button class="btn btn-blue" type="submit">Save review</button><span id="rvmsg" class="sub" role="status"></span></div>
          </form>
          <ul class="rvlist">${reviews.length ? reviews.map(r => `<li><b>${esc(DECISIONS[r.decision] || r.decision)}</b><span class="sub">${esc(r.by)} · ${when(r.at)}</span>${r.note ? `<p>${esc(r.note)}</p>` : ""}</li>`).join("") : '<li class="sub">No reviews yet.</li>'}</ul>
        </section>
      </div>`;

    $("#toReview").onclick = e => { e.preventDefault(); $("#review").scrollIntoView({ behavior: "smooth" }); $("#dec").focus(); };
    $("#rvf").onsubmit = async e => {
      e.preventDefault(); const m = $("#rvmsg"); m.textContent = "Saving…";
      try { await Cortex.review(p.id, $("#dec").value, $("#note").value.trim()); S.wl = null; renderPatient(p.id); }
      catch (x) { m.textContent = x.message; }
    };
    $("#addVisit").onclick = () => openVisit(p);
  }

  function openVisit(p) {
    const last = p.visits[p.visits.length - 1] || {};
    const dlg = $("#dlg"), live = Cortex.mode === "live";
    const top = (last.dsa || [])[0] || {};
    dlg.innerHTML = `<form id="vf" class="vf">
      <h3>Add lab results · ${esc(p.id)}</h3>
      ${!live ? `<p class="note">This preview has no API server, so new results cannot be saved or re-scored here.</p>` : ""}
      <div class="vgrid">
        <label for="v_month">Month post-transplant<input id="v_month" type="number" step="0.25" value="${(last.month || 0) + 1}" required></label>
        <label for="v_cr">Creatinine (${creaUnit()})<input id="v_cr" type="number" step="${S.unit === "umol" ? 1 : 0.01}" value="${crea(last) ?? ""}" required></label>
        <label for="v_upcr">UPCR (g/g)<input id="v_upcr" type="number" step="0.01" value="${last.upcr ?? ""}" required></label>
        <label for="v_tac">Tacrolimus trough (ng/mL)<input id="v_tac" type="number" step="0.1" value="${last.tac_trough ?? ""}" required></label>
        <label for="v_dd">dd-cfDNA (%)<input id="v_dd" type="number" step="0.01" value="${last.ddcfdna ?? ""}" required></label>
        <label for="v_dsa_spec">DSA specificity (blank if none)<input id="v_dsa_spec" placeholder="e.g. DQ7" value="${esc(top.spec || "")}"></label>
        <label for="v_dsa_cls">DSA class<select id="v_dsa_cls"><option value="II" ${top.class !== "I" ? "selected" : ""}>Class II</option><option value="I" ${top.class === "I" ? "selected" : ""}>Class I</option></select></label>
        <label for="v_dsa_mfi">DSA MFI<input id="v_dsa_mfi" type="number" step="1" value="${top.mfi ?? ""}"></label>
        <label for="v_bk" class="ck"><input id="v_bk" type="checkbox" ${last.bk_viremia ? "checked" : ""}> BK viremia detected</label>
      </div>
      <p class="sub">eGFR is calculated from creatinine with CKD-EPI 2021. Tacrolimus CV, time in range and the 3-month eGFR change are derived automatically.</p>
      <div class="sub" id="vmsg" role="status"></div>
      <div class="rv-actions"><button class="btn" type="button" id="vcancel">Cancel</button><button class="btn btn-blue" type="submit" ${live ? "" : "disabled"}>Save and re-score</button></div>
    </form>`;
    dlg.showModal();
    $("#vcancel").onclick = () => dlg.close();
    $("#vf").onsubmit = async e => {
      e.preventDefault();
      const num = id => parseFloat($(id).value);
      const spec = $("#v_dsa_spec").value.trim(), mfi = num("#v_dsa_mfi");
      const body = { month: num("#v_month"), creatinine: num("#v_cr"), creatinine_unit: S.unit === "umol" ? "umol/L" : "mg/dL",
        upcr: num("#v_upcr"), tac_trough: num("#v_tac"), ddcfdna: num("#v_dd"), bk_viremia: $("#v_bk").checked ? 1 : 0,
        dsa: spec && mfi >= 0 ? [{ spec, hla_class: $("#v_dsa_cls").value, mfi }] : [] };
      if (Object.values(body).some(v => typeof v === "number" && isNaN(v))) { $("#vmsg").textContent = "Fill in every numeric field."; return; }
      try { await Cortex.addVisit(p.id, body); dlg.close(); S.wl = null; renderPatient(p.id); }
      catch (x) { $("#vmsg").textContent = x.message; }
    };
  }

  // ---------- model card ----------
  async function renderModel() {
    navOn("model"); setTitle("Model card", "What the model is for, how it was built and where it falls short");
    const m = await Cortex.model(), g = m.gbm;
    const cal = g.calibration_deciles || [];
    const calSvg = CXChart({ series: [{ color: "var(--blue)", points: cal.map(c => ({ x: c.predicted * 100, y: c.observed * 100, label: `pred ${pct(c.predicted)} · obs ${pct(c.observed)}` })) },
      { color: "var(--muted)", dashed: true, width: 1, noDots: true, points: [{ x: 0, y: 0 }, { x: Math.max(...cal.map(c => c.predicted * 100), 50), y: Math.max(...cal.map(c => c.predicted * 100), 50) }] }],
      yUnit: "%", xMin: 0, yMin: 0, endLabel: false, height: 220, xFmt: t => t + "%", aria: "Calibration plot" });
    view.innerHTML = `
      <div class="grid g-1-1">
        <section class="panel prose">
          <header class="ph"><h3>Intended use</h3></header>
          <p>Estimate the probability of biopsy-proven T-cell-mediated or antibody-mediated rejection within 12 months of a clinic visit, for adult kidney transplant recipients 1–24 months after transplantation, to help transplant teams prioritise review.</p>
          <dl class="kv"><dt>Target</dt><dd>${esc(m.target)}</dd><dt>Unit</dt><dd>${esc(m.unit)}</dd><dt>Model</dt><dd>${esc(m.model)}</dd><dt>Explanations</dt><dd>${esc(m.explainer)}</dd><dt>Data</dt><dd>${esc(m.data)}</dd></dl>
        </section>
        <section class="panel">
          <header class="ph"><h3>Held-out performance</h3><span class="sub">Synthetic test set, split by patient</span></header>
          <div class="mtiles">
            <div><span>ROC-AUC</span><b class="num">${g.roc_auc.toFixed(2)}</b></div>
            <div><span>PR-AUC</span><b class="num">${g.pr_auc.toFixed(2)}</b></div>
            <div><span>Brier</span><b class="num">${g.brier.toFixed(3)}</b></div>
            <div><span>Event rate</span><b class="num">${pct(m.event_rate, 1)}</b></div>
          </div>
          <p class="sub">${n0(m.n_patients)} simulated recipients · ${n0(m.n_visits_train)} training visits · ${n0(m.n_visits_test)} test visits. Logistic baseline ROC-AUC ${m.logistic.roc_auc.toFixed(2)}.</p>
          <h4 class="mini">Calibration (deciles)</h4>
          ${calSvg}
          <p class="disclaimer">Observed vs predicted event rate. The dashed line is perfect calibration.</p>
        </section>
      </div>
      <section class="panel prose">
        <header class="ph"><h3>Limitations</h3></header>
        <ul class="lims">${m.limitations.map(l => `<li>${esc(l)}</li>`).join("")}</ul>
      </section>`;
  }

  // ---------- thresholds ----------
  async function renderThresholds() {
    navOn("thresholds"); setTitle("Alert thresholds", "Centre-specific cut-offs used for signals and risk bands");
    const t = await Cortex.thresholds();
    const single = (window.CORTEX_CONFIG || {}).single_account !== false;
    const canEdit = !single && S.user.role === "admin" && Cortex.mode === "live";
    view.innerHTML = `<div class="grid g-1-1">
      <section class="panel"><header class="ph"><h3>Accounts</h3><span class="sub">${users.length}</span></header>
        <table class="tbl compact"><thead><tr><th>Name</th><th>Login</th><th>Role</th></tr></thead><tbody>${users.map(u => `<tr><td>${esc(u.name)}</td><td class="mono">${esc(u.email)}</td><td>${esc(u.role)}</td></tr>`).join("")}</tbody></table></section>
      <section class="panel"><header class="ph"><h3>Access policy</h3></header>
        ${single ? `<p class="note">Single-account mode. The workspace has one administrator account, set on the server with CORTEX_ADMIN_LOGIN and CORTEX_ADMIN_PASSWORD. New accounts cannot be created. Roles: <b>admin</b> manages thresholds, team and audit; <b>clinician</b> reads charts and records reviews.</p>` : `
        ${!canEdit ? `<p class="note">${Cortex.mode !== "live" ? "Preview mode: accounts are managed on the deployed server." : "Only administrators can create accounts."}</p>` : ""}
        <form id="uf" class="rvf">
          <label for="u_name">Full name</label><input id="u_name" required ${canEdit ? "" : "disabled"}>
          <label for="u_email">Login or work email</label><input id="u_email" required ${canEdit ? "" : "disabled"}>
          <label for="u_pw">Temporary password (min. 10 characters)</label><input id="u_pw" type="password" minlength="10" autocomplete="new-password" required ${canEdit ? "" : "disabled"}>
          <label for="u_role">Role</label><select id="u_role" ${canEdit ? "" : "disabled"}><option value="clinician">Clinician</option><option value="admin">Administrator</option></select>
          <div class="rv-actions"><button class="btn btn-blue" type="submit" ${canEdit ? "" : "disabled"}>Create account</button><span id="umsg" class="sub" role="status"></span></div>
        </form>`}</section></div>`;
    const uf = $("#uf");
    if (uf) uf.onsubmit = async e => {
      e.preventDefault();
      try { await Cortex.createUser({ name: $("#u_name").value.trim(), email: $("#u_email").value.trim(), password: $("#u_pw").value, role: $("#u_role").value }); renderTeam(); }
      catch (x) { $("#umsg").textContent = x.message; }
    };
  }

  // ---------- audit ----------
  async function renderAudit() {
    navOn("audit"); setTitle("Audit log", "Sign-ins, record views, reviews and setting changes");
    const rows = await Cortex.audit();
    view.innerHTML = `<section class="panel"><div class="tbl-wrap"><table class="tbl compact"><thead><tr><th>When</th><th>User</th><th>Action</th><th>Target</th><th>Detail</th></tr></thead>
      <tbody>${rows.length ? rows.map(r => `<tr><td class="mono">${when(r.at)}</td><td>${esc(r.user)}</td><td>${esc(r.action.replace(/_/g, " "))}</td><td class="mono">${esc(r.target)}</td><td class="sub">${esc(r.detail || "")}</td></tr>`).join("") : '<tr><td colspan="5" class="empty">No events yet. Reviews you record appear here.</td></tr>'}</tbody></table></div></section>`;
  }

  // ---------- router ----------
  async function route() {
    const h = location.hash.replace(/^#/, "") || "worklist";
    try {
      if (h.startsWith("patient-")) await renderPatient(h.slice(8));
      else if (h === "model") await renderModel();
      else if (h === "thresholds") await renderThresholds();
      else if (h === "team") await renderTeam();
      else if (h === "audit") await renderAudit();
      else if (h === "review") return;
      else await renderWorklist();
      $("#main").scrollTo?.(0, 0); window.scrollTo(0, 0);
    } catch (e) { if (e.status === 401) location.href = "login.html"; else err(e); }
  }

  async function boot() {
    const mode = await Cortex.init();
    try { S.user = await Cortex.me(); }
    catch { location.href = "login.html"; return; }
    $("#uname").textContent = S.user.name; $("#urole").textContent = S.user.role === "admin" ? "Administrator" : "Clinician";
    $("#mode").textContent = mode === "live" ? "Live · synthetic cohort" : "Preview · synthetic data";
    $("#mode").classList.toggle("demo", mode !== "live");
    if (S.user.role !== "admin") document.querySelectorAll(".admin-only").forEach(x => x.hidden = true);
    $("#logout").onclick = async () => { await Cortex.logout(); location.href = "login.html"; };
    document.querySelectorAll(".unit button").forEach(b => {
      b.setAttribute("aria-pressed", b.dataset.u === S.unit);
      b.onclick = () => { S.unit = b.dataset.u; try { localStorage.setItem("cx_unit", S.unit); } catch {}
        document.querySelectorAll(".unit button").forEach(x => x.setAttribute("aria-pressed", x === b)); route(); };
    });
    $("#gsearch").addEventListener("keydown", e => {
      if (e.key !== "Enter") return;
      const q = e.target.value.trim().toUpperCase(); if (!q) return;
      S.q = q; S.filter = "all"; location.hash === "#worklist" ? renderWorklist() : (location.hash = "worklist");
    });
    window.addEventListener("hashchange", route);
    route();
  }
  boot();
})();
