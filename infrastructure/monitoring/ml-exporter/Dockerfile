FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ML_EXPORTER_HOST=0.0.0.0

WORKDIR /app

RUN groupadd --system mlmonitor \
    && useradd --system --gid mlmonitor \
       --home-dir /nonexistent mlmonitor

RUN pip install --no-cache-dir \
    "numpy>=1.26,<3" \
    "pandas>=2.2,<3" \
    "pyarrow>=17,<24" \
    "scipy>=1.13,<2" \
    "scikit-learn>=1.5,<2" \
    "catboost>=1.2,<2" \
    "prometheus-client>=0.20,<1"

COPY src/monitoring/ /app/src/monitoring/

USER mlmonitor

EXPOSE 19101

CMD ["python", "-m", "src.monitoring.exporter"]
