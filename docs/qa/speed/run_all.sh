#!/usr/bin/env bash
# Full C13 measurement: 3 cold starts per answer set (server restarted before each), then every
# tap 3× on the warm server. Usage: docs/qa/speed/run_all.sh <label> [port]
set -e
LABEL=${1:?label}; PORT=${2:-8501}
cd "$(dirname "$0")/../../.."
export NODE_PATH=$(npm root -g)
rm -f "docs/qa/speed/$LABEL.json"
for mode in cold-a cold-b cold-a cold-b cold-a cold-b; do
  docs/qa/speed/serve.sh "$PORT"
  node docs/qa/speed/measure_speed.js "$LABEL" "http://127.0.0.1:$PORT" "$mode"
done
node docs/qa/speed/measure_speed.js "$LABEL" "http://127.0.0.1:$PORT"
