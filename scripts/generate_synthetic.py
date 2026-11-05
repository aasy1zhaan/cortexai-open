"""Generate a fully synthetic kidney-transplant cohort.

No real patient data is used. Feature distributions and effect directions are
loosely inspired by published transplant literature (HLA mismatch, DSA, PRA,
cold ischemia, delayed graft function, tacrolimus variability raise risk), but
all numbers are simulated. The output is for software demonstration only and
must not be used for clinical decisions.
"""
import argparse
import numpy as np
import pandas as pd

FEATURES = [
    "recipient_age", "donor_age", "donor_type_deceased", "hla_mismatch",
    "pra_percent", "dsa_present", "cold_ischemia_hours", "delayed_graft_function",
    "prior_transplant", "creatinine_month1", "creatinine_month3", "egfr_month3",
    "proteinuria_g_day", "tacrolimus_trough", "tacrolimus_cv_percent", "bk_viremia",
    "cmv_mismatch", "diabetes", "adherence_score",
]


def simulate(n: int, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    d = pd.DataFrame()
    d["recipient_age"] = rng.normal(45, 13, n).clip(18, 80).round()
    d["donor_type_deceased"] = rng.binomial(1, 0.45, n)
    d["donor_age"] = np.where(d.donor_type_deceased == 1,
                              rng.normal(50, 14, n), rng.normal(40, 11, n)).clip(18, 80).round()
    d["hla_mismatch"] = rng.integers(0, 7, n)
    d["pra_percent"] = (rng.beta(0.6, 3.0, n) * 100).round()
    d["dsa_present"] = rng.binomial(1, 0.08 + 0.004 * d.pra_percent)
    d["cold_ischemia_hours"] = np.where(d.donor_type_deceased == 1,
                                        rng.gamma(4, 3.5, n), rng.gamma(2, 0.8, n)).round(1)
    d["prior_transplant"] = rng.binomial(1, 0.1, n)
    dgf_logit = -2.5 + 0.08 * d.cold_ischemia_hours + 0.02 * (d.donor_age - 45) + 0.6 * d.donor_type_deceased
    d["delayed_graft_function"] = rng.binomial(1, 1 / (1 + np.exp(-dgf_logit)))
    d["creatinine_month1"] = (rng.normal(1.4, 0.4, n) + 0.5 * d.delayed_graft_function).clip(0.6, 5).round(2)
    d["creatinine_month3"] = (d.creatinine_month1 + rng.normal(-0.1, 0.25, n)).clip(0.6, 5).round(2)
    d["egfr_month3"] = (100 * d.creatinine_month3 ** -1.1 * 0.993 ** d.recipient_age).clip(8, 120).round()
    d["proteinuria_g_day"] = rng.gamma(1.2, 0.25, n).round(2)
    d["tacrolimus_trough"] = rng.normal(7.5, 2.0, n).clip(2, 15).round(1)
    d["tacrolimus_cv_percent"] = rng.gamma(4, 7, n).clip(5, 80).round()
    d["bk_viremia"] = rng.binomial(1, 0.1, n)
    d["cmv_mismatch"] = rng.binomial(1, 0.2, n)
    d["diabetes"] = rng.binomial(1, 0.25, n)
    d["adherence_score"] = rng.beta(6, 1.5, n).round(2)

    logit = (-3.2
             + 0.22 * d.hla_mismatch
             + 0.012 * d.pra_percent
             + 1.3 * d.dsa_present
             + 0.6 * d.delayed_graft_function
             + 0.5 * d.prior_transplant
             + 0.7 * (d.creatinine_month3 - 1.3)
             + 0.6 * d.proteinuria_g_day
             - 0.12 * (d.tacrolimus_trough - 7.5)
             + 0.025 * (d.tacrolimus_cv_percent - 25)
             + 0.4 * d.bk_viremia
             - 2.0 * (d.adherence_score - 0.8)
             - 0.012 * (d.recipient_age - 45))
    p = 1 / (1 + np.exp(-logit))
    d["rejection_12m"] = rng.binomial(1, p)
    return d[FEATURES + ["rejection_12m"]]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=20000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default="data/synthetic_cohort.csv")
    a = ap.parse_args()
    df = simulate(a.n, a.seed)
    df.to_csv(a.out, index=False)
    print(f"wrote {len(df)} rows to {a.out}; rejection rate {df.rejection_12m.mean():.1%}")
