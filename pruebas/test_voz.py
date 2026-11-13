"""Parte 4: voz (sin hablar de verdad) y portapapeles (con funciones falsas)."""
from __future__ import annotations

import json
import time

import pytest

from lycan_face_control.sistema import portapapeles
from lycan_face_control.sistema import voz as V


def test_escapado_xml():
    assert V.escapar_xml("Tom & Jerry <3 > 2") == "Tom &amp; Jerry &lt;3 &gt; 2"
    assert V.escapar_xml("línea\nnueva\x07") == "línea nueva "
    x = V.xml_para("a & b", "Microsoft Sabina Desktop")
    assert x == '<voice required="Name=Microsoft Sabina Desktop">a &amp; b</voice>'
    assert V.xml_para("<hola>", None) == "&lt;hola&gt;"


def test_idioma_espanol():
    for i in ("80A", "c0a", "40a", "es-MX", "409;80a"):
        assert V.es_espanol(i), i
    for i in ("409", "", "zz", "416"):
        assert not V.es_espanol(i), i


VOCES = [{"nombre": "Microsoft Zira Desktop", "idioma": "409"},
         {"nombre": "Microsoft Sabina Desktop", "idioma": "80A"},
         {"nombre": "Microsoft Helena Desktop", "idioma": "C0A"}]


def test_eleccion_de_voz():
    assert V.elegir_voz(VOCES) == "Microsoft Sabina Desktop"
    assert V.elegir_voz(VOCES, "Microsoft Helena Desktop") == "Microsoft Helena Desktop"
    assert V.elegir_voz(VOCES, "Una que no existe") == "Microsoft Sabina Desktop"
    sin_sabina = [v for v in VOCES if "Sabina" not in v["nombre"]]
    assert V.elegir_voz(sin_sabina) == "Microsoft Helena Desktop"         # otra es-*
    assert V.elegir_voz([VOCES[0]]) is None                                 # predeterminada
    assert V.elegir_voz([]) is None


def test_comando_de_respaldo_powershell():
    cmd = V.comando_powershell("Microsoft Sabina Desktop")
    assert cmd[0] == "powershell.exe" and "-NoProfile" in cmd and "-NonInteractive" in cmd
    guion = cmd[-1]
    assert "System.Speech" in guion and "es-*" in guion and "SpeakAsyncCancelAll" in guion
    assert "Microsoft Sabina Desktop" in guion and "UTF8" in guion
    assert "'" not in V.comando_powershell("O'Malley")[-1].split("$pref = ")[1].split("\n")[0][1:-1]
    linea = V.linea_powershell("Hola\nmundo", 80, -1)
    assert "\n" not in linea and json.loads(linea) == {"t": "Hola mundo", "v": 80, "r": -1}


class SapiFalso:
    def __init__(self):
        self.dicho, self.vol, self.vel = [], [], []
        self.cerrado = False

    def volumen(self, v):
        self.vol.append(v)

    def velocidad(self, v):
        self.vel.append(v)

    def hablar(self, xml, flags=V.FLAGS_HABLAR):
        if "No Existe" in xml:
            return V.SPERR_NOT_FOUND
        self.dicho.append(xml)
        return 0

    def cerrar(self):
        self.cerrado = True


def _esperar(cond, s=2.0):
    fin = time.monotonic() + s
    while time.monotonic() < fin:
        if cond():
            return True
        time.sleep(0.01)
    return False


def test_voz_con_sapi_falso_urgente_y_cierre():
    sapi = SapiFalso()
    v = V.Voz({"volumen": 70, "velocidad": -1}, crear_sapi=lambda: sapi, listar=lambda: VOCES)
    assert v.hablar("Tengo sed")
    assert _esperar(lambda: sapi.dicho)
    assert sapi.dicho[0] == '<voice required="Name=Microsoft Sabina Desktop">Tengo sed</voice>'
    assert sapi.vol[-1] == 70 and sapi.vel[-1] == -1
    assert v.hablar("¡Ayuda!", urgente=True)
    assert _esperar(lambda: len(sapi.dicho) >= 2)
    assert sapi.vol[-1] == 100                              # urgencia: volumen máximo
    assert v.motor == "sapi" and v.ultimo == "¡Ayuda!"
    v.cerrar()
    assert sapi.cerrado and not v._hilo.is_alive()


def test_voz_inexistente_cae_a_la_predeterminada():
    sapi = SapiFalso()
    v = V.Voz({"nombre": "Voz No Existe"}, crear_sapi=lambda: sapi,
              listar=lambda: [{"nombre": "Voz No Existe", "idioma": "80a"}])
    v.hablar("Hola")
    assert _esperar(lambda: sapi.dicho)
    assert sapi.dicho[0] == "Hola" and v.nombre_voz is None
    v.cerrar()


def test_sin_sapi_usa_el_respaldo_y_sin_nada_devuelve_false():
    dichos = []

    class Respaldo:
        def __init__(self, voz):
            self.voz = voz

        def hablar(self, texto, volumen, velocidad):
            dichos.append((texto, volumen, velocidad))

        def cerrar(self):
            pass

    def falla():
        raise OSError("sin COM")

    v = V.Voz({"volumen": 50}, crear_sapi=falla, crear_respaldo=Respaldo, listar=lambda: VOCES)
    assert v.hablar("Hola")
    assert _esperar(lambda: dichos)
    assert dichos[0] == ("Hola", 50, -1) and v.motor == "powershell"
    v.cerrar()

    def falla2(_voz=None):
        raise OSError("sin PowerShell")

    v = V.Voz({}, crear_sapi=falla, crear_respaldo=falla2, listar=lambda: [])
    assert v.hablar("Hola") is False                        # la interfaz lo muestra en grande
    assert v.hablar("") is True
    v.cerrar()


def test_respaldo_powershell_con_proceso_falso():
    escrito = []

    class Proc:
        def __init__(self, cmd, **kw):
            assert cmd[0] == "powershell.exe" and kw["creationflags"] == V.CREATE_NO_WINDOW
            self.stdin = self
            self.stdout = self

        def readline(self):
            return "listo\n"

        def write(self, s):
            escrito.append(s)

        def flush(self):
            pass

        def poll(self):
            return None

        def close(self):
            pass

        def wait(self, timeout=None):
            return 0

    m = V.MotorPowerShell("Microsoft Sabina Desktop", popen=Proc)
    m.hablar("Me duele", 80, -1)
    assert json.loads(escrito[0]) == {"t": "Me duele", "v": 80, "r": -1}
    m.cerrar()


def test_listar_voces_no_falla():
    voces = V.listar_voces()
    assert isinstance(voces, list)
    assert all("nombre" in v for v in voces)


@pytest.mark.manual
def test_hablar_de_verdad():                                # pragma: no cover - lo hace una persona
    v = V.Voz({"volumen": 80})
    assert v.hablar("Hola, soy la voz de Lycan Face Control.")
    time.sleep(3)
    v.cerrar()


# --------------------------------------------------------------------------- portapapeles
class ApiFalsa:
    def __init__(self, ocupado=0):
        self.ocupado = ocupado
        self.texto = None
        self.abierto = False

    def abrir(self):
        if self.ocupado:
            self.ocupado -= 1
            return False
        self.abierto = True
        return True

    def cerrar(self):
        self.abierto = False

    def vaciar(self):
        self.texto = None
        return True

    def poner(self, texto):
        self.texto = texto
        return True

    def leer(self):
        return self.texto


def test_copiar_y_reintentos():
    api = ApiFalsa()
    assert portapapeles.copiar("¿Ñandú? 👍", api=api, dormir=lambda s: None)
    assert api.texto == "¿Ñandú? 👍" and not api.abierto
    api = ApiFalsa(ocupado=3)
    esperas = []
    assert portapapeles.copiar("hola", api=api, dormir=esperas.append)
    assert esperas == [0.05] * 3
    api = ApiFalsa(ocupado=10)
    assert not portapapeles.copiar("hola", api=api, dormir=lambda s: None)
    assert portapapeles.leer(ApiFalsa(), dormir=lambda s: None) is None
