"""Worker standalone de diarizacion, para correr DENTRO de WSL2 (P11).

Deliberadamente independiente del paquete `tae`: no se instala `tae` en la
distro Ubuntu (invariante de "solo la diarizacion cruza a WSL2"), asi que este
script corre con el venv de `scripts/wsl_diarize_setup.sh` y solo depende de
whisperx/torch. `core/diarize_wsl.py` (lado Windows) lo invoca via
`wsl.exe -d <distro> -- <venv>/bin/python wsl_diarize_worker.py ...`.

Protocolo con el lado Windows (todo por stdout, una directiva por linea):
- "TAE_PID <pid>"            primera linea, el pid real dentro de la distro
                              (para poder matarlo si se cancela, ver E1 del plan)
- "TAE_INFO <mensaje>"       aviso legible (device, descarga de pesos, etapa)
- "TAE_PROGRESS <0..1>"      fraccion de avance
- "TAE_ERROR <categoria> <mensaje>"  fallo, categoria en {unavailable, setup, error}
El resultado (segmentos + idioma) se escribe como JSON en --out, no por stdout,
para no arriesgar mezclarlo con el resto del output de whisperX/torch.
"""

from __future__ import annotations

import argparse
import json
import os
import sys


def emit(directive: str, *parts: str) -> None:
    print(directive, *parts, flush=True)


def emit_pid() -> None:
    emit("TAE_PID", str(os.getpid()))


def emit_info(msg: str) -> None:
    emit("TAE_INFO", msg)


def emit_progress(fraction: float) -> None:
    emit("TAE_PROGRESS", f"{fraction:.4f}")


def emit_error(category: str, msg: str) -> None:
    emit("TAE_ERROR", category, msg.replace("\n", " "))


def _hf_token() -> str | None:
    for var in ("HF_TOKEN", "HUGGINGFACE_TOKEN"):
        token = os.environ.get(var)
        if token:
            return token.strip()
    return None


def _looks_like_terms_error(exc: Exception) -> bool:
    """Misma heuristica que `core/diarize.py::_looks_like_terms_error` (duplicada
    a proposito: este script no puede importar `tae.core`, vive en otro entorno)."""
    if isinstance(exc, (TypeError, AttributeError, NameError, KeyError, IndexError, ValueError)):
        return False
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


def _make_diarization_pipeline(whisperx, token: str, device: str):
    """Misma tolerancia de firma que `core/diarize.py::_make_diarization_pipeline`."""
    import inspect

    pipeline_cls = getattr(whisperx, "DiarizationPipeline", None)
    if pipeline_cls is None:
        from whisperx.diarize import DiarizationPipeline as pipeline_cls  # type: ignore

    params = inspect.signature(pipeline_cls.__init__).parameters
    kwargs: dict = {"device": device}
    if "token" in params:
        return pipeline_cls(token=token, **kwargs)
    if "use_auth_token" in params:
        return pipeline_cls(use_auth_token=token, **kwargs)
    return pipeline_cls(token, device=device)


def run(args: argparse.Namespace) -> int:
    emit_pid()

    try:
        import torch
        import whisperx
    except ImportError as exc:
        emit_error("unavailable", f"whisperx/torch no disponibles en este venv: {exc}")
        return 1

    token = _hf_token()
    if not token:
        emit_error(
            "setup",
            "Falta HF_TOKEN/HUGGINGFACE_TOKEN dentro de WSL2. Corre "
            "scripts/wsl_diarize_setup.sh para ver como configurarlo.",
        )
        return 1

    device = "cuda" if torch.cuda.is_available() else "cpu"
    compute_type = "float16" if device == "cuda" else "int8"
    emit_info(f"Diarizando en {device} (modelo {args.model}, WSL2).")
    emit_info("Cargando modelos (la primera vez se descargan los pesos)...")

    try:
        audio_data = whisperx.load_audio(args.audio)
        whisper_model = whisperx.load_model(
            args.model, device, compute_type=compute_type, language=args.language
        )
        trans = whisper_model.transcribe(audio_data, batch_size=16)
        detected_language = trans.get("language") or args.language
        emit_progress(0.5)

        trans_segments = trans.get("segments") or []
        if not trans_segments:
            with open(args.out, "w", encoding="utf-8") as fh:
                json.dump({"language": detected_language, "segments": []}, fh)
            emit_progress(1.0)
            return 0

        emit_info("Alineando la transcripcion...")
        align_model, align_meta = whisperx.load_align_model(
            language_code=detected_language, device=device
        )
        aligned = whisperx.align(
            trans_segments, align_model, align_meta, audio_data, device,
            return_char_alignments=False,
        )
        emit_progress(0.75)

        emit_info("Identificando hablantes...")
        diarize_pipeline = _make_diarization_pipeline(whisperx, token, device)
        if args.speakers is not None:
            diarize_segments = diarize_pipeline(audio_data, num_speakers=args.speakers)
        else:
            diarize_segments = diarize_pipeline(audio_data)

        result = whisperx.assign_word_speakers(diarize_segments, aligned)
        emit_progress(1.0)
    except Exception as exc:  # noqa: BLE001 - se reporta legible via TAE_ERROR
        if _looks_like_terms_error(exc):
            emit_error("setup", str(exc))
        else:
            emit_error("error", f"{type(exc).__name__}: {exc}")
        return 1

    segments = []
    for seg in result.get("segments") or []:
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        segments.append(
            {
                "start": float(seg.get("start", 0.0)),
                "end": float(seg.get("end", 0.0)),
                "text": text,
                "speaker": seg.get("speaker"),
            }
        )

    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump({"language": detected_language, "segments": segments}, fh)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio", required=True, help="Ruta al audio (path Linux, ya convertido)")
    parser.add_argument("--out", required=True, help="Ruta del JSON de resultado a escribir")
    parser.add_argument("--model", default="medium")
    parser.add_argument("--language", default=None)
    parser.add_argument("--speakers", type=int, default=None)
    args = parser.parse_args()

    try:
        return run(args)
    except Exception as exc:  # noqa: BLE001 - ultimo resguardo, nunca traceback crudo a stdout
        emit_error("error", f"{type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
