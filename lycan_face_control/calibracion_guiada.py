"""Secuencia de la calibración guiada (sección 4.1). Lógica pura: recibe (t, medidas, io_fracción)
y dice en qué paso va, cuánto falta y, al final, arma la calibración con ``calibracion.py``.

Cada paso tiene dos fases:

- ``preparar``: se muestran las instrucciones (la persona lee y se acomoda), sin medir;
- ``medir``: se juntan medidas durante el tiempo del paso. **El reloj del paso solo corre
  mientras se ve la cara**: si la cara se pierde, el paso se detiene y sigue cuando vuelve.

Los pasos avanzan solos (así la persona no necesita manos). El cuidador puede repetir un paso,
volver atrás u omitir la prueba de un gesto. No importa tkinter.

Ronda 2 de arreglos: con el **barrido** o «Solo comunicación» encendidos se agrega el paso
``parpadeo_largo``: la persona practica el cierre voluntario (la barra se llena y se pone verde) y
el paso termina con 3 parpadeos largos reconocidos por el mismo clasificador que se usa después
(o, si no los logra en 40 s, sigue con un aviso). Con «Solo comunicación» el puntero no se usa: no
se piden los cuatro giros de la cabeza (se quedan los rangos de fábrica, sin aviso de "poco
movimiento").
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import copy

from . import calibracion as C
from .config import PARPADEO_LARGO_PISO_MS
from .gestos import Gestos, ParpadeoLargo
from .mapeo import RANGO_PITCH_FABRICA, RANGO_YAW_FABRICA

PREPARAR_S = 2.0
DURACION_S = {
    "posicion": 1.0,         # 1 s seguido a buena distancia
    "centro": 3.0,
    "izq": 2.5, "der": 2.5, "arr": 2.5, "aba": 2.5,      # 2 s + 0,5 s que se descartan
    "reposo": 3.0,
    "parpadeo": 15.0,
    "parpadeo_largo": 40.0,  # tope: si en 40 s no hay 3 parpadeos largos, sigue con un aviso
    "gesto_boca": 6.0, "gesto_cejas": 6.0, "gesto_sonrisa": 6.0,
}
POSICION_MAX_S = 20.0        # si en 20 s no se logra buena distancia, se sigue con un aviso
PASO_MAX_DT = 0.25           # un hueco mayor entre cuadros no cuenta como tiempo medido
GESTOS_PROBABLES = ("boca", "cejas", "sonrisa")
PARPADEOS_LARGOS = 3         # cierres voluntarios reconocidos para dar el paso por bueno


def usa_barrido(cfg: dict) -> bool:
    tec = cfg.get("teclado") or {}
    return bool(tec.get("barrido") or tec.get("solo_comunicacion"))


def sin_puntero(cfg: dict) -> bool:
    return bool((cfg.get("teclado") or {}).get("solo_comunicacion"))


def pasos_para(cfg: dict) -> list[str]:
    """Pasos según la configuración: la prueba de gestos solo para los encendidos; el parpadeo
    largo para quien usa el barrido; sin giros de cabeza en «Solo comunicación»."""
    pasos = ["posicion", "centro"]
    if not sin_puntero(cfg):
        pasos += ["izq", "der", "arr", "aba"]
    pasos.append("reposo")
    if cfg["gestos"]["parpadeo"].get("activo", True):
        pasos.append("parpadeo")
        if usa_barrido(cfg):
            pasos.append("parpadeo_largo")
    for g in GESTOS_PROBABLES:
        if cfg["gestos"][g].get("activo"):
            pasos.append(f"gesto_{g}")
    return pasos


@dataclass
class EstadoGuia:
    paso: str
    indice: int
    total: int
    fase: str                      # 'preparar' | 'medir' | 'terminado'
    progreso: float                # 0..1 del paso actual
    sin_cara: bool = False
    posicion: str = ""             # 'bien' | 'lejos' | 'cerca' (paso posición)
    nivel: float | None = None     # señal en vivo del gesto (paso de gesto), relativa a la base
    avisos: list = field(default_factory=list)
    contador: int = 0              # paso parpadeo_largo: cierres reconocidos
    parpadeo: float | None = None  # paso parpadeo_largo: 0..1 del cierre en curso
    parpadeo_listo: bool = False   # ...ya llegó al tiempo (la barra en verde: puede abrir los ojos)


class Guia:
    def __init__(self, cfg: dict, t0: float, preparar_s: float = PREPARAR_S, duraciones: dict | None = None):
        self.cfg = cfg
        self.pasos = pasos_para(cfg)
        self.preparar_s = float(preparar_s)
        self.dur = dict(DURACION_S)
        if duraciones:
            self.dur.update(duraciones)
        self.i = 0
        self.recs: dict = {}
        self.resultados: dict = {}
        self.avisos: list[str] = []
        self.terminado = False
        self._empezar_paso(t0)

    # ------------------------------------------------------------ control
    @property
    def paso(self) -> str:
        return self.pasos[min(self.i, len(self.pasos) - 1)]

    def _empezar_paso(self, t: float):
        self.fase = "preparar"
        self._t_fase = t
        self._medido = 0.0
        self._t_ult = None
        self._t_bien = None
        self._sin_cara = False
        self._posicion = ""
        self._nivel = None
        self._rec = None
        self._t_inicio_medir = None
        self._g_largo = None
        self._n_largos = 0
        self._parpadeo = None
        self._parpadeo_listo = False

    def repetir(self, t: float):
        self.terminado = False
        self.resultados.pop(self.paso, None)
        self._empezar_paso(t)

    def atras(self, t: float):
        if self.i > 0:
            self.i -= 1
        self.terminado = False
        self.resultados.pop(self.paso, None)
        self._empezar_paso(t)

    def omitir(self, t: float):
        """Solo los pasos de gesto se pueden omitir (se queda el umbral de fábrica)."""
        if self.paso.startswith("gesto_"):
            self.resultados[self.paso] = None
            self._siguiente(t)

    def _siguiente(self, t: float):
        if self.i >= len(self.pasos) - 1:
            self.terminado = True
            self.fase = "terminado"
            return
        self.i += 1
        self._empezar_paso(t)

    # ------------------------------------------------------------ cuadros
    def alimentar(self, t: float, medidas, io_fraccion: float | None = None) -> EstadoGuia:
        if self.terminado:
            return self.estado(t)
        if self.fase == "preparar":
            if t - self._t_fase >= self.preparar_s - 1e-9:
                self.fase = "medir"
                self._t_fase = t
                self._t_inicio_medir = t
                self._rec = C.Recolector(t, descartar_s=0.5 if self.paso in ("izq", "der", "arr", "aba") else 0.0)
                self._t_ult = None
            else:
                self._sin_cara = medidas is None
                return self.estado(t)
        # fase medir
        self._sin_cara = medidas is None
        if medidas is None:
            self._t_ult = None        # el reloj del paso se detiene
            if self._g_largo is not None:
                self._g_largo.actualizar(None, t)
            if self.paso == "posicion":
                self._t_bien = None
            return self.estado(t)
        dt = 0.0 if self._t_ult is None else min(max(t - self._t_ult, 0.0), PASO_MAX_DT)
        self._t_ult = t
        p = self.paso
        if p == "posicion":
            self._posicion = C.posicion_correcta(io_fraccion if io_fraccion is not None else float("nan"))
            self._medido += dt
            if self._posicion == "bien":
                if self._t_bien is None:
                    self._t_bien = t
                if t - self._t_bien >= self.dur["posicion"] - 1e-9:
                    self.resultados[p] = "bien"
                    self._siguiente(t)
            else:
                self._t_bien = None
                if self._medido >= POSICION_MAX_S:
                    self.resultados[p] = self._posicion
                    self.avisos.append("posicion")
                    self._siguiente(t)
            return self.estado(t)
        if p == "parpadeo_largo":
            return self._paso_parpadeo_largo(t, medidas, dt)
        # pasos con tiempo: el Recolector usa un tiempo "medido" (sin los huecos sin cara)
        self._medido += dt
        self._rec.agregar(self._rec.t0 + self._medido, medidas)
        if p.startswith("gesto_"):
            self._nivel = self._nivel_gesto(p[6:], medidas)
        if self._medido >= self.dur[p] - 1e-9:
            self._cerrar_paso(p)
            self._siguiente(t)
        return self.estado(t)

    def _base(self) -> dict:
        return self.resultados.get("reposo") or dict(C.BASE_REFERENCIA)

    def largo_ms(self) -> int:
        """Tiempo del parpadeo largo que quedará en la configuración (según los naturales)."""
        return max(int(C.parpadeo_largo_ms(self.resultados.get("parpadeo") or [])), PARPADEO_LARGO_PISO_MS)

    def _crear_clasificador_largo(self):
        g = copy.deepcopy(self.cfg["gestos"])
        g["parpadeo"]["largo_ms"] = self.largo_ms()
        g["parpadeo"]["doble"] = False
        g["parpadeo"]["activo"] = True
        return Gestos(g, {"base": self._base(), "umbrales": {}})

    def _paso_parpadeo_largo(self, t: float, medidas, dt: float) -> EstadoGuia:
        if self._g_largo is None:
            self._g_largo = self._crear_clasificador_largo()
        r = self._g_largo.actualizar(medidas, t)
        self._n_largos += sum(1 for e in r.eventos if isinstance(e, ParpadeoLargo))
        self._parpadeo = r.parpadeo_progreso if r.ojos_cerrados else 0.0
        self._parpadeo_listo = bool(r.parpadeo_listo)
        self._medido += dt
        p = "parpadeo_largo"
        if self._n_largos >= PARPADEOS_LARGOS:
            self.resultados[p] = self._n_largos
            self._siguiente(t)
        elif self._medido >= self.dur[p] - 1e-9:
            self.resultados[p] = self._n_largos
            self.avisos.append(p)
            self._siguiente(t)
        return self.estado(t)

    def _nivel_gesto(self, nombre: str, m) -> float | None:
        b = self._base()
        try:
            if nombre == "boca":
                return float(m.mar - b["mar"])
            if nombre == "cejas":
                return float(m.cejas / b["cejas"] - 1.0)
            if nombre == "sonrisa":
                return float(m.sonrisa / b["sonrisa"] - 1.0)
        except (ZeroDivisionError, TypeError, KeyError):
            return None
        return None

    def _cerrar_paso(self, p: str):
        rec = self._rec
        if p == "centro":
            c = C.centro(rec)
            self.resultados[p] = c
            self.resultados["temblor"] = C.temblor(rec)
        elif p in ("izq", "der", "arr", "aba"):
            self.resultados[p] = rec
        elif p == "reposo":
            self.resultados[p] = C.bases(rec)
        elif p == "parpadeo":
            g = self.cfg["gestos"]["parpadeo"]
            self.resultados[p] = C.parpadeos_naturales(rec, self._base(), g.get("cerrado", 0.55),
                                                       g.get("abierto", 0.70))
        elif p.startswith("gesto_"):
            nombre = p[6:]
            campo = {"boca": "mar", "cejas": "cejas", "sonrisa": "sonrisa"}[nombre]
            vals = rec.valores(campo)
            if nombre == "sonrisa":
                # sonrisa con la boca cerrada: los cuadros con la boca abierta no cuentan
                b = self._base()
                vals = [getattr(m, "sonrisa") for _, m in rec.muestras
                        if math.isfinite(m.sonrisa) and m.mar < b["mar"] + 0.15]
            self.resultados[p] = max(vals) if vals else None

    def estado(self, t: float) -> EstadoGuia:
        p = self.paso
        if self.terminado:
            prog = 1.0
        elif self.fase == "preparar":
            prog = min(max((t - self._t_fase) / self.preparar_s, 0.0), 1.0) if self.preparar_s > 0 else 1.0
        elif p == "posicion":
            prog = 0.0 if self._t_bien is None else min((t - self._t_bien) / self.dur["posicion"], 1.0)
        elif p == "parpadeo_largo":
            prog = min(self._n_largos / PARPADEOS_LARGOS, 1.0)
        else:
            prog = min(self._medido / self.dur[p], 1.0)
        return EstadoGuia(p, self.i, len(self.pasos), "terminado" if self.terminado else self.fase, prog,
                          self._sin_cara, self._posicion, self._nivel, list(self.avisos),
                          self._n_largos, self._parpadeo, self._parpadeo_listo)

    # ------------------------------------------------------------ resultado
    def resultado(self):
        """(calibración, parpadeo_largo_ms, lados con poco movimiento). None si falta el centro."""
        c = self.resultados.get("centro")
        if c is None:
            return None
        recs = {lado: self.resultados.get(lado) for lado in ("izq", "der", "arr", "aba")}
        recs = {k: v for k, v in recs.items() if v is not None}
        if not recs and not any(lado in self.pasos for lado in ("izq", "der", "arr", "aba")):
            # «Solo comunicación»: no se pidieron los giros; rangos de fábrica, sin aviso
            extremos = {"der": c[0] + RANGO_YAW_FABRICA, "izq": c[0] - RANGO_YAW_FABRICA,
                        "aba": c[1] + RANGO_PITCH_FABRICA, "arr": c[1] - RANGO_PITCH_FABRICA}
            pocos = []
        else:
            extremos, pocos = C.rangos(c, recs)
        n = self.resultados.get("parpadeo_largo")
        # None = no hubo paso; si no, cuántos parpadeos largos se reconocieron
        self.parpadeos_largos = n if "parpadeo_largo" in self.pasos else None
        base = self._base()
        umbrales = {}
        self.gestos_no_detectados = []
        for g in GESTOS_PROBABLES:
            clave = f"gesto_{g}"
            if clave in self.resultados:
                if not C.gesto_detectado(g, base, self.resultados[clave]):
                    self.gestos_no_detectados.append(g)
                u = C.umbral_gesto(g, base, self.resultados[clave])
                if u is not None:
                    umbrales[g] = u
        durs = self.resultados.get("parpadeo")
        cal = C.construir(c, extremos, base, umbrales, durs if durs is not None else [],
                          temblor_cabeza=self.resultados.get("temblor"))
        largo = C.parpadeo_largo_ms(durs or [])
        return cal, largo, pocos
