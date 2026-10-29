param([ValidateSet('rev1','rev3')][string]$Revision='rev3')
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
$env:IDF_TOOLS_PATH=Join-Path $root '.local/tooling/idf-tools'
$env:IDF_PATH=Join-Path $root '.local/tooling/esp-idf'
$env:IDF_COMPONENT_MANAGER='0'
$runtime=Split-Path (Get-Command python).Source
$env:PATH="$runtime;$env:PATH"
$secret=Join-Path $root '.local/lan-key.txt'
if(-not(Test-Path $secret)) {
    $bytes=New-Object byte[] 24
    $rng=[System.Security.Cryptography.RandomNumberGenerator]::Create()
    try{$rng.GetBytes($bytes)}finally{$rng.Dispose()}
    [IO.File]::WriteAllText($secret,([BitConverter]::ToString($bytes).Replace('-','').ToLowerInvariant()))
}
$key=[IO.File]::ReadAllText($secret).Trim()
if($key -notmatch '^[a-zA-Z0-9_-]{24,128}$'){throw 'Invalid local LAN key'}
$secretDefaults=Join-Path $root '.local/sdkconfig.secret.defaults'
[IO.File]::WriteAllText($secretDefaults,"CONFIG_CLUSTER_KEY=`"$key`"`n")
$build=Join-Path $root ".local/build/$Revision"
New-Item -ItemType Directory -Force $build | Out-Null
Push-Location $env:IDF_PATH
try{. ./export.ps1}finally{Pop-Location}
Push-Location "$root/firmware"
try {
    $defaults="$root/firmware/sdkconfig.defaults;$root/firmware/sdkconfig.$Revision.defaults;$secretDefaults"
    & python "$env:IDF_PATH/tools/idf.py" -B $build -D "IDF_TARGET=esp32p4" -D "SDKCONFIG=$build/sdkconfig" -D "SDKCONFIG_DEFAULTS=$defaults" build
    if($LASTEXITCODE){throw 'ESP-IDF build failed'}
}finally{Pop-Location}
