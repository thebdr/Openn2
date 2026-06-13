# Run-AllTests.ps1 - rebuilds SafetyDB.xlsm and runs both pipeline tests.
#   1. validation pass: full synthetic input (every rule fires), gate blocks
#   2. export pass: clean synthetic input (no errors), files written
# Closes any stray Excel first so a hung COM instance can't hold the workbook.
param([string]$Root = (Split-Path $PSScriptRoot -Parent))
$ErrorActionPreference = 'Stop'

Get-Process EXCEL -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep 1
Remove-Item (Join-Path $Root 'Input\_staged\*'), (Join-Path $Root 'stage.log'), (Join-Path $Root 'SafetyDB.xlsm') -Force -ErrorAction SilentlyContinue

# Test scripts end with `exit`, which would terminate THIS script if called via
# `&` - so each runs in its own child PowerShell process (isolated exit codes).
$ps = (Get-Process -Id $PID).Path

Write-Output '################ VALIDATION PASS (full input) ################'
python (Join-Path $PSScriptRoot 'New-TestInputs.py') (Join-Path $Root 'TestInput')
& (Join-Path $PSScriptRoot 'Setup-SafetyDB.ps1') -TestParams | Out-Null
& $ps -NoProfile -File (Join-Path $PSScriptRoot 'Test-Pipeline.ps1')

Write-Output ''
Write-Output '################ EXPORT PASS (clean input) ################'
Get-Process EXCEL -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep 1
Remove-Item (Join-Path $Root 'Input\_staged\*'), (Join-Path $Root 'SafetyDB.xlsm') -Force -ErrorAction SilentlyContinue
python (Join-Path $PSScriptRoot 'New-TestInputs.py') (Join-Path $Root 'TestInput') clean
& (Join-Path $PSScriptRoot 'Setup-SafetyDB.ps1') -TestParams | Out-Null
& $ps -NoProfile -File (Join-Path $PSScriptRoot 'Test-Export.ps1')
