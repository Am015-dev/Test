#!/usr/bin/env bash
# Start the app on the published DB with no secrets (C13 measurements). Usage:
#   docs/qa/speed/serve.sh [port]    → PID in /tmp/scout-<port>.pid, log in /tmp/scout-<port>.log
set -e
PORT=${1:-8501}
cd "$(dirname "$0")/../../.."
[ -f /tmp/scout-$PORT.pid ] && kill "$(cat /tmp/scout-$PORT.pid)" 2>/dev/null && sleep 1
touch data/listings.db  # keep the local copy "fresh" so remote_db does not re-download it
env -u ANTHROPIC_API_KEY -u GITHUB_TOKEN -u GAUNTLET \
  python -m streamlit run src/scout/ui/app.py --server.headless true --server.port "$PORT" \
  --browser.gatherUsageStats false > /tmp/scout-$PORT.log 2>&1 &
echo $! > /tmp/scout-$PORT.pid
for _ in $(seq 60); do curl -sf "http://127.0.0.1:$PORT/_stcore/health" >/dev/null && exit 0; sleep 0.5; done
echo "app did not come up" >&2; exit 1
