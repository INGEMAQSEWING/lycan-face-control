"""Ventana de la lupa (versión 1.1, paquete A): la parte de la pantalla alrededor del punto,
agrandada, para hacer un clic preciso con la cabeza (como el "Adjust Target" de TD Control).

- La zona se captura con Pillow (``ImageGrab``) **antes** de mostrar la ventana, para no
  fotografiarse a sí misma. La imagen solo vive en memoria y **nunca se guarda en disco**.
- La ventana va donde dijo la máquina (``lupa.ubicar_ventana``): nunca tapa la zona. Es un
  ``Toplevel`` siempre encima y sin foco, con el texto de instrucciones arriba, la imagen con una
  mira en el centro y el botón «Cerrar lupa» debajo.
- La imagen es el objetivo ``lupa:zona`` (lo atiende la máquina: quedarse quieto encima hace el
  clic en el punto real); «Cerrar lupa» es ``lupa:cerrar``.
"""
from __future__ import annotations

import logging
import tkinter as tk

from .. import lupa as L
from .comun import LETRA, BotonGrande, no_activar, tema
from .textos import t

log = logging.getLogger("lycan")

MARCO_PX = 8


def capturar(zona):
    """Imagen (Pillow) de la zona de la pantalla, en píxeles físicos (todos los monitores)."""
    from PIL import ImageGrab
    l, a, d, ab = zona
    try:
        return ImageGrab.grab(bbox=(l, a, d, ab), all_screens=True)
    except TypeError:            # Pillow viejo sin all_screens
        return ImageGrab.grab(bbox=(l, a, d, ab))


class VentanaLupa:
    def __init__(self, root, app, zona, ventana, imagen, capturar_fn=None):
        """Lanza una excepción si la captura falla (la aplicación avisa y vuelve a NORMAL)."""
        self.root = root
        self.app = app
        self.zona = tuple(zona)
        self.ventana = tuple(ventana)
        self.imagen = tuple(imagen)
        self.cerrada = False
        self.visto = False                     # la máquina ya mostró el submodo LUPA
        self.win = None
        self._foto = None
        # 1. captura primero (la ventana todavía no existe)
        img = (capturar_fn or capturar)(self.zona)
        if img is None:
            raise RuntimeError("captura vacía")
        iw, ih = self.imagen[2] - self.imagen[0], self.imagen[3] - self.imagen[1]
        if iw <= 0 or ih <= 0:
            raise ValueError("imagen sin tamaño")
        from PIL import Image, ImageTk
        try:
            filtro = Image.Resampling.LANCZOS
        except AttributeError:          # pragma: no cover - Pillow viejo
            filtro = Image.LANCZOS
        grande = img.convert("RGB").resize((iw, ih), filtro)
        self._foto = ImageTk.PhotoImage(grande, master=root)
        del img, grande                  # solo queda la foto que se muestra (en memoria)
        # 2. la ventana
        cfg = app.cfg.datos
        T = self.tema = tema(cfg)
        reg = app.registro
        vl, va, vd, vab = self.ventana
        W, H = vd - vl, vab - va
        w = self.win = tk.Toplevel(root)
        w.overrideredirect(True)
        w.attributes("-topmost", True)
        w.configure(bg=T.fondo)
        w.title(t("lupa_titulo"))
        w.geometry(f"{W}x{H}+{vl}+{va}")
        arriba = self.imagen[1] - va
        tk.Label(w, text=t("lupa_instruccion"), bg=T.fondo, fg=T.texto, font=(LETRA, 16, "bold"),
                 wraplength=max(W - 16, 100), justify="center").place(x=0, y=0, width=W, height=arriba)
        c = self.canvas = tk.Canvas(w, width=iw, height=ih, bd=0, highlightthickness=0, bg="#000000",
                                    cursor="crosshair")
        c.place(x=self.imagen[0] - vl, y=arriba, width=iw, height=ih)
        c.create_image(0, 0, image=self._foto, anchor="nw")
        cx, cy = iw / 2.0, ih / 2.0
        for color, ancho in (("#000000", 5), (T.acento, 2)):
            c.create_line(cx - 26, cy, cx - 6, cy, fill=color, width=ancho)
            c.create_line(cx + 6, cy, cx + 26, cy, fill=color, width=ancho)
            c.create_line(cx, cy - 26, cx, cy - 6, fill=color, width=ancho)
            c.create_line(cx, cy + 6, cx, cy + 26, fill=color, width=ancho)
        c.create_rectangle(1, 1, iw - 1, ih - 1, outline=T.acento, width=2)
        reg.agregar(L.ID_ZONA, c, None, interno=True)
        abajo = tk.Frame(w, bg=T.fondo)
        y_abajo = self.imagen[3] - va
        abajo.place(x=0, y=y_abajo, width=W, height=max(H - y_abajo, 1))
        self.boton_cerrar = BotonGrande(abajo, t("lupa_cerrar"), reg.comando(L.ID_CERRAR), T,
                                        (LETRA, 20, "bold"), icono="✕")
        self.boton_cerrar.pack(fill="both", expand=True, padx=MARCO_PX, pady=MARCO_PX)
        reg.agregar(L.ID_CERRAR, self.boton_cerrar, self._cerrar_elegido)
        reg.ventana("lupa", w)
        no_activar(w)
        log.info("Lupa en pantalla (la imagen no se guarda)")

    def _cerrar_elegido(self):
        """«Cerrar lupa» (con la cabeza o con el ratón): se cierra sin clic."""
        f = getattr(self.app, "cerrar_lupa", None)
        if f is not None:
            f(avisar_motor=True)
        else:
            self.cerrar()

    def cerrar(self):
        if self.cerrada:
            return
        self.cerrada = True
        reg = self.app.registro
        reg.quitar("lupa:")
        reg.quitar_ventana("lupa")
        try:
            if self.win is not None:
                self.win.destroy()
        except tk.TclError:
            pass
        self.win = None
        self._foto = None                # la imagen se suelta de la memoria
