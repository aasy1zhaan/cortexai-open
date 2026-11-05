"""CortexAI Open — clinician platform API (synthetic demo data).

Storage: PostgreSQL via DATABASE_URL (Huawei Cloud RDS for PostgreSQL in production),
SQLite fallback for local development.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import Cookie, Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import JSON, Column, DateTime, Integer, String, Text, create_engine, select
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from cortex.cohort import demo_cohort
from cortex.engine import DEFAULT_THRESHOLDS, THRESHOLD_INFO, summarize

ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT / "web"
log = logging.getLogger("cortex")
logging.basicConfig(level=logging.INFO)

engine = create_engine(os.getenv("DATABASE_URL", f"sqlite:///{ROOT / 'cortex_open.db'}"), pool_pre_ping=True)
Base = declarative_base()
SessionLocal = sessionmaker(engine, expire_on_commit=False)
now = lambda: datetime.now(timezone.utc)  # noqa: E731


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String(200), unique=True, nullable=False)
    name = Column(String(200), nullable=False)
    role = Column(String(20), nullable=False, default="clinician")  # clinician | admin
    pw_hash = Column(String(300), nullable=False)
    created_at = Column(DateTime(timezone=True), default=now)


class SessionToken(Base):
    __tablename__ = "sessions"
    id = Column(Integer, primary_key=True)
    token_hash = Column(String(64), unique=True, nullable=False)
    user_id = Column(Integer, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)


class Patient(Base):
    __tablename__ = "patients"
    id = Column(String(20), primary_key=True)
    data = Column(JSON, nullable=False)


class Review(Base):
    __tablename__ = "reviews"
    id = Column(Integer, primary_key=True)
    patient_id = Column(String(20), index=True)
    user_id = Column(Integer)
    user_name = Column(String(200))
    decision = Column(String(40))
    note = Column(Text)
    created_at = Column(DateTime(timezone=True), default=now)


class Audit(Base):
    __tablename__ = "audit"
    id = Column(Integer, primary_key=True)
    at = Column(DateTime(timezone=True), default=now)
    user_id = Column(Integer, nullable=True)
    action = Column(String(60))
    target = Column(String(60))
    detail = Column(Text)


class Setting(Base):
    __tablename__ = "settings"
    key = Column(String(60), primary_key=True)
    value = Column(JSON)


# ---------- security helpers ----------

def hash_pw(pw: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, 310_000)
    return f"pbkdf2_sha256$310000${salt.hex()}${dk.hex()}"


def verify_pw(pw: str, stored: str) -> bool:
    try:
        _, it, salt, dk = stored.split("$")
        cand = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), int(it))
        return hmac.compare_digest(cand.hex(), dk)
    except Exception:
        return False


def tok_hash(t: str) -> str:
    return hashlib.sha256(t.encode()).hexdigest()


_attempts: dict[str, list[float]] = defaultdict(list)


def rate_limited(key: str, limit: int = 8, window: int = 600) -> bool:
    t = time.time()
    _attempts[key] = [x for x in _attempts[key] if t - x < window]
    return len(_attempts[key]) >= limit


def audit(db: Session, user_id, action, target="", detail=""):
    db.add(Audit(user_id=user_id, action=action, target=target, detail=detail))


# ---------- startup ----------

def init_db():
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if not db.scalar(select(User).limit(1)):
            email = os.getenv("CORTEX_ADMIN_EMAIL", "admin@cortex.local")
            pw = os.getenv("CORTEX_ADMIN_PASSWORD") or secrets.token_urlsafe(14)
            db.add(User(email=email.lower(), name=os.getenv("CORTEX_ADMIN_NAME", "Administrator"),
                        role="admin", pw_hash=hash_pw(pw)))
            if not os.getenv("CORTEX_ADMIN_PASSWORD"):
                log.warning("Created admin %s with generated password: %s  (set CORTEX_ADMIN_PASSWORD to choose one)",
                            email, pw)
        if not db.scalar(select(Patient).limit(1)):
            seed = WEB_DIR / "assets" / "demo-data.json"
            pts = [x["patient"] for x in json.loads(seed.read_text())["patients"]] if seed.exists() else demo_cohort()
            for p in pts:
                db.add(Patient(id=p["id"], data=p))
        if not db.get(Setting, "thresholds"):
            db.add(Setting(key="thresholds", value=DEFAULT_THRESHOLDS))
        db.commit()


init_db()
app = FastAPI(title="CortexAI Open", version="0.2.0", docs_url="/api/docs", openapi_url="/api/openapi.json")


def get_db():
    with SessionLocal() as db:
        yield db


def current_user(cx_session: Optional[str] = Cookie(default=None), db: Session = Depends(get_db)) -> User:
    if not cx_session:
        raise HTTPException(401, "Not signed in")
    s = db.scalar(select(SessionToken).where(SessionToken.token_hash == tok_hash(cx_session)))
    if not s or s.expires_at.replace(tzinfo=timezone.utc) < now():
        raise HTTPException(401, "Session expired")
    u = db.get(User, s.user_id)
    if not u:
        raise HTTPException(401)
    return u


def admin_user(u: User = Depends(current_user)) -> User:
    if u.role != "admin":
        raise HTTPException(403, "Administrator only")
    return u


def thresholds(db: Session) -> dict:
    s = db.get(Setting, "thresholds")
    return {**DEFAULT_THRESHOLDS, **(s.value if s else {})}


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "same-origin"
    if request.url.path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-store"
    return resp


# ---------- auth ----------

class LoginIn(BaseModel):
    email: str
    password: str


@app.post("/api/auth/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    key = f"{body.email.lower()}|{request.client.host if request.client else ''}"
    if rate_limited(key):
        raise HTTPException(429, "Too many attempts. Try again in 10 minutes.")
    u = db.scalar(select(User).where(User.email == body.email.lower().strip()))
    if not u or not verify_pw(body.password, u.pw_hash):
        _attempts[key].append(time.time())
        audit(db, None, "login_failed", body.email.lower()[:60])
        db.commit()
        raise HTTPException(401, "Invalid email or password")
    token = secrets.token_urlsafe(32)
    db.add(SessionToken(token_hash=tok_hash(token), user_id=u.id, expires_at=now() + timedelta(hours=12)))
    audit(db, u.id, "login")
    db.commit()
    response.set_cookie("cx_session", token, httponly=True, samesite="lax", max_age=12 * 3600,
                        secure=os.getenv("COOKIE_SECURE", "0") == "1")
    return {"name": u.name, "role": u.role}


@app.post("/api/auth/logout")
def logout(response: Response, cx_session: Optional[str] = Cookie(default=None), db: Session = Depends(get_db)):
    if cx_session:
        s = db.scalar(select(SessionToken).where(SessionToken.token_hash == tok_hash(cx_session)))
        if s:
            db.delete(s)
            db.commit()
    response.delete_cookie("cx_session")
    return {"ok": True}


@app.get("/api/auth/me")
def me(u: User = Depends(current_user)):
    return {"id": u.id, "email": u.email, "name": u.name, "role": u.role}


class UserIn(BaseModel):
    email: str
    name: str
    password: str = Field(min_length=10)
    role: str = Field("clinician", pattern="^(clinician|admin)$")


@app.get("/api/users")
def list_users(_: User = Depends(admin_user), db: Session = Depends(get_db)):
    return [{"id": u.id, "email": u.email, "name": u.name, "role": u.role} for u in db.scalars(select(User))]


@app.post("/api/users")
def create_user(body: UserIn, a: User = Depends(admin_user), db: Session = Depends(get_db)):
    if db.scalar(select(User).where(User.email == body.email.lower())):
        raise HTTPException(409, "User exists")
    db.add(User(email=body.email.lower(), name=body.name, role=body.role, pw_hash=hash_pw(body.password)))
    audit(db, a.id, "user_created", body.email.lower())
    db.commit()
    return {"ok": True}


# ---------- clinical ----------

def _last_review(db, pid):
    r = db.scalar(select(Review).where(Review.patient_id == pid).order_by(Review.id.desc()))
    return {"by": r.user_name, "at": r.created_at.isoformat(), "decision": r.decision} if r else None


@app.get("/api/worklist")
def worklist(u: User = Depends(current_user), db: Session = Depends(get_db)):
    th = thresholds(db)
    rows = []
    for p in db.scalars(select(Patient)):
        d = p.data
        s = summarize(d, th)
        last = d["visits"][-1] if d["visits"] else {}
        rows.append({
            "id": d["id"], "name": d["display_name"], "sex": d["sex"], "age": d["age"],
            "months_since_tx": d["follow_up_months"], "donor_type": d["donor_type"],
            "risk_12m": s["risk_12m"], "risk_delta": s["risk_delta"], "band": s["band"],
            "alerts": s["alerts"], "egfr": last.get("egfr"), "ddcfdna": last.get("ddcfdna"),
            "dsa_mfi_max": last.get("dsa_mfi_max"), "tac_trough": last.get("tac_trough"),
            "spark": [t["risk"] for t in s["trajectory"]][-8:], "last_review": _last_review(db, d["id"]),
        })
    rows.sort(key=lambda r: (-sum(a["severity"] == "high" for a in r["alerts"]), -r["risk_12m"]))
    audit(db, u.id, "worklist_view")
    db.commit()
    return {"thresholds": th, "patients": rows}


@app.get("/api/patients/{pid}")
def patient(pid: str, u: User = Depends(current_user), db: Session = Depends(get_db)):
    p = db.get(Patient, pid)
    if not p:
        raise HTTPException(404)
    reviews = [{"by": r.user_name, "at": r.created_at.isoformat(), "decision": r.decision, "note": r.note}
               for r in db.scalars(select(Review).where(Review.patient_id == pid).order_by(Review.id.desc()))]
    audit(db, u.id, "patient_view", pid)
    db.commit()
    return {"patient": p.data, "summary": summarize(p.data, thresholds(db)), "reviews": reviews}


class VisitIn(BaseModel):
    month: float = Field(gt=0, le=240)
    creatinine: float = Field(gt=0.2, le=15)
    egfr: float = Field(gt=1, le=150)
    upcr: float = Field(ge=0, le=20)
    tac_trough: float = Field(ge=0, le=40)
    ddcfdna: float = Field(ge=0, le=20)
    dsa_mfi_max: float = Field(ge=0, le=40000)
    bk_viremia: int = Field(0, ge=0, le=1)


@app.post("/api/patients/{pid}/visits")
def add_visit(pid: str, v: VisitIn, u: User = Depends(current_user), db: Session = Depends(get_db)):
    p = db.get(Patient, pid)
    if not p:
        raise HTTPException(404)
    d = json.loads(json.dumps(p.data))
    visits = d["visits"]
    if visits and v.month <= visits[-1]["month"]:
        raise HTTPException(400, "New visit must be later than the last recorded visit")
    lo, hi = (8.0, 12.0) if v.month <= 3 else (5.0, 8.0)
    window = [x for x in visits if v.month - 6 <= x["month"]] + [{"month": v.month, "tac_trough": v.tac_trough,
                                                                  "tac_target_low": lo, "tac_target_high": hi}]
    tr = [x["tac_trough"] for x in window]
    import numpy as np
    cv = float(np.std(tr) / np.mean(tr) * 100) if len(tr) > 1 and np.mean(tr) > 0 else 0.0
    ttr = float(np.mean([x["tac_target_low"] <= x["tac_trough"] <= x["tac_target_high"] for x in window]) * 100)
    ref = [x for x in visits if v.month - 4 <= x["month"] <= v.month - 2] or visits[-1:]
    change = float(np.clip((v.egfr - ref[0]["egfr"]) / ref[0]["egfr"] * 100, -80, 80)) if ref else 0.0
    visits.append({**v.model_dump(), "tac_target_low": lo, "tac_target_high": hi, "tac_cv": round(cv, 1),
                   "tac_ttr": round(ttr), "egfr_change_3m": round(change, 1)})
    d["follow_up_months"] = v.month
    p.data = d
    audit(db, u.id, "visit_added", pid, json.dumps(v.model_dump()))
    db.commit()
    return {"summary": summarize(d, thresholds(db))}


class ReviewIn(BaseModel):
    decision: str = Field(pattern="^(reviewed|escalate|biopsy_requested|repeat_tests|no_action)$")
    note: str = Field("", max_length=2000)


@app.post("/api/patients/{pid}/reviews")
def add_review(pid: str, body: ReviewIn, u: User = Depends(current_user), db: Session = Depends(get_db)):
    if not db.get(Patient, pid):
        raise HTTPException(404)
    db.add(Review(patient_id=pid, user_id=u.id, user_name=u.name, decision=body.decision, note=body.note))
    audit(db, u.id, "review", pid, body.decision)
    db.commit()
    return {"ok": True}


@app.get("/api/settings/thresholds")
def get_thresholds(_: User = Depends(current_user), db: Session = Depends(get_db)):
    return {"values": thresholds(db), "defaults": DEFAULT_THRESHOLDS, "info": THRESHOLD_INFO}


@app.put("/api/settings/thresholds")
def put_thresholds(body: dict, a: User = Depends(admin_user), db: Session = Depends(get_db)):
    clean = {k: float(v) for k, v in body.items() if k in DEFAULT_THRESHOLDS}
    s = db.get(Setting, "thresholds")
    s.value = {**thresholds(db), **clean}
    audit(db, a.id, "thresholds_changed", "", json.dumps(clean))
    db.commit()
    return {"values": s.value}


@app.get("/api/audit")
def get_audit(limit: int = 100, _: User = Depends(admin_user), db: Session = Depends(get_db)):
    names = {u.id: u.name for u in db.scalars(select(User))}
    rows = db.scalars(select(Audit).order_by(Audit.id.desc()).limit(min(limit, 500)))
    return [{"at": r.at.isoformat(), "user": names.get(r.user_id, "—"), "action": r.action,
             "target": r.target, "detail": r.detail} for r in rows]


@app.get("/api/model")
def model_card(_: User = Depends(current_user)):
    return json.loads((ROOT / "model" / "metrics.json").read_text())


@app.get("/api/health")
def health():
    return {"status": "ok"}


# ---------- static web ----------
WEB = ROOT / "web"


@app.get("/")
def landing():
    return FileResponse(WEB / "index.html")


@app.get("/login")
def login_page():
    return FileResponse(WEB / "login.html")


@app.get("/app")
def app_page():
    return FileResponse(WEB / "app.html")


app.mount("/", StaticFiles(directory=WEB), name="web")
