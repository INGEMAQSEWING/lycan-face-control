"""Ayuda (sección 6.7): chuleta de gestos con dibujos de la cara y la acción que tienen ahora;
cómo se usa; sección para el cuidador; "Qué hacer si…" (con la nota honesta sobre los límites);
Acerca de (versión, licencia MIT y atribución de la lista de palabras).

Todo se recorre con botones grandes (sin desplazar con la cabeza).
"""
from __future__ import annotations

import tkinter as tk

from ..version import VERSION
from .comun import BotonGrande, area_libre, dibujar_cara, letra, no_activar, tema
from .textos import nombre_accion, t

SECCIONES = ("gestos", "uso", "cuidador", "problemas", "acerca")


def resumen_gestos(cfg: dict) -> list[tuple[str, str, str]]:
    """(gesto para el dibujo, nombre, qué hace ahora) de cada gesto."""
    g = cfg["gestos"]
    out = []
    for nombre, dibujo in (("boca", "boca"), ("cejas", "cejas"), ("sonrisa", "sonrisa")):
        d = g[nombre]
        if not d.get("activo"):
            accion = t("ayuda_gesto_apagado")
        else:
            accion = nombre_accion(d["corto"])
            if d.get("largo", "ninguna") != "ninguna":
                accion += "\n" + t("ayuda_gesto_largo", accion=nombre_accion(d["largo"]))
        out.append((dibujo, t(f"ayuda_gesto_{nombre}"), accion))
    p = g["parpadeo"]
    if not p.get("activo"):
        accion = t("ayuda_gesto_apagado")
    else:
        accion = nombre_accion("elegir")
        fuera = p.get("fuera_barrido", "ninguna")
        if fuera != "ninguna":
            accion += "\n" + nombre_accion(fuera)
    out.append(("ojos", t("ayuda_gesto_parpadeo"), accion))
    return out


class VentanaAyuda:
    def __init__(self, root, app, seccion: str = "gestos"):
        self.root = root
        self.app = app
        self.seccion = seccion
        cfg = app.cfg.datos
        T = self.tema = tema(cfg)
        w = self.win = tk.Toplevel(root)
        w.title(t("ayuda_titulo"))
        w.configure(bg=T.fondo)
        w.attributes("-topmost", True)
        w.protocol("WM_DELETE_WINDOW", self.cerrar)
        l, a, d, ab = area_libre(app, root)
        self.W = min(int((d - l) * 0.82), 1000)
        self.H = min(int((ab - a) * 0.9), 700)
        w.geometry(f"{self.W}x{self.H}+{l + (d - l - self.W) // 2}+{a + (ab - a - self.H) // 2}")
        app.registro.ventana("ayuda", w)
        tabs = tk.Frame(w, bg=T.fondo)
        tabs.pack(fill="x", padx=10, pady=(10, 4))
        self.tabs = {}
        for s in SECCIONES:
            b = BotonGrande(tabs, t(f"ayuda_sec_{s}"), app.registro.comando(f"ayuda:{s}"), T, letra(cfg, 16, True))
            b.pack(side="left", expand=True, fill="x", padx=3)
            app.registro.agregar(f"ayuda:{s}", b, lambda s=s: self.ir_a(s))
            self.tabs[s] = b
        abajo = tk.Frame(w, bg=T.fondo)
        abajo.pack(side="bottom", fill="x", padx=10, pady=10)
        b = BotonGrande(abajo, t("btn_cerrar"), app.registro.comando("ayuda:cerrar"), T, letra(cfg, 18, True))
        b.pack(fill="x")
        app.registro.agregar("ayuda:cerrar", b, self.cerrar)
        self.cuerpo = tk.Frame(w, bg=T.fondo)
        self.cuerpo.pack(fill="both", expand=True, padx=16, pady=8)
        self.ir_a(seccion)
        no_activar(w)

    def ir_a(self, seccion: str):
        self.seccion = seccion
        for s, b in self.tabs.items():
            b.activo(s == seccion)
        for c in self.cuerpo.winfo_children():
            c.destroy()
        cfg = self.app.cfg.datos
        T = self.tema
        if seccion == "gestos":
            tk.Label(self.cuerpo, text=t("ayuda_gestos_intro"), bg=T.fondo, fg=T.texto, font=letra(cfg, 18, True),
                     anchor="w").pack(fill="x")
            fila = tk.Frame(self.cuerpo, bg=T.fondo)
            fila.pack(fill="both", expand=True, pady=6)
            lado = max(min(int((self.W - 80) / 4), 200), 120)
            for dibujo, nombre, accion in resumen_gestos(cfg):
                col = tk.Frame(fila, bg=T.fondo_2)
                col.pack(side="left", expand=True, fill="both", padx=5)
                c = tk.Canvas(col, width=lado, height=lado, bg=T.fondo_2, highlightthickness=0)
                c.pack(pady=(8, 0))
                dibujar_cara(c, lado / 2, lado / 2, lado * 0.7, T.acento, dibujo)
                tk.Label(col, text=nombre, bg=T.fondo_2, fg=T.texto, font=letra(cfg, 16, True), wraplength=lado,
                         justify="center").pack(pady=(4, 2))
                tk.Label(col, text=accion, bg=T.fondo_2, fg=T.acento, font=letra(cfg, 16), wraplength=lado,
                         justify="center").pack(pady=(0, 8))
            tk.Label(self.cuerpo, text=t("ayuda_honestidad"), bg=T.fondo, fg=T.texto_suave, font=letra(cfg, 16),
                     wraplength=self.W - 60, justify="left", anchor="w").pack(fill="x", pady=(6, 0))
            return
        texto = t(f"ayuda_{seccion}", version=VERSION)
        tk.Label(self.cuerpo, text=texto, bg=T.fondo, fg=T.texto, font=letra(cfg, 16), wraplength=self.W - 60,
                 justify="left", anchor="nw").pack(fill="both", expand=True)

    def cerrar(self):
        try:
            self.win.destroy()
        except tk.TclError:
            pass
        f = getattr(self.app, "ayuda_cerrada", None)
        if f is not None:
            f(self)
