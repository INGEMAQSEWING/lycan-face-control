"""Versión 1.1, paquete C: modelo de la mirada y filtro de fijación (lógica pura, caras sintéticas)."""
import math

import numpy as np
import pytest

from lycan_face_control.calibracion import calibracion_valida, mirada_valida, modelo_mirada
from lycan_face_control.mapeo import Monitor
from lycan_face_control.mirada import FiltroFijacion, ModeloMirada, ambos_ojos, rasgos
from ojos_sinteticos import (CAMARA, MON, cal_con_mirada, con_ruido, medidas_mirando, modelo_sintetico,
                             muestras_calibracion, puntos_9)

VALIDAR = [(300, 200), (1000, 600), (683, 384), (200, 650), (1100, 150)]


def _error(mod, puntos=VALIDAR, cabeza=(0.0,)):
    errs = []
    for x, y in puntos:
        for cy in cabeza:
            m = medidas_mirando(x, y, cy)
            p = mod.predecir(m.iris_x, m.iris_y, m.yaw_n, m.pitch_n)
            errs.append(math.hypot(p[0] - x, p[1] - y))
    return errs


# ------------------------------------------------------------------ rasgos
def test_rasgos_necesitan_iris_finito():
    m = medidas_mirando(400, 300)
    assert rasgos(m) == (m.iris_x, m.iris_y) and ambos_ojos(m)
    from conftest import medidas
    assert rasgos(medidas()) is None and not ambos_ojos(medidas())
    assert rasgos(medidas(iris_x=float("nan"), iris_y=0.0)) is None


# ------------------------------------------------------------------ modelo
def test_nueve_puntos_sin_ruido_error_menor_que_5_px():
    mu, c0 = muestras_calibracion(con_cabeza=False)
    mod = ModeloMirada.ajustar(mu, c0)
    assert mod.tipo == "cuadratico"
    for ix, iy, yaw, pitch, x, y in mu:
        p = mod.predecir(ix, iy, yaw, pitch)
        assert math.hypot(p[0] - x, p[1] - y) < 5.0


TOPE_RUIDO_PX = 60.0        # error mediano documentado con ruido_iris = 0,3 px por punto del iris


def test_con_ruido_del_iris_queda_bajo_el_tope_documentado():
    rng = np.random.default_rng(7)
    from sintetico.cara_sintetica import cara, mirar_a
    from lycan_face_control.cara import medir_si_valida

    def med(x, y, n=12):
        ms = [medir_si_valida(cara(**mirar_a(x, y, monitor=MON), ruido_iris=0.3, rng=rng), 640, 480)
              for _ in range(n)]
        return (float(np.median([m.iris_x for m in ms])), float(np.median([m.iris_y for m in ms])),
                ms[0].yaw_n, ms[0].pitch_n)
    m0 = med(*MON.centro)
    mu = [med(x, y) + (x, y) for x, y in puntos_9()]
    mod = ModeloMirada.ajustar(mu, (m0[2], m0[3]))
    errs = []
    for x, y in VALIDAR:
        r = med(x, y, 6)
        p = mod.predecir(*r)
        errs.append(math.hypot(p[0] - x, p[1] - y))
    assert float(np.median(errs)) < TOPE_RUIDO_PX, errs


def test_con_cinco_puntos_se_usa_el_modelo_lineal():
    mu, c0 = muestras_calibracion(con_cabeza=False)
    cinco = [mu[i] for i in (4, 0, 2, 6, 8)]
    mod = ModeloMirada.ajustar(cinco, c0)
    assert mod is not None and mod.tipo == "lineal"
    assert ModeloMirada.ajustar(cinco, c0, tipo="cuadratico").tipo == "lineal"
    assert max(_error(mod)) < 80


def test_puntos_iguales_nan_o_pocos_no_dan_modelo():
    mu, c0 = muestras_calibracion(con_cabeza=False)
    iguales = [mu[4]] * 9
    assert ModeloMirada.ajustar(iguales, c0) is None
    # los ojos casi no se movieron (mismo iris en todos los puntos)
    quietos = [(mu[4][0], mu[4][1], r[2], r[3], r[4], r[5]) for r in mu]
    assert ModeloMirada.ajustar(quietos, c0) is None
    con_nan = [(float("nan"),) + tuple(r[1:]) for r in mu]
    assert ModeloMirada.ajustar(con_nan, c0) is None
    assert ModeloMirada.ajustar(mu[:3], c0) is None
    assert ModeloMirada.ajustar(mu, (float("nan"), 0.5)) is None
    assert ModeloMirada.ajustar([], c0) is None
    assert ModeloMirada.ajustar([("a", 1)], c0) is None


def test_ida_y_vuelta_por_dict():
    mod = modelo_sintetico()
    d = mod.como_dict()
    import json
    otra = ModeloMirada.desde_dict(json.loads(json.dumps(d)))
    m = medidas_mirando(900, 250, 3)
    assert otra.predecir(m.iris_x, m.iris_y, m.yaw_n, m.pitch_n) == pytest.approx(
        mod.predecir(m.iris_x, m.iris_y, m.yaw_n, m.pitch_n))
    assert otra.temblor_iris == pytest.approx(mod.temblor_iris)


@pytest.mark.parametrize("cambio", [{"tipo": "otro"}, {"coef_x": [1, 2]}, {"media": None},
                                    {"escala": [-1.0] * 7}, {"cabeza0": [float("inf"), 0]},
                                    {"coef_y": ["x"] * 8}])
def test_un_dict_danado_no_da_modelo(cambio):
    d = modelo_sintetico().como_dict()
    d.update(cambio)
    assert ModeloMirada.desde_dict(d) is None
    assert ModeloMirada.desde_dict("nada") is None


def test_cambiar_el_monitor_o_la_camara_invalida_el_modelo():
    cal = cal_con_mirada()
    assert mirada_valida(cal["mirada"], MON, CAMARA)
    assert not mirada_valida(cal["mirada"], Monitor(0, 0, 1920, 1080), CAMARA)
    assert not mirada_valida(cal["mirada"], MON, {"ancho": 1280, "alto": 720})
    assert modelo_mirada(None, MON, CAMARA) is None
    # la calibración de la cabeza sigue valiendo aunque la mirada esté dañada o falte
    cal["mirada"] = {"tipo": "roto"}
    assert calibracion_valida(cal) and not mirada_valida(cal["mirada"], MON, CAMARA)


def test_recentrar_corrige_solo_el_desplazamiento():
    mod = modelo_sintetico()
    m = medidas_mirando(*MON.centro)
    crudo = mod.predecir(m.iris_x, m.iris_y, m.yaw_n, m.pitch_n)
    corrido = (crudo[0] + 50, crudo[1] - 30)                     # como si la mirada se hubiera corrido
    assert mod.recentrar(corrido, MON.centro)
    p = mod.predecir(m.iris_x, m.iris_y, m.yaw_n, m.pitch_n)
    # el punto que daba «corrido» ahora da el centro: lo de ahora queda 50 px a la izquierda y 30 abajo
    assert p == pytest.approx((MON.centro[0] - 50, MON.centro[1] + 30), abs=1e-6)
    assert not mod.recentrar(None, MON.centro)
    assert not mod.recentrar((float("nan"), 1.0), MON.centro)


# ------------------------------------------------------------------ cabeza en movimiento
TOPE_CABEZA_PX = 40.0


def test_con_el_paso_de_la_cabeza_mirar_fijo_girando_la_cabeza_8_grados_tiene_poco_error():
    con = _error(modelo_sintetico(True), cabeza=(-8.0, -4.0, 4.0, 8.0))
    sin = _error(modelo_sintetico(False), cabeza=(-8.0, -4.0, 4.0, 8.0))
    assert max(con) < TOPE_CABEZA_PX, con
    assert float(np.median(sin)) > 4 * float(np.median(con))
    assert float(np.median(sin)) > 100


# ------------------------------------------------------------------ filtro de fijación
def test_en_la_fijacion_el_filtro_reduce_el_temblor():
    rng = np.random.default_rng(1)
    f = FiltroFijacion(3, umbral_px=120)
    salida = []
    for k in range(200):
        x, y = 500 + rng.normal(0, 20), 300 + rng.normal(0, 20)
        salida.append(f(x, y, k * 0.05))
    xs = np.array([p[0] for p in salida[50:]])
    assert np.std(xs) < 20 * 0.5
    assert f.en_fijacion(10.0, 0.25)


def test_una_sacada_salta_sin_el_retraso_del_filtro_y_un_pico_no():
    f = FiltroFijacion(5, umbral_px=80)
    for k in range(20):
        f(200, 200, k * 0.05)
    t = 20 * 0.05
    p = f(800, 200, t)                    # un cuadro lejos: puede ser un pico
    assert p[0] < 300 and not f.sacada
    p = f(200, 200, t + 0.05)             # volvió: era un pico, no se movió
    assert p[0] < 300
    f(800, 200, t + 0.1)
    p = f(800, 200, t + 0.15)             # dos seguidos: sacada
    assert f.sacada and p[0] == pytest.approx(800)
    assert f.t_fijacion_desde == pytest.approx(t + 0.15)
    assert not f.en_fijacion(t + 0.2, 0.25) and f.en_fijacion(t + 0.45, 0.25)


def test_con_ruido_real_de_la_mirada_no_hay_sacadas_falsas():
    rng = np.random.default_rng(2)
    mod = modelo_sintetico()
    m = medidas_mirando(700, 400)
    gx, gy = mod.ganancia_px()
    f = FiltroFijacion(3, max(80.0, 6 * 0.004 * max(gx, gy)))     # como lo arma el puntero
    saltos = 0
    for k in range(600):
        mm = con_ruido(m, 0.004, rng)
        p = mod.predecir(mm.iris_x, mm.iris_y, mm.yaw_n, mm.pitch_n)
        f(p[0], p[1], k / 30)
        saltos += f.sacada
    assert saltos == 0
