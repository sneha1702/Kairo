FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY narrative_engine.py .
COPY narrative_tracker.py .
COPY elasticsearch_manager.py .
COPY app.py .
COPY utils.py .
COPY config.py .

# Copy data
COPY data/ /app/data/

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Expose Streamlit port
EXPOSE 8501

# Health check
HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health || exit 1

# Configure Streamlit
RUN mkdir -p ~/.streamlit
RUN echo "\
[server]\n\
port = 8501\n\
address = 0.0.0.0\n\
headless = true\n\
" > ~/.streamlit/config.toml

# Run Streamlit app
CMD ["streamlit", "run", "app.py"]
