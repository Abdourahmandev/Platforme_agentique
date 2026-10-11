param([switch]$Force)
$ErrorActionPreference='Stop'
$stateDirectory=Join-Path $env:LOCALAPPDATA 'AsiaBackup'
New-Item -ItemType Directory -Force -Path $stateDirectory | Out-Null
try {$backupLock=[IO.File]::Open((Join-Path $stateDirectory 'backup.lock'),'OpenOrCreate','ReadWrite','None')} catch {exit 0}
try {
    $lastFile=Join-Path $stateDirectory 'last-backup.json'
    if (!$Force -and (Test-Path -LiteralPath $lastFile)) {
        $last=Get-Content -LiteralPath $lastFile -Raw | ConvertFrom-Json
        if (([DateTimeOffset]::UtcNow-[DateTimeOffset]::Parse($last.completed_at)).TotalHours -lt 23) {exit 0}
    }
    $python=Join-Path $env:LOCALAPPDATA 'Programs\AsiaLiteLLM\venv\Scripts\python.exe'
    & $python (Join-Path $PSScriptRoot 'backup.py') 1> (Join-Path $stateDirectory 'backup.stdout.log') 2> (Join-Path $stateDirectory 'backup.stderr.log')
    if ($LASTEXITCODE -ne 0) {throw 'La sauvegarde a échoué. Voir AsiaBackup/backup.stderr.log.'}
} finally {$backupLock.Dispose()}
