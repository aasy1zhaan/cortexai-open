"""Risk scoring, explanations and rule-based signals for CortexAI Open."""
from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from .sim import FEATURE_LABELS, FEATURES, snapshot

MODEL_DIR = Path(__file__).resolve().parent.parent / "model"
_BUNDLE = None
_CACHE: dict = {}

# Editable per centre. Defaults and their sources: ml/CLINICAL_BASIS.md
DEFAULT_THRESHOLDS = {
    "risk_high": 0.30, "risk_moderate": 0.12, "ddcfdna_pct": 1.0, "dsa_mfi": 1400, "dsa_rise_pct": 50,
    "tac_cv_pct": 30, "egfr_drop_pct": 20, "upcr_g_g": 0.5, "eplet_class2": 14,
}
THRESHOLD_INFO = {
    "risk_high": "Model risk at or above this value is shown as high.",
    "risk_moderate": "Model risk at or above this value is shown as moderate.",
    "ddcfdna_pct": "1% is the cut-off most often used to separate normal from abnormal dd-cfDNA (e.g. DART). Some centres use 0.5-0.75%. Not evaluated in the first month, when dd-cfDNA is physiologically raised.",
    "dsa_mfi": "MFI >= 1,400 is the binary DSA cut-off used by the iBox prognostication system. Laboratory cut-offs differ.",
    "dsa_rise_pct": "Relative rise in the immunodominant DSA MFI versus the previous measurement.",
    "tac_cv_pct": "Published cut-offs for high tacrolimus intrapatient variability span roughly 23-40%. Computed over the stable phase only (month 3 onward, >= 3 troughs).",
    "egfr_drop_pct": "Relative eGFR decline vs ~3 months earlier (CKD-EPI 2021). Not evaluated before month 3, while early graft function is still settling.",
    "upcr_g_g": "Urine protein-to-creatinine ratio in g/g.",
    "eplet_class2": "Class II (DR+DQ) eplet mismatch >= 14 was associated with more de novo class II DSA (Sakamoto 2020).",
}
# Features shown as context rather than explained (not modifiable, not a clinical finding)
_NOT_EXPLAINED = {"months_since_tx"}
_BINARY = {"donor_deceased", "retransplant", "induction_atg", "dgf", "bk_viremia", "prior_rejection", "dsa_class2"}


def bundle():
    global _BUNDLE
    if _BUNDLE is None:
        _BUNDLE = joblib.load(MODEL_DIR / "cortex_open.joblib")
    return _BUNDLE


def _predict(X: pd.DataFrame) -> np.ndarray:
    return bundle()["gbm"].predict_proba(X[FEATURES])[:, 1]


def trajectory(patient: dict) -> list[dict]:
    v = patient["visits"]
    key = (patient["id"], len(v), v[-1]["month"] if v else 0, v[-1].get("ddcfdna") if v else 0, v[-1].get("dsa_mfi_max") if v else 0)
    if key in _CACHE:
        return _CACHE[key]
    idxs = [i for i, x in enumerate(v) if x["month"] >= 1] or [len(v) - 1]
    probs = _predict(pd.DataFrame([snapshot(patient, i) for i in idxs]))
    out = [{"month": v[i]["month"], "risk": round(float(p), 3)} for i, p in zip(idxs, probs)]
    _CACHE[key] = out
    return out


def explain(patient: dict, idx: int, top: int = 6) -> list[dict]:
    """Model-agnostic explanation on the production model.

    For each factor, the factor is reset to a reference value (a typical stable recipient:
    cohort median, or 'absent' for yes/no findings) and the patient is re-scored. The
    difference is that factor's contribution in percentage points of 12-month risk.
    """
    ref = bundle()["reference"]
    x = pd.DataFrame([snapshot(patient, idx)])
    base = float(_predict(x)[0])
    feats = [f for f in FEATURES if f not in _NOT_EXPLAINED]
    rows = []
    for f in feats:
        xr = x.copy()
        xr[f] = ref[f]
        rows.append(xr)
    alt = _predict(pd.concat(rows, ignore_index=True))
    out = []
    for f, a in zip(feats, alt):
        val = x.iloc[0][f]
        out.append({"feature": f, "label": FEATURE_LABELS[f], "value": None if pd.isna(val) else float(val),
                    "reference": float(ref[f]), "contribution_pp": round((base - float(a)) * 100, 1)})
    out.sort(key=lambda d: -abs(d["contribution_pp"]))
    return [d for d in out if abs(d["contribution_pp"]) >= 0.3][:top]


def band(risk: float, th: dict) -> str:
    return "high" if risk >= th["risk_high"] else "moderate" if risk >= th["risk_moderate"] else "low"


def alerts(patient: dict, th: dict, risk: float) -> list[dict]:
    v = patient["visits"]
    if not v:
        return []
    cur, prev = v[-1], (v[-2] if len(v) > 1 else None)
    m = cur["month"]
    out = []

    def add(code, severity, title, detail):
        out.append({"code": code, "severity": severity, "title": title, "detail": detail})

    if risk >= th["risk_high"]:
        add("risk_high", "high", "High predicted rejection risk", f"12-month risk {risk:.0%}")
    if m >= 1 and cur["ddcfdna"] >= th["ddcfdna_pct"]:
        add("ddcfdna", "high", "dd-cfDNA above threshold", f"{cur['ddcfdna']:.2f}% (threshold {th['ddcfdna_pct']:g}%)")
    if cur["dsa_mfi_max"] >= th["dsa_mfi"]:
        top = (cur.get("dsa") or [{}])[0]
        spec = f"anti-{top['spec']} (class {top['class']}), " if top.get("spec") else ""
        denovo = not patient.get("preformed_dsa") or any(
            d.get("spec") not in {x.get("spec") for x in (v[0].get("dsa") or [])} for d in cur.get("dsa") or [])
        add("dsa", "high" if denovo else "medium", "De novo DSA" if denovo else "Persistent preformed DSA",
            f"{spec}MFI {cur['dsa_mfi_max']:,.0f}")
    if prev and prev["dsa_mfi_max"] >= 500 and cur["dsa_mfi_max"] >= prev["dsa_mfi_max"] * (1 + th["dsa_rise_pct"] / 100):
        add("dsa_rise", "medium", "DSA MFI rising", f"{prev['dsa_mfi_max']:,.0f} → {cur['dsa_mfi_max']:,.0f}")
    if cur["tac_trough"] < cur["tac_target_low"]:
        add("tac_low", "medium", "Tacrolimus below target",
            f"{cur['tac_trough']} ng/mL (target {cur['tac_target_low']:g}–{cur['tac_target_high']:g})")
    if cur.get("tac_cv") is not None and cur["tac_cv"] > th["tac_cv_pct"]:
        add("tac_cv", "medium", "High tacrolimus variability", f"CV {cur['tac_cv']:.0f}% (stable phase, last 6 months)")
    if m >= 3 and cur["egfr_change_3m"] <= -th["egfr_drop_pct"]:
        add("egfr_drop", "high", "eGFR decline", f"{cur['egfr_change_3m']:+.0f}% vs ~3 months ago")
    if cur["upcr"] >= th["upcr_g_g"]:
        add("upcr", "medium", "Proteinuria", f"UPCR {cur['upcr']:.2f} g/g")
    if cur["bk_viremia"]:
        add("bk", "medium", "BK viremia detected", "Possible over-immunosuppression")
    order = {"high": 0, "medium": 1}
    return sorted(out, key=lambda a: order[a["severity"]])


def considerations(patient: dict, al: list[dict]) -> list[str]:
    codes = {a["code"] for a in al}
    out = []
    if {"ddcfdna", "dsa"} <= codes or {"ddcfdna", "egfr_drop"} <= codes or {"dsa", "egfr_drop"} <= codes:
        out.append("Pattern compatible with active allograft injury: consider for-cause biopsy per centre protocol, after excluding obstruction and vascular causes on Doppler ultrasound.")
    elif "ddcfdna" in codes:
        out.append("Isolated dd-cfDNA elevation: consider repeat dd-cfDNA and DSA testing; exclude infection, including BK.")
    elif "egfr_drop" in codes:
        out.append("eGFR decline: check hydration, tacrolimus toxicity, obstruction and infection; Doppler ultrasound; consider biopsy if unexplained.")
    if "dsa" in codes or "dsa_rise" in codes:
        out.append("DSA positive: consider repeat single-antigen bead testing (with C1q if available) and review immunosuppression intensity and adherence.")
    if codes & {"tac_low", "tac_cv"}:
        out.append("Tacrolimus under-exposure or high variability: review adherence, sampling time, formulation and drug interactions.")
    if "bk" in codes:
        out.append("BK viremia: follow BK PCR; reduction of immunosuppression is usually considered, weighed against rejection risk (DSA, dd-cfDNA).")
    if "upcr" in codes and "dsa" not in codes:
        out.append("Proteinuria: repeat UPCR; consider recurrent disease or chronic injury in the differential.")
    if not out:
        out.append("No actionable signals at the latest visit. Continue the routine surveillance schedule.")
    return out


def summarize(patient: dict, th: dict) -> dict:
    traj = trajectory(patient)
    idx = len(patient["visits"]) - 1
    risk = traj[-1]["risk"]
    prev = traj[-2]["risk"] if len(traj) > 1 else risk
    al = alerts(patient, th, risk)
    return {"risk_12m": risk, "risk_delta": round(risk - prev, 3), "band": band(risk, th), "trajectory": traj,
            "drivers": explain(patient, idx), "alerts": al, "considerations": considerations(patient, al),
            "eplet_flag": patient["eplet_mm_class2"] >= th["eplet_class2"]}
