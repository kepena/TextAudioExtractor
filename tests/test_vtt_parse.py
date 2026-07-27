"""Parseo de WebVTT a Segment[] (B1), sin romper el parser SRT existente."""

from tae.core.subtitles import parse_srt, parse_vtt

VTT = """WEBVTT
Kind: captions
Language: es

00:00:01.000 --> 00:00:04.000 align:start position:0%
<c>Hola</c> mundo

00:00:04.500 --> 00:00:07.250
Segunda&nbsp;linea con <00:00:05.000><c> tags</c> inline

NOTE esto es un comentario que debe ignorarse

00:00:08.000 --> 00:00:10.000
Tercera linea
"""


def test_parse_vtt_extrae_segmentos_limpios():
    segs = parse_vtt(VTT)
    assert len(segs) == 3
    assert segs[0].start == 1.0
    assert segs[0].end == 4.0
    assert segs[0].text == "Hola mundo"  # tags <c> removidos
    # entidad HTML decodificada y tags de tiempo inline removidos
    assert segs[1].text == "Segunda linea con tags inline"
    assert segs[2].text == "Tercera linea"


def test_parse_vtt_ignora_header_y_notes():
    segs = parse_vtt(VTT)
    # El header WEBVTT y el bloque NOTE no producen segmentos.
    textos = [s.text for s in segs]
    assert not any("WEBVTT" in t for t in textos)
    assert not any("comentario" in t for t in textos)


def test_parse_vtt_vacio_devuelve_lista_vacia():
    assert parse_vtt("WEBVTT\n\n") == []
    assert parse_vtt("") == []


def test_parser_srt_sigue_intacto():
    srt = "1\n00:00:01,000 --> 00:00:02,000\nHola\n"
    segs = parse_srt(srt)
    assert len(segs) == 1
    assert segs[0].text == "Hola"
