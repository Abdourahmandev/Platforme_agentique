# Copy the current bot credential into the private migration runtime.
# This performs read-only Telegram checks; it never starts a second consumer.
$ErrorActionPreference='Stop'
$runtime=Join-Path $env:LOCALAPPDATA 'AsiaDocker'
if (-not (Test-Path -LiteralPath (Join-Path $runtime 'runtime-private.json'))) {
    throw 'Initialiser le runtime Docker avant de preparer le token Asia.'
}
$source=Join-Path $env:LOCALAPPDATA 'OpenCodeTelegramSetup\bot-credentials.json'
$credentials=Get-Content -LiteralPath $source -Raw | ConvertFrom-Json
$folder=Join-Path $runtime 'secrets'
$destination=Join-Path $folder 'asia.token'
try {
    $token=[string]$credentials.Token
    if ($token -notmatch '^\d+:[A-Za-z0-9_-]+$') { throw 'Format du token actuel invalide.' }
    try {
        $bot=Invoke-RestMethod -Uri ('https://api.telegram.org/bot'+$token+'/getMe') -TimeoutSec 20
    } catch { throw 'Impossible de valider le bot actuel aupres de Telegram. Aucun changement applique.' }
    if (-not $bot.ok -or -not $bot.result.is_bot) { throw 'Le token ne correspond pas a un bot valide.' }
    New-Item -ItemType Directory -Force -Path $folder | Out-Null
    $identity=[Security.Principal.WindowsIdentity]::GetCurrent().Name
    & icacls $folder /inheritance:r /grant:r "${identity}:(OI)(CI)F" '*S-1-5-18:(OI)(CI)F' | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Impossible de proteger le dossier des secrets.' }
    if ((Test-Path -LiteralPath $destination) -and [IO.File]::ReadAllText($destination).Trim() -ne $token) {
        throw 'Un autre token Asia est deja prepare : remplacement refuse.'
    }
    [IO.File]::WriteAllText($destination,$token,[Text.UTF8Encoding]::new($false))
    if ([IO.File]::ReadAllText($destination) -ne $token) { throw 'Verification de copie du token echouee.' }
    Write-Output ('Reprise preparee pour @'+$bot.result.username+'. Le consommateur actuel reste inchange.')
} finally {
    $token=$null
    $credentials=$null
}
