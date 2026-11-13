"""Hilo MOTOR (sección 2.1): último cuadro -> detector (FaceMesh) -> medidas -> máquina de
estados (gestos, puntero, permanencia) -> salida.

- Es el **único** que envía acciones de ratón y teclado, salvo ``salida.soltar_todo()`` (seguro
  desde cualquier hilo). El texto del teclado en pantalla llega como orden (``OrdenEscribir``),
  nunca se envía desde tkinter.
- Procesa como máximo ``camara.fps_proceso`` cuadros por segundo; siempre el más reciente.
- Deja para la interfaz una ``VistaMotor`` en una cola de 1 (se descarta la vieja) y los avisos y
  sonidos en otra cola.
- Cualquier error suelta todo y pausa; 3 errores en 60 s detienen el motor (la interfaz avisa).
- Al terminar (por lo que sea) suelta todo, detiene la cámara y cierra el detector.

Con ``CamaraFalsa`` + ``DetectorFalso`` + ``SalidaSimulada`` funciona sin cámara, sin mediapipe y
sin tocar Windows (pruebas y ``--simular --camara-falsa``).
"""
from __future__ import annotations

import logging
import queue
import threading
import time
from collections import deque
from dataclasses import dataclass, field

from . import constantes as K
from .acciones import Aviso, Elegir, Hablar, Sonido, TeclaVK, Texto, describir, es_de_entrada
from .cara import medir_si_valida, posicion_y_tamano
from .estados import Maquina, Vista
from .salida.base import ErrorEnvio

log = logging.getLogger("lycan")

REINTENTO_BLOQUEO_S = 2.0       # tras un SendInput rechazado, cada cuánto se prueba otra vez
ESPERA_CUADRO_S = 0.1
PASO_SIN_CUADRO_S = 0.25        # sin cuadros nuevos, igual corren los relojes (sin cara, etc.)
REGISTRO_RENDIMIENTO_S = 60.0


@dataclass(frozen=True)
class OrdenEscribir:
    """Texto armado en el teclado en pantalla para escribir en el programa activo."""
    texto: str


@dataclass
class VistaMotor:
    """Lo que la interfaz pinta: la vista de la máquina + datos del motor."""
    maquina: Vista = field(default_factory=Vista)
    fps: float = 0.0
    latencia_ms: float = 0.0
    puntos: object = None            # (N, 3) normalizados de la cara (para la silueta), o None
    io_fraccion: float | None = None  # tamaño de la cara (paso "Posición" de la calibración)
    centro_cara: tuple | None = None
    camara: str = ""
    ultima_accion: str = ""
    simulada: bool = False
    t: float = 0.0


class Estadisticas:
    def __init__(self):
        self.t_cuadros: deque = deque(maxlen=60)
        self.latencias: deque = deque(maxlen=600)
        self.total = 0

    def cuadro(self, t: float):
        self.t_cuadros.append(t)
        self.total += 1

    @property
    def fps(self) -> float:
        if len(self.t_cuadros) < 2:
            return 0.0
        dt = self.t_cuadros[-1] - self.t_cuadros[0]
        return (len(self.t_cuadros) - 1) / dt if dt > 0 else 0.0

    def latencia(self, ms: float):
        self.latencias.append(ms)

    def resumen(self) -> dict:
        lat = sorted(self.latencias)
        p95 = lat[int(0.95 * (len(lat) - 1))] if lat else 0.0
        return {"fps": round(self.fps, 1), "latencia_media_ms": round(sum(lat) / len(lat), 1) if lat else 0.0,
                "latencia_p95_ms": round(p95, 1), "cuadros": self.total}


class Motor(threading.Thread):
    def __init__(self, config: dict, salida, camara=None, detector=None, sistema: bool = True, monitor=None,
                 reloj=None, maquina: Maquina | None = None):
        super().__init__(daemon=True, name="motor")
        self.cfg = config
        self.salida = salida
        self.camara = camara
        self.detector = detector
        self.sistema = sistema              # False en pruebas: no consulta Windows
        self.monitor = monitor
        self.reloj = reloj or time.perf_counter
        self.maquina = maquina
        self.ordenes: queue.Queue = queue.Queue()
        self.vistas: queue.Queue = queue.Queue(maxsize=1)
        self.avisos: queue.Queue = queue.Queue()
        self.cola_calibracion: queue.Queue = queue.Queue(maxsize=600)   # (t, medidas, io_fr, centro)
        self._lock_obj = threading.Lock()
        self._objetivos = None              # lista nueva pendiente de pasar a la máquina
        self._parar = threading.Event()
        self.stats = Estadisticas()
        self.listo = threading.Event()
        self.error_inicio: str | None = None
        self.ultima_accion = ""
        self._numero = 0
        self._t_ult_proceso = None
        self._t_ult_paso = None
        self._t_reintento = None
        self._t_registro = None
        self.fatal = False

    # ------------------------------------------------------------- arranque
    def preparar(self):
        """Crea lo que falte (monitor, máquina, cámara, detector). Lo llama ``run``; las pruebas
        pueden llamarlo y luego usar ``vuelta()`` sin hilo."""
        if self.monitor is None and self.sistema:
            from .sistema import pantallas
            self.monitor = pantallas.elegir((self.cfg.get("pantalla") or {}).get("monitor", "principal"))
            if hasattr(self.salida, "actualizar_pantalla"):
                try:
                    self.salida.actualizar_pantalla()
                except Exception:  # noqa: BLE001
                    log.exception("No se pudo leer el escritorio")
        if self.maquina is None:
            self.maquina = Maquina(self.cfg, self.monitor, pos_cursor=self._pos_cursor, t0=self.reloj())
        if self.camara is None:
            from .captura import Camara
            cam = self.cfg["camara"]
            self.camara = Camara(cam["indice"], cam["ancho"], cam["alto"], cam["fps"], cam.get("espejo", True))
            self.camara.al_perder = lambda: self.ordenes.put(("camara_perdida",))
        if hasattr(self.camara, "is_alive") and not self.camara.is_alive() and hasattr(self.camara, "start"):
            self.camara.start()
        if self.detector is None:
            from .detector import Detector
            self.detector = Detector()

    def _pos_cursor(self):
        try:
            return self.salida.posicion_cursor()
        except Exception:  # noqa: BLE001
            return None

    def run(self):
        try:
            self.preparar()
        except Exception as e:  # noqa: BLE001
            log.exception("No se pudo arrancar el motor")
            self.error_inicio = repr(e)
            self.salida.soltar_todo("error al arrancar")
            self.avisos.put(Aviso("error_inicio", repr(e)))
            self.listo.set()
            return
        self.listo.set()
        try:
            while not self._parar.is_set():
                try:
                    self.vuelta()
                except Exception as e:  # noqa: BLE001
                    # un error fuera de lo previsto NO puede matar el hilo en silencio
                    self._error_en_vuelta(e)
        finally:
            self.cerrar()

    def cerrar(self):
        """Suelta todo y libera la cámara y el detector (idempotente)."""
        try:
            self.salida.soltar_todo("fin del motor")
        except Exception:  # noqa: BLE001
            log.exception("soltar_todo al cerrar")
        for obj, metodo in ((self.camara, "detener"), (self.detector, "cerrar")):
            try:
                if obj is not None and hasattr(obj, metodo):
                    getattr(obj, metodo)()
            except Exception:  # noqa: BLE001
                pass

    def detener(self):
        self._parar.set()

    # ------------------------------------------------------------- interfaz con la UI
    def poner_objetivos(self, objetivos):
        """Desde el hilo de la interfaz: botones propios en píxeles de pantalla."""
        with self._lock_obj:
            self._objetivos = list(objetivos or [])

    def orden(self, *args):
        self.ordenes.put(tuple(args))

    def escribir(self, texto: str):
        self.ordenes.put(OrdenEscribir(texto))

    def atajo(self, nombre: str):
        """Desde el hilo de atajos del cuidador. "pausar" suelta todo AL INSTANTE (aunque el
        motor estuviera trabado) y luego pide la pausa; "salir" también suelta todo."""
        if nombre == "pausar":
            self.salida.soltar_todo("atajo de pausa")
            self.ordenes.put(("alternar_pausa",))
        elif nombre == "recentrar":
            self.ordenes.put(("recentrar",))
        elif nombre == "salir":
            self.salida.soltar_todo("salir")

    # ------------------------------------------------------------- bucle
    def vuelta(self):
        """Una vuelta: órdenes, último cuadro, detector y un paso de la máquina."""
        self._atender_ordenes()
        with self._lock_obj:
            nuevos, self._objetivos = self._objetivos, None
        if nuevos is not None:
            self.maquina.poner_objetivos(nuevos)
        cuadro = self.camara.ultimo(self._numero, espera=ESPERA_CUADRO_S)
        if cuadro is None:
            ahora = self.reloj()
            if self._t_ult_paso is None or ahora - self._t_ult_paso > PASO_SIN_CUADRO_S:
                # sin cuadros (cámara perdida): igual corre el reloj de "sin cara"
                self._paso(ahora, None, None)
            return
        self._numero = cuadro.numero
        fps_max = float(self.cfg["camara"].get("fps_proceso", 20))
        if self._t_ult_proceso is not None and fps_max > 0 \
                and cuadro.t_captura - self._t_ult_proceso < 1.0 / fps_max - 0.004:
            return                      # más cuadros de los que hace falta procesar
        self._t_ult_proceso = cuadro.t_captura
        try:
            cara = self.detector.procesar(cuadro.imagen, cuadro.t_captura)
        except Exception as e:  # noqa: BLE001
            log.exception("Error en el detector de la cara")
            self._aplicar(self.maquina.por_error(cuadro.t_captura, e))
            self._revisar_fatal()
            return
        self._paso(cuadro.t_captura, cara, cuadro)

    def _paso(self, t: float, cara, cuadro):
        self._t_ult_paso = self.reloj()
        medidas = None
        io_fr = centro = None
        if cara is not None:
            medidas = medir_si_valida(cara.puntos, cara.ancho, cara.alto)
            try:
                centro, io_fr = posicion_y_tamano(cara.puntos, cara.ancho, cara.alto)
            except Exception:  # noqa: BLE001
                centro = io_fr = None
        self._revisar_bloqueo(t)
        res = self.maquina.procesar(t, medidas)
        self._aplicar(res.acciones)
        if self.maquina.estado == K.CALIBRANDO:
            try:
                self.cola_calibracion.put_nowait((t, medidas, io_fr, centro))
            except queue.Full:
                pass
        if cuadro is not None:
            self.stats.cuadro(cuadro.t_captura)
            self.stats.latencia(max((self.reloj() - cuadro.t_captura) * 1000.0, 0.0))
        self._registro_rendimiento(t)
        self._publicar(res.vista, cara, io_fr, centro, t)
        self._revisar_fatal()

    def _revisar_fatal(self):
        if self.maquina is not None and self.maquina.fatal and not self.fatal:
            self.fatal = True
            self.avisos.put(Aviso("fatal"))
            self._parar.set()

    def _error_en_vuelta(self, e: Exception):
        log.exception("Error en el motor: se suelta todo y se pausa")
        try:
            self.salida.soltar_todo("error en el motor")
        except Exception:  # noqa: BLE001
            pass
        try:
            if self.maquina is not None:
                self._aplicar(self.maquina.por_error(self.reloj(), e))
        except Exception:  # noqa: BLE001
            log.exception("Tampoco se pudo pausar tras el error")
            self.avisos.put(Aviso("error"))
        self._revisar_fatal()
        time.sleep(0.05)          # si el error se repite en cada vuelta, no se come un núcleo

    # ------------------------------------------------------------- aplicar
    def _aplicar(self, acciones):
        try:
            for a in self.salida.aplicar(acciones):
                self.avisos.put(a)
        except ErrorEnvio as e:
            log.warning("Windows no aceptó los eventos (%s): se pausa", e)
            self.salida.soltar_todo("SendInput bloqueado")
            t = self.reloj()
            self._aplicar_sin_envio(self.maquina.bloquear(t, "envio"))
            self._t_reintento = t
        for a in acciones:
            if isinstance(a, (Aviso, Sonido, Hablar, Elegir)):
                self.avisos.put(a)
            elif es_de_entrada(a):
                self.ultima_accion = describir(a)

    def _aplicar_sin_envio(self, acciones):
        try:
            self.salida.aplicar(acciones)
        except ErrorEnvio:
            self.salida.soltar_todo("orden")
        for a in acciones:
            if isinstance(a, (Aviso, Sonido, Hablar, Elegir)):
                self.avisos.put(a)

    def _revisar_bloqueo(self, t: float):
        """Tras un SendInput rechazado (pantalla bloqueada, UAC), probar cada 2 s y seguir solo
        si la pausa fue por eso."""
        if self._t_reintento is None or t - self._t_reintento < REINTENTO_BLOQUEO_S:
            return
        self._t_reintento = t
        if self.salida.probar():
            self._t_reintento = None
            if self.maquina.estado == K.PAUSA and self.maquina.motivo_pausa == "envio":
                self._aplicar(self.maquina.reanudar(t, "Windows acepta de nuevo"))

    # ------------------------------------------------------------- órdenes
    def _atender_ordenes(self):
        while True:
            try:
                o = self.ordenes.get_nowait()
            except queue.Empty:
                return
            t = self.reloj()
            try:
                self._orden(o, t)
            except Exception as e:  # noqa: BLE001
                log.exception("Error atendiendo una orden")
                self._aplicar(self.maquina.por_error(t, e))

    def _orden(self, o, t: float):
        m = self.maquina
        if isinstance(o, OrdenEscribir):
            if o.texto:
                self._aplicar([Texto(o.texto)])
            return
        nombre = o[0]
        arg = o[1] if len(o) > 1 else None
        if nombre == "alternar_pausa":
            self._aplicar(m.alternar_pausa(t))
        elif nombre == "pausar":
            self._aplicar(m.pausar(t, arg or "pausa"))
        elif nombre == "reanudar":
            self._aplicar(m.reanudar(t, arg or "reanudar"))
        elif nombre == "recentrar":
            self._aplicar(m.recentrar(t))
        elif nombre == "submodo":
            self._aplicar(m.poner_submodo(t, arg))
        elif nombre == "elegir":
            # la interfaz eligió un botón propio con el ratón (cuidador): mismo efecto
            self._aplicar([x for x in m.elegir(t, arg) if not isinstance(x, Elegir)])
        elif nombre == "tecla_vk":
            self._aplicar([TeclaVK(int(arg))])
        elif nombre == "config":
            self.cfg = arg
            self._aplicar(m.nueva_config(t, arg, o[2] if len(o) > 2 else None))
        elif nombre == "calibrar":
            if arg:
                self._aplicar(m.iniciar_calibracion(t))
            else:
                self._aplicar(m.terminar_calibracion(t, o[2] if len(o) > 2 else None,
                                                     o[3] if len(o) > 3 else None))
        elif nombre == "soltar":
            self.salida.soltar_todo(arg or "orden")
        elif nombre == "camara_perdida":
            self.salida.soltar_todo("cámara perdida")
            self.avisos.put(Aviso("camara_perdida"))
        elif nombre == "error_externo":
            self.salida.soltar_todo("error")
            self._aplicar(m.por_error(t, arg if isinstance(arg, Exception) else RuntimeError(str(arg))))

    # ------------------------------------------------------------- vista
    def _registro_rendimiento(self, t: float):
        if self._t_registro is None:
            self._t_registro = t
            return
        if t - self._t_registro >= REGISTRO_RENDIMIENTO_S:
            self._t_registro = t
            log.info("Rendimiento: %s", self.stats.resumen())

    def _publicar(self, vista: Vista, cara, io_fr, centro, t: float):
        v = VistaMotor(maquina=vista, fps=self.stats.fps,
                       latencia_ms=self.stats.latencias[-1] if self.stats.latencias else 0.0,
                       puntos=None if cara is None else cara.normalizados, io_fraccion=io_fr, centro_cara=centro,
                       camara=getattr(self.camara, "estado", ""), ultima_accion=self.ultima_accion,
                       simulada=bool(getattr(self.salida, "simulada", False)), t=t)
        try:
            self.vistas.get_nowait()
        except queue.Empty:
            pass
        try:
            self.vistas.put_nowait(v)
        except queue.Full:
            pass
