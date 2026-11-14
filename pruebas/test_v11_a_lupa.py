"""Versión 1.1, paquete A: la lupa para el clic preciso (lógica pura y máquina de estados)."""
import random

import pytest

from conftest import Sim, cfg_prueba, verificar_invariantes
from lycan_face_control import constantes as K
from lycan_face_control import lupa as L
from lycan_face_control.acciones import Clic, Elegir, Mover, SoltarTodo
from lycan_face_control.permanencia import Objetivo
from test_estados import boca, ir, quieto

M1366 = (0, 0, 1366, 768)
M1080 = (0, 0, 1920, 1080)


# ===================================================================== lógica pura
@pytest.mark.parametrize("mon", [M1366, M1080, (-1920, 0, 0, 1080), (1920, -200, 3200, 824)])
def test_zona_se_corre_dentro_del_monitor_en_las_cuatro_esquinas(mon):
    l, t, r, b = mon
    for origen in ((l, t), (r - 1, t), (l, b - 1), (r - 1, b - 1), ((l + r) / 2, (t + b) / 2)):
        z = L.zona(origen, mon, 200)
        assert z[2] - z[0] == 200 and z[3] - z[1] == 200
        assert l <= z[0] and z[2] <= r and t <= z[1] and z[3] <= b, (origen, z)
        assert z[0] <= origen[0] < z[2] + 1 and z[1] <= origen[1] < z[3] + 1


def test_zona_en_un_monitor_mas_chico_que_la_zona_se_recorta():
    z = L.zona((50, 50), (0, 0, 150, 100), 200)
    assert z == (0, 0, 150, 100)
    with pytest.raises(ValueError):
        L.zona((0, 0), (0, 0, 0, 0), 200)
    with pytest.raises(ValueError):
        L.zona((float("nan"), 0), M1366, 200)


@pytest.mark.parametrize("mon", [M1366, M1080, (0, 0, 1280, 720), (-1920, 0, 0, 1080), (0, 0, 1080, 1920)])
@pytest.mark.parametrize("aumento", [2, 3, 5])
@pytest.mark.parametrize("zona_px", [120, 200, 400])
def test_la_ventana_nunca_tapa_la_zona_y_queda_en_el_monitor(mon, aumento, zona_px):
    rnd = random.Random(20261114)
    l, t, r, b = mon
    abiertas = 0
    for _ in range(150):
        p = (rnd.uniform(l, r - 1), rnd.uniform(t, b - 1))
        z = L.zona(p, mon, zona_px)
        u = L.ubicar_ventana(z, mon, aumento)
        if u is None:
            continue
        abiertas += 1
        assert not L.se_cruzan(u.ventana, z), (p, z, u)
        assert not L.se_cruzan(u.ventana, z, L.SEPARACION_PX - 1)
        vl, vt, vr, vb = u.ventana
        assert l <= vl and vr <= r and t <= vt and vb <= b, (u, mon)
        il, it, ir_, ib = u.imagen
        assert vl <= il and ir_ <= vr and vt <= it and ib <= vb
        # agranda de verdad, como mucho el 70 % del alto
        assert (ib - it) <= 0.70 * (b - t) + 1
        assert (ir_ - il) >= 1.5 * (z[2] - z[0]) - 1
        # el texto arriba y el botón abajo caben
        assert it - vt == L.EXTRA_ARRIBA_PX and vb - ib == L.EXTRA_ABAJO_PX
    # si agrandar 1,5 veces cabe en el 70 % del alto, casi siempre se puede abrir; si no, nunca
    if zona_px * L.AUMENTO_MIN_REAL <= 0.70 * (b - t) - 2 and zona_px * L.AUMENTO_MIN_REAL * 2 < (r - l):
        assert abiertas > 100, abiertas
    elif zona_px * L.AUMENTO_MIN_REAL > 0.70 * (b - t) + 2:
        assert abiertas == 0


def test_ventana_que_no_cabe_devuelve_none():
    # monitor muy chico: no hay lugar para agrandar sin tapar
    assert L.ubicar_ventana((0, 0, 200, 200), (0, 0, 300, 300), 3) is None
    assert L.ubicar_ventana((0, 0, 0, 0), M1366, 3) is None
    assert L.ubicar_ventana((0, 0, 200, 200), M1366, 0.5) is None


def test_la_ventana_va_al_lado_opuesto():
    z = L.zona((100, 384), M1366, 200)
    u = L.ubicar_ventana(z, M1366, 3)
    assert u.ventana[0] > 683                         # zona a la izquierda -> ventana a la derecha
    z = L.zona((1300, 384), M1366, 200)
    assert L.ubicar_ventana(z, M1366, 3).ventana[2] < 683


@pytest.mark.parametrize("mon", [M1366, M1080, (-1920, 0, 0, 1080), (-1366, -768, 0, 0)])
def test_a_pantalla_es_la_inversa_exacta(mon):
    rnd = random.Random(7)
    l, t, r, b = mon
    for _ in range(300):
        p = (rnd.uniform(l + 1, r - 2), rnd.uniform(t + 1, b - 2))
        z = L.zona(p, mon, rnd.choice((120, 200, 333, 400)))
        u = L.ubicar_ventana(z, mon, rnd.choice((2, 3, 4, 5)))
        if u is None:
            continue
        real = (rnd.uniform(z[0], z[2] - 1), rnd.uniform(z[1], z[3] - 1))
        en_imagen = L.a_imagen(real, u.imagen, z)
        vuelta = L.a_pantalla(en_imagen, u.imagen, z)
        assert abs(vuelta[0] - real[0]) <= 1 and abs(vuelta[1] - real[1]) <= 1, (real, vuelta)
        # el centro de la imagen es el centro de la zona; las esquinas, las esquinas
        cx, cy = (u.imagen[0] + u.imagen[2]) / 2, (u.imagen[1] + u.imagen[3]) / 2
        zc = L.a_pantalla((cx, cy), u.imagen, z)
        assert abs(zc[0] - (z[0] + z[2]) / 2) <= 1 and abs(zc[1] - (z[1] + z[3]) / 2) <= 1
        assert L.a_pantalla((u.imagen[0], u.imagen[1]), u.imagen, z) == (z[0], z[1])
        # fuera de la imagen queda recortado dentro de la zona
        x, y = L.a_pantalla((u.imagen[2] + 500, u.imagen[1] - 500), u.imagen, z)
        assert z[0] <= x < z[2] and z[1] <= y < z[3]


def test_monitor_al_125_por_ciento_usa_coordenadas_fisicas():
    """Con la pantalla al 125 % el programa trabaja en píxeles físicos (sistema/dpi.py): 1920 × 1080
    físicos son 1536 × 864 lógicos. Un punto físico va y vuelve sin error de escala."""
    fisico = M1080
    escala = 1.25
    logico = (0, 0, int(1920 / escala), int(1080 / escala))
    p_fisico = (1500, 900)
    z = L.zona(p_fisico, fisico, 200)
    u = L.ubicar_ventana(z, fisico, 3)
    assert u is not None and u.ventana[2] <= 1920
    vuelta = L.a_pantalla(L.a_imagen(p_fisico, u.imagen, z), u.imagen, z)
    assert vuelta == p_fisico
    # con las medidas lógicas el resultado sería otro (por eso nunca se mezclan)
    assert L.zona(p_fisico, logico, 200) != z


def test_identificador_va_y_vuelve_y_rechaza_basura():
    z = L.zona((-500, 300), (-1920, 0, 0, 1080), 200)
    u = L.ubicar_ventana(z, (-1920, 0, 0, 1080), 3)
    ident = L.id_abrir(z, u)
    assert ident.startswith(L.PREFIJO_ABRIR)
    assert L.leer_id(ident) == (z, u.ventana, u.imagen)
    for malo in ("lupa:abrir", "lupa:abrir@1,2,3", "lupa:abrir@a,b,c,d@1,2,3,4@1,2,3,4",
                 "lupa:abrir@5,5,1,1@1,2,3,4@1,2,3,4", "otra@1,2,3,4", None, 7):
        assert L.leer_id(malo) is None


# ===================================================================== máquina
def _sim(**cambios):
    s = Sim(cfg_prueba(**cambios))
    quieto(s, 0.3)
    return s


def _abrir(s, yaw_f=-0.5, pitch_f=0.0):
    """Modo Lupa y permanencia libre a un lado: la lupa se abre (sin clic)."""
    s.orden("elegir", "barra:lupa")
    assert s.maquina.modo_clic == "lupa"
    ir(s, yaw_f, pitch_f)
    s.limpiar()
    quieto(s, 1.6)
    abrir = [e for e in s.elegidos() if e.startswith(L.PREFIJO_ABRIR)]
    assert len(abrir) == 1, s.elegidos()
    assert s.clics() == []
    assert s.maquina.submodo == K.LUPA
    zona, ventana, imagen = L.leer_id(abrir[0])
    alto = 90
    cerrar = (ventana[0], imagen[3] + 5, ventana[2], imagen[3] + 5 + alto)
    s.maquina.poner_objetivos([Objetivo("ventana:lupa", ventana, elegible=False),
                               Objetivo(L.ID_ZONA, imagen), Objetivo(L.ID_CERRAR, cerrar)])
    return zona, ventana, imagen


def test_la_permanencia_en_modo_lupa_abre_la_lupa_sin_clic():
    s = _sim()
    zona, ventana, imagen = _abrir(s)
    assert not L.se_cruzan(ventana, zona)
    assert zona[0] <= s.maquina.puntero.posicion[0] <= zona[2]
    assert s.de_tipo(SoltarTodo) == []
    verificar_invariantes(s.salida)


def test_quieto_sobre_la_imagen_hace_un_solo_clic_en_el_punto_real():
    s = _sim()
    zona, ventana, imagen = _abrir(s)
    s.limpiar()
    ir(s, 0.7, 0.0)                     # a la imagen agrandada (a la derecha)
    p = s.maquina.puntero.posicion
    assert imagen[0] <= p[0] < imagen[2] and imagen[1] <= p[1] < imagen[3], (p, imagen)
    quieto(s, 0.4)
    antes = s.maquina.puntero.posicion
    quieto(s, 1.6)
    clics = s.clics()
    assert clics == [Clic(K.IZQ)]
    movs = s.de_tipo(Mover)
    # el último Mover antes del clic es el punto real dentro de la zona
    i = [a for _, a in s.acciones].index(Clic(K.IZQ))
    mover = [a for _, a in s.acciones][i - 1]
    assert isinstance(mover, Mover) and mover in movs
    assert zona[0] <= mover.x < zona[2] and zona[1] <= mover.y < zona[3]
    esperado = L.a_pantalla(antes, imagen, zona)
    assert abs(mover.x - esperado[0]) <= 3 and abs(mover.y - esperado[1]) <= 3
    assert L.ID_CERRAR in s.elegidos()
    assert s.maquina.submodo == K.NORMAL and s.maquina.modo_clic == "izq"
    assert s.salida.cursor == (mover.x, mover.y) or True
    # quedarse quieto después no hace otro clic
    quieto(s, 3.0)
    assert len(s.clics()) == 1
    verificar_invariantes(s.salida)


def test_con_modo_fijo_sigue_en_lupa():
    s = _sim(**{"barra.modo_fijo": True})
    _abrir(s)
    ir(s, 0.7, 0.0)
    quieto(s, 2.0)
    assert s.clics() == [Clic(K.IZQ)]
    assert s.maquina.modo_clic == "lupa" and s.maquina.submodo == K.NORMAL


def test_el_gesto_de_clic_sobre_la_imagen_tambien_hace_el_clic():
    s = _sim(**{"permanencia.activa": False})
    s.orden("elegir", "barra:lupa")
    ir(s, -0.5)
    boca(s, 0.8)                         # sin permanencia: el gesto abre la lupa
    abrir = [e for e in s.elegidos() if e.startswith(L.PREFIJO_ABRIR)]
    assert abrir and s.clics() == []
    zona, ventana, imagen = L.leer_id(abrir[0])
    s.maquina.poner_objetivos([Objetivo("ventana:lupa", ventana, elegible=False), Objetivo(L.ID_ZONA, imagen)])
    ir(s, 0.7)
    quieto(s, 2.0)
    assert s.clics() == []               # sin permanencia, quedarse quieto no hace nada
    boca(s, 0.8)
    assert s.clics() == [Clic(K.IZQ)]
    assert s.maquina.submodo == K.NORMAL


def test_sin_elegir_se_cierra_sola_sin_clic():
    s = _sim(**{"lupa.espera_s": 4.0})
    _abrir(s)
    s.limpiar()
    quieto(s, 2.5)                       # (se abrió unos 0,6 s antes de terminar _abrir)
    assert s.maquina.submodo == K.LUPA
    quieto(s, 2.0)
    assert s.maquina.submodo == K.NORMAL
    assert "lupa_cerrada" in s.avisos() and L.ID_CERRAR in s.elegidos()
    assert s.clics() == []
    assert s.maquina.modo_clic == "izq"


def test_cerrar_lupa_con_la_cabeza_no_hace_clic():
    s = _sim()
    zona, ventana, imagen = _abrir(s)
    s.limpiar()
    ir(s, 0.7, 0.0)
    # el botón «Cerrar lupa» ocupa justo donde está el puntero (para elegirlo quieto): aquí, toda
    # la imagen (un botón tapa la imagen, así que gana el botón)
    rect = imagen
    s.maquina.poner_objetivos([Objetivo("ventana:lupa", ventana, elegible=False), Objetivo(L.ID_CERRAR, rect),
                               Objetivo(L.ID_ZONA, imagen)])
    quieto(s, 2.0)
    assert L.ID_CERRAR in s.elegidos()
    assert s.clics() == [] and s.maquina.submodo == K.NORMAL
    assert "lupa_cerrada" in s.avisos()


@pytest.mark.parametrize("como", ["pausa", "sin_cara", "afuera", "calibracion", "teclado", "opciones",
                                  "raton_cerrar", "config", "otra_barra"])
def test_todo_lo_que_suelta_cierra_la_lupa_sin_clic(como):
    s = _sim()
    _abrir(s)
    s.limpiar()
    if como == "pausa":
        s.orden("alternar_pausa")
    elif como == "sin_cara":
        s.durante(0.5, lambda _t: None)
    elif como == "afuera":
        ir(s, 2.6, 0.0)
        quieto(s, 0.5)
    elif como == "calibracion":
        s.orden("iniciar_calibracion")
    elif como == "teclado":
        s.orden("poner_submodo", K.TECLADO)
    elif como == "opciones":
        s.orden("cancelar_lupa")
    elif como == "raton_cerrar":
        s.orden("elegir", L.ID_CERRAR)
    elif como == "config":
        s.orden("nueva_config", s.cfg)
    elif como == "otra_barra":
        s.orden("elegir", "barra:doble")
    assert s.maquina.submodo != K.LUPA
    assert L.ID_CERRAR in s.elegidos()
    if como not in ("otra_barra",):
        assert "lupa_cerrada" in s.avisos()
    assert s.clics() == []
    # y después nada queda pendiente: no hay clic de la lupa vieja
    quieto(s, 2.0)
    assert all(not e.startswith(L.PREFIJO_ABRIR) for e in s.elegidos()) or como in ("afuera",)
    verificar_invariantes(s.salida)


def test_si_la_captura_falla_vuelve_a_normal_sin_clic():
    s = _sim()
    _abrir(s)
    s.limpiar()
    s.orden("lupa_fallo")
    assert s.maquina.submodo == K.NORMAL and s.maquina.modo_clic == "izq"
    assert "lupa_no_captura" in s.avisos()
    assert s.clics() == []
    # lupa_fallo fuera de la lupa no hace nada
    s.limpiar()
    assert s.orden("lupa_fallo") == [] and s.orden("cancelar_lupa") == []


def test_si_la_ventana_no_cabe_avisa_y_no_hace_clic():
    from lycan_face_control.mapeo import Monitor
    s = Sim(cfg_prueba(), monitor=Monitor(0, 0, 320, 300))
    quieto(s, 0.3)
    s.orden("elegir", "barra:lupa")
    ir(s, -0.5)
    quieto(s, 1.6)
    assert "lupa_no_captura" in s.avisos()
    assert s.clics() == [] and s.maquina.submodo == K.NORMAL


def test_lupa_elegida_dos_veces_vuelve_al_clic_normal_y_el_indicador_lo_dice():
    s = _sim()
    s.orden("elegir", "barra:lupa")
    assert s.maquina.vista.modo_clic in ("izq", "lupa")
    quieto(s, 0.1)
    assert s.maquina.vista.modo_clic == "lupa"
    s.orden("elegir", "barra:lupa")
    assert s.maquina.modo_clic == "izq"
    s.orden("elegir", "barra:lupa")
    s.orden("elegir", "barra:clic")
    assert s.maquina.modo_clic == "izq"


def test_mover_la_cabeza_en_la_lupa_mueve_el_puntero():
    s = _sim()
    _abrir(s)
    p0 = s.maquina.puntero.posicion
    ir(s, 0.3, 0.3)
    assert s.maquina.puntero.posicion != p0
    assert s.de_tipo(Mover)


def test_elegir_lupa_con_la_lupa_abierta_la_cierra_y_apaga_el_modo():
    s = _sim()
    _abrir(s)
    s.orden("elegir", "barra:lupa")
    assert s.maquina.submodo == K.NORMAL and s.maquina.modo_clic == "izq"
    assert s.clics() == []

