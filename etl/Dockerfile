FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TZ=Asia/Taipei
WORKDIR /app
COPY db /app/db
COPY etl /app/etl
RUN pip install --no-cache-dir /app/db /app/etl
CMD ["python", "-m", "twstock_etl.cli", "scheduler"]
