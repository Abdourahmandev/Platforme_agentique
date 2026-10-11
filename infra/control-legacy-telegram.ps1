param([ValidateSet('Check','Pause','Resume')][string]$Mode='Check')
$ErrorActionPreference='Stop'
$state=Join-Path $env:LOCALAPPDATA 'OpenCodeTelegramSetup'
$runner=Join-Path $env:LOCALAPPDATA 'Programs\OpenCodeTelegram\run-bot.ps1'
$cli=Join-Path $env:LOCALAPPDATA 'Programs\OpenCodeTelegram\node_modules\@grinev\opencode-telegram-bot\dist\cli.js'
$marker=Join-Path $state 'migration-paused'
$runtime=Get-Content -LiteralPath (Join-Path $state 'bot-runtime.json') -Raw | ConvertFrom-Json
$supervisor=Get-CimInstance Win32_Process -Filter ("ProcessId = "+[int]$runtime.SupervisorPID)
$bot=Get-CimInstance Win32_Process -Filter ("ProcessId = "+[int]$runtime.BotPID)
$isAdmin=([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if($Mode -eq 'Check') {
    [pscustomobject]@{Paused=(Test-Path -LiteralPath $marker);SupervisorRunning=($null -ne $supervisor);BotRunning=($null -ne $bot);Administrator=$isAdmin} | ConvertTo-Json
    exit 0
}
if($Mode -eq 'Pause') {
    # Check identity before changing anything. Never kill an unrelated reused PID.
    if($supervisor -and (!$supervisor.CommandLine -or !$supervisor.CommandLine.Contains($runner))) {throw 'Cannot verify supervisor identity. Run this script in administrator PowerShell.'}
    if($bot -and (!$bot.CommandLine -or !$bot.CommandLine.Contains($cli) -or $bot.ParentProcessId -ne $runtime.SupervisorPID)) {throw 'Cannot verify bot identity. Run this script in administrator PowerShell.'}
    $auth=Get-Content -LiteralPath (Join-Path $env:LOCALAPPDATA 'OpenCodeWeb/server-secret.json') -Raw | ConvertFrom-Json
    $basic=[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($auth.username+':'+$auth.password))
    $active=Invoke-RestMethod -Uri 'http://127.0.0.1:4096/session/status' -Headers @{Authorization=('Basic '+$basic)} -TimeoutSec 15
    if(@($active.PSObject.Properties).Count -gt 0) {throw 'OpenCode has active tasks. Wait for completion before pausing Telegram.'}
    $source=[IO.File]::ReadAllText($runner)
    if(!$source.Contains('Asia migration pause guard')) {
        if(!$source.Contains('while($true) {')) {throw 'Unexpected launcher; no automatic modification performed.'}
        $copy=Join-Path $state ('run-bot.before-migration-'+(Get-Date -Format 'yyyyMMddHHmmss')+'.ps1')
        [IO.File]::WriteAllText($copy,$source)
        $guard='# Asia migration pause guard'+[Environment]::NewLine+'if (Test-Path -LiteralPath (Join-Path $env:LOCALAPPDATA ''OpenCodeTelegramSetup\migration-paused'')) { exit 0 }'+[Environment]::NewLine
        $source=$guard+$source.Replace('while($true) {','while($true) {'+[Environment]::NewLine+'  if (Test-Path -LiteralPath (Join-Path $state ''migration-paused'')) { break }')
        [IO.File]::WriteAllText($runner,$source)
    }
    [IO.File]::WriteAllText($marker,[DateTimeOffset]::UtcNow.ToString('o'))
    # Stop the supervisor first so it cannot recreate the consumer.
    if($supervisor) {Stop-Process -Id $supervisor.ProcessId -Force -ErrorAction Stop}
    if($bot) {Stop-Process -Id $bot.ProcessId -Force -ErrorAction Stop}
    Start-Sleep -Seconds 3
    $remaining=Get-CimInstance Win32_Process | Where-Object {$_.CommandLine -and ($_.CommandLine.Contains($runner) -or $_.CommandLine.Contains($cli))}
    if($remaining) {throw 'A legacy Telegram process is still running. Do not activate OpenClaw Asia.'}
    $probe=[IO.File]::Open((Join-Path $state 'bot-supervisor.lock'),'OpenOrCreate','ReadWrite','None')
    $probe.Dispose()
    [pscustomobject]@{LegacyTelegramStopped=$true;AutomaticRelaunchBlocked=$true;OpenCodeServerUnchanged=$true}|ConvertTo-Json
    exit 0
}
# A rollback must prove that the new consumer is disabled or stopped first.
$docker='C:\Program Files\Docker\Docker\resources\bin\docker.exe'
$running=& $docker inspect --format '{{.State.Running}}' asia-platform-staging-openclaw-1 2>$null
if($LASTEXITCODE -ne 0) {throw 'Cannot prove the OpenClaw consumer is stopped; refusing duplicate Telegram polling.'}
if($running.Trim() -eq 'true') {
    $enabled=& $docker exec asia-platform-staging-openclaw-1 node -e 'const c=JSON.parse(require("fs").readFileSync("/home/node/.openclaw/openclaw.json"));process.stdout.write(String(c.channels?.telegram?.enabled!==false && c.channels?.telegram?.accounts?.asia?.enabled===true))' 2>$null
    if($LASTEXITCODE -ne 0 -or $enabled.Trim() -ne 'false') {throw 'Disable OpenClaw Asia and verify its channel has stopped before resuming the legacy bot.'}
    # A disabled config alone is insufficient if its hot reload failed.
    throw 'For a rollback, stop the OpenClaw container first; this proves there is no live Asia consumer.'
}
if(Test-Path -LiteralPath $marker) {Remove-Item -LiteralPath $marker}
Start-Process -FilePath 'powershell.exe' -ArgumentList @('-NoLogo','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',('"'+$runner+'"')) -WindowStyle Hidden | Out-Null
$deadline=[DateTimeOffset]::UtcNow.AddSeconds(20)
do {
    Start-Sleep -Seconds 2
    $resumed=Get-Content -LiteralPath (Join-Path $state 'bot-runtime.json') -Raw | ConvertFrom-Json
    $parent=Get-CimInstance Win32_Process -Filter ('ProcessId = '+[int]$resumed.SupervisorPID)
    $child=Get-CimInstance Win32_Process -Filter ('ProcessId = '+[int]$resumed.BotPID)
    if($parent.CommandLine -and $child.CommandLine -and $parent.CommandLine.Contains($runner) -and $child.CommandLine.Contains($cli) -and $child.ParentProcessId -eq $parent.ProcessId) {
        Write-Output 'Legacy supervisor and bot processes restarted. Owner Telegram response still needs verification.'
        exit 0
    }
} until([DateTimeOffset]::UtcNow -ge $deadline)
throw 'Legacy process restart was not verified. OpenClaw must remain stopped.'
