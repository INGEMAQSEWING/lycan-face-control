"""Monitores y mapeo de la pose de la cabeza a la pantalla (sección 3.6). Lógica pura.

``Monitor``, ``zona_segura`` y ``MONITOR_REFERENCIA`` se copian de Lycan Mouse Control.
``MapeoCabeza`` convierte ``yaw_n``/``pitch_n`` en (u, v): 0 en el centro y ±1 en el extremo
cómodo calibrado de cada lado, con zona muerta en el centro; luego en píxeles (``a_pixeles``) o en
velocidad para el modo joystick (``velocidad_joystick``).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

BARRA_TAREAS_PX = 48     # alto típico de la barra de tareas de Windows 11 (si no se conoce)


@dataclass(frozen=True)
class Monitor:
    x: int
    y: int
    ancho: int
    alto: int
    principal: bool = True
    # Área de trabajo (sin la barra de tareas) como (izq, arriba, der, abajo) exclusivo, o None.
    trabajo: tuple | None = field(default=None, compare=False)

    @property
    def rect(self):
        return (self.x, self.y, self.x + self.ancho, self.y + self.alto)

    @property
    def centro(self):
        return (self.x + (self.ancho - 1) / 2.0, self.y + (self.alto - 1) / 2.0)

    def zona_segura(self, margen: int = 60):
        """Rectángulo (x0, y0, x1, y1) inclusivo, lejos de los bordes y de la barra de tareas."""
        if self.trabajo is not None:
            l, t, r, b = self.trabajo
        else:
            l, t, r, b = self.x, self.y, self.x + self.ancho, self.y + self.alto - BARRA_TAREAS_PX
        l, t = max(l, self.x), max(t, self.y)
        r, b = min(r, self.x + self.ancho), min(b, self.y + self.alto)
        mx = min(margen, max((r - l) // 4, 0))
        my = min(margen, max((b - t) // 4, 0))
        return (l + mx, t + my, r - 1 - mx, b - 1 - my)

    def recortar(self, x: float, y: float):
        """(x, y) dentro del monitor."""
        return (min(max(x, self.x), self.x + self.ancho - 1), min(max(y, self.y), self.y + self.alto - 1))


MONITOR_REFERENCIA = Monitor(0, 0, 1366, 768, True)


# ---------------------------------------------------------------------------------------------
# Mapeo de la cabeza (sección 3.6)
# ---------------------------------------------------------------------------------------------
# Sin calibración: rango cómodo de fábrica (cara real: ±20° de giro ≈ ±0,12 de yaw_n; se toma
# ~15° como "cómodo"). El centro se toma de la propia persona con un recentrado automático al ver
# la cara por primera vez (ver estados.py).
RANGO_YAW_FABRICA = 0.09
RANGO_PITCH_FABRICA = 0.08
CENTRO_FABRICA = (0.0, 0.55)
RANGO_MINIMO_YAW = 0.02          # menos que esto no es un rango usable (calibración)
RANGO_MINIMO_PITCH = 0.03
U_MAX_JOYSTICK = 1.5             # más allá de 1,5 veces el extremo cómodo no acelera más


def _num(v, defecto: float) -> float:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return defecto
    return v if math.isfinite(v) else defecto


class MapeoCabeza:
    """Pose de la cabeza -> (u, v) -> píxeles del monitor.

    - ``centro`` = (yaw0, pitch0); ``izq``/``der``/``arr``/``aba`` = valores de yaw/pitch en el
      extremo cómodo de cada lado (percentil 90 de la calibración). Si ``der`` < ``yaw0`` el eje
      está invertido: el signo sale de la calibración, no se adivina.
    - Mapeo por tramos: u = (yaw - yaw0)/(der - yaw0) hacia la derecha y
      (yaw - yaw0)/(yaw0 - izq) hacia la izquierda (igual con pitch: ``aba`` abajo, ``arr`` arriba).
    - Zona muerta del centro: |u| < zm => 0, y el resto se reescala para seguir llegando a 1.
    - Píxeles: x = cx + u·sens_x·(W/2)·(1 + margen) (lo recorta quien lo use): el borde se
      alcanza un poco antes del extremo cómodo.
    """

    def __init__(self, monitor: Monitor | None = None, calibracion: dict | None = None, sens_x: float = 1.0,
                 sens_y: float = 1.2, zona_muerta: float = 0.03, margen: float = 0.10,
                 joystick_g: float = 1200.0):
        self.monitor = monitor or MONITOR_REFERENCIA
        self.sens_x = float(sens_x)
        self.sens_y = float(sens_y)
        self.zona_muerta = min(max(float(zona_muerta), 0.0), 0.5)
        self.margen = max(float(margen), 0.0)
        self.joystick_g = float(joystick_g)
        self.calibrado = False
        self.yaw0, self.pitch0 = CENTRO_FABRICA
        self.r_der = self.r_izq = RANGO_YAW_FABRICA
        self.r_aba = self.r_arr = RANGO_PITCH_FABRICA
        self.signo_x = 1.0
        self.signo_y = 1.0
        if calibracion:
            self.poner_calibracion(calibracion)

    @classmethod
    def desde_config(cls, cfg: dict, monitor: Monitor | None = None, calibracion: dict | None = None):
        p = cfg["puntero"]
        # Ronda 3: la zona muerta del centro solo en el modo Palanca. En Directo y Almohadilla
        # creaba una franja plana: la cabeza seguía girando, el puntero se quedaba quieto en el
        # centro y la permanencia lo tomaba por "quieto" (clic no pedido al pasar despacio). Se
        # probó también una curva suave (parábola sin tramo plano): daba aún más clics al pasar
        # despacio (17 contra 5 en 10 pasadas a 60 px/s). El temblor lo controlan el filtro, la
        # zona muerta en px y el radio de la permanencia.
        zm = p["zona_muerta_centro"] if p.get("modo") == "joystick" else 0.0
        return cls(monitor, calibracion, sens_x=p["sens_x"], sens_y=p["sens_y"],
                   zona_muerta=zm, margen=p["margen"], joystick_g=p["joystick_g"])

    # ------------------------------------------------------------ calibración
    def poner_calibracion(self, cal: dict | None):
        """Usa una calibración (dict de la sección 9). Si está incompleta o rara, se queda con los
        valores de fábrica en lo que falte (nunca falla)."""
        if not isinstance(cal, dict):
            return
        c = cal.get("centro")
        if isinstance(c, (list, tuple)) and len(c) == 2:
            self.yaw0 = _num(c[0], self.yaw0)
            self.pitch0 = _num(c[1], self.pitch0)
        nan = float("nan")
        der, izq = _num(cal.get("der"), nan), _num(cal.get("izq"), nan)
        arr, aba = _num(cal.get("arr"), nan), _num(cal.get("aba"), nan)
        # signo del eje: hacia dónde queda "der" respecto al centro (o el dado en la calibración)
        sx = _num(cal.get("signo_x"), nan)
        if math.isfinite(der) and abs(der - self.yaw0) > 1e-9:
            sx = 1.0 if der > self.yaw0 else -1.0
        self.signo_x = -1.0 if math.isfinite(sx) and sx < 0 else 1.0
        sy = _num(cal.get("signo_y"), nan)
        if math.isfinite(aba) and abs(aba - self.pitch0) > 1e-9:
            sy = 1.0 if aba > self.pitch0 else -1.0
        self.signo_y = -1.0 if math.isfinite(sy) and sy < 0 else 1.0
        if math.isfinite(der):
            self.r_der = max(abs(der - self.yaw0), RANGO_MINIMO_YAW)
        if math.isfinite(izq):
            self.r_izq = max(abs(izq - self.yaw0), RANGO_MINIMO_YAW)
        if math.isfinite(aba):
            self.r_aba = max(abs(aba - self.pitch0), RANGO_MINIMO_PITCH)
        if math.isfinite(arr):
            self.r_arr = max(abs(arr - self.pitch0), RANGO_MINIMO_PITCH)
        self.calibrado = True

    def recentrar(self, yaw0: float, pitch0: float):
        """Mueve el centro sin tocar los rangos (la postura en cama o silla cambia en el día)."""
        if math.isfinite(yaw0) and math.isfinite(pitch0):
            self.yaw0, self.pitch0 = float(yaw0), float(pitch0)

    # ------------------------------------------------------------ cálculo
    def _eje(self, d: float, r_pos: float, r_neg: float) -> float:
        u = d / r_pos if d >= 0 else d / r_neg
        zm = self.zona_muerta
        a = abs(u)
        if zm <= 0.0:
            return u
        if a <= zm:
            return 0.0
        return math.copysign((a - zm) / (1.0 - zm), u)

    def normalizar(self, yaw: float, pitch: float):
        """(u, v) sin sensibilidad: 0 en el centro, ±1 en el extremo cómodo; sin recortar."""
        u = self._eje(self.signo_x * (yaw - self.yaw0), self.r_der, self.r_izq)
        v = self._eje(self.signo_y * (pitch - self.pitch0), self.r_aba, self.r_arr)
        return u, v

    def escala_px(self):
        """Píxeles por unidad de (u, v), ya con la sensibilidad de cada eje."""
        m = self.monitor
        return (self.sens_x * (m.ancho / 2.0) * (1.0 + self.margen),
                self.sens_y * (m.alto / 2.0) * (1.0 + self.margen))

    def ganancia_uv(self):
        """Unidades de (u, v) por unidad de pose (el lado más sensible de cada eje)."""
        f = 1.0 / (1.0 - self.zona_muerta) if self.zona_muerta < 1.0 else 1.0
        return f / max(min(self.r_der, self.r_izq), 1e-6), f / max(min(self.r_aba, self.r_arr), 1e-6)

    def ganancia_px(self):
        """Píxeles por unidad de pose (yaw_n, pitch_n), con la sensibilidad: cuánto se amplifica el
        temblor de la cabeza en la pantalla."""
        ux, uy = self.ganancia_uv()
        ex, ey = self.escala_px()
        return ux * ex, uy * ey

    def a_pixeles(self, yaw: float, pitch: float):
        """Posición (sin recortar) del modo absoluto."""
        u, v = self.normalizar(yaw, pitch)
        return self.uv_a_pixeles(u, v)

    def uv_a_pixeles(self, u: float, v: float):
        cx, cy = self.monitor.centro
        ex, ey = self.escala_px()
        return cx + u * ex, cy + v * ey

    def pixeles_a_uv(self, x: float, y: float):
        """Inverso de ``uv_a_pixeles`` (con la sensibilidad incluida)."""
        cx, cy = self.monitor.centro
        ex, ey = self.escala_px()
        return ((x - cx) / ex if ex else 0.0), ((y - cy) / ey if ey else 0.0)

    def velocidad_joystick(self, u: float, v: float):
        """Modo joystick: velocidad en px/s = g·|u|^1,5 en la dirección de (u, v), por eje.
        (u, v) ya vienen sin la zona muerta del centro."""
        def eje(a):
            a = max(-U_MAX_JOYSTICK, min(U_MAX_JOYSTICK, a))
            return math.copysign(self.joystick_g * abs(a) ** 1.5, a) if a else 0.0
        return eje(u), eje(v)

    def recortar(self, x: float, y: float):
        return self.monitor.recortar(x, y)

    def como_dict(self) -> dict:
        """Lo que hoy usa el mapeo, con las claves de la calibración."""
        return {"centro": [self.yaw0, self.pitch0], "der": self.yaw0 + self.signo_x * self.r_der,
                "izq": self.yaw0 - self.signo_x * self.r_izq, "aba": self.pitch0 + self.signo_y * self.r_aba,
                "arr": self.pitch0 - self.signo_y * self.r_arr, "signo_x": self.signo_x, "signo_y": self.signo_y}
