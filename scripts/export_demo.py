"""Export the demo cohort with precomputed summaries for the static preview (no backend)."""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from cortex.cohort import demo_cohort
from cortex.engine import DEFAULT_THRESHOLDS, THRESHOLD_INFO, summarize
pts = demo_cohort()
out = {"thresholds": DEFAULT_THRESHOLDS, "threshold_info": THRESHOLD_INFO,
       "model": json.loads((ROOT / "model/metrics.json").read_text()),
       "patients": [{"patient": p, "summary": summarize(p, DEFAULT_THRESHOLDS)} for p in pts]}
(ROOT / "web/assets/demo-data.json").write_text(json.dumps(out, separators=(",", ":")))
print(len(pts), round((ROOT / "web/assets/demo-data.json").stat().st_size / 1024), "KB")
