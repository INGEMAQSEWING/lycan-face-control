"""Configuración (sección 13.2, test_config.py): valores fuera de rango vuelven a fábrica, archivo
dañado se renombra, coherencia del parpadeo y "siempre hay forma de reanudar"."""
import copy
import json

import pytest

from lycan_face_control import config as CF
from lycan_face_control.config import (FABRICA, Configuracion, ErrorSoloLectura, calibracion_activa, carpeta_datos,
                                       formas_de_reanudar, por_defecto, ruta_config, ruta_recurso, validar)


def _con(**cambios):
    """Copia de fábrica con cambios por ruta: _con(**{"gestos.boca.sens": 3})."""
    d = por_defecto()
    for ruta, v in cambios.items():
        partes = ruta.split(".")
        nodo = d
        for p in partes[:-1]:
            nodo = nodo[p]
        nodo[partes[-1]] = v
    return d


def test_fabrica_es_valida_y_completa():
    problemas = []
    out = validar(FABRICA, problemas=problemas)
    assert problemas == []
    assert out == FABRICA
    # valores clave de la especificación
    assert FABRICA["gestos"]["parpadeo"]["largo_ms"] == 800
    assert FABRICA["gestos"]["boca"]["corto"] == "clic" and FABRICA["gestos"]["boca"]["largo"] == "pausar"
    assert FABRICA["gestos"]["sonrisa"]["activo"] is False
    assert FABRICA["permanencia"]["tiempo_s"] == 1.0 and FABRICA["permanencia"]["radio_px"] == 30
    assert FABRICA["comodidad"]["mostrar_video"] is False
    assert FABRICA["atajos"]["pausar"] == "Ctrl+Alt+Espacio"
    assert FABRICA["perfiles"] == {"Principal": {"calibracion": None}}


def test_carpeta_de_pruebas(tmp_path):
    # el conftest cambia la carpeta: nunca se toca la configuración real
    assert str(carpeta_datos()).startswith(str(tmp_path))
    assert ruta_config().name == "config.json"


@pytest.mark.parametrize("ruta,valor", [
    ("camara.fps_proceso", 5), ("camara.fps_proceso", 31), ("puntero.sens_x", 0.1), ("puntero.sens_y", 9),
    ("puntero.suavidad", 0), ("puntero.zona_muerta_px", 20), ("puntero.margen", 0.5),
    ("permanencia.tiempo_s", 0.1), ("permanencia.radio_px", 200), ("gestos.boca.sens", 3.0),
    ("gestos.cejas.sostener_ms", 50), ("gestos.sonrisa.sostener_ms", 5000), ("gestos.parpadeo.largo_ms", 100),
    ("gestos.parpadeo.largo_ms", 3000), ("gestos.refractario_ms", 100), ("barra.boton_px", 40),
    ("teclado.barrido_paso_s", 0.2), ("voz.volumen", 150), ("voz.velocidad", -9),
    ("seguridad.soltar_sin_cara_ms", 50), ("comodidad.escala_letra", 3.0), ("gestos.reanudar_ms", 100),
])
def test_fuera_de_rango_vuelve_a_fabrica(ruta, valor):
    problemas = []
    out = validar(_con(**{ruta: valor}), problemas=problemas)
    esperado = FABRICA
    nodo = out
    for p in ruta.split("."):
        nodo, esperado = nodo[p], esperado[p]
    assert nodo == esperado
    assert any(ruta in p for p in problemas)


def test_piso_de_400_ms_del_parpadeo_largo():
    # aunque la configuración diga 100 ms, nunca queda por debajo de 400
    for v in (0, 100, 399, -5):
        out = validar(_con(**{"gestos.parpadeo.largo_ms": v}))
        assert out["gestos"]["parpadeo"]["largo_ms"] >= CF.PARPADEO_LARGO_PISO_MS
    out = validar(_con(**{"gestos.parpadeo.largo_ms": 400}))
    assert out["gestos"]["parpadeo"]["largo_ms"] == 400


@pytest.mark.parametrize("valor", [float("nan"), float("inf"), "800", None, True, [800], 10 ** 400])
def test_tipos_raros_no_rompen(valor):
    out = validar(_con(**{"gestos.parpadeo.largo_ms": valor}))
    assert out["gestos"]["parpadeo"]["largo_ms"] == 800


def test_enteros_se_redondean():
    problemas = []
    out = validar(_con(**{"permanencia.radio_px": 30.6, "gestos.boca.sostener_ms": 400.0}), problemas=problemas)
    assert out["permanencia"]["radio_px"] == 31 and isinstance(out["permanencia"]["radio_px"], int)
    assert out["gestos"]["boca"]["sostener_ms"] == 400 and isinstance(out["gestos"]["boca"]["sostener_ms"], int)
    assert len(problemas) == 1


def test_decimales_se_guardan_como_decimales():
    out = validar(_con(**{"puntero.sens_x": 2}))
    assert out["puntero"]["sens_x"] == 2.0 and isinstance(out["puntero"]["sens_x"], float)


def test_opciones_no_permitidas():
    out = validar(_con(**{"puntero.modo": "turbo", "gestos.boca.corto": "borrar_disco", "teclado.genero": "x",
                          "barra.posicion": "centro", "gestos.parpadeo.fuera_barrido": "volar"}))
    assert out["puntero"]["modo"] == "absoluto"
    assert out["gestos"]["boca"]["corto"] == "clic"
    assert out["teclado"]["genero"] == "neutro"
    assert out["barra"]["posicion"] == "derecha"
    assert out["gestos"]["parpadeo"]["fuera_barrido"] == "ninguna"
    ok = validar(_con(**{"gestos.cejas.corto": "borrar", "gestos.parpadeo.fuera_barrido": "clic"}))
    assert ok["gestos"]["cejas"]["corto"] == "borrar"
    assert ok["gestos"]["parpadeo"]["fuera_barrido"] == "clic"


def test_si_no_y_textos():
    out = validar(_con(**{"permanencia.activa": "sí", "teclado.cuidador": "", "voz.nombre": 5}))
    assert out["permanencia"]["activa"] is True
    assert out["teclado"]["cuidador"] == "alguien"
    assert out["voz"]["nombre"] == 5          # opcional: número o texto (lo resuelve voz.py)
    out = validar(_con(**{"teclado.cuidador": "Marta", "voz.nombre": "Microsoft Sabina Desktop"}))
    assert out["teclado"]["cuidador"] == "Marta"
    assert validar(_con(**{"teclado.cuidador": "x" * 41}))["teclado"]["cuidador"] == "alguien"
    assert validar(_con(**{"voz.nombre": {"a": 1}}))["voz"]["nombre"] is None


def test_monitor():
    assert validar(_con(**{"pantalla.monitor": "todo"}))["pantalla"]["monitor"] == "todo"
    assert validar(_con(**{"pantalla.monitor": 1}))["pantalla"]["monitor"] == "1"
    assert validar(_con(**{"pantalla.monitor": "2"}))["pantalla"]["monitor"] == "2"
    assert validar(_con(**{"pantalla.monitor": "lejos"}))["pantalla"]["monitor"] == "principal"
    assert validar(_con(**{"pantalla.monitor": 1.5}))["pantalla"]["monitor"] == "principal"


def test_descanso_minimo_si_no_es_cero():
    assert validar(_con(**{"comodidad.descanso_min": 0}))["comodidad"]["descanso_min"] == 0
    assert validar(_con(**{"comodidad.descanso_min": 3}))["comodidad"]["descanso_min"] == 10
    assert validar(_con(**{"comodidad.descanso_min": 25}))["comodidad"]["descanso_min"] == 25


def test_descanso_del_parpadeo_mas_largo_que_el_parpadeo():
    out = validar(_con(**{"gestos.parpadeo.largo_ms": 2000, "gestos.parpadeo.descanso_ms": 2500}))
    p = out["gestos"]["parpadeo"]
    assert p["descanso_ms"] >= p["largo_ms"] + 1000


def test_umbral_abierto_por_encima_de_cerrado():
    out = validar(_con(**{"gestos.parpadeo.cerrado": 0.70, "gestos.parpadeo.abierto": 0.72}))
    p = out["gestos"]["parpadeo"]
    assert p["abierto"] == pytest.approx(0.80)
    out = validar(_con(**{"gestos.parpadeo.cerrado": 0.40, "gestos.parpadeo.abierto": 0.95}))
    assert out["gestos"]["parpadeo"]["abierto"] == pytest.approx(0.65)
    out = validar(_con(**{"gestos.parpadeo.cerrado": 0.50, "gestos.parpadeo.abierto": 0.70}))
    assert out["gestos"]["parpadeo"]["abierto"] == 0.70


def test_siempre_hay_forma_de_reanudar():
    # sin permanencia y sin ningún gesto con "pausar": se vuelve a encender la permanencia
    d = _con(**{"permanencia.activa": False, "gestos.boca.largo": "ninguna"})
    problemas = []
    out = validar(d, problemas=problemas)
    assert out["permanencia"]["activa"] is True
    assert any("reanudar" in p for p in problemas)
    assert formas_de_reanudar(out)
    # con la boca larga en "pausar" sí se puede apagar la permanencia
    out = validar(_con(**{"permanencia.activa": False}))
    assert out["permanencia"]["activa"] is False
    assert formas_de_reanudar(out) == ["gesto:boca"]
    # un gesto apagado no cuenta
    d = _con(**{"permanencia.activa": False, "gestos.boca.activo": False})
    assert validar(d)["permanencia"]["activa"] is True
    # todos los gestos apagados y sin permanencia
    d = _con(**{"permanencia.activa": False, "gestos.boca.activo": False, "gestos.cejas.activo": False})
    assert validar(d)["permanencia"]["activa"] is True


def test_perfiles():
    cal = {"fecha": "2026-11-13", "centro": [0.02, 0.55], "base": {"mar": 0.02}}
    d = por_defecto()
    d["perfiles"] = {"Principal": {"calibracion": cal}, "Tarde": {"calibracion": None}}
    d["perfil_activo"] = "Tarde"
    out = validar(d)
    assert out["perfiles"]["Principal"]["calibracion"] == cal
    assert out["perfil_activo"] == "Tarde"
    assert calibracion_activa(out) is None
    out["perfil_activo"] = "Principal"
    assert calibracion_activa(out) == cal


def test_perfiles_malos():
    d = por_defecto()
    d["perfiles"] = {"": {"calibracion": None}, "Bien": {"calibracion": {"x": float("nan")}}, "Raro": 5}
    d["perfil_activo"] = "No existe"
    problemas = []
    out = validar(d, problemas=problemas)
    assert "" not in out["perfiles"]
    assert out["perfiles"]["Bien"]["calibracion"] is None       # dañada: hay que calibrar de nuevo
    assert out["perfiles"]["Raro"] == {"calibracion": None}
    assert out["perfil_activo"] in out["perfiles"]
    d["perfiles"] = "nada"
    out = validar(d)
    assert out["perfiles"] == FABRICA["perfiles"] and out["perfil_activo"] == "Principal"
    d["perfiles"] = {f"P{i}": {"calibracion": None} for i in range(50)}
    assert len(validar(d)["perfiles"]) == CF.MAX_PERFILES


def test_secciones_de_tipo_equivocado():
    d = por_defecto()
    d["gestos"] = "nada"
    d["puntero"] = [1, 2]
    out = validar(d)
    assert out["gestos"] == FABRICA["gestos"]
    assert out["puntero"] == FABRICA["puntero"]


def test_claves_desconocidas_se_descartan():
    d = por_defecto()
    d["extra"] = 1
    d["gestos"]["guino"] = {"activo": True}
    out = validar(d)
    assert "extra" not in out and "guino" not in out["gestos"]


# ---- archivo ----

def test_cargar_sin_archivo_es_fabrica():
    c = Configuracion()
    assert c.cargar() == FABRICA
    assert c.aviso is None


def test_guardar_y_cargar(tmp_path):
    c = Configuracion()
    d = por_defecto()
    d["primera_vez"] = False
    d["teclado"]["cuidador"] = "Ana María"
    c.guardar(d)
    texto = ruta_config().read_text(encoding="utf-8")
    assert "Ana María" in texto                     # UTF-8 sin escapar
    c2 = Configuracion()
    assert c2.cargar()["teclado"]["cuidador"] == "Ana María"
    assert c2.datos["primera_vez"] is False
    assert not ruta_config().with_name("config.json.tmp").exists()


@pytest.mark.parametrize("contenido", ["", "   ", "{no es json", "[1, 2]", "\"texto\"", "[" * 5000])
def test_archivo_danado_se_renombra(contenido):
    ruta = ruta_config()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(contenido, encoding="utf-8")
    c = Configuracion()
    assert c.cargar() == FABRICA
    assert c.aviso == CF.AVISO_RESTABLECIDA
    assert not ruta.exists()
    apartados = list(ruta.parent.glob("config.dañado-*.json"))
    assert len(apartados) == 1
    assert apartados[0].read_text(encoding="utf-8") == contenido
    c.guardar()
    assert ruta.exists()


def test_bytes_invalidos_se_tratan_como_danado():
    ruta = ruta_config()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(b"\xff\xfe\x00{")
    c = Configuracion()
    c.cargar()
    assert c.aviso == CF.AVISO_RESTABLECIDA


def test_version_mas_nueva_avisa_pero_conserva_lo_valido():
    d = por_defecto()
    d["version"] = 99
    d["teclado"]["cuidador"] = "Pedro"
    ruta = ruta_config()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(d), encoding="utf-8")
    c = Configuracion()
    out = c.cargar()
    assert out["teclado"]["cuidador"] == "Pedro" and out["version"] == 1
    assert c.aviso == CF.AVISO_RESTABLECIDA


def test_valor_malo_en_archivo_se_corrige_sin_aviso():
    d = por_defecto()
    d["permanencia"]["tiempo_s"] = 99
    ruta = ruta_config()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(d), encoding="utf-8")
    c = Configuracion()
    assert c.cargar()["permanencia"]["tiempo_s"] == 1.0
    assert c.problemas and c.aviso is None


def test_archivo_bloqueado_queda_solo_lectura(monkeypatch):
    ruta = ruta_config()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(por_defecto()), encoding="utf-8")
    monkeypatch.setattr(CF, "PAUSA_REINTENTO_S", 0.0)
    c = Configuracion()

    def bloqueado(*a, **k):
        raise PermissionError("bloqueado")
    monkeypatch.setattr(type(c.ruta), "read_text", bloqueado)
    datos = c.cargar()
    assert c.solo_lectura and datos["primera_vez"] is False
    assert c.aviso == CF.AVISO_NO_LEIDA
    with pytest.raises(ErrorSoloLectura):
        c.guardar()
    assert c.guardar_seguro() is False
    assert ruta.exists()                                  # no se apartó ni se borró


def test_guardar_valida_lo_que_recibe():
    c = Configuracion()
    d = por_defecto()
    d["voz"]["volumen"] = 500
    c.guardar(d)
    assert c.datos["voz"]["volumen"] == 80
    assert json.loads(ruta_config().read_text(encoding="utf-8"))["voz"]["volumen"] == 80


def test_restablecer_fabrica_conserva_calibracion_y_atajos():
    c = Configuracion()
    d = por_defecto()
    d["atajos"]["teclado"] = "Ctrl+Alt+K"
    d["perfiles"]["Principal"]["calibracion"] = {"centro": [0.0, 0.55]}
    d["teclado"]["cuidador"] = "Luz"
    d["puntero"]["sens_x"] = 2.5
    c.datos = validar(d)
    out = c.restablecer_fabrica()
    assert out["atajos"]["teclado"] == "Ctrl+Alt+K"
    assert out["perfiles"]["Principal"]["calibracion"] == {"centro": [0.0, 0.55]}
    assert out["teclado"]["cuidador"] == "Luz"
    assert out["puntero"]["sens_x"] == 1.0
    assert out["primera_vez"] is False


def test_por_defecto_es_copia():
    a = por_defecto()
    a["gestos"]["boca"]["sens"] = 2.0
    assert FABRICA["gestos"]["boca"]["sens"] == 1.0
    b = copy.deepcopy(FABRICA)
    assert b == por_defecto()


def test_ruta_recurso_palabras():
    assert ruta_recurso("palabras_es.txt").exists()
