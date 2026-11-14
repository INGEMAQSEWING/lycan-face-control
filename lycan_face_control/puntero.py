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
- Filtro One Euro por eje sobre la **pose de la cabeza** (yaw_n, pitch_n), no sobre los píxeles
  (ronda 2 de arreglos): así ni ``min_cutoff`` ni ``beta`` dependen de la ganancia del mapeo. Con
  un rango calibrado pequeño (persona con ELA que mueve poco el cuello) el temblor de FaceMesh ya
  no abre el filtro.
- **Temblor esperado en píxeles** (``temblor_px``): el temblor de la cabeza quieta (medido en la
  calibración, o el de fábrica) × lo que lo atenúa el filtro × la ganancia (px por unidad de
  pose). La zona muerta en pantalla (4 px a 1080 de alto, escalada) crece hasta
  ``ZONA_MUERTA_SIGMAS``·temblor_px, y la permanencia usa ese mismo valor para su radio
  (``estados.py``): el temblor no hace clics fantasma y quedarse quieto a propósito sí hace clic.
- Joystick: zona muerta propia mucho mayor que el temblor (``JOYSTICK_ZONA_MIN`` o
  ``JOYSTICK_SIGMAS``·temblor en u) para que la cabeza quieta en el centro no arrastre el puntero.
- Historial de 0,5 s. ``congelar(t)`` fija el puntero donde estaba ~150 ms antes (los gestos de
  boca, cejas o sonrisa mueven la nariz, y el puntero no debe irse con ellos); al
  ``descongelar`` la posición nueva se mezcla en 300 ms.
- ``perder_cara``/``recuperar_cara``: al volver la cara se mezcla 500 ms desde donde quedó (no
  salta).
- ``actualizar`` devuelve la posición entera; ``cambio`` dice si cambió (no se envía ``Mover``
  si la posición entera es la misma).

1.1 paquete C, **fuente** del puntero (``puntero.fuente``):
- ``cabeza`` (de fábrica): todo igual que en la 1.0 (los caminos nuevos ni se tocan).
- ``ojos``: el puntero va a donde dice el modelo de la mirada (``mirada.ModeloMirada``), pasado por
  el filtro de fijación y sacada y luego por ``_paso_absoluto`` (zona muerta, recorte, mezclas).
  Siempre absoluto. Sin iris (ojo cerrado, sin los puntos del iris) el puntero **se queda quieto**:
  nunca cae a la cabeza.
- ``cabeza_y_ojos``: la cabeza mueve el puntero en modo relativo con ``ojos.ganancia_fina``; al
  empezar una fijación de ``ojos.fijacion_ms`` a más de ``ojos.salto_px`` del puntero, el puntero
  salta a la mirada con una mezcla de 150 ms (``salto`` = True en ese cuadro: la máquina desarma
  la permanencia, el salto nunca hace clic).
Si la fuente pide los ojos pero no hay una calibración de la mirada válida (o es de otro monitor o
de otra resolución de la cámara), se usa la cabeza y ``aviso_fuente`` = "ojos_sin_calibrar".
"""
from __future__ import annotations

import math
from collections import deque

from .filtros import OneEuro
from .mapeo import MapeoCabeza
from .mirada import SACADA_MIN_PX, SACADA_SIGMAS, FiltroFijacion

# Suavidad 1..5 (sección 3.7): más alto = más suave (y un poco más lento)
SUAVIDAD_MIN_CUTOFF = (2.0, 1.5, 1.0, 0.7, 0.5)
# beta en "unidades de pose por segundo" (el filtro trabaja sobre yaw_n/pitch_n). Equivale al beta
# que se usaba en altos de pantalla con el rango de fábrica (≈ 11 altos de pantalla por unidad de yaw).
SUAVIDAD_BETA = (45.0, 34.0, 22.6, 15.8, 11.3)
D_CUTOFF = 1.0
# Aceleración 0..3 (0 = apagada): ganancia × (1 + k·v), v en px/s
ACELERACION_K = (0.0, 0.0005, 0.001, 0.002)
ACELERACION_MAX = 4.0           # tope del factor (un tirón no lanza el puntero al otro lado)

HISTORIAL_S = 0.5
CONGELAR_ATRAS_S = 0.15
MEZCLA_DESCONGELAR_S = 0.3
MEZCLA_REENTRADA_S = 0.5
DT_MAX = 0.25                   # un hueco más largo entre cuadros no acumula un salto (joystick)
# Temblor de FaceMesh con la cabeza quieta (desviación por eje, en unidades de pose): medido con la
# serie real de pruebas/datos (0,002-0,004 a io≈75 px). La calibración guarda el de la persona.
TEMBLOR_FABRICA = 0.003
# Ronda 3: una calibración SIN temblor medido (hecha a mano o de antes de la ronda 2) usa un valor
# del lado seguro. Con la zona muerta del centro (que ya no se usa fuera del modo Palanca) el
# temblor de la cabeza quieta justo en el centro quedaba escondido; con un rango calibrado
# pequeño y la serie real "5.0" (0,0042) el valor de fábrica daba un clic fantasma en 5 minutos.
TEMBLOR_SIN_MEDIR = 0.0045
TEMBLOR_MIN, TEMBLOR_MAX = 0.001, 0.02
DT_TIPICO = 0.05                # 20 cuadros/s (para estimar cuánto atenúa el filtro)
# Ronda 3: con poca luz la cámara baja a 8-12 cuadros/s y el filtro deja pasar más temblor. Se
# mide el intervalo real (media móvil) y, si es claramente mayor que el supuesto, se recalcula el
# temblor esperado (zona muerta, y la máquina agranda el radio de la permanencia). Solo hacia
# arriba: si luego vuelve a ir rápido, queda del lado seguro hasta la siguiente configuración.
DT_MEDIO_ALFA = 0.05
DT_RECALCULAR_S = 2.0
DT_CAMBIO = 0.2                 # se recalcula si el intervalo real pasa 20 % del supuesto
DT_TOPE = 0.15
ZONA_MUERTA_SIGMAS = 1.0        # zona muerta >= 1 x temblor filtrado en px (el radio de la permanencia hace el resto)
JOYSTICK_ZONA_MIN = 0.12        # zona muerta del joystick (fracción del rango cómodo)
JOYSTICK_SIGMAS = 5.0           # ...o 5 x el temblor filtrado en u, lo que sea mayor

MODOS = ("absoluto", "relativo", "joystick")
# ---- 1.1 paquete C: mover con los ojos ----
FUENTES = ("cabeza", "ojos", "cabeza_y_ojos")
MEZCLA_SALTO_S = 0.15            # el salto a la mirada se mezcla en ~150 ms


class _FuenteMirada:
    """La mirada como fuente del puntero, con la misma interfaz que el mapeo para lo que usa el
    puntero (``monitor``, ``recortar``, ``ganancia_px``) y ``a_pixeles`` con el iris."""

    def __init__(self, modelo, monitor, suavidad: int = 3, dt: float = DT_TIPICO):
        self.modelo = modelo
        self.monitor = monitor
        gx, gy = modelo.ganancia_px()
        self.ruido_crudo_px = modelo.temblor_iris * max(gx, gy)
        self.filtro = FiltroFijacion(suavidad, max(SACADA_MIN_PX, SACADA_SIGMAS * self.ruido_crudo_px))
        self.temblor_px = self.ruido_crudo_px * self.filtro.atenuacion(dt)
        self.crudo = None                 # última mirada sin filtrar
        self.crudo_sin_desplazamiento = None

    def a_pixeles(self, t: float, iris, yaw: float, pitch: float):
        """Mirada filtrada (sin recortar) o None si no hay iris."""
        if iris is None:
            self.crudo = self.crudo_sin_desplazamiento = None
            return None
        p = self.modelo.predecir(iris[0], iris[1], yaw, pitch)
        if p is None:
            self.crudo = self.crudo_sin_desplazamiento = None
            return None
        self.crudo = p
        d = self.modelo.desplazamiento
        self.crudo_sin_desplazamiento = (p[0] - d[0], p[1] - d[1])
        return self.filtro(p[0], p[1], t)

    def ganancia_px(self):
        return self.modelo.ganancia_px()

    def recortar(self, x: float, y: float):
        return self.monitor.recortar(x, y)


def _alfa_filtro(cutoff: float, dt: float) -> float:
    tau = 1.0 / (2.0 * math.pi * cutoff)
    return 1.0 / (1.0 + tau / dt)


def _temblor(v, defecto: float = TEMBLOR_FABRICA):
    """(σ_yaw, σ_pitch) en unidades de pose, dentro de límites razonables."""
    out = []
    try:
        vals = list(v) if v is not None else []
    except TypeError:
        vals = []
    for i in range(2):
        try:
            x = float(vals[i])
        except (IndexError, TypeError, ValueError):
            x = defecto
        if not math.isfinite(x) or x <= 0:
            x = defecto
        out.append(min(max(x, TEMBLOR_MIN), TEMBLOR_MAX))
    return tuple(out)


def zona_muerta_escalada(zona_px: float, alto: int) -> float:
    """4 px a 1080 de alto -> proporcional al alto del monitor."""
    return max(float(zona_px), 0.0) * float(alto) / 1080.0


class Puntero:
    def __init__(self, mapeo: MapeoCabeza, modo: str = "absoluto", suavidad: int = 3, zona_muerta_px: float = 4.0,
                 aceleracion: int = 0, posicion_inicial=None, temblor=None,
                 temblor_defecto: float = TEMBLOR_FABRICA):
        self._mirada: _FuenteMirada | None = None   # 1.1: con la cabeza, None (camino de la 1.0)
        self.mapeo = mapeo
        self.modo = modo if modo in MODOS else "absoluto"
        self.temblor = _temblor(temblor, temblor_defecto)
        self._zona_cfg = zona_muerta_escalada(zona_muerta_px, mapeo.monitor.alto)
        self._dt_calc = DT_TIPICO                 # intervalo con que se calculó el temblor
        self._dt_medio = DT_TIPICO                # intervalo real entre cuadros (media móvil)
        self._t_recalc = None
        self.temblor_cambio = False               # la máquina reajusta el radio de la permanencia
        self.poner_suavidad(suavidad)
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
        self.joystick_moviendo = False            # joystick fuera de su zona muerta (el puntero avanza)
        # 1.1 paquete C: fuente del puntero (cabeza, ojos, ojos y cabeza)
        self.fuente = "cabeza"
        self.fuente_pedida = "cabeza"
        self.aviso_fuente = None                  # "ojos_sin_calibrar" si se pidió ojos sin calibrarlos
        self.mirada = None                        # mirada filtrada (px, sin recortar) o None
        self.salto = False                        # cabeza_y_ojos: saltó a la mirada en este cuadro
        self._salto = None                        # (t0, desde, hasta) del salto en curso
        self._fij_usada = None                    # fijación que ya se revisó para saltar
        self._fijacion_s = 0.25
        self._salto_px = 200.0
        self._fina = 0.4

    @classmethod
    def desde_config(cls, cfg: dict, mapeo: MapeoCabeza, posicion_inicial=None, calibracion: dict | None = None):
        p = cfg["puntero"]
        temblor = calibracion.get("temblor") if isinstance(calibracion, dict) else None
        defecto = TEMBLOR_SIN_MEDIR if isinstance(calibracion, dict) else TEMBLOR_FABRICA
        pt = cls(mapeo, p["modo"], p["suavidad"], p["zona_muerta_px"], p["aceleracion"], posicion_inicial,
                 temblor, defecto)
        fuente = p.get("fuente", "cabeza")
        if fuente in FUENTES and fuente != "cabeza":
            from .calibracion import modelo_mirada
            cal_m = calibracion.get("mirada") if isinstance(calibracion, dict) else None
            modelo = modelo_mirada(cal_m, mapeo.monitor, cfg.get("camara"))
            pt.fuente_pedida = fuente
            if modelo is None:
                pt.aviso_fuente = "ojos_sin_calibrar"     # se usa la cabeza (la opción guardada no se borra)
            else:
                pt.poner_mirada(fuente, modelo, cfg.get("ojos") or {})
        return pt

    def poner_mirada(self, fuente: str, modelo, ojos: dict | None = None):
        """Mover con los ojos (``ojos``) o con ojos y cabeza (``cabeza_y_ojos``)."""
        if fuente not in ("ojos", "cabeza_y_ojos") or modelo is None:
            return
        o = ojos or {}
        self.fuente = self.fuente_pedida = fuente
        self.aviso_fuente = None
        self._mirada = _FuenteMirada(modelo, self.mapeo.monitor, int(o.get("suavidad", 3)), self._dt_calc)
        self._fijacion_s = float(o.get("fijacion_ms", 250)) / 1000.0
        self._salto_px = float(o.get("salto_px", 200))
        self._fina = float(o.get("ganancia_fina", 0.4))
        # los ojos son siempre absolutos; con ojos y cabeza, la cabeza afina en modo relativo
        self.modo = "absoluto" if fuente == "ojos" else "relativo"
        self._calcular_temblor()

    @property
    def usa_ojos(self) -> bool:
        return self._mirada is not None

    # ------------------------------------------------------------ ajustes
    def poner_suavidad(self, nivel: int):
        i = int(min(max(int(nivel), 1), 5)) - 1
        self.suavidad = i + 1
        self._fx = OneEuro(SUAVIDAD_MIN_CUTOFF[i], SUAVIDAD_BETA[i], D_CUTOFF)
        self._fy = OneEuro(SUAVIDAD_MIN_CUTOFF[i], SUAVIDAD_BETA[i], D_CUTOFF)
        self._calcular_temblor()

    def _calcular_temblor(self):
        """Temblor esperado del puntero quieto (px, desviación por eje tras el filtro) y, con él,
        la zona muerta en pantalla y la del joystick."""
        a = _alfa_filtro(SUAVIDAD_MIN_CUTOFF[self.suavidad - 1], self._dt_calc)
        atenua = math.sqrt(a / (2.0 - a))           # ruido blanco tras un filtro de primer orden
        gx, gy = self.mapeo.ganancia_px()
        sx, sy = self.temblor
        self.temblor_px = max(sx * atenua * gx, sy * atenua * gy)
        self.zona_muerta = max(self._zona_cfg, ZONA_MUERTA_SIGMAS * self.temblor_px)
        ux, uy = self.mapeo.ganancia_uv()
        z = max(JOYSTICK_ZONA_MIN, JOYSTICK_SIGMAS * max(sx * atenua * ux, sy * atenua * uy))
        self.zona_joystick = min(z, 0.5)
        mir = self._mirada
        if mir is not None:
            if self.fuente == "ojos":
                # con los ojos, el temblor que cuenta es el de la mirada (ya filtrada)
                mir.temblor_px = mir.ruido_crudo_px * mir.filtro.atenuacion(self._dt_calc)
                self.temblor_px = mir.temblor_px
                self.zona_muerta = max(self._zona_cfg, ZONA_MUERTA_SIGMAS * self.temblor_px)
            else:
                # ojos y cabeza: la cabeza mueve con la ganancia fina (la zona muerta es de la cabeza)
                self.temblor_px *= self._fina

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
        if self._mirada is not None:
            self._salto = None
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
        if self._mirada is not None:
            self._mirada.filtro.reiniciar()
            self._salto = None
        if self.modo == "absoluto":
            self._mezcla = (t, MEZCLA_REENTRADA_S, self._pos[0], self._pos[1])

    def reiniciar_filtros(self, t: float | None = None):
        """Tras recentrar o cambiar la calibración: sin saltos (mezcla de 500 ms)."""
        self._fx.reset()
        self._fy.reset()
        if self._mirada is not None:
            self._mirada.filtro.reiniciar()
            self._salto = None
        self.filtrado = None
        self._ancla = None
        self._f_ant = None
        if t is not None and self.modo == "absoluto":
            self._mezcla = (t, MEZCLA_REENTRADA_S, self._pos[0], self._pos[1])

    # ------------------------------------------------------------ paso
    def actualizar(self, t: float, yaw: float, pitch: float, iris=None):
        """Un cuadro con cara. Devuelve la posición entera (x, y). ``self.cambio`` = cambió.
        ``iris`` = (iris_x, iris_y) o None; solo se usa con las fuentes con ojos."""
        if self._mirada is not None:
            return self._actualizar_con_ojos(t, yaw, pitch, iris)
        if self.sin_cara:
            self.recuperar_cara(t)
        fyaw = self._fx(yaw, t)
        fpitch = self._fy(pitch, t)
        fx, fy = self.mapeo.a_pixeles(fyaw, fpitch)
        dt = DT_MAX if self._t_ant is None else min(max(t - self._t_ant, 1e-3), DT_MAX)
        if self._t_ant is not None and dt < 0.2:
            self._medir_ritmo(t, dt)
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

    # ------------------------------------------------------------ 1.1 paquete C: ojos
    def _actualizar_con_ojos(self, t: float, yaw: float, pitch: float, iris):
        if self.sin_cara:
            self.recuperar_cara(t)
        fyaw = self._fx(yaw, t)
        fpitch = self._fy(pitch, t)
        hx, hy = self.mapeo.a_pixeles(fyaw, fpitch)       # la cabeza sigue midiéndose (Desplazar)
        dt = DT_MAX if self._t_ant is None else min(max(t - self._t_ant, 1e-3), DT_MAX)
        if self._t_ant is not None and dt < 0.2:
            self._medir_ritmo(t, dt)
        if self.filtrado is not None and self._t_ant is not None:
            self._v_filtrada = math.hypot(hx - self.filtrado[0], hy - self.filtrado[1]) / dt
        else:
            self._v_filtrada = 0.0
        self.filtrado = (hx, hy)
        self._t_ant = t
        self.salto = False
        g = None
        if iris is not None:
            try:
                ix, iy = float(iris[0]), float(iris[1])
                if math.isfinite(ix) and math.isfinite(iy):
                    g = self._mirada.a_pixeles(t, (ix, iy), fyaw, fpitch)
            except (TypeError, ValueError, IndexError):
                g = None
        if g is None:
            self._mirada.a_pixeles(t, None, fyaw, fpitch)
        self.mirada = g
        anterior = self._pos
        if self.congelado:
            self._pos = self._pos_fija if self._pos_fija is not None else self._pos
            self._f_ant = (hx, hy)
        elif self.fuente == "ojos":
            if g is not None:                    # sin iris: quieto (nunca cae a la cabeza)
                self._paso_absoluto(t, g[0], g[1])
        else:
            self._paso_mixto(t, hx, hy, g)
        d = math.hypot(self._pos[0] - anterior[0], self._pos[1] - anterior[1])
        self.velocidad = d / dt if dt > 0 else 0.0
        self.historial.append((t, self._pos[0], self._pos[1]))
        while self.historial and self.historial[0][0] < t - HISTORIAL_S:
            self.historial.popleft()
        return self._actualizar_entero()

    def _paso_mixto(self, t: float, hx: float, hy: float, g):
        """Ojos y cabeza: la mirada lleva el puntero cerca (salto al empezar una fijación lejana) y
        la cabeza lo afina (relativo, con la ganancia fina)."""
        if self._salto is not None:
            t0, (x0, y0), (x1, y1) = self._salto
            a = (t - t0) / MEZCLA_SALTO_S
            if a >= 1.0:
                self._pos = (float(x1), float(y1))
                self._salto = None
            else:
                a = max(a, 0.0)
                self._pos = (x0 + (x1 - x0) * a, y0 + (y1 - y0) * a)
            self._ancla = None                   # la cabeza sigue desde aquí, sin arrastrar el salto
            return
        f = self._mirada.filtro
        if g is not None and f.en_fijacion(t, self._fijacion_s) and f.t_fijacion_desde != self._fij_usada:
            # una sola revisión por fijación: después la cabeza puede afinar sin que la mirada la tire
            self._fij_usada = f.t_fijacion_desde
            gx, gy = self.mapeo.recortar(*g)
            if math.hypot(gx - self._pos[0], gy - self._pos[1]) > self._salto_px:
                self._salto = (t, self._pos, (float(gx), float(gy)))
                self.salto = True
                self._ancla = None
                return
        ancla_ant = self._ancla
        ax, ay = self._con_zona_muerta(hx, hy)
        if ancla_ant is None or (ax, ay) == ancla_ant:
            return
        dx, dy = (ax - ancla_ant[0]) * self._fina, (ay - ancla_ant[1]) * self._fina
        x, y = self.mapeo.recortar(self._pos[0] + dx, self._pos[1] + dy)
        self._pos = (float(x), float(y))

    def mirada_cruda(self):
        """La mirada de este cuadro sin filtrar y sin el desplazamiento de «Recentrar» (o None)."""
        return None if self._mirada is None else self._mirada.crudo_sin_desplazamiento

    def recentrar_mirada(self, crudo, t: float | None = None) -> bool:
        """«Recentrar» con los ojos: la persona miró el centro; se corrige solo el desplazamiento."""
        if self._mirada is None:
            return False
        ok = self._mirada.modelo.recentrar(crudo, self.mapeo.monitor.centro)
        if ok:
            self.reiniciar_filtros(t)
        return ok

    def _medir_ritmo(self, t: float, dt: float):
        self._dt_medio += DT_MEDIO_ALFA * (dt - self._dt_medio)
        if self._t_recalc is None:
            self._t_recalc = t
            return
        if t - self._t_recalc < DT_RECALCULAR_S:
            return
        self._t_recalc = t
        nuevo = min(self._dt_medio, DT_TOPE)
        if nuevo > self._dt_calc * (1.0 + DT_CAMBIO):
            self._dt_calc = nuevo
            self._calcular_temblor()
            self.temblor_cambio = True

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
        # zona muerta propia del joystick (radial, mucho mayor que el temblor): dentro, quieto
        r = math.hypot(u, v)
        z = self.zona_joystick
        if r <= z:
            self.joystick_moviendo = False
            return
        k = (r - z) / (1.0 - z) / r if z < 1.0 else 0.0
        u, v = u * k, v * k
        self.joystick_moviendo = True
        # la sensibilidad de cada eje es la ganancia
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
