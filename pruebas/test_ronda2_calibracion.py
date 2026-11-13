"""Ronda 2 de arreglos: la calibración practica y comprueba el parpadeo largo de quien usa el
barrido, sin pedir giros de cabeza en «Solo comunicación»; la prueba final no son círculos."""
import copy

from conftest import REPOSO, cfg_prueba, medidas
from lycan_face_control.calibracion_guiada import DURACION_S, PARPADEOS_LARGOS, Guia, pasos_para
from lycan_face_control.config import validar
from lycan_face_control.ui import textos as T
from test_interfaz import _girar, app_viva  # noqa: F401  (fixture)

IO_BIEN = 0.15


def _cfg(**k):
    return validar(cfg_prueba(**k))


def test_con_barrido_hay_paso_de_parpadeo_largo():
    p = pasos_para(_cfg(**{"teclado.barrido": True}))
    assert "parpadeo_largo" in p and p.index("parpadeo_largo") == p.index("parpadeo") + 1
    assert "izq" in p                                   # con barrido el puntero puede usarse
    p = pasos_para(_cfg(**{"teclado.solo_comunicacion": True}))
    assert "parpadeo_largo" in p
    assert not any(x in p for x in ("izq", "der", "arr", "aba"))
    assert "parpadeo_largo" not in pasos_para(_cfg())


def _correr(guia, t, dur, fuente, dt=0.05):
    fin = t + dur
    while t < fin - 1e-9 and not guia.terminado:
        guia.alimentar(t, fuente(t), IO_BIEN)
        t += dt
    return t


def _hasta_el_paso(guia, t, paso):
    while guia.paso != paso and not guia.terminado:
        t = _correr(guia, t, 0.05, lambda _t: medidas())
    return t


def _cierres(n, profundo=True):
    """n cierres de 1,2 s separados por 1,5 s con los ojos abiertos."""
    ear = (0.04, 0.04) if profundo else (0.18, 0.19)    # 0,18/0,357 = 0,5: cerrado pero no profundo

    def fuente_desde(t0):
        def f(t):
            k = (t - t0) % 2.7
            if (t - t0) < n * 2.7 and 0.5 <= k < 1.7:
                return medidas(ear_der=ear[0], ear_izq=ear[1])
            return medidas()
        return f
    return fuente_desde


def test_paso_de_parpadeo_largo_reconoce_tres_cierres():
    cfg = _cfg(**{"teclado.solo_comunicacion": True})
    g = Guia(cfg, 0.0, preparar_s=0.1)
    t = _hasta_el_paso(g, 0.0, "parpadeo_largo")
    t = _correr(g, t, 0.2, lambda _t: medidas())         # preparar
    t = _correr(g, t, 12.0, _cierres(3)(t))
    assert g.resultados.get("parpadeo_largo") == PARPADEOS_LARGOS
    assert "parpadeo_largo" not in g.avisos
    while not g.terminado:
        t = _correr(g, t, 0.5, lambda _t: medidas())
    cal, largo, pocos = g.resultado()
    assert g.parpadeos_largos == PARPADEOS_LARGOS
    assert pocos == []                                   # sin giros: no hay aviso de poco movimiento
    assert cal["der"] > cal["centro"][0] > cal["izq"]


def test_paso_de_parpadeo_largo_avisa_si_no_los_logra():
    cfg = _cfg(**{"teclado.barrido": True})
    g = Guia(cfg, 0.0, preparar_s=0.1)
    t = _hasta_el_paso(g, 0.0, "parpadeo_largo")
    t = _correr(g, t, 0.2, lambda _t: medidas())
    est = None
    t0 = t
    f = _cierres(20, profundo=False)(t)
    while g.paso == "parpadeo_largo" and t - t0 < DURACION_S["parpadeo_largo"] + 5:
        est = g.alimentar(t, f(t), IO_BIEN)
        t += 0.05
    assert g.resultados.get("parpadeo_largo", 0) < PARPADEOS_LARGOS
    assert "parpadeo_largo" in g.avisos


def test_estado_del_paso_muestra_la_barra_y_el_contador():
    cfg = _cfg(**{"teclado.solo_comunicacion": True})
    g = Guia(cfg, 0.0, preparar_s=0.1)
    t = _hasta_el_paso(g, 0.0, "parpadeo_largo")
    t = _correr(g, t, 0.2, lambda _t: medidas())
    for _ in range(25):                                  # 1,25 s con los ojos cerrados
        est = g.alimentar(t, medidas(ear_der=0.04, ear_izq=0.04), IO_BIEN)
        t += 0.05
    assert est.parpadeo_listo and est.parpadeo >= 1.0
    est = g.alimentar(t, medidas(), IO_BIEN)
    est = g.alimentar(t + 0.1, medidas(), IO_BIEN)
    est = g.alimentar(t + 0.2, medidas(), IO_BIEN)
    assert est.contador == 1


def test_prueba_final_con_barrido_no_son_circulos(app_viva):  # noqa: F811
    app = app_viva
    app.cfg.datos["teclado"]["solo_comunicacion"] = True
    _girar(app, 300)
    c = app.abrir_calibracion()
    c.empezar()
    g = c.guia = Guia(copy.deepcopy(app.cfg.datos), 0.0, preparar_s=0.1)
    t = _hasta_el_paso(g, 0.0, "parpadeo_largo")
    t = _correr(g, t, 0.2, lambda _t: medidas())
    t = _correr(g, t, 12.0, _cierres(3)(t))
    while not g.terminado:
        t = _correr(g, t, 0.5, lambda _t: medidas())
    c._finalizar_pasos()
    assert c.fase == "final"
    assert c.lbl_final.cget("text") == T.t("cal_final_barrido_bien")
    assert c.circulos == {}
    assert getattr(c, "_cierre_solo", None) is not None
    c._cerrar_solo()
    assert c.fase == "cerrada"


def test_con_menos_de_cuatro_circulos_se_orienta(app_viva):  # noqa: F811
    app = app_viva
    _girar(app, 300)
    c = app.abrir_calibracion()
    c.fase = "final"
    c.pocos, c.no_detectados, c.parpadeos_largos = [], [], None
    c._pantalla_final()
    c.alcanzar(1)
    assert T.t("cal_final_regular") in c.lbl_final.cget("text")
    for i in (2, 3, 4):
        c.alcanzar(i)
    assert T.t("cal_final_bien") in c.lbl_final.cget("text")
    c.terminar()


def test_reposo_tiene_las_medidas_de_referencia():
    assert REPOSO["ear_der"] > 0.3
