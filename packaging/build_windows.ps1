# Build reproducible de la carpeta portable tae-gui (ver docs/plans/2026-08-01-empaquetado-windows-portable.md).
#
# Uso: ./packaging/build_windows.ps1
#
# Requiere: packaging/bin/ffmpeg.exe, ffprobe.exe, yt-dlp.exe ya colocados a
# mano (ver packaging/README.md) — no se descargan solos.

$ErrorActionPreference = "Stop"

# El repo vive en G: (unidad compartida/Google Shared Drive). Un .venv ahi
# revienta al instalar torch/whisperx (miles de archivos chicos -> Windows
# "error 1450: recursos insuficientes", visto en la practica). Por eso este
# build usa SIEMPRE un venv dedicado en disco local, fijado aqui mismo (no en
# una variable de entorno global) — mismo patron que ya usa UnidadSO con el
# suyo. Ver docs/pendientes.md (venv en unidad de red).
$env:UV_PROJECT_ENVIRONMENT = "C:\Users\kepen\.venvs\tae"

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

# El build (build/ y dist/ de PyInstaller: cientos de miles de archivos
# chicos durante ~40 min) NO puede vivir en G: (unidad de red/Google Shared
# Drive) — el cliente de sync compite por los mismos archivos y da "acceso
# denegado" / "recursos insuficientes" a mitad de camino (visto en la
# practica, dos veces). Por eso build/dist van en disco local; el resultado
# final se copia a G: solo una vez al terminar, ya como carpeta cerrada.
$LocalRoot = Join-Path $env:LOCALAPPDATA "TextAudioExtractor"
$LocalWork = Join-Path $LocalRoot "build"
$LocalDist = Join-Path $LocalRoot "dist"
$LocalDistDir = Join-Path $LocalDist "tae-gui"

$BinDir = Join-Path $PSScriptRoot "bin"
$DistDir = Join-Path $RepoRoot "dist\tae-gui"
$RequiredBins = @("ffmpeg.exe", "ffprobe.exe", "yt-dlp.exe")

Write-Output "== 1/6: verificando binarios externos en packaging/bin/ =="
foreach ($bin in $RequiredBins) {
    $path = Join-Path $BinDir $bin
    if (-not (Test-Path $path)) {
        throw "Falta $path. Ver packaging/README.md para donde descargarlo."
    }
}

Write-Output "== 2/6: limpiando build/dist previos (disco local) =="
foreach ($dir in @($LocalWork, $LocalDist)) {
    if (Test-Path $dir) { Remove-Item -Recurse -Force $dir }
}
# El dist/ viejo en G: (de intentos previos) puede seguir bloqueado por el
# sync de Google Drive — no es fatal si no se puede limpiar, se sobreescribe
# al copiar el resultado final (paso 6/6).
if (Test-Path $DistDir) {
    Remove-Item -Recurse -Force $DistDir -ErrorAction SilentlyContinue
}

Write-Output "== 3/6: corriendo PyInstaller (uv run --extra diarize) =="
# PyInstaller/uv escriben su progreso a stderr. En PowerShell 5.1, con
# $ErrorActionPreference = "Stop", stderr de un comando nativo se envuelve en
# un NativeCommandError que aborta el script aunque el proceso vaya bien —
# por eso se relaja aqui y se valida el fallo real con $LASTEXITCODE.
$prevEap = $ErrorActionPreference
$ErrorActionPreference = "Continue"
uv run --extra diarize pyinstaller (Join-Path $PSScriptRoot "tae-gui.spec") --noconfirm `
    --workpath $LocalWork --distpath $LocalDist
$pyinstallerExitCode = $LASTEXITCODE
$ErrorActionPreference = $prevEap
if ($pyinstallerExitCode -ne 0) { throw "PyInstaller fallo con codigo $pyinstallerExitCode" }
if (-not (Test-Path $LocalDistDir)) { throw "PyInstaller no genero $LocalDistDir" }

Write-Output "== 4/6: copiando ffmpeg/yt-dlp y DLL de CUDA (disco local) =="
foreach ($bin in $RequiredBins) {
    Copy-Item (Join-Path $BinDir $bin) (Join-Path $LocalDistDir $bin) -Force
}

$VenvSitePackages = Join-Path $env:UV_PROJECT_ENVIRONMENT "Lib\site-packages\nvidia"
$CudaDllsOut = Join-Path $LocalDistDir "cuda_dlls"
New-Item -ItemType Directory -Force -Path $CudaDllsOut | Out-Null
$foundAny = $false
foreach ($pkg in @("cublas", "cudnn")) {
    $binDir = Join-Path $VenvSitePackages "$pkg\bin"
    if (Test-Path $binDir) {
        Get-ChildItem $binDir -Filter "*.dll" | ForEach-Object {
            Copy-Item $_.FullName $CudaDllsOut -Force
            $foundAny = $true
        }
    }
}
if (-not $foundAny) {
    throw "No se encontraron DLL de cublas/cudnn en $VenvSitePackages. " +
        "Verifica que 'uv sync' instalo nvidia-cublas-cu12/nvidia-cudnn-cu12 (ver pyproject.toml)."
}

Write-Output "== 5/6: smoke test (sobre el build local) =="
& (Join-Path $PSScriptRoot "smoke_test.ps1") -DistDir $LocalDistDir

Write-Output "== 6/6: copiando resultado final a $DistDir =="
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $DistDir) | Out-Null
Copy-Item $LocalDistDir $DistDir -Recurse -Force

Write-Output ""
Write-Output "Build listo: $DistDir (tambien queda en disco local: $LocalDistDir)"
