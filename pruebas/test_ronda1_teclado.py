"""Ronda 1 de arreglos: teclado, barrido y frases (con la aplicación completa, sin cámara)."""
from __future__ import annotations

import pytest

from lycan_face_control.barrido import CONGELAR_MAX_S, Barrido
from lycan_face_control.teclado_logica import Escritura, buscar_tecla
from test_interfaz import _girar
from test_teclado import _elegir, app_tec  # noqa: F401  (fixture)


# ------------------------------------------------------------------ barrido (lógica pura)
def test_barrido_no_se_traba_con_los_ojos_entrecerrados():
    b = Barrido([["a", "b"], ["c", "d"], ["e"]], 1.5, t0=0.0)
    t = 0.0
    filas = set()
    while t < 60.0:
        t += 0.1
        filas.add(b.actualizar(t, True, None).fila)
    assert len(filas) > 1                      # siguió avanzando
    # un cierre normal sí congela (menos del tope)
    b = Barrido([["a", "b"], ["c", "d"], ["e"]], 1.5, t0=0.0)
    t = 0.0
    while t < CONGELAR_MAX_S - 0.5:
        t += 0.1
        est = b.actualizar(t, True, None)
    assert est.congelado and est.fila == 0


# ------------------------------------------------------------------ escritura
def test_nuevo_mensaje_no_deja_pasos_de_deshacer():
    e = Escritura()
    for c in "hola":
        e.pulsar(buscar_tecla(f"tecla:{c}"))
    e.nuevo_mensaje()
    assert e.texto == "" and not e.puede_deshacer()


def _esperar(app, condicion, ms=5000):
    """Gira la interfaz hasta que se cumpla ``condicion()`` (el motor va en su hilo)."""
    import time
    fin = time.monotonic() + ms / 1000
    while time.monotonic() < fin and not condicion():
        _girar(app, 50)
    return condicion()


@pytest.fixture
def app_directo(app_tec):  # noqa: F811
    app = app_tec
    app.cfg.datos["teclado"]["modo_escritura"] = "directo"
    _girar(app, 300)
    app.alternar_teclado()
    _girar(app, 300)
    return app


def test_directo_nuevo_y_deshacer_no_duplica(app_directo):
    app = app_directo
    for c in "hola":
        _elegir(app, f"tecla:{c}")
    assert _esperar(app, lambda: app.salida.texto() == "Hola")
    _elegir(app, "accion:escribir")             # "Nuevo"
    _elegir(app, "accion:deshacer")
    _girar(app, 300)
    assert app.salida.texto() == "Hola"


def test_directo_limpiar_todo_borra_mas_de_200_caracteres(app_directo):
    app = app_directo
    app.salida.eventos = list(app.salida.eventos)    # sin recorte: hacen falta todos los eventos
    for _ in range(250):
        _elegir(app, "tecla:a")
    assert _esperar(app, lambda: len(app.salida.texto()) == 250)
    _elegir(app, "accion:limpiar")
    _elegir(app, "frase:si")                    # confirmar
    assert _esperar(app, lambda: app.salida.texto() == "")
    assert app.teclado.escritura.texto == ""


# ------------------------------------------------------------------ barrido con la aplicación
def test_con_barrido_de_opciones_no_se_puede_salir_ni_cerrar_desde_el_barrido(app_tec):  # noqa: F811
    app = app_tec
    app.cfg.datos["teclado"]["barrido"] = True
    _girar(app, 300)
    app.alternar_teclado()
    _girar(app, 400)
    filas = app.teclado.filas_barrido()
    todos = {i for f in filas for i in f}
    assert "accion:barrido" not in todos and "accion:cerrar" not in todos
    assert "accion:pausa" in todos             # la pausa sí (se quita con dos parpadeos largos)
    # la urgencia está en la primera fila del barrido, junto a Sí y No
    primera = filas[0]
    assert primera[:2] == ["frase:si", "frase:no"]
    rapidas = app.teclado.frases.rapidas()
    urg = [i for i in primera if i.startswith("frase:rapida:") and rapidas[int(i.rsplit(":", 1)[1])]["urgente"]]
    assert urg, primera


def test_barrido_temporal_si_deja_salir(app_tec):  # noqa: F811
    app = app_tec
    _girar(app, 300)
    app.alternar_teclado()
    _girar(app, 300)
    app.teclado.accion("barrido")               # la persona lo encendió con la cabeza
    _girar(app, 300)
    todos = {i for f in app.teclado.filas_barrido() for i in f}
    assert "accion:barrido" in todos
