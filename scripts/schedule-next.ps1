# Runs `f1pred next --publish --notify` hourly on Sat, Sun and Mon (Manila race weekends; Americas races end Monday). -Remove takes it off again.
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

$action = New-ScheduledTaskAction -Execute $python -Argument "-m f1pred next --publish --notify --log `"$log`"" -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Saturday, Sunday, Monday -At 00:00
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At 00:00 -RepetitionInterval (New-TimeSpan -Hours 1) `
    -RepetitionDuration (New-TimeSpan -Days 1)).Repetition
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Settings $settings -Force `
    -Description "Predicts after quali and scores after the race, then pushes site/. Log: $log" | Out-Null
Write-Output "Scheduled '$name' hourly on Sat, Sun and Mon. Log: $log"
