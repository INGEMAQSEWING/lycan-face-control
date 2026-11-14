"""Ayudas de las pruebas del paquete C (mover con los ojos). Sin cámara: caras sintéticas.

- ``medidas_mirando(px, py, cabeza_yaw, cabeza_pitch)``: las medidas de la cara sintética que mira
  el punto (px, py) de la pantalla de referencia (con la cabeza girada esos grados).
- ``modelo_sintetico()`` / ``cal_con_mirada()``: un modelo de la mirada ajustado con 9 puntos y
  el paso de la cabeza en movimiento, y la calibración ``CAL_SINTETICA`` con ``"mirada"``.
- ``con_ruido(m, sigma, rng)``: le suma temblor al iris (en unidades del ancho del ojo).
"""
from __future__ import annotations

import copy
import math
from dataclasses import replace
from functools import lru_cache

from conftest import CAL_SINTETICA
from lycan_face_control.calibracion import rect_monitor
from lycan_face_control.cara import medir_si_valida
from lycan_face_control.mapeo import MONITOR_REFERENCIA
from lycan_face_control.mirada import ModeloMirada
from sintetico.cara_sintetica import cara, mirar_a

MON = MONITOR_REFERENCIA
CAMARA = {"ancho": 640, "alto": 480}


@lru_cache(maxsize=4096)
def _medir(px: int, py: int, cy10: int, cp10: int, ojos10: int, baja100: int):
    p = mirar_a(px, py, cy10 / 10.0, cp10 / 10.0, MON)
    return medir_si_valida(cara(**p, ojos=ojos10 / 10.0, iris_baja=baja100 / 100.0), 640, 480)


def medidas_mirando(px, py, cabeza_yaw: float = 0.0, cabeza_pitch: float = 0.0, ojos: float = 1.0,
                    iris_baja: float = 0.0):
    return _medir(int(round(px)), int(round(py)), int(round(cabeza_yaw * 10)), int(round(cabeza_pitch * 10)),
                  int(round(ojos * 10)), int(round(iris_baja * 100)))


def con_ruido(m, sigma: float, rng):
    if m is None or m.iris_x is None or not sigma:
        return m
    return replace(m, iris_x=m.iris_x + float(rng.normal(0, sigma)), iris_y=m.iris_y + float(rng.normal(0, sigma)))


def puntos_9(monitor=MON):
    fr = (0.08, 0.5, 0.92)
    return [(monitor.x + (monitor.ancho - 1) * fx, monitor.y + (monitor.alto - 1) * fy) for fy in fr for fx in fr]


def muestras_calibracion(con_cabeza: bool = True):
    m0 = medidas_mirando(*MON.centro)
    c0 = (m0.yaw_n, m0.pitch_n)
    mu = []
    for x, y in puntos_9():
        m = medidas_mirando(x, y)
        mu.append((m.iris_x, m.iris_y, m.yaw_n, m.pitch_n, x, y))
    if con_cabeza:
        n = 40
        for k in range(n):
            cy = 8 * math.sin(k / n * 2 * math.pi)
            cp = 6 * math.cos(k / n * 4 * math.pi)
            m = medidas_mirando(*MON.centro, cy, cp)
            mu.append((m.iris_x, m.iris_y, m.yaw_n, m.pitch_n, *MON.centro, 3.0 / n))
    return mu, c0


@lru_cache(maxsize=2)
def _modelo(con_cabeza: bool):
    mu, c0 = muestras_calibracion(con_cabeza)
    return ModeloMirada.ajustar(mu, c0, temblor_iris=0.004)


def modelo_sintetico(con_cabeza: bool = True) -> ModeloMirada:
    m = _modelo(con_cabeza)
    return ModeloMirada.desde_dict(m.como_dict())        # copia (el desplazamiento no se comparte)


def cal_con_mirada(monitor=MON, camara=CAMARA, **extra) -> dict:
    cal = copy.deepcopy(CAL_SINTETICA)
    d = _modelo(True).como_dict()
    d.update({"error_px": 40.0, "error_grados": 1.5, "io_fraccion": 124.656 / 640.0,
              "monitor": rect_monitor(monitor), "camara": [camara["ancho"], camara["alto"]],
              "fecha": "2026-11-14 00:00"})
    d.update(extra)
    cal["mirada"] = d
    return cal
