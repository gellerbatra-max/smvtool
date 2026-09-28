FROM python:3.12-slim AS base

WORKDIR /app

# psycopg[binary] ships its own libpq, so no build-essential/libpq-dev needed.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY smv_engine ./smv_engine
COPY migrations ./migrations
COPY alembic.ini .
COPY docker-entrypoint.sh .
RUN chmod +x docker-entrypoint.sh

# Only needed by the opt-in `seed-demo` Compose service (see
# docker-compose.yml's `demo` profile), but small (httpx is already a
# dependency) and simplest to always include rather than build a second
# image just for it.
COPY scripts ./scripts

ENV PYTHONPATH=/app:/app/smv_engine \
    PYTHONUNBUFFERED=1

EXPOSE 8000

ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
