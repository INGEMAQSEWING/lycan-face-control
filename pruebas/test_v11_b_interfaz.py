"""Versión 1.1, paquete B: interfaz de la emergencia (Tk, sin cámara real y sin sonido: la
aplicación de prueba usa ``AlarmaMuda``).

- Botón rojo AYUDA en la barra, en la pestaña de la barra minimizada y en el teclado.
- Pantalla roja a pantalla completa: título, cuidador, «Ya me atendieron», Esc, clic y atajo.
- El color alterna como máximo una vez por segundo.
- «Cómo usar» reemplaza a «Ayuda»; con ``emergencia.activa = False`` no hay botones AYUDA.
- Con la detección caída el ratón igual abre (y cierra) la emergencia.
- «Probar la alarma (3 segundos)» en Opciones.
"""
from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont

import pytest

from lycan_face_control import constantes as K
from lycan_face_control import emergencia as E
from lycan_face_control.acciones import Aviso, Elegir
from lycan_face_control.barrido import EstadoBarrido
from lycan_face_control.sistema.alarma import AlarmaMuda
from lycan_face_control.ui import opciones as OP
from lycan_face_control.ui import textos as T
from lycan_face_control.ui.barra import AYUDA_MIN_PX, SEPARACION
from lycan_face_control.ui.comun import TEMA_NORMAL
from lycan_face_control.ui.emergencia import BOTON_MIN_ALTO, BOTON_MIN_ANCHO, PT_TITULO, VentanaEmergencia
from test_interfaz import _app, _girar, bombear, root  # noqa: F401  (fixtures)


@pytest.fixture
def app_quieta(tmp_path):
    """Aplicación de prueba con la cabeza sintética quieta a la izquierda (lejos de la barra y del
    botón «Ya me atendieron», para que ninguna permanencia se dispare sola)."""
    from conftest import verificar_invariantes
    app = _app(tmp_path, funcion=lambda t: {"yaw": -9.0})
    app.cfg.datos["teclado"]["cuidador"] = "Marta"
    app.motor.start()
    try:
        app.construir_interfaz()
    except tk.TclError as e:
        app.finalizar()
        pytest.skip(f"sin pantalla ({e})")
    yield app
    if not app.cerrando:
        app.salir_seguro()
    app.finalizar()
    assert not app.motor.is_alive()
    alarma = app.alarma
    assert alarma is None or not alarma.sonando          # al salir la alarma nunca queda sonando
    verificar_invariantes(app.salida)


def _esperar(app, cond, ms=3000):
    paso = 0
    while not cond() and paso < ms // 100:
        _girar(app, 100)
        paso += 1
    return cond()


def _pedir_con_el_raton(app):
    app.barra.botones["ayuda"].invocar()
    assert _esperar(app, lambda: app.motor.maquina.emergencia and app.emergencia is not None)
    return app.emergencia


# =========================================================================== barra
def test_la_barra_tiene_ayuda_rojo_al_final_con_doble_separacion(app_quieta):
    app = app_quieta
    _girar(app, 600)
    b = app.barra
    ids = list(b.botones)
    assert ids[-1] == "ayuda"
    ayuda = b.botones["ayuda"]
    assert ayuda.texto == "AYUDA" and ayuda._color == TEMA_NORMAL.rojo
    objs = {o.id: o for o in app.motor.maquina.objetivos}
    o = objs[K.ID_EMERGENCIA_BARRA]
    assert o.rect[2] - o.rect[0] >= 72 and o.rect[3] - o.rect[1] >= 72
    assert o.tiempo_s is None                       # el tiempo (2,5 s) lo pone la máquina
    # doble separación respecto del botón de encima (si está en la misma columna)
    anterior = b.botones[ids[-2]]
    if anterior.winfo_rootx() == ayuda.winfo_rootx():
        hueco = ayuda.winfo_rooty() - (anterior.winfo_rooty() + anterior.winfo_height())
        assert hueco >= 2 * b.medidas[2] - 1, hueco
    f = tkfont.Font(root=app.root, font=ayuda.cget("font"))
    assert f.measure(ayuda.texto) <= ayuda.winfo_width() - 8
    # todo cabe en el área de trabajo
    from lycan_face_control.ui.comun import area_de_trabajo
    l, a, d, ab = area_de_trabajo(app.root)
    w = b.win
    assert w.winfo_rooty() >= a and w.winfo_rooty() + w.winfo_height() <= ab


def test_la_pestana_de_la_barra_minimizada_tiene_ayuda(app_quieta):
    app = app_quieta
    _girar(app, 400)
    for pos in ("derecha", "abajo"):
        app.cfg.datos["barra"]["posicion"] = pos
        app.barra.construir()
        app.barra.minimizar()
        _girar(app, 400)
        objs = {o.id: o for o in app.motor.maquina.objetivos}
        assert K.ID_EMERGENCIA_PESTANA in objs and K.ID_EMERGENCIA_BARRA not in objs
        o = objs[K.ID_EMERGENCIA_PESTANA]
        assert o.rect[2] - o.rect[0] >= AYUDA_MIN_PX and o.rect[3] - o.rect[1] >= AYUDA_MIN_PX, (pos, o.rect)
        m = objs["ui:barra_mostrar"]
        # el AYUDA no se encima con la pestaña «Barra»
        assert o.rect[1] >= m.rect[3] or o.rect[0] >= m.rect[2]
        app.barra.mostrar()
    # con el ratón del cuidador, el AYUDA de la pestaña también la pide
    app.barra.minimizar()
    app.barra.boton_pestana_ayuda.invocar()
    assert _esperar(app, lambda: app.motor.maquina.emergencia)


def test_sin_el_boton_ayuda_no_hay_ayuda_en_ningun_lado(app_quieta):
    app = app_quieta
    app.cfg.datos["emergencia"]["activa"] = False
    app.barra.construir()
    assert "ayuda" not in app.barra.botones and app.barra.boton_pestana_ayuda is None
    app.alternar_teclado()
    _girar(app, 500)
    assert K.ID_EMERGENCIA_TECLADO not in app.teclado.botones
    ids = {o.id for o in app.motor.maquina.objetivos}
    assert not ids & set(K.IDS_EMERGENCIA)


# =========================================================================== pantalla roja
def test_ayuda_con_el_raton_abre_la_pantalla_roja_completa(app_quieta):
    app = app_quieta
    _girar(app, 400)
    e = _pedir_con_el_raton(app)
    _girar(app, 300)
    assert isinstance(app.alarma, AlarmaMuda) and app.alarma.sonando
    w = e.win
    l, a, d, ab = app._monitor_emergencia()
    assert (w.winfo_width(), w.winfo_height()) == (d - l, ab - a)
    assert e.lbl_titulo.cget("text") == "NECESITO AYUDA"
    assert int(tkfont.Font(root=app.root, font=e.lbl_titulo.cget("font")).actual("size")) >= PT_TITULO
    assert "Marta" in e.lbl_llamando.cget("text")
    assert e.boton.texto == "Ya me atendieron"
    assert e.boton.winfo_width() >= BOTON_MIN_ANCHO and e.boton.winfo_height() >= BOTON_MIN_ALTO
    assert "Ctrl+Alt+A" in e.lbl_como.cget("text")
    objs = {o.id for o in app.motor.maquina.objetivos}
    assert K.ID_ATENDIDO in objs and "ventana:emergencia" in objs
    assert app.ultima_vista.maquina.emergencia
    # pedirla otra vez no abre otra ventana
    app.barra.botones["ayuda"].invocar()
    _girar(app, 300)
    assert app.emergencia is e


def test_esc_apaga_la_alarma_y_vuelve_a_como_estaba(app_quieta):
    app = app_quieta
    _girar(app, 400)
    e = _pedir_con_el_raton(app)
    e.win.event_generate("<Escape>")
    e.escape()                                  # sin evento también (e=None)
    assert not app.alarma.sonando               # se calla al instante
    assert _esperar(app, lambda: app.emergencia is None and not app.motor.maquina.emergencia)
    assert app.motor.maquina.estado == K.ACTIVO
    assert not e.viva()
    _girar(app, 500)
    assert app.emergencia is None               # no se vuelve a abrir sola


def test_clic_en_ya_me_atendieron_apaga(app_quieta):
    app = app_quieta
    _girar(app, 400)
    app.orden("pausar", "cuidador")
    _girar(app, 300)
    e = _pedir_con_el_raton(app)
    e.boton.invocar()
    assert _esperar(app, lambda: app.emergencia is None and not app.motor.maquina.emergencia)
    assert app.motor.maquina.estado == K.PAUSA  # estaba en pausa: sigue en pausa


def test_el_atajo_del_cuidador_calla_en_su_hilo_y_apaga(app_quieta):
    app = app_quieta
    _girar(app, 400)
    _pedir_con_el_raton(app)
    app._atajo_emergencia()                     # lo que corre en el hilo de atajos
    assert not app.alarma.sonando
    app.cola_atajos.put("emergencia")
    assert _esperar(app, lambda: app.emergencia is None and not app.motor.maquina.emergencia)
    # sin emergencia, el atajo no hace nada
    app._atajo_emergencia()
    app.cola_atajos.put("emergencia")
    _girar(app, 300)
    assert app.motor.maquina.estado == K.ACTIVO and app.emergencia is None


def test_si_se_pierde_el_aviso_la_pantalla_sigue_a_la_maquina(app_quieta):
    app = app_quieta
    _girar(app, 400)
    app.motor.orden("ayuda", "botón")
    # el aviso se pierde: se vacía la cola antes de que la interfaz la lea
    _girar(app, 0)
    assert _esperar(app, lambda: app.emergencia is not None)
    app.motor.orden("atendido", "atajo")
    assert _esperar(app, lambda: app.emergencia is None)


def test_la_alarma_que_no_suena_avisa_y_la_pantalla_sigue(app_quieta):
    app = app_quieta
    _girar(app, 400)
    app.alarma = AlarmaMuda(falla=True)
    e = _pedir_con_el_raton(app)
    _girar(app, 300)
    assert e.viva()
    assert T.t("aviso_alarma_falla") in app.ventana.lbl_aviso.cget("text")


def test_el_color_alterna_como_maximo_una_vez_por_segundo(app_quieta):
    app = app_quieta
    reloj = [1000.0]
    e = VentanaEmergencia(app.root, app, (0, 0, 800, 600), prueba=False, reloj=lambda: reloj[0])
    try:
        for _ in range(100):                    # 10 s en pasos de 0,1 s
            reloj[0] += 0.1
            e._pintar_color()
        colores = [c for _, c in e.cambios]
        assert set(colores) == {E.ROJO_CLARO, E.ROJO_OSCURO}
        tiempos = [x for x, _ in e.cambios]
        assert all(b - a >= 1.0 - 1e-6 for a, b in zip(tiempos, tiempos[1:]))
        assert len(e.cambios) <= 11
        assert e.win.cget("bg") in (E.ROJO_CLARO, E.ROJO_OSCURO)
    finally:
        e.cerrar()


def test_con_la_deteccion_caida_el_raton_abre_y_cierra_la_emergencia(app_quieta):
    app = app_quieta
    _girar(app, 400)
    import time
    app._rendirse(time.monotonic())                  # la detección se rindió (no reintenta en 1 minuto)
    app.barra.botones["ayuda"].invocar()
    bombear(app.root, 100)
    assert app.emergencia is not None and app._emergencia_local
    assert not app.motor.maquina.emergencia          # la máquina no se enteró: la abrió la interfaz
    assert app.alarma.sonando
    app.emergencia.boton.invocar()
    bombear(app.root, 100)
    assert app.emergencia is None and not app.alarma.sonando
    # Esc también
    app.pedir_ayuda("barrido")
    assert app.emergencia is not None
    app.emergencia.escape()
    assert app.emergencia is None
    app.motor_rendido = False
    app._t_rendido = None


def test_salir_detiene_la_alarma_y_cierra_la_pantalla(app_quieta):
    app = app_quieta
    _girar(app, 400)
    _pedir_con_el_raton(app)
    _girar(app, 200)
    alarma = app.alarma
    assert alarma.sonando
    app.salir_seguro()
    assert not alarma.sonando and app.emergencia is None


def test_la_voz_se_dice_entre_alarmas(app_quieta, monkeypatch):
    app = app_quieta
    dicho = []

    class VozFalsa:
        voz_espanol = True

        def hablar(self, texto, urgente=False):
            dicho.append((texto, urgente))
            return True
    app.voz = VozFalsa()
    app.cfg.datos["emergencia"]["repetir_s"] = 5
    _girar(app, 300)
    _pedir_con_el_raton(app)
    plan = app._plan_alarma
    assert plan.con_voz
    # se adelanta el reloj del plan para no esperar 5 s
    plan.t0 -= 5.2
    _girar(app, 400)
    assert dicho == [("Necesito ayuda. Por favor, que venga Marta.", True)]
    assert not app.alarma.sonando                # mientras habla, la alarma se calla
    plan.t0 -= plan.duracion_voz_s + 0.5
    _girar(app, 400)
    assert app.alarma.sonando                    # y vuelve
    assert len(dicho) == 1


# =========================================================================== probar
def test_probar_la_alarma_dura_3_s_y_no_cambia_el_estado(app_quieta):
    app = app_quieta
    _girar(app, 400)
    op = app.abrir_opciones()
    op.ir_a("emergencia")
    bombear(app.root, 100)
    rutas = [c[1] for c in OP.controles("emergencia")]
    assert "probar_alarma" in rutas
    b = next(e.widget for e in app.registro.entradas if e.ident == "op:probar_alarma")
    b.invocar()
    bombear(app.root, 200)
    e = app.emergencia
    assert e is not None and e.prueba and app.alarma.sonando
    assert T.t("emergencia_prueba") in e.lbl_como.cget("text")
    assert not app.motor.maquina.emergencia
    assert K.ID_ATENDIDO not in {o.id for o in app.motor.maquina.objetivos}
    bombear(app.root, int(E.PROBAR_S * 1000) + 600)
    assert app.emergencia is None and not app.alarma.sonando
    assert not app.motor.maquina.emergencia
    # Esc la corta antes
    app.probar_alarma()
    app.emergencia.escape()
    assert app.emergencia is None
    op.cancelar()


def test_pestana_emergencia_de_opciones(app_quieta):
    app = app_quieta
    op = app.abrir_opciones()
    op.ir_a("emergencia")
    bombear(app.root, 100)
    textos = [w.cget("text") for w in op.cuerpo.winfo_children() if isinstance(w, tk.Label)]
    assert T.t("op_emergencia_nota") in textos
    # apagar el botón avisa lo que significa
    b = next(e.widget for e in app.registro.entradas if e.ident == "op:emergencia.activa:alternar")
    b.invocar()
    bombear(app.root, 100)
    assert op.datos["emergencia"]["activa"] is False
    assert T.t("aviso_emergencia_apagada") in app.ventana.lbl_aviso.cget("text")
    # el mensaje se recorta a 60 letras
    var = op.entradas["emergencia.mensaje"]
    var.set("x" * 90)
    assert len(op.datos["emergencia"]["mensaje"]) == 60
    op.ir_pagina(+1)
    bombear(app.root, 100)
    op.ir_a("atajos")
    bombear(app.root, 100)
    assert "atajos.emergencia" in op.entradas
    # las 7 pestañas caben a lo ancho (en dos filas si hace falta) y «Guardar» sigue a la vista
    bombear(app.root, 100)
    tabs = [e.widget for e in app.registro.entradas if e.ident.startswith("op:tab:")]
    assert len(tabs) == 7
    for w in tabs:
        f = tkfont.Font(root=app.root, font=w.cget("font"))
        assert f.measure(w.texto) <= w.winfo_width() - 8, w.texto
        assert w.winfo_rootx() + w.winfo_width() <= op.win.winfo_rootx() + op.win.winfo_width()
    for pestana in OP.PESTANAS:
        op.ir_a(pestana)
        bombear(app.root, 150)
        op.win.update()

        def vivo(ident):
            return [e.widget for e in app.registro.entradas
                    if e.ident == ident and e.widget.winfo_exists() and e.widget.winfo_ismapped()]
        g = vivo("op:guardar")[0]
        assert g.winfo_rooty() + g.winfo_height() <= op.win.winfo_rooty() + op.win.winfo_height(), pestana
        for b in vivo("op:pagina:siguiente"):
            assert b.winfo_rooty() + b.winfo_height() <= g.winfo_rooty(), pestana
    op.cancelar()


# =========================================================================== «Cómo usar»
def test_como_usar_reemplaza_a_ayuda_y_cabe(app_quieta):
    app = app_quieta
    _girar(app, 400)
    b = app.ventana.b["ui:ayuda"]
    assert b.texto == "Cómo usar"
    f = tkfont.Font(root=app.root, font=b.cget("font"))
    assert f.measure("Cómo usar") <= b.winfo_width() - 8
    app.alternar_teclado()
    _girar(app, 500)
    tb = app.teclado.botones["accion:ayuda"]
    assert tb.texto == "Cómo usar"
    # en la fila de acciones va en dos líneas (como «Borrar palabra»): cada palabra cabe a lo ancho
    # y las dos líneas caben a lo alto
    f = tkfont.Font(root=app.root, font=tb.cget("font"))
    assert max(f.measure(p) for p in ("Cómo", "usar")) <= tb.winfo_width() - 12
    # sin el «?» encima: como mucho dos líneas, igual que «Borrar palabra» (riesgo conocido del
    # teclado con letra de 20 pt; ver docs/decisiones.md)
    assert T.t("icono_tec_ayuda_btn") == "" and tb.texto.count(" ") == 1


def test_la_ayuda_tiene_la_pagina_de_emergencia_y_las_pestanas_caben(app_quieta):
    app = app_quieta
    a = app.abrir_ayuda()
    a.ir_a("emergencia")
    bombear(app.root, 200)
    texto = " ".join(w.cget("text") for w in a.cuerpo.winfo_children() if isinstance(w, tk.Label))
    assert "AYUDA" in texto and "{" not in texto
    for s, w in a.tabs.items():
        f = tkfont.Font(root=app.root, font=w.cget("font"))
        assert f.measure(w.texto) <= w.winfo_width() - 8, s
    a.cerrar()


# =========================================================================== teclado
def test_teclado_tiene_ayuda_rojo_primero_y_con_el_raton_la_pide(app_quieta):
    app = app_quieta
    _girar(app, 300)
    app.alternar_teclado()
    _girar(app, 500)
    tec = app.teclado
    b = tec.botones[K.ID_EMERGENCIA_TECLADO]
    assert b.texto == "AYUDA" and b._color == TEMA_NORMAL.rojo
    fila = tec.disp.fila("texto")
    assert fila[0].id == "accion:emergencia"
    o = next(o for o in app.motor.maquina.objetivos if o.id == K.ID_EMERGENCIA_TECLADO)
    assert o.rect[3] - o.rect[1] >= 72
    f = tkfont.Font(root=app.root, font=b.cget("font"))
    assert f.measure("AYUDA") <= b.winfo_width() - 8
    b.invocar()
    assert _esperar(app, lambda: app.motor.maquina.emergencia and app.emergencia is not None)


def test_en_el_barrido_ayuda_esta_en_el_primer_grupo_y_se_elige(app_quieta):
    app = app_quieta
    app.cfg.datos["teclado"]["barrido"] = True
    _girar(app, 300)
    app.alternar_teclado()
    _girar(app, 600)
    tec = app.teclado
    assert tec.barrido is not None
    filas = tec.filas_barrido()
    assert filas[0][:3] == ["frase:si", "frase:no", K.ID_EMERGENCIA_TECLADO]
    assert all(K.ID_EMERGENCIA_TECLADO not in f for f in filas[1:])
    # el barrido la elige (parpadeo largo sobre lo iluminado)
    tec._atender_estado_barrido(EstadoBarrido(elegido=K.ID_EMERGENCIA_TECLADO))
    assert _esperar(app, lambda: app.motor.maquina.emergencia and app.emergencia is not None)
    # mientras dura, el barrido no avanza
    t_antes = tec.barrido._t
    _girar(app, 300)
    assert tec.barrido._t >= t_antes
    app.motor.orden("atendido", "atajo")
    assert _esperar(app, lambda: app.emergencia is None)


def test_atender_el_aviso_de_la_maquina_abre_y_cierra(app_quieta):
    app = app_quieta
    _girar(app, 300)
    app.atender(Aviso("emergencia", "gesto"))
    assert app.emergencia is not None and app.emergencia.viva()
    app.atender(Aviso("emergencia_fin", "persona"))
    assert app.emergencia is None
    assert T.t("aviso_emergencia_fin") in app.ventana.lbl_aviso.cget("text")
    # elegirlo con la cabeza (la máquina ya hizo lo suyo): la interfaz no repite nada
    app.atender(Elegir(K.ID_EMERGENCIA_BARRA))
    _girar(app, 200)
