"""Tests de las piezas robustas de core/diarize.py (sin ejecutar whisperx real).

Blindan los 3 bugs que destapo la verificacion real (k-verify, 2026-07-28):
device desde torch, kwarg del token del constructor, y no confundir un error de
codigo con "falta el token".
"""

from tae.core import diarize
from tae.core.errors import DiarizationSetupError


def test_torch_device_devuelve_algo_usable():
    """_torch_device siempre da un par valido, con o sin CUDA en torch (invariante 3)."""
    device, compute = diarize._torch_device()
    assert device in ("cuda", "cpu")
    assert compute in ("float16", "int8")
    # coherencia: cpu -> int8, cuda -> float16
    assert (device == "cpu") == (compute == "int8")


def test_typeerror_no_es_error_de_terminos():
    """Un TypeError (bug de API) NO debe mapearse a falta de token, aunque el texto
    mencione 'token' (bug 2: `use_auth_token` inesperado se tragaba como setup)."""
    exc = TypeError("__init__() got an unexpected keyword argument 'use_auth_token'")
    assert diarize._looks_like_terms_error(exc) is False


def test_error_gated_si_es_de_terminos():
    """Un fallo real de repo gated (401/'accept user conditions') si es setup."""
    exc = RuntimeError(
        "Could not download Pipeline from pyannote/speaker-diarization-community-1. "
        "It might be because the repository is private or gated: "
        "visit https://hf.co/pyannote/speaker-diarization-community-1 to accept user conditions"
    )
    assert diarize._looks_like_terms_error(exc) is True


def test_terms_hint_extrae_url_del_modelo():
    """_terms_hint saca las lineas con la URL a aceptar y descarta la del token."""
    exc = RuntimeError(
        "Cannot access gated repo for url "
        "https://huggingface.co/pyannote/speaker-diarization-community-1/resolve/main/config.yaml.\n"
        "Visit https://hf.co/pyannote/speaker-diarization-community-1 to accept user conditions\n"
        ">>> Pipeline.from_pretrained('pyannote/...', token='hf_....')"
    )
    hint = diarize._terms_hint(exc)
    assert "speaker-diarization-community-1" in hint
    assert "token=" not in hint  # la linea de ejemplo con el token no se incluye


def test_diarization_setup_error_incluye_detalle():
    """DiarizationSetupError adjunta el detalle de pyannote cuando se pasa."""
    err = DiarizationSetupError(detail="visit https://hf.co/pyannote/... to accept")
    assert "Detalle de pyannote:" in str(err)
    assert "accept" in str(err)
