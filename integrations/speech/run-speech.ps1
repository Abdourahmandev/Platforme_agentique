$ErrorActionPreference='Stop'
$root=Join-Path $env:LOCALAPPDATA 'Programs\OpenCodeTelegramSpeech'
$state=Join-Path $env:LOCALAPPDATA 'OpenCodeTelegramSetup'
try { $lock=[IO.File]::Open((Join-Path $state 'speech-supervisor.lock'),[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None) } catch { exit 0 }
try {
 $env:TELEGRAM_STT_SECRET=[IO.File]::ReadAllText((Join-Path $state 'speech-secret.txt')).Trim()
 $env:HF_HUB_DISABLE_TELEMETRY='1'
 $env:HF_HUB_OFFLINE='1'
 $env:PYTHONUNBUFFERED='1'
 while($true) {
  $process=Start-Process -FilePath (Join-Path $root 'venv\Scripts\python.exe') -ArgumentList @(('"'+(Join-Path $root 'speech_server.py')+'"')) -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput (Join-Path $state 'speech.stdout.log') -RedirectStandardError (Join-Path $state 'speech.stderr.log') -PassThru
  @{SupervisorPID=$PID;ServerPID=$process.Id;StartedAt=(Get-Date).ToString('o')} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $state 'speech-runtime.json')
  $process.WaitForExit()
  Start-Sleep -Seconds 10
 }
} finally { $lock.Dispose() }
