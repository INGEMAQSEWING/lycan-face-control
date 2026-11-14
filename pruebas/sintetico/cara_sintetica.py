"""Generador de caras sintéticas para las pruebas (sección 13.1). Sin mediapipe y sin cámara.

Parte de ``pruebas/datos/cara_dibujada_base.json`` (478 puntos reales que MediaPipe sacó de la
cara dibujada de herramientas/cara_dibujada.py) y la deforma:

- ojos (0 cerrado .. 1 abierto): acerca los párpados superiores a los inferiores;
- boca (0..1): baja el labio inferior y un poco el mentón;
- cejas (0..1): sube las cejas;
- sonrisa (0..1): separa y sube las comisuras de la boca;
- cabeza: giro 3D (yaw, pitch, roll en grados) alrededor del centro de la cara;
- escala, posición y ruido gaussiano en píxeles;
- 1.1 paquete C, mirada: ``ojo_yaw``/``ojo_pitch`` (grados) mueven el iris dentro del ojo
  R·sin(ángulo), con R = 0,40 × el ancho del ojo, y el anillo se encoge por cos(ángulo);
  ``ruido_iris`` (px) mueve solo los puntos del iris; ``iris_baja`` (0..1) baja el iris al
  cerrar el ojo (como FaceMesh) y ``parpado_sigue`` (0..1) sube o baja el párpado superior con la
  mirada. ``mirar_a`` da los parámetros para mirar un punto de la pantalla.

Convenciones de signo (iguales a ``lycan_face_control.cara``):
- ``yaw > 0``: la nariz va hacia +x de la imagen (con la imagen en espejo, la persona gira a su
  derecha) => ``yaw_n`` crece.
- ``pitch > 0``: la cabeza baja (la nariz va hacia +y) => ``pitch_n`` crece.
- ``roll > 0``: la cabeza se inclina en sentido horario en la imagen => ``roll`` crece.

Los puntos salen en píxeles: (x, y, z) con z en la escala de x, como ``CaraDetectada.puntos``.
"""
from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path

import numpy as np

RUTA_BASE = Path(__file__).resolve().parents[1] / "datos" / "cara_dibujada_base.json"

# Párpados (sección 13.1)
PARPADO_SUP_DER = (159, 160, 161, 158, 157, 56, 28, 27, 29, 30, 247, 246)
PARPADO_INF_DER = (145, 144, 153, 154, 155, 163, 7)
PARPADO_SUP_IZQ = (386, 385, 384, 387, 388, 286, 258, 257, 259, 260, 467, 466)
PARPADO_INF_IZQ = (374, 373, 380, 381, 382, 390, 249)
COMISURAS_OJO_DER = (33, 133)
COMISURAS_OJO_IZQ = (263, 362)
# Labio inferior y mentón
LABIO_INFERIOR = (14, 87, 178, 88, 95, 317, 402, 318, 324, 15, 16, 17, 84, 181, 91, 146, 314, 405, 321, 375)
MENTON = (152, 148, 176, 149, 150, 377, 400, 378, 379, 175, 199, 200, 18, 83, 313, 201, 421, 208, 428, 171, 396)
# Cejas
CEJA_DER = (70, 63, 105, 66, 107, 46, 53, 52, 65, 55)
CEJA_IZQ = (300, 293, 334, 296, 336, 276, 283, 282, 295, 285)
# Comisuras de la boca (persona: derecha = 61 a la izquierda de la imagen) y vecinas
COMISURA_DER, COMISURA_IZQ = 61, 291
VECINAS_DER = {78: 0.7, 62: 0.5, 76: 0.5, 77: 0.4, 146: 0.4, 185: 0.4, 184: 0.4}
VECINAS_IZQ = {308: 0.7, 292: 0.5, 306: 0.5, 307: 0.4, 375: 0.4, 409: 0.4, 408: 0.4}

# Cuánto se mueve cada gesto a tope (en fracciones de io, la distancia entre ojos)
BOCA_BAJA = 0.36       # MAR ≈ 0,016 -> ≈ 0,7
MENTON_BAJA = 0.5      # fracción del movimiento del labio
CEJAS_SUBEN = 0.13
SONRISA_SEPARA = 0.075  # por lado
SONRISA_SUBE = 0.035


@lru_cache(maxsize=1)
def _base_cruda():
    with open(RUTA_BASE, encoding="utf-8") as f:
        d = json.load(f)
    ancho, alto = d["ancho"], d["alto"]
    norm = np.asarray(d["puntos"], dtype=float)
    return norm * np.array([ancho, alto, ancho], dtype=float), int(ancho), int(alto)


def cara_base() -> np.ndarray:
    """Los 478 puntos de la cara de referencia en píxeles (copia)."""
    return _base_cruda()[0].copy()


def tamano_imagen():
    """(ancho, alto) de la imagen de la cara de referencia."""
    _, ancho, alto = _base_cruda()
    return ancho, alto


def _io(P) -> float:
    return float(np.linalg.norm(P[33] - P[263]))


def _cerrar_ojo(P, base, sup, inf, comisuras, apertura: float):
    """Lleva cada punto del párpado superior hacia el inferior (interpolado por x)."""
    apertura = min(max(float(apertura), 0.0), 1.0)
    if apertura >= 1.0:
        return
    linea = sorted(set(inf) | set(comisuras), key=lambda i: base[i, 0])
    xs = base[linea, 0]
    ys = base[linea, 1]
    zs = base[linea, 2]
    for i in sup:
        x = base[i, 0]
        y_obj = float(np.interp(x, xs, ys))
        z_obj = float(np.interp(x, xs, zs))
        P[i, 1] = y_obj + (base[i, 1] - y_obj) * apertura
        P[i, 2] = z_obj + (base[i, 2] - z_obj) * apertura


def _rotar(L, yaw: float, pitch: float, roll: float):
    """Gira puntos locales (centrados) en 3D. x derecha, y abajo, z hacia el fondo."""
    a, b, c = math.radians(yaw), math.radians(pitch), math.radians(roll)
    x, y, z = L[:, 0].copy(), L[:, 1].copy(), L[:, 2].copy()
    # pitch (eje x): la nariz (z negativa) baja con pitch > 0
    y, z = y * math.cos(b) - z * math.sin(b), y * math.sin(b) + z * math.cos(b)
    # yaw (eje y): la nariz va hacia +x con yaw > 0
    x, z = x * math.cos(a) - z * math.sin(a), x * math.sin(a) + z * math.cos(a)
    # roll (en el plano de la imagen)
    x, y = x * math.cos(c) - y * math.sin(c), x * math.sin(c) + y * math.cos(c)
    return np.stack([x, y, z], axis=1)


# ---- 1.1 paquete C: iris ----
IRIS_DER_PUNTOS = (468, 469, 470, 471, 472)      # centro y anillo
IRIS_IZQ_PUNTOS = (473, 474, 475, 476, 477)
RADIO_GIRO_OJO = 0.40                            # R = 0,40 × el ancho del ojo
DISTANCIA_CM = 60.0
ANCHO_PANTALLA_CM = 34.5                         # pantalla supuesta de 15,6 pulgadas


def _mover_iris(P, base, puntos, comisuras, ojo_yaw, ojo_pitch, apertura, iris_baja, parpado_sigue, sup):
    a, b = comisuras
    ancho = float(np.linalg.norm(base[a, :2] - base[b, :2]))
    r = RADIO_GIRO_OJO * ancho
    cy = math.radians(ojo_yaw)
    cp = math.radians(ojo_pitch)
    dx = r * math.sin(cy)
    dy = r * math.sin(cp)
    if iris_baja:
        dy += float(iris_baja) * (1.0 - min(max(float(apertura), 0.0), 1.0)) * ancho
    c = base[puntos[0]]
    for i in puntos:
        P[i, 0] = c[0] + (base[i, 0] - c[0]) * math.cos(cy) + dx
        P[i, 1] = c[1] + (base[i, 1] - c[1]) * math.cos(cp) + dy
    if parpado_sigue:
        P[list(sup), 1] += float(parpado_sigue) * r * math.sin(cp)


def cara(yaw: float = 0.0, pitch: float = 0.0, roll: float = 0.0, ojo_der: float = 1.0, ojo_izq: float = 1.0,
         boca: float = 0.0, cejas: float = 0.0, sonrisa: float = 0.0, escala: float = 1.0,
         centro=(320.0, 240.0), ruido: float = 0.0, rng=None, ojos: float | None = None,
         ojo_yaw: float = 0.0, ojo_pitch: float = 0.0, ruido_iris: float = 0.0, iris_baja: float = 0.0,
         parpado_sigue: float = 0.0) -> np.ndarray:
    """Una cara sintética: (478, 3) en píxeles. ``ojos`` (si se da) fija ambos ojos a la vez."""
    if ojos is not None:
        ojo_der = ojo_izq = ojos
    base = cara_base()
    P = base.copy()
    io = _io(base)
    # ---- expresión (en la cara de frente, antes de girar) ----
    _cerrar_ojo(P, base, PARPADO_SUP_DER, PARPADO_INF_DER, COMISURAS_OJO_DER, ojo_der)
    _cerrar_ojo(P, base, PARPADO_SUP_IZQ, PARPADO_INF_IZQ, COMISURAS_OJO_IZQ, ojo_izq)
    if ojo_yaw or ojo_pitch or iris_baja:
        _mover_iris(P, base, IRIS_DER_PUNTOS, COMISURAS_OJO_DER, ojo_yaw, ojo_pitch, ojo_der, iris_baja,
                    parpado_sigue, PARPADO_SUP_DER)
        _mover_iris(P, base, IRIS_IZQ_PUNTOS, COMISURAS_OJO_IZQ, ojo_yaw, ojo_pitch, ojo_izq, iris_baja,
                    parpado_sigue, PARPADO_SUP_IZQ)
    if boca:
        dy = max(float(boca), 0.0) * BOCA_BAJA * io
        P[list(LABIO_INFERIOR), 1] += dy
        P[list(MENTON), 1] += dy * MENTON_BAJA
    if cejas:
        dy = max(float(cejas), 0.0) * CEJAS_SUBEN * io
        P[list(CEJA_DER) + list(CEJA_IZQ), 1] -= dy
    if sonrisa:
        s = max(float(sonrisa), 0.0)
        dx, dy = s * SONRISA_SEPARA * io, s * SONRISA_SUBE * io
        lado_der = base[COMISURA_DER, 0] < base[COMISURA_IZQ, 0]   # 61 a la izquierda de la imagen
        sx = -1.0 if lado_der else 1.0
        for idx, peso in [(COMISURA_DER, 1.0), *VECINAS_DER.items()]:
            P[idx, 0] += sx * dx * peso
            P[idx, 1] -= dy * peso
        for idx, peso in [(COMISURA_IZQ, 1.0), *VECINAS_IZQ.items()]:
            P[idx, 0] -= sx * dx * peso
            P[idx, 1] -= dy * peso
    # ---- cabeza: giro alrededor del centro de la cara, escala y posición ----
    c = base.mean(axis=0)
    L = (P - c) * float(escala)
    if yaw or pitch or roll:
        L = _rotar(L, yaw, pitch, roll)
    out = L + np.array([float(centro[0]), float(centro[1]), c[2]])
    if ruido:
        rng = rng if rng is not None else np.random.default_rng()
        out = out + rng.normal(0.0, float(ruido), size=out.shape)
    if ruido_iris:
        rng = rng if rng is not None else np.random.default_rng()
        idx = list(IRIS_DER_PUNTOS + IRIS_IZQ_PUNTOS)
        out[idx, :2] = out[idx, :2] + rng.normal(0.0, float(ruido_iris), size=(len(idx), 2))
    return out


def mirar_a(px: float, py: float, cabeza_yaw: float = 0.0, cabeza_pitch: float = 0.0, monitor=None,
            distancia_cm: float = DISTANCIA_CM, px_por_cm: float | None = None) -> dict:
    """Parámetros de ``cara()`` para mirar el punto (px, py) de la pantalla con la cabeza girada
    ``cabeza_yaw``/``cabeza_pitch`` grados: los ojos giran lo que falta (ángulo al punto menos el
    de la cabeza). La pantalla está a ``distancia_cm`` y tiene ``px_por_cm`` (de fábrica, una de
    34,5 cm de ancho)."""
    if monitor is None:
        from lycan_face_control.mapeo import MONITOR_REFERENCIA as monitor
    if px_por_cm is None:
        px_por_cm = monitor.ancho / ANCHO_PANTALLA_CM
    cx, cy = monitor.centro
    ax = math.degrees(math.atan((px - cx) / px_por_cm / distancia_cm))
    ay = math.degrees(math.atan((py - cy) / px_por_cm / distancia_cm))
    return {"yaw": cabeza_yaw, "pitch": cabeza_pitch, "ojo_yaw": ax - cabeza_yaw, "ojo_pitch": ay - cabeza_pitch}


def centro_base():
    """Centro (x, y) de la cara de referencia: con este ``centro`` la cara no se traslada."""
    c = cara_base().mean(axis=0)
    return float(c[0]), float(c[1])


def normalizar(puntos, ancho: int = 640, alto: int = 480) -> np.ndarray:
    """Píxeles -> como los da MediaPipe (x, y en 0..1; z relativo al ancho)."""
    return np.asarray(puntos, dtype=float) / np.array([ancho, alto, ancho], dtype=float)


_NUMERICOS = ("yaw", "pitch", "roll", "ojo_der", "ojo_izq", "boca", "cejas", "sonrisa", "escala", "ruido",
              "ojo_yaw", "ojo_pitch", "ruido_iris")
# valores de cara() cuando una clave no los nombra
POR_DEFECTO = {"yaw": 0.0, "pitch": 0.0, "roll": 0.0, "ojo_der": 1.0, "ojo_izq": 1.0, "boca": 0.0,
               "cejas": 0.0, "sonrisa": 0.0, "escala": 1.0, "ruido": 0.0, "centro": (320.0, 240.0),
               "ojo_yaw": 0.0, "ojo_pitch": 0.0, "ruido_iris": 0.0}


def _completar(p: dict) -> dict:
    out = dict(POR_DEFECTO)
    out.update(p)
    if out.get("ojos") is not None:          # "ojos" fija los dos ojos
        out["ojo_der"] = out["ojo_izq"] = out.pop("ojos")
    out.pop("ojos", None)
    return out


def _interpolar(a: dict, b: dict, f: float) -> dict:
    a, b = _completar(a), _completar(b)
    out = dict(a)
    for k in set(a) | set(b):
        va, vb = a.get(k), b.get(k)
        if k in _NUMERICOS and isinstance(va, (int, float)) and isinstance(vb, (int, float)):
            out[k] = va + (vb - va) * f
        elif k == "centro" and va is not None and vb is not None:
            out[k] = (va[0] + (vb[0] - va[0]) * f, va[1] + (vb[1] - va[1]) * f)
        elif k not in a:
            out[k] = vb
    return out


def linea_de_tiempo(claves, fps: float = 30.0, rng=None):
    """Secuencia de cuadros: ``claves`` = [(t, params | None), ...] ordenadas por t.

    Devuelve [(t, puntos | None), ...] a ``fps`` cuadros por segundo desde la primera clave hasta
    la última, interpolando linealmente los parámetros numéricos. ``None`` = sin cara (se
    mantiene hasta la clave siguiente). Las claves sin ruido explícito no llevan ruido."""
    claves = sorted(claves, key=lambda c: c[0])
    if not claves:
        return []
    t0, t_fin = claves[0][0], claves[-1][0]
    dt = 1.0 / float(fps)
    n = int(math.floor((t_fin - t0) / dt + 1e-9)) + 1
    out = []
    j = 0
    for k in range(n):
        t = t0 + k * dt
        while j + 1 < len(claves) and claves[j + 1][0] <= t + 1e-12:
            j += 1
        ta, pa = claves[j]
        if pa is None:
            out.append((t, None))
            continue
        if j + 1 < len(claves) and claves[j + 1][1] is not None:
            tb, pb = claves[j + 1]
            f = (t - ta) / (tb - ta) if tb > ta else 0.0
            params = _interpolar(pa, pb, f)
        else:
            params = _completar(pa)
        if (params.get("ruido") or params.get("ruido_iris")) and rng is not None:
            params["rng"] = rng
        out.append((t, cara(**params)))
    return out


class FuenteSecuencia:
    """``fuente(t) -> puntos | None`` para ``DetectorFalso``: devuelve el cuadro de la línea de
    tiempo más cercano por debajo de ``t`` (o una función de t si se pasa ``funcion``)."""

    def __init__(self, cuadros=None, funcion=None, desfase: float = 0.0):
        self.cuadros = list(cuadros or [])
        self.funcion = funcion
        self.desfase = desfase

    def __call__(self, t: float):
        if self.funcion is not None:
            params = self.funcion(t - self.desfase)
            return None if params is None else cara(**params)
        if not self.cuadros:
            return None
        t = t - self.desfase
        sel = self.cuadros[0][1]
        for tc, p in self.cuadros:
            if tc <= t + 1e-9:
                sel = p
            else:
                break
        return sel
