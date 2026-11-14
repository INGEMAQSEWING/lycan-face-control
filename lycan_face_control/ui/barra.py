"""Barra de acciones flotante (sección 6.2): Clic, Doble, Derecho, Arrastrar, Desplazar, Teclado,
Pausa y (versión 1.1) Sin clic, Lupa y Minimizar, con ícono y texto grandes. Siempre encima y sin
robar el foco.

Se elige con la cabeza: cada botón es un objetivo (``barra:<id>``) que la máquina de estados
atiende por permanencia o con un gesto de clic; **nunca** se hace clic en lo que está detrás.
El botón del modo de clic elegido se ve resaltado. En pausa, "Pausa" se vuelve "Reanudar"; en
el modo Desplazar aparece "Terminar" (y no se puede minimizar: "Terminar" tiene que verse).

1.1 paquete A:
- Si los botones no caben en una columna (o fila) sin bajar de 72 px, se arman en dos, de arriba
  abajo y luego al lado (``medidas_barra`` devuelve también cuántas columnas).
- «Minimizar» esconde la barra y deja la pestaña «Barra» en el mismo borde; quedarse quieto
  0,6 s sobre la pestaña (``ui:barra_mostrar``, también en pausa) o el ratón del cuidador la
  vuelven a abrir. Lo minimizado no se guarda: al abrir el programa manda ``barra.visible``.
- Con el teclado abierto la barra no muestra «Sin clic» ni «Lupa» (cabe en una columna y el
  teclado conserva su ancho; ver docs/decisiones.md).
"""
from __future__ import annotations

import math
import tkinter as tk
import tkinter.font as tkfont

from .. import constantes as K
from .comun import LETRA, MIN_PT_BARRA, BotonGrande, area_de_trabajo, escala, no_activar, tema
from .textos import t

SEPARACION = 12
MARGEN_BORDE = 8
PT_TEXTO = MIN_PT_BARRA
PT_MAX_BARRA = 28           # con letra al 200 % la barra no cabría en la pantalla
ALTO_MIN = 72
MAX_COLUMNAS = 3
# pestaña de la barra minimizada (1.1)
ID_MOSTRAR = "ui:barra_mostrar"
PESTANA_TIEMPO_S = 0.6      # abrir la barra no tiene riesgo: basta poco tiempo quieto
PESTANA_CORTO, PESTANA_LARGO = 56, 120
PT_PESTANA = 18
SIN_TECLADO = ("sin_clic", "lupa")    # botones que no se muestran con el teclado abierto


def _cabe(n: int, tam: int, sep: int, largo: int) -> bool:
    return n * tam + (n - 1) * sep <= largo


def medidas_barra(n: int, boton_px: int, area: tuple, vertical: bool, alto_natural: int, ancho_natural: int):
    """Tamaño de cada botón, separación y número de columnas para que ``n`` botones quepan en el
    área de trabajo.

    Devuelve (ancho, alto, separación, columnas); en la barra horizontal "columnas" son filas.
    Primero se intenta una columna: se achica hasta el tamaño natural del texto y, si aun así no
    cabe, se reduce la separación (a 4 px). Si para caber habría que bajar de 72 px (``ALTO_MIN``)
    —o, en la barra horizontal, cortar el texto—, se arman 2 columnas (y, en una pantalla muy
    chica, 3). Nunca se baja de 72 px mientras haya otra opción."""
    l, a, d, ab = area
    largo = (ab - a) if vertical else (d - l)
    largo -= 2 * MARGEN_BORDE
    n = max(int(n), 1)
    alto0 = max(boton_px, alto_natural)
    ancho0 = max(boton_px, ancho_natural)
    # lo mínimo para que el texto se lea entero (en la vertical lo da el alto: 72 px alcanzan)
    legible = ALTO_MIN if vertical else max(ALTO_MIN, ancho_natural - 16)
    opciones = []
    for cols in range(1, MAX_COLUMNAS + 1):
        por_col = math.ceil(n / cols)
        sep = SEPARACION
        tam = alto0 if vertical else ancho0
        nat = alto_natural if vertical else ALTO_MIN
        if not _cabe(por_col, tam, sep, largo):
            tam = max(int((largo - (por_col - 1) * sep) / por_col), nat, ALTO_MIN)
        if not _cabe(por_col, tam, sep, largo):
            sep = 4
            tam = max(int((largo - (por_col - 1) * sep) / por_col), 1)
        opciones.append((tam, sep, cols, _cabe(por_col, tam, sep, largo)))
    elegida = (next((o for o in opciones if o[3] and o[0] >= legible), None)
               or next((o for o in opciones if o[3] and o[0] >= ALTO_MIN), None) or opciones[-1])
    tam, sep, cols, _ = elegida
    if vertical:
        return int(ancho0), int(tam), sep, cols
    return int(tam), int(alto0), sep, cols


class BarraAcciones:
    def __init__(self, root, app):
        self.root = root
        self.app = app
        self.win = None
        self.pestana = None
        # 1.1: minimizada en esta sesión (no se guarda); al abrir manda barra.visible
        self.minimizada = not bool(self.cfg["barra"].get("visible", True))
        self.con_teclado = False
        self._avisado_minimizar = False
        self.botones: dict = {}
        self.boton_pestana = None
        self._estado = None
        self._submodo = None
        self._modo = None
        self.medidas = (0, 0, 0, 1)
        self.construir()

    @property
    def cfg(self):
        return self.app.cfg.datos

    @property
    def expandida(self) -> bool:
        """Compatibilidad: la barra se ve (no está minimizada)."""
        return not self.minimizada

    # ------------------------------------------------------------ construcción
    def _ids(self, submodo: str | None = None) -> list:
        b = self.cfg["barra"]
        ids = [i for i, _ in K.BOTONES_BARRA]
        if not b.get("boton_sin_clic", True):
            ids.remove("sin_clic")
        if not b.get("boton_lupa", True):
            ids.remove("lupa")
        if self.con_teclado:
            ids = [i for i in ids if i not in SIN_TECLADO]
        if submodo == K.DESPLAZAR:
            ids.insert(ids.index("desplazar") + 1, "terminar")
            ids.remove("minimizar")          # "Terminar" tiene que quedar a la vista
        return ids

    def destruir(self):
        for w in (self.win, self.pestana):
            if w is not None:
                try:
                    w.destroy()
                except tk.TclError:
                    pass
        self.win = self.pestana = None
        self.botones = {}
        self.boton_pestana = None

    def construir(self, submodo: str | None = None):
        self.destruir()
        cfg = self.cfg
        T = self.tema = tema(cfg)
        reg = self.app.registro
        pos = cfg["barra"].get("posicion", "derecha")
        vertical = pos in ("derecha", "izquierda")
        esc = min(escala(cfg), PT_MAX_BARRA / PT_TEXTO)
        f_texto = (LETRA, max(int(round(PT_TEXTO * esc)), MIN_PT_BARRA), "bold")
        ids = self._ids(submodo)
        textos = {i: self._texto(i) for i in ids}
        ft = tkfont.Font(root=self.root, font=f_texto)
        ancho_nat = max(max(ft.measure(tx), ft.measure(ic)) for tx, ic in textos.values()) + 28
        alto_nat = 2 * ft.metrics("linespace") + 20      # ícono y texto, una línea cada uno
        area = area_de_trabajo(self.root)
        ancho, alto, sep, cols = medidas_barra(len(ids), int(cfg["barra"].get("boton_px", 96)), area, vertical,
                                               alto_nat, ancho_nat)
        self.medidas = (ancho, alto, sep, cols)
        por_col = math.ceil(len(ids) / cols)
        w = self.win = tk.Toplevel(self.root)
        w.overrideredirect(True)
        w.attributes("-topmost", True)
        w.configure(bg=T.fondo)
        for n, ident in enumerate(ids):
            marco = tk.Frame(w, width=ancho, height=alto, bg=T.fondo)
            marco.pack_propagate(False)
            if vertical:
                # de arriba abajo y luego a la columna de al lado
                fila, col = n % por_col, n // por_col
            else:
                fila, col = n // por_col, n % por_col
            marco.grid(row=fila, column=col, padx=(0 if col == 0 else sep, 0), pady=(0 if fila == 0 else sep, 0))
            texto, icono = textos[ident]
            oid = self._oid(ident)
            b = BotonGrande(marco, texto, self._comando(ident), T, f_texto, icono=icono)
            b.configure(font=f_texto)
            b.pack(fill="both", expand=True)
            interno = (oid.startswith("barra:") and ident != "minimizar") or oid == K_TERMINAR
            reg.agregar(oid, b, self._accion(ident), interno=interno)
            self.botones[ident] = b
        w.update_idletasks()
        W, H = w.winfo_reqwidth(), w.winfo_reqheight()
        l, a, d, ab = area
        if pos == "derecha":
            x, y = d - W - MARGEN_BORDE, a + max((ab - a - H) // 2, 0)
        elif pos == "izquierda":
            x, y = l + MARGEN_BORDE, a + max((ab - a - H) // 2, 0)
        elif pos == "arriba":
            x, y = l + max((d - l - W) // 2, 0), a + MARGEN_BORDE + 6
        else:
            x, y = l + max((d - l - W) // 2, 0), ab - H - MARGEN_BORDE
        w.geometry(f"+{x}+{y}")
        reg.ventana("barra", w)
        self._construir_pestana(pos, area, T)
        self._submodo = submodo
        self._estado = self._modo = None
        self._aplicar_visibilidad()
        for win in (w, self.pestana):
            no_activar(win)

    def _construir_pestana(self, pos: str, area: tuple, T):
        """Pestaña «Barra» de la barra minimizada: al menos 56 × 120 px (120 × 56 en la barra
        horizontal), letra de 18 pt o más."""
        reg = self.app.registro
        l, a, d, ab = area
        vertical = pos in ("derecha", "izquierda")
        p = self.pestana = tk.Toplevel(self.root)
        p.overrideredirect(True)
        p.attributes("-topmost", True)
        p.configure(bg=T.fondo)
        bt = BotonGrande(p, t("barra_mostrar"), reg.comando(ID_MOSTRAR), T, (LETRA, PT_PESTANA, "bold"),
                         icono=t(f"icono_mostrar_{pos}"))
        bt.pack(fill="both", expand=True)
        reg.agregar(ID_MOSTRAR, bt, self.mostrar, tiempo_s=PESTANA_TIEMPO_S)
        self.boton_pestana = bt
        p.update_idletasks()
        if vertical:
            pw, ph = max(p.winfo_reqwidth(), PESTANA_CORTO), max(p.winfo_reqheight(), PESTANA_LARGO)
        else:
            pw, ph = max(p.winfo_reqwidth(), PESTANA_LARGO), max(p.winfo_reqheight(), PESTANA_CORTO)
        if pos == "derecha":
            px, py = d - pw, a + (ab - a - ph) // 2
        elif pos == "izquierda":
            px, py = l, a + (ab - a - ph) // 2
        elif pos == "arriba":
            px, py = l + (d - l - pw) // 2, a + 6
        else:
            px, py = l + (d - l - pw) // 2, ab - ph
        p.geometry(f"{pw}x{ph}+{px}+{py}")
        self.tam_pestana = (pw, ph)
        reg.ventana("barra_pestana", p)

    def _aplicar_visibilidad(self):
        try:
            if not self.minimizada:
                self.win.deiconify()
                self.pestana.withdraw()
            else:
                self.win.withdraw()
                self.pestana.deiconify()
        except (tk.TclError, AttributeError):
            pass

    @staticmethod
    def _oid(ident: str) -> str:
        if ident == "terminar":
            return K_TERMINAR
        return f"barra:{ident}"

    def _texto(self, ident: str):
        if ident == "pausa" and self._estado == K.PAUSA:
            return t("barra_reanudar"), t("icono_reanudar")
        return t(f"barra_{ident}"), t(f"icono_{ident}")

    def _accion(self, ident: str):
        if ident == "minimizar":
            return self.minimizar
        return None

    def _comando(self, ident: str):
        reg = self.app.registro
        oid = self._oid(ident)
        if ident == "teclado":
            def teclado():
                # en pausa la máquina no atiende la barra: el cuidador igual puede abrir el teclado
                if self._estado == K.PAUSA:
                    self.app.alternar_teclado()
                else:
                    reg.elegir(oid, "raton")
            return teclado
        return reg.comando(oid)

    # ------------------------------------------------------------ minimizar (1.1)
    def mostrar(self):
        """La pestaña «Barra»: vuelve a abrir la barra."""
        if not self.minimizada:
            return
        self.minimizada = False
        self._aplicar_visibilidad()

    def minimizar(self):
        """Esconde la barra en el borde (no en el modo Desplazar: "Terminar" tiene que verse)."""
        if self.minimizada or self._submodo == K.DESPLAZAR:
            return
        self.minimizada = True
        self._aplicar_visibilidad()
        if not self._avisado_minimizar:
            self._avisado_minimizar = True
            f = getattr(self.app, "mostrar_aviso", None)
            if f is not None:
                f(t("globo_minimizar"), 8)

    # nombres de la versión 1.0 (la pestaña de "Mostrar la barra" apagado)
    def mostrar_temporal(self):
        self.mostrar()

    def ocultar(self):
        self.minimizar()

    def poner_teclado(self, abierto: bool):
        """El teclado se abre o se cierra: con el teclado abierto la barra no muestra «Sin clic»
        ni «Lupa» y se rehace antes de que el teclado mida el espacio libre."""
        abierto = bool(abierto)
        if abierto == self.con_teclado:
            return
        self.con_teclado = abierto
        self.construir(self._submodo)
        try:
            self.root.update_idletasks()
        except tk.TclError:
            pass

    # ------------------------------------------------------------ pintar
    def actualizar(self, vista):
        if vista is None or self.win is None:
            return
        m = vista.maquina
        sub = m.submodo if m.estado == K.ACTIVO else K.NORMAL
        quiere_terminar = sub == K.DESPLAZAR
        tiene_terminar = "terminar" in self.botones
        if quiere_terminar != tiene_terminar:
            self.construir(K.DESPLAZAR if quiere_terminar else None)
        if quiere_terminar and self.minimizada:
            self.mostrar()                   # Desplazar: "Terminar" siempre a la vista
        if m.estado != self._estado:
            self._estado = m.estado
            b = self.botones.get("pausa")
            if b is not None:
                texto, icono = self._texto("pausa")
                b.poner_texto(texto, icono)
                b.poner_color(self.tema.verde if m.estado == K.PAUSA else None)
        clave = (m.modo_clic, sub)
        if clave != self._modo:
            self._modo = clave
            activo = {"doble": "doble", "der": "derecho", "arrastrar": "arrastrar",
                      "ninguno": "sin_clic", "lupa": "lupa"}.get(m.modo_clic)
            if sub in (K.ARRASTRE_INICIO, K.ARRASTRANDO):
                activo = "arrastrar"
            if sub == K.DESPLAZAR:
                activo = "desplazar"
            if sub == K.LUPA:
                activo = "lupa"
            if sub in (K.TECLADO, K.BARRIDO, K.SOLO_COMUNICACION):
                activo = activo or "teclado"
            for ident, b in self.botones.items():
                b.activo(ident == activo)


K_TERMINAR = "desplazar:terminar"
