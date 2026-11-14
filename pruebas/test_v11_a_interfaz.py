"""Versión 1.1, paquete A: interfaz (Tk, sin cámara real y sin capturar la pantalla real).

- Barra de 10 u 11 botones en dos columnas cuando no caben, «Minimizar» y la pestaña «Barra».
- Opciones: «Más lento» / «Más rápido» y la velocidad arriba y abajo.
- Teclado: «Minimizar» conserva lo escrito y «Teclado» lo restaura.
- Lupa: ventana con la imagen agrandada (la captura se reemplaza por una imagen de prueba).
"""
from __future__ import annotations

import copy
import math
import tkinter as tk
import tkinter.font as tkfont

import pytest

from conftest import CAL_SINTETICA
from lycan_face_control import constantes as K
from lycan_face_control import lupa as L
from lycan_face_control.acciones import Elegir
from lycan_face_control.estados import Vista
from lycan_face_control.motor import VistaMotor
from lycan_face_control.teclado_logica import (ACCION_MINIMIZAR, ACCIONES, ACCIONES_FILA, ACCIONES_TEXTO,
                                               ACCIONES_TEXTO_MINIMIZAR, disposicion, distribucion)
from lycan_face_control.ui import opciones as OP
from lycan_face_control.ui import textos as T
from lycan_face_control.ui.barra import ALTO_MIN, MARGEN_BORDE, PESTANA_CORTO, PESTANA_LARGO, medidas_barra
from test_interfaz import _girar, app_viva, bombear, root  # noqa: F401  (fixtures)
from test_teclado import _elegir


# =========================================================================== barra: medidas
def _naturales(pt):
    """Tamaño natural de los botones con letra de ``pt`` puntos (como lo mide la barra)."""
    r = tk.Tk()
    r.withdraw()
    try:
        ft = tkfont.Font(root=r, font=("Segoe UI", pt, "bold"))
        textos = [T.t(f"barra_{i}") for i, _ in K.BOTONES_BARRA] + ["Reanudar", "Terminar", "AYUDA"]
        ancho = max(ft.measure(x) for x in textos) + 28
        alto = 2 * ft.metrics("linespace") + 20
    finally:
        r.destroy()
    return alto, ancho


@pytest.fixture(scope="module")
def naturales():
    try:
        return {100: _naturales(20), 200: _naturales(28)}
    except tk.TclError as e:
        pytest.skip(f"sin pantalla ({e})")


@pytest.mark.parametrize("pantalla", [(1366, 728), (1280, 680), (1920, 1040)])
@pytest.mark.parametrize("letra", [100, 200])
@pytest.mark.parametrize("lado", ["derecha", "izquierda", "arriba", "abajo"])
@pytest.mark.parametrize("n", [10, 11])
def test_once_botones_caben_sin_bajar_de_72_px(naturales, pantalla, letra, lado, n):
    ancho_p, alto_p = pantalla
    alto_nat, ancho_nat = naturales[letra]
    vertical = lado in ("derecha", "izquierda")
    area = (0, 0, ancho_p, alto_p)
    ancho, alto, sep, cols = medidas_barra(n, 96, area, vertical, alto_nat, ancho_nat)
    assert ancho >= ALTO_MIN and alto >= ALTO_MIN, (ancho, alto)
    por_col = math.ceil(n / cols)
    if vertical:
        largo, ancho_total = por_col * alto + (por_col - 1) * sep, cols * ancho + (cols - 1) * sep
        assert largo <= alto_p - 2 * MARGEN_BORDE and ancho_total <= ancho_p // 2
    else:
        largo, alto_total = por_col * ancho + (por_col - 1) * sep, cols * alto + (cols - 1) * sep
        assert largo <= ancho_p - 2 * MARGEN_BORDE and alto_total <= alto_p // 2
        assert ancho >= ancho_nat - 16                    # el texto se lee entero
    if vertical and pantalla == (1366, 728):
        assert cols == 2                                  # 11 botones no caben en una columna


def test_siete_u_ocho_botones_siguen_en_una_columna(naturales):
    alto_nat, ancho_nat = naturales[100]
    for n in (7, 8, 9):
        assert medidas_barra(n, 96, (0, 0, 1366, 728), True, alto_nat, ancho_nat)[3] == 1, n


# =========================================================================== barra: en pantalla
def test_barra_tiene_los_botones_nuevos_y_todos_miden_72_px_o_mas(app_viva):
    app = app_viva
    _girar(app, 800)
    for i in ("sin_clic", "lupa", "minimizar"):
        assert i in app.barra.botones, i
    assert "ocultar" not in app.barra.botones
    ids = {o.id for o in app.motor.maquina.objetivos}
    assert {"barra:sin_clic", "barra:lupa", "barra:minimizar"} <= ids
    barra = [o for o in app.motor.maquina.objetivos if o.id.startswith("barra:")]
    assert all(o.rect[3] - o.rect[1] >= 72 and o.rect[2] - o.rect[0] >= 72 for o in barra)
    # los rótulos caben en su botón
    for ident, b in app.barra.botones.items():
        f = tkfont.Font(root=app.root, font=b.cget("font"))
        assert f.measure(b.texto) <= b.winfo_width() - 8, (ident, b.texto)


def test_botones_sin_clic_y_lupa_se_pueden_quitar(app_viva):
    app = app_viva
    app.cfg.datos["barra"]["boton_sin_clic"] = False
    app.cfg.datos["barra"]["boton_lupa"] = False
    app.barra.construir()
    assert "sin_clic" not in app.barra.botones and "lupa" not in app.barra.botones
    assert "minimizar" in app.barra.botones


def test_sin_clic_y_lupa_desde_la_barra_cambian_el_modo_y_se_resaltan(app_viva):
    app = app_viva
    _girar(app, 500)
    app.barra.botones["sin_clic"].invocar()
    _girar(app, 300)
    assert app.motor.maquina.modo_clic == "ninguno"
    assert app.barra.botones["sin_clic"]._activo and not app.barra.botones["clic"]._activo
    app.barra.botones["lupa"].invocar()
    _girar(app, 300)
    assert app.motor.maquina.modo_clic == "lupa"
    assert app.barra.botones["lupa"]._activo and not app.barra.botones["sin_clic"]._activo
    app.barra.botones["clic"].invocar()
    _girar(app, 300)
    assert app.motor.maquina.modo_clic == "izq"


def test_minimizar_esconde_la_barra_y_la_pestana_la_vuelve_a_abrir(app_viva):
    app = app_viva
    _girar(app, 500)
    b = app.barra
    b.botones["minimizar"].invocar()                    # el cuidador con el ratón
    _girar(app, 400)
    assert b.minimizada and not b.win.winfo_viewable() and b.pestana.winfo_viewable()
    ids = {o.id for o in app.motor.maquina.objetivos}
    assert "ui:barra_mostrar" in ids and "barra:clic" not in ids
    o = next(o for o in app.motor.maquina.objetivos if o.id == "ui:barra_mostrar")
    assert o.tiempo_s == 0.6
    w, h = o.rect[2] - o.rect[0], o.rect[3] - o.rect[1]
    assert w >= PESTANA_CORTO and h >= PESTANA_LARGO, (w, h)          # barra a la derecha: vertical
    assert T.t("barra_mostrar") == "Barra"
    # con la cabeza: la máquina elige la pestaña
    app.atender(Elegir("ui:barra_mostrar"))
    _girar(app, 300)
    assert not b.minimizada and b.win.winfo_viewable() and not b.pestana.winfo_viewable()
    # minimizar con la cabeza (Elegir de la máquina)
    app.atender(Elegir("barra:minimizar"))
    _girar(app, 200)
    assert b.minimizada
    # el ratón del cuidador en la pestaña
    b.boton_pestana.invocar()
    _girar(app, 200)
    assert not b.minimizada


def test_pestana_horizontal_y_lo_minimizado_no_se_guarda(app_viva, tmp_path):
    app = app_viva
    app.cfg.datos["barra"]["posicion"] = "abajo"
    app.barra.construir()
    app.barra.minimizar()
    _girar(app, 300)
    pw, ph = app.barra.tam_pestana
    assert pw >= PESTANA_LARGO and ph >= PESTANA_CORTO
    app.guardar_config()
    from lycan_face_control.config import Configuracion
    assert Configuracion(app.cfg.ruta).cargar()["barra"]["visible"] is True
    # al abrir, manda barra.visible
    app.cfg.datos["barra"]["visible"] = False
    from lycan_face_control.ui.barra import BarraAcciones
    otra = BarraAcciones(app.root, app)
    try:
        assert otra.minimizada
    finally:
        otra.destruir()


def test_en_desplazar_no_hay_minimizar_y_la_barra_se_ve(app_viva):
    app = app_viva
    _girar(app, 500)
    app.barra.minimizar()
    app.orden("elegir", "barra:desplazar")
    _girar(app, 500)
    assert app.motor.maquina.submodo == K.DESPLAZAR
    assert "terminar" in app.barra.botones and "minimizar" not in app.barra.botones
    assert not app.barra.minimizada and app.barra.win.winfo_viewable()
    app.barra.minimizar()                               # tampoco por otro camino
    assert not app.barra.minimizada
    app.barra.botones["terminar"].invocar()
    _girar(app, 400)
    assert "minimizar" in app.barra.botones


def test_indicador_dice_sin_clic_y_lupa(app_viva):
    ind = app_viva.indicador
    for modo, clave in (("ninguno", "ind_sin_clic"), ("lupa", "ind_lupa")):
        v = VistaMotor(maquina=Vista(estado=K.ACTIVO, modo_clic=modo, puntero=(100, 100)))
        assert ind.contenido(v)[4] == T.t(clave)
    ind.actualizar(VistaMotor(maquina=Vista(estado=K.ACTIVO, modo_clic="ninguno", puntero=(100, 100))))


# =========================================================================== Opciones: velocidad
def test_mas_rapido_y_mas_lento_con_tope_y_cancelar(app_viva):
    app = app_viva
    _girar(app, 300)
    antes = copy.deepcopy(app.cfg.datos)
    cal = copy.deepcopy(antes["perfiles"]["Principal"]["calibracion"])
    ordenes = []
    original = app.orden
    app.orden = lambda *a: (ordenes.append(a), original(*a))
    op = app.abrir_opciones()
    _girar(app, 300)
    lbl, vel = op.etiquetas_valor["puntero.sens_x"]
    assert lbl.cget("text") == "3 de 10"
    reg = app.registro
    for _ in range(10):
        reg.elegir("op:puntero.sens_x:mas", "raton")
    assert lbl.cget("text") == "10 de 10"
    p = op.datos["puntero"]
    assert (p["sens_x"], p["sens_y"], p["joystick_g"]) == OP.sens_de_velocidad(10, 1.2)
    ultima = [o for o in ordenes if o[0] == "config"][-1][1]
    assert ultima["puntero"]["joystick_g"] == 3000                # se prueba en vivo
    for _ in range(12):
        reg.elegir("op:puntero.sens_x:menos", "raton")
    assert lbl.cget("text") == "1 de 10"
    # los botones son grandes (elegibles con la cabeza)
    _girar(app, 400)
    objs = {o.id: o for o in app.motor.maquina.objetivos}
    for ident in ("op:puntero.sens_x:mas", "op:puntero.sens_x:menos"):
        o = objs[ident]
        assert o.rect[3] - o.rect[1] >= 72, (ident, o.rect)
    assert op.datos["perfiles"]["Principal"]["calibracion"] == cal       # la calibración no cambia
    op.cancelar()
    ultima = [o for o in ordenes if o[0] == "config"][-1][1]
    assert ultima["puntero"] == antes["puntero"]
    assert app.cfg.datos["puntero"] == antes["puntero"]


def test_velocidad_arriba_y_abajo_recalcula_la_vertical(app_viva):
    app = app_viva
    op = app.abrir_opciones()
    _girar(app, 200)
    lbl, ctl = op.etiquetas_valor["puntero.ajuste_vertical"]
    assert lbl.cget("text") == "120 % de la de los lados"
    for _ in range(2):
        op.cambiar(ctl, -1)
    assert lbl.cget("text") == "Igual que a los lados"
    assert op.datos["puntero"]["sens_y"] == op.datos["puntero"]["sens_x"] == 1.0
    for _ in range(20):
        op.cambiar(ctl, +1)
    assert op.datos["puntero"]["ajuste_vertical"] == 2.0
    assert op.datos["puntero"]["sens_y"] == 2.0
    for _ in range(30):
        op.cambiar(ctl, -1)
    assert op.datos["puntero"]["ajuste_vertical"] == 0.8
    assert op.datos["puntero"]["sens_y"] == 0.92                 # piso: sigue llegando a los bordes
    op.guardar()
    assert app.cfg.datos["puntero"]["ajuste_vertical"] == 0.8
    assert app.cfg.datos["perfiles"]["Principal"]["calibracion"] == CAL_SINTETICA


def test_pestanas_nuevas_de_opciones_se_arman(app_viva):
    app = app_viva
    op = app.abrir_opciones()
    for p in ("clic", "comodidad"):
        op.ir_a(p)
        for _ in range(3):
            op.ir_pagina(+1)
            bombear(app.root, 20)
    rutas = {c[1] for c in OP.controles("clic")} | {c[1] for c in OP.controles("comodidad")}
    assert {"lupa.aumento", "lupa.zona_px", "lupa.espera_s", "barra.boton_sin_clic", "barra.boton_lupa"} <= rutas
    assert T.t("op_barra_visible") == "Mostrar la barra al abrir"
    op.cancelar()


# =========================================================================== teclado
def test_minimizar_esta_arriba_a_la_derecha_y_no_en_el_barrido():
    assert ACCION_MINIMIZAR in ACCIONES and ACCION_MINIMIZAR not in ACCIONES_FILA
    d = disposicion(distribucion("qwerty"), 1196, 720, acciones_texto=ACCIONES_TEXTO_MINIMIZAR)
    texto = d.fila("texto")
    assert texto[-1].id == "accion:minimizar"
    assert "accion:minimizar" not in [c.id for c in d.fila("acciones")]
    assert "accion:cerrar" in [c.id for c in d.fila("acciones")]
    d2 = disposicion(distribucion("qwerty"), 1196, 720, acciones_texto=ACCIONES_TEXTO)
    assert "accion:minimizar" not in [c.id for c in d2.cajas()]


@pytest.mark.parametrize("ancho,alto", [(1196, 720), (1366, 728), (1040, 728)])
def test_rotulos_minimizar_y_cerrar_caben(root, ancho, alto):  # noqa: F811
    d = disposicion(distribucion("qwerty"), ancho, alto, acciones_texto=ACCIONES_TEXTO_MINIMIZAR)
    h = d.tecla_alto
    f_accion = tkfont.Font(root=root, font=("Segoe UI", max(20, min(22, int(h * 0.22))), "bold"))
    f_fila = tkfont.Font(root=root, font=("Segoe UI", 20))
    caja_min = next(c for c in d.cajas() if c.id == "accion:minimizar")
    caja_cerrar = next(c for c in d.cajas() if c.id == "accion:cerrar")
    # el botón deja 12 px para el borde de resalte y el relleno
    assert f_accion.measure(T.t("tec_minimizar")) <= caja_min.ancho - 12, (ancho, caja_min.ancho)
    assert f_fila.measure(T.t("tec_cerrar")) <= caja_cerrar.ancho - 12
    assert caja_min.alto >= 72


def _teclado(app):
    _girar(app, 300)
    app.alternar_teclado()
    _girar(app, 400)
    return app.teclado


def test_minimizar_conserva_el_texto_y_restaurar_lo_devuelve(app_viva):
    app = app_viva
    tec = _teclado(app)
    assert app.motor.maquina.submodo == K.TECLADO
    assert "accion:minimizar" in tec.botones
    # con el teclado abierto la barra no muestra Sin clic ni Lupa (y cabe en una columna)
    assert "sin_clic" not in app.barra.botones and app.barra.medidas[3] == 1
    for c in "hola":
        _elegir(app, f"tecla:{c}")
    texto = tec.escritura.texto
    assert texto.lower() == "hola"
    _elegir(app, "accion:minimizar")
    _girar(app, 500)
    assert tec.minimizado and not tec.win.winfo_viewable()
    assert tec.pestana is not None and tec.pestana.winfo_viewable()
    assert app.motor.maquina.submodo == K.NORMAL            # el puntero manda otra vez
    assert app.teclado is tec
    assert "sin_clic" in app.barra.botones                  # la barra vuelve a estar completa
    objs = {o.id: o for o in app.motor.maquina.objetivos}
    assert "ui:teclado_mostrar" in objs and "tecla:a" not in objs
    o = objs["ui:teclado_mostrar"]
    assert o.tiempo_s == 0.6 and o.rect[2] - o.rect[0] >= 160 and o.rect[3] - o.rect[1] >= 56
    assert T.t("tec_pestana") == "Teclado"
    # la pestaña con la cabeza lo restaura con el texto
    app.atender(Elegir("ui:teclado_mostrar"))
    _girar(app, 400)
    assert not tec.minimizado and tec.win.winfo_viewable() and tec.pestana is None
    assert tec.escritura.texto == texto
    assert app.motor.maquina.submodo == K.TECLADO
    assert "sin_clic" not in app.barra.botones


def test_la_barra_y_el_atajo_restauran_en_vez_de_abrir_uno_vacio(app_viva):
    app = app_viva
    tec = _teclado(app)
    _elegir(app, "tecla:s")
    _elegir(app, "accion:minimizar")
    _girar(app, 300)
    app.orden("elegir", "barra:teclado")                     # «Teclado» en la barra
    _girar(app, 500)
    assert app.teclado is tec and not tec.minimizado and tec.escritura.texto.lower() == "s"
    tec.minimizar()
    app._atender_atajo("teclado")                            # el atajo del cuidador
    _girar(app, 300)
    assert app.teclado is tec and not tec.minimizado
    # «Cerrar» sigue cerrando como siempre
    _elegir(app, "accion:cerrar")
    _girar(app, 300)
    assert app.teclado is None and app.motor.maquina.submodo == K.NORMAL
    assert "sin_clic" in app.barra.botones


def test_con_barrido_o_solo_comunicacion_no_se_ofrece_minimizar(app_viva):
    app = app_viva
    for clave in ("barrido", "solo_comunicacion"):
        app.cfg.datos["teclado"][clave] = True
        tec = _teclado(app)
        assert "accion:minimizar" not in tec.botones
        assert all("accion:minimizar" not in f for f in tec.filas_barrido())
        tec.minimizar()                                      # tampoco por otro camino
        assert not tec.minimizado
        app.cfg.datos["teclado"][clave] = False
        app.cfg.datos["teclado"]["solo_comunicacion"] = False
        app.cerrar_teclado()
        _girar(app, 200)


def test_opciones_mientras_el_teclado_esta_minimizado_no_lo_muestra(app_viva):
    app = app_viva
    tec = _teclado(app)
    tec.minimizar()
    tec.reconstruir()
    _girar(app, 200)
    assert tec.minimizado and not tec.win.winfo_viewable()
    tec.restaurar()
    _girar(app, 200)
    assert tec.win.winfo_viewable()


# =========================================================================== lupa
def _imagen_prueba(zona):
    from PIL import Image
    return Image.new("RGB", (zona[2] - zona[0], zona[3] - zona[1]), (40, 120, 200))


def _abrir_lupa(app):
    mon = app.motor.maquina.mapeo.monitor
    z = L.zona((300, 300), mon.rect, 200)
    u = L.ubicar_ventana(z, mon.rect, 3)
    return z, u, L.id_abrir(z, u)


def test_ventana_de_la_lupa_en_su_lugar_y_sin_tapar_la_zona(app_viva):
    app = app_viva
    app.capturar_lupa = _imagen_prueba             # nunca se captura la pantalla real en las pruebas
    _girar(app, 300)
    z, u, ident = _abrir_lupa(app)
    app.atender(Elegir(ident))
    _girar(app, 400)
    lp = app.lupa
    assert lp is not None
    objs = {o.id: o for o in app.registro.calcular()}
    assert objs[L.ID_ZONA].rect == u.imagen, (objs[L.ID_ZONA].rect, u.imagen)
    assert objs["ventana:lupa"].rect == u.ventana
    c = objs[L.ID_CERRAR].rect
    assert c[3] - c[1] >= 72 and not L.se_cruzan(c, z)
    assert not L.se_cruzan(objs["ventana:lupa"].rect, z)
    # «Cerrar lupa» con el ratón: cierra y avisa a la máquina
    ordenes = []
    original = app.orden
    app.orden = lambda *a: (ordenes.append(a), original(*a))
    lp.boton_cerrar.invocar()
    _girar(app, 200)
    assert app.lupa is None and ("lupa_cerrar",) in ordenes
    assert L.ID_ZONA not in {o.id for o in app.registro.calcular()}


def test_si_la_captura_falla_avisa_a_la_maquina(app_viva):
    app = app_viva
    _girar(app, 200)

    def falla(_zona):
        raise OSError("pantalla protegida")
    app.capturar_lupa = falla
    ordenes = []
    original = app.orden
    app.orden = lambda *a: (ordenes.append(a), original(*a))
    _z, _u, ident = _abrir_lupa(app)
    app.atender(Elegir(ident))
    assert app.lupa is None and ("lupa_fallo",) in ordenes
    app.atender(Elegir("lupa:abrir@basura"))
    assert app.lupa is None and ordenes.count(("lupa_fallo",)) == 2


def test_la_lupa_se_cierra_si_la_maquina_ya_no_esta_en_lupa(app_viva):
    app = app_viva
    app.capturar_lupa = _imagen_prueba
    _girar(app, 300)
    _z, _u, ident = _abrir_lupa(app)
    app.atender(Elegir(ident))
    assert app.lupa is not None
    app.lupa.visto = True
    _girar(app, 300)                                   # la máquina sigue en NORMAL
    assert app.lupa is None
    # sin ninguna vista en LUPA, se cierra a los 1,5 s igual
    app.atender(Elegir(ident))
    assert app.lupa is not None
    _girar(app, 1800)
    assert app.lupa is None


def test_lupa_completa_con_el_motor(tmp_path):
    """De punta a punta con el motor: modo Lupa, la cabeza (sintética) se queda quieta, la
    máquina abre la lupa en vez de hacer clic, la interfaz la muestra y abrir Opciones la cierra
    sin clic."""
    from conftest import verificar_invariantes
    from test_interfaz import _app
    # la cabeza se mueve al empezar (para armar la permanencia) y después se queda quieta
    t0 = []

    def cabeza(t):
        if not t0:
            t0.append(t)
        r = t - t0[0]          # el reloj de la cámara es el del sistema: se cuenta desde el primer cuadro
        return {"yaw": 2.0 + (3.0 * math.sin(2.5 * r) * (4.0 - r) / 4.0 if r < 4.0 else 0.0)}
    app = _app(tmp_path, funcion=cabeza)
    app.capturar_lupa = _imagen_prueba
    app.motor.start()
    try:
        app.construir_interfaz()
    except tk.TclError as e:
        app.finalizar()
        pytest.skip(f"sin pantalla ({e})")
    try:
        m = app.motor.maquina
        app.orden("elegir", "barra:lupa")
        fin = 0
        while app.lupa is None and fin < 100:
            _girar(app, 100)
            fin += 1
        assert app.lupa is not None, (m.submodo, m.modo_clic, m.estado, m.puntero.posicion, m.vista.permanencia,
                                      [(o.id, o.rect) for o in m.objetivos if o.id.startswith("ventana:")])
        assert m.submodo == K.LUPA
        assert not any(ev[0] == "boton" for _, ev in app.salida.eventos)       # ningún clic
        objs = {o.id for o in app.motor.maquina.objetivos}
        _girar(app, 400)
        objs = {o.id for o in app.motor.maquina.objetivos}
        assert L.ID_ZONA in objs and L.ID_CERRAR in objs and "ventana:lupa" in objs
        app.abrir_opciones()
        _girar(app, 500)
        assert m.submodo == K.NORMAL and app.lupa is None
        assert not any(ev[0] == "boton" for _, ev in app.salida.eventos)
        app.opciones.cancelar()
    finally:
        if not app.cerrando:
            app.salir_seguro()
        app.finalizar()
    verificar_invariantes(app.salida)


def test_la_imagen_de_la_lupa_no_se_guarda_en_disco(app_viva, tmp_path):
    import os
    app = app_viva
    app.capturar_lupa = _imagen_prueba
    datos = os.environ["LYCAN_FACE_DATOS"]
    antes = set()
    for raiz, _d, archivos in os.walk(datos):
        antes |= {os.path.join(raiz, a) for a in archivos}
    _z, _u, ident = _abrir_lupa(app)
    app.atender(Elegir(ident))
    _girar(app, 200)
    app.cerrar_lupa()
    despues = set()
    for raiz, _d, archivos in os.walk(datos):
        despues |= {os.path.join(raiz, a) for a in archivos}
    nuevos = [x for x in despues - antes if x.lower().endswith((".png", ".jpg", ".bmp", ".gif"))]
    assert nuevos == []
    import inspect
    from lycan_face_control.ui import lupa as UL
    fuente = inspect.getsource(UL)
    assert ".save(" not in fuente
