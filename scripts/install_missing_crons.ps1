Set-Location C:\projet\V9
$V9Root = "C:\projet\V9"
$Python = "$V9Root\.venv\Scripts\python.exe"

# V9_AutoCalibrator (quotidien 03:00)
$tr = "`"$Python`" $V9Root\scripts\v9_auto_calibrator.py --once"
schtasks /create /tn V9_AutoCalibrator /tr "$tr" /sc daily /st 03:00 /rl highest /f
if ($LASTEXITCODE -eq 0) { Write-Host "[OK] V9_AutoCalibrator installe" } else { Write-Host "[FAIL] V9_AutoCalibrator" }

# V9_TelegramAgent (au login)
$tr2 = "`"$Python`" $V9Root\scripts\v9_telegram_notifier.py --watch"
schtasks /create /tn V9_TelegramAgent /tr "$tr2" /sc onlogon /rl highest /f
if ($LASTEXITCODE -eq 0) { Write-Host "[OK] V9_TelegramAgent installe" } else { Write-Host "[FAIL] V9_TelegramAgent" }

# Verification
Write-Host "`nCrons V9 apres installation :"
Get-ScheduledTask | Where-Object { $_.TaskName -match 'V9_' } | Select-Object TaskName, State | Format-Table -AutoSize
