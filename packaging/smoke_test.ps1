# Smoke test post-build (ver Bloque E2 del plan). Falla visiblemente si algo
# no arranca, en vez de dar el build por bueno solo porque PyInstaller no
# reporto errores.
#
# Uso: ./packaging/smoke_test.ps1 -DistDir dist/tae-gui

param(
    [Parameter(Mandatory = $true)]
    [string]$DistDir
)

$ErrorActionPreference = "Stop"

function Fail($msg) {
    Write-Error "SMOKE TEST FALLO: $msg"
    exit 1
}

$exe = Join-Path $DistDir "tae-gui.exe"
if (-not (Test-Path $exe)) { Fail "no existe $exe" }

# 1) ffmpeg/ffprobe/yt-dlp bundleados responden a su flag de version.
# Ojo: ffmpeg/ffprobe usan `-version` (un guion); yt-dlp usa `--version`
# (estilo GNU) — no son intercambiables, ffmpeg falla duro con el flag de
# otro binario.
$versionFlag = @{
    "ffmpeg.exe"  = "-version"
    "ffprobe.exe" = "-version"
    "yt-dlp.exe"  = "--version"
}
foreach ($bin in @("ffmpeg.exe", "ffprobe.exe", "yt-dlp.exe")) {
    $path = Join-Path $DistDir $bin
    if (-not (Test-Path $path)) { Fail "falta $bin en $DistDir (ver packaging/README.md)" }
    $absPath = (Resolve-Path $path).Path
    & $absPath $versionFlag[$bin] > $null
    if ($LASTEXITCODE -ne 0) { Fail "$bin $($versionFlag[$bin]) salio con codigo $LASTEXITCODE" }
}
Write-Output "OK: ffmpeg/ffprobe/yt-dlp bundleados responden."

# 2) cuda_dlls presente (no valida contenido de GPU real, solo que el build lo copio).
$cudaDlls = Join-Path $DistDir "cuda_dlls"
if (-not (Test-Path $cudaDlls)) { Fail "falta la carpeta cuda_dlls en $DistDir" }
if (-not (Get-ChildItem $cudaDlls -Filter "*.dll" -ErrorAction SilentlyContinue)) {
    Fail "cuda_dlls existe pero no tiene .dll"
}
Write-Output "OK: cuda_dlls con DLL presentes."

# 3) tae-gui.exe arranca y sigue vivo pasados unos segundos (no crashea al abrir).
$proc = Start-Process -FilePath $exe -PassThru
Start-Sleep -Seconds 8
$stillRunning = Get-Process -Id $proc.Id -ErrorAction SilentlyContinue
if (-not $stillRunning) { Fail "tae-gui.exe crasheo o cerro solo en los primeros 8s" }
Stop-Process -Id $proc.Id -Force
Write-Output "OK: tae-gui.exe arranca y se mantiene corriendo."

Write-Output ""
Write-Output "Smoke test basico OK. Falta la validacion manual real (Bloque F1 del plan):"
Write-Output "transcripcion GPU, diarizacion CPU/WSL2, tae url, cancelar a mitad."
