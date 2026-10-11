$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$user=[Security.Principal.WindowsIdentity]::GetCurrent().Name
$shell=Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$principal=New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
$settings=New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 15) -ExecutionTimeLimit (New-TimeSpan -Minutes 25) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
foreach($job in @(@{Name='Asia Docker Startup';Script='ops/start-docker.ps1';Daily=$false},@{Name='Asia Docker Backup';Script='ops/run-docker-backup.ps1';Daily=$true})) {
    $script=Join-Path $root $job.Script
    $action=New-ScheduledTaskAction -Execute $shell -Argument ('-NoLogo -NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "'+$script+'"') -WorkingDirectory $root
    $triggers=@(New-ScheduledTaskTrigger -AtLogOn -User $user)
    if($job.Daily) {$triggers+=New-ScheduledTaskTrigger -Daily -At '03:30'}
    $existing=Get-ScheduledTask -TaskName $job.Name -ErrorAction SilentlyContinue
    if($existing -and !$existing.Actions.Arguments.Contains($script)) {throw ('Unrelated task already exists: '+$job.Name)}
    Register-ScheduledTask -TaskName $job.Name -Action $action -Trigger $triggers -Principal $principal -Settings $settings -Force | Out-Null
    Write-Output ($job.Name+' registered for the current user.')
}
