# A plain script preserves Docker flags such as -d (otherwise PowerShell can
# consume -d as the common -Debug parameter before forwarding the arguments).
$ErrorActionPreference='Stop'
$runtime=Join-Path $env:LOCALAPPDATA 'AsiaDocker'
if (-not (Test-Path -LiteralPath (Join-Path $runtime 'litellm.env'))) {
    throw 'Runtime absent. Suivre documentation/migration.md avant de demarrer.'
}
$env:ASIA_RUNTIME_DIR=$runtime.Replace('\','/')
& 'C:\Program Files\Docker\Docker\resources\bin\docker.exe' compose -f (Join-Path $PSScriptRoot 'compose.yaml') @args
exit $LASTEXITCODE
