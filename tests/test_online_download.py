"""Descarga y probe (B2/B3) con subprocess mockeado — sin tocar la red."""

import json
import subprocess

import pytest

from tae.online import download as dl_mod
from tae.online.download import (
    _choose_subtitle,
    classify_failure,
    download,
    probe_url,
)
from tae.online.errors import DownloadFailed, FailureCause


def _cp(returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr
    )


@pytest.fixture(autouse=True)
def _fake_ytdlp(monkeypatch):
    """yt-dlp siempre 'presente' en estos tests."""
    monkeypatch.setattr(dl_mod, "ensure_ytdlp", lambda: "yt-dlp")


# ---------- classify_failure (§6) ----------
@pytest.mark.parametrize(
    "stderr,expected",
    [
        ("ERROR: Private video. Sign in if you've been granted access", FailureCause.PRIVATE),
        ("ERROR: This video is not available in your country", FailureCause.GEOBLOCKED),
        ("ERROR: Video unavailable. This video has been removed", FailureCause.UNAVAILABLE),
        ("ERROR: Sign in to confirm your age", FailureCause.NEEDS_LOGIN),
        (
            'ERROR: could not find firefox cookies database in "C:\\...\\Profiles"',
            FailureCause.COOKIES_ERROR,
        ),
        (
            "ERROR: Could not copy Chrome cookie database. See issues/7271",
            FailureCause.COOKIES_ERROR,
        ),
        ("ERROR: Unable to extract video data; please report", FailureCause.EXTRACTOR_ERROR),
        (
            "ERROR: [youtube] jNQXAC9IVRw: No video formats found!",
            FailureCause.EXTRACTOR_ERROR,
        ),
        ("ERROR: <urlopen error getaddrinfo failed>", FailureCause.NETWORK),
        ("ERROR: algo totalmente distinto", FailureCause.UNKNOWN),
        ("", FailureCause.UNKNOWN),
    ],
)
def test_classify_failure(stderr, expected):
    assert classify_failure(stderr) is expected


# ---------- _choose_subtitle ----------
def test_choose_prefiere_creador_sobre_auto():
    meta = {"subtitles": {"es": [{}]}, "automatic_captions": {"es": [{}]}, "language": "es"}
    lang, is_auto = _choose_subtitle(meta, requested_lang="es", allow_auto_subs=True)
    assert lang == "es" and is_auto is False


def test_choose_cae_a_auto_solo_si_permitido():
    meta = {"subtitles": {}, "automatic_captions": {"en": [{}]}, "language": "en"}
    # sin permiso -> nada
    lang, is_auto = _choose_subtitle(meta, requested_lang="en", allow_auto_subs=False)
    assert lang is None and is_auto is False
    # con permiso -> auto
    lang, is_auto = _choose_subtitle(meta, requested_lang="en", allow_auto_subs=True)
    assert lang == "en" and is_auto is True


def test_choose_tolera_variante_regional():
    meta = {"subtitles": {"en-US": [{}]}, "automatic_captions": {}, "language": "en"}
    lang, is_auto = _choose_subtitle(meta, requested_lang="en", allow_auto_subs=False)
    assert lang == "en-US" and is_auto is False


# ---------- download() ----------
def _meta_json(**over):
    base = {
        "id": "abc123",
        "title": "Mi Charla",
        "language": "es",
        "subtitles": {},
        "automatic_captions": {},
    }
    base.update(over)
    return json.dumps(base)


def test_download_con_subs_del_creador(monkeypatch, tmp_path):
    meta = _meta_json(subtitles={"es": [{"ext": "vtt"}]})

    def fake_run(cmd, *, capture=True):
        if "--dump-json" in cmd:
            return _cp(stdout=meta)
        # descarga: crear audio + subtitulo
        (tmp_path / "abc123.webm").write_bytes(b"audio")
        (tmp_path / "abc123.es.vtt").write_text("WEBVTT\n", encoding="utf-8")
        return _cp()

    monkeypatch.setattr(dl_mod, "run", fake_run)
    res = download("http://x", tmp_path, lang="es")
    assert res.audio_path.name == "abc123.webm"
    assert res.subtitle_path is not None
    assert res.subtitle_path.name == "abc123.es.vtt"
    assert res.subtitle_is_auto is False
    assert res.title == "Mi Charla"


def test_download_sin_subs(monkeypatch, tmp_path):
    meta = _meta_json()  # sin subtitulos ni auto

    def fake_run(cmd, *, capture=True):
        if "--dump-json" in cmd:
            return _cp(stdout=meta)
        (tmp_path / "abc123.m4a").write_bytes(b"audio")
        return _cp()

    monkeypatch.setattr(dl_mod, "run", fake_run)
    res = download("http://x", tmp_path)
    assert res.audio_path.name == "abc123.m4a"
    assert res.subtitle_path is None


def test_choose_ignora_live_chat():
    # Premiere/directo: su unica "pista" es el chat en vivo (no es texto util).
    meta = {"subtitles": {"live_chat": [{}]}, "automatic_captions": {}, "language": "en"}
    lang, is_auto = _choose_subtitle(meta, requested_lang=None, allow_auto_subs=True)
    assert lang is None and is_auto is False


def test_choose_salta_live_chat_y_toma_subtitulo_real():
    meta = {
        "subtitles": {"live_chat": [{}], "en": [{}]},
        "automatic_captions": {},
        "language": "en",
    }
    lang, is_auto = _choose_subtitle(meta, requested_lang=None, allow_auto_subs=False)
    assert lang == "en" and is_auto is False


def test_download_no_toma_live_chat_json_como_audio(monkeypatch, tmp_path):
    # Regresion: yt-dlp deja `id.live_chat.json` junto al audio; no debe elegirse
    # como pista de audio (ffmpeg no puede con un JSON).
    meta = _meta_json(subtitles={"live_chat": [{"ext": "json"}]})

    def fake_run(cmd, *, capture=True):
        if "--dump-json" in cmd:
            return _cp(stdout=meta)
        (tmp_path / "abc123.live_chat.json").write_text("[]", encoding="utf-8")
        (tmp_path / "abc123.webm").write_bytes(b"audio-real-mucho-mas-grande" * 20)
        return _cp()

    monkeypatch.setattr(dl_mod, "run", fake_run)
    res = download("http://x", tmp_path)
    assert res.audio_path.name == "abc123.webm"
    assert res.subtitle_path is None


def test_download_falla_privado_se_traduce(monkeypatch, tmp_path):
    def fake_run(cmd, *, capture=True):
        return _cp(returncode=1, stderr="ERROR: Private video")

    monkeypatch.setattr(dl_mod, "run", fake_run)
    with pytest.raises(DownloadFailed) as exc:
        download("http://x", tmp_path)
    assert exc.value.cause is FailureCause.PRIVATE
    assert exc.value.url == "http://x"


# ---------- probe_url() (B3) ----------
def test_probe_url_video_unico(monkeypatch):
    rec = json.dumps({"_type": "video", "id": "v1", "title": "Solo", "url": "http://v1"})

    monkeypatch.setattr(dl_mod, "run", lambda cmd, *, capture=True: _cp(stdout=rec))
    info = probe_url("http://v1")
    assert info.is_playlist is False
    assert len(info.entries) == 1
    assert info.entries[0].video_id == "v1"


def test_probe_url_playlist(monkeypatch):
    lines = "\n".join(
        json.dumps({"id": f"v{i}", "title": f"Video {i}", "url": f"http://v{i}",
                    "playlist_title": "Mi Lista"})
        for i in range(1, 4)
    )
    monkeypatch.setattr(dl_mod, "run", lambda cmd, *, capture=True: _cp(stdout=lines))
    info = probe_url("http://list")
    assert info.is_playlist is True
    assert [e.index for e in info.entries] == [1, 2, 3]
    assert info.playlist_title == "Mi Lista"


def test_probe_url_falla_se_traduce(monkeypatch):
    monkeypatch.setattr(
        dl_mod, "run",
        lambda cmd, *, capture=True: _cp(returncode=1, stderr="ERROR: Video unavailable"),
    )
    with pytest.raises(DownloadFailed) as exc:
        probe_url("http://x")
    assert exc.value.cause is FailureCause.UNAVAILABLE


# ---------- cookies llegan a yt-dlp (P8) ----------
def test_probe_url_pasa_cookies_de_navegador(monkeypatch):
    seen: list[list[str]] = []

    def fake_run(cmd, *, capture=True):
        seen.append(cmd)
        return _cp(stdout=json.dumps({"_type": "video", "id": "v1", "url": "http://v1"}))

    monkeypatch.setattr(dl_mod, "run", fake_run)
    probe_url("http://v1", cookies="firefox")
    assert seen and "--cookies-from-browser" in seen[0]
    assert seen[0][seen[0].index("--cookies-from-browser") + 1] == "firefox"


def test_download_pasa_cookies_a_metadata_y_descarga(monkeypatch, tmp_path):
    # Todas las invocaciones de yt-dlp (metadata + descarga) deben llevar las cookies.
    cmds: list[list[str]] = []

    def fake_run(cmd, *, capture=True):
        cmds.append(cmd)
        if "--dump-json" in cmd:
            return _cp(stdout=_meta_json())
        (tmp_path / "abc123.m4a").write_bytes(b"audio")
        return _cp()

    monkeypatch.setattr(dl_mod, "run", fake_run)
    download("http://x", tmp_path, cookies="/ruta/cookies.txt")
    assert cmds, "yt-dlp no fue invocado"
    for cmd in cmds:
        assert "--cookies" in cmd
        assert cmd[cmd.index("--cookies") + 1] == "/ruta/cookies.txt"


def test_download_sin_cookies_no_agrega_flag(monkeypatch, tmp_path):
    cmds: list[list[str]] = []

    def fake_run(cmd, *, capture=True):
        cmds.append(cmd)
        if "--dump-json" in cmd:
            return _cp(stdout=_meta_json())
        (tmp_path / "abc123.m4a").write_bytes(b"audio")
        return _cp()

    monkeypatch.setattr(dl_mod, "run", fake_run)
    download("http://x", tmp_path)
    for cmd in cmds:
        assert "--cookies" not in cmd
        assert "--cookies-from-browser" not in cmd
