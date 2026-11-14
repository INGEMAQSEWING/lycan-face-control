"""Versión 1.1, paquete C: medidas del iris en la cara (sin cámara: caras sintéticas)."""
import math

import numpy as np
import pytest

from lycan_face_control import constantes as K
from lycan_face_control.cara import medir, medir_si_valida
from sintetico.cara_sintetica import cara, mirar_a


def _m(**kw):
    return medir_si_valida(cara(**kw), 640, 480)


def test_iris_x_crece_con_la_mirada_a_los_lados_y_de_frente_casi_cero():
    xs = [_m(ojo_yaw=a).iris_x for a in (-25, -15, -5, 0, 5, 15, 25)]
    assert all(b > a for a, b in zip(xs, xs[1:]))
    frente = _m()
    assert abs(frente.iris_x) < 0.03 and abs(frente.iris_y) < 0.08     # la cara de base no es simétrica
    ys = [_m(ojo_pitch=a).iris_y for a in (-20, 0, 20)]
    assert ys[0] < ys[1] < ys[2]                                       # mirar abajo = crece


@pytest.mark.parametrize("kw", [{"escala": 0.6}, {"escala": 1.4}, {"centro": (200.0, 180.0)},
                                {"centro": (420.0, 300.0)}, {"roll": 15}, {"roll": -15}])
def test_iris_no_cambia_con_la_escala_el_centro_ni_la_inclinacion(kw):
    base = _m(ojo_yaw=12, ojo_pitch=-8)
    otra = _m(ojo_yaw=12, ojo_pitch=-8, **kw)
    assert otra.iris_x == pytest.approx(base.iris_x, abs=0.004)
    assert otra.iris_y == pytest.approx(base.iris_y, abs=0.004)


def test_con_468_puntos_no_hay_iris_y_lo_demas_se_mide_igual():
    P = cara(ojo_yaw=10)
    m478 = medir_si_valida(P, 640, 480)
    m468 = medir_si_valida(P[:468], 640, 480)
    assert m468 is not None
    assert m468.iris_x is None and m468.iris_y is None and m468.iris_der is None and m468.iris_izq is None
    assert m468.yaw_n == pytest.approx(m478.yaw_n) and m468.mar == pytest.approx(m478.mar)


def test_nan_en_el_iris_da_none_sin_fallar_y_la_cara_sigue_valida():
    P = cara()
    P[K.IRIS_DER, 0] = np.nan
    P[K.IRIS_IZQ_ANILLO[1], 1] = np.inf
    m = medir_si_valida(P, 640, 480)
    assert m is not None and m.iris_x is None
    assert math.isfinite(m.yaw_n)


def test_nan_en_un_solo_ojo_usa_el_otro():
    P = cara(ojo_yaw=10)
    P[K.IRIS_DER, 0] = np.nan
    m = medir_si_valida(P, 640, 480)
    assert m.iris_der is None and m.iris_izq is not None
    assert m.iris_x == pytest.approx(m.iris_izq[0])


def test_con_un_ojo_cerrado_se_usa_el_otro():
    m = _m(ojo_yaw=10, ojo_der=0.2)
    assert m.iris_der is None and m.iris_izq is not None
    assert m.iris_x == pytest.approx(m.iris_izq[0])
    abierto = _m(ojo_yaw=10)
    assert m.iris_x == pytest.approx(abierto.iris_izq[0], abs=1e-6)


def test_con_los_dos_ojos_cerrados_por_igual_sigue_midiendo_pero_la_maquina_congela():
    # FaceMesh baja el iris al cerrar los ojos: la medida existe (no la descarta el EAR relativo),
    # y por eso la máquina congela SIEMPRE el puntero de los ojos con los ojos cerrándose
    abierto = _m(ojos=1.0)
    cerrado = _m(ojos=0.1, iris_baja=0.3)
    assert cerrado.iris_y is not None and cerrado.iris_y > abierto.iris_y + 0.05


def test_los_puntos_del_iris_no_son_obligatorios_para_validar():
    assert not set(K.IRIS_DER_ANILLO + K.IRIS_IZQ_ANILLO + (K.IRIS_DER, K.IRIS_IZQ)) & set(K.PUNTOS_CLAVE)
    assert K.PARPADO_MEDIO_DER == (159, 145) and K.PARPADO_MEDIO_IZQ == (386, 374)


def test_cara_degenerada_sin_iris_no_falla():
    P = np.zeros((478, 3))
    m = medir(P)
    assert m.iris_x is None


def test_mirar_a_la_derecha_de_la_pantalla_mueve_el_iris_a_la_derecha():
    from lycan_face_control.mapeo import MONITOR_REFERENCIA as M
    izq = medir_si_valida(cara(**mirar_a(100, 384, monitor=M)), 640, 480)
    der = medir_si_valida(cara(**mirar_a(1266, 384, monitor=M)), 640, 480)
    assert der.iris_x > izq.iris_x + 0.1
    # con la cabeza girada hacia el punto, los ojos giran menos
    p = mirar_a(1266, 384, cabeza_yaw=8, monitor=M)
    assert p["yaw"] == 8 and p["ojo_yaw"] < mirar_a(1266, 384, monitor=M)["ojo_yaw"]
