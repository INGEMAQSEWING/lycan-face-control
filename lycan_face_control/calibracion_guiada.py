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

1.1 paquete C: si el puntero se mueve con los ojos (``puntero.fuente`` distinto de "cabeza"), después
de «Mirar abajo» van los pasos de la **mirada**, con puntos en la pantalla (``EstadoGuia.punto``,
en píxeles reales del monitor):

- ``mirada_centro``: 2 s mirando el punto del centro (temblor del iris, cabeza de referencia y
  distancia a la cámara);
- ``mirada_puntos``: 9 puntos (o 5): 1,0 s de preparación y 1,2 s de medida por punto, sin los
  primeros 0,4 s, con la mediana. Un punto con la cabeza movida más de 3 × su temblor se repite
  (hasta 2 veces; luego se acepta, para no quedar en un ciclo sin fin);
- ``mirada_cabeza``: 4 s mirando el centro mientras mueve la cabeza (enseña cuánto pesa la cabeza);
- ``mirada_validar``: 4 puntos nuevos para medir el error real.

En estos pasos el reloj solo corre con la cara **y los dos ojos abiertos**. Revisión de la 1.1: para
no quedar detenidos para siempre (un párpado caído, frecuente en ELA), si pasan
``MIRADA_SIN_OJOS_MAX_S`` (15 s) sin ver los dos ojos abiertos: en «mirada_centro» se dejan todos
los pasos de la mirada (los ojos quedan sin calibrar y el puntero sigue con la cabeza, con el aviso
``cal_mirada_fallo``); en «mirada_puntos» se salta ese punto y, si ya no pueden quedar 5 puntos, se
dejan los pasos de la mirada; en «mirada_cabeza» y «mirada_validar» se cierra el paso con lo que
haya.
"""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field

import copy

from . import calibracion as C
from .config import PARPADEO_LARGO_PISO_MS
from .gestos import Gestos, ParpadeoLargo
from .mapeo import MONITOR_REFERENCIA, RANGO_PITCH_FABRICA, RANGO_YAW_FABRICA
from .mirada import ModeloMirada, ambos_ojos, px_por_cm, rasgos

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
DURACION_S.update({"mirada_centro": 2.0, "mirada_cabeza": 4.0})
POSICION_MAX_S = 20.0        # si en 20 s no se logra buena distancia, se sigue con un aviso
# ---- 1.1 paquete C: mirada ----
PASOS_MIRADA = ("mirada_centro", "mirada_puntos", "mirada_cabeza", "mirada_validar")
PUNTO_PREPARAR_S = 1.0
PUNTO_MEDIR_S = 1.2
PUNTO_DESCARTAR_S = 0.4
MARGEN_PUNTOS = 0.08         # los puntos quedan a 8 % del borde
REPETIR_PUNTO_MAX = 2        # un punto con la cabeza movida se repite hasta 2 veces
CABEZA_MOVIDA_SIGMAS = 3.0
PESO_CABEZA = 3.0            # las muestras del paso "cabeza en movimiento" valen como 3 puntos
ERROR_IMPRECISO_PX = 250     # con más error se recomienda «Ojos y cabeza» o «La cabeza»
DISTANCIA_SUPUESTA_CM = 60.0
MIRADA_SIN_OJOS_MAX_S = 15.0  # sin los dos ojos abiertos este tiempo, el paso (o el punto) no se espera más
PUNTOS_MINIMOS = 5           # con menos puntos medidos no se puede ajustar el modelo de la mirada


def puntos_mirada(monitor, n: int = 9) -> list:
    """Puntos de la calibración (en píxeles reales): 3 × 3 o el centro y las 4 esquinas."""
    m = monitor or MONITOR_REFERENCIA
    fr = (MARGEN_PUNTOS, 0.5, 1.0 - MARGEN_PUNTOS)
    if int(n) == 5:
        rel = [(0.5, 0.5), (fr[0], fr[0]), (fr[2], fr[0]), (fr[0], fr[2]), (fr[2], fr[2])]
    else:
        rel = [(fx, fy) for fy in fr for fx in fr]
    return [(m.x + (m.ancho - 1) * fx, m.y + (m.alto - 1) * fy) for fx, fy in rel]


def puntos_validar(monitor) -> list:
    m = monitor or MONITOR_REFERENCIA
    rel = ((0.3, 0.28), (0.72, 0.3), (0.28, 0.72), (0.7, 0.7))
    return [(m.x + (m.ancho - 1) * fx, m.y + (m.alto - 1) * fy) for fx, fy in rel]


def usa_ojos(cfg: dict) -> bool:
    return (cfg.get("puntero") or {}).get("fuente", "cabeza") != "cabeza"
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
        if usa_ojos(cfg):
            pasos += list(PASOS_MIRADA)            # 1.1 paquete C
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
    # ---- 1.1 paquete C: mirada ----
    punto: tuple | None = None     # punto que hay que mirar (px reales del monitor)
    punto_fase: str = ""           # 'preparar' | 'medir' (el punto se encoge al medir)
    punto_progreso: float = 0.0    # 0..1 del punto actual
    sin_ojos: bool = False         # no se ven los dos ojos abiertos: el reloj está detenido
    repetir_punto: bool = False    # el punto anterior se repite (la cabeza se movió)


class Guia:
    def __init__(self, cfg: dict, t0: float, preparar_s: float = PREPARAR_S, duraciones: dict | None = None,
                 monitor=None):
        self.cfg = cfg
        self.monitor = monitor or MONITOR_REFERENCIA
        self.modelo_mirada = None
        self.mirada_info = None        # {"error_px", "cm", "boton", "impreciso"} tras validar
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
        # 1.1 paquete C: mirada
        self._sin_ojos = False
        self._k = 0                    # punto actual
        self._c = 0.0                  # reloj del punto (solo corre con los dos ojos abiertos)
        self._sub = []                 # muestras del punto o del paso
        self._repeticiones = 0
        self._repetir_punto = False
        self._t_sin_ojos = 0.0         # tiempo seguido sin los dos ojos abiertos (en este punto o paso)
        self._saltados = 0             # puntos que se saltaron por no ver los ojos

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
        if p in PASOS_MIRADA:
            return self._paso_mirada(t, medidas, dt)
        # pasos con tiempo: el Recolector usa un tiempo "medido" (sin los huecos sin cara)
        self._medido += dt
        self._rec.agregar(self._rec.t0 + self._medido, medidas)
        if p.startswith("gesto_"):
            self._nivel = self._nivel_gesto(p[6:], medidas)
        if self._medido >= self.dur[p] - 1e-9:
            self._cerrar_paso(p)
            self._siguiente(t)
        return self.estado(t)

    # ------------------------------------------------------------ 1.1 paquete C: mirada
    def _puntos_paso(self, p: str) -> list:
        if p == "mirada_puntos":
            return puntos_mirada(self.monitor, (self.cfg.get("ojos") or {}).get("puntos_cal", 9))
        if p == "mirada_validar":
            return puntos_validar(self.monitor) if self.modelo_mirada is not None else []
        return [self.monitor.centro]

    def _umbral_cabeza(self):
        tb = self.resultados.get("temblor") or []
        out = []
        for i in range(2):
            try:
                v = float(tb[i])
            except (IndexError, TypeError, ValueError):
                v = 0.0
            out.append(CABEZA_MOVIDA_SIGMAS * max(v if math.isfinite(v) else 0.0, 0.003))
        return out

    def _ojos_abiertos(self, m) -> bool:
        """Los dos ojos con iris y abiertos (EAR de cada ojo al menos el umbral de «abierto» del
        parpadeo × el de frente; sin medida de frente, el de referencia)."""
        if not ambos_ojos(m):
            return False
        ref = self.resultados.get("ear_centro") or {}
        umbral = float((self.cfg.get("gestos") or {}).get("parpadeo", {}).get("abierto", 0.70))
        for k in ("ear_der", "ear_izq"):
            base = ref.get(k) or C.BASE_REFERENCIA[k]
            try:
                v = float(getattr(m, k))
            except (TypeError, ValueError, AttributeError):
                return False
            if not (math.isfinite(v) and v >= umbral * base):
                return False
        return True

    def _paso_mirada(self, t: float, m, dt: float) -> EstadoGuia:
        p = self.paso
        ojos = self._ojos_abiertos(m)
        self._sin_ojos = not ojos
        if not ojos:
            self._t_sin_ojos += dt
            if self._t_sin_ojos >= MIRADA_SIN_OJOS_MAX_S - 1e-9:
                self._sin_ojos_demasiado(t, p)
            return self.estado(t)            # el reloj se detiene
        self._t_sin_ojos = 0.0
        r = rasgos(m)
        muestra = (r[0], r[1], float(m.yaw_n), float(m.pitch_n), float(getattr(m, "io_px", float("nan"))))
        if p in ("mirada_centro", "mirada_cabeza"):
            self._medido += dt
            if self._medido >= 0.3 or p == "mirada_cabeza":
                self._sub.append(muestra)
            if self._medido >= self.dur[p] - 1e-9:
                self._cerrar_mirada(p)
                self._siguiente(t)
            return self.estado(t)
        # mirada_puntos y mirada_validar: punto por punto
        puntos = self._puntos_paso(p)
        if not puntos:
            self.resultados[p] = []
            self._siguiente(t)
            return self.estado(t)
        self._c += dt
        if self._c >= PUNTO_PREPARAR_S + PUNTO_DESCARTAR_S - 1e-9:
            self._sub.append(muestra)
        if self._c >= PUNTO_PREPARAR_S + PUNTO_MEDIR_S - 1e-9:
            self._cerrar_punto(p, puntos[self._k])
            if self._k >= len(puntos):
                self._cerrar_mirada(p)
                self._siguiente(t)
        return self.estado(t)

    def _sin_ojos_demasiado(self, t: float, p: str):
        """No se vieron los dos ojos abiertos durante ``MIRADA_SIN_OJOS_MAX_S``: no se espera más."""
        self._t_sin_ojos = 0.0
        if p == "mirada_centro":
            self._dejar_mirada(t)
            return
        if p == "mirada_puntos":
            puntos = self._puntos_paso(p)
            self._sub = []
            self._c = 0.0
            self._repeticiones = 0
            self._repetir_punto = False
            self._k += 1
            self._saltados += 1
            if len(puntos) - self._saltados < PUNTOS_MINIMOS:
                self._dejar_mirada(t)
                return
            if self._k >= len(puntos):
                self._cerrar_mirada(p)
                self._siguiente(t)
            return
        # mirada_cabeza (lo medido hasta ahora) y mirada_validar (los puntos ya vistos)
        self._cerrar_mirada(p)
        self._siguiente(t)

    def _dejar_mirada(self, t: float):
        """Los ojos no se pueden calibrar: sin modelo de la mirada (la pantalla de calibración deja
        el puntero con la cabeza y lo dice) y se sigue con el paso de después de la mirada."""
        self.modelo_mirada = None
        self.mirada_info = None
        self.resultados.pop("mirada_puntos", None)
        if "mirada_sin_ojos" not in self.avisos:
            self.avisos.append("mirada_sin_ojos")
        ultimo = max(i for i, x in enumerate(self.pasos) if x in PASOS_MIRADA)
        self.i = ultimo
        self._siguiente(t)

    def _mediana(self, filas, i):
        vals = [f[i] for f in filas if math.isfinite(f[i])]
        return statistics.median(vals) if vals else float("nan")

    def _cerrar_punto(self, p: str, destino):
        filas = self._sub
        self._sub = []
        self._c = 0.0
        if not filas:
            return                                     # sin muestras: se repite el mismo punto
        med = [self._mediana(filas, i) for i in range(5)]
        lista = self.resultados.setdefault(p, [])
        if p == "mirada_puntos":
            c0 = self.resultados.get("mirada_cabeza0")
            if c0 is not None:
                uy, up = self._umbral_cabeza()
                movida = abs(med[2] - c0[0]) > uy or abs(med[3] - c0[1]) > up
                if movida and self._repeticiones < REPETIR_PUNTO_MAX:
                    self._repeticiones += 1
                    self._repetir_punto = True
                    return                             # mismo punto otra vez
        self._repeticiones = 0
        self._repetir_punto = False
        lista.append((med[0], med[1], med[2], med[3], float(destino[0]), float(destino[1])))
        self._k += 1

    def _cerrar_mirada(self, p: str):
        filas = self._sub
        self._sub = []
        if p == "mirada_centro":
            if not filas:
                self.resultados[p] = None
                return
            c0 = (self._mediana(filas, 2), self._mediana(filas, 3))
            self.resultados["mirada_cabeza0"] = c0
            self.resultados["mirada_temblor"] = _temblor_iris(filas)
            ios = [f[4] for f in filas if math.isfinite(f[4])]
            ancho = (self.cfg.get("camara") or {}).get("ancho") or 640
            self.resultados["mirada_io"] = (statistics.median(ios) / float(ancho)) if ios else None
            self.resultados[p] = c0
        elif p == "mirada_cabeza":
            self.resultados[p] = filas
            self.modelo_mirada = self._ajustar()
        elif p == "mirada_validar":
            self._resumen_validacion()

    def _ajustar(self):
        pts = list(self.resultados.get("mirada_puntos") or [])
        c0 = self.resultados.get("mirada_cabeza0")
        if c0 is None or len(pts) < 5:
            return None
        muestras = [tuple(x) + (1.0,) for x in pts]
        cab = self.resultados.get("mirada_cabeza") or []
        if cab:
            cx, cy = self.monitor.centro
            w = PESO_CABEZA / len(cab)
            muestras += [(f[0], f[1], f[2], f[3], cx, cy, w) for f in cab]
        return ModeloMirada.ajustar(muestras, c0, temblor_iris=self.resultados.get("mirada_temblor"))

    def _resumen_validacion(self):
        mod = self.modelo_mirada
        val = self.resultados.get("mirada_validar") or []
        errores = []
        for ix, iy, yaw, pitch, x, y in val:
            q = mod.predecir(ix, iy, yaw, pitch) if mod is not None else None
            if q is not None:
                errores.append(math.hypot(q[0] - x, q[1] - y))
        if mod is None:
            self.mirada_info = None
            return
        err = statistics.median(errores) if errores else None
        ppc = px_por_cm(self.monitor)
        cm = (err / ppc) if err is not None else None
        self.mirada_info = {
            "error_px": err,
            "cm": None if cm is None else max(int(round(cm)), 1),
            "boton": None if cm is None else max(int(math.ceil(2 * cm)), 1),
            "impreciso": err is not None and err > ERROR_IMPRECISO_PX,
            "error_grados": (None if cm is None else math.degrees(math.atan(cm / DISTANCIA_SUPUESTA_CM))),
        }

    def mirada_para_guardar(self, fecha: str | None = None):
        """``cal["mirada"]`` (o None si no hubo modelo)."""
        mod = self.modelo_mirada
        if mod is None:
            return None
        from .calibracion import rect_monitor, tam_camara
        import time
        info = self.mirada_info or {}
        d = mod.como_dict()
        d.update({
            "error_px": info.get("error_px"),
            "error_grados": info.get("error_grados"),
            "io_fraccion": self.resultados.get("mirada_io"),
            "monitor": rect_monitor(self.monitor),
            "camara": tam_camara(self.cfg.get("camara")),
            "fecha": fecha or time.strftime("%Y-%m-%d %H:%M"),
        })
        return {k: (v if not isinstance(v, float) or math.isfinite(v) else None) for k, v in d.items()}

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
            # 1.1 paquete C: apertura de los ojos de frente (para saber si están abiertos en la mirada)
            self.resultados["ear_centro"] = {k: (statistics.median(sorted(v)[len(v) // 2:]) if v else None)
                                             for k, v in (("ear_der", rec.valores("ear_der")),
                                                          ("ear_izq", rec.valores("ear_izq")))}
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
        elif p in ("mirada_puntos", "mirada_validar"):
            n = max(len(self._puntos_paso(p)), 1)
            prog = min((self._k + self._c / (PUNTO_PREPARAR_S + PUNTO_MEDIR_S)) / n, 1.0)
        else:
            prog = min(self._medido / self.dur[p], 1.0)
        punto, fase_p, prog_p = None, "", 0.0
        if p in PASOS_MIRADA and not self.terminado:
            puntos = self._puntos_paso(p)
            if puntos and self._k < len(puntos):
                punto = puntos[self._k] if p in ("mirada_puntos", "mirada_validar") else puntos[0]
                if p in ("mirada_puntos", "mirada_validar") and self.fase == "medir":
                    fase_p = "medir" if self._c >= PUNTO_PREPARAR_S else "preparar"
                    prog_p = min(self._c / (PUNTO_PREPARAR_S + PUNTO_MEDIR_S), 1.0)
                else:
                    fase_p = "medir" if self.fase == "medir" else "preparar"
                    prog_p = prog if self.fase == "medir" else 0.0
        return EstadoGuia(p, self.i, len(self.pasos), "terminado" if self.terminado else self.fase, prog,
                          self._sin_cara, self._posicion, self._nivel, list(self.avisos),
                          self._n_largos, self._parpadeo, self._parpadeo_listo,
                          punto, fase_p, prog_p, self._sin_ojos and self.fase == "medir", self._repetir_punto)

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
        if any(p in self.pasos for p in PASOS_MIRADA):
            mir = self.mirada_para_guardar(cal.get("fecha"))
            if mir is not None:
                cal["mirada"] = mir
        largo = C.parpadeo_largo_ms(durs or [])
        return cal, largo, pocos


def _temblor_iris(filas):
    """Temblor del iris con la mirada quieta (como el de la cabeza: el mayor de la desviación
    alrededor de la mediana y la de las diferencias entre cuadros), el mayor de los dos ejes."""
    out = []
    for i in (0, 1):
        vals = [f[i] for f in filas if math.isfinite(f[i])]
        if len(vals) < 10:
            return None
        med = statistics.median(vals)
        mad = 1.4826 * statistics.median([abs(v - med) for v in vals])
        difs = [abs(b - a) for a, b in zip(vals, vals[1:])]
        out.append(max(mad, statistics.median(difs) / 0.954))
    return float(max(out))
