"""Nombres de archivo seguros para las salidas del modulo online.

Los titulos de YouTube traen caracteres invalidos para el filesystem de Windows
(`\\ / : * ? " < > |`), colisionan entre si dentro de una playlist y necesitan un
prefijo numerico que respete el orden (spec §5.2). Aqui viven las tres piezas.
"""

from __future__ import annotations

import re

# Caracteres invalidos en nombres de archivo de Windows + control chars.
_INVALID_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
# Windows no permite estos nombres reservados (con o sin extension).
_RESERVED = {
    "con", "prn", "aux", "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}


def safe_stem(title: str, *, fallback: str = "video") -> str:
    """Convierte un titulo en un stem valido para el filesystem.

    Reemplaza caracteres invalidos por `_`, colapsa espacios, recorta puntos y
    espacios de los extremos (Windows los prohibe al final), y limita el largo.
    Si queda vacio o es un nombre reservado, usa `fallback`.
    """
    stem = _INVALID_RE.sub("_", title)
    stem = re.sub(r"\s+", " ", stem).strip()
    stem = stem.strip(". ")
    stem = stem[:120].strip(". ")
    # Si tras el saneo no queda ningun caracter alfanumerico (solo `_`/vacio) o es
    # un nombre reservado de Windows, usar el fallback.
    if not any(c.isalnum() for c in stem) or stem.lower() in _RESERVED:
        return fallback
    return stem


def resolve_collisions(stem: str, used: set[str]) -> str:
    """Devuelve un stem unico frente a `used`, aplicando sufijos `_2`, `_3`, ...

    Compara sin distinguir mayusculas (el filesystem de Windows no las distingue)
    y registra el resultado en `used` para la siguiente llamada.
    """
    candidate = stem
    n = 2
    while candidate.lower() in used:
        candidate = f"{stem}_{n}"
        n += 1
    used.add(candidate.lower())
    return candidate


def numbered(index: int, stem: str, *, width: int = 2) -> str:
    """Prefija el stem con el indice de playlist: `01_titulo` (spec §5.2)."""
    return f"{index:0{width}d}_{stem}"
