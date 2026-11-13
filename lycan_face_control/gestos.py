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
- Sin cara: todo vuelve a reposo sin eventos.
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
        self.doble = bool(p.get("doble", False))
        self._t_refr = -1e9
        self._refr_por = None
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

    # ------------------------------------------------------------ paso
    def actualizar(self, m, t: float) -> ResultadoGestos:
        res = ResultadoGestos()
        if m is None:
            self.reiniciar()
            return res
        eventos: list = []
        activos = set()
        for nombre, g in self._g.items():
            if not g.encendido:
                continue
            s = self._senal(nombre, m)
            self._paso_gesto(g, s, t, eventos)
            if g.fuera_de_reposo:
                activos.add(nombre)
            dur = g.duracion(t) if g.t_tramo is not None else 0.0
            res.progreso[nombre] = min(dur / g.sostener_s, 1.0) if g.sostener_s > 0 else 0.0
            res.progreso_largo[nombre] = min(dur / self.largo_s, 1.0) if self.largo_s > 0 else 0.0
            ref = self.base["mar"] if nombre == "boca" else 1.0
            res.nivel[nombre] = ((s - ref) / (g.entrar - ref)) if _finito(s) and g.entrar > ref else 0.0
        if self.parpadeo_activo:
            self._paso_parpadeo(m, t, eventos, res)
        res.eventos = eventos
        res.activos = frozenset(activos)
        return res

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
            if not g.emitido and not g.consumido and not self.en_refractario(t):
                ev = None
                if g.tiene_largo and d >= self.largo_s - 1e-9:
                    ev = GestoLargo(g.nombre)
                elif d >= g.sostener_s - 1e-9:
                    ev = GestoCorto(g.nombre)
                if ev is not None:
                    g.necesita_reposo = g.fuera_de_reposo
                    self._emitir(ev, t, eventos, g.nombre)
            g.t_tramo = None
            g.t_ult = None
            g.emitido = False
            g.consumido = False

    # ------------------------------------------------------------ parpadeo
    def _reiniciar_parpadeo(self):
        self._cerrados = False
        self._t_cierre = None          # primer cuadro con ambos ojos cerrados
        self._t_ult_cerrado = None     # último cuadro con ambos ojos cerrados
        self._t_abierto = None         # cuándo se abrieron (pendiente de confirmar 80 ms)
        self._listo = False

    def _proporciones(self, m):
        bd, bi = self.base["ear_der"], self.base["ear_izq"]
        rd = m.ear_der / bd if bd > 0 else float("nan")
        ri = m.ear_izq / bi if bi > 0 else float("nan")
        return rd, ri

    def _paso_parpadeo(self, m, t: float, eventos: list, res: ResultadoGestos):
        rd, ri = self._proporciones(m)
        if not (_finito(rd) and _finito(ri)):
            return
        ambos = rd < self.cerrado and ri < self.cerrado
        alguno_abierto = rd > self.abierto or ri > self.abierto
        res.ojos_cerrando = rd < self.abierto or ri < self.abierto
        if not self._cerrados:
            if ambos:
                if self._t_cierre is not None and self._t_abierto is not None \
                        and t - self._t_abierto < TOLERANCIA_ABIERTO_S:
                    pass                    # se abrió solo un instante: sigue el mismo cierre
                else:
                    self._t_cierre = t
                    self._listo = False
                self._cerrados = True
                self._t_abierto = None
                self._t_ult_cerrado = t
            elif self._t_cierre is not None and self._t_abierto is not None \
                    and t - self._t_abierto >= TOLERANCIA_ABIERTO_S - 1e-9:
                self._terminar_cierre(t, eventos)
        else:
            if alguno_abierto:
                self._cerrados = False
                self._t_abierto = t
            elif ambos:
                self._t_ult_cerrado = t
        if self._t_cierre is not None:
            dur = self._t_ult_cerrado - self._t_cierre
            res.ojos_cerrados = True
            res.parpadeo_progreso = min(dur / self.parpadeo_largo_s, 1.0)
            if dur >= self.parpadeo_largo_s - 1e-9 and dur <= self.descanso_s and not self._listo \
                    and not self._refractario_para_parpadeo(self._t_cierre):
                self._listo = True
                eventos.append(ParpadeoListo())
            res.parpadeo_listo = self._listo and dur <= self.descanso_s

    def _refractario_para_parpadeo(self, t_cierre: float) -> bool:
        """El refractario de boca, cejas o sonrisa anula un parpadeo largo que empezó dentro de él;
        el de otro parpadeo largo no (el doble parpadeo tiene que poder hacerse seguido)."""
        return t_cierre < self._t_refr and self._refr_por != "parpadeo"

    def _terminar_cierre(self, t: float, eventos: list):
        dur = self._t_ult_cerrado - self._t_cierre
        t_cierre = self._t_cierre
        self._reiniciar_parpadeo()
        if dur < self.parpadeo_largo_s - 1e-9:
            return                          # parpadeo natural: NUNCA hace nada
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
