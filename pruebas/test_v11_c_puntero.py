"""Versión 1.1, paquete C: el puntero con los ojos en la máquina de estados (caras sintéticas, sin
cámara): fuente «ojos», «ojos y cabeza», imán, lupa, parpadeo, mirar afuera, recentrar y AYUDA."""
import math

import numpy as np
import pytest

from conftest import Sim, cfg_prueba, medidas, verificar_invariantes
from lycan_face_control import constantes as K
from lycan_face_control import lupa as L
from lycan_face_control.acciones import Aviso, Bajar, Clic, Elegir, Mover
from lycan_face_control.estados import RADIO_MAX_OJOS
from lycan_face_control.permanencia import Objetivo, Permanencia
from ojos_sinteticos import MON, cal_con_mirada, con_ruido, medidas_mirando


def sim_ojos(fuente="ojos", **cambios):
    cfg = cfg_prueba(**{"puntero.fuente": fuente, **cambios})
    s = Sim(cfg, calibracion=cal_con_mirada())
    assert s.maquina.puntero.fuente == fuente
    return s


def mirar(s, x, y, dur, ruido=0.0, rng=None, cabeza=(0.0, 0.0), **kw):
    m = medidas_mirando(x, y, *cabeza, **kw)
    s.durante(dur, lambda _t: con_ruido(m, ruido, rng) if ruido else m)


def movers(s, desde=None):
    return [(t, a) for t, a in s.acciones if isinstance(a, Mover) and (desde is None or t >= desde)]


# =========================================================================== fuente «cabeza»
def test_con_la_cabeza_el_iris_no_cambia_nada():
    a, b = Sim(), Sim()
    for k in range(120):
        y = 0.022 + 0.05 * math.sin(k / 15)
        a.paso(medidas(yaw_n=y))
        b.paso(medidas(yaw_n=y, iris_x=0.1 * math.cos(k), iris_y=0.05))
    assert [x for _, x in a.acciones] == [x for _, x in b.acciones]
    assert a.maquina.perm.radio == b.maquina.perm.radio


# =========================================================================== fuente «ojos»
def test_ojos_el_puntero_va_a_donde_mira():
    s = sim_ojos()
    mirar(s, 1100, 200, 1.0)
    x, y = s.maquina.puntero.posicion
    assert abs(x - 1100) < 25 and abs(y - 200) < 25
    mirar(s, 250, 600, 1.0)
    x, y = s.maquina.puntero.posicion
    assert abs(x - 250) < 25 and abs(y - 600) < 25


def test_ojos_una_sacada_de_600_px_llega_en_menos_de_150_ms():
    s = sim_ojos()
    mirar(s, 300, 384, 1.0)
    s.limpiar()
    t0 = s.t
    mirar(s, 900, 384, 0.5)
    llegada = next(t for t, a in movers(s) if abs(a.x - 900) < 40)
    assert llegada - t0 < 0.15


@pytest.mark.parametrize("semilla", [1, 2])
def test_ojos_cinco_minutos_mirando_fijo_con_ruido_no_hace_clics(semilla):
    rng = np.random.default_rng(semilla)
    s = sim_ojos(**{"ojos.lupa": False})
    mirar(s, 900, 300, 300.0, ruido=0.004, rng=rng)
    assert s.clics() == [] and not any(e.startswith("lupa:abrir") for e in s.elegidos())
    verificar_invariantes(s.salida)


def test_ojos_quedarse_mirando_despues_de_moverse_si_hace_clic_sin_lupa():
    s = sim_ojos(**{"ojos.lupa": False})
    mirar(s, 300, 300, 0.6)
    mirar(s, 900, 500, 3.0)
    assert len(s.clics()) == 1


def test_ojos_el_parpadeo_con_el_iris_bajando_no_mueve_el_puntero():
    s = sim_ojos()
    mirar(s, 700, 300, 1.0)
    antes = s.maquina.puntero.posicion
    s.limpiar()
    # parpadeo de 200 ms: los ojos se cierran y FaceMesh baja el iris
    for o in (0.6, 0.3, 0.1, 0.1, 0.3, 0.6):
        s.paso(medidas_mirando(700, 300, ojos=o, iris_baja=0.4))
    mirar(s, 700, 300, 0.6)
    assert all(math.hypot(a.x - antes[0], a.y - antes[1]) < 12 for _, a in movers(s))
    assert s.clics() == []


def test_ojos_sin_iris_el_puntero_queda_quieto_y_no_cae_a_la_cabeza():
    s = sim_ojos()
    mirar(s, 400, 250, 1.0)
    antes = s.maquina.puntero.posicion
    s.limpiar()
    # cara de 468 puntos (sin iris) mientras la cabeza gira mucho
    s.durante(1.5, lambda t: medidas(yaw_n=0.022 + 0.06 * t))
    assert s.maquina.puntero.posicion == antes and movers(s) == []


def test_ojos_el_radio_de_la_permanencia_nunca_pasa_de_120_px():
    cal = cal_con_mirada(temblor_iris=0.05)               # mucho temblor del iris
    s = Sim(cfg_prueba(**{"puntero.fuente": "ojos"}), calibracion=cal)
    assert s.maquina.puntero.temblor_px * 4 > RADIO_MAX_OJOS
    assert s.maquina.perm.radio <= RADIO_MAX_OJOS + 1e-9
    s.maquina.puntero.temblor_cambio = True
    s.maquina._revisar_temblor()
    assert s.maquina.perm.radio <= RADIO_MAX_OJOS + 1e-9
    # un radio configurado mayor que el tope se respeta (el tope es para el temblor)
    p = Permanencia(radio_px=80, alto_pantalla=2160)
    p.ajustar_radio_minimo(500, tope=120)
    assert p.radio == pytest.approx(160)


def test_ojos_usa_su_propio_tiempo_de_permanencia():
    s = sim_ojos(**{"ojos.permanencia_s": 2.0})
    assert s.maquina.perm.tiempo_s == pytest.approx(2.0)


# =========================================================================== «ojos y cabeza»
def test_mixto_la_cabeza_mueve_con_la_ganancia_fina():
    def recorrido(fina):
        s = sim_ojos("cabeza_y_ojos", **{"ojos.ganancia_fina": fina})
        m = medidas_mirando(683, 384)
        s.durante(1.0, lambda t: m)
        x0 = s.maquina.puntero.posicion[0]
        # la cabeza gira un poco con la mirada al mismo punto (los ojos lo compensan)
        from dataclasses import replace
        s.durante(1.0, lambda t: replace(m, yaw_n=m.yaw_n + 0.02 * min(t / 0.5, 1)))
        return s.maquina.puntero.posicion[0] - x0
    a, b = recorrido(0.4), recorrido(0.8)
    assert 10 < a < b
    assert b == pytest.approx(2 * a, rel=0.35)


def test_mixto_el_ruido_de_la_mirada_cerca_del_puntero_no_lo_hace_saltar():
    rng = np.random.default_rng(5)
    s = sim_ojos("cabeza_y_ojos")
    mirar(s, 683, 384, 1.0)
    s.limpiar()
    for k in range(20):                         # pequeñas fijaciones a menos de salto_px
        mirar(s, 683 + 60 * math.sin(k), 384 + 40 * math.cos(k), 0.5, ruido=0.004, rng=rng)
    x, y = s.maquina.puntero.posicion
    assert math.hypot(x - 683, y - 384) < 30
    assert s.clics() == []


def test_mixto_una_fijacion_lejana_hace_saltar_el_puntero_sin_clic():
    s = sim_ojos("cabeza_y_ojos")
    mirar(s, 300, 300, 1.0)
    pos0 = s.maquina.puntero.posicion
    s.limpiar()
    t0 = s.t
    mirar(s, 1000, 550, 0.2)                    # antes de los 250 ms de fijación: no salta
    assert s.maquina.puntero.posicion == pos0
    mirar(s, 1000, 550, 0.4)
    x, y = s.maquina.puntero.posicion
    assert math.hypot(x - 1000, y - 550) < 25
    assert s.clics() == []
    llegada = next(t for t, a in movers(s) if math.hypot(a.x - 1000, a.y - 550) < 25)
    assert llegada - t0 < 0.25 + 0.15 + 0.15
    # quedarse quieto justo después del salto tampoco hace clic (el salto desarma la permanencia)
    mirar(s, 1000, 550, 3.0)
    assert s.clics() == []


# =========================================================================== imán
def test_iman_cerca_de_un_boton_el_puntero_se_pega_a_su_centro_y_se_suelta_con_histeresis():
    s = sim_ojos()
    boton = Objetivo("barra:clic", (1000, 300, 1100, 400))
    s.maquina.poner_objetivos([boton])
    mirar(s, 960, 350, 1.0)                     # 40 px a la izquierda del botón (imán de 80 px)
    assert s.vista.iman == "barra:clic" and s.vista.puntero == (1050, 350)
    assert any(a.x == 1050 and a.y == 350 for _, a in movers(s))
    mirar(s, 915, 350, 0.6)                     # 85 px: todavía pegado (se suelta a 96 px)
    assert s.vista.iman == "barra:clic"
    mirar(s, 880, 350, 0.6)                     # 120 px: se suelta
    assert s.vista.iman is None and abs(s.vista.puntero[0] - 880) < 25


def test_iman_elige_el_boton_quedandose_quieto_cerca():
    s = sim_ojos()
    s.maquina.poner_objetivos([Objetivo("barra:doble", (1000, 300, 1100, 400))])
    mirar(s, 600, 350, 0.5)
    mirar(s, 950, 350, 2.0)                     # fuera del botón, a 50 px
    assert "barra:doble" in s.elegidos() and s.maquina.modo_clic == "doble"


def test_sin_iman_no_se_pega_y_nunca_hay_iman_sobre_otros_programas():
    s = sim_ojos(**{"ojos.iman": False})
    s.maquina.poner_objetivos([Objetivo("barra:clic", (1000, 300, 1100, 400))])
    mirar(s, 960, 350, 1.0)
    assert s.vista.iman is None and abs(s.vista.puntero[0] - 960) < 25
    s = sim_ojos()
    s.maquina.poner_objetivos([Objetivo("ventana:principal", (1000, 300, 1100, 400), elegible=False)])
    mirar(s, 960, 350, 1.0)
    assert s.vista.iman is None


def test_con_la_cabeza_no_hay_iman():
    s = Sim(calibracion=cal_con_mirada())
    s.maquina.poner_objetivos([Objetivo("barra:clic", (1000, 300, 1100, 400))])
    s.quieto(1.0)
    assert s.vista.iman is None


# =========================================================================== lupa
def test_con_ojos_la_permanencia_libre_abre_la_lupa_y_el_clic_cae_en_el_punto_correcto():
    s = sim_ojos(**{"lupa.espera_s": 20.0})
    mirar(s, 300, 300, 0.6)
    mirar(s, 900, 250, 2.5)
    abiertos = [e for e in s.elegidos() if e.startswith(L.PREFIJO_ABRIR)]
    assert len(abiertos) == 1 and s.clics() == []
    assert s.maquina.submodo == K.LUPA
    zona, ventana, imagen = L.leer_id(abiertos[0])
    s.maquina.poner_objetivos([Objetivo(L.ID_ZONA, imagen, elegible=True),
                               Objetivo(L.ID_CERRAR, (ventana[0], ventana[3] - 90, ventana[2], ventana[3]))])
    # punto real que se quiere: (910, 260); en la imagen agrandada:
    destino = L.a_imagen((910, 260), imagen, zona)
    mirar(s, destino[0], destino[1], 0.4)
    s.limpiar()
    mirar(s, destino[0], destino[1], 3.0)
    clics = s.clics()
    assert len(clics) == 1 and clics[0].boton == K.IZQ
    mov = [a for a in s.de_tipo(Mover)]
    i = [k for k, (_, a) in enumerate(s.acciones) if isinstance(a, Clic)][0]
    ult = [a for _, a in s.acciones[:i] if isinstance(a, Mover)][-1]
    assert math.hypot(ult.x - 910, ult.y - 260) <= 12
    assert s.maquina.submodo == K.NORMAL and mov


def test_con_ojos_y_modo_doble_la_lupa_hace_doble_clic():
    s = sim_ojos(**{"lupa.espera_s": 20.0})
    s.maquina.modo_clic = "doble"
    mirar(s, 300, 300, 0.6)
    mirar(s, 900, 250, 2.5)
    zona, ventana, imagen = L.leer_id([e for e in s.elegidos() if e.startswith(L.PREFIJO_ABRIR)][0])
    s.maquina.poner_objetivos([Objetivo(L.ID_ZONA, imagen)])
    c = ((imagen[0] + imagen[2]) / 2, (imagen[1] + imagen[3]) / 2)
    mirar(s, *c, 3.5)
    assert [x.veces for x in s.clics()] == [2]


def test_ojos_y_cabeza_no_usa_la_lupa_de_los_ojos():
    s = sim_ojos("cabeza_y_ojos")
    s.maquina.poner_objetivos([])
    mirar(s, 300, 300, 1.0)
    from dataclasses import replace
    m = medidas_mirando(300, 300)
    s.durante(1.0, lambda t: replace(m, yaw_n=m.yaw_n + 0.03 * min(t / 0.4, 1)))   # se mueve con la cabeza
    s.durante(2.5, lambda t: replace(m, yaw_n=m.yaw_n + 0.03))
    assert not any(e.startswith(L.PREFIJO_ABRIR) for e in s.elegidos())
    assert len(s.clics()) == 1


# =========================================================================== seguridad
def test_mirar_fuera_de_la_pantalla_congela_y_no_hace_clics():
    s = sim_ojos(**{"ojos.lupa": False})
    mirar(s, 700, 384, 0.6)
    s.limpiar()
    mirar(s, 1366 * 1.35, 384, 3.0)               # muy a la derecha, fuera del monitor
    assert s.vista.mirando_afuera
    assert s.clics() == []
    mirar(s, 700, 384, 0.5)
    assert not s.vista.mirando_afuera


def test_sin_cara_y_otra_cara_siguen_pausando_con_los_ojos():
    s = sim_ojos()
    mirar(s, 700, 384, 0.5)
    s.durante(11.0, lambda t: None)
    assert s.maquina.estado == K.PAUSA


def test_ayuda_vale_con_los_ojos_y_durante_la_emergencia_no_hay_clics():
    s = sim_ojos()
    cx, cy = MON.centro
    s.maquina.poner_objetivos([Objetivo(K.ID_EMERGENCIA_BARRA, (1150, 300, 1300, 450))])
    mirar(s, 600, 384, 0.6)
    mirar(s, 1225, 375, 4.0)
    assert s.maquina.emergencia
    s.limpiar()
    s.maquina.poner_objetivos([Objetivo(K.ID_ATENDIDO, (cx - 170, cy - 70, cx + 170, cy + 70))])
    mirar(s, 300, 600, 1.0)
    assert s.clics() == [] and not s.de_tipo(Bajar)
    mirar(s, cx, cy, 4.0)                        # la mirada lleva al puntero a «Ya me atendieron»
    assert not s.maquina.emergencia
    verificar_invariantes(s.salida)


def test_recentrar_con_los_ojos_pide_mirar_el_centro_y_corrige_el_desplazamiento():
    s = sim_ojos()
    mirar(s, *MON.centro, 0.5)
    mod = s.maquina.puntero._mirada.modelo
    mod.desplazamiento = (120.0, -60.0)          # como si la mirada se hubiera corrido
    s.limpiar()
    s.orden("recentrar")
    assert "ojos_recentrar" in s.avisos()
    mirar(s, *MON.centro, 2.0)
    assert mod.desplazamiento == pytest.approx((0.0, 0.0), abs=6)
    mirar(s, *MON.centro, 1.0)
    x, y = s.maquina.puntero.posicion
    assert math.hypot(x - MON.centro[0], y - MON.centro[1]) < 20


def test_aviso_de_distancia_si_la_cara_cambio_de_tamano():
    s = sim_ojos()
    from dataclasses import replace
    m = medidas_mirando(700, 384)
    s.durante(4.0, lambda t: m)
    assert "ojos_distancia" not in s.avisos()
    # se aleja de a poco (un salto brusco de tamaño sería «otra cara»)
    s.durante(6.0, lambda t: replace(m, io_px=m.io_px * (1 - 0.3 * min(t / 4.0, 1))))
    s.durante(10.0, lambda t: replace(m, io_px=m.io_px * 0.7))
    assert s.maquina.estado == K.ACTIVO
    assert s.avisos().count("ojos_distancia") == 1     # una vez por minuto como mucho


def test_pausa_con_los_ojos_reanudar_mirando_el_boton():
    s = sim_ojos()
    mirar(s, 700, 384, 0.5)
    s.orden("pausar", "cuidador")
    s.maquina.poner_objetivos([Objetivo("reanudar", (1000, 500, 1200, 650))])
    mirar(s, 400, 300, 0.8)
    mirar(s, 1100, 575, 3.0)
    assert s.maquina.estado == K.ACTIVO
    assert s.clics() == []


def test_recentrar_con_los_ojos_no_se_pierde_al_cambiar_una_opcion():
    """Revisión de la 1.1: el cuidador toca cualquier «+» o «−» de Opciones (la vista previa manda
    la configuración a la máquina) y la mirada no vuelve a quedar corrida."""
    import copy
    s = sim_ojos()
    mirar(s, *MON.centro, 0.5)
    s.maquina.puntero._mirada.modelo.desplazamiento = (35.0, -20.0)    # lo que dejó «Recentrar»
    cfg = copy.deepcopy(s.cfg)
    cfg["emergencia"]["volumen"] = 80
    s.orden("nueva_config", cfg)
    assert s.maquina.puntero.usa_ojos
    assert s.maquina.puntero._mirada.modelo.desplazamiento == pytest.approx((35.0, -20.0))
    # con una calibración nueva se empieza de cero
    s.orden("nueva_config", copy.deepcopy(cfg), cal_con_mirada())
    assert s.maquina.puntero._mirada.modelo.desplazamiento == pytest.approx((0.0, 0.0))
