"""Export the demo cohort with precomputed summaries (used by the static preview and to seed the DB)."""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from cortex_ml.cohort import demo_cohort  # noqa: E402
from cortex_ml.engine import DEFAULT_THRESHOLDS, THRESHOLD_INFO, summarize  # noqa: E402

OUT = HERE.parent / "web" / "assets" / "demo-data.json"
pts = demo_cohort()
data = {"thresholds": DEFAULT_THRESHOLDS, "threshold_info": THRESHOLD_INFO,
        "model": json.loads((HERE / "model" / "metrics.json").read_text()),
        "patients": [{"patient": p, "summary": summarize(p, DEFAULT_THRESHOLDS)} for p in pts]}
OUT.write_text(json.dumps(data, separators=(",", ":")))
print(len(pts), "patients,", round(OUT.stat().st_size / 1024), "KB ->", OUT)
