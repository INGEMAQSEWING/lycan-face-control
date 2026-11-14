"""Versión 1.1, paquete B: configuración de la emergencia (bloque ``emergencia``, atajo
``atajos.emergencia`` y la regla del gesto corto), textos y opciones."""
import copy
import json
import math

import pytest

from lycan_face_control import config as C
from lycan_face_control import constantes as K
from lycan_face_control.sistema import atajos
from lycan_face_control.ui import opciones as OP
from lycan_face_control.ui import textos as T


def _validar(**cambios):
    d = C.por_defecto()
    for ruta, v in cambios.items():
        x = d
        partes = ruta.split(".")
        for p in partes[:-1]:
            x = x[p]
        x[partes[-1]] = v
    problemas = []
    return C.validar(d, problemas=problemas), problemas


def test_valores_de_fabrica():
    e = C.FABRICA["emergencia"]
    assert e == {"activa": True, "mensaje": "Necesito ayuda", "volumen": 100, "repetir_voz": True,
                 "repetir_s": 12, "permanencia_s": 2.5, "detener_s": 3.0}
    assert C.FABRICA["atajos"]["emergencia"] == "Ctrl+Alt+A"
    assert C.LARGO_TEXTO["emergencia.mensaje"] == 60
    # la permanencia de AYUDA es más larga que la de un botón normal
    assert e["permanencia_s"] > C.FABRICA["barra"]["permanencia_s"]
    out, problemas = _validar()
    assert problemas == [] and out["emergencia"] == e


@pytest.mark.parametrize("ruta,malo", [
    ("emergencia.volumen", 5), ("emergencia.volumen", 101), ("emergencia.volumen", float("nan")),
    ("emergencia.volumen", "fuerte"), ("emergencia.repetir_s", 4), ("emergencia.repetir_s", 61),
    ("emergencia.repetir_s", float("inf")), ("emergencia.permanencia_s", 1.4), ("emergencia.permanencia_s", 5.1),
    ("emergencia.permanencia_s", None), ("emergencia.detener_s", 1.9), ("emergencia.detener_s", 5.5),
    ("emergencia.detener_s", float("nan")), ("emergencia.activa", "sí"), ("emergencia.activa", 1),
    ("emergencia.repetir_voz", "no"), ("emergencia.mensaje", 7), ("emergencia.mensaje", ""),
    ("emergencia.mensaje", "    "), ("emergencia.mensaje", "x" * 200), ("emergencia.mensaje", None),
])
def test_valor_malo_vuelve_al_de_fabrica_y_se_anota(ruta, malo):
    out, problemas = _validar(**{ruta: malo})
    clave = ruta.split(".")[1]
    assert out["emergencia"][clave] == C.FABRICA["emergencia"][clave]
    assert any(ruta in p for p in problemas), problemas


@pytest.mark.parametrize("ruta,bueno", [
    ("emergencia.volumen", 10), ("emergencia.volumen", 100), ("emergencia.repetir_s", 5),
    ("emergencia.repetir_s", 60), ("emergencia.permanencia_s", 1.5), ("emergencia.permanencia_s", 5.0),
    ("emergencia.detener_s", 2.0), ("emergencia.detener_s", 5.0), ("emergencia.activa", False),
    ("emergencia.repetir_voz", False), ("emergencia.mensaje", "Me duele"), ("emergencia.mensaje", "x" * 60),
])
def test_valores_del_borde_se_aceptan(ruta, bueno):
    out, problemas = _validar(**{ruta: bueno})
    assert out["emergencia"][ruta.split(".")[1]] == bueno
    assert problemas == []


def test_repetir_s_es_entero():
    out, problemas = _validar(**{"emergencia.repetir_s": 12.6})
    assert out["emergencia"]["repetir_s"] == 13 and isinstance(out["emergencia"]["repetir_s"], int)
    assert problemas


def test_bloque_de_tipo_equivocado_o_ausente_toma_la_fabrica():
    out, problemas = _validar(emergencia="encendida")
    assert out["emergencia"] == C.FABRICA["emergencia"] and problemas
    d = C.por_defecto()
    del d["emergencia"]
    del d["atajos"]["emergencia"]
    out = C.validar(d)
    assert out["emergencia"] == C.FABRICA["emergencia"]
    assert out["atajos"]["emergencia"] == "Ctrl+Alt+A"


def test_configuracion_vieja_de_la_1_0_se_lee_con_la_emergencia_de_fabrica(tmp_path):
    vieja = C.por_defecto()
    del vieja["emergencia"]
    del vieja["atajos"]["emergencia"]
    del vieja["lupa"]
    vieja["gestos"]["boca"]["largo"] = "pausar"
    ruta = tmp_path / "config.json"
    ruta.write_text(json.dumps(vieja), "utf-8")
    cfg = C.Configuracion(ruta)
    datos = cfg.cargar()
    assert cfg.aviso is None
    assert datos["emergencia"] == C.FABRICA["emergencia"]
    assert datos["atajos"]["emergencia"] == "Ctrl+Alt+A"
    assert datos["gestos"]["boca"]["largo"] == "pausar"


@pytest.mark.parametrize("gesto", ["boca", "cejas", "sonrisa"])
def test_gesto_corto_emergencia_pasa_a_ninguna_y_el_largo_se_acepta(gesto):
    out, problemas = _validar(**{f"gestos.{gesto}.corto": "emergencia"})
    assert out["gestos"][gesto]["corto"] == "ninguna"
    assert any(f"gestos.{gesto}.corto" in p and "largo" in p for p in problemas)
    out, problemas = _validar(**{f"gestos.{gesto}.largo": "emergencia"})
    assert out["gestos"][gesto]["largo"] == "emergencia" and problemas == []


def test_el_parpadeo_nunca_pide_ayuda():
    out, problemas = _validar(**{"gestos.parpadeo.fuera_barrido": "emergencia"})
    assert out["gestos"]["parpadeo"]["fuera_barrido"] == "ninguna"
    assert any("parpadeo" in p for p in problemas)
    assert "emergencia" in K.ACCIONES_GESTO
    assert "emergencia" not in OP.ACCIONES_PARPADEO
    assert "emergencia" not in OP.ACCIONES_GESTO_UI          # el gesto corto no la ofrece
    assert "emergencia" in OP.ACCIONES_GESTO_LARGO_UI        # el largo sí


def test_el_gesto_largo_de_emergencia_no_cuenta_como_forma_de_reanudar():
    out, _ = _validar(**{"gestos.boca.largo": "emergencia", "gestos.cejas.activo": False,
                         "permanencia.activa": False})
    # sin pausar en ningún gesto: la validación vuelve a encender la permanencia
    assert out["permanencia"]["activa"] is True


def test_identificadores_y_constantes():
    assert K.IDS_EMERGENCIA == ("barra:ayuda", "teclado:ayuda", "pestana:ayuda")
    assert K.ID_ATENDIDO == "emergencia:atendido"
    assert K.BOTONES_BARRA[-1] == ("ayuda", "AYUDA")


# =========================================================================== atajo
def test_atajo_de_emergencia_se_registra_justo_despues_de_salir():
    orden = atajos.orden_registro(C.FABRICA["atajos"])
    assert [n for _, n, _ in orden][:2] == ["salir", "emergencia"]
    # los identificadores de los demás atajos no cambian (posición en el diccionario)
    ids = {n: i for i, n, _ in orden}
    assert ids["pausar"] == 1 and ids["salir"] == 5 and ids["emergencia"] == 6
    assert atajos.interpretar("Ctrl+Alt+A") == (atajos.MOD_CONTROL | atajos.MOD_ALT, ord("A"))


def test_atajo_de_emergencia_invalido_o_repetido_avisa():
    bien = dict(C.FABRICA["atajos"])
    assert OP.atajos_validos(bien, revisar_teclado=False) is None
    malo = dict(bien, emergencia="A")
    assert OP.atajos_validos(malo, revisar_teclado=False) == T.t(
        "op_atajo_invalido", texto="A", motivo="tiene que llevar Ctrl o Alt")
    assert OP.atajos_validos(dict(bien, emergencia=""), revisar_teclado=False) == T.t("op_atajo_vacio")
    repetido = OP.atajos_validos(dict(bien, emergencia="Ctrl+Alt+Espacio"), revisar_teclado=False)
    assert repetido and "Pausar / reanudar" in repetido
    otro = OP.atajos_validos(dict(bien, teclado="Ctrl+Alt+A"), revisar_teclado=False)
    assert otro and "Ctrl+Alt+A" in otro
    # el aviso del hilo de atajos nombra la función de emergencia con palabras
    assert "Apagar la alarma de AYUDA" in atajos.texto_repetido("Ctrl+Alt+A", "emergencia")


def test_restablecer_fabrica_conserva_el_atajo_y_vuelve_la_emergencia(tmp_path):
    cfg = C.Configuracion(tmp_path / "config.json")
    cfg.cargar()
    cfg.datos["atajos"]["emergencia"] = "Ctrl+Alt+F9"
    cfg.datos["emergencia"]["volumen"] = 40
    cfg.restablecer_fabrica()
    assert cfg.datos["atajos"]["emergencia"] == "Ctrl+Alt+F9"
    assert cfg.datos["emergencia"]["volumen"] == 100


# =========================================================================== opciones y textos
def test_pestana_emergencia_y_sus_controles_tienen_rango_y_texto():
    assert "emergencia" in OP.PESTANAS
    ctl = OP.controles("emergencia")
    rutas = [c[1] for c in ctl]
    assert rutas == ["emergencia.activa", "probar_alarma", "emergencia.mensaje", "emergencia.volumen",
                     "emergencia.repetir_voz", "emergencia.repetir_s", "emergencia.permanencia_s",
                     "emergencia.detener_s"]
    for tipo, ruta, clave, paso, fmt in ctl:
        assert clave in T.TXT, clave
        if tipo == "num":
            assert ruta in C.RANGOS
            lo, hi = C.RANGOS[ruta]
            d = C.por_defecto()
            for _ in range(200):
                d_nuevo = OP.paso_numero(d, ruta, paso, +1)
                OP.escribir(d, ruta, d_nuevo)
            assert OP.leer(d, ruta) == hi
            for _ in range(200):
                OP.escribir(d, ruta, OP.paso_numero(d, ruta, paso, -1))
            assert OP.leer(d, ruta) == lo
            assert C.validar(d)["emergencia"][ruta.split(".")[1]] == lo
            assert fmt(lo)
    atj = [c[1] for c in OP.controles("atajos")]
    assert "atajos.emergencia" in atj and len(atj) <= OP.FILAS_POR_PAGINA


def test_textos_de_la_emergencia():
    assert T.t("btn_ayuda") == "Cómo usar" and T.t("tec_ayuda_btn") == "Cómo usar"
    assert T.t("barra_ayuda") == "AYUDA" and T.t("tec_emergencia") == "AYUDA"
    assert T.t("emergencia_titulo") == "NECESITO AYUDA"
    assert T.t("accion_emergencia") == "Pedir AYUDA (alarma)"
    assert T.nombre_accion("emergencia") == "Pedir AYUDA (alarma)"
    assert T.t("emergencia_como_parar", atajo="Ctrl+Alt+A").endswith("usar Ctrl+Alt+A.")
    assert T.atajos_kw(C.FABRICA)["emergencia"] == "Ctrl+Alt+A"
    # la Ayuda nombra el atajo que de verdad está puesto
    cfg = C.por_defecto()
    cfg["atajos"]["emergencia"] = "Ctrl+Alt+F9"
    assert "Ctrl+Alt+F9" in T.t("ayuda_emergencia", mensaje="x", **T.atajos_kw(cfg), **T.ayuda_kw(cfg))
    assert "Ctrl+Alt+F9" in T.t("ayuda_cuidador", **T.atajos_kw(cfg))
    for clave in [k for k in T.TXT if "emergencia" in k or k in ("btn_ayuda", "tec_ayuda_btn", "barra_ayuda")]:
        bajo = " " + T.TXT[clave].lower() + " "
        for p in T.TUTEO + T.PALABRAS_PROHIBIDAS:
            assert p not in bajo, (clave, p)
    # «Ayuda» como palabra suelta de un botón ya no se usa: AYUDA es solo la emergencia
    assert all(v != "Ayuda" for k, v in T.TXT.items() if k.startswith(("btn_", "tec_", "barra_")))
