# Begin Telegram companions
$telegramState=Join-Path $env:LOCALAPPDATA 'OpenCodeTelegramSetup'
foreach($telegramCompanion in @(@{Name='speech';Path=(Join-Path $env:LOCALAPPDATA 'Programs\OpenCodeTelegramSpeech\run-speech.ps1')},@{Name='bot';Path=(Join-Path $env:LOCALAPPDATA 'Programs\OpenCodeTelegram\run-bot.ps1')})) {
 if ((Test-Path -LiteralPath $telegramCompanion.Path) -and (Test-Path -LiteralPath (Join-Path $telegramState 'bot-credentials.json'))) {
  try {
   Start-Process -FilePath 'powershell.exe' -ArgumentList @('-NoLogo','-NoProfile','-ExecutionPolicy','Bypass','-File',('"'+$telegramCompanion.Path+'"')) -WindowStyle Hidden -RedirectStandardOutput (Join-Path $telegramState ($telegramCompanion.Name+'-supervisor.stdout.log')) -RedirectStandardError (Join-Path $telegramState ($telegramCompanion.Name+'-supervisor.stderr.log')) | Out-Null
  } catch { Write-Warning ('Telegram companion could not start: '+$telegramCompanion.Name) }
 }
}
# End Telegram companions

# Start OpenChamber companion at computer startup
$chamberDir = Join-Path $env:LOCALAPPDATA 'OpenChamberWeb'
$chamberRunner = Join-Path $chamberDir 'run-openchamber.ps1'
Start-Process -FilePath "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -ArgumentList @('-NoLogo','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',('"'+$chamberRunner+'"')) -WindowStyle Hidden -RedirectStandardOutput (Join-Path $chamberDir 'supervisor.stdout.log') -RedirectStandardError (Join-Path $chamberDir 'supervisor.stderr.log')
$ErrorActionPreference = 'Stop'
$serviceDir = Join-Path $env:LOCALAPPDATA 'OpenCodeWeb'
$credentials = Get-Content -LiteralPath (Join-Path $serviceDir 'server-secret.json') -Raw | ConvertFrom-Json
$env:OPENCODE_SERVER_USERNAME = $credentials.username
$env:OPENCODE_SERVER_PASSWORD = $credentials.password
$exePath = Join-Path $env:LOCALAPPDATA 'Programs\OpenCode\opencode.exe'
$projectDir = Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'OpenCode'
$process = Start-Process -FilePath $exePath -ArgumentList @('serve','--hostname','127.0.0.1','--port','4096') -WorkingDirectory $projectDir -WindowStyle Hidden -RedirectStandardOutput (Join-Path $serviceDir 'server.stdout.log') -RedirectStandardError (Join-Path $serviceDir 'server.stderr.log') -PassThru -Wait
exit $process.ExitCode