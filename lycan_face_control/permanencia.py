"""Clic por permanencia: quedarse quieto un momento (sección 3.8). Lógica pura.

Dos maneras de contar:

1. **Libre** (sobre cualquier programa): el contador corre mientras el puntero siga dentro de un
   círculo de ``radio`` alrededor del punto donde empezó la quietud.
   - Salirse del círculo reinicia, salvo un **margen** de 150 ms: si vuelve dentro en ese tiempo,
     el contador sigue (estilo OptiKey).
   - **Activación**: tras cada disparo el contador no se arma hasta que el puntero se aleje más de
     ``2 × radio`` del punto del disparo **y siga lejos al menos 250 ms** (un pico suelto del
     temblor de la cámara no arma). Así la persona puede descansar quieta sin que se repitan los
     clics ("toque de Midas"). Al empezar también hay que moverse primero.
   - **Recuperación**: 1 s sin disparos tras cada disparo.
2. **Por objetivo** (botones propios: barra, teclas, frases, "Reanudar"): el contador sigue
   mientras el puntero esté dentro del rectángulo del objetivo ampliado con una franja del 12 %;
   no exige activación para pasar de un botón a otro. Para repetir el mismo botón hay que salir
   de él o esperar otra permanencia completa.

El anillo solo se muestra desde los 200 ms (antes no, para que no parpadee con cada pausa corta).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

FRANJA_OBJETIVO = 0.12
ARMAR_SOSTENIDO_S = 0.25      # hay que estar lejos del último disparo este tiempo seguido para armar


@dataclass(frozen=True)
class Objetivo:
    """Un botón propio en píxeles físicos de pantalla. ``rect`` = (izq, arriba, der, abajo),
    der/abajo exclusivos. ``tiempo_s`` = permanencia propia (None = la del tipo de objetivo).
    ``elegible=False`` marca solo una ventana propia (sin botón): ahí no se hace clic.
    ``repetir``: quedarse encima repite tras otra permanencia completa (None = solo las teclas
    ``tecla:...``; los botones de la barra no se repiten: hay que salir y volver)."""
    id: str
    rect: tuple
    tiempo_s: float | None = None
    elegible: bool = True
    repetir: bool | None = None

    @property
    def se_repite(self) -> bool:
        return self.id.startswith("tecla:") if self.repetir is None else bool(self.repetir)

    def contiene(self, x: float, y: float, franja: float = 0.0) -> bool:
        l, t, r, b = self.rect
        fx = (r - l) * franja
        fy = (b - t) * franja
        return l - fx <= x < r + fx and t - fy <= y < b + fy


def buscar_objetivo(pos, objetivos, actual: Objetivo | None = None, franja: float = FRANJA_OBJETIVO):
    """El objetivo elegible bajo el puntero. Si ya estaba sobre ``actual``, se mantiene mientras
    siga dentro de su rectángulo ampliado (histéresis en el borde)."""
    x, y = pos
    if actual is not None and actual.elegible and actual.contiene(x, y, franja) \
            and any(o.id == actual.id for o in objetivos):
        return actual          # la franja gana aunque ya pise el botón vecino
    for o in objetivos:
        if o.elegible and o.contiene(x, y):
            return o
    return None


def sobre_ventana_propia(pos, objetivos) -> bool:
    """True si el puntero está sobre cualquier ventana o botón propio."""
    x, y = pos
    return any(o.contiene(x, y) for o in objetivos)


@dataclass(frozen=True)
class EstadoPermanencia:
    progreso: float = 0.0          # 0..1
    visible: bool = False          # dibujar el anillo
    disparo: bool = False          # se cumplió en este cuadro
    objetivo: str | None = None    # id del objetivo (modo por objetivo) o None (libre)
    centro: tuple | None = None    # dónde dibujar el anillo
    armado: bool = True            # (libre) ya se movió lo suficiente desde el último disparo


class Permanencia:
    def __init__(self, tiempo_s: float = 1.0, radio_px: float = 30.0, recuperacion_s: float = 1.0,
                 margen_ms: float = 150.0, anillo_desde_ms: float = 200.0, alto_pantalla: int = 1080,
                 tiempo_objetivo_s: float = 1.0):
        self.tiempo_s = float(tiempo_s)
        self.radio = max(float(radio_px), 1.0) * float(alto_pantalla) / 1080.0
        self.recuperacion_s = float(recuperacion_s)
        self.margen_s = float(margen_ms) / 1000.0
        self.anillo_desde_s = float(anillo_desde_ms) / 1000.0
        self.tiempo_objetivo_s = float(tiempo_objetivo_s)
        self.distancia_activacion = 2.0 * self.radio
        # libre
        self._ancla = None
        self._t_inicio = None
        self._previo = None               # (ancla, t_inicio, t_salida) al salirse un instante
        self._armado = False
        self._inicio = True               # al empezar también hay que moverse primero
        self._pos_disparo = None          # desde dónde hay que alejarse para armar
        self._dist_armar = self.distancia_activacion
        self._t_lejos = None              # desde cuándo está lejos del último disparo
        self._t_ultimo_disparo = -1e9
        # por objetivo
        self._obj = None
        self._t_obj = None

    @classmethod
    def desde_config(cls, cfg: dict, alto_pantalla: int = 1080):
        p = cfg["permanencia"]
        return cls(p["tiempo_s"], p["radio_px"], p["recuperacion_s"], p["margen_ms"], p["anillo_desde_ms"],
                   alto_pantalla, cfg["barra"]["permanencia_s"])

    # ------------------------------------------------------------ control
    def ajustar_radio_minimo(self, minimo_px: float, factor_armar: float = 1.5):
        """El radio no baja de ``minimo_px`` (lo fija el temblor esperado del puntero) y la
        distancia para armar no baja de ``factor_armar`` × ``minimo_px``: el temblor de la cámara
        ni dispara clics ni los impide. (La distancia para armar no se dobla con el radio: con una
        ganancia muy alta exigiría moverse media pantalla para el siguiente clic.)"""
        try:
            minimo_px = float(minimo_px)
        except (TypeError, ValueError):
            return
        if not math.isfinite(minimo_px):
            return
        if minimo_px > self.radio:
            self.radio = minimo_px
        armar = max(self.distancia_activacion, factor_armar * minimo_px)
        if armar > self.distancia_activacion:
            self.distancia_activacion = armar
            self._dist_armar = armar

    def desarmar(self, pos, distancia: float | None = None):
        """Exige alejarse ``distancia`` (por defecto 2 × radio) de ``pos`` antes del próximo
        disparo libre."""
        self._armado = False
        self._pos_disparo = tuple(pos) if pos is not None else None
        self._dist_armar = self.distancia_activacion if distancia is None else float(distancia)
        self._t_lejos = None
        self._ancla = None
        self._t_inicio = None
        self._previo = None

    def marcar_disparo(self, pos, t: float, distancia: float | None = None):
        """Hubo un clic por otro camino (un gesto): cuenta como disparo (activación y
        recuperación) para no sumar un clic por permanencia encima."""
        self._t_ultimo_disparo = t
        self.desarmar(pos, distancia)
        self._obj = None
        self._t_obj = None

    def reiniciar(self, t: float | None = None):
        """Empieza a contar de nuevo (sin cambiar si está armado)."""
        self._ancla = None
        self._t_inicio = None
        self._previo = None
        self._obj = None
        self._t_obj = None

    def armar(self):
        self._armado = True
        self._pos_disparo = None

    @property
    def armado(self) -> bool:
        return self._armado

    # ------------------------------------------------------------ paso
    def actualizar(self, pos, t: float, objetivo: Objetivo | None = None, libre: bool = True,
                   tiempo_objetivo_s: float | None = None) -> EstadoPermanencia:
        """Un cuadro. ``objetivo`` = botón propio bajo el puntero (ver ``buscar_objetivo``);
        ``libre=False`` apaga el modo libre (permanencia apagada, ventana propia, etc.)."""
        x, y = float(pos[0]), float(pos[1])
        if self._inicio:
            self._inicio = False
            if not self._armado and self._pos_disparo is None:
                self._pos_disparo = (x, y)
        # la activación se revisa siempre (también sobre los objetivos)
        if not self._armado:
            if self._pos_disparo is None:
                self._armado = True
            elif math.hypot(x - self._pos_disparo[0], y - self._pos_disparo[1]) > self._dist_armar:
                if self._t_lejos is None:
                    self._t_lejos = t
                if t - self._t_lejos >= ARMAR_SOSTENIDO_S - 1e-9:
                    self._armado = True
                    self._pos_disparo = None
                    self._t_lejos = None
            else:
                self._t_lejos = None
        if objetivo is not None:
            return self._por_objetivo(objetivo, (x, y), t, tiempo_objetivo_s)
        self._obj = None
        self._t_obj = None
        if not libre:
            self._ancla = None
            self._t_inicio = None
            return EstadoPermanencia(armado=self._armado)
        return self._libre((x, y), t)

    def _por_objetivo(self, obj: Objetivo, pos, t: float, tiempo_s: float | None) -> EstadoPermanencia:
        self._ancla = None
        self._t_inicio = None
        if self._obj is None or self._obj.id != obj.id:
            self._obj = obj
            self._t_obj = t
        dur = obj.tiempo_s if obj.tiempo_s is not None else (tiempo_s or self.tiempo_objetivo_s)
        dur = max(float(dur), 0.05)
        l, tp, r, b = obj.rect
        centro = ((l + r) / 2.0, (tp + b) / 2.0)
        if self._t_obj is None:
            # ya se eligió y no se repite: hay que salir del botón y volver
            return EstadoPermanencia(0.0, False, False, obj.id, centro, self._armado)
        transcurrido = t - self._t_obj
        if transcurrido >= dur - 1e-9:
            # las teclas se repiten tras otra permanencia completa; los demás botones no
            self._t_obj = t if obj.se_repite else None
            return EstadoPermanencia(1.0, True, True, obj.id, centro, self._armado)
        prog = max(transcurrido / dur, 0.0)
        return EstadoPermanencia(prog, transcurrido >= self.anillo_desde_s, False, obj.id, centro, self._armado)

    def _libre(self, pos, t: float) -> EstadoPermanencia:
        x, y = pos
        if not self._armado:
            return EstadoPermanencia(armado=False)
        if self._previo is not None:
            ancla, t_ini, t_sal = self._previo
            if t - t_sal > self.margen_s + 1e-9:
                self._previo = None          # se fue de verdad: la quietud anterior se pierde
            elif math.hypot(x - ancla[0], y - ancla[1]) <= self.radio:
                # volvió dentro del margen: el contador anterior sigue
                self._ancla, self._t_inicio = ancla, t_ini
                self._previo = None
        if self._ancla is None:
            self._ancla = (x, y)
            self._t_inicio = t
        elif math.hypot(x - self._ancla[0], y - self._ancla[1]) > self.radio:
            if self._previo is None:
                self._previo = (self._ancla, self._t_inicio, t)
            # la quietud empieza de nuevo aquí (el anillo no se llena mientras se mueve)
            self._ancla = (x, y)
            self._t_inicio = t
        return self._estado_libre(t, disparar=True)

    def _estado_libre(self, t: float, disparar: bool) -> EstadoPermanencia:
        transcurrido = t - self._t_inicio
        if t - self._t_ultimo_disparo < self.recuperacion_s:
            # en recuperación: el contador no avanza (empieza al terminar)
            self._t_inicio = max(self._t_inicio, self._t_ultimo_disparo + self.recuperacion_s)
            transcurrido = max(t - self._t_inicio, 0.0)
        prog = min(max(transcurrido / self.tiempo_s, 0.0), 1.0)
        visible = transcurrido >= self.anillo_desde_s
        if disparar and transcurrido >= self.tiempo_s - 1e-9:
            centro = self._ancla
            self._t_ultimo_disparo = t
            self.desarmar(centro)
            return EstadoPermanencia(1.0, True, True, None, centro, False)
        return EstadoPermanencia(prog, visible, False, None, self._ancla, True)
