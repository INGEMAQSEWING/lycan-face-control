"""Configuración: %APPDATA%\\Lycan Face Control\\config.json (UTF-8). Sección 9 de la especificación.

- Escritura atómica (archivo temporal + os.replace).
- Si está vacío o dañado: se renombra a config.dañado-AAAAMMDD-HHMMSS.json, se usan los valores
  de fábrica y se avisa "Se restableció la configuración.".
- Cada valor se valida (tipo y rango); uno fuera de rango vuelve al de fábrica y se anota.
- Reglas de coherencia: el parpadeo largo nunca baja de 400 ms, el descanso es más largo que
  el parpadeo largo, el umbral de "ojo abierto" queda por encima del de "cerrado" y **siempre
  hay forma de reanudar** (ver ``_coherencia``).
- La carpeta se puede cambiar con la variable LYCAN_FACE_DATOS (las pruebas la usan para no
  tocar la configuración real).

Mecanismo copiado de Lycan Mouse Control; el contenido es nuevo.
"""
from __future__ import annotations

import copy
import json
import logging
import math
import os
import time
from pathlib import Path

from .constantes import ACCIONES_GESTO, CARPETA_DATOS

log = logging.getLogger("lycan")

VERSION_CONFIG = 1
REINTENTOS_LECTURA = 3
PAUSA_REINTENTO_S = 0.2
PARPADEO_LARGO_PISO_MS = 400       # regla absoluta: los parpadeos naturales nunca hacen nada
MAX_PERFILES = 20
MAX_NOMBRE_PERFIL = 40
PERFIL_PRINCIPAL = "Principal"
AVISO_RESTABLECIDA = "Se restableció la configuración."
AVISO_NO_LEIDA = ("No se pudo leer la configuración (otro programa la tenía abierta); se usan los valores "
                  "de fábrica sin cambiar su archivo. Cierre y vuelva a abrir para recuperarla.")


class ErrorSoloLectura(OSError):
    """La configuración no se pudo leer al abrir: en esta sesión no se escribe encima."""


FABRICA: dict = {
    "version": 1,
    "primera_vez": True,
    "perfil_activo": PERFIL_PRINCIPAL,
    "camara": {"indice": 0, "ancho": 640, "alto": 480, "fps": 30, "fps_proceso": 20, "espejo": True},
    "pantalla": {"monitor": "principal"},
    "puntero": {"modo": "absoluto", "sens_x": 1.0, "sens_y": 1.2, "suavidad": 3, "zona_muerta_px": 4.0,
                "zona_muerta_centro": 0.03, "aceleracion": 0, "margen": 0.10, "joystick_g": 1200},
    "permanencia": {"activa": True, "tiempo_s": 1.0, "radio_px": 30, "recuperacion_s": 1.0,
                    "margen_ms": 150, "anillo_px": 48, "anillo_desde_ms": 200, "sonido": True},
    "gestos": {
        "boca": {"activo": True, "sens": 1.0, "sostener_ms": 600, "corto": "clic", "largo": "pausar"},
        "cejas": {"activo": True, "sens": 1.0, "sostener_ms": 600, "corto": "clic_der", "largo": "ninguna"},
        "sonrisa": {"activo": False, "sens": 1.0, "sostener_ms": 400, "corto": "ninguna", "largo": "ninguna"},
        "parpadeo": {"activo": True, "largo_ms": 800, "descanso_ms": 4000, "doble": False,
                     "cerrado": 0.55, "abierto": 0.70, "fuera_barrido": "ninguna"},
        "largo_ms": 2000, "refractario_ms": 600, "reanudar_ms": 3000,
    },
    "barra": {"visible": True, "posicion": "derecha", "boton_px": 96, "permanencia_s": 1.0, "modo_fijo": False},
    "teclado": {"distribucion": "auto", "permanencia_s": 1.0, "barrido": False, "barrido_paso_s": 1.5,
                "modo_escritura": "mensaje", "letra_pt": 28, "posicion": "abajo", "genero": "neutro",
                "cuidador": "alguien", "solo_comunicacion": False, "aprender": True,
                "repetir_teclas": False},
    "voz": {"nombre": None, "volumen": 80, "velocidad": -1, "hablar_frases": True},
    "seguridad": {"soltar_sin_cara_ms": 300, "pausa_sin_cara_s": 10, "arrastre_max_s": 60},
    "arranque": {"al_encender": False, "estado": "auto"},
    "atajos": {"pausar": "Ctrl+Alt+Espacio", "teclado": "Ctrl+Alt+T", "recentrar": "Ctrl+Alt+C",
               "ventana": "Ctrl+Alt+Inicio", "salir": "Ctrl+Alt+Fin"},
    "comodidad": {"escala_letra": 1.0, "alto_contraste": False, "indicador_borde": True,
                  "mostrar_video": False, "descanso_min": 0, "sonidos": True},
    "ventana": {"x": None, "y": None, "mini": False},
    "perfiles": {PERFIL_PRINCIPAL: {"calibracion": None}},
}
# ---- 1.1 paquete A: velocidad, minimizar y extras de TD Control ----
# Velocidad arriba y abajo aparte (sens_y = sens_x × ajuste; antes fijo en 1,2), los botones
# «Sin clic» y «Lupa» de la barra, y la lupa para el clic preciso.
FABRICA["puntero"]["ajuste_vertical"] = 1.2
FABRICA["barra"]["boton_sin_clic"] = True
FABRICA["barra"]["boton_lupa"] = True
FABRICA["lupa"] = {"zona_px": 200, "aumento": 3, "espera_s": 8.0}
# ---- 1.1 paquete B: emergencia (botón AYUDA) ----
# Pantalla roja, alarma sin internet y voz. Quedarse quieto 2,5 s sobre AYUDA la pide (más que un
# botón normal); 3 s sobre «Ya me atendieron» la apaga. El cuidador la apaga con Ctrl+Alt+A.
FABRICA["emergencia"] = {"activa": True, "mensaje": "Necesito ayuda", "volumen": 100, "repetir_voz": True,
                         "repetir_s": 12, "permanencia_s": 2.5, "detener_s": 3.0}
FABRICA["atajos"]["emergencia"] = "Ctrl+Alt+A"

# Rangos válidos (ruta con puntos -> (mínimo, máximo)). "*" vale por cualquier gesto.
# Fuera de rango = valor de fábrica (y se anota en el registro).
RANGOS = {
    "camara.indice": (0, 9), "camara.ancho": (160, 1920), "camara.alto": (120, 1080),
    "camara.fps": (10, 60), "camara.fps_proceso": (10, 30),
    "puntero.sens_x": (0.5, 3.0), "puntero.sens_y": (0.5, 3.3), "puntero.suavidad": (1, 5),
    "puntero.zona_muerta_px": (0.0, 15.0), "puntero.zona_muerta_centro": (0.0, 0.10),
    "puntero.aceleracion": (0, 3), "puntero.margen": (0.0, 0.25), "puntero.joystick_g": (600, 3000),
    "permanencia.tiempo_s": (0.4, 3.0), "permanencia.radio_px": (10, 80),
    "permanencia.recuperacion_s": (0.3, 3.0), "permanencia.margen_ms": (0, 500),
    "permanencia.anillo_px": (40, 80), "permanencia.anillo_desde_ms": (0, 1000),
    "gestos.*.sens": (0.5, 2.0), "gestos.*.sostener_ms": (100, 1000),
    "gestos.parpadeo.largo_ms": (PARPADEO_LARGO_PISO_MS, 2000),
    "gestos.parpadeo.descanso_ms": (2000, 10000),
    "gestos.parpadeo.cerrado": (0.35, 0.75), "gestos.parpadeo.abierto": (0.45, 1.0),
    "gestos.largo_ms": (1000, 4000), "gestos.refractario_ms": (300, 2000), "gestos.reanudar_ms": (1500, 5000),
    "barra.boton_px": (72, 140), "barra.permanencia_s": (0.4, 3.0),
    "teclado.permanencia_s": (0.4, 3.0), "teclado.barrido_paso_s": (0.5, 4.0), "teclado.letra_pt": (18, 48),
    "voz.volumen": (0, 100), "voz.velocidad": (-5, 5),
    "seguridad.soltar_sin_cara_ms": (150, 1000), "seguridad.pausa_sin_cara_s": (3, 60),
    "seguridad.arrastre_max_s": (10, 300),
    "comodidad.escala_letra": (1.0, 2.0), "comodidad.descanso_min": (0, 120),
    # ---- 1.1 paquete A: velocidad, minimizar y extras de TD Control ----
    "puntero.ajuste_vertical": (0.8, 2.0),
    "lupa.zona_px": (120, 400), "lupa.aumento": (2, 5), "lupa.espera_s": (4.0, 20.0),
    # ---- 1.1 paquete B: emergencia ----
    "emergencia.volumen": (10, 100), "emergencia.repetir_s": (5, 60),
    "emergencia.permanencia_s": (1.5, 5.0), "emergencia.detener_s": (2.0, 5.0),
}
# 0 = apagado; si no es 0, hay un mínimo (un aviso de descanso cada minuto no sirve)
MINIMO_SI_NO_CERO = {"comodidad.descanso_min": 10}

OPCIONES = {
    "puntero.modo": ("absoluto", "relativo", "joystick"),
    "barra.posicion": ("derecha", "izquierda", "arriba", "abajo"),
    "teclado.distribucion": ("auto", "qwerty", "frecuencia"),
    "teclado.modo_escritura": ("mensaje", "directo"),
    "teclado.posicion": ("abajo", "arriba"),
    "teclado.genero": ("neutro", "masculino", "femenino"),
    "arranque.estado": ("auto", "activo", "pausa"),
    "gestos.*.corto": ACCIONES_GESTO,
    "gestos.*.largo": ACCIONES_GESTO,
    "gestos.parpadeo.fuera_barrido": ACCIONES_GESTO,
}
# Textos con largo máximo (el nombre del cuidador se dice en voz alta en las frases)
LARGO_TEXTO = {"teclado.cuidador": 40}
# ---- 1.1 paquete B: lo que dice la voz al pedir ayuda ----
LARGO_TEXTO["emergencia.mensaje"] = 60


def carpeta_datos() -> Path:
    """%APPDATA%\\Lycan Face Control (se puede cambiar con LYCAN_FACE_DATOS, para pruebas)."""
    otra = os.environ.get("LYCAN_FACE_DATOS")
    if otra:
        return Path(otra)
    base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return Path(base) / CARPETA_DATOS


def ruta_config() -> Path:
    return carpeta_datos() / "config.json"


def ruta_recurso(nombre: str) -> Path:
    """Archivo de la carpeta ``recursos`` (ícono, lista de palabras, sonidos), tanto con el
    código fuente como dentro del programa empaquetado con PyInstaller (sys._MEIPASS)."""
    import sys
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / "recursos" / nombre
    return Path(__file__).resolve().parents[1] / "recursos" / nombre


def por_defecto() -> dict:
    return copy.deepcopy(FABRICA)


def _es_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _finito(v) -> bool:
    """math.isfinite sin reventar con enteros gigantes (no caben en un float)."""
    try:
        return math.isfinite(v)
    except (OverflowError, TypeError, ValueError):
        return False


def _comodin(ruta: str) -> str:
    """'gestos.boca.sens' -> 'gestos.*.sens' (para buscar en RANGOS y OPCIONES)."""
    partes = ruta.split(".")
    if len(partes) == 3 and partes[0] == "gestos":
        return f"gestos.*.{partes[2]}"
    return ruta


def _buscar(tabla: dict, ruta: str):
    if ruta in tabla:
        return tabla[ruta]
    return tabla.get(_comodin(ruta))


def _json_seguro(v, profundidad: int = 0) -> bool:
    """True si ``v`` es un dato JSON sencillo (sin NaN ni infinitos) y no demasiado anidado."""
    if profundidad > 8:
        return False
    if v is None or isinstance(v, (bool, str)):
        return True
    if _es_num(v):
        return _finito(v)
    if isinstance(v, list):
        return len(v) <= 1000 and all(_json_seguro(x, profundidad + 1) for x in v)
    if isinstance(v, dict):
        return len(v) <= 200 and all(isinstance(k, str) and _json_seguro(x, profundidad + 1) for k, x in v.items())
    return False


def _validar_perfiles(v, problemas: list) -> dict:
    """Perfiles: {nombre: {"calibracion": None | dict}}. La calibración se revisa a fondo al
    usarla (calibracion.py); aquí solo se exige que sea un objeto JSON sencillo."""
    if not isinstance(v, dict):
        problemas.append("perfiles: tipo equivocado")
        return copy.deepcopy(FABRICA["perfiles"])
    out = {}
    for nombre, perfil in v.items():
        if len(out) >= MAX_PERFILES:
            problemas.append(f"perfiles: más de {MAX_PERFILES}; se ignoran los demás")
            break
        if not isinstance(nombre, str) or not nombre.strip() or len(nombre) > MAX_NOMBRE_PERFIL:
            problemas.append("perfiles: nombre de perfil inválido")
            continue
        cal = perfil.get("calibracion") if isinstance(perfil, dict) else None
        if not isinstance(perfil, dict):
            problemas.append(f"perfiles.{nombre}: tipo equivocado")
        elif cal is not None and not (isinstance(cal, dict) and _json_seguro(cal)):
            problemas.append(f"perfiles.{nombre}.calibracion: dañada; hay que calibrar de nuevo")
            cal = None
        out[nombre] = {"calibracion": copy.deepcopy(cal)}
    if not out:
        out = copy.deepcopy(FABRICA["perfiles"])
    return out


def validar(datos, fabrica: dict | None = None, ruta: str = "", problemas: list | None = None) -> dict:
    """Devuelve una configuración completa y válida. Anota en ``problemas`` lo que se corrigió."""
    fabrica = FABRICA if fabrica is None else fabrica
    problemas = [] if problemas is None else problemas
    if not isinstance(datos, dict):
        problemas.append("la configuración no es un objeto" if ruta == "" else f"{ruta}: tipo equivocado")
        datos = {}
    out = {}
    for clave, fab in fabrica.items():
        r = f"{ruta}.{clave}" if ruta else clave
        if clave not in datos:
            out[clave] = copy.deepcopy(fab)
            continue
        v = datos[clave]
        if r == "perfiles":
            out[clave] = _validar_perfiles(v, problemas)
        elif r == "pantalla.monitor":
            # 'principal', 'todo' o el número de monitor (como texto o como número)
            if isinstance(v, str) and (v in ("principal", "todo") or (v.isascii() and v.isdigit() and int(v) < 16)):
                out[clave] = v
            elif _es_num(v) and _finito(v) and float(v).is_integer() and 0 <= v < 16:
                out[clave] = str(int(v))
            else:
                problemas.append(f"{r}: valor no permitido")
                out[clave] = fab
        elif isinstance(fab, dict):
            out[clave] = validar(v, fab, r, problemas)
        elif isinstance(fab, bool):
            if isinstance(v, bool):
                out[clave] = v
            else:
                problemas.append(f"{r}: se esperaba sí/no")
                out[clave] = fab
        elif _es_num(fab):
            out[clave] = _validar_numero(r, v, fab, problemas)
        elif isinstance(fab, str):
            opciones = _buscar(OPCIONES, r)
            if not isinstance(v, str):
                problemas.append(f"{r}: se esperaba texto")
                out[clave] = fab
            elif opciones is not None and v not in opciones:
                problemas.append(f"{r}: valor '{v}' no permitido")
                out[clave] = fab
            elif r in LARGO_TEXTO and not (0 < len(v.strip()) <= LARGO_TEXTO[r]):
                problemas.append(f"{r}: texto vacío o demasiado largo")
                out[clave] = fab
            else:
                out[clave] = v
        elif fab is None:
            # campos opcionales (voz.nombre, ventana.x/y): número finito, texto corto o nada
            if v is None or (_es_num(v) and _finito(v)) or (isinstance(v, str) and len(v) <= 200):
                out[clave] = v
            else:
                problemas.append(f"{r}: valor no permitido")
                out[clave] = None
        else:  # pragma: no cover - no hay otros tipos en FABRICA
            out[clave] = copy.deepcopy(fab)
    if ruta == "":
        _coherencia(out, problemas)
        out["version"] = VERSION_CONFIG
    return out


def _validar_numero(r: str, v, fab, problemas: list):
    if not _es_num(v) or not _finito(v):        # NaN, infinito, texto o entero gigante
        problemas.append(f"{r}: se esperaba un número")
        return fab
    lo_hi = _buscar(RANGOS, r)
    if lo_hi and not (lo_hi[0] <= v <= lo_hi[1]):
        problemas.append(f"{r}: {v} fuera de rango {lo_hi}")
        return fab
    if r in MINIMO_SI_NO_CERO and v != 0 and v < MINIMO_SI_NO_CERO[r]:
        problemas.append(f"{r}: {v} es muy poco (0 o desde {MINIMO_SI_NO_CERO[r]})")
        return MINIMO_SI_NO_CERO[r]
    if isinstance(fab, float):
        return float(v)
    # campo entero (milisegundos, píxeles, niveles...): un decimal se redondea
    if isinstance(v, float) and not v.is_integer():
        problemas.append(f"{r}: {v} no es un número entero; se usó {int(round(v))}")
    return int(round(v))


def formas_de_reanudar(cfg: dict) -> list[str]:
    """Formas de salir de la pausa SIN manos, además del atajo del cuidador.

    El botón grande "Reanudar" se elige con permanencia; un gesto activo con la acción "pausar"
    (corta o larga) también reanuda (sostenido ``gestos.reanudar_ms``)."""
    formas = []
    if cfg["permanencia"]["activa"]:
        formas.append("permanencia")
    for nombre in ("boca", "cejas", "sonrisa"):
        g = cfg["gestos"][nombre]
        if g["activo"] and "pausar" in (g["corto"], g["largo"]):
            formas.append(f"gesto:{nombre}")
    return formas


def _coherencia(out: dict, problemas: list):
    p = out["gestos"]["parpadeo"]
    # piso absoluto del parpadeo largo (ya lo garantiza RANGOS; se repite por seguridad)
    if p["largo_ms"] < PARPADEO_LARGO_PISO_MS:
        problemas.append("gestos.parpadeo.largo_ms: por debajo del piso de 400 ms")
        p["largo_ms"] = FABRICA["gestos"]["parpadeo"]["largo_ms"]
    if p["descanso_ms"] < p["largo_ms"] + 1000:
        problemas.append("gestos.parpadeo.descanso_ms: debe superar al parpadeo largo en 1 s")
        p["descanso_ms"] = max(FABRICA["gestos"]["parpadeo"]["descanso_ms"], p["largo_ms"] + 1000)
    lo, hi = round(p["cerrado"] + 0.10, 4), round(p["cerrado"] + 0.25, 4)
    if not (lo <= p["abierto"] <= hi):
        nuevo = min(max(p["abierto"], lo), hi)
        problemas.append(f"gestos.parpadeo.abierto: {p['abierto']} fuera de {lo}–{hi}; se usó {nuevo}")
        p["abierto"] = nuevo
    # 1.1 paquete B: pedir AYUDA solo con un gesto LARGO (un gesto corto sale sin querer al
    # hablar, bostezar o toser) y nunca con el parpadeo (un parpadeo largo de sueño, de noche)
    for nombre in ("boca", "cejas", "sonrisa"):
        g = out["gestos"][nombre]
        if g["corto"] == "emergencia":
            problemas.append(f"gestos.{nombre}.corto: «emergencia» solo se permite en el gesto largo")
            g["corto"] = "ninguna"
    if p.get("fuera_barrido") == "emergencia":
        problemas.append("gestos.parpadeo.fuera_barrido: el parpadeo no puede pedir ayuda")
        p["fuera_barrido"] = "ninguna"
    # siempre hay forma de reanudar sin manos
    if not formas_de_reanudar(out):
        problemas.append("sin forma de reanudar: se volvió a encender la permanencia")
        out["permanencia"]["activa"] = True
    # el perfil activo tiene que existir
    if out["perfil_activo"] not in out["perfiles"]:
        problemas.append(f"perfil_activo: '{out['perfil_activo']}' no existe")
        out["perfil_activo"] = (PERFIL_PRINCIPAL if PERFIL_PRINCIPAL in out["perfiles"]
                                else next(iter(out["perfiles"])))


def calibracion_activa(cfg: dict):
    """La calibración del perfil activo (o None si aún no se ha calibrado)."""
    perfil = cfg.get("perfiles", {}).get(cfg.get("perfil_activo"), {})
    return perfil.get("calibracion") if isinstance(perfil, dict) else None


class Configuracion:
    """Carga y guarda la configuración. ``aviso`` queda con el texto para la interfaz, si hubo."""

    def __init__(self, ruta: Path | None = None):
        self.ruta = Path(ruta) if ruta else ruta_config()
        self.datos: dict = por_defecto()
        self.aviso: str | None = None
        self.problemas: list[str] = []
        self.solo_lectura = False     # True: en esta sesión no se escribe el archivo

    def _leer_texto(self) -> str | None:
        """Lee el archivo con 3 intentos (un antivirus, una copia de seguridad o OneDrive pueden
        tenerlo bloqueado un momento). None si no se pudo leer. Un error de CONTENIDO
        (UnicodeDecodeError) se deja pasar: eso sí es archivo dañado."""
        ultimo = None
        for intento in range(REINTENTOS_LECTURA):
            try:
                return self.ruta.read_text(encoding="utf-8-sig")   # acepta el BOM del Bloc de notas o PowerShell
            except UnicodeDecodeError:
                raise
            except OSError as e:
                ultimo = e
                if intento < REINTENTOS_LECTURA - 1:
                    time.sleep(PAUSA_REINTENTO_S)
        log.warning("No se pudo leer la configuración (%s): se usan los valores de fábrica sin "
                    "tocar el archivo.", ultimo)
        return None

    def cargar(self) -> dict:
        self.aviso = None
        self.problemas = []
        self.solo_lectura = False
        if not self.ruta.exists():
            self.datos = por_defecto()
            return self.datos
        try:
            texto = self._leer_texto()
            if texto is None:
                # Bloqueado o sin permiso: NO es un archivo dañado. No se aparta ni se escribe
                # encima en esta sesión (se perdería la calibración).
                self.datos = por_defecto()
                self.datos["primera_vez"] = False
                self.solo_lectura = True
                self.aviso = AVISO_NO_LEIDA
                return self.datos
            if not texto.strip():
                raise ValueError("archivo vacío")
            crudo = json.loads(texto)
            if not isinstance(crudo, dict):
                raise ValueError("no es un objeto JSON")
            version = crudo.get("version")
            problemas: list[str] = []
            if _es_num(version) and version > VERSION_CONFIG:
                problemas.append(f"versión {version} más nueva que la del programa")
            datos = validar(crudo, problemas=problemas)
        except (ValueError, UnicodeDecodeError, RecursionError, MemoryError, OverflowError, TypeError) as e:
            log.warning("Configuración dañada (%s); se restablece.",
                        type(e).__name__ if isinstance(e, RecursionError) else e)
            self.datos = por_defecto()
            self.aviso = AVISO_RESTABLECIDA
            if not self._apartar_danado():
                self.datos["primera_vez"] = False
                self.solo_lectura = True
            return self.datos
        self.problemas = problemas
        self.datos = datos
        for p in self.problemas:
            log.warning("Configuración: %s (se usa un valor seguro)", p)
        if any("versión" in p for p in self.problemas):
            self.aviso = AVISO_RESTABLECIDA
        return self.datos

    def _apartar_danado(self) -> bool:
        try:
            sello = time.strftime("%Y%m%d-%H%M%S")
            destino = self.ruta.with_name(f"config.dañado-{sello}.json")
            n = 1
            while destino.exists():
                destino = self.ruta.with_name(f"config.dañado-{sello}-{n}.json")
                n += 1
            os.replace(self.ruta, destino)
            return True
        except OSError as e:
            log.warning("No se pudo apartar la configuración dañada: %s", e)
            return False

    def guardar(self, datos: dict | None = None):
        if datos is not None:
            self.datos = validar(datos)
        if self.solo_lectura:
            raise ErrorSoloLectura("la configuración no se pudo leer al abrir; no se escribe encima")
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        # Ruta temporal FIJA y un solo intento (tempfile.mkstemp en Windows puede quedarse
        # reintentando sin fin si la carpeta no deja escribir).
        tmp = self.ruta.with_name(self.ruta.name + ".tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.datos, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.ruta)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def guardar_seguro(self, datos: dict | None = None) -> bool:
        """Como guardar(), pero nunca lanza: anota el problema y devuelve False."""
        try:
            self.guardar(datos)
            return True
        except (OSError, ValueError, TypeError) as e:
            log.warning("No se pudo guardar la configuración: %s", e)
            return False

    def restablecer_fabrica(self) -> dict:
        """Vuelve a los valores de fábrica, pero conserva atajos, ventana, perfiles (calibración)
        y el nombre del cuidador."""
        nuevo = por_defecto()
        for clave in ("atajos", "ventana", "perfiles", "perfil_activo"):
            nuevo[clave] = copy.deepcopy(self.datos.get(clave, nuevo[clave]))
        nuevo["teclado"]["cuidador"] = self.datos.get("teclado", {}).get("cuidador", "alguien")
        nuevo["primera_vez"] = False
        self.datos = validar(nuevo)
        return self.datos
