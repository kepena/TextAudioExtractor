"""Diarizacion de hablantes con whisperX (opt-in, camino C del spec).

Envuelve el pipeline whisperX (transcribe -> alinea palabra a palabra -> separa
hablantes) y devuelve la misma `list[Segment]` que `transcribe.py`, pero con
`speaker` poblado.

Invariantes:
- Import diferido de `whisperx` DENTRO de la funcion: importar este modulo no debe
  arrastrar torch/pyannote (invariante 4) ni romper el arranque si el extra no esta
  instalado. Si falta -> `DiarizationUnavailable`.
- whisperX + token HF son dependencias de setup (invariante 5): si faltan, error
  claro, no traceback.
- Degrada sin GPU (invariante 3): avisa que en CPU sera lento y procede.
- Todo local (invariante 1): el token HF solo autoriza la descarga inicial de pesos.

whisperX no entrega segmentos en streaming, asi que el progreso se reporta por
ETAPAS (~0.5 transcribe, ~0.75 alinear, ~1.0 diarizar/asignar), no por segmento.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

from .errors import (
    Cancelled,
    DiarizationSetupError,
    DiarizationUnavailable,
)
from .models import Segment
from .transcribe import _add_cuda_dll_dirs, detect_device


def _hf_token() -> str | None:
    """Lee el token de HuggingFace de las variables de entorno habituales."""
    for var in ("HF_TOKEN", "HUGGINGFACE_TOKEN"):
        token = os.environ.get(var)
        if token:
            return token.strip()
    return None


def _looks_like_terms_error(exc: Exception) -> bool:
    """Heuristica: ¿el fallo es por terminos no aceptados / token invalido?

    pyannote/HuggingFace no exponen un tipo de excepcion estable para esto; el
    fallo llega como HTTP 401/403 o mensajes de 'gated'/'access'. Lo mapeamos a
    `DiarizationSetupError` para no soltar el traceback crudo.
    """
    text = f"{type(exc).__name__} {exc}".lower()
    needles = (
        "401",
        "403",
        "gated",
        "unauthorized",
        "authenticated",
        "authentication",
        "access to model",
        "accept the",
        "user agreement",
        "terms",
        "token",
        "permission",
        "forbidden",
    )
    return any(n in text for n in needles)


def transcribe_and_diarize(
    audio: Path,
    *,
    model: str = "medium",
    language: str | None = None,
    num_speakers: int | None = None,
    duration: float | None = None,
    on_progress: Callable[[float], None] | None = None,
    on_info: Callable[[str], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> tuple[list[Segment], str | None]:
    """Transcribe y diariza el audio. Devuelve (segmentos, idioma_detectado).

    Cada `Segment` trae `speaker` poblado (`SPEAKER_00`, ...) cuando whisperX pudo
    asignarlo. `on_info` recibe avisos legibles (device, descarga de pesos, etapa);
    `should_cancel` se consulta entre etapas para cortar limpio.
    """
    _add_cuda_dll_dirs()

    # --- Import diferido: si whisperx no esta instalado, es un fallo de setup ---
    try:
        import whisperx
    except ImportError as exc:
        raise DiarizationUnavailable() from exc

    token = _hf_token()
    if not token:
        raise DiarizationSetupError()

    device, compute_type = detect_device()
    if on_info:
        if device == "cuda":
            on_info(f"Diarizando en GPU (modelo {model}).")
        else:
            on_info(
                f"No se detecto GPU NVIDIA disponible: la diarizacion correra en CPU "
                f"(modelo {model}) y sera notablemente lenta."
            )
        on_info("Cargando modelos (la primera vez se descargan los pesos)...")

    def check_cancel() -> None:
        if should_cancel and should_cancel():
            raise Cancelled("Diarizacion cancelada por el usuario.")

    def progress(value: float) -> None:
        if on_progress:
            on_progress(value)

    # --- Etapa 1: transcribir ---
    audio_data = whisperx.load_audio(str(audio))
    whisper_model = whisperx.load_model(
        model, device, compute_type=compute_type, language=language
    )
    trans = whisper_model.transcribe(audio_data, batch_size=16)
    detected_language = trans.get("language") or language
    progress(0.5)
    check_cancel()

    trans_segments = trans.get("segments") or []
    if not trans_segments:
        # Audio sin voz: no hay nada que alinear ni diarizar (spec §6).
        progress(1.0)
        return [], detected_language

    # --- Etapa 2: alinear palabra a palabra ---
    if on_info:
        on_info("Alineando la transcripcion...")
    align_model, align_meta = whisperx.load_align_model(
        language_code=detected_language, device=device
    )
    aligned = whisperx.align(
        trans_segments,
        align_model,
        align_meta,
        audio_data,
        device,
        return_char_alignments=False,
    )
    progress(0.75)
    check_cancel()

    # --- Etapa 3: separar hablantes y asignarlos a cada palabra/segmento ---
    if on_info:
        on_info("Identificando hablantes...")
    try:
        diarize_pipeline = _make_diarization_pipeline(whisperx, token, device)
        if num_speakers is not None:
            diarize_segments = diarize_pipeline(audio_data, num_speakers=num_speakers)
        else:
            diarize_segments = diarize_pipeline(audio_data)
    except (DiarizationUnavailable, DiarizationSetupError, Cancelled):
        raise
    except Exception as exc:
        if _looks_like_terms_error(exc):
            raise DiarizationSetupError() from exc
        raise

    result = whisperx.assign_word_speakers(diarize_segments, aligned)
    progress(1.0)

    segments: list[Segment] = []
    for seg in result.get("segments") or []:
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        segments.append(
            Segment(
                start=float(seg.get("start", 0.0)),
                end=float(seg.get("end", 0.0)),
                text=text,
                speaker=seg.get("speaker"),
            )
        )
    return segments, detected_language


def _make_diarization_pipeline(whisperx, token: str, device: str):
    """Construye el pipeline de diarizacion tolerando variantes de la API whisperX.

    Segun la version, `DiarizationPipeline` vive en `whisperx` o en
    `whisperx.diarize`. Un fallo por terminos/token se mapea arriba.
    """
    pipeline_cls = getattr(whisperx, "DiarizationPipeline", None)
    if pipeline_cls is None:
        from whisperx.diarize import DiarizationPipeline as pipeline_cls  # type: ignore
    return pipeline_cls(use_auth_token=token, device=device)
