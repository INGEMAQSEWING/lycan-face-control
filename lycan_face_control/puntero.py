"""Puntero movido con la cabeza (sección 3.7). Lógica pura: recibe la pose y el tiempo real,
devuelve la posición en píxeles. No toca Windows.

Tres modos (``puntero.modo``):
- ``absoluto`` (por defecto): cada pose de la cabeza es un punto fijo de la pantalla (mapeo por
  tramos de ``MapeoCabeza``).
- ``relativo`` (tipo touchpad): el puntero se desplaza lo que se movió la cabeza, con la misma
  ganancia que el absoluto y aceleración opcional; al tocar un borde "se reacomoda" solo.
- ``joystick``: fuera de la zona muerta del centro el puntero avanza a una velocidad que crece con
  lo lejos que esté la cabeza del centro (para quien mueve poco el cuello).

En los tres:
- Filtro One Euro por eje sobre la posición en píxeles (5 niveles de "Suavidad").
- Zona muerta en pantalla (4 px a 1080 de alto, escalada a la resolución): cambios menores no
  mueven el puntero (quita el temblor fino).
- Historial de 0,5 s. ``congelar(t)`` fija el puntero donde estaba ~150 ms antes (los gestos de
  boca, cejas o sonrisa mueven la nariz, y el puntero no debe irse con ellos); al
  ``descongelar`` la posición nueva se mezcla en 300 ms.
- ``perder_cara``/``recuperar_cara``: al volver la cara se mezcla 500 ms desde donde quedó (no
  salta).
- ``actualizar`` devuelve la posición entera; ``cambio`` dice si cambió (no se envía ``Mover``
  si la posición entera es la misma).
"""
from __future__ import annotations

import math
from collections import deque

from .filtros import OneEuro
from .mapeo import MapeoCabeza

# Suavidad 1..5 (sección 3.7): más alto = más suave (y un poco más lento)
SUAVIDAD_MIN_CUTOFF = (2.0, 1.5, 1.0, 0.7, 0.5)
SUAVIDAD_BETA = (0.04, 0.03, 0.02, 0.015, 0.01)
D_CUTOFF = 1.0
# Aceleración 0..3 (0 = apagada): ganancia × (1 + k·v), v en px/s
ACELERACION_K = (0.0, 0.0005, 0.001, 0.002)
ACELERACION_MAX = 4.0           # tope del factor (un tirón no lanza el puntero al otro lado)

HISTORIAL_S = 0.5
CONGELAR_ATRAS_S = 0.15
MEZCLA_DESCONGELAR_S = 0.3
MEZCLA_REENTRADA_S = 0.5
DT_MAX = 0.25                   # un hueco más largo entre cuadros no acumula un salto (joystick)

MODOS = ("absoluto", "relativo", "joystick")


def zona_muerta_escalada(zona_px: float, alto: int) -> float:
    """4 px a 1080 de alto -> proporcional al alto del monitor."""
    return max(float(zona_px), 0.0) * float(alto) / 1080.0


class Puntero:
    def __init__(self, mapeo: MapeoCabeza, modo: str = "absoluto", suavidad: int = 3, zona_muerta_px: float = 4.0,
                 aceleracion: int = 0, posicion_inicial=None):
        self.mapeo = mapeo
        self.modo = modo if modo in MODOS else "absoluto"
        self.poner_suavidad(suavidad)
        self.zona_muerta = zona_muerta_escalada(zona_muerta_px, mapeo.monitor.alto)
        self.aceleracion = int(min(max(int(aceleracion), 0), len(ACELERACION_K) - 1))
        if posicion_inicial is None:
            posicion_inicial = mapeo.monitor.centro
        x, y = mapeo.recortar(*posicion_inicial)
        self._pos = (float(x), float(y))         # posición de salida (sin redondear)
        self._ancla = None                        # posición filtrada que fijó la última salida
        self._f_ant = None                        # posición filtrada anterior (relativo)
        self._t_ant = None
        self.historial: deque = deque()           # (t, x, y) de la salida
        self.congelado = False
        self._pos_fija = None
        self.sin_cara = False
        self._mezcla = None                       # (t0, duración, desde_x, desde_y)
        self._entero = (int(round(self._pos[0])), int(round(self._pos[1])))
        self.cambio = False
        self.velocidad = 0.0                      # px/s de la salida (para la aceleración)
        self.filtrado = None                      # última posición filtrada (sin recortar)
        self._v_filtrada = 0.0

    @classmethod
    def desde_config(cls, cfg: dict, mapeo: MapeoCabeza, posicion_inicial=None):
        p = cfg["puntero"]
        return cls(mapeo, p["modo"], p["suavidad"], p["zona_muerta_px"], p["aceleracion"], posicion_inicial)

    # ------------------------------------------------------------ ajustes
    def poner_suavidad(self, nivel: int):
        i = int(min(max(int(nivel), 1), 5)) - 1
        self.suavidad = i + 1
        self._fx = OneEuro(SUAVIDAD_MIN_CUTOFF[i], SUAVIDAD_BETA[i], D_CUTOFF)
        self._fy = OneEuro(SUAVIDAD_MIN_CUTOFF[i], SUAVIDAD_BETA[i], D_CUTOFF)

    @property
    def posicion(self):
        """Posición entera actual (la última que se habría enviado)."""
        return self._entero

    @property
    def posicion_real(self):
        return self._pos

    # ------------------------------------------------------------ eventos
    def fijar_posicion(self, x: float, y: float, t: float | None = None):
        """El puntero real está en (x, y) (p. ej. lo movió el cuidador con el ratón durante la
        pausa). En absoluto se mezcla 500 ms desde ahí; en relativo y joystick sigue desde ahí."""
        x, y = self.mapeo.recortar(x, y)
        self._pos = (float(x), float(y))
        self._entero = (int(round(x)), int(round(y)))
        self.historial.clear()
        self._ancla = None
        self._f_ant = None
        if t is not None and self.modo == "absoluto":
            self._mezcla = (t, MEZCLA_REENTRADA_S, self._pos[0], self._pos[1])

    def congelar(self, t: float):
        """Fija el puntero en la posición de ~150 ms antes (si no estaba congelado ya)."""
        if self.congelado:
            return
        self.congelado = True
        objetivo = t - CONGELAR_ATRAS_S
        fija = self._pos
        for (th, x, y) in reversed(self.historial):
            if th <= objetivo + 1e-9:
                fija = (x, y)
                break
        else:
            if self.historial:
                fija = (self.historial[0][1], self.historial[0][2])
        self._pos_fija = fija
        self._pos = fija
        self._actualizar_entero()

    def descongelar(self, t: float):
        if not self.congelado:
            return
        self.congelado = False
        self._pos_fija = None
        self._ancla = None
        self._f_ant = None
        if self.modo == "absoluto":
            self._mezcla = (t, MEZCLA_DESCONGELAR_S, self._pos[0], self._pos[1])

    def perder_cara(self, t: float):
        """Sin cara: el puntero se queda donde está."""
        self.sin_cara = True
        self._mezcla = None

    def recuperar_cara(self, t: float):
        """Vuelve la cara: filtros desde cero (sin arrastrar valores viejos) y mezcla de 500 ms
        desde la posición en que quedó."""
        if not self.sin_cara:
            return
        self.sin_cara = False
        self._fx.reset()
        self._fy.reset()
        self.filtrado = None
        self._ancla = None
        self._f_ant = None
        self._t_ant = None
        if self.modo == "absoluto":
            self._mezcla = (t, MEZCLA_REENTRADA_S, self._pos[0], self._pos[1])

    def reiniciar_filtros(self, t: float | None = None):
        """Tras recentrar o cambiar la calibración: sin saltos (mezcla de 500 ms)."""
        self._fx.reset()
        self._fy.reset()
        self.filtrado = None
        self._ancla = None
        self._f_ant = None
        if t is not None and self.modo == "absoluto":
            self._mezcla = (t, MEZCLA_REENTRADA_S, self._pos[0], self._pos[1])

    # ------------------------------------------------------------ paso
    def actualizar(self, t: float, yaw: float, pitch: float):
        """Un cuadro con cara. Devuelve la posición entera (x, y). ``self.cambio`` = cambió."""
        if self.sin_cara:
            self.recuperar_cara(t)
        crudo = self.mapeo.a_pixeles(yaw, pitch)
        fx = self._fx(crudo[0], t)
        fy = self._fy(crudo[1], t)
        dt = DT_MAX if self._t_ant is None else min(max(t - self._t_ant, 1e-3), DT_MAX)
        # rapidez de la cabeza (posición filtrada, cuadro a cuadro) para la aceleración
        if self.filtrado is not None and self._t_ant is not None:
            self._v_filtrada = math.hypot(fx - self.filtrado[0], fy - self.filtrado[1]) / dt
        else:
            self._v_filtrada = 0.0
        self.filtrado = (fx, fy)
        self._t_ant = t
        anterior = self._pos
        if self.congelado:
            self._pos = self._pos_fija if self._pos_fija is not None else self._pos
            self._f_ant = (fx, fy)
        elif self.modo == "absoluto":
            self._paso_absoluto(t, fx, fy)
        elif self.modo == "relativo":
            self._paso_relativo(fx, fy, dt)
        else:
            self._paso_joystick(fx, fy, dt)
        d = math.hypot(self._pos[0] - anterior[0], self._pos[1] - anterior[1])
        self.velocidad = d / dt if dt > 0 else 0.0
        self.historial.append((t, self._pos[0], self._pos[1]))
        while self.historial and self.historial[0][0] < t - HISTORIAL_S:
            self.historial.popleft()
        return self._actualizar_entero()

    def _actualizar_entero(self):
        nuevo = (int(round(self._pos[0])), int(round(self._pos[1])))
        self.cambio = nuevo != self._entero
        self._entero = nuevo
        return nuevo

    def _con_zona_muerta(self, fx: float, fy: float):
        """Posición filtrada con la zona muerta: si se movió menos de ``zona_muerta`` desde la
        última que contó, se queda en esa."""
        if self._ancla is None or math.hypot(fx - self._ancla[0], fy - self._ancla[1]) >= self.zona_muerta:
            self._ancla = (fx, fy)
        return self._ancla

    def _paso_absoluto(self, t: float, fx: float, fy: float):
        ax, ay = self._con_zona_muerta(fx, fy)
        ox, oy = self.mapeo.recortar(ax, ay)
        if self._mezcla is not None:
            t0, dur, dx0, dy0 = self._mezcla
            a = (t - t0) / dur if dur > 0 else 1.0
            if a >= 1.0:
                self._mezcla = None
            else:
                a = max(a, 0.0)
                ox, oy = dx0 + (ox - dx0) * a, dy0 + (oy - dy0) * a
        self._pos = (float(ox), float(oy))

    def _factor_aceleracion(self, v: float) -> float:
        k = ACELERACION_K[self.aceleracion]
        return min(1.0 + k * v, ACELERACION_MAX)

    def _paso_relativo(self, fx: float, fy: float, dt: float):
        ancla_ant = self._ancla
        ax, ay = self._con_zona_muerta(fx, fy)
        if ancla_ant is None or (ax, ay) == ancla_ant:
            return
        dx, dy = ax - ancla_ant[0], ay - ancla_ant[1]
        f = self._factor_aceleracion(self._v_filtrada)
        x, y = self.mapeo.recortar(self._pos[0] + dx * f, self._pos[1] + dy * f)
        self._pos = (float(x), float(y))

    def _paso_joystick(self, fx: float, fy: float, dt: float):
        u, v = self.mapeo.pixeles_a_uv(fx, fy)
        # la zona muerta del centro ya la quitó el mapeo; la sensibilidad de cada eje es la ganancia
        vx, vy = self.mapeo.velocidad_joystick(u, v)
        vx, vy = vx * self.mapeo.sens_x, vy * self.mapeo.sens_y
        rapidez = math.hypot(vx, vy)
        f = self._factor_aceleracion(rapidez)
        x, y = self.mapeo.recortar(self._pos[0] + vx * f * dt, self._pos[1] + vy * f * dt)
        self._pos = (float(x), float(y))

    def uv_actual(self):
        """(u, v) de la pose filtrada (sin sensibilidad), para el modo Desplazar."""
        if self.filtrado is None:
            return 0.0, 0.0
        return self.mapeo.pixeles_a_uv(*self.filtrado)
