"""La aplicación completa (secciones 2.1, 3.1, 6 y 8): une la configuración, la salida, el motor,
los atajos del cuidador, los sonidos, la voz (si existe) y todas las ventanas.

Hilo de la interfaz (este): cada ~33 ms toma la última vista del motor, atiende sus avisos
(``Elegir``, ``Sonido``, ``Hablar``, ``Aviso``) y los atajos, pinta las ventanas y, cada 250 ms,
publica al motor los botones propios en coordenadas de pantalla.

Seguridad (sección 8):
- ``soltar_todo`` en atexit, señales, al salir, al abrir Opciones y cuando falla algo;
- si el motor deja de publicar 2 s (o se cae), se suelta todo, se avisa y se reinicia la
  detección hasta 3 veces;
- el atajo de pausa del cuidador suelta todo en el propio hilo de atajos.

Teclado en pantalla (Parte 4): ``ui/teclado.py`` con ``VentanaTeclado(root, app)`` (``cerrar()``,
``submodo_inicial()``, ``actualizar(vista)``, ``reconstruir()``). La predicción de palabras y las
frases rápidas se cargan una vez (``obtener_prediccion``, ``obtener_frases``) y se comparten con el
editor de frases (``abrir_editor_frases``). La voz: ``sistema/voz.py`` (``Voz(cfg_voz)``).
"""
from __future__ import annotations

import atexit
import copy
import ctypes
import json
import logging
import queue
import signal
import sys
import time

from .. import constantes as K
from .. import registro as registro_mod
from ..acciones import Aviso, Elegir, Hablar, Sonido
from ..config import Configuracion, validar
from ..version import VERSION
from .objetivos import Registro
from .textos import t, texto_aviso

log = logging.getLogger("lycan")

REFRESCO_MS = 33
PUBLICAR_CADA_S = 0.25
MOTOR_CAIDO_S = 2.0             # sin vistas este tiempo: se suelta todo (por si acaso) y se mira el latido
MOTOR_COLGADO_S = 12.0          # hilo vivo pero sin latido este tiempo: trabado, se reinicia
MAX_REINICIOS = 3
REINICIOS_VENTANA_S = 300.0     # se rinde con 3 reinicios en 5 minutos (no en toda la sesión)...
REINTENTO_RENDIDO_S = 60.0      # ...pero nunca para siempre: vuelve a intentar cada minuto
ESPERA_MOTOR_VIEJO_S = 10.0     # antes de crear otro motor, el viejo suelta la cámara y FaceMesh
GUARDAR_PALABRAS_S = 300.0      # las palabras aprendidas se guardan cada 5 minutos si cambiaron
AVISOS_POR_VUELTA = 60
# avisos que no se muestran (o que ya se ven en el estado grande)
AVISOS_CALLADOS = {"pausa", "activo", "teclado", "sobre_ventana", "arrastre_fin"}


class App:
    def __init__(self, args, fabrica_motor=None, salida=None, sistema: bool = True, cfg: Configuracion | None = None):
        """``fabrica_motor(cfg, salida) -> Motor``: las pruebas la usan para un motor sin cámara.
        ``sistema=False``: no toca Windows (sin atajos, sin registro de arranque, sin foco)."""
        self.args = args
        self.sistema = sistema
        self.cerrando = False
        self.root = None
        self.ventana = None
        self.barra = None
        self.indicador = None
        self.borde = None
        self.flotante = None
        self.teclado = None
        self.calibracion = None
        self.opciones = None
        self.ayuda = None
        self.asistente = None
        self.atajos = None
        self.voz = None
        self.prediccion = None
        self.frases = None
        self.editor = None
        self.lupa = None                       # 1.1: ventana de la lupa abierta (o None)
        self._t_lupa = None
        # 1.1 paquete B: emergencia (pantalla roja, alarma y voz)
        self.emergencia = None                 # VentanaEmergencia abierta (o None)
        self._emergencia_local = False         # abierta por la interfaz con el motor caído
        self._t_emergencia = None
        self._plan_alarma = None
        self._que_suena = None
        self._ciclo_voz = 0
        self._alarma_callada = False
        self._loop_alarma = None
        self.alarma = None                     # se crea la primera vez (sistema/alarma.py)
        self._avisado_tec_minimizar = False
        self.ultima_vista = None
        self.oyentes_vista: list = []
        self.cola_atajos: queue.Queue = queue.Queue()
        self.reinicios = 0
        self._t_reinicios: list = []           # cuándo fue cada reinicio (ventana de 5 min)
        self._t_ult_vuelta = None              # última vuelta de la interfaz (para notar suspensión)
        self._t_guardar_palabras = time.monotonic()
        self.motor_rendido = False
        self._t_rendido = None
        self._motor_viejo = None               # (motor, desde) que se está esperando que termine
        self._soltado_lento = False
        self.ultima_externa = None
        self._t_ult_vista = time.monotonic()
        self._t_publicar = 0.0
        self._t_descanso = time.monotonic()
        self._hwnd_atravesables: set = set()
        self.cfg = cfg or Configuracion()
        if cfg is None:
            self.cfg.cargar()
        self.simulada = bool(getattr(args, "simular", False))
        if salida is None:
            from ..salida import crear
            salida = crear(self.simulada)
        self.salida = salida
        self._fabrica_motor = fabrica_motor or self._motor_normal
        # un botón que quedó abajo de una sesión cerrada a la fuerza se suelta antes de empezar
        try:
            self.salida.soltar_botones_huerfanos("arranque")
        except Exception:  # noqa: BLE001
            log.exception("No se pudieron revisar los botones al arrancar")
        atexit.register(self._soltar_seguro, "atexit")
        if sistema:
            for nombre in ("SIGINT", "SIGBREAK", "SIGTERM"):
                sig = getattr(signal, nombre, None)
                if sig is not None:
                    try:
                        signal.signal(sig, self._senal)
                    except (ValueError, OSError):
                        pass
            self._preparar_salida()
        from ..sistema.sonidos import Sonidos
        self.sonidos = Sonidos(bool(self.cfg.datos["comodidad"].get("sonidos", True)), arrancar=sistema)
        self.registro = Registro(publicar=self._publicar_objetivos, orden=self.orden)
        self.motor = self._crear_motor()
        registro_mod.instalar_ganchos(self._al_fallar)

    # ------------------------------------------------------------ motor y salida
    def _config_motor(self) -> dict:
        c = copy.deepcopy(self.cfg.datos)
        if getattr(self.args, "camara", None) is not None:
            c["camara"]["indice"] = int(self.args.camara)       # solo para esta sesión
        return c

    def _motor_normal(self, cfg, salida):
        from ..motor import Motor
        camara = None
        if getattr(self.args, "camara_falsa", False):
            from ..captura import CamaraFalsa
            camara = CamaraFalsa(generador=_generador_cara_dibujada())
        return Motor(cfg, salida, camara=camara)

    def _crear_motor(self):
        m = self._fabrica_motor(self._config_motor(), self.salida)
        if getattr(self, "registro", None) is not None:
            self.registro._ultimo = None           # el motor nuevo necesita los botones otra vez
        return m

    def _preparar_salida(self):
        """En Windows: no hacer clic en ventanas propias (por PID, sin contar las atravesables)
        y avisar si la ventana activa es de administrador."""
        try:
            from ..sistema import ventanas_win as vw
            self.salida.es_propia_en = self._es_propia_en
            self.salida.revisar_destino = lambda: "administrador" if vw.primer_plano_bloqueado() else None
        except Exception:  # noqa: BLE001
            log.exception("No se pudo preparar la salida")

    def _es_propia_en(self, x, y) -> bool:
        from ..sistema import ventanas_win as vw
        hwnd = vw.ventana_en(x, y)
        if not hwnd:
            return False
        try:
            raiz = ctypes.windll.user32.GetAncestor(hwnd, 2) or hwnd     # GA_ROOT
        except Exception:  # noqa: BLE001
            raiz = hwnd
        if raiz in self._hwnd_atravesables:
            # el indicador junto al cursor no cuenta: se miran los rectángulos propios publicados
            # (este código corre en el hilo del motor: aquí nunca se llama a tkinter)
            return any(o.contiene(x, y) for o in self.registro.ultimos if not o.elegible)
        return vw.es_propia_en(x, y)

    def _soltar_seguro(self, motivo: str):
        try:
            self.salida.soltar_todo(motivo)
        except Exception:  # noqa: BLE001
            pass

    def _senal(self, signum, _frame):
        self._soltar_seguro(f"señal {signum}")
        if self.root is not None:
            try:
                self.root.after(0, self.salir_seguro)
                return
            except Exception:  # noqa: BLE001
                pass
        raise SystemExit(1)

    def _al_fallar(self, exc):
        self._soltar_seguro("error no atrapado")
        self.orden("error_externo", exc)

    def _publicar_objetivos(self, objetivos):
        self.motor.poner_objetivos(objetivos)

    # ------------------------------------------------------------ órdenes
    def orden(self, nombre, *args):
        # 1.1 paquete B: AYUDA y «Ya me atendieron» con el ratón. Si la detección está caída, la
        # interfaz abre (o cierra) la emergencia sin esperar al motor.
        if nombre == "elegir" and args and args[0] in K.IDS_EMERGENCIA and not self._motor_funciona():
            self.abrir_emergencia("cuidador", local=True)
            return
        if nombre == "elegir" and args and args[0] == K.ID_ATENDIDO:
            self._callar_alarma()
            if self._emergencia_local or not self._motor_funciona():
                self.cerrar_emergencia()
                return
        if nombre == "config" and args and getattr(self.args, "camara", None) is not None:
            try:
                args[0]["camara"]["indice"] = int(self.args.camara)
            except (KeyError, TypeError, IndexError):
                pass
        self.motor.orden(nombre, *args)

    def pausar(self):
        self.orden("pausar", "botón Pausar")

    def recentrar(self):
        self.orden("recentrar")

    def guardar_config(self, datos: dict | None = None) -> bool:
        if getattr(self.args, "prueba_segundos", 0) and getattr(self.args, "simular", False) and self.cfg.ruta.exists():
            return True     # una prueba automática no cambia la configuración real
        if self.cfg.guardar_seguro(datos):
            return True
        self.mostrar_aviso(t("aviso_config_solo_lectura") if self.cfg.solo_lectura else t("aviso_no_guardo"), 10)
        return False

    def aplicar_config(self, datos: dict, antes: dict | None = None):
        """Opciones guardadas: se guarda, se le pasa al motor y se rehacen las ventanas que dependen
        de la apariencia."""
        antes = antes or self.cfg.datos
        self.cfg.datos = validar(datos)
        self.guardar_config()
        self.orden("config", self._config_motor())
        self.sonidos.activos = bool(self.cfg.datos["comodidad"].get("sonidos", True))
        # los atajos también: el globo de «Pausar» dice el atajo que está puesto
        apariencia = any(antes.get(k) != self.cfg.datos.get(k) for k in ("comodidad", "barra", "atajos"))
        if apariencia and self.root is not None:
            try:
                if self.ventana is not None:
                    self.ventana.reconstruir()
                if self.barra is not None:
                    self.barra.construir()
            except Exception:  # noqa: BLE001
                log.exception("No se pudieron rehacer las ventanas")
        elif self.ventana is not None:
            self.ventana._mostrar_barras()
        if antes.get("atajos") != self.cfg.datos.get("atajos"):
            self.reiniciar_atajos()
        if self.voz is not None and hasattr(self.voz, "configurar"):
            try:
                self.voz.configurar(self.cfg.datos["voz"])
            except Exception:  # noqa: BLE001
                pass
        if self.prediccion is not None:
            self.prediccion.aprender_activo = bool(self.cfg.datos["teclado"].get("aprender", True))
        self._config_teclado(antes)
        self._t_descanso = time.monotonic()

    def _config_teclado(self, antes: dict):
        """Opciones del teclado cambiadas: se rehace el teclado abierto y se pone el submodo que
        corresponde ("solo comunicación" abre el teclado y lo deja abierto)."""
        nuevo = self.cfg.datos
        cambio = any(antes.get(k) != nuevo.get(k) for k in ("teclado", "comodidad", "barra"))
        solo = bool(nuevo["teclado"].get("solo_comunicacion"))
        if self.teclado is not None:
            if cambio and hasattr(self.teclado, "reconstruir"):
                try:
                    self.teclado.reconstruir()
                except Exception:  # noqa: BLE001
                    log.exception("No se pudo rehacer el teclado")
            f = getattr(self.teclado, "submodo_inicial", None)
            if f is not None and cambio:
                self.orden("submodo", f())
        elif solo and self.root is not None:
            self.alternar_teclado()
        elif bool(antes.get("teclado", {}).get("solo_comunicacion")) and not solo:
            self.orden("submodo", K.NORMAL)

    def poner_al_encender(self, si: bool):
        if not self.sistema:
            return
        from ..sistema import inicio
        if not inicio.poner(si):
            self.mostrar_aviso(t("aviso_no_guardo"), 8)

    # ------------------------------------------------------------ ventanas
    def mostrar_aviso(self, texto: str, segundos: float = 6.0):
        if not texto:
            return
        if self.ventana is not None:
            self.ventana.mostrar_aviso(texto, segundos)
        # con el teclado abierto la ventana principal queda tapada: el aviso se ve en el teclado
        tec = self.teclado
        if tec is not None and getattr(tec, "win", None) is not None and hasattr(tec, "mostrar_aviso"):
            try:
                tec.mostrar_aviso(texto, segundos)
            except Exception:  # noqa: BLE001
                log.exception("No se pudo mostrar el aviso en el teclado")

    def _ventana_viva(self, w) -> bool:
        try:
            return w is not None and w.win.winfo_exists()
        except Exception:  # noqa: BLE001
            return False

    def _al_frente(self, w):
        try:
            w.win.deiconify()
            w.win.lift()
        except Exception:  # noqa: BLE001
            pass
        return w

    def abrir_opciones(self):
        if self._ventana_viva(self.opciones):
            return self._al_frente(self.opciones)
        from .opciones import VentanaOpciones
        self.opciones = VentanaOpciones(self.root, self)
        return self.opciones

    def opciones_cerradas(self, o):
        if self.opciones is o:
            self.opciones = None

    def abrir_ayuda(self):
        if self._ventana_viva(self.ayuda):
            return self._al_frente(self.ayuda)
        from .ayuda import VentanaAyuda
        self.ayuda = VentanaAyuda(self.root, self)
        return self.ayuda

    def ayuda_cerrada(self, a):
        if self.ayuda is a:
            self.ayuda = None

    def abrir_asistente(self):
        if self._ventana_viva(self.asistente):
            return self._al_frente(self.asistente)
        from .asistente import Asistente
        self.asistente = Asistente(self.root, self)
        return self.asistente

    def asistente_cerrado(self, a):
        if self.asistente is a:
            self.asistente = None

    def abrir_calibracion(self, empezar_ya: bool = False):
        if self._ventana_viva(self.calibracion):
            return self._al_frente(self.calibracion)
        from .calibracion import VentanaCalibracion
        self.calibracion = VentanaCalibracion(self.root, self, empezar_ya=empezar_ya)
        return self.calibracion

    def calibracion_cerrada(self, c):
        if self.calibracion is c:
            self.calibracion = None

    # ------------------------------------------------------------ teclado: palabras y frases
    def obtener_prediccion(self):
        """La predicción de palabras se carga una vez (20 000 palabras) y se comparte."""
        if self.prediccion is None:
            from ..prediccion import Prediccion, ruta_palabras_usuario
            self.prediccion = Prediccion(ruta_usuario=ruta_palabras_usuario(),
                                         aprender=bool(self.cfg.datos["teclado"].get("aprender", True)))
            if self.prediccion.aviso:
                self.mostrar_aviso(t(f"aviso_{self.prediccion.aviso}"), 8)
        return self.prediccion

    def obtener_frases(self):
        if self.frases is None:
            from ..frases import Frases, ruta_frases
            self.frases = Frases(ruta_frases())
            self.frases.cargar()
            if self.frases.aviso:
                self.mostrar_aviso(t(f"aviso_{self.frases.aviso}"), 8)
        return self.frases

    def abrir_editor_frases(self):
        if self._ventana_viva(self.editor):
            return self._al_frente(self.editor)
        from .editor_frases import EditorFrases
        self.editor = EditorFrases(self.root, self)
        return self.editor

    def editor_cerrado(self, e):
        if self.editor is e:
            self.editor = None

    def alternar_teclado(self):
        if self.teclado is not None:
            if getattr(self.teclado, "minimizado", False):
                return self.restaurar_teclado()          # 1.1: vuelve con el texto como estaba
            if self.cfg.datos["teclado"].get("solo_comunicacion"):
                return self._al_frente(self.teclado)     # en "solo comunicación" nunca se cierra
            self.cerrar_teclado()
            return
        try:
            from .teclado import VentanaTeclado
        except ImportError:
            self.mostrar_aviso(t("aviso_teclado_no_disponible"))
            return
        self._barra_con_teclado(True)       # antes de que el teclado mida el espacio libre
        try:
            self.teclado = VentanaTeclado(self.root, self)
        except Exception:  # noqa: BLE001
            log.exception("No se pudo abrir el teclado")
            self.teclado = None
            self._barra_con_teclado(False)
            self.mostrar_aviso(t("aviso_error"))
            return
        sub = K.TECLADO
        f = getattr(self.teclado, "submodo_inicial", None)
        if f is not None:
            try:
                sub = f() or K.TECLADO
            except Exception:  # noqa: BLE001
                sub = K.TECLADO
        if not getattr(self.teclado, "gestiona_submodo", False):
            self.orden("submodo", sub)

    def cerrar_teclado(self):
        tec, self.teclado = self.teclado, None
        if tec is None:
            return
        self._barra_con_teclado(False)
        f = getattr(tec, "cerrar", None)
        try:
            if f is not None:
                f()
            elif hasattr(tec, "win"):
                tec.win.destroy()
        except Exception:  # noqa: BLE001
            pass
        if not self.cfg.datos["teclado"].get("solo_comunicacion"):
            self.orden("submodo", K.NORMAL)

    def teclado_cerrado(self, tec=None):
        """El teclado avisa que se cerró solo."""
        if tec is None or tec is self.teclado:
            self.teclado = None
            self._barra_con_teclado(False)
            if not self.cfg.datos["teclado"].get("solo_comunicacion"):
                self.orden("submodo", K.NORMAL)

    # ---- 1.1 paquete A: teclado minimizado ----
    def _barra_con_teclado(self, abierto: bool):
        f = getattr(self.barra, "poner_teclado", None)
        if f is None:
            return
        try:
            f(abierto)
        except Exception:  # noqa: BLE001
            log.exception("No se pudo rehacer la barra")

    def restaurar_teclado(self):
        tec = self.teclado
        if tec is not None and hasattr(tec, "restaurar"):
            tec.restaurar()
        return tec

    def teclado_minimizado(self, tec=None):
        """El teclado se escondió (con su pestaña): la barra vuelve a tener todos sus botones."""
        self._barra_con_teclado(False)
        if not self._avisado_tec_minimizar:
            self._avisado_tec_minimizar = True
            self.mostrar_aviso(t("globo_tec_minimizar"), 6)

    def teclado_restaurando(self, tec=None):
        self._barra_con_teclado(True)

    # ---- 1.1 paquete A: lupa ----
    def _evento_lupa(self, ident: str) -> bool:
        from .. import lupa as L
        if ident.startswith(L.PREFIJO_ABRIR):
            self.abrir_lupa(ident)
            return True
        if ident == L.ID_CERRAR:
            self.cerrar_lupa()
            return True
        return False

    def abrir_lupa(self, ident: str, capturar_fn=None):
        """La máquina abrió la lupa: se captura la zona y se muestra agrandada. Si algo falla,
        se avisa a la máquina (vuelve a NORMAL sin clic)."""
        from .. import lupa as L
        self.cerrar_lupa()
        datos = L.leer_id(ident)
        if datos is None or self.root is None:
            self.orden("lupa_fallo")
            return None
        zona, ventana, imagen = datos
        try:
            from .lupa import VentanaLupa
            self.lupa = VentanaLupa(self.root, self, zona, ventana, imagen,
                                    capturar_fn=capturar_fn or getattr(self, "capturar_lupa", None))
            self._t_lupa = time.monotonic()
        except Exception:  # noqa: BLE001
            log.exception("No se pudo agrandar la zona de la lupa")
            self.lupa = None
            self.orden("lupa_fallo")
        return self.lupa

    def cerrar_lupa(self, avisar_motor: bool = False):
        lp, self.lupa = self.lupa, None
        if lp is not None:
            try:
                lp.cerrar()
            except Exception:  # noqa: BLE001
                log.exception("No se pudo cerrar la lupa")
        if avisar_motor:
            self.orden("lupa_cerrar")

    def _revisar_lupa(self, m):
        """Por si se pierde un aviso: la ventana de la lupa no queda abierta si la máquina ya no
        está en LUPA (pausa, sin cara, calibración, Opciones...)."""
        lp = self.lupa
        if lp is None:
            return
        if m is not None and m.submodo == K.LUPA and m.estado in (K.ACTIVO, K.SIN_CARA):
            lp.visto = True
            return
        if lp.visto or (self._t_lupa is not None and time.monotonic() - self._t_lupa > 1.5):
            self.cerrar_lupa()

    def mostrar_ventana(self):
        if self.root is None:
            return
        try:
            self.root.deiconify()
            self.root.lift()
            self.root.attributes("-topmost", True)
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------ emergencia (1.1 paquete B)
    def _motor_funciona(self) -> bool:
        m = self.motor
        if m is None or self.motor_rendido:
            return False
        try:
            return bool(m.is_alive())
        except Exception:  # noqa: BLE001
            return False

    def pedir_ayuda(self, origen: str = "cuidador"):
        """AYUDA desde la interfaz (el barrido del teclado). La pide la máquina; con la detección
        caída se abre la pantalla roja directamente."""
        if self._motor_funciona():
            self.orden("ayuda", origen)
        else:
            self.abrir_emergencia(origen, local=True)

    def apagar_emergencia(self, origen: str = "cuidador"):
        """Esc en la pantalla roja: la alarma se calla ya y la máquina vuelve a como estaba."""
        self._callar_alarma()
        if self.emergencia is not None and (self.emergencia.prueba or self._emergencia_local
                                            or not self._motor_funciona()):
            self.cerrar_emergencia()
            return
        self.orden("atendido", origen)

    def _nueva_alarma(self, volumen):
        if not self.sistema or self.simulada:
            from ..sistema.alarma import AlarmaMuda
            return AlarmaMuda(volumen)          # pruebas, --simular y capturas: nunca suena
        from ..sistema.alarma import Alarma
        return Alarma(volumen)

    def _obtener_alarma(self, volumen=None):
        vol = self.cfg.datos.get("emergencia", {}).get("volumen", 100) if volumen is None else volumen
        if self.alarma is None:
            self.alarma = self._nueva_alarma(vol)
        self.alarma.volumen = vol
        return self.alarma

    def _callar_alarma(self):
        """Seguro desde cualquier hilo (el atajo del cuidador la calla en el hilo de atajos)."""
        self._alarma_callada = True
        a = self.alarma
        if a is not None:
            try:
                a.detener()
            except Exception:  # noqa: BLE001
                log.exception("No se pudo detener la alarma")

    def _monitor_emergencia(self) -> tuple:
        """El monitor donde está el puntero (el del mapeo); si no se sabe, el principal."""
        mon = getattr(getattr(getattr(self.motor, "maquina", None), "mapeo", None), "monitor", None)
        if mon is None:
            mon = getattr(self.motor, "monitor", None)
        try:
            if mon is not None:
                return tuple(int(v) for v in mon.rect)
        except (AttributeError, TypeError, ValueError):
            pass
        try:
            return (0, 0, int(self.root.winfo_screenwidth()), int(self.root.winfo_screenheight()))
        except Exception:  # noqa: BLE001
            return (0, 0, 1366, 768)

    def _hay_voz(self) -> bool:
        if self.voz is None and self.sistema and not self.simulada:
            self._crear_voz()
        return self.voz is not None and getattr(self.voz, "voz_espanol", True) is not False

    def abrir_emergencia(self, origen: str = "", local: bool = False, prueba: bool = False, volumen=None):
        """Abre la pantalla roja y arranca la alarma y la voz. ``prueba``: 3 segundos, sin voz y
        sin cambiar el estado del programa."""
        if self.root is None or self.cerrando:
            return None
        e = self.emergencia
        if e is not None and e.viva():
            if e.prueba and not prueba:
                self.cerrar_emergencia(avisar=False)   # una emergencia de verdad reemplaza la prueba
            else:
                return e
        from .. import emergencia as E
        from .emergencia import VentanaEmergencia
        try:
            self.cerrar_lupa()
        except Exception:  # noqa: BLE001
            pass
        try:
            self.emergencia = VentanaEmergencia(self.root, self, self._monitor_emergencia(), prueba=prueba,
                                                al_cerrar=self._emergencia_cerrada)
        except Exception:  # noqa: BLE001
            log.exception("No se pudo abrir la pantalla de emergencia")
            self.emergencia = None
        self._emergencia_local = bool(local) and not prueba
        self._t_emergencia = time.monotonic()
        c = self.cfg.datos.get("emergencia", {})
        ahora = time.monotonic()
        if prueba:
            self._plan_alarma = E.PlanAlarma(ahora, repetir_voz=False)
        else:
            mensaje = E.mensaje_voz(self.cfg.datos)
            self._mensaje_emergencia = mensaje
            self._plan_alarma = E.PlanAlarma(ahora, bool(c.get("repetir_voz", True)), c.get("repetir_s", 12),
                                             E.duracion_voz(mensaje), hay_voz=self._hay_voz())
            log.info("Emergencia: pantalla roja y alarma (%s)", origen or "botón")
        self._obtener_alarma(volumen)
        self._que_suena = None
        self._ciclo_voz = 0
        self._alarma_callada = False
        self._paso_alarma()
        return self.emergencia

    def probar_alarma(self, volumen=None):
        """Opciones › Emergencia › «Probar la alarma (3 segundos)»."""
        return self.abrir_emergencia("prueba", prueba=True, volumen=volumen)

    def _paso_alarma(self):
        """Cada 200 ms con la pantalla roja abierta: alarma, voz o silencio según el plan."""
        self._loop_alarma = None
        e, plan = self.emergencia, self._plan_alarma
        if e is None or plan is None or not e.viva() or self.cerrando:
            return
        from .. import emergencia as E
        ahora = time.monotonic()
        que = plan.que_toca(ahora)
        alarma = self.alarma
        if self._alarma_callada:
            que = E.SILENCIO
        if que != self._que_suena:
            self._que_suena = que
            if que == E.ALARMA and alarma is not None:
                try:
                    ok = alarma.tocar()
                except Exception:  # noqa: BLE001
                    log.exception("La alarma falló")
                    ok = False
                if not ok:
                    plan.hay_alarma = False
                    self._que_suena = E.SILENCIO
                    self.mostrar_aviso(t("aviso_alarma_falla"), 10)
            elif alarma is not None:
                try:
                    alarma.detener()
                except Exception:  # noqa: BLE001
                    log.exception("No se pudo detener la alarma")
        if que == E.VOZ:
            n = plan.ciclo(ahora)
            if n != self._ciclo_voz:
                self._ciclo_voz = n
                self._decir_emergencia(getattr(self, "_mensaje_emergencia", ""))
        try:
            self._loop_alarma = self.root.after(200, self._paso_alarma)
        except Exception:  # noqa: BLE001
            self._loop_alarma = None

    def _decir_emergencia(self, texto: str):
        if not texto or self.voz is None:
            return
        try:
            f = getattr(self.voz, "hablar", None)
            if f is not None:
                f(texto, urgente=True) if _acepta_urgente(f) else f(texto)
        except Exception:  # noqa: BLE001
            log.exception("La voz de la emergencia falló")

    def _emergencia_cerrada(self, ventana):
        """La ventana se cerró (prueba terminada, Esc en la prueba o cerrar_emergencia)."""
        if self.emergencia is ventana:
            self.emergencia = None
            self._plan_alarma = None
            self._emergencia_local = False
            self._callar_alarma()

    def cerrar_emergencia(self, avisar: bool = True):
        e = self.emergencia
        self._callar_alarma()
        if self._loop_alarma is not None and self.root is not None:
            try:
                self.root.after_cancel(self._loop_alarma)
            except Exception:  # noqa: BLE001
                pass
            self._loop_alarma = None
        if e is None:
            return
        prueba = e.prueba
        self.emergencia = None
        self._plan_alarma = None
        self._emergencia_local = False
        try:
            e.cerrar()
        except Exception:  # noqa: BLE001
            log.exception("No se pudo cerrar la pantalla de emergencia")
        if avisar and not prueba:
            self.mostrar_aviso(t("aviso_emergencia_fin"), 5)

    def _revisar_emergencia(self, m):
        """Por si se pierde un aviso: la pantalla roja sigue a la máquina (se abre si la máquina
        está en emergencia y se cierra si ya no lo está), salvo la de prueba o la abierta con la
        detección caída."""
        if m is None or self.motor_rendido:
            return
        e = self.emergencia
        viva = e is not None and e.viva()
        if getattr(m, "emergencia", False):
            if not viva:
                self.abrir_emergencia("vista")
        elif viva and not e.prueba and not self._emergencia_local and self._t_emergencia is not None \
                and time.monotonic() - self._t_emergencia > 1.5:
            self.cerrar_emergencia()

    # ------------------------------------------------------------ voz
    def hablar(self, texto: str, urgente: bool = False):
        if urgente:
            self.sonidos.tocar("alerta")
        if self.voz is None and self.sistema:
            self._crear_voz()
        ok = False
        if self.voz is not None:
            try:
                f = getattr(self.voz, "hablar", None)
                if f is not None:
                    r = f(texto, urgente=urgente) if _acepta_urgente(f) else f(texto)
                    ok = r is not False
            except Exception:  # noqa: BLE001
                log.exception("La voz falló")
        if not ok:
            self._mostrar_no_dicho(texto)
        elif getattr(self.voz, "voz_espanol", None) is False:
            # hay voz, pero no en español: se avisa una vez y el texto se ve en grande siempre
            if not getattr(self, "_avisado_sin_voz", False):
                self._avisado_sin_voz = True
                self.mostrar_aviso(t("aviso_sin_voz"), 10)
            else:
                self._mostrar_no_dicho(texto, avisar=False)

    def _mostrar_no_dicho(self, texto: str, avisar: bool = True):
        """Lo que la voz no dijo se muestra entero y en grande: con el teclado abierto, sobre la caja
        del texto (con la letra ajustada al largo) y un aviso corto en la franja; si no, en la
        ventana principal (ronda 3: antes iba a la franja, de una fila, y se cortaba)."""
        tec = self.teclado
        if tec is not None and getattr(tec, "win", None) is not None and hasattr(tec, "mostrar_grande"):
            try:
                tec.mostrar_grande(texto, 12)
                if avisar:
                    tec.mostrar_aviso(t("aviso_no_dicho"), 6)
                if self.ventana is not None:
                    self.ventana.mostrar_aviso(texto, 10)
                return
            except Exception:  # noqa: BLE001
                log.exception("No se pudo mostrar en grande lo que no se dijo")
        self.mostrar_aviso(texto, 10)

    def _revisar_voz(self):
        """Frases que la voz no pudo decir (falló después de arrancar): se muestran en grande."""
        cola = getattr(self.voz, "fallidos", None)
        if cola is None:
            return
        while True:
            try:
                texto = cola.get_nowait()
            except queue.Empty:
                break
            except Exception:  # noqa: BLE001
                break
            self._mostrar_no_dicho(texto)

    def _crear_voz(self):
        try:
            from ..sistema import voz as modulo
        except ImportError:
            self.voz = None
            return
        try:
            clase = getattr(modulo, "Voz", None)
            self.voz = clase(self.cfg.datos["voz"]) if clase is not None else modulo
        except Exception:  # noqa: BLE001
            log.exception("No se pudo preparar la voz")
            self.voz = None

    # ------------------------------------------------------------ atajos
    def _arrancar_atajos(self):
        if not self.sistema or getattr(self.args, "sin_atajos", False):
            return
        try:
            from ..sistema.atajos import HiloAtajos
            self.atajos = HiloAtajos(self.cfg.datos["atajos"], self.cola_atajos,
                                     directos={"pausar": lambda: self.motor.atajo("pausar"),
                                               "salir": lambda: self.motor.atajo("salir"),
                                               # 1.1: la alarma se calla ya, en el hilo de atajos
                                               "emergencia": self._atajo_emergencia})
            self.atajos.start()
            self.root.after(800, self._avisar_atajos)
        except Exception:  # noqa: BLE001
            log.exception("No se pudieron registrar los atajos")
            self.atajos = None

    def reiniciar_atajos(self):
        if self.atajos is not None:
            try:
                self.atajos.detener()
                self.atajos.join(timeout=1.0)
            except Exception:  # noqa: BLE001
                pass
            self.atajos = None
        self._arrancar_atajos()

    def _avisar_atajos(self):
        if self.atajos is not None and self.atajos.fallidos:
            self.mostrar_aviso(t("aviso_atajos") + "\n" + "\n".join(txt for _, txt in self.atajos.fallidos), 10)

    def _atajo_emergencia(self):
        """En el hilo de atajos: callar la alarma y avisar a la máquina (corto y seguro)."""
        self._callar_alarma()
        self.motor.atajo("emergencia")

    def _atender_atajo(self, nombre: str):
        if nombre == "emergencia":
            # la máquina ya recibió «atendido» (hilo de atajos); con el motor caído, la prueba o la
            # pantalla abierta por la interfaz, se cierra aquí
            e = self.emergencia
            if e is not None and (e.prueba or self._emergencia_local or not self._motor_funciona()):
                self.cerrar_emergencia()
            return
        if nombre == "pausar":
            # ya se atendió en el hilo de atajos (suelta todo al instante); si la detección se
            # había rendido, el atajo del cuidador la vuelve a intentar ya
            if self.motor_rendido and self._motor_viejo is None:
                log.info("El cuidador pidió reintentar la detección con el atajo")
                self._reintentar_motor(time.monotonic())
        elif nombre == "teclado":
            self.alternar_teclado()
        elif nombre == "recentrar":
            self.motor.atajo("recentrar")
        elif nombre == "ventana":
            if self.ventana is not None and self.ventana.mini:
                self.ventana.alternar_mini()
            self.mostrar_ventana()
        elif nombre == "salir":
            self.salir_seguro()

    # ------------------------------------------------------------ ciclo de vida
    def construir_interfaz(self):
        import tkinter as tk
        from .barra import BarraAcciones
        from .indicador import BordeEstado, IndicadorCursor, ReanudarFlotante
        from .ventana_principal import VentanaPrincipal
        self.root = tk.Tk()
        self.ventana = VentanaPrincipal(self.root, self)
        self.root.update_idletasks()
        from .comun import no_activar
        no_activar(self.root)
        self.barra = BarraAcciones(self.root, self)
        self.indicador = IndicadorCursor(self.root, self)
        self.borde = BordeEstado(self.root, self)
        self.flotante = ReanudarFlotante(self.root, self)
        self.registro.manejador("lupa:", self._evento_lupa)
        # errores dentro de callbacks de tkinter (after, command, bind): al registro y a pausa
        self.root.report_callback_exception = self._error_en_callback
        # Windows avisa que se apaga o se cierra la sesión: guardar rápido (no siempre llega a finalizar)
        try:
            self.root.protocol("WM_SAVE_YOURSELF", self._al_apagar_windows)
        except Exception:  # noqa: BLE001
            pass
        if self.cfg.aviso:
            self.mostrar_aviso(self.cfg.aviso, 10)
        if registro_mod.ERROR:
            self.root.after(300, lambda: self.mostrar_aviso(t("aviso_sin_registro"), 8))
        self.root.after(REFRESCO_MS, self._refrescar)
        return self.root

    def correr(self) -> int:
        codigo = 0
        try:
            self.motor.start()
            self.construir_interfaz()
            self._arrancar_atajos()
            prueba = float(getattr(self.args, "prueba_segundos", 0) or 0)
            if self.cfg.datos.get("primera_vez") and not prueba:
                self.root.after(700, self.abrir_asistente)
            elif self.cfg.datos["teclado"].get("solo_comunicacion"):
                self.root.after(500, self.alternar_teclado)        # el teclado siempre abierto
            if prueba:
                self.root.after(int(prueba * 1000), self.salir_seguro)
            self.root.mainloop()
        except KeyboardInterrupt:
            codigo = 1
        except Exception:  # noqa: BLE001
            log.exception("Error en la interfaz")
            codigo = 1
        finally:
            self.finalizar()
        return codigo

    def _refrescar(self):
        if self.cerrando or self.root is None:
            return
        try:
            self.vuelta_interfaz()
        except Exception:  # noqa: BLE001
            log.exception("Error al pintar la interfaz")
        if not self.cerrando:
            try:
                self.root.after(REFRESCO_MS, self._refrescar)
            except Exception:  # noqa: BLE001
                pass

    def vuelta_interfaz(self):
        """Una vuelta del hilo de la interfaz (las pruebas la llaman directamente)."""
        ahora0 = time.monotonic()
        if self._t_ult_vuelta is not None and ahora0 - self._t_ult_vuelta > MOTOR_CAIDO_S:
            # la interfaz misma estuvo parada (el computador se suspendió): no es el motor caído
            log.info("La interfaz estuvo parada %.1f s (suspensión?)", ahora0 - self._t_ult_vuelta)
            self._t_ult_vista = ahora0
        self._t_ult_vuelta = ahora0
        while True:
            try:
                self._atender_atajo(self.cola_atajos.get_nowait())
            except queue.Empty:
                break
        try:
            v = self.motor.vistas.get_nowait()
            self.ultima_vista = v
            self._t_ult_vista = time.monotonic()
        except queue.Empty:
            v = self.ultima_vista
        for _ in range(AVISOS_POR_VUELTA):
            try:
                a = self.motor.avisos.get_nowait()
            except queue.Empty:
                break
            self.atender(a)
        self._revisar_voz()
        self._pintar(v)
        ahora = time.monotonic()
        if ahora - self._t_publicar >= PUBLICAR_CADA_S:
            self._t_publicar = ahora
            self.registro.publicar()
            self._revisar_foco()
            self._revisar_descanso(ahora)
            self._guardar_palabras_cada_tanto(ahora)
        self._vigilar_motor(ahora)

    def _pintar(self, v):
        detenido = self.motor_rendido
        if self.ventana is not None:
            self.ventana.actualizar(v, detenido=detenido)
        m = v.maquina if v is not None else None
        if self.barra is not None:
            self.barra.actualizar(v)
        if self.indicador is not None:
            self.indicador.actualizar(v)
        if self.borde is not None:
            self.borde.actualizar(m.estado if m is not None else K.PAUSA,
                                  bool(self.cfg.datos["comodidad"].get("indicador_borde", True)))
            self._recordar_atravesable(self.borde)
        if self.indicador is not None:
            self._recordar_atravesable(self.indicador)
        if self.flotante is not None:
            escondida = False
            try:
                escondida = not self.root.winfo_viewable()
            except Exception:  # noqa: BLE001
                pass
            self.flotante.actualizar(m is not None and m.estado == K.PAUSA and escondida)
        self._revisar_lupa(m)
        self._revisar_emergencia(m)
        if m is not None:
            self.registro.resaltar(m.objetivo)
        for f in list(self.oyentes_vista):
            try:
                f(v)
            except Exception:  # noqa: BLE001
                log.exception("Error en un oyente de la vista")
        if self.teclado is not None and hasattr(self.teclado, "actualizar"):
            try:
                self.teclado.actualizar(v)
            except Exception:  # noqa: BLE001
                log.exception("Error al pintar el teclado")

    def _recordar_atravesable(self, obj):
        if not self.sistema or getattr(obj, "_hwnd_recordado", False):
            return
        try:
            from ..sistema import ventanas_win as vw
            hwnd = vw.raiz(obj.win.winfo_id())
            self._hwnd_atravesables.add(hwnd)
            obj._hwnd_recordado = True
        except Exception:  # noqa: BLE001
            pass

    def atender(self, a):
        """Un aviso del motor."""
        if isinstance(a, Elegir):
            if not a.objetivo.startswith("ventana:"):
                self.registro.elegir(a.objetivo, "cabeza")
            return
        if isinstance(a, Sonido):
            self.sonidos.tocar(a.nombre)
            return
        if isinstance(a, Hablar):
            self.hablar(a.texto, a.urgente)
            return
        if not isinstance(a, Aviso):
            return
        clave = a.clave
        if clave == "teclado":
            self.alternar_teclado()
            return
        # ---- 1.1 paquete B: emergencia ----
        if clave == "emergencia":
            self.abrir_emergencia(a.texto)
            return
        if clave == "emergencia_fin":
            self.cerrar_emergencia()
            return
        if clave == "fatal":
            self.mostrar_aviso(t("aviso_fatal"), 8)
            return            # el vigilante reinicia el motor
        if clave == "error_inicio":
            self._rendirse(time.monotonic())
        if clave in AVISOS_CALLADOS:
            return
        texto = texto_aviso(a)
        if texto:
            self.mostrar_aviso(texto, 8 if clave in ("administrador", "foco_propio", "bloqueo") else 6)

    def _revisar_foco(self):
        """Cada 250 ms: si la ventana activa es propia, no se escribe en ella; se recuerda la
        última ventana de otro programa (para devolverle el foco antes de escribir)."""
        if not self.sistema:
            return
        try:
            from ..sistema import ventanas_win as vw
            hwnd = vw.ventana_activa()
            propia = bool(hwnd) and vw.es_propia(hwnd)
            self.salida.foco_propio = propia
            if hwnd and not propia:
                self.ultima_externa = hwnd
        except Exception:  # noqa: BLE001
            pass

    def _revisar_descanso(self, ahora: float):
        minutos = int(self.cfg.datos["comodidad"].get("descanso_min", 0) or 0)
        if minutos <= 0:
            self._t_descanso = ahora
            return
        if ahora - self._t_descanso >= minutos * 60:
            self._t_descanso = ahora
            self.mostrar_aviso(t("aviso_descanso"), 15)

    def _vigilar_motor(self, ahora: float):
        """Sección 8.5 (ronda 2 de arreglos). Distingue un motor **lento** (vivo y con latido: un
        cuadro que tardó, memoria paginada en un equipo con poca RAM) de uno **muerto o trabado**.
        - Sin vistas 2 s: se suelta todo una vez (por seguridad) y se espera; si se recupera solo,
          no cuenta como reinicio ni deja en pausa.
        - Muerto, o vivo sin latido 12 s: se reinicia (queda en pausa). Antes de crear el motor
          nuevo se espera a que el viejo termine (no dos cámaras ni dos FaceMesh a la vez).
        - 3 reinicios en 5 minutos: se rinde, pero vuelve a intentar cada minuto y el atajo de
          pausa del cuidador lo intenta ya."""
        if self.cerrando:
            return
        if self._motor_viejo is not None:
            viejo, desde = self._motor_viejo
            if viejo.is_alive() and ahora - desde < ESPERA_MOTOR_VIEJO_S:
                return
            if viejo.is_alive():
                log.warning("El motor anterior no terminó en %.0f s; se crea otro igual", ESPERA_MOTOR_VIEJO_S)
                self._apagar_camara(viejo)
            self._motor_viejo = None
            self._arrancar_motor_nuevo(ahora)
            return
        m = self.motor
        if self.motor_rendido:
            if self._t_rendido is None or ahora - self._t_rendido >= REINTENTO_RENDIDO_S:
                self._reintentar_motor(ahora)
            return
        if not m.listo.is_set():
            self._t_ult_vista = ahora           # todavía cargando la detección
            return
        if getattr(m, "error_inicio", None):
            self._rendirse(ahora)
            self.mostrar_aviso(t("aviso_error_inicio"), 15)
            return
        muerto = not m.is_alive()
        if not muerto and ahora - self._t_ult_vista <= MOTOR_CAIDO_S:
            self._soltado_lento = False
            return
        if not muerto:
            latido = getattr(m, "latido", None)
            if latido is not None and ahora - latido <= MOTOR_COLGADO_S:
                if not self._soltado_lento:
                    self._soltado_lento = True
                    self._soltar_seguro("motor lento")
                    log.warning("La detección va lenta (%.1f s sin vistas); se espera sin reiniciar",
                                ahora - self._t_ult_vista)
                return
        self._soltar_seguro("motor caído")
        self._t_reinicios = [x for x in self._t_reinicios if ahora - x < REINICIOS_VENTANA_S]
        if len(self._t_reinicios) >= MAX_REINICIOS:
            log.error("El motor no se pudo reiniciar; se vuelve a intentar en %.0f s", REINTENTO_RENDIDO_S)
            self._rendirse(ahora)
            self.mostrar_aviso(t("aviso_motor_rendido"), 30)
            return
        self.reinicios += 1
        self._t_reinicios.append(ahora)
        log.warning("El motor no responde: reinicio %d (%d en los últimos 5 minutos, máximo %d)",
                    self.reinicios, len(self._t_reinicios), MAX_REINICIOS)
        self.mostrar_aviso(t("aviso_motor_caido"), 8)
        self._reemplazar_motor(ahora)

    def _rendirse(self, ahora: float):
        self.motor_rendido = True
        self._t_rendido = ahora

    def _reintentar_motor(self, ahora: float):
        self.motor_rendido = False
        self._t_rendido = None
        self._t_reinicios = []
        self.mostrar_aviso(t("aviso_motor_reintento"), 8)
        self._reemplazar_motor(ahora)

    def _reemplazar_motor(self, ahora: float):
        m = self.motor
        try:
            m.detener()
            m.join(timeout=1.0)
        except Exception:  # noqa: BLE001
            pass
        try:
            vivo = m.is_alive()
        except Exception:  # noqa: BLE001
            vivo = False
        if vivo:
            # trabado: su cámara solo se apagaría al final de su run(); se apaga ya para que el
            # motor nuevo pueda abrir el aparato (ronda 3)
            self._apagar_camara(m)
            self._motor_viejo = (m, ahora)      # se crea el nuevo cuando el viejo termine
            return
        self._arrancar_motor_nuevo(ahora)

    @staticmethod
    def _apagar_camara(m):
        cam = getattr(m, "camara", None)
        if cam is None:
            return
        try:
            cam.detener()
            if hasattr(cam, "join"):
                cam.join(timeout=1.0)
        except Exception:  # noqa: BLE001
            log.exception("No se pudo apagar la cámara del motor anterior")

    def _arrancar_motor_nuevo(self, ahora: float):
        self.motor = self._crear_motor()
        self.motor.start()
        self.motor.orden("pausar", "reinicio")
        self._t_ult_vista = ahora
        self._soltado_lento = False
        self.registro.publicar(forzar=True)

    def _error_en_callback(self, tipo, valor, traza):
        log.error("Error en la interfaz", exc_info=(tipo, valor, traza))
        try:
            self._al_fallar(valor)
        except Exception:  # noqa: BLE001
            log.exception("Tampoco se pudo pausar tras el error de la interfaz")

    def guardar_rapido(self, motivo: str = ""):
        """Suelta todo y guarda configuración, palabras y frases, sin cerrar ventanas."""
        self._soltar_seguro(motivo or "guardar")
        try:
            if self.ventana is not None:
                x, y = self.ventana.posicion()
                self.cfg.datos["ventana"]["x"], self.cfg.datos["ventana"]["y"] = int(x), int(y)
        except Exception:  # noqa: BLE001
            pass
        for obj, metodo in ((self.prediccion, "guardar"),):
            try:
                if obj is not None:
                    getattr(obj, metodo)()
            except Exception:  # noqa: BLE001
                log.exception("No se pudo guardar al apagar")
        try:
            if not self.cfg.solo_lectura:
                self.guardar_config()
        except Exception:  # noqa: BLE001
            log.exception("No se pudo guardar la configuración al apagar")

    def _al_apagar_windows(self):
        log.info("Windows se apaga o cierra la sesión: se guarda todo")
        self.guardar_rapido("apagado de Windows")

    def _guardar_palabras_cada_tanto(self, ahora: float):
        if ahora - self._t_guardar_palabras < GUARDAR_PALABRAS_S:
            return
        self._t_guardar_palabras = ahora
        if self.prediccion is not None:
            try:
                self.prediccion.guardar()
            except Exception:  # noqa: BLE001
                log.exception("No se pudieron guardar las palabras aprendidas")

    def salir_seguro(self):
        if self.cerrando:
            return
        self.cerrando = True
        self._soltar_seguro("salir")
        log.info("Saliendo")
        try:
            if self.ventana is not None:
                x, y = self.ventana.posicion()
                self.cfg.datos["ventana"]["x"], self.cfg.datos["ventana"]["y"] = int(x), int(y)
        except Exception:  # noqa: BLE001
            pass
        try:
            self.cerrar_lupa()
        except Exception:  # noqa: BLE001
            pass
        try:
            self.cerrar_emergencia(avisar=False)
        except Exception:  # noqa: BLE001
            pass
        for w in (self.indicador, self.borde, self.flotante):
            try:
                if w is not None:
                    w.destruir()
            except Exception:  # noqa: BLE001
                pass
        try:
            if self.root is not None:
                self.root.destroy()
        except Exception:  # noqa: BLE001
            pass

    def finalizar(self):
        """Soltar todo -> detener el motor -> atajos -> voz -> sonidos -> guardar."""
        self.cerrando = True
        self._callar_alarma()                   # 1.1: la alarma nunca queda sonando al salir
        self._soltar_seguro("fin")
        try:
            self.motor.detener()
            self.motor.join(timeout=2.0)
        except Exception:  # noqa: BLE001
            pass
        self._soltar_seguro("fin del motor")
        if self.atajos is not None:
            try:
                self.atajos.detener()
            except Exception:  # noqa: BLE001
                pass
        if self.prediccion is not None:
            try:
                self.prediccion.guardar()
            except Exception:  # noqa: BLE001
                log.exception("No se pudieron guardar las palabras aprendidas")
        if self.voz is not None and hasattr(self.voz, "cerrar"):
            try:
                self.voz.cerrar()
            except Exception:  # noqa: BLE001
                pass
        try:
            self.sonidos.cerrar()
        except Exception:  # noqa: BLE001
            pass
        try:
            if not self.cfg.solo_lectura:
                self.guardar_config()
        except Exception:  # noqa: BLE001
            log.exception("No se pudo guardar la configuración")
        if getattr(self.args, "prueba_segundos", 0):
            self._informe()

    def _informe(self):
        m = self.motor
        r = m.stats.resumen() if hasattr(m, "stats") else {}
        maq = getattr(m, "maquina", None)
        r.update({
            "version": VERSION,
            "camara": getattr(getattr(m, "camara", None), "estado", ""),
            "error_inicio": getattr(m, "error_inicio", None),
            "estado_final": getattr(maq, "estado", None),
            "todo_suelto": self.salida.todo_suelto(),
            "simulada": self.simulada,
            "reinicios": self.reinicios,
        })
        log.info("Informe: %s", r)
        try:
            print(json.dumps(r, ensure_ascii=False))
        except Exception:  # noqa: BLE001
            pass


def _acepta_urgente(f) -> bool:
    try:
        import inspect
        return "urgente" in inspect.signature(f).parameters
    except (TypeError, ValueError):
        return False


def _generador_cara_dibujada():
    """Para ``--camara-falsa``: siempre la misma cara dibujada (la reconoce la detección real),
    así se puede probar el programa entero sin cámara."""
    try:
        from ..autoprueba import cara_dibujada
        img = cara_dibujada()
    except Exception:  # noqa: BLE001
        return None
    return lambda _t: img


def correr(args) -> int:
    """Punto de entrada que llama ``app.main`` (una sola copia abierta; mutex propio en ensayo)."""
    from ..sistema import ventanas_win
    mutex = K.MUTEX + ("Ensayo" if getattr(args, "simular", False) else "")
    if not ventanas_win.instancia_unica(mutex):
        if getattr(args, "prueba_segundos", 0):
            try:
                print(json.dumps({"error": "ya abierto"}))
            except Exception:  # noqa: BLE001
                pass
            return 2
        ventanas_win.traer_al_frente(K.NOMBRE_APP)
        _mensaje(t("aviso_ya_abierto"))
        return 0
    try:
        app = App(args)
    except Exception:  # noqa: BLE001
        log.exception("No se pudo abrir Lycan Face Control")
        if not getattr(args, "prueba_segundos", 0):
            _mensaje(t("aviso_no_abre"), error=True)
        return 1
    return app.correr()


def _mensaje(texto: str, error: bool = False):
    try:
        import tkinter as tk
        from tkinter import messagebox
        r = tk.Tk()
        r.withdraw()
        (messagebox.showerror if error else messagebox.showinfo)(K.NOMBRE_APP, texto, parent=r)
        r.destroy()
    except Exception:  # noqa: BLE001
        pass


if __name__ == "__main__":  # pragma: no cover
    sys.exit(1)
