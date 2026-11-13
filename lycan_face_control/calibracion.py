"""Calibración guiada: lógica pura (sección 4.1). La pantalla está en ``ui/calibracion.py``.

Cada paso junta medidas (``Recolector``) y estas funciones las convierten en la calibración del
perfil (sección 9):

``{"fecha", "centro": [yaw0, pitch0], "izq", "der", "arr", "aba", "signo_x", "signo_y",
  "base": {"ear_der", "ear_izq", "mar", "cejas", "sonrisa"}, "umbrales": {...},
  "parpadeo_natural_max_ms", "parpadeos_min"}``

No importa mediapipe, cv2, tkinter ni ctypes.
"""
from __future__ import annotations

import math
import statistics
import time

from .gestos import BASE_REFERENCIA, BOCA_ENTRA, CEJAS_ENTRA, SONRISA_ENTRA
from .mapeo import RANGO_MINIMO_PITCH, RANGO_MINIMO_YAW

DESCARTAR_INICIO_S = 0.5          # los primeros 0,5 s de cada paso no cuentan (la persona se acomoda)
PERCENTIL_RANGO = 90
PARPADEO_LARGO_POR_DEFECTO_MS = 800
PARPADEO_LARGO_MIN_CAL_MS = 600
PARPADEO_LARGO_MAX_MS = 2000
POSICION_IO_MIN, POSICION_IO_MAX = 0.09, 0.22   # io como fracción del ancho de la imagen


def _finito(v) -> bool:
    try:
        return v is not None and math.isfinite(v)
    except TypeError:
        return False


def percentil(valores, p: float) -> float:
    """Percentil con interpolación lineal (sin numpy)."""
    xs = sorted(v for v in valores if _finito(v))
    if not xs:
        return float("nan")
    if len(xs) == 1:
        return xs[0]
    k = (len(xs) - 1) * p / 100.0
    i = int(math.floor(k))
    j = min(i + 1, len(xs) - 1)
    return xs[i] + (xs[j] - xs[i]) * (k - i)


class Recolector:
    """Junta (t, medidas) de un paso, descartando el primer medio segundo."""

    def __init__(self, t0: float, descartar_s: float = DESCARTAR_INICIO_S):
        self.t0 = t0
        self.descartar_s = descartar_s
        self.muestras: list = []
        self.sin_cara = 0

    def agregar(self, t: float, medidas):
        if medidas is None:
            self.sin_cara += 1
            return
        if t - self.t0 >= self.descartar_s - 1e-9:
            self.muestras.append((t, medidas))

    def valores(self, campo: str) -> list:
        return [getattr(m, campo) for _, m in self.muestras if _finito(getattr(m, campo))]

    def duracion(self) -> float:
        if len(self.muestras) < 2:
            return 0.0
        return self.muestras[-1][0] - self.muestras[0][0]

    def __len__(self):
        return len(self.muestras)


# ------------------------------------------------------------------ pasos
def posicion_correcta(io_fraccion: float) -> str:
    """Paso 1: 'bien', 'lejos' o 'cerca' según el tamaño de la cara en la imagen."""
    if not _finito(io_fraccion) or io_fraccion < POSICION_IO_MIN:
        return "lejos"
    if io_fraccion > POSICION_IO_MAX:
        return "cerca"
    return "bien"


def centro(rec: Recolector):
    """Paso 2: mediana de yaw y pitch mirando al frente."""
    ys, ps = rec.valores("yaw_n"), rec.valores("pitch_n")
    if not ys or not ps:
        return None
    return statistics.median(ys), statistics.median(ps)


def temblor(rec: Recolector):
    """Paso 2: temblor de la cabeza quieta (desviación por eje de yaw_n y pitch_n), con dos
    estimaciones robustas (un cuadro raro no la infla): la desviación alrededor de la mediana
    (1,4826 × mediana de |x − mediana|) y la de las diferencias entre cuadros seguidos (mediana
    de |Δ| / 0,954, que no cuenta una deriva lenta). Se queda con la mayor: el temblor de
    FaceMesh no es del todo "blanco" y la segunda sola lo subestima. None si hay pocas muestras."""
    out = []
    for campo in ("yaw_n", "pitch_n"):
        vals = rec.valores(campo)
        if len(vals) < 10:
            return None
        med = statistics.median(vals)
        mad = 1.4826 * statistics.median([abs(v - med) for v in vals])
        difs = [abs(b - a) for a, b in zip(vals, vals[1:])]
        out.append(float(max(mad, statistics.median(difs) / 0.954)))
    return out


def extremo(rec: Recolector, campo: str, c: float, hacia: float, minimo: float):
    """Paso 3: valor del extremo cómodo hacia un lado (percentil 90 del recorrido, no el máximo).

    ``hacia`` = +1 o -1: el lado que se espera (si la persona se movió al revés, se usa el lado
    medido: el signo sale de la calibración, no se adivina). Devuelve (valor, poco_movimiento)."""
    vals = rec.valores(campo)
    if not vals:
        return c + hacia * minimo, True
    desp = [v - c for v in vals]
    # el recorrido hacia donde más se movió
    pos = [d for d in desp if d > 0]
    neg = [-d for d in desp if d < 0]
    if hacia > 0:
        principal, signo = (pos, 1.0) if pos else (neg, -1.0)
    else:
        principal, signo = (neg, -1.0) if neg else (pos, 1.0)
    if not principal:
        return c + hacia * minimo, True
    r = percentil(principal, PERCENTIL_RANGO)
    if r < minimo:
        return c + signo * minimo, True
    return c + signo * r, False


def rangos(c, recs: dict) -> tuple[dict, list]:
    """Paso 3 completo: ``recs`` = {'izq': Recolector, 'der': ..., 'arr': ..., 'aba': ...}.
    Devuelve (valores, lados con poco movimiento)."""
    yaw0, pitch0 = c
    out, pocos = {}, []
    for lado, campo, hacia, minimo, c0 in (("der", "yaw_n", 1.0, RANGO_MINIMO_YAW, yaw0),
                                           ("izq", "yaw_n", -1.0, RANGO_MINIMO_YAW, yaw0),
                                           ("aba", "pitch_n", 1.0, RANGO_MINIMO_PITCH, pitch0),
                                           ("arr", "pitch_n", -1.0, RANGO_MINIMO_PITCH, pitch0)):
        rec = recs.get(lado)
        if rec is None:
            out[lado] = c0 + hacia * minimo
            pocos.append(lado)
            continue
        v, poco = extremo(rec, campo, c0, hacia, minimo)
        out[lado] = v
        if poco:
            pocos.append(lado)
    # coherencia: der y izq a lados opuestos del centro (igual arr y aba)
    if (out["der"] - yaw0) * (out["izq"] - yaw0) > 0:
        out["izq"] = yaw0 - (out["der"] - yaw0)
    if (out["aba"] - pitch0) * (out["arr"] - pitch0) > 0:
        out["arr"] = pitch0 - (out["aba"] - pitch0)
    return out, pocos


def bases(rec: Recolector) -> dict:
    """Paso 4: cara en reposo, boca cerrada -> medianas (EAR solo con los ojos abiertos)."""
    out = {}
    for campo in ("mar", "cejas", "sonrisa"):
        vals = rec.valores(campo)
        out[campo] = statistics.median(vals) if vals else BASE_REFERENCIA[campo]
    for campo in ("ear_der", "ear_izq"):
        vals = rec.valores(campo)
        if vals:
            # descarta los cuadros de parpadeo: se queda con la mitad más abierta
            alto = sorted(vals)[len(vals) // 2:]
            out[campo] = statistics.median(alto)
        else:
            out[campo] = BASE_REFERENCIA[campo]
    return out


def parpadeos_naturales(rec: Recolector, base: dict, cerrado: float = 0.55, abierto: float = 0.70) -> list:
    """Paso 5: duraciones (ms) de los cierres naturales (ambos ojos, con histéresis), medidas
    como en ``gestos.py``: del primer al último cuadro con los ojos cerrados."""
    durs = []
    t_ini = t_ult = None
    cerrados = False
    for t, m in rec.muestras:
        rd = m.ear_der / base["ear_der"] if base.get("ear_der") else float("nan")
        ri = m.ear_izq / base["ear_izq"] if base.get("ear_izq") else float("nan")
        if not (_finito(rd) and _finito(ri)):
            continue
        ambos = rd < cerrado and ri < cerrado
        if not cerrados and ambos:
            cerrados = True
            t_ini = t_ult = t
        elif cerrados:
            if rd > abierto or ri > abierto:
                cerrados = False
                durs.append(max((t_ult - t_ini) * 1000.0, 0.0))
            elif ambos:
                t_ult = t
    return durs


def parpadeo_largo_ms(duraciones_ms: list) -> int:
    """``clamp(max(600, 2 × máximo natural), 600, 2000)``; sin parpadeos: 800."""
    if not duraciones_ms:
        return PARPADEO_LARGO_POR_DEFECTO_MS
    v = max(PARPADEO_LARGO_MIN_CAL_MS, 2.0 * max(duraciones_ms))
    return int(round(min(max(v, PARPADEO_LARGO_MIN_CAL_MS), PARPADEO_LARGO_MAX_MS)))


GESTO_MIN_FRACCION_FABRICA = 0.6    # el gesto medido tiene que llegar al 60 % del umbral de fábrica


def _senal_gesto(nombre: str, base: dict, maximo):
    """(referencia, desplazamiento de fábrica, señal máxima) o None."""
    if maximo is None or not _finito(maximo):
        return None
    if nombre == "boca":
        return base["mar"], BOCA_ENTRA, maximo
    if nombre == "cejas":
        return 1.0, CEJAS_ENTRA, maximo / base["cejas"]
    if nombre == "sonrisa":
        return 1.0, SONRISA_ENTRA, maximo / base["sonrisa"]
    return None


def gesto_detectado(nombre: str, base: dict, maximo: float | None) -> bool:
    """¿La persona hizo de verdad el gesto en el paso "Probar"? Si apenas se movió (ruido, o no
    puede hacerlo, algo común en ELA bulbar), no."""
    r = _senal_gesto(nombre, base, maximo)
    if r is None:
        return False
    ref, fab, senal = r
    return (senal - ref) >= fab * GESTO_MIN_FRACCION_FABRICA - 1e-9


def umbral_gesto(nombre: str, base: dict, maximo: float | None) -> float | None:
    """Paso 6: umbral de entrada al 50 % entre la base y el máximo medido, sin bajar de la
    mitad del valor de fábrica. Unidades: MAR (boca) o cociente con la base (cejas, sonrisa).
    None si no se midió nada útil o la persona **no hizo el gesto** (se queda el de fábrica:
    nunca se vuelve más sensible a partir de una medida sin gesto real)."""
    if maximo is None or not _finito(maximo):
        return None
    if not gesto_detectado(nombre, base, maximo):
        return None
    if nombre == "boca":
        ref, fab = base["mar"], BOCA_ENTRA
        señal_max = maximo
    elif nombre == "cejas":
        ref, fab = 1.0, CEJAS_ENTRA
        señal_max = maximo / base["cejas"]
    elif nombre == "sonrisa":
        ref, fab = 1.0, SONRISA_ENTRA
        señal_max = maximo / base["sonrisa"]
    else:
        return None
    desp = (señal_max - ref) * 0.5
    if desp <= 0:
        return None
    desp = max(desp, fab * 0.5)
    return ref + desp


def construir(c, extremos: dict, base: dict, umbrales: dict | None = None,
              parpadeos_ms: list | None = None, fecha: str | None = None, temblor_cabeza=None) -> dict:
    """Arma la calibración del perfil (sección 9)."""
    yaw0, pitch0 = c
    cal = {
        "fecha": fecha or time.strftime("%Y-%m-%d %H:%M"),
        "centro": [float(yaw0), float(pitch0)],
        "izq": float(extremos["izq"]), "der": float(extremos["der"]),
        "arr": float(extremos["arr"]), "aba": float(extremos["aba"]),
        "signo_x": 1.0 if extremos["der"] >= yaw0 else -1.0,
        "signo_y": 1.0 if extremos["aba"] >= pitch0 else -1.0,
        "base": {k: float(v) for k, v in base.items()},
        "umbrales": {k: float(v) for k, v in (umbrales or {}).items() if v is not None and _finito(v)},
        "parpadeo_natural_max_ms": float(max(parpadeos_ms)) if parpadeos_ms else None,
        "parpadeos_min": len(parpadeos_ms or []),
    }
    if temblor_cabeza is not None and all(_finito(x) and x >= 0 for x in temblor_cabeza):
        cal["temblor"] = [float(x) for x in temblor_cabeza]
    return cal


def calibracion_valida(cal) -> bool:
    """Revisión a fondo antes de usar una calibración guardada."""
    if not isinstance(cal, dict):
        return False
    c = cal.get("centro")
    if not (isinstance(c, (list, tuple)) and len(c) == 2 and all(_finito(x) for x in c)):
        return False
    for k in ("izq", "der", "arr", "aba"):
        if not _finito(cal.get(k)):
            return False
    b = cal.get("base")
    if not isinstance(b, dict):
        return False
    return (all(_finito(b.get(k)) and b.get(k) > 0 for k in ("ear_der", "ear_izq", "cejas", "sonrisa"))
            and _finito(b.get("mar")) and b.get("mar") >= 0)
