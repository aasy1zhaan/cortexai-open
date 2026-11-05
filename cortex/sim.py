"""Synthetic kidney-transplant simulator.

Every patient, lab value and biopsy produced here is simulated. Effect directions follow
published transplant literature (HLA class II eplet load and de novo DSA, tacrolimus
under-exposure and intrapatient variability, dd-cfDNA elevation around rejection,
eGFR decline and proteinuria), but magnitudes are invented for software demonstration.
Nothing here is clinical evidence.
"""
from __future__ import annotations

import numpy as np

HLA_POOLS = {
    "A": ["01:01", "02:01", "03:01", "11:01", "24:02", "26:01", "30:01", "68:01"],
    "B": ["07:02", "08:01", "13:02", "15:01", "18:01", "27:05", "35:01", "44:02", "51:01", "57:01"],
    "C": ["03:04", "04:01", "06:02", "07:01", "07:02", "12:03"],
    "DRB1": ["01:01", "03:01", "04:01", "07:01", "11:01", "13:01", "15:01"],
    "DQB1": ["02:01", "03:01", "03:02", "05:01", "06:02", "06:03"],
}
VISIT_MONTHS = [0.25, 0.5, 1, 1.5, 2, 3, 4, 5, 6, 8, 10, 12, 15, 18, 21, 24, 30, 36]

FEATURES = [
    "months_since_tx", "recipient_age", "donor_age", "donor_deceased", "retransplant",
    "cpra", "hla_mismatch", "eplet_mm_class2", "pirche_ii", "induction_atg", "dgf",
    "egfr", "egfr_change_3m", "upcr", "tac_trough", "tac_cv", "tac_ttr",
    "ddcfdna", "dsa_mfi_max", "bk_viremia", "prior_rejection",
]

FEATURE_LABELS = {
    "months_since_tx": "Time since transplant", "recipient_age": "Recipient age",
    "donor_age": "Donor age", "donor_deceased": "Deceased donor", "retransplant": "Re-transplant",
    "cpra": "cPRA", "hla_mismatch": "HLA A/B/DR mismatch", "eplet_mm_class2": "Class II eplet mismatch",
    "pirche_ii": "PIRCHE-II score", "induction_atg": "ATG induction", "dgf": "Delayed graft function",
    "egfr": "eGFR", "egfr_change_3m": "eGFR change (3 mo)", "upcr": "Proteinuria (UPCR)",
    "tac_trough": "Tacrolimus trough", "tac_cv": "Tacrolimus CV", "tac_ttr": "Tacrolimus time in range",
    "ddcfdna": "dd-cfDNA", "dsa_mfi_max": "DSA MFI (max)", "bk_viremia": "BK viremia",
    "prior_rejection": "Prior rejection",
}


def _sig(x):
    return 1 / (1 + np.exp(-x))


def _typing(rng):
    return {loc: sorted(rng.choice(pool, 2, replace=True).tolist()) for loc, pool in HLA_POOLS.items()}


def _mismatch(donor, recip):
    out = {}
    for loc in donor:
        out[loc] = [a for a in sorted(set(donor[loc])) if a not in recip[loc]]
    return out


def simulate_patient(rng, pid: str, follow_up_months: float | None = None) -> dict:
    sex = rng.choice(["F", "M"], p=[0.4, 0.6])
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
    preformed_dsa = int(rng.random() < 0.02 + cpra / 600)

    # latent patient traits
    egfr_set = float(np.clip(rng.normal(62, 14) - 0.25 * (donor_age - 45) - 6 * dgf, 22, 100))
    tac_target = (8.0, 12.0)  # months 0-3, then 5-8 handled below
    adherence = float(rng.beta(6, 1.6))
    tac_noise = 0.12 + (1 - adherence) * 0.55
    base_logit = (-4.4 + 0.045 * (eplet2 - 12) + 0.012 * cpra + 0.5 * retx + 0.45 * dgf
                  - 0.35 * induction_atg + 0.015 * (40 - age) * 0.5)

    fu = follow_up_months if follow_up_months is not None else float(rng.uniform(3, 36))
    visits = [m for m in VISIT_MONTHS if m <= fu]
    dsa_mfi = float(rng.uniform(2000, 6000)) if preformed_dsa else 0.0
    dsa_onset = 0.0 if preformed_dsa else None
    troughs, rejections, rows, biopsies = [], [], [], []
    bk = 0
    egfr_hist = []
    smoldering = 0.0  # subclinical injury that precedes clinical rejection
    for m in visits:
        lo, hi = (8.0, 12.0) if m <= 3 else (5.0, 8.0)
        target_mid = (lo + hi) / 2
        trough = float(np.clip(target_mid * rng.lognormal(-0.05 * (1 - adherence) * 4, tac_noise), 1.5, 20))
        troughs.append((m, trough, lo, hi))
        recent = [t for (mm_, t, _, _) in troughs if m - 6 <= mm_ <= m and mm_ >= 1] or [trough]
        tac_cv = float(np.std(recent) / np.mean(recent) * 100) if len(recent) > 1 else 15.0
        in_range = [lo_ <= t <= hi_ for (mm_, t, lo_, hi_) in troughs if m - 6 <= mm_ <= m]
        tac_ttr = float(np.mean(in_range) * 100)
        under = max(0.0, (lo - trough) / lo)

        # de novo DSA
        if dsa_onset is None and m >= 2:
            p_dsa = _sig(-6.0 + 0.09 * eplet2 + 3.0 * under + 0.03 * max(tac_cv - 25, 0))
            if rng.random() < p_dsa:
                dsa_onset, dsa_mfi = m, float(rng.uniform(1000, 3000))
        elif dsa_onset is not None:
            treated = any(0 < m - r["month"] <= 4 and r["type"] == "ABMR" for r in rejections)
            dsa_mfi = float(np.clip(dsa_mfi * (rng.uniform(0.55, 0.85) if treated else rng.uniform(0.97, 1.18))
                                    + rng.normal(0, 250), 300, 16000))

        # BK viremia (over-immunosuppression)
        if bk and rng.random() < 0.35:
            bk = 0
        elif not bk and 1 <= m <= 12 and rng.random() < 0.012 + 0.02 * induction_atg:
            bk = 1

        hazard = _sig(base_logit + 2.2 * under + 0.035 * max(tac_cv - 25, 0) + 0.9 * (dsa_mfi > 1400)
                      + 0.00005 * dsa_mfi - 0.06 * min(m, 12) + 1.2 * smoldering)
        # after a treated rejection episode, intensified immunosuppression suppresses new episodes for months
        if any(0 < m - r["month"] <= 6 for r in rejections):
            hazard *= 0.12
        smoldering = 0.6 * smoldering + (rng.random() < hazard * 2.2) * rng.uniform(0.4, 1.0)
        event = rng.random() < hazard and len(rejections) < 3
        rej_type = None
        if event:
            rej_type = "ABMR" if (dsa_mfi > 1400 and rng.random() < 0.75) else (
                "TCMR" if rng.random() < 0.8 else "Borderline")
            rejections.append({"month": m, "type": rej_type})

        active = any(m - r["month"] < 1.5 and m >= r["month"] for r in rejections)
        injury = (0.35 if active else 0) + 0.25 * smoldering
        dd = float(np.clip(rng.lognormal(np.log(0.28), 0.35) * (1 + 6 * injury + 0.6 * bk)
                           * (1.8 if m < 0.6 else 1), 0.05, 9))
        dgf_drag = 0.55 if (dgf and m < 0.6) else 0.0
        drift = -0.35 * len(rejections) * 3 - 0.05 * (dsa_mfi > 3000) * m
        egfr = float(np.clip(egfr_set * (1 - dgf_drag) * (1 - 0.32 * active - 0.08 * smoldering)
                             + drift + rng.normal(0, 3.5), 6, 120))
        egfr_hist.append((m, egfr))
        prev = [e for (mm_, e) in egfr_hist if m - 3.5 <= mm_ <= m - 2.5] or [egfr_hist[0][1]]
        egfr_change = float(np.clip((egfr - prev[0]) / prev[0] * 100, -80, 80)) if len(egfr_hist) > 1 else 0.0
        upcr = float(np.clip(rng.lognormal(np.log(0.15), 0.5) * (1 + 3 * active + 1.5 * (dsa_mfi > 3000)
                                                                   + 2 * injury), 0.03, 6))
        creat = float(np.clip(100 * (egfr / 140) ** (-1 / 1.1) / 88.4, 0.5, 9))  # mg/dL, rough inverse

        rows.append({
            "month": m, "creatinine": round(creat, 2), "egfr": round(egfr, 1),
            "egfr_change_3m": round(egfr_change, 1), "upcr": round(upcr, 2),
            "tac_trough": round(trough, 1), "tac_target_low": lo, "tac_target_high": hi,
            "tac_cv": round(tac_cv, 1), "tac_ttr": round(tac_ttr, 0),
            "ddcfdna": round(dd, 2), "dsa_mfi_max": round(dsa_mfi), "bk_viremia": bk,
            "_event": int(event), "_rej_type": rej_type,
        })
        if m in (3, 12) or event:
            banff = {"ABMR": "Active ABMR (g2, ptc2, C4d+)", "TCMR": "Acute TCMR grade IA (i2, t2)",
                     "Borderline": "Borderline (i1, t1)"}.get(rej_type, "No rejection; IFTA grade I" if m >= 12 else "No rejection")
            biopsies.append({"month": m, "indication": "for-cause" if event else "protocol", "result": banff})

    patient = {
        "id": pid, "sex": sex, "age": age, "donor_type": "deceased" if deceased else "living",
        "donor_age": donor_age, "retransplant": retx, "cpra": cpra, "cold_ischemia_h": cit,
        "dgf": dgf, "induction": "ATG" if induction_atg else "Basiliximab",
        "maintenance": "Tacrolimus + MMF + prednisolone",
        "hla": {"donor": donor, "recipient": recip, "mismatched": mm},
        "hla_mismatch": hla_mm, "eplet_mm_class2": eplet2, "pirche_ii": pirche,
        "preformed_dsa": preformed_dsa, "follow_up_months": visits[-1] if visits else 0,
        "visits": rows, "biopsies": biopsies, "rejections": rejections,
    }
    return patient


def snapshot(patient: dict, idx: int) -> dict:
    v = patient["visits"][idx]
    prior = any(r["month"] < v["month"] for r in patient["rejections"])
    return {
        "months_since_tx": v["month"], "recipient_age": patient["age"], "donor_age": patient["donor_age"],
        "donor_deceased": int(patient["donor_type"] == "deceased"), "retransplant": patient["retransplant"],
        "cpra": patient["cpra"], "hla_mismatch": patient["hla_mismatch"],
        "eplet_mm_class2": patient["eplet_mm_class2"], "pirche_ii": patient["pirche_ii"],
        "induction_atg": int(patient["induction"] == "ATG"), "dgf": patient["dgf"],
        "egfr": v["egfr"], "egfr_change_3m": v["egfr_change_3m"], "upcr": v["upcr"],
        "tac_trough": v["tac_trough"], "tac_cv": v["tac_cv"], "tac_ttr": v["tac_ttr"],
        "ddcfdna": v["ddcfdna"], "dsa_mfi_max": v["dsa_mfi_max"], "bk_viremia": v["bk_viremia"],
        "prior_rejection": int(prior),
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
            # rows already inside an active rejection are excluded (we predict *future* rejection)
            if any(abs(v["month"] - r["month"]) < 1e-9 for r in p["rejections"]):
                continue
            s = snapshot(p, j)
            s["label"] = label_next_12m(p, j)
            s["patient"] = i
            recs.append(s)
    return pd.DataFrame(recs)
