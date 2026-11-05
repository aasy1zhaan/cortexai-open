import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["DATABASE_URL"] = "sqlite:///" + str(ROOT / "test_api.db")
os.environ["CORTEX_ADMIN_EMAIL"] = "admin@test.local"
os.environ["CORTEX_ADMIN_PASSWORD"] = "test-password-123"
(ROOT / "test_api.db").unlink(missing_ok=True)

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402

c = TestClient(app)


def login():
    r = c.post("/api/auth/login", json={"email": "admin@test.local", "password": "test-password-123"})
    assert r.status_code == 200


def test_clinical_routes_require_session():
    for path in ("/api/worklist", "/api/patients/CX-1040", "/api/model", "/api/audit"):
        assert c.get(path).status_code == 401


def test_wrong_password_rejected():
    assert c.post("/api/auth/login", json={"email": "admin@test.local", "password": "nope"}).status_code == 401


def test_worklist_and_new_visit_rescored():
    login()
    wl = c.get("/api/worklist").json()["patients"]
    assert len(wl) == 40
    pid = wl[0]["id"]
    before = c.get(f"/api/patients/{pid}").json()
    last = before["patient"]["visits"][-1]
    body = {"month": last["month"] + 1, "creatinine": last["creatinine_umol"] * 1.4, "creatinine_unit": "umol/L",
            "upcr": 0.9, "tac_trough": 3.0, "ddcfdna": 2.2, "dsa": [{"spec": "DQ7", "hla_class": "II", "mfi": 6000}]}
    r = c.post(f"/api/patients/{pid}/visits", json=body)
    assert r.status_code == 200, r.text
    codes = {a["code"] for a in r.json()["summary"]["alerts"]}
    assert {"ddcfdna", "dsa", "tac_low", "upcr"} <= codes
    new = c.get(f"/api/patients/{pid}").json()["patient"]["visits"][-1]
    assert new["egfr"] < last["egfr"]          # eGFR derived from creatinine via CKD-EPI
    assert c.post(f"/api/patients/{pid}/reviews", json={"decision": "biopsy_requested", "note": "t"}).status_code == 200
    assert any(e["action"] == "review" for e in c.get("/api/audit").json())
