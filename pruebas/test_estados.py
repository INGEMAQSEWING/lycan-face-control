"""Máquina de estados (sección 5) con el simulador ``Sim`` (máquina + salida simulada)."""
import math

import pytest

from conftest import REPOSO, Sim, cfg_prueba, medidas, verificar_invariantes
from lycan_face_control import constantes as K
from lycan_face_control.acciones import Bajar, Clic, Mover, Rueda, SoltarTodo
from lycan_face_control.permanencia import Objetivo

Y0, P0 = REPOSO["yaw_n"], REPOSO["pitch_n"]
RY, RP = 0.089, 0.094


def ir(sim, yaw_f, pitch_f=0.0, dur=0.6, **kw):
    """Mueve la cabeza en línea recta hasta (yaw_f, pitch_f) en fracciones del rango cómodo."""
    m0 = sim.maquina.puntero
    y_ini = getattr(sim, "_yaw", Y0)
    p_ini = getattr(sim, "_pitch", P0)
    y_fin, p_fin = Y0 + yaw_f * RY, P0 + pitch_f * RP
    sim.durante(dur, lambda t: medidas(yaw_n=y_ini + (y_fin - y_ini) * min(t / dur, 1),
                                       pitch_n=p_ini + (p_fin - p_ini) * min(t / dur, 1), **kw))
    sim._yaw, sim._pitch = y_fin, p_fin
    return m0.posicion


def quieto(sim, dur, **kw):
    sim.quieto(dur, yaw_n=getattr(sim, "_yaw", Y0), pitch_n=getattr(sim, "_pitch", P0), **kw)


def boca(sim, dur, nivel=0.6):
    quieto(sim, 0.1)
    quieto(sim, dur, mar=nivel)
    quieto(sim, 0.2)


def botones(sim):
    return sim.salida.botones()


# ---------------------------------------------------------------- arranque
def test_arranca_activo_con_calibracion_y_en_pausa_sin_ella():
    assert Sim().maquina.estado == K.ACTIVO
    s = Sim(calibracion=None)
    assert s.maquina.estado == K.PAUSA
    s.quieto(2.0, yaw_n=0.05, pitch_n=0.5)
    assert "recomendar_calibrar" in s.avisos()
    # sin calibrar, el centro es la postura de la persona al aparecer
    assert (s.maquina.mapeo.yaw0, s.maquina.mapeo.pitch0) == pytest.approx((0.05, 0.5))


def test_arranque_forzado_en_pausa():
    s = Sim(cfg_prueba(**{"arranque.estado": "pausa"}))
    assert s.maquina.estado == K.PAUSA


# ---------------------------------------------------------------- puntero y permanencia
def test_mover_la_cabeza_mueve_el_puntero():
    s = Sim()
    quieto(s, 0.5)
    ir(s, 0.5, -0.5, dur=1.0)
    quieto(s, 0.5)
    x, y = s.salida.cursor
    cx, cy = s.monitor.centro
    assert x > cx + 200 and y < cy - 100
    assert s.de_tipo(Mover)


def test_clic_por_permanencia_una_sola_vez():
    s = Sim()
    quieto(s, 0.5)
    ir(s, 0.3)
    quieto(s, 4.0)
    assert s.clics() == [Clic("izq")]
    verificar_invariantes(s.salida)


def test_quedarse_quieto_al_empezar_no_hace_clic():
    s = Sim()
    quieto(s, 5.0)
    assert s.clics() == []


def test_permanencia_apagada_solo_gestos():
    s = Sim(cfg_prueba(**{"permanencia.activa": False}))
    quieto(s, 0.3)
    ir(s, 0.3)
    quieto(s, 3.0)
    assert s.clics() == []
    boca(s, 0.8)
    assert s.clics() == [Clic("izq")]


def test_gesto_congela_el_puntero_y_detiene_la_permanencia():
    s = Sim()
    quieto(s, 0.3)
    ir(s, 0.3)
    quieto(s, 0.5)
    pos = s.salida.cursor
    # boca abierta 1,5 s (la nariz se mueve un poco con la boca): ni se mueve ni hay clic por permanencia
    s.quieto(1.5, yaw_n=s._yaw + 0.01, pitch_n=s._pitch + 0.02, mar=0.6)
    assert abs(s.salida.cursor[0] - pos[0]) <= 3
    assert s.clics() == []
    assert s.maquina.vista.congelado


def test_boca_corta_es_clic_y_no_se_suma_la_permanencia():
    s = Sim()
    quieto(s, 0.3)
    ir(s, 0.3)
    boca(s, 0.8)
    quieto(s, 3.0)
    assert s.clics() == [Clic("izq")]


def test_cejas_es_clic_derecho():
    s = Sim()
    quieto(s, 0.3)
    s.quieto(0.8, cejas=0.356 * 1.3)          # 600 ms de fábrica (ronda 2: 350 ms daba clics al sorprenderse)
    quieto(s, 0.3)
    assert s.clics() == [Clic("der")]


# ---------------------------------------------------------------- pausa
def test_pausar_con_boca_larga_y_reanudar_exige_3_s():
    s = Sim()
    quieto(s, 0.3)
    boca(s, 2.3)
    assert s.maquina.estado == K.PAUSA
    assert any(isinstance(a, SoltarTodo) for a in s.de_tipo(SoltarTodo))
    assert s.clics() == []
    # 2,5 s de boca en pausa: no reanuda
    boca(s, 2.5)
    assert s.maquina.estado == K.PAUSA
    # 3,2 s: reanuda; al soltar no pausa otra vez ni hace clic
    boca(s, 3.2)
    assert s.maquina.estado == K.ACTIVO
    quieto(s, 1.0)
    assert s.maquina.estado == K.ACTIVO
    assert s.clics() == []


def test_en_pausa_no_mueve_ni_hace_clic():
    s = Sim()
    quieto(s, 0.3)
    s.orden("alternar_pausa")
    s.limpiar()
    ir(s, 0.6)
    quieto(s, 3.0)
    boca(s, 0.8)
    s.quieto(0.6, cejas=0.5)
    assert s.de_tipo(Mover) == [] and s.clics() == []
    assert s.maquina.vista.puntero_virtual is not None


def test_atajo_pausa_y_reanuda_y_siempre_suelta():
    s = Sim()
    quieto(s, 0.3)
    acc = s.orden("alternar_pausa")
    assert any(isinstance(a, SoltarTodo) for a in acc)
    assert s.maquina.estado == K.PAUSA and s.maquina.motivo_pausa == "atajo"
    acc = s.orden("alternar_pausa")
    assert any(isinstance(a, SoltarTodo) for a in acc)
    assert s.maquina.estado == K.ACTIVO


def test_reanudar_con_permanencia_de_2_s_sobre_el_boton():
    s = Sim()
    quieto(s, 0.3)
    s.orden("alternar_pausa")
    cx, cy = s.monitor.centro
    # el botón "Reanudar" está a la derecha del centro
    s.maquina.poner_objetivos([Objetivo("reanudar", (cx + 150, cy - 80, cx + 350, cy + 80))])
    ir(s, 0.4)
    quieto(s, 1.5)
    assert s.maquina.estado == K.PAUSA
    quieto(s, 1.0)
    assert s.maquina.estado == K.ACTIVO
    assert "reanudar" in s.elegidos()
    assert s.clics() == []


def test_reanudar_sin_mirar_el_boton_no_reanuda():
    s = Sim()
    quieto(s, 0.3)
    s.orden("alternar_pausa")
    cx, cy = s.monitor.centro
    s.maquina.poner_objetivos([Objetivo("reanudar", (cx + 150, cy - 80, cx + 350, cy + 80))])
    ir(s, -0.4)
    quieto(s, 5.0)
    assert s.maquina.estado == K.PAUSA


# ---------------------------------------------------------------- sin cara
def test_perder_la_cara_a_mitad_de_un_arrastre_suelta_a_los_300_ms():
    s = Sim()
    quieto(s, 0.3)
    s.orden("elegir", "barra:arrastrar")
    assert s.maquina.submodo == K.ARRASTRE_INICIO
    ir(s, 0.3)
    quieto(s, 1.3)
    assert s.maquina.submodo == K.ARRASTRANDO
    assert s.salida.botones_abajo == ["izq"]
    ir(s, 0.6)
    t_perdida = s.t
    s.durante(0.25, lambda t: None)
    assert s.maquina.estado == K.SIN_CARA
    assert s.salida.botones_abajo == ["izq"]           # aún no (300 ms)
    s.durante(0.1, lambda t: None)
    assert s.salida.botones_abajo == []
    soltar = [t for t, a in s.acciones if isinstance(a, SoltarTodo) and a.motivo == "sin cara"]
    assert soltar and soltar[0] - t_perdida == pytest.approx(0.3, abs=0.04)
    assert s.maquina.submodo == K.NORMAL
    # vuelve la cara: nada queda abajo, sigue activo
    quieto(s, 2.0)
    assert s.maquina.estado == K.ACTIVO
    verificar_invariantes(s.salida)


def test_pausa_automatica_a_los_10_s_y_reanuda_con_cara_estable_1_s():
    s = Sim()
    quieto(s, 0.3)
    s.durante(9.5, lambda t: None)
    assert s.maquina.estado == K.SIN_CARA
    s.durante(0.6, lambda t: None)
    assert s.maquina.estado == K.PAUSA and s.maquina.pausa_auto
    # la cara aparece a ratos: no reanuda
    for _ in range(3):
        quieto(s, 0.5)
        s.durante(0.2, lambda t: None)
    assert s.maquina.estado == K.PAUSA
    quieto(s, 1.1)
    assert s.maquina.estado == K.ACTIVO


def test_pausa_a_proposito_no_se_reanuda_sola():
    s = Sim()
    quieto(s, 0.3)
    s.orden("alternar_pausa")
    s.durante(12.0, lambda t: None)
    quieto(s, 3.0)
    assert s.maquina.estado == K.PAUSA


def test_volver_antes_de_300_ms_sigue_igual_y_sin_saltos():
    s = Sim()
    quieto(s, 0.3)
    ir(s, -0.5)
    quieto(s, 0.5)
    antes = s.salida.cursor
    s.durante(0.2, lambda t: None)
    assert s.maquina.estado == K.SIN_CARA
    s.limpiar()
    s.durante(1.0, lambda t: medidas(yaw_n=Y0 + 0.5 * RY, pitch_n=P0))
    assert s.maquina.estado == K.ACTIVO
    xs = [antes[0]] + [a.x for a in s.de_tipo(Mover)]
    dist = abs(xs[-1] - xs[0])
    assert dist > 400
    assert max(abs(b - a) for a, b in zip(xs, xs[1:])) <= dist / 10 + 2


# ---------------------------------------------------------------- arrastre
def test_arrastre_completo_bajar_y_subir():
    s = Sim()
    quieto(s, 0.3)
    s.orden("elegir", "barra:arrastrar")
    ir(s, 0.3)
    quieto(s, 1.3)                        # permanencia: baja el botón
    assert botones(s) == [("izq", True)]
    quieto(s, 3.0)                        # quieto en el mismo sitio NO suelta (hay que moverse)
    assert botones(s) == [("izq", True)]
    ir(s, -0.3)
    quieto(s, 1.3)                        # permanencia en el destino: suelta
    assert botones(s) == [("izq", True), ("izq", False)]
    assert s.maquina.submodo == K.NORMAL and s.maquina.modo_clic == "izq"
    verificar_invariantes(s.salida)


def test_arrastre_con_gesto():
    s = Sim(cfg_prueba(**{"gestos.boca.corto": "arrastrar"}))
    quieto(s, 0.3)
    ir(s, 0.2)
    boca(s, 0.8)
    assert s.salida.botones_abajo == ["izq"]
    ir(s, -0.2)
    boca(s, 0.8)
    assert s.salida.botones_abajo == []
    verificar_invariantes(s.salida)


def test_tope_de_arrastre():
    s = Sim(cfg_prueba(**{"seguridad.arrastre_max_s": 10}))
    quieto(s, 0.3)
    s.orden("elegir", "barra:arrastrar")
    ir(s, 0.3)
    quieto(s, 1.3)
    assert s.salida.botones_abajo == ["izq"]
    # se mueve sin parar (nunca se queda quieto) más allá del tope
    s.durante(11.0, lambda t: medidas(yaw_n=Y0 + 0.5 * RY * math.sin(t * 2), pitch_n=P0))
    assert s.salida.botones_abajo == []
    assert "arrastre_largo" in s.avisos()


def test_pausa_durante_arrastre_suelta():
    s = Sim()
    quieto(s, 0.3)
    s.orden("elegir", "barra:arrastrar")
    ir(s, 0.3)
    quieto(s, 1.3)
    assert s.salida.botones_abajo == ["izq"]
    s.orden("alternar_pausa")
    assert s.salida.botones_abajo == []
    verificar_invariantes(s.salida)


# ---------------------------------------------------------------- modo de clic de la barra
def test_modo_de_clic_de_un_solo_uso():
    s = Sim()
    quieto(s, 0.3)
    s.orden("elegir", "barra:doble")
    assert s.maquina.modo_clic == "doble"
    ir(s, 0.3)
    quieto(s, 1.5)
    ir(s, -0.3)
    quieto(s, 1.5)
    assert s.clics() == [Clic("izq", 2), Clic("izq")]
    assert s.maquina.modo_clic == "izq"


def test_modo_de_clic_fijo():
    s = Sim(cfg_prueba(**{"barra.modo_fijo": True}))
    quieto(s, 0.3)
    s.orden("elegir", "barra:derecho")
    for f in (0.3, -0.3):
        ir(s, f)
        quieto(s, 1.5)
    assert s.clics() == [Clic("der"), Clic("der")]


def test_barra_por_permanencia_nunca_hace_clic_en_windows():
    s = Sim()
    cx, cy = s.monitor.centro
    s.maquina.poner_objetivos([
        Objetivo("ventana:barra", (cx + 100, cy - 200, cx + 300, cy + 200), elegible=False),
        Objetivo("barra:derecho", (cx + 110, cy - 50, cx + 290, cy + 50)),
    ])
    quieto(s, 0.3)
    ir(s, 0.38)
    quieto(s, 1.3)
    assert "barra:derecho" in s.elegidos()
    assert s.clics() == []
    assert s.maquina.modo_clic == "der"
    # gesto de clic sobre la barra: también elige, sin clic
    s.limpiar()
    boca(s, 0.8)
    assert s.clics() == [] and s.elegidos()
    # sobre la ventana de la barra pero fuera de un botón: ni clic ni permanencia
    s.limpiar()
    ir(s, 0.38, -0.25)
    quieto(s, 2.0)
    assert s.clics() == []


# ---------------------------------------------------------------- desplazar
def test_desplazar_envia_rueda_y_termina_a_los_10_s():
    s = Sim()
    quieto(s, 0.3)
    s.orden("elegir", "barra:desplazar")
    assert s.maquina.submodo == K.DESPLAZAR
    pos = s.salida.cursor
    ir(s, 0.0, 0.6, dur=0.3)             # cabeza abajo
    quieto(s, 2.0)
    ruedas = s.de_tipo(Rueda)
    assert ruedas and all(r.delta < 0 for r in ruedas)
    n = len(ruedas)
    assert 4 <= n <= 20                  # entre 1 y 8 muescas por segundo
    assert s.salida.cursor == pos        # el puntero no se mueve
    ir(s, 0.0, 0.0, dur=0.3)             # vuelve al centro: para
    n2 = len(s.de_tipo(Rueda))
    quieto(s, 5.0)
    assert len(s.de_tipo(Rueda)) == n2
    assert s.maquina.submodo == K.DESPLAZAR
    quieto(s, 5.5)
    assert s.maquina.submodo == K.NORMAL
    # cabeza arriba = rueda positiva
    s.orden("elegir", "barra:desplazar")
    s.limpiar()
    ir(s, 0.0, -0.7, dur=0.3)
    quieto(s, 1.0)
    assert all(r.delta > 0 for r in s.de_tipo(Rueda)) and s.de_tipo(Rueda)


def test_desplazar_termina_con_un_gesto_de_clic():
    s = Sim()
    quieto(s, 0.3)
    s.orden("elegir", "barra:desplazar")
    boca(s, 0.8)
    assert s.maquina.submodo == K.NORMAL
    assert s.clics() == []


# ---------------------------------------------------------------- barrido y parpadeo
def parpadeo(sim, dur, ojos=0.05):
    quieto(sim, 0.05, ear_der=0.357 * ojos, ear_izq=0.375 * ojos)
    quieto(sim, dur - 0.05, ear_der=0.357 * ojos, ear_izq=0.375 * ojos)
    quieto(sim, 0.4)


def test_parpadeos_naturales_no_eligen_en_el_barrido():
    s = Sim()
    quieto(s, 0.3)
    s.orden("poner_submodo", K.BARRIDO)
    for d in (0.1, 0.15, 0.25, 0.39, 0.2, 0.39):
        parpadeo(s, d)
        quieto(s, 0.6)
    assert s.elegidos() == [] and s.clics() == []
    parpadeo(s, 0.9)
    assert s.elegidos() == ["barrido:elegir"]


def test_en_barrido_el_puntero_no_se_mueve():
    s = Sim()
    quieto(s, 0.3)
    s.orden("poner_submodo", K.SOLO_COMUNICACION)
    s.limpiar()
    ir(s, 0.7, 0.5)
    quieto(s, 3.0)
    assert s.de_tipo(Mover) == [] and s.clics() == []
    # un gesto de clic (boca) elige lo resaltado
    boca(s, 0.8)
    assert s.elegidos() == ["barrido:elegir"] and s.clics() == []


def test_parpadeo_largo_fuera_del_barrido_no_hace_nada_por_defecto():
    s = Sim()
    quieto(s, 0.3)
    parpadeo(s, 1.0)
    assert s.clics() == [] and s.elegidos() == []


def test_parpadeo_largo_como_clic_y_naturales_nunca():
    s = Sim(cfg_prueba(**{"gestos.parpadeo.fuera_barrido": "clic", "permanencia.activa": False}))
    quieto(s, 0.3)
    for d in (0.1, 0.2, 0.3, 0.39):
        parpadeo(s, d)
    assert s.clics() == []
    parpadeo(s, 1.0)
    assert s.clics() == [Clic("izq")]


def test_doble_parpadeo_reanuda_en_solo_comunicacion():
    s = Sim(cfg_prueba(**{"teclado.solo_comunicacion": True}))
    assert s.maquina.submodo == K.SOLO_COMUNICACION
    quieto(s, 0.3)
    s.orden("alternar_pausa")
    parpadeo(s, 1.0)
    assert s.maquina.estado == K.PAUSA
    parpadeo(s, 1.0)
    assert s.maquina.estado == K.ACTIVO
    assert s.maquina.submodo == K.SOLO_COMUNICACION


# ---------------------------------------------------------------- calibración, recentrar, errores
def test_calibrando_no_envia_nada_y_suelta_al_entrar():
    s = Sim()
    quieto(s, 0.3)
    acc = s.orden("iniciar_calibracion")
    assert any(isinstance(a, SoltarTodo) for a in acc)
    s.limpiar()
    ir(s, 0.5)
    quieto(s, 3.0)
    boca(s, 0.8)
    assert s.acciones == [] or all(not isinstance(a, (Mover, Clic, Bajar)) for _, a in s.acciones)
    s.orden("terminar_calibracion", None)
    assert s.maquina.estado == K.ACTIVO


def test_terminar_calibracion_con_una_nueva():
    s = Sim(calibracion=None)
    quieto(s, 0.3)
    s.orden("iniciar_calibracion")
    from conftest import CAL_SINTETICA
    s.orden("terminar_calibracion", CAL_SINTETICA)
    assert s.maquina.calibracion is CAL_SINTETICA
    assert s.maquina.mapeo.calibrado


def test_recentrar():
    s = Sim()
    quieto(s, 0.3)
    s._yaw = Y0 + 0.3 * RY
    s.orden("recentrar")
    quieto(s, 2.0)
    assert "recentrado" in s.avisos()
    quieto(s, 1.0)
    cx, cy = s.monitor.centro
    assert abs(s.salida.cursor[0] - cx) <= 4


def test_error_suelta_y_pausa_y_tres_errores_es_fatal():
    s = Sim()
    quieto(s, 0.3)
    acc = s.orden("por_error", RuntimeError("x"))
    assert isinstance(acc[0], SoltarTodo)
    assert s.maquina.estado == K.PAUSA and not s.maquina.fatal
    s.orden("por_error", RuntimeError("x"))
    s.orden("por_error", RuntimeError("x"))
    assert s.maquina.fatal


def test_nueva_config_conserva_el_estado_y_suelta():
    s = Sim()
    quieto(s, 0.3)
    cfg = cfg_prueba(**{"puntero.sens_x": 2.0})
    acc = s.orden("nueva_config", cfg)
    assert isinstance(acc[0], SoltarTodo)
    assert s.maquina.estado == K.ACTIVO and s.maquina.mapeo.sens_x == 2.0


# ---------------------------------------------------------------- movimientos involuntarios
def test_movimientos_involuntarios_parpadeos_y_habla_sin_clics_si_no_hay_permanencia():
    """30 s de sacudidas, temblor, parpadeos naturales y habla: con la permanencia apagada,
    ningún clic, ninguna pausa y nada presionado."""
    import numpy as np
    rng = np.random.default_rng(5)
    s = Sim(cfg_prueba(**{"permanencia.activa": False}))
    eventos = []
    t_parp = rng.uniform(1, 4)
    for i in range(30 * 30):
        t = i / 30
        yaw = Y0 + 0.3 * RY * math.sin(t * 0.7) + rng.normal(0, 0.004)
        if rng.random() < 0.02:
            yaw += rng.normal(0, 0.05)                 # sacudida
        pitch = P0 + 0.2 * RP * math.cos(t * 0.5) + rng.normal(0, 0.004)
        ojos = 1.0
        if t_parp <= t < t_parp + 0.25:
            ojos = 0.1
        elif t >= t_parp + 0.25:
            t_parp = t + rng.uniform(1.5, 5)
        hablando = 10 <= t < 14
        mar = (0.016 + 0.3 * abs(math.sin(t * 13))) if hablando else 0.016
        res = s.paso(medidas(yaw_n=yaw, pitch_n=pitch, ear_der=0.357 * ojos, ear_izq=0.375 * ojos, mar=mar))
        eventos += res.vista.gestos.eventos
    assert s.clics() == []
    assert s.maquina.estado == K.ACTIVO
    verificar_invariantes(s.salida)


def test_temblor_grande_continuo_no_hace_clic_por_permanencia():
    s = Sim()
    quieto(s, 0.3)
    s.durante(10.0, lambda t: medidas(yaw_n=Y0 + 0.15 * RY * math.sin(t * 9) + 0.2 * RY * math.sin(t * 1.3),
                                      pitch_n=P0 + 0.1 * RP * math.cos(t * 7)))
    assert s.clics() == []


def test_quedarse_quieto_sobre_pausa_no_pausa_y_reanuda_una_y_otra_vez():
    s = Sim()
    cx, cy = s.monitor.centro
    s.maquina.poner_objetivos([Objetivo("barra:pausa", (cx + 150, cy - 80, cx + 350, cy + 80))])
    quieto(s, 0.3)
    ir(s, 0.4)
    quieto(s, 10.0)
    assert s.maquina.estado == K.PAUSA
    assert s.avisos().count("pausa") == 1 and "activo" not in s.avisos()
    # sale del botón y vuelve: ahora sí reanuda (2 s)
    ir(s, -0.3)
    ir(s, 0.4)
    quieto(s, 2.3)
    assert s.maquina.estado == K.ACTIVO
    quieto(s, 5.0)
    assert s.maquina.estado == K.ACTIVO


def test_botones_de_la_barra_no_se_repiten_quedandose_encima():
    s = Sim()
    cx, cy = s.monitor.centro
    s.maquina.poner_objetivos([Objetivo("barra:doble", (cx + 150, cy - 80, cx + 350, cy + 80))])
    quieto(s, 0.3)
    ir(s, 0.4)
    quieto(s, 5.0)
    assert s.elegidos() == ["barra:doble"]
    assert s.maquina.modo_clic == "doble"
