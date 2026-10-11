$ErrorActionPreference = 'Stop'
$stateDirectory = Join-Path $env:LOCALAPPDATA 'AsiaLiteLLM'
New-Item -ItemType Directory -Path $stateDirectory -Force | Out-Null
try { $lock = [IO.File]::Open((Join-Path $stateDirectory 'supervisor.lock'), 'OpenOrCreate', 'ReadWrite', 'None') } catch { exit 0 }
$python = Join-Path $env:LOCALAPPDATA 'Programs\AsiaLiteLLM\venv\Scripts\python.exe'
try {
    while ($true) {
        if (Get-NetTCPConnection -LocalPort 4000 -State Listen -ErrorAction SilentlyContinue) { Start-Sleep -Seconds 15; continue }
        $child = Start-Process -FilePath $python -ArgumentList @('-u', 'run.py') -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $stateDirectory 'stdout.log') -RedirectStandardError (Join-Path $stateDirectory 'stderr.log') -PassThru
        @{ SupervisorPID=$PID; ServerPID=$child.Id; StartedAt=(Get-Date).ToString('o') } | ConvertTo-Json | Set-Content (Join-Path $stateDirectory 'runtime.json')
        $child.WaitForExit()
        Start-Sleep -Seconds 10
    }
} finally { $lock.Dispose() }
