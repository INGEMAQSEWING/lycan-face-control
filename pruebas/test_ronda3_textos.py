"""Ronda 3 de arreglos: la Ayuda cabe (páginas), dice la verdad sobre Desplazar y sobre «seguir en
ese modo», textos sin género fijo, el permiso de la cámara de Windows, los mensajes de los atajos y
la cámara a menos de 10 cuadros por segundo."""
import pytest

from lycan_face_control.config import RANGOS, por_defecto, validar
from lycan_face_control.ui import textos as T
from lycan_face_control.ui import ayuda as AY
from test_interfaz import _app, _girar


def _ayuda(cfg, seccion):
    return T.t(f"ayuda_{seccion}", version="1", pausa=T.pausa_uso(cfg), barra=T.barra_uso(cfg),
               **T.atajos_kw(cfg))


def test_la_ayuda_explica_desplazar_y_como_salir():
    txt = _ayuda(por_defecto(), "uso")
    assert "Desplazar" in txt and "Terminar" in txt and "incline la cabeza" in txt
    assert "Desplazar antes de hacer clic" not in txt


def test_la_ayuda_dice_si_la_barra_vuelve_sola_segun_la_opcion():
    cfg = por_defecto()
    assert "vuelve solo al clic normal" in _ayuda(cfg, "uso")
    cfg["barra"]["modo_fijo"] = True
    txt = _ayuda(cfg, "uso")
    assert "vuelve solo" not in txt and "Sigue en ese modo" in txt


def test_textos_sin_genero_fijo():
    assert "Bienvenido" not in T.TXT["asis_1_titulo"]
    assert "verlo" not in T.TXT["cal_posicion_timeout"]


def test_el_aviso_de_camara_y_la_ayuda_mencionan_el_permiso_de_windows():
    for clave in ("aviso_no_camara", "ayuda_problemas"):
        assert "Privacidad y seguridad" in T.TXT[clave]
        assert "aplicaciones de escritorio" in T.TXT[clave]


def test_mensajes_de_atajos_en_usted_y_sin_jerga():
    from lycan_face_control.sistema.atajos import AtajoInvalido, interpretar
    for malo in ("", "Ctrl+Alt+Q+W", "Alt+Shift+Ñ", "Ctrl+Alt", "Shift+T"):
        try:
            interpretar(malo)
        except AtajoInvalido as e:
            texto = T.t("op_atajo_invalido", texto=malo, motivo=str(e))
        else:
            pytest.fail(malo)
        bajo = " " + texto.lower() + " "
        for p in T.TUTEO + T.PALABRAS_PROHIBIDAS:
            assert p not in bajo, (malo, p)
        assert "desconocida" not in bajo and "muerta" not in bajo
    for clave in ("op_atajo_vacio", "op_atajo_escribe", "op_atajo_acento"):
        assert T.TXT[clave]


def test_camara_a_menos_de_10_cuadros_vuelve_a_fabrica():
    assert RANGOS["camara.fps"][0] >= 10
    d = por_defecto()
    d["camara"]["fps"] = 5
    assert validar(d)["camara"]["fps"] == por_defecto()["camara"]["fps"]


@pytest.mark.parametrize("escala", (1.0, 1.3, 2.0))
@pytest.mark.parametrize("area", ((0, 0, 1366, 728), (0, 0, 1280, 680)))
def test_cada_seccion_de_la_ayuda_cabe_en_la_ventana(tmp_path, monkeypatch, escala, area):
    monkeypatch.setattr(AY, "area_libre", lambda app, root: area)
    app = _app(tmp_path)
    app.cfg.datos["comodidad"]["escala_letra"] = escala
    app.motor.start()
    try:
        app.construir_interfaz()
    except Exception as e:  # noqa: BLE001
        app.finalizar()
        pytest.skip(f"sin pantalla ({e})")
    try:
        _girar(app, 100)
        v = app.abrir_ayuda()
        for s in AY.SECCIONES:
            v.ir_a(s)
            vistos = set()
            for _ in range(v.paginas):
                v.win.update()
                req = sum(c.winfo_reqheight() for c in v.cuerpo.winfo_children())
                assert req <= v.cuerpo.winfo_height() + 2, (s, v.pagina, req, v.cuerpo.winfo_height())
                vistos.add(v.pagina)
                v.ir_pagina(1)
            assert vistos == set(range(v.paginas))
            if v.paginas > 1:
                ids = {e.ident for e in app.registro.entradas}
                assert "ayuda:pagina:anterior" in ids        # se llega a la última y se puede volver
        v.cerrar()
    finally:
        app.salir_seguro()
        app.finalizar()


def test_las_paginas_de_la_ayuda_no_pierden_texto(tmp_path, monkeypatch):
    monkeypatch.setattr(AY, "area_libre", lambda app, root: (0, 0, 1280, 680))
    app = _app(tmp_path)
    app.cfg.datos["comodidad"]["escala_letra"] = 2.0
    app.motor.start()
    try:
        app.construir_interfaz()
    except Exception as e:  # noqa: BLE001
        app.finalizar()
        pytest.skip(f"sin pantalla ({e})")
    try:
        _girar(app, 100)
        v = app.abrir_ayuda()
        v.ir_a("cuidador")
        completo = _ayuda(app.cfg.datos, "cuidador")
        paginas = v.paginas_de(completo, v._alto_disponible(), ("Segoe UI", 32))
        assert len(paginas) > 1
        assert "\n".join(p for p, _f in paginas) == completo
        v.cerrar()
    finally:
        app.salir_seguro()
        app.finalizar()
