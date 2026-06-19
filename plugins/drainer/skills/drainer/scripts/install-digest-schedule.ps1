# install-digest-schedule.ps1 - register (or remove) the once-a-day Scheduled Task that opens the
# interactive drainer digest tab.
#
# Run this BY HAND once (not from a Claude session), after the manual digest tryout is trusted. It
# registers a Windows Scheduled Task that runs run-digest.py once a day at a fixed time; run-digest.py
# opens ONE visible Claude tab that empties the fyi/junk queue and re-surfaces stale needs-you items,
# with Russell reviewing before anything is cleared.
#
#   powershell -File install-digest-schedule.ps1 -RepoDir C:/Users/russe/Dev/personal-ai-pod [-At 17:00]
#   powershell -File install-digest-schedule.ps1 -RepoDir C:/Users/russe/Dev/personal-ai-pod -Remove
#
# Runs in the interactive desktop session (LogonType Interactive) so the spawned digest tab appears.
# ASCII-only: Windows PowerShell 5.1 misparses UTF-8 punctuation (em-dashes, curly quotes).

param(
    [Parameter(Mandatory = $true)][string]$RepoDir,
    [string]$At = '17:00',
    [switch]$Remove
)

$TaskName = 'DrainerDigest'

if ($Remove) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "Removed scheduled task '$TaskName'."
    return
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$digest = Join-Path $scriptDir 'run-digest.py'

$action = New-ScheduledTaskAction -Execute 'python' `
    -Argument ('"' + $digest + '" --repo "' + $RepoDir + '"')

$trigger = New-ScheduledTaskTrigger -Daily -At $At

$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -MultipleInstances IgnoreNew

# Interactive desktop session - required so the spawned digest tab (wt.exe new-tab) appears on screen.
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
    -Principal $principal `
    -Description "Drainer EOD digest - opens one interactive digest tab once a day at $At." `
    -Force | Out-Null

Write-Host "Registered '$TaskName': python run-digest.py --repo $RepoDir daily at $At."
Write-Host "Remove with:  install-digest-schedule.ps1 -RepoDir $RepoDir -Remove"
