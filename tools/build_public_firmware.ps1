param([string]$SourceBase='', [string]$OutputBase='')
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
if(-not $SourceBase){$SourceBase=Join-Path $root '.local/public-firmware/packages'}
if(-not $OutputBase){$OutputBase=Join-Path $root '.local/public-firmware/build'}
$env:IDF_TOOLS_PATH=Join-Path $root '.local/tooling/idf-tools'
$env:IDF_PATH=Join-Path $root '.local/tooling/esp-idf'
$env:IDF_COMPONENT_MANAGER='0'
$runtime=Join-Path ([Environment]::GetFolderPath('UserProfile')) '.cache/codex-runtimes/codex-primary-runtime/dependencies/python'
$env:PATH="$runtime;$env:PATH"
Push-Location $env:IDF_PATH
try{. ./export.ps1}finally{Pop-Location}
$matrix=@(@('0.2.0','rev1'),@('0.3.0','rev1'),@('0.4.0','rev1'),@('0.5.5','rev1'),@('0.5.5','rev3'))
foreach($item in $matrix) {
    $version=$item[0];$revision=$item[1]
    $source=Join-Path $SourceBase "$version/source/firmware"
    $build=Join-Path $OutputBase "$version-$revision"
    if(Test-Path (Join-Path $build 'sdkconfig')){throw 'Refuse to reuse an existing firmware configuration'}
    New-Item -ItemType Directory -Force $build | Out-Null
    $defaultsFile=Join-Path $build 'public.defaults'
    [IO.File]::WriteAllText($defaultsFile,"CONFIG_CLUSTER_KEY=`"`"`nCONFIG_APP_REPRODUCIBLE_BUILD=y`nCONFIG_COMPILER_HIDE_PATHS_MACROS=y`n")
    $defaults="$source/sdkconfig.defaults;$source/sdkconfig.$revision.defaults;$defaultsFile"
    Write-Output "BUILD $version $revision keyless diagnostic"
    Push-Location $source
    try {
        & python "$env:IDF_PATH/tools/idf.py" -B $build -D 'IDF_TARGET=esp32p4' -D "SDKCONFIG=$build/sdkconfig" -D "SDKCONFIG_DEFAULTS=$defaults" build *> (Join-Path $build 'build.log')
        if($LASTEXITCODE){Get-Content (Join-Path $build 'build.log') -Tail 18;throw "Public build failed: $version $revision"}
    }finally{Pop-Location}
    Write-Output "BUILT $version $revision"
}
