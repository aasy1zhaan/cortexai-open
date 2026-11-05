"""Deterministic synthetic demo cohort shown in the clinician app.

The demo cohort is deliberately enriched with higher-risk recipients so every screen has
something to show. Its risk mix is therefore NOT representative of a real clinic.
"""
import numpy as np

from .sim import simulate_patient

FEMALE = ["Aigerim", "Dana", "Madina", "Zhanar", "Aliya", "Saule", "Kamila", "Asel", "Ainur", "Gulnara"]
MALE = ["Nursultan", "Yerlan", "Arman", "Timur", "Daulet", "Ruslan", "Bekzat", "Marat", "Olzhas", "Sanzhar"]
LAST = ["S.", "K.", "B.", "T.", "M.", "A.", "Zh.", "N.", "O.", "R."]
FU = [1.5, 2, 3, 4, 6, 8, 10, 12, 15, 18, 24, 30, 36]


def demo_cohort(n: int = 40, seed: int = 2026) -> list[dict]:
    from .engine import DEFAULT_THRESHOLDS, summarize  # local import: engine loads the trained model

    rng = np.random.default_rng(seed)
    pool = []
    for i in range(360):
        p = simulate_patient(rng, "", follow_up_months=float(rng.choice(FU)))
        for v in p["visits"]:
            v.pop("_event", None)
            v.pop("_rej_type", None)
        s = summarize(p, DEFAULT_THRESHOLDS)
        pool.append((p, s))
    high = [x for x in pool if x[1]["band"] == "high"]
    signal = [x for x in pool if x[1]["band"] != "high" and any(a["severity"] == "high" for a in x[1]["alerts"])]
    moderate = [x for x in pool if x[1]["band"] == "moderate" and x not in signal]
    low = [x for x in pool if x[1]["band"] == "low" and not x[1]["alerts"]]
    rest = [x for x in pool if x not in high + signal + moderate + low]
    # one example of each signal type so every screen state is visible
    showcase = []
    for code in ("ddcfdna", "egfr_drop", "bk", "tac_cv", "tac_low", "upcr"):
        for x in pool:
            if x not in showcase and any(a["code"] == code for a in x[1]["alerts"]):
                showcase.append(x)
                break
    taken = lambda lst, k: [x for x in lst if x not in showcase][:k]  # noqa: E731
    pick = showcase + taken(high, 4) + taken(signal, 4) + taken(moderate, 8)
    pick += [x for x in rest if x not in pick][:4]
    pick += [x for x in low if x not in pick][: n - len(pick)]
    out = []
    for i, (p, _) in enumerate(pick[:n]):
        p["id"] = f"CX-{1040 + i * 7:04d}"
        p["display_name"] = f"{rng.choice(FEMALE if p['sex'] == 'F' else MALE)} {rng.choice(LAST)}"
        p["centre"] = str(rng.choice(["Astana, National Scientific Medical Center", "Almaty, City Clinical Hospital No. 7"]))
        out.append(p)
    return out
