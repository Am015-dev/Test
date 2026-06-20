#!/usr/bin/env bash
set -e

# Ensure the schema exists (works for both SQLite and Postgres via DATABASE_URL).
python -c "from scout.db import init_db; init_db()"

# Populate real listings on first boot in the background (no demo/seed data).
# Safe to fail — the daily cron retries; the dashboard shows a clean empty state.
( python -c "from scout.pipeline import run; print(run())" \
    >> /var/log/holargos-daily.log 2>&1 & ) || true

exec streamlit run src/scout/ui/app.py \
    --server.port=8501 \
    --server.address=0.0.0.0 \
    --server.headless=true \
    --server.fileWatcherType=none
