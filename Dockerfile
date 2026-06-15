FROM --platform=linux/amd64 python:3.11-slim-bullseye

WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    openssl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir poetry

COPY pyproject.toml poetry.lock ./

RUN poetry config virtualenvs.create false \
    && poetry install --no-root --no-interaction --no-ansi

# Build a MongoDB-specific CA bundle:
#   - Let's Encrypt ISRG Root X1 (Atlas historical CA)
#   - Google Trust Services roots (Atlas migrated to GTS by June 2025)
# Using a targeted bundle avoids ambiguity in certifi's full Mozilla store.
RUN curl -fsSL https://letsencrypt.org/certs/isrgrootx1.pem -o /tmp/isrgrootx1.pem \
    && curl -fsSL https://pki.goog/roots.pem -o /tmp/gts_roots.pem \
    && cat /tmp/isrgrootx1.pem /tmp/gts_roots.pem > /app/mongodb_ca.pem \
    && rm /tmp/isrgrootx1.pem /tmp/gts_roots.pem

COPY app/ ./app/
COPY config/ ./config/
COPY kairo/ ./kairo/
COPY web/ ./web/
COPY templates/ ./templates/
COPY manage.py .
COPY diagnose_atlas_tls.py .

RUN mkdir -p /app/.session_store

RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8080

HEALTHCHECK CMD curl --fail http://localhost:8080/ || exit 1

CMD ["sh", "-c", "python3 /app/diagnose_atlas_tls.py; exec gunicorn kairo.wsgi:application --bind 0.0.0.0:8080 --workers 2 --timeout 120"]
