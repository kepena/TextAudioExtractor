#!/usr/bin/env bash
# Setup del entorno de diarizacion GPU dentro de WSL2 (Ubuntu/Debian).
#
# Corre ESTE script DESDE Windows (PowerShell/Git Bash), pasandolo por stdin:
#   wsl.exe -d Ubuntu -- bash < scripts/wsl_diarize_setup.sh
# Importante: NO uses una ruta tipo /mnt/<letra>/... si el repo vive en una
# unidad que WSL2 no automonta (ej. una unidad de red o de Google Drive para
# escritorio: en esta maquina el repo esta en G: y WSL2 no la monta sola en
# /mnt/g). La forma de stdin de arriba evita ese problema por completo, porque
# es Windows quien lee el archivo, no WSL2. Tambien sirve correrlo copiado o
# clonado dentro de la distro y ejecutado directo con bash ahi.
#
# Crea un venv aislado con whisperX 3.8 + torch (indice CUDA cu128) para que la
# diarizacion (P11, docs/plans/2026-07-30-diarizacion-gpu-wsl2.md) corra en GPU.
# No instala el paquete `tae`: el worker que usa este venv
# (scripts/wsl_diarize_worker.py) es standalone a proposito, para no duplicar
# todo el entorno Windows del lado Linux.
#
# Ruta del venv y version de whisperX configurables por variable de entorno,
# consistentes con lo que espera `core/diarize_wsl.py` (TAE_WSL_DIARIZE_VENV).
set -euo pipefail

VENV_DIR="${TAE_WSL_DIARIZE_VENV:-$HOME/.venvs/tae-diarize}"
TORCH_INDEX="${TAE_TORCH_CUDA_INDEX:-https://download.pytorch.org/whl/cu128}"
WHISPERX_SPEC="${TAE_WHISPERX_SPEC:-whisperx>=3.8}"
# whisperX 3.8 fija torch~=2.8.0/torchaudio~=2.8.0/torchvision~=0.23.0 (ver su
# pyproject). Si aqui se instala un torch SIN fijar, pip trae el mas nuevo del
# indice cu128 (ej. 2.11) y despues, al instalar whisperx, el resolver ve que
# no cumple el pin y descarga OTRO torch completo (~900MB) del indice normal
# -- duplica la descarga y puede perder la build CUDA correcta. Por eso se fija
# aqui a la misma version que whisperx pide, en el MISMO comando/indice.
TORCH_PACKAGES="${TAE_TORCH_PACKAGES:-torch~=2.8.0 torchaudio~=2.8.0 torchvision~=0.23.0}"

echo "== Setup diarizacion GPU (WSL2) =="
echo "Venv: $VENV_DIR"

if ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: python3 no esta instalado en esta distro. Instalalo primero" >&2
    echo "  (ej. sudo apt update && sudo apt install -y python3 python3-venv)." >&2
    exit 1
fi

if ! command -v ffmpeg >/dev/null 2>&1; then
    echo "ERROR: ffmpeg no esta instalado en esta distro." >&2
    echo "  whisperx.load_audio() lo necesita para decodificar el audio (invariante 5:" >&2
    echo "  es un binario de sistema, no una dependencia pip, y va aparte del venv)." >&2
    echo "  Instalalo con:" >&2
    echo "    sudo apt update && sudo apt install -y ffmpeg" >&2
    exit 1
fi

if [ -x "$VENV_DIR/bin/python" ] && "$VENV_DIR/bin/python" -m pip --version >/dev/null 2>&1; then
    echo "Venv ya existe y tiene pip, reutilizando."
else
    echo "Creando venv (o recreandolo: el anterior no tenia pip funcional)..."
    rm -rf "$VENV_DIR"
    python3 -m venv "$VENV_DIR"
fi

PY="$VENV_DIR/bin/python"
"$PY" -m pip install --upgrade pip

echo "Instalando $TORCH_PACKAGES (indice CUDA: $TORCH_INDEX)..."
# shellcheck disable=SC2086
"$PY" -m pip install $TORCH_PACKAGES --index-url "$TORCH_INDEX"

echo "Instalando $WHISPERX_SPEC (sin tocar el torch ya instalado)..."
"$PY" -m pip install "$WHISPERX_SPEC"

echo
echo "== Verificando CUDA dentro del venv =="
if "$PY" -c "import torch, sys; sys.exit(0 if torch.cuda.is_available() else 1)"; then
    echo "OK: torch ve la GPU dentro de WSL2."
else
    echo "AVISO: torch NO ve GPU dentro de WSL2 todavia."
    echo "  Revisa 'nvidia-smi' dentro de esta distro y los drivers NVIDIA para WSL2 en Windows."
fi

echo
echo "== Falta el token de HuggingFace =="
echo "La diarizacion (pyannote, via whisperX) necesita un token de HuggingFace para"
echo "descargar los pesos la primera vez:"
echo "  1. Crea una cuenta gratis en https://huggingface.co y genera un token en"
echo "     https://huggingface.co/settings/tokens"
echo "  2. Acepta los terminos del modelo en"
echo "     https://huggingface.co/pyannote/speaker-diarization-community-1"
echo "  3. Exporta el token DENTRO de esta distro (no en Windows), agregandolo a"
echo "     ~/.profile (NO a ~/.bashrc: el .bashrc estandar de Ubuntu corta la"
echo "     ejecucion en shells no interactivos con 'case \$- in *i*) ;; *) return;;"
echo "     esac', que es exactamente como core/diarize_wsl.py invoca WSL2 -- si"
echo "     el token solo esta en .bashrc, la app real nunca lo ve):"
echo "       echo 'export HF_TOKEN=hf_xxxxxxxxxxxxxxxxxxxx' >> ~/.profile"
echo "     Verifica con un shell no interactivo (asi es como corre la app):"
echo "       bash -lc 'echo \$HF_TOKEN'"
echo
echo "Setup completo. Venv listo en: $VENV_DIR"
