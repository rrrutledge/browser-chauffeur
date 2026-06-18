# install-schedule.ps1 — register (or remove) the ~5-min Scheduled Task that runs the keeper.
#
# This is the ONLY PowerShell in the keeper, and you run it BY HAND once (not from a Claude session),
# after the manual tryout is trusted. It registers a Windows Scheduled Task that runs the Python
# poller every N minutes; the poller is itself presence-gated, so idle/locked cycles are cheap no-ops.
#
#   powershell -File install-schedule.ps1 -RepoDir C:/Users/russe/Dev/personal-ai-pod [-IntervalMinutes 5]
#   powershell -File install-schedule.ps1 -RepoDir C:/Users/russe/Dev/personal-ai-pod -Remove
#
# Runs in your interactive desktop session (LogonType Interactive) so presence detection and the
# spawned worker tabs work.

param(
    [Parameter(Mandatory = $true)][string]$RepoDir,
    [int]$IntervalMinutes = 5,
    [switch]$Remove
)

$TaskName = 'DrainerKeeper'

if ($Remove) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "Removed scheduled task '$TaskName'."
    return
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$poller = Join-Path $scriptDir 'run-poller.py'

$action = New-ScheduledTaskAction -Execute 'python' `
    -Argument "`"$poller`" --repo `"$RepoDir`""

$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes)

$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
    -Description "Drainer continuous keeper — one presence-gated poller cycle every $IntervalMinutes min." `
    -Force | Out-Null

Write-Host "Registered '$TaskName': python run-poller.py --repo $RepoDir every $IntervalMinutes min."
Write-Host "Remove with:  powershell -File install-schedule.ps1 -RepoDir `"$RepoDir`" -Remove"
