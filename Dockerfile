FROM python:3.11-slim
WORKDIR /app

COPY pyproject.toml strategy.yaml ./
COPY src/ src/
COPY scripts/ scripts/

# Install Python deps. No headless browser needed: the XE collector fetches the
# server-rendered HTML over plain HTTP. The postgres extra ships the psycopg driver.
RUN pip install --no-cache-dir -e ".[schedule,postgres]"

# Volume mount point for the persistent DB and raw HTML cache.
RUN mkdir -p data

EXPOSE 8501

CMD ["bash", "scripts/start.sh"]
