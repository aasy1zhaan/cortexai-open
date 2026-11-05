FROM python:3.12-slim
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Train on the synthetic cohort and bundle the demo data at build time (reproducible, no real data).
RUN python ml/train.py 6000 && python ml/export_demo.py && python -m pytest -q ml/tests tests
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
