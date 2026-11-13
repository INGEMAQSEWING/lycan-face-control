"""Asistente de primera vez: explicación corta para la persona y el cuidador (qué es, cómo poner
la cámara, cómo se hace clic) y, al final, la calibración guiada.

Al terminarlo (o elegir «Más tarde») ``primera_vez`` queda en falso para no volver a mostrarlo;
la máquina igual recuerda calibrar mientras no haya calibración.
"""
from __future__ import annotations

import tkinter as tk

from .comun import BotonGrande, area_libre, dibujar_cara, letra, no_activar, tema
from .textos import t

PAGINAS = ("asis_1", "asis_2", "asis_3", "asis_4")


class Asistente:
    def __init__(self, root, app):
        self.root = root
        self.app = app
        self.i = 0
        self.cerrado = False
        cfg = app.cfg.datos
        T = self.tema = tema(cfg)
        w = self.win = tk.Toplevel(root)
        w.title(t("asis_titulo"))
        w.configure(bg=T.fondo)
        w.attributes("-topmost", True)
        w.protocol("WM_DELETE_WINDOW", self.mas_tarde)
        l, a, d, ab = area_libre(app, root)
        self.W = min(int((d - l) * 0.75), 960)
        self.H = min(int((ab - a) * 0.85), 640)
        w.geometry(f"{self.W}x{self.H}+{l + (d - l - self.W) // 2}+{a + (ab - a - self.H) // 2}")
        app.registro.ventana("asistente", w)
        self.cuerpo = tk.Frame(w, bg=T.fondo)
        self.cuerpo.pack(fill="both", expand=True, padx=20, pady=12)
        self.abajo = tk.Frame(w, bg=T.fondo)
        self.abajo.pack(side="bottom", fill="x", padx=14, pady=12)
        self.mostrar()
        no_activar(w)

    def _boton(self, texto, ident, accion, color=None):
        b = BotonGrande(self.abajo, texto, self.app.registro.comando(ident), self.tema,
                        letra(self.app.cfg.datos, 18, True), color=color)
        b.pack(side="left", expand=True, fill="x", padx=6)
        self.app.registro.agregar(ident, b, accion)
        return b

    def mostrar(self):
        cfg = self.app.cfg.datos
        T = self.tema
        for c in self.cuerpo.winfo_children():
            c.destroy()
        for c in self.abajo.winfo_children():
            c.destroy()
        clave = PAGINAS[self.i]
        tk.Label(self.cuerpo, text=t(f"{clave}_titulo"), bg=T.fondo, fg=T.acento, font=letra(cfg, 26, True),
                 wraplength=self.W - 60, justify="center").pack(pady=(4, 8))
        if self.i in (0, 3):
            c = tk.Canvas(self.cuerpo, width=200, height=200, bg=T.fondo, highlightthickness=0)
            c.pack()
            dibujar_cara(c, 100, 95, 160, T.acento, "sonrisa" if self.i == 0 else "reposo")
        tk.Label(self.cuerpo, text=t(clave), bg=T.fondo, fg=T.texto, font=letra(cfg, 18), wraplength=self.W - 80,
                 justify="left").pack(pady=6, fill="x")
        tk.Label(self.cuerpo, text=f"{self.i + 1} / {len(PAGINAS)}", bg=T.fondo, fg=T.texto_suave,
                 font=letra(cfg, 16)).pack(side="bottom")
        if self.i > 0:
            self._boton("◀ " + t("btn_anterior"), "asis:anterior", self.anterior)
        if self.i < len(PAGINAS) - 1:
            self._boton(t("btn_siguiente") + " ▶", "asis:siguiente", self.siguiente, color=T.verde)
        else:
            self._boton(t("asis_calibrar"), "asis:calibrar", self.calibrar, color=T.verde)
            self._boton(t("btn_mas_tarde"), "asis:mas_tarde", self.mas_tarde)

    def siguiente(self):
        if self.i < len(PAGINAS) - 1:
            self.i += 1
            self.mostrar()

    def anterior(self):
        if self.i > 0:
            self.i -= 1
            self.mostrar()

    def _terminar(self):
        if self.cerrado:
            return
        self.cerrado = True
        self.app.cfg.datos["primera_vez"] = False
        self.app.guardar_config()
        try:
            self.win.destroy()
        except tk.TclError:
            pass
        f = getattr(self.app, "asistente_cerrado", None)
        if f is not None:
            f(self)

    def calibrar(self):
        self._terminar()
        self.app.abrir_calibracion(empezar_ya=False)

    def mas_tarde(self):
        self._terminar()
