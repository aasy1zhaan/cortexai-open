"""Risk scoring, explanations and rule-based alerts for CortexAI Open."""
from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from .sim import FEATURE_LABELS, FEATURES, snapshot

ROOT = Path(__file__).resolve().parent.parent
_BUNDLE = None


def bundle():
    global _BUNDLE
    if _BUNDLE is None:
        _BUNDLE = joblib.load(ROOT / "model" / "cortex_open.joblib")
    return _BUNDLE


# Thresholds are editable by an administrator. Defaults come from the literature cited in
# docs/clinical-basis.md and are meant to be tuned to each centre's protocol.
DEFAULT_THRESHOLDS = {
    "risk_high": 0.30,            # model 12-month risk, high band
    "risk_moderate": 0.12,        # model 12-month risk, moderate band
    "ddcfdna_pct": 1.0,           # dd-cfDNA fraction, commonly used 1% cut-off
    "dsa_mfi": 1400,              # DSA MFI cut-off used in iBox
    "dsa_rise_pct": 50,           # relative MFI increase vs previous visit
    "tac_cv_pct": 30,             # tacrolimus intrapatient variability
    "egfr_drop_pct": 20,          # eGFR decline over ~3 months
    "upcr_g_g": 0.5,              # proteinuria
    "eplet_class2": 14,           # class II eplet mismatch load (baseline risk flag)
}

THRESHOLD_INFO = {
    "risk_high": "Model risk at or above this value is shown as high.",
    "risk_moderate": "Model risk at or above this value is shown as moderate.",
    "ddcfdna_pct": "1% is the cut-off most often used to separate normal from abnormal dd-cfDNA (e.g. DART). Some centres use 0.5-0.75%.",
    "dsa_mfi": "MFI >= 1,400 is the binary DSA cut-off used by the iBox prognostication system. Labs differ.",
    "dsa_rise_pct": "Relative rise in the immunodominant DSA MFI versus the previous measurement.",
    "tac_cv_pct": "Published cut-offs for high tacrolimus intrapatient variability range roughly 23-40%.",
    "egfr_drop_pct": "Relative eGFR decline compared with the value ~3 months earlier.",
    "upcr_g_g": "Urine protein-to-creatinine ratio in g/g.",
    "eplet_class2": "Class II (DR+DQ) eplet mismatch >= 14 was associated with more de novo class II DSA (Sakamoto 2020).",
}


def features_for(patient: dict, idx: int) -> pd.DataFrame:
    return pd.DataFrame([snapshot(patient, idx)])[FEATURES]


def risk_at(patient: dict, idx: int) -> float:
    return float(bundle()["gbm"].predict_proba(features_for(patient, idx))[0, 1])


def drivers(patient: dict, idx: int, top: int = 6) -> list[dict]:
    scaler, lr = bundle()["lr"].named_steps.values()
    x = features_for(patient, idx)
    contrib = scaler.transform(x)[0] * lr.coef_[0]
    order = np.argsort(-np.abs(contrib))[:top]
    return [{"feature": FEATURES[i], "label": FEATURE_LABELS[FEATURES[i]], "value": float(x.iloc[0, i]),
             "contribution": round(float(contrib[i]), 3)} for i in order]


def band(risk: float, th: dict) -> str:
    return "high" if risk >= th["risk_high"] else "moderate" if risk >= th["risk_moderate"] else "low"


def alerts(patient: dict, th: dict, risk: float) -> list[dict]:
    v = patient["visits"]
    if not v:
        return []
    cur = v[-1]
    prev = v[-2] if len(v) > 1 else None
    out = []

    def add(code, severity, title, detail):
        out.append({"code": code, "severity": severity, "title": title, "detail": detail})

    if risk >= th["risk_high"]:
        add("risk_high", "high", "High predicted rejection risk", f"12-month risk {risk:.0%}")
    if cur["ddcfdna"] >= th["ddcfdna_pct"]:
        add("ddcfdna", "high", "dd-cfDNA above threshold", f"{cur['ddcfdna']:.2f}% (threshold {th['ddcfdna_pct']}%)")
    if cur["dsa_mfi_max"] >= th["dsa_mfi"]:
        denovo = not patient.get("preformed_dsa")
        add("dsa", "high" if denovo else "medium", ("De novo DSA" if denovo else "Persistent DSA"),
            f"Immunodominant MFI {cur['dsa_mfi_max']:,.0f}")
    if prev and prev["dsa_mfi_max"] >= 500 and cur["dsa_mfi_max"] >= prev["dsa_mfi_max"] * (1 + th["dsa_rise_pct"] / 100):
        add("dsa_rise", "medium", "DSA MFI rising", f"{prev['dsa_mfi_max']:,.0f} -> {cur['dsa_mfi_max']:,.0f}")
    if cur["tac_trough"] < cur["tac_target_low"]:
        add("tac_low", "medium", "Tacrolimus below target",
            f"{cur['tac_trough']} ng/mL (target {cur['tac_target_low']:g}-{cur['tac_target_high']:g})")
    if cur["tac_cv"] > th["tac_cv_pct"]:
        add("tac_cv", "medium", "High tacrolimus variability", f"CV {cur['tac_cv']:.0f}% over last 6 months")
    if cur["egfr_change_3m"] <= -th["egfr_drop_pct"]:
        add("egfr_drop", "high", "eGFR decline", f"{cur['egfr_change_3m']:+.0f}% vs ~3 months ago")
    if cur["upcr"] >= th["upcr_g_g"]:
        add("upcr", "medium", "Proteinuria", f"UPCR {cur['upcr']:.2f} g/g")
    if cur["bk_viremia"]:
        add("bk", "medium", "BK viremia detected", "Consider over-immunosuppression")
    order = {"high": 0, "medium": 1}
    return sorted(out, key=lambda a: order[a["severity"]])


def considerations(patient: dict, al: list[dict]) -> list[str]:
    codes = {a["code"] for a in al}
    out = []
    if {"ddcfdna", "dsa"} <= codes or ({"ddcfdna", "egfr_drop"} <= codes):
        out.append("Pattern compatible with active allograft injury: consider for-cause biopsy per centre protocol.")
    elif "ddcfdna" in codes:
        out.append("Isolated dd-cfDNA elevation: consider repeat dd-cfDNA and DSA testing; rule out infection.")
    if "dsa" in codes or "dsa_rise" in codes:
        out.append("DSA positive: consider repeat single-antigen bead testing and review immunosuppression intensity.")
    if codes & {"tac_low", "tac_cv"}:
        out.append("Tacrolimus under-exposure or high variability: review adherence, timing of sampling and drug interactions.")
    if "bk" in codes:
        out.append("BK viremia: follow BK PCR trend; balance against rejection risk before reducing immunosuppression.")
    if "upcr" in codes and "dsa" not in codes:
        out.append("Proteinuria: repeat UPCR; consider recurrent disease or chronic injury in the differential.")
    if not out:
        out.append("No actionable signals at the latest visit. Continue routine surveillance schedule.")
    return out


_CACHE: dict = {}


def _trajectory(patient: dict) -> list[dict]:
    key = (patient["id"], len(patient["visits"]), patient["visits"][-1]["month"] if patient["visits"] else 0,
           patient["visits"][-1].get("ddcfdna") if patient["visits"] else 0)
    if key in _CACHE:
        return _CACHE[key]
    idxs = [i for i, v in enumerate(patient["visits"]) if v["month"] >= 1] or [len(patient["visits"]) - 1]
    X = pd.DataFrame([snapshot(patient, i) for i in idxs])[FEATURES]
    probs = bundle()["gbm"].predict_proba(X)[:, 1]
    traj = [{"month": patient["visits"][i]["month"], "risk": round(float(p), 3)} for i, p in zip(idxs, probs)]
    _CACHE[key] = traj
    return traj


def summarize(patient: dict, th: dict) -> dict:
    """Latest risk, trajectory, drivers, alerts for a patient."""
    traj = _trajectory(patient)
    idx = len(patient["visits"]) - 1
    risk = traj[-1]["risk"]
    prev_risk = traj[-2]["risk"] if len(traj) > 1 else risk
    al = alerts(patient, th, risk)
    return {
        "risk_12m": round(risk, 3), "risk_delta": round(risk - prev_risk, 3), "band": band(risk, th),
        "trajectory": traj, "drivers": drivers(patient, idx), "alerts": al,
        "considerations": considerations(patient, al),
        "eplet_flag": patient["eplet_mm_class2"] >= th["eplet_class2"],
    }
