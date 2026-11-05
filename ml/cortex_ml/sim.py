"""Synthetic kidney-transplant simulator.

Every patient, lab value, HLA typing and biopsy produced here is simulated. Effect directions
follow published transplant literature (class II eplet load and de novo DSA, tacrolimus
under-exposure and variability, dd-cfDNA elevation around rejection, eGFR decline and
proteinuria), but magnitudes are invented for software demonstration. Nothing here is
clinical evidence.
"""
from __future__ import annotations

import numpy as np

from .clinical import (HLA_CLASS, MGDL_TO_UMOL, SEROLOGY, ckd_epi_2021, creatinine_for_egfr,
                       egfr_change_3m, tac_metrics, tac_target)

HLA_POOLS = {loc: list(alleles) for loc, alleles in SEROLOGY.items()}
VISIT_MONTHS = [0.25, 0.5, 1, 1.5, 2, 3, 4, 5, 6, 8, 10, 12, 15, 18, 21, 24, 30, 36]

FEATURES = [
    "months_since_tx", "recipient_age", "donor_age", "donor_deceased", "retransplant",
    "cpra", "hla_mismatch", "eplet_mm_class2", "pirche_ii", "induction_atg", "dgf",
    "egfr", "egfr_change_3m", "upcr", "tac_trough", "tac_cv", "tac_ttr",
    "ddcfdna", "dsa_mfi_max", "dsa_class2", "bk_viremia", "prior_rejection",
]
FEATURE_LABELS = {
    "months_since_tx": "Time since transplant", "recipient_age": "Recipient age", "donor_age": "Donor age",
    "donor_deceased": "Deceased donor", "retransplant": "Re-transplant", "cpra": "cPRA",
    "hla_mismatch": "HLA A/B/DR mismatch", "eplet_mm_class2": "Class II eplet mismatch",
    "pirche_ii": "PIRCHE-II score", "induction_atg": "ATG induction", "dgf": "Delayed graft function",
    "egfr": "eGFR", "egfr_change_3m": "eGFR change (3 mo)", "upcr": "Proteinuria (UPCR)",
    "tac_trough": "Tacrolimus trough", "tac_cv": "Tacrolimus CV", "tac_ttr": "Tacrolimus time in range",
    "ddcfdna": "dd-cfDNA", "dsa_mfi_max": "DSA MFI (immunodominant)", "dsa_class2": "Class II DSA",
    "bk_viremia": "BK viremia", "prior_rejection": "Prior rejection",
}


def _sig(x):
    return 1 / (1 + np.exp(-x))


def _typing(rng):
    return {loc: sorted(rng.choice(pool, 2, replace=True).tolist()) for loc, pool in HLA_POOLS.items()}


def _mismatch(donor, recip):
    return {loc: [a for a in sorted(set(donor[loc])) if a not in recip[loc]] for loc in donor}


def _new_dsa(rng, mm, class2_bias=0.8):
    cls2 = [(l, a) for l in ("DQB1", "DRB1") for a in mm[l]]
    cls1 = [(l, a) for l in ("A", "B", "C") for a in mm[l]]
    pool = cls2 if (cls2 and (rng.random() < class2_bias or not cls1)) else cls1
    if not pool:
        return None
    w = np.array([0.65 if l == "DQB1" else 0.35 if l == "DRB1" else 1.0 for l, _ in pool])
    l, a = pool[rng.choice(len(pool), p=w / w.sum())]
    return {"spec": SEROLOGY[l][a], "locus": l, "class": HLA_CLASS[l], "allele": f"{l}*{a}"}


def simulate_patient(rng, pid: str, follow_up_months: float | None = None) -> dict:
    sex = str(rng.choice(["F", "M"], p=[0.4, 0.6]))
    age = int(np.clip(rng.normal(44, 13), 18, 76))
    deceased = int(rng.random() < 0.45)
    donor_age = int(np.clip(rng.normal(50 if deceased else 41, 12), 18, 78))
    retx = int(rng.random() < 0.09)
    cpra = int(np.clip(rng.beta(0.5, 3.2) * 100 + (25 if retx else 0), 0, 99))
    donor, recip = _typing(rng), _typing(rng)
    mm = _mismatch(donor, recip)
    hla_mm = sum(len(mm[l]) for l in ("A", "B", "DRB1"))
    eplet2 = int(sum(rng.integers(4, 13) for _ in mm["DRB1"] + mm["DQB1"]))
    pirche = int(eplet2 * rng.uniform(9, 15) + rng.integers(0, 40))
    induction_atg = int(cpra > 40 or retx or rng.random() < 0.2)
    cit = round(float(rng.gamma(4, 3.5) if deceased else rng.gamma(2, 0.8)), 1)
    dgf = int(rng.random() < _sig(-2.6 + 0.08 * cit + 0.025 * (donor_age - 45) + 0.5 * deceased))

    dsa = {}  # spec -> {"meta":..., "mfi":..., "onset":...}
    preformed = 0
    if rng.random() < 0.02 + cpra / 600:
        d = _new_dsa(rng, mm, class2_bias=0.45)
        if d:
            dsa[d["spec"]] = {"meta": d, "mfi": float(rng.uniform(2000, 6000)), "onset": 0.0}
            preformed = 1

    egfr_set = float(np.clip(rng.normal(62, 14) - 0.25 * (donor_age - 45) - 6 * dgf, 22, 100))
    adherence = float(rng.beta(6, 1.6))
    tac_noise = 0.12 + (1 - adherence) * 0.55
    base_logit = (-4.4 + 0.045 * (eplet2 - 12) + 0.012 * cpra + 0.5 * retx + 0.45 * dgf
                  - 0.35 * induction_atg + 0.0075 * (40 - age))

    fu = follow_up_months if follow_up_months is not None else float(rng.uniform(3, 36))
    visits = [m for m in VISIT_MONTHS if m <= fu]
    rejections, rows, biopsies, hist = [], [], [], []
    bk, smoldering = 0, 0.0
    for m in visits:
        lo, hi = tac_target(m)
        trough = float(np.clip((lo + hi) / 2 * rng.lognormal(-0.2 * (1 - adherence), tac_noise), 1.5, 20))
        under = max(0.0, (lo - trough) / lo)

        # donor-specific antibodies
        treated = any(0 < m - r["month"] <= 4 and r["type"] in ("Active ABMR", "Chronic active ABMR", "Mixed") for r in rejections)
        for s in dsa.values():
            s["mfi"] = float(np.clip(s["mfi"] * (rng.uniform(0.55, 0.85) if treated else rng.uniform(0.97, 1.18))
                                     + rng.normal(0, 250), 300, 16000))
        prior_cv = tac_metrics(hist, m)[0] if hist else None
        if m >= 2 and len(dsa) < 2:
            p_dsa = _sig(-6.2 + 0.09 * eplet2 + 3.0 * under + 0.03 * max((prior_cv or 20) - 25, 0))
            if rng.random() < p_dsa:
                d = _new_dsa(rng, mm)
                if d and d["spec"] not in dsa:
                    dsa[d["spec"]] = {"meta": d, "mfi": float(rng.uniform(1000, 3000)), "onset": m}
        dsa_max = max((s["mfi"] for s in dsa.values()), default=0.0)
        dsa_c2 = int(any(s["meta"]["class"] == "II" and s["mfi"] >= 1000 for s in dsa.values()))

        if bk and rng.random() < 0.35:
            bk = 0
        elif not bk and 1 <= m <= 12 and rng.random() < 0.012 + 0.02 * induction_atg:
            bk = 1

        hazard = _sig(base_logit + 2.2 * under + 0.035 * max((prior_cv or 20) - 25, 0) + 0.9 * (dsa_max > 1400)
                      + 0.00005 * dsa_max + 0.3 * dsa_c2 - 0.06 * min(m, 12) + 1.2 * smoldering)
        if any(0 < m - r["month"] <= 6 for r in rejections):
            hazard *= 0.12
        smoldering = 0.6 * smoldering + (rng.random() < hazard * 2.2) * rng.uniform(0.4, 1.0)
        rej_type = None
        if rng.random() < hazard and len(rejections) < 3 and m >= 0.5:
            if dsa_max > 1400 and rng.random() < 0.75:
                rej_type = "Chronic active ABMR" if m >= 12 and any(m - s["onset"] >= 6 for s in dsa.values()) else (
                    "Mixed" if rng.random() < 0.15 else "Active ABMR")
            else:
                rej_type = "TCMR" if rng.random() < 0.8 else "Borderline"
            rejections.append({"month": m, "type": rej_type})

        active = any(0 <= m - r["month"] < 1.5 for r in rejections)
        injury = (0.35 if active else 0) + 0.25 * smoldering
        dd = float(np.clip(rng.lognormal(np.log(0.28), 0.35) * (1 + 6 * injury + 0.6 * bk)
                           * (2.5 if m < 0.6 else 1), 0.05, 9))
        drift = -1.05 * len(rejections) - 0.05 * (dsa_max > 3000) * m
        dgf_drag = 0.55 if (dgf and m < 0.6) else 0.0
        egfr_true = float(np.clip(egfr_set * (1 - dgf_drag) * (1 - 0.32 * active - 0.08 * smoldering)
                                  + drift + rng.normal(0, 3.0), 6, 120))
        scr = round(creatinine_for_egfr(egfr_true, age, sex) * rng.lognormal(0, 0.03), 2)  # lab noise on creatinine
        egfr = round(ckd_epi_2021(scr, age, sex), 1)
        upcr = float(np.clip(rng.lognormal(np.log(0.15), 0.5) * (1 + 3 * active + 1.5 * (dsa_max > 3000) + 2 * injury), 0.03, 6))

        hist.append({"month": m, "tac_trough": trough, "egfr": egfr})
        cv, ttr = tac_metrics(hist, m)
        rows.append({
            "month": m, "creatinine": scr, "creatinine_umol": round(scr * MGDL_TO_UMOL), "egfr": egfr,
            "egfr_change_3m": egfr_change_3m(hist[:-1], m, egfr), "upcr": round(upcr, 2),
            "tac_trough": round(trough, 1), "tac_target_low": lo, "tac_target_high": hi,
            "tac_cv": cv, "tac_ttr": ttr, "ddcfdna": round(dd, 2),
            "dsa": sorted([{**s["meta"], "mfi": round(s["mfi"])} for s in dsa.values()], key=lambda x: -x["mfi"]),
            "dsa_mfi_max": round(dsa_max), "dsa_class2": dsa_c2, "bk_viremia": bk,
        })
        if m in (3, 12) or rej_type:
            banff = {"Active ABMR": "Active ABMR (g2, ptc2, C4d+)",
                     "Chronic active ABMR": "Chronic active ABMR (cg1, ptc2, C4d-)",
                     "Mixed": "Mixed: active ABMR + TCMR IA",
                     "TCMR": str(rng.choice(["Acute TCMR grade IA (i2, t2)", "Acute TCMR grade IB (i2, t3)", "Acute TCMR grade IIA (v1)"], p=[0.6, 0.3, 0.1])),
                     "Borderline": "Borderline changes (i1, t1)"}.get(rej_type, "No rejection; IFTA grade I (ci1, ct1)" if m >= 12 else "No rejection")
            biopsies.append({"month": m, "indication": "for-cause" if rej_type else "protocol", "result": banff,
                             "rejection": bool(rej_type and rej_type != "Borderline")})

    return {
        "id": pid, "sex": sex, "age": age, "donor_type": "deceased" if deceased else "living",
        "donor_age": donor_age, "retransplant": retx, "cpra": cpra, "cold_ischemia_h": cit,
        "dgf": dgf, "induction": "ATG" if induction_atg else "Basiliximab",
        "maintenance": "Tacrolimus + MMF + prednisolone",
        "hla": {"donor": donor, "recipient": recip, "mismatched": mm},
        "hla_mismatch": hla_mm, "eplet_mm_class2": eplet2, "pirche_ii": pirche,
        "preformed_dsa": preformed, "follow_up_months": visits[-1] if visits else 0,
        "visits": rows, "biopsies": biopsies, "rejections": rejections,
    }


def snapshot(patient: dict, idx: int) -> dict:
    v = patient["visits"][idx]
    prior = any(r["month"] < v["month"] and r["type"] != "Borderline" for r in patient["rejections"])
    return {
        "months_since_tx": v["month"], "recipient_age": patient["age"], "donor_age": patient["donor_age"],
        "donor_deceased": int(patient["donor_type"] == "deceased"), "retransplant": patient["retransplant"],
        "cpra": patient["cpra"], "hla_mismatch": patient["hla_mismatch"],
        "eplet_mm_class2": patient["eplet_mm_class2"], "pirche_ii": patient["pirche_ii"],
        "induction_atg": int(patient["induction"] == "ATG"), "dgf": patient["dgf"],
        "egfr": v["egfr"], "egfr_change_3m": v["egfr_change_3m"], "upcr": v["upcr"],
        "tac_trough": v["tac_trough"], "tac_cv": np.nan if v["tac_cv"] is None else v["tac_cv"],
        "tac_ttr": v["tac_ttr"], "ddcfdna": v["ddcfdna"], "dsa_mfi_max": v["dsa_mfi_max"],
        "dsa_class2": v.get("dsa_class2", 0), "bk_viremia": v["bk_viremia"], "prior_rejection": int(prior),
    }


def label_next_12m(patient: dict, idx: int) -> int:
    m = patient["visits"][idx]["month"]
    return int(any(m < r["month"] <= m + 12 and r["type"] != "Borderline" for r in patient["rejections"]))


def training_table(n_patients: int, seed: int = 7):
    import pandas as pd
    rng = np.random.default_rng(seed)
    recs = []
    for i in range(n_patients):
        p = simulate_patient(rng, f"T{i}", follow_up_months=36)
        for j, v in enumerate(p["visits"]):
            if v["month"] < 1 or v["month"] > 24:
                continue
            if any(abs(v["month"] - r["month"]) < 1e-9 for r in p["rejections"]):
                continue  # predict *future* rejection: skip visits that are themselves a rejection episode
            s = snapshot(p, j)
            s["label"] = label_next_12m(p, j)
            s["patient"] = i
            recs.append(s)
    return pd.DataFrame(recs)
