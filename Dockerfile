FROM python:3.12-slim
WORKDIR /srv
# Build hosts report 0 physical cores to joblib/loky; pin threads so training does not hang.
ENV LOKY_MAX_CPU_COUNT=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Train on the synthetic cohort and bundle the demo data at build time (reproducible, no real data).
RUN pip install --no-cache-dir "pytest>=8" && timeout 900 python ml/train.py 6000 && python ml/export_demo.py && python ml/export_browser_model.py && python -m pytest -q ml/tests tests
EXPOSE 8000
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips="*"
