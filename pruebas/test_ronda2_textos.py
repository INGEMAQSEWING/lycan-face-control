"""Ronda 2 de arreglos: la ayuda dice la verdad (atajos puestos, forma de pausar, clic sin
permanencia), textos que antes no se mostraban y el README."""
from pathlib import Path
from types import SimpleNamespace

from conftest import cfg_prueba
from lycan_face_control import constantes as K
from lycan_face_control.ui import textos as T
from lycan_face_control.version import VERSION

RAIZ = Path(__file__).resolve().parents[1]
UI = RAIZ / "lycan_face_control" / "ui"


def _ayuda(seccion, cfg):
    """Igual que ui/ayuda.py arma el texto de una pestaña."""
    return T.t(f"ayuda_{seccion}", version=VERSION, pausa=T.pausa_uso(cfg), barra=T.barra_uso(cfg),
               **T.atajos_kw(cfg))


def test_la_ayuda_dice_los_atajos_que_estan_puestos():
    cfg = cfg_prueba(**{"atajos.pausar": "Ctrl+Alt+P"})
    texto = _ayuda("cuidador", cfg)
    assert "Ctrl+Alt+P = pausar" in texto and "Ctrl+Alt+Espacio" not in texto
    assert "Ctrl+Alt+P" in T.t("globo_pausa", **T.atajos_kw(cfg))
    assert "Ctrl+Alt+P" in T.t("asis_2", **T.atajos_kw(cfg))
    fab = _ayuda("cuidador", cfg_prueba())
    assert "Ctrl+Alt+Espacio = pausar" in fab


def test_ningun_texto_de_ayuda_queda_con_llaves():
    cfg = cfg_prueba()
    for sec in ("uso", "cuidador", "problemas", "acerca"):
        assert "{" not in _ayuda(sec, cfg), sec
    for clave in ("globo_pausa", "asis_2"):
        assert "{" not in T.t(clave, **T.atajos_kw(cfg))


def test_la_linea_de_pausa_sigue_a_los_gestos():
    fab = T.pausa_uso(cfg_prueba())
    assert "boca" in fab and "3 segundos" in fab
    sin_boca = T.pausa_uso(cfg_prueba(**{"gestos.boca.activo": False}))
    assert sin_boca == T.t("pausa_sin_gesto")
    cejas = T.pausa_uso(cfg_prueba(**{"gestos.boca.largo": "ninguna", "gestos.cejas.largo": "pausar"}))
    assert "cejas" in cejas and "boca" not in cejas
    assert "boca" not in _ayuda("uso", cfg_prueba(**{"gestos.boca.activo": False}))


def test_subtitulo_sin_permanencia_no_dice_quedese_quieto():
    m = SimpleNamespace(estado=K.ACTIVO, submodo=K.NORMAL, recentrando=None, pausa_auto=False)
    v = SimpleNamespace(maquina=m, camara=None)
    assert T.subtitulo(v, cfg_prueba()) == T.t("sub_ACTIVO")
    sin = T.subtitulo(v, cfg_prueba(**{"permanencia.activa": False}))
    assert sin == T.t("sub_ACTIVO_gestos") and "quieto" not in sin
    cfg = cfg_prueba()
    cfg["permanencia"]["activa"] = False
    cfg["gestos"]["boca"]["activo"] = cfg["gestos"]["cejas"]["activo"] = False
    assert T.subtitulo(v, cfg) == T.t("sub_ACTIVO_sin_clic")
    assert T.subtitulo(v) == T.t("sub_ACTIVO")          # sin configuración, como antes


def test_textos_que_antes_no_se_mostraban_ahora_se_usan():
    teclado = (UI / "teclado.py").read_text("utf-8")
    calib = (UI / "calibracion.py").read_text("utf-8")
    editor = (UI / "editor_frases.py").read_text("utf-8")
    assert '"tec_ayuda"' in teclado
    assert '"cal_final_regular"' in calib
    assert '"ed_no_olvido"' in editor and "ed_no_olvido" in T.TXT
    assert "tilde" in _ayuda("uso", cfg_prueba())


def test_readme_nombra_opciones_que_existen():
    readme = (RAIZ / "README.md").read_text("utf-8")
    assert "tamaño del círculo" not in readme
    assert T.t("op_perm_radio") in readme and T.t("op_perm_tiempo") in readme
    assert "aunque \"Decir las frases en voz alta\" esté en No" in readme
