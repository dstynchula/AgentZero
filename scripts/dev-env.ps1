# AgentZero Windows dev defaults
# Dot-source from the repo root:
#   . .\scripts\dev-env.ps1
#
# Or add to your PowerShell profile:
#   . C:\path\to\AgentZero\scripts\dev-env.ps1

$PSDefaultParameterValues['Out-File:Encoding'] = 'utf8'
$PSDefaultParameterValues['Set-Content:Encoding'] = 'utf8'

Write-Host 'AgentZero: Out-File and Set-Content default to UTF-8 for this session.'
