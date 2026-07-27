"""Modulo online (YouTube/plataformas) — capa aislada sobre el motor.

Toda la orquestacion de descarga vive aqui; el core no depende de este paquete
(invariante 4). Usa `yt-dlp` como binario del sistema (invariante 5) y reutiliza
las primitivas del motor (`transcribe`, `outputs`, `audio`) para producir texto
plano, `.srt` y audio a partir de una URL.
"""
