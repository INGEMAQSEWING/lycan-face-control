"""Ronda 3 de arreglos: puntero (pasar despacio por el centro no hace clics, el temblor esperado
sigue el ritmo real de cuadros, la cabeza quieta con la cámara lenta no hace clics fantasma)."""
import json
from pathlib import Path

import numpy as np
import pytest

from conftest import CAL_SINTETICA, Sim, cfg_prueba, medidas
from lycan_face_control.acciones import Clic
from lycan_face_control.mapeo import MapeoCabeza, Monitor

SERIES = json.loads((Path(__file__).parent / "datos" / "serie_quieta_facemesh.json").read_text("utf-8"))["series"]


def _cal(rango=None, temblor=(0.003, 0.003)):
    cal = dict(CAL_SINTETICA)
    c = cal["centro"]
    if rango:
        cal["der"], cal["izq"] = c[0] + rango, c[0] - rango
        cal["aba"], cal["arr"] = c[1] + rango, c[1] - rango
    if temblor is not None:
        cal["temblor"] = list(temblor)
    return cal


@pytest.mark.parametrize("pxs", (60, 100, 120))
@pytest.mark.parametrize("modo", ("absoluto", "relativo"))
def test_pasar_despacio_por_el_centro_no_hace_clics(pxs, modo):
    mon = Monitor(0, 0, 1920, 1080)
    s = Sim(cfg_prueba(**{"puntero.modo": modo}), calibracion=_cal(), monitor=mon, fps=20)
    cc = s.maquina.calibracion["centro"]
    g = s.maquina.puntero.mapeo.ganancia_px()[0]
    y = cc[0] - 0.05
    for _ in range(20):
        s.paso(medidas(yaw_n=y, pitch_n=cc[1]))
    s.limpiar()
    cerca = []
    for _ in range(int(0.1 * g / pxs / s.dt)):       # cruza el centro de lado a lado, sin parar
        y += pxs / g * s.dt
        r = s.paso(medidas(yaw_n=y, pitch_n=cc[1]))
        x, _y = s.salida.posicion_cursor()
        if any(isinstance(a, Clic) for a in r.acciones) and abs(x - mon.centro[0]) < 400:
            cerca.append(s.salida.posicion_cursor())     # (en Almohadilla puede llegar al borde)
    assert cerca == []


def test_la_zona_muerta_del_centro_solo_en_palanca():
    for modo, zm in (("absoluto", 0.0), ("relativo", 0.0), ("joystick", 0.03)):
        m = MapeoCabeza.desde_config(cfg_prueba(**{"puntero.modo": modo}))
        assert m.zona_muerta == zm
    m = MapeoCabeza.desde_config(cfg_prueba())
    # en Directo el puntero se mueve aunque la cabeza apenas salga del centro
    assert m.normalizar(m.yaw0 + 0.001, m.pitch0)[0] > 0


def test_el_temblor_esperado_crece_si_la_camara_va_lenta():
    s20 = Sim(calibracion=_cal(0.05), fps=20)
    s8 = Sim(calibracion=_cal(0.05), fps=8)
    s20.quieto(5.0)
    s8.quieto(5.0)
    assert s8.maquina.puntero.temblor_px > 1.2 * s20.maquina.puntero.temblor_px
    assert s8.maquina.perm.radio > s20.maquina.perm.radio


@pytest.mark.parametrize("fps,rango", ((8, 0.05), (8, 0.03), (12, 0.03), (12, 0.05)))
def test_cabeza_quieta_con_la_camara_lenta_no_hace_clics(fps, rango):
    serie = np.array(SERIES["5.0"], float)
    serie -= np.median(serie, axis=0)
    # el temblor que mediría la calibración con esa serie
    s = Sim(cfg_prueba(), calibracion=_cal(rango, (0.0034, 0.0043)), monitor=Monitor(0, 0, 1366, 768), fps=fps)
    c = s.maquina.calibracion["centro"]
    for rep in range(3):
        for n in (serie if rep % 2 == 0 else serie[::-1]):
            s.paso(medidas(yaw_n=c[0] + n[0], pitch_n=c[1] + n[1]))
    assert s.clics() == []


def test_calibracion_sin_temblor_medido_usa_un_valor_seguro():
    from lycan_face_control.puntero import TEMBLOR_FABRICA, TEMBLOR_SIN_MEDIR
    sin = Sim(calibracion=_cal(0.05, temblor=None))
    assert sin.maquina.puntero.temblor == (TEMBLOR_SIN_MEDIR, TEMBLOR_SIN_MEDIR)
    sin_cal = Sim(calibracion=None)
    assert sin_cal.maquina.puntero.temblor == (TEMBLOR_FABRICA, TEMBLOR_FABRICA)
