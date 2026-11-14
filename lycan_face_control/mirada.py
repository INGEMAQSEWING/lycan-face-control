"""Mover el puntero con los ojos (versión 1.1, paquete C). Lógica pura con numpy: sin tkinter, sin
cámara y sin Windows.

- ``rasgos(m)``: la posición del iris dentro del ojo (``Medidas.iris_x``/``iris_y``) o None.
- ``ModeloMirada``: de (iris, pose de la cabeza) a un punto de la pantalla. Se ajusta con los
  puntos de la calibración de la mirada:
  - **lineal** (5 puntos): ``[1, ix, iy, dyaw, dpitch]``;
  - **cuadrático** (9 puntos): además ``ix², iy², ix·iy``.
  ``dyaw``/``dpitch`` = la cabeza respecto a la de la calibración (``cabeza0``): la mirada es la
  cabeza más el ojo, y el paso «Ojos fijos, cabeza en movimiento» enseña cuánto pesa la cabeza.
  Mínimos cuadrados con ridge (λ = 1e-3) sobre rasgos estandarizados; una columna que casi no
  cambió en la calibración (la cabeza, si no hubo ese paso) no se usa. Si la matriz está mal
  condicionada (puntos iguales, pocos puntos) no hay modelo (None).
- ``FiltroFijacion``: dos filtros One Euro (x, y) y un detector de sacadas por distancia: en una
  fijación suaviza fuerte; en una sacada (dos cuadros seguidos lejos) salta sin retraso.

Precisión esperada con una cámara web: 3 a 5 grados (3 a 5 cm a 60 cm de la pantalla). Ver
docs/decisiones.md, "Versión 1.1, paquete C".
"""
from __future__ import annotations

import math

import numpy as np

from .filtros import OneEuro

LAMBDA_RIDGE = 1e-3
COND_MAX = 1e6                # número de condición máximo de la matriz de rasgos
PISO_IRIS = 2e-3              # desviación mínima del iris entre puntos (si no, "puntos iguales")
PISO_CABEZA = 2e-3            # la cabeza cambió menos que esto en la calibración: su columna no se usa
TIPOS = ("lineal", "cuadratico")
N_RASGOS = {"lineal": 4, "cuadratico": 7}
MIN_PUNTOS = {"lineal": 5, "cuadratico": 9}
# Temblor del iris con la mirada quieta (en unidades del ancho del ojo). VALOR SUPUESTO: falta grabar
# una serie quieta real con iris (pruebas/datos) para fijarlo con datos (ver docs/decisiones.md).
TEMBLOR_IRIS_FABRICA = 0.004
TEMBLOR_IRIS_MIN, TEMBLOR_IRIS_MAX = 0.0005, 0.05

# Filtro de fijación (suavidad 1..5: más alto = más suave)
FIJACION_MIN_CUTOFF = (1.2, 0.8, 0.5, 0.3, 0.2)
FIJACION_BETA = 0.0           # la sacada la detecta el umbral (no la velocidad del One Euro)
SACADA_MIN_PX = 80.0          # una sacada es un salto de al menos esto (o 6 × el temblor crudo)
SACADA_SIGMAS = 6.0
SACADA_CUADROS = 2            # cuadros seguidos lejos para creer que es una sacada (no un pico)


def _finito(v) -> bool:
    try:
        return v is not None and math.isfinite(float(v))
    except (TypeError, ValueError):
        return False


def rasgos(m):
    """(ix, iy) del iris o None (sin iris, ojo cerrado, NaN)."""
    ix, iy = getattr(m, "iris_x", None), getattr(m, "iris_y", None)
    if not (_finito(ix) and _finito(iy)):
        return None
    return float(ix), float(iy)


def ambos_ojos(m) -> bool:
    """Los dos ojos abiertos y con iris (la calibración de la mirada solo mide así)."""
    return getattr(m, "iris_der", None) is not None and getattr(m, "iris_izq", None) is not None \
        and rasgos(m) is not None


def _vector(ix, iy, dyaw, dpitch, tipo: str) -> list:
    if tipo == "cuadratico":
        return [ix, iy, ix * ix, iy * iy, ix * iy, dyaw, dpitch]
    return [ix, iy, dyaw, dpitch]


def _lista(v, n: int):
    if not isinstance(v, (list, tuple)) or len(v) != n:
        return None
    try:
        out = [float(x) for x in v]
    except (TypeError, ValueError):
        return None
    return out if all(math.isfinite(x) for x in out) else None


class ModeloMirada:
    """Iris + cabeza -> punto de la pantalla (píxeles físicos)."""

    def __init__(self, tipo: str, coef_x, coef_y, media, escala, cabeza0, temblor_iris: float | None = None,
                 desplazamiento=(0.0, 0.0)):
        self.tipo = tipo if tipo in TIPOS else "lineal"
        self.coef_x = [float(v) for v in coef_x]
        self.coef_y = [float(v) for v in coef_y]
        self.media = [float(v) for v in media]
        self.escala = [float(v) for v in escala]      # 0 = columna sin usar
        self.cabeza0 = (float(cabeza0[0]), float(cabeza0[1]))
        t = temblor_iris if _finito(temblor_iris) and float(temblor_iris) > 0 else TEMBLOR_IRIS_FABRICA
        self.temblor_iris = min(max(float(t), TEMBLOR_IRIS_MIN), TEMBLOR_IRIS_MAX)
        self.desplazamiento = (float(desplazamiento[0]), float(desplazamiento[1]))

    # ------------------------------------------------------------ ajuste
    @classmethod
    def ajustar(cls, muestras, cabeza0, tipo: str | None = None, temblor_iris: float | None = None,
                lam: float = LAMBDA_RIDGE):
        """``muestras`` = [(ix, iy, yaw, pitch, x, y[, peso]), ...]. ``tipo`` None = según los puntos
        distintos (9 o más: cuadrático; 5 a 8: lineal). None si no se puede ajustar."""
        try:
            filas = []
            for s in muestras:
                v = [float(a) for a in s[:6]]
                w = float(s[6]) if len(s) > 6 else 1.0
                if not all(math.isfinite(a) for a in v) or not (math.isfinite(w) and w > 0):
                    continue
                filas.append(v + [w])
            if len(filas) < MIN_PUNTOS["lineal"]:
                return None
            y0, p0 = float(cabeza0[0]), float(cabeza0[1])
            if not (math.isfinite(y0) and math.isfinite(p0)):
                return None
        except (TypeError, ValueError, IndexError):
            return None
        A = np.array(filas, dtype=float)
        destinos = {(round(r[4]), round(r[5])) for r in filas}
        if tipo is None:
            tipo = "cuadratico" if len(destinos) >= MIN_PUNTOS["cuadratico"] else "lineal"
        if tipo == "cuadratico" and len(destinos) < MIN_PUNTOS["cuadratico"]:
            tipo = "lineal"
        if len(destinos) < 3:
            return None
        ix, iy = A[:, 0], A[:, 1]
        if np.std(ix) < PISO_IRIS or np.std(iy) < PISO_IRIS:
            return None                                  # los ojos casi no se movieron
        F = np.array([_vector(r[0], r[1], r[2] - y0, r[3] - p0, tipo) for r in filas], dtype=float)
        w = A[:, 6]
        media = np.average(F, axis=0, weights=w)
        desv = np.sqrt(np.average((F - media) ** 2, axis=0, weights=w))
        escala = desv.copy()
        n_r = F.shape[1]
        for j in range(n_r):
            piso = PISO_CABEZA if j >= n_r - 2 else 1e-9
            if not (desv[j] > piso):
                escala[j] = 0.0                          # columna sin usar
        usadas = [j for j in range(n_r) if escala[j] > 0]
        Z = np.zeros((len(filas), len(usadas) + 1))
        Z[:, 0] = 1.0
        for k, j in enumerate(usadas):
            Z[:, k + 1] = (F[:, j] - media[j]) / escala[j]
        try:
            cond = np.linalg.cond(Z * np.sqrt(w)[:, None])
        except np.linalg.LinAlgError:
            return None
        if not math.isfinite(cond) or cond > COND_MAX:
            return None
        sw = np.sqrt(w)[:, None]
        Zw = Z * sw
        reg = lam * np.eye(Z.shape[1])
        reg[0, 0] = 0.0
        M = Zw.T @ Zw + reg * float(np.sum(w))
        coefs = []
        for col in (4, 5):
            b = Zw.T @ (A[:, col] * np.sqrt(w))
            try:
                c = np.linalg.solve(M, b)
            except np.linalg.LinAlgError:
                return None
            if not np.all(np.isfinite(c)):
                return None
            full = [float(c[0])] + [0.0] * n_r
            for k, j in enumerate(usadas):
                full[j + 1] = float(c[k + 1])
            coefs.append(full)
        return cls(tipo, coefs[0], coefs[1], [float(v) for v in media], [float(v) for v in escala], (y0, p0),
                   temblor_iris)

    # ------------------------------------------------------------ uso
    def _z(self, ix, iy, yaw, pitch):
        f = _vector(ix, iy, yaw - self.cabeza0[0], pitch - self.cabeza0[1], self.tipo)
        return [1.0] + [((f[j] - self.media[j]) / self.escala[j]) if self.escala[j] > 0 else 0.0
                        for j in range(len(f))]

    def predecir(self, ix: float, iy: float, yaw: float, pitch: float):
        """Punto (x, y) de la pantalla, sin recortar. None si algún dato no es un número."""
        try:
            z = self._z(float(ix), float(iy), float(yaw), float(pitch))
        except (TypeError, ValueError):
            return None
        x = sum(a * b for a, b in zip(self.coef_x, z)) + self.desplazamiento[0]
        y = sum(a * b for a, b in zip(self.coef_y, z)) + self.desplazamiento[1]
        if not (math.isfinite(x) and math.isfinite(y)):
            return None
        return x, y

    def ganancia_px(self):
        """Píxeles por unidad de iris (cerca del centro de la calibración), por eje: cuánto se
        amplifica el temblor del iris en la pantalla."""
        ix, iy = self.media[0], self.media[1]
        h = 0.01
        y0, p0 = self.cabeza0
        a = self.predecir(ix - h, iy, y0, p0)
        b = self.predecir(ix + h, iy, y0, p0)
        c = self.predecir(ix, iy - h, y0, p0)
        d = self.predecir(ix, iy + h, y0, p0)
        if None in (a, b, c, d):
            return 0.0, 0.0
        gx = math.hypot(b[0] - a[0], b[1] - a[1]) / (2 * h)
        gy = math.hypot(d[0] - c[0], d[1] - c[1]) / (2 * h)
        return gx, gy

    def recentrar(self, crudo, centro):
        """Recentrar con los ojos: la persona mira el centro y ``crudo`` es la mirada medida (sin
        el desplazamiento de ahora). Solo se corrige el desplazamiento (no la forma del modelo)."""
        if crudo is None or not all(_finito(v) for v in (*crudo, *centro)):
            return False
        self.desplazamiento = (float(centro[0]) - float(crudo[0]), float(centro[1]) - float(crudo[1]))
        return True

    def predecir_sin_desplazamiento(self, ix, iy, yaw, pitch):
        p = self.predecir(ix, iy, yaw, pitch)
        if p is None:
            return None
        return p[0] - self.desplazamiento[0], p[1] - self.desplazamiento[1]

    # ------------------------------------------------------------ guardar
    def como_dict(self) -> dict:
        return {"tipo": self.tipo, "coef_x": list(self.coef_x), "coef_y": list(self.coef_y),
                "media": list(self.media), "escala": list(self.escala), "cabeza0": list(self.cabeza0),
                "temblor_iris": self.temblor_iris}

    @classmethod
    def desde_dict(cls, d):
        """El modelo guardado (o None si falta algo o está dañado)."""
        if not isinstance(d, dict):
            return None
        tipo = d.get("tipo")
        if tipo not in TIPOS:
            return None
        n = N_RASGOS[tipo]
        cx, cy = _lista(d.get("coef_x"), n + 1), _lista(d.get("coef_y"), n + 1)
        media, escala = _lista(d.get("media"), n), _lista(d.get("escala"), n)
        c0 = _lista(d.get("cabeza0"), 2)
        if None in (cx, cy, media, escala, c0) or any(e < 0 for e in escala):
            return None
        if escala[0] <= 0 or escala[1] <= 0:
            return None                                   # sin iris no es un modelo de la mirada
        t = d.get("temblor_iris")
        return cls(tipo, cx, cy, media, escala, c0, t if _finito(t) else None)


def px_por_cm(monitor) -> float:
    """Píxeles por centímetro supuestos (no se sabe el tamaño real de la pantalla): una pantalla de
    34,5 cm de ancho (15,6 pulgadas), la más común en los portátiles."""
    try:
        return max(float(monitor.ancho) / 34.5, 1.0)
    except (AttributeError, TypeError, ValueError):
        return 1366 / 34.5


# ---------------------------------------------------------------------------------------------
# Filtro de fijación y sacada
# ---------------------------------------------------------------------------------------------
class FiltroFijacion:
    """En la fijación suaviza fuerte (One Euro con corte bajo); en una sacada (``SACADA_CUADROS``
    cuadros seguidos a más de ``umbral_px`` de la posición filtrada) se reinicia en el punto nuevo:
    el puntero salta sin el retraso del filtro."""

    def __init__(self, suavidad: int = 3, umbral_px: float = SACADA_MIN_PX):
        i = int(min(max(int(suavidad), 1), 5)) - 1
        self.suavidad = i + 1
        self.min_cutoff = FIJACION_MIN_CUTOFF[i]
        self.umbral_px = max(float(umbral_px), 1.0)
        self._fx = OneEuro(self.min_cutoff, FIJACION_BETA, 1.0)
        self._fy = OneEuro(self.min_cutoff, FIJACION_BETA, 1.0)
        self.pos = None
        self._lejos = 0
        self.t_fijacion_desde = None
        self.sacada = False                  # hubo una sacada en este cuadro

    def reiniciar(self):
        self._fx.reset()
        self._fy.reset()
        self.pos = None
        self._lejos = 0
        self.t_fijacion_desde = None
        self.sacada = False

    def __call__(self, x: float, y: float, t: float):
        self.sacada = False
        if self.pos is None:
            self._fx.reset()
            self._fy.reset()
            self.pos = (self._fx(x, t), self._fy(y, t))
            self.t_fijacion_desde = t
            return self.pos
        d = math.hypot(x - self.pos[0], y - self.pos[1])
        self._lejos = self._lejos + 1 if d > self.umbral_px else 0
        if self._lejos >= SACADA_CUADROS:
            self._lejos = 0
            self._fx.reset()
            self._fy.reset()
            self.pos = (self._fx(x, t), self._fy(y, t))
            self.t_fijacion_desde = t
            self.sacada = True
            return self.pos
        if self._lejos:
            return self.pos                  # un cuadro lejos: puede ser un pico; se espera el siguiente
        self.pos = (self._fx(x, t), self._fy(y, t))
        return self.pos

    def en_fijacion(self, t: float, minimo_s: float) -> bool:
        return self.t_fijacion_desde is not None and t - self.t_fijacion_desde >= minimo_s - 1e-9

    def atenuacion(self, dt: float = 0.05) -> float:
        """Cuánto reduce el filtro el temblor (ruido blanco tras un filtro de primer orden)."""
        tau = 1.0 / (2.0 * math.pi * self.min_cutoff)
        a = 1.0 / (1.0 + tau / dt)
        return math.sqrt(a / (2.0 - a))
