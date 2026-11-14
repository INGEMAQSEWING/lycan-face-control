"""Versión 1.1, paquete C: interfaz (Tk, sin cámara real): «Mover el puntero con» en la calibración
y en Opciones, la ventana de los puntos de la mirada, la página «Con los ojos» de la ayuda y el
punto del centro al recentrar."""
from __future__ import annotations

import copy

import pytest

from conftest import medidas
from lycan_face_control import constantes as K
from lycan_face_control.calibracion_guiada import PASOS_MIRADA, Guia
from lycan_face_control.config import Configuracion
from lycan_face_control.ui import ayuda as AY
from lycan_face_control.ui import opciones as OP
from lycan_face_control.ui import textos as T
from lycan_face_control.ui.calibracion_mirada import RADIO_MEDIR_MIN, RADIO_PREPARAR, radio_punto
from ojos_sinteticos import MON, cal_con_mirada, medidas_mirando
from test_interfaz import DUR_CORTAS, _girar, app_viva, bombear, root  # noqa: F401  (fixtures)

POR_PASO = {"izq": medidas(yaw_n=-0.06), "der": medidas(yaw_n=0.11), "arr": medidas(pitch_n=0.45),
            "aba": medidas(pitch_n=0.66), "gesto_boca": medidas(mar=0.5), "gesto_cejas": medidas(cejas=0.45)}


def _correr_calibracion(app, cal, hasta=None):
    """Alimenta la guía (pasos cortos) mirando los puntos que pide; pinta de vez en cuando."""
    cal.guia = Guia(cal._cfg_guia(), 0.0, preparar_s=0.0, duraciones=DUR_CORTAS, monitor=cal._monitor())
    t = 0.0
    vista_mirada = False
    for k in range(30 * 120):
        g = cal.guia
        if g.terminado or (hasta and g.paso == hasta):
            break
        if g.paso in PASOS_MIRADA:
            est = g.estado(t)
            if g.paso == "mirada_cabeza":
                import math
                m = medidas_mirando(*MON.centro, 6 * math.sin(3 * t), 4 * math.cos(5 * t))
            else:
                m = medidas_mirando(*(est.punto or MON.centro))
        else:
            m = POR_PASO.get(g.paso, medidas_mirando(*MON.centro))
        est = cal.alimentar(t, m, 0.15)
        t += 1 / 30
        if k % 10 == 0:
            cal._pintar(est)
            cal._pintar_mirada(est)
            vista_mirada = vista_mirada or cal.ventana_mirada is not None
            app.root.update()
    return vista_mirada


def test_radio_del_punto_se_encoge_al_medir():
    assert radio_punto("preparar", 0.5) == RADIO_PREPARAR
    assert radio_punto("medir", 0.0) == RADIO_PREPARAR
    assert radio_punto("medir", 1.0) == RADIO_MEDIR_MIN
    assert RADIO_MEDIR_MIN < radio_punto("medir", 0.5) < RADIO_PREPARAR


def test_calibrar_los_ojos_desde_la_pantalla_de_inicio_y_guardar_la_fuente(app_viva):
    app = app_viva
    _girar(app, 300)
    cal = app.abrir_calibracion()
    assert cal.fuente == "cabeza" and cal.lbl_fuente.cget("text") == T.t("op_fuente_cabeza")
    ids = {e.ident for e in app.registro.entradas}
    assert {"cal:fuente:menos", "cal:fuente:mas"} <= ids
    app.registro.elegir("cal:fuente:mas")                    # con la cabeza (o el ratón)
    assert cal.fuente == "ojos" and cal.lbl_fuente.cget("text") == T.t("op_fuente_ojos")
    cal.cambiar_fuente(+1)
    cal.cambiar_fuente(-1)
    assert cal.fuente == "ojos"
    # todavía no se guardó nada
    assert app.cfg.datos["puntero"]["fuente"] == "cabeza"
    cal.empezar()
    _girar(app, 300)
    cal.cambiar_fuente(+1)                                   # ya empezó: no cambia
    assert cal.fuente == "ojos"
    vio = _correr_calibracion(app, cal)
    assert vio                                               # los pasos de la mirada fueron a pantalla completa
    assert cal.guia.terminado
    cal._finalizar_pasos()
    assert cal.ventana_mirada is None
    assert app.cfg.datos["puntero"]["fuente"] == "ojos"
    guardada = Configuracion(app.cfg.ruta).cargar()
    assert guardada["puntero"]["fuente"] == "ojos"
    assert "mirada" in guardada["perfiles"]["Principal"]["calibracion"]
    texto, aviso = cal.texto_mirada
    assert "cm" in texto and not aviso
    _girar(app, 600)
    assert app.motor.maquina.puntero.fuente == "ojos"
    cal.terminar()


def test_la_ventana_de_los_puntos_cubre_el_monitor_y_sus_botones_caben(app_viva):
    app = app_viva
    _girar(app, 200)
    cal = app.abrir_calibracion()
    cal.cambiar_fuente(+1)
    cal.empezar()
    _girar(app, 200)
    _correr_calibracion(app, cal, hasta="mirada_puntos")
    est = cal.guia.estado(100.0)
    cal._pintar_mirada(est)
    v = cal.ventana_mirada
    assert v is not None
    app.root.update()
    assert (v.win.winfo_width(), v.win.winfo_height()) == (MON.ancho, MON.alto)
    assert v.canvas.find_withtag("punto")
    ids = {e.ident for e in app.registro.entradas}
    assert {"cal_ojos:repetir_paso", "cal_ojos:atras", "cal_ojos:cancelar"} <= ids
    fila = list(v.botones.values())[0].master
    assert fila.winfo_reqwidth() < MON.ancho - 40
    assert all(b.winfo_reqheight() >= 40 for b in v.botones.values())
    assert v.lbl_titulo.cget("text") == T.t("cal_mirada_puntos_titulo")
    # sin ver los ojos: el aviso
    est.sin_ojos = True
    v.actualizar(est)
    assert v.lbl_estado.cget("text") == T.t("cal_mirada_sin_ojos")
    # «Repetir este paso» con el ratón (el cuidador) vuelve al primer punto
    cal.guia._k = 3
    cal._ult_t = 100.0
    app.registro.elegir("cal_ojos:repetir_paso", "raton")
    assert cal.guia._k == 0
    # «Cancelar» cierra todo y no cambia la fuente
    app.registro.elegir("cal_ojos:cancelar", "raton")
    _girar(app, 300)
    assert app.calibracion is None and cal.ventana_mirada is None
    assert app.cfg.datos["puntero"]["fuente"] == "cabeza"
    assert app.motor.maquina.estado == K.ACTIVO


def test_si_los_ojos_no_se_pueden_calibrar_queda_la_cabeza_y_se_dice(app_viva):
    app = app_viva
    _girar(app, 200)
    cal = app.abrir_calibracion()
    cal.cambiar_fuente(+1)
    cal.empezar()
    _girar(app, 200)
    cal.guia = Guia(cal._cfg_guia(), 0.0, preparar_s=0.0, duraciones=DUR_CORTAS, monitor=cal._monitor())
    t = 0.0
    while not cal.guia.terminado:
        cal.alimentar(t, POR_PASO.get(cal.guia.paso, medidas_mirando(*MON.centro)), 0.15)   # nunca mueve los ojos
        t += 1 / 30
    cal._finalizar_pasos()
    assert app.cfg.datos["puntero"]["fuente"] == "cabeza"
    assert cal.texto_mirada == (T.t("cal_mirada_fallo"), True)
    cal.terminar()


def test_opciones_mover_el_puntero_con_y_las_filas_de_los_ojos(app_viva):
    app = app_viva
    op = app.abrir_opciones()
    _girar(app, 200)
    ctl = next(c for c in OP.controles("puntero") if c[1] == "puntero.fuente")
    # la fila puede quedar en la página 2 si la pantalla es chica
    while "puntero.fuente" not in op.etiquetas_valor and "op:pagina:siguiente" in {e.ident for e in app.registro.entradas}:
        op.ir_pagina(+1)
    assert "puntero.fuente" in op.etiquetas_valor
    op.cambiar(ctl, +1)
    assert op.datos["puntero"]["fuente"] == "ojos"
    lbl, _ = op.etiquetas_valor["puntero.fuente"]
    assert lbl.cget("text") == T.t("op_fuente_ojos")
    # las filas de los ojos están en las páginas siguientes
    vistas = set()
    for _ in range(4):
        vistas |= set(op.etiquetas_valor)
        if "op:pagina:siguiente" not in {e.ident for e in app.registro.entradas}:
            break
        op.ir_pagina(+1)
        app.root.update()
        vistas |= set(op.etiquetas_valor)
    assert {"ojos.permanencia_s", "ojos.iman", "ojos.lupa", "ojos.puntos_cal"} <= vistas
    # la sugerencia de la cámara
    op.pagina = 0
    op.ir_pagina(0)
    while "op:camara_ojos" not in {e.ident for e in app.registro.entradas}:
        op.ir_pagina(+1)
    app.registro.elegir("op:camara_ojos", "raton")
    assert (op.datos["camara"]["ancho"], op.datos["camara"]["alto"]) == OP.CAMARA_OJOS
    assert not OP.sugerir_camara(op.datos)
    op.cancelar()
    _girar(app, 200)
    assert app.cfg.datos["puntero"]["fuente"] == "cabeza" and app.cfg.datos["camara"]["ancho"] == 640


def test_opciones_textos_de_los_ojos_caben_en_1366(app_viva):
    import tkinter.font as tkfont
    app = app_viva
    ft = tkfont.Font(root=app.root, font=("Segoe UI", 16))
    for ruta in ("op_fuente", "op_ojos_permanencia", "op_ojos_salto", "op_ojos_lupa", "op_ojos_iman"):
        # la etiqueta de la fila tiene el 42 % del ancho de Opciones (800 px en 1366 × 768) y puede ir en 2 líneas
        assert ft.measure(T.t(ruta)) < 2 * 0.42 * 1000, ruta
    ft18 = tkfont.Font(root=app.root, font=("Segoe UI", 18, "bold"))
    assert ft18.measure(T.t("op_fuente_cabeza_y_ojos")) < 380          # cabe en el valor de «◀ ▶»
    for clave in ("cal_repetir_paso", "cal_atras", "btn_cancelar", "op_ojos_camara_si"):
        assert ft18.measure(T.t(clave)) < 300


def test_la_ayuda_tiene_la_pagina_con_los_ojos(app_viva):
    app = app_viva
    assert "ojos" in AY.SECCIONES
    a = app.abrir_ayuda()
    _girar(app, 200)
    app.registro.elegir("ayuda:ojos", "raton")
    app.root.update()
    textos = " ".join(w.cget("text") for w in a.cuerpo.winfo_children() if hasattr(w, "cget") and
                      w.winfo_class() == "Label")
    assert "3 a 5 cm" in textos or a.paginas > 1
    a.cerrar()


def test_recentrar_con_los_ojos_muestra_el_punto_del_centro(app_viva):
    app = app_viva
    _girar(app, 200)
    from lycan_face_control.acciones import Aviso
    antes = len(app.root.winfo_children())
    app.atender(Aviso("ojos_recentrar"))
    app.root.update()
    assert len(app.root.winfo_children()) == antes + 1
    p = app.mostrar_punto_centro()
    p.win.update()
    x = p.win.winfo_rootx() + p.win.winfo_width() / 2
    assert abs(x - MON.centro[0]) <= 2
    p.cerrar()
    assert T.texto_aviso(Aviso("ojos_recentrar")) == T.t("aviso_ojos_recentrar")


def test_la_maquina_de_la_aplicacion_usa_los_ojos_con_la_calibracion_de_la_mirada(app_viva):
    app = app_viva
    _girar(app, 200)
    datos = copy.deepcopy(app.cfg.datos)
    datos["perfiles"]["Principal"]["calibracion"] = cal_con_mirada()
    datos["puntero"]["fuente"] = "cabeza_y_ojos"
    app.aplicar_config(datos)
    _girar(app, 500)
    assert app.motor.maquina.puntero.fuente == "cabeza_y_ojos"
    assert app.ultima_vista.maquina.fuente == "cabeza_y_ojos"
