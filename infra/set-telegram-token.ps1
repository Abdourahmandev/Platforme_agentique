param([Parameter(Mandatory=$true)][ValidateSet('asia-test','developpement','recherche')][string]$Agent)
$ErrorActionPreference='Stop'
$folder=Join-Path $env:LOCALAPPDATA 'AsiaDocker\secrets'
New-Item -ItemType Directory -Force -Path $folder | Out-Null
$identity=[Security.Principal.WindowsIdentity]::GetCurrent().Name
& icacls $folder /inheritance:r /grant:r "${identity}:(OI)(CI)F" '*S-1-5-18:(OI)(CI)F' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Impossible de proteger le dossier des secrets.' }
$secure=Read-Host "Token BotFather pour $Agent (saisie masquee)" -AsSecureString
$pointer=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try {
    $token=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer).Trim()
    if ($token -notmatch '^\d+:[A-Za-z0-9_-]+$') { throw 'Format de token Telegram invalide.' }
    try { $bot=Invoke-RestMethod -Uri ('https://api.telegram.org/bot'+$token+'/getMe') -TimeoutSec 20 }
    catch { throw 'Telegram ne valide pas ce token. Le secret ne sera pas enregistre.' }
    if (-not $bot.ok) { throw 'Telegram ne valide pas ce token.' }
    [IO.File]::WriteAllText((Join-Path $folder ($Agent+'.token')),$token,[Text.UTF8Encoding]::new($false))
    Write-Output ("Token enregistre pour $Agent : @"+$bot.result.username)
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    $token=$null
    $secure.Dispose()
}
