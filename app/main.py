"""CortexAI Open — demo API for kidney-transplant rejection risk on synthetic data.

Storage: PostgreSQL via DATABASE_URL (Huawei Cloud RDS for PostgreSQL in production),
falls back to local SQLite for development.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import JSON, Column, DateTime, Float, Integer, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

ROOT = Path(__file__).resolve().parent.parent
BUNDLE = joblib.load(ROOT / "model" / "cortex_open.joblib")
METRICS = json.loads((ROOT / "model" / "metrics.json").read_text())
FEATURES = BUNDLE["features"]

engine = create_engine(os.getenv("DATABASE_URL", f"sqlite:///{ROOT / 'cortex_open.db'}"))
Base = declarative_base()


class Assessment(Base):
    __tablename__ = "assessments"
    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    inputs = Column(JSON)
    risk = Column(Float)


Base.metadata.create_all(engine)
Session = sessionmaker(engine)


class Patient(BaseModel):
    recipient_age: float = Field(45, ge=18, le=90)
    donor_age: float = Field(45, ge=0, le=90)
    donor_type_deceased: int = Field(0, ge=0, le=1)
    hla_mismatch: int = Field(3, ge=0, le=6)
    pra_percent: float = Field(10, ge=0, le=100)
    dsa_present: int = Field(0, ge=0, le=1)
    cold_ischemia_hours: float = Field(2, ge=0, le=48)
    delayed_graft_function: int = Field(0, ge=0, le=1)
    prior_transplant: int = Field(0, ge=0, le=1)
    creatinine_month1: float = Field(1.4, ge=0.3, le=10)
    creatinine_month3: float = Field(1.3, ge=0.3, le=10)
    egfr_month3: float = Field(60, ge=1, le=150)
    proteinuria_g_day: float = Field(0.3, ge=0, le=10)
    tacrolimus_trough: float = Field(7.5, ge=0, le=30)
    tacrolimus_cv_percent: float = Field(25, ge=0, le=100)
    bk_viremia: int = Field(0, ge=0, le=1)
    cmv_mismatch: int = Field(0, ge=0, le=1)
    diabetes: int = Field(0, ge=0, le=1)
    adherence_score: float = Field(0.85, ge=0, le=1)


def explain(x: pd.DataFrame) -> list[dict]:
    """Per-feature contribution to the log-odds from the transparent logistic model."""
    scaler, lr = BUNDLE["lr"].named_steps.values()
    z = scaler.transform(x)[0]
    contrib = z * lr.coef_[0]
    order = np.argsort(-np.abs(contrib))[:6]
    return [{"feature": FEATURES[i], "value": float(x.iloc[0, i]),
             "contribution": round(float(contrib[i]), 3)} for i in order]


app = FastAPI(title="CortexAI Open", version="0.1.0")


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/model")
def model_info():
    return {"features": FEATURES, "metrics": METRICS}


@app.post("/api/predict")
def predict(p: Patient):
    x = pd.DataFrame([p.model_dump()])[FEATURES]
    risk = float(BUNDLE["gbm"].predict_proba(x)[0, 1])
    band = "high" if risk >= 0.35 else "moderate" if risk >= 0.15 else "low"
    with Session() as s:
        a = Assessment(inputs=p.model_dump(), risk=risk)
        s.add(a)
        s.commit()
        aid = a.id
    return {"id": aid, "risk_12m": round(risk, 3), "band": band, "drivers": explain(x),
            "disclaimer": "Demo on synthetic data. Not for clinical use."}


@app.get("/api/assessments")
def assessments(limit: int = 20):
    with Session() as s:
        rows = s.query(Assessment).order_by(Assessment.id.desc()).limit(min(limit, 200)).all()
        return [{"id": r.id, "created_at": r.created_at.isoformat(), "risk_12m": round(r.risk, 3)} for r in rows]


@app.get("/api/assessments/{aid}")
def assessment(aid: int):
    with Session() as s:
        r = s.get(Assessment, aid)
        if not r:
            raise HTTPException(404)
        return {"id": r.id, "created_at": r.created_at.isoformat(), "inputs": r.inputs, "risk_12m": r.risk}


web = ROOT / "web"
if web.exists():
    app.mount("/", StaticFiles(directory=web, html=True), name="web")
