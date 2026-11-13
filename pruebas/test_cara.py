"""Medidas de la cara (sección 13.2, test_cara.py) y generador sintético. Sin mediapipe."""
import math

import numpy as np
import pytest

from lycan_face_control import cara as C
from lycan_face_control.cara import medir, medir_si_valida, posicion_y_tamano, puntos_validos
from sintetico import cara, cara_base, centro_base, linea_de_tiempo, normalizar
from sintetico.cara_sintetica import FuenteSecuencia


@pytest.fixture(scope="module")
def base():
    return medir(cara_base())


def test_valores_de_la_cara_de_referencia(base):
    # sección 3.4: EAR 0,357/0,375; MAR 0,016; cejas 0,356; sonrisa 0,557
    assert base.ear_der == pytest.approx(0.357, abs=0.002)
    assert base.ear_izq == pytest.approx(0.375, abs=0.002)
    assert base.mar == pytest.approx(0.016, abs=0.002)
    assert base.cejas == pytest.approx(0.356, abs=0.002)
    assert base.sonrisa == pytest.approx(0.557, abs=0.002)
    assert base.pitch_n == pytest.approx(0.55, abs=0.05)
    assert abs(base.yaw_n) < 0.05
    assert abs(base.roll) < 2
    assert base.io_px > 100


def test_generador_sin_cambios_es_la_base():
    cx, cy = centro_base()
    np.testing.assert_allclose(cara(centro=(cx, cy)), cara_base(), atol=1e-6)
    assert cara().shape == (478, 3)


@pytest.mark.parametrize("cambio", [
    {"centro": (380, 240)}, {"centro": (260, 300)}, {"escala": 0.7}, {"roll": 15}, {"roll": -15},
    {"escala": 0.7, "roll": 15, "centro": (360, 220)},
])
def test_pose_invariante_a_mover_escalar_e_inclinar(cambio, base):
    m = medir(cara(**cambio))
    assert m.yaw_n == pytest.approx(base.yaw_n, abs=0.01)
    assert m.pitch_n == pytest.approx(base.pitch_n, abs=0.02)
    # las medidas de expresión tampoco cambian
    for k in ("ear_der", "ear_izq", "mar", "cejas", "sonrisa"):
        assert getattr(m, k) == pytest.approx(getattr(base, k), rel=0.02), k


def test_yaw_crece_al_girar_a_la_derecha():
    valores = [medir(cara(yaw=y)).yaw_n for y in (-20, -10, 0, 10, 20)]
    assert valores == sorted(valores)
    assert valores[-1] - valores[2] > 0.08     # ±20° ≈ ±0,12 o más
    assert valores[2] - valores[0] > 0.08


def test_pitch_crece_al_bajar_la_cabeza():
    valores = [medir(cara(pitch=p)).pitch_n for p in (-15, 0, 15)]
    assert valores == sorted(valores)
    assert valores[2] - valores[0] > 0.15


def test_roll_en_grados():
    assert medir(cara(roll=15)).roll == pytest.approx(15 + medir(cara()).roll, abs=0.5)
    assert medir(cara(roll=-10)).roll == pytest.approx(-10 + medir(cara()).roll, abs=0.5)


def test_girar_no_cambia_el_otro_eje(base):
    assert medir(cara(yaw=15)).pitch_n == pytest.approx(base.pitch_n, abs=0.03)
    assert medir(cara(pitch=12)).yaw_n == pytest.approx(base.yaw_n, abs=0.03)


def test_ojos_cerrados_bajan_el_ear(base):
    cerrado = medir(cara(ojos=0))
    assert cerrado.ear_der / base.ear_der < 0.35
    assert cerrado.ear_izq / base.ear_izq < 0.35
    medio = medir(cara(ojos=0.5))
    assert 0.4 < medio.ear_der / base.ear_der < 0.7
    # un solo ojo
    uno = medir(cara(ojo_der=0))
    assert uno.ear_der / base.ear_der < 0.35
    assert uno.ear_izq == pytest.approx(base.ear_izq, rel=1e-6)


def test_ear_monotono_con_la_apertura():
    valores = [medir(cara(ojos=a)).ear_der for a in (0, 0.25, 0.5, 0.75, 1)]
    assert valores == sorted(valores)


def test_cerrar_los_ojos_no_mueve_las_cejas(base):
    # se mide contra las comisuras (no contra el párpado) justamente por esto
    assert medir(cara(ojos=0)).cejas == pytest.approx(base.cejas, rel=0.01)


def test_boca_abierta(base):
    m = medir(cara(boca=1))
    assert m.mar > base.mar + 0.5
    assert medir(cara(boca=0.5)).mar > base.mar + 0.25
    assert m.ear_der == pytest.approx(base.ear_der)


def test_cejas_arriba(base):
    assert medir(cara(cejas=1)).cejas / base.cejas > 1.2
    assert medir(cara(cejas=0.5)).cejas / base.cejas > 1.10


def test_sonrisa(base):
    m = medir(cara(sonrisa=1))
    assert m.sonrisa / base.sonrisa > 1.15
    assert m.mar < base.mar + 0.05            # sonreír no abre la boca
    # con la boca abierta la sonrisa sigue midiéndose, pero el MAR lo delata (gestos lo usa)
    assert medir(cara(sonrisa=1, boca=1)).mar > base.mar + 0.3


def test_gestos_no_mueven_la_pose_de_mas(base):
    for kw in ({"ojos": 0}, {"cejas": 1}):
        m = medir(cara(**kw))
        assert m.yaw_n == pytest.approx(base.yaw_n, abs=1e-6)
        assert m.pitch_n == pytest.approx(base.pitch_n, abs=1e-6)


def test_puntos_validos_rechaza_lo_malo():
    P = cara()
    assert puntos_validos(P)
    assert puntos_validos(P, 640, 480)
    malo = P.copy()
    malo[33, 0] = np.nan
    assert not puntos_validos(malo)
    malo = P.copy()
    malo[5, 2] = np.inf
    assert not puntos_validos(malo)
    assert not puntos_validos(cara(escala=0.3))          # io < 40 px
    assert not puntos_validos(P[:400])                   # faltan puntos
    assert not puntos_validos(None)
    assert not puntos_validos("no")
    assert not puntos_validos(np.zeros((478,)))
    # media cara fuera de la imagen
    assert not puntos_validos(cara(centro=(20, 240)), 640, 480)
    assert puntos_validos(cara(centro=(20, 240)))        # sin tamaño de imagen no se revisa


def test_puntos_sin_iris_y_en_2d():
    P = cara()
    assert puntos_validos(P[:468])
    assert puntos_validos(P[:, :2])
    m = medir(P[:468])
    assert math.isfinite(m.ear_der)


def test_medir_cara_degenerada_da_nan():
    m = medir(np.zeros((478, 3)))
    assert math.isnan(m.yaw_n) and math.isnan(m.mar)
    assert medir_si_valida(np.zeros((478, 3))) is None


def test_medir_si_valida():
    assert medir_si_valida(cara(), 640, 480) is not None
    assert medir_si_valida(cara(escala=0.2), 640, 480) is None


def test_posicion_y_tamano():
    (x, y), io_rel = posicion_y_tamano(cara(centro=(320, 240)), 640, 480)
    assert 0.4 < x < 0.6 and 0.3 < y < 0.6
    assert 0.09 <= io_rel <= 0.22          # la cara de referencia está a buena distancia
    _, lejos = posicion_y_tamano(cara(escala=0.4), 640, 480)
    assert lejos < 0.09


def test_ruido_es_reproducible(rng):
    a = cara(ruido=1.0, rng=np.random.default_rng(7))
    b = cara(ruido=1.0, rng=np.random.default_rng(7))
    np.testing.assert_allclose(a, b)
    assert not np.allclose(a, cara())
    m = medir(cara(ruido=0.5, rng=rng))
    assert m.ear_der == pytest.approx(medir(cara()).ear_der, rel=0.15)


def test_linea_de_tiempo_interpola_y_respeta_sin_cara():
    claves = [(0.0, {"boca": 0.0}), (1.0, {"boca": 1.0}), (1.5, None), (2.0, {"ojos": 0.0})]
    cuadros = linea_de_tiempo(claves, fps=10)
    ts = [t for t, _ in cuadros]
    assert ts[0] == 0.0 and ts[-1] == pytest.approx(2.0)
    assert len(cuadros) == 21
    mar = [medir(p).mar for t, p in cuadros if t < 1.0 + 1e-9]
    assert mar == sorted(mar)
    sin_cara = [p for t, p in cuadros if 1.5 <= t < 2.0 - 1e-9]
    assert sin_cara and all(p is None for p in sin_cara)
    assert medir(cuadros[-1][1]).ear_der < 0.15


def test_fuente_secuencia_para_detector_falso():
    cuadros = linea_de_tiempo([(0.0, {}), (1.0, {"boca": 1.0}), (1.2, None)], fps=10)
    f = FuenteSecuencia(cuadros)
    assert medir(f(0.0)).mar < 0.05
    assert medir(f(1.05)).mar > 0.5
    assert f(1.3) is None
    g = FuenteSecuencia(funcion=lambda t: None if t > 1 else {"yaw": 10 * t})
    assert medir(g(1.0)).yaw_n > medir(g(0.0)).yaw_n
    assert g(2.0) is None


def test_normalizar_ida_y_vuelta():
    P = cara()
    n = normalizar(P)
    np.testing.assert_allclose(n * [640, 480, 640], P)


def test_cara_py_es_pura():
    """La lógica no importa ctypes, cv2, tkinter ni mediapipe (regla de oro, sección 2.2)."""
    import inspect
    fuente = inspect.getsource(C)
    for prohibido in ("import cv2", "import tkinter", "import mediapipe", "import ctypes"):
        assert prohibido not in fuente
