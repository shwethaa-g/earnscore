# Reset EarnScore to the freshly generated state (Windows PowerShell).
# Deletes everything done in the app (the earnscore-data volume) and restores the generated dataset from the image.
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
$url = "http://localhost:8000"

docker compose down -v
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
docker compose up -d --wait
if ($LASTEXITCODE -ne 0) { Write-Host "The container did not become healthy. See: docker compose logs app"; exit 1 }

# waits for /healthz inside the container, then checks accounts, lenders and the generated workers (read-only)
docker compose exec -T app python -m app.cli verify-clean
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "Ready: clean state"
Write-Host $url
