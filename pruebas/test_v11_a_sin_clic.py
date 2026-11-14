"""Versión 1.1, paquete A: «Sin clic» (modo lectura) y la pestaña de la barra minimizada en la
máquina de estados."""
import json
from pathlib import Path

import pytest

from conftest import CAL_SINTETICA, Sim, cfg_prueba, medidas, verificar_invariantes
from lycan_face_control import constantes as K
from lycan_face_control.acciones import Clic, Sonido
from lycan_face_control.estados import ID_BARRA_MOSTRAR
from lycan_face_control.permanencia import Objetivo
from lycan_face_control.ui import textos as T
from test_estados import boca, ir, quieto
from test_ronda1_puntero import _cal_para

SERIES = json.loads((Path(__file__).parent / "datos" / "serie_quieta_facemesh.json").read_text("utf-8"))["series"]


def _sim(**cambios):
    s = Sim(cfg_prueba(**cambios))
    quieto(s, 0.3)
    s.orden("elegir", "barra:sin_clic")
    assert s.maquina.modo_clic == "ninguno"
    return s


@pytest.mark.parametrize("ruido", sorted(SERIES))
def test_cinco_minutos_quieto_con_temblor_real_no_hace_ningun_clic(ruido):
    serie = SERIES[ruido]
    s = Sim(cfg_prueba(), calibracion=_cal_para(serie), fps=20)
    s.paso(medidas(yaw_n=serie[0][0], pitch_n=serie[0][1]))
    s.orden("elegir", "barra:sin_clic")
    s.limpiar()
    for _vuelta in range(5):                     # 5 × 60 s
        for y, p in serie:
            s.paso(medidas(yaw_n=y, pitch_n=p))
    assert s.clics() == []
    assert Sonido("clic") not in s.de_tipo(Sonido)
    assert s.maquina.modo_clic == "ninguno"
    # el anillo nunca se muestra fuera de lo propio
    assert not s.vista.permanencia.visible
    verificar_invariantes(s.salida)


def test_moverse_y_quedarse_quieto_fuera_no_hace_clic_pero_el_puntero_sigue():
    s = _sim()
    s.limpiar()
    for f in (-0.6, 0.5, 0.2, -0.3):
        p0 = s.maquina.puntero.posicion
        ir(s, f)
        assert s.maquina.puntero.posicion != p0      # el puntero sigue a la cabeza (no es pausa)
        quieto(s, 2.5)
    assert s.clics() == []
    assert s.maquina.estado == K.ACTIVO


def test_sobre_el_boton_clic_la_permanencia_elige_y_vuelve_al_clic_normal():
    s = _sim()
    cx, cy = s.monitor.centro
    s.maquina.poner_objetivos([Objetivo("ventana:barra", (cx + 100, cy - 200, cx + 300, cy + 200), elegible=False),
                               Objetivo("barra:clic", (cx + 110, cy - 50, cx + 290, cy + 50))])
    ir(s, 0.38)
    quieto(s, 1.4)
    assert "barra:clic" in s.elegidos()
    assert s.maquina.modo_clic == "izq"
    assert s.clics() == []
    # ya en el clic normal, quedarse quieto fuera hace clic otra vez
    ir(s, -0.4)
    quieto(s, 1.5)
    assert s.clics() == [Clic(K.IZQ)]


def test_elegir_sin_clic_otra_vez_vuelve_al_clic_normal():
    s = _sim()
    s.orden("elegir", "barra:sin_clic")
    assert s.maquina.modo_clic == "izq"
    s.orden("elegir", "barra:sin_clic")
    s.orden("elegir", "barra:doble")              # otro modo también lo termina
    assert s.maquina.modo_clic == "doble"


def test_los_gestos_de_clic_si_hacen_clic_y_el_modo_sigue():
    s = _sim()
    ir(s, -0.3)
    s.limpiar()
    boca(s, 0.8)
    assert s.clics() == [Clic(K.IZQ)]
    assert s.maquina.modo_clic == "ninguno"
    # las cejas (clic derecho) también
    s.limpiar()
    quieto(s, 1.0)
    quieto(s, 0.8, cejas=0.6)
    quieto(s, 0.5)
    assert s.clics() == [Clic(K.DER)]
    assert s.maquina.modo_clic == "ninguno"
    verificar_invariantes(s.salida)


def test_pausar_reanudar_y_cambiar_opciones_conservan_sin_clic():
    s = _sim(**{"barra.modo_fijo": False})
    s.orden("alternar_pausa")
    assert s.maquina.estado == K.PAUSA
    s.orden("alternar_pausa")
    assert s.maquina.estado == K.ACTIVO and s.maquina.modo_clic == "ninguno"
    s.orden("nueva_config", s.cfg)
    assert s.maquina.modo_clic == "ninguno"
    # modo_fijo no lo afecta
    s2 = _sim(**{"barra.modo_fijo": True})
    boca(s2, 0.8)
    assert s2.maquina.modo_clic == "ninguno"


def test_sin_clic_lo_dicen_el_aviso_el_subtitulo_y_el_indicador():
    s = Sim()
    quieto(s, 0.3)
    s.limpiar()
    s.orden("elegir", "barra:sin_clic")
    assert "sin_clic" in s.avisos()
    assert T.texto_aviso(type("A", (), {"clave": "sin_clic"})()) == T.t("aviso_sin_clic")
    quieto(s, 0.2)
    assert T.subtitulo(s.vista) == T.t("sub_ACTIVO_ninguno")
    assert "quedarse quieto no hace clic" in T.subtitulo(s.vista)


def test_sin_clic_en_el_arrastre_lo_termina_sin_dejar_el_boton_abajo():
    s = Sim()
    quieto(s, 0.3)
    s.orden("elegir", "barra:arrastrar")
    assert s.maquina.submodo == K.ARRASTRE_INICIO
    s.orden("elegir", "barra:sin_clic")
    assert s.maquina.submodo == K.NORMAL and s.maquina.modo_clic == "ninguno"
    ir(s, 0.4)
    quieto(s, 2.0)
    assert s.clics() == [] and s.salida.botones() == set() or s.salida.todo_suelto()
    verificar_invariantes(s.salida)


# ------------------------------------------------------------------ pestaña de la barra minimizada
def _pestana(s):
    cx, cy = s.monitor.centro
    rect = (int(cx) + 180, int(cy) - 80, int(cx) + 360, int(cy) + 80)
    s.maquina.poner_objetivos([Objetivo(ID_BARRA_MOSTRAR, rect, tiempo_s=0.6)])
    return rect


def test_la_pestana_se_elige_quieto_0_6_s_en_activo():
    s = Sim()
    quieto(s, 0.3)
    _pestana(s)
    ir(s, 0.38)
    s.limpiar()
    quieto(s, 0.45)
    assert ID_BARRA_MOSTRAR not in s.elegidos()
    quieto(s, 0.4)
    assert s.elegidos().count(ID_BARRA_MOSTRAR) == 1
    assert s.clics() == []


@pytest.mark.parametrize("motivo", ["atajo", "gesto", "cuidador", "botón Pausa"])
def test_la_pestana_se_elige_tambien_en_pausa_y_no_reanuda(motivo):
    s = Sim()
    quieto(s, 0.3)
    s.orden("pausar", motivo)
    assert s.maquina.estado == K.PAUSA
    _pestana(s)
    ir(s, 0.38)
    quieto(s, 0.9)
    assert s.elegidos().count(ID_BARRA_MOSTRAR) == 1
    assert s.maquina.estado == K.PAUSA        # abrir la barra no reanuda
    assert s.clics() == []
    quieto(s, 3.0)                            # quieto encima: no se repite ni reanuda
    assert s.elegidos().count(ID_BARRA_MOSTRAR) == 1 and s.maquina.estado == K.PAUSA


def test_pasar_por_encima_de_la_pestana_sin_quedarse_quieto_no_la_abre():
    s = Sim()
    quieto(s, 0.3)
    _pestana(s)
    for _ in range(4):                     # va y vuelve cruzando la pestaña sin parar
        ir(s, 0.8, dur=0.5)
        ir(s, -0.2, dur=0.5)
    assert ID_BARRA_MOSTRAR not in s.elegidos()
    s.orden("alternar_pausa")
    for _ in range(4):
        ir(s, 0.8, dur=0.5)
        ir(s, -0.2, dur=0.5)
    assert ID_BARRA_MOSTRAR not in s.elegidos()


def test_en_pausa_la_minimizar_de_la_barra_no_se_elige():
    s = Sim()
    quieto(s, 0.3)
    s.orden("alternar_pausa")
    cx, cy = s.monitor.centro
    s.maquina.poner_objetivos([Objetivo("barra:minimizar", (int(cx) + 180, int(cy) - 80, int(cx) + 360, int(cy) + 80))])
    ir(s, 0.38)
    quieto(s, 3.0)
    assert "barra:minimizar" not in s.elegidos()
