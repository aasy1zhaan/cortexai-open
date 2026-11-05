# CortexAI Open

Open-source demo of 12-month kidney-transplant rejection-risk estimation, built for the
Huawei ICT Competition 2026–2027 (Innovation track: *Creating Innovative AI Applications
Powered by Huawei Cloud*).

> **Synthetic data only.** No real patient data is used or included. This is not a medical
> device and must not be used for clinical decisions.

## What it does
- Generates a synthetic transplant cohort (`scripts/generate_synthetic.py`)
- Trains a calibrated gradient-boosting model plus a transparent logistic explainer (`scripts/train.py`)
- Serves a REST API (`app/main.py`): risk score, risk band, top drivers, assessment history
- Stores assessments in PostgreSQL (SQLite fallback for local dev)

Current demo metrics on the held-out synthetic test set: see `model/metrics.json`
(ROC-AUC ≈ 0.75). Synthetic metrics say nothing about real-world performance.

## Run locally
```bash
pip install -r requirements.txt
python scripts/generate_synthetic.py && python scripts/train.py
uvicorn app.main:app --reload        # http://localhost:8000
# or
docker compose up --build
```

## API
| Method | Path | Description |
|---|---|---|
| GET | `/api/health` | health check |
| GET | `/api/model` | features and metrics |
| POST | `/api/predict` | JSON patient features → `risk_12m`, `band`, `drivers` |
| GET | `/api/assessments` | recent assessments |
| GET | `/api/assessments/{id}` | one assessment |

## Huawei Cloud deployment plan
| Component | Huawei Cloud service |
|---|---|
| API container | ECS (or CCE for Kubernetes) |
| Database | RDS for PostgreSQL (`DATABASE_URL`) |
| Image registry | SWR |
| Model training / hosting (stage 2) | ModelArts |
| Static assets / exports | OBS |

Steps once cloud vouchers are issued:
1. Create a VPC, an ECS instance and an RDS for PostgreSQL instance in the same VPC.
2. Push the image to SWR: `docker build -t swr.<region>.myhuaweicloud.com/<org>/cortex-open:0.1 . && docker push ...`
3. On ECS: `docker run -d -p 80:8000 -e DATABASE_URL=postgresql+psycopg://<user>:<pass>@<rds-host>:5432/cortex <image>`
4. (Stage 2) Move training to a ModelArts job and serve the model as a ModelArts real-time service.

## License
Apache-2.0
