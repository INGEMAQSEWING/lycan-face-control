"""Medidas puras de la cara (sección 3.4). Sin mediapipe, cv2, tkinter ni ctypes.

Todas las distancias se dividen por ``io`` (distancia 3D entre las comisuras externas de los
ojos, 33-263), así no cambian al acercarse o alejarse de la cámara.

| Medida   | Fórmula                                                                 |
|----------|-------------------------------------------------------------------------|
| io       | d(P33, P263)                                                            |
| ejes     | ex = unitario2D(P263 − P33), ey = (−ex.y, ex.x)                         |
| roll     | atan2(ex.y, ex.x) en grados                                             |
| yaw_n    | v = P1 − medio(33, 263); yaw_n = (v·ex) / io (2D)                       |
| pitch_n  | boca = medio(61, 291); pitch_n = (v·ey) / ((boca − ojos)·ey)            |
| EAR      | (d(p2,p6) + d(p3,p5)) / (2·d(p1,p4)) por ojo                            |
| MAR      | d(P13, P14) / d(P78, P308)                                              |
| cejas    | media de d(ceja_k, centro de las comisuras del ojo) / io, ambos lados   |
| sonrisa  | d(P61, P291) / io                                                       |

``yaw_n`` y ``pitch_n`` son la pose RELATIVA de la nariz respecto a los ojos y la boca: mover el
cuerpo (sin girar la cabeza), acercarse o inclinar la cabeza de lado casi no los cambia.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .constantes import (BOCA_INT_DER, BOCA_INT_IZQ, CEJA_DER, CEJA_IZQ, COMISURA_DER, COMISURA_IZQ, EAR_DER,
                         EAR_IZQ, IO_MIN_PX, LABIO_INF, LABIO_SUP, N_PUNTOS_MIN, NARIZ, OJO_DER_EXT, OJO_DER_INT,
                         OJO_IZQ_EXT, OJO_IZQ_INT, PUNTOS_CLAVE)


@dataclass(frozen=True)
class Medidas:
    io_px: float      # escala de la cara en píxeles
    yaw_n: float      # giro a los lados (positivo = la nariz va hacia +x de la imagen)
    pitch_n: float    # arriba/abajo (crece al bajar la nariz); centro típico ≈ 0,55
    roll: float       # inclinación de lado, en grados
    ear_der: float    # apertura del ojo derecho de la persona
    ear_izq: float    # apertura del ojo izquierdo
    mar: float        # apertura de la boca
    cejas: float      # altura de las cejas
    sonrisa: float    # ancho de la boca

    def como_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


def _d(P, a: int, b: int) -> float:
    return float(np.linalg.norm(P[a] - P[b]))


def ear(P, ojo) -> float:
    """Eye Aspect Ratio de un ojo: [p1, p2, p3, p4, p5, p6]."""
    p1, p2, p3, p4, p5, p6 = ojo
    ancho = _d(P, p1, p4)
    if ancho <= 1e-9:
        return float("nan")
    return (_d(P, p2, p6) + _d(P, p3, p5)) / (2.0 * ancho)


def _ceja_lado(P, ceja, a: int, b: int) -> float:
    centro = (P[a] + P[b]) / 2.0
    return float(np.mean([np.linalg.norm(P[i] - centro) for i in ceja]))


def medir(puntos) -> Medidas:
    """Calcula todas las medidas. ``puntos``: (N >= 468, 3) en píxeles (x, y, z·ancho).

    No comprueba la validez: llame antes a ``puntos_validos``. Si la cara es degenerada
    (io = 0) devuelve NaN en todo."""
    P = np.asarray(puntos, dtype=float)
    io = _d(P, OJO_DER_EXT, OJO_IZQ_EXT)
    eje = (P[OJO_IZQ_EXT] - P[OJO_DER_EXT])[:2]
    n_eje = float(np.linalg.norm(eje))
    if io <= 1e-9 or n_eje <= 1e-9:
        nan = float("nan")
        return Medidas(io, nan, nan, nan, nan, nan, nan, nan, nan)
    ex = eje / n_eje
    ey = np.array([-ex[1], ex[0]])
    roll = math.degrees(math.atan2(ex[1], ex[0]))
    ojos = (P[OJO_DER_EXT] + P[OJO_IZQ_EXT]) / 2.0
    boca = (P[COMISURA_DER] + P[COMISURA_IZQ]) / 2.0
    v = (P[NARIZ] - ojos)[:2]
    yaw_n = float(v @ ex) / io
    alto_cara = float((boca - ojos)[:2] @ ey)
    pitch_n = float(v @ ey) / alto_cara if abs(alto_cara) > 1e-9 else float("nan")
    ancho_boca = _d(P, BOCA_INT_DER, BOCA_INT_IZQ)
    mar = _d(P, LABIO_SUP, LABIO_INF) / ancho_boca if ancho_boca > 1e-9 else float("nan")
    cejas = (_ceja_lado(P, CEJA_DER, OJO_DER_EXT, OJO_DER_INT)
             + _ceja_lado(P, CEJA_IZQ, OJO_IZQ_INT, OJO_IZQ_EXT)) / 2.0 / io
    sonrisa = _d(P, COMISURA_DER, COMISURA_IZQ) / io
    return Medidas(io_px=io, yaw_n=yaw_n, pitch_n=pitch_n, roll=roll,
                   ear_der=ear(P, EAR_DER), ear_izq=ear(P, EAR_IZQ),
                   mar=mar, cejas=cejas, sonrisa=sonrisa)


def puntos_validos(puntos, ancho: float | None = None, alto: float | None = None,
                   io_min: float = IO_MIN_PX, tolerancia: float = 0.0) -> bool:
    """True si se puede confiar en las medidas: forma correcta, sin NaN ni infinitos,
    ``io >= io_min`` px y (si se dan ``ancho`` y ``alto``) los puntos que se usan para medir
    dentro de la imagen (con ``tolerancia`` en píxeles)."""
    if puntos is None:
        return False
    try:
        P = np.asarray(puntos, dtype=float)
    except (TypeError, ValueError):
        return False
    if P.ndim != 2 or P.shape[0] < N_PUNTOS_MIN or P.shape[1] < 2:
        return False
    if not np.all(np.isfinite(P)):
        return False
    if P.shape[1] == 2:
        P = np.hstack([P, np.zeros((P.shape[0], 1))])
    if _d(P, OJO_DER_EXT, OJO_IZQ_EXT) < io_min:
        return False
    if ancho is not None and alto is not None:
        clave = P[list(PUNTOS_CLAVE), :2]
        if (clave[:, 0].min() < -tolerancia or clave[:, 1].min() < -tolerancia
                or clave[:, 0].max() > ancho + tolerancia or clave[:, 1].max() > alto + tolerancia):
            return False
    return True


def medir_si_valida(puntos, ancho=None, alto=None) -> Medidas | None:
    """``medir`` solo si ``puntos_validos``; si no, None (se trata como "sin cara")."""
    if not puntos_validos(puntos, ancho, alto):
        return None
    m = medir(puntos)
    valores = (m.yaw_n, m.pitch_n, m.ear_der, m.ear_izq, m.mar, m.cejas, m.sonrisa)
    if not all(math.isfinite(x) for x in valores):
        return None
    return m


def posicion_y_tamano(puntos, ancho: float, alto: float):
    """Para la calibración (paso "Posición"): centro de la cara en 0..1 de la imagen y ``io``
    como fracción del ancho de la imagen (bien entre 0,09 y 0,22)."""
    P = np.asarray(puntos, dtype=float)
    io = _d(P, OJO_DER_EXT, OJO_IZQ_EXT)
    ojos = (P[OJO_DER_EXT] + P[OJO_IZQ_EXT]) / 2.0
    return (float(ojos[0] / ancho), float(ojos[1] / alto)), float(io / ancho)
