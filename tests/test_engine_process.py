"""Tests del target del subproceso `engine_process.run_engine` (P12, D3).

Se llama in-process (sin spawn) con `pipeline.run` monkeypatcheado, asi que no hay
GPU, token ni ffmpeg de por medio: solo se verifica el protocolo de la cola.
"""

from __future__ import annotations

import tempfile
from queue import Empty


def _drain(q) -> list:
    out = []
    while True:
        try:
            out.append(q.get(timeout=1))
        except Empty:
            break
    return out


def _with_tempdir_restored(fn):
    """run_engine muta tempfile.tempdir global; en el test lo restauramos."""
    orig = tempfile.tempdir
    try:
        fn()
    finally:
        tempfile.tempdir = orig


def test_run_engine_local_publica_ok(monkeypatch, tmp_path):
    from multiprocessing import Queue

    from tae.core.models import JobResult, TextSource
    from tae.gui import engine_process

    def fake_run(options, *, on_stage, on_info, on_progress, should_cancel):
        assert should_cancel is None  # el corte ya no es cooperativo (se mata el proceso)
        on_stage("Transcribiendo...")
        on_progress(0.5)
        return JobResult(text_source=TextSource.TRANSCRIBED, language="es")

    monkeypatch.setattr("tae.core.pipeline.run", fake_run)
    q: Queue = Queue()

    _with_tempdir_restored(lambda: engine_process.run_engine(q, "local", object(), tmp_path))

    msgs = _drain(q)
    assert ("stage", "Transcribiendo...") in msgs
    assert ("progress", 0.5) in msgs
    assert msgs[-1][0] == "ok"
    assert isinstance(msgs[-1][1], JobResult)
    # el motor debe haber usado la carpeta temporal que le pasamos
    assert tempfile.tempdir != str(tmp_path)  # restaurado tras la corrida


def test_run_engine_local_taeerror_es_failed(monkeypatch, tmp_path):
    from multiprocessing import Queue

    from tae.core.errors import NoAudioTrack
    from tae.gui import engine_process

    def fake_run(options, **kwargs):
        raise NoAudioTrack("El video no tiene pista de audio: no hay audio que diarizar.")

    monkeypatch.setattr("tae.core.pipeline.run", fake_run)
    q: Queue = Queue()

    _with_tempdir_restored(lambda: engine_process.run_engine(q, "local", object(), tmp_path))

    msgs = _drain(q)
    assert msgs[-1][0] == "failed"
    assert "no hay audio" in msgs[-1][1]


def test_run_engine_error_inesperado_no_suelta_traceback(monkeypatch, tmp_path):
    from multiprocessing import Queue

    from tae.gui import engine_process

    def fake_run(options, **kwargs):
        raise RuntimeError("boom interno")

    monkeypatch.setattr("tae.core.pipeline.run", fake_run)
    q: Queue = Queue()

    _with_tempdir_restored(lambda: engine_process.run_engine(q, "local", object(), tmp_path))

    msgs = _drain(q)
    assert msgs[-1][0] == "failed"
    assert msgs[-1][1].startswith("Error inesperado:")


def test_run_engine_kind_desconocido(tmp_path):
    from multiprocessing import Queue

    from tae.gui import engine_process

    q: Queue = Queue()
    _with_tempdir_restored(lambda: engine_process.run_engine(q, "xxx", object(), tmp_path))

    msgs = _drain(q)
    assert msgs[-1][0] == "failed"
