"""Versión 1.1: correcciones de la revisión final (seguridad, corrección e interfaz).

Sin cámara real: la aplicación de prueba usa CamaraFalsa, DetectorFalso y ``AlarmaMuda``.
"""
from __future__ import annotations

import time

from lycan_face_control.ui import aplicacion as AP
from lycan_face_control.ui import emergencia as UE
from test_interfaz import _girar, root  # noqa: F401  (fixtures)
from test_v11_b_interfaz import _esperar, app_quieta  # noqa: F401  (fixtures)


# =========================================================================== emergencia y reinicio
def test_reiniciar_la_deteccion_no_apaga_la_emergencia(app_quieta):
    """La detección se cae durante una emergencia y el vigilante crea un motor nuevo (que empieza
    sin emergencia): la pantalla roja y la alarma siguen hasta que alguien la atienda."""
    app = app_quieta
    _girar(app, 400)
    app.barra.botones["ayuda"].invocar()
    assert _esperar(app, lambda: app.motor.maquina.emergencia and app.emergencia is not None)
    _girar(app, 2000)                                 # ya pasaron más de 1,5 s
    viejo = app.motor
    app._reemplazar_motor(time.monotonic())
    assert app.motor is not viejo
    _girar(app, 3000)
    assert app.emergencia is not None and app.emergencia.viva()
    assert app.alarma.sonando
    assert app.motor.maquina.emergencia               # la máquina nueva bloquea los clics
    # la persona (o el cuidador) la apaga como siempre
    app.motor.orden("atendido", "atajo")
    assert _esperar(app, lambda: app.emergencia is None)
    assert not app.alarma.sonando


def test_con_un_motor_viejo_trabado_no_se_cierra_la_emergencia(app_quieta):
    app = app_quieta
    _girar(app, 400)
    app.barra.botones["ayuda"].invocar()
    assert _esperar(app, lambda: app.emergencia is not None)
    _girar(app, 2000)

    class Vista:
        emergencia = False
    app._motor_viejo = (app.motor, time.monotonic())   # esperando que el viejo termine
    try:
        app._revisar_emergencia(Vista())
        assert app.emergencia is not None and app.alarma.sonando
    finally:
        app._motor_viejo = None


# =========================================================================== pantalla roja que falla
def test_sin_pantalla_roja_la_alarma_suena_igual_y_se_reintenta_poco(app_quieta, monkeypatch):
    app = app_quieta
    _girar(app, 400)
    original = UE.VentanaEmergencia
    intentos = []

    def falla(*a, **k):
        intentos.append(time.monotonic())
        raise RuntimeError("Tk no pudo crear la ventana")
    monkeypatch.setattr(UE, "VentanaEmergencia", falla)
    monkeypatch.setattr(AP, "REINTENTO_VENTANA_S", 1.0)
    app.barra.botones["ayuda"].invocar()
    assert _esperar(app, lambda: app.motor.maquina.emergencia)
    _girar(app, 600)
    assert app.emergencia is None and app._sin_ventana and app.emergencia_abierta()
    assert app.alarma.sonando and app.alarma.veces_tocar >= 1     # la alarma no depende de la ventana
    assert "PIDIERON AYUDA" in app.ventana.lbl_aviso.cget("text")
    assert "Ctrl+Alt+A" in app.ventana.lbl_aviso.cget("text")
    n = len(intentos)
    _girar(app, 1500)
    assert len(intentos) - n <= 2                    # no un intento por cuadro
    # cuando Tk vuelve a funcionar, la pantalla roja aparece y la alarma sigue
    monkeypatch.setattr(UE, "VentanaEmergencia", original)
    assert _esperar(app, lambda: app.emergencia is not None, 3000)
    assert not app._sin_ventana and app.alarma.sonando
    app.motor.orden("atendido", "atajo")
    assert _esperar(app, lambda: app.emergencia is None)
    assert not app.alarma.sonando


def test_sin_pantalla_roja_el_cuidador_la_apaga(app_quieta, monkeypatch):
    app = app_quieta
    _girar(app, 400)

    def falla(*a, **k):
        raise RuntimeError("Tk no pudo crear la ventana")
    monkeypatch.setattr(UE, "VentanaEmergencia", falla)
    app.barra.botones["ayuda"].invocar()
    assert _esperar(app, lambda: app._sin_ventana and app.alarma.sonando)
    app.motor.orden("atendido", "atajo")             # el atajo del cuidador llega a la máquina
    assert _esperar(app, lambda: not app._sin_ventana)
    assert not app.alarma.sonando and not app.emergencia_abierta()
    assert not app.motor.maquina.emergencia


def test_la_prueba_de_la_alarma_sin_pantalla_no_queda_sonando(app_quieta, monkeypatch):
    app = app_quieta
    _girar(app, 400)

    def falla(*a, **k):
        raise RuntimeError("Tk no pudo crear la ventana")
    monkeypatch.setattr(UE, "VentanaEmergencia", falla)
    assert app.probar_alarma() is None
    _girar(app, 400)
    assert not app._sin_ventana and not app.emergencia_abierta()
    assert app.alarma is None or not app.alarma.sonando


# =========================================================================== barra, pestaña y teclado
import pytest  # noqa: E402
import tkinter as tk  # noqa: E402
import tkinter.font as tkfont  # noqa: E402

from lycan_face_control.permanencia import buscar_objetivo  # noqa: E402


def _cruza(a, b):
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


@pytest.fixture
def pantalla(tmp_path, monkeypatch):
    """Aplicación de prueba con un monitor fingido (ancho, alto); el área de trabajo deja 40 px para
    la barra de tareas. Se llama con los datos de comodidad ya puestos."""
    from conftest import verificar_invariantes
    from lycan_face_control.sistema import pantallas
    from test_interfaz import _app
    creadas = []

    def crear(W=1366, H=768, escala=1.0, posicion="derecha"):
        monkeypatch.setattr(pantallas, "elegir",
                            lambda nombre="principal": pantallas.Monitor(0, 0, W, H, True, trabajo=(0, 0, W, H - 40)))
        app = _app(tmp_path, funcion=lambda t: {"yaw": -9.0})
        app.cfg.datos["comodidad"]["escala_letra"] = escala
        app.cfg.datos["barra"]["posicion"] = posicion
        app.motor.start()
        for intento in range(5):             # crear Tk a veces falla un instante (como en el fixture root)
            try:
                app.construir_interfaz()
                break
            except tk.TclError as e:
                if intento == 4:
                    app.finalizar()
                    pytest.skip(f"sin pantalla ({e})")
                time.sleep(0.3)
        creadas.append(app)
        _girar(app, 400)
        return app
    yield crear
    for app in creadas:
        if not app.cerrando:
            app.salir_seguro()
        app.finalizar()
        verificar_invariantes(app.salida)


def test_el_teclado_no_tapa_la_pestana_de_la_barra_minimizada(pantalla):
    app = pantalla(1366, 768)
    app.barra.minimizar()
    _girar(app, 300)
    app.alternar_teclado()
    _girar(app, 600)
    objs = app.motor.maquina.objetivos
    tec = next(o for o in objs if o.id == "ventana:teclado")
    for oid in ("ui:barra_mostrar", "pestana:ayuda"):
        p = next(o for o in objs if o.id == oid)
        assert not _cruza(p.rect, tec.rect), (oid, p.rect, tec.rect)
    # ninguna tecla queda debajo de la pestaña: al quedarse sobre una tecla se escribe esa tecla
    for o in objs:
        if o.id.startswith("tecla:"):
            cx, cy = (o.rect[0] + o.rect[2]) // 2, (o.rect[1] + o.rect[3]) // 2
            g = buscar_objetivo((cx, cy), objs)
            assert g is not None and g.id == o.id, (o.id, g and g.id)
    # al volver a abrir la barra el teclado se acomoda y tampoco queda debajo de ella
    app.barra.mostrar()
    _girar(app, 500)
    objs = app.motor.maquina.objetivos
    tec = next(o for o in objs if o.id == "ventana:teclado")
    barra = next(o for o in objs if o.id == "ventana:barra")
    assert not _cruza(barra.rect, tec.rect), (barra.rect, tec.rect)


def test_con_el_teclado_la_barra_cabe_en_una_columna_en_1280(pantalla):
    app = pantalla(1280, 720)
    app.alternar_teclado()
    _girar(app, 600)
    b = app.barra
    assert "minimizar" not in b.botones and "ayuda" in b.botones
    assert b.medidas[3] == 1, b.medidas                  # una sola columna: el teclado conserva su ancho
    app.cerrar_teclado()
    _girar(app, 400)
    assert "minimizar" in app.barra.botones              # sin el teclado vuelve «Minimizar»


@pytest.mark.parametrize("escala", [1.3, 1.5])
def test_con_letra_grande_y_teclado_los_botones_de_la_barra_no_se_cortan(pantalla, escala):
    app = pantalla(1366, 768, escala=escala)
    app.alternar_teclado()
    _girar(app, 600)
    for ident, b in app.barra.botones.items():
        assert b.winfo_reqheight() <= b.winfo_height() + 2, (ident, b.winfo_reqheight(), b.winfo_height())
        f = tkfont.Font(root=app.root, font=b.cget("font"))
        assert f.measure(b.texto) <= b.winfo_width(), ident


# =========================================================================== presentación de la calibración
@pytest.mark.parametrize("W,H,pos", [(1280, 720, "derecha"), (1366, 768, "abajo"), (1366, 768, "arriba"),
                                     (1280, 720, "abajo")])
def test_la_presentacion_de_la_calibracion_cabe_con_sus_botones_enteros(pantalla, W, H, pos):
    app = pantalla(W, H, posicion=pos)
    cal = app.abrir_calibracion()
    _girar(app, 300)
    botones = {e.ident: e.widget for e in app.registro.entradas
               if e.ident in ("cal:empezar", "cal:cancelar", "cal:fuente:menos", "cal:fuente:mas")}
    assert len(botones) == 4
    for ident, b in botones.items():
        assert b.winfo_height() >= b.winfo_reqheight() - 2, (ident, b.winfo_height(), b.winfo_reqheight())
        assert b.winfo_width() >= b.winfo_reqwidth() - 2, ident
        if ident.startswith("cal:fuente"):
            assert b.winfo_height() >= 72, (ident, b.winfo_height())
        y = b.winfo_rooty() - cal.win.winfo_rooty()
        assert 0 <= y and y + b.winfo_height() <= cal.win.winfo_height(), ident
    # ◀ y ▶ no se mueven al cambiar de opción
    menos, mas = botones["cal:fuente:menos"], botones["cal:fuente:mas"]
    antes = (menos.winfo_rootx(), mas.winfo_rootx())
    for _ in range(3):
        cal.cambiar_fuente(+1)
        _girar(app, 60)
        assert (menos.winfo_rootx(), mas.winfo_rootx()) == antes
    cal.cancelar()


# =========================================================================== colores
@pytest.mark.parametrize("nombre", ["TEMA_NORMAL", "TEMA_ALTO_CONTRASTE"])
def test_ayuda_tiene_su_propio_rojo_en_los_dos_temas(nombre):
    from lycan_face_control.ui import comun
    T = getattr(comun, nombre)
    assert T.emergencia not in (T.verde, T.acento, T.ambar, T.boton)
    assert comun.contraste(T.sobre_color, T.emergencia) >= 7.0


def test_la_pantalla_de_emergencia_llega_a_7_a_1():
    from lycan_face_control import emergencia as E
    from lycan_face_control.ui import comun
    for fondo in (E.ROJO_CLARO, E.ROJO_OSCURO):
        assert comun.contraste(UE.TEXTO_BLANCO, fondo) >= 7.0, fondo


def test_en_alto_contraste_ayuda_no_se_ve_como_reanudar(pantalla, tmp_path):
    from lycan_face_control.ui.comun import TEMA_ALTO_CONTRASTE
    app = pantalla(1366, 768)
    app.cfg.datos["comodidad"]["alto_contraste"] = True
    app.barra.construir()
    _girar(app, 200)
    assert app.barra.botones["ayuda"]._color == TEMA_ALTO_CONTRASTE.emergencia
    assert app.barra.botones["ayuda"]._color != TEMA_ALTO_CONTRASTE.verde


def test_la_pestana_del_teclado_minimizado_no_corta_su_texto(pantalla):
    app = pantalla(1366, 768)
    app.alternar_teclado()
    _girar(app, 500)
    app.teclado.minimizar()
    _girar(app, 300)
    b = app.teclado.boton_pestana
    assert b.winfo_height() >= b.winfo_reqheight() - 2 and b.winfo_width() >= b.winfo_reqwidth() - 2
    app.teclado.restaurar()


# =========================================================================== Opciones con letra grande
@pytest.mark.parametrize("W,H,escala", [(1366, 768, 1.3), (1280, 720, 1.3), (1366, 768, 1.5)])
def test_opciones_con_letra_grande_los_botones_caben_enteros(pantalla, W, H, escala):
    from lycan_face_control.ui import opciones as OP
    from lycan_face_control.ui.comun import BotonGrande
    app = pantalla(W, H, escala=escala)
    op = app.abrir_opciones()
    _girar(app, 200)
    malos = []
    for p in OP.PESTANAS:
        op.pestana, op.pagina = p, 0
        op._armar()
        while True:
            op.win.update_idletasks()
            _girar(app, 30)
            ww, wh = op.win.winfo_width(), op.win.winfo_height()
            ox, oy = op.win.winfo_rootx(), op.win.winfo_rooty()

            def revisar(w):
                for c in w.winfo_children():
                    if isinstance(c, BotonGrande) and c.winfo_ismapped():
                        x, y = c.winfo_rootx() - ox, c.winfo_rooty() - oy
                        if (c.winfo_width() < c.winfo_reqwidth() - 2 or c.winfo_height() < c.winfo_reqheight() - 2
                                or x < -1 or y < -1 or x + c.winfo_width() > ww + 1 or y + c.winfo_height() > wh + 1):
                            malos.append((p, op.pagina, c.cget("text"), (x, y, c.winfo_width(), c.winfo_height()),
                                          (c.winfo_reqwidth(), c.winfo_reqheight()), (ww, wh)))
                    revisar(c)
            revisar(op.win)
            n0 = op.pagina
            op.ir_pagina(1)
            if op.pagina == n0:
                break
    op.cancelar()
    assert not malos, malos[:6]


# =========================================================================== textos de la Ayuda
def test_la_ayuda_dice_el_tiempo_y_las_opciones_de_verdad():
    import copy
    from lycan_face_control.config import FABRICA
    from lycan_face_control.emergencia import mensaje_voz
    from lycan_face_control.ui import textos as T
    c = copy.deepcopy(FABRICA)

    def texto(sec):
        return T.t(f"ayuda_{sec}", version="1.1.0", pausa=T.pausa_uso(c), barra=T.barra_uso(c),
                   mensaje=mensaje_voz(c), **T.atajos_kw(c), **T.ayuda_kw(c))
    assert "unos 2,5 segundos" in texto("emergencia") and "{" not in texto("emergencia")
    assert "lupa" in texto("ojos") and "se pega" in texto("ojos")
    c["emergencia"]["permanencia_s"] = 4.0
    c["ojos"]["lupa"] = False
    c["ojos"]["iman"] = False
    assert "unos 4 segundos" in texto("emergencia")
    assert "aparecer la lupa" not in texto("ojos") and "se pega" not in texto("ojos")
    assert "{" not in texto("ojos")
    assert T.t("ayuda_titulo") == "Cómo usar"        # AYUDA es solo la emergencia


def test_apagar_ayuda_con_un_gesto_de_ayuda_lo_dice(app_quieta):
    from lycan_face_control.ui import textos as T
    app = app_quieta
    app.cfg.datos["gestos"]["cejas"]["activo"] = True
    app.cfg.datos["gestos"]["cejas"]["largo"] = "emergencia"
    op = app.abrir_opciones()
    op.ir_a("emergencia")
    _girar(app, 100)
    b = next(e.widget for e in app.registro.entradas if e.ident == "op:emergencia.activa:alternar")
    b.invocar()
    _girar(app, 100)
    assert T.t("aviso_emergencia_apagada_gesto") in app.ventana.lbl_aviso.cget("text")
    op.cancelar()
