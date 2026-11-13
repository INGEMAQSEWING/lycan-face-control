"""Ronda 2 de arreglos: vigilante del motor (lento no es caído), archivos con BOM, validación del
monitor, "olvidar" que olvida todo y voz que falla después de arrancar."""
import copy
import json
import time

from conftest import CAL_SINTETICA
from lycan_face_control import config as C
from lycan_face_control.config import Configuracion
from lycan_face_control.frases import Frases
from lycan_face_control.prediccion import Prediccion
from lycan_face_control.sistema import voz as V
from lycan_face_control.ui import aplicacion as A
from test_interfaz import _girar, app_viva  # noqa: F401  (fixture)

BOM = b"\xef\xbb\xbf"


# ------------------------------------------------------------ vigilante del motor
def test_motor_lento_pero_vivo_no_se_reinicia_ni_queda_en_pausa(app_viva):  # noqa: F811
    app = app_viva
    _girar(app, 400)
    viejo = app.motor
    estado = app.motor.maquina.estado
    soltados = []
    real = app.salida.soltar_todo
    app.salida.soltar_todo = lambda motivo="": (soltados.append(motivo), real(motivo))
    app._t_ult_vista = time.monotonic() - 3          # 3 s sin vistas, pero el hilo late
    app._vigilar_motor(time.monotonic())
    assert app.motor is viejo and app.reinicios == 0 and not app.motor_rendido
    assert soltados == ["motor lento"]                # por seguridad se suelta todo, una vez
    app._vigilar_motor(time.monotonic())
    assert soltados == ["motor lento"]
    _girar(app, 300)
    assert app.motor.maquina.estado == estado


def test_motor_vivo_sin_latido_se_reinicia(app_viva):  # noqa: F811
    app = app_viva
    _girar(app, 300)
    viejo = app.motor
    app._t_ult_vista = time.monotonic() - 20
    viejo.latido = time.monotonic() - 20
    app._vigilar_motor(time.monotonic())
    if app._motor_viejo is not None:
        app._vigilar_motor(time.monotonic() + A.ESPERA_MOTOR_VIEJO_S + 1)
    assert app.motor is not viejo and app.reinicios == 1
    assert not viejo.is_alive()


def test_no_crea_otro_motor_mientras_el_viejo_sigue_vivo(app_viva, monkeypatch):  # noqa: F811
    app = app_viva
    _girar(app, 300)
    viejo = app.motor
    creados = []
    real = app._crear_motor
    monkeypatch.setattr(app, "_crear_motor", lambda: (creados.append(1), real())[1])
    monkeypatch.setattr(viejo, "is_alive", lambda: True)       # el viejo tarda en soltar la cámara
    monkeypatch.setattr(viejo, "join", lambda timeout=None: None)
    ahora = time.monotonic()
    app._t_ult_vista = ahora - 20
    viejo.latido = ahora - 20
    app._vigilar_motor(ahora)
    assert creados == [] and app._motor_viejo is not None
    app._vigilar_motor(ahora + 2)
    assert creados == []
    monkeypatch.setattr(viejo, "is_alive", lambda: False)      # ya terminó
    app._vigilar_motor(ahora + 3)
    assert creados == [1] and app.motor is not viejo


def test_rendido_vuelve_a_intentar_cada_minuto_y_con_el_atajo(app_viva):  # noqa: F811
    app = app_viva
    _girar(app, 300)
    ahora = time.monotonic()
    app._rendirse(ahora)
    viejo = app.motor
    app._vigilar_motor(ahora + 30)
    assert app.motor_rendido and app.motor is viejo
    app._vigilar_motor(ahora + A.REINTENTO_RENDIDO_S + 1)
    if app._motor_viejo is not None:
        app._vigilar_motor(ahora + A.REINTENTO_RENDIDO_S + A.ESPERA_MOTOR_VIEJO_S + 2)
    assert not app.motor_rendido and app.motor is not viejo
    # el atajo de pausa del cuidador lo intenta ya
    app._rendirse(time.monotonic())
    viejo = app.motor
    app._atender_atajo("pausar")
    if app._motor_viejo is not None:
        app._vigilar_motor(time.monotonic() + A.ESPERA_MOTOR_VIEJO_S + 1)
    assert not app.motor_rendido and app.motor is not viejo


# ------------------------------------------------------------ archivos con BOM
def test_config_con_bom_se_lee_y_no_se_pierde_la_calibracion(tmp_path):
    datos = C.por_defecto()
    datos["primera_vez"] = False
    datos["perfiles"]["Principal"]["calibracion"] = copy.deepcopy(CAL_SINTETICA)
    ruta = tmp_path / "config.json"
    ruta.write_bytes(BOM + json.dumps(datos, ensure_ascii=False).encode("utf-8"))
    cfg = Configuracion(ruta)
    cfg.cargar()
    assert cfg.datos["primera_vez"] is False
    assert cfg.datos["perfiles"]["Principal"]["calibracion"]["centro"] == CAL_SINTETICA["centro"]
    assert not list(tmp_path.glob("config.dañado-*"))


def test_frases_y_palabras_con_bom_se_leen(tmp_path):
    f = Frases(tmp_path / "frases.json")
    f.cargar()
    f.datos["categorias"][0]["frases"][0]["texto"] = "Tengo sed, mamá"
    datos = f.datos
    (tmp_path / "frases.json").write_bytes(BOM + json.dumps(datos, ensure_ascii=False).encode("utf-8"))
    g = Frases(tmp_path / "frases.json")
    g.cargar()
    assert g.aviso is None
    assert g.datos["categorias"][0]["frases"][0]["texto"] == "Tengo sed, mamá"
    ruta = tmp_path / "palabras_usuario.json"
    ruta.write_bytes(BOM + json.dumps({"version": 2, "palabras": {"morfina": [5, 1]}, "pares": {}}).encode("utf-8"))
    p = Prediccion([("hola", 10)], ruta_usuario=ruta)
    p.cargar_usuario()
    assert p.usos.get("morfina") == 5
    assert not list(tmp_path.glob("*.dañado-*"))


def test_monitor_con_digitos_raros_vuelve_a_fabrica():
    problemas = []
    out = C.validar({"pantalla": {"monitor": "²"}}, problemas=problemas)
    assert out["pantalla"]["monitor"] == "principal" and problemas
    assert C.validar({"pantalla": {"monitor": "2"}})["pantalla"]["monitor"] == "2"


# ------------------------------------------------------------ olvidar
def test_olvidar_borra_tambien_las_copias_apartadas(tmp_path):
    ruta = tmp_path / "palabras_usuario.json"
    ruta.write_text('{"version": 2, "palabras": {"morfina": [3, 1]', encoding="utf-8")   # truncado
    p = Prediccion([("hola", 10)], ruta_usuario=ruta)
    p.cargar_usuario()
    assert list(tmp_path.glob("palabras_usuario.dañado-*.json"))
    p.aprender("hospital")
    p.guardar()
    (tmp_path / "palabras_usuario.json.tmp").write_text("{}", encoding="utf-8")
    assert p.olvidar() is True
    assert not list(tmp_path.glob("palabras_usuario*"))


# ------------------------------------------------------------ voz que falla después de arrancar
def _esperar(cond, s=2.0):
    fin = time.monotonic() + s
    while time.monotonic() < fin:
        if cond():
            return True
        time.sleep(0.01)
    return False


def test_voz_que_falla_despues_de_arrancar_avisa_y_devuelve_false():
    creados = []

    class RespaldoMuerto:
        def __init__(self, voz):
            creados.append(self)
            if len(creados) > 1:
                raise OSError("no arranca")

        def hablar(self, texto, volumen, velocidad):
            raise OSError("El respaldo de voz se cerró")

        def cerrar(self):
            pass

    def sin_sapi():
        raise OSError("sin COM")

    v = V.Voz({}, crear_sapi=sin_sapi, crear_respaldo=RespaldoMuerto, listar=lambda: [])
    assert v.hablar("Tengo sed") is True               # todavía no se sabe
    assert _esperar(lambda: not v.fallidos.empty())
    assert v.fallidos.get_nowait() == "Tengo sed"
    assert len(creados) == 2                           # se intentó recrear una vez
    assert v.hablar("Tengo dolor") is False            # ahora la interfaz lo muestra en grande
    v.cerrar()


def test_voz_se_recupera_si_recrearla_funciona():
    dichos = []
    creados = []

    class Respaldo:
        def __init__(self, voz):
            creados.append(self)
            self.vivo = len(creados) > 1

        def hablar(self, texto, volumen, velocidad):
            if not self.vivo:
                raise OSError("se cerró")
            dichos.append(texto)

        def cerrar(self):
            pass

    def sin_sapi():
        raise OSError("sin COM")

    v = V.Voz({}, crear_sapi=sin_sapi, crear_respaldo=Respaldo, listar=lambda: [])
    assert v.hablar("Hola")
    assert _esperar(lambda: dichos == ["Hola"])
    assert v.fallidos.empty() and v.motor == "powershell"
    v.cerrar()


def test_cambio_de_voz_entre_frases_no_se_pierde():
    v = V.Voz({}, arrancar=False)
    v.listo.set()
    v.motor = "sapi"
    v.cola.put(("hablar", "uno", False))
    v.cola.put(("config",))
    v.cola.put(("hablar", "dos", False))
    v.cola.put(("cerrar",))
    dichos = []

    class S:
        def volumen(self, x):
            pass

        def velocidad(self, x):
            pass

        def hablar(self, xml, flags=0):
            dichos.append(xml)
            return 0

        def cerrar(self):
            pass

    leidas = []
    v._iniciar = lambda: S()
    v._listar = lambda: (leidas.append(1), [])[1]
    v.cfg = {"nombre": "Otra"}
    v._correr()
    assert dichos and "dos" in dichos[0]
    assert leidas                                       # la orden de configuración sí se aplicó
