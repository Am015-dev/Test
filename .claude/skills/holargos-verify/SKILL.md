---
name: holargos-verify
description: Run the project's full verification gate (tests, lint, format) and a real-Postgres end-to-end smoke before committing/shipping a change to the Holargos scout. Use after making any code change here, especially DB/pipeline/queue changes, and before merging to main.
---

# Verify & ship (Holargos)

The standard quality gate. Run it after any change before committing.

## 1. Test + lint + format gate (always)

```bash
cd /root/holargos && . .venv/bin/activate
python -m pytest -q                         # all green
ruff check src/ tests/ scripts/
black --check src/ tests/ scripts/          # (run `black src/ tests/ scripts/` to fix)
```

## 2. Real-Postgres smoke (for DB / pipeline / queue / migration changes)

The repo defaults to SQLite, but production is Postgres — verify there too. A local
Postgres can be run as an unprivileged user (it refuses to run as root):

```bash
PGBIN=$(dirname $(ls /usr/lib/postgresql/*/bin/initdb | head -1))
id pguser >/dev/null 2>&1 || useradd -m pguser
if [ ! -d /tmp/pgdata/base ]; then
  rm -rf /tmp/pgdata && mkdir -p /tmp/pgdata /tmp/pgrun && chown -R pguser /tmp/pgdata /tmp/pgrun
  su pguser -c "$PGBIN/initdb -D /tmp/pgdata -U holargos --auth=trust"
fi
chown -R pguser /tmp/pgdata /tmp/pgrun
su pguser -c "$PGBIN/pg_ctl -D /tmp/pgdata -o '-p 5433 -k /tmp/pgrun -c listen_addresses=127.0.0.1' -l /tmp/pglog.log start"
sleep 3
su pguser -c "$PGBIN/psql -h 127.0.0.1 -p 5433 -U holargos -d postgres -tc \"SELECT 1 FROM pg_database WHERE datname='holargos'\"" | grep -q 1 \
  || su pguser -c "$PGBIN/createdb -h 127.0.0.1 -p 5433 -U holargos holargos"
```

Then exercise the integrated paths (Postgres reset is fine — it's a test DB):

```bash
export DATABASE_URL="postgresql+psycopg://holargos@127.0.0.1:5433/holargos"
python -c "
import scout.db as db; db._engine=None
from scout.models import Base; from scout.db import get_engine, init_db
Base.metadata.drop_all(get_engine()); init_db()           # exercises migrations
from scout import queue; from scout.health import check_health
print('enqueue:', queue.enqueue_areas(['Cholargos']))
import importlib.util; s=importlib.util.spec_from_file_location('w','scripts/worker.py'); w=importlib.util.module_from_spec(s); s.loader.exec_module(w)
print('drained:', w.drain_once('verify-worker', 30))      # real scrape; may 0 if IP-throttled
print('jobs:', queue.job_stats()); print('health:', check_health().status)
"
```

Note: a real XE scrape from this environment is often rate-limited (per-IP) — `stored=0`
with a clean `blocked` log is EXPECTED here and not a regression; the retry/backoff and
fail-soft paths are what matter. Postgres stops between sessions; restart with the block above.

## 3. Ship

```bash
git checkout claude/holargos-property-scout-8yffib
git add -A && git commit -m "<clear message>"
git push -u origin claude/holargos-property-scout-8yffib
git checkout main && git merge --ff-only claude/holargos-property-scout-8yffib && git push origin main
```

Do NOT open a PR unless asked. The Oracle instance auto-deploys `main` within ~5 min.
