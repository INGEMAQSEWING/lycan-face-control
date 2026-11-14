"""Parte 4: lógica del teclado (tildes, mayúsculas, borrar, deshacer, sugerencias, medidas) y la
ventana del teclado con la aplicación completa (sin cámara ni ratón reales)."""
from __future__ import annotations

import tkinter as tk

import pytest

from lycan_face_control import constantes as K
from lycan_face_control.teclado_logica import (DISTRIBUCIONES, TECLA_MIN_PX, Cambio, Escritura, buscar_tecla,
                                               diferencia, disposicion, distribucion, nombre_distribucion,
                                               sin_tildes)


def escribir(e: Escritura, cadena: str) -> list[Cambio]:
    """Pulsa las teclas de ``cadena``: ´ = tilde, ⇧ = mayúscula, espacio y letras."""
    cambios = []
    for c in cadena:
        if c == "´":
            cambios.append(e.pulsar(buscar_tecla("tecla:tilde")))
        elif c == "⇧":
            cambios.append(e.pulsar(buscar_tecla("tecla:mayus")))
        elif c == " ":
            cambios.append(e.pulsar(buscar_tecla("tecla:espacio")))
        elif c == "\n":
            cambios.append(e.pulsar(buscar_tecla("tecla:enter")))
        else:
            cambios.append(e.pulsar(buscar_tecla(f"tecla:{c}")))
    return cambios


# --------------------------------------------------------------------------- distribuciones
def test_distribuciones_en_espanol():
    q = DISTRIBUCIONES["qwerty"]
    assert [t.valor for t in q[0]] == list("qwertyuiop")
    assert [t.valor for t in q[1]][-1] == "ñ"
    assert any(t.tipo == "tilde" for t in q[2])
    assert sum(t.ancho for t in q[3]) == 11 and any(t.tipo == "espacio" and t.ancho == 4 for t in q[3])
    f = DISTRIBUCIONES["frecuencia"]
    assert [t.texto for t in f[0]][:7] == ["␣", "E", "A", "O", "S", "R", "N"]
    assert len(f) == 4 and all(8 <= len(r) <= 10 for r in f)
    assert [t.valor for t in f[1]][:7] == list("idlctum")
    letras = {t.valor for r in f for t in r if t.tipo == "letra"}
    assert letras == set("abcdefghijklmnñopqrstuvwxyz")
    # identificadores únicos en cada distribución
    for filas in DISTRIBUCIONES.values():
        ids = [t.id for r in filas for t in r]
        assert len(ids) == len(set(ids))
        assert all(i.startswith("tecla:") for i in ids)


def test_distribucion_auto():
    assert nombre_distribucion({"distribucion": "auto"}, barrido=False) == "qwerty"
    assert nombre_distribucion({"distribucion": "auto"}, barrido=True) == "frecuencia"
    assert nombre_distribucion({"distribucion": "qwerty"}, barrido=True) == "qwerty"
    assert distribucion("rara") is DISTRIBUCIONES["qwerty"]


# --------------------------------------------------------------------------- escritura
def test_tilde_mas_vocal_es_vocal_tildada():
    e = Escritura()
    escribir(e, "cami´on")
    assert e.texto == "Camión"
    e = Escritura(mayuscula_auto=False)
    escribir(e, "´a´e´i´o´u")
    assert e.texto == "áéíóú"


def test_tilde_con_consonante_y_dieresis():
    e = Escritura(mayuscula_auto=False)
    escribir(e, "´n")
    assert e.texto == "n"                                 # sin vocal: la letra sale sin tilde
    escribir(e, " ping´´uino")
    assert e.texto == "n pingüino"


def test_mayuscula_automatica_y_shift():
    e = Escritura()
    escribir(e, "hola. que tal")
    assert e.texto == "Hola. Que tal"
    escribir(e, "?")
    escribir(e, " bien")
    assert e.texto == "Hola. Que tal? Bien"
    e = Escritura()
    e.escribir_caracter("¿")
    escribir(e, "c´omo")
    assert e.texto == "¿Cómo"
    escribir(e, " ⇧juan y ana")
    assert e.texto == "¿Cómo Juan y ana"
    e2 = Escritura()
    escribir(e2, "uno\ndos")
    assert e2.texto == "Uno\nDos"


def test_borrar_borrar_palabra_y_cancelar_tilde():
    e = Escritura(mayuscula_auto=False)
    escribir(e, "tengo sed")
    assert e.borrar() == Cambio(1, "")
    assert e.texto == "tengo se"
    assert e.borrar_palabra() == Cambio(2, "")
    assert e.texto == "tengo "
    e.borrar_palabra()
    assert e.texto == ""
    assert e.borrar() == Cambio()                         # nada que borrar
    escribir(e, "a´")
    assert e.tilde == 1
    e.borrar()                                           # primero cancela la tilde pendiente
    assert e.tilde == 0 and e.texto == "a"
    escribir(e, ",")
    e.borrar_palabra()                                   # un signo suelto se borra solo
    assert e.texto == "a"


def test_deshacer_y_limpiar():
    e = Escritura()
    escribir(e, "hola")
    e.limpiar()
    assert e.texto == ""
    assert e.deshacer() == Cambio(0, "Hola")
    assert e.texto == "Hola"
    e.deshacer()
    assert e.texto == "Hol"
    while e.puede_deshacer():
        e.deshacer()
    assert e.texto == "" and e.deshacer() == Cambio()


def test_sugerencia_reemplaza_y_agrega_espacio():
    e = Escritura()
    escribir(e, "sab")
    c = e.elegir_sugerencia("sábana")
    assert e.texto == "Sábana " and c == Cambio(2, "ábana ")
    escribir(e, "lim")
    e.elegir_sugerencia("limpia")
    assert e.texto == "Sábana limpia "
    escribir(e, ".")                                      # el signo se pega a la palabra
    assert e.texto == "Sábana limpia."
    escribir(e, " ")
    e.elegir_sugerencia("quiero")                          # inicio de frase: mayúscula
    assert e.texto == "Sábana limpia. Quiero "
    e.elegir_sugerencia("BiPAP")
    assert e.texto.endswith("BiPAP ")
    assert e.palabra_anterior() == "BiPAP"


def test_palabra_actual_y_anterior():
    e = Escritura()
    escribir(e, "me duele la cab")
    assert e.palabra_actual() == "cab" and e.palabra_anterior() == "la"
    escribir(e, "eza. ")
    assert e.palabra_actual() == "" and e.palabra_anterior() is None


def test_emoji_y_limite():
    e = Escritura()
    e.escribir_caracter("👍")
    assert e.texto == "👍"
    e.borrar()
    assert e.texto == ""
    e.poner_texto("x" * 5000)
    assert len(e.texto) == 2000
    assert e.escribir_caracter("a") == Cambio()


def test_diferencia_para_modo_directo():
    assert diferencia("hola", "holas") == Cambio(0, "s")
    assert diferencia("hola", "hol") == Cambio(1, "")
    assert diferencia("sab", "sábana ") == Cambio(2, "ábana ")
    assert diferencia("", "") == Cambio() and Cambio().vacio


def test_sin_tildes():
    assert sin_tildes("Sábana") == "sabana"
    assert sin_tildes("PINGÜINO") == "pinguino"
    assert sin_tildes("Ñandú") == "ñandu"


# --------------------------------------------------------------------------- medidas
@pytest.mark.parametrize("nombre", ["qwerty", "frecuencia"])
@pytest.mark.parametrize("ancho,alto", [(1366 - 126, 728), (1366, 728), (1920 - 140, 1040)])
def test_objetivos_sin_solaparse_y_de_80_px(nombre, ancho, alto):
    d = disposicion(distribucion(nombre), ancho, alto)
    cajas = d.cajas()
    assert len({c.id for c in cajas}) == len(cajas)
    for i, a in enumerate(cajas):
        assert a.ancho >= TECLA_MIN_PX and a.alto >= TECLA_MIN_PX, a
        assert a.x >= 0 and a.y >= 0 and a.x + a.ancho <= ancho, a
        for b in cajas[i + 1:]:
            assert not a.se_solapa(b), (a, b)
    assert d.alto <= alto, (d.alto, alto)              # cabe en una pantalla de 1366×768
    ids = {c.id for c in cajas}
    for esperado in ("frase:si", "frase:no", "accion:hablar", "accion:escribir", "accion:borrar",
                     "accion:copiar", "accion:deshacer", "accion:frases", "accion:cerrar", "sugerencia:0",
                     "tecla:ñ", "tecla:tilde"):
        assert esperado in ids, esperado
    # Sí y No grandes y separados (en los extremos de su fila)
    rap = d.fila("rapidas")
    assert rap[0].id == "frase:si" and rap[-1].id == "frase:no"
    assert rap[-1].x - (rap[0].x + rap[0].ancho) > 400


def test_pagina_de_frases():
    filas = [[("frase:cat:0", 1), ("frase:cat:1", 1)], [("frase:1:0", 1), ("frase:1:1", 1), ("frase:1:2", 1)]]
    d = disposicion(distribucion("qwerty"), 1240, 728, pagina="frases", filas_cuerpo=filas)
    ids = [c.id for c in d.cajas()]
    assert "frase:cat:1" in ids and "frase:1:2" in ids and "tecla:q" not in ids


# =========================================================================== ventana del teclado
from test_interfaz import _app, _girar  # noqa: E402

from lycan_face_control.acciones import Elegir  # noqa: E402
from conftest import verificar_invariantes  # noqa: E402


@pytest.fixture
def app_tec(tmp_path):
    app = _app(tmp_path)
    app.motor.start()
    try:
        app.construir_interfaz()
    except tk.TclError as e:
        app.finalizar()
        pytest.skip(f"sin pantalla ({e})")
    hablado = []
    app.hablar = lambda texto, urgente=False: hablado.append((texto, urgente))
    app.hablado = hablado
    yield app
    if not app.cerrando:
        app.salir_seguro()
    app.finalizar()
    assert not app.motor.is_alive()
    verificar_invariantes(app.salida)


def _elegir(app, ident):
    app.atender(Elegir(ident))


def test_teclado_escribe_habla_y_envia(app_tec):
    app = app_tec
    _girar(app, 400)
    app.alternar_teclado()
    tec = app.teclado
    assert tec is not None
    _girar(app, 500)
    assert app.motor.maquina.submodo == K.TECLADO
    ids = {o.id for o in app.motor.maquina.objetivos}
    for esperado in ("tecla:q", "tecla:ñ", "frase:si", "frase:no", "accion:hablar", "ventana:teclado"):
        assert esperado in ids, esperado
    teclas = [o for o in app.motor.maquina.objetivos if o.id.startswith(("tecla:", "accion:", "frase:"))]
    # Teclas grandes: 80 px en pantallas como la del portátil (1366x768 o más). En pantallas
    # más pequeñas (el servidor de GitHub usa 1024x768) se exige al menos 60 px.
    ancho_pantalla = tec.win.winfo_screenwidth() if hasattr(tec, "win") else 1366
    minimo = 80 if ancho_pantalla >= 1280 else 60
    chicas = [(o.id, o.rect) for o in teclas
              if o.rect[2] - o.rect[0] < minimo or o.rect[3] - o.rect[1] < minimo]
    assert not chicas, (ancho_pantalla, chicas[:5])
    # elegir con la cabeza: Ñ, a, n, d, ´, u
    for c in ("ñ", "a", "n", "d", "tilde", "u"):
        _elegir(app, f"tecla:{c}")
    assert tec.escritura.texto == "Ñandú"
    _elegir(app, "accion:hablar")
    assert app.hablado[-1] == ("Ñandú", False)
    _elegir(app, "accion:escribir")
    _girar(app, 400)
    assert app.salida.texto() == "Ñandú"
    _elegir(app, "accion:repetir")
    assert app.hablado[-1] == ("Ñandú", False)
    # sugerencias: "sab" -> sábana
    _elegir(app, "tecla:espacio")
    for c in "sab":
        _elegir(app, f"tecla:{c}")
    assert any(s.lower() == "sábana" for s in tec._sugerencias), tec._sugerencias
    i = [s.lower() for s in tec._sugerencias].index("sábana")
    _elegir(app, f"sugerencia:{i}")
    assert tec.escritura.texto == "Ñandú sábana "
    # borrar, deshacer y limpiar (sin confirmar desde la ronda 2: «Deshacer» lo recupera)
    _elegir(app, "accion:palabra")
    assert tec.escritura.texto == "Ñandú "
    _elegir(app, "accion:deshacer")
    assert tec.escritura.texto == "Ñandú sábana "
    _elegir(app, "accion:limpiar")
    assert not tec.confirmando and tec.escritura.texto == ""
    _elegir(app, "accion:deshacer")
    assert tec.escritura.texto == "Ñandú sábana "
    _elegir(app, "accion:limpiar")
    assert tec.escritura.texto == ""
    # Sí y No dicen en voz alta y se muestran en grande
    _elegir(app, "frase:si")
    assert app.hablado[-1] == ("Sí", False)
    assert tec.lbl_grande.cget("text") == "Sí"
    # el gesto "borrar" (la máquina avisa accion:borrar)
    _elegir(app, "tecla:a")
    _elegir(app, "accion:borrar")
    assert tec.escritura.texto == ""
    app.alternar_teclado()
    _girar(app, 400)
    assert app.teclado is None and app.motor.maquina.submodo == K.NORMAL
    assert not any(o.id.startswith("tecla:") for o in app.motor.maquina.objetivos)


def test_teclado_frases_urgencia_y_cuidador(app_tec):
    app = app_tec
    app.cfg.datos["teclado"]["cuidador"] = "Marta"
    app.alternar_teclado()
    tec = app.teclado
    _girar(app, 300)
    # fila rápida
    textos = [tec.botones[f"frase:rapida:{i}"].texto for i in range(5)]
    assert "Tengo sed" in textos and "Llamar a Marta" in textos
    _elegir(app, f"frase:rapida:{textos.index('Tengo sed')}")
    assert app.hablado[-1] == ("Tengo sed", False)
    # página de frases: categoría Urgencia
    _elegir(app, "accion:frases")
    assert tec.pagina == "frases"
    nombres = app.obtener_frases().nombres()
    _elegir(app, f"frase:cat:{nombres.index('Urgencia')}")
    _girar(app, 200)
    urg = [i for i, fr in tec._frases_visibles.items() if fr.get("urgente")]
    _elegir(app, urg[0])
    assert app.hablado[-1][1] is True                     # urgente: alerta y volumen máximo
    # género
    app.cfg.datos["teclado"]["genero"] = "femenino"
    _elegir(app, f"frase:cat:{nombres.index('Afecto')}")
    textos = [fr for fr in tec._frases_visibles.values()]
    assert any(tec._texto_frase(fr) == "Estoy cansada" for fr in textos)
    _elegir(app, "accion:frases")
    assert tec.pagina == "letras" and "tecla:q" in tec.botones


def test_teclado_modo_directo(app_tec):
    app = app_tec
    app.cfg.datos["teclado"]["modo_escritura"] = "directo"
    app.alternar_teclado()
    _girar(app, 300)
    for c in ("h", "o", "l", "a"):
        _elegir(app, f"tecla:{c}")
    _elegir(app, "accion:borrar")
    _girar(app, 400)
    assert app.salida.texto() == "Hol"
    assert app.teclado.botones["accion:escribir"].texto == "Nuevo"


def test_teclado_copiar(app_tec):
    app = app_tec
    copiado = []
    app.copiar_prueba = lambda texto: copiado.append(texto) or True
    app.alternar_teclado()
    _girar(app, 200)
    _elegir(app, "accion:copiar")                          # sin texto: no copia
    assert copiado == []
    _elegir(app, "tecla:s")
    _elegir(app, "tecla:i")
    _elegir(app, "accion:copiar")
    assert copiado == ["Si"]


def test_teclado_barrido_elige_fila_y_tecla(app_tec, monkeypatch):
    import lycan_face_control.ui.teclado as modulo
    app = app_tec
    app.cfg.datos["teclado"]["barrido"] = True
    reloj = [1000.0]
    monkeypatch.setattr(modulo, "_ahora", lambda: reloj[0])
    app.alternar_teclado()
    tec = app.teclado
    _girar(app, 400)
    assert app.motor.maquina.submodo == K.BARRIDO
    assert tec.nombre_dist == "frecuencia"
    filas = tec.barrido.filas
    assert filas[0][:2] == ["frase:si", "frase:no"]
    assert any(f[0] == "tecla:espacio" for f in filas)
    # primera fila (Sí, No...) iluminada: elegirla y luego elegir "Sí"
    vista = app.ultima_vista
    tec.actualizar(vista)
    assert "frase:si" in tec._resaltados
    _elegir(app, "barrido:elegir")
    assert tec.barrido.nivel == "elementos" and tec._resaltados == {"frase:si"}
    _elegir(app, "barrido:elegir")
    assert app.hablado[-1] == ("Sí", False)
    # avanza solo hasta la fila de letras "e a o..." y elige la "e"
    reloj[0] += 1.0
    i_letras = next(i for i, f in enumerate(filas) if "tecla:e" in f)
    while tec.barrido.fila != i_letras:
        reloj[0] += 0.5
        tec.actualizar(app.ultima_vista)
    _elegir(app, "barrido:elegir")
    while tec._resaltados != {"tecla:e"}:
        reloj[0] += 0.5
        tec.actualizar(app.ultima_vista)
    _elegir(app, "barrido:elegir")
    assert tec.escritura.texto == "E"
    # salir del barrido desde el teclado
    tec.accion("barrido")
    _girar(app, 300)
    assert app.motor.maquina.submodo == K.TECLADO and tec.barrido is None


def test_solo_comunicacion_no_se_cierra(app_tec):
    app = app_tec
    import copy
    d = copy.deepcopy(app.cfg.datos)
    d["teclado"]["solo_comunicacion"] = True
    app.aplicar_config(d)
    _girar(app, 400)
    assert app.teclado is not None
    assert app.motor.maquina.submodo == K.SOLO_COMUNICACION
    app.alternar_teclado()                                  # gesto o atajo: no lo cierra
    assert app.teclado is not None
    app.teclado.accion("cerrar")
    assert app.teclado is not None


def test_editor_de_frases(app_tec):
    app = app_tec
    ed = app.abrir_editor_frases()
    _girar(app, 200)
    ed.cat = 0
    ed._pintar()
    n = len(app.obtener_frases().frases(0))
    ed.var.set("Quiero agua con hielo")
    ed.agregar()
    assert len(app.obtener_frases().frases(0)) == n + 1
    ed.var.set("")
    ed.agregar()                                           # vacía: no se agrega y avisa
    assert ed.lbl_aviso.cget("text")
    assert ed.guardar()
    assert app.frases.ruta.exists()
    ed.olvidar()                                           # pide confirmación
    assert ed.preguntando == "olvidar"
    ed.olvidar()
    assert ed.preguntando is None
    ed.cerrar()
    assert app.editor is None
    from lycan_face_control.frases import Frases
    f = Frases(app.frases.ruta)
    f.cargar()
    assert any(fr["texto"] == "Quiero agua con hielo" for fr in f.frases(0))


def test_en_pausa_el_boton_pausa_del_teclado_reanuda(app_tec):
    app = app_tec
    app.alternar_teclado()
    tec = app.teclado
    _girar(app, 300)
    _elegir(app, "accion:pausa")
    _girar(app, 400)
    assert app.motor.maquina.estado == K.PAUSA
    b = tec.botones["accion:pausa"]
    assert b.texto == "Reanudar"
    _girar(app, 300)
    assert "teclado:reanudar" in {o.id for o in app.motor.maquina.objetivos}
    b.invocar()                                             # el cuidador con el ratón
    _girar(app, 400)
    assert app.motor.maquina.estado == K.ACTIVO
    assert b.texto == "Pausa"


def test_la_siguiente_palabra_no_repite_la_anterior():
    from lycan_face_control.prediccion import Prediccion
    p = Prediccion([("de", 100), ("que", 90), ("hola", 80), ("no", 70), ("la", 60), ("el", 50)])
    p.aprender_par(None, "hola")
    assert "hola" not in [s.lower() for s in p.sugerir("", "Hola")]
