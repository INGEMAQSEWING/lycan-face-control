"""Alarma de la emergencia (versión 1.1, paquete B): un sonido fuerte que funciona sin internet.

- El sonido se arma en memoria con ``wave`` y ``struct``: dos tonos que se alternan (960 y 640 Hz,
  0,35 s cada uno), con la fuerza de ``emergencia.volumen``. No hay archivos de sonido en el
  repositorio.
- La primera vez se escribe en ``carpeta_datos()/alarma.wav`` (si no se puede, en la carpeta
  temporal) y se toca en bucle con ``winsound.PlaySound`` (asíncrono: no traba la interfaz).
- ``detener()`` la calla al instante (``PlaySound(None, 0)``); se puede llamar desde cualquier hilo
  (el atajo del cuidador la calla desde el hilo de atajos).
- Si ``PlaySound`` falla, el respaldo es ``winsound.Beep`` en un hilo propio; si tampoco hay
  ``winsound``, ``tocar()`` devuelve False y la interfaz avisa (la pantalla roja y la voz siguen).
- No se toca el volumen de Windows y no se usa la red.
"""
from __future__ import annotations

import io
import logging
import math
import struct
import tempfile
import threading
import wave
from pathlib import Path

try:
    import winsound as _winsound
except ImportError:  # pragma: no cover - solo Windows
    _winsound = None

log = logging.getLogger("lycan")

FRECUENCIA_MUESTREO = 22050
TONO_ALTO, TONO_BAJO = 960, 640
DURACION_TONO_S = 0.35
AMPLITUD_MAX = 32000          # 16 bits con signo (deja un margen para no saturar)
NOMBRE_ARCHIVO = "alarma.wav"
RAMPA_S = 0.005               # rampa corta al empezar y al terminar cada tono (sin chasquidos)


def amplitud(volumen) -> int:
    """Fuerza de la onda según ``emergencia.volumen`` (10 a 100)."""
    try:
        v = float(volumen)
    except (TypeError, ValueError):
        v = 100.0
    if not math.isfinite(v):
        v = 100.0
    v = min(max(v, 10.0), 100.0)
    return int(round(AMPLITUD_MAX * v / 100.0))


def generar_wav(volumen=100, frecuencia: int = FRECUENCIA_MUESTREO) -> bytes:
    """Un ciclo de la alarma (tono alto + tono bajo) como WAV mono de 16 bits, en memoria."""
    amp = amplitud(volumen)
    n = int(round(frecuencia * DURACION_TONO_S))
    rampa = max(int(frecuencia * RAMPA_S), 1)
    muestras = []
    for f in (TONO_ALTO, TONO_BAJO):
        for i in range(n):
            env = min(1.0, i / rampa, (n - 1 - i) / rampa)
            muestras.append(int(amp * env * math.sin(2 * math.pi * f * i / frecuencia)))
    datos = struct.pack("<%dh" % len(muestras), *muestras)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(frecuencia)
        w.writeframes(datos)
    return buf.getvalue()


def _carpeta_datos() -> Path:
    from ..config import carpeta_datos
    return carpeta_datos()


class Alarma:
    """``tocar()`` la hace sonar en bucle; ``detener()`` la calla. ``winsound_mod`` y ``carpeta``
    son para las pruebas (un winsound simulado y una carpeta temporal)."""

    def __init__(self, volumen=100, carpeta: Path | None = None, winsound_mod=None):
        self.volumen = volumen
        self.carpeta = Path(carpeta) if carpeta is not None else None
        self.ws = _winsound if winsound_mod is None else winsound_mod
        self.ruta: Path | None = None
        self._vol_escrito = None
        self.sonando = False
        self.respaldo = False          # True: suena con Beep porque PlaySound falló
        self._parar = threading.Event()
        self._hilo = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------ archivo
    def preparar(self) -> Path | None:
        """Escribe el WAV (una vez por volumen). Primero en la carpeta de datos; si no se puede,
        en la carpeta temporal. None si no se pudo escribir en ninguna."""
        if self.ruta is not None and self._vol_escrito == amplitud(self.volumen) and self.ruta.exists():
            return self.ruta
        datos = generar_wav(self.volumen)
        lugares = []
        try:
            lugares.append(self.carpeta if self.carpeta is not None else _carpeta_datos())
        except Exception:  # noqa: BLE001
            pass
        lugares.append(Path(tempfile.gettempdir()))
        for carpeta in lugares:
            try:
                carpeta.mkdir(parents=True, exist_ok=True)
                ruta = carpeta / NOMBRE_ARCHIVO
                ruta.write_bytes(datos)
                self.ruta = ruta
                self._vol_escrito = amplitud(self.volumen)
                return ruta
            except OSError as e:
                log.warning("No se pudo escribir la alarma en %s: %s", carpeta, e)
        self.ruta = None
        return None

    # ------------------------------------------------------------ sonar
    def tocar(self) -> bool:
        """Empieza a sonar en bucle. False si no se pudo de ninguna forma."""
        with self._lock:
            if self.sonando:
                return True
            ws = self.ws
            if ws is None:
                log.warning("La alarma no puede sonar: no hay winsound")
                return False
            ruta = self.preparar()
            if ruta is not None:
                try:
                    ws.PlaySound(str(ruta), ws.SND_FILENAME | ws.SND_ASYNC | ws.SND_LOOP)
                    self.sonando = True
                    self.respaldo = False
                    return True
                except Exception as e:  # noqa: BLE001
                    log.warning("PlaySound no pudo tocar la alarma (%s); se usa el respaldo", e)
            if not callable(getattr(ws, "Beep", None)):
                return False
            self._parar.clear()
            self.respaldo = True
            self.sonando = True
            self._hilo = threading.Thread(target=self._bucle_beep, daemon=True, name="alarma")
            self._hilo.start()
            log.warning("La alarma suena con el respaldo (Beep)")
            return True

    def _bucle_beep(self):
        ms = int(DURACION_TONO_S * 1000)
        fallos = 0
        while not self._parar.is_set():
            for f in (TONO_ALTO, TONO_BAJO):
                if self._parar.is_set():
                    return
                try:
                    self.ws.Beep(f, ms)
                except Exception:  # noqa: BLE001
                    fallos += 1
                    if fallos > 20:
                        log.warning("Tampoco suena el respaldo de la alarma")
                        self.sonando = False
                        return
                    self._parar.wait(DURACION_TONO_S)

    def detener(self):
        """Calla la alarma al instante (seguro desde cualquier hilo y aunque no esté sonando)."""
        self._parar.set()
        ws = self.ws
        if ws is not None:
            try:
                ws.PlaySound(None, 0)
            except Exception:  # noqa: BLE001
                pass
        self.sonando = False


class AlarmaMuda:
    """La misma interfaz sin sonido: para ``--simular``, las pruebas y las capturas del video (nunca
    suena de verdad). Anota cuántas veces se pidió tocar y detener."""

    def __init__(self, volumen=100, falla: bool = False):
        self.volumen = volumen
        self.falla = falla
        self.sonando = False
        self.respaldo = False
        self.veces_tocar = 0
        self.veces_detener = 0

    def tocar(self) -> bool:
        self.veces_tocar += 1
        if self.falla:
            return False
        self.sonando = True
        return True

    def detener(self):
        self.veces_detener += 1
        self.sonando = False
