FROM python:3.11-slim
WORKDIR /app

COPY pyproject.toml strategy.yaml ./
COPY src/ src/
COPY scripts/ scripts/

# Install Python deps + Playwright Chromium and all its system libraries.
RUN pip install --no-cache-dir -e ".[schedule]" \
    && playwright install --with-deps chromium

# Volume mount point for the persistent SQLite DB and raw HTML cache.
RUN mkdir -p data

EXPOSE 8501

CMD ["bash", "scripts/start.sh"]
