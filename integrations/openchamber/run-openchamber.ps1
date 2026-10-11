$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
$appDir=Join-Path $env:LOCALAPPDATA 'Programs\OpenChamber'
$stateDir=Join-Path $env:LOCALAPPDATA 'OpenChamberWeb'
$nodeDir=Join-Path $appDir 'node-v24.21.0-win-x64'
$node=Join-Path $nodeDir 'node.exe'
$cli=Join-Path $appDir 'node_modules\@openchamber\web\bin\cli.js'
$projectDir=Join-Path $env:USERPROFILE 'Documents\OpenCode'
$lockPath=Join-Path $stateDir 'supervisor.lock'
try { $lock=[IO.File]::Open($lockPath,[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None) } catch { exit 0 }
try {
 $env:PATH=$nodeDir+';'+$env:LOCALAPPDATA+'\Programs\OpenCode;'+$env:PATH
 $env:OPENCODE_BINARY=Join-Path $env:LOCALAPPDATA 'Programs\OpenCode\opencode.exe'
 $env:OPENCODE_HOST='http://127.0.0.1:4096'
 $env:OPENCODE_SKIP_START='true'
 $env:OPENCHAMBER_OPENCODE_CWD=$projectDir
 $env:OPENCHAMBER_RELAY_HOST='off'
 while($true) {
  $credentials=Get-Content -LiteralPath (Join-Path $env:LOCALAPPDATA 'OpenCodeWeb\server-secret.json') -Raw | ConvertFrom-Json
  $env:OPENCODE_SERVER_USERNAME=$credentials.username
  $env:OPENCODE_SERVER_PASSWORD=$credentials.password
  $env:OPENCHAMBER_UI_PASSWORD=$credentials.password
  $process=Start-Process -FilePath $node -ArgumentList @(('"'+$cli+'"'),'serve','--host','127.0.0.1','--port','3000','--foreground') -WorkingDirectory $projectDir -WindowStyle Hidden -RedirectStandardOutput (Join-Path $stateDir 'server.stdout.log') -RedirectStandardError (Join-Path $stateDir 'server.stderr.log') -PassThru
  @{SupervisorPID=$PID;ServerPID=$process.Id;StartedAt=(Get-Date).ToString('o')} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $stateDir 'runtime.json')
  $process.WaitForExit()
  Start-Sleep -Seconds 10
 }
} finally {if($lock){$lock.Dispose()}}
