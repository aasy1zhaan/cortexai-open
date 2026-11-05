"""Clinical calculations shared by the simulator, the API and the tests."""
from __future__ import annotations

import math
from typing import Optional

MGDL_TO_UMOL = 88.42


def ckd_epi_2021(scr_mg_dl: float, age: float, sex: str) -> float:
    """eGFR (mL/min/1.73 m2), race-free CKD-EPI 2021 creatinine equation."""
    female = sex == "F"
    k, a = (0.7, -0.241) if female else (0.9, -0.302)
    r = scr_mg_dl / k
    egfr = 142 * min(r, 1) ** a * max(r, 1) ** -1.200 * 0.9938 ** age
    return egfr * (1.012 if female else 1.0)


def creatinine_for_egfr(egfr: float, age: float, sex: str) -> float:
    """Inverse of CKD-EPI 2021: serum creatinine (mg/dL) that yields the given eGFR."""
    female = sex == "F"
    k, a = (0.7, -0.241) if female else (0.9, -0.302)
    base = 142 * 0.9938 ** age * (1.012 if female else 1.0)
    r = (egfr / base) ** (1 / -1.200)          # branch Scr > k
    if r < 1:
        r = (egfr / base) ** (1 / a)          # branch Scr <= k
    return k * r


def tac_target(month: float) -> tuple[float, float]:
    """Demo tacrolimus trough corridor (ng/mL). Centres set their own."""
    return (8.0, 12.0) if month <= 3 else (5.0, 8.0)


def tac_metrics(history: list[dict], month: float) -> tuple[Optional[float], float]:
    """Intrapatient variability (CV %) and time in range (%) over the last 6 months.

    CV uses only the stable phase (month >= 3, same target corridor) and needs >= 3 troughs,
    because mixing the early and late corridors inflates variability. Returns (cv or None, ttr).
    """
    window = [h for h in history if month - 6 <= h["month"] <= month]
    stable = [h["tac_trough"] for h in window if h["month"] >= 3 and tac_target(h["month"]) == tac_target(month)]
    cv = None
    if len(stable) >= 3:
        mean = sum(stable) / len(stable)
        sd = math.sqrt(sum((x - mean) ** 2 for x in stable) / (len(stable) - 1))
        cv = sd / mean * 100 if mean > 0 else None
    ttr_src = window or history[-1:]
    lo_hi = [tac_target(h["month"]) for h in ttr_src]
    ttr = sum(lo <= h["tac_trough"] <= hi for h, (lo, hi) in zip(ttr_src, lo_hi)) / len(ttr_src) * 100
    return (round(cv, 1) if cv is not None else None), round(ttr)


def egfr_change_3m(history: list[dict], month: float, egfr: float) -> float:
    """Relative eGFR change vs the measurement closest to ~3 months earlier (clipped to +/-80%)."""
    prev = [h for h in history if month - 4.5 <= h["month"] <= month - 2]
    if not prev:
        return 0.0
    ref = min(prev, key=lambda h: abs(h["month"] - (month - 3)))["egfr"]
    return round(max(-80.0, min(80.0, (egfr - ref) / ref * 100)), 1)


# Approximate serological equivalents for the alleles used in the simulator
SEROLOGY = {
    "A": {"01:01": "A1", "02:01": "A2", "03:01": "A3", "11:01": "A11", "24:02": "A24", "26:01": "A26", "30:01": "A30", "68:01": "A68"},
    "B": {"07:02": "B7", "08:01": "B8", "13:02": "B13", "15:01": "B62", "18:01": "B18", "27:05": "B27", "35:01": "B35", "44:02": "B44", "51:01": "B51", "57:01": "B57"},
    "C": {"03:04": "Cw10", "04:01": "Cw4", "06:02": "Cw6", "07:01": "Cw7", "07:02": "Cw7", "12:03": "Cw12"},
    "DRB1": {"01:01": "DR1", "03:01": "DR17", "04:01": "DR4", "07:01": "DR7", "11:01": "DR11", "13:01": "DR13", "15:01": "DR15"},
    "DQB1": {"02:01": "DQ2", "03:01": "DQ7", "03:02": "DQ8", "05:01": "DQ5", "06:02": "DQ6", "06:03": "DQ6"},
}
HLA_CLASS = {"A": "I", "B": "I", "C": "I", "DRB1": "II", "DQB1": "II"}
