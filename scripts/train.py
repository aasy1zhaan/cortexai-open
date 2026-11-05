"""Train the CortexAI Open demo model on the synthetic cohort and save metrics."""
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, brier_score_loss, average_precision_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).parent))
from generate_synthetic import FEATURES  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
df = pd.read_csv(ROOT / "data" / "synthetic_cohort.csv")
X, y = df[FEATURES], df["rejection_12m"]
Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, stratify=y, random_state=0)

gbm = CalibratedClassifierCV(HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, random_state=0),
                             method="isotonic", cv=3).fit(Xtr, ytr)
# Logistic baseline also serves as the per-feature explainer (transparent coefficients).
lr = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000)).fit(Xtr, ytr)

metrics = {}
for name, m in {"gbm": gbm, "logistic": lr}.items():
    p = m.predict_proba(Xte)[:, 1]
    metrics[name] = {"roc_auc": round(roc_auc_score(yte, p), 3),
                     "pr_auc": round(average_precision_score(yte, p), 3),
                     "brier": round(brier_score_loss(yte, p), 4)}
metrics["n_train"], metrics["n_test"] = len(Xtr), len(Xte)
metrics["prevalence"] = round(float(y.mean()), 3)
metrics["note"] = "Synthetic data only. Not validated on real patients. Not a medical device."

(ROOT / "model").mkdir(exist_ok=True)
joblib.dump({"gbm": gbm, "lr": lr, "features": FEATURES,
             "means": Xtr.mean().to_dict()}, ROOT / "model" / "cortex_open.joblib")
(ROOT / "model" / "metrics.json").write_text(json.dumps(metrics, indent=2))
print(json.dumps(metrics, indent=2))
