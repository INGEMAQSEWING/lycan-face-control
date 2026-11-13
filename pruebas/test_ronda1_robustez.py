"""Ronda 1 de arreglos: robustez (la cámara no muere por un error de OpenCV, avisos claros de
cámara, cambio de pantalla con el programa abierto). Sin cámara real."""
import threading
import time

import numpy as np

from conftest import CAL_SINTETICA, Sim, cfg_prueba
from lycan_face_control.acciones import Aviso
from lycan_face_control.captura import FUNCIONANDO, PERDIDA, Camara
from lycan_face_control.detector import DetectorFalso
from lycan_face_control.mapeo import MONITOR_REFERENCIA, Monitor
from lycan_face_control.motor import Motor
from lycan_face_control.salida.simulada import SalidaSimulada
from lycan_face_control.ui import textos


class _Reloj:
    def __init__(self):
        self.t = 50.0

    def __call__(self):
        return self.t


def _cfg():
    cfg = cfg_prueba()
    cfg["perfiles"]["Principal"]["calibracion"] = dict(CAL_SINTETICA)
    return cfg


# ------------------------------------------------------------------ hilo de la cámara
def test_un_error_de_opencv_no_mata_el_hilo_de_la_camara(monkeypatch):
    class ErrorCv(Exception):
        pass

    class CapFalla:
        def __init__(self):
            self.n = 0

        def read(self):
            self.n += 1
            if self.n > 3:
                raise ErrorCv("MSMF: el dispositivo se desconectó")
            return True, np.zeros((4, 4, 3), np.uint8)

        def release(self):
            pass

    cam = Camara(0)
    aperturas = []

    def abrir():
        aperturas.append(1)
        cam.cap = CapFalla()
        return True

    cam._abrir = abrir
    perdidas = []
    cam.al_perder = lambda: perdidas.append(1)
    monkeypatch.setattr(cam, "_parar", threading.Event())
    sin_atrapar = []
    anterior = threading.excepthook
    threading.excepthook = lambda a: sin_atrapar.append(a.exc_type)
    try:
        # reintento rápido para la prueba
        esperas = []
        real_wait = cam._parar.wait

        def wait(seg):
            esperas.append(seg)
            return real_wait(0.01)
        cam._parar.wait = wait
        cam.start()
        fin = time.time() + 3
        while len(aperturas) < 3 and time.time() < fin:
            time.sleep(0.01)
        assert cam.is_alive()
        assert len(aperturas) >= 3                 # se volvió a abrir solo
        assert perdidas                            # avisó que se perdió
        assert sin_atrapar == []
    finally:
        cam.detener()
        cam.join(2)
        threading.excepthook = anterior
    assert not cam.is_alive()


# ------------------------------------------------------------------ avisos de cámara
class _CamEstado:
    def __init__(self, reloj, estado):
        self.r = reloj
        self.estado = estado

    def is_alive(self):
        return True

    def ultimo(self, despues_de=0, espera=0.1):
        self.r.t += espera
        return None

    def detener(self):
        pass


def _avisos(m):
    out = []
    while not m.avisos.empty():
        a = m.avisos.get()
        if isinstance(a, Aviso):
            out.append(a.clave)
    return out


def test_camara_ocupada_avisa_con_palabras_claras_una_sola_vez():
    r = _Reloj()
    sal = SalidaSimulada(escritorio=(0, 0, 1366, 768), cursor=(683, 384), reloj=r)
    cam = _CamEstado(r, "OCUPADA")
    m = Motor(_cfg(), sal, camara=cam, detector=DetectorFalso(None), sistema=False,
              monitor=MONITOR_REFERENCIA, reloj=r)
    m.preparar()
    fin = r.t + 5
    while r.t < fin:
        m.vuelta()
    av = _avisos(m)
    assert av.count("camara_ocupada") == 1
    cam.estado = "NO_ABRE"
    m.vuelta()
    cam.estado = FUNCIONANDO
    m.vuelta()
    cam.estado = "OCUPADA"
    m.vuelta()
    assert _avisos(m).count("camara_ocupada") == 1
    for clave in ("no_camara", "camara_ocupada", "camara_perdida"):
        assert textos.TXT[f"aviso_{clave}"]


def test_subtitulo_dice_el_problema_de_la_camara_y_no_no_veo_su_cara():
    from lycan_face_control.estados import Vista
    from lycan_face_control.motor import VistaMotor
    from lycan_face_control import constantes as K
    v = VistaMotor(maquina=Vista(estado=K.PAUSA, pausa_auto=True), camara="OCUPADA")
    assert "Otro programa" in textos.subtitulo(v)
    v = VistaMotor(maquina=Vista(estado=K.PAUSA, pausa_auto=False, reanuda_parpadeo=True), camara=FUNCIONANDO)
    assert "dos veces" in textos.subtitulo(v)


def test_la_pausa_en_barrido_explica_como_seguir_con_parpadeos():
    from lycan_face_control import constantes as K
    s = Sim(cfg_prueba(**{"teclado.barrido": True}))
    s.quieto(0.5)
    s.orden("alternar_pausa")
    s.quieto(0.2)
    assert s.maquina.vista.reanuda_parpadeo
    assert s.maquina.estado == K.PAUSA


# ------------------------------------------------------------------ cambio de pantalla
def test_cambio_de_monitor_rehace_el_mapeo_sin_perder_la_calibracion():
    s = Sim(monitor=Monitor(0, 0, 1366, 768))
    s.quieto(0.5)
    acc = s.maquina.cambiar_monitor(s.t, Monitor(0, 0, 1920, 1080))
    assert s.maquina.mapeo.monitor.ancho == 1920
    assert s.maquina.calibracion is not None
    s.salida.escritorio = (0, 0, 1920, 1080)
    # mirar muy a la derecha y abajo: ahora llega más allá de la pantalla vieja
    s.quieto(1.5, yaw_n=0.2, pitch_n=0.8)
    x, y = s.maquina.puntero.posicion
    assert x > 1366 and y > 768
    assert acc


def test_el_motor_relee_el_monitor_si_cambia(monkeypatch):
    from lycan_face_control.sistema import pantallas
    r = _Reloj()
    sal = SalidaSimulada(escritorio=(0, 0, 1366, 768), cursor=(683, 384), reloj=r)
    m = Motor(_cfg(), sal, camara=_CamEstado(r, FUNCIONANDO), detector=DetectorFalso(None), sistema=False,
              monitor=Monitor(0, 0, 1366, 768), reloj=r)
    m.preparar()
    m._monitor_auto = True                 # como si lo hubiera elegido el motor (sistema=True)
    monkeypatch.setattr(pantallas, "elegir", lambda nombre="principal": Monitor(0, 0, 1920, 1080))
    for _ in range(30):
        m.vuelta()
    assert m.monitor.ancho == 1920
    assert m.maquina.mapeo.monitor.ancho == 1920
