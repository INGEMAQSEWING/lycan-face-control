"""Ronda 2 de arreglos: el temblor de FaceMesh con un rango calibrado pequeño o mucha velocidad
(clics fantasma y clics a propósito que no salían) y el joystick que se arrastraba solo."""
import json
from pathlib import Path

import numpy as np
import pytest

from conftest import CAL_SINTETICA, Sim, cfg_prueba, medidas
from lycan_face_control import calibracion as C
from lycan_face_control.cara import Medidas
from lycan_face_control.mapeo import Monitor
from lycan_face_control.puntero import TEMBLOR_FABRICA, Puntero
from lycan_face_control.mapeo import MapeoCabeza

SERIES = json.loads((Path(__file__).parent / "datos" / "serie_quieta_facemesh.json").read_text("utf-8"))["series"]
PANTALLA = Monitor(0, 0, 1366, 768)


def _serie(ruido):
    a = np.array(SERIES[ruido], float)
    return a - np.median(a, axis=0)


def _cal(rango=None, temblor=None):
    cal = dict(CAL_SINTETICA)
    c = cal["centro"]
    if rango:
        cal["der"], cal["izq"] = c[0] + rango, c[0] - rango
        cal["aba"], cal["arr"] = c[1] + rango, c[1] - rango
    if temblor is not None:
        cal["temblor"] = list(temblor)
    return cal


def _temblor_medido(serie):
    rec = C.Recolector(0.0)
    for i, (y, p) in enumerate(serie[:60]):          # los 3 s del paso "centro"
        rec.agregar(i * 0.05, Medidas(io_px=75.0, yaw_n=float(y), pitch_n=float(p), roll=0.0, ear_der=0.35,
                                      ear_izq=0.35, mar=0.02, cejas=0.35, sonrisa=0.55))
    return C.temblor(rec)


def _cinco_minutos_quieto(modo, ruido, rango, sens=(1.0, 1.2), temblor=None):
    s = Sim(cfg_prueba(**{"puntero.modo": modo, "puntero.sens_x": sens[0], "puntero.sens_y": sens[1]}),
            calibracion=_cal(rango, temblor), monitor=PANTALLA, fps=20)
    c = s.maquina.calibracion["centro"]
    serie = _serie(ruido)
    for rep in range(5):                              # 5 × 60 s (la serie y su reversa, sin saltos)
        for n in (serie if rep % 2 == 0 else serie[::-1]):
            s.paso(medidas(yaw_n=c[0] + n[0], pitch_n=c[1] + n[1]))
    return s


# ------------------------------------------------------------ clics fantasma
@pytest.mark.parametrize("modo", ("absoluto", "relativo"))
@pytest.mark.parametrize("ruido", ("3.0", "5.0"))
@pytest.mark.parametrize("rango", (0.03, 0.05, None))
def test_cinco_minutos_quieto_con_rango_pequeno_no_hace_clics(modo, ruido, rango):
    assert len(_cinco_minutos_quieto(modo, ruido, rango).clics()) == 0


@pytest.mark.parametrize("ruido", ("3.0", "5.0"))
def test_cinco_minutos_quieto_a_velocidad_alta_no_hace_clics(ruido):
    assert len(_cinco_minutos_quieto("absoluto", ruido, None, sens=(1.75, 2.1)).clics()) == 0


@pytest.mark.parametrize("ruido", ("3.0", "5.0"))
@pytest.mark.parametrize("rango", (0.03, None))
def test_joystick_quieto_en_el_centro_no_se_arrastra_ni_hace_clics(ruido, rango):
    # con el temblor que mide la calibración (el de fábrica es 0,003; la serie "5.0" tiene más)
    s = _cinco_minutos_quieto("joystick", ruido, rango, temblor=_temblor_medido(_serie(ruido)))
    assert len(s.clics()) == 0
    x, y = s.maquina.puntero.posicion
    cx, cy = PANTALLA.centro
    assert abs(x - cx) <= 10 and abs(y - cy) <= 10


def test_joystick_sigue_moviendo_el_puntero_al_inclinar_la_cabeza():
    s = Sim(cfg_prueba(**{"puntero.modo": "joystick"}), monitor=PANTALLA, fps=20)
    c = CAL_SINTETICA["centro"]
    s.quieto(1.0, yaw_n=c[0], pitch_n=c[1])
    x0 = s.maquina.puntero.posicion[0]
    s.quieto(1.0, yaw_n=c[0] + 0.5 * (CAL_SINTETICA["der"] - c[0]), pitch_n=c[1])
    assert s.maquina.puntero.posicion[0] > x0 + 100


# ------------------------------------------------------------ clic a propósito
def _clic_a_proposito(ruido, rango, sens=(1.0, 1.2), temblor=None, intentos=5):
    serie = _serie(ruido)
    tiempos = []
    for rep in range(intentos):
        cal = _cal(rango, temblor)
        s = Sim(cfg_prueba(**{"puntero.sens_x": sens[0], "puntero.sens_y": sens[1]}), calibracion=cal,
                monitor=PANTALLA, fps=20)
        c = cal["centro"]
        k = [rep * 120]

        def n():
            k[0] += 1
            return serie[k[0] % len(serie)]
        for _ in range(20):
            r = n()
            s.paso(medidas(yaw_n=c[0] + r[0], pitch_n=c[1] + r[1]))
        dy, dp = (cal["der"] - c[0]) * 0.4, (cal["aba"] - c[1]) * 0.3
        for i in range(14):                         # va a un punto en 0,7 s
            f, r = (i + 1) / 14, n()
            s.paso(medidas(yaw_n=c[0] + dy * f + r[0], pitch_n=c[1] + dp * f + r[1]))
        s.limpiar()
        t0, primero = s.t, None
        for _ in range(120):                        # y se queda quieto hasta 6 s
            r = n()
            s.paso(medidas(yaw_n=c[0] + dy + r[0], pitch_n=c[1] + dp + r[1]))
            if primero is None and s.clics():
                primero = s.t - t0
        tiempos.append(primero)
    return tiempos


@pytest.mark.parametrize("rango", (0.03, 0.05))
@pytest.mark.parametrize("sens", ((1.0, 1.2), (1.75, 2.1)))
def test_clic_a_proposito_con_rango_pequeno_sale_en_menos_de_2_s(rango, sens):
    serie = _serie("3.0")
    tiempos = _clic_a_proposito("3.0", rango, sens, temblor=_temblor_medido(serie))
    assert all(t is not None and t < 2.0 for t in tiempos), tiempos


def test_clic_a_proposito_con_mucho_temblor_y_temblor_calibrado():
    serie = _serie("5.0")
    tiempos = _clic_a_proposito("5.0", None, (1.75, 2.1), temblor=_temblor_medido(serie))
    assert all(t is not None and t < 2.5 for t in tiempos), tiempos


# ------------------------------------------------------------ piezas
def test_la_calibracion_mide_el_temblor_de_la_cabeza():
    for ruido in ("3.0", "5.0"):
        serie = _serie(ruido)
        sy, sp = _temblor_medido(serie)
        real = serie[:60].std(axis=0)
        assert 0.5 * real[0] < sy < 2.0 * real[0]
        assert 0.5 * real[1] < sp < 2.0 * real[1]


def test_el_temblor_calibrado_se_guarda_y_se_usa():
    cal = C.construir((0.0, 0.55), {"izq": -0.03, "der": 0.03, "arr": 0.52, "aba": 0.58},
                      dict(C.BASE_REFERENCIA), temblor_cabeza=[0.004, 0.005])
    assert cal["temblor"] == [0.004, 0.005]
    s = Sim(calibracion=cal, monitor=PANTALLA)
    assert s.maquina.puntero.temblor == (0.004, 0.005)


def test_radio_y_zona_muerta_crecen_con_la_ganancia():
    def p(rango):
        m = MapeoCabeza(PANTALLA, _cal(rango))
        return Puntero(m)
    fabrica, corto = p(None), p(0.03)
    assert corto.temblor_px > 2.5 * fabrica.temblor_px
    assert corto.zona_muerta > fabrica.zona_muerta
    s_f = Sim(calibracion=_cal(None), monitor=PANTALLA)
    s_c = Sim(calibracion=_cal(0.03), monitor=PANTALLA)
    assert s_c.maquina.perm.radio > 2 * s_f.maquina.perm.radio


def test_temblor_raro_en_la_calibracion_no_rompe_nada():
    for raro in (None, "x", [float("nan"), -1], [0.0], [1e9, 1e9]):
        cal = _cal(None)
        cal["temblor"] = raro
        m = MapeoCabeza(PANTALLA, cal)
        p = Puntero.desde_config(cfg_prueba(), m, None, cal)
        assert all(0 < v <= 0.02 for v in p.temblor)
    assert Puntero(MapeoCabeza(PANTALLA)).temblor == (TEMBLOR_FABRICA, TEMBLOR_FABRICA)
