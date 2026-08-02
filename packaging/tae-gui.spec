# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec para tae-gui (carpeta portable --onedir, ver docs/plans/2026-08-01-empaquetado-windows-portable.md).

No correr `pyinstaller` a mano salvo para iterar en desarrollo: el build
reproducible real es `packaging/build_windows.ps1`, que ademas copia
ffmpeg/yt-dlp y los DLL de CUDA que este spec no incluye.
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

REPO_ROOT = Path(SPECPATH).parent  # packaging/ -> raiz del repo
SRC = REPO_ROOT / "src"

datas = [
    # Mismo layout relativo que en el repo, para que
    # Path(__file__).parent / "assets"|"fonts" en app.py siga resolviendo.
    (str(SRC / "tae" / "gui" / "assets"), "tae/gui/assets"),
    (str(SRC / "tae" / "gui" / "fonts"), "tae/gui/fonts"),
    # Worker standalone de diarizacion GPU vía WSL2 (P11): en modo congelado
    # diarize_wsl.py lo busca junto al ejecutable (ver _worker_script_path()).
    (str(REPO_ROOT / "scripts" / "wsl_diarize_worker.py"), "."),
]

# PyInstaller solo sigue imports .py: los datos no-Python que estos paquetes
# traen junto a su codigo (ej. faster_whisper/assets/silero_vad_v6.onnx, el
# modelo de VAD) no se copian solos. Encontrado en la practica (2026-08-01,
# validacion manual real) cuando faltaba justo ese .onnx.
for pkg in ("faster_whisper", "whisperx", "pyannote.audio"):
    datas += collect_data_files(pkg)

# Se completa en la tarea C2 a medida que aparezcan ModuleNotFoundError reales
# al correr el .exe generado (ctranslate2/faster_whisper/torch/whisperx/
# pyannote suelen necesitar hidden imports explicitos con PyInstaller).
hiddenimports = []

a = Analysis(
    [str(REPO_ROOT / "packaging" / "entrypoint_gui.py")],
    pathex=[str(SRC)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="tae-gui",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="tae-gui",
)
