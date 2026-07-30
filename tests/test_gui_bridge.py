"""Tests del puente GUI<->subproceso (P12, D1 y D2).

D1: traduccion de un mensaje de la cola a la senal Qt correcta (sin proceso real).
D2: matar un subproceso real corta en <2 s y limpia la carpeta temporal.
"""

from __future__ import annotations

import shutil
import tempfile
import time
from pathlib import Path

import pytest

from tae.gui.worker import _EngineBridge


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtCore import QCoreApplication

    app = QCoreApplication.instance() or QCoreApplication([])
    yield app


def _bridge_with_recorder():
    bridge = _EngineBridge(options=None)
    events: list = []
    bridge.stage.connect(lambda m: events.append(("stage", m)))
    bridge.info.connect(lambda m: events.append(("info", m)))
    bridge.progress.connect(lambda f: events.append(("progress", f)))
    bridge.item.connect(lambda p, t, ti: events.append(("item", p, t, ti)))
    bridge.finished_ok.connect(lambda r: events.append(("ok", r)))
    bridge.finished_batch.connect(lambda r: events.append(("batch", r)))
    bridge.failed.connect(lambda m: events.append(("failed", m)))
    bridge.cancelled.connect(lambda: events.append(("cancelled",)))
    return bridge, events


def test_dispatch_no_terminales(qapp):
    bridge, events = _bridge_with_recorder()
    assert bridge._dispatch(("stage", "Transcribiendo...")) is False
    assert bridge._dispatch(("info", "usando CPU")) is False
    assert bridge._dispatch(("progress", 0.5)) is False
    assert bridge._dispatch(("item", 1, 3, "video A")) is False
    assert events == [
        ("stage", "Transcribiendo..."),
        ("info", "usando CPU"),
        ("progress", 0.5),
        ("item", 1, 3, "video A"),
    ]


def test_dispatch_terminales(qapp):
    bridge, events = _bridge_with_recorder()
    assert bridge._dispatch(("ok", "R")) is True
    assert bridge._dispatch(("batch", "B")) is True
    assert bridge._dispatch(("failed", "boom")) is True
    assert ("ok", "R") in events
    assert ("batch", "B") in events
    assert ("failed", "boom") in events


def test_dispatch_desconocido_se_ignora(qapp):
    bridge, events = _bridge_with_recorder()
    assert bridge._dispatch(("zzz", "algo")) is False
    assert events == []


# ---- D2: terminar un subproceso real ----

def _sleeper(queue, kind, options, job_tmp):
    """Target de prueba: publica progreso y se duerme; simula una etapa larga."""
    import time as _t

    queue.put(("progress", 0.1))
    _t.sleep(30)
    queue.put(("ok", "no deberia llegar"))


def test_terminar_subproceso_es_inmediato_y_limpia():
    from multiprocessing import Process, Queue

    queue: Queue = Queue()
    job_tmp = Path(tempfile.mkdtemp(prefix="tae_job_test_"))
    proc = Process(target=_sleeper, args=(queue, "local", None, job_tmp))
    proc.start()
    try:
        # esperar a que el hijo arranque y publique el primer progreso
        assert queue.get(timeout=15) == ("progress", 0.1)

        t0 = time.time()
        proc.terminate()
        proc.join(3)
        elapsed = time.time() - t0

        assert not proc.is_alive(), "el proceso no murio tras terminate()"
        assert elapsed < 2, f"terminate tardo {elapsed:.2f}s (>2s)"
    finally:
        if proc.is_alive():
            proc.kill()
            proc.join(2)
        shutil.rmtree(job_tmp, ignore_errors=True)

    assert not job_tmp.exists()
