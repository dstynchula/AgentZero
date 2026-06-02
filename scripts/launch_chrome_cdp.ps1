# Start Google Chrome with remote debugging (CDP) on a DEDICATED profile.
#
# Chrome 136+ refuses --remote-debugging-port on the default user-data-dir.
# Log into Indeed/Glassdoor once in the launched window; sessions persist in the profile dir.
#
# Usage:
#   .\scripts\launch_chrome_cdp.ps1
#   .\scripts\launch_chrome_cdp.ps1 -Port 9223
#   .\scripts\launch_chrome_cdp.ps1 -UserDataDir "C:\path\to\profile"
#
# macOS / Linux: python scripts/launch_chrome_cdp.py  or  ./scripts/launch_chrome_cdp.sh

param(
    [int]$Port = 9222,
    [string]$UserDataDir = ""
)

$repoRoot = Split-Path -Parent $PSScriptRoot
$py = Join-Path $repoRoot "scripts\launch_chrome_cdp.py"
if (-not (Test-Path $py)) {
    Write-Error "Missing $py"
    exit 1
}

$args = @("--port", "$Port")
if ($UserDataDir) {
    $args += @("--user-data-dir", $UserDataDir)
}

& python $py @args
exit $LASTEXITCODE
