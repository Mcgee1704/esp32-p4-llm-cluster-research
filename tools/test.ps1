$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$python = 'python'
$zig = Join-Path $root '.local/tooling/host/ziglang/zig.exe'
$build = Join-Path $root '.local/build'
New-Item -ItemType Directory -Force $build | Out-Null
& $zig cc -shared -O2 -Wall -Wextra -Werror -ffp-contract=off -I "$root/firmware/components/tinyllm/include" "$root/firmware/components/tinyllm/tinyllm.c" "$root/firmware/components/tinyllm/model_envelope.c" "$root/firmware/components/tinyllm/gpt2_tokenizer.c" "$root/firmware/components/tinyllm/sp_tokenizer.c" "$root/firmware/components/tinyllm/cluster_rpc.c" -o "$build/tinyllm.dll"
if ($LASTEXITCODE) { throw 'Native C build failed' }
& $zig cc -shared -O2 -Wall -Wextra -Werror -I "$root/firmware/components/dispatch_queue/include" "$root/firmware/components/dispatch_queue/dispatch_queue.c" -o "$build/dispatch_queue.dll"
if ($LASTEXITCODE) { throw 'Native dispatch queue build failed' }
Push-Location $root
try {
    & $python -m unittest discover -s tests -v
    if ($LASTEXITCODE) { throw 'Tests failed' }
} finally { Pop-Location }
