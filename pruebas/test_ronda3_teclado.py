"""Ronda 3 de arreglos: teclado y voz (el barrido no se reinicia con los avisos, la tilde y ⇧
empiezan el mensaje nuevo, Ayuda del barrido, ⇧ en «las más usadas», repetición de teclas,
mensaje al máximo, la voz que no arranca y el texto largo que no se dijo) y textos de Opciones."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from conftest import Sim, medidas
from lycan_face_control import constantes as K
from lycan_face_control.acciones import Elegir
from lycan_face_control.barrido import Barrido
from lycan_face_control.gestos import ResultadoGestos
from lycan_face_control.permanencia import Objetivo, Permanencia
from lycan_face_control.sistema.voz import Voz
from lycan_face_control.teclado_logica import DISTRIBUCIONES, MAX_TEXTO, Escritura, buscar_tecla
from lycan_face_control.ui.textos import TXT, t
from test_interfaz import _girar
from test_teclado import _elegir, app_tec  # noqa: F401  (fixture)

import lycan_face_control.ui.teclado as modulo


def _reloj(monkeypatch):
    reloj = [1000.0]
    monkeypatch.setattr(modulo, "_ahora", lambda: reloj[0])
    return reloj


def _vista_activa():
    m = SimpleNamespace(estado=K.ACTIVO, sin_cara_s=0.0, pausa_auto=False, reanuda_parpadeo=False,
                        gestos=ResultadoGestos(), submodo=K.BARRIDO, motivo_pausa="")
    return SimpleNamespace(maquina=m, camara=None)


# ------------------------------------------------------------ barrido y franja
def test_poner_filas_conserva_la_fila_y_el_elemento_aunque_cambie_el_numero_de_filas():
    filas = [["a", "b"], ["s1", "s2"], ["x", "y", "z"], ["fin"]]
    b = Barrido(filas, 1.0, 0.0)
    b.nivel, b.fila, b.elemento = "elementos", 2, 1
    b.poner_filas([["a", "b"], ["x", "y", "z"], ["fin"]], 5.0, conservar=True)   # se fue la fila 1
    assert (b.nivel, b.fila, b.elemento) == ("elementos", 1, 1)
    b.poner_filas(filas, 6.0, conservar=True)                                     # volvió
    assert (b.nivel, b.fila, b.elemento) == ("elementos", 2, 1)
    b.nivel, b.fila, b.elemento = "filas", 3, -1
    b.poner_filas([["a", "b"], ["x", "y", "z"], ["fin"]], 7.0, conservar=True)
    assert (b.nivel, b.fila) == ("filas", 2)
    # sin conservar, o si la fila en la que estaba ya no existe, vuelve a empezar
    b.nivel, b.fila, b.elemento = "elementos", 1, 0
    b.poner_filas([["otra"]], 8.0, conservar=True)
    assert (b.nivel, b.fila) == ("filas", 0)


def test_un_aviso_no_saca_al_barrido_de_la_fila(app_tec, monkeypatch):
    app = app_tec
    app.cfg.datos["teclado"]["barrido"] = True
    reloj = _reloj(monkeypatch)
    app.alternar_teclado()
    tec = app.teclado
    _girar(app, 300)
    filas = tec.barrido.filas
    i_letras = next(i for i, f in enumerate(filas) if "tecla:s" in f)
    v = _vista_activa()
    while tec.barrido.fila != i_letras:
        reloj[0] += 0.5
        tec.actualizar(v)
    _elegir(app, "barrido:elegir")
    reloj[0] += 0.1
    tec.actualizar(v)
    while tec._resaltados != {"tecla:o"}:
        reloj[0] += 0.5
        tec.actualizar(v)
    fila = tec.barrido.fila
    tec.mostrar_aviso("algo", 2)                  # aparece la franja (tapa las sugerencias)
    assert tec.barrido.nivel == "elementos" and "tecla:o" in tec._resaltados
    reloj[0] += 2.5                               # y se va
    tec.actualizar(v)
    assert tec.barrido.nivel == "elementos"
    assert tec.barrido.filas[tec.barrido.fila] == filas[fila]


def test_al_vencer_limpiar_el_barrido_sigue_en_la_fila(app_tec, monkeypatch):
    app = app_tec
    app.cfg.datos["teclado"]["barrido"] = True
    reloj = _reloj(monkeypatch)
    app.alternar_teclado()
    tec = app.teclado
    _girar(app, 200)
    for c in "hola":
        _elegir(app, f"tecla:{c}")
    _elegir(app, "accion:limpiar")
    v = _vista_activa()
    tec.barrido.reiniciar(reloj[0])
    tec.actualizar(v)
    tec.barrido.actualizar(reloj[0], False, "elegir")
    assert tec.barrido.nivel == "elementos"
    for _ in range(10):                           # 5 s: la franja de «Borré el texto» se va a los 4 s
        reloj[0] += 0.5
        tec.actualizar(v)
    assert tec._franja_mostrada is None
    assert tec.barrido.nivel == "elementos"


def test_ayuda_en_barrido_habla_de_los_ojos(app_tec):
    app = app_tec
    app.cfg.datos["teclado"]["barrido"] = True
    app.alternar_teclado()
    tec = app.teclado
    _girar(app, 200)
    tec.accion("ayuda")
    txt = tec.lbl_franja.cget("text")
    assert txt == t("tec_ayuda_barrido")
    assert "quieto" not in txt.lower() and "ojos" in txt


# ------------------------------------------------------------ mensaje nuevo tras Hablar
@pytest.mark.parametrize("primera,esperado", (("tilde", "Á"), ("mayus", "A")))
def test_tilde_o_mayuscula_despues_de_hablar_empiezan_mensaje_nuevo(app_tec, primera, esperado):
    app = app_tec
    app.alternar_teclado()
    tec = app.teclado
    _girar(app, 200)
    for c in "hola":
        _elegir(app, f"tecla:{c}")
    _elegir(app, "accion:hablar")
    _elegir(app, f"tecla:{primera}")
    _elegir(app, "tecla:a")
    assert tec.escritura.texto == esperado


def test_coma_despues_de_hablar_sigue_el_mismo_mensaje(app_tec):
    app = app_tec
    app.alternar_teclado()
    tec = app.teclado
    _girar(app, 200)
    for c in "hola":
        _elegir(app, f"tecla:{c}")
    _elegir(app, "accion:hablar")
    _elegir(app, "tecla:,")
    assert tec.escritura.texto == "Hola,"


# ------------------------------------------------------------ distribución con barrido
def test_las_mas_usadas_traen_mayuscula_y_enter():
    ids = {tc.id for f in DISTRIBUCIONES["frecuencia"] for tc in f}
    assert "tecla:mayus" in ids and "tecla:enter" in ids
    assert max(len(f) for f in DISTRIBUCIONES["frecuencia"]) <= 10


def test_con_barrido_se_puede_escribir_un_nombre_con_mayuscula(app_tec):
    app = app_tec
    app.cfg.datos["teclado"]["barrido"] = True
    app.alternar_teclado()
    tec = app.teclado
    _girar(app, 200)
    assert "tecla:mayus" in tec.botones
    for ident in ("tecla:a", "tecla:espacio", "tecla:mayus", "tecla:m", "tecla:a"):
        _elegir(app, ident)
    assert tec.escritura.texto == "A Ma"


# ------------------------------------------------------------ repetición de teclas
def _quieto_sobre(cfg_cambios, ident, segundos=20.0):
    from conftest import cfg_prueba
    s = Sim(cfg_prueba(**cfg_cambios))
    s.orden("poner_submodo", K.TECLADO)
    s.quieto(1.0)
    x, y = map(int, s.maquina.puntero.posicion)
    s.maquina.poner_objetivos([Objetivo(ident, (x - 60, y - 50, x + 60, y + 50))])
    s.limpiar()
    s.quieto(segundos)
    return [e for e in s.elegidos() if e == ident]


def test_quedarse_sobre_una_tecla_la_escribe_una_sola_vez():
    assert len(_quieto_sobre({}, "tecla:a")) == 1


def test_con_repeticion_encendida_repite_despacio_y_con_tope():
    assert len(_quieto_sobre({"teclado.repetir_teclas": True}, "tecla:a")) == 3     # 1 + 2 repeticiones
    p = Permanencia(tiempo_objetivo_s=1.0, repetir_teclas=True)
    o = Objetivo("tecla:a", (0, 0, 100, 100))
    disparos = [k / 20 for k in range(200) if p.actualizar((50, 50), k / 20, o).disparo]
    assert disparos[1] - disparos[0] >= 2.4      # la repetición espera 2,5 veces más


@pytest.mark.parametrize("ident", ("tecla:espacio", "tecla:enter"))
def test_espacio_y_enter_nunca_se_repiten(ident):
    assert len(_quieto_sobre({"teclado.repetir_teclas": True}, ident)) == 1


def test_un_cuadro_de_temblor_fuera_del_boton_no_reinicia_el_contador():
    p = Permanencia(tiempo_objetivo_s=1.0)
    o = Objetivo("barra:clic", (0, 0, 100, 100))
    disparo = None
    for k in range(40):
        t = k / 20
        afuera = k in (8, 15)                    # dos cuadros sueltos fuera del botón
        st = p.actualizar((150, 50) if afuera else (50, 50), t, None if afuera else o)
        if st.disparo:
            disparo = t
            break
    assert disparo is not None and disparo <= 1.05


def test_salir_del_boton_de_verdad_si_reinicia():
    p = Permanencia(tiempo_objetivo_s=1.0)
    o = Objetivo("barra:clic", (0, 0, 100, 100))
    disparos = []
    for k in range(60):
        t = k / 20
        afuera = 10 <= k < 20                    # medio segundo fuera
        st = p.actualizar((150, 50) if afuera else (50, 50), t, None if afuera else o)
        if st.disparo:
            disparos.append(t)
    assert disparos and disparos[0] >= 1.9


# ------------------------------------------------------------ mensaje al máximo
def test_una_sugerencia_que_no_cabe_no_queda_cortada():
    e = Escritura()
    e.texto = "a" * (MAX_TEXTO - 2) + " "
    c = e.elegir_sugerencia("cobija")
    assert c.vacio and e.texto.endswith("a ") and e.rechazado


def test_al_llegar_al_maximo_avisa(app_tec):
    app = app_tec
    app.alternar_teclado()
    tec = app.teclado
    _girar(app, 200)
    tec.escritura.texto = "a" * MAX_TEXTO
    _elegir(app, "tecla:b")
    assert tec.lbl_franja.cget("text") == t("tec_lleno")


# ------------------------------------------------------------ voz
def test_la_voz_que_no_arranca_no_pierde_la_frase_en_silencio():
    import time

    def sapi():
        raise OSError("no")

    def respaldo(_voz=None):
        time.sleep(0.6)
        raise OSError("no")

    v = Voz({}, crear_sapi=sapi, crear_respaldo=respaldo, listar=lambda: [])
    t0 = time.monotonic()
    v.hablar("Tengo dolor")
    assert time.monotonic() - t0 < 1.0          # no congela la interfaz 2 s
    fin = time.monotonic() + 3
    while v.fallidos.empty() and time.monotonic() < fin:
        time.sleep(0.05)
    assert v.fallidos.get_nowait() == "Tengo dolor"
    v.cerrar()


def test_mensaje_largo_que_no_se_dijo_se_ve_entero(app_tec):
    app = app_tec
    app.alternar_teclado()
    tec = app.teclado
    _girar(app, 200)
    tec.escritura.texto = ("palabra " * 120).strip()
    tec._pintar_texto()
    del app.hablar                                # la de verdad, con una voz que falla
    app.voz = SimpleNamespace(hablar=lambda texto, urgente=False: False, voz_espanol=True)
    _elegir(app, "accion:hablar")
    app.root.update()
    g = tec.lbl_grande
    txt = g.cget("text")
    # entero si cabe; si no, el final (el mensaje completo sigue en la caja y en la ventana)
    assert txt == tec.escritura.texto or (txt.startswith("…") and tec.escritura.texto.endswith(txt[1:]))
    assert g.winfo_reqheight() <= tec.caja_texto.alto + 4
    assert g.winfo_ismapped()
    assert tec.lbl_franja.cget("text") == t("aviso_no_dicho")


# ------------------------------------------------------------ textos de Opciones
def test_mensaje_corto_que_no_se_dijo_se_ve_entero(app_tec):
    app = app_tec
    app.alternar_teclado()
    tec = app.teclado
    _girar(app, 200)
    del app.hablar
    app.voz = SimpleNamespace(hablar=lambda texto, urgente=False: False, voz_espanol=True)
    for c in "tengo sed":
        _elegir(app, "tecla:espacio" if c == " " else f"tecla:{c}")
    _elegir(app, "accion:hablar")
    app.root.update()
    assert tec.lbl_grande.cget("text") == "Tengo sed"


def test_textos_de_atajos_con_usted_y_sin_jerga(monkeypatch):
    from lycan_face_control.ui import opciones as OP
    monkeypatch.setattr("lycan_face_control.sistema.atajos.produce_caracter", lambda *a: "@")
    m = OP.atajos_validos({"pausar": "Ctrl+Alt+Q"})
    assert m == t("op_atajo_escribe", texto="Ctrl+Alt+Q", car="@")
    monkeypatch.setattr("lycan_face_control.sistema.atajos.produce_caracter", lambda *a: "´")
    assert OP.atajos_validos({"pausar": "Ctrl+Alt+Q"}) == t("op_atajo_acento", texto="Ctrl+Alt+Q")
    assert OP.atajos_validos({"pausar": ""}) == t("op_atajo_vacio")
    m = OP.atajos_validos({"pausar": "Alt+Shift+Ñ"}, revisar_teclado=False)
    assert "tecla muerta" not in m and "desconocida" not in m and "ñ" in m


def test_etiqueta_del_paso_del_barrido_dice_que_mas_es_mas_lento():
    assert "lento" in TXT["op_barrido_paso"]
