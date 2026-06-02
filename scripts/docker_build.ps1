# Build AgentZero Docker image with progress + ETA (see docs/DOCKER.md).
$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot
python scripts/docker_build.py @args
exit $LASTEXITCODE
