"""Excepciones tipadas del motor.

Cada una lleva un mensaje accionable en espanol: la GUI y la CLI las muestran
directamente al usuario en vez de un traceback (spec §6).
"""


class TaeError(Exception):
    """Base de todos los errores esperados del motor."""


class FfmpegNotFound(TaeError):
    """No se encontro ffmpeg o ffprobe en el sistema (invariante 5)."""


class UnreadableVideo(TaeError):
    """El video no se pudo leer o esta corrupto."""


class NoAudioTrack(TaeError):
    """El video no tiene pista de audio, no hay nada que extraer/transcribir."""


class SubtitleExtractionFailed(TaeError):
    """Fallo la extraccion de la pista de subtitulos incrustada."""


class OutputWriteError(TaeError):
    """No se pudo escribir un archivo de salida (disco lleno o sin permiso)."""


class Cancelled(TaeError):
    """El usuario cancelo el trabajo a mitad del proceso."""


class DiarizationUnavailable(TaeError):
    """whisperX no esta instalado; la diarizacion es una dependencia de setup.

    Se trata como el resto de binarios/paquetes de setup (invariante 5): mensaje
    claro con como instalarlo, no un traceback.
    """

    def __init__(
        self,
        message: str = (
            "La identificacion de hablantes (diarizacion) necesita whisperX, que "
            "no esta instalado. Instalalo con el extra opcional:\n"
            "    uv pip install \"text-audio-extractor[diarize]\"\n"
            "(o `pip install whisperx`). Es una descarga grande porque arrastra "
            "torch y pyannote."
        ),
    ) -> None:
        super().__init__(message)


class DiarizationSetupError(TaeError):
    """Falta el token de HuggingFace o no se aceptaron los terminos del modelo.

    Los pesos de diarizacion (pyannote, via whisperX) se descargan una vez tras
    aceptar los terminos en HuggingFace con un token gratuito. Sin eso no se puede
    diarizar; se avisa con instrucciones (invariante 5), sin traceback.
    """

    def __init__(
        self,
        message: str = (
            "No pude configurar la diarizacion. Para identificar hablantes:\n"
            "  1. Crea una cuenta gratis en https://huggingface.co y genera un "
            "token de acceso en https://huggingface.co/settings/tokens\n"
            "  2. Acepta los terminos de los modelos "
            "https://huggingface.co/pyannote/speaker-diarization-3.1 y "
            "https://huggingface.co/pyannote/segmentation-3.0\n"
            "  3. Exporta el token en la variable de entorno HF_TOKEN "
            "(o HUGGINGFACE_TOKEN) y vuelve a intentarlo.\n"
            "En runtime nada sale a la nube: el token solo autoriza la descarga "
            "inicial de los pesos."
        ),
    ) -> None:
        super().__init__(message)
