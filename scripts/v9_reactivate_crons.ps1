# v9_reactivate_crons.ps1
# Réactivation idempotente des 7 crons V9 gelés après audit DB P0-P2.
# Motion CEO 2026-07-18 15h15 UTC (cf DECISIONS_LOG.md).

param(
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$repo_root = Split-Path -Parent $PSScriptRoot
Set-Location $repo_root

# 7 crons à réactiver (motion CEO)
$CRONS_TO_ENABLE = @(
    "V9_CalibrationLoop",
    "V9_MetaAgentScan",
    "V9_ResolveLoop",
    "V9_PaperTradeLoop",
    "V9_StrategyPoleRecompute",
    "V9_HeartbeatCheck",
    "V9_AutoRestart"
)

function Write-Section($title) {
    Write-Host ""
    Write-Host "=== $title ==="
}

function Test-CronExists($name) {
    $output = schtasks /Query /TN $name 2>&1
    return ($LASTEXITCODE -eq 0)
}

function Get-CronState($name) {
    $output = schtasks /Query /TN $name /FO LIST /V 2>&1
    if ($LASTEXITCODE -ne 0) { return "Unknown" }
    if ($output -match "Disabled") { return "Disabled" }
    if ($output -match "Running") { return "Running" }
    if ($output -match "Ready") { return "Ready" }
    return "Unknown"
}

function Enable-Cron($name) {
    if ($DryRun) {
        Write-Host "  [DRY-RUN] Would enable: $name"
        return
    }
    schtasks /Change /ENABLE /TN $name 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to enable cron: $name (exit $LASTEXITCODE)"
    }
    Write-Host "  Enabled: $name"
}

# Phase 1 : Pré-vérifications
Write-Section "Phase 1 : Pré-vérifications"

Write-Host "Vérification motion CEO dans DECISIONS_LOG.md..."
$decisions_log = Join-Path $repo_root "workspace/perplexity/memory/DECISIONS_LOG.md"
if (-not (Test-Path $decisions_log)) {
    throw "DECISIONS_LOG.md introuvable"
}
$motion_found = Select-String -Path $decisions_log -Pattern "Motion CEO.*audit.*Option B" -Quiet
if (-not $motion_found) {
    throw "Motion CEO 'audit Option B + réactivation 21h UTC' NON trouvée. R28 strict."
}
Write-Host "  Motion CEO trouvee"

Write-Host "Vérification port 31685..."
$port_check = netstat -ano | Select-String ":31685"
if ($port_check) {
    Write-Host "  Port 31685 occupe : $port_check"
} else {
    Write-Host "  Port 31685 libre"
}

# Phase 2 : État actuel
Write-Section "Phase 2 : Etat actuel des 7 crons"

$crons_state = @{}
foreach ($cron in $CRONS_TO_ENABLE) {
    if (-not (Test-CronExists $cron)) {
        Write-Host "  $cron : N'EXISTE PAS"
        continue
    }
    $state = Get-CronState $cron
    $crons_state[$cron] = $state
    Write-Host "  $cron : $state"
}

# Phase 3 : Réactivation
Write-Section "Phase 3 : Réactivation"

$enabled_count = 0
$already_enabled_count = 0
$failed_count = 0

foreach ($cron in $CRONS_TO_ENABLE) {
    if (-not $crons_state.ContainsKey($cron)) {
        $failed_count++
        continue
    }
    $state = $crons_state[$cron]
    if ($state -eq "Ready" -or $state -eq "Running") {
        Write-Host "  Already enabled: $cron"
        $already_enabled_count++
    } elseif ($state -eq "Disabled") {
        try {
            Enable-Cron $cron
            $enabled_count++
        } catch {
            Write-Host "  Failed: $cron - $_"
            $failed_count++
        }
    } else {
        Write-Host "  Unknown state for $cron : $state"
        $failed_count++
    }
}

# Phase 4 : Vérification post
Write-Section "Phase 4 : Vérification post-réactivation"

if (-not $DryRun) {
    Start-Sleep -Seconds 2
    foreach ($cron in $CRONS_TO_ENABLE) {
        if ($crons_state.ContainsKey($cron)) {
            $new_state = Get-CronState $cron
            Write-Host "  $cron : $new_state"
        }
    }
}

# Phase 5 : Bilan
Write-Section "Bilan"

if ($DryRun) {
    Write-Host "MODE DRY-RUN : aucune modification"
    Write-Host "Pour executer : .\v9_reactivate_crons.ps1"
} else {
    Write-Host "Reactivation terminee :"
    Write-Host "  - $enabled_count crons actives"
    Write-Host "  - $already_enabled_count deja actifs"
    Write-Host "  - $failed_count echecs"
}
Write-Host ""
