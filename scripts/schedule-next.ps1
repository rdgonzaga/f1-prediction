# Runs `f1pred next --publish` every hour in the background. -Remove takes it off again.
param([switch]$Remove)

$name = "f1pred next"
if ($Remove) {
    Unregister-ScheduledTask -TaskName $name -Confirm:$false
    Write-Output "Removed the '$name' task."
    return
}

$root = Split-Path $PSScriptRoot -Parent
$python = Join-Path $root ".venv\Scripts\pythonw.exe"
$log = Join-Path $root "data\next.log"
if (-not (Test-Path $python)) { throw "No $python; set up the .venv first." }

$action = New-ScheduledTaskAction -Execute $python -Argument "-m f1pred next --publish --log `"$log`"" -WorkingDirectory $root
$start = (Get-Date).Date.AddHours((Get-Date).Hour + 1)
$trigger = New-ScheduledTaskTrigger -Once -At $start -RepetitionInterval (New-TimeSpan -Hours 1)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Settings $settings -Force `
    -Description "Predicts after quali and scores after the race, then pushes site/. Log: $log" | Out-Null
Write-Output "Scheduled '$name' hourly from $($start.ToString('HH:mm')). Log: $log"
