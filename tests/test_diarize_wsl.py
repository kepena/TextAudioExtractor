"""Tests de core/diarize_wsl.py (P11) con subprocess/Popen mockeados.

No requieren WSL2 real instalado: cubren deteccion de disponibilidad, parseo del
protocolo TAE_* del worker, manejo de resultado ausente/corrupto y cancelacion,
que es lo que puede probarse en CI sin GPU/WSL2.
"""

from __future__ import annotations

import json
import subprocess
import threading
import time

import pytest

from tae.core import diarize_wsl
from tae.core.errors import Cancelled, DiarizationSetupError, DiarizationUnavailable


class _CompletedProcess:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class _FakePipe:
    """Simula stdout/stderr de un Popen: entrega `lines` y luego EOF (""),
    con un retraso opcional SOLO antes de devolver el EOF (para simular un
    proceso que se queda corriendo sin mas output todavia)."""

    def __init__(self, lines=(), eof_delay: float = 0.0):
        self._lines = list(lines)
        self._i = 0
        self._eof_delay = eof_delay

    def readline(self):
        if self._i >= len(self._lines):
            if self._eof_delay:
                time.sleep(self._eof_delay)
            return ""
        line = self._lines[self._i]
        self._i += 1
        return line

    def close(self):
        pass


class _FakeStdin:
    """El codigo real escribe el codigo fuente del worker y cierra stdin."""

    def __init__(self):
        self.written = ""
        self.closed = False

    def write(self, text):
        self.written += text

    def close(self):
        self.closed = True


class _FakeProcess:
    def __init__(self, stdout_lines=(), stderr_lines=(), returncode=0, stdout_eof_delay=0.0):
        self.stdin = _FakeStdin()
        self.stdout = _FakePipe(stdout_lines, eof_delay=stdout_eof_delay)
        self.stderr = _FakePipe(stderr_lines)
        self.returncode = returncode
        self.terminated = False
        self.killed = False

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True

    def wait(self, timeout=None):
        return self.returncode


# --- check_availability ------------------------------------------------------


def test_check_availability_sin_wsl_en_path(monkeypatch):
    monkeypatch.setattr(diarize_wsl.shutil, "which", lambda name: None)
    available, reason = diarize_wsl.check_availability()
    assert available is False
    assert "PATH" in reason


def test_check_availability_timeout(monkeypatch):
    monkeypatch.setattr(diarize_wsl.shutil, "which", lambda name: "wsl.exe")

    def boom(*a, **k):
        raise subprocess.TimeoutExpired(cmd="wsl.exe", timeout=8)

    monkeypatch.setattr(diarize_wsl, "_run_wsl", boom)
    available, reason = diarize_wsl.check_availability()
    assert available is False
    assert "respondio" in reason


def test_check_availability_ok(monkeypatch):
    monkeypatch.setattr(diarize_wsl.shutil, "which", lambda name: "wsl.exe")
    monkeypatch.setattr(
        diarize_wsl, "_run_wsl", lambda *a, **k: _CompletedProcess(returncode=0)
    )
    assert diarize_wsl.check_availability() == (True, "OK")
    assert diarize_wsl.is_available() is True


def test_check_availability_venv_o_gpu_ausente(monkeypatch):
    monkeypatch.setattr(diarize_wsl.shutil, "which", lambda name: "wsl.exe")
    monkeypatch.setattr(
        diarize_wsl,
        "_run_wsl",
        lambda *a, **k: _CompletedProcess(returncode=1, stderr="No module named torch"),
    )
    available, reason = diarize_wsl.check_availability()
    assert available is False
    assert "No module named torch" in reason
    assert diarize_wsl.is_available() is False


# --- _parse_line ---------------------------------------------------------------


def test_parse_line_directivas():
    assert diarize_wsl._parse_line("TAE_PID 4242") == ("TAE_PID", ["4242"])
    assert diarize_wsl._parse_line("TAE_PROGRESS 0.5000") == ("TAE_PROGRESS", ["0.5000"])
    assert diarize_wsl._parse_line("TAE_INFO Cargando modelos...") == (
        "TAE_INFO",
        ["Cargando modelos..."],
    )
    assert diarize_wsl._parse_line("") is None


# --- _quote_wsl_arg --------------------------------------------------------------


def test_quote_wsl_arg_preserva_expansion_de_tilde():
    """shlex.quote comillaria '~/foo', lo que en bash desactiva la expansion de
    '~' (bug real encontrado en k-verify: buscaba una carpeta literal '~')."""
    assert diarize_wsl._quote_wsl_arg("~/.venvs/tae-diarize/bin/python") == (
        "~/.venvs/tae-diarize/bin/python"
    )
    assert diarize_wsl._quote_wsl_arg("~") == "~"


def test_quote_wsl_arg_cita_rutas_normales():
    assert diarize_wsl._quote_wsl_arg("/mnt/c/foo bar/audio.wav") == "'/mnt/c/foo bar/audio.wav'"
    assert diarize_wsl._quote_wsl_arg("/mnt/c/audio.wav") == "/mnt/c/audio.wav"


# --- _to_wsl_path ---------------------------------------------------------------


def test_to_wsl_path_traduce(monkeypatch, tmp_path):
    monkeypatch.setattr(
        diarize_wsl,
        "_run_wsl",
        lambda *a, **k: _CompletedProcess(returncode=0, stdout="/mnt/c/foo/audio.wav\n"),
    )
    assert diarize_wsl._to_wsl_path(tmp_path / "audio.wav") == "/mnt/c/foo/audio.wav"


def test_to_wsl_path_error(monkeypatch, tmp_path):
    monkeypatch.setattr(
        diarize_wsl,
        "_run_wsl",
        lambda *a, **k: _CompletedProcess(returncode=1, stderr="wslpath: no existe"),
    )
    with pytest.raises(RuntimeError, match="wslpath: no existe"):
        diarize_wsl._to_wsl_path(tmp_path / "audio.wav")


# --- transcribe_and_diarize_wsl --------------------------------------------------


def _patch_identity_paths(monkeypatch):
    monkeypatch.setattr(diarize_wsl, "_to_wsl_path", lambda p: str(p))


def test_transcribe_and_diarize_wsl_exito(monkeypatch, tmp_path):
    _patch_identity_paths(monkeypatch)
    result_payload = {
        "language": "es",
        "segments": [
            {"start": 0.0, "end": 1.5, "text": "Hola", "speaker": "SPEAKER_00"},
            {"start": 1.5, "end": 3.0, "text": "Que tal", "speaker": "SPEAKER_01"},
        ],
    }

    def fake_popen(cmd, **kwargs):
        # cmd = ["wsl.exe", "-d", distro, "--", "bash", "-lc", command_string]
        command = cmd[-1]
        out_flag = "--out "
        idx = command.index(out_flag) + len(out_flag)
        out_path = command[idx:].split(" ", 1)[0].strip("'\"")
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(result_payload, fh)
        return _FakeProcess(
            stdout_lines=[
                "TAE_PID 4242\n",
                "TAE_INFO Diarizando en cuda (modelo medium, WSL2).\n",
                "TAE_PROGRESS 0.5000\n",
                "TAE_PROGRESS 1.0000\n",
            ],
            returncode=0,
        )

    monkeypatch.setattr(diarize_wsl.subprocess, "Popen", fake_popen)

    progresses = []
    infos = []
    audio = tmp_path / "audio.wav"
    segments, language = diarize_wsl.transcribe_and_diarize_wsl(
        audio,
        model="medium",
        on_progress=progresses.append,
        on_info=infos.append,
        should_cancel=lambda: False,
    )

    assert language == "es"
    assert [s.speaker for s in segments] == ["SPEAKER_00", "SPEAKER_01"]
    assert segments[0].text == "Hola"
    assert progresses == [0.5, 1.0]
    assert any("cuda" in msg for msg in infos)


def test_transcribe_and_diarize_wsl_resultado_faltante(monkeypatch, tmp_path):
    _patch_identity_paths(monkeypatch)

    def fake_popen(cmd, **kwargs):
        return _FakeProcess(stdout_lines=["TAE_PID 1\n"], returncode=0)

    monkeypatch.setattr(diarize_wsl.subprocess, "Popen", fake_popen)

    with pytest.raises(RuntimeError, match="no genero el archivo"):
        diarize_wsl.transcribe_and_diarize_wsl(tmp_path / "audio.wav", should_cancel=lambda: False)


def test_transcribe_and_diarize_wsl_error_setup(monkeypatch, tmp_path):
    _patch_identity_paths(monkeypatch)

    def fake_popen(cmd, **kwargs):
        return _FakeProcess(
            stdout_lines=["TAE_PID 1\n", "TAE_ERROR setup Falta HF_TOKEN dentro de WSL2\n"],
            returncode=1,
        )

    monkeypatch.setattr(diarize_wsl.subprocess, "Popen", fake_popen)

    with pytest.raises(DiarizationSetupError, match="Falta HF_TOKEN"):
        diarize_wsl.transcribe_and_diarize_wsl(tmp_path / "audio.wav", should_cancel=lambda: False)


def test_transcribe_and_diarize_wsl_error_unavailable(monkeypatch, tmp_path):
    _patch_identity_paths(monkeypatch)

    def fake_popen(cmd, **kwargs):
        return _FakeProcess(
            stdout_lines=["TAE_ERROR unavailable whisperx no instalado en el venv\n"],
            returncode=1,
        )

    monkeypatch.setattr(diarize_wsl.subprocess, "Popen", fake_popen)

    with pytest.raises(DiarizationUnavailable, match="whisperx no instalado"):
        diarize_wsl.transcribe_and_diarize_wsl(tmp_path / "audio.wav", should_cancel=lambda: False)


def test_transcribe_and_diarize_wsl_cancelacion_mata_proceso_interno(monkeypatch, tmp_path):
    _patch_identity_paths(monkeypatch)
    killed_pids = []

    def fake_popen(cmd, **kwargs):
        # El PID llega de inmediato; el EOF tarda para dar tiempo a que el poll
        # loop vea should_cancel() antes de que el "proceso" termine solo.
        return _FakeProcess(
            stdout_lines=["TAE_PID 9999\n"],
            stdout_eof_delay=1.0,
            returncode=0,
        )

    def fake_run_wsl(args, *, timeout):
        if "kill" in args:
            killed_pids.append(args[args.index("kill") + 2])
        return _CompletedProcess(returncode=0)

    monkeypatch.setattr(diarize_wsl.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(diarize_wsl, "_run_wsl", fake_run_wsl)

    cancel_flag = {"value": False}

    def should_cancel():
        return cancel_flag["value"]

    def flip_cancel_soon():
        time.sleep(0.05)
        cancel_flag["value"] = True

    threading.Thread(target=flip_cancel_soon, daemon=True).start()

    with pytest.raises(Cancelled):
        diarize_wsl.transcribe_and_diarize_wsl(tmp_path / "audio.wav", should_cancel=should_cancel)

    # El PID interno (TAE_PID) ya habia llegado antes del corte: debe haberse
    # intentado matar con `kill -9` dentro de la distro (E1), no solo `wsl.exe`.
    assert killed_pids == ["9999"]
