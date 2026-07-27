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
