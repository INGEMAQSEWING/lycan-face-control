"""Ronda 1 de arreglos: robustez de la interfaz (reinicios del motor, errores en callbacks de tk,
apagado de Windows, "abrir al encender" y atajos repetidos). Sin cámara ni Windows reales."""
import time

from lycan_face_control import constantes as K
from lycan_face_control.ui import aplicacion as A
from lycan_face_control.ui import opciones as OP
from lycan_face_control.ui import textos as T
from test_interfaz import _girar, app_viva  # noqa: F401  (fixture)


def test_tres_tropiezos_separados_no_rinden_el_motor(app_viva, monkeypatch):  # noqa: F811
    app = app_viva
    _girar(app, 300)
    reloj = [time.monotonic()]
    for _ in range(4):
        # un tropiezo aislado cada 10 minutos
        app._t_ult_vista = reloj[0] - 5
        app._vigilar_motor(reloj[0])
        assert not app.motor_rendido
        _girar(app, 300)
        reloj[0] += A.REINICIOS_VENTANA_S * 2
    assert app.reinicios == 4
    # tres seguidos en 5 minutos sí: ahí se rinde
    for _ in range(4):
        app._t_ult_vista = reloj[0] - 5
        app._vigilar_motor(reloj[0])
        reloj[0] += 1
    assert app.motor_rendido


def test_la_interfaz_parada_por_suspension_no_cuenta_como_motor_caido(app_viva):  # noqa: F811
    app = app_viva
    _girar(app, 300)
    app._t_ult_vuelta = time.monotonic() - 30        # el portátil estuvo suspendido 30 s
    app._t_ult_vista = time.monotonic() - 30
    app.vuelta_interfaz()
    assert app.reinicios == 0 and not app.motor_rendido


def test_error_en_un_callback_de_tk_queda_en_el_registro_y_pausa(app_viva, caplog):  # noqa: F811
    app = app_viva
    _girar(app, 500)
    assert app.motor.maquina.estado == K.ACTIVO

    def falla():
        raise RuntimeError("falla de prueba en un after")
    app.root.after(1, falla)
    with caplog.at_level("ERROR", logger="lycan"):
        _girar(app, 600)
    assert any("Error en la interfaz" in r.getMessage() for r in caplog.records)
    assert app.motor.maquina.estado == K.PAUSA


def test_apagar_windows_guarda_palabras_y_configuracion(app_viva, monkeypatch):  # noqa: F811
    app = app_viva
    _girar(app, 200)
    guardados = []

    class PredFalsa:
        def guardar(self, forzar=False):
            guardados.append("palabras")
            return True
    app.prediccion = PredFalsa()
    monkeypatch.setattr(app, "guardar_config", lambda datos=None: guardados.append("config") or True)
    app._al_apagar_windows()
    assert guardados == ["palabras", "config"]
    assert app.root.winfo_exists()                # no destruye ventanas
    assert app.salida.todo_suelto()


def test_palabras_se_guardan_cada_tanto(app_viva):  # noqa: F811
    app = app_viva
    n = []

    class PredFalsa:
        def guardar(self, forzar=False):
            n.append(1)
            return True
    app.prediccion = PredFalsa()
    app._t_guardar_palabras = time.monotonic() - A.GUARDAR_PALABRAS_S - 1
    app._t_publicar = 0.0
    app.vuelta_interfaz()
    assert n == [1]


def test_atajos_repetidos_o_vacios_no_se_guardan():
    bien = {"pausar": "Ctrl+Alt+Espacio", "teclado": "Ctrl+Alt+T", "recentrar": "Ctrl+Alt+C",
            "ventana": "Ctrl+Alt+Inicio", "salir": "Ctrl+Alt+Fin"}
    assert OP.atajos_validos(bien, revisar_teclado=False) is None
    malo = dict(bien, pausar="Ctrl+Alt+Fin")
    error = OP.atajos_validos(malo, revisar_teclado=False)
    assert error and "repetido" in error
    assert OP.atajos_validos(dict(bien, teclado=""), revisar_teclado=False)


def test_atajo_que_escribe_una_letra_no_se_guarda(monkeypatch):
    from lycan_face_control.sistema import atajos as AT
    monkeypatch.setattr(AT, "produce_caracter", lambda mods, vk, hkl=None: "@" if vk == ord("Q") else None)
    bien = {"pausar": "Ctrl+Alt+Q", "salir": "Ctrl+Alt+Fin"}
    error = OP.atajos_validos(bien)
    assert error and "@" in error


def test_opciones_lee_abrir_al_encender_del_registro_y_siempre_lo_aplica(app_viva, monkeypatch):  # noqa: F811
    from lycan_face_control.sistema import inicio
    app = app_viva
    app.sistema = True                              # como en Windows, pero con el registro falso
    monkeypatch.setattr(inicio, "activo", lambda: True)
    puestos = []
    monkeypatch.setattr(app, "poner_al_encender", lambda si: puestos.append(si))
    monkeypatch.setattr(app, "_revisar_foco", lambda: None)
    op = app.abrir_opciones()
    try:
        assert op.datos["arranque"]["al_encender"] is True      # el instalador lo puso
        op.datos["arranque"]["al_encender"] = False             # el cuidador lo apaga
        op.guardar()
    finally:
        app.sistema = False
    assert puestos == [False]


def test_textos_de_la_ronda():
    assert "dos veces" in T.TXT["sub_PAUSA_parpadeo"]
    assert T.TXT["op_parpadeo_fuera"] == "Parpadeo largo cuando no está en barrido"
    assert "barrido" in T.TXT["op_solo_com"]
    assert "Solo comunicación" in T.TXT["ayuda_cuidador"]
    assert "dos minutos" in T.TXT["cal_intro"] and "dos minutos" in T.TXT["asis_4"]
