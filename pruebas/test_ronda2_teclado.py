"""Ronda 2 de arreglos: teclado (urgencia siempre audible, mensaje nuevo tras Hablar, avisos dentro
del teclado, modo Directo sin desfase, números y signos) y predicción (ñ escrita como n)."""
from __future__ import annotations

from types import SimpleNamespace

from lycan_face_control import constantes as K
from lycan_face_control.gestos import ResultadoGestos
from lycan_face_control.prediccion import Prediccion
from lycan_face_control.teclado_logica import (DISTRIBUCIONES, NUMEROS, TECLA_MIN_PX, Escritura, buscar_tecla,
                                               disposicion)
from lycan_face_control.ui.textos import t
from test_interfaz import _girar
from test_teclado import _elegir, app_tec  # noqa: F401  (fixture)


def _escribir(e, cadena):
    for c in cadena:
        e.pulsar(buscar_tecla("tecla:espacio") if c == " " else buscar_tecla(f"tecla:{c.lower()}"))


# ------------------------------------------------------------ sugerencias tras un signo
def test_sugerencia_despues_de_un_signo_lleva_espacio():
    for signo, esperado in ((".", "Hola. Quiero "), (",", "Hola, quiero "), ("?", "Hola? Quiero ")):
        e = Escritura()
        _escribir(e, "hola")
        e.escribir_caracter(signo)
        e.elegir_sugerencia("quiero")
        assert e.texto == esperado


def test_palabra_anterior_salta_la_coma():
    e = Escritura()
    _escribir(e, "tengo")
    e.escribir_caracter(",")
    assert e.palabra_anterior() == "Tengo"
    e.escribir_caracter(".")
    assert e.palabra_anterior() is None                 # tras un punto empieza otra frase


def test_espacio_tras_una_sugerencia_no_duplica():
    e = Escritura()
    _escribir(e, "ten")
    e.elegir_sugerencia("tengo")
    e.pulsar(buscar_tecla("tecla:espacio"))
    assert e.texto == "Tengo "
    e.pulsar(buscar_tecla("tecla:espacio"))
    assert e.texto == "Tengo  "                         # un segundo espacio a propósito sí


# ------------------------------------------------------------ números y signos
def test_hay_numeros_y_arroba():
    for c in "0123456789@-/:$%+":
        assert buscar_tecla(f"tecla:{c}") is not None, c
    for nombre, filas in DISTRIBUCIONES.items():
        assert any(tc.id == "tecla:numeros" for f in filas for tc in f), nombre
    assert any(tc.id == "tecla:letras" for f in NUMEROS for tc in f)
    assert len(NUMEROS) == len(DISTRIBUCIONES["qwerty"])


def test_pagina_de_numeros_cabe_con_teclas_de_80_px():
    d = disposicion(NUMEROS, 1196, 720)
    for c in d.cajas():
        assert c.ancho >= TECLA_MIN_PX and c.alto >= TECLA_MIN_PX, c


def test_pulsar_123_no_escribe_nada():
    e = Escritura()
    assert e.pulsar(buscar_tecla("tecla:numeros")).vacio and e.texto == ""


# ------------------------------------------------------------ predicción con n en vez de ñ
def test_n_en_vez_de_ene_tambien_sugiere():
    p = Prediccion()
    assert "mañana" in p.sugerir("manan")
    assert "mañana" in p.sugerir("manana")
    assert "año" in p.sugerir("ano") or "años" in p.sugerir("ano")
    assert any(s in p.sugerir("nin") for s in ("niño", "niña", "niños"))
    assert all("ñ" in s for s in p.sugerir("mañ"))        # con la ñ escrita, solo palabras con ñ


# ------------------------------------------------------------ con la aplicación
def _abrir(app):
    _girar(app, 300)
    app.alternar_teclado()
    _girar(app, 300)
    return app.teclado


def test_frase_urgente_se_dice_aunque_las_frases_esten_calladas(app_tec):  # noqa: F811
    app = app_tec
    app.cfg.datos["voz"]["hablar_frases"] = False
    tec = _abrir(app)
    tec.decir_frase({"texto": "¡Ayuda, llamen a alguien!", "urgente": True})
    assert app.hablado[-1] == ("¡Ayuda, llamen a alguien!", True)
    n = len(app.hablado)
    tec.decir_frase({"texto": "Tengo sed", "urgente": False})
    assert len(app.hablado) == n                         # las demás sí respetan la opción


def test_despues_de_hablar_la_primera_letra_empieza_un_mensaje_nuevo(app_tec):  # noqa: F811
    app = app_tec
    tec = _abrir(app)
    for c in "agua":
        _elegir(app, f"tecla:{c}")
    _elegir(app, "accion:hablar")
    assert app.hablado[-1] == ("Agua", False)
    _elegir(app, "tecla:s")
    assert tec.escritura.texto == "S"                    # sin limpiar a mano
    _elegir(app, "accion:repetir")
    assert app.hablado[-1] == ("Agua", False)
    _elegir(app, "accion:deshacer")
    _elegir(app, "accion:deshacer")
    assert tec.escritura.texto == "Agua"                 # lo anterior se recupera
    # un espacio o una coma después de Hablar siguen el mismo mensaje
    _elegir(app, "accion:hablar")
    _elegir(app, "tecla:,")
    assert tec.escritura.texto == "Agua,"


def test_limpiar_sin_confirmar_y_deshacer_lo_recupera(app_tec):  # noqa: F811
    app = app_tec
    tec = _abrir(app)
    for c in "hola":
        _elegir(app, f"tecla:{c}")
    _elegir(app, "accion:limpiar")
    assert tec.escritura.texto == "" and not tec.confirmando
    assert tec.lbl_franja.cget("text") == t("tec_limpiado")
    _elegir(app, "accion:deshacer")
    assert tec.escritura.texto == "Hola"


def test_avisos_y_estado_se_ven_en_el_teclado_sin_tapar_el_texto(app_tec):  # noqa: F811
    app = app_tec
    tec = _abrir(app)
    app.mostrar_aviso(t("aviso_foco_propio"), 8)
    app.root.update()
    assert tec.lbl_franja.winfo_ismapped() and tec.lbl_franja.cget("text") == t("aviso_foco_propio")
    fila = tec.disp.fila("sugerencias")[0]
    assert int(tec.lbl_franja.place_info()["y"]) == fila.y
    assert int(tec.lbl_franja.place_info()["y"]) >= tec.caja_texto.y + tec.caja_texto.alto
    # mientras la franja tapa las sugerencias, no se pueden elegir
    activos = {e.ident for e in app.registro.entradas if e.activo}
    assert not any(i.startswith("sugerencia:") for i in activos)
    tec._franja_aviso = None
    # sin cara un rato: "No veo su cara"
    m = SimpleNamespace(estado=K.SIN_CARA, sin_cara_s=2.0, pausa_auto=False, reanuda_parpadeo=False,
                        gestos=ResultadoGestos(), submodo=K.TECLADO)
    tec.actualizar(SimpleNamespace(maquina=m, camara=None))
    assert tec.lbl_franja.cget("text") == t("tec_sin_cara")
    # un cuadro perdido suelto no la muestra
    m.sin_cara_s = 0.1
    tec.actualizar(SimpleNamespace(maquina=m, camara=None))
    assert not tec.lbl_franja.winfo_ismapped() or tec._franja_mostrada is None
    # pausa automática: se dice que sigue sola (no que cierre los ojos)
    m.estado, m.pausa_auto, m.reanuda_parpadeo = K.PAUSA, True, True
    tec.actualizar(SimpleNamespace(maquina=m, camara=None))
    assert tec.lbl_franja.cget("text") == t("sub_PAUSA_auto")


def test_barrido_detenido_no_tapa_el_texto(app_tec):  # noqa: F811
    app = app_tec
    app.cfg.datos["teclado"]["barrido"] = True
    tec = _abrir(app)
    for c in "hola":
        _elegir(app, f"tecla:{c}")
    tec._pintar_barrido(SimpleNamespace(resaltado=[], volver=False, detenido=True))
    app.root.update()
    assert tec.lbl_franja.cget("text") == t("tec_barrido_detenido")
    assert "cierre los ojos" in t("tec_barrido_detenido").lower()
    assert not tec.lbl_grande.winfo_ismapped()
    tec._pintar_barrido(SimpleNamespace(resaltado=[], volver=False, detenido=False))
    assert tec._franja_mostrada is None


def test_directo_no_se_desfasa_si_el_envio_no_llega(app_tec):  # noqa: F811
    app = app_tec
    app.cfg.datos["teclado"]["modo_escritura"] = "directo"
    tec = _abrir(app)
    app.salida.foco_propio = True                   # Lycan recién abierto: no hay otro programa elegido
    for c in "hola":
        _elegir(app, f"tecla:{c}")
    assert tec.escritura.texto == ""
    assert tec.lbl_franja.cget("text") == t("aviso_foco_propio")
    app.salida.foco_propio = False
    app.motor.escribir("Mi carta")                  # lo que la persona ya tenía en el documento
    _girar(app, 400)
    _elegir(app, "accion:limpiar")
    _elegir(app, "accion:borrar")
    _elegir(app, "accion:deshacer")
    _girar(app, 400)
    assert app.salida.texto() == "Mi carta"


def test_directo_otra_ventana_empieza_mensaje_nuevo(app_tec):  # noqa: F811
    app = app_tec
    app.cfg.datos["teclado"]["modo_escritura"] = "directo"
    tec = _abrir(app)
    app.ultima_externa = 111
    for c in "ab":
        _elegir(app, f"tecla:{c}")
    _girar(app, 300)
    assert app.salida.texto() == "Ab"
    app.ultima_externa = 222                        # eligió otra ventana con la cabeza
    _elegir(app, "accion:limpiar")
    _girar(app, 300)
    assert app.salida.texto() == "Ab"               # no se mandaron retrocesos a la otra ventana
    assert tec.escritura.texto == ""


def test_pagina_de_numeros_y_boton_de_ayuda(app_tec):  # noqa: F811
    app = app_tec
    tec = _abrir(app)
    _elegir(app, "tecla:numeros")
    assert tec.pagina == "numeros" and "tecla:7" in tec.botones
    _elegir(app, "tecla:7")
    _elegir(app, "tecla:@")
    assert tec.escritura.texto == "7@"
    _elegir(app, "tecla:letras")
    assert tec.pagina == "letras" and "tecla:q" in tec.botones
    _elegir(app, "accion:ayuda")
    assert tec.lbl_franja.cget("text") == t("tec_ayuda")
    assert "123" in t("tec_ayuda") and "´" in t("tec_ayuda")
