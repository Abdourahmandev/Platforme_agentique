$ErrorActionPreference='Stop'
$state=Join-Path $env:LOCALAPPDATA 'AsiaDocker'
$docker='C:\Program Files\Docker\Docker\resources\bin\docker.exe'
$desktop='C:\Program Files\Docker\Docker\Docker Desktop.exe'
try {$lock=[IO.File]::Open((Join-Path $state 'startup.lock'),'OpenOrCreate','ReadWrite','None')} catch {exit 0}
function Invoke-StartupDocker([string[]]$DockerArguments,[string]$LogName) {
    # Windows PowerShell 5 treats native stderr as RemoteException under Stop.
    # Docker writes ordinary progress to stderr, so use process exit codes.
    $process=Start-Process -FilePath $docker -ArgumentList $DockerArguments -WindowStyle Hidden -Wait -PassThru -RedirectStandardOutput (Join-Path $state ($LogName+'.stdout.log')) -RedirectStandardError (Join-Path $state ($LogName+'.stderr.log'))
    return $process.ExitCode
}
try {
    $runtime=Get-Content -LiteralPath (Join-Path $state 'runtime-private.json') -Raw | ConvertFrom-Json
    if($runtime.phase -notin @('staging','asia-pilot')) {throw 'Docker startup suspended by migration state.'}
    $journalPath=Join-Path $state 'asia-handoff-private.json'
    if(Test-Path -LiteralPath $journalPath) {
        $journal=Get-Content -LiteralPath $journalPath -Raw | ConvertFrom-Json
        if($journal.status -ne 'active') {throw 'Handoff incomplete or rolled back; operator review required.'}
    }
    $code=Invoke-StartupDocker @('info','--format','{{.ServerVersion}}') 'startup-engine'
    if($code -ne 0) {
        Start-Process -FilePath $desktop -WindowStyle Hidden | Out-Null
        $deadline=[DateTimeOffset]::UtcNow.AddMinutes(4)
        do {
            Start-Sleep -Seconds 5
            $ready=((Invoke-StartupDocker @('info','--format','{{.ServerVersion}}') 'startup-engine') -eq 0)
        } until($ready -or [DateTimeOffset]::UtcNow -ge $deadline)
        if(!$ready) {throw 'Docker engine did not become ready.'}
    }
    $env:ASIA_RUNTIME_DIR=$state.Replace('\','/')
    $compose=Join-Path $PSScriptRoot '../infra/compose.yaml'
    $code=Invoke-StartupDocker @('compose','-f',('"'+$compose+'"'),'--profile','audio','up','-d','--wait','--wait-timeout','360','postgres','litellm','openclaw','speaches','playwright') 'startup'
    if($code -ne 0) {throw 'Docker services did not become healthy.'}
    @{completed_at=[DateTimeOffset]::UtcNow.ToString('o');passed=$true} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $state 'startup-result.json')
} catch {
    @{completed_at=[DateTimeOffset]::UtcNow.ToString('o');passed=$false;error_type=$_.Exception.GetType().Name} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $state 'startup-result.json')
    exit 1
} finally {$lock.Dispose()}
