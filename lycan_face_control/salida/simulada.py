"""Salida simulada: no llega nada a Windows. Anota cada evento con su tiempo y lleva el estado de
botones, teclas y cursor para que las pruebas verifiquen que todo quedó suelto. Se usa en las
pruebas, en la calibración (modo ensayo) y con --simular.
"""
from __future__ import annotations

import threading
import time
from collections import deque

from ..constantes import VK_BACK, VK_RETURN, VK_TAB
from .base import ErrorEnvio, SalidaBase


class SalidaSimulada(SalidaBase):
    simulada = True

    def __init__(self, escritorio=(0, 0, 1366, 768), cursor=(683, 384), reloj=None, al_enviar=None,
                 max_eventos: int | None = None):
        """max_eventos: con --simular la lista se recorta a los últimos N (si no, crece sin
        límite). Las pruebas la usan completa."""
        super().__init__()
        self.escritorio = escritorio
        self.cursor = tuple(cursor)
        self.eventos = deque(maxlen=int(max_eventos)) if max_eventos else []   # (t, evento)
        self.envios: list[list] = [] if not max_eventos else deque(maxlen=int(max_eventos))
        self.n_eventos = 0
        self.reloj = reloj or time.perf_counter
        self.fallar = False              # simula SendInput bloqueado
        self.al_enviar = al_enviar       # callback(lista_eventos) para mostrar en pantalla
        self.violaciones: list[str] = []
        self.llamadas = 0
        self.presionados_windows: list = []   # simula botones que quedaron abajo en Windows
        self._lock_ev = threading.Lock()

    def _botones_presionados_en_windows(self) -> list:
        return list(self.presionados_windows)

    def posicion_cursor(self):
        return self.cursor

    def _dormir(self, ms: int):
        with self._lock_ev:
            self.eventos.append((self.reloj(), ("esperar", ms)))
            self.n_eventos += 1

    def _enviar(self, eventos: list):
        if self.fallar:
            raise ErrorEnvio(5, "SendInput bloqueado (simulado)")
        t = self.reloj()
        self.llamadas += 1
        with self._lock_ev:
            # Teclas y caracteres: en cada envío todo lo que baja tiene que subir
            balance: dict = {}
            for ev in eventos:
                if ev[0] == "mover":
                    self.cursor = (ev[1], ev[2])
                elif ev[0] in ("rueda", "rueda_h"):
                    if any(k in self.teclas_abajo for k in ("shift", "ctrl")):
                        self.violaciones.append("rueda con modificadores abajo")
                elif ev[0] in ("vk", "unicode"):
                    clave = (ev[0], ev[1])
                    balance[clave] = balance.get(clave, 0) + (1 if ev[2] else -1)
                self.eventos.append((t, ev))
                self.n_eventos += 1
            if any(v != 0 for v in balance.values()):
                self.violaciones.append(f"tecla o carácter sin soltar en el mismo envío: {balance}")
            self.envios.append(list(eventos))
        if self.al_enviar:
            try:
                self.al_enviar(eventos)
            except Exception:  # noqa: BLE001
                pass

    # ---- ayudas para pruebas ----
    def solo(self, tipo: str) -> list:
        return [ev for _, ev in self.eventos if ev[0] == tipo]

    def botones(self) -> list:
        """Lista de ('izq', True/False) en orden."""
        return [(ev[1], ev[2]) for _, ev in self.eventos if ev[0] == "boton"]

    def texto(self) -> str:
        """Reconstruye lo que se habría escrito (Unicode, Enter, Tab y Borrar)."""
        unidades: list[int] = []
        for _, ev in self.eventos:
            if ev[0] not in ("unicode", "vk") or not ev[2]:
                continue          # solo cuentan las bajadas de teclas y caracteres
            if ev[0] == "unicode":
                unidades.append(ev[1])
            elif ev[0] == "vk":
                if ev[1] == VK_RETURN:
                    unidades.append(0x0A)
                elif ev[1] == VK_TAB:
                    unidades.append(0x09)
                elif ev[1] == VK_BACK and unidades:
                    u = unidades.pop()
                    if 0xDC00 <= u <= 0xDFFF and unidades:   # borrar el emoji entero
                        unidades.pop()
        datos = b"".join(u.to_bytes(2, "little") for u in unidades)
        return datos.decode("utf-16-le", errors="replace")

    def limpiar(self):
        with self._lock_ev:
            self.eventos.clear()
            self.envios.clear()
