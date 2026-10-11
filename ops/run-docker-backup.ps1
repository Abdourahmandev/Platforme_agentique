param([switch]$Force)
$ErrorActionPreference='Stop'
$state=Join-Path $env:LOCALAPPDATA 'AsiaDocker'
# Share the Windows backup lock: the two jobs must not snapshot concurrently.
$backupState=Join-Path $env:LOCALAPPDATA 'AsiaBackup'
try {$lock=[IO.File]::Open((Join-Path $backupState 'backup.lock'),'OpenOrCreate','ReadWrite','None')} catch {exit 0}
try {
    $lastFile=Join-Path $state 'scheduled-backup-result.json'
    if(!$Force -and (Test-Path -LiteralPath $lastFile)) {
        $last=Get-Content -LiteralPath $lastFile -Raw | ConvertFrom-Json
        if($last.passed -and ([DateTimeOffset]::UtcNow-[DateTimeOffset]::Parse($last.completed_at)).TotalHours -lt 23) {exit 0}
    }
    $python=Join-Path $env:LOCALAPPDATA 'Programs\AsiaLiteLLM\venv\Scripts\python.exe'
    $process=Start-Process -FilePath $python -ArgumentList @(('"'+(Join-Path $PSScriptRoot 'backup-docker.py')+'"')) -WindowStyle Hidden -Wait -PassThru -RedirectStandardOutput (Join-Path $state 'scheduled-backup.stdout.log') -RedirectStandardError (Join-Path $state 'scheduled-backup.stderr.log')
    if($process.ExitCode -ne 0) {throw 'Docker backup failed.'}
    @{completed_at=[DateTimeOffset]::UtcNow.ToString('o');passed=$true} | ConvertTo-Json | Set-Content -LiteralPath $lastFile
} catch {
    @{completed_at=[DateTimeOffset]::UtcNow.ToString('o');passed=$false;error_type=$_.Exception.GetType().Name} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $state 'scheduled-backup-result.json')
    exit 1
} finally {$lock.Dispose()}
