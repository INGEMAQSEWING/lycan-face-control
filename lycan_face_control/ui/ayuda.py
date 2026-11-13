"""Ayuda (sección 6.7): chuleta de gestos con dibujos de la cara y la acción que tienen ahora;
cómo se usa; sección para el cuidador; "Qué hacer si…" (con la nota honesta sobre los límites);
Acerca de (versión, licencia MIT y atribución de la lista de palabras).

Todo se recorre con botones grandes (sin desplazar con la cabeza). Ronda 3 de arreglos: cada
sección se parte en **páginas** que caben en la ventana (con «Anterior / Siguiente», elegibles con
la cabeza): con una pantalla pequeña o con la letra grande ya no se corta el texto por abajo.
"""
from __future__ import annotations

import tkinter as tk

from ..version import VERSION
from .comun import BotonGrande, area_libre, dibujar_cara, letra, no_activar, tema
from .textos import atajos_kw, barra_uso, nombre_accion, pausa_uso, t

SECCIONES = ("gestos", "uso", "cuidador", "problemas", "acerca")
MIN_PT_AYUDA = 11            # si un solo párrafo no cabe ni en una página, se achica hasta aquí


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
        self.pagina = 0
        self.paginas = 1
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
        tabs = self._tabs = tk.Frame(w, bg=T.fondo)
        tabs.pack(fill="x", padx=10, pady=(10, 4))
        self.tabs = {}
        for s in SECCIONES:
            b = BotonGrande(tabs, t(f"ayuda_sec_{s}"), app.registro.comando(f"ayuda:{s}"), T, letra(cfg, 16, True))
            b.pack(side="left", expand=True, fill="x", padx=3)
            app.registro.agregar(f"ayuda:{s}", b, lambda s=s: self.ir_a(s))
            self.tabs[s] = b
        abajo = self._abajo = tk.Frame(w, bg=T.fondo)
        abajo.pack(side="bottom", fill="x", padx=10, pady=10)
        b = BotonGrande(abajo, t("btn_cerrar"), app.registro.comando("ayuda:cerrar"), T, letra(cfg, 18, True))
        b.pack(fill="x")
        app.registro.agregar("ayuda:cerrar", b, self.cerrar)
        self.cuerpo = tk.Frame(w, bg=T.fondo)
        self.cuerpo.pack(fill="both", expand=True, padx=16, pady=8)
        self.ir_a(seccion)
        no_activar(w)

    # ------------------------------------------------------------ páginas
    def _alto_disponible(self) -> int:
        """Alto del cuerpo (la ventana menos las pestañas, «Cerrar» y los márgenes)."""
        try:
            self.win.update_idletasks()
            h = self.H - self._tabs.winfo_reqheight() - self._abajo.winfo_reqheight() - (10 + 4) - 20 - 16
            real = self.cuerpo.winfo_height()
            if real > 50:
                h = min(h, real)            # ya está en pantalla: se usa el alto de verdad
        except tk.TclError:
            h = self.H - 200
        return max(int(h) - 4, 80)

    def _medir(self, texto: str, fuente) -> int:
        lbl = tk.Label(self.cuerpo, text=texto, font=fuente, wraplength=self.W - 60, justify="left")
        try:
            lbl.update_idletasks()
            return lbl.winfo_reqheight()
        finally:
            lbl.destroy()

    def _alto_nav(self) -> int:
        cfg = self.app.cfg.datos
        b = BotonGrande(self.cuerpo, "Siguiente", None, self.tema, letra(cfg, 16, True))
        try:
            b.update_idletasks()
            return b.winfo_reqheight() + 6
        finally:
            b.destroy()

    def paginas_de(self, texto: str, disponible: int, fuente) -> list[tuple[str, object]]:
        """Parte el texto (por párrafos) en páginas que caben en ``disponible`` px. Un párrafo que
        no cabe solo en una página va con la letra más chica que haga falta (no menos de 11)."""
        parrafos = [p for p in texto.split("\n")]
        if self._medir(texto, fuente) <= disponible:
            return [(texto, fuente)]
        disponible -= self._alto_nav()
        paginas, actual = [], []
        for p in parrafos:
            prueba = "\n".join(actual + [p])
            if not actual or self._medir(prueba, fuente) <= disponible:
                actual.append(p)
                if len(actual) == 1 and self._medir(p, fuente) > disponible:
                    paginas.append(("\n".join(actual), self._fuente_que_cabe(p, disponible, fuente)))
                    actual = []
                continue
            paginas.append(("\n".join(actual), fuente))
            actual = [p]
            if self._medir(p, fuente) > disponible:
                paginas.append((p, self._fuente_que_cabe(p, disponible, fuente)))
                actual = []
        if actual:
            paginas.append(("\n".join(actual), fuente))
        # sin páginas vacías (párrafos en blanco al principio)
        return [pg for pg in paginas if pg[0].strip()] or [(texto, fuente)]

    def _fuente_que_cabe(self, texto: str, disponible: int, fuente):
        familia, pt = fuente[0], int(fuente[1])
        estilo = fuente[2:] if len(fuente) > 2 else ()
        while pt > MIN_PT_AYUDA:
            pt -= 1
            f = (familia, pt) + tuple(estilo)
            if self._medir(texto, f) <= disponible:
                return f
        return (familia, MIN_PT_AYUDA) + tuple(estilo)

    def _nav(self, contenedor):
        if self.paginas <= 1:
            return
        T = self.tema
        cfg = self.app.cfg.datos
        reg = self.app.registro
        nav = tk.Frame(contenedor, bg=T.fondo)
        nav.pack(side="bottom", fill="x", pady=(6, 0))
        if self.pagina > 0:
            b = BotonGrande(nav, "◀ " + t("btn_anterior"), reg.comando("ayuda:pagina:anterior"), T,
                            letra(cfg, 16, True))
            b.pack(side="left", padx=4)
            reg.agregar("ayuda:pagina:anterior", b, lambda: self.ir_pagina(-1))
        tk.Label(nav, text=f"{self.pagina + 1} / {self.paginas}", bg=T.fondo, fg=T.texto,
                 font=letra(cfg, 16)).pack(side="left", expand=True)
        if self.pagina < self.paginas - 1:
            b = BotonGrande(nav, t("btn_siguiente") + " ▶", reg.comando("ayuda:pagina:siguiente"), T,
                            letra(cfg, 16, True))
            b.pack(side="right", padx=4)
            reg.agregar("ayuda:pagina:siguiente", b, lambda: self.ir_pagina(1))

    def ir_pagina(self, signo: int):
        self.pagina = min(max(self.pagina + signo, 0), max(self.paginas - 1, 0))
        self._armar()

    def ir_a(self, seccion: str):
        self.seccion = seccion
        self.pagina = 0
        self._armar()

    def _armar(self):
        seccion = self.seccion
        for s, b in self.tabs.items():
            b.activo(s == seccion)
        for c in self.cuerpo.winfo_children():
            c.destroy()
        cfg = self.app.cfg.datos
        T = self.tema
        disponible = self._alto_disponible()
        if seccion == "gestos":
            self._armar_gestos(cfg, T, disponible)
            return
        # los atajos y la forma de pausar son los que de verdad están puestos (no los de fábrica)
        texto = t(f"ayuda_{seccion}", version=VERSION, pausa=pausa_uso(cfg), barra=barra_uso(cfg),
                  **atajos_kw(cfg))
        paginas = self.paginas_de(texto, disponible, letra(cfg, 16))
        self.paginas = len(paginas)
        self.pagina = min(self.pagina, self.paginas - 1)
        txt, fuente = paginas[self.pagina]
        self._nav(self.cuerpo)
        tk.Label(self.cuerpo, text=txt, bg=T.fondo, fg=T.texto, font=fuente, wraplength=self.W - 60,
                 justify="left", anchor="nw").pack(fill="both", expand=True)

    def _armar_gestos(self, cfg, T, disponible):
        """Los dibujos de los gestos: 4 por página si caben; si no (letra grande, pantalla chica),
        2 o 1 por página. La nota honesta va debajo si cabe; si no, en las páginas siguientes."""
        honesta = t("ayuda_honestidad")
        gestos = resumen_gestos(cfg)
        nav = self._alto_nav()
        por_pagina = 1
        ancho = self.W - 80
        intentos = [(n, None, True) for n in (4, 2)] + [(1, f, True) for f in (1.0, 0.75, 0.55, 0.4)]             + [(1, 0.4, False)]                  # al final, sin el título «Así está configurado ahora»
        intro = True
        for n, f, intro in intentos:
            ancho = int((self.W - 80) / n)
            lado = max(min(ancho, 200, int(disponible * 0.4)), 90)
            if f is not None:
                lado = max(int(lado * f), 50)
            for c in self.cuerpo.winfo_children():
                c.destroy()
            self._dibujos(cfg, T, lado, gestos[:n], ancho, intro)
            self.cuerpo.update_idletasks()
            alto = sum(c.winfo_reqheight() for c in self.cuerpo.winfo_children()) + 12
            por_pagina = n
            if alto <= disponible - (0 if n == len(gestos) else nav):
                break
        for c in self.cuerpo.winfo_children():
            c.destroy()
        grupos = [gestos[i:i + por_pagina] for i in range(0, len(gestos), por_pagina)]
        f_nota = letra(cfg, 16)
        # ¿la nota cabe debajo de la última página de dibujos?
        self._dibujos(cfg, T, lado, grupos[-1], ancho, intro)
        self.cuerpo.update_idletasks()
        alto_ultima = sum(c.winfo_reqheight() for c in self.cuerpo.winfo_children()) + 12
        for c in self.cuerpo.winfo_children():
            c.destroy()
        cabe_nota = alto_ultima + self._medir(honesta, f_nota) + 6 <= disponible - (nav if len(grupos) > 1 else 0)
        notas = [] if cabe_nota else self.paginas_de(honesta, disponible - nav, f_nota)
        self.paginas = len(grupos) + len(notas)
        self.pagina = min(self.pagina, self.paginas - 1)
        self._nav(self.cuerpo)
        if self.pagina < len(grupos):
            self._dibujos(cfg, T, lado, grupos[self.pagina], ancho, intro)
            if cabe_nota and self.pagina == len(grupos) - 1:
                tk.Label(self.cuerpo, text=honesta, bg=T.fondo, fg=T.texto_suave, font=f_nota,
                         wraplength=self.W - 60, justify="left", anchor="w").pack(fill="x", pady=(6, 0))
            return
        txt, fuente = notas[self.pagina - len(grupos)]
        tk.Label(self.cuerpo, text=txt, bg=T.fondo, fg=T.texto_suave, font=fuente, wraplength=self.W - 60,
                 justify="left", anchor="nw").pack(fill="both", expand=True)

    def _dibujos(self, cfg, T, lado, gestos, ancho=None, intro=True):
        envolver = max((ancho or lado) - 16, lado)
        if intro:
            tk.Label(self.cuerpo, text=t("ayuda_gestos_intro"), bg=T.fondo, fg=T.texto,
                     font=letra(cfg, 18, True), anchor="w").pack(fill="x")
        fila = tk.Frame(self.cuerpo, bg=T.fondo)
        fila.pack(fill="both", expand=True, pady=6)
        for dibujo, nombre, accion in gestos:
            col = tk.Frame(fila, bg=T.fondo_2)
            col.pack(side="left", expand=True, fill="both", padx=5)
            c = tk.Canvas(col, width=lado, height=lado, bg=T.fondo_2, highlightthickness=0)
            c.pack(pady=(8, 0))
            dibujar_cara(c, lado / 2, lado / 2, lado * 0.7, T.acento, dibujo)
            tk.Label(col, text=nombre, bg=T.fondo_2, fg=T.texto, font=letra(cfg, 16, True), wraplength=envolver,
                     justify="center").pack(pady=(4, 2))
            tk.Label(col, text=accion, bg=T.fondo_2, fg=T.acento, font=letra(cfg, 16), wraplength=envolver,
                     justify="center").pack(pady=(0, 8))
        return fila

    def cerrar(self):
        try:
            self.win.destroy()
        except tk.TclError:
            pass
        f = getattr(self.app, "ayuda_cerrada", None)
        if f is not None:
            f(self)
