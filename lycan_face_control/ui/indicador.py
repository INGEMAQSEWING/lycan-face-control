"""Indicadores que acompañan a la persona (secciones 6.1 y 6.3):

- ``IndicadorCursor``: junto al puntero, el anillo de permanencia (se llena mientras se queda
  quieto), la barra de cierre de ojos (al llenarse se pone verde: "Abra los ojos") y el modo de
  clic cuando no es el normal ("Doble", "Derecho", "Arrastrando"). Los clics lo atraviesan.
- ``BordeEstado``: tira de 6 px arriba de la pantalla con el color del estado (atravesable).
- ``ReanudarFlotante``: botón grande "Reanudar" que aparece en pausa cuando la ventana principal
  está escondida (siempre hay forma de reanudar con la cabeza).
"""
from __future__ import annotations

import tkinter as tk

from .. import constantes as K
from .comun import BotonGrande, LETRA, atravesable, letra, no_activar, tema
from .textos import t

TRANSPARENTE = "#010203"
LADO = 150                  # tamaño de la ventana del indicador (el anillo va en el centro)
ALTO_BORDE = 6


class IndicadorCursor:
    def __init__(self, root, app):
        self.root = root
        self.app = app
        self.activo = True
        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        try:
            self.win.attributes("-transparentcolor", TRANSPARENTE)
        except tk.TclError:
            pass
        self.win.configure(bg=TRANSPARENTE)
        self.canvas = tk.Canvas(self.win, width=LADO, height=LADO + 40, bg=TRANSPARENTE, highlightthickness=0)
        self.canvas.pack()
        self.win.withdraw()
        self._pos = None
        self._visible = False
        self._firma = None
        self._atravesable = False

    @property
    def cfg(self):
        return self.app.cfg.datos

    def _parpadeo_con_accion(self, m) -> bool:
        g = self.cfg["gestos"]["parpadeo"]
        if not g.get("activo", True):
            return False
        if m.submodo in (K.BARRIDO, K.SOLO_COMUNICACION):
            return True
        return g.get("fuera_barrido", "ninguna") != "ninguna"

    def _etiqueta(self, m) -> str:
        if m.estado == K.PAUSA:
            return t("ind_reanudar") if m.permanencia.visible else ""
        if m.submodo == K.ARRASTRANDO:
            return t("ind_arrastrando")
        if m.submodo == K.DESPLAZAR:
            return t("ind_desplazar")
        return {"doble": t("ind_doble"), "der": t("ind_der"), "arrastrar": t("ind_arrastrar"),
                # 1.1 paquete A
                "ninguno": t("ind_sin_clic"), "lupa": t("ind_lupa")}.get(m.modo_clic, "")

    def contenido(self, vista):
        """Qué dibujar (o None): (pos, progreso_anillo, barra_ojos, ojos_listos, etiqueta,
        progreso_gesto). Separado para probarlo sin pantalla."""
        if not self.activo or vista is None:
            return None
        m = vista.maquina
        if m.estado in (K.CALIBRANDO, K.SIN_CARA):
            return None
        pos = m.puntero if m.estado != K.PAUSA else m.puntero_virtual
        if pos is None:
            return None
        st = m.permanencia
        anillo = st.progreso if st.visible else None
        ojos = None
        listo = False
        if m.estado == K.ACTIVO and m.gestos.ojos_cerrados and self._parpadeo_con_accion(m):
            ojos = min(max(float(m.gestos.parpadeo_progreso), 0.0), 1.0)
            listo = bool(m.gestos.parpadeo_listo)
        gesto = None
        if m.gestos.progreso:
            activos = [v for k, v in m.gestos.progreso.items() if k in m.gestos.activos]
            if activos:
                gesto = min(max(activos), 1.0)
        etiqueta = self._etiqueta(m)
        if anillo is None and ojos is None and not etiqueta and gesto is None:
            return None
        if m.estado == K.PAUSA and anillo is None:
            return None
        return (tuple(int(v) for v in pos), anillo, ojos, listo, etiqueta, gesto)

    def actualizar(self, vista):
        c = self.contenido(vista)
        if c is None:
            if self._visible:
                self.win.withdraw()
                self._visible = False
            return
        pos, anillo, ojos, listo, etiqueta, gesto = c
        T = tema(self.cfg)
        firma = (None if anillo is None else round(anillo, 2), None if ojos is None else round(ojos, 2), listo,
                 etiqueta, None if gesto is None else round(gesto, 2))
        if firma != self._firma:
            self._firma = firma
            cv = self.canvas
            cv.delete("all")
            d = int(self.cfg["permanencia"].get("anillo_px", 48))
            x0 = (LADO - d) / 2
            if anillo is not None:
                cv.create_oval(x0, x0, x0 + d, x0 + d, outline="#5a6b8a", width=4)
                if anillo > 0:
                    cv.create_arc(x0, x0, x0 + d, x0 + d, start=90, extent=-359.9 * min(anillo, 1.0),
                                  style="arc", outline=T.acento, width=5)
            if gesto is not None:
                gi = x0 - 10
                cv.create_arc(gi, gi, LADO - gi, LADO - gi, start=90, extent=-359.9 * gesto, style="arc",
                              outline=T.ambar, width=4)
            y = x0 + d + 14
            if ojos is not None:
                ancho = 110
                bx = (LADO - ancho) / 2
                cv.create_rectangle(bx, y, bx + ancho, y + 14, outline=T.texto, width=2, fill="#1d2b44")
                cv.create_rectangle(bx + 2, y + 2, bx + 2 + (ancho - 4) * ojos, y + 12,
                                    fill=T.verde if listo else T.acento, outline="")
                y += 18
                if listo:
                    self._texto(cv, LADO / 2, y, t("ind_abra_ojos"), T.verde)
                    y += 26
            if etiqueta:
                self._texto(cv, LADO / 2, y, etiqueta, T.acento)
        x, yy = pos
        nueva = (x - LADO // 2, yy - LADO // 2)
        if nueva != self._pos:
            self._pos = nueva
            self.win.geometry(f"+{nueva[0]}+{nueva[1]}")
        if not self._visible:
            self.win.deiconify()
            self._visible = True
            if not self._atravesable:
                self._atravesable = atravesable(self.win)

    @staticmethod
    def _texto(cv, x, y, texto, color):
        # fondo oscuro detrás del texto para que se lea sobre cualquier programa
        tid = cv.create_text(x, y, text=texto, fill=color, font=(LETRA, 16, "bold"), anchor="n")
        x0, y0, x1, y1 = cv.bbox(tid)
        rid = cv.create_rectangle(x0 - 6, y0 - 2, x1 + 6, y1 + 2, fill="#0b1a36", outline="")
        cv.tag_lower(rid, tid)

    def destruir(self):
        try:
            self.win.destroy()
        except tk.TclError:
            pass


class BordeEstado:
    """Tira de color del estado en el borde superior de la pantalla (atravesable por clics)."""

    def __init__(self, root, app):
        self.root = root
        self.app = app
        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        ancho = root.winfo_screenwidth()
        self.win.geometry(f"{ancho}x{ALTO_BORDE}+0+0")
        self.win.configure(bg=K.AMBAR)
        self._color = None
        self._visible = True
        self._atravesable = False
        self.win.withdraw()

    def actualizar(self, estado: str | None, mostrar: bool):
        if not mostrar or estado is None:
            if self._visible:
                self.win.withdraw()
                self._visible = False
            return
        color = K.COLORES_ESTADO.get(estado, K.ACENTO)
        if color != self._color:
            self._color = color
            self.win.configure(bg=color)
        if not self._visible:
            self.win.deiconify()
            self._visible = True
            if not self._atravesable:
                self._atravesable = atravesable(self.win)

    def destruir(self):
        try:
            self.win.destroy()
        except tk.TclError:
            pass


class ReanudarFlotante:
    """Botón "Reanudar" grande arriba al centro, solo en pausa y con la ventana principal escondida."""

    def __init__(self, root, app):
        self.root = root
        self.app = app
        T = tema(app.cfg.datos)
        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.configure(bg=T.fondo)
        self.boton = BotonGrande(self.win, t("btn_reanudar"), app.registro.comando("reanudar"), T,
                                 letra(app.cfg.datos, 22, True, minimo=20), icono="▶", color=T.verde)
        self.boton.pack(padx=6, pady=6, ipadx=30, ipady=10)
        app.registro.agregar("reanudar", self.boton, None, interno=True)
        app.registro.ventana("reanudar", self.win)
        self.win.update_idletasks()
        w = self.win.winfo_reqwidth()
        self.win.geometry(f"+{(root.winfo_screenwidth() - w) // 2}+{ALTO_BORDE + 20}")
        self._visible = True
        self._no_activar = False
        self.win.withdraw()
        self._visible = False

    def actualizar(self, mostrar: bool):
        if mostrar and not self._visible:
            self.win.deiconify()
            self._visible = True
            if not self._no_activar:
                self._no_activar = no_activar(self.win) is not None
        elif not mostrar and self._visible:
            self.win.withdraw()
            self._visible = False

    def destruir(self):
        try:
            self.win.destroy()
        except tk.TclError:
            pass
