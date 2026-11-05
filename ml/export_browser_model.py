"""Export the trained model to JSON so the AI page can run inference in the browser (no server).

Format per calibration fold: baseline raw score, trees as flat node arrays, isotonic calibrator.
Parity with scikit-learn is checked on held-out simulated visits before writing.
"""
import json
import sys
from pathlib import Path

import joblib
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from cortex_ml.sim import FEATURE_LABELS, FEATURES, training_table  # noqa: E402

b = joblib.load(HERE / "model" / "cortex_open.joblib")
folds = []
for cc in b["gbm"].calibrated_classifiers_:
    est, cal = cc.estimator, cc.calibrators[0]
    trees = []
    for (pred,) in est._predictors:
        n = pred.nodes
        # node: [feature, threshold, missing_left, left, right, is_leaf, value]
        trees.append([[int(x["feature_idx"]), float(x["num_threshold"]), int(x["missing_go_to_left"]),
                       int(x["left"]), int(x["right"]), int(x["is_leaf"]), round(float(x["value"]), 6)] for x in n])
    folds.append({"baseline": float(est._baseline_prediction.ravel()[0]), "trees": trees,
                  "cal_x": [round(float(v), 6) for v in cal.X_thresholds_], "cal_y": [round(float(v), 6) for v in cal.y_thresholds_]})


def js_like(row):
    out = []
    for f in folds:
        raw = f["baseline"]
        for t in f["trees"]:
            i = 0
            while not t[i][5]:
                v = row[t[i][0]]
                i = t[i][3] if ((np.isnan(v) and t[i][2]) or (not np.isnan(v) and v <= t[i][1])) else t[i][4]
            raw += t[i][6]
        out.append(float(np.interp(raw, f["cal_x"], f["cal_y"])))
    return float(np.mean(out))


df = training_table(300, seed=99)
X = df[FEATURES].to_numpy(dtype=float)
ref = b["gbm"].predict_proba(df[FEATURES])[:, 1]
mine = np.array([js_like(r) for r in X[:600]])
err = float(np.abs(mine - ref[:600]).max())
print("max abs difference vs scikit-learn:", err)
assert err < 2e-3, err

out = {"features": FEATURES, "labels": FEATURE_LABELS, "reference": b["reference"], "folds": folds}
dst = HERE.parent / "web" / "assets" / "model.json"
dst.write_text(json.dumps(out, separators=(",", ":")))
print(round(dst.stat().st_size / 1e6, 2), "MB ->", dst)
