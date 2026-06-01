# Start Google Chrome with remote debugging (CDP) on a DEDICATED profile.
#
# Chrome 136+ refuses --remote-debugging-port when launched against the default
# user-data-dir (security hardening), so we use a separate profile under the repo.
# Log into Indeed/Glassdoor once in that window; the session persists in the dir.
#
# Usage:
#   .\scripts\launch_chrome_cdp.ps1
#   .\scripts\launch_chrome_cdp.ps1 -Port 9223
#   .\scripts\launch_chrome_cdp.ps1 -UserDataDir "C:\path\to\profile"
#
# Then in .env:
#   AGENTZERO_SCRAPE_CDP_URL=http://127.0.0.1:9222
#   AGENTZERO_SCRAPE_CDP_SITES=indeed,glassdoor

param(
    [int]$Port = 9222,
    [string]$UserDataDir = ""
)

$chromeCandidates = @(
    "${env:ProgramFiles}\Google\Chrome\Application\chrome.exe",
    "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe"
)

$chrome = $chromeCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $chrome) {
    Write-Error "Google Chrome not found. Install Chrome or pass a custom path."
    exit 1
}

if (-not $UserDataDir) {
    $repoRoot = Split-Path -Parent $PSScriptRoot
    $UserDataDir = Join-Path $repoRoot "data\browser_profiles\cdp"
}
if (-not (Test-Path $UserDataDir)) {
    New-Item -ItemType Directory -Path $UserDataDir -Force | Out-Null
}

Write-Host ""
Write-Host "Starting Chrome with CDP on port $Port ..."
Write-Host "Dedicated profile: $UserDataDir"
Write-Host ""
Write-Host "Add to .env:" -ForegroundColor Cyan
Write-Host "  AGENTZERO_SCRAPE_CDP_URL=http://127.0.0.1:$Port"
Write-Host "  AGENTZERO_SCRAPE_CDP_SITES=indeed,glassdoor"
Write-Host ""

Start-Process -FilePath $chrome -ArgumentList @(
    "--remote-debugging-port=$Port",
    "--user-data-dir=`"$UserDataDir`""
)

Write-Host "Chrome started. Log in to Indeed/Glassdoor in that window, then run:"
Write-Host "  python scripts/login_job_boards.py --site indeed,glassdoor"
Write-Host "  python scripts/verify_browser_session.py --site indeed,glassdoor"
