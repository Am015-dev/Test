#!/usr/bin/env bash
set -e

# Seed demo listings on first boot when the DB is absent or empty.
if [ ! -s "data/listings.db" ]; then
    echo "[start] First boot — seeding demo listings..."
    python scripts/seed.py || echo "[start] Seed failed (non-fatal), continuing..."
fi

exec streamlit run src/scout/ui/app.py \
    --server.port=8501 \
    --server.address=0.0.0.0 \
    --server.headless=true \
    --server.fileWatcherType=none
