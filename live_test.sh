#!/bin/sh
set -eu
cd "$(dirname "$0")"
if [ ! -x .venv-live/bin/python ] || [ ! -f models/face_landmarker.task ]; then
  echo 'First prepare .venv-live and models/face_landmarker.task; see docs/LIVE_TEST.md.'
  exit 1
fi
mkdir -p logs
exec .venv-live/bin/python -u -m lampkit run --profile desk \
  --set personalize.state_file=null --set personalize.enabled=false \
  --duration "${1:-300}" --log "logs/live-$(date +%Y%m%d-%H%M%S).jsonl"
