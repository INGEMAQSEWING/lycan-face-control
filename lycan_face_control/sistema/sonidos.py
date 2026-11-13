"""Sonidos cortos en un hilo aparte (winsound.Beep bloquea mientras suena). Copiado de Lycan Mouse
Control con los tonos de Lycan Face Control (sección 6.8)."""
from __future__ import annotations

import queue
import threading

try:
    import winsound
except ImportError:  # pragma: no cover
    winsound = None

TONOS = {
    "activar": [(660, 70), (880, 90)],          # reanudar
    "pausar": [(523, 80), (392, 100)],
    "clic": [(1200, 15)],                       # disparo de permanencia o gesto
    "perdida": [(300, 120)],                    # no veo su cara
    "listo": [(988, 40)],                       # parpadeo largo cumplido: ya puede abrir los ojos
    "alerta": [(880, 180), (660, 180), (880, 180), (660, 180)],   # frase de urgencia
}


class Sonidos:
    def __init__(self, activos: bool = True, arrancar: bool = True):
        self.activos = activos
        self._cola: queue.Queue = queue.Queue(maxsize=8)
        self._hilo = threading.Thread(target=self._bucle, daemon=True, name="sonidos")
        if arrancar:
            self._hilo.start()

    def tocar(self, nombre: str):
        # la alerta de urgencia suena aunque los sonidos estén apagados
        if (not self.activos and nombre != "alerta") or winsound is None or nombre not in TONOS:
            return
        try:
            self._cola.put_nowait(nombre)
        except queue.Full:
            pass

    def _bucle(self):
        while True:
            nombre = self._cola.get()
            if nombre is None:
                return
            for f, ms in TONOS.get(nombre, ()):
                try:
                    winsound.Beep(f, ms)
                except RuntimeError:
                    pass

    def cerrar(self):
        try:
            self._cola.put_nowait(None)
        except queue.Full:
            pass
