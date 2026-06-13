FROM --platform=linux/amd64 python:3.11-slim-bullseye

WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir poetry

COPY pyproject.toml poetry.lock ./

RUN poetry config virtualenvs.create false \
    && poetry install --no-root --no-interaction --no-ansi

# Patch pymongo to cap TLS at 1.2 — Atlas M0 rejects TLS 1.3 from Cloud Run.
COPY patch_pymongo_ssl.py /tmp/patch_pymongo_ssl.py
RUN python3 /tmp/patch_pymongo_ssl.py

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
COPY .streamlit/ ./.streamlit/
COPY streamlit_app.py .

RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8501

HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health || exit 1

CMD ["streamlit", "run", "streamlit_app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true"]
