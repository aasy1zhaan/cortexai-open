# Clinical basis for CortexAI Open

This document explains where each signal and default threshold comes from. All thresholds are
editable per centre (Alert thresholds screen) and should follow local protocol and laboratory
practice.

## Prediction target
Biopsy-proven T-cell-mediated (TCMR) or antibody-mediated (ABMR) rejection within 12 months of a
clinic visit, months 1–24 after transplantation. Borderline changes are not counted as events.

## Signals and defaults

| Signal | Default | Basis |
|---|---|---|
| dd-cfDNA fraction | ≥ 1.0%, from month 1 | Most commonly used cut-off separating normal from abnormal; high negative predictive value (DART; Kant & Brennan, *Transplant International* 2022). Some centres use 0.5–0.75%. |
| DSA, immunodominant MFI | ≥ 1,400 | Binary DSA cut-off used in the iBox prognostication system (Loupy et al., *BMJ* 2019;366:l4923). Laboratory cut-offs vary. |
| DSA rising | +50% vs previous | Trend signal for de novo or rebounding DSA. |
| Tacrolimus below target | per phase | Target corridor 8–12 ng/mL in months 0–3 and 5–8 ng/mL afterwards (demo default; set per centre). |
| Tacrolimus intrapatient variability | CV > 30%, stable phase (month ≥ 3, ≥ 3 troughs, last 6 months) | Published cut-offs range roughly 23–40%; under-exposure and variability are associated with rejection and graft loss (e.g. Benning et al., *Front Immunol* 2026; doi 10.3389/fimmu.2026.1739104). |
| eGFR decline | ≤ −20% over ~3 months, from month 3 | eGFR by CKD-EPI 2021 (race-free) from serum creatinine. Not evaluated earlier, while graft function settles after transplant/DGF. eGFR and proteinuria are core iBox inputs. |
| Proteinuria | UPCR ≥ 0.5 g/g | Functional/injury marker; iBox input. |
| Class II eplet mismatch | ≥ 14 | Living-donor recipients with DRB+DQB eplet mismatch ≥ 14 developed de novo class II DSA in 20.2% vs 3.4% (Sakamoto et al., *Front Immunol* 2020; doi 10.3389/fimmu.2020.02000). Shown as a baseline risk flag. |
| BK viremia | detected | Over-immunosuppression; must be balanced against rejection risk. |

## Considerations
The platform shows short, protocol-style considerations (for example, "consider for-cause biopsy
per centre protocol") when combinations of signals occur. They are prompts for the treating team,
not orders, and every decision is recorded by a clinician.

## What is simulated
- Every patient, lab value, HLA typing and biopsy in this repository.
- Class II eplet and PIRCHE-II values (production use requires HLAMatchmaker / PIRCHE-II integration
  from high-resolution typing).
- Model performance numbers, which describe the simulator and not real-world accuracy.

## Before any clinical use
Retrospective validation on local cohorts, prospective silent-mode evaluation, calibration per
centre, data-protection review, and regulatory assessment as software as a medical device.

## Imaging
CT is not used to diagnose kidney allograft rejection. Doppler ultrasound is used to exclude vascular
and urological causes of dysfunction before biopsy; a resistive index field can be added as an
optional input. Biopsy with Banff classification remains the reference standard.

## Explanations
Per-factor explanations are computed on the production model: each factor is reset to a typical
stable recipient (cohort median, or absent for yes/no findings) and the patient is re-scored. The
difference is reported in percentage points of 12-month risk.
