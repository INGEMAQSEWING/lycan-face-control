"""Máquina de estados (sección 5). Lógica pura: une el mapeo, el puntero, la permanencia y los
gestos, y devuelve listas de acciones. No toca Windows, ni la cámara, ni tkinter.

Estados: PAUSA, ACTIVO, SIN_CARA, CALIBRANDO. Submodos de ACTIVO: NORMAL, ARRASTRE_INICIO,
ARRASTRANDO, DESPLAZAR, TECLADO, BARRIDO, SOLO_COMUNICACION.

Seguridad (sección 5.5 y 8): entrar a PAUSA, a SIN_CARA (a los 300 ms) o a CALIBRANDO, un
error o el tope de 60 s de arrastre producen siempre ``SoltarTodo``. Los clics van completos
(bajar y subir juntos); el único botón que puede quedar abajo es el del arrastre.

Objetivos propios (botones de la barra, teclas, frases, "Reanudar"): la interfaz los publica con
``poner_objetivos``. Sobre ellos la permanencia y los gestos de clic producen ``Elegir(id)``
(nunca un clic de Windows). Los de la barra (``barra:clic``, ``barra:doble``...) y
``reanudar``/``desplazar:terminar`` los atiende además la propia máquina.
"""
from __future__ import annotations

import logging
import math
import statistics
from collections import deque
from dataclasses import dataclass, field, replace

from . import constantes as K
from . import lupa as lupa_mod
from .acciones import Aviso, Bajar, Clic, Elegir, Mover, Rueda, Sonido, SoltarTodo, Subir
from .config import calibracion_activa
from .gestos import (DobleParpadeoLargo, GestoCorto, GestoLargo, Gestos, ParpadeoLargo, ParpadeoListo,
                     ResultadoGestos)
from .mapeo import MapeoCabeza, Monitor
from .permanencia import EstadoPermanencia, Permanencia, buscar_objetivo, sobre_ventana_propia
from .puntero import MEZCLA_DESCONGELAR_S, MEZCLA_REENTRADA_S, Puntero

log = logging.getLogger("lycan")

# Identificadores de objetivos que atiende la máquina
ID_REANUDAR = "reanudar"
ID_TERMINAR_DESPLAZAR = "desplazar:terminar"
ID_BARRIDO_ELEGIR = "barrido:elegir"
ID_BARRIDO_SIGUIENTE = "barrido:siguiente"
ID_REANUDAR_TECLADO = "teclado:reanudar"   # el botón Pausa del teclado en pantalla, en pausa
IDS_REANUDAR = (ID_REANUDAR, "barra:pausa", ID_REANUDAR_TECLADO)
# Botones que pausan (en el teclado y en la ventana principal): al reanudar quedan bloqueados hasta
# que el puntero salga de ellos (si no, quien reanuda quieto encima vuelve a pausar).
IDS_PAUSA = ("accion:pausa", "ui:pausar", "barra:pausa")
# La interfaz publica el botón nuevo (Pausa <-> Reanudar) unos cuadros después del cambio de estado:
# un bloqueo de un botón que todavía no aparece se guarda este tiempo (ronda 3).
BLOQUEO_AUSENTE_S = 3.0
# "Mirando a otro lado" (ronda 3): la cabeza muy por fuera de su rango cómodo calibrado (al
# cuidador, a la televisión, a comer). El puntero se congela, la permanencia se desarma y los
# gestos de clic no cuentan (la pausa sí). En unidades del rango cómodo (1 = extremo calibrado).
U_AFUERA = 1.6
U_AFUERA_VUELVE = 1.35                # histéresis: para volver hay que entrar claramente
REANUDAR_PERMANENCIA_S = 2.0          # permanencia sobre "Reanudar" (más larga que un botón normal)
REANUDAR_VENTANA_S = 2.5              # el gesto de reanudar vale si se suelta entre reanudar_ms y +2,5 s
# Pausas puestas por el cuidador (atajo, ratón, Opciones): ningún gesto de la cara las quita (un
# bostezo o comer no deben reactivar el puntero). Sí el botón "Reanudar" con la cabeza, el atajo y,
# con barrido, el doble parpadeo largo (quien solo parpadea siempre tiene que poder pedir ayuda).
MOTIVOS_CUIDADOR = ("atajo", "cuidador", "opciones")
# Cara distinta (otra persona entra en el cuadro y FaceMesh la sigue): salto brusco de un cuadro
SALTO_IO = 0.25                       # el tamaño de la cara cambia más de 25 %
SALTO_CENTRO_IO = 0.5                 # o el centro salta más de media distancia entre ojos
CARA_ESTABLE_S = 1.0                  # tras un salto: 1 s de cara estable antes de aceptar clics
# Tras un hueco sin cara, la cara que vuelve se compara con la última cara válida (no con el
# cuadro anterior, que no tenía cara): alguien que se cruza delante de la cámara deja casi
# siempre uno o varios cuadros sin cara antes de que FaceMesh siga a la otra persona.
HUECO_CORTO_S = 2.0                   # con un hueco más corto se avisa "otra cara" (como sin hueco)
# Huella de la cara de la persona (ronda 3): tamaño (distancia entre ojos en px) y proporciones
# estables (cejas y ancho de la boca respecto a la distancia entre ojos), aprendidas despacio
# mientras la cara es de confianza. Tras un salto de cara, si la cara nueva no se parece a la
# huella, se pausa ("otra cara") hasta que vuelva una cara compatible o la persona elija Reanudar.
HUELLA_TOL = {"io": 0.20, "cejas": 0.15, "sonrisa": 0.15}
HUELLA_ALFA = 0.02                    # por cuadro (≈ 2,5 s de constante de tiempo a 20 cuadros/s)
MOTIVO_OTRA_CARA = "otra_cara"
# El puntero se desliza solo hasta su posición nueva tras recentrar, cambiar una opción, reanudar
# o volver la cara: ese deslizamiento no es "moverse a propósito" y no arma la permanencia.
DESARMAR_TRAS_DESLIZAR_S = MEZCLA_REENTRADA_S + 0.3
# Tras un clic con un gesto, el puntero (congelado durante el gesto) termina de llegar a donde mira
# la cabeza: ese acomodo no cuenta como "moverse" para armar la permanencia (si no, se sumaba un
# clic por permanencia al lado del clic del gesto).
DESARMAR_TRAS_GESTO_S = 0.8

RADIO_SIGMAS = 4.0                    # radio de la permanencia >= 4 x temblor esperado del puntero
                                      # (y para armar hay que alejarse >= 6 x temblor)
REFRACTARIO_FIN_CALIBRACION_S = 1.0
ESTABLE_PARA_REANUDAR_S = 1.0         # pausa automática: cara estable 1 s para seguir
RECENTRAR_S = 1.5
DESPLAZAR_ZONA = 0.15                 # zona muerta del modo Desplazar (fracción del rango cómodo)
DESPLAZAR_TOPE = 0.8                  # a esta inclinación ya va a la velocidad máxima
DESPLAZAR_MIN, DESPLAZAR_MAX = 1.0, 8.0   # muescas por segundo
DESPLAZAR_INACTIVO_S = 10.0          # sin desplazar CLARAMENTE este tiempo, el modo termina solo
DESPLAZAR_CLARO = 2 * DESPLAZAR_ZONA  # inclinación que cuenta como "sigue desplazando"
DESPLAZAR_MAX_S = 60.0               # tope de un modo Desplazar continuo
QUIETO_PX_S = 150.0                   # puntero "casi quieto" (para recordar dónde se trabajaba)
ERRORES_FATALES = 3                   # errores en 60 s => el motor se detiene (fatal)
VENTANA_ERRORES_S = 60.0

ACCIONES_CLIC = ("clic", "clic_izq", "clic_der", "doble", "arrastrar")
MODOS_CLIC = ("izq", "doble", "der", "arrastrar", "desplazar")
# ---- 1.1 paquete A: «Sin clic» (modo lectura) y «Lupa» (clic preciso) ----
MODOS_CLIC = MODOS_CLIC + ("ninguno", "lupa")
ID_BARRA_MOSTRAR = "ui:barra_mostrar"     # pestaña de la barra minimizada: se elige también en pausa
SUBMODOS_SIN_PUNTERO = (K.BARRIDO, K.SOLO_COMUNICACION)
# ---- 1.1 paquete B: emergencia (botón AYUDA) ----
IDS_EMERGENCIA = K.IDS_EMERGENCIA
ID_ATENDIDO = K.ID_ATENDIDO


@dataclass
class Vista:
    """Lo que la interfaz necesita para pintar (copia; no se comparte con la máquina)."""
    estado: str = K.PAUSA
    submodo: str = K.NORMAL
    modo_clic: str = "izq"
    motivo_pausa: str = ""
    pausa_auto: bool = False
    puntero: tuple | None = None
    puntero_virtual: tuple | None = None        # en pausa: dónde apunta la cabeza (sin mover)
    permanencia: EstadoPermanencia = field(default_factory=EstadoPermanencia)
    gestos: ResultadoGestos = field(default_factory=ResultadoGestos)
    sin_cara_s: float = 0.0
    recentrando: float | None = None            # 0..1 mientras toma el centro
    calibrado: bool = False
    congelado: bool = False
    arrastre_s: float = 0.0
    medidas: object = None
    objetivo: str | None = None
    reanuda_parpadeo: bool = False              # en pausa: dos parpadeos largos reanudan
    mirando_afuera: bool = False                # la cabeza está muy fuera de su rango cómodo
    emergencia: bool = False                    # 1.1: se pidió AYUDA (pantalla roja y alarma)


@dataclass
class Resultado:
    acciones: list
    vista: Vista


class Maquina:
    def __init__(self, cfg: dict, monitor: Monitor | None = None, calibracion: dict | None = None,
                 pos_cursor=None, t0: float = 0.0, usar_calibracion_config: bool = True):
        self.cfg = cfg
        self.monitor = monitor
        self.pos_cursor = pos_cursor              # callable() -> (x, y) del puntero real, o None
        if calibracion is None and usar_calibracion_config:
            calibracion = calibracion_activa(cfg)
        self.calibracion = calibracion if isinstance(calibracion, dict) else None
        self._construir()
        arranque = cfg["arranque"]["estado"]
        if arranque == "activo" or (arranque == "auto" and self.calibracion is not None):
            self.estado = K.ACTIVO
            self.motivo_pausa = ""
        else:
            self.estado = K.PAUSA
            self.motivo_pausa = "inicio"
        self.submodo = K.SOLO_COMUNICACION if cfg["teclado"].get("solo_comunicacion") else K.NORMAL
        self.modo_clic = "izq"
        self.pausa_auto = False
        self._estado_previo = K.ACTIVO            # para volver de SIN_CARA / CALIBRANDO
        self._t_sin_cara = None
        self._soltado_sin_cara = False
        self._t_cara_desde = None                 # desde cuándo hay cara seguida
        self._recentrar = None                    # {"t0", "yaw": [], "pitch": []}
        self._centrado = self.calibracion is not None
        self._aviso_calibrar = False
        self._t_arrastre = None
        self._desp_ref = None
        self._desp_acum = 0.0
        self._t_ult_desp = None
        self._t_ant = None
        self._obj_actual = None
        self.objetivos: list = []
        self._errores: deque = deque()
        self._bloqueados: dict = {}             # id -> t: botones ignorados hasta que el puntero salga de ellos
        self._afuera = False                     # la cabeza mira muy fuera de su rango cómodo
        self.fatal = False
        self._ultima_vista = Vista()
        self._ultimas_medidas = None
        self._m_ult_valida = None                 # última cara válida (para "cara distinta")
        self._t_ult_valida = None
        self._huella = None                       # {"io", "cejas", "sonrisa"} de la persona
        self._muestras: deque = deque()           # (t, io, cejas, sonrisa) del último segundo
        self._t_cara_nueva = None                 # tras un salto: desde cuándo la cara está estable
        self._por_cuidador = False
        self._ult_pos_externa = None              # última posición del puntero fuera de ventanas propias
        self._t_desp_inicio = None
        self._desarmar_hasta = None
        self._clic_gesto_congelado = False
        self._lupa = None                         # {"zona", "ventana", "imagen", "t0"} con la lupa abierta
        # 1.1 paquete B: emergencia. Mientras dura, el puntero se mueve pero ningún clic llega a
        # Windows y lo único elegible es «Ya me atendieron».
        self.emergencia = False
        self._estado_antes_emergencia = None
        self._t_emergencia = None

    # ------------------------------------------------------------ armado
    def _construir(self, conservar_pos: bool = False):
        cfg = self.cfg
        pos = None
        if conservar_pos and getattr(self, "puntero", None) is not None:
            pos = self.puntero.posicion_real
        elif self.pos_cursor is not None:
            try:
                pos = self.pos_cursor()
            except Exception:  # noqa: BLE001
                pos = None
        self.mapeo = MapeoCabeza.desde_config(cfg, self.monitor, self.calibracion)
        self.puntero = Puntero.desde_config(cfg, self.mapeo, pos, self.calibracion)
        self.perm = Permanencia.desde_config(cfg, self.mapeo.monitor.alto)
        # el círculo de la permanencia nunca es menor que el temblor esperado del puntero (con un
        # rango calibrado pequeño o mucha velocidad el temblor de FaceMesh se amplifica)
        self.perm.ajustar_radio_minimo(RADIO_SIGMAS * self.puntero.temblor_px)
        self.gestos = Gestos(cfg["gestos"], self.calibracion)
        # el clasificador nuevo arranca "recién vuelta la cara": un gesto que ya esté arriba (las
        # cejas de la prueba final de la calibración, la boca al guardar Opciones) tiene que volver
        # a reposo antes de contar
        self.gestos.perder_cara()

    def _desarmar_tras_deslizar(self, t: float | None, extra_s: float = 0.0):
        """El puntero se va a deslizar solo (mezcla): la permanencia no se arma con eso."""
        if t is None:
            return
        hasta = t + DESARMAR_TRAS_DESLIZAR_S + extra_s
        if self._desarmar_hasta is None or hasta > self._desarmar_hasta:
            self._desarmar_hasta = hasta
        self.perm.desarmar(self.puntero.posicion)

    def nueva_config(self, t: float | None, cfg: dict, calibracion: dict | None = None) -> list:
        """Opciones cambiadas o calibración nueva: se rehace todo sin perder el estado."""
        acciones = [SoltarTodo("nueva configuración")]
        self.cfg = cfg
        if calibracion is not None:
            self.calibracion = calibracion
            self._centrado = True
            self._huella = None                   # la cara de la calibración nueva es la de la persona
        else:
            cal = calibracion_activa(cfg)
            if isinstance(cal, dict):
                self.calibracion = cal
                self._centrado = True
        yaw0_pitch0 = (self.mapeo.yaw0, self.mapeo.pitch0)
        self._construir(conservar_pos=True)
        if self.calibracion is None:
            self.mapeo.recentrar(*yaw0_pitch0)   # conserva el centro tomado sin calibrar
        if self.submodo in (K.ARRASTRE_INICIO, K.ARRASTRANDO, K.DESPLAZAR):
            self.submodo = K.NORMAL
        if self.submodo == K.LUPA:
            self._cerrar_lupa(acciones)
        # «Sin clic» dura hasta que la persona elija otro modo (cambiar una opción no lo quita)
        self.modo_clic = "ninguno" if self.modo_clic == "ninguno" else "izq"
        if t is not None:
            self.puntero.reiniciar_filtros(t)
            self._desarmar_tras_deslizar(t)
        return acciones

    def cambiar_monitor(self, t: float | None, monitor: Monitor) -> list:
        """La pantalla cambió (otro monitor, otra resolución): se rehace el mapeo conservando la
        calibración y el estado."""
        self.monitor = monitor
        return self.nueva_config(t, self.cfg)

    def poner_objetivos(self, objetivos):
        """Lista de ``permanencia.Objetivo`` en píxeles físicos de pantalla (la publica la interfaz)."""
        self.objetivos = list(objetivos or [])
        if self._obj_actual is not None and all(o.id != self._obj_actual.id for o in self.objetivos):
            self._obj_actual = None

    # ------------------------------------------------------------ utilidades
    def _bloquear(self, ids, t: float):
        for i in ids:
            self._bloqueados[i] = t

    def _objetivos_libres(self, pos, t: float):
        """Los objetivos sin los bloqueados. Tras pausar o reanudar, los botones Pausa y
        Reanudar no cuentan hasta que el puntero salga de ellos: si la persona se queda quieta
        encima, no se pausa y reanuda una y otra vez. Un botón bloqueado que todavía no aparece
        (la interfaz lo publica unos cuadros después) sigue bloqueado hasta BLOQUEO_AUSENTE_S."""
        if not self._bloqueados:
            return self.objetivos
        x, y = pos
        presentes = {o.id: o for o in self.objetivos}
        for i, tb in list(self._bloqueados.items()):
            o = presentes.get(i)
            if o is not None:
                if not o.contiene(x, y, 0.12):
                    del self._bloqueados[i]
            elif t - tb > BLOQUEO_AUSENTE_S:
                del self._bloqueados[i]
        return [o for o in self.objetivos if o.id not in self._bloqueados]

    @property
    def _p_cfg(self):
        return self.cfg["permanencia"]

    def _sonido(self, nombre: str, acc: list):
        if self.cfg["comodidad"].get("sonidos", True) or nombre == "alerta":
            acc.append(Sonido(nombre))

    def _pos_real(self):
        if self.pos_cursor is not None:
            try:
                p = self.pos_cursor()
                if p is not None:
                    return p
            except Exception:  # noqa: BLE001
                pass
        return self.puntero.posicion

    def _parpadeo_con_accion(self) -> bool:
        if not self.gestos.encendido("parpadeo"):
            return False
        if self.submodo in SUBMODOS_SIN_PUNTERO:
            return True
        return self.cfg["gestos"]["parpadeo"].get("fuera_barrido", "ninguna") != "ninguna"

    def _reanuda_con_doble_parpadeo(self) -> bool:
        """Quien usa el barrido (o "solo comunicación") solo cuenta con los párpados: en pausa,
        dos parpadeos largos seguidos reanudan, la haya puesto quien la haya puesto."""
        tec = self.cfg["teclado"]
        return bool(tec.get("solo_comunicacion") or tec.get("barrido")) or self.submodo in SUBMODOS_SIN_PUNTERO

    def reanuda_con_parpadeo(self) -> bool:
        """Para la interfaz: en pausa, ¿se puede seguir con dos parpadeos largos?"""
        return self.gestos.encendido("parpadeo") and self._reanuda_con_doble_parpadeo()

    def _gestos_de_pausa(self):
        g = self.cfg["gestos"]
        return [n for n in ("boca", "cejas", "sonrisa")
                if g[n]["activo"] and "pausar" in (g[n]["corto"], g[n]["largo"])]

    def _volver_modo_clic(self):
        if not self.cfg["barra"].get("modo_fijo", False):
            self.modo_clic = "izq"

    # ------------------------------------------------------------ órdenes públicas
    def pausar(self, t: float, motivo: str = "pausa", auto: bool = False) -> list:
        acc: list = []
        self._pausar(t, motivo, acc, auto)
        return acc

    def reanudar(self, t: float, motivo: str = "reanudar") -> list:
        acc: list = []
        if self.estado == K.PAUSA:
            self._reanudar(t, motivo, acc)
        return acc

    def alternar_pausa(self, t: float) -> list:
        """Atajo del cuidador: siempre suelta todo."""
        if self.estado == K.PAUSA:
            return [SoltarTodo("atajo")] + self.reanudar(t, "atajo")
        if self.estado == K.CALIBRANDO:
            return [SoltarTodo("atajo")]
        return self.pausar(t, "atajo")

    def por_error(self, t: float, e: Exception | None = None) -> list:
        """Un error en el motor: soltar todo y pausar. 3 errores en 60 s = fatal."""
        self._errores.append(t)
        while self._errores and self._errores[0] < t - VENTANA_ERRORES_S:
            self._errores.popleft()
        if len(self._errores) >= ERRORES_FATALES:
            self.fatal = True
        acc = [SoltarTodo("error")]
        if self.estado != K.PAUSA:
            self._pausar(t, "error", acc)
        acc.append(Aviso("error", repr(e) if e is not None else ""))
        return acc

    def bloquear(self, t: float, motivo: str = "envio") -> list:
        """Windows no aceptó los eventos (pantalla de bloqueo, UAC): pausa con aviso."""
        acc: list = [SoltarTodo(motivo)]
        if self.estado != K.PAUSA:
            self._pausar(t, motivo, acc)
        acc.append(Aviso("bloqueo", motivo))
        return acc

    def recentrar(self, t: float) -> list:
        if self.estado in (K.ACTIVO, K.PAUSA, K.SIN_CARA):
            self._recentrar = {"t0": t, "yaw": [], "pitch": []}
            return [Aviso("recentrando")]
        return []

    def iniciar_calibracion(self, t: float) -> list:
        if self.estado != K.CALIBRANDO:
            self._estado_previo = K.ACTIVO if self.estado == K.SIN_CARA else self.estado
        acc: list = [SoltarTodo("calibración")]
        self._salir_de_submodos_con_boton(acc)
        self.estado = K.CALIBRANDO
        self._recentrar = None
        self.perm.reiniciar()
        return acc

    def terminar_calibracion(self, t: float, calibracion: dict | None = None, cfg: dict | None = None) -> list:
        acc: list = [SoltarTodo("fin de la calibración")]
        if cfg is not None or calibracion is not None:
            acc += self.nueva_config(t, cfg or self.cfg, calibracion)
        # refractario de 1 s: el gesto de la última prueba (cejas, boca) no hace un clic real
        self.gestos.refractario_hasta(t + REFRACTARIO_FIN_CALIBRACION_S)
        if self.estado == K.CALIBRANDO:
            self.estado = self._estado_previo if self._estado_previo in (K.ACTIVO, K.PAUSA) else K.PAUSA
            if self.estado == K.ACTIVO:
                self.puntero.fijar_posicion(*self._pos_real(), t)
                self._desarmar_tras_deslizar(t)
        return acc

    def elegir(self, t: float, ident: str) -> list:
        """Un botón propio elegido desde fuera (el cuidador con el ratón, o la interfaz)."""
        acc: list = []
        if not ident:
            return acc
        if ident in IDS_EMERGENCIA:
            # el cuidador con el ratón o el barrido del teclado: vale en cualquier estado
            self._pedir_ayuda(t, "barrido" if ident == K.ID_EMERGENCIA_TECLADO and
                              self.submodo in SUBMODOS_SIN_PUNTERO else "cuidador", acc)
            return acc
        if ident == ID_ATENDIDO:
            self._atendido(t, "cuidador", acc)
            return acc
        if self.emergencia:
            return acc                          # durante la emergencia no se elige nada más
        if self.estado == K.PAUSA:
            if ident in IDS_REANUDAR:
                self._reanudar(t, "botón Reanudar", acc)
            return acc
        if self.estado in (K.ACTIVO, K.SIN_CARA):
            self._por_cuidador = True          # una pausa desde aquí la puso el cuidador
            try:
                self._elegir(str(ident), t, self.puntero.posicion, acc)
            finally:
                self._por_cuidador = False
        return acc

    def poner_submodo(self, t: float, submodo: str) -> list:
        """La interfaz abre o cierra el teclado o el barrido (TECLADO, BARRIDO,
        SOLO_COMUNICACION o NORMAL)."""
        acc: list = []
        if submodo not in (K.NORMAL, K.TECLADO, K.BARRIDO, K.SOLO_COMUNICACION):
            return acc
        self._salir_de_submodos_con_boton(acc)
        antes = self.submodo
        self.submodo = submodo
        if antes in SUBMODOS_SIN_PUNTERO and submodo not in SUBMODOS_SIN_PUNTERO:
            self.puntero.fijar_posicion(*self._pos_real(), t)
        self.perm.reiniciar()
        return acc

    # ------------------------------------------------------------ transiciones internas
    def _salir_de_submodos_con_boton(self, acc: list):
        if self.submodo == K.LUPA:
            self._cerrar_lupa(acc)
        if self.submodo == K.ARRASTRANDO:
            acc.append(Subir(K.IZQ))
        if self.submodo in (K.ARRASTRE_INICIO, K.ARRASTRANDO, K.DESPLAZAR):
            self.submodo = K.NORMAL
            self.modo_clic = "izq"
            self._t_arrastre = None
            self._desp_ref = None

    def _pausar(self, t: float, motivo: str, acc: list, auto: bool = False):
        acc.append(SoltarTodo(motivo))
        self._salir_de_submodos_con_boton(acc)
        self.estado = K.PAUSA
        self.motivo_pausa = motivo
        self.pausa_auto = auto
        self._t_cara_desde = None
        # el parpadeo largo que eligió «Pausa» no cuenta como el primero del doble parpadeo
        self.gestos.olvidar_parpadeo_largo()
        self.perm.reiniciar()
        self._obj_actual = None
        self._bloquear(IDS_REANUDAR, t)
        self._sonido("pausar", acc)
        acc.append(Aviso("pausa", motivo))
        log.info("Pausa (%s)", motivo)

    def _reanudar(self, t: float, motivo: str, acc: list):
        self.estado = K.ACTIVO
        self.motivo_pausa = ""
        self.pausa_auto = False
        self._t_sin_cara = None
        self._soltado_sin_cara = False
        self.puntero.fijar_posicion(*self._pos_real(), t)
        self.perm.reiniciar()
        self._desarmar_tras_deslizar(t)
        self._obj_actual = None
        self._afuera = False
        if motivo != "cara de nuevo":
            # la persona (o el cuidador) reanudó a propósito: la cara de ahora es la de confianza
            self._huella = self._huella_de_muestras()
        self._bloquear(IDS_REANUDAR + IDS_PAUSA, t)
        for n in ("boca", "cejas", "sonrisa"):
            if self.gestos.duracion_sostenida(n, t) > 0:
                self.gestos.consumir(n)        # el gesto que reanudó no hace nada más al soltarlo
        self._sonido("activar", acc)
        acc.append(Aviso("activo", motivo))
        log.info("Activo (%s)", motivo)

    # ------------------------------------------------------------ paso principal
    def procesar(self, t: float, medidas) -> Resultado:
        """Un cuadro: ``medidas`` (``cara.Medidas``) o None si no hay cara."""
        acc: list = []
        dt = 0.05 if self._t_ant is None else min(max(t - self._t_ant, 0.0), 0.5)
        self._t_ant = t
        self._ultimas_medidas = medidas
        hueco = None if self._t_ult_valida is None else t - self._t_ult_valida
        cambio = self._cara_distinta(medidas, t)
        if cambio:
            self.gestos.perder_cara(t)          # los gestos en curso no son de esta cara
            self._muestras.clear()
        self._guardar_muestra(medidas, t)
        g = self.gestos.actualizar(medidas, t)
        if self.emergencia:
            # 1.1: con la emergencia activa no cuenta nada más (ni la cara perdida, ni mirar afuera,
            # ni los gestos): solo «Ya me atendieron»
            st = self._paso_emergencia(t, medidas, g, acc)
            return Resultado(acc, self._vista(t, g, st, medidas))
        if self._t_cara_nueva is not None:
            if t - self._t_cara_nueva < CARA_ESTABLE_S - 1e-9:
                g.eventos = []                  # todavía no se aceptan gestos de esta cara
                g.soltados = []
            else:
                self._t_cara_nueva = None
                if not self._compatible() and self.estado in (K.ACTIVO, K.PAUSA) and medidas is not None:
                    self._otra_cara(t, acc)
                    g.eventos = []
                    g.soltados = []
        st = EstadoPermanencia()
        if cambio and self.estado != K.CALIBRANDO:
            acc.append(SoltarTodo("cara distinta"))
            self._salir_de_submodos_con_boton(acc)
            self.perm.reiniciar()
            # la otra persona no hace clic por permanencia: hay que moverse a propósito después
            # de la espera (y del deslizamiento del puntero al descongelarse)
            self._desarmar_tras_deslizar(t, CARA_ESTABLE_S + MEZCLA_DESCONGELAR_S)
            if self.estado != K.PAUSA and (hueco is None or hueco < HUECO_CORTO_S):
                acc.append(Aviso("cara_distinta"))
            log.info("Cambió la cara del cuadro: se suelta todo y se espera 1 s de cara estable")
        if self.estado == K.CALIBRANDO:
            return Resultado(acc, self._vista(t, g, st, medidas))
        if medidas is None:
            self._sin_cara(t, acc)
            return Resultado(acc, self._vista(t, g, st, medidas))
        # ---- hay cara ----
        if self._t_cara_desde is None:
            self._t_cara_desde = t
        if self.estado == K.SIN_CARA:
            largo = self._soltado_sin_cara
            self.estado = K.ACTIVO
            self._t_sin_cara = None
            self._soltado_sin_cara = False
            self.perm.reiniciar()
            if largo:
                # el puntero se desliza desde donde quedó: eso no arma la permanencia
                self._desarmar_tras_deslizar(t)
            acc.append(Aviso("cara_vuelve"))
        self._t_sin_cara = None
        if not self._centrado and self._recentrar is None:
            # sin calibración: el centro es la postura de la persona al aparecer
            self._recentrar = {"t0": t, "yaw": [], "pitch": [], "auto": True}
            if not self._aviso_calibrar:
                self._aviso_calibrar = True
                acc.append(Aviso("recomendar_calibrar"))
        self._paso_recentrar(t, medidas, acc)
        if self.estado == K.PAUSA:
            st = self._en_pausa(t, medidas, g, acc)
        else:
            st = self._en_activo(t, medidas, g, dt, acc)
        if self.estado == K.ACTIVO:
            self._aprender_huella(t, g)
        return Resultado(acc, self._vista(t, g, st, medidas))

    @staticmethod
    def _io_valido(m):
        try:
            io = float(m.io_px)
        except (AttributeError, TypeError, ValueError):
            return None
        return io if math.isfinite(io) and io > 0 else None

    def _cara_distinta(self, m, t: float) -> bool:
        """Salto brusco de tamaño o de posición de la cara respecto a la **última cara válida**
        (el cuadro anterior con cara, aunque en medio haya cuadros sin cara): casi seguro es otra
        persona (FaceMesh sigue una sola cara). Mientras la cara no esté estable 1 s, cada salto
        nuevo vuelve a empezar la espera."""
        if m is None:
            return False                # un cuadro sin cara no borra la referencia
        ant = self._m_ult_valida
        self._m_ult_valida = m
        self._t_ult_valida = t
        if ant is None:
            return False
        try:
            io0, io1 = float(ant.io_px), float(m.io_px)
            if not (io0 > 0 and io1 > 0):
                return False
            salto = abs(io1 - io0) / io0 > SALTO_IO
            c0, c1 = getattr(ant, "centro", None), getattr(m, "centro", None)
            if not salto and c0 is not None and c1 is not None:
                d = math.hypot(c1[0] - c0[0], c1[1] - c0[1])
                salto = math.isfinite(d) and d > SALTO_CENTRO_IO * max(io0, io1)
        except (TypeError, ValueError):
            return False
        if salto:
            self._t_cara_nueva = t
        return salto

    # ------------------------------------------------------------ huella de la cara
    def _guardar_muestra(self, m, t: float):
        if m is None:
            self._muestras.clear()
            return
        try:
            io, cj, so = float(m.io_px), float(m.cejas), float(m.sonrisa)
        except (AttributeError, TypeError, ValueError):
            return
        if not all(math.isfinite(v) and v > 0 for v in (io, cj, so)):
            return
        self._muestras.append((t, io, cj, so))
        while self._muestras and self._muestras[0][0] < t - CARA_ESTABLE_S - 1e-9:
            self._muestras.popleft()

    def _huella_de_muestras(self):
        if not self._muestras:
            return None
        return {"io": statistics.median(x[1] for x in self._muestras),
                "cejas": statistics.median(x[2] for x in self._muestras),
                "sonrisa": statistics.median(x[3] for x in self._muestras)}

    def _compatible(self) -> bool:
        """¿La cara del último segundo se parece a la huella de la persona? Sin huella, sí."""
        h = self._huella
        if h is None:
            return True
        ahora = self._huella_de_muestras()
        if ahora is None:
            return True
        for k, tol in HUELLA_TOL.items():
            ref = h.get(k)
            if ref and abs(ahora[k] - ref) / ref > tol:
                return False
        return True

    def _aprender_huella(self, t: float, g: ResultadoGestos):
        """Con la cara de confianza y en reposo (sin gestos): la huella sigue despacio los cambios
        de distancia y de postura del día."""
        if not self._muestras or self._cara_en_espera(t) or g.activos or self._afuera:
            return
        _t, io, cj, so = self._muestras[-1]
        h = self._huella
        if h is None:
            self._huella = self._huella_de_muestras()
            return
        a = HUELLA_ALFA
        h["io"] += a * (io - h["io"])
        h["cejas"] += a * (cj - h["cejas"])
        h["sonrisa"] += a * (so - h["sonrisa"])

    def _otra_cara(self, t: float, acc: list):
        """La cara que quedó tras el salto no se parece a la de la persona: pausa automática."""
        log.info("La cara nueva no se parece a la de la persona: pausa hasta que vuelva")
        acc.append(Aviso("otra_cara"))
        if self.estado == K.PAUSA:
            if self.pausa_auto:
                self.motivo_pausa = MOTIVO_OTRA_CARA
            return
        self._pausar(t, MOTIVO_OTRA_CARA, acc, auto=True)

    def _cara_en_espera(self, t: float) -> bool:
        return self._t_cara_nueva is not None and t - self._t_cara_nueva < CARA_ESTABLE_S - 1e-9

    def _sin_cara(self, t: float, acc: list):
        self._t_cara_desde = None
        if self._recentrar is not None and not self._recentrar.get("auto"):
            acc.append(Aviso("recentrar_cancelado"))
        self._recentrar = None
        if self._t_sin_cara is None:
            self._t_sin_cara = t
        self.puntero.perder_cara(t)
        self.perm.reiniciar()
        if self.estado == K.ACTIVO:
            self.estado = K.SIN_CARA
            self._soltado_sin_cara = False
        if self.estado != K.SIN_CARA:
            return
        seg = self.cfg["seguridad"]
        dur = t - self._t_sin_cara
        if not self._soltado_sin_cara and dur >= seg["soltar_sin_cara_ms"] / 1000.0 - 1e-9:
            self._soltado_sin_cara = True
            acc.append(SoltarTodo("sin cara"))
            self._salir_de_submodos_con_boton(acc)
            self._sonido("perdida", acc)
            acc.append(Aviso("sin_cara"))
        if dur >= seg["pausa_sin_cara_s"] - 1e-9:
            self._pausar(t, "sin_cara", acc, auto=True)

    def _paso_recentrar(self, t: float, m, acc: list):
        r = self._recentrar
        if r is None:
            return
        r["yaw"].append(m.yaw_n)
        r["pitch"].append(m.pitch_n)
        if t - r["t0"] >= RECENTRAR_S - 1e-9 and len(r["yaw"]) >= 3:
            self.mapeo.recentrar(statistics.median(r["yaw"]), statistics.median(r["pitch"]))
            self._centrado = True
            self._recentrar = None
            self.puntero.reiniciar_filtros(t)
            self._desarmar_tras_deslizar(t)     # el deslizamiento al centro nuevo no hace clic
            if not r.get("auto"):
                acc.append(Aviso("recentrado"))

    # ------------------------------------------------------------ PAUSA
    def _en_pausa(self, t: float, m, g: ResultadoGestos, acc: list) -> EstadoPermanencia:
        # el puntero no se mueve, pero se calcula a dónde apunta la cabeza (para "Reanudar")
        pos = self.puntero.actualizar(t, m.yaw_n, m.pitch_n)
        if self.pausa_auto and not self._compatible():
            self._t_cara_desde = t        # otra cara (el cuidador): no reanuda sola
            if self.motivo_pausa != MOTIVO_OTRA_CARA and len(self._muestras) >= 3 \
                    and self._muestras[-1][0] - self._muestras[0][0] >= CARA_ESTABLE_S - 0.1:
                self.motivo_pausa = MOTIVO_OTRA_CARA   # el aviso dice cómo seguir (Reanudar)
        if self.pausa_auto and self._t_cara_desde is not None and not self._cara_en_espera(t) \
                and t - self._t_cara_desde >= ESTABLE_PARA_REANUDAR_S - 1e-9:
            self._reanudar(t, "cara de nuevo", acc)
            return EstadoPermanencia()
        reanudar_s = self.cfg["gestos"]["reanudar_ms"] / 1000.0
        if self.motivo_pausa not in MOTIVOS_CUIDADOR:
            # el gesto vale al SOLTARLO, si duró entre reanudar_ms y 2,5 s más (más largo es un
            # bostezo o un descanso; con los ojos cerrados es bostezo y ni siquiera llega aquí)
            pausa = self._gestos_de_pausa()
            for sol in g.soltados:
                if sol.nombre in pausa and \
                        reanudar_s - 1e-9 <= sol.duracion_ms / 1000.0 <= reanudar_s + REANUDAR_VENTANA_S:
                    self._reanudar(t, f"gesto {sol.nombre}", acc)
                    return EstadoPermanencia()
        if self._reanuda_con_doble_parpadeo():
            if any(isinstance(e, DobleParpadeoLargo) for e in g.eventos):
                self._reanudar(t, "doble parpadeo", acc)
                return EstadoPermanencia()
        # 1.1: el gesto LARGO asignado a «emergencia» pide ayuda también en pausa (la pausa del
        # cuidador incluida): solo el gesto largo completo, un bostezo corto no basta
        if self._gesto_largo_emergencia(g):
            self._pedir_ayuda(t, "gesto", acc)
            return EstadoPermanencia()
        candidatos = [o for o in self._objetivos_libres(pos, t)
                      if o.id in IDS_REANUDAR + (ID_BARRA_MOSTRAR,) + IDS_EMERGENCIA and o.elegible]
        obj = self._con_tiempo_emergencia(buscar_objetivo(pos, candidatos, self._obj_actual))
        self._obj_actual = obj
        if g.gesto_activo:
            self.perm.reiniciar()
            return EstadoPermanencia()
        st = self.perm.actualizar(pos, t, obj, libre=False, tiempo_objetivo_s=REANUDAR_PERMANENCIA_S)
        if st.disparo and st.objetivo:
            acc.append(Elegir(st.objetivo))
            if st.objetivo == ID_BARRA_MOSTRAR:
                return st                  # abrir la barra minimizada no reanuda
            if st.objetivo in IDS_EMERGENCIA:
                self._pedir_ayuda(t, "botón", acc)
                return st
            self._reanudar(t, "botón Reanudar", acc)
        return st

    # ------------------------------------------------------------ ACTIVO
    def _revisar_temblor(self):
        """La cámara va más lenta de lo supuesto: el puntero recalculó su temblor y el radio de la
        permanencia crece con él (no hay clics fantasma con la cabeza quieta)."""
        if self.puntero.temblor_cambio:
            self.puntero.temblor_cambio = False
            self.perm.ajustar_radio_minimo(RADIO_SIGMAS * self.puntero.temblor_px)

    def _mirando_afuera(self, t: float, m) -> bool:
        """¿La cabeza está muy por fuera de su rango cómodo (mira a otro lado)? Con histéresis.
        Al volver, el deslizamiento del puntero no arma la permanencia."""
        try:
            u, v = self.mapeo.normalizar(float(m.yaw_n), float(m.pitch_n))
            a = max(abs(u), abs(v))
        except (AttributeError, TypeError, ValueError):
            return self._afuera
        if not math.isfinite(a):
            return self._afuera
        if self._afuera:
            if a < U_AFUERA_VUELVE:
                self._afuera = False
                self._desarmar_tras_deslizar(t, MEZCLA_DESCONGELAR_S)
                log.info("La cabeza volvió a su rango cómodo")
        elif a > U_AFUERA:
            self._afuera = True
            self.perm.reiniciar()
            log.info("La cabeza mira fuera de su rango cómodo: puntero quieto y sin clics")
        return self._afuera

    def _quitar_gestos_de_clic(self, g: ResultadoGestos):
        """Mirando a otro lado: solo cuentan los gestos que pausan."""
        gc = self.cfg["gestos"]
        quedan = []
        for ev in g.eventos:
            if isinstance(ev, GestoCorto):
                ok = gc[ev.nombre]["corto"] == "pausar"
            elif isinstance(ev, GestoLargo):
                ok = gc[ev.nombre]["largo"] in ("pausar", "emergencia")   # 1.1: pedir ayuda mirando a otro lado
            elif isinstance(ev, ParpadeoLargo):
                ok = gc["parpadeo"].get("fuera_barrido", "ninguna") == "pausar"
            else:
                ok = not isinstance(ev, ParpadeoListo)
            if ok:
                quedan.append(ev)
        g.eventos = quedan

    def _en_activo(self, t: float, m, g: ResultadoGestos, dt: float, acc: list) -> EstadoPermanencia:
        sub = self.submodo
        afuera = sub not in SUBMODOS_SIN_PUNTERO and self._mirando_afuera(t, m)
        if afuera:
            self._quitar_gestos_de_clic(g)
        congelar = (afuera or g.gesto_activo or (g.ojos_cerrando and self._parpadeo_con_accion())
                    or self._recentrar is not None or sub == K.DESPLAZAR or sub in SUBMODOS_SIN_PUNTERO
                    or self._cara_en_espera(t))
        if congelar:
            self.puntero.congelar(t)
        else:
            if self.puntero.congelado and self._clic_gesto_congelado:
                self._desarmar_hasta = t + DESARMAR_TRAS_GESTO_S
            self._clic_gesto_congelado = False
            self.puntero.descongelar(t)
        pos = self.puntero.actualizar(t, m.yaw_n, m.pitch_n)
        self._revisar_temblor()
        if self.puntero.cambio and sub not in SUBMODOS_SIN_PUNTERO:
            acc.append(Mover(*pos))
        # ---- eventos de gestos ----
        for ev in g.eventos:
            if isinstance(ev, GestoCorto):
                corto = self.cfg["gestos"][ev.nombre]["corto"]
                if corto != "emergencia":       # 1.1: el gesto corto nunca pide ayuda
                    self._accion_gesto(corto, t, pos, acc, ev.nombre)
            elif isinstance(ev, GestoLargo):
                self._accion_gesto(self.cfg["gestos"][ev.nombre]["largo"], t, pos, acc, ev.nombre)
            elif isinstance(ev, ParpadeoLargo):
                if self.submodo in SUBMODOS_SIN_PUNTERO:
                    accion = "elegir"
                else:
                    accion = self.cfg["gestos"]["parpadeo"].get("fuera_barrido", "ninguna")
                if accion != "emergencia":      # 1.1: el parpadeo nunca pide ayuda
                    self._accion_gesto(accion, t, pos, acc, None)
            elif isinstance(ev, ParpadeoListo):
                if self._parpadeo_con_accion():
                    self._sonido("listo", acc)
            if self.estado != K.ACTIVO or self.emergencia:
                return EstadoPermanencia()
        sub = self.submodo
        # ---- arrastre: tope de seguridad ----
        if sub == K.ARRASTRANDO and self._t_arrastre is not None \
                and t - self._t_arrastre >= self.cfg["seguridad"]["arrastre_max_s"] - 1e-9:
            acc.append(Subir(K.IZQ))
            acc.append(Aviso("arrastre_largo"))
            self.submodo = K.NORMAL
            self._t_arrastre = None
            self._volver_modo_clic()
            self.perm.marcar_disparo(pos, t)
            return EstadoPermanencia()
        # ---- desplazar ----
        if sub == K.DESPLAZAR:
            self._paso_desplazar(t, dt, acc)
            if self.submodo != K.DESPLAZAR:
                return EstadoPermanencia()
            return self._permanencia_terminar(t, acc)
        if self.puntero.velocidad < QUIETO_PX_S and not sobre_ventana_propia(pos, self.objetivos):
            self._ult_pos_externa = pos       # donde la persona estaba trabajando (puntero casi quieto)
        if sub in SUBMODOS_SIN_PUNTERO:
            self.perm.reiniciar()
            return EstadoPermanencia()
        # ---- lupa abierta ----
        if sub == K.LUPA:
            return self._paso_lupa(t, pos, afuera, acc)
        # ---- permanencia ----
        if self.puntero.congelado or afuera:
            self.perm.reiniciar()
            return EstadoPermanencia()
        if self.puntero.modo == "joystick" and self.puntero.joystick_moviendo:
            # el joystick lleva el puntero a velocidad constante (o muy lenta): eso no es "quieto"
            self.perm.reiniciar()
            return EstadoPermanencia()
        if sub == K.ARRASTRANDO:
            # arrastrando, quedarse quieto suelta el botón; solo AYUDA se puede elegir encima
            obj = buscar_objetivo(pos, [o for o in self._objetivos_libres(pos, t)
                                        if o.id in IDS_EMERGENCIA and o.elegible], self._obj_actual)
        else:
            obj = buscar_objetivo(pos, self._objetivos_libres(pos, t), self._obj_actual)
        obj = self._con_tiempo_emergencia(obj)
        self._obj_actual = obj
        libre = bool(self._p_cfg["activa"]) and (sub == K.ARRASTRANDO or not sobre_ventana_propia(pos, self.objetivos))
        if self.modo_clic == "ninguno" and sub == K.NORMAL:
            libre = False           # «Sin clic»: quedarse quieto fuera de lo propio no hace nada
        tiempo_obj = None
        if obj is not None:
            if obj.id.startswith(("tecla:", "frase:", "sugerencia:", "accion:")):
                tiempo_obj = self.cfg["teclado"]["permanencia_s"]
            elif obj.id == ID_REANUDAR:
                tiempo_obj = REANUDAR_PERMANENCIA_S
            else:
                tiempo_obj = self.cfg["barra"]["permanencia_s"]
        if self._desarmar_hasta is not None:
            if t < self._desarmar_hasta:
                self.perm.desarmar(pos)
            else:
                self._desarmar_hasta = None
        st = self.perm.actualizar(pos, t, obj, libre, tiempo_obj)
        if st.disparo:
            if st.objetivo:
                self._elegir(st.objetivo, t, pos, acc)
            else:
                if self._p_cfg.get("sonido", True):
                    self._sonido("clic", acc)
                self._clic_actual(t, pos, acc, por_permanencia=True)
        return st

    def _permanencia_terminar(self, t: float, acc: list) -> EstadoPermanencia:
        """En Desplazar el puntero real queda quieto sobre la página, pero la cabeza sigue
        apuntando: con ese puntero "virtual" se puede elegir «Terminar» quedándose quieto."""
        f = self.puntero.filtrado
        if f is None:
            return EstadoPermanencia()
        vpos = self.mapeo.recortar(*f)
        candidatos = [o for o in self._objetivos_libres(vpos, t)
                      if o.id in (ID_TERMINAR_DESPLAZAR,) + IDS_EMERGENCIA and o.elegible]
        obj = self._con_tiempo_emergencia(buscar_objetivo(vpos, candidatos, self._obj_actual))
        self._obj_actual = obj
        if obj is None:
            self.perm.reiniciar()
            return EstadoPermanencia()
        st = self.perm.actualizar(vpos, t, obj, libre=False, tiempo_objetivo_s=self.cfg["barra"]["permanencia_s"])
        if st.disparo and st.objetivo:
            self._elegir(st.objetivo, t, self.puntero.posicion, acc)
        return st

    def _paso_desplazar(self, t: float, dt: float, acc: list):
        if self._afuera:
            # mirando a otro lado (a comer, al cuidador): no se desplaza, y tampoco cuenta como
            # "seguir desplazando" (el modo termina solo a los 10 s)
            self._desp_acum = 0.0
            if self._t_ult_desp is not None and t - self._t_ult_desp >= DESPLAZAR_INACTIVO_S - 1e-9:
                self._terminar_desplazar(t, acc)
            return
        u, v = self.puntero.uv_actual()
        if self._desp_ref is None:
            self._desp_ref = (u, v)
            self._t_ult_desp = t
        dv = v - self._desp_ref[1]
        a = abs(dv)
        if a > DESPLAZAR_ZONA:
            f = min((a - DESPLAZAR_ZONA) / (DESPLAZAR_TOPE - DESPLAZAR_ZONA), 1.0)
            rapidez = DESPLAZAR_MIN + (DESPLAZAR_MAX - DESPLAZAR_MIN) * f
            # cabeza abajo (v crece) = bajar la página = rueda negativa
            self._desp_acum += -math.copysign(rapidez * dt, dv)
            if a > DESPLAZAR_CLARO:
                self._t_ult_desp = t      # descansar apenas inclinado no cuenta como "seguir"
        else:
            self._desp_acum = 0.0
        n = int(self._desp_acum)
        if n:
            self._desp_acum -= n
            acc.append(Rueda(n * K.WHEEL_DELTA))
        if self._t_ult_desp is not None and t - self._t_ult_desp >= DESPLAZAR_INACTIVO_S - 1e-9:
            self._terminar_desplazar(t, acc)
        elif self._t_desp_inicio is not None and t - self._t_desp_inicio >= DESPLAZAR_MAX_S - 1e-9:
            self._terminar_desplazar(t, acc)

    def _entrar_desplazar(self, t: float, acc: list):
        self._salir_de_submodos_con_boton(acc)
        self.submodo = K.DESPLAZAR
        self.modo_clic = "desplazar"
        self._desp_ref = None
        self._desp_acum = 0.0
        self._t_ult_desp = t
        self._t_desp_inicio = t
        # la rueda va a la ventana que está bajo el puntero: si se eligió desde la barra, el
        # puntero vuelve a la página donde estaba antes de ir a la barra
        p = self._ult_pos_externa
        if p is not None and sobre_ventana_propia(self.puntero.posicion, self.objetivos):
            self.puntero.fijar_posicion(*p)
            self.puntero.congelado = False
            self.puntero.congelar(t)
            acc.append(Mover(*self.puntero.posicion))
        self.perm.reiniciar()
        acc.append(Aviso("desplazar"))

    def _terminar_desplazar(self, t: float, acc: list):
        if self.submodo != K.DESPLAZAR:
            return
        self.submodo = K.NORMAL
        self._desp_ref = None
        self._desp_acum = 0.0
        self._t_desp_inicio = None
        self.modo_clic = "izq"
        self.puntero.descongelar(t)
        self.perm.desarmar(self.puntero.posicion)
        acc.append(Aviso("desplazar_fin"))

    # ------------------------------------------------------------ clics
    def _clic_actual(self, t: float, pos, acc: list, por_permanencia: bool = False):
        """La acción de clic vigente (``modo_clic`` y el submodo)."""
        sub = self.submodo
        if sub == K.ARRASTRE_INICIO:
            acc.append(Bajar(K.IZQ))
            self.submodo = K.ARRASTRANDO
            self._t_arrastre = t
            # para soltar hay que moverse primero (si no, soltaría en el mismo sitio)
            self.perm.marcar_disparo(pos, t, distancia=self.perm.radio)
            acc.append(Aviso("arrastrando"))
            return
        if sub == K.ARRASTRANDO:
            acc.append(Subir(K.IZQ))
            self._t_arrastre = None
            if self.cfg["barra"].get("modo_fijo", False):
                self.submodo = K.ARRASTRE_INICIO
            else:
                self.submodo = K.NORMAL
                self.modo_clic = "izq"
            self.perm.marcar_disparo(pos, t)
            acc.append(Aviso("arrastre_fin"))
            return
        modo = self.modo_clic
        if modo == "lupa":
            self._abrir_lupa(t, pos, acc)
            return
        if modo == "ninguno":
            # «Sin clic»: solo llega aquí un gesto de clic (es a propósito) y el modo sigue
            acc.append(Clic(K.IZQ))
            self.perm.marcar_disparo(pos, t)
            return
        if modo == "doble":
            acc.append(Clic(K.IZQ, 2))
        elif modo == "der":
            acc.append(Clic(K.DER))
        else:
            acc.append(Clic(K.IZQ))
        self._volver_modo_clic()
        self.perm.marcar_disparo(pos, t)

    def _accion_gesto(self, accion: str, t: float, pos, acc: list, nombre: str | None):
        if not accion or accion == "ninguna":
            return
        if accion == "emergencia":
            # 1.1: solo llega aquí el gesto largo (la validación y _en_activo filtran los demás).
            # El gesto largo se cuenta al soltarlo: no hay tramo en curso que consumir.
            self._pedir_ayuda(t, "gesto", acc)
            return
        sub = self.submodo
        if sub in SUBMODOS_SIN_PUNTERO:
            # en el barrido el puntero no se usa: un gesto de clic elige lo resaltado
            if accion in ACCIONES_CLIC or accion == "elegir":
                acc.append(Elegir(ID_BARRIDO_ELEGIR))
                return
            if accion == "siguiente":
                acc.append(Elegir(ID_BARRIDO_SIGUIENTE))
                return
        if accion in ACCIONES_CLIC or accion == "elegir":
            if sub == K.DESPLAZAR:
                self._terminar_desplazar(t, acc)
                return
            if sub == K.LUPA:
                self._gesto_en_lupa(t, pos, acc)
                return
            if sub != K.ARRASTRANDO:
                obj = buscar_objetivo(pos, self.objetivos, self._obj_actual)
                if obj is not None and obj.id in IDS_EMERGENCIA:
                    # AYUDA se pide quedándose quieto: un gesto de clic encima (hablar, bostezar)
                    # no la dispara; se recuerda cómo pedirla
                    acc.append(Aviso("emergencia_quieto"))
                    return
                if obj is not None:
                    self._elegir(obj.id, t, pos, acc)
                    self.perm.marcar_disparo(pos, t)
                    return
                if sobre_ventana_propia(pos, self.objetivos):
                    acc.append(Aviso("sobre_ventana"))
                    return
            if accion == "elegir":
                return
            self._sonido("clic", acc)
            self._clic_gesto_congelado = self.puntero.congelado
            self._desarmar_hasta = t + DESARMAR_TRAS_GESTO_S
            if accion == "clic" or sub in (K.ARRASTRE_INICIO, K.ARRASTRANDO):
                self._clic_actual(t, pos, acc)
            elif accion == "clic_izq":
                acc.append(Clic(K.IZQ))
                self.perm.marcar_disparo(pos, t)
            elif accion == "clic_der":
                acc.append(Clic(K.DER))
                self.perm.marcar_disparo(pos, t)
            elif accion == "doble":
                acc.append(Clic(K.IZQ, 2))
                self.perm.marcar_disparo(pos, t)
            elif accion == "arrastrar":
                self.submodo = K.ARRASTRE_INICIO
                self._clic_actual(t, pos, acc)
            return
        if accion == "pausar":
            if nombre:
                self.gestos.consumir(nombre)
            self._pausar(t, "gesto", acc)
        elif accion == "teclado":
            acc.append(Aviso("teclado"))
        elif accion == "recentrar":
            acc += self.recentrar(t)
        elif accion in ("borrar", "hablar"):
            acc.append(Elegir(f"accion:{accion}"))
        elif accion == "siguiente":
            acc.append(Elegir(ID_BARRIDO_SIGUIENTE))

    def _elegir(self, ident: str, t: float, pos, acc: list):
        """Un objetivo propio elegido (permanencia o gesto). Nunca es un clic de Windows."""
        if ident == lupa_mod.ID_ZONA:
            if self.submodo == K.LUPA:
                self._clic_lupa(t, pos, acc)
            return
        if ident in IDS_EMERGENCIA:
            acc.append(Elegir(ident))
            self._pedir_ayuda(t, "cuidador" if self._por_cuidador else "botón", acc)
            return
        if ident == ID_ATENDIDO:
            self._atendido(t, "cuidador" if self._por_cuidador else "persona", acc)
            return
        acc.append(Elegir(ident))
        self._sonido("clic", acc)
        modo_antes = self.modo_clic
        if self.submodo == K.LUPA and ident != ID_BARRA_MOSTRAR:
            # cualquier otro botón con la lupa abierta la cierra primero, sin clic
            self._cerrar_lupa(acc)
            if ident == lupa_mod.ID_CERRAR:
                return
        if ident in ("barra:sin_clic", "barra:lupa"):
            modo = "ninguno" if ident == "barra:sin_clic" else "lupa"
            if self.submodo in (K.ARRASTRE_INICIO, K.DESPLAZAR):
                self._terminar_desplazar(t, acc)
                self.submodo = K.NORMAL
            if modo_antes == modo:              # elegirlo otra vez (también con la lupa abierta) lo apaga
                self.modo_clic = "izq"
            else:
                self.modo_clic = modo
                if modo == "ninguno":
                    acc.append(Aviso("sin_clic"))
            return
        if ident == "barra:clic":
            if self.submodo in (K.ARRASTRE_INICIO, K.DESPLAZAR):
                self._terminar_desplazar(t, acc)
                self.submodo = K.NORMAL
            self.modo_clic = "izq"
        elif ident == "barra:doble":
            self.modo_clic = "izq" if self.modo_clic == "doble" else "doble"
        elif ident == "barra:derecho":
            self.modo_clic = "izq" if self.modo_clic == "der" else "der"
        elif ident == "barra:arrastrar":
            if self.submodo == K.ARRASTRE_INICIO:
                self.submodo = K.NORMAL
                self.modo_clic = "izq"
            elif self.submodo != K.ARRASTRANDO:
                self.submodo = K.ARRASTRE_INICIO
                self.modo_clic = "arrastrar"
        elif ident == "barra:desplazar":
            if self.submodo == K.DESPLAZAR:
                self._terminar_desplazar(t, acc)
            else:
                self._entrar_desplazar(t, acc)
        elif ident == ID_TERMINAR_DESPLAZAR:
            self._terminar_desplazar(t, acc)
        elif ident == "barra:pausa":
            self._pausar(t, "cuidador" if self._por_cuidador else "botón Pausa", acc)
        elif ident == "barra:teclado":
            acc.append(Aviso("teclado"))

    # ------------------------------------------------------------ lupa (1.1 paquete A)
    def cancelar_lupa(self, t: float | None = None) -> list:
        """Opciones abiertas o cualquier «soltar todo» de la interfaz: la lupa se cierra sin clic."""
        acc: list = []
        if self.submodo == K.LUPA:
            self._cerrar_lupa(acc)
        return acc

    def lupa_fallo(self, t: float | None = None) -> list:
        """La interfaz no pudo agrandar la zona (pantalla protegida, error de la captura): se
        vuelve a NORMAL sin hacer ningún clic."""
        acc: list = []
        if self.submodo == K.LUPA:
            self.submodo = K.NORMAL
            self._lupa = None
            self._volver_modo_clic()
            self.perm.reiniciar()
            acc.append(Aviso("lupa_no_captura"))
            log.info("La lupa no pudo capturar la zona: no se hace clic")
        return acc

    def _abrir_lupa(self, t: float, pos, acc: list):
        """La permanencia libre (o el gesto de clic) en el modo «Lupa»: en vez de hacer clic se
        abre la lupa alrededor del punto."""
        c = self.cfg.get("lupa") or {}
        mon = self.mapeo.monitor
        area = mon.trabajo if getattr(mon, "trabajo", None) else mon.rect
        self.perm.marcar_disparo(pos, t)
        try:
            zona = lupa_mod.zona(pos, mon.rect, c.get("zona_px", 200))
            ub = lupa_mod.ubicar_ventana(zona, area, c.get("aumento", 3))
        except (TypeError, ValueError, IndexError):
            zona = ub = None
        if ub is None:
            acc.append(Aviso("lupa_no_captura"))
            self._volver_modo_clic()
            log.info("La lupa no cabe sin tapar la zona: no se abre")
            return
        self._lupa = {"zona": zona, "ventana": ub.ventana, "imagen": ub.imagen, "t0": t}
        self.submodo = K.LUPA
        self._obj_actual = None
        acc.append(Elegir(lupa_mod.id_abrir(zona, ub)))
        log.info("Lupa abierta")

    def _cerrar_lupa(self, acc: list, aviso: bool = True):
        """Cierra la lupa SIN hacer clic (Cerrar lupa, tiempo vencido, pausa, sin cara, mirando
        afuera, calibración, teclado, Opciones o cualquier «soltar todo»)."""
        if self.submodo != K.LUPA and self._lupa is None:
            return
        if self.submodo == K.LUPA:
            self.submodo = K.NORMAL
        self._lupa = None
        acc.append(Elegir(lupa_mod.ID_CERRAR))
        if aviso:
            acc.append(Aviso("lupa_cerrada"))
        self._volver_modo_clic()
        self.perm.reiniciar()
        log.info("Lupa cerrada sin clic")

    def _zona_lupa(self):
        return next((o for o in self.objetivos if o.id == lupa_mod.ID_ZONA), None)

    def _clic_lupa(self, t: float, pos, acc: list):
        """Clic en el punto real que corresponde al punto de la imagen agrandada."""
        lp = self._lupa
        if lp is None:
            return
        zobj = self._zona_lupa()
        imagen = zobj.rect if zobj is not None else lp["imagen"]
        x, y = lupa_mod.a_pantalla(pos, imagen, lp["zona"])
        acc.append(Mover(x, y))
        acc.append(Clic(K.IZQ))
        self.submodo = K.NORMAL
        self._lupa = None
        acc.append(Elegir(lupa_mod.ID_CERRAR))
        # el puntero queda en el punto real y vuelve deslizándose a donde apunta la cabeza: ese
        # deslizamiento no arma la permanencia
        self.puntero.fijar_posicion(x, y, t)
        self._desarmar_tras_deslizar(t)
        self.perm.marcar_disparo(self.puntero.posicion, t)
        self._volver_modo_clic()
        log.info("Clic con la lupa")

    def _gesto_en_lupa(self, t: float, pos, acc: list):
        """Un gesto de clic con la lupa abierta: sobre un botón lo elige; sobre la imagen hace el
        clic preciso; en cualquier otra parte no hace nada."""
        otros = [o for o in self.objetivos if o.id != lupa_mod.ID_ZONA]
        obj = buscar_objetivo(pos, otros, self._obj_actual)
        if obj is not None and obj.id in IDS_EMERGENCIA:
            acc.append(Aviso("emergencia_quieto"))     # 1.1: AYUDA solo quedándose quieto
            return
        if obj is not None:
            self._elegir(obj.id, t, pos, acc)
            self.perm.marcar_disparo(pos, t)
            return
        zobj = self._zona_lupa()
        if zobj is not None and zobj.contiene(*pos):
            self._sonido("clic", acc)
            self._clic_lupa(t, pos, acc)

    def _paso_lupa(self, t: float, pos, afuera: bool, acc: list) -> EstadoPermanencia:
        """Con la lupa abierta el puntero se mueve igual que siempre. Quedarse quieto sobre la
        imagen hace el clic preciso; sobre «Cerrar lupa» (u otro botón) lo elige."""
        lp = self._lupa
        if lp is None:
            self.submodo = K.NORMAL
            return EstadoPermanencia()
        espera = float((self.cfg.get("lupa") or {}).get("espera_s", 8.0))
        if afuera or t - lp["t0"] >= espera - 1e-9:
            self._cerrar_lupa(acc)
            return EstadoPermanencia()
        if self.puntero.congelado or (self.puntero.modo == "joystick" and self.puntero.joystick_moviendo):
            self.perm.reiniciar()
            return EstadoPermanencia()
        zobj = self._zona_lupa()
        otros = [o for o in self._objetivos_libres(pos, t) if o.id != lupa_mod.ID_ZONA]
        obj = self._con_tiempo_emergencia(buscar_objetivo(pos, otros, self._obj_actual))
        self._obj_actual = obj
        libre = obj is None and zobj is not None and zobj.contiene(*pos) and bool(self._p_cfg["activa"])
        tiempo_obj = self.cfg["barra"]["permanencia_s"] if obj is not None else None
        if self._desarmar_hasta is not None:
            if t < self._desarmar_hasta:
                self.perm.desarmar(pos)
            else:
                self._desarmar_hasta = None
        st = self.perm.actualizar(pos, t, obj, libre, tiempo_obj)
        if st.disparo:
            if st.objetivo:
                self._elegir(st.objetivo, t, pos, acc)
            else:
                if self._p_cfg.get("sonido", True):
                    self._sonido("clic", acc)
                self._clic_lupa(t, pos, acc)
        return st

    # ------------------------------------------------------------ emergencia (1.1 paquete B)
    def pedir_ayuda(self, t: float, origen: str = "cuidador") -> list:
        """Pide AYUDA (botón, gesto largo, barrido o el ratón del cuidador). Vale en cualquier
        estado, también en pausa."""
        acc: list = []
        self._pedir_ayuda(t, origen, acc)
        return acc

    def atendido(self, t: float, origen: str = "atajo") -> list:
        """Apaga la emergencia («Ya me atendieron», Esc, el ratón o el atajo del cuidador). Sin
        emergencia no hace nada."""
        acc: list = []
        self._atendido(t, origen, acc)
        return acc

    def _gesto_largo_emergencia(self, g: ResultadoGestos) -> bool:
        gc = self.cfg["gestos"]
        return any(isinstance(ev, GestoLargo) and gc[ev.nombre]["largo"] == "emergencia"
                   for ev in g.eventos)

    def _con_tiempo_emergencia(self, obj):
        """Los botones AYUDA piden quedarse quieto ``emergencia.permanencia_s`` (2,5 s), más que
        un botón normal, aunque la interfaz publique otro tiempo; «Ya me atendieron» pide
        ``emergencia.detener_s``."""
        if obj is None:
            return None
        if obj.id in IDS_EMERGENCIA:
            return replace(obj, tiempo_s=float(self.cfg["emergencia"]["permanencia_s"]))
        if obj.id == ID_ATENDIDO:
            return replace(obj, tiempo_s=float(self.cfg["emergencia"]["detener_s"]))
        return obj

    def _pedir_ayuda(self, t: float, origen: str, acc: list):
        if self.emergencia:
            return
        # primero se suelta el botón de un arrastre y se sale de los submodos con botón
        self._salir_de_submodos_con_boton(acc)
        acc.append(SoltarTodo("emergencia"))
        self._estado_antes_emergencia = self.estado
        if self.estado == K.SIN_CARA:
            self.estado = K.ACTIVO               # al terminar sigue como siempre (sin cara: pausa)
        self.emergencia = True
        self._t_emergencia = t
        self._recentrar = None
        self._t_sin_cara = None
        self._soltado_sin_cara = False
        self.perm.reiniciar()
        self._obj_actual = None
        self.puntero.congelado = False
        self.puntero.fijar_posicion(*self._pos_real(), t)
        # «Ya me atendieron» aparece en el centro: si el puntero ya estaba ahí, primero hay que
        # salir y volver (si no, quien descansa quieto apagaría su propia alarma)
        self._bloquear((ID_ATENDIDO,), t)
        acc.append(Aviso("emergencia", origen))
        log.info("Emergencia activada (%s)", origen)

    def _atendido(self, t: float, origen: str, acc: list):
        if not self.emergencia:
            return
        self.emergencia = False
        self._t_emergencia = None
        acc.append(SoltarTodo("emergencia atendida"))
        self.perm.reiniciar()
        self._obj_actual = None
        self._t_sin_cara = None
        self._soltado_sin_cara = False
        # AYUDA queda bloqueado hasta que el puntero salga de él (no se vuelve a pedir quieto encima)
        self._bloquear(IDS_EMERGENCIA + (ID_ATENDIDO,), t)
        # el gesto que estaba en curso no hace nada al soltarlo
        self.gestos.refractario_hasta(t + REFRACTARIO_FIN_CALIBRACION_S)
        for n in ("boca", "cejas", "sonrisa"):
            if self.gestos.duracion_sostenida(n, t) > 0:
                self.gestos.consumir(n)
        if self.estado == K.ACTIVO:
            self.puntero.fijar_posicion(*self._pos_real(), t)
            self._desarmar_tras_deslizar(t)
        acc.append(Aviso("emergencia_fin", origen))
        log.info("Emergencia apagada (%s)", origen)

    def _paso_emergencia(self, t: float, m, g: ResultadoGestos, acc: list) -> EstadoPermanencia:
        """Durante la emergencia el puntero sigue a la cabeza (para llegar a «Ya me atendieron»),
        pero ningún clic llega a Windows: ni por permanencia ni por gesto."""
        if m is None:
            # la cara perdida no detiene nada: el puntero queda donde estaba
            self.puntero.perder_cara(t)
            self.perm.reiniciar()
            self._obj_actual = None
            return EstadoPermanencia()
        if self.puntero.congelado:
            self.puntero.descongelar(t)
        pos = self.puntero.actualizar(t, m.yaw_n, m.pitch_n)
        if self.puntero.cambio:
            acc.append(Mover(*pos))
        candidatos = [o for o in self._objetivos_libres(pos, t) if o.id == ID_ATENDIDO and o.elegible]
        obj = self._con_tiempo_emergencia(buscar_objetivo(pos, candidatos, self._obj_actual))
        self._obj_actual = obj
        st = self.perm.actualizar(pos, t, obj, libre=False,
                                  tiempo_objetivo_s=self.cfg["emergencia"]["detener_s"])
        if st.disparo and st.objetivo == ID_ATENDIDO:
            acc.append(Elegir(ID_ATENDIDO))
            self._atendido(t, "persona", acc)
        return st

    # ------------------------------------------------------------ vista
    def _vista(self, t: float, g: ResultadoGestos, st: EstadoPermanencia, m) -> Vista:
        r = self._recentrar
        v = Vista(
            estado=self.estado, submodo=self.submodo, modo_clic=self.modo_clic,
            motivo_pausa=self.motivo_pausa, pausa_auto=self.pausa_auto,
            puntero=self.puntero.posicion if self.estado != K.PAUSA or self.emergencia else None,
            puntero_virtual=(self.puntero.posicion if self.estado == K.PAUSA and m is not None
                             and not self.emergencia else None),
            permanencia=st, gestos=g,
            sin_cara_s=(t - self._t_sin_cara) if self._t_sin_cara is not None else 0.0,
            recentrando=(min((t - r["t0"]) / RECENTRAR_S, 1.0) if r is not None else None),
            calibrado=self.calibracion is not None, congelado=self.puntero.congelado,
            arrastre_s=(t - self._t_arrastre) if self._t_arrastre is not None else 0.0,
            medidas=m, objetivo=self._obj_actual.id if self._obj_actual is not None else None,
            reanuda_parpadeo=self.estado == K.PAUSA and self.reanuda_con_parpadeo(),
            mirando_afuera=self._afuera and self.estado == K.ACTIVO,
            emergencia=self.emergencia)
        self._ultima_vista = v
        return v

    @property
    def vista(self) -> Vista:
        return self._ultima_vista
