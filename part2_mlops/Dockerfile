# Inference service: FastAPI + the champion sklearn Pipeline (features + preprocessing + model).
FROM python:3.12-slim

# LightGBM needs the OpenMP runtime
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements-serve.txt .
RUN pip install --no-cache-dir -r requirements-serve.txt

COPY src ./src
# The champion is exported by `python -m severity_model.train` - build after training.
COPY models/champion ./models/champion
ENV PYTHONPATH=/app/src \
    CHAMPION_DIR=/app/models/champion \
    PREDICTION_LOG_PATH=/app/logs/predictions.jsonl

RUN useradd --create-home appuser && mkdir -p /app/logs && chown -R appuser /app
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD curl -fs http://localhost:8000/health || exit 1
CMD ["uvicorn", "severity_model.api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
