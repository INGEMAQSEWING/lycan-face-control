"""Parte 4: predicción de palabras sin internet (sección 7.3)."""
from __future__ import annotations

import json

import pytest

from lycan_face_control.prediccion import (MAX_PALABRAS, MAX_PARES, INICIOS, Prediccion, cargar_lista,
                                           palabras_de)


@pytest.fixture(scope="module")
def lista():
    return cargar_lista()


def test_la_lista_trae_20000_palabras(lista):
    assert 19000 <= len(lista) <= 20100
    assert lista[0][0] == "de" and lista[0][1] > lista[1000][1]


def test_sab_sugiere_sabana_y_cob_sugiere_cobija(lista):
    p = Prediccion(lista)
    s = p.sugerir("sab")
    assert len(s) == 5 and "sábana" in s
    assert "cobija" in p.sugerir("cob")
    assert "BiPAP" in p.sugerir("bip")
    assert "oxígeno" in p.sugerir("oxi")                   # sin tildes al comparar
    assert p.sugerir("SAB") == s                            # sin importar mayúsculas
    assert p.sugerir("zzzzqq") == []


def test_no_repite_lo_ya_escrito(lista):
    p = Prediccion(lista)
    assert "casa" not in p.sugerir("casa")


def test_aprende_y_sube_su_puesto(lista, tmp_path):
    r = tmp_path / "palabras_usuario.json"
    p = Prediccion(lista, ruta_usuario=r)
    antes = p.sugerir("fis")
    assert "fisioterapia" not in antes
    p.aprender("Hoy viene la fisioterapia")
    s = p.sugerir("fis")
    assert "fisioterapia" in s                               # puesto reservado a las palabras propias
    puesto = s.index("fisioterapia")
    for _ in range(40):
        p.aprender("Hoy viene la fisioterapia")
    s = p.sugerir("fis")
    assert s.index("fisioterapia") < puesto or puesto == 0
    assert s[0] == "fisioterapia"
    assert p.guardar() and r.exists()
    p2 = Prediccion(lista, ruta_usuario=r)
    assert p2.sugerir("fis")[0] == "fisioterapia"


def test_siguiente_palabra_por_pares(lista):
    p = Prediccion(lista)
    assert p.sugerir("", None)[:5] == list(INICIOS)
    for _ in range(4):
        p.aprender_par("quiero", "agua")
    p.aprender_par("quiero", "dormir")
    s = p.sugerir("", "Quiero")
    assert s[:2] == ["agua", "dormir"]
    assert p.sugerir("a", "quiero")[0] == "agua"


def test_aprender_apagado_no_guarda(lista, tmp_path):
    r = tmp_path / "p.json"
    p = Prediccion(lista, ruta_usuario=r, aprender=False)
    p.aprender("palabra secreta")
    p.aprender_par(None, "otra")
    assert p.usos == {}
    assert p.guardar() and not r.exists()


def test_archivo_danado_se_renombra_y_sigue(lista, tmp_path):
    r = tmp_path / "palabras_usuario.json"
    r.write_text("{esto no es json", encoding="utf-8")
    p = Prediccion(lista, ruta_usuario=r)
    assert p.aviso == "palabras_danadas"
    assert not r.exists()
    assert list(tmp_path.glob("palabras_usuario.dañado-*.json"))
    p.aprender("hola mundo")
    assert p.guardar() and r.exists()
    # datos raros dentro de un JSON válido: se descartan sin fallar
    r.write_text(json.dumps({"palabras": {"bien": [3, 1], "mal1": [1, 1], "x" * 50: 1, "raro": "no"},
                             "pares": {"a b": 2, "malo": 1, "c d": -1}}), encoding="utf-8")
    p = Prediccion(lista, ruta_usuario=r)
    assert p.usos == {"bien": 3} and p.pares == {"a b": 2}


def test_limite_de_tamano(lista):
    p = Prediccion(lista[:100])
    for i in range(MAX_PALABRAS + 300):
        p.aprender_par(None, "pal" + "".join(chr(97 + int(d)) for d in str(i)))
    assert len(p.usos) <= MAX_PALABRAS
    for i in range(MAX_PARES + 200):
        p.pares[f"a{i} b"] = 1
    p._recortar()
    assert len(p.pares) <= MAX_PARES


def test_olvidar(lista, tmp_path):
    r = tmp_path / "p.json"
    p = Prediccion(lista, ruta_usuario=r)
    p.aprender("algo privado")
    p.guardar()
    assert r.exists()
    assert p.olvidar()
    assert p.usos == {} and not r.exists()


def test_palabras_de():
    assert palabras_de("¿Cómo está, Ñandú? 3 veces") == ["Cómo", "está", "Ñandú", "veces"]
