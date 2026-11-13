"""Mapeo de la pose de la cabeza a la pantalla (sección 3.6). Sin mediapipe."""
import math

import pytest

from conftest import CAL_SINTETICA
from lycan_face_control.mapeo import (MONITOR_REFERENCIA, RANGO_MINIMO_YAW, MapeoCabeza, Monitor)

M = MONITOR_REFERENCIA


def mapeo(**kw):
    return MapeoCabeza(M, CAL_SINTETICA, **kw)


def test_centro_va_al_centro_de_la_pantalla():
    m = mapeo()
    x, y = m.a_pixeles(0.022, 0.556)
    assert (x, y) == pytest.approx(M.centro)


def test_extremos_comodos_llegan_al_borde_con_margen():
    m = mapeo(sens_y=1.0)
    x, _ = m.recortar(*m.a_pixeles(0.111, 0.556))
    assert x == M.ancho - 1
    x, _ = m.recortar(*m.a_pixeles(-0.069, 0.556))
    assert x == 0
    _, y = m.recortar(*m.a_pixeles(0.022, 0.650))
    assert y == M.alto - 1
    _, y = m.recortar(*m.a_pixeles(0.022, 0.453))
    assert y == 0
    # con el margen de 10 %, el borde se alcanza antes del extremo cómodo (al ~91 %)
    x91, _ = m.a_pixeles(0.022 + 0.92 * (0.111 - 0.022), 0.556)
    assert x91 >= M.ancho - 1


def test_mapeo_por_tramos_asimetrico():
    """Cada lado usa su propio rango: la mitad del recorrido izquierdo = la mitad de la pantalla."""
    m = mapeo(zona_muerta=0.0)
    xd, _ = m.a_pixeles(0.022 + 0.5 * (0.111 - 0.022), 0.556)
    xi, _ = m.a_pixeles(0.022 - 0.5 * (0.022 + 0.069), 0.556)
    cx = M.centro[0]
    assert xd - cx == pytest.approx(cx - xi, rel=1e-6)


def test_zona_muerta_del_centro():
    m = mapeo(zona_muerta=0.03)
    # 2 % del rango hacia la derecha: dentro de la zona muerta
    x, y = m.a_pixeles(0.022 + 0.02 * 0.089, 0.556)
    assert (x, y) == pytest.approx(M.centro)
    # 10 %: ya se mueve, pero menos que sin zona muerta (se reescala)
    x1, _ = m.a_pixeles(0.022 + 0.10 * 0.089, 0.556)
    x0, _ = mapeo(zona_muerta=0.0).a_pixeles(0.022 + 0.10 * 0.089, 0.556)
    assert M.centro[0] < x1 < x0
    # y el extremo sigue llegando al mismo sitio
    assert m.a_pixeles(0.111, 0.556)[0] == pytest.approx(mapeo(zona_muerta=0.0).a_pixeles(0.111, 0.556)[0])


def test_sensibilidad_por_eje():
    m1, m2 = mapeo(sens_x=1.0, sens_y=1.0), mapeo(sens_x=2.0, sens_y=1.0)
    p = (0.022 + 0.3 * 0.089, 0.556 + 0.3 * 0.094)
    cx, cy = M.centro
    x1, y1 = m1.a_pixeles(*p)
    x2, y2 = m2.a_pixeles(*p)
    assert (x2 - cx) == pytest.approx(2 * (x1 - cx))
    assert y2 == pytest.approx(y1)
    # la vertical es 1,2 veces más sensible por defecto
    m3 = MapeoCabeza(M, CAL_SINTETICA)
    _, y3 = m3.a_pixeles(*p)
    assert (y3 - cy) == pytest.approx(1.2 * (y1 - cy))


def test_signo_sale_de_la_calibracion_no_se_adivina():
    """Si el extremo derecho calibrado tiene yaw menor que el centro (cámara al revés), mirar a la
    derecha igual lleva el puntero a la derecha."""
    cal = dict(CAL_SINTETICA, der=-0.069, izq=0.111, signo_x=-1.0)
    m = MapeoCabeza(M, cal)
    x, _ = m.a_pixeles(-0.05, 0.556)
    assert x > M.centro[0]
    assert m.signo_x == -1.0


def test_recentrar_mueve_solo_el_centro():
    m = mapeo()
    r = (m.r_der, m.r_izq, m.r_aba, m.r_arr)
    m.recentrar(0.05, 0.60)
    assert m.a_pixeles(0.05, 0.60) == pytest.approx(M.centro)
    assert (m.r_der, m.r_izq, m.r_aba, m.r_arr) == r


def test_recorte_en_monitor_secundario():
    mon = Monitor(1366, 0, 1920, 1080, False)
    m = MapeoCabeza(mon, CAL_SINTETICA)
    assert m.a_pixeles(0.022, 0.556) == pytest.approx(mon.centro)
    x, y = m.recortar(*m.a_pixeles(0.5, 2.0))
    assert x == 1366 + 1919 and y == 1079
    x, y = m.recortar(*m.a_pixeles(-0.5, -2.0))
    assert x == 1366 and y == 0


def test_sin_calibracion_usa_rangos_de_fabrica_y_no_falla_con_basura():
    m = MapeoCabeza(M, None)
    assert not m.calibrado
    for basura in ({"centro": "x"}, {"centro": [float("nan"), 1]}, {"der": "a", "izq": None}, {"der": 0.0001}):
        m2 = MapeoCabeza(M, basura)
        x, y = m2.a_pixeles(0.0, 0.55)
        assert math.isfinite(x) and math.isfinite(y)
    # un rango diminuto se sube al mínimo seguro
    m3 = MapeoCabeza(M, dict(CAL_SINTETICA, der=0.023))
    assert m3.r_der == pytest.approx(RANGO_MINIMO_YAW)


def test_joystick_velocidad():
    m = mapeo(joystick_g=1200)
    assert m.velocidad_joystick(0.0, 0.0) == (0.0, 0.0)
    v1 = m.velocidad_joystick(0.5, 0.0)[0]
    v2 = m.velocidad_joystick(1.0, 0.0)[0]
    assert 0 < v1 < v2 == pytest.approx(1200)
    assert m.velocidad_joystick(-1.0, 0.0)[0] == pytest.approx(-1200)
    # tope a 1,5 veces el extremo
    assert m.velocidad_joystick(5.0, 0.0)[0] == pytest.approx(1200 * 1.5 ** 1.5)


def test_ida_y_vuelta_pixeles_uv():
    m = mapeo()
    for u, v in ((0.0, 0.0), (0.3, -0.7), (-1.0, 1.0)):
        x, y = m.uv_a_pixeles(u, v)
        assert m.pixeles_a_uv(x, y) == pytest.approx((u, v))


def test_como_dict_recupera_la_calibracion():
    m = mapeo()
    d = m.como_dict()
    m2 = MapeoCabeza(M, d)
    for p in ((0.05, 0.6), (-0.03, 0.5)):
        assert m2.a_pixeles(*p) == pytest.approx(m.a_pixeles(*p))
