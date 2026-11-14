"""Versión 1.1, paquete B: el botón AYUDA (emergencia) en la máquina de estados, con caras
sintéticas (sin cámara).

- Quedarse quieto 2,5 s sobre AYUDA la pide (2,4 s no); pasar por encima no.
- Vale en ACTIVO y en PAUSA (la del cuidador y la automática), en Sin clic, Lupa, Desplazar y
  arrastrando (suelta el botón primero).
- Durante la emergencia ningún clic, botón ni rueda llega a Windows.
- Se apaga con «Ya me atendieron» (3 s quieto), el atajo o el ratón; vuelve al estado anterior y
  AYUDA queda bloqueado hasta salir de él.
- El gesto LARGO asignado a «emergencia» la pide; el corto y los parpadeos nunca.
"""
import pytest

from conftest import Sim, cfg_prueba, medidas, verificar_invariantes
from lycan_face_control import constantes as K
from lycan_face_control.acciones import Aviso, Bajar, Clic, Mover, Rueda, SoltarTodo, Subir
from lycan_face_control.permanencia import Objetivo
from test_estados import RP, RY, Y0, P0, boca, ir, quieto

AYUDA = K.ID_EMERGENCIA_BARRA


def _ayuda_a_la_derecha(s, extra=()):
    """AYUDA a la derecha del centro (como el «Reanudar» de las pruebas de la pausa)."""
    cx, cy = s.monitor.centro
    s.maquina.poner_objetivos([Objetivo(AYUDA, (cx + 150, cy - 80, cx + 350, cy + 80))] + list(extra))


def _atendido_en_el_centro(s, extra=()):
    cx, cy = s.monitor.centro
    s.maquina.poner_objetivos([Objetivo(K.ID_ATENDIDO, (cx - 170, cy - 70, cx + 170, cy + 70))] + list(extra))


def _tiempo_hasta_disparo(s, maximo=6.0):
    """Quieto cuadro a cuadro: segundos desde que el puntero entra a AYUDA hasta la emergencia."""
    t_entra = None
    fin = s.t + maximo
    m = medidas(yaw_n=s._yaw, pitch_n=s._pitch)
    while s.t < fin:
        s.paso(m)
        if t_entra is None and s.vista.objetivo == AYUDA:
            t_entra = s.t - s.dt
        if s.maquina.emergencia:
            return s.t - s.dt - t_entra
    return None


# =========================================================================== pedir ayuda
def test_quieto_2_4_s_no_pide_ayuda_y_2_5_s_si():
    s = Sim()
    quieto(s, 0.3)
    _ayuda_a_la_derecha(s)
    s.limpiar()
    # se acerca SIN entrar (para medir desde que entra)
    ir(s, 0.15)
    assert s.vista.objetivo is None
    s._yaw = Y0 + 0.4 * RY
    dur = _tiempo_hasta_disparo(s)
    assert dur is not None
    assert 2.4 < dur <= 2.5 + 2 * s.dt, dur
    assert Aviso("emergencia", "botón") in s.de_tipo(Aviso)
    assert any(isinstance(a, SoltarTodo) and a.motivo == "emergencia" for a in s.de_tipo(SoltarTodo))
    assert s.clics() == []
    assert s.maquina.vista.emergencia is True


def test_el_tiempo_de_ayuda_es_el_de_la_configuracion_aunque_la_interfaz_diga_otro():
    s = Sim(cfg_prueba(**{"emergencia.permanencia_s": 4.0}))
    quieto(s, 0.3)
    cx, cy = s.monitor.centro
    # la interfaz publica un tiempo corto por error: manda la configuración
    s.maquina.poner_objetivos([Objetivo(AYUDA, (cx + 150, cy - 80, cx + 350, cy + 80), tiempo_s=0.5)])
    ir(s, 0.15)
    s._yaw = Y0 + 0.4 * RY
    dur = _tiempo_hasta_disparo(s)
    assert 3.9 < dur <= 4.0 + 2 * s.dt


def test_pasar_por_encima_sin_parar_no_pide_ayuda():
    s = Sim()
    quieto(s, 0.3)
    _ayuda_a_la_derecha(s)
    for _ in range(6):                      # de un lado al otro, sin parar (unos 300 a 400 px/s)
        ir(s, -0.6, dur=4.0)
        ir(s, 0.9, dur=4.0)
    assert not s.maquina.emergencia
    assert "emergencia" not in s.avisos()


def test_en_la_pausa_del_cuidador_quieto_sobre_ayuda_la_pide():
    s = Sim()
    quieto(s, 0.3)
    s.orden("alternar_pausa")
    assert s.maquina.estado == K.PAUSA and s.maquina.motivo_pausa == "atajo"
    _ayuda_a_la_derecha(s)
    ir(s, 0.4)
    quieto(s, 3.0)
    assert s.maquina.emergencia
    assert s.maquina.estado == K.PAUSA                # la emergencia no quita la pausa por debajo
    assert s.clics() == []


def test_con_la_pausa_automatica_sin_cara_al_volver_la_cara_quieto_sobre_ayuda_la_pide():
    s = Sim()
    quieto(s, 0.3)
    s.durante(10.5, lambda _t: None)
    assert s.maquina.estado == K.PAUSA and s.maquina.pausa_auto
    _ayuda_a_la_derecha(s)
    s._yaw = Y0 + 0.4 * RY
    quieto(s, 4.0)
    assert s.maquina.emergencia
    assert s.clics() == []


def test_en_sin_clic_y_en_lupa_ayuda_tambien_vale():
    for modo in ("barra:sin_clic", "barra:lupa"):
        s = Sim()
        quieto(s, 0.3)
        s.orden("elegir", modo)
        _ayuda_a_la_derecha(s)
        ir(s, 0.4)
        quieto(s, 3.0)
        assert s.maquina.emergencia, modo
        assert s.clics() == []


def test_un_gesto_de_clic_sobre_ayuda_no_la_pide_y_recuerda_como():
    s = Sim()
    quieto(s, 0.3)
    _ayuda_a_la_derecha(s)
    ir(s, 0.4)
    boca(s, 0.8)                            # gesto corto de clic encima, antes de los 2,5 s
    assert not s.maquina.emergencia
    assert "emergencia_quieto" in s.avisos()
    assert s.clics() == []


def test_arrastrando_pedir_ayuda_suelta_el_boton_antes_de_todo():
    s = Sim()
    quieto(s, 0.3)
    s.orden("elegir", "barra:arrastrar")
    ir(s, -0.3)
    quieto(s, 1.3)
    assert s.salida.botones_abajo == ["izq"]
    _ayuda_a_la_derecha(s)
    s.limpiar()
    ir(s, 0.4)
    quieto(s, 3.0)
    assert s.maquina.emergencia
    tipos = [a for _, a in s.acciones]
    i_subir = next(i for i, a in enumerate(tipos) if isinstance(a, Subir))
    i_aviso = next(i for i, a in enumerate(tipos) if isinstance(a, Aviso) and a.clave == "emergencia")
    assert i_subir < i_aviso
    assert s.salida.botones_abajo == []
    assert s.maquina.submodo == K.NORMAL
    verificar_invariantes(s.salida)


def test_en_desplazar_ayuda_se_elige_con_el_puntero_virtual_y_sale_del_modo():
    s = Sim()
    quieto(s, 0.3)
    s.orden("elegir", "barra:desplazar")
    assert s.maquina.submodo == K.DESPLAZAR
    _ayuda_a_la_derecha(s)
    ir(s, 0.4)
    quieto(s, 3.0)
    assert s.maquina.emergencia
    assert s.maquina.submodo == K.NORMAL
    # desde Desplazar por orden (el cuidador con el ratón): igual
    s2 = Sim()
    quieto(s2, 0.3)
    s2.orden("elegir", "barra:desplazar")
    s2.orden("elegir", AYUDA)
    assert s2.maquina.emergencia and s2.maquina.submodo == K.NORMAL


# =========================================================================== durante la emergencia
def test_durante_la_emergencia_nada_llega_a_windows_salvo_mover():
    s = Sim()
    quieto(s, 0.3)
    s.orden("pedir_ayuda", "botón")
    assert s.maquina.emergencia
    s.limpiar()
    t0 = s.t
    while s.t - t0 < 60.0:
        ir(s, 0.5, 0.3)
        quieto(s, 2.5)                      # quieto fuera de todo: no hay clic por permanencia
        boca(s, 0.8)                        # gesto de clic
        s.quieto(0.8, yaw_n=s._yaw, pitch_n=s._pitch, cejas=0.5)   # clic derecho
        boca(s, 2.3)                        # gesto largo (pausar): tampoco
        ir(s, -0.5, -0.3)
    assert s.clics() == [] and s.de_tipo(Bajar) == [] and s.de_tipo(Rueda) == []
    assert s.de_tipo(Mover)                 # el puntero sí sigue a la cabeza
    assert s.maquina.emergencia
    verificar_invariantes(s.salida)


def test_la_cara_perdida_y_mirar_afuera_no_apagan_la_emergencia():
    s = Sim()
    quieto(s, 0.3)
    s.orden("pedir_ayuda", "botón")
    s.durante(15.0, lambda _t: None)       # más que la pausa automática
    assert s.maquina.emergencia and s.maquina.estado == K.ACTIVO
    ir(s, 2.5)                              # muy fuera del rango cómodo
    quieto(s, 3.0)
    assert s.maquina.emergencia
    assert s.clics() == []


def test_ya_me_atendieron_quieto_3_s_vuelve_a_activo():
    s = Sim()
    quieto(s, 0.3)
    s.orden("pedir_ayuda", "botón")
    _atendido_en_el_centro(s)
    # el puntero ya estaba en el centro: primero hay que salir y volver
    quieto(s, 4.0)
    assert s.maquina.emergencia
    ir(s, 0.8)
    ir(s, 0.0)
    quieto(s, 2.8)
    assert s.maquina.emergencia             # 3 s, no menos
    quieto(s, 0.5)
    assert not s.maquina.emergencia
    assert s.maquina.estado == K.ACTIVO
    assert "emergencia_fin" in s.avisos()
    assert K.ID_ATENDIDO in s.elegidos()
    assert s.clics() == []


def test_ya_me_atendieron_vuelve_a_la_pausa_si_estaba_en_pausa():
    s = Sim()
    quieto(s, 0.3)
    s.orden("alternar_pausa")
    s.orden("pedir_ayuda", "gesto")
    _atendido_en_el_centro(s)
    ir(s, 0.8)
    ir(s, 0.0)
    quieto(s, 3.5)
    assert not s.maquina.emergencia
    assert s.maquina.estado == K.PAUSA and s.maquina.motivo_pausa == "atajo"


def test_el_atajo_y_el_raton_tambien_apagan_y_sin_emergencia_no_hacen_nada():
    s = Sim()
    quieto(s, 0.3)
    assert s.orden("atendido", "atajo") == []          # sin emergencia: nada
    assert s.maquina.estado == K.ACTIVO
    s.orden("pedir_ayuda", "botón")
    s.orden("atendido", "atajo")
    assert not s.maquina.emergencia and s.maquina.estado == K.ACTIVO
    s.orden("pedir_ayuda", "botón")
    s.orden("elegir", K.ID_ATENDIDO)                    # clic del cuidador en el botón
    assert not s.maquina.emergencia
    # pedirla dos veces no la duplica
    s.orden("pedir_ayuda", "botón")
    acc = s.orden("pedir_ayuda", "botón")
    assert acc == [] and s.avisos().count("emergencia") == 3


def test_despues_ayuda_queda_bloqueado_hasta_salir_del_boton():
    s = Sim()
    quieto(s, 0.3)
    _ayuda_a_la_derecha(s)
    ir(s, 0.4)
    quieto(s, 3.0)
    assert s.maquina.emergencia
    s.orden("atendido", "atajo")                        # el puntero sigue sobre AYUDA
    quieto(s, 6.0)
    assert not s.maquina.emergencia                     # quieto encima no la vuelve a pedir
    ir(s, -0.4)
    ir(s, 0.4)
    quieto(s, 3.0)
    assert s.maquina.emergencia                         # saliendo y volviendo, sí


def test_al_terminar_el_gesto_en_curso_no_hace_clic():
    s = Sim()
    quieto(s, 0.3)
    s.orden("pedir_ayuda", "botón")
    quieto(s, 0.2)
    s.quieto(0.4, yaw_n=s._yaw if hasattr(s, "_yaw") else Y0, pitch_n=P0, mar=0.6)
    s.orden("atendido", "atajo")
    quieto(s, 0.6)
    assert s.clics() == []


# =========================================================================== gestos y parpadeo
def test_gesto_largo_emergencia_pide_ayuda_en_activo_y_en_pausa():
    cfg = cfg_prueba(**{"gestos.boca.largo": "emergencia"})
    s = Sim(cfg)
    quieto(s, 0.3)
    boca(s, 2.3)
    assert s.maquina.emergencia
    assert Aviso("emergencia", "gesto") in s.de_tipo(Aviso)
    s.orden("atendido", "atajo")
    s.orden("alternar_pausa")                           # pausa del cuidador
    quieto(s, 1.2)
    boca(s, 2.3)
    assert s.maquina.emergencia and s.maquina.estado == K.PAUSA
    assert s.clics() == []


def test_un_bostezo_corto_o_largo_de_mas_no_pide_ayuda():
    s = Sim(cfg_prueba(**{"gestos.boca.largo": "emergencia"}))
    quieto(s, 0.3)
    s.orden("alternar_pausa")
    quieto(s, 1.0)
    boca(s, 1.2)                     # corto: es el clic (en pausa no hace nada)
    boca(s, 6.0)                     # mucho más que el gesto largo: bostezo o descanso
    assert not s.maquina.emergencia


def test_el_gesto_corto_nunca_pide_ayuda_aunque_la_configuracion_lo_diga():
    cfg = cfg_prueba()
    cfg["gestos"]["boca"]["corto"] = "emergencia"       # sin validar (no debería pasar nunca)
    s = Sim(cfg)
    quieto(s, 0.3)
    boca(s, 0.8)
    assert not s.maquina.emergencia
    # y la validación lo corrige
    assert cfg_prueba(**{"gestos.boca.corto": "emergencia"})["gestos"]["boca"]["corto"] == "ninguna"


@pytest.mark.parametrize("fuera", ["ninguna", "emergencia"])
def test_cinco_minutos_de_parpadeos_naturales_y_largos_nunca_piden_ayuda(fuera):
    cfg = cfg_prueba()
    cfg["gestos"]["parpadeo"]["fuera_barrido"] = fuera  # "emergencia" sin validar: igual no
    s = Sim(cfg)
    quieto(s, 0.3)
    _ayuda_a_la_derecha(s)
    ir(s, -0.4)
    t0 = s.t
    n = 0
    while s.t - t0 < 300.0:
        d = (0.12, 0.2, 0.35, 1.0, 1.6)[n % 5]          # naturales y largos (sueño, cansancio)
        quieto(s, d, ear_der=0.02, ear_izq=0.02)
        quieto(s, 2.5)
        n += 1
    assert not s.maquina.emergencia
    assert "emergencia" not in s.avisos()


def test_en_el_barrido_ayuda_elegida_desde_el_teclado_la_pide():
    s = Sim()
    quieto(s, 0.3)
    s.orden("poner_submodo", K.BARRIDO)
    s.orden("elegir", K.ID_EMERGENCIA_TECLADO)
    assert s.maquina.emergencia
    assert Aviso("emergencia", "barrido") in s.de_tipo(Aviso)
    assert s.maquina.submodo == K.BARRIDO               # al terminar sigue en el barrido
    s.orden("atendido", "atajo")
    assert s.maquina.submodo == K.BARRIDO and not s.maquina.emergencia


def test_mirando_afuera_el_gesto_largo_de_emergencia_vale():
    s = Sim(cfg_prueba(**{"gestos.boca.largo": "emergencia"}))
    quieto(s, 0.3)
    ir(s, 2.5)
    quieto(s, 0.5)
    assert s.maquina.vista.mirando_afuera
    boca(s, 2.3)
    assert s.maquina.emergencia


def test_pedir_ayuda_sin_cara_desde_el_raton_y_al_terminar_sigue_como_siempre():
    s = Sim()
    quieto(s, 0.3)
    s.durante(1.0, lambda _t: None)
    assert s.maquina.estado == K.SIN_CARA
    s.orden("elegir", AYUDA)                            # el cuidador con el ratón
    assert s.maquina.emergencia
    s.orden("atendido", "atajo")
    s.durante(0.5, lambda _t: None)
    assert s.maquina.estado == K.SIN_CARA               # sin cara otra vez, como siempre
    s.durante(10.5, lambda _t: None)
    assert s.maquina.estado == K.PAUSA
