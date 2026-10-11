$ErrorActionPreference='Stop'
$root=Join-Path $env:LOCALAPPDATA 'Programs\OpenCodeTelegram'
$state=Join-Path $env:LOCALAPPDATA 'OpenCodeTelegramSetup'
$nodeDir=Join-Path $env:LOCALAPPDATA 'Programs\OpenChamber\node-v24.21.0-win-x64'
$projectDir=Join-Path $env:USERPROFILE 'Documents\OpenCode'
try { $lock=[IO.File]::Open((Join-Path $state 'bot-supervisor.lock'),[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None) } catch { exit 0 }
try {
 $env:PATH=$nodeDir+';'+$env:LOCALAPPDATA+'\Programs\OpenCode;'+$env:PATH
 $env:OPENCODE_TELEGRAM_HOME=Join-Path $env:APPDATA 'opencode-telegram-bot'
 $env:OPENCODE_SERVER_VERSION='v1'
 $env:OPENCODE_API_URL='http://127.0.0.1:4096'
 $env:OPENCODE_AUTO_RESTART_ENABLED='false'
 $env:OPENCODE_MODEL_PROVIDER='litellm'
 $env:OPENCODE_MODEL_ID='asia-auto'
 $env:BOT_LOCALE='en'
 $env:LOG_LEVEL='warn'
 $env:TRACK_BACKGROUND_SESSIONS='false'
 $env:STT_API_URL='http://127.0.0.1:4123/v1'
 $env:STT_API_KEY=[IO.File]::ReadAllText((Join-Path $state 'speech-secret.txt')).Trim()
 $env:STT_MODEL='base'
 $env:STT_NOTE_PROMPT='The following message was transcribed from speech and may contain transcription errors. Respond naturally and concisely in the language the user speaks.'
 $env:TTS_PROVIDER='edge'
 $env:TTS_VOICE='en-US-EmmaMultilingualNeural'
 while($true) {
  $credentials=Get-Content -LiteralPath (Join-Path $state 'bot-credentials.json') -Raw | ConvertFrom-Json
  $opencode=Get-Content -LiteralPath (Join-Path $env:LOCALAPPDATA 'OpenCodeWeb\server-secret.json') -Raw | ConvertFrom-Json
  $env:TELEGRAM_BOT_TOKEN=$credentials.Token
  $env:TELEGRAM_ALLOWED_USER_ID=[string]$credentials.AllowedUserId
  $env:OPENCODE_SERVER_USERNAME=$opencode.username
  $env:OPENCODE_SERVER_PASSWORD=$opencode.password
  $process=Start-Process -FilePath (Join-Path $nodeDir 'node.exe') -ArgumentList @(('"'+(Join-Path $root 'node_modules\@grinev\opencode-telegram-bot\dist\cli.js')+'"'),'start','--mode','installed') -WorkingDirectory $projectDir -WindowStyle Hidden -RedirectStandardOutput (Join-Path $state 'bot.stdout.log') -RedirectStandardError (Join-Path $state 'bot.stderr.log') -PassThru
  @{SupervisorPID=$PID;BotPID=$process.Id;StartedAt=(Get-Date).ToString('o')} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $state 'bot-runtime.json')
  $process.WaitForExit()
  Start-Sleep -Seconds 10
 }
} finally { $lock.Dispose() }
