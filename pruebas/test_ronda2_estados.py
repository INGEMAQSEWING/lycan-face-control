"""Ronda 2 de arreglos: otra cara tras un hueco, gestos al terminar la calibración, tos y bostezo,
recentrar sin clics, y la pausa del barrido."""
import copy
import math

import pytest

from conftest import CAL_SINTETICA, REPOSO, Sim, cfg_prueba, medidas, verificar_invariantes
from lycan_face_control import constantes as K
from lycan_face_control.acciones import Clic
from lycan_face_control.cara import Medidas
from lycan_face_control.estados import Maquina
from lycan_face_control.mapeo import MONITOR_REFERENCIA
from lycan_face_control.salida.simulada import SalidaSimulada
from sintetico.cara_sintetica import cara

Y0, P0 = REPOSO["yaw_n"], REPOSO["pitch_n"]


def otra_cara(**kw):
    d = dict(REPOSO)
    d.update(io_px=70.0, yaw_n=-0.05, pitch_n=0.6)
    d.update(kw)
    return Medidas(**d, centro=(500.0, 300.0))


def _arrastrando():
    s = Sim(fps=20)
    s.quieto(1.0)
    s.orden("elegir", "barra:arrastrar")
    s.durante(0.6, lambda t: medidas(yaw_n=Y0 + 0.08 * t / 0.6))
    s.quieto(1.5, yaw_n=Y0 + 0.08)
    assert s.maquina.submodo == K.ARRASTRANDO
    assert "izq" in s.salida.botones_abajo
    s.limpiar()
    return s


# ------------------------------------------------------------ otra cara tras un hueco
@pytest.mark.parametrize("hueco", (0, 1, 2, 4, 10))
def test_otra_cara_tras_un_hueco_suelta_el_arrastre(hueco):
    s = _arrastrando()
    for _ in range(hueco):
        s.paso(None)
    for _ in range(10):
        s.paso(otra_cara())
    assert s.maquina.submodo != K.ARRASTRANDO
    assert s.salida.botones_abajo == []
    assert "cara_distinta" in s.avisos()
    verificar_invariantes(s.salida)


@pytest.mark.parametrize("hueco", (0, 1, 3))
def test_gestos_de_otra_cara_tras_un_hueco_no_hacen_clic(hueco):
    s = Sim(fps=20)
    s.quieto(1.5)
    for _ in range(hueco):
        s.paso(None)
    for _ in range(9):                     # 0,45 s subiendo las cejas al hablar
        s.paso(otra_cara(cejas=0.356 * 1.3))
    for _ in range(10):
        s.paso(otra_cara())
    assert s.clics() == []


def test_la_misma_cara_tras_un_hueco_no_es_otra():
    s = Sim(fps=20)
    s.quieto(1.0)
    for _ in range(3):
        s.paso(None)
    s.quieto(0.5)
    assert "cara_distinta" not in s.avisos()


def test_otra_cara_quieta_no_hace_clic_por_permanencia():
    s = Sim(fps=20)
    s.quieto(0.5)
    s.durante(0.6, lambda t: medidas(yaw_n=Y0 + 0.05 * t / 0.6))     # se mueve: queda armada
    s.limpiar()
    s.durante(4.0, lambda _t: otra_cara(io_px=80.0, yaw_n=Y0 - 0.04, pitch_n=P0 + 0.03))
    assert "cara_distinta" in s.avisos()
    assert s.clics() == []


def test_pausa_automatica_no_la_quita_la_cara_del_cuidador():
    s = Sim(fps=20)
    s.quieto(1.0)
    s.durante(11.0, lambda _t: None)
    assert s.maquina.estado == K.PAUSA and s.maquina.pausa_auto
    s.durante(3.0, lambda _t: otra_cara())                 # el cuidador se asoma
    assert s.maquina.estado == K.PAUSA
    s.durante(0.5, lambda _t: None)
    s.quieto(2.5)                                          # vuelve la persona
    assert s.maquina.estado == K.ACTIVO


# ------------------------------------------------------------ gesto sostenido al rehacer la máquina
def test_cejas_sostenidas_al_terminar_la_calibracion_no_hacen_clic():
    s = Sim(fps=20)
    s.quieto(1.0)
    s.orden("iniciar_calibracion")
    s.quieto(1.0)
    s.quieto(1.5, cejas=0.356 * 1.25)
    s.limpiar()
    cal = copy.deepcopy(CAL_SINTETICA)
    cal["umbrales"] = {"cejas": 1.125}
    s.aplicar(s.maquina.terminar_calibracion(s.t, cal, cfg_prueba()))
    s.aplicar(s.maquina.reanudar(s.t, "calibración"))
    s.quieto(0.8, cejas=0.356 * 1.25)
    s.quieto(0.5)
    assert s.clics() == []
    # después de volver a reposo, el gesto sí funciona
    s.quieto(1.0)
    s.quieto(0.8, cejas=0.356 * 1.3)
    s.quieto(0.3)
    assert s.clics() == [Clic("der")]


def test_boca_sostenida_al_guardar_opciones_no_hace_clic():
    cfg = cfg_prueba(**{"gestos.cejas.activo": False})
    s = Sim(cfg, fps=20)
    s.quieto(1.0)
    s.quieto(0.3, mar=0.6)
    s.aplicar(s.maquina.nueva_config(s.t, cfg_prueba(**{"gestos.cejas.activo": False})))
    s.quieto(0.8, mar=0.6)
    s.quieto(0.5)
    assert s.clics() == []


# ------------------------------------------------------------ tos, risa, bostezo, sorpresa
def _con_cara(fuente, T, cfg=None):
    s = Sim(cfg, fps=20)
    for _ in range(20):
        s.cara(cara())
    s.limpiar()
    for k in range(int(T * 20)):
        s.cara(cara(**fuente(k / 20)))
    for _ in range(30):
        s.cara(cara())
    return s


def _tos(dur):
    def f(t):
        pitch = 12 * math.sin(math.pi * min(t / 0.3, 1)) if t < 0.3 else 0
        return dict(boca=0.6 if t < dur else 0.0, pitch=pitch, ojos=0.6)
    return f


@pytest.mark.parametrize("dur", (0.7, 0.9, 1.2))
def test_toser_con_sacudida_no_hace_clic(dur):
    assert _con_cara(_tos(dur), 1.5).clics() == []


def test_sacudida_sola_con_la_boca_abierta_anula_el_gesto():
    def f(t):
        pitch = 12 * math.sin(math.pi * min(t / 0.3, 1)) if t < 0.3 else 0
        return dict(boca=0.6 if t < 0.9 else 0.0, pitch=pitch)      # ojos normales
    assert _con_cara(f, 1.5).clics() == []


def test_reir_y_bostezar_con_ojos_entrecerrados_no_hace_clic():
    s = _con_cara(lambda t: dict(boca=0.5 if t < 1.0 else 0, sonrisa=0.6, ojos=0.6), 1.5)
    assert s.clics() == []
    s = _con_cara(lambda t: dict(boca=0.8 if t < 1.6 else 0, ojos=0.6), 2.0)
    assert s.clics() == []
    s = _con_cara(lambda t: dict(boca=0.8 if t < 3 else 0, ojos=0.6), 3.5)
    assert s.clics() == [] and s.maquina.estado == K.ACTIVO


def test_sorpresa_con_las_cejas_no_hace_clic_derecho():
    assert _con_cara(lambda t: dict(cejas=0.9 if t < 0.4 else 0), 1.0).clics() == []


def test_abrir_la_boca_a_proposito_sigue_haciendo_clic():
    s = _con_cara(lambda t: dict(boca=0.6 if t < 0.9 else 0), 1.5)
    assert s.clics() == [Clic("izq")]


def test_llegar_moviendo_la_cabeza_y_abrir_la_boca_si_hace_clic():
    """El movimiento para llegar al botón, justo antes del gesto, no lo anula."""
    def f(t):
        if t < 0.4:
            return dict(yaw=8 * t / 0.4)
        return dict(yaw=8, boca=0.6 if t < 1.3 else 0)
    s = _con_cara(f, 1.8)
    assert s.clics() == [Clic("izq")]


# ------------------------------------------------------------ recentrar y deslizamientos
def test_primer_arranque_sin_calibrar_con_el_cursor_lejos_no_hace_clic():
    cfg = cfg_prueba(**{"arranque.estado": "activo"})
    t = [100.0]
    sal = SalidaSimulada(escritorio=(0, 0, 1366, 768), cursor=(100, 100), reloj=lambda: t[0])
    m = Maquina(cfg, MONITOR_REFERENCIA, None, pos_cursor=sal.posicion_cursor, t0=100.0,
                usar_calibracion_config=False)
    clics = []
    for _ in range(160):
        r = m.procesar(t[0], medidas(yaw_n=Y0 + 0.01, pitch_n=P0 + 0.01))
        sal.aplicar(r.acciones)
        clics += [a for a in r.acciones if isinstance(a, Clic)]
        t[0] += 0.05
    assert m.estado == K.ACTIVO and clics == []


def test_recentrar_y_quedarse_quieto_no_hace_clic():
    s = Sim(fps=20)
    s.quieto(1.0)
    s.quieto(1.0, yaw_n=Y0 + 0.05, pitch_n=P0 + 0.04)    # otra postura (puntero lejos del centro)
    s.limpiar()
    s.orden("recentrar")
    s.quieto(5.0, yaw_n=Y0 + 0.05, pitch_n=P0 + 0.04)
    assert "recentrado" in s.avisos()
    assert s.clics() == []


def test_cambiar_la_velocidad_con_la_cabeza_quieta_no_hace_clic():
    s = Sim(fps=20)
    s.quieto(0.5)
    s.durante(0.6, lambda t: medidas(yaw_n=Y0 + 0.04 * t / 0.6, pitch_n=P0 + 0.02 * t / 0.6))
    s.quieto(2.0, yaw_n=Y0 + 0.04, pitch_n=P0 + 0.02)
    assert len(s.clics()) == 1
    s.limpiar()
    antes = s.maquina.puntero.posicion
    s.aplicar(s.maquina.nueva_config(s.t, cfg_prueba(**{"puntero.sens_x": 2.0})))
    s.quieto(4.0, yaw_n=Y0 + 0.04, pitch_n=P0 + 0.02)
    assert s.maquina.puntero.posicion != antes
    assert s.clics() == []


def test_reanudar_con_el_puntero_lejos_no_hace_clic():
    s = Sim(fps=20)
    s.quieto(1.0)
    s.orden("pausar", "atajo")
    s.salida.cursor = (100, 100)             # el cuidador movió el ratón durante la pausa
    s.quieto(0.5)
    s.limpiar()
    s.orden("reanudar", "atajo")
    s.quieto(4.0)
    assert s.clics() == []


# ------------------------------------------------------------ pausa por barrido
def test_tras_pausar_con_parpadeo_hacen_falta_dos_parpadeos_largos():
    s = Sim(cfg_prueba(**{"teclado.solo_comunicacion": True}), fps=20)
    s.quieto(1.0)
    s.quieto(1.3, ear_der=0.05, ear_izq=0.05)        # parpadeo largo (eligió «Pausa»)
    s.quieto(0.3)
    s.orden("pausar", "botón Pausa")
    assert s.maquina.estado == K.PAUSA
    s.quieto(0.4)
    s.quieto(1.3, ear_der=0.05, ear_izq=0.05)        # un solo parpadeo largo
    s.quieto(0.5)
    assert s.maquina.estado == K.PAUSA
    s.quieto(1.3, ear_der=0.05, ear_izq=0.05)        # el segundo
    s.quieto(0.5)
    assert s.maquina.estado == K.ACTIVO
