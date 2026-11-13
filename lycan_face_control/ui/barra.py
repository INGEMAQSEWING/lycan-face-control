"""Barra de acciones flotante (sección 6.2): Clic, Doble, Derecho, Arrastrar, Desplazar, Teclado y
Pausa, con ícono y texto grandes. Siempre encima y sin robar el foco.

Se elige con la cabeza: cada botón es un objetivo (``barra:<id>``) que la máquina de estados
atiende por permanencia o con un gesto de clic; **nunca** se hace clic en lo que está detrás.
El botón del modo de clic elegido se ve resaltado. En pausa, "Pausa" se vuelve "Reanudar"; en
el modo Desplazar aparece "Terminar".

Si ``barra.visible`` está apagado queda una pestaña pequeña que al elegirla muestra la barra.
"""
from __future__ import annotations

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


def medidas_barra(n: int, boton_px: int, area: tuple, vertical: bool, alto_natural: int, ancho_natural: int):
    """Tamaño de cada botón y separación para que ``n`` botones quepan en el área de trabajo.

    Devuelve (ancho, alto, separación). Se achica hasta el tamaño natural del texto; si aun así
    no cabe, se reduce la separación (a 4 px)."""
    l, a, d, ab = area
    largo = (ab - a) if vertical else (d - l)
    largo -= 2 * MARGEN_BORDE
    sep = SEPARACION
    if vertical:
        alto = max(boton_px, alto_natural)
        ancho = max(boton_px, ancho_natural)
        if n * alto + (n - 1) * sep > largo:
            alto = max(int((largo - (n - 1) * sep) / n), alto_natural, ALTO_MIN)
        if n * alto + (n - 1) * sep > largo:
            sep = 4
            alto = max(int((largo - (n - 1) * sep) / n), 1)
    else:
        alto = max(boton_px, alto_natural)
        ancho = max(boton_px, ancho_natural)
        if n * ancho + (n - 1) * sep > largo:
            ancho = max(int((largo - (n - 1) * sep) / n), ALTO_MIN)
        if n * ancho + (n - 1) * sep > largo:
            sep = 4
            ancho = max(int((largo - (n - 1) * sep) / n), 1)
    return int(ancho), int(alto), sep


class BarraAcciones:
    def __init__(self, root, app):
        self.root = root
        self.app = app
        self.win = None
        self.pestana = None
        self.expandida = False
        self.botones: dict = {}
        self._estado = None
        self._submodo = None
        self._modo = None
        self.construir()

    @property
    def cfg(self):
        return self.app.cfg.datos

    # ------------------------------------------------------------ construcción
    def _ids(self, submodo: str | None = None) -> list:
        ids = [b for b, _ in K.BOTONES_BARRA]
        if submodo == K.DESPLAZAR:
            ids.insert(ids.index("desplazar") + 1, "terminar")
        if not self.cfg["barra"].get("visible", True):
            ids.append("ocultar")
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
        ancho, alto, sep = medidas_barra(len(ids), int(cfg["barra"].get("boton_px", 96)), area, vertical,
                                         alto_nat, ancho_nat)
        self.medidas = (ancho, alto, sep)
        w = self.win = tk.Toplevel(self.root)
        w.overrideredirect(True)
        w.attributes("-topmost", True)
        w.configure(bg=T.fondo)
        for n, ident in enumerate(ids):
            marco = tk.Frame(w, width=ancho, height=alto, bg=T.fondo)
            marco.pack_propagate(False)
            if vertical:
                marco.pack(side="top", pady=(0 if n == 0 else sep, 0))
            else:
                marco.pack(side="left", padx=(0 if n == 0 else sep, 0))
            texto, icono = textos[ident]
            oid = self._oid(ident)
            b = BotonGrande(marco, texto, self._comando(ident), T, f_texto, icono=icono)
            b.configure(font=f_texto)
            b.pack(fill="both", expand=True)
            reg.agregar(oid, b, self._accion(ident), interno=oid.startswith("barra:") or oid == K_TERMINAR)
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
        # pestaña para mostrar la barra oculta
        p = self.pestana = tk.Toplevel(self.root)
        p.overrideredirect(True)
        p.attributes("-topmost", True)
        p.configure(bg=T.fondo)
        bt = BotonGrande(p, t("barra_mostrar"), reg.comando("ui:barra_mostrar"), T, (LETRA, 16, "bold"))
        bt.pack(fill="both", expand=True)
        reg.agregar("ui:barra_mostrar", bt, self.mostrar_temporal)
        p.update_idletasks()
        pw, ph = max(p.winfo_reqwidth(), 24), max(p.winfo_reqheight(), 64)
        if pos == "derecha":
            px, py = d - pw, a + (ab - a - ph) // 2
        elif pos == "izquierda":
            px, py = l, a + (ab - a - ph) // 2
        elif pos == "arriba":
            px, py = l + (d - l - pw) // 2, a + 6
        else:
            px, py = l + (d - l - pw) // 2, ab - ph
        p.geometry(f"{pw}x{ph}+{px}+{py}")
        reg.ventana("barra_pestana", p)
        self._submodo = submodo
        self._estado = self._modo = None
        self._aplicar_visibilidad()
        for win in (w, p):
            no_activar(win)

    def _aplicar_visibilidad(self):
        visible = self.cfg["barra"].get("visible", True) or self.expandida
        try:
            if visible:
                self.win.deiconify()
                self.pestana.withdraw()
            else:
                self.win.withdraw()
                self.pestana.deiconify()
        except tk.TclError:
            pass

    @staticmethod
    def _oid(ident: str) -> str:
        if ident == "terminar":
            return K_TERMINAR
        if ident == "ocultar":
            return "ui:barra_ocultar"
        return f"barra:{ident}"

    def _texto(self, ident: str):
        if ident == "pausa" and self._estado == K.PAUSA:
            return t("barra_reanudar"), t("icono_reanudar")
        return t(f"barra_{ident}"), t(f"icono_{ident}")

    def _accion(self, ident: str):
        if ident == "ocultar":
            return self.ocultar
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

    def mostrar_temporal(self):
        self.expandida = True
        self._aplicar_visibilidad()

    def ocultar(self):
        self.expandida = False
        self._aplicar_visibilidad()

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
            activo = {"doble": "doble", "der": "derecho", "arrastrar": "arrastrar"}.get(m.modo_clic)
            if sub in (K.ARRASTRE_INICIO, K.ARRASTRANDO):
                activo = "arrastrar"
            if sub == K.DESPLAZAR:
                activo = "desplazar"
            if sub in (K.TECLADO, K.BARRIDO, K.SOLO_COMUNICACION):
                activo = activo or "teclado"
            for ident, b in self.botones.items():
                b.activo(ident == activo)


K_TERMINAR = "desplazar:terminar"
