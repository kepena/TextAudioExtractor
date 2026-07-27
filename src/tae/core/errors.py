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
