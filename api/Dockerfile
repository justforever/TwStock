FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TZ=Asia/Taipei
WORKDIR /app
COPY db /app/db
COPY api /app/api
RUN pip install --no-cache-dir /app/db /app/api
EXPOSE 8000
CMD ["uvicorn", "twstock_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
