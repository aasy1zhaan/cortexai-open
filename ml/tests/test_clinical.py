import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cortex_ml.clinical import ckd_epi_2021, creatinine_for_egfr, egfr_change_3m, tac_metrics  # noqa: E402
from cortex_ml.engine import DEFAULT_THRESHOLDS, alerts  # noqa: E402


def test_ckd_epi_2021_reference_values():
    # Hand-checked against the published 2021 race-free equation
    assert round(ckd_epi_2021(2.3, 54, "M"), 1) == 32.9
    assert round(ckd_epi_2021(0.6, 30, "F"), 1) == 123.8
    assert round(ckd_epi_2021(1.0, 60, "M"), 0) == 86


def test_creatinine_inverse_roundtrip():
    for egfr in (15, 34, 60, 90, 115):
        for sex in "MF":
            assert math.isclose(ckd_epi_2021(creatinine_for_egfr(egfr, 45, sex), 45, sex), egfr, rel_tol=1e-6)


def test_tac_cv_ignores_early_phase_and_needs_three_values():
    early = [{"month": m, "tac_trough": t} for m, t in [(1, 12), (2, 9), (3, 6)]]
    cv, _ = tac_metrics(early, 3)
    assert cv is None  # only one stable-phase value
    # month 3 still belongs to the early 8-12 corridor; stable phase starts after it
    hist = early + [{"month": m, "tac_trough": 6.0} for m in (4, 5, 6)]
    cv, ttr = tac_metrics(hist, 6)
    assert cv == 0.0            # three identical stable-phase troughs
    assert ttr == round(100 * 5 / 6)  # month-3 trough of 6 was below its 8-12 target


def test_egfr_change_uses_value_about_three_months_earlier():
    hist = [{"month": 3, "egfr": 60}, {"month": 4, "egfr": 58}]
    assert egfr_change_3m(hist, 6, 45) == -25.0
    assert egfr_change_3m([], 6, 45) == 0.0


def _patient(month, **v):
    base = {"month": month, "ddcfdna": 0.3, "dsa_mfi_max": 0, "dsa": [], "tac_trough": 7, "tac_target_low": 5,
            "tac_target_high": 8, "tac_cv": 20, "egfr_change_3m": 0, "upcr": 0.1, "bk_viremia": 0}
    base.update(v)
    return {"preformed_dsa": 0, "visits": [base]}


def test_alert_rules_respect_timing():
    th = DEFAULT_THRESHOLDS
    assert not alerts(_patient(0.5, ddcfdna=2.0), th, 0.05)            # physiological early dd-cfDNA
    assert any(a["code"] == "ddcfdna" for a in alerts(_patient(4, ddcfdna=1.2), th, 0.05))
    assert not alerts(_patient(2, egfr_change_3m=-40), th, 0.05)       # early graft function settling
    assert any(a["code"] == "egfr_drop" for a in alerts(_patient(6, egfr_change_3m=-25), th, 0.05))
    dsa = [{"spec": "DQ7", "class": "II", "mfi": 3000}]
    a = alerts(_patient(6, dsa_mfi_max=3000, dsa=dsa), th, 0.05)
    assert a[0]["title"] == "De novo DSA" and "DQ7" in a[0]["detail"]
