"""Pantalla de emergencia (versión 1.1, paquete B): se pidió AYUDA.

- ``Toplevel`` a pantalla completa en el monitor del puntero, siempre encima.
- Fondo rojo que alterna entre ``#b00000`` y ``#5a0000`` **una vez por segundo** (menos de tres
  destellos por segundo: seguro ante las convulsiones, WCAG 2.3.1).
- «NECESITO AYUDA» en letra de 72 pt o más, en blanco; debajo, «Por favor, que venga {cuidador}.».
- Un botón grande «Ya me atendieron» (al menos 300 × 120 px), verde sobre fondo oscuro: es el
  objetivo ``emergencia:atendido`` que atiende la máquina (quedarse quieto ``emergencia.detener_s``).
- Abajo, cómo se apaga (Esc, clic o el atajo del cuidador).
- Es la **única** ventana del programa que toma el foco (``focus_force``), para que Esc llegue.
  Cuando se abre ya se soltó todo y nadie está escribiendo.
- ``prueba=True`` («Probar la alarma»): la misma pantalla 3 segundos; se cierra sola y no cambia
  el estado del programa (el botón y Esc la cierran).
"""
from __future__ import annotations

import logging
import time
import tkinter as tk

from .. import constantes as K
from .. import emergencia as E
from .comun import LETRA, BotonGrande, tema
from .textos import t

log = logging.getLogger("lycan")

PT_TITULO = 72
PT_LLAMANDO = 36
PT_COMO_PARAR = 20
BOTON_MIN_ANCHO, BOTON_MIN_ALTO = 300, 120
FONDO_BOTON = "#101010"
TEXTO_BLANCO = "#ffffff"
PASO_COLOR_MS = 200            # se revisa 5 veces por segundo; el color cambia solo una vez por segundo


class VentanaEmergencia:
    def __init__(self, root, app, rect, prueba: bool = False, al_cerrar=None, reloj=time.monotonic):
        """``rect`` = (izq, arriba, der, abajo) del monitor en píxeles físicos."""
        self.root = root
        self.app = app
        self.prueba = bool(prueba)
        self.al_cerrar = al_cerrar
        self.reloj = reloj
        self.t0 = reloj()
        self.cerrada = False
        self.cambios: list = []            # (t, color) de cada cambio de color (para las pruebas)
        self.color = None
        self._loop = None
        self._fin = None
        cfg = app.cfg.datos
        T = self.tema = tema(cfg)
        textos = E.textos_pantalla(cfg)
        l, a, d, ab = (int(v) for v in rect)
        self.rect = (l, a, d, ab)
        w = self.win = tk.Toplevel(root)
        w.overrideredirect(True)
        w.attributes("-topmost", True)
        w.title(textos["titulo"])
        w.geometry(f"{max(d - l, 200)}x{max(ab - a, 200)}+{l}+{a}")
        fondo = E.ROJO_CLARO
        w.configure(bg=fondo)
        ancho_texto = max(d - l - 80, 200)
        self.lbl_titulo = tk.Label(w, text=textos["titulo"], bg=fondo, fg=TEXTO_BLANCO,
                                   font=(LETRA, PT_TITULO, "bold"), wraplength=ancho_texto, justify="center")
        self.lbl_titulo.pack(pady=(max((ab - a) // 12, 20), 10))
        self.lbl_llamando = tk.Label(w, text=textos["llamando"], bg=fondo, fg=TEXTO_BLANCO,
                                     font=(LETRA, PT_LLAMANDO, "bold"), wraplength=ancho_texto, justify="center")
        self.lbl_llamando.pack(pady=(0, 20))
        # «Ya me atendieron»: verde sobre un marco oscuro, de al menos 300 × 120 px
        self.marco = tk.Frame(w, bg=FONDO_BOTON, width=max(BOTON_MIN_ANCHO + 120, (d - l) // 3),
                              height=BOTON_MIN_ALTO + 40)
        self.marco.pack_propagate(False)
        self.marco.pack(pady=10)
        reg = app.registro
        comando = self.cerrar if self.prueba else reg.comando(K.ID_ATENDIDO)
        self.boton = BotonGrande(self.marco, textos["atendido"], comando, T, (LETRA, 30, "bold"))
        self.boton.poner_color(K.VERDE, "#000000")
        self.boton.pack(fill="both", expand=True, padx=20, pady=20)
        if not self.prueba:
            reg.agregar(K.ID_ATENDIDO, self.boton, None, interno=True)
        abajo = textos["como_parar"]
        if self.prueba:
            abajo = t("emergencia_prueba") + "\n" + abajo
        self.lbl_como = tk.Label(w, text=abajo, bg=fondo, fg=TEXTO_BLANCO, font=(LETRA, PT_COMO_PARAR, "bold"),
                                 wraplength=ancho_texto, justify="center")
        self.lbl_como.pack(pady=(20, 10))
        reg.ventana("emergencia", w)
        for x in (w, self.lbl_titulo, self.lbl_llamando, self.lbl_como, self.marco, self.boton):
            x.bind("<Escape>", lambda e=None: self.escape())
        self._pintar_color()
        try:
            w.lift()
            w.focus_force()                # la única ventana propia que toma el foco (para Esc)
        except tk.TclError:
            pass
        if self.prueba:
            self._fin = w.after(int(E.PROBAR_S * 1000), self.cerrar)
        log.info("Pantalla de emergencia abierta%s", " (prueba)" if self.prueba else "")

    # ------------------------------------------------------------ color
    def _pintar_color(self):
        if self.cerrada:
            return
        color = E.color_fondo(self.reloj(), self.t0)
        if color != self.color:
            self.color = color
            self.cambios.append((self.reloj(), color))
            try:
                for x in (self.win, self.lbl_titulo, self.lbl_llamando, self.lbl_como):
                    x.configure(bg=color)
            except tk.TclError:
                return
        try:
            self._loop = self.win.after(PASO_COLOR_MS, self._pintar_color)
        except tk.TclError:
            pass

    # ------------------------------------------------------------ cerrar
    def escape(self, _e=None):
        """Esc: quien cuida apaga la alarma (en la prueba, cierra)."""
        if self.prueba:
            self.cerrar()
            return
        f = getattr(self.app, "apagar_emergencia", None)
        if f is not None:
            f("Esc")

    def viva(self) -> bool:
        if self.cerrada:
            return False
        try:
            return bool(self.win.winfo_exists())
        except tk.TclError:
            return False

    def cerrar(self, _e=None):
        if self.cerrada:
            return
        self.cerrada = True
        for job in (self._loop, self._fin):
            if job is not None:
                try:
                    self.win.after_cancel(job)
                except (tk.TclError, ValueError):
                    pass
        try:
            self.app.registro.quitar_ventana("emergencia")
        except Exception:  # noqa: BLE001
            pass
        try:
            self.win.destroy()
        except tk.TclError:
            pass
        log.info("Pantalla de emergencia cerrada")
        if self.al_cerrar is not None:
            try:
                self.al_cerrar(self)
            except Exception:  # noqa: BLE001
                log.exception("Error al cerrar la pantalla de emergencia")
