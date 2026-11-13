"""Ronda 1 de arreglos: puntero (temblor de FaceMesh, "toque de Midas"), Desplazar y velocidad."""
import json
from pathlib import Path

import numpy as np
import pytest

from conftest import CAL_SINTETICA, REPOSO, Sim, cfg_prueba, medidas
from lycan_face_control import constantes as K
from lycan_face_control.acciones import Mover, Rueda
from lycan_face_control.mapeo import MapeoCabeza
from lycan_face_control.permanencia import Objetivo

SERIES = json.loads((Path(__file__).parent / "datos" / "serie_quieta_facemesh.json").read_text("utf-8"))["series"]


def _cal_para(serie):
    """Calibración centrada en la postura quieta de la serie, con los rangos de la cara sintética."""
    a = np.array(serie)
    med = np.median(a, axis=0)
    c = dict(CAL_SINTETICA)
    c["centro"] = [float(med[0]), float(med[1])]
    c["der"], c["izq"] = med[0] + 0.09, med[0] - 0.09
    c["aba"], c["arr"] = med[1] + 0.094, med[1] - 0.103
    return c


def _quieto_con_serie(serie, **cambios):
    s = Sim(cfg_prueba(**cambios), calibracion=_cal_para(serie), fps=20)
    pos = []
    for y, p in serie:                       # 1200 cuadros = 60 s con la cabeza quieta
        s.paso(medidas(yaw_n=y, pitch_n=p))
        pos.append(s.maquina.puntero.posicion)
    return s, np.array(pos[40:])


@pytest.mark.parametrize("ruido", sorted(SERIES))
@pytest.mark.parametrize("suavidad", (1, 3, 5))
def test_cabeza_quieta_60_s_con_temblor_real_no_hace_clics(ruido, suavidad):
    s, _ = _quieto_con_serie(SERIES[ruido], **{"puntero.suavidad": suavidad})
    assert len(s.clics()) <= 1


def test_velocidad_maxima_con_temblor_no_hace_clics():
    s, _ = _quieto_con_serie(SERIES["3.0"], **{"puntero.sens_x": 3.0, "puntero.sens_y": 3.0})
    assert len(s.clics()) <= 1


def test_la_suavidad_si_reduce_el_temblor():
    serie = SERIES["5.0"]
    _, p1 = _quieto_con_serie(serie, **{"puntero.suavidad": 1})
    _, p5 = _quieto_con_serie(serie, **{"puntero.suavidad": 5})
    r1 = np.ptp(p1[:, 0]) + np.ptp(p1[:, 1])
    r5 = np.ptp(p5[:, 0]) + np.ptp(p5[:, 1])
    assert r5 < 0.7 * r1
    assert np.ptp(p5[:, 0]) < 80 and np.ptp(p5[:, 1]) < 80


# ------------------------------------------------------------------ Desplazar
def _sim_con_barra():
    s = Sim()
    s.quieto(0.5)
    bx, by = s.maquina.puntero.posicion
    desp = Objetivo("barra:desplazar", (bx - 48, by - 48, bx + 48, by + 48))
    term = Objetivo("desplazar:terminar", (bx - 48, by + 60, bx + 48, by + 156))
    return s, desp, term


def _ir_a_la_pagina_y_elegir_desplazar(s, desp, term):
    y0, p0 = REPOSO["yaw_n"], REPOSO["pitch_n"]
    s.maquina.poner_objetivos([desp, term])
    s.quieto(1.0, yaw_n=y0 - 0.04)          # en la página, a la izquierda de la barra
    pagina = s.maquina.puntero.posicion
    assert not desp.contiene(*pagina)
    s.quieto(2.5)                            # vuelve a la barra y se queda quieto en «Desplazar»
    assert s.maquina.submodo == K.DESPLAZAR
    return pagina


def test_desplazar_desde_la_barra_desplaza_la_pagina_y_no_la_barra():
    s, desp, term = _sim_con_barra()
    pagina = _ir_a_la_pagina_y_elegir_desplazar(s, desp, term)
    assert not desp.contiene(*s.salida.cursor)
    assert abs(s.salida.cursor[0] - pagina[0]) <= 3 and abs(s.salida.cursor[1] - pagina[1]) <= 3
    s.limpiar()
    s.quieto(2.0, pitch_n=REPOSO["pitch_n"] + 0.06)
    assert s.de_tipo(Rueda)
    assert not desp.contiene(*s.salida.cursor)            # la rueda cae sobre la página


def test_en_desplazar_se_elige_terminar_quedandose_quieto():
    s, desp, term = _sim_con_barra()
    _ir_a_la_pagina_y_elegir_desplazar(s, desp, term)
    # la cabeza baja un poco hasta «Terminar» (justo debajo) y se queda quieta
    p_term = REPOSO["pitch_n"] + 0.03
    s.quieto(3.0, pitch_n=p_term)
    assert s.maquina.submodo == K.NORMAL
    assert "desplazar:terminar" in s.elegidos()


def test_desplazar_termina_solo_si_se_descansa_apenas_inclinado():
    s, desp, term = _sim_con_barra()
    _ir_a_la_pagina_y_elegir_desplazar(s, desp, term)
    s.maquina.poner_objetivos([desp])                       # sin «Terminar» a mano
    s.limpiar()
    s.quieto(30.0, pitch_n=REPOSO["pitch_n"] + 0.02)        # ~2° más abajo, quieto
    assert s.maquina.submodo == K.NORMAL
    assert len(s.de_tipo(Rueda)) < 20


def test_desplazar_tiene_tope_aunque_siga_inclinado():
    s, desp, term = _sim_con_barra()
    _ir_a_la_pagina_y_elegir_desplazar(s, desp, term)
    s.maquina.poner_objetivos([desp])
    s.quieto(65.0, pitch_n=REPOSO["pitch_n"] + 0.07)
    assert s.maquina.submodo == K.NORMAL


# ------------------------------------------------------------------ velocidad
def test_velocidad_baja_igual_llega_a_los_bordes():
    from lycan_face_control.ui.opciones import sens_de_velocidad
    for n in (1, 2, 3):
        sx, sy = sens_de_velocidad(n)
        cfg = cfg_prueba(**{"puntero.sens_x": sx, "puntero.sens_y": sy})
        from lycan_face_control.mapeo import MONITOR_REFERENCIA as M
        mp = MapeoCabeza.desde_config(cfg, M, CAL_SINTETICA)
        c = CAL_SINTETICA
        xs = [mp.a_pixeles(c["izq"], c["centro"][1])[0], mp.a_pixeles(c["der"], c["centro"][1])[0]]
        ys = [mp.a_pixeles(c["centro"][0], c["arr"])[1], mp.a_pixeles(c["centro"][0], c["aba"])[1]]
        assert min(xs) <= 5 and max(xs) >= M.ancho - 6, (n, xs)
        assert min(ys) <= 5 and max(ys) >= M.alto - 6, (n, ys)
