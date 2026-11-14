"""Versión 1.1, paquete A: claves nuevas de la configuración y la velocidad del puntero
(velocidad 1 a 10 que escribe sens_x, sens_y y joystick_g; velocidad arriba y abajo aparte)."""
import copy
import math

import pytest

from conftest import CAL_SINTETICA, REPOSO, Sim, cfg_prueba, medidas
from lycan_face_control import constantes as K
from lycan_face_control.config import FABRICA, OPCIONES, RANGOS, Configuracion, por_defecto, validar
from lycan_face_control.mapeo import MONITOR_REFERENCIA as M
from lycan_face_control.ui import opciones as OP

AJUSTES = [round(0.8 + 0.1 * i, 1) for i in range(13)]       # 0,8 … 2,0


# ------------------------------------------------------------------ configuración
def test_claves_nuevas_en_fabrica_y_rangos():
    d = por_defecto()
    assert d["puntero"]["ajuste_vertical"] == 1.2
    assert d["barra"]["boton_sin_clic"] is True and d["barra"]["boton_lupa"] is True
    assert d["lupa"] == {"zona_px": 200, "aumento": 3, "espera_s": 8.0}
    assert RANGOS["puntero.ajuste_vertical"] == (0.8, 2.0)
    assert RANGOS["lupa.zona_px"] == (120, 400)
    assert RANGOS["lupa.aumento"] == (2, 5)
    assert RANGOS["lupa.espera_s"] == (4.0, 20.0)
    # la fábrica misma pasa la validación sin correcciones
    problemas = []
    assert validar(por_defecto(), problemas=problemas) == validar(por_defecto())
    assert problemas == []


@pytest.mark.parametrize("ruta,malo", [
    ("puntero.ajuste_vertical", float("nan")), ("puntero.ajuste_vertical", "1,5"),
    ("puntero.ajuste_vertical", 5.0), ("puntero.ajuste_vertical", 0.5), ("puntero.ajuste_vertical", True),
    ("puntero.ajuste_vertical", None), ("puntero.ajuste_vertical", float("inf")),
    ("lupa.zona_px", 100), ("lupa.zona_px", 401), ("lupa.zona_px", "200"), ("lupa.zona_px", float("nan")),
    ("lupa.aumento", 1), ("lupa.aumento", 6), ("lupa.aumento", "3"), ("lupa.aumento", ""),
    ("lupa.espera_s", 3.9), ("lupa.espera_s", 20.5), ("lupa.espera_s", []), ("lupa.espera_s", float("-inf")),
    ("barra.boton_sin_clic", "sí"), ("barra.boton_sin_clic", 1), ("barra.boton_sin_clic", None),
    ("barra.boton_lupa", "no"), ("barra.boton_lupa", 0), ("barra.boton_lupa", ""),
])
def test_valor_malo_vuelve_al_de_fabrica_y_se_anota(ruta, malo):
    d = por_defecto()
    a, b = ruta.split(".")
    d[a][b] = malo
    problemas = []
    v = validar(d, problemas=problemas)
    assert v[a][b] == FABRICA[a][b]
    assert any(ruta in p for p in problemas), problemas


def test_valores_validos_se_conservan():
    d = por_defecto()
    d["puntero"]["ajuste_vertical"] = 1.7
    d["lupa"] = {"zona_px": 400, "aumento": 5, "espera_s": 20.0}
    d["barra"]["boton_lupa"] = False
    v = validar(d)
    assert v["puntero"]["ajuste_vertical"] == 1.7
    assert v["lupa"] == {"zona_px": 400, "aumento": 5, "espera_s": 20.0}
    assert v["barra"]["boton_lupa"] is False
    # el aumento es entero: un decimal se redondea y se anota
    d["lupa"]["aumento"] = 2.6
    problemas = []
    assert validar(d, problemas=problemas)["lupa"]["aumento"] == 3
    assert any("lupa.aumento" in p for p in problemas)


def test_lupa_que_no_es_objeto_vuelve_entera_a_fabrica():
    d = por_defecto()
    d["lupa"] = "grande"
    problemas = []
    assert validar(d, problemas=problemas)["lupa"] == FABRICA["lupa"]
    assert any(p.startswith("lupa") for p in problemas)


def test_configuracion_1_0_sin_claves_nuevas(tmp_path):
    """Una configuración guardada por la 1.0 (sin las claves nuevas) se lee igual: la velocidad
    no cambia y las claves nuevas toman sus valores de fábrica, sin problemas anotados."""
    import json
    vieja = por_defecto()
    del vieja["puntero"]["ajuste_vertical"]
    del vieja["barra"]["boton_sin_clic"]
    del vieja["barra"]["boton_lupa"]
    del vieja["lupa"]
    vieja["puntero"]["sens_x"], vieja["puntero"]["sens_y"] = 2.0, 2.4
    vieja["perfiles"]["Principal"]["calibracion"] = copy.deepcopy(CAL_SINTETICA)
    ruta = tmp_path / "config.json"
    ruta.write_text(json.dumps(vieja), encoding="utf-8")
    c = Configuracion(ruta)
    d = c.cargar()
    assert c.problemas == [] and c.aviso is None
    assert d["puntero"]["ajuste_vertical"] == 1.2
    assert d["barra"]["boton_sin_clic"] is True and d["barra"]["boton_lupa"] is True
    assert d["lupa"] == FABRICA["lupa"]
    assert OP.velocidad_de_sens(d["puntero"]["sens_x"]) == 7
    assert d["puntero"]["sens_y"] == 2.4                      # no se toca hasta cambiar la velocidad
    assert d["perfiles"]["Principal"]["calibracion"] == CAL_SINTETICA


def test_restablecer_de_fabrica_incluye_las_claves_nuevas(tmp_path):
    c = Configuracion(tmp_path / "config.json")
    c.datos["lupa"]["aumento"] = 5
    c.datos["puntero"]["ajuste_vertical"] = 2.0
    d = c.restablecer_fabrica()
    assert d["lupa"]["aumento"] == 3 and d["puntero"]["ajuste_vertical"] == 1.2


# ------------------------------------------------------------------ velocidad 1 a 10
def test_nivel_3_es_fabrica_y_todo_sube_con_la_velocidad():
    assert OP.sens_de_velocidad(3) == (1.0, 1.2, 1200)
    assert OP.sens_de_velocidad(3, 1.2) == (FABRICA["puntero"]["sens_x"], FABRICA["puntero"]["sens_y"],
                                            FABRICA["puntero"]["joystick_g"])
    for aj in AJUSTES:
        prev = None
        for n in range(1, 11):
            v = OP.sens_de_velocidad(n, aj)
            if prev is not None:
                assert v[0] > prev[0] and v[1] >= prev[1] and v[2] > prev[2], (aj, n, v, prev)
            prev = v
    assert OP.JOYSTICK_VELOCIDAD == (1000, 1050, 1200, 1400, 1600, 1800, 2000, 2300, 2600, 3000)


def test_vertical_nunca_sale_de_0_92_a_3_3_y_todo_valida_sin_correcciones():
    for aj in AJUSTES:
        for n in range(1, 11):
            sx, sy, jg = OP.sens_de_velocidad(n, aj)
            assert 0.92 <= sy <= 3.3, (n, aj, sy)
            d = por_defecto()
            d["puntero"].update(sens_x=sx, sens_y=sy, joystick_g=jg, ajuste_vertical=aj)
            problemas = []
            v = validar(d, problemas=problemas)
            assert problemas == [], (n, aj, problemas)
            assert (v["puntero"]["sens_x"], v["puntero"]["sens_y"], v["puntero"]["joystick_g"]) == (sx, sy, jg)
            assert OP.velocidad_de_sens(sx) == n


def test_ajuste_vertical_raro_usa_el_de_fabrica_y_niveles_fuera_se_recortan():
    for malo in (float("nan"), "x", None, 5.0, 0.1, float("inf")):
        assert OP.sens_de_velocidad(5, malo) == OP.sens_de_velocidad(5, 1.2)
    assert OP.sens_de_velocidad(-4) == OP.sens_de_velocidad(1)
    assert OP.sens_de_velocidad(40) == OP.sens_de_velocidad(10)
    assert OP.sens_de_velocidad("raro") == OP.sens_de_velocidad(3)
    # 2,0 al nivel 10: el tope de 3,3 manda
    assert OP.sens_de_velocidad(10, 2.0)[1] == 3.3
    # 0,8 al nivel 1: el piso de 0,92 manda
    assert OP.sens_de_velocidad(1, 0.8)[1] == 0.92


def test_formato_del_ajuste_vertical():
    # revisión de la 1.1: valor corto (la explicación va en la ayuda de la fila)
    assert OP._ajuste_vertical(1.0) == "Igual"
    assert OP._ajuste_vertical(1.2) == "120 %"
    assert OP._ajuste_vertical(0.8) == "80 %"
    # el porcentaje que se muestra es el que de verdad queda
    assert OP.ajuste_efectivo({"sens_x": 1.0, "sens_y": 0.92}, 0.8) == 0.92
    assert OP.ajuste_efectivo({"sens_x": 2.75, "sens_y": 3.3}, 2.0) == 1.2
    assert OP.ajuste_efectivo({}, 1.5) == 1.5
    assert OP._aumento(3) == "3 veces"


def test_velocidad_1_con_ajuste_0_8_igual_llega_a_los_bordes():
    """Con la cara (medidas) girada hasta los extremos calibrados el puntero llega a los cuatro
    bordes aun con la velocidad más lenta y la vertical al mínimo."""
    sx, sy, jg = OP.sens_de_velocidad(1, 0.8)
    cfg = cfg_prueba(**{"puntero.sens_x": sx, "puntero.sens_y": sy, "puntero.joystick_g": jg,
                        "puntero.ajuste_vertical": 0.8, "permanencia.activa": False,
                        "gestos.boca.activo": True})
    c = CAL_SINTETICA
    for yaw, pitch, eje, borde in ((c["izq"], c["centro"][1], 0, 0), (c["der"], c["centro"][1], 0, M.ancho - 1),
                                   (c["centro"][0], c["arr"], 1, 0), (c["centro"][0], c["aba"], 1, M.alto - 1)):
        s = Sim(cfg)
        s.quieto(0.5)
        # un poco más allá del extremo calibrado (la persona llega al borde de su rango cómodo)
        y = yaw + (yaw - c["centro"][0]) * 0.05
        p = pitch + (pitch - c["centro"][1]) * 0.05
        s.quieto(2.0, yaw_n=y, pitch_n=p)
        pos = s.maquina.puntero.posicion
        assert abs(pos[eje] - borde) <= 6, (eje, borde, pos)
        assert s.clics() == []
