"""Versión 1.1, paquete C: claves nuevas de la configuración (``puntero.fuente`` y ``ojos.*``)."""
import copy
import json

import pytest

from conftest import CAL_SINTETICA, Sim, cfg_prueba
from lycan_face_control import config as C
from lycan_face_control.config import FABRICA, OPCIONES, RANGOS, Configuracion, validar
from lycan_face_control.mapeo import Monitor
from lycan_face_control.ui import opciones as OP
from lycan_face_control.ui import textos as T
from ojos_sinteticos import cal_con_mirada

CLAVES_OJOS = {"suavidad": 3, "puntos_cal": 9, "fijacion_ms": 250, "salto_px": 200, "ganancia_fina": 0.4,
               "permanencia_s": 1.3, "franja": 0.35, "iman": True, "iman_px": 80, "lupa": True}


def test_valores_de_fabrica_y_rangos():
    assert FABRICA["puntero"]["fuente"] == "cabeza"
    assert FABRICA["ojos"] == CLAVES_OJOS
    assert OPCIONES["puntero.fuente"] == ("cabeza", "ojos", "cabeza_y_ojos")
    for k in ("suavidad", "puntos_cal", "fijacion_ms", "salto_px", "ganancia_fina", "permanencia_s", "franja",
              "iman_px"):
        lo, hi = RANGOS[f"ojos.{k}"]
        assert lo <= FABRICA["ojos"][k] <= hi
    # la lupa de los ojos usa las claves del paquete A (sin claves repetidas)
    assert "aumento" not in FABRICA["ojos"] and "zona_px" not in FABRICA["ojos"]


@pytest.mark.parametrize("clave,malo", [
    ("suavidad", 0), ("suavidad", 6), ("fijacion_ms", 50), ("fijacion_ms", 900), ("salto_px", 10),
    ("salto_px", 700), ("ganancia_fina", 0.1), ("ganancia_fina", 1.5), ("permanencia_s", 0.3),
    ("permanencia_s", 3.5), ("franja", 0.05), ("franja", 0.9), ("iman_px", -1), ("iman_px", 300),
    ("puntos_cal", 4), ("puntos_cal", 12),
    ("suavidad", float("nan")), ("salto_px", "200"), ("permanencia_s", None), ("franja", True),
])
def test_valor_fuera_de_rango_o_de_tipo_equivocado_vuelve_al_de_fabrica(clave, malo):
    d = C.por_defecto()
    d["ojos"][clave] = malo
    problemas = []
    v = validar(d, problemas=problemas)
    assert v["ojos"][clave] == FABRICA["ojos"][clave]
    assert problemas


@pytest.mark.parametrize("malo", [1, "si", None])
def test_iman_y_lupa_con_tipo_equivocado_vuelven_a_si(malo):
    d = C.por_defecto()
    d["ojos"]["iman"] = malo
    d["ojos"]["lupa"] = malo
    v = validar(d)
    assert v["ojos"]["iman"] is True and v["ojos"]["lupa"] is True


@pytest.mark.parametrize("n,esperado", [(5, 5), (9, 9), (7, 9), (6, 9), (8.0, 9)])
def test_puntos_cal_solo_5_o_9(n, esperado):
    d = C.por_defecto()
    d["ojos"]["puntos_cal"] = n
    problemas = []
    assert validar(d, problemas=problemas)["ojos"]["puntos_cal"] == esperado
    if esperado != n:
        assert any("puntos_cal" in p for p in problemas)


@pytest.mark.parametrize("malo", ["ojo", "", "OJOS", 3, None, "mouse"])
def test_una_fuente_invalida_vuelve_a_la_cabeza(malo):
    d = C.por_defecto()
    d["puntero"]["fuente"] = malo
    assert validar(d)["puntero"]["fuente"] == "cabeza"


@pytest.mark.parametrize("f", ["ojos", "cabeza_y_ojos"])
def test_las_fuentes_validas_se_conservan(f):
    d = C.por_defecto()
    d["puntero"]["fuente"] = f
    assert validar(d)["puntero"]["fuente"] == f


def test_una_configuracion_1_0_sin_las_claves_queda_con_la_cabeza(tmp_path):
    vieja = C.por_defecto()
    del vieja["ojos"]
    del vieja["puntero"]["fuente"]
    ruta = tmp_path / "config.json"
    ruta.write_text(json.dumps(vieja), encoding="utf-8")
    cfg = Configuracion(ruta)
    datos = cfg.cargar()
    assert datos["puntero"]["fuente"] == "cabeza"
    assert datos["ojos"] == CLAVES_OJOS
    assert cfg.aviso is None


def test_la_calibracion_de_la_mirada_se_guarda_en_el_perfil(tmp_path):
    d = C.por_defecto()
    d["perfiles"]["Principal"]["calibracion"] = cal_con_mirada()
    cfg = Configuracion(tmp_path / "config.json")
    cfg.guardar(d)
    cfg2 = Configuracion(tmp_path / "config.json")
    datos = cfg2.cargar()
    m = datos["perfiles"]["Principal"]["calibracion"]["mirada"]
    assert m["tipo"] == "cuadratico" and m["monitor"] == [0, 0, 1366, 768] and m["camara"] == [640, 480]


# ------------------------------------------------------------------ ojos sin calibrar
def test_ojos_sin_calibrar_usa_la_cabeza_con_aviso_y_no_borra_la_opcion():
    s = Sim(cfg_prueba(**{"puntero.fuente": "ojos"}), calibracion=copy.deepcopy(CAL_SINTETICA))
    assert s.maquina.puntero.fuente == "cabeza" and s.maquina.puntero.fuente_pedida == "ojos"
    s.quieto(0.5)
    assert s.avisos().count("ojos_sin_calibrar") == 1
    assert s.cfg["puntero"]["fuente"] == "ojos"
    # cambiar otra opción no repite el aviso
    s.limpiar()
    s.orden("nueva_config", cfg_prueba(**{"puntero.fuente": "ojos", "puntero.suavidad": 4}))
    s.quieto(0.3)
    assert "ojos_sin_calibrar" not in s.avisos()
    assert T.texto_aviso(type("A", (), {"clave": "ojos_sin_calibrar"})()) == T.t("aviso_ojos_sin_calibrar")


def test_calibracion_de_otra_pantalla_o_camara_usa_la_cabeza():
    cal = cal_con_mirada(monitor=Monitor(0, 0, 1920, 1080))
    s = Sim(cfg_prueba(**{"puntero.fuente": "ojos"}), calibracion=cal)
    assert s.maquina.puntero.fuente == "cabeza"
    cal = cal_con_mirada(camara={"ancho": 1280, "alto": 720})
    s = Sim(cfg_prueba(**{"puntero.fuente": "cabeza_y_ojos"}), calibracion=cal)
    assert s.maquina.puntero.fuente == "cabeza"
    s.quieto(0.2)
    assert "ojos_sin_calibrar" in s.avisos()


def test_con_la_cabeza_no_hay_aviso_ni_camino_de_los_ojos():
    s = Sim(calibracion=cal_con_mirada())
    assert s.maquina.puntero.fuente == "cabeza" and not s.maquina.puntero.usa_ojos
    s.quieto(0.5)
    assert "ojos_sin_calibrar" not in s.avisos()


# ------------------------------------------------------------------ Opciones
def test_las_filas_de_los_ojos_solo_con_una_fuente_con_ojos_y_en_otra_pagina():
    d = C.por_defecto()
    rutas = [c[1] for c in OP.controles("puntero", datos=d)]
    assert "puntero.fuente" in rutas and not any(r.startswith("ojos.") for r in rutas)
    d["puntero"]["fuente"] = "ojos"
    filas = OP.controles("puntero", datos=d)
    rutas = [c[1] for c in filas]
    assert "ojos.permanencia_s" in rutas and "ojos.lupa" in rutas and "ojos.salto_px" not in rutas
    assert "camara_ojos" in rutas                       # 640 × 480: se sugiere 1280 × 720
    paginas = OP.paginas_de("puntero", filas, 6)
    assert all(not c[1].startswith(("ojos.", "camara_")) for c in paginas[0])
    assert paginas[1][0][1] == "camara_ojos"
    d["puntero"]["fuente"] = "cabeza_y_ojos"
    d["camara"]["ancho"], d["camara"]["alto"] = 1280, 720
    rutas = [c[1] for c in OP.controles("puntero", datos=d)]
    assert "ojos.salto_px" in rutas and "ojos.ganancia_fina" in rutas and "camara_ojos" not in rutas


def test_paginas_de_las_demas_pestanas_no_cambian():
    filas = OP.controles("clic")
    assert [len(p) for p in OP.paginas_de("clic", filas, 6)] == [6, len(filas) - 6]
    assert OP.paginas_de("puntero", [], 6) == [[]]


def test_textos_nuevos_sin_tuteo_ni_jerga():
    claves = [k for k in T.TXT if k.startswith(("op_fuente", "op_ojos", "cal_mirada", "aviso_ojos", "ayuda_ojos",
                                                "cal_fuente", "ayuda_sec_ojos"))]
    assert len(claves) >= 30
    for k in claves:
        bajo = " " + T.TXT[k].lower().replace("\n", " ") + " "
        for p in T.TUTEO + T.PALABRAS_PROHIBIDAS:
            assert p not in bajo, (k, p)
    # el texto honesto dice los límites
    assert "3 a 5 cm" in T.t("ayuda_ojos") and "No es tan preciso" in T.t("ayuda_ojos")
