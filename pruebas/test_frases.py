"""Parte 4: frases rápidas (sección 7.4)."""
from __future__ import annotations

import json

import pytest

from lycan_face_control.frases import (FABRICA, MAX_CATEGORIAS, MAX_FRASES, Frases, aplicar_genero, texto_final,
                                       validar)


def test_fabrica_tiene_lo_necesario():
    f = Frases()
    nombres = f.nombres()
    assert nombres[0] == "Rápidas"
    for n in ("Básicas", "Necesidades", "Dolor", "Urgencia", "Afecto"):
        assert n in nombres
    textos = [fr["texto"] for c in f.categorias for fr in c["frases"]]
    for esperado in ("Sí", "No", "Gracias", "Tengo sed", "Tengo dolor", "Cambiarme de posición",
                     "¡Ayuda, llamen a alguien!", "Llamar a {cuidador}"):
        assert esperado in textos
    urg = [fr for fr in f.frases(nombres.index("Urgencia")) if fr["urgente"]]
    assert any(fr["texto"].startswith("¡Ayuda") for fr in urg)
    assert [fr["texto"] for fr in f.rapidas()] == ["¡Ayuda, llamen a alguien!", "Tengo sed", "Tengo dolor",
                                                   "Cambiarme de posición", "Llamar a {cuidador}"]
    assert f.rapidas()[0]["urgente"] is True               # la urgencia, en la fila rápida
    validar(FABRICA)                                        # la de fábrica es válida


def test_cuidador_y_genero():
    assert texto_final("Llamar a {cuidador}", cuidador="Marta") == "Llamar a Marta"
    assert texto_final("Llamar a {cuidador}", cuidador="  ") == "Llamar a alguien"
    t = "{Estoy cansado|Estoy cansada|Siento cansancio}"
    assert aplicar_genero(t, "masculino") == "Estoy cansado"
    assert aplicar_genero(t, "femenino") == "Estoy cansada"
    assert aplicar_genero(t, "neutro") == "Siento cansancio"
    assert aplicar_genero("Estoy cansad{o|a}", "femenino") == "Estoy cansada"
    assert aplicar_genero("Estoy cansad{o|a}", "neutro") == "Estoy cansado"
    assert aplicar_genero("Sin grupos {cuidador}", "femenino") == "Sin grupos {cuidador}"


def test_editar_guardar_y_releer(tmp_path):
    r = tmp_path / "frases.json"
    f = Frases(r)
    f.cargar()
    assert f.agregar(0, "Quiero ver a mis nietos")
    assert f.cambiar(0, 0, "Muchas gracias", urgente=False)
    assert f.mover(0, 0, +1) == 1
    assert f.borrar(0, 2)
    assert f.agregar_categoria("Familia")
    assert f.renombrar_categoria(len(f.nombres()) - 1, "Mi familia")
    assert f.guardar()
    g = Frases(r)
    g.cargar()
    assert g.datos == f.datos
    assert "Mi familia" in g.nombres()
    assert g.borrar_categoria(len(g.nombres()) - 1)
    g.restaurar()
    assert g.datos == FABRICA


def test_validar_textos_y_tipos(tmp_path):
    f = Frases()
    assert not f.agregar(0, "")
    assert not f.agregar(0, "   ")
    assert not f.agregar(0, "x" * 201)
    assert not f.agregar(0, "dos\nlíneas")
    assert not f.agregar(99, "categoría que no existe")
    assert not f.cambiar(0, 999, "nada")
    assert not f.agregar_categoria("")
    probs = []
    d = validar({"categorias": [{"nombre": "Bien", "frases": ["Hola", {"texto": ""}, {"texto": 5},
                                                               {"texto": "Ok", "urgente": "sí"}]},
                                {"nombre": "", "frases": []}, "rara"]}, probs)
    assert d["categorias"] == [{"nombre": "Bien", "frases": [{"texto": "Hola", "urgente": False},
                                                             {"texto": "Ok", "urgente": False}]}]
    assert len(probs) >= 4
    with pytest.raises(ValueError):
        validar({"categorias": []})
    with pytest.raises(ValueError):
        validar([1, 2])


def test_limites():
    d = {"categorias": [{"nombre": f"C{i}", "frases": [f"f{j}" for j in range(MAX_FRASES + 5)]}
                        for i in range(MAX_CATEGORIAS + 3)]}
    v = validar(d)
    assert len(v["categorias"]) == MAX_CATEGORIAS
    assert all(len(c["frases"]) == MAX_FRASES for c in v["categorias"])
    f = Frases()
    f.datos = v
    assert not f.agregar(0, "una más")
    assert not f.agregar_categoria("otra")
    f.datos = {"version": 1, "categorias": [{"nombre": "Única", "frases": []}]}
    assert not f.borrar_categoria(0)                       # siempre queda una


def test_archivo_danado_se_renombra(tmp_path):
    r = tmp_path / "frases.json"
    r.write_text("[[[no sirve", encoding="utf-8")
    f = Frases(r)
    f.cargar()
    assert f.aviso == "frases_danadas" and f.datos == FABRICA
    assert not r.exists() and list(tmp_path.glob("frases.dañado-*.json"))
    r.write_text(json.dumps({"categorias": "no es lista"}), encoding="utf-8")
    f.cargar()
    assert f.aviso == "frases_danadas"
