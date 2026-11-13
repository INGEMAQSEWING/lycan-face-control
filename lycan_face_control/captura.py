"""Hilo de la cámara: lee sin parar y guarda SOLO el último cuadro (nunca hace cola).

- Abre con DirectShow; si en 2 s no entrega cuadros, prueba Media Foundation.
- Pide 640x480 a 30 cuadros/s y BUFFERSIZE=1. Prueba MJPG; si va más lento, vuelve al formato normal.
- Voltea la imagen (espejo) UNA sola vez, aquí. Nunca se vuelve a invertir x en otro lugar.
- 15 lecturas fallidas seguidas = cámara perdida: avisa y reintenta abrir cada 2 s.
- Si al abrir entrega menos de 8 cuadros/s, casi siempre es porque otro programa (Zoom, Teams,
  Cámara) la está usando: se suelta (estado OCUPADA) y se reintenta cada 2,5 s. Tras 3 intentos
  se usa igual (puede ser poca luz). Si ya abierta se queda por debajo de 8 cuadros/s más de 5 s,
  se suelta y se vuelve a abrir (con espera creciente entre reaperturas).

Copiado de Lycan Mouse Control. Nuevo: ``espejo`` configurable y ``CamaraFalsa`` (misma interfaz,
sin cámara real) para las pruebas, --camara-falsa y el soporte.
La imagen NUNCA se guarda en disco.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass

import numpy as np

log = logging.getLogger("lycan")

ABRIENDO, FUNCIONANDO, NO_ABRE, PERDIDA, DETENIDA = "ABRIENDO", "FUNCIONANDO", "NO_ABRE", "PERDIDA", "DETENIDA"
OCUPADA = "OCUPADA"


@dataclass
class Cuadro:
    imagen: np.ndarray     # BGR, ya en espejo
    t_captura: float       # time.perf_counter()
    numero: int


class Camara(threading.Thread):
    FPS_MIN = 8.0             # por debajo: cámara compartida u ocupada
    INTENTOS_LENTA = 3        # aperturas lentas seguidas antes de usarla igual
    ESPERA_OCUPADA_S = 2.5
    MEDIR_S = 1.5             # tope de tiempo de cada medición de cuadros/s
    LENTA_S = 5.0             # tiempo por debajo de FPS_MIN antes de reabrir
    REABRIR_MIN_S = 20.0      # espera mínima entre reaperturas por lentitud (se duplica)

    def __init__(self, indice: int = 0, ancho: int = 640, alto: int = 480, fps: int = 30, espejo: bool = True):
        super().__init__(daemon=True, name="camara")
        self.indice, self.ancho, self.alto, self.fps_pedidos = indice, ancho, alto, fps
        self.espejo = bool(espejo)
        self._lock = threading.Lock()
        self._nuevo = threading.Condition(self._lock)
        self._cuadro: Cuadro | None = None
        self._parar = threading.Event()
        self.estado = ABRIENDO
        self.cap = None
        self.backend = ""
        self.fps_reales = 0.0
        self._n = 0
        self.al_perder = None   # callback() cuando se pierde la cámara
        self.fps_al_abrir = 0.0
        self._intentos_lentos = 0
        self._espera_reabrir = self.REABRIR_MIN_S
        self._t_reabierta = -1e9

    # ---- apertura ----
    def _abrir(self) -> bool:
        import cv2
        for nombre, api in (("DirectShow", cv2.CAP_DSHOW), ("Media Foundation", cv2.CAP_MSMF)):
            if self._parar.is_set():
                return False
            try:
                cap = cv2.VideoCapture(self.indice, api)
            except Exception:  # noqa: BLE001
                continue
            try:
                if self._preparar(cap, nombre):
                    return True
            except Exception:  # noqa: BLE001
                # MSMF/DirectShow pueden lanzar cv2.error al abrir o al volver de suspensión
                log.exception("Cámara %d: error al abrir con %s", self.indice, nombre)
            if self.estado == OCUPADA:
                return False
            try:
                cap.release()
            except Exception:  # noqa: BLE001
                pass
        return False

    def _preparar(self, cap, nombre: str) -> bool:
        """Ajusta y prueba un VideoCapture recién creado. True = quedó como ``self.cap``."""
        import cv2
        if not cap or not cap.isOpened():
            return False
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.ancho)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.alto)
        cap.set(cv2.CAP_PROP_FPS, self.fps_pedidos)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if self._entrega(cap, 2.0):
            fps = self._probar_mjpg(cap)
            self.fps_al_abrir = fps
            if 0.0 <= fps < self.FPS_MIN and self._intentos_lentos < self.INTENTOS_LENTA - 1:
                self._intentos_lentos += 1
                log.warning("Cámara %d: solo %.1f cuadros/s al abrir; parece compartida u ocupada "
                            "por otro programa. Se suelta y se reintenta.", self.indice, fps)
                try:
                    cap.release()
                except Exception:  # noqa: BLE001
                    pass
                self.estado = OCUPADA
                return False
            if fps < self.FPS_MIN:
                log.warning("Cámara %d: sigue lenta (%.1f cuadros/s); se usa igual.", self.indice, fps)
            self._intentos_lentos = 0
            self.cap = cap
            self.backend = nombre
            log.info("Cámara %d abierta con %s (%dx%d)", self.indice, nombre,
                     int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
            return True
        return False

    def _entrega(self, cap, segundos: float) -> bool:
        fin = time.perf_counter() + segundos
        while time.perf_counter() < fin and not self._parar.is_set():
            ok, img = cap.read()
            if ok and img is not None and img.size:
                return True
            time.sleep(0.05)
        return False

    def _medir(self, cap, n=12) -> float:
        """Cuadros/s en hasta ``n`` lecturas o MEDIR_S segundos (lo que pase primero): con una
        cámara compartida a 1 cuadro/s, 12 lecturas tardaban 12 s."""
        t0 = time.perf_counter()
        k = 0
        for _ in range(n):
            ok, _img = cap.read()
            if ok:
                k += 1
            if time.perf_counter() - t0 > self.MEDIR_S or self._parar.is_set():
                break
        dt = time.perf_counter() - t0
        return k / dt if dt > 0 else 0.0

    def _probar_mjpg(self, cap) -> float:
        """Prueba MJPG y deja el formato más rápido. Devuelve los cuadros/s que quedaron."""
        import cv2
        try:
            antes = self._medir(cap)
            fourcc_prev = cap.get(cv2.CAP_PROP_FOURCC)
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
            despues = self._medir(cap)
            if despues + 2 < antes:
                cap.set(cv2.CAP_PROP_FOURCC, fourcc_prev)
            log.info("Cámara: %.1f cuadros/s normal, %.1f con MJPG", antes, despues)
            return max(antes, despues)
        except Exception:  # noqa: BLE001
            return -1.0      # no se pudo medir: no se descarta la cámara

    # ---- bucle ----
    def _avisar_perdida(self):
        if self.al_perder:
            try:
                self.al_perder()
            except Exception:  # noqa: BLE001
                pass

    def _soltar_cap(self):
        cap, self.cap = self.cap, None
        if cap is not None:
            try:
                cap.release()
            except Exception:  # noqa: BLE001
                pass

    def run(self):
        """Nunca muere por un error de OpenCV: cualquier excepción suelta la cámara, la marca
        PERDIDA, avisa y se reintenta a los 2 s (como con 15 lecturas fallidas)."""
        while not self._parar.is_set():
            try:
                self._vuelta()
            except Exception:  # noqa: BLE001
                log.exception("Error en el hilo de la cámara; se suelta y se reintenta")
                self._soltar_cap()
                self.estado = PERDIDA
                self._avisar_perdida()
                if self._parar.wait(2.0):
                    break
        self._soltar_cap()
        self.estado = DETENIDA

    def _vuelta(self):
        """Abrir, leer hasta perderla, soltar. Una vuelta del bucle de ``run``."""
        import cv2
        self.estado = ABRIENDO
        if not self._abrir():
            if self.estado == OCUPADA:
                self._parar.wait(self.ESPERA_OCUPADA_S)
                return
            self.estado = NO_ABRE if self._n == 0 else PERDIDA
            self._parar.wait(2.0)
            return
        self.estado = FUNCIONANDO
        fallos = 0
        t_fps, n_fps = time.perf_counter(), 0
        t_lenta = None
        while not self._parar.is_set():
            ok, img = self.cap.read()
            if not ok or img is None:
                fallos += 1
                if fallos >= 15:
                    self.estado = PERDIDA
                    log.warning("La cámara se desconectó. Reintentando…")
                    self._avisar_perdida()
                    break
                time.sleep(0.02)
                continue
            fallos = 0
            if self.espejo:
                img = cv2.flip(img, 1)   # espejo: UNA sola vez, aquí
            t = time.perf_counter()
            with self._nuevo:
                self._n += 1
                self._cuadro = Cuadro(img, t, self._n)
                self._nuevo.notify_all()
            n_fps += 1
            if t - t_fps >= 1.0:
                self.fps_reales = n_fps / (t - t_fps)
                t_fps, n_fps = t, 0
                if self._lenta_hay_que_reabrir(t, t_lenta):
                    break
                t_lenta = (t_lenta or t) if self.fps_reales < self.FPS_MIN else None
        self._soltar_cap()
        if not self._parar.is_set():
            self._parar.wait(2.0)

    def _lenta_hay_que_reabrir(self, t: float, t_lenta) -> bool:
        """Lenta más de LENTA_S: se suelta y se vuelve a abrir (el otro programa pudo soltarla).
        Entre reaperturas se espera cada vez el doble (para no cortar la imagen sin fin si es
        poca luz)."""
        if t_lenta is None or self.fps_reales >= self.FPS_MIN or t - t_lenta < self.LENTA_S:
            return False
        if t - self._t_reabierta < self._espera_reabrir:
            return False
        log.warning("Cámara a %.1f cuadros/s por más de %.0f s: se vuelve a abrir.", self.fps_reales,
                    self.LENTA_S)
        if self._t_reabierta > 0:
            self._espera_reabrir = min(self._espera_reabrir * 2, 300.0)
        self._t_reabierta = t
        self._intentos_lentos = 0
        return True

    def ultimo(self, despues_de: int = 0, espera: float = 0.1) -> Cuadro | None:
        """El cuadro más reciente con número > despues_de (espera hasta ``espera`` s)."""
        with self._nuevo:
            if self._cuadro is None or self._cuadro.numero <= despues_de:
                self._nuevo.wait(espera)
            c = self._cuadro
        if c is None or c.numero <= despues_de:
            return None
        return c

    def detener(self):
        self._parar.set()
        with self._nuevo:
            self._nuevo.notify_all()

    # alias con los nombres de la especificación (sección 3.2)
    def iniciar(self):
        self.start()


def probar_indices(maximo: int = 4) -> list[int]:
    """Índices de cámara que abren (para Opciones). Tarda unos segundos."""
    import cv2
    out = []
    for i in range(maximo):
        cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
        try:
            if cap.isOpened():
                ok, _ = cap.read()
                if ok:
                    out.append(i)
        finally:
            cap.release()
    return out


class CamaraFalsa:
    """Cámara sin cámara: misma interfaz que ``Camara`` (start/iniciar, ultimo, detener, join,
    estado, fps_reales) pero no abre ningún dispositivo.

    - ``generador(t) -> imagen BGR | None``: si se da, cada cuadro sale de ahí; si no, negro.
    - ``reloj``: función de tiempo (por defecto time.perf_counter); las pruebas pasan uno propio.
    - ``fps``: si ``tiempo_real`` es True, ``ultimo()`` espera lo que falte para respetar esos
      cuadros por segundo (como una cámara de verdad); con False entrega uno nuevo en cada
      llamada, sin esperar (pruebas rápidas).
    """

    backend = "Cámara falsa"

    def __init__(self, generador=None, ancho: int = 640, alto: int = 480, fps: float = 30.0,
                 reloj=None, tiempo_real: bool = True):
        self.generador = generador
        self.ancho, self.alto = int(ancho), int(alto)
        self.fps_pedidos = float(fps)
        self.reloj = reloj or time.perf_counter
        self.tiempo_real = tiempo_real
        self.estado = ABRIENDO
        self.fps_reales = 0.0
        self.al_perder = None
        self.indice = -1
        self._n = 0
        self._t_ultimo = None
        self._negro = np.zeros((self.alto, self.ancho, 3), np.uint8)
        self._parar = threading.Event()
        self._vivo = False

    # ---- interfaz de hilo ----
    def start(self):
        self.estado = FUNCIONANDO
        self.fps_reales = self.fps_pedidos
        self._vivo = True

    iniciar = start

    def is_alive(self) -> bool:
        return self._vivo

    def join(self, timeout=None):
        return None

    def detener(self):
        self._parar.set()
        self._vivo = False
        self.estado = DETENIDA

    # ---- cuadros ----
    def ultimo(self, despues_de: int = 0, espera: float = 0.1) -> Cuadro | None:
        if self._parar.is_set() or self.estado != FUNCIONANDO:
            return None
        if self.tiempo_real and self._t_ultimo is not None and self.fps_pedidos > 0:
            falta = self._t_ultimo + 1.0 / self.fps_pedidos - self.reloj()
            if falta > 0:
                if falta > espera:
                    self._parar.wait(espera)
                    return None
                self._parar.wait(falta)
        t = self.reloj()
        img = None
        if self.generador is not None:
            img = self.generador(t)
        if img is None:
            img = self._negro
        self._n += 1
        self._t_ultimo = t
        return Cuadro(img, t, self._n)
