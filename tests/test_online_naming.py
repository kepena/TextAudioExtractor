"""Nombres de salida seguros: saneo, colisiones y numeracion (C3)."""

from tae.online.naming import numbered, resolve_collisions, safe_stem


def test_safe_stem_reemplaza_caracteres_invalidos():
    assert safe_stem('a/b:c*d?e"f<g>h|i') == "a_b_c_d_e_f_g_h_i"


def test_safe_stem_colapsa_espacios_y_recorta_puntos():
    assert safe_stem("  Hola   mundo .. ") == "Hola mundo"


def test_safe_stem_vacio_o_reservado_usa_fallback():
    assert safe_stem("///") == "video"
    assert safe_stem("   ") == "video"
    assert safe_stem("CON") == "video"  # nombre reservado en Windows
    assert safe_stem("", fallback="clip") == "clip"


def test_safe_stem_limita_largo():
    assert len(safe_stem("x" * 300)) <= 120


def test_resolve_collisions_aplica_sufijos():
    used: set[str] = set()
    assert resolve_collisions("charla", used) == "charla"
    assert resolve_collisions("charla", used) == "charla_2"
    assert resolve_collisions("charla", used) == "charla_3"
    # otro distinto no colisiona
    assert resolve_collisions("otra", used) == "otra"


def test_resolve_collisions_ignora_mayusculas():
    used: set[str] = set()
    assert resolve_collisions("Charla", used) == "Charla"
    # 'charla' colisiona con 'Charla' en filesystem Windows
    assert resolve_collisions("charla", used) == "charla_2"


def test_numbered_prefija_con_indice():
    assert numbered(1, "titulo") == "01_titulo"
    assert numbered(12, "titulo") == "12_titulo"
    assert numbered(3, "titulo", width=3) == "003_titulo"
