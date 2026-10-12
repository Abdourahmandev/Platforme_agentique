$ErrorActionPreference='Stop'
$runtime=Join-Path $env:LOCALAPPDATA 'AsiaPaperclip'
if (!(Test-Path -LiteralPath (Join-Path $runtime 'paperclip.env'))) {throw 'Paperclip runtime absent.'}
$env:ASIA_PAPERCLIP_DIR=$runtime.Replace('\','/')
& 'C:\Program Files\Docker\Docker\resources\bin\docker.exe' compose -f (Join-Path $PSScriptRoot 'compose.yaml') @args
exit $LASTEXITCODE
