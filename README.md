# CortexAI Open — Graft Care

Open-source clinician workspace for **kidney transplant rejection-risk monitoring**, built for the
Huawei ICT Competition 2026–2027 (Innovation track: *Creating Innovative AI Applications Powered by
Huawei Cloud*).

> **Synthetic data only.** No real patient data is used or included. This is a research prototype,
> not a medical device, and must not be used for clinical decisions.

## What clinicians get

| Screen | What it does |
|---|---|
| **Worklist** | Every recipient ranked by high-severity signals, then predicted 12-month risk. Filters for unreviewed, high risk, dd-cfDNA, DSA+, tacrolimus. |
| **Patient chart** | Risk trajectory, active signals with protocol-style considerations, per-factor explanation, HLA donor vs recipient (mismatches highlighted), class II eplet load and PIRCHE-II, trends for eGFR, tacrolimus (target corridor, CV, TTR), dd-cfDNA, DSA MFI, UPCR, creatinine, Banff biopsy history, visit log. |
| **Clinical review** | Clinician records a decision (reviewed, repeat tests, for-cause biopsy, escalate to MDT) with a note. |
| **Add lab results** | New visit is re-scored immediately (CV, TTR and eGFR change are derived). |
| **Model card** | Intended use, target, data, held-out metrics, calibration, limitations. |
| **Alert thresholds** | Centre-tunable cut-offs with the literature behind each default (admin only). |
| **Team and access / Audit log** | Accounts are issued by an admin; sign-ins, record views, reviews and setting changes are logged. |

Public pages: `/` landing (platform, clinical basis, roadmap, recognition) and `/login`.

## Architecture
```
web/            static front end (no build step): landing, login, clinician app
app/main.py     FastAPI: auth (PBKDF2 + HttpOnly session cookie), clinical API, audit, static files
cortex/sim.py   longitudinal synthetic transplant simulator
cortex/engine.py risk scoring, explanations, rule-based signals, considerations
cortex/cohort.py demo cohort (enriched with higher-risk recipients)
scripts/train.py   train + evaluate (patient-level split) -> model/
scripts/export_demo.py  bundle the demo cohort for the static preview
```
If the front end cannot reach `/api/health` it switches to **preview mode** and serves the bundled
synthetic cohort read-only. That is how the static preview works without a server.

## Run locally
```bash
pip install -r requirements.txt
python scripts/train.py 6000          # ~2-4 min, writes model/
python scripts/export_demo.py         # writes web/assets/demo-data.json (also used to seed the DB)
CORTEX_ADMIN_EMAIL=you@hospital.kz CORTEX_ADMIN_PASSWORD='choose-a-long-one' uvicorn app.main:app
# open http://localhost:8000
```
If `CORTEX_ADMIN_PASSWORD` is not set, a random admin password is generated and printed once in the log.
Docker: `docker compose up --build` (PostgreSQL + API).

## API (all clinical routes need a session)
`POST /api/auth/login` · `POST /api/auth/logout` · `GET /api/auth/me` · `GET /api/worklist` ·
`GET /api/patients/{id}` · `POST /api/patients/{id}/visits` · `POST /api/patients/{id}/reviews` ·
`GET|PUT /api/settings/thresholds` · `GET|POST /api/users` (admin) · `GET /api/audit` (admin) ·
`GET /api/model` · `GET /api/health`. OpenAPI docs at `/api/docs`.

## Huawei Cloud deployment
| Component | Huawei Cloud service |
|---|---|
| API + web container | ECS (or CCE) |
| Database | RDS for PostgreSQL via `DATABASE_URL` |
| Image registry | SWR |
| Training / model hosting (stage 2) | ModelArts |
| Backups, exports | OBS |

1. Create a VPC, an ECS instance and an RDS for PostgreSQL instance in the same VPC; open 443 only.
2. `docker build -t swr.<region>.myhuaweicloud.com/<org>/cortex-open:0.2 . && docker push …`
3. On ECS: `docker run -d -p 8000:8000 -e DATABASE_URL=postgresql+psycopg://<user>:<pass>@<rds-host>:5432/cortex -e CORTEX_ADMIN_EMAIL=… -e CORTEX_ADMIN_PASSWORD=… -e COOKIE_SECURE=1 <image>` behind an HTTPS load balancer (ELB).
4. Stage 2: move `scripts/train.py` to a ModelArts training job and serve the model as a ModelArts real-time service.

## Clinical basis and limitations
See `docs/clinical-basis.md`. In short: default thresholds follow published work (dd-cfDNA 1%, DSA
MFI 1,400 as in iBox, class II eplet mismatch ≥ 14, tacrolimus CV > 30%), the model is trained on a
simulated cohort, and eplet/PIRCHE values are simulated until HLAMatchmaker/PIRCHE are integrated.

## License
Apache-2.0
