"""Ronda 1 de arreglos: privacidad de las palabras aprendidas, lista de palabras limpia, archivos
bloqueados un momento, y voz (largo y voces que no son en español)."""
import json
from pathlib import Path

import pytest

from lycan_face_control import frases as F
from lycan_face_control import prediccion as PR
from lycan_face_control.sistema import voz as V
from test_voz import SapiFalso, _esperar


# ------------------------------------------------------------------ privacidad
def test_el_archivo_no_permite_rearmar_la_frase_escrita(tmp_path):
    ruta = tmp_path / "palabras_usuario.json"
    p = PR.Prediccion(lista=[("hola", 5)], ruta_usuario=ruta)
    frase = "Mi hija Laura me pega cuando no hay nadie"
    p.aprender(frase)
    assert p.guardar(forzar=True)
    d = json.loads(ruta.read_text("utf-8"))
    assert "contador" not in d
    valores = [v for v in d["palabras"].values()]
    assert all(v[1] in (0, 1) for v in valores)           # "reciente" sí/no, nunca un orden
    assert list(d["palabras"]) == sorted(d["palabras"])    # en orden alfabético
    # sigue funcionando al volver a abrir
    q = PR.Prediccion(lista=[("hola", 5)], ruta_usuario=ruta)
    assert q.usos["laura"] == 1
    assert "laura" in q.sugerir("lau")


def test_archivo_viejo_con_orden_se_lee_y_se_reescribe_sin_orden(tmp_path):
    ruta = tmp_path / "palabras_usuario.json"
    ruta.write_text(json.dumps({"version": 1, "contador": 500,
                                "palabras": {"agua": [3, 499], "cobija": [2, 10]}, "pares": {}}), "utf-8")
    p = PR.Prediccion(lista=[("hola", 5)], ruta_usuario=ruta)
    assert p.usos == {"agua": 3, "cobija": 2}
    assert "agua" in p.ultimo and "cobija" not in p.ultimo     # solo la reciente
    assert p.guardar()
    assert json.loads(ruta.read_text("utf-8"))["version"] == PR.VERSION_ARCHIVO


def test_readme_dice_la_verdad_sobre_lo_que_se_guarda():
    readme = (Path(__file__).resolve().parents[1] / "README.md").read_text("utf-8")
    assert "solo se guardan palabras sueltas" not in readme
    assert "seguidas" in readme


# ------------------------------------------------------------------ lista de palabras
def test_no_sugiere_groserias_que_la_persona_no_escribio():
    p = PR.Prediccion()
    for pre, mala in (("mam", "mamada"), ("put", "puta"), ("mier", "mierda"), ("maric", "marica"),
                      ("pend", "pendejo"), ("cul", "culo")):
        assert mala not in p.sugerir(pre), pre
    assert "mamá" in p.sugerir("mam")
    # si la persona la escribe, es suya y sí se sugiere
    p.aprender("mierda")
    assert "mierda" in p.sugerir("mier")


def test_no_sugiere_la_forma_sin_tilde_si_es_una_falta():
    p = PR.Prediccion()
    s = p.sugerir("nin")
    assert "nina" not in s and "ningun" not in s and "ningún" in s
    assert "verguenza" not in p.sugerir("verg")
    # las dos formas correctas se quedan
    assert {"esta", "está"} <= set(p.sugerir("est", n=8))
    assert {"como", "cómo"} <= set(p.sugerir("com"))
    assert "sí" in p.sugerir("si")
    assert "si" in p.frec and "sí" in p.frec


def test_limpiar_lista_suma_la_frecuencia_a_la_forma_correcta():
    out = PR.limpiar_lista({"aqui": 10, "aquí": 100, "llego": 30, "llegó": 300, "si": 50, "sí": 500})
    assert "aqui" not in out and out["aquí"] == 110
    assert "llego" in out                                    # tilde final: dos palabras correctas
    assert "si" in out


# ------------------------------------------------------------------ archivos bloqueados
def _bloquear_lectura(monkeypatch, ruta):
    original = Path.read_text
    llamadas = []

    def falso(self, *a, **k):
        if Path(self) == ruta:
            llamadas.append(1)
            raise PermissionError(13, "El proceso no tiene acceso al archivo")
        return original(self, *a, **k)
    monkeypatch.setattr(Path, "read_text", falso)
    monkeypatch.setattr("lycan_face_control.config.PAUSA_REINTENTO_S", 0.0)
    return llamadas


def test_palabras_bloqueadas_al_abrir_no_se_pisan(tmp_path, monkeypatch):
    ruta = tmp_path / "palabras_usuario.json"
    p0 = PR.Prediccion(lista=[("hola", 5)], ruta_usuario=ruta)
    p0.aprender("abuela mamita querida")
    p0.guardar(forzar=True)
    bueno = ruta.read_text("utf-8")
    llamadas = _bloquear_lectura(monkeypatch, ruta)
    p = PR.Prediccion(lista=[("hola", 5)], ruta_usuario=ruta)
    assert len(llamadas) == 3                               # reintentó
    assert p.solo_lectura and p.aviso == "palabras_no_leidas"
    monkeypatch.undo()
    p.aprender("hola")
    assert p.guardar() is False
    assert ruta.read_text("utf-8") == bueno                 # el archivo bueno sigue intacto


def test_frases_bloqueadas_al_abrir_no_se_pisan(tmp_path, monkeypatch):
    ruta = tmp_path / "frases.json"
    f0 = F.Frases(ruta)
    f0.cargar()
    f0.agregar(0, "Quiero ver a mi nieta")
    assert f0.guardar()
    bueno = ruta.read_text("utf-8")
    _bloquear_lectura(monkeypatch, ruta)
    f = F.Frases(ruta)
    f.cargar()
    assert f.solo_lectura and f.aviso == "frases_no_leidas"
    monkeypatch.undo()
    f.agregar(0, "Otra")
    assert f.guardar() is False
    assert ruta.read_text("utf-8") == bueno


def test_textos_de_archivos_bloqueados():
    from lycan_face_control.ui import textos as T
    assert T.TXT["aviso_frases_no_leidas"] and T.TXT["aviso_palabras_no_leidas"]


# ------------------------------------------------------------------ voz
def test_un_mensaje_largo_se_dice_entero_y_no_se_corta_en_media_palabra():
    sapi = SapiFalso()
    v = V.Voz({}, crear_sapi=lambda: sapi, listar=lambda: [{"nombre": V.SABINA, "idioma": "80a"}])
    texto = " ".join(["palabra"] * 250)                     # 1999 caracteres
    assert v.hablar(texto)
    assert _esperar(lambda: sapi.dicho)
    assert texto in sapi.dicho[0]
    v.cerrar()
    largo = " ".join(["palabra"] * 300)
    r = V.recortar(largo)
    assert len(r) <= V.MAX_TEXTO and r.endswith("palabra")


def test_sin_voz_en_espanol_se_sabe_y_la_app_avisa():
    sapi = SapiFalso()
    v = V.Voz({}, crear_sapi=lambda: sapi,
              listar=lambda: [{"nombre": "Microsoft David Desktop", "idioma": "409"},
                              {"nombre": "Microsoft Zira Desktop", "idioma": "409"}])
    assert v.hablar("Tengo sed")
    assert _esperar(lambda: sapi.dicho)
    assert v.voz_espanol is False
    v.cerrar()
    sapi = SapiFalso()
    v = V.Voz({}, crear_sapi=lambda: sapi, listar=lambda: [{"nombre": V.SABINA, "idioma": "80a"}])
    v.hablar("Hola")
    assert _esperar(lambda: sapi.dicho)
    assert v.voz_espanol is True
    v.cerrar()


def test_la_aplicacion_avisa_una_vez_si_la_voz_no_es_en_espanol():
    from lycan_face_control.ui import aplicacion as A
    from lycan_face_control.ui.textos import t

    class VozIngles:
        voz_espanol = False

        def hablar(self, texto, urgente=False):
            return True

    class AppMin:
        sistema = False
        hablar = A.App.hablar
        _mostrar_no_dicho = A.App._mostrar_no_dicho
        teclado = None
        ventana = None

        def __init__(self):
            self.voz = VozIngles()
            self.avisos = []
            self.sonidos = type("S", (), {"tocar": lambda self, n: None})()

        def mostrar_aviso(self, texto, s=6):
            self.avisos.append(texto)
    app = AppMin()
    app.hablar("Tengo sed")
    app.hablar("Tengo frío")
    assert app.avisos == [t("aviso_sin_voz"), "Tengo frío"]
