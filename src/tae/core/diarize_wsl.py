"""Diarizacion de hablantes en GPU vía WSL2 (P11, camino GPU real en Windows).

`torchaudio` con CUDA en Windows enruta por `k2`, que no tiene ruedas para esa
plataforma (ver docs/pendientes.md P11), asi que la diarizacion en GPU no es
viable dentro de Windows. Este modulo cruza la frontera: lanza
`scripts/wsl_diarize_worker.py` dentro de WSL2 (Ubuntu, donde `k2` si tiene
ruedas) como un subproceso `wsl.exe`, y traduce su progreso/resultado de vuelta
al mismo contrato que `diarize.transcribe_and_diarize` (misma firma, mismo
`tuple[list[Segment], str | None]`), para que `pipeline.py` pueda intercambiarlas
sin logica adicional.

Invariantes:
- Todo local (invariante 1): WSL2 es la misma maquina, no sale nada a la nube
  salvo la descarga inicial de pesos (autorizada por el token de HF, igual que en
  Windows).
- Degradar sin bloquear (invariante 3): `check_availability()`/`is_available()`
  nunca lanzan excepcion; cualquier fallo de deteccion (wsl.exe ausente, distro no
  responde, venv sin GPU) devuelve `False` para que `pipeline.py` caiga al camino
  CPU existente (`diarize.py`) sin intervencion del usuario.
- Import diferido de nada especial aqui: este modulo solo usa `subprocess`, no
  torch/whisperx (esos viven del lado WSL2, en el venv de
  `scripts/wsl_diarize_setup.sh`).

No confundir con `diarize.py`: aquel corre whisperx DENTRO del proceso Windows
(CPU); este modulo nunca importa whisperx, solo orquesta un subproceso externo.
"""

from __future__ import annotations

import json
import os
import queue
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
from collections.abc import Callable
from pathlib import Path

from .errors import Cancelled, DiarizationSetupError, DiarizationUnavailable
from .models import Segment

_DEFAULT_DISTRO = "Ubuntu"
_DEFAULT_VENV = "~/.venvs/tae-diarize"
# `import torch` con CUDA puede tardar >8s en cargar la primera vez (verificado
# en esta maquina: ~8s ya no alcanzaba, 30s si). Este chequeo corre una vez por
# job de diarizacion, no por tick de progreso, asi que un timeout generoso no
# cuesta latencia perceptible en el caso exitoso.
_AVAILABILITY_TIMEOUT = 30.0
_WSLPATH_TIMEOUT = 10.0
_POLL_INTERVAL = 0.2
_KILL_TIMEOUT = 5.0

def _worker_script_path() -> Path:
    """Ruta a scripts/wsl_diarize_worker.py.

    En un build congelado (PyInstaller, ver packaging/) el arbol de fuente del
    repo no existe: el script de build copia wsl_diarize_worker.py junto al
    ejecutable, y es ahi donde hay que buscarlo. En modo dev sigue subiendo
    desde este archivo hasta la raiz del repo, como antes.
    """
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", None) or Path(sys.executable).parent)
        return base / "wsl_diarize_worker.py"
    return Path(__file__).resolve().parents[3] / "scripts" / "wsl_diarize_worker.py"


_WORKER_SCRIPT = _worker_script_path()


def _distro_name() -> str:
    return os.environ.get("TAE_WSL_DISTRO", _DEFAULT_DISTRO).strip()


def _venv_dir() -> str:
    return os.environ.get("TAE_WSL_DIARIZE_VENV", _DEFAULT_VENV).strip()


def _wsl_env() -> dict:
    # WSL_UTF8=1 evita que wsl.exe emita UTF-16LE (que se ve como texto
    # espaciado/corrupto si se decodifica como texto normal).
    env = dict(os.environ)
    env["WSL_UTF8"] = "1"
    return env


def _quote_wsl_arg(arg: str) -> str:
    """Como `shlex.quote`, pero preserva la expansion de `~` inicial.

    `shlex.quote("~/foo")` envuelve el string en comillas simples porque `~` no
    esta en su set de caracteres seguros -- y las comillas simples DESACTIVAN la
    expansion de `~` en bash, asi que `~/.venvs/...` termina siendo un nombre de
    carpeta literal ("~") en vez de expandirse a $HOME. Aqui se deja el `~`
    inicial sin comillas (bash lo expande igual) y se cita solo el resto.
    """
    if arg == "~" or arg.startswith("~/"):
        rest = arg[1:]
        return "~" + (shlex.quote(rest) if rest else "")
    return shlex.quote(arg)


def _run_wsl(args: list[str], *, timeout: float) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["wsl.exe", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        env=_wsl_env(),
    )


# NOTA sobre `-e`/`--exec`: sin el, `wsl.exe -d <distro> -- <comando>` reenvia el
# comando a traves de una capa de "traduccion de rutas + shell por defecto" que
# CORROMPE el argumento -- verificado en k-verify (2026-07-31): las barras
# invertidas de una ruta Windows (`C:\Users\...`) desaparecen, y toda referencia
# `$VAR` dentro del comando se sustituye por vacio ANTES de llegar al shell real
# (asi que `bash -lc 'X=hi; echo $X'` imprimia vacio). `-e` ejecuta el comando
# directo, sin esa capa, y ambos bugs desaparecen. Por eso TODAS las llamadas a
# wsl.exe en este modulo usan `-e` en vez de `--`.


def check_availability(timeout: float = _AVAILABILITY_TIMEOUT) -> tuple[bool, str]:
    """(disponible, motivo). Nunca lanza excepcion — cualquier fallo es "no disponible".

    Comprueba en un solo paso: `wsl.exe` en PATH, la distro responde, el venv de
    diarizacion existe ahi, torch ve la GPU dentro de esa distro, y `ffmpeg` esta
    instalado ahi (whisperx.load_audio lo necesita; es un binario de sistema
    aparte del venv, ver invariante 5 y scripts/wsl_diarize_setup.sh).
    """
    if shutil.which("wsl.exe") is None and shutil.which("wsl") is None:
        return False, "wsl.exe no esta en el PATH de Windows."

    distro = _distro_name()
    python_bin = f"{_venv_dir()}/bin/python"
    check_cmd = (
        f"{_quote_wsl_arg(python_bin)} -c "
        "\"import shutil, torch, sys; "
        "sys.exit(0 if torch.cuda.is_available() and shutil.which('ffmpeg') else 1)\""
    )
    try:
        proc = _run_wsl(["-d", distro, "-e", "bash", "-lc", check_cmd], timeout=timeout)
    except FileNotFoundError:
        return False, "wsl.exe no esta disponible en este sistema."
    except subprocess.TimeoutExpired:
        return False, f"wsl.exe no respondio en {timeout:.0f}s (distro '{distro}')."
    except OSError as exc:
        return False, f"No se pudo invocar wsl.exe: {exc}"

    if proc.returncode == 0:
        return True, "OK"

    detail = (proc.stderr or proc.stdout or "").strip()
    return False, (
        f"GPU vía WSL2 no disponible (distro '{distro}', venv '{_venv_dir()}', "
        f"codigo {proc.returncode}). "
        + (f"Detalle: {detail[:300]}" if detail else "Revisa scripts/wsl_diarize_setup.sh.")
    )


def is_available() -> bool:
    return check_availability()[0]


def _to_wsl_path(win_path: Path) -> str:
    proc = _run_wsl(
        ["-d", _distro_name(), "-e", "wslpath", "-a", str(win_path)], timeout=_WSLPATH_TIMEOUT
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"No se pudo traducir la ruta '{win_path}' a WSL2: {proc.stderr.strip()}"
        )
    return proc.stdout.strip()


def _drain(pipe, sink: queue.Queue) -> None:
    try:
        for line in iter(pipe.readline, ""):
            sink.put(line)
    finally:
        sink.put(None)  # centinela de EOF
        pipe.close()


def _kill_tree(process: subprocess.Popen, distro: str, inner_pid: str | None) -> None:
    """Mata tanto `wsl.exe` en Windows como el proceso real dentro de la distro.

    Matar solo `wsl.exe` no basta: reenvia la ejecucion al init de la distro, asi
    que el proceso Python que quedo corriendo adentro puede sobrevivir (mismo tipo
    de problema que P12 resolvio para el subproceso Windows, cruzando ahora la
    frontera de la VM de WSL2).
    """
    try:
        process.terminate()
    except Exception:
        pass
    if inner_pid:
        try:
            _run_wsl(["-d", distro, "-e", "kill", "-9", str(inner_pid)], timeout=_KILL_TIMEOUT)
        except Exception:
            pass
    try:
        process.wait(timeout=_KILL_TIMEOUT)
    except Exception:
        try:
            process.kill()
        except Exception:
            pass


def _parse_line(line: str) -> tuple[str, list[str]] | None:
    line = line.rstrip("\n").rstrip("\r")
    if not line:
        return None
    parts = line.split(" ", 1)
    directive = parts[0]
    rest = parts[1] if len(parts) > 1 else ""
    return directive, [rest]


def transcribe_and_diarize_wsl(
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
    """Igual contrato que `diarize.transcribe_and_diarize`, pero corriendo en GPU
    dentro de WSL2. Asumir ya confirmado `is_available()` antes de llamar esto —
    aqui un fallo NO degrada a CPU (esa decision ya se tomo antes de invocar este
    camino), se relanza como error claro.
    """
    distro = _distro_name()
    python_bin = f"{_venv_dir()}/bin/python"

    with tempfile.TemporaryDirectory(dir=audio.parent) as tmp:
        out_json = Path(tmp) / "result.json"

        # El audio y el JSON de salida viven bajo el temp de Windows (unidad C:,
        # montada por WSL2 en /mnt/c), asi que wslpath los traduce sin problema.
        # El WORKER SCRIPT no se traduce por ruta: el repo puede vivir en una
        # unidad que WSL2 no automonta (ej. una unidad compartida de red/Drive,
        # confirmado en esta maquina que G: no aparece en /mnt), asi que en vez de
        # traducir su ruta se envia su codigo fuente por stdin a `python -`
        # (invariante 5: no asumir de donde se ejecuta el repo).
        audio_wsl = _to_wsl_path(audio)
        out_wsl = _to_wsl_path(out_json)
        worker_source = _WORKER_SCRIPT.read_text(encoding="utf-8")

        cmd_parts = [
            _quote_wsl_arg(python_bin),
            "-",
            "--audio", shlex.quote(audio_wsl),
            "--out", shlex.quote(out_wsl),
            "--model", shlex.quote(model),
        ]
        if language:
            cmd_parts += ["--language", shlex.quote(language)]
        if num_speakers is not None:
            cmd_parts += ["--speakers", str(int(num_speakers))]
        command = " ".join(cmd_parts)

        process = subprocess.Popen(
            ["wsl.exe", "-d", distro, "-e", "bash", "-lc", command],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=_wsl_env(),
        )
        process.stdin.write(worker_source)
        process.stdin.close()

        out_q: queue.Queue = queue.Queue()
        out_thread = threading.Thread(target=_drain, args=(process.stdout, out_q), daemon=True)
        out_thread.start()

        # stderr se drena aparte (hilo propio) solo para no bloquear el pipe y
        # tener contexto de diagnostico si el proceso falla sin TAE_ERROR.
        process_stderr_holder: list[str] = []

        def _drain_stderr() -> None:
            try:
                for line in iter(process.stderr.readline, ""):
                    process_stderr_holder.append(line)
            except Exception:
                pass

        err_thread = threading.Thread(target=_drain_stderr, daemon=True)
        err_thread.start()

        inner_pid: str | None = None
        last_error: tuple[str, str] | None = None
        eof = False

        while not eof:
            try:
                line = out_q.get(timeout=_POLL_INTERVAL)
            except queue.Empty:
                if should_cancel and should_cancel():
                    _kill_tree(process, distro, inner_pid)
                    raise Cancelled("Diarizacion cancelada por el usuario.") from None
                continue

            if line is None:
                eof = True
                break

            parsed = _parse_line(line)
            if parsed is None:
                continue
            directive, rest = parsed
            value = rest[0]

            if directive == "TAE_PID":
                inner_pid = value.strip()
            elif directive == "TAE_INFO":
                if on_info:
                    on_info(value)
            elif directive == "TAE_PROGRESS":
                if on_progress:
                    try:
                        on_progress(float(value))
                    except ValueError:
                        pass
            elif directive == "TAE_ERROR":
                cat_and_msg = value.split(" ", 1)
                category = cat_and_msg[0] if cat_and_msg else "error"
                message = cat_and_msg[1] if len(cat_and_msg) > 1 else ""
                last_error = (category, message)

        out_thread.join(timeout=_KILL_TIMEOUT)
        err_thread.join(timeout=_KILL_TIMEOUT)
        returncode = process.wait(timeout=_KILL_TIMEOUT)

        if returncode != 0:
            stderr_tail = "".join(process_stderr_holder)[-500:].strip()
            if last_error is not None:
                category, message = last_error
                if category == "unavailable":
                    raise DiarizationUnavailable(message) if message else DiarizationUnavailable()
                if category == "setup":
                    raise DiarizationSetupError(detail=message or None)
                raise RuntimeError(f"Diarizacion en WSL2 fallo: {message}")
            raise RuntimeError(
                f"Diarizacion en WSL2 termino con codigo {returncode} sin detalle. "
                + (f"stderr: {stderr_tail}" if stderr_tail else "")
            )

        if not out_json.exists():
            raise RuntimeError(
                "Diarizacion en WSL2 termino sin error pero no genero el archivo de "
                "resultado esperado."
            )
        try:
            data = json.loads(out_json.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise RuntimeError(f"Resultado de diarizacion en WSL2 corrupto: {exc}") from exc

        segments = [
            Segment(
                start=float(item["start"]),
                end=float(item["end"]),
                text=item["text"],
                speaker=item.get("speaker"),
            )
            for item in data.get("segments") or []
        ]
        return segments, data.get("language")
