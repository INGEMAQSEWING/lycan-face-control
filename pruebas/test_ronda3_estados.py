"""Ronda 3 de arreglos: mirar a otro lado no hace clics, la pausa no rebota con el botón que
cambia de id, hablar con las cejas arriba no hace clic derecho, la huella de la cara (otra
persona no maneja el puntero), el motor que no arranca no deja la cámara encendida, el ritmo de
cuadros procesados y los botones que quedaron abajo de una sesión anterior."""
import math

import pytest

from conftest import REPOSO, Sim, cfg_prueba, medidas, verificar_invariantes
from lycan_face_control import constantes as K
from lycan_face_control.acciones import Clic, Elegir
from lycan_face_control.permanencia import Objetivo
from lycan_face_control.salida.simulada import SalidaSimulada

Y0, P0 = REPOSO["yaw_n"], REPOSO["pitch_n"]


def _mover(s, y0, p0, y1, p1, dur, **kw):
    s.durante(dur, lambda t: medidas(yaw_n=y0 + (y1 - y0) * min(t / dur, 1.0),
                                     pitch_n=p0 + (p1 - p0) * min(t / dur, 1.0), **kw))


# ------------------------------------------------------------ mirar a otro lado
@pytest.mark.parametrize("dy,dp", ((0.30, -0.25), (0.35, 0.0), (-0.30, 0.0), (0.0, 0.30)))
def test_girar_30_grados_y_quedarse_no_hace_clics(dy, dp):
    s = Sim()
    s.quieto(1.0)
    _mover(s, Y0, P0, Y0 + dy, P0 + dp, 0.8)
    s.quieto(5.0, yaw_n=Y0 + dy, pitch_n=P0 + dp)
    assert s.clics() == []
    assert s.vista.mirando_afuera
    assert s.maquina.puntero.congelado
    verificar_invariantes(s.salida)


def test_al_volver_al_rango_comodo_el_clic_por_permanencia_sigue_funcionando():
    s = Sim()
    s.quieto(1.0)
    _mover(s, Y0, P0, Y0 + 0.35, P0, 0.8)
    s.quieto(3.0, yaw_n=Y0 + 0.35)
    assert s.clics() == []
    _mover(s, Y0 + 0.35, P0, Y0 + 0.04, P0, 0.8)
    assert not s.vista.mirando_afuera
    s.quieto(1.0, yaw_n=Y0 + 0.04)
    assert s.clics() == []                      # volver no es "moverse a propósito"
    _mover(s, Y0 + 0.04, P0, Y0 + 0.08, P0, 0.6)
    s.quieto(3.0, yaw_n=Y0 + 0.08)
    assert len(s.clics()) == 1
    verificar_invariantes(s.salida)


def test_mirando_a_otro_lado_los_gestos_de_clic_no_cuentan_pero_la_pausa_si():
    cfg = cfg_prueba(**{"gestos.cejas.corto": "pausar"})
    s = Sim(cfg)
    s.quieto(1.0)
    _mover(s, Y0, P0, Y0 + 0.35, P0, 0.8)
    s.quieto(1.0, yaw_n=Y0 + 0.35)
    s.limpiar()
    # boca abierta (clic de fábrica): nada
    s.quieto(0.8, yaw_n=Y0 + 0.35, mar=0.5)
    s.quieto(1.0, yaw_n=Y0 + 0.35)
    assert s.clics() == [] and s.maquina.estado == K.ACTIVO
    # cejas (aquí pausan): sí
    s.quieto(1.0, yaw_n=Y0 + 0.35, cejas=REPOSO["cejas"] * 1.25)
    assert s.maquina.estado == K.PAUSA


# ------------------------------------------------------------ pausa que no rebota
def _pausa_quieto(id_pausa, id_reanudar, sub, retraso):
    s = Sim()
    if sub:
        s.orden("poner_submodo", sub)
    s.quieto(1.0)
    x, y = map(int, s.maquina.puntero.posicion)
    rect = (x - 60, y - 50, x + 60, y + 50)
    s.maquina.poner_objetivos([Objetivo(id_pausa, rect)])
    s.limpiar()
    hist = []
    fin = s.t + 20
    while s.t < fin:
        res = s.paso(medidas())
        for a in res.acciones:
            if isinstance(a, Elegir) and a.objetivo == id_pausa:
                s.orden("pausar", "botón Pausar")       # como hace la interfaz
        hist.append(s.maquina.estado)
        # la interfaz publica el botón nuevo unos cuadros después del cambio de estado
        vista = hist[-1 - retraso] if len(hist) > retraso else hist[0]
        s.maquina.poner_objetivos([Objetivo(id_reanudar if vista == K.PAUSA else id_pausa, rect)])
    return s


@pytest.mark.parametrize("ids", (("accion:pausa", "teclado:reanudar", K.TECLADO), ("ui:pausar", "reanudar", None)))
@pytest.mark.parametrize("retraso", (0, 1, 3, 10))
def test_pausar_quieto_sobre_el_boton_no_se_reanuda_solo(ids, retraso):
    s = _pausa_quieto(*ids, retraso=retraso)
    assert s.avisos().count("pausa") == 1
    assert s.avisos().count("activo") == 0
    assert s.maquina.estado == K.PAUSA


def test_tras_reanudar_quieto_sobre_el_boton_no_se_vuelve_a_pausar():
    s = Sim()
    s.orden("poner_submodo", K.TECLADO)
    s.quieto(1.0)
    x, y = map(int, s.maquina.puntero.posicion)
    rect = (x - 60, y - 50, x + 60, y + 50)
    s.orden("pausar", "botón Pausar")
    s.maquina.poner_objetivos([Objetivo("teclado:reanudar", rect)])
    s.quieto(0.5)
    s.orden("reanudar", "botón Reanudar")        # el cuidador con el ratón
    s.quieto(0.1)
    s.maquina.poner_objetivos([Objetivo("accion:pausa", rect)])
    s.limpiar()
    s.quieto(6.0)
    assert s.maquina.estado == K.ACTIVO
    assert "accion:pausa" not in s.elegidos()
    # al salir del botón y volver, sí se puede pausar otra vez
    _mover(s, Y0, P0, Y0 + 0.06, P0, 0.6)
    s.quieto(1.0, yaw_n=Y0 + 0.06)
    _mover(s, Y0 + 0.06, P0, Y0, P0, 0.6)
    s.quieto(2.0)
    assert "accion:pausa" in s.elegidos()


# ------------------------------------------------------------ hablar con las cejas arriba
def _hablar(t):
    return 0.016 + 0.35 * max(0.0, math.sin(2 * math.pi * 4 * t))


def test_hablar_y_levantar_las_cejas_no_hace_clic_derecho():
    s = Sim()
    s.quieto(1.0)
    s.limpiar()
    s.durante(3.0, lambda t: medidas(mar=_hablar(t),
                                     cejas=REPOSO["cejas"] * (1.18 if 1.0 <= t < 1.8 else 1.0)))
    assert s.clics() == []


def test_hablar_y_sonreir_no_hace_clic():
    cfg = cfg_prueba(**{"gestos.sonrisa.activo": True, "gestos.sonrisa.corto": "clic_izq"})
    s = Sim(cfg)
    s.quieto(1.0)
    s.limpiar()
    # habla con pausas cortas en las que sonríe (la boca cerrada entre sílabas)
    s.durante(3.0, lambda t: medidas(mar=_hablar(t), sonrisa=REPOSO["sonrisa"] * 1.2))
    assert s.clics() == []


def test_cejas_con_la_boca_cerrada_siguen_dando_clic_derecho():
    s = Sim()
    s.quieto(1.0)
    s.limpiar()
    s.quieto(1.0, cejas=REPOSO["cejas"] * 1.18)
    s.quieto(1.0)
    assert [c.boton for c in s.clics()] == [K.DER]


def test_cejas_poco_despues_de_hablar_si_cuentan():
    s = Sim()
    s.quieto(1.0)
    s.durante(2.0, lambda t: medidas(mar=_hablar(t)))
    s.quieto(2.0)                               # deja de hablar
    s.limpiar()
    s.quieto(1.0, cejas=REPOSO["cejas"] * 1.18)
    s.quieto(0.5)
    assert [c.boton for c in s.clics()] == [K.DER]


# ------------------------------------------------------------ huella de la cara
def _usuario_y_luego(s, hueco):
    s.quieto(1.0)
    s.durante(0.5, lambda t: medidas(yaw_n=Y0 + 0.05 * t))
    s.quieto(1.5, yaw_n=Y0 + 0.025)
    if hueco:
        s.durante(hueco, lambda t: None)
    s.limpiar()


def _cuidador(y, p):
    return medidas(io_px=180.0, centro=(400.0, 200.0), yaw_n=y, pitch_n=p)


@pytest.mark.parametrize("hueco", (0.0, 3.0, 12.0))
def test_otra_cara_no_maneja_el_puntero_ni_hace_clics(hueco):
    s = Sim()
    _usuario_y_luego(s, hueco)
    s.durante(2.0, lambda t: _cuidador(Y0, P0))
    s.durante(0.6, lambda t: _cuidador(Y0 + 0.06 * t / 0.6, P0 - 0.03 * t / 0.6))
    s.durante(3.0, lambda t: _cuidador(Y0 + 0.06, P0 - 0.03))
    s.durante(0.8, lambda t: _cuidador(Y0, P0 + 0.04 * t / 0.8))
    s.durante(3.0, lambda t: _cuidador(Y0, P0 + 0.04))
    assert s.clics() == []
    assert s.maquina.estado == K.PAUSA
    assert s.maquina.motivo_pausa == "otra_cara"
    assert "otra_cara" in s.avisos()
    verificar_invariantes(s.salida)


def test_cuando_vuelve_la_persona_sigue_sola():
    s = Sim()
    _usuario_y_luego(s, 0.0)
    s.durante(3.0, lambda t: _cuidador(Y0, P0))
    assert s.maquina.estado == K.PAUSA
    s.durante(0.5, lambda t: None)              # el cuidador se va
    s.quieto(2.5)                               # vuelve la persona, igual que antes
    assert s.maquina.estado == K.ACTIVO
    s.limpiar()
    _mover(s, Y0, P0, Y0 + 0.05, P0, 0.6)
    s.quieto(2.5, yaw_n=Y0 + 0.05)
    assert len(s.clics()) == 1


def test_la_persona_a_otra_distancia_reanuda_con_el_boton_y_queda_como_su_cara():
    s = Sim()
    _usuario_y_luego(s, 12.0)                   # la acomodaron en la cama: vuelve más cerca
    s.durante(2.0, lambda t: medidas(io_px=170.0))
    assert s.maquina.estado == K.PAUSA and s.maquina.motivo_pausa == "otra_cara"
    s.orden("reanudar", "botón Reanudar")
    assert s.maquina.estado == K.ACTIVO
    s.durante(0.3, lambda t: None)              # un hueco corto: ya es su cara
    s.quieto(2.0, io_px=170.0)
    assert s.maquina.estado == K.ACTIVO


def test_un_cambio_lento_de_distancia_no_pausa():
    s = Sim(fps=20)
    s.quieto(1.0)
    # se acerca poco a poco (40 % en 20 s) y luego FaceMesh pierde la cara un instante
    s.durante(20.0, lambda t: medidas(io_px=REPOSO["io_px"] * (1 + 0.4 * t / 20.0)))
    s.durante(0.3, lambda t: None)
    s.quieto(2.0, io_px=REPOSO["io_px"] * 1.4)
    assert s.maquina.estado == K.ACTIVO


def test_la_pausa_automatica_no_la_quita_otra_cara_de_tamano_parecido_y_proporciones_distintas():
    s = Sim()
    s.quieto(2.0)
    s.durante(11.0, lambda t: None)
    assert s.maquina.estado == K.PAUSA and s.maquina.pausa_auto
    s.durante(3.0, lambda t: medidas(io_px=REPOSO["io_px"] * 1.1, cejas=REPOSO["cejas"] * 0.8,
                                     sonrisa=REPOSO["sonrisa"] * 0.8))
    assert s.maquina.estado == K.PAUSA
    assert s.maquina.motivo_pausa == "otra_cara"
    s.durante(0.5, lambda t: None)
    s.quieto(2.0)
    assert s.maquina.estado == K.ACTIVO


def test_textos_de_la_pausa_por_otra_cara():
    from lycan_face_control.ui import textos
    s = Sim()
    _usuario_y_luego(s, 0.0)
    s.durante(3.0, lambda t: _cuidador(Y0, P0))
    assert "Reanudar" in textos.subtitulo(s.vista)
    assert textos.texto_aviso(type("A", (), {"clave": "otra_cara"})())


# ------------------------------------------------------------ motor
class _CamEspia:
    estado = "FUNCIONANDO"
    fps_reales = 30

    def __init__(self):
        self.vivo = False
        self.detenida = False

    def is_alive(self):
        return self.vivo

    def start(self):
        self.vivo = True

    def detener(self):
        self.detenida = True
        self.vivo = False

    def join(self, timeout=None):
        return None

    def ultimo(self, *a, **k):
        return None


def test_motor_que_no_carga_la_deteccion_no_deja_la_camara_encendida(monkeypatch):
    from lycan_face_control import detector as det
    from lycan_face_control.mapeo import MONITOR_REFERENCIA
    from lycan_face_control.motor import Motor

    class DetectorQueFalla:
        def __init__(self, *a, **k):
            raise MemoryError("sin memoria")

    monkeypatch.setattr(det, "Detector", DetectorQueFalla)
    camaras = []
    for _ in range(4):                           # como los reintentos del vigilante
        cam = _CamEspia()
        camaras.append(cam)
        salida = SalidaSimulada()
        m = Motor(cfg_prueba(), salida, camara=cam, sistema=False, monitor=MONITOR_REFERENCIA)
        m.start()
        m.join(5)
        assert not m.is_alive()
        assert m.error_inicio and "MemoryError" in m.error_inicio
        assert salida.todo_suelto()
    assert not any(c.vivo for c in camaras)


def test_reemplazar_un_motor_trabado_apaga_su_camara():
    from lycan_face_control.ui.aplicacion import App

    class Trabado:
        def __init__(self):
            self.camara = _CamEspia()
            self.camara.start()

        def detener(self):
            pass

        def join(self, timeout=None):
            pass

        def is_alive(self):
            return True

    app = App.__new__(App)
    app._motor_viejo = None
    m = Trabado()
    app.motor = m
    App._reemplazar_motor(app, 0.0)
    assert m.camara.detenida and app._motor_viejo is not None


class _CamRitmo:
    estado = "FUNCIONANDO"

    def __init__(self, fps, reloj):
        import numpy as np
        self.fps, self.n, self.r = fps, 0, reloj
        self.img = np.zeros((48, 64, 3), np.uint8)

    def is_alive(self):
        return True

    def ultimo(self, despues_de=0, espera=0.1):
        from lycan_face_control.captura import Cuadro
        self.r[0] += 1.0 / self.fps
        self.n += 1
        return Cuadro(self.img, self.r[0], self.n)


@pytest.mark.parametrize("fps_cam,esperado", ((30, 19), (25, 19), (20, 19), (60, 19), (15, 14.5)))
def test_el_limitador_procesa_los_cuadros_pedidos(fps_cam, esperado):
    from lycan_face_control.detector import DetectorFalso
    from lycan_face_control.mapeo import MONITOR_REFERENCIA
    from lycan_face_control.motor import Motor
    reloj = [100.0]
    det = DetectorFalso(lambda t: None)
    m = Motor(cfg_prueba(), SalidaSimulada(reloj=lambda: reloj[0]), camara=_CamRitmo(fps_cam, reloj),
              detector=det, sistema=False, monitor=MONITOR_REFERENCIA, reloj=lambda: reloj[0])
    m.preparar()
    for _ in range(fps_cam * 10):
        m.vuelta()
    por_s = det.llamadas / 10.0
    assert esperado <= por_s <= 20.5


# ------------------------------------------------------------ botones de una sesión anterior
def test_al_arrancar_se_suelta_un_boton_que_quedo_abajo():
    s = SalidaSimulada()
    s.presionados_windows = ["izq"]
    assert s.soltar_botones_huerfanos("arranque") == ["izq"]
    assert ("boton", "izq", False) in [e for _, e in s.eventos]
    s2 = SalidaSimulada()
    assert s2.soltar_botones_huerfanos() == []
    assert s2.eventos == []


def test_la_aplicacion_revisa_los_botones_al_arrancar():
    from lycan_face_control.ui import aplicacion as A
    import inspect
    fuente = inspect.getsource(A.App.__init__)
    assert "soltar_botones_huerfanos" in fuente
