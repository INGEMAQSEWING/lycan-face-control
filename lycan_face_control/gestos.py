"""Clasificador de gestos de la cara (sección 3.5). Lógica pura: recibe ``Medidas`` y el tiempo
real (segundos de ``perf_counter``) y devuelve eventos. Nunca cuenta cuadros.

Gestos: boca abierta, cejas arriba, sonrisa y parpadeo largo voluntario (ambos ojos).

Reglas:
- Cada gesto se compara con la **base de la persona** (calibración) o, sin calibrar, con la de la
  cara de referencia.
- **Histéresis**: entra con un umbral y vuelve a reposo con otro más bajo (no rebota).
- **Sostener**: el tiempo cuenta solo mientras la señal está por encima del umbral de entrada de
  forma continua. Al hablar, la boca abre y cierra varias veces por segundo: ningún tramo llega a
  los 350 ms y no hace clic.
- **Corto y largo**: ``GestoCorto`` si el tramo duró entre ``sostener`` y ``largo``;
  ``GestoLargo`` si llegó a ``largo`` (2 s). Se deciden al soltar. Si el gesto no tiene acción
  larga, el corto sale apenas se cumple ``sostener`` (más rápido).
- **Refractario** (600 ms): tras cualquier evento no se acepta otro gesto, y el mismo gesto tiene
  que volver a reposo antes de repetirse.
- **Parpadeo largo**: ambos ojos cerrados de forma continua (un instante abierto de menos de
  80 ms no corta). Un cierre más corto que ``parpadeo_largo`` (mínimo absoluto 400 ms) es un
  parpadeo natural y **nunca** produce nada. El evento sale **al abrir los ojos** si el cierre duró
  entre ``parpadeo_largo`` y ``descanso`` (más largo = descanso, se ignora). La duración se mide
  de forma conservadora (del primer al último cuadro con los ojos cerrados), así un parpadeo
  natural nunca "se estira" por tener pocos cuadros por segundo.
- Sin cara: los tramos en curso se cortan sin eventos, pero **no** se olvida lo que hace falta
  para no repetir: un gesto que estaba fuera de reposo sigue "esperando reposo" cuando vuelve la
  cara, y un tramo que ya empieza arriba al volver la cara tampoco cuenta (ronda 1 de arreglos).
- Parpadeo y cara perdida: un hueco corto (< 300 ms) durante un cierre no lo corta; uno más
  largo deja el cierre **inválido** (al abrir no sale nada), y un cierre que ya viene en curso
  al volver la cara tampoco cuenta. Así un descanso con los ojos cerrados nunca se vuelve
  parpadeo largo porque FaceMesh perdió la cara un instante.
- Parpadeo voluntario **profundo**: la mayor parte del cierre tiene que estar muy por debajo
  del umbral de cierre (``profundo``); unos ojos entrecerrados por sueño o al mirar hacia abajo
  no cuentan. El cierre termina en cuanto los ojos pasan otra vez del umbral de cierre dos
  cuadros seguidos (u 80 ms): una ráfaga de parpadeos naturales no se junta en uno largo.
- Inhibición cruzada: un cierre de ojos con la boca abierta, las cejas arriba o sonriendo
  (bostezo, risa) no es parpadeo largo; y una boca abierta con los ojos cerrados (bostezo) no
  da ningún gesto de boca.
- Tos, estornudo, risa y bostezo (ronda 2 de arreglos): un tramo de boca, cejas o sonrisa durante
  el que la cabeza se **sacude** (yaw_n o pitch_n cambian más de ``SACUDIDA_POSE`` en menos de
  ``SACUDIDA_VENTANA_S``) no cuenta; y una boca abierta con los dos ojos **entrecerrados** (bajo
  el umbral de "abierto") al menos ``ENTRECERRADOS_S`` tampoco (tos, risa y bostezo achinan los
  ojos; abrir la boca a propósito no).
- Tope del gesto largo: un tramo de más de ``largo + 3 s`` es un bostezo o un descanso y no da
  ``GestoLargo``.
- ``ResultadoGestos.soltados`` trae un ``GestoSoltado(nombre, duracion_ms)`` por cada tramo válido
  que terminó en ese cuadro (la pausa lo usa para reanudar al soltar).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .config import PARPADEO_LARGO_PISO_MS

# Base de la cara dibujada de referencia (sección 3.4): se usa sin calibración
BASE_REFERENCIA = {"ear_der": 0.357, "ear_izq": 0.375, "mar": 0.016, "cejas": 0.356, "sonrisa": 0.557}

# Umbrales de fábrica (desplazamiento sobre la base, con sensibilidad 1)
BOCA_ENTRA, BOCA_SALE = 0.25, 0.15            # MAR > base + 0,25
CEJAS_ENTRA, CEJAS_SALE = 0.12, 0.06          # cejas/base > 1,12
SONRISA_ENTRA, SONRISA_SALE = 0.10, 0.05      # sonrisa/base > 1,10
SONRISA_BOCA_MAX = 0.15                       # y MAR < base + 0,15 (boca abierta no es sonrisa)
FRACCION_SALIDA_CALIBRADA = 0.6               # salida = 60 % del umbral de entrada calibrado

TOLERANCIA_ABIERTO_S = 0.08                   # un instante abierto más corto no corta el cierre
CUADROS_ABIERTO_CORTAN = 2                    # ...pero dos cuadros seguidos abiertos sí lo cortan
PROFUNDO_BAJO_CERRADO = 0.13                  # cierre profundo: por debajo de cerrado − 0,13
PROFUNDO_MIN = 0.30
FRACCION_PROFUNDA = 0.6                       # al menos el 60 % de los cuadros del cierre, profundos
PERDIDA_CORTA_S = 0.3                         # hueco sin cara que no corta un cierre de ojos
BOSTEZO_OJOS_S = 0.3                          # boca abierta con los ojos cerrados este tiempo = bostezo
ENTRECERRADOS_S = 0.3                         # boca abierta con los ojos entrecerrados = tos, risa, bostezo
SACUDIDA_VENTANA_S = 0.3                      # sacudida de la cabeza: cambio de pose en esta ventana...
SACUDIDA_POSE = 0.07                          # ...mayor que esto (≈ 7°): tos, estornudo, risa fuerte
LARGO_EXTRA_S = 3.0                           # un gesto largo de más de largo + 3 s no cuenta
DOBLE_PARPADEO_S = 2.5
NOMBRES = ("boca", "cejas", "sonrisa")


# ------------------------------------------------------------------ eventos
@dataclass(frozen=True)
class GestoCorto:
    nombre: str


@dataclass(frozen=True)
class GestoLargo:
    nombre: str


@dataclass(frozen=True)
class GestoSoltado:
    """Un tramo válido (no consumido, no bostezo) terminó: cuánto duró."""
    nombre: str
    duracion_ms: int = 0


@dataclass(frozen=True)
class ParpadeoListo:
    """El cierre ya cumplió el tiempo del parpadeo largo: "ya puede abrir los ojos"."""


@dataclass(frozen=True)
class ParpadeoLargo:
    duracion_ms: int = 0


@dataclass(frozen=True)
class DobleParpadeoLargo:
    """Dos parpadeos largos separados por 2,5 s o menos."""


@dataclass
class ResultadoGestos:
    eventos: list = field(default_factory=list)
    progreso: dict = field(default_factory=dict)        # nombre -> 0..1 hacia "sostener"
    progreso_largo: dict = field(default_factory=dict)  # nombre -> 0..1 hacia "largo"
    nivel: dict = field(default_factory=dict)           # nombre -> señal / umbral (1 = umbral)
    activos: frozenset = frozenset()                    # gestos encendidos fuera de reposo
    ojos_cerrando: bool = False                         # algún ojo empezó a cerrarse
    ojos_cerrados: bool = False                         # cierre de ambos en curso
    parpadeo_progreso: float = 0.0                      # 0..1 hacia el parpadeo largo
    parpadeo_listo: bool = False
    soltados: list = field(default_factory=list)        # GestoSoltado de este cuadro

    @property
    def gesto_activo(self) -> bool:
        return bool(self.activos)


def _finito(v) -> bool:
    try:
        return v is not None and math.isfinite(v)
    except TypeError:
        return False


class _Gesto:
    """Boca, cejas o sonrisa."""

    def __init__(self, nombre: str, activo: bool, entrar: float, salir: float, sostener_s: float,
                 tiene_largo: bool):
        self.nombre = nombre
        self.encendido = activo
        self.entrar = entrar
        self.salir = salir
        self.sostener_s = sostener_s
        self.tiene_largo = tiene_largo
        self.reiniciar()

    def reiniciar(self):
        self.fuera_de_reposo = False      # histéresis: entre "entrar" y volver bajo "salir"
        self.t_tramo = None               # inicio del tramo continuo por encima de "entrar"
        self.t_ult = None                 # último cuadro del tramo por encima
        self.emitido = False              # el tramo actual ya dio su evento
        self.consumido = False            # el tramo actual no debe dar eventos
        self.necesita_reposo = False      # tras un evento: volver a reposo antes de repetir
        self.ojos_cerrados_s = 0.0        # tiempo del tramo con los dos ojos cerrados (bostezo)
        self.entrecerrados_s = 0.0        # tiempo del tramo con los dos ojos entrecerrados (tos, risa)

    def perder_cara(self):
        """Sin cara: se corta el tramo sin eventos, pero si el gesto estaba fuera de reposo tiene
        que volver a reposo (con la cara presente) antes de contar otra vez."""
        afuera = self.fuera_de_reposo or self.t_tramo is not None or self.necesita_reposo
        self.t_tramo = None
        self.t_ult = None
        self.emitido = False
        self.consumido = False
        self.ojos_cerrados_s = 0.0
        self.entrecerrados_s = 0.0
        if afuera:
            self.fuera_de_reposo = True
            self.necesita_reposo = True

    def duracion(self, t: float) -> float:
        if self.t_tramo is None:
            return 0.0
        return max((self.t_ult if self.t_ult is not None else t) - self.t_tramo, 0.0)


class Gestos:
    """Clasificador. ``actualizar(medidas | None, t) -> ResultadoGestos``."""

    def __init__(self, cfg_gestos: dict, calibracion: dict | None = None):
        self.cfg = cfg_gestos
        base = dict(BASE_REFERENCIA)
        umbrales = {}
        self.calibrado = False
        if isinstance(calibracion, dict):
            b = calibracion.get("base")
            if isinstance(b, dict):
                for k in base:
                    if _finito(b.get(k)) and (b.get(k) > 0 or (k == "mar" and b.get(k) >= 0)):
                        base[k] = float(b[k])
                self.calibrado = True
            u = calibracion.get("umbrales")
            if isinstance(u, dict):
                umbrales = {k: float(v) for k, v in u.items() if _finito(v)}
        self.base = base
        self.umbrales = umbrales
        largo_ms = float(cfg_gestos.get("largo_ms", 2000))
        self.largo_s = largo_ms / 1000.0
        self.refractario_s = float(cfg_gestos.get("refractario_ms", 600)) / 1000.0
        self._g = {}
        for nombre in NOMBRES:
            g = cfg_gestos[nombre]
            entrar, salir = self._umbrales(nombre, float(g.get("sens", 1.0)))
            self._g[nombre] = _Gesto(nombre, bool(g["activo"]), entrar, salir, float(g["sostener_ms"]) / 1000.0,
                                     g.get("largo", "ninguna") != "ninguna")
        p = cfg_gestos["parpadeo"]
        self.parpadeo_activo = bool(p.get("activo", True))
        # piso absoluto: aunque la configuración diga otra cosa, nunca menos de 400 ms
        self.parpadeo_largo_s = max(float(p.get("largo_ms", 800)), PARPADEO_LARGO_PISO_MS) / 1000.0
        self.descanso_s = max(float(p.get("descanso_ms", 4000)) / 1000.0, self.parpadeo_largo_s + 1.0)
        self.cerrado = float(p.get("cerrado", 0.55))
        self.abierto = max(float(p.get("abierto", 0.70)), self.cerrado + 0.05)
        self.profundo = min(self.cerrado, max(self.cerrado - PROFUNDO_BAJO_CERRADO, PROFUNDO_MIN))
        self.doble = bool(p.get("doble", False))
        self._t_refr = -1e9
        self._refr_por = None
        self._t_ult_cara = None        # último cuadro con cara
        self._recien_vuelta = False    # el cuadro actual es el primero tras perder la cara
        self._t_prev = None
        self._soltados: list = []
        self._pose: list = []          # (t, yaw_n, pitch_n) de los últimos cuadros (sacudidas)
        self._reiniciar_parpadeo()
        self._t_ultimo_largo = None

    # ------------------------------------------------------------ umbrales
    def _umbrales(self, nombre: str, sens: float):
        """(entrar, salir) en unidades de la señal: MAR para la boca; cociente con la base para
        cejas y sonrisa. ``sens`` > 1 = hace falta menos movimiento (el desplazamiento sobre la
        base se divide por la sensibilidad)."""
        sens = min(max(sens, 0.5), 2.0)
        if nombre == "boca":
            ref, de, ds = self.base["mar"], BOCA_ENTRA, BOCA_SALE
        elif nombre == "cejas":
            ref, de, ds = 1.0, CEJAS_ENTRA, CEJAS_SALE
        else:
            ref, de, ds = 1.0, SONRISA_ENTRA, SONRISA_SALE
        cal = self.umbrales.get(nombre)
        if cal is not None and cal > ref:
            de = cal - ref
            ds = de * FRACCION_SALIDA_CALIBRADA
        return ref + de / sens, ref + ds / sens

    def _senal(self, nombre: str, m) -> float:
        if nombre == "boca":
            return m.mar
        if nombre == "cejas":
            return m.cejas / self.base["cejas"]
        if m.mar >= self.base["mar"] + SONRISA_BOCA_MAX:
            return float("-inf")          # con la boca abierta no hay sonrisa
        return m.sonrisa / self.base["sonrisa"]

    # ------------------------------------------------------------ control
    def reiniciar(self):
        for g in self._g.values():
            g.reiniciar()
        self._reiniciar_parpadeo()

    def consumir(self, nombre: str):
        """El tramo en curso de ese gesto ya se usó (p. ej. para reanudar): no dará más eventos y
        el gesto tiene que volver a reposo."""
        g = self._g.get(nombre)
        if g is not None:
            g.consumido = True
            g.necesita_reposo = True

    def duracion_sostenida(self, nombre: str, t: float) -> float:
        """Segundos que lleva sostenido el gesto ahora mismo (0 si no, o si ya se consumió)."""
        g = self._g.get(nombre)
        if g is None or not g.encendido or g.t_tramo is None or g.consumido:
            return 0.0
        return g.duracion(t)

    def encendido(self, nombre: str) -> bool:
        if nombre == "parpadeo":
            return self.parpadeo_activo
        g = self._g.get(nombre)
        return bool(g and g.encendido)

    def en_refractario(self, t: float) -> bool:
        return t < self._t_refr

    def refractario_hasta(self, t_hasta: float):
        """Ningún gesto (ni parpadeo largo que empiece antes) cuenta hasta ``t_hasta`` (p. ej. al
        terminar la calibración, cuya última prueba es un gesto)."""
        if t_hasta > self._t_refr:
            self._t_refr = t_hasta
            self._refr_por = "externo"

    def olvidar_parpadeo_largo(self):
        """El último parpadeo largo ya se usó (p. ej. eligió «Pausa»): no cuenta como el primero
        de un doble parpadeo."""
        self._t_ultimo_largo = None

    # ------------------------------------------------------------ paso
    def perder_cara(self, t: float | None = None):
        """Sin cara (o una cara que no es la misma): ver la docstring del módulo."""
        for g in self._g.values():
            g.perder_cara()
        self._recien_vuelta = True
        self._t_prev = None
        self._pose = []

    def actualizar(self, m, t: float) -> ResultadoGestos:
        res = ResultadoGestos()
        if m is None:
            self.perder_cara(t)
            return res
        dt = 0.0 if self._t_prev is None else min(max(t - self._t_prev, 0.0), 0.2)
        self._t_prev = t
        hueco = None
        if self._recien_vuelta:
            hueco = float("inf") if self._t_ult_cara is None else t - self._t_ult_cara
        self._t_ult_cara = t
        ojos_ambos = self._ambos_cerrados(m)
        rd, ri = self._proporciones(m)
        entrecerrados = _finito(rd) and _finito(ri) and rd < self.abierto and ri < self.abierto
        self._guardar_pose(m, t)
        self._soltados = []
        eventos: list = []
        activos = set()
        for nombre, g in self._g.items():
            if not g.encendido:
                continue
            s = self._senal(nombre, m)
            if nombre == "boca" and g.t_tramo is not None and ojos_ambos:
                g.ojos_cerrados_s += dt
                if g.ojos_cerrados_s >= BOSTEZO_OJOS_S - 1e-9 and not g.consumido:
                    g.consumido = True            # bostezo: la boca no hace nada
                    g.necesita_reposo = True
            if nombre == "boca" and g.t_tramo is not None and entrecerrados:
                g.entrecerrados_s += dt
                if g.entrecerrados_s >= ENTRECERRADOS_S - 1e-9 and not g.consumido:
                    g.consumido = True            # tos, risa o bostezo con los ojos achinados
                    g.necesita_reposo = True
            if g.t_tramo is not None and not g.consumido and self._sacudida(g.t_tramo, t):
                g.consumido = True                # la cabeza se sacudió (tos, estornudo)
                g.necesita_reposo = True
            self._paso_gesto(g, s, t, eventos)
            if g.fuera_de_reposo:
                activos.add(nombre)
            dur = g.duracion(t) if g.t_tramo is not None else 0.0
            res.progreso[nombre] = min(dur / g.sostener_s, 1.0) if g.sostener_s > 0 else 0.0
            res.progreso_largo[nombre] = min(dur / self.largo_s, 1.0) if self.largo_s > 0 else 0.0
            ref = self.base["mar"] if nombre == "boca" else 1.0
            res.nivel[nombre] = ((s - ref) / (g.entrar - ref)) if _finito(s) and g.entrar > ref else 0.0
        if self.parpadeo_activo:
            self._paso_parpadeo(m, t, eventos, res, hueco)
        self._recien_vuelta = False
        res.eventos = eventos
        res.soltados = self._soltados
        res.activos = frozenset(activos)
        return res

    def _guardar_pose(self, m, t: float):
        y, p = getattr(m, "yaw_n", None), getattr(m, "pitch_n", None)
        if _finito(y) and _finito(p):
            self._pose.append((t, float(y), float(p)))
        corte = t - 2.0 * SACUDIDA_VENTANA_S
        while self._pose and self._pose[0][0] < corte:
            self._pose.pop(0)

    def _sacudida(self, t_tramo: float, t: float) -> bool:
        """¿La cabeza se sacudió durante el tramo? Solo cuentan los cuadros del propio tramo (el
        movimiento para llegar al botón, justo antes del gesto, no) y de la última ventana."""
        desde = max(t_tramo, t - SACUDIDA_VENTANA_S) - 1e-9
        ys = [y for (tp, y, _p) in self._pose if tp >= desde]
        ps = [p for (tp, _y, p) in self._pose if tp >= desde]
        if len(ys) < 2:
            return False
        return max(ys) - min(ys) > SACUDIDA_POSE or max(ps) - min(ps) > SACUDIDA_POSE

    def _emitir(self, ev, t: float, eventos: list, quien: str | None):
        eventos.append(ev)
        self._t_refr = t + self.refractario_s
        self._refr_por = quien
        # los demás gestos que estén en curso quedan anulados hasta volver a reposo
        for nombre, g in self._g.items():
            if nombre != quien and g.t_tramo is not None:
                g.consumido = True
                g.necesita_reposo = True

    def _paso_gesto(self, g: _Gesto, s: float, t: float, eventos: list):
        arriba = _finito(s) and s > g.entrar
        # histéresis de reposo
        if g.fuera_de_reposo:
            if not _finito(s) or s < g.salir:
                g.fuera_de_reposo = False
                g.necesita_reposo = False
        elif arriba:
            g.fuera_de_reposo = True
        if arriba:
            if g.t_tramo is None:
                g.t_tramo = t
                g.emitido = False
                g.ojos_cerrados_s = 0.0
                g.entrecerrados_s = 0.0
                if self._recien_vuelta:
                    g.necesita_reposo = True      # ya venía arriba al volver la cara: no se sabe desde cuándo
                    g.fuera_de_reposo = True
                # un tramo que empieza en el refractario o sin haber vuelto a reposo no cuenta
                g.consumido = g.necesita_reposo or self.en_refractario(t)
            g.t_ult = t
            d = g.t_ult - g.t_tramo
            if (not g.tiene_largo and not g.emitido and not g.consumido
                    and d >= g.sostener_s - 1e-9 and not self.en_refractario(t)):
                g.emitido = True
                g.necesita_reposo = True
                self._emitir(GestoCorto(g.nombre), t, eventos, g.nombre)
            return
        # terminó el tramo (la señal bajó del umbral de entrada)
        if g.t_tramo is not None:
            d = g.duracion(t)
            if not g.consumido:
                self._soltados.append(GestoSoltado(g.nombre, int(round(d * 1000))))
            if not g.emitido and not g.consumido and not self.en_refractario(t):
                ev = None
                if g.tiene_largo and d >= self.largo_s - 1e-9:
                    if d <= self.largo_s + LARGO_EXTRA_S + 1e-9:
                        ev = GestoLargo(g.nombre)   # más largo: bostezo o descanso, no cuenta
                elif d >= g.sostener_s - 1e-9:
                    ev = GestoCorto(g.nombre)
                if ev is not None:
                    g.necesita_reposo = g.fuera_de_reposo
                    self._emitir(ev, t, eventos, g.nombre)
            g.t_tramo = None
            g.t_ult = None
            g.emitido = False
            g.consumido = False
            g.ojos_cerrados_s = 0.0
            g.entrecerrados_s = 0.0

    # ------------------------------------------------------------ parpadeo
    def _reiniciar_parpadeo(self):
        self._cerrados = False
        self._t_cierre = None          # primer cuadro con ambos ojos cerrados
        self._t_ult_cerrado = None     # último cuadro con ambos ojos cerrados
        self._t_abierto = None         # cuándo se abrieron (pendiente de confirmar 80 ms)
        self._n_abiertos = 0           # cuadros abiertos seguidos dentro del cierre
        self._n_cerr = 0               # cuadros del cierre con los dos ojos cerrados
        self._n_prof = 0               # ...de ellos, con cierre profundo
        self._invalido = False         # el cierre no puede dar parpadeo largo
        self._listo = False

    def _ambos_cerrados(self, m) -> bool:
        rd, ri = self._proporciones(m)
        return _finito(rd) and _finito(ri) and rd < self.cerrado and ri < self.cerrado

    def _otro_gesto_fuera(self, m) -> bool:
        """Boca abierta, cejas arriba o sonrisa (encendidos o no): cambian la forma del ojo."""
        for nombre, g in self._g.items():
            s = self._senal(nombre, m)
            if not _finito(s):
                continue
            if nombre == "boca":
                if s > g.salir:
                    return True
            elif s > g.entrar:
                return True
        return False

    def _cierre_valido(self) -> bool:
        if self._invalido or self._n_cerr <= 0:
            return False
        return self._n_prof >= FRACCION_PROFUNDA * self._n_cerr - 1e-9

    def _proporciones(self, m):
        bd, bi = self.base["ear_der"], self.base["ear_izq"]
        rd = m.ear_der / bd if bd > 0 else float("nan")
        ri = m.ear_izq / bi if bi > 0 else float("nan")
        return rd, ri

    def _paso_parpadeo(self, m, t: float, eventos: list, res: ResultadoGestos, hueco: float | None = None):
        rd, ri = self._proporciones(m)
        if not (_finito(rd) and _finito(ri)):
            return
        ambos = rd < self.cerrado and ri < self.cerrado
        # "empezando a cerrar": los DOS ojos bajo el umbral de abierto (un párpado caído solo no)
        res.ojos_cerrando = rd < self.abierto and ri < self.abierto
        if hueco is not None and hueco > PERDIDA_CORTA_S + 1e-9:
            # primer cuadro tras perder la cara un buen rato: no se sabe qué pasó en el hueco
            if self._t_cierre is not None:
                self._invalido = True
            elif ambos:
                self._t_cierre = t              # un cierre que ya venía: no cuenta
                self._t_ult_cerrado = t
                self._cerrados = True
                self._invalido = True
        if not self._cerrados:
            if ambos:
                if self._t_cierre is not None and self._t_abierto is not None \
                        and t - self._t_abierto < TOLERANCIA_ABIERTO_S \
                        and self._n_abiertos < CUADROS_ABIERTO_CORTAN:
                    pass                    # se abrió solo un instante: sigue el mismo cierre
                else:
                    if self._t_cierre is not None:
                        self._terminar_cierre(t, eventos)
                    self._reiniciar_parpadeo()
                    self._t_cierre = t
                self._cerrados = True
                self._t_abierto = None
                self._n_abiertos = 0
                self._t_ult_cerrado = t
            elif self._t_cierre is not None and self._t_abierto is not None:
                self._n_abiertos += 1
                if t - self._t_abierto >= TOLERANCIA_ABIERTO_S - 1e-9 \
                        or self._n_abiertos >= CUADROS_ABIERTO_CORTAN:
                    self._terminar_cierre(t, eventos)
        else:
            if not ambos:
                self._cerrados = False
                self._t_abierto = t
                self._n_abiertos = 1
            else:
                self._t_ult_cerrado = t
        if self._cerrados and ambos:
            self._n_cerr += 1
            if rd < self.profundo and ri < self.profundo:
                self._n_prof += 1
            if self._otro_gesto_fuera(m):
                self._invalido = True           # bostezo, risa, cejas: no es un parpadeo voluntario
        if self._t_cierre is not None:
            dur = self._t_ult_cerrado - self._t_cierre
            valido = self._cierre_valido()
            res.ojos_cerrados = True
            res.parpadeo_progreso = min(dur / self.parpadeo_largo_s, 1.0) if valido else 0.0
            if dur >= self.parpadeo_largo_s - 1e-9 and dur <= self.descanso_s and not self._listo \
                    and valido and not self._refractario_para_parpadeo(self._t_cierre):
                self._listo = True
                eventos.append(ParpadeoListo())
            res.parpadeo_listo = self._listo and dur <= self.descanso_s and valido

    def _refractario_para_parpadeo(self, t_cierre: float) -> bool:
        """El refractario de boca, cejas o sonrisa anula un parpadeo largo que empezó dentro de él;
        el de otro parpadeo largo no (el doble parpadeo tiene que poder hacerse seguido)."""
        return t_cierre < self._t_refr and self._refr_por != "parpadeo"

    def _terminar_cierre(self, t: float, eventos: list):
        dur = self._t_ult_cerrado - self._t_cierre
        t_cierre = self._t_cierre
        valido = self._cierre_valido()
        self._reiniciar_parpadeo()
        if dur < self.parpadeo_largo_s - 1e-9:
            return                          # parpadeo natural: NUNCA hace nada
        if not valido:
            return                          # poco profundo, cara perdida, bostezo...
        if dur > self.descanso_s:
            return                          # descanso con los ojos cerrados: se ignora
        if self._refractario_para_parpadeo(t_cierre):
            return                          # empezó durante el refractario de otro gesto
        doble = self._t_ultimo_largo is not None and t_cierre - self._t_ultimo_largo <= DOBLE_PARPADEO_S
        if self.doble:
            if doble:
                self._t_ultimo_largo = None
                self._emitir(ParpadeoLargo(int(round(dur * 1000))), t, eventos, "parpadeo")
                eventos.append(DobleParpadeoLargo())
            else:
                self._t_ultimo_largo = t
            return
        self._emitir(ParpadeoLargo(int(round(dur * 1000))), t, eventos, "parpadeo")
        if doble:
            self._t_ultimo_largo = None
            eventos.append(DobleParpadeoLargo())
        else:
            self._t_ultimo_largo = t
