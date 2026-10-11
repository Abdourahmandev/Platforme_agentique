$ErrorActionPreference = 'Stop'
$stateDirectory = Join-Path $env:LOCALAPPDATA 'AsiaPostgreSQL'
$pgCtl = Join-Path $env:LOCALAPPDATA 'Programs\AsiaPostgreSQL\pgsql\bin\pg_ctl.exe'
$dataDirectory = Join-Path $stateDirectory 'data'
try { $lock = [IO.File]::Open((Join-Path $stateDirectory 'supervisor.lock'), 'OpenOrCreate', 'ReadWrite', 'None') } catch { exit 0 }
try {
    while ($true) {
        & $pgCtl -D $dataDirectory status *> $null
        if ($LASTEXITCODE -ne 0) {
            $process = Start-Process -FilePath $pgCtl -ArgumentList @('-D', ('"'+$dataDirectory+'"'), '-l', ('"'+(Join-Path $stateDirectory 'postgres.log')+'"'), '-w', 'start') -WindowStyle Hidden -PassThru
            $process.WaitForExit()
        }
        Start-Sleep -Seconds 15
    }
} finally { $lock.Dispose() }
