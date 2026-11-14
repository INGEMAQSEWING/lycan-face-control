"""Opciones (sección 6.6): pestañas grandes, controles con botones «−» y «+» (operables con la
cabeza), vista previa en vivo y «Cancelar» que revierte.

- Cada cambio se valida y se manda al motor al instante (``orden("config", copia)``), así la
  persona prueba la velocidad o el tiempo de permanencia antes de guardar.
- «Guardar» escribe ``config.json``; «Abrir al encender» solo toca el registro de Windows al
  guardar. «Cancelar» devuelve al motor la configuración de antes.
- Al abrir se suelta todo (sección 5.5).
- Las pestañas largas se parten en páginas («Anterior» / «Siguiente») para no tener que
  desplazar con la cabeza.
"""
from __future__ import annotations

import copy
import logging
import tkinter as tk

from .. import constantes as K
from ..config import OPCIONES, RANGOS, por_defecto, validar
from .comun import BotonGrande, acomodar_pestanas, area_libre, boton_ayuda, letra, tema
from .textos import nombre_accion, t

log = logging.getLogger("lycan")

FILAS_POR_PAGINA = 6
VELOCIDAD_MIN, VELOCIDAD_MAX = 1, 10
ACCIONES_PARPADEO = ("ninguna", "clic", "clic_izq", "clic_der", "doble", "pausar", "teclado", "recentrar")
ACCIONES_GESTO_UI = ("ninguna", "clic", "clic_izq", "clic_der", "doble", "arrastrar", "pausar", "teclado",
                     "recentrar", "borrar", "hablar", "siguiente")
# 1.1 paquete B: «Pedir AYUDA (alarma)» solo en el gesto LARGO (nunca en el corto ni en el parpadeo)
ACCIONES_GESTO_LARGO_UI = ACCIONES_GESTO_UI + ("emergencia",)


# ------------------------------------------------------------------ velocidad del puntero (1 a 10)
# Velocidad 1..10 -> sens_x. 3 = fábrica (1,0). Por debajo de 1,0 el puntero ya no llega a los
# bordes moviendo la cabeza dentro del rango cómodo calibrado (con 0,5 quedaba un tercio de la
# pantalla fuera de alcance, incluida la barra): 1 y 2 apenas bajan, y siguen llegando a todo.
SENS_VELOCIDAD = (0.92, 0.96, 1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5, 2.75)
# ---- 1.1 paquete A: la velocidad también gradúa el joystick, y arriba/abajo va aparte ----
# Nivel 3 = 1200 (fábrica); todos caben en el rango (600, 3000) de puntero.joystick_g.
JOYSTICK_VELOCIDAD = (1000, 1050, 1200, 1400, 1600, 1800, 2000, 2300, 2600, 3000)
AJUSTE_VERTICAL_FABRICA = 1.2
SENS_Y_MIN, SENS_Y_MAX = 0.92, 3.3     # por debajo de 0,92 el puntero deja de llegar a los bordes


def _ajuste_valido(ajuste_vertical) -> float:
    lo, hi = RANGOS["puntero.ajuste_vertical"]
    try:
        a = float(ajuste_vertical)
    except (TypeError, ValueError):
        return AJUSTE_VERTICAL_FABRICA
    if a != a or not lo <= a <= hi:
        return AJUSTE_VERTICAL_FABRICA
    return a


def sens_de_velocidad(n: int, ajuste_vertical: float = AJUSTE_VERTICAL_FABRICA) -> tuple[float, float, int]:
    """Velocidad 1..10 -> (sens_x, sens_y, joystick_g). 3 = valores de fábrica (1,0; 1,2; 1200).

    ``sens_y = sens_x × ajuste_vertical`` (entre 0,92 y 3,3). La calibración no cambia: solo las
    ganancias."""
    try:
        n = int(n)
    except (TypeError, ValueError):
        n = 3
    n = min(max(n, VELOCIDAD_MIN), VELOCIDAD_MAX)
    sx = SENS_VELOCIDAD[n - 1]
    sy = round(max(min(sx * _ajuste_valido(ajuste_vertical), SENS_Y_MAX), SENS_Y_MIN), 2)
    return sx, sy, JOYSTICK_VELOCIDAD[n - 1]


def velocidad_de_sens(sens_x: float) -> int:
    try:
        v = float(sens_x)
    except (TypeError, ValueError):
        return 3
    if v != v:
        return 3
    i = min(range(len(SENS_VELOCIDAD)), key=lambda k: abs(SENS_VELOCIDAD[k] - v))
    return min(max(i + 1, VELOCIDAD_MIN), VELOCIDAD_MAX)


# ------------------------------------------------------------------ acceso por ruta
def leer(datos: dict, ruta: str):
    d = datos
    for p in ruta.split("."):
        d = d[p]
    return d


def escribir(datos: dict, ruta: str, valor):
    partes = ruta.split(".")
    d = datos
    for p in partes[:-1]:
        d = d[p]
    d[partes[-1]] = valor


def _rango(ruta: str):
    if ruta in RANGOS:
        return RANGOS[ruta]
    partes = ruta.split(".")
    if len(partes) == 3 and partes[0] == "gestos":
        return RANGOS.get(f"gestos.*.{partes[2]}")
    return None


def _decimal(v: float, dec: int = 1) -> str:
    return f"{v:.{dec}f}".replace(".", ",")


# ------------------------------------------------------------------ definición de controles
# (tipo, ruta, clave de texto, paso o lista de opciones, formato)
#  tipo: "num" (− valor +), "bool" (Sí/No), "opc" (◀ valor ▶), "vel" (velocidad 1..10),
#        "texto" (campo para el cuidador), "boton" (abre algo)
def _seg(v):
    return t("op_segundos", n=_decimal(float(v)))


def _ms(v):
    return t("op_segundos", n=_decimal(float(v) / 1000.0, 2))


def _pct(v):
    return t("op_porcentaje", n=int(round(float(v) * 100)))


def _min(v):
    return t("op_apagado") if int(v) == 0 else t("op_minutos", n=int(v))


def _entero(v):
    return str(int(round(float(v))))


def _veces(v):
    return _decimal(float(v)) + " ×"


def _ajuste_vertical(v):
    v = float(v)
    if abs(v - 1.0) < 1e-6:
        return t("op_ajuste_vertical_igual")
    return t("op_ajuste_vertical_valor", n=int(round(v * 100)))


def _aumento(v):
    return t("op_lupa_aumento_valor", n=int(round(float(v))))


PESTANAS = ("puntero", "clic", "gestos", "teclado", "comodidad", "atajos")
# 1.1 paquete B: pestaña «Emergencia» (botón AYUDA)
PESTANAS = PESTANAS + ("emergencia",)
NOMBRES_ATAJOS = ("pausar", "teclado", "recentrar", "ventana", "salir", "emergencia")


def _segundos_enteros(v):
    return t("op_segundos", n=int(round(float(v))))


def _volumen(v):
    return t("op_porcentaje", n=int(round(float(v))))


def _puntos_cal(v):
    return t("op_ojos_puntos_valor", n=int(v))


CAMARA_OJOS = (1280, 720)       # con los ojos se sugiere esta resolución (el iris se ve mejor)


def sugerir_camara(datos: dict) -> bool:
    """¿Mostrar la sugerencia de subir la cámara a 1280 × 720? Solo con una fuente con ojos."""
    try:
        return datos["puntero"].get("fuente", "cabeza") != "cabeza" and int(datos["camara"]["ancho"]) < CAMARA_OJOS[0]
    except (KeyError, TypeError, ValueError):
        return False


def controles_ojos(datos: dict | None = None) -> list:
    """1.1 paquete C: filas de los ojos (página aparte de la pestaña Puntero). Sin ``datos`` van
    todas; con ``datos`` solo si el puntero se mueve con los ojos."""
    fuente = "ojos" if datos is None else datos["puntero"].get("fuente", "cabeza")
    if fuente == "cabeza":
        return []
    filas = []
    if datos is None or sugerir_camara(datos):
        filas.append(("boton", "camara_ojos", "op_ojos_camara", None, None))
    filas += [
        ("num", "ojos.permanencia_s", "op_ojos_permanencia", 0.1, _seg),
        ("num", "ojos.suavidad", "op_ojos_suavidad", 1, _entero),
        ("bool", "ojos.iman", "op_ojos_iman", None, None),
        ("bool", "ojos.lupa", "op_ojos_lupa", None, None),
    ]
    if datos is None or fuente == "cabeza_y_ojos":
        filas += [
            ("num", "ojos.salto_px", "op_ojos_salto", 20, _entero),
            ("num", "ojos.ganancia_fina", "op_ojos_fina", 0.1, _veces),
        ]
    filas.append(("opc", "ojos.puntos_cal", "op_ojos_puntos", (5, 9), _puntos_cal))
    return filas


def paginas_de(pestana: str, todos: list, por: int) -> list:
    """Parte los controles en páginas de ``por`` filas. En la pestaña Puntero las filas de los
    ojos empiezan siempre en una página nueva (1.1 paquete C)."""
    por = max(int(por), 1)
    grupos = [todos]
    if pestana == "puntero":
        i = next((k for k, c in enumerate(todos) if c[1].startswith("ojos.") or c[1] == "camara_ojos"), None)
        if i is not None and i > 0:
            grupos = [todos[:i], todos[i:]]
    paginas = []
    for g in grupos:
        for k in range(0, len(g), por):
            paginas.append(g[k:k + por])
    return paginas or [[]]


def controles(pestana: str, gesto: str = "boca", datos: dict | None = None) -> list:
    if pestana == "puntero":
        return [
            ("vel", "puntero.sens_x", "op_velocidad", 1, None),
            ("num", "puntero.ajuste_vertical", "op_ajuste_vertical", 0.1, _ajuste_vertical),
            ("num", "puntero.suavidad", "op_suavidad", 1, _entero),
            ("opc", "puntero.modo", "op_modo", OPCIONES["puntero.modo"],
             lambda v: t(f"op_modo_{v}")),
            # 1.1 paquete C: con qué se mueve el puntero (las filas de los ojos van en otra página)
            ("opc", "puntero.fuente", "op_fuente", OPCIONES["puntero.fuente"], lambda v: t(f"op_fuente_{v}")),
        ] + controles_ojos(datos)
    if pestana == "clic":
        return [
            ("bool", "permanencia.activa", "op_perm_activa", None, None),
            ("num", "permanencia.tiempo_s", "op_perm_tiempo", 0.1, _seg),
            ("num", "permanencia.radio_px", "op_perm_radio", 5, _entero),
            ("num", "permanencia.recuperacion_s", "op_perm_recuperacion", 0.1, _seg),
            ("bool", "permanencia.sonido", "op_perm_sonido", None, None),
            ("num", "barra.permanencia_s", "op_barra_tiempo", 0.1, _seg),
            ("bool", "barra.modo_fijo", "op_barra_fijo", None, None),
            # ---- 1.1 paquete A: lupa ----
            ("num", "lupa.aumento", "op_lupa_aumento", 1, _aumento),
            ("num", "lupa.zona_px", "op_lupa_zona", 20, _entero),
            ("num", "lupa.espera_s", "op_lupa_espera", 1.0, _seg),
        ]
    if pestana == "gestos":
        if gesto == "parpadeo":
            return [
                ("bool", "gestos.parpadeo.activo", "op_gesto_activo", None, None),
                ("num", "gestos.parpadeo.largo_ms", "op_parpadeo_largo", 100, _ms),
                ("opc", "gestos.parpadeo.fuera_barrido", "op_parpadeo_fuera", ACCIONES_PARPADEO, nombre_accion),
                ("bool", "gestos.parpadeo.doble", "op_parpadeo_doble", None, None),
            ]
        b = f"gestos.{gesto}"
        return [
            ("bool", f"{b}.activo", "op_gesto_activo", None, None),
            ("num", f"{b}.sens", "op_gesto_sens", 0.1, _veces),
            ("num", f"{b}.sostener_ms", "op_gesto_sostener", 50, _ms),
            ("opc", f"{b}.corto", "op_gesto_corto", ACCIONES_GESTO_UI, nombre_accion),
            ("opc", f"{b}.largo", "op_gesto_largo", ACCIONES_GESTO_LARGO_UI, nombre_accion),
        ]
    if pestana == "teclado":
        return [
            ("opc", "teclado.distribucion", "op_distribucion", OPCIONES["teclado.distribucion"],
             lambda v: t(f"op_dist_{v}")),
            ("num", "teclado.permanencia_s", "op_tecla_tiempo", 0.1, _seg),
            ("bool", "teclado.repetir_teclas", "op_repetir_teclas", None, None),
            ("bool", "teclado.barrido", "op_barrido", None, None),
            ("num", "teclado.barrido_paso_s", "op_barrido_paso", 0.1, _seg),
            ("opc", "teclado.modo_escritura", "op_escritura", OPCIONES["teclado.modo_escritura"],
             lambda v: t(f"op_escritura_{v}")),
            ("num", "teclado.letra_pt", "op_letra_teclado", 2, _entero),
            ("num", "voz.volumen", "op_voz_volumen", 10, lambda v: t("op_porcentaje", n=int(v))),
            ("num", "voz.velocidad", "op_voz_velocidad", 1, lambda v: f"{int(v):+d}"),
            ("bool", "voz.hablar_frases", "op_voz_frases", None, None),
            ("opc", "teclado.genero", "op_genero", OPCIONES["teclado.genero"], lambda v: t(f"op_genero_{v}")),
            ("bool", "teclado.solo_comunicacion", "op_solo_com", None, None),
            ("bool", "teclado.aprender", "op_aprender", None, None),
            ("texto", "teclado.cuidador", "op_cuidador", None, None),
            ("boton", "frases", "op_editar_frases", None, None),
        ]
    if pestana == "comodidad":
        return [
            ("num", "comodidad.escala_letra", "op_escala", 0.1, _pct),
            ("bool", "comodidad.alto_contraste", "op_alto_contraste", None, None),
            ("opc", "barra.posicion", "op_barra_posicion", OPCIONES["barra.posicion"], lambda v: t(f"op_pos_{v}")),
            ("num", "barra.boton_px", "op_barra_tam", 8, _entero),
            ("bool", "barra.visible", "op_barra_visible", None, None),
            ("bool", "barra.boton_sin_clic", "op_boton_sin_clic", None, None),      # 1.1
            ("bool", "barra.boton_lupa", "op_boton_lupa", None, None),              # 1.1
            ("bool", "comodidad.indicador_borde", "op_indicador_borde", None, None),
            ("bool", "comodidad.sonidos", "op_sonidos", None, None),
            ("num", "comodidad.descanso_min", "op_descanso", 5, _min),
            ("bool", "comodidad.mostrar_video", "op_video", None, None),
            ("bool", "arranque.al_encender", "op_al_encender", None, None),
            ("opc", "arranque.estado", "op_arranque", OPCIONES["arranque.estado"], lambda v: t(f"op_arranque_{v}")),
        ]
    if pestana == "atajos":
        return [("atajo", f"atajos.{n}", f"op_atajo_{n}", None, None) for n in NOMBRES_ATAJOS]
    if pestana == "emergencia":
        return [
            ("bool", "emergencia.activa", "op_emergencia_activa", None, None),
            ("boton", "probar_alarma", "op_emergencia_probar", None, None),
            ("texto", "emergencia.mensaje", "op_emergencia_mensaje", None, None),
            ("num", "emergencia.volumen", "op_emergencia_volumen", 10, _volumen),
            ("bool", "emergencia.repetir_voz", "op_emergencia_voz", None, None),
            ("num", "emergencia.repetir_s", "op_emergencia_cada", 1, _segundos_enteros),
            ("num", "emergencia.permanencia_s", "op_emergencia_tiempo", 0.5, _seg),
            ("num", "emergencia.detener_s", "op_emergencia_detener", 0.5, _seg),
        ]
    return []


def paso_numero(datos: dict, ruta: str, paso, signo: int):
    """Nuevo valor de un control numérico, recortado a su rango."""
    v = leer(datos, ruta)
    lo, hi = _rango(ruta) or (None, None)
    if ruta == "comodidad.descanso_min":
        if signo > 0:
            nuevo = 10 if v < 10 else v + paso
        else:
            nuevo = 0 if v <= 10 else v - paso
    else:
        nuevo = v + signo * paso
    if lo is not None:
        nuevo = min(max(nuevo, lo), hi)
    if isinstance(v, int) and not isinstance(v, bool) and float(paso).is_integer():
        return int(round(nuevo))
    return round(float(nuevo), 4)


def ciclar(opciones, actual, signo: int):
    opciones = list(opciones)
    i = opciones.index(actual) if actual in opciones else 0
    return opciones[(i + signo) % len(opciones)]


# Ayuda corta que se ve debajo del nombre de algunos controles
AYUDAS_CONTROL = {"puntero.sens_x": "op_velocidad_ayuda", "barra.modo_fijo": "op_barra_fijo_ayuda",
                  "puntero.ajuste_vertical": "op_ajuste_vertical_ayuda", "puntero.fuente": "op_fuente_ayuda"}
VEL_ALTO_PX = 76            # botones «Más lento» y «Más rápido»: grandes, elegibles con la cabeza


def _al_encender_real(app) -> bool | None:
    """Si el programa abre al encender según el registro de Windows (None si no se puede saber)."""
    if not getattr(app, "sistema", False):
        return None
    try:
        from ..sistema import inicio
        return bool(inicio.activo())
    except Exception:  # noqa: BLE001
        return None


def atajos_validos(atajos: dict, revisar_teclado: bool = True) -> str | None:
    """Texto del primer problema de los atajos (o None): que se entienda, que no esté repetido y
    que no escriba una letra con el teclado de la persona (AltGr). Mismos textos que los atajos."""
    try:
        from ..sistema.atajos import AtajoInvalido, interpretar, produce_caracter, texto_repetido
    except Exception:  # noqa: BLE001
        return None
    usados: dict = {}
    for nombre, texto in atajos.items():
        if not isinstance(texto, str) or not texto.strip():
            return t("op_atajo_vacio")
        try:
            combo = interpretar(texto)
        except AtajoInvalido as e:
            return t("op_atajo_invalido", texto=texto, motivo=str(e))
        except Exception:  # noqa: BLE001
            return t("op_atajo_invalido", texto=texto, motivo="")
        if combo in usados:
            return texto_repetido(texto, usados[combo])
        usados[combo] = nombre
        if revisar_teclado:
            try:
                car = produce_caracter(*combo)
            except Exception:  # noqa: BLE001
                car = None
            if car:
                from ..sistema.atajos import TECLA_MUERTA
                if car == TECLA_MUERTA:
                    return t("op_atajo_acento", texto=texto)
                return t("op_atajo_escribe", texto=texto, car=car)
    return None


class VentanaOpciones:
    def __init__(self, root, app):
        self.root = root
        self.app = app
        self.original = copy.deepcopy(app.cfg.datos)
        self.datos = copy.deepcopy(app.cfg.datos)
        # "Abrir al encender": lo que manda es el registro de Windows (el instalador también lo pone)
        real = _al_encender_real(app)
        if real is not None:
            self.original["arranque"]["al_encender"] = real
            self.datos["arranque"]["al_encender"] = real
        self.pestana = "puntero"
        self.gesto = "boca"
        self.pagina = 0
        self.confirmando = False
        self.cerrada = False
        self.entradas: dict = {}
        self.etiquetas_valor: dict = {}
        T = self.tema = tema(self.datos)
        w = self.win = tk.Toplevel(root)
        w.title(t("op_titulo"))
        w.configure(bg=T.fondo)
        w.attributes("-topmost", True)
        w.protocol("WM_DELETE_WINDOW", self.cancelar)
        l, a, d, ab = area_libre(app, root)
        self.W = min(int((d - l) * 0.8), 1000)
        self.H = min(int((ab - a) * 0.92), 700)
        w.geometry(f"{self.W}x{self.H}+{l + (d - l - self.W) // 2}+{a + (ab - a - self.H) // 2}")
        app.registro.ventana("opciones", w)
        self.app.orden("soltar", "opciones")
        self._armar()
        self._loop = w.after(150, self._en_vivo)

    # ------------------------------------------------------------ armado
    def _f(self, pt=16, negrita=True):
        return letra(self.original, pt, negrita)

    def _boton(self, padre, texto, ident, accion, color=None, ancho=None):
        b = BotonGrande(padre, texto, self.app.registro.comando(ident), self.tema, self._f(), color=color)
        if ancho:
            b.configure(width=ancho)
        self.app.registro.agregar(ident, b, accion)
        return b

    def _armar(self):
        for c in self.win.winfo_children():
            c.destroy()
        T = self.tema
        self.entradas = {}
        self.etiquetas_valor = {}
        arriba = tk.Frame(self.win, bg=T.fondo)
        arriba.pack(fill="x", padx=10, pady=(10, 4))
        ayuda = boton_ayuda(arriba, t("op_ayuda"), self.original, T)
        ayuda.pack(side="right", padx=(6, 0), anchor="n")
        tabs = tk.Frame(arriba, bg=T.fondo)
        tabs.pack(side="left", fill="x", expand=True)
        botones = []
        for p in PESTANAS:
            b = self._boton(tabs, t(f"op_tab_{p}"), f"op:tab:{p}", lambda p=p: self.ir_a(p))
            b.activo(p == self.pestana)
            botones.append(b)
        # 1.1: con 7 pestañas no caben en una fila en 1366 × 768: van en dos
        ayuda.update_idletasks()
        acomodar_pestanas(tabs, botones, self.W - 20 - ayuda.winfo_reqwidth() - 6)
        # 1.1: «Guardar / Cancelar» se ubica antes que el cuerpo: si algo no cabe, se acorta el
        # cuerpo (que pasa a más páginas), nunca desaparecen los botones de abajo
        abajo = tk.Frame(self.win, bg=T.fondo)
        abajo.pack(fill="x", side="bottom", padx=10, pady=10)
        self.cuerpo = tk.Frame(self.win, bg=T.fondo)
        self.cuerpo.pack(fill="both", expand=True, padx=14, pady=6)
        self._arriba, self._abajo = arriba, abajo
        if self.confirmando:
            tk.Label(abajo, text=t("op_fabrica_pregunta"), bg=T.fondo, fg=T.texto, font=self._f(16),
                     wraplength=self.W - 40, justify="left").pack(fill="x", pady=(0, 6))
            self._boton(abajo, t("op_fabrica_si"), "op:fabrica_si", self.fabrica_si, color=T.ambar).pack(
                side="left", expand=True, fill="x", padx=4)
            self._boton(abajo, t("btn_no"), "op:fabrica_no", self.fabrica_no).pack(side="left", expand=True,
                                                                                   fill="x", padx=4)
        else:
            self._boton(abajo, t("btn_guardar"), "op:guardar", self.guardar, color=T.verde).pack(
                side="left", expand=True, fill="x", padx=4)
            self._boton(abajo, t("btn_cancelar"), "op:cancelar", self.cancelar).pack(side="left", expand=True,
                                                                                     fill="x", padx=4)
            self._boton(abajo, t("op_fabrica"), "op:fabrica", self.pedir_fabrica).pack(side="left", expand=True,
                                                                                       fill="x", padx=4)
        self._armar_cuerpo()

    def _armar_cuerpo(self):
        T = self.tema
        for c in self.cuerpo.winfo_children():
            c.destroy()
        self.entradas = {}
        self.etiquetas_valor = {}
        self.c_nivel = None
        if self.pestana == "gestos":
            sel = tk.Frame(self.cuerpo, bg=T.fondo)
            sel.pack(fill="x", pady=(0, 6))
            for g in K.GESTOS:
                b = self._boton(sel, t(f"gesto_{g}"), f"op:gesto:{g}", lambda g=g: self.elegir_gesto(g))
                b.pack(side="left", expand=True, fill="x", padx=3)
                b.activo(g == self.gesto)
        if self.pestana == "emergencia" and self.pagina == 0:
            tk.Label(self.cuerpo, text=t("op_emergencia_nota"), bg=T.fondo, fg=T.texto_suave,
                     font=self._f(16, False), wraplength=self.W - 60, justify="left").pack(fill="x", pady=(0, 8))
        if self.pestana == "atajos":
            tk.Label(self.cuerpo, text=t("op_atajos_ayuda"), bg=T.fondo, fg=T.texto_suave, font=self._f(16, False),
                     wraplength=self.W - 60, justify="left").pack(fill="x", pady=(0, 8))
        todos = controles(self.pestana, self.gesto, self.datos)
        por = self._filas_pagina()
        lista_paginas = paginas_de(self.pestana, todos, por)
        paginas = len(lista_paginas)
        self.pagina = min(self.pagina, paginas - 1)
        filas = lista_paginas[self.pagina]
        for ctl in filas:
            self._fila(ctl)
        if self.pestana == "gestos":
            nota = t("op_parpadeo_nota") if self.gesto == "parpadeo" else t("op_gesto_nivel")
            f = tk.Frame(self.cuerpo, bg=T.fondo)
            f.pack(fill="x", pady=(8, 0))
            tk.Label(f, text=nota, bg=T.fondo, fg=T.texto_suave, font=self._f(16, False), anchor="w",
                     wraplength=self.W - 60, justify="left").pack(side="left")
            if self.gesto != "parpadeo":
                self.c_nivel = tk.Canvas(f, width=260, height=26, bg=T.fondo_2, highlightthickness=1,
                                         highlightbackground=T.texto_suave)
                self.c_nivel.pack(side="left", padx=10)
        if self.pestana == "puntero" and any(c[1] == "puntero.modo" for c in filas):
            tk.Label(self.cuerpo, text=t("op_modo_ayuda"), bg=T.fondo, fg=T.texto_suave, font=self._f(16, False),
                     wraplength=self.W - 60, justify="left").pack(fill="x", pady=(10, 0))
        if paginas > 1:
            nav = tk.Frame(self.cuerpo, bg=T.fondo)
            nav.pack(side="bottom", fill="x", pady=(6, 0))
            if self.pagina > 0:
                self._boton(nav, "◀ " + t("btn_anterior"), "op:pagina:anterior",
                            lambda: self.ir_pagina(-1)).pack(side="left", padx=4)
            tk.Label(nav, text=f"{self.pagina + 1} / {paginas}", bg=T.fondo, fg=T.texto,
                     font=self._f(16)).pack(side="left", expand=True)
            if self.pagina < paginas - 1:
                self._boton(nav, t("btn_siguiente") + " ▶", "op:pagina:siguiente",
                            lambda: self.ir_pagina(1)).pack(side="right", padx=4)
        # 1.1: si la página no cabe a lo alto (pantalla chica, letra grande, pestañas en dos filas),
        # se arma otra vez con una fila menos por página
        if por > 1 and self._no_cabe():
            self._por_pagina[(self.pestana, self.gesto)] = por - 1
            self._armar_cuerpo()

    def _filas_pagina(self) -> int:
        if not hasattr(self, "_por_pagina"):
            self._por_pagina = {}
        return self._por_pagina.get((self.pestana, self.gesto), FILAS_POR_PAGINA)

    def _no_cabe(self) -> bool:
        try:
            self.win.update_idletasks()
            alto = (self.H - self._arriba.winfo_reqheight() - self._abajo.winfo_reqheight()
                    - (10 + 4) - 2 * 10 - 2 * 6)
            return self.cuerpo.winfo_reqheight() > alto
        except (tk.TclError, AttributeError):
            return False

    def _fila(self, ctl):
        tipo, ruta, clave, extra, fmt = ctl
        T = self.tema
        fila = tk.Frame(self.cuerpo, bg=T.fondo_2)
        fila.pack(fill="x", pady=3)
        ayuda = AYUDAS_CONTROL.get(ruta)
        if ayuda:
            # 1.1 paquete B: la ayuda corta va debajo, a todo el ancho de la fila (al lado de los
            # botones ocupaba muchas líneas y la pestaña no cabía a lo alto en 1366 × 768)
            tk.Label(fila, text=t(ayuda), bg=T.fondo_2, fg=T.texto_suave, font=self._f(13, False), anchor="w",
                     wraplength=self.W - 80, justify="left").pack(side="bottom", fill="x", padx=10, pady=(0, 4))
            tk.Label(fila, text=t(clave), bg=T.fondo_2, fg=T.texto, font=self._f(16, False), anchor="w",
                     wraplength=int(self.W * 0.42), justify="left").pack(side="left", padx=10, pady=4, fill="x",
                                                                        expand=True)
        else:
            tk.Label(fila, text=t(clave), bg=T.fondo_2, fg=T.texto, font=self._f(16, False), anchor="w",
                     wraplength=int(self.W * 0.42), justify="left").pack(side="left", padx=10, pady=6, fill="x",
                                                                        expand=True)
        if tipo == "vel":
            # 1.1: «◀ Más lento»  3 de 10  «Más rápido ▶», botones de 76 px de alto
            caja = tk.Frame(fila, bg=T.fondo_2)
            caja.pack(side="right", padx=6, pady=4)
            caja.grid_rowconfigure(0, minsize=VEL_ALTO_PX)      # alto mínimo, ancho según el texto
            for col, texto, sufijo, signo in ((0, t("op_mas_lento"), "menos", -1),
                                              (2, t("op_mas_rapido"), "mas", +1)):
                self._boton(caja, texto, f"op:{ruta}:{sufijo}",
                            lambda e=None, s=signo: self.cambiar(ctl, s)).grid(row=0, column=col, sticky="nsew",
                                                                                 padx=4)
            v = tk.Label(caja, text="", bg=T.fondo_2, fg=T.acento, font=self._f(18), width=7)
            v.grid(row=0, column=1, sticky="nsew")
            self.etiquetas_valor[ruta] = (v, ctl)
        elif tipo == "num":
            self._boton(fila, "+", f"op:{ruta}:mas", lambda: self.cambiar(ctl, +1), ancho=3).pack(side="right",
                                                                                                padx=6, pady=4)
            v = tk.Label(fila, text="", bg=T.fondo_2, fg=T.acento, font=self._f(18), width=12)
            v.pack(side="right")
            self._boton(fila, "−", f"op:{ruta}:menos", lambda: self.cambiar(ctl, -1), ancho=3).pack(side="right",
                                                                                                  padx=6, pady=4)
            self.etiquetas_valor[ruta] = (v, ctl)
        elif tipo == "bool":
            b = self._boton(fila, "", f"op:{ruta}:alternar", lambda: self.cambiar(ctl, 1), ancho=8)
            b.pack(side="right", padx=6, pady=4)
            self.etiquetas_valor[ruta] = (b, ctl)
        elif tipo == "opc":
            self._boton(fila, "▶", f"op:{ruta}:mas", lambda: self.cambiar(ctl, +1), ancho=3).pack(side="right",
                                                                                                padx=6, pady=4)
            v = tk.Label(fila, text="", bg=T.fondo_2, fg=T.acento, font=self._f(16), width=20, wraplength=300)
            v.pack(side="right")
            self._boton(fila, "◀", f"op:{ruta}:menos", lambda: self.cambiar(ctl, -1), ancho=3).pack(side="right",
                                                                                                  padx=6, pady=4)
            self.etiquetas_valor[ruta] = (v, ctl)
        elif tipo in ("texto", "atajo"):
            var = tk.StringVar(value=str(leer(self.datos, ruta) or ""))
            e = tk.Entry(fila, textvariable=var, font=self._f(16, False), width=22, bg="#ffffff", fg="#000000",
                         insertbackground="#000000")
            e.pack(side="right", padx=8, pady=6)
            var.trace_add("write", lambda *_a, r=ruta, vv=var: self._texto_cambiado(r, vv))
            self.entradas[ruta] = var
        elif tipo == "boton" and ruta == "camara_ojos":
            # 1.1 paquete C: subir la cámara a 1280 × 720 (el iris se ve mejor)
            b = self._boton(fila, t("op_ojos_camara_si"), "op:camara_ojos", lambda e=None: self._camara_ojos())
            b.pack(side="right", padx=6, pady=4)
        elif tipo == "boton" and ruta == "probar_alarma":
            # 1.1: «Probar la alarma (3 segundos)»: suena 3 s con la pantalla roja y no cambia nada
            b = self._boton(fila, "▶", "op:probar_alarma", self._probar_alarma, ancho=4)
            b.pack(side="right", padx=6, pady=4)
        elif tipo == "boton":
            disponible = hasattr(self.app, "abrir_editor_frases")
            b = self._boton(fila, "✎", "op:frases", self._editar_frases, ancho=4)
            b.pack(side="right", padx=6, pady=4)
            if not disponible:
                b.configure(fg=T.texto_suave)
        self._pintar_valor(ruta)

    def _pintar_valor(self, ruta):
        par = self.etiquetas_valor.get(ruta)
        if par is None:
            return

        w, (tipo, _r, _c, extra, fmt) = par
        v = leer(self.datos, ruta)
        if tipo == "vel":
            texto = t("op_velocidad_valor", n=velocidad_de_sens(v))
        elif tipo == "bool":
            texto = t("op_si") if v else t("op_no")
            if isinstance(w, BotonGrande):
                w.poner_texto(texto)
                w.poner_color(self.tema.verde if v else None)
            return
        else:
            texto = fmt(v) if fmt else str(v)
        w.configure(text=texto)

    # ------------------------------------------------------------ cambios
    def cambiar(self, ctl, signo: int):
        tipo, ruta, _clave, extra, _fmt = ctl
        if tipo == "vel":
            n = velocidad_de_sens(leer(self.datos, "puntero.sens_x")) + signo
            self._poner_velocidad(n)
        elif tipo == "num":
            escribir(self.datos, ruta, paso_numero(self.datos, ruta, extra, signo))
            if ruta == "puntero.ajuste_vertical":
                # la vertical se recalcula con la velocidad de ahora (la calibración no cambia)
                self._poner_velocidad(velocidad_de_sens(leer(self.datos, "puntero.sens_x")))
        elif tipo == "bool":
            escribir(self.datos, ruta, not bool(leer(self.datos, ruta)))
            if ruta == "emergencia.activa" and not leer(self.datos, ruta):
                self.app.mostrar_aviso(t("aviso_emergencia_apagada"), 10)
        elif tipo == "opc":
            escribir(self.datos, ruta, ciclar(extra, leer(self.datos, ruta), signo))
        self._vista_previa()
        if ruta == "puntero.fuente":
            # 1.1 paquete C: aparecen o desaparecen las filas de los ojos (y la sugerencia de la cámara)
            self._armar_cuerpo()
            return
        self._pintar_valor(ruta)

    def _camara_ojos(self):
        """Sube la cámara a 1280 × 720 (se prueba al instante; «Cancelar» la devuelve)."""
        self.datos["camara"]["ancho"], self.datos["camara"]["alto"] = CAMARA_OJOS
        self._vista_previa()
        self.app.mostrar_aviso(t("op_ojos_camara_hecho"), 8)
        self._armar_cuerpo()

    def _poner_velocidad(self, n: int):
        """La velocidad escribe los tres valores juntos: sens_x, sens_y y joystick_g."""
        p = self.datos["puntero"]
        sx, sy, jg = sens_de_velocidad(n, p.get("ajuste_vertical", AJUSTE_VERTICAL_FABRICA))
        p["sens_x"], p["sens_y"], p["joystick_g"] = sx, sy, jg

    def _texto_cambiado(self, ruta, var):
        valor = var.get()
        if ruta.startswith("atajos."):
            escribir(self.datos, ruta, valor.strip())
        else:
            from ..config import LARGO_TEXTO
            escribir(self.datos, ruta, valor.strip()[:LARGO_TEXTO.get(ruta, 40)])

    def _vista_previa(self):
        """Los cambios llegan al motor al instante (sin guardar)."""
        problemas: list = []
        validos = validar(copy.deepcopy(self.datos), problemas=problemas)
        # la validación puede corregir (p. ej. encender la permanencia si no queda cómo reanudar)
        for ruta in ("permanencia.activa",):
            if leer(validos, ruta) != leer(self.datos, ruta):
                escribir(self.datos, ruta, leer(validos, ruta))
                self._pintar_valor(ruta)
        self.app.orden("config", validos)

    def ir_a(self, pestana: str):
        self.pestana = pestana
        self.pagina = 0
        self._armar()

    def ir_pagina(self, signo: int):
        self.pagina = max(self.pagina + signo, 0)
        self._armar_cuerpo()

    def elegir_gesto(self, g: str):
        self.gesto = g
        self.pagina = 0
        self._armar_cuerpo()

    def _probar_alarma(self):
        f = getattr(self.app, "probar_alarma", None)
        if f is not None:
            # con el volumen que se está eligiendo (aunque todavía no se haya guardado)
            f(int(leer(self.datos, "emergencia.volumen") or 100))

    def _editar_frases(self):
        f = getattr(self.app, "abrir_editor_frases", None)
        if f is not None:
            f()
        else:
            self.app.mostrar_aviso(t("aviso_teclado_no_disponible"))

    def pedir_fabrica(self):
        self.confirmando = True
        self._armar()

    def fabrica_no(self):
        self.confirmando = False
        self._armar()

    def fabrica_si(self):
        nuevo = por_defecto()
        for clave in ("atajos", "ventana", "perfiles", "perfil_activo"):
            nuevo[clave] = copy.deepcopy(self.datos.get(clave, nuevo[clave]))
        nuevo["teclado"]["cuidador"] = self.datos.get("teclado", {}).get("cuidador", "alguien")
        nuevo["primera_vez"] = False
        self.datos = validar(nuevo)
        self.confirmando = False
        self._vista_previa()
        self._armar()

    # ------------------------------------------------------------ en vivo
    def _en_vivo(self):
        if self.cerrada:
            return
        try:
            if self.c_nivel is not None and self.pestana == "gestos":
                v = getattr(self.app, "ultima_vista", None)
                nivel = None
                if v is not None:
                    nivel = v.maquina.gestos.nivel.get(self.gesto)
                c = self.c_nivel
                c.delete("all")
                try:
                    frac = min(max(float(nivel) / 1.5, 0.0), 1.0) if nivel is not None else 0.0
                except (TypeError, ValueError):
                    frac = 0.0
                if frac != frac:
                    frac = 0.0
                activo = v is not None and self.gesto in v.maquina.gestos.activos
                c.create_rectangle(0, 0, 260 * frac, 26, fill=self.tema.verde if activo else self.tema.acento,
                                   outline="")
                c.create_line(260 / 1.5, 0, 260 / 1.5, 26, fill=self.tema.texto, width=3)
            self._loop = self.win.after(100, self._en_vivo)
        except tk.TclError:
            pass

    # ------------------------------------------------------------ cerrar
    def _atajos_validos(self) -> str | None:
        return atajos_validos(self.datos.get("atajos", {}), bool(getattr(self.app, "sistema", False)))

    def guardar(self):
        error = self._atajos_validos()
        if error:
            self.app.mostrar_aviso(error, 10)
            self.pestana = "atajos"
            self._armar()
            return
        datos = validar(copy.deepcopy(self.datos))
        self.app.aplicar_config(datos, self.original)
        # siempre, haya cambiado o no: así la casilla y el registro de Windows quedan iguales
        self.app.poner_al_encender(bool(datos["arranque"].get("al_encender")))
        self.app.mostrar_aviso(t("op_guardado"), 4)
        self._cerrar()

    def cancelar(self):
        self.app.orden("config", copy.deepcopy(self.original))
        self.app.mostrar_aviso(t("op_cancelado"), 4)
        self._cerrar()

    def _cerrar(self):
        self.cerrada = True
        try:
            self.win.after_cancel(self._loop)
        except (tk.TclError, ValueError):
            pass
        try:
            self.win.destroy()
        except tk.TclError:
            pass
        f = getattr(self.app, "opciones_cerradas", None)
        if f is not None:
            f(self)
