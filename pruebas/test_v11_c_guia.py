"""Versión 1.1, paquete C: pasos de la mirada en la calibración guiada (caras sintéticas que miran
los puntos que pide la guía; sin cámara)."""
import math

import numpy as np
import pytest

from conftest import cfg_prueba, medidas
from lycan_face_control import calibracion_guiada as G
from lycan_face_control.calibracion import calibracion_valida, mirada_valida
from lycan_face_control.calibracion_guiada import PASOS_MIRADA, Guia, pasos_para, puntos_mirada
from lycan_face_control.cara import medir_si_valida
from ojos_sinteticos import CAMARA, MON, medidas_mirando
from sintetico.cara_sintetica import cara, mirar_a

DT = 1 / 30


def _cfg(fuente="ojos", **kw):
    return cfg_prueba(**{"puntero.fuente": fuente, **kw})


def _hasta_mirada(g, t):
    """Avanza la guía (cara de frente, sin gestos) hasta el primer paso de la mirada."""
    m = medidas_mirando(*MON.centro)
    while g.paso not in PASOS_MIRADA and not g.terminado:
        g.alimentar(t, m, 0.15)
        t += DT
    return t


def _correr_mirada(g, t, cabeza_movida=None, ojos_cerrados_s=0.0, ruido=0.0, rng=None):
    """Mira cada punto que pide la guía; en «cabeza» mueve la cabeza mirando el centro."""
    cerrados = 0.0
    while g.paso in PASOS_MIRADA and not g.terminado:
        est = g.estado(t)
        if g.paso == "mirada_cabeza" and g.fase == "medir":
            k = t * 2.0
            p = mirar_a(*MON.centro, 7 * math.sin(k), 5 * math.cos(1.7 * k), MON)
            m = medir_si_valida(cara(**p), 640, 480)
        else:
            punto = est.punto or MON.centro
            cy = cabeza_movida(g, est) if cabeza_movida else 0.0
            if cerrados < ojos_cerrados_s and g.paso == "mirada_puntos" and g.fase == "medir":
                cerrados += DT
                m = medidas_mirando(*punto, cy, ojos=0.2)
            else:
                m = medidas_mirando(*punto, cy)
        if ruido and m is not None:
            from dataclasses import replace
            m = replace(m, iris_x=m.iris_x + rng.normal(0, ruido), iris_y=m.iris_y + rng.normal(0, ruido))
        g.alimentar(t, m, 0.15)
        t += DT
    return t


def test_los_pasos_de_la_mirada_solo_con_una_fuente_con_ojos():
    assert not set(PASOS_MIRADA) & set(pasos_para(cfg_prueba()))
    p = pasos_para(_cfg("cabeza_y_ojos"))
    i = p.index("aba")
    assert p[i + 1:i + 5] == list(PASOS_MIRADA)
    # «Solo comunicación» no usa el puntero: no hay pasos de giros ni de la mirada
    assert not set(PASOS_MIRADA) & set(pasos_para(_cfg(**{"teclado.solo_comunicacion": True})))


def test_puntos_de_la_calibracion_a_8_por_ciento_del_borde():
    p9 = puntos_mirada(MON, 9)
    assert len(p9) == 9 and len(puntos_mirada(MON, 5)) == 5
    xs = sorted({round(x) for x, _ in p9})
    assert xs[0] == round(0.08 * 1365) and xs[-1] == round(0.92 * 1365)


def test_una_secuencia_de_9_puntos_da_una_calibracion_de_la_mirada_valida():
    g = Guia(_cfg(), 0.0, preparar_s=0.3, monitor=MON)
    t = _hasta_mirada(g, 0.0)
    t = _correr_mirada(g, t)
    assert len(g.resultados["mirada_puntos"]) == 9
    assert g.modelo_mirada is not None and g.modelo_mirada.tipo == "cuadratico"
    info = g.mirada_info
    assert info["error_px"] < 40 and not info["impreciso"] and info["cm"] >= 1 and info["boton"] >= 1
    # termina los demás pasos y arma la calibración
    m = medidas_mirando(*MON.centro)
    while not g.terminado:
        g.alimentar(t, m, 0.15)
        t += DT
    cal, _largo, _pocos = g.resultado()
    assert calibracion_valida(cal)
    assert mirada_valida(cal["mirada"], MON, CAMARA)
    assert cal["mirada"]["monitor"] == [0, 0, 1366, 768] and cal["mirada"]["camara"] == [640, 480]
    assert cal["mirada"]["io_fraccion"] == pytest.approx(medidas_mirando(*MON.centro).io_px / 640, rel=0.01)
    from lycan_face_control.config import _json_seguro
    assert _json_seguro(cal)


def test_con_5_puntos_el_modelo_es_lineal():
    g = Guia(_cfg(**{"ojos.puntos_cal": 5}), 0.0, preparar_s=0.3, monitor=MON)
    t = _correr_mirada(g, _hasta_mirada(g, 0.0))
    assert len(g.resultados["mirada_puntos"]) == 5 and g.modelo_mirada.tipo == "lineal"


def test_un_punto_con_la_cabeza_movida_se_repite():
    repetidos = {"n": 0}

    def cabeza(g, est):
        # el tercer punto, la primera vez, con la cabeza girada 6 grados
        if g.paso == "mirada_puntos" and g._k == 2 and g._repeticiones == 0:
            return 6.0
        return 0.0
    g = Guia(_cfg(), 0.0, preparar_s=0.3, monitor=MON)
    t = _hasta_mirada(g, 0.0)
    vio_repetir = False
    while g.paso in PASOS_MIRADA and not g.terminado:
        est = g.estado(t)
        vio_repetir = vio_repetir or est.repetir_punto
        if g.paso == "mirada_puntos" and g.fase == "medir":
            m = medidas_mirando(*est.punto, cabeza(g, est))
        else:
            m = medidas_mirando(*(est.punto or MON.centro))
        g.alimentar(t, m, 0.15)
        t += DT
        if g.paso != "mirada_puntos" and "mirada_puntos" in g.resultados:
            break
    assert vio_repetir
    assert len(g.resultados["mirada_puntos"]) == 9
    del repetidos


def test_la_cabeza_siempre_movida_no_deja_la_guia_en_un_ciclo_sin_fin():
    g = Guia(_cfg(), 0.0, preparar_s=0.3, monitor=MON)
    t = _hasta_mirada(g, 0.0)
    t0 = t
    t = _correr_mirada(g, t, cabeza_movida=lambda g, est: 6.0 if g.paso == "mirada_puntos" else 0.0)
    assert len(g.resultados["mirada_puntos"]) == 9
    assert t - t0 < 9 * 2.2 * (G.REPETIR_PUNTO_MAX + 1) + 30


def test_sin_ver_los_ojos_el_reloj_se_detiene():
    g = Guia(_cfg(), 0.0, preparar_s=0.3, monitor=MON)
    t = _hasta_mirada(g, 0.0)
    m = medidas_mirando(*MON.centro)
    while g.fase != "medir":
        g.alimentar(t, m, 0.15)
        t += DT
    sin_iris = medidas()                       # cara sin iris (468 puntos)
    cerrados = medidas_mirando(*MON.centro, ojos=0.2)
    for k in range(90):
        est = g.alimentar(t, sin_iris if k % 2 else cerrados, 0.15)
        t += DT
    assert g.paso == "mirada_centro" and est.progreso == 0.0 and est.sin_ojos
    for _ in range(int(2.2 / DT)):
        est = g.alimentar(t, m, 0.15)
        t += DT
    assert g.paso == "mirada_puntos" and not est.sin_ojos


def test_sin_cara_el_reloj_tambien_se_detiene():
    g = Guia(_cfg(), 0.0, preparar_s=0.3, monitor=MON)
    t = _hasta_mirada(g, 0.0)
    for _ in range(100):
        g.alimentar(t, None, None)
        t += DT
    assert g.paso == "mirada_centro"


def test_los_ojos_que_casi_no_se_mueven_no_dan_modelo_ni_mirada_en_la_calibracion():
    g = Guia(_cfg(), 0.0, preparar_s=0.3, monitor=MON)
    t = _hasta_mirada(g, 0.0)
    m = medidas_mirando(*MON.centro)
    while g.paso in PASOS_MIRADA:
        g.alimentar(t, m, 0.15)                # siempre mira el centro
        t += DT
    assert g.modelo_mirada is None and g.mirada_info is None
    while not g.terminado:
        g.alimentar(t, m, 0.15)
        t += DT
    cal, _l, _p = g.resultado()
    assert "mirada" not in cal and calibracion_valida(cal)


def test_puntos_cal_7_se_corrige_a_9():
    cfg = _cfg(**{"ojos.puntos_cal": 7})
    assert cfg["ojos"]["puntos_cal"] == 9
    g = Guia(cfg, 0.0, preparar_s=0.3, monitor=MON)
    assert len(g._puntos_paso("mirada_puntos")) == 9


def test_repetir_y_atras_en_los_pasos_de_la_mirada():
    g = Guia(_cfg(), 0.0, preparar_s=0.3, monitor=MON)
    t = _hasta_mirada(g, 0.0)
    m = medidas_mirando(*MON.centro)
    while g.paso != "mirada_puntos":
        g.alimentar(t, m, 0.15)
        t += DT
    for _ in range(int(3 / DT)):
        est = g.estado(t)
        g.alimentar(t, medidas_mirando(*est.punto), 0.15)
        t += DT
    assert g._k >= 1
    g.repetir(t)
    assert g._k == 0 and "mirada_puntos" not in g.resultados
    g.atras(t)
    assert g.paso == "mirada_centro"


# ---- revisión de la 1.1: los pasos de la mirada nunca quedan detenidos para siempre ----
def test_sin_ver_los_ojos_en_el_centro_se_dejan_los_ojos_y_sigue_la_calibracion():
    """Un párpado caído (o lentes con reflejo): sin los dos ojos abiertos 15 s, la guía no espera
    más: los ojos quedan sin calibrar (el puntero seguirá con la cabeza) y la calibración sigue."""
    g = Guia(_cfg(), 0.0, preparar_s=0.3, monitor=MON)
    t = _hasta_mirada(g, 0.0)
    cerrados = medidas_mirando(*MON.centro, ojos=0.2)
    n = 0
    while g.paso == "mirada_centro" and n < int(60 / DT):          # nunca más de 1 minuto
        g.alimentar(t, cerrados, 0.15)
        t += DT
        n += 1
    assert g.paso not in PASOS_MIRADA, g.paso
    assert n * DT <= G.MIRADA_SIN_OJOS_MAX_S + 0.3 + 1.0
    assert g.modelo_mirada is None and "mirada_sin_ojos" in g.avisos
    # la calibración de la cabeza termina bien y sin la parte de los ojos
    m = medidas_mirando(*MON.centro)
    while not g.terminado:
        g.alimentar(t, m, 0.15)
        t += DT
    cal = g.resultado()
    cal = cal[0] if isinstance(cal, tuple) else cal
    assert "mirada" not in cal


def test_un_punto_que_no_se_puede_mirar_se_salta():
    g = Guia(_cfg(), 0.0, preparar_s=0.3, monitor=MON)
    t = _hasta_mirada(g, 0.0)
    while g.paso == "mirada_centro":
        g.alimentar(t, medidas_mirando(*MON.centro), 0.15)
        t += DT
    assert g.paso == "mirada_puntos"
    # el primer punto (arriba a la izquierda) no se logra: los ojos se ven medio cerrados
    k0 = g._k
    while g._k == k0:
        est = g.estado(t)
        g.alimentar(t, medidas_mirando(*est.punto, ojos=0.2), 0.15)
        t += DT
    t = _correr_mirada(g, t)
    assert len(g.resultados["mirada_puntos"]) == 8
    assert g.modelo_mirada is not None


def test_si_no_quedan_5_puntos_se_dejan_los_ojos():
    g = Guia(_cfg(), 0.0, preparar_s=0.3, monitor=MON)
    t = _hasta_mirada(g, 0.0)
    while g.paso == "mirada_centro":
        g.alimentar(t, medidas_mirando(*MON.centro), 0.15)
        t += DT
    n = 0
    while g.paso == "mirada_puntos" and n < int(5 * 60 / DT):
        est = g.estado(t)
        g.alimentar(t, medidas_mirando(*(est.punto or MON.centro), ojos=0.2), 0.15)
        t += DT
        n += 1
    assert g.paso not in PASOS_MIRADA
    assert g.modelo_mirada is None and "mirada_sin_ojos" in g.avisos
    # 9 puntos: al quinto saltado ya no pueden quedar 5 (no se espera 9 × 15 s)
    assert n * DT < 5 * (G.MIRADA_SIN_OJOS_MAX_S + 1.5)
