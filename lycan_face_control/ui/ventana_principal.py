"""Ventana principal (sección 6.1): estado grande con color, ícono y texto; silueta de la cara
(sin video por defecto); barras en vivo de los gestos con su línea de umbral; botones grandes
elegibles con la cabeza; modo pequeño (tira con el estado y Reanudar).

Solo pinta lo que deja el motor (``actualizar(vista)``) y llama a la aplicación; nunca envía
eventos a Windows.
"""
from __future__ import annotations

import logging
import time
import tkinter as tk

from .. import constantes as K
from .comun import BotonGrande, Globo, area_de_trabajo, dibujar_puntos, letra, poner_icono, tema
from .textos import atajos_kw, icono_estado, subtitulo, t, texto_estado

log = logging.getLogger("lycan")

VISTA_W, VISTA_H = 220, 165
BARRA_W, BARRA_H = 190, 20
REFRESCO_VISTA_S = 1 / 15          # la silueta se repinta a 15 por segundo como máximo
GESTOS_BARRAS = ("boca", "cejas", "sonrisa", "parpadeo")


class VentanaPrincipal:
    def __init__(self, root: tk.Tk, app):
        self.root = root
        self.app = app
        self.mini = False
        self.confirmando_salir = False
        self._aviso_hasta = 0.0
        self._t_vista = 0.0
        self._estado = None
        self._id_pausa = "ui:pausar"
        self._foto = None
        self._arr = (0, 0)
        self._construir()
        self._posicionar()

    # ------------------------------------------------------------ construcción
    @property
    def cfg(self):
        return self.app.cfg.datos

    def _construir(self):
        r = self.root
        self.tema = T = tema(self.cfg)
        r.title(K.NOMBRE_APP)
        poner_icono(r)
        r.configure(bg=T.ambar)
        r.resizable(False, False)
        r.attributes("-topmost", True)
        self.marco = tk.Frame(r, bg=T.fondo)
        self.marco.pack(fill="both", expand=True, padx=5, pady=5)
        reg = self.app.registro

        # 1. estado grande
        self.cab = tk.Frame(self.marco, bg=T.fondo)
        self.cab.pack(fill="x", padx=8, pady=(6, 0))
        self.lbl_icono = tk.Label(self.cab, text=icono_estado(K.PAUSA), bg=T.fondo, fg=T.ambar,
                                  font=letra(self.cfg, 28, True))
        self.lbl_icono.pack(side="left")
        self.lbl_estado = tk.Label(self.cab, text=texto_estado(K.PAUSA), bg=T.fondo, fg=T.ambar,
                                   font=letra(self.cfg, 28, True), anchor="w")
        self.lbl_estado.pack(side="left", padx=(10, 0))
        for w in (self.cab, self.lbl_estado, self.lbl_icono):
            w.bind("<ButtonPress-1>", self._arrastre_ini)
            w.bind("<B1-Motion>", self._arrastre)
        self.lbl_sub = tk.Label(self.marco, text="", bg=T.fondo, fg=T.texto, font=letra(self.cfg, 16),
                                justify="left", anchor="w", wraplength=self._ancho_texto())
        self.lbl_sub.pack(fill="x", padx=8)
        self.lbl_ensayo = tk.Label(self.marco, text=t("modo_ensayo"), bg=T.fondo, fg=T.acento,
                                   font=letra(self.cfg, 16, True), anchor="w")
        if getattr(self.app, "simulada", False):
            self.lbl_ensayo.pack(fill="x", padx=8)

        # 2. vista de la cara + barras de gestos
        self.medio = tk.Frame(self.marco, bg=T.fondo)
        self.medio.pack(fill="x", padx=8, pady=6)
        self.lienzo = tk.Canvas(self.medio, width=VISTA_W, height=VISTA_H, bg=T.fondo_2, highlightthickness=2,
                                highlightbackground=T.texto_suave)
        self.lienzo.pack(side="left")
        self.gestos_marco = tk.Frame(self.medio, bg=T.fondo)
        self.gestos_marco.pack(side="left", fill="both", expand=True, padx=(12, 0))
        tk.Label(self.gestos_marco, text=t("titulo_gestos"), bg=T.fondo, fg=T.texto,
                 font=letra(self.cfg, 16, True), anchor="w").pack(fill="x")
        self.barras: dict = {}
        for g in GESTOS_BARRAS:
            fila = tk.Frame(self.gestos_marco, bg=T.fondo)
            lbl = tk.Label(fila, text=t(f"gesto_{g}"), bg=T.fondo, fg=T.texto, font=letra(self.cfg, 16),
                           width=8, anchor="w")
            lbl.pack(side="left")
            c = tk.Canvas(fila, width=BARRA_W, height=BARRA_H, bg=T.fondo_2, highlightthickness=1,
                          highlightbackground=T.texto_suave)
            c.pack(side="left", padx=(4, 0))
            self.barras[g] = (fila, c)
        self._mostrar_barras()

        # 3. avisos
        self.lbl_aviso = tk.Label(self.marco, text="", bg=T.aviso_fondo, fg=T.aviso_texto,
                                  font=letra(self.cfg, 16), wraplength=self._ancho_texto(), justify="left",
                                  anchor="w", padx=8, pady=4)

        # 4. botones
        self.botones = tk.Frame(self.marco, bg=T.fondo)
        self.botones.pack(fill="x", padx=4, pady=(2, 6))
        f = letra(self.cfg, 16, True)
        self.b_pausa = BotonGrande(self.botones, t("btn_pausar"), lambda: reg.elegir(self._id_pausa, "raton"),
                                   T, f, icono="❚❚", color=T.ambar)
        self.b_pausa.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=3, pady=3)
        reg.agregar("ui:pausar", self.b_pausa, self.app.pausar)
        Globo(self.b_pausa, t("globo_pausa", **atajos_kw(self.cfg)), cfg=self.cfg)
        defs = (
            ("ui:teclado", "btn_teclado", self.app.alternar_teclado, None, 0, 1),
            ("ui:recentrar", "btn_recentrar", self.app.recentrar, "globo_recentrar", 0, 2),
            ("ui:calibrar", "btn_calibrar", self.app.abrir_calibracion, "globo_calibrar", 0, 3),
            ("ui:opciones", "btn_opciones", self.app.abrir_opciones, None, 1, 1),
            ("ui:ayuda", "btn_ayuda", self.app.abrir_ayuda, None, 1, 2),
            ("ui:mini", "btn_mini", self.alternar_mini, "globo_mini", 1, 3),
            ("ui:salir", "btn_salir", self.pedir_salir, "globo_salir", 0, 4),
        )
        self.b = {}
        for ident, clave, accion, globo, fila, col in defs:
            b = BotonGrande(self.botones, t(clave), reg.comando(ident), T, f)
            b.grid(row=fila, column=col, rowspan=2 if ident == "ui:salir" else 1, sticky="nsew", padx=3, pady=3)
            reg.agregar(ident, b, accion)
            if globo:
                Globo(b, t(globo), cfg=self.cfg)
            self.b[ident] = b
        for c in range(5):
            self.botones.grid_columnconfigure(c, weight=1)

        # confirmación de salir (reemplaza los botones)
        self.confirmar = tk.Frame(self.marco, bg=T.fondo)
        tk.Label(self.confirmar, text=t("pregunta_salir"), bg=T.fondo, fg=T.texto, font=letra(self.cfg, 16, True),
                 wraplength=self._ancho_texto(), justify="left").pack(fill="x", padx=6, pady=(4, 6))
        fila = tk.Frame(self.confirmar, bg=T.fondo)
        fila.pack(fill="x")
        self.b_si_salir = BotonGrande(fila, t("btn_si_salir"), reg.comando("ui:salir_si"), T, f, color=T.rojo)
        self.b_si_salir.pack(side="left", expand=True, fill="x", padx=6, pady=4)
        reg.agregar("ui:salir_si", self.b_si_salir, self.app.salir_seguro)
        self.b_no_salir = BotonGrande(fila, t("btn_no"), reg.comando("ui:salir_no"), T, f)
        self.b_no_salir.pack(side="left", expand=True, fill="x", padx=6, pady=4)
        reg.agregar("ui:salir_no", self.b_no_salir, self.cancelar_salir)

        # modo pequeño
        self.tira = tk.Frame(r, bg=T.fondo)
        self.lbl_mini = tk.Label(self.tira, text="", bg=T.fondo, fg=T.ambar, font=letra(self.cfg, 18, True),
                                 anchor="w")
        self.lbl_mini.pack(side="left", padx=(8, 6))
        for w in (self.tira, self.lbl_mini):
            w.bind("<ButtonPress-1>", self._arrastre_ini)
            w.bind("<B1-Motion>", self._arrastre)
        self.b_grande = BotonGrande(self.tira, t("btn_grande"), reg.comando("ui:grande"), T, letra(self.cfg, 16, True))
        self.b_grande.pack(side="right", padx=4, pady=4)
        reg.agregar("ui:grande", self.b_grande, self.alternar_mini)
        self.b_pausa_mini = BotonGrande(self.tira, t("btn_pausar"), lambda: reg.elegir(self._id_pausa, "raton"),
                                        T, letra(self.cfg, 16, True), color=T.ambar)
        self.b_pausa_mini.pack(side="right", padx=4, pady=4)
        reg.agregar("ui:pausar", self.b_pausa_mini, self.app.pausar)

        self.root.protocol("WM_DELETE_WINDOW", self.pedir_salir)
        reg.ventana("principal", self.root)

    def _ancho_texto(self) -> int:
        return int(500 * min(max(float(self.cfg["comodidad"].get("escala_letra", 1.0)), 1.0), 2.0))

    def _mostrar_barras(self):
        g = self.cfg["gestos"]
        for nombre, (fila, _c) in self.barras.items():
            if g[nombre].get("activo"):
                fila.pack(fill="x", pady=2)
            else:
                fila.pack_forget()

    def _posicionar(self):
        r = self.root
        r.update_idletasks()
        v = self.cfg.get("ventana") or {}
        x, y = v.get("x"), v.get("y")
        sw, sh = r.winfo_screenwidth(), r.winfo_screenheight()
        if not isinstance(x, int) or not isinstance(y, int) or not (-20 <= x < sw - 80 and 0 <= y < sh - 80):
            l, _a, _d, abajo = area_de_trabajo(r)
            x = l + 16
            y = max(abajo - r.winfo_reqheight() - 140, 0)      # espacio para un aviso y el título
        r.geometry(f"+{x}+{y}")
        if v.get("mini") or getattr(self.app.args, "minimizado", False):
            self.alternar_mini()

    def posicion(self):
        return self.root.winfo_x(), self.root.winfo_y()

    # ------------------------------------------------------------ interacción
    def _arrastre_ini(self, e):
        self._arr = (e.x_root - self.root.winfo_x(), e.y_root - self.root.winfo_y())

    def _arrastre(self, e):
        self.root.geometry(f"+{e.x_root - self._arr[0]}+{e.y_root - self._arr[1]}")

    def alternar_mini(self):
        self.mini = not self.mini
        if self.mini:
            self.marco.pack_forget()
            self.tira.pack(fill="both", expand=True, padx=3, pady=3)
        else:
            self.tira.pack_forget()
            self.marco.pack(fill="both", expand=True, padx=5, pady=5)
        try:
            self.cfg["ventana"]["mini"] = self.mini
        except (KeyError, TypeError):
            pass
        self.root.update_idletasks()
        self._dentro_de_pantalla()

    def _dentro_de_pantalla(self):
        """Al crecer, la ventana no puede quedar bajo la barra de tareas."""
        try:
            l, a, d, ab = area_de_trabajo(self.root)
            w, h = self.root.winfo_reqwidth(), self.root.winfo_reqheight()
            h += max(self.root.winfo_rooty() - self.root.winfo_y(), 0)      # barra de título
            x = min(max(self.root.winfo_x(), l), max(d - w, l))
            y = min(max(self.root.winfo_y(), a), max(ab - h - 4, a))
            self.root.geometry(f"+{x}+{y}")
        except tk.TclError:
            pass

    def pedir_salir(self):
        if self.mini:
            self.alternar_mini()
        self.confirmando_salir = True
        self.botones.pack_forget()
        self.confirmar.pack(fill="x", padx=4, pady=(2, 6))
        self.root.update_idletasks()
        self._dentro_de_pantalla()

    def cancelar_salir(self):
        self.confirmando_salir = False
        self.confirmar.pack_forget()
        self.botones.pack(fill="x", padx=4, pady=(2, 6))

    def mostrar_aviso(self, texto: str, segundos: float = 6.0):
        if not texto:
            return
        self.lbl_aviso.configure(text=texto)
        if not self.lbl_aviso.winfo_manager():
            antes = self.botones if self.botones.winfo_manager() else self.confirmar
            self.lbl_aviso.pack(fill="x", padx=8, pady=(0, 4), before=antes)
            self.root.update_idletasks()
            self._dentro_de_pantalla()
        self._aviso_hasta = time.monotonic() + segundos

    # ------------------------------------------------------------ pintar
    def actualizar(self, vista, detenido: bool = False):
        """``vista``: ``motor.VistaMotor`` (o None si aún no hay)."""
        T = self.tema
        if self._aviso_hasta and time.monotonic() > self._aviso_hasta:
            self._aviso_hasta = 0.0
            self.lbl_aviso.pack_forget()
        m = vista.maquina if vista is not None else None
        estado = "DETENIDO" if detenido else (m.estado if m is not None else K.PAUSA)
        pausa = estado == K.PAUSA
        if estado != self._estado:
            self._estado = estado
            color = T.color_estado(estado) if estado != "DETENIDO" else T.rojo
            texto_color = T.texto_estado(estado) if estado != "DETENIDO" else T.rojo_texto
            self.lbl_icono.configure(text=icono_estado(estado), fg=texto_color)
            self.lbl_estado.configure(text=texto_estado(estado), fg=texto_color)
            self.lbl_mini.configure(text=f"{icono_estado(estado)} {texto_estado(estado)}", fg=texto_color)
            self.root.configure(bg=color)
            nuevo = "reanudar" if pausa else "ui:pausar"
            if nuevo != self._id_pausa:
                self._id_pausa = nuevo
                for b in (self.b_pausa, self.b_pausa_mini):
                    self.app.registro.cambiar_id(b, nuevo, interno=pausa)
            for b, icono in ((self.b_pausa, True), (self.b_pausa_mini, False)):
                if pausa:
                    b.poner_texto(t("btn_reanudar"), "▶" if icono else None)
                    b.poner_color(T.verde)
                else:
                    b.poner_texto(t("btn_pausar"), "❚❚" if icono else None)
                    b.poner_color(T.ambar)
        if detenido:
            sub = t("sub_DETENIDO")
        else:
            sub = subtitulo(vista, self.cfg) if vista is not None else t("sub_PAUSA")
        if self.lbl_sub.cget("text") != sub:
            self.lbl_sub.configure(text=sub)
        if self.mini or vista is None:
            return
        ahora = time.monotonic()
        if ahora - self._t_vista >= REFRESCO_VISTA_S:
            self._t_vista = ahora
            self._pintar_cara(vista)
            self._pintar_gestos(m)

    def _pintar_cara(self, vista):
        c = self.lienzo
        T = self.tema
        c.delete("all")
        img = getattr(vista, "imagen", None)
        if img is not None and self.cfg["comodidad"].get("mostrar_video"):
            try:
                from PIL import Image, ImageTk
                rgb = img[:, :, ::-1]
                im = Image.fromarray(rgb).resize((VISTA_W, VISTA_H))
                self._foto = ImageTk.PhotoImage(im)
                c.create_image(0, 0, image=self._foto, anchor="nw")
                return
            except Exception:  # noqa: BLE001
                pass
        if vista.puntos is None:
            c.create_text(VISTA_W / 2, VISTA_H / 2, text=t("vista_sin_cara"), fill=T.rojo_texto,
                          font=letra(self.cfg, 16, True))
            return
        color = T.texto_estado(vista.maquina.estado)
        # los puntos vienen ya en espejo (la cámara se voltea una vez): se dibujan tal cual
        dibujar_puntos(c, vista.puntos, VISTA_W, VISTA_H, color)

    def _pintar_gestos(self, m):
        T = self.tema
        g = m.gestos
        for nombre, (_fila, c) in self.barras.items():
            if not self.cfg["gestos"][nombre].get("activo"):
                continue
            c.delete("all")
            if nombre == "parpadeo":
                frac = float(g.parpadeo_progreso or 0.0)
                linea = 1.0
                lleno = T.verde if g.parpadeo_listo else T.acento
            else:
                nivel = g.nivel.get(nombre)
                try:
                    nivel = float(nivel)
                except (TypeError, ValueError):
                    nivel = 0.0
                if nivel != nivel:      # NaN
                    nivel = 0.0
                frac = min(max(nivel, 0.0) / 1.5, 1.0)
                linea = 1.0 / 1.5
                lleno = T.verde if nombre in g.activos else T.acento
            c.create_rectangle(0, 0, BARRA_W * min(max(frac, 0.0), 1.0), BARRA_H, fill=lleno, outline="")
            x = BARRA_W * linea - 2
            c.create_line(x, 0, x, BARRA_H, fill=T.texto, width=3)

    def reconstruir(self):
        """Tras cambiar el tamaño de letra o el contraste."""
        mini = self.mini
        for w in list(self.root.winfo_children()):
            if isinstance(w, tk.Toplevel):
                continue
            w.destroy()
        self.mini = False
        self._estado = None
        self._id_pausa = "ui:pausar"
        self._construir()
        if mini:
            self.alternar_mini()
        self.root.update_idletasks()
        self._dentro_de_pantalla()
