"""Calibración de la mirada (versión 1.1, paquete C): ventana a pantalla completa con los puntos.

- ``Toplevel`` a pantalla completa en el monitor del mapeo, siempre encima y **sin activar** (no le
  quita el foco a nadie).
- Dibuja el punto que hay que mirar en coordenadas reales del monitor (los puntos quedan a 8 % del
  borde, ``calibracion_guiada.puntos_mirada``). Mientras se prepara es grande; al medir se encoge
  (la vista se queda en el centro del punto).
- Arriba del centro, el título y la instrucción del paso; si no se ven los dos ojos, el aviso
  «No veo bien sus ojos…»; si un punto se repite, «Mueva solo los ojos…».
- Más abajo, para el cuidador (con el ratón): «Repetir este paso», «Atrás», «Cancelar» y «?».
  Quedan entre las filas de puntos para no taparlos.
- ``PuntoCentro``: el punto del centro durante «Recentrar» con los ojos (1,5 s, se cierra solo).
"""
from __future__ import annotations

import logging
import tkinter as tk

from .comun import BotonGrande, boton_ayuda, letra, no_activar, tema
from .textos import t

log = logging.getLogger("lycan")

RADIO_PREPARAR = 30            # el punto mientras se prepara (px)
RADIO_MEDIR_MIN = 8            # al terminar de medir
CENTRO_PUNTO = 4
FONDO = "#0b1a36"
Y_TEXTO = 0.29                 # entre la fila de puntos de arriba (8 %) y la del medio (50 %)
Y_BOTONES = 0.71               # entre la del medio y la de abajo (92 %)
PUNTO_CENTRO_MS = 1600


def radio_punto(fase: str, progreso: float) -> float:
    """Radio del punto: grande al prepararse; se encoge mientras se mide."""
    if fase != "medir":
        return float(RADIO_PREPARAR)
    p = min(max(float(progreso), 0.0), 1.0)
    return RADIO_MEDIR_MIN + (RADIO_PREPARAR - RADIO_MEDIR_MIN) * (1.0 - p)


class VentanaMirada:
    def __init__(self, root, app, monitor, al_repetir=None, al_atras=None, al_cancelar=None):
        self.root = root
        self.app = app
        self.monitor = monitor
        self.cerrada = False
        cfg = app.cfg.datos
        T = self.tema = tema(cfg)
        self.W, self.H = max(int(monitor.ancho), 200), max(int(monitor.alto), 200)
        w = self.win = tk.Toplevel(root)
        w.overrideredirect(True)
        w.attributes("-topmost", True)
        w.configure(bg=FONDO)
        w.geometry(f"{self.W}x{self.H}+{int(monitor.x)}+{int(monitor.y)}")
        self.canvas = tk.Canvas(w, width=self.W, height=self.H, bg=FONDO, highlightthickness=0)
        self.canvas.place(x=0, y=0)
        self.lbl_titulo = tk.Label(w, text="", bg=FONDO, fg=T.acento, font=letra(cfg, 26, True))
        self.lbl_titulo.place(relx=0.5, rely=Y_TEXTO - 0.07, anchor="center")
        self.lbl_instr = tk.Label(w, text="", bg=FONDO, fg=T.texto, font=letra(cfg, 20, True),
                                  wraplength=int(self.W * 0.7), justify="center")
        self.lbl_instr.place(relx=0.5, rely=Y_TEXTO, anchor="center")
        self.lbl_estado = tk.Label(w, text="", bg=FONDO, fg=T.ambar, font=letra(cfg, 18, True),
                                   wraplength=int(self.W * 0.7), justify="center")
        self.lbl_estado.place(relx=0.5, rely=Y_TEXTO + 0.08, anchor="center")
        fila = tk.Frame(w, bg=FONDO)
        fila.place(relx=0.5, rely=Y_BOTONES, anchor="center")
        reg = app.registro
        self.botones = {}
        for ident, clave, accion in (("cal_ojos:repetir_paso", "cal_repetir_paso", al_repetir),
                                     ("cal_ojos:atras", "cal_atras", al_atras),
                                     ("cal_ojos:cancelar", "btn_cancelar", al_cancelar)):
            b = BotonGrande(fila, t(clave), reg.comando(ident), T, letra(cfg, 16, True))
            b.pack(side="left", padx=6)
            reg.agregar(ident, b, (lambda e=None, f=accion: f() if f else None))
            self.botones[ident] = b
        boton_ayuda(fila, t("cal_ayuda"), cfg, T).pack(side="left", padx=6)
        reg.ventana("calibracion_mirada", w)
        no_activar(w)
        self._firma = None

    def actualizar(self, est):
        """Pinta un estado de la guía (``calibracion_guiada.EstadoGuia``)."""
        if self.cerrada:
            return
        T = self.tema
        p = est.paso
        try:
            if self.lbl_titulo.cget("text") != t(f"cal_{p}_titulo"):
                self.lbl_titulo.configure(text=t(f"cal_{p}_titulo"))
                self.lbl_instr.configure(text=t(f"cal_{p}"))
            if est.sin_ojos:
                self.lbl_estado.configure(text=t("cal_mirada_sin_ojos"), fg=T.rojo_texto)
            elif est.sin_cara and est.fase == "medir":
                self.lbl_estado.configure(text=t("cal_sin_cara"), fg=T.rojo_texto)
            elif est.repetir_punto:
                self.lbl_estado.configure(text=t("cal_mirada_repetir"), fg=T.ambar)
            elif est.fase == "preparar":
                self.lbl_estado.configure(text=t("cal_preparese"), fg=T.ambar)
            else:
                self.lbl_estado.configure(text="")
            firma = (None if est.punto is None else (int(est.punto[0]), int(est.punto[1])), est.punto_fase,
                     round(est.punto_progreso, 2))
            if firma == self._firma:
                return
            self._firma = firma
            c = self.canvas
            c.delete("punto")
            if est.punto is None:
                return
            x = est.punto[0] - self.monitor.x
            y = est.punto[1] - self.monitor.y
            r = radio_punto(est.punto_fase, est.punto_progreso)
            color = T.verde if est.punto_fase == "medir" else T.acento
            c.create_oval(x - r, y - r, x + r, y + r, fill=color, outline="", tags="punto")
            c.create_oval(x - CENTRO_PUNTO, y - CENTRO_PUNTO, x + CENTRO_PUNTO, y + CENTRO_PUNTO, fill="#ffffff",
                          outline="", tags="punto")
        except tk.TclError:
            pass

    def cerrar(self):
        if self.cerrada:
            return
        self.cerrada = True
        for ident in self.botones:
            try:
                self.app.registro.quitar(ident)
            except Exception:  # noqa: BLE001
                pass
        try:
            self.win.destroy()
        except tk.TclError:
            pass


class PuntoCentro:
    """«Recentrar» con los ojos: un punto en el centro del monitor durante 1,6 s (sin activar)."""

    def __init__(self, root, monitor, cfg=None, ms: int = PUNTO_CENTRO_MS):
        T = tema(cfg)
        lado = 2 * RADIO_PREPARAR + 8
        self.win = w = tk.Toplevel(root)
        w.overrideredirect(True)
        w.attributes("-topmost", True)
        w.configure(bg=FONDO)
        cx, cy = monitor.centro
        w.geometry(f"{lado}x{lado}+{int(cx - lado / 2)}+{int(cy - lado / 2)}")
        c = tk.Canvas(w, width=lado, height=lado, bg=FONDO, highlightthickness=0)
        c.pack()
        m = lado / 2
        c.create_oval(m - RADIO_PREPARAR, m - RADIO_PREPARAR, m + RADIO_PREPARAR, m + RADIO_PREPARAR,
                      fill=T.acento, outline="")
        c.create_oval(m - CENTRO_PUNTO, m - CENTRO_PUNTO, m + CENTRO_PUNTO, m + CENTRO_PUNTO, fill="#ffffff",
                      outline="")
        no_activar(w)
        self._fin = w.after(int(ms), self.cerrar)

    def cerrar(self):
        try:
            self.win.destroy()
        except tk.TclError:
            pass
