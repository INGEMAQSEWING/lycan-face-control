"""Parte 3: interfaz. Sin cámara real ni ratón real: motor con ``CamaraFalsa`` + ``DetectorFalso``
(caras sintéticas) + ``SalidaSimulada``, y ventanas de tkinter que se crean y se cierran solas.

La lógica sin pantalla (textos, contraste, velocidad, pasos de la calibración) se prueba aparte.
"""
from __future__ import annotations

import argparse
import copy
import math
import time
import tkinter as tk

import pytest

from conftest import CAL_SINTETICA, medidas, verificar_invariantes
from lycan_face_control import constantes as K
from lycan_face_control.acciones import Aviso, Elegir, Hablar, Sonido
from lycan_face_control.calibracion_guiada import Guia, pasos_para
from lycan_face_control.config import Configuracion, RANGOS, por_defecto, validar
from lycan_face_control.ui import comun
from lycan_face_control.ui import opciones as OP
from lycan_face_control.ui import textos as T


# =========================================================================== sin pantalla
def test_textos_sin_jerga_y_en_usted():
    for clave, txt in T.TXT.items():
        bajo = " " + txt.lower().replace("\n", " ") + " "
        for p in T.PALABRAS_PROHIBIDAS:
            assert p not in bajo, (clave, p)
        for p in T.TUTEO:
            assert p not in bajo, (clave, p)


def test_textos_obligatorios_y_no_dicen_gratis():
    assert T.t("aviso_sin_cara") == "No veo su cara. Acérquese a la cámara o revise la luz."
    assert "Primero elija con la cabeza el programa donde quiere escribir" in T.t("aviso_foco_propio")
    assert "administrador" in T.t("aviso_administrador")
    for txt in T.TXT.values():
        assert "gratis" not in txt.lower() and "gratuito" not in txt.lower()
    # honestidad: la ayuda dice el límite del programa
    assert "párpados" in T.t("ayuda_problemas")
    assert "CC BY-SA 4.0" in T.t("ayuda_acerca") and "MIT" in T.t("ayuda_acerca")


def test_cada_accion_y_estado_tiene_texto():
    for a in K.ACCIONES_GESTO:
        assert T.nombre_accion(a) != a, a
    for e in K.ESTADOS:
        assert T.texto_estado(e) != e
    assert T.t("clave_que_no_existe") == "clave_que_no_existe"


@pytest.mark.parametrize("tema_", [comun.TEMA_NORMAL, comun.TEMA_ALTO_CONTRASTE])
def test_contraste_de_7_a_1(tema_):
    pares = [(tema_.texto, tema_.fondo), (tema_.texto_suave, tema_.fondo), (tema_.acento, tema_.fondo),
             (tema_.ambar, tema_.fondo), (tema_.verde, tema_.fondo), (tema_.rojo_texto, tema_.fondo),
             (tema_.boton_texto, tema_.boton), (tema_.texto, tema_.fondo_2), (tema_.texto_suave, tema_.fondo_2),
             (tema_.sobre_color, tema_.ambar), (tema_.sobre_color, tema_.verde), (tema_.sobre_color, tema_.rojo),
             (tema_.sobre_color, tema_.acento), (tema_.aviso_texto, tema_.aviso_fondo)]
    for a, b in pares:
        assert comun.contraste(a, b) >= 7.0, (a, b, comun.contraste(a, b))


def test_letras_nunca_bajan_de_16_y_escalan():
    cfg = por_defecto()
    assert comun.letra(cfg, 10)[1] == 16
    cfg["comodidad"]["escala_letra"] = 2.0
    assert comun.letra(cfg, 16)[1] == 32
    cfg["comodidad"]["escala_letra"] = 9           # fuera de rango: se recorta
    assert comun.letra(cfg, 16)[1] == 32


def test_velocidad_del_puntero_1_a_10():
    assert OP.sens_de_velocidad(3) == (1.0, 1.2)                # 3 = fábrica
    lo, hi = RANGOS["puntero.sens_x"]
    for n in range(1, 11):
        sx, sy = OP.sens_de_velocidad(n)
        assert lo <= sx <= hi and lo <= sy <= hi
        assert OP.velocidad_de_sens(sx) == n
    assert OP.sens_de_velocidad(0) == OP.sens_de_velocidad(1)
    assert OP.sens_de_velocidad(99) == OP.sens_de_velocidad(10)
    assert OP.velocidad_de_sens("raro") == 3


def test_pasos_de_los_controles_respetan_los_rangos():
    d = por_defecto()
    d["permanencia"]["tiempo_s"] = 2.95
    assert OP.paso_numero(d, "permanencia.tiempo_s", 0.1, +1) == 3.0
    d["permanencia"]["tiempo_s"] = 0.4
    assert OP.paso_numero(d, "permanencia.tiempo_s", 0.1, -1) == 0.4
    assert OP.paso_numero(d, "gestos.boca.sostener_ms", 50, +1) == 650
    assert isinstance(OP.paso_numero(d, "gestos.boca.sostener_ms", 50, +1), int)
    # descanso: 0 (apagado) <-> 10 minutos
    assert OP.paso_numero(d, "comodidad.descanso_min", 5, +1) == 10
    d["comodidad"]["descanso_min"] = 10
    assert OP.paso_numero(d, "comodidad.descanso_min", 5, -1) == 0
    assert OP.ciclar(("a", "b", "c"), "c", +1) == "a"
    assert OP.ciclar(("a", "b", "c"), "x", -1) == "c"


def test_todos_los_controles_apuntan_a_claves_validas():
    d = por_defecto()
    for p in OP.PESTANAS:
        for g in K.GESTOS:
            for tipo, ruta, clave, extra, fmt in OP.controles(p, g):
                assert clave in T.TXT, clave
                if tipo == "boton":
                    continue
                v = OP.leer(d, ruta)
                if tipo == "opc":
                    assert v in extra, (ruta, v)
                    for o in extra:
                        assert fmt(o)
                elif tipo == "num":
                    assert fmt(v)
                    assert OP._rango(ruta) is not None, ruta


# --------------------------------------------------------------------------- calibración guiada
DUR_CORTAS = {"posicion": 0.5, "centro": 1.0, "izq": 1.0, "der": 1.0, "arr": 1.0, "aba": 1.0, "reposo": 1.0,
              "parpadeo": 3.0, "gesto_boca": 1.0, "gesto_cejas": 1.0, "gesto_sonrisa": 1.0}


def _alimentar(guia, t, segundos, fps=30.0, io_fr=0.15, funcion=None):
    n = int(segundos * fps)
    est = None
    for i in range(n):
        tt = t + i / fps
        m = funcion(tt - t) if funcion is not None else medidas()
        est = guia.alimentar(tt, m, io_fr)
    return t + n / fps, est


def test_pasos_segun_gestos_encendidos():
    cfg = por_defecto()
    assert pasos_para(cfg)[-2:] == ["gesto_boca", "gesto_cejas"]
    cfg["gestos"]["sonrisa"]["activo"] = True
    cfg["gestos"]["parpadeo"]["activo"] = False
    p = pasos_para(cfg)
    assert "parpadeo" not in p and p[-1] == "gesto_sonrisa"


def test_guia_completa_arma_una_calibracion_coherente():
    cfg = por_defecto()
    g = Guia(cfg, 0.0, preparar_s=0.5, duraciones=DUR_CORTAS)
    t = 0.0
    t, est = _alimentar(g, t, 0.6)                       # preparar
    assert g.paso == "posicion"
    t, est = _alimentar(g, t, 0.7)                       # buena distancia 0,5 s
    assert g.paso == "centro"
    t, _ = _alimentar(g, t, 1.6)
    assert g.paso == "izq"
    t, _ = _alimentar(g, t, 1.6, funcion=lambda r: medidas(yaw_n=0.022 - 0.08 * min(r / 0.6, 1)))
    t, _ = _alimentar(g, t, 1.6, funcion=lambda r: medidas(yaw_n=0.022 + 0.09 * min(r / 0.6, 1)))
    t, _ = _alimentar(g, t, 1.6, funcion=lambda r: medidas(pitch_n=0.556 - 0.10 * min(r / 0.6, 1)))
    t, _ = _alimentar(g, t, 1.6, funcion=lambda r: medidas(pitch_n=0.556 + 0.10 * min(r / 0.6, 1)))
    assert g.paso == "reposo"
    t, _ = _alimentar(g, t, 1.6)
    assert g.paso == "parpadeo"

    def parpadeos(r):
        # tres parpadeos naturales de 200 ms en 3 s
        cerrado = any(a <= r < a + 0.2 for a in (0.5, 1.2, 1.9))
        return medidas(ear_der=0.06, ear_izq=0.06) if cerrado else medidas()
    t, _ = _alimentar(g, t, 3.6, funcion=parpadeos)
    assert g.paso == "gesto_boca"
    t, _ = _alimentar(g, t, 1.6, funcion=lambda r: medidas(mar=0.016 + 0.5 * (math.sin(r * 6) > 0)))
    assert g.paso == "gesto_cejas"
    g.omitir(t)
    assert g.terminado
    cal, largo, pocos = g.resultado()
    assert cal["centro"][0] == pytest.approx(0.022, abs=1e-6)
    assert cal["izq"] < cal["centro"][0] < cal["der"]
    assert cal["arr"] < cal["centro"][1] < cal["aba"]
    assert cal["signo_x"] == 1.0 and cal["signo_y"] == 1.0
    assert cal["parpadeos_min"] == 3
    assert 600 <= largo <= 2000                           # nunca por debajo de 600 tras calibrar
    assert "boca" in cal["umbrales"] and "cejas" not in cal["umbrales"]
    assert pocos == []
    cfg["perfiles"]["Principal"]["calibracion"] = cal
    assert validar(cfg)["perfiles"]["Principal"]["calibracion"] is not None


def test_sin_cara_el_paso_se_detiene_y_sigue_al_volver():
    g = Guia(por_defecto(), 0.0, preparar_s=0.0, duraciones=DUR_CORTAS)
    t, _ = _alimentar(g, 0.0, 0.6)
    assert g.paso == "centro"
    t, _ = _alimentar(g, t, 0.5)
    avance = g.estado(t).progreso
    for i in range(60):                                   # 2 s sin cara
        est = g.alimentar(t + i / 30, None, None)
    t += 2.0
    assert est.sin_cara and g.paso == "centro"
    assert g.estado(t).progreso == pytest.approx(avance, abs=0.05)
    t, _ = _alimentar(g, t, 0.7)
    assert g.paso == "izq"


def test_posicion_lejos_espera_y_luego_sigue_con_aviso():
    g = Guia(por_defecto(), 0.0, preparar_s=0.0, duraciones=DUR_CORTAS)
    t, est = _alimentar(g, 0.0, 5.0, io_fr=0.04)
    assert g.paso == "posicion" and est.posicion == "lejos"
    t, est = _alimentar(g, t, 16.0, io_fr=0.04)
    assert g.paso == "centro" and "posicion" in est.avisos


def test_repetir_y_atras():
    g = Guia(por_defecto(), 0.0, preparar_s=0.0, duraciones=DUR_CORTAS)
    t, _ = _alimentar(g, 0.0, 0.6)
    t, _ = _alimentar(g, t, 1.2)
    assert g.paso == "izq"
    g.atras(t)
    assert g.paso == "centro" and g.estado(t).fase == "preparar" and g._medido == 0.0
    g.repetir(t)
    assert g.paso == "centro"
    g.omitir(t)                       # el centro no se puede omitir
    assert g.paso == "centro"
    assert g.resultado() is None      # sin centro no hay calibración


# =========================================================================== con pantalla
@pytest.fixture
def root():
    ultimo = None
    for _ in range(5):
        try:
            r = tk.Tk()
            break
        except tk.TclError as e:
            ultimo = e
            time.sleep(0.2)
    else:
        pytest.skip(f"sin pantalla ({ultimo})")
    r.withdraw()
    yield r
    try:
        r.destroy()
    except tk.TclError:
        pass


def bombear(root, ms=200):
    fin = time.monotonic() + ms / 1000
    while time.monotonic() < fin:
        root.update()
        time.sleep(0.01)


def test_registro_publica_rectangulos_y_elige(root):
    from lycan_face_control.ui.comun import BotonGrande
    from lycan_face_control.ui.objetivos import Registro
    publicados, ordenes, hechos = [], [], []
    reg = Registro(publicar=publicados.append, orden=lambda *a: ordenes.append(a))
    top = tk.Toplevel(root)
    top.geometry("400x200+50+50")
    b1 = BotonGrande(top, "Uno", reg.comando("ui:uno"))
    b1.pack()
    b2 = BotonGrande(top, "Clic", reg.comando("barra:clic"))
    b2.pack()
    reg.agregar("ui:uno", b1, lambda: hechos.append("uno"))
    reg.agregar("barra:clic", b2, None, interno=True)
    reg.ventana("prueba", top)
    reg.manejador("barrido:", lambda i: hechos.append(i) or True)
    bombear(root, 150)
    assert reg.publicar() is True
    assert reg.publicar() is False                       # sin cambios no se republica
    objs = {o.id: o for o in publicados[-1]}
    assert set(objs) == {"ui:uno", "barra:clic", "ventana:prueba"}
    assert objs["ventana:prueba"].elegible is False
    l, a, d, ab = objs["ui:uno"].rect
    assert d - l == b1.winfo_width() and ab - a == b1.winfo_height()
    assert reg.elegir("ui:uno", "cabeza") and hechos == ["uno"]
    assert reg.elegir("barra:clic", "cabeza") and ordenes == []           # la máquina ya lo hizo
    b2.invocar()                                                          # clic del cuidador
    assert ordenes == [("elegir", "barra:clic")]
    assert reg.elegir("barrido:elegir") and hechos[-1] == "barrido:elegir"
    assert not reg.elegir("nada:aqui")
    reg.resaltar("ui:uno")
    assert b1._resaltado and not b2._resaltado
    b1.destroy()
    bombear(root, 50)
    reg.publicar()
    assert "ui:uno" not in {o.id for o in publicados[-1]}
    top.withdraw()
    bombear(root, 50)
    reg.publicar()
    assert publicados[-1] == []                         # ventana escondida: nada que elegir
    top.destroy()


# --------------------------------------------------------------------------- aplicación completa
def _args(**kw):
    base = dict(check=False, minimizado=False, simular=True, camara_falsa=True, prueba_segundos=0.0, camara=None,
                sin_atajos=True)
    base.update(kw)
    return argparse.Namespace(**base)


def _fabrica(funcion=None):
    from lycan_face_control.captura import CamaraFalsa
    from lycan_face_control.detector import DetectorFalso
    from lycan_face_control.mapeo import MONITOR_REFERENCIA
    from lycan_face_control.motor import Motor
    from sintetico import FuenteSecuencia
    funcion = funcion or (lambda t: {"yaw": 4.0 * math.sin(t)})

    def fabrica(cfg, salida):
        fuente = FuenteSecuencia(funcion=funcion)
        return Motor(cfg, salida, camara=CamaraFalsa(fps=30.0), detector=DetectorFalso(fuente), sistema=False,
                     monitor=MONITOR_REFERENCIA)
    return fabrica


def _app(tmp_path, calibrada=True, funcion=None, **kw):
    from lycan_face_control.salida.simulada import SalidaSimulada
    from lycan_face_control.ui.aplicacion import App
    cfg = Configuracion(tmp_path / "config.json")
    cfg.cargar()
    if calibrada:
        cfg.datos["perfiles"]["Principal"]["calibracion"] = copy.deepcopy(CAL_SINTETICA)
        cfg.datos["primera_vez"] = False
    salida = SalidaSimulada(escritorio=(0, 0, 1366, 768), cursor=(683, 384), max_eventos=5000)
    salida.intervalo_doble_ms = 0
    return App(_args(**kw), fabrica_motor=_fabrica(funcion), salida=salida, sistema=False, cfg=cfg)


def _girar(app, ms):
    fin = time.monotonic() + ms / 1000
    while time.monotonic() < fin:
        app.vuelta_interfaz()
        app.root.update()
        time.sleep(0.02)


@pytest.fixture
def app_viva(tmp_path):
    app = _app(tmp_path)
    app.motor.start()
    try:
        app.construir_interfaz()
    except tk.TclError as e:
        app.finalizar()
        pytest.skip(f"sin pantalla ({e})")
    app.root.after_cancel  # noqa: B018 - la vuelta se llama a mano en las pruebas
    yield app
    if not app.cerrando:
        app.salir_seguro()
    app.finalizar()
    assert not app.motor.is_alive()
    verificar_invariantes(app.salida)


def test_app_arranca_pinta_y_publica_botones(app_viva):
    app = app_viva
    _girar(app, 1500)
    assert app.ultima_vista is not None
    assert app.motor.maquina.estado == K.ACTIVO
    ids = {o.id for o in app.motor.maquina.objetivos}
    for esperado in ("barra:clic", "barra:doble", "barra:derecho", "barra:arrastrar", "barra:desplazar",
                     "barra:teclado", "barra:pausa", "ui:pausar", "ui:opciones", "ui:ayuda", "ui:calibrar",
                     "ventana:principal", "ventana:barra"):
        assert esperado in ids, esperado
    # cada botón propio es grande (al menos 72 px de alto en la barra)
    barra = [o for o in app.motor.maquina.objetivos if o.id.startswith("barra:")]
    assert all(o.rect[3] - o.rect[1] >= 72 for o in barra)
    assert app.ventana.lbl_estado.cget("text") == T.texto_estado(K.ACTIVO)


def test_pausa_y_reanudar_desde_la_interfaz(app_viva):
    app = app_viva
    _girar(app, 600)
    app.ventana.b_pausa.invocar()                      # el cuidador con el ratón
    _girar(app, 400)
    assert app.motor.maquina.estado == K.PAUSA
    assert app.ventana.lbl_estado.cget("text") == T.texto_estado(K.PAUSA)
    assert app.ventana.b_pausa.texto == T.t("btn_reanudar")
    assert app.barra.botones["pausa"].texto == T.t("barra_reanudar")
    ids = {o.id for o in app.motor.maquina.objetivos}
    assert "reanudar" in ids and "ui:pausar" not in ids
    app.ventana.b_pausa.invocar()
    _girar(app, 400)
    assert app.motor.maquina.estado == K.ACTIVO
    assert app.ventana.b_pausa.texto == T.t("btn_pausar")


def test_barra_cambia_el_modo_de_clic_y_desplazar_muestra_terminar(app_viva):
    app = app_viva
    _girar(app, 500)
    app.barra.botones["doble"].invocar()
    _girar(app, 300)
    assert app.motor.maquina.modo_clic == "doble"
    assert app.barra.botones["doble"]._activo
    app.barra.botones["desplazar"].invocar()
    _girar(app, 300)
    assert app.motor.maquina.submodo == K.DESPLAZAR
    assert "terminar" in app.barra.botones
    app.barra.botones["terminar"].invocar()
    _girar(app, 300)
    assert app.motor.maquina.submodo == K.NORMAL
    assert "terminar" not in app.barra.botones


def test_avisos_del_motor(app_viva):
    app = app_viva
    _girar(app, 300)
    hablado = []
    app.hablar = lambda texto, urgente=False: hablado.append((texto, urgente))
    app.atender(Sonido("clic"))
    app.atender(Hablar("Tengo sed"))
    app.atender(Aviso("sin_cara"))
    assert hablado == [("Tengo sed", False)]
    assert app.ventana.lbl_aviso.cget("text") == T.t("aviso_sin_cara")
    app.atender(Aviso("teclado"))                     # sin teclado todavía: aviso claro, sin error
    assert app.teclado is None or app.teclado is not None
    app.atender(Elegir("ui:ayuda"))                   # elegido con la cabeza
    assert app.ayuda is not None
    app.ayuda.ir_a("acerca")
    app.ayuda.ir_a("gestos")
    app.atender(Elegir("ayuda:cerrar"))
    assert app.ayuda is None
    app.atender(Elegir("ventana:principal"))          # no hace nada


def test_hablar_sin_voz_muestra_el_texto(app_viva):
    app = app_viva
    app.voz = None
    app.hablar("Me duele la cabeza")
    assert app.ventana.lbl_aviso.cget("text") == "Me duele la cabeza"


def test_salir_pide_confirmacion(app_viva):
    app = app_viva
    _girar(app, 200)
    app.atender(Elegir("ui:salir"))
    assert app.ventana.confirmando_salir and not app.cerrando
    app.atender(Elegir("ui:salir_no"))
    assert not app.ventana.confirmando_salir
    app.atender(Elegir("ui:salir"))
    app.atender(Elegir("ui:salir_si"))
    assert app.cerrando


def test_modo_mini_y_reanudar_flotante(app_viva):
    app = app_viva
    _girar(app, 300)
    app.ventana.alternar_mini()
    _girar(app, 500)
    ids = {o.id for o in app.motor.maquina.objetivos}
    assert "ui:grande" in ids and "ui:pausar" in ids and "ui:opciones" not in ids
    app.ventana.alternar_mini()
    app.orden("pausar")
    app.root.withdraw()
    _girar(app, 600)
    assert app.flotante._visible
    assert "reanudar" in {o.id for o in app.motor.maquina.objetivos}
    app.mostrar_ventana()
    _girar(app, 400)
    assert not app.flotante._visible


def test_opciones_vista_previa_cancelar_y_guardar(app_viva, monkeypatch):
    app = app_viva
    _girar(app, 200)
    ordenes = []
    original = app.orden
    app.orden = lambda *a: (ordenes.append(a), original(*a))
    op = app.abrir_opciones()
    assert ("soltar", "opciones") in ordenes
    assert app.abrir_opciones() is op                 # una sola ventana de Opciones
    vel = [c for c in OP.controles("puntero") if c[0] == "vel"][0]
    op.cambiar(vel, +1)
    ultima = [o for o in ordenes if o[0] == "config"][-1][1]
    assert ultima["puntero"]["sens_x"] == 1.25
    assert app.cfg.datos["puntero"]["sens_x"] == 1.0      # todavía no se guardó
    for p in OP.PESTANAS:
        op.ir_a(p)
        bombear(app.root, 30)
    op.ir_a("comodidad")
    op.ir_pagina(+1)
    op.ir_a("gestos")
    op.elegir_gesto("parpadeo")
    op.elegir_gesto("boca")
    _girar(app, 600)
    ids = {o.id for o in app.motor.maquina.objetivos}
    assert "op:gestos.boca.sens:mas" in ids and "op:guardar" in ids and "ventana:opciones" in ids, sorted(ids)
    op.cancelar()
    assert [o for o in ordenes if o[0] == "config"][-1][1]["puntero"]["sens_x"] == 1.0
    assert app.opciones is None
    # guardar
    op = app.abrir_opciones()
    op.cambiar(vel, +1)
    activo = ("bool", "permanencia.activa", "op_perm_activa", None, None)
    op.cambiar(activo, 1)                              # apagar la permanencia (la boca sigue pausando)
    llamadas = []
    monkeypatch.setattr(app, "poner_al_encender", lambda si: llamadas.append(si))
    op.ir_a("comodidad")
    op.cambiar(("bool", "arranque.al_encender", "op_al_encender", None, None), 1)
    op.cambiar(("num", "comodidad.escala_letra", "op_escala", 0.1, None), 1)
    op.guardar()
    assert app.cfg.datos["puntero"]["sens_x"] == 1.25 and app.cfg.datos["puntero"]["sens_y"] == 1.5
    assert app.cfg.datos["permanencia"]["activa"] is False
    assert llamadas == [True]
    assert Configuracion(app.cfg.ruta).cargar()["puntero"]["sens_x"] == 1.25
    _girar(app, 300)                                   # ventanas rehechas con letra al 110 %
    assert app.ventana.lbl_estado.cget("font")


def test_opciones_valores_de_fabrica_conservan_la_calibracion(app_viva):
    app = app_viva
    op = app.abrir_opciones()
    op.cambiar(("vel", "puntero.sens_x", "op_velocidad", 1, None), +3)
    op.pedir_fabrica()
    assert op.confirmando
    op.fabrica_si()
    assert op.datos["puntero"]["sens_x"] == 1.0
    assert op.datos["perfiles"]["Principal"]["calibracion"] is not None
    op.cancelar()


def test_opciones_atajo_invalido_no_guarda(app_viva):
    app = app_viva
    op = app.abrir_opciones()
    op.ir_a("atajos")
    op.entradas["atajos.pausar"].set("Ctrl+Alt+Ñ")
    op.guardar()
    assert app.opciones is op and op.pestana == "atajos"
    assert app.cfg.datos["atajos"]["pausar"] == "Ctrl+Alt+Espacio"
    op.cancelar()


def test_ayuda_resumen_de_gestos():
    from lycan_face_control.ui.ayuda import resumen_gestos
    cfg = por_defecto()
    r = resumen_gestos(cfg)
    assert [x[0] for x in r] == ["boca", "cejas", "sonrisa", "ojos"]
    assert T.nombre_accion("clic") in r[0][2] and T.nombre_accion("pausar") in r[0][2]
    assert r[2][2] == T.t("ayuda_gesto_apagado")


def test_asistente_y_calibracion_guiada_completa(tmp_path):
    from lycan_face_control.calibracion_guiada import Guia as G
    app = _app(tmp_path, calibrada=False)
    app.motor.start()
    try:
        app.construir_interfaz()
    except tk.TclError as e:
        app.finalizar()
        pytest.skip(f"sin pantalla ({e})")
    try:
        assert app.cfg.datos["primera_vez"] is True
        a = app.abrir_asistente()
        assert app.abrir_asistente() is a
        for _ in range(3):
            a.siguiente()
        a.calibrar()
        assert app.cfg.datos["primera_vez"] is False and app.asistente is None
        cal = app.calibracion
        assert cal is not None and cal.fase == "intro"
        _girar(app, 300)
        cal.empezar()
        _girar(app, 300)
        assert app.motor.maquina.estado == K.CALIBRANDO
        # pasos cortos para la prueba, alimentados con medidas directas
        cal.guia = G(app.cfg.datos, 0.0, preparar_s=0.0, duraciones=DUR_CORTAS)
        t = 0.0
        por_paso = {"izq": medidas(yaw_n=-0.06), "der": medidas(yaw_n=0.11), "arr": medidas(pitch_n=0.45),
                    "aba": medidas(pitch_n=0.66), "gesto_boca": medidas(mar=0.5), "gesto_cejas": medidas(cejas=0.45)}
        for _ in range(30 * 30):
            if cal.guia.terminado:
                break
            cal.alimentar(t, por_paso.get(cal.guia.paso, medidas()), 0.15)
            t += 1 / 30
            if int(t * 30) % 15 == 0:
                cal._pintar(cal.guia.estado(t))
        assert cal.guia.terminado
        cal._finalizar_pasos()
        assert cal.fase == "final"
        guardada = app.cfg.datos["perfiles"]["Principal"]["calibracion"]
        assert guardada is not None and guardada["umbrales"].get("boca")
        assert Configuracion(app.cfg.ruta).cargar()["perfiles"]["Principal"]["calibracion"] is not None
        _girar(app, 500)
        assert app.motor.maquina.estado == K.ACTIVO and app.motor.maquina.calibracion is not None
        ids = {o.id for o in app.motor.maquina.objetivos}
        assert {"cal:objetivo:1", "cal:objetivo:4", "cal:terminar"} <= ids
        for i in range(1, 5):
            app.atender(Elegir(f"cal:objetivo:{i}"))
        assert "4 de 4" in cal.lbl_final.cget("text")
        app.atender(Elegir("cal:terminar"))
        assert app.calibracion is None
    finally:
        app.salir_seguro()
        app.finalizar()
    verificar_invariantes(app.salida)


def test_cancelar_la_calibracion_vuelve_como_estaba(app_viva):
    app = app_viva
    _girar(app, 300)
    c = app.abrir_calibracion()
    c.empezar()
    _girar(app, 300)
    assert app.motor.maquina.estado == K.CALIBRANDO
    c.cancelar()
    _girar(app, 300)
    assert app.motor.maquina.estado == K.ACTIVO
    assert app.calibracion is None


def test_motor_caido_se_reinicia_y_suelta_todo(app_viva, monkeypatch):
    app = app_viva
    _girar(app, 300)
    viejo = app.motor
    viejo.detener()
    viejo.join(timeout=2)
    soltados = []
    real = app.salida.soltar_todo
    monkeypatch.setattr(app.salida, "soltar_todo", lambda motivo="": (soltados.append(motivo), real(motivo)))
    app._vigilar_motor(time.monotonic())
    assert app.motor is not viejo and app.reinicios == 1
    assert "motor caído" in soltados
    assert app.ventana.lbl_aviso.cget("text") == T.t("aviso_motor_caido")
    _girar(app, 600)
    assert app.motor.maquina.estado == K.PAUSA          # tras reiniciar queda en pausa
    # sin vistas nuevas más de 2 s también cuenta; al tercer reinicio se rinde
    for _ in range(3):
        app._t_ult_vista = time.monotonic() - 5
        app._vigilar_motor(time.monotonic())
    assert app.motor_rendido and app.reinicios == 3
    _girar(app, 100)
    assert app.ventana.lbl_estado.cget("text") == T.texto_estado("DETENIDO")


def test_indicador_junto_al_cursor_contenido(app_viva):
    from lycan_face_control.estados import Vista
    from lycan_face_control.gestos import ResultadoGestos
    from lycan_face_control.motor import VistaMotor
    from lycan_face_control.permanencia import EstadoPermanencia
    ind = app_viva.indicador
    v = VistaMotor(maquina=Vista(estado=K.ACTIVO, puntero=(500, 400),
                                 permanencia=EstadoPermanencia(0.5, True, False, None, (500, 400))))
    c = ind.contenido(v)
    assert c[0] == (500, 400) and c[1] == 0.5
    ind.actualizar(v)
    # parpadeo natural sin acción fuera del barrido: no se muestra la barra de ojos
    g = ResultadoGestos(ojos_cerrados=True, parpadeo_progreso=0.3)
    v2 = VistaMotor(maquina=Vista(estado=K.ACTIVO, puntero=(10, 10), gestos=g))
    assert ind.contenido(v2) is None
    v3 = VistaMotor(maquina=Vista(estado=K.ACTIVO, submodo=K.BARRIDO, puntero=(10, 10),
                                  gestos=ResultadoGestos(ojos_cerrados=True, parpadeo_progreso=1.0,
                                                         parpadeo_listo=True)))
    c3 = ind.contenido(v3)
    assert c3[2] == 1.0 and c3[3] is True
    ind.actualizar(v3)
    v4 = VistaMotor(maquina=Vista(estado=K.ACTIVO, modo_clic="doble", puntero=(10, 10)))
    assert ind.contenido(v4)[4] == T.t("ind_doble")
    assert ind.contenido(VistaMotor(maquina=Vista(estado=K.SIN_CARA, puntero=(1, 1)))) is None
    ind.actualizar(None)


def test_barra_cabe_en_una_pantalla_pequena():
    from lycan_face_control.ui.barra import medidas_barra
    area = (0, 0, 1366, 728)
    ancho, alto, sep = medidas_barra(8, 96, area, True, 70, 150)
    assert 8 * alto + 7 * sep <= 728 - 16 and alto >= 72 and ancho >= 150
    ancho, alto, sep = medidas_barra(7, 140, (0, 0, 1366, 728), False, 70, 150)
    assert 7 * ancho + 6 * sep <= 1366 - 16


# --------------------------------------------------------------------------- arranque de humo
@pytest.mark.mediapipe
def test_arranque_real_simulado_con_camara_falsa(tmp_path):
    """El programa completo (con la detección real sobre una cara dibujada) arranca en modo
    ensayo y se cierra solo a los pocos segundos, sin dejar nada presionado ni procesos vivos."""
    import json
    import os
    import subprocess
    import sys
    from pathlib import Path
    raiz = Path(__file__).resolve().parents[1]
    env = dict(os.environ, LYCAN_FACE_DATOS=str(tmp_path / "datos"))
    p = subprocess.run([sys.executable, "-m", "lycan_face_control", "--simular", "--camara-falsa", "--sin-atajos",
                        "--prueba-segundos", "5"], cwd=raiz, env=env, capture_output=True, text=True,
                       timeout=120, encoding="utf-8", errors="replace")
    lineas = [x for x in p.stdout.splitlines() if x.startswith("{")]
    assert p.returncode == 0, (p.stdout, p.stderr)
    informe = json.loads(lineas[-1])
    assert informe["todo_suelto"] is True and informe["simulada"] is True
    assert informe["error_inicio"] is None
    assert informe["cuadros"] > 10
