$ErrorActionPreference = 'Stop'
$appDirectory = $PSScriptRoot
$stateDirectory = Join-Path $env:LOCALAPPDATA 'AsiaAgent'
New-Item -ItemType Directory -Path $stateDirectory -Force | Out-Null
try {
    $lock = [System.IO.File]::Open((Join-Path $stateDirectory 'supervisor.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
} catch { exit 0 }
$nodeBinary = (Get-Command node.exe -ErrorAction Stop).Source
$env:ASIA_CONFIG = Join-Path $appDirectory 'config.local.json'
$stdout = Join-Path $stateDirectory 'server.stdout.log'
$stderr = Join-Path $stateDirectory 'server.stderr.log'
try {
    while ($true) {
        $listener = Get-NetTCPConnection -LocalPort 3210 -State Listen -ErrorAction SilentlyContinue
        if ($listener) { Start-Sleep -Seconds 15; continue }
        $child = Start-Process -FilePath $nodeBinary -ArgumentList @('server.mjs') -WorkingDirectory $appDirectory -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
        @{ SupervisorPID=$PID; ServerPID=$child.Id; AppDirectory=$appDirectory; StartedAt=(Get-Date).ToString('o') } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $stateDirectory 'runtime.json')
        $child.WaitForExit()
        Start-Sleep -Seconds 5
    }
} finally { $lock.Dispose() }
