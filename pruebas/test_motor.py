"""Motor completo sin cámara ni mediapipe: CamaraFalsa + DetectorFalso (caras sintéticas) +
SalidaSimulada (sección 13.2, "Motor")."""
import threading
import time


from conftest import CAL_SINTETICA, cfg_prueba, verificar_invariantes
from lycan_face_control import constantes as K
from lycan_face_control.acciones import Aviso
from lycan_face_control.captura import DETENIDA, CamaraFalsa
from lycan_face_control.detector import DetectorFalso
from lycan_face_control.mapeo import MONITOR_REFERENCIA
from lycan_face_control.motor import Motor, OrdenEscribir, VistaMotor
from lycan_face_control.salida.simulada import SalidaSimulada
from sintetico import FuenteSecuencia


class Reloj:
    """Reloj de prueba: la cámara lo avanza un cuadro en cada lectura."""

    def __init__(self, t0=50.0, fps=30.0):
        self.t = t0
        self.dt = 1.0 / fps

    def cuadro(self):
        self.t += self.dt
        return self.t

    def __call__(self):
        return self.t


def cfg_calibrada(**cambios):
    cfg = cfg_prueba(**cambios)
    cfg["perfiles"]["Principal"]["calibracion"] = dict(CAL_SINTETICA)
    return cfg


def armar(params, cfg=None, reloj=None):
    """Motor sin hilo. ``params(t_relativo) -> dict de cara() | None``."""
    reloj = reloj or Reloj()
    t0 = reloj.t
    fuente = FuenteSecuencia(funcion=lambda t: params(t - t0))
    salida = SalidaSimulada(escritorio=(0, 0, 1366, 768), cursor=(683, 384), reloj=reloj)
    salida.intervalo_doble_ms = 0
    camara = CamaraFalsa(ancho=640, alto=480, reloj=reloj.cuadro, tiempo_real=False)
    motor = Motor(cfg or cfg_calibrada(), salida, camara=camara, detector=DetectorFalso(fuente), sistema=False,
                  monitor=MONITOR_REFERENCIA, reloj=reloj)
    motor.preparar()
    return motor, salida, reloj


def correr(motor, reloj, segundos):
    fin = reloj.t + segundos
    while reloj.t < fin:
        motor.vuelta()


def avisos(motor):
    out = []
    while not motor.avisos.empty():
        out.append(motor.avisos.get_nowait())
    return out


def mover_y_quedarse(t):
    """De frente 0,5 s, gira 4° en 0,5 s y se queda quieto."""
    if t < 0.5:
        return {}
    return {"yaw": 4.0 * min((t - 0.5) / 0.5, 1.0)}


def test_tres_segundos_mueven_el_puntero_y_hacen_un_clic_por_permanencia():
    motor, salida, reloj = armar(mover_y_quedarse)
    assert motor.maquina.estado == K.ACTIVO
    correr(motor, reloj, 3.5)
    assert salida.solo("mover"), "el puntero no se movió"
    assert salida.cursor[0] > 683 + 100
    assert motor.maquina.estado == K.ACTIVO
    clics = [ev for ev in salida.botones()]
    assert clics == [("izq", True), ("izq", False)]
    # procesa como máximo fps_proceso (20) cuadros por segundo con una cámara de 30
    assert 12 <= motor.stats.fps <= 20.5
    motor.cerrar()
    verificar_invariantes(salida)
    assert motor.camara.estado == DETENIDA


def test_detenerse_suelta_todo_aunque_este_arrastrando():
    motor, salida, reloj = armar(mover_y_quedarse)
    motor.orden("elegir", "barra:arrastrar")
    correr(motor, reloj, 2.5)
    assert salida.botones_abajo == ["izq"]
    motor.cerrar()
    assert salida.botones_abajo == []
    verificar_invariantes(salida)


def test_perder_la_cara_en_el_motor_suelta_a_los_300_ms():
    def params(t):
        if t >= 2.5:
            return None
        return mover_y_quedarse(t)
    motor, salida, reloj = armar(params)
    motor.orden("elegir", "barra:arrastrar")
    correr(motor, reloj, 2.5)
    assert salida.botones_abajo == ["izq"]
    correr(motor, reloj, 0.2)
    assert salida.botones_abajo == ["izq"]
    correr(motor, reloj, 0.2)
    assert salida.botones_abajo == []
    assert motor.maquina.estado == K.SIN_CARA
    assert any(isinstance(a, Aviso) and a.clave == "sin_cara" for a in avisos(motor))


def test_ordenes_pausa_escribir_y_vista():
    motor, salida, reloj = armar(lambda t: {})
    correr(motor, reloj, 0.3)
    motor.orden("alternar_pausa")
    correr(motor, reloj, 0.2)
    assert motor.maquina.estado == K.PAUSA
    motor.escribir("¿Ñandú? 👍")
    motor.ordenes.put(OrdenEscribir(""))
    correr(motor, reloj, 0.1)
    assert salida.texto() == "¿Ñandú? 👍"
    v = motor.vistas.get_nowait()
    assert isinstance(v, VistaMotor)
    assert v.maquina.estado == K.PAUSA and v.puntos is not None and v.simulada
    assert motor.vistas.empty()                    # cola de 1: nunca se acumulan
    motor.orden("alternar_pausa")
    correr(motor, reloj, 0.2)
    assert motor.maquina.estado == K.ACTIVO
    motor.cerrar()
    verificar_invariantes(salida)


def test_calibrando_entrega_medidas_y_no_envia_nada():
    motor, salida, reloj = armar(mover_y_quedarse)
    motor.orden("calibrar", True)
    correr(motor, reloj, 3.0)
    assert motor.maquina.estado == K.CALIBRANDO
    assert salida.solo("mover") == [] and salida.botones() == []
    n = motor.cola_calibracion.qsize()
    assert n >= 30
    t, m, io_fr, centro = motor.cola_calibracion.get_nowait()
    assert m is not None and 0.09 < io_fr < 0.3
    motor.orden("calibrar", False, dict(CAL_SINTETICA))
    correr(motor, reloj, 0.2)
    assert motor.maquina.estado == K.ACTIVO


def test_error_del_detector_suelta_y_pausa_y_tres_son_fatales():
    class DetectorRoto:
        def __init__(self):
            self.n = 0

        def procesar(self, img, t=None):
            self.n += 1
            raise RuntimeError("falló el detector")

        def cerrar(self):
            pass

    reloj = Reloj()
    salida = SalidaSimulada(escritorio=(0, 0, 1366, 768), reloj=reloj)
    motor = Motor(cfg_calibrada(), salida, camara=CamaraFalsa(reloj=reloj.cuadro, tiempo_real=False),
                  detector=DetectorRoto(), sistema=False, monitor=MONITOR_REFERENCIA, reloj=reloj)
    motor.preparar()
    motor.vuelta()
    assert motor.maquina.estado == K.PAUSA
    assert salida.contador_soltar >= 1
    for _ in range(6):
        motor.vuelta()
    assert motor.fatal and motor._parar.is_set()
    assert any(isinstance(a, Aviso) and a.clave == "fatal" for a in avisos(motor))


def test_envio_bloqueado_pausa_y_reanuda_cuando_windows_acepta():
    motor, salida, reloj = armar(mover_y_quedarse)
    correr(motor, reloj, 0.5)
    salida.fallar = True
    correr(motor, reloj, 0.5)
    assert motor.maquina.estado == K.PAUSA and motor.maquina.motivo_pausa == "envio"
    salida.fallar = False
    correr(motor, reloj, 2.5)
    assert motor.maquina.estado == K.ACTIVO


def test_objetivos_desde_otro_hilo():
    from lycan_face_control.permanencia import Objetivo
    motor, salida, reloj = armar(mover_y_quedarse)
    hilo = threading.Thread(target=motor.poner_objetivos,
                            args=([Objetivo("barra:doble", (700, 300, 1366, 500))],))
    hilo.start()
    hilo.join()
    correr(motor, reloj, 3.0)
    assert motor.maquina.modo_clic == "doble"         # se eligió el botón, sin clic de Windows
    assert salida.botones() == []


def test_hilo_real_arranca_y_se_detiene_sin_dejar_nada():
    """El hilo de verdad, con tiempo real, ~0,8 s (cámara falsa, nunca la real)."""
    t0 = time.perf_counter()
    fuente = FuenteSecuencia(funcion=lambda t: mover_y_quedarse(t - t0))
    salida = SalidaSimulada(escritorio=(0, 0, 1366, 768), cursor=(683, 384))
    camara = CamaraFalsa(fps=30)
    motor = Motor(cfg_calibrada(), salida, camara=camara, detector=DetectorFalso(fuente), sistema=False,
                  monitor=MONITOR_REFERENCIA)
    motor.start()
    assert motor.listo.wait(5)
    time.sleep(0.8)
    motor.detener()
    motor.join(3)
    assert not motor.is_alive()
    assert motor.stats.total >= 5
    assert camara.estado == DETENIDA
    assert salida.todo_suelto()
    assert salida.contador_soltar >= 1                # soltar todo al terminar


def test_atajo_de_pausa_suelta_al_instante_aunque_el_motor_no_corra():
    motor, salida, reloj = armar(mover_y_quedarse)
    motor.orden("elegir", "barra:arrastrar")
    correr(motor, reloj, 2.5)
    assert salida.botones_abajo == ["izq"]
    motor.atajo("pausar")                     # sin otra vuelta del motor: ya soltó
    assert salida.botones_abajo == []
    correr(motor, reloj, 0.1)
    assert motor.maquina.estado == K.PAUSA
    verificar_invariantes(salida)
