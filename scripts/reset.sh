#!/bin/sh
# Reset EarnScore to the freshly generated state (macOS / Linux / Git Bash).
# Deletes everything done in the app (the earnscore-data volume) and restores the generated dataset from the image.
set -e
cd "$(dirname "$0")/.."
URL="http://localhost:8000"

docker compose down -v
docker compose up -d --wait || { echo "The container did not become healthy. See: docker compose logs app"; exit 1; }

# waits for /healthz inside the container, then checks accounts, lenders and the generated workers (read-only)
docker compose exec -T app python -m app.cli verify-clean

echo ""
echo "Ready: clean state"
echo "$URL"
