"""Descarga vía yt-dlp: audio + subtitulos del creador, y expansion de playlist.

Toda la red vive aqui (invariante 1: la red solo trae la fuente; la transcripcion
sigue siendo Whisper local). yt-dlp se invoca por `ytdlp_utils.run` y sus fallos
se clasifican a `FailureCause` parseando stderr, para armar el resumen de lote.
"""

from __future__ import annotations

import json
from pathlib import Path

from .errors import DownloadFailed, FailureCause, message_for
from .models import DownloadResult, PlaylistEntry, UrlInfo
from .ytdlp_utils import cookie_args, ensure_ytdlp, run

# Sidecars que yt-dlp puede dejar en el work_dir junto al audio y que NO son la
# pista de audio: subtitulos, miniaturas, y JSON (incluye `.info.json` y el
# `.live_chat.json` del chat en vivo de premieres/directos). `Path.suffix` de
# `id.live_chat.json` es `.json`, asi que este set lo cubre.
_NON_MEDIA_EXTS = {
    ".vtt", ".srt", ".ass", ".ssa", ".lrc",  # subtitulos
    ".json",                                  # .info.json, .live_chat.json
    ".jpg", ".jpeg", ".png", ".webp",         # miniaturas
    ".description", ".txt", ".url", ".nfo",   # otros sidecars
}

# Pseudo-"idiomas" de subtitulo que no son texto transcribible (el chat en vivo
# se entrega como live_chat.json). Nunca deben elegirse como pista de subtitulos.
_IGNORED_SUB_LANGS = {"live_chat"}


def probe_url(url: str, *, cookies: str | None = None) -> UrlInfo:
    """Detecta si la URL es un video unico o una playlist y lista sus entradas (B3).

    Usa `--flat-playlist --dump-json` (una linea JSON por entrada, sin resolver
    cada video), barato y suficiente para ordenar y numerar el lote. `cookies`
    (nombre de navegador o ruta a cookies.txt) sortea el login/anti-bot (P8).
    """
    ytdlp = ensure_ytdlp()
    result = run(
        [
            ytdlp,
            *cookie_args(cookies),
            "--flat-playlist",
            "--dump-json",
            "--ignore-no-formats-error",
            url,
        ]
    )
    if result.returncode != 0:
        cause = classify_failure(result.stderr)
        raise DownloadFailed(
            f"No pude inspeccionar la URL. {message_for(cause)}",
            cause=cause,
            url=url,
        )

    records = _parse_json_lines(result.stdout)
    if not records:
        raise DownloadFailed(
            "yt-dlp no devolvio informacion de la URL. Revisa que sea valida.",
            cause=FailureCause.UNKNOWN,
            url=url,
        )

    # Un video suelto: una sola linea con _type != 'playlist'. Una playlist:
    # varias lineas, cada una una entrada con su id/titulo.
    entries: list[PlaylistEntry] = []
    playlist_title: str | None = None
    for i, rec in enumerate(records, start=1):
        if rec.get("_type") == "playlist" and "entries" not in rec:
            # Cabecera de playlist sin entradas resueltas: la ignoramos.
            playlist_title = rec.get("title") or playlist_title
            continue
        entry_url = rec.get("url") or rec.get("webpage_url") or rec.get("id")
        if not entry_url:
            continue
        playlist_title = rec.get("playlist_title") or playlist_title
        entries.append(
            PlaylistEntry(
                url=entry_url,
                title=rec.get("title") or rec.get("id") or entry_url,
                video_id=rec.get("id") or "",
                index=i,
            )
        )

    is_playlist = len(entries) > 1 or any(
        r.get("_type") == "playlist" for r in records
    )
    return UrlInfo(
        is_playlist=is_playlist,
        entries=entries,
        playlist_title=playlist_title,
    )


def download(
    url: str,
    work_dir: Path,
    *,
    lang: str | None = None,
    allow_auto_subs: bool = False,
    keep_video: bool = False,
    cookies: str | None = None,
) -> DownloadResult:
    """Descarga `bestaudio` + subtitulos de una URL de video unico a `work_dir`.

    Prioriza subtitulos oficiales del creador; los auto-generados solo se
    descargan si `allow_auto_subs` (spec §6, ASR). Devuelve un `DownloadResult`
    con el audio, el subtitulo (o None) y metadatos. Lanza `DownloadFailed` con
    la causa clasificada si yt-dlp falla. `cookies` (nombre de navegador o ruta a
    cookies.txt) sortea el login/anti-bot (P8).
    """
    ytdlp = ensure_ytdlp()
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    meta = _fetch_metadata(ytdlp, url, cookies=cookies)
    video_id = meta.get("id") or "video"
    title = meta.get("title") or video_id
    video_language = meta.get("language")

    chosen_lang, is_auto = _choose_subtitle(
        meta, requested_lang=lang, allow_auto_subs=allow_auto_subs
    )

    out_template = str(work_dir / "%(id)s.%(ext)s")
    cmd = [
        ytdlp,
        *cookie_args(cookies),
        "--no-playlist",
        "-f", "bestaudio/best",
        "-o", out_template,
    ]
    if chosen_lang is not None:
        cmd += ["--sub-langs", chosen_lang, "--sub-format", "vtt/srt/best"]
        cmd.append("--write-auto-subs" if is_auto else "--write-subs")
    cmd.append(url)

    result = run(cmd)
    if result.returncode != 0:
        cause = classify_failure(result.stderr)
        raise DownloadFailed(
            f"No pude descargar el video. {message_for(cause)}",
            cause=cause,
            url=url,
        )

    audio_path = _locate_audio(work_dir, video_id)
    if audio_path is None:
        raise DownloadFailed(
            "La descarga termino pero no encontre el archivo de audio.",
            cause=FailureCause.UNKNOWN,
            url=url,
        )
    subtitle_path = (
        _locate_subtitle(work_dir, video_id) if chosen_lang is not None else None
    )

    return DownloadResult(
        audio_path=audio_path,
        title=title,
        video_id=video_id,
        language=lang or video_language,
        subtitle_path=subtitle_path,
        subtitle_is_auto=is_auto if subtitle_path is not None else False,
    )


def _fetch_metadata(ytdlp: str, url: str, *, cookies: str | None = None) -> dict:
    """Trae los metadatos del video (id, titulo, idioma, subtitulos disponibles)."""
    result = run(
        [ytdlp, *cookie_args(cookies), "--no-playlist", "--dump-json",
         "--skip-download", url]
    )
    if result.returncode != 0:
        cause = classify_failure(result.stderr)
        raise DownloadFailed(
            f"No pude leer los datos del video. {message_for(cause)}",
            cause=cause,
            url=url,
        )
    records = _parse_json_lines(result.stdout)
    if not records:
        raise DownloadFailed(
            "yt-dlp no devolvio metadatos del video.",
            cause=FailureCause.UNKNOWN,
            url=url,
        )
    return records[0]


def _choose_subtitle(
    meta: dict, *, requested_lang: str | None, allow_auto_subs: bool
) -> tuple[str | None, bool]:
    """Decide que idioma de subtitulo pedir y si es auto-generado.

    Prioridad: subtitulo del creador en el idioma pedido (o el original) > auto
    (solo si `allow_auto_subs`). Devuelve (lang, is_auto) o (None, False) si no
    hay subtitulo utilizable y habra que transcribir.
    """
    manual = {
        k: v for k, v in (meta.get("subtitles") or {}).items()
        if k not in _IGNORED_SUB_LANGS
    }
    auto = {
        k: v for k, v in (meta.get("automatic_captions") or {}).items()
        if k not in _IGNORED_SUB_LANGS
    }
    original = meta.get("language")

    # Orden de preferencia de idiomas a intentar.
    candidates = [
        requested_lang,
        original,
        "es",
        "en",
    ]

    # 1) Subtitulo del creador (manual) en algun idioma preferido.
    for lang in candidates:
        if lang and _lang_available(manual, lang):
            return _resolve_lang(manual, lang), False
    # Si no hubo match por preferencia pero el creador subio alguno, tomar el 1ro.
    if manual and requested_lang is None:
        return next(iter(manual)), False

    # 2) Auto-generados, solo si se permiten.
    if allow_auto_subs:
        for lang in candidates:
            if lang and _lang_available(auto, lang):
                return _resolve_lang(auto, lang), True
        if auto and requested_lang is None:
            return next(iter(auto)), True

    return None, False


def _lang_available(subs: dict, lang: str) -> bool:
    """True si `lang` (o una variante regional, p.ej. en-US) esta en `subs`."""
    return _resolve_lang(subs, lang) is not None


def _resolve_lang(subs: dict, lang: str) -> str | None:
    """Devuelve la clave real del idioma en `subs`, tolerando variantes (en/en-US)."""
    if lang in subs:
        return lang
    prefix = lang.split("-")[0].lower()
    for key in subs:
        if key.lower() == prefix or key.lower().startswith(prefix + "-"):
            return key
    return None


def _locate_audio(work_dir: Path, video_id: str) -> Path | None:
    """Encuentra el archivo de audio descargado, ignorando los sidecars.

    yt-dlp deja junto al audio subtitulos, miniaturas y JSON (`.info.json`,
    `.live_chat.json`). Se descartan por extension y, como red de seguridad, se
    elige el archivo mas grande: el medio real pesa MB y los sidecars KB.
    """
    candidates = [
        path
        for path in work_dir.glob(f"{video_id}.*")
        if path.is_file() and path.suffix.lower() not in _NON_MEDIA_EXTS
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_size)


def _locate_subtitle(work_dir: Path, video_id: str) -> Path | None:
    """Encuentra el subtitulo descargado (`<id>.<lang>.vtt|srt`), si lo hay."""
    for ext in ("*.vtt", "*.srt"):
        matches = sorted(work_dir.glob(f"{video_id}.{ext}"))
        if matches:
            return matches[0]
    return None


def _parse_json_lines(stdout: str | None) -> list[dict]:
    """Parsea la salida de yt-dlp: una o varias lineas JSON, tolerando ruido."""
    records: list[dict] = []
    for line in (stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def classify_failure(stderr: str | None) -> FailureCause:
    """Mapea el stderr de yt-dlp a una FailureCause (spec §6).

    Chequea de lo mas especifico a lo mas generico. Cae a UNKNOWN si nada calza.
    """
    text = (stderr or "").lower()
    if not text:
        return FailureCause.UNKNOWN

    if "private video" in text or "this video is private" in text:
        return FailureCause.PRIVATE
    if (
        "not available in your country" in text
        or "not made this video available in your country" in text
        or "geo" in text and "block" in text
        or "geo-restricted" in text
    ):
        return FailureCause.GEOBLOCKED
    if (
        "sign in to confirm your age" in text
        or "confirm you" in text and "bot" in text
        or "sign in to confirm" in text
        or "members-only" in text
        or "this video is available to this channel's members" in text
        or "login required" in text
        or "requires authentication" in text
        or "use --cookies" in text
        or "cookies" in text and "sign in" in text
    ):
        return FailureCause.NEEDS_LOGIN
    if (
        "cookie database" in text
        or "cookies database" in text
        or "could not copy" in text and "cookie" in text
        or "could not find" in text and "cookies" in text
        or "unable to decrypt" in text and "cookie" in text
        or "failed to decrypt" in text and "cookie" in text
        or "no such table: cookies" in text
    ):
        return FailureCause.COOKIES_ERROR
    if (
        "video unavailable" in text
        or "has been removed" in text
        or "has been terminated" in text
        or "no longer available" in text
        or "does not exist" in text
        or "removed by the uploader" in text
        or "account associated with this video has been terminated" in text
    ):
        return FailureCause.UNAVAILABLE
    if (
        "urlopen error" in text
        or "getaddrinfo failed" in text
        or "temporary failure in name resolution" in text
        or "network is unreachable" in text
        or "connection reset" in text
        or "connection refused" in text
        or "timed out" in text
        or "failed to resolve" in text
    ):
        return FailureCause.NETWORK
    if (
        "unable to extract" in text
        or "unsupported url" in text
        or "unable to download webpage" in text
        or "nsig extraction failed" in text
        or "requested format is not available" in text
        or "extractor" in text
    ):
        return FailureCause.EXTRACTOR_ERROR
    return FailureCause.UNKNOWN
