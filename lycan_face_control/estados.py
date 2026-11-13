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
from dataclasses import dataclass, field

from . import constantes as K
from .acciones import Aviso, Bajar, Clic, Elegir, Mover, Rueda, Sonido, SoltarTodo, Subir
from .config import calibracion_activa
from .gestos import (DobleParpadeoLargo, GestoCorto, GestoLargo, Gestos, ParpadeoLargo, ParpadeoListo,
                     ResultadoGestos)
from .mapeo import MapeoCabeza, Monitor
from .permanencia import EstadoPermanencia, Permanencia, buscar_objetivo, sobre_ventana_propia
from .puntero import Puntero

log = logging.getLogger("lycan")

# Identificadores de objetivos que atiende la máquina
ID_REANUDAR = "reanudar"
ID_TERMINAR_DESPLAZAR = "desplazar:terminar"
ID_BARRIDO_ELEGIR = "barrido:elegir"
ID_BARRIDO_SIGUIENTE = "barrido:siguiente"
ID_REANUDAR_TECLADO = "teclado:reanudar"   # el botón Pausa del teclado en pantalla, en pausa
IDS_REANUDAR = (ID_REANUDAR, "barra:pausa", ID_REANUDAR_TECLADO)
REANUDAR_PERMANENCIA_S = 2.0          # permanencia sobre "Reanudar" (más larga que un botón normal)

ESTABLE_PARA_REANUDAR_S = 1.0         # pausa automática: cara estable 1 s para seguir
RECENTRAR_S = 1.5
DESPLAZAR_ZONA = 0.15                 # zona muerta del modo Desplazar (fracción del rango cómodo)
DESPLAZAR_TOPE = 0.8                  # a esta inclinación ya va a la velocidad máxima
DESPLAZAR_MIN, DESPLAZAR_MAX = 1.0, 8.0   # muescas por segundo
DESPLAZAR_INACTIVO_S = 10.0
ERRORES_FATALES = 3                   # errores en 60 s => el motor se detiene (fatal)
VENTANA_ERRORES_S = 60.0

ACCIONES_CLIC = ("clic", "clic_izq", "clic_der", "doble", "arrastrar")
MODOS_CLIC = ("izq", "doble", "der", "arrastrar", "desplazar")
SUBMODOS_SIN_PUNTERO = (K.BARRIDO, K.SOLO_COMUNICACION)


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
        self._bloqueados: set = set()           # botones ignorados hasta que el puntero salga de ellos
        self.fatal = False
        self._ultima_vista = Vista()
        self._ultimas_medidas = None

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
        self.puntero = Puntero.desde_config(cfg, self.mapeo, pos)
        self.perm = Permanencia.desde_config(cfg, self.mapeo.monitor.alto)
        self.gestos = Gestos(cfg["gestos"], self.calibracion)

    def nueva_config(self, t: float | None, cfg: dict, calibracion: dict | None = None) -> list:
        """Opciones cambiadas o calibración nueva: se rehace todo sin perder el estado."""
        acciones = [SoltarTodo("nueva configuración")]
        self.cfg = cfg
        if calibracion is not None:
            self.calibracion = calibracion
            self._centrado = True
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
        self.modo_clic = "izq"
        if t is not None:
            self.puntero.reiniciar_filtros(t)
        return acciones

    def poner_objetivos(self, objetivos):
        """Lista de ``permanencia.Objetivo`` en píxeles físicos de pantalla (la publica la interfaz)."""
        self.objetivos = list(objetivos or [])
        if self._obj_actual is not None and all(o.id != self._obj_actual.id for o in self.objetivos):
            self._obj_actual = None

    # ------------------------------------------------------------ utilidades
    def _objetivos_libres(self, pos):
        """Los objetivos sin los bloqueados. Tras pausar o reanudar, los botones Pausa y
        Reanudar no cuentan hasta que el puntero salga de ellos: si la persona se queda quieta
        encima, no se pausa y reanuda una y otra vez."""
        if not self._bloqueados:
            return self.objetivos
        x, y = pos
        for o in self.objetivos:
            if o.id in self._bloqueados and not o.contiene(x, y, 0.12):
                self._bloqueados.discard(o.id)
        self._bloqueados &= {o.id for o in self.objetivos}
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
        if self.estado == K.CALIBRANDO:
            self.estado = self._estado_previo if self._estado_previo in (K.ACTIVO, K.PAUSA) else K.PAUSA
            if self.estado == K.ACTIVO:
                self.puntero.fijar_posicion(*self._pos_real(), t)
                self.perm.desarmar(self.puntero.posicion)
        return acc

    def elegir(self, t: float, ident: str) -> list:
        """Un botón propio elegido desde fuera (el cuidador con el ratón, o la interfaz)."""
        acc: list = []
        if not ident:
            return acc
        if self.estado == K.PAUSA:
            if ident in IDS_REANUDAR:
                self._reanudar(t, "botón Reanudar", acc)
            return acc
        if self.estado in (K.ACTIVO, K.SIN_CARA):
            self._elegir(str(ident), t, self.puntero.posicion, acc)
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
        self.perm.reiniciar()
        self._obj_actual = None
        self._bloqueados |= set(IDS_REANUDAR)
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
        self.perm.desarmar(self.puntero.posicion)
        self.perm.reiniciar()
        self._obj_actual = None
        self._bloqueados |= set(IDS_REANUDAR)
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
        g = self.gestos.actualizar(medidas, t)
        st = EstadoPermanencia()
        if self.estado == K.CALIBRANDO:
            return Resultado(acc, self._vista(t, g, st, medidas))
        if medidas is None:
            self._sin_cara(t, acc)
            return Resultado(acc, self._vista(t, g, st, medidas))
        # ---- hay cara ----
        if self._t_cara_desde is None:
            self._t_cara_desde = t
        if self.estado == K.SIN_CARA:
            self.estado = K.ACTIVO
            self._t_sin_cara = None
            self._soltado_sin_cara = False
            self.perm.reiniciar()
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
        return Resultado(acc, self._vista(t, g, st, medidas))

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
            if not r.get("auto"):
                acc.append(Aviso("recentrado"))

    # ------------------------------------------------------------ PAUSA
    def _en_pausa(self, t: float, m, g: ResultadoGestos, acc: list) -> EstadoPermanencia:
        # el puntero no se mueve, pero se calcula a dónde apunta la cabeza (para "Reanudar")
        pos = self.puntero.actualizar(t, m.yaw_n, m.pitch_n)
        if self.pausa_auto and self._t_cara_desde is not None \
                and t - self._t_cara_desde >= ESTABLE_PARA_REANUDAR_S - 1e-9:
            self._reanudar(t, "cara de nuevo", acc)
            return EstadoPermanencia()
        reanudar_s = self.cfg["gestos"]["reanudar_ms"] / 1000.0
        for nombre in self._gestos_de_pausa():
            if self.gestos.duracion_sostenida(nombre, t) >= reanudar_s - 1e-9:
                self.gestos.consumir(nombre)
                self._reanudar(t, f"gesto {nombre}", acc)
                return EstadoPermanencia()
        if self.cfg["teclado"].get("solo_comunicacion") or self.submodo == K.SOLO_COMUNICACION:
            if any(isinstance(e, DobleParpadeoLargo) for e in g.eventos):
                self._reanudar(t, "doble parpadeo", acc)
                return EstadoPermanencia()
        candidatos = [o for o in self._objetivos_libres(pos) if o.id in IDS_REANUDAR and o.elegible]
        obj = buscar_objetivo(pos, candidatos, self._obj_actual)
        self._obj_actual = obj
        if g.gesto_activo:
            self.perm.reiniciar()
            return EstadoPermanencia()
        st = self.perm.actualizar(pos, t, obj, libre=False, tiempo_objetivo_s=REANUDAR_PERMANENCIA_S)
        if st.disparo and st.objetivo:
            acc.append(Elegir(st.objetivo))
            self._reanudar(t, "botón Reanudar", acc)
        return st

    # ------------------------------------------------------------ ACTIVO
    def _en_activo(self, t: float, m, g: ResultadoGestos, dt: float, acc: list) -> EstadoPermanencia:
        sub = self.submodo
        congelar = (g.gesto_activo or (g.ojos_cerrando and self._parpadeo_con_accion())
                    or self._recentrar is not None or sub == K.DESPLAZAR or sub in SUBMODOS_SIN_PUNTERO)
        if congelar:
            self.puntero.congelar(t)
        else:
            self.puntero.descongelar(t)
        pos = self.puntero.actualizar(t, m.yaw_n, m.pitch_n)
        if self.puntero.cambio and sub not in SUBMODOS_SIN_PUNTERO:
            acc.append(Mover(*pos))
        # ---- eventos de gestos ----
        for ev in g.eventos:
            if isinstance(ev, GestoCorto):
                self._accion_gesto(self.cfg["gestos"][ev.nombre]["corto"], t, pos, acc, ev.nombre)
            elif isinstance(ev, GestoLargo):
                self._accion_gesto(self.cfg["gestos"][ev.nombre]["largo"], t, pos, acc, ev.nombre)
            elif isinstance(ev, ParpadeoLargo):
                if self.submodo in SUBMODOS_SIN_PUNTERO:
                    accion = "elegir"
                else:
                    accion = self.cfg["gestos"]["parpadeo"].get("fuera_barrido", "ninguna")
                self._accion_gesto(accion, t, pos, acc, None)
            elif isinstance(ev, ParpadeoListo):
                if self._parpadeo_con_accion():
                    self._sonido("listo", acc)
            if self.estado != K.ACTIVO:
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
            return EstadoPermanencia()
        if sub in SUBMODOS_SIN_PUNTERO:
            self.perm.reiniciar()
            return EstadoPermanencia()
        # ---- permanencia ----
        if self.puntero.congelado:
            self.perm.reiniciar()
            return EstadoPermanencia()
        if sub == K.ARRASTRANDO:
            obj = None
        else:
            obj = buscar_objetivo(pos, self._objetivos_libres(pos), self._obj_actual)
        self._obj_actual = obj
        libre = bool(self._p_cfg["activa"]) and (sub == K.ARRASTRANDO or not sobre_ventana_propia(pos, self.objetivos))
        tiempo_obj = None
        if obj is not None:
            if obj.id.startswith(("tecla:", "frase:", "sugerencia:", "accion:")):
                tiempo_obj = self.cfg["teclado"]["permanencia_s"]
            elif obj.id == ID_REANUDAR:
                tiempo_obj = REANUDAR_PERMANENCIA_S
            else:
                tiempo_obj = self.cfg["barra"]["permanencia_s"]
        st = self.perm.actualizar(pos, t, obj, libre, tiempo_obj)
        if st.disparo:
            if st.objetivo:
                self._elegir(st.objetivo, t, pos, acc)
            else:
                if self._p_cfg.get("sonido", True):
                    self._sonido("clic", acc)
                self._clic_actual(t, pos, acc, por_permanencia=True)
        return st

    def _paso_desplazar(self, t: float, dt: float, acc: list):
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
            self._t_ult_desp = t
        else:
            self._desp_acum = 0.0
        n = int(self._desp_acum)
        if n:
            self._desp_acum -= n
            acc.append(Rueda(n * K.WHEEL_DELTA))
        if self._t_ult_desp is not None and t - self._t_ult_desp >= DESPLAZAR_INACTIVO_S - 1e-9:
            self._terminar_desplazar(t, acc)

    def _entrar_desplazar(self, t: float, acc: list):
        self._salir_de_submodos_con_boton(acc)
        self.submodo = K.DESPLAZAR
        self.modo_clic = "desplazar"
        self._desp_ref = None
        self._desp_acum = 0.0
        self._t_ult_desp = t
        acc.append(Aviso("desplazar"))

    def _terminar_desplazar(self, t: float, acc: list):
        if self.submodo != K.DESPLAZAR:
            return
        self.submodo = K.NORMAL
        self._desp_ref = None
        self._desp_acum = 0.0
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
            if sub != K.ARRASTRANDO:
                obj = buscar_objetivo(pos, self.objetivos, self._obj_actual)
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
        acc.append(Elegir(ident))
        self._sonido("clic", acc)
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
            self._pausar(t, "botón Pausa", acc)
        elif ident == "barra:teclado":
            acc.append(Aviso("teclado"))

    # ------------------------------------------------------------ vista
    def _vista(self, t: float, g: ResultadoGestos, st: EstadoPermanencia, m) -> Vista:
        r = self._recentrar
        v = Vista(
            estado=self.estado, submodo=self.submodo, modo_clic=self.modo_clic,
            motivo_pausa=self.motivo_pausa, pausa_auto=self.pausa_auto,
            puntero=self.puntero.posicion if self.estado != K.PAUSA else None,
            puntero_virtual=self.puntero.posicion if self.estado == K.PAUSA and m is not None else None,
            permanencia=st, gestos=g,
            sin_cara_s=(t - self._t_sin_cara) if self._t_sin_cara is not None else 0.0,
            recentrando=(min((t - r["t0"]) / RECENTRAR_S, 1.0) if r is not None else None),
            calibrado=self.calibracion is not None, congelado=self.puntero.congelado,
            arrastre_s=(t - self._t_arrastre) if self._t_arrastre is not None else 0.0,
            medidas=m, objetivo=self._obj_actual.id if self._obj_actual is not None else None)
        self._ultima_vista = v
        return v

    @property
    def vista(self) -> Vista:
        return self._ultima_vista
