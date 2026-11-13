"""Interfaz común de las salidas (Windows real y simulada). Copiada de Lycan Mouse Control y
ampliada con texto Unicode (``Texto``), teclas virtuales (``TeclaVK``), doble clic y rueda horizontal.

La base lleva la cuenta de lo presionado (bajo Lock) y aplica las reglas de seguridad:
- ``Bajar`` no hace nada si el botón ya está abajo (nunca dos "abajo" seguidos).
- Nunca se envía rueda con Shift o Ctrl abajo.
- No se presiona nada sobre una ventana propia (barra, teclado, ventana principal): eso se
  elige por cálculo interno, nunca con un clic.
- Clics, teclas y cada carácter de texto bajan y suben en el MISMO envío: nunca quedan
  presionados. El único botón que puede quedar abajo es el del arrastre.
- ``soltar_todo()`` suelta todo en una llamada; es seguro desde cualquier hilo e idempotente.
"""
from __future__ import annotations

import logging
import threading
import time

from ..acciones import (Aviso, Bajar, Clic, Esperar, Mover, MoverDelta, Rueda, SoltarTodo, Subir, Tecla,
                        TeclaVK, Texto, es_de_entrada)
from ..constantes import ALT, CTRL, SHIFT, VK_PERMITIDAS, VK_RETURN, VK_TAB

log = logging.getLogger("lycan")

TROZO_TEXTO = 200          # caracteres por envío de texto


class ErrorEnvio(OSError):
    """SendInput entregó menos eventos de los pedidos (pantalla bloqueada, UAC...)."""


def eventos_texto(texto: str, trozo: int = TROZO_TEXTO) -> list[list]:
    """Convierte un texto en envíos (listas de eventos primitivos).

    - Cada carácter: ('unicode', unidad UTF-16, abajo) bajando y subiendo seguidos; los
      caracteres por encima de U+FFFF (emoji) van como par sustituto.
    - '\\n', '\\r\\n' y '\\r' -> Enter ('vk', VK_RETURN); '\\t' -> Tab (el 0x0A Unicode no llega).
    - Se parte en trozos de ``trozo`` caracteres; un carácter nunca queda partido entre envíos.
    """
    envios: list[list] = []
    actual: list = []
    n = 0
    i = 0
    while i < len(texto):
        c = texto[i]
        if c == "\r":
            if i + 1 < len(texto) and texto[i + 1] == "\n":
                i += 1
            c = "\n"
        if c == "\n":
            evs = [("vk", VK_RETURN, True), ("vk", VK_RETURN, False)]
        elif c == "\t":
            evs = [("vk", VK_TAB, True), ("vk", VK_TAB, False)]
        else:
            cp = ord(c)
            if cp > 0xFFFF:
                cp -= 0x10000
                unidades = (0xD800 + (cp >> 10), 0xDC00 + (cp & 0x3FF))
                # par sustituto: las dos unidades abajo y luego arriba (así lo arma Windows)
                evs = [("unicode", unidades[0], True), ("unicode", unidades[1], True),
                       ("unicode", unidades[0], False), ("unicode", unidades[1], False)]
            else:
                evs = [("unicode", cp, True), ("unicode", cp, False)]
        actual.extend(evs)
        n += 1
        if n >= trozo:
            envios.append(actual)
            actual, n = [], 0
        i += 1
    if actual:
        envios.append(actual)
    return envios


class SalidaBase:
    simulada = False

    def __init__(self):
        self._lock = threading.RLock()
        self.botones_abajo: list[str] = []
        self.teclas_abajo: list[str] = []
        self.rect_propio = None          # (l, t, r, b) de una ventana propia (respaldo)
        self.es_propia_en = None         # callable(x, y) -> bool: ¿ventana propia bajo el punto?
        self.foco_propio = False         # la ventana activa es una propia (no se escribe en ella)
        self.revisar_destino = None      # callable() -> clave de aviso | None (p. ej. "administrador")
        self.escritorio = (0, 0, 1366, 768)  # x, y, ancho, alto del escritorio virtual
        self.intervalo_doble_ms = 160    # entre los dos clics del doble clic
        self.ultimo_motivo = ""
        self.contador_soltar = 0

    # ---- lo que implementa cada salida ----
    def _enviar(self, eventos: list):  # pragma: no cover - abstracto
        """eventos: ('mover', x, y) | ('boton', b, abajo) | ('rueda', delta) | ('rueda_h', delta)
        | ('tecla', k, abajo) | ('vk', vk, abajo) | ('unicode', unidad, abajo)."""
        raise NotImplementedError

    def posicion_cursor(self):  # pragma: no cover - abstracto
        raise NotImplementedError

    def _dormir(self, ms: int):
        time.sleep(ms / 1000.0)

    # ---- utilidades ----
    def _sobre_ventana_propia(self) -> bool:
        try:
            x, y = self.posicion_cursor()
        except Exception:  # noqa: BLE001
            return False
        if self.es_propia_en is not None:
            try:
                if self.es_propia_en(x, y):
                    return True
            except Exception:  # noqa: BLE001
                pass
        if self.rect_propio is None:
            return False
        l, t, r, b = self.rect_propio
        return l <= x < r and t <= y < b

    def _limitar(self, x: int, y: int):
        vx, vy, vw, vh = self.escritorio
        return min(max(int(x), vx), vx + vw - 1), min(max(int(y), vy), vy + vh - 1)

    def _destino_para_teclas(self):
        """Aviso si no se puede escribir en la ventana activa (propia o de administrador)."""
        if self.foco_propio:
            return Aviso("foco_propio")
        if self.revisar_destino is not None:
            try:
                clave = self.revisar_destino()
            except Exception:  # noqa: BLE001
                clave = None
            if clave:
                return Aviso(clave)
        return None

    # ---- API ----
    def aplicar(self, acciones) -> list:
        """Aplica una lista de acciones. Devuelve avisos (p. ej. puntero sobre ventana propia).
        Lanza ErrorEnvio si Windows rechazó los eventos."""
        avisos = []
        for a in acciones or ():
            if a is None or not es_de_entrada(a):
                continue
            if isinstance(a, Clic) and a.veces > 1:
                self._doble(a, avisos)
                continue
            if isinstance(a, Texto):
                self._texto(a, avisos)
                continue
            with self._lock:
                if isinstance(a, Mover):
                    self._enviar([("mover",) + self._limitar(a.x, a.y)])
                elif isinstance(a, MoverDelta):
                    x, y = self.posicion_cursor()
                    self._enviar([("mover",) + self._limitar(x + a.dx, y + a.dy)])
                elif isinstance(a, Bajar):
                    if a.boton in self.botones_abajo:
                        continue
                    if self._sobre_ventana_propia():
                        avisos.append(Aviso("sobre_ventana"))
                        continue
                    self._enviar([("boton", a.boton, True)])
                    self.botones_abajo.append(a.boton)
                elif isinstance(a, Subir):
                    if a.boton not in self.botones_abajo:
                        continue
                    self.botones_abajo.remove(a.boton)
                    self._enviar([("boton", a.boton, False)])
                elif isinstance(a, Clic):
                    if self._sobre_ventana_propia():
                        avisos.append(Aviso("sobre_ventana"))
                        continue
                    if a.boton in self.botones_abajo:
                        continue
                    self._enviar([("boton", a.boton, True), ("boton", a.boton, False)])
                elif isinstance(a, Rueda):
                    if SHIFT in self.teclas_abajo or CTRL in self.teclas_abajo:
                        self._soltar(motivo="rueda con modificadores")
                    if a.delta:
                        self._enviar([("rueda_h" if a.horizontal else "rueda", int(a.delta))])
                elif isinstance(a, Tecla):
                    if a.abajo:
                        if a.tecla in self.teclas_abajo:
                            continue
                        self._enviar([("tecla", a.tecla, True)])
                        self.teclas_abajo.append(a.tecla)
                    else:
                        if a.tecla not in self.teclas_abajo:
                            continue
                        self.teclas_abajo.remove(a.tecla)
                        self._enviar([("tecla", a.tecla, False)])
                elif isinstance(a, TeclaVK):
                    if a.vk not in VK_PERMITIDAS:
                        log.warning("Tecla virtual no permitida: %s", a.vk)
                        continue
                    aviso = self._destino_para_teclas()
                    if aviso:
                        avisos.append(aviso)
                        continue
                    self._enviar([("vk", a.vk, True), ("vk", a.vk, False)])
                elif isinstance(a, Esperar):
                    self._dormir(int(a.ms))
                elif isinstance(a, SoltarTodo):
                    self._soltar(a.motivo)
        return avisos

    def _doble(self, a: Clic, avisos: list):
        """Doble clic: dos clics completos separados por ``intervalo_doble_ms`` (la espera va
        fuera del Lock para no demorar un soltar_todo de otro hilo)."""
        for i in range(2):
            with self._lock:
                if self._sobre_ventana_propia():
                    avisos.append(Aviso("sobre_ventana"))
                    return
                if a.boton in self.botones_abajo:
                    return
                self._enviar([("boton", a.boton, True), ("boton", a.boton, False)])
            if i == 0 and self.intervalo_doble_ms > 0:
                self._dormir(int(self.intervalo_doble_ms))

    def _texto(self, a: Texto, avisos: list):
        if not a.texto:
            return
        with self._lock:
            aviso = self._destino_para_teclas()
            if aviso:
                avisos.append(aviso)
                return
            for envio in eventos_texto(a.texto):
                self._enviar(envio)

    def _soltar(self, motivo: str = ""):
        # Orden fijo: izquierdo, derecho y por último el del medio; luego Shift, Ctrl y Alt.
        orden = ("izq", "der", "medio")
        abajo = list(self.botones_abajo)
        eventos = [("boton", b, False) for b in orden if b in abajo]
        eventos += [("boton", b, False) for b in abajo if b not in orden]
        # por seguridad siempre se sueltan Shift, Ctrl y Alt aunque no figuren
        eventos += [("tecla", k, False) for k in (SHIFT, CTRL, ALT)]
        self.botones_abajo.clear()
        self.teclas_abajo.clear()
        self.ultimo_motivo = motivo
        self.contador_soltar += 1
        try:
            self._enviar(eventos)
        except Exception as e:  # noqa: BLE001 - soltar de más no hace daño; nunca romper aquí
            log.warning("soltar_todo no pudo enviar (%s): %s", motivo, e)

    def soltar_todo(self, motivo: str = ""):
        """Suelta todo lo presionado. Seguro desde cualquier hilo y llamado varias veces."""
        with self._lock:
            hubo = bool(self.botones_abajo or self.teclas_abajo)
            self._soltar(motivo)
        if hubo:
            log.info("Soltar todo: %s", motivo or "sin motivo")

    def _botones_presionados_en_windows(self) -> list:
        """Botones del ratón que Windows cree presionados (la salida de Windows lo pregunta)."""
        return []

    def soltar_botones_huerfanos(self, motivo: str = "arranque") -> list:
        """Al arrancar (ronda 3): si la sesión anterior se cerró a la fuerza en medio de un
        arrastre (Administrador de tareas, un fallo nativo), Windows sigue con el botón abajo y
        la persona no tiene un ratón para soltarlo. Se envía "subir" de los que estén abajo."""
        try:
            abajo = [b for b in self._botones_presionados_en_windows() if b not in self.botones_abajo]
        except Exception:  # noqa: BLE001
            log.exception("No se pudo revisar el estado de los botones")
            return []
        if not abajo:
            return []
        try:
            with self._lock:
                self._enviar([("boton", b, False) for b in abajo])
        except Exception:  # noqa: BLE001
            log.exception("No se pudo soltar un botón que quedó presionado")
            return []
        log.warning("Se soltó %s: quedó presionado de la sesión anterior (%s)", ", ".join(abajo), motivo)
        return abajo

    def probar(self) -> bool:
        """Envío inocuo para saber si Windows vuelve a aceptar eventos."""
        try:
            with self._lock:
                x, y = self.posicion_cursor()
                self._enviar([("mover",) + self._limitar(x, y)])
            return True
        except Exception:  # noqa: BLE001
            return False

    def todo_suelto(self) -> bool:
        return not self.botones_abajo and not self.teclas_abajo
