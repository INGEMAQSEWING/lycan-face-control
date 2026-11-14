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
REVISAR_MONITOR_S = 2.0         # cada cuánto se relee el monitor (televisor conectado, resolución...)
REVISAR_CAMARA_S = 2.0          # cada cuánto se revisa que el hilo de la cámara siga vivo
# estado de la cámara -> aviso para la persona (en vez de "No veo su cara")
AVISOS_CAMARA = {"NO_ABRE": "no_camara", "OCUPADA": "camara_ocupada", "PERDIDA": "camara_perdida"}


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
    imagen: object = None            # cuadro reducido (BGR) SOLO si "Mostrar el video" está encendido


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
        self._t_proximo = None              # horario del limitador de cuadros procesados
        self._t_ult_paso = None
        # latido (time.monotonic) al empezar cada vuelta: el vigilante de la interfaz distingue un
        # motor lento (un cuadro que tardó, memoria paginada) de uno trabado o muerto
        self.latido = time.monotonic()
        self._t_reintento = None
        self._t_registro = None
        self.fatal = False
        self._monitor_auto = False          # el monitor lo eligió el motor: se relee
        self._t_monitor = None
        self._camara_propia = False         # la cámara la creó el motor: se puede recrear
        self._t_camara = None
        self._aviso_camara = None           # último aviso de cámara dado (sin repetir)

    # ------------------------------------------------------------- arranque
    def preparar(self):
        """Crea lo que falte (monitor, máquina, cámara, detector). Lo llama ``run``; las pruebas
        pueden llamarlo y luego usar ``vuelta()`` sin hilo."""
        if self.monitor is None and self.sistema:
            from .sistema import pantallas
            self._monitor_auto = True
            self.monitor = pantallas.elegir((self.cfg.get("pantalla") or {}).get("monitor", "principal"))
            if hasattr(self.salida, "actualizar_pantalla"):
                try:
                    self.salida.actualizar_pantalla()
                except Exception:  # noqa: BLE001
                    log.exception("No se pudo leer el escritorio")
        if self.maquina is None:
            self.maquina = Maquina(self.cfg, self.monitor, pos_cursor=self._pos_cursor, t0=self.reloj())
        # la detección se carga ANTES de encender la cámara (ronda 3): si falla (poca memoria, falta
        # una DLL) la cámara ni se abre y el bombillo no queda encendido
        if self.detector is None:
            from .detector import Detector
            self.detector = Detector()
        if self.camara is None:
            self.camara = self._nueva_camara()
            self._camara_propia = True
        if hasattr(self.camara, "is_alive") and not self.camara.is_alive() and hasattr(self.camara, "start"):
            self.camara.start()

    def _nueva_camara(self):
        from .captura import Camara
        cam = self.cfg["camara"]
        c = Camara(cam["indice"], cam["ancho"], cam["alto"], cam["fps"], cam.get("espejo", True))
        c.al_perder = lambda: self.ordenes.put(("camara_perdida",))
        return c

    def _vigilar_camara(self, t: float):
        """Avisa con palabras claras si no hay cámara o la usa otro programa (una vez por cambio) y,
        si el hilo de la cámara murió sin que nadie lo pidiera, crea otro."""
        cam = self.camara
        estado = getattr(cam, "estado", "")
        clave = AVISOS_CAMARA.get(estado)
        if estado == "FUNCIONANDO":
            self._aviso_camara = None
        elif clave is not None and clave != self._aviso_camara:
            self._aviso_camara = clave
            self.salida.soltar_todo("cámara: " + estado)
            self.avisos.put(Aviso(clave))
        if not self._camara_propia or self._parar.is_set():
            return
        if self._t_camara is not None and t - self._t_camara < REVISAR_CAMARA_S:
            return
        self._t_camara = t
        try:
            muerta = getattr(cam, "ident", None) is not None and not cam.is_alive() \
                and not getattr(cam, "_parar").is_set()
        except Exception:  # noqa: BLE001
            muerta = False
        if muerta:
            log.error("El hilo de la cámara se detuvo solo; se abre otra vez")
            try:
                self.camara = self._nueva_camara()
                self.camara.start()
                self._numero = 0
            except Exception:  # noqa: BLE001
                log.exception("No se pudo volver a abrir la cámara")

    def revisar_monitor(self, t: float, forzar: bool = False):
        """Relee el monitor (conectar un televisor, cambiar la resolución o la escala). Si cambió,
        rehace el mapeo y la permanencia conservando la calibración."""
        if not self._monitor_auto:
            return
        if not forzar and self._t_monitor is not None and t - self._t_monitor < REVISAR_MONITOR_S:
            return
        self._t_monitor = t
        try:
            from .sistema import pantallas
            nuevo = pantallas.elegir((self.cfg.get("pantalla") or {}).get("monitor", "principal"))
        except Exception:  # noqa: BLE001
            log.exception("No se pudo releer el monitor")
            return
        if nuevo is None or nuevo == self.monitor:
            return
        log.info("Cambió la pantalla: %s -> %s", self.monitor, nuevo)
        self.monitor = nuevo
        if hasattr(self.salida, "actualizar_pantalla"):
            try:
                self.salida.actualizar_pantalla()
            except Exception:  # noqa: BLE001
                log.exception("No se pudo leer el escritorio")
        if self.maquina is not None:
            self._aplicar(self.maquina.cambiar_monitor(t, nuevo))

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
            # suelta todo y apaga lo que alcanzó a abrir (cámara, detector): el reintento del
            # vigilante tiene que poder abrir la cámara otra vez
            self.cerrar()
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
        self.latido = time.monotonic()
        self._atender_ordenes()
        ahora = self.reloj()
        self._vigilar_camara(ahora)
        self.revisar_monitor(ahora)
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
        if not self._toca_procesar(cuadro.t_captura):
            return                      # más cuadros de los que hace falta procesar
        try:
            cara = self.detector.procesar(cuadro.imagen, cuadro.t_captura)
        except Exception as e:  # noqa: BLE001
            log.exception("Error en el detector de la cara")
            self._aplicar(self.maquina.por_error(cuadro.t_captura, e))
            self._revisar_fatal()
            return
        self._paso(cuadro.t_captura, cara, cuadro)

    def _toca_procesar(self, tc: float) -> bool:
        """Limitador con horario (ronda 3): se procesa si llegó la hora del siguiente cuadro y la
        hora avanza un periodo cada vez. Antes se comparaba con el último procesado y una cámara
        de 30 cuadros/s quedaba en 15 (se saltaba uno de cada dos)."""
        try:
            fps_max = float(self.cfg["camara"].get("fps_proceso", 20))
        except (TypeError, ValueError):
            fps_max = 20.0
        if not fps_max > 0:
            return True
        periodo = 1.0 / fps_max
        prox = self._t_proximo
        if prox is not None and tc < prox - 0.004:
            if prox - tc <= 2.0 * periodo:
                return False
            prox = None                 # el reloj de la cámara volvió atrás: horario nuevo
        base = tc if prox is None else prox
        self._t_proximo = max(base + periodo, tc - periodo)
        return True

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
        self._publicar(res.vista, cara, io_fr, centro, t, cuadro)
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
            self.revisar_monitor(t, forzar=True)
        elif nombre == "calibrar":
            if arg:
                self._aplicar(m.iniciar_calibracion(t))
            else:
                self._aplicar(m.terminar_calibracion(t, o[2] if len(o) > 2 else None,
                                                     o[3] if len(o) > 3 else None))
        elif nombre == "soltar":
            self.salida.soltar_todo(arg or "orden")
            self._aplicar(m.cancelar_lupa(t))          # 1.1: la lupa abierta se cierra sin clic
        # ---- 1.1 paquete A: lupa ----
        elif nombre == "lupa_cerrar":
            self._aplicar(m.cancelar_lupa(t))
        elif nombre == "lupa_fallo":
            self._aplicar(m.lupa_fallo(t))
        elif nombre == "camara_perdida":
            self.salida.soltar_todo("cámara perdida")       # el aviso lo da _vigilar_camara
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

    def _publicar(self, vista: Vista, cara, io_fr, centro, t: float, cuadro=None):
        imagen = None
        if cuadro is not None and (self.cfg.get("comodidad") or {}).get("mostrar_video"):
            try:
                imagen = cuadro.imagen[::2, ::2].copy()     # la mitad: basta para la ventana
            except Exception:  # noqa: BLE001
                imagen = None
        v = VistaMotor(maquina=vista, fps=self.stats.fps,
                       latencia_ms=self.stats.latencias[-1] if self.stats.latencias else 0.0,
                       puntos=None if cara is None else cara.normalizados, io_fraccion=io_fr, centro_cara=centro,
                       camara=getattr(self.camara, "estado", ""), ultima_accion=self.ultima_accion,
                       simulada=bool(getattr(self.salida, "simulada", False)), t=t, imagen=imagen)
        try:
            self.vistas.get_nowait()
        except queue.Empty:
            pass
        try:
            self.vistas.put_nowait(v)
        except queue.Full:
            pass
