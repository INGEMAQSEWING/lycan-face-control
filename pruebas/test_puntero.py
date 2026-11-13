"""Puntero con la cabeza (sección 3.7): filtro, zona muerta, congelar, reentrada, modos."""
import math

import numpy as np
import pytest

from conftest import CAL_SINTETICA
from lycan_face_control.mapeo import MONITOR_REFERENCIA, MapeoCabeza
from lycan_face_control.puntero import Puntero

M = MONITOR_REFERENCIA
Y0, P0 = 0.022, 0.556
RY = 0.089           # rango cómodo a la derecha


def puntero(modo="absoluto", **kw):
    mapeo = MapeoCabeza(M, CAL_SINTETICA, sens_y=1.0)
    return Puntero(mapeo, modo, **kw)


def correr(p, t0, dur, yaw, pitch=P0, fps=30.0):
    """Pose fija (o función de t) durante ``dur``; devuelve [(t, pos)]."""
    out = []
    n = int(round(dur * fps))
    for i in range(n):
        t = t0 + i / fps
        y = yaw(t) if callable(yaw) else yaw
        pt = pitch(t) if callable(pitch) else pitch
        out.append((t, p.actualizar(t, y, pt)))
    return out


def test_pose_fija_converge_al_punto_mapeado():
    p = puntero()
    pose = (Y0 + 0.5 * RY, P0)
    objetivo = p.mapeo.a_pixeles(*pose)
    r = correr(p, 0.0, 2.0, pose[0])
    x, y = r[-1][1]
    assert abs(x - objetivo[0]) <= 4 and abs(y - objetivo[1]) <= 4


def test_temblor_fino_no_mueve_el_puntero():
    """Ruido de ±0,001 en yaw (≈ 8 px crudos) casi no produce movimientos tras el filtro y la zona
    muerta."""
    rng = np.random.default_rng(7)
    p = puntero()
    correr(p, 0.0, 1.0, Y0)
    cambios = 0
    pos = []
    for i in range(90):
        t = 1.0 + i / 30
        pos.append(p.actualizar(t, Y0 + rng.normal(0, 0.001), P0 + rng.normal(0, 0.001)))
        cambios += p.cambio
    xs = [q[0] for q in pos]
    assert max(xs) - min(xs) <= 12
    assert cambios <= 30


def test_no_cambia_si_la_posicion_entera_es_la_misma():
    p = puntero()
    correr(p, 0.0, 1.0, Y0)
    p.actualizar(1.1, Y0, P0)
    assert p.cambio is False


def test_recorte_a_la_pantalla():
    p = puntero()
    r = correr(p, 0.0, 2.0, Y0 + 5 * RY, P0 + 3.0)
    x, y = r[-1][1]
    assert x == M.ancho - 1 and y == M.alto - 1
    r = correr(p, 2.0, 2.0, Y0 - 5 * RY, P0 - 3.0)
    assert r[-1][1] == (0, 0)


def test_congelar_devuelve_la_posicion_de_150_ms_antes():
    p = puntero()
    vel = 0.5 * RY            # el yaw avanza medio rango por segundo
    r = correr(p, 0.0, 1.0, lambda t: Y0 + vel * t)
    t_c = 1.0
    p.congelar(t_c)
    esperado = [pos for t, pos in r if t <= t_c - 0.15 + 1e-9][-1]
    fija = p.posicion
    # la posición fija es la del historial de ~150 ms antes (no la última)
    assert fija == esperado
    assert fija != r[-1][1]
    # mientras está congelado no se mueve aunque la cabeza siga
    r2 = correr(p, t_c, 0.5, lambda t: Y0 + vel * t)
    assert all(pos == fija for _, pos in r2)


def test_descongelar_mezcla_sin_saltos():
    p = puntero()
    correr(p, 0.0, 1.0, Y0)
    p.congelar(1.0)
    correr(p, 1.0, 1.0, Y0 + 0.8 * RY)          # la cabeza se fue mientras estaba congelado
    desde = p.posicion
    p.descongelar(2.0)
    r = correr(p, 2.0, 1.0, Y0 + 0.8 * RY)
    destino = r[-1][1]
    dist = abs(destino[0] - desde[0])
    assert dist > 300
    ant = desde
    for _, pos in r:
        assert abs(pos[0] - ant[0]) <= dist / 8 + 2
        ant = pos


def test_reentrada_sin_saltos_tras_perder_la_cara():
    p = puntero()
    correr(p, 0.0, 1.0, Y0 - 0.6 * RY)
    desde = p.posicion
    p.perder_cara(1.0)
    # vuelve la cara con la cabeza en otro sitio
    r = correr(p, 2.0, 1.5, Y0 + 0.6 * RY)
    destino = r[-1][1]
    dist = abs(destino[0] - desde[0])
    assert dist > 500
    ant = desde
    for _, pos in r:
        assert abs(pos[0] - ant[0]) <= dist / 10 + 1, "salto mayor que 1/10 de la distancia en un cuadro"
        ant = pos
    objetivo = p.mapeo.recortar(*p.mapeo.a_pixeles(Y0 + 0.6 * RY, P0))
    assert abs(destino[0] - objetivo[0]) <= 4


def test_suavidad_mas_alta_es_mas_suave():
    def temblor(nivel):
        rng = np.random.default_rng(3)
        p = puntero(suavidad=nivel, zona_muerta_px=0)
        xs = []
        for i in range(150):
            t = i / 30
            p.actualizar(t, Y0 + 0.3 * RY + rng.normal(0, 0.002), P0)
            xs.append(p.filtrado[0])        # antes de la zona muerta (que crece con el temblor)
        return float(np.std(xs[30:]))
    assert temblor(5) < temblor(1)


def test_modo_relativo_tipo_touchpad():
    """En relativo el puntero se desplaza lo que se movió la cabeza: ir y volver deja el puntero
    donde estaba; ir, "levantar" (recentrar) e ir otra vez acumula."""
    p = puntero("relativo")
    correr(p, 0.0, 1.0, Y0)
    x0 = p.posicion[0]
    correr(p, 1.0, 1.0, Y0 + 0.3 * RY)
    x1 = p.posicion[0]
    assert x1 > x0 + 100
    correr(p, 2.0, 1.0, Y0)
    assert abs(p.posicion[0] - x0) <= 6
    # con la cabeza quieta en otro sitio no se mueve (no es joystick)
    correr(p, 3.0, 1.0, Y0 + 0.3 * RY)
    xa = p.posicion[0]
    correr(p, 4.0, 1.0, Y0 + 0.3 * RY)
    assert abs(p.posicion[0] - xa) <= 1


def test_aceleracion_en_relativo():
    """Un giro rápido avanza más con aceleración que sin ella; uno lento casi igual."""
    def recorrido(acel, dur):
        p = puntero("relativo", aceleracion=acel)
        correr(p, 0.0, 0.5, Y0)
        x0 = p.posicion[0]
        correr(p, 0.5, dur, lambda t: Y0 + 0.25 * RY * min((t - 0.5) / dur, 1.0))
        correr(p, 0.5 + dur, 0.5, Y0 + 0.25 * RY)
        return p.posicion[0] - x0
    rapido_sin, rapido_con = recorrido(0, 0.15), recorrido(3, 0.15)
    assert rapido_con > rapido_sin * 1.2
    lento_sin, lento_con = recorrido(0, 3.0), recorrido(3, 3.0)
    assert lento_con < lento_sin * 1.25


def test_modo_joystick():
    p = puntero("joystick")
    correr(p, 0.0, 1.0, Y0)
    x0 = p.posicion[0]
    # en el centro no se mueve
    correr(p, 1.0, 1.0, Y0)
    assert abs(p.posicion[0] - x0) <= 1
    # la cabeza a la derecha y quieta: el puntero sigue avanzando
    r = correr(p, 2.0, 1.0, Y0 + 0.4 * RY)
    xs = [pos[0] for _, pos in r]
    assert xs[-1] > xs[10] > x0
    # más inclinación = más rápido
    p2 = puntero("joystick")
    correr(p2, 0.0, 1.0, Y0)
    r2 = correr(p2, 1.0, 1.0, Y0 + 0.8 * RY)
    assert (r2[-1][1][0] - r2[10][1][0]) > (xs[-1] - xs[10])


def test_fijar_posicion_en_relativo_sigue_desde_ahi():
    p = puntero("relativo")
    correr(p, 0.0, 1.0, Y0)
    p.fijar_posicion(100, 100, 1.0)
    correr(p, 1.0, 0.5, Y0)
    assert p.posicion == (100, 100)


def test_nunca_nan():
    p = puntero()
    for i in range(60):
        x, y = p.actualizar(i / 30, Y0 + math.sin(i) * 0.5, P0 + math.cos(i))
        assert 0 <= x < M.ancho and 0 <= y < M.alto


@pytest.mark.parametrize("modo", ["absoluto", "relativo", "joystick"])
def test_congelado_no_se_mueve_en_ningun_modo(modo):
    p = puntero(modo)
    correr(p, 0.0, 1.0, Y0)
    p.congelar(1.0)
    fija = p.posicion
    r = correr(p, 1.0, 1.0, Y0 + 0.9 * RY)
    assert all(pos == fija for _, pos in r)
