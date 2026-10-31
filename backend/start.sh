#!/bin/sh
# Container entrypoint: migrate, make sure the generated dataset exists (an empty disk is regenerated),
# create role accounts from env, purge due deletions, serve.
set -e
python -m app.cli migrate
python -m app.cli ensure-data
python -m app.cli seed
python -m app.cli purge || true
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips='*'
