#!/bin/sh
set -eu
cd "$(dirname "$0")"
if [ ! -x .venv-live/bin/python ] || [ ! -f models/face_landmarker.task ]; then
  echo 'Prepare .venv-live and the face model first; see docs/LIVE_TEST.md.'
  exit 1
fi
if [ ! -f web/dist/index.html ]; then
  (cd web && npm ci && npm run build)
fi
exec .venv-live/bin/python -u -m lampkit.lab "$@"
