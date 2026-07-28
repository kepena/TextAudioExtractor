"""Verifica los invariantes del repo que un cambio descuidado romperia en silencio."""

import subprocess
import sys

import pytest

from tae.core.errors import FfmpegNotFound
from tae.core.ffmpeg_utils import ensure_ffmpeg


def test_invariant4_core_no_importa_gui():
    """El motor no debe arrastrar PySide6 (invariante 4)."""
    code = (
        "import sys; import tae.core.pipeline;"
        "assert 'PySide6' not in sys.modules, 'core importo PySide6';"
        "print('ok')"
    )
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


def test_invariant5_ffmpeg_faltante_da_error_claro(monkeypatch):
    """Sin ffmpeg en PATH, ensure_ffmpeg lanza un error accionable (invariante 5)."""
    monkeypatch.setattr("tae.core.ffmpeg_utils.shutil.which", lambda _: None)
    with pytest.raises(FfmpegNotFound) as exc:
        ensure_ffmpeg()
    assert "ffmpeg" in str(exc.value).lower()


def test_invariant3_detect_device_no_crashea():
    """detect_device siempre devuelve algo usable, con o sin GPU (invariante 3)."""
    from tae.core.transcribe import detect_device

    device, compute = detect_device()
    assert device in ("cuda", "cpu")
    assert compute in ("float16", "int8")


def test_invariant4_core_no_importa_online():
    """Importar el core no debe arrastrar el modulo online (capa aislada, invariante 4)."""
    code = (
        "import sys; import tae.core.pipeline;"
        "assert not any(m.startswith('tae.online') for m in sys.modules), "
        "'core importo tae.online';"
        "print('ok')"
    )
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


def test_core_subtitles_sigue_exportando_api_previa():
    """parse_srt y extract_subtitles siguen existiendo tras agregar parse_vtt (E3)."""
    from tae.core import subtitles

    assert hasattr(subtitles, "parse_srt")
    assert hasattr(subtitles, "extract_subtitles")
    assert hasattr(subtitles, "parse_vtt")  # el aditivo de esta fase


def test_invariante_diarize_import_diferido_whisperx():
    """Importar core.diarize NO debe cargar whisperx (import diferido, invariante 5)."""
    code = (
        "import sys; import tae.core.diarize;"
        "assert 'whisperx' not in sys.modules, 'core.diarize importo whisperx en el modulo';"
        "print('ok')"
    )
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


def test_invariante4_diarize_no_importa_gui():
    """core.diarize no debe arrastrar PySide6 (invariante 4)."""
    code = (
        "import sys; import tae.core.diarize;"
        "assert 'PySide6' not in sys.modules, 'core.diarize importo PySide6';"
        "print('ok')"
    )
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
