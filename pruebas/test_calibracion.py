"""Lógica de la calibración guiada (sección 4.1) con caras sintéticas."""
import json

import numpy as np
import pytest

from conftest import Sim, medidas
from lycan_face_control import calibracion as C
from lycan_face_control import config
from lycan_face_control import constantes as K
from lycan_face_control.cara import medir_si_valida
from lycan_face_control.gestos import Gestos
from lycan_face_control.mapeo import MONITOR_REFERENCIA, MapeoCabeza
from sintetico import cara, linea_de_tiempo


def recolectar(claves, fps=30, t0=0.0, rng=None):
    rec = C.Recolector(t0)
    for t, P in linea_de_tiempo(claves, fps, rng=rng):
        rec.agregar(t, None if P is None else medir_si_valida(P, 640, 480))
    return rec


def test_percentil():
    assert C.percentil([1, 2, 3, 4, 5], 50) == 3
    assert C.percentil([0, 10], 90) == pytest.approx(9)
    assert np.isnan(C.percentil([], 90))


def test_posicion():
    assert C.posicion_correcta(0.05) == "lejos"
    assert C.posicion_correcta(0.15) == "bien"
    assert C.posicion_correcta(0.3) == "cerca"


def test_centro_descarta_el_primer_medio_segundo_y_usa_la_mediana():
    rng = np.random.default_rng(2)
    claves = [(0.0, {"yaw": 15.0}), (0.4, {"yaw": 15.0}), (0.45, {"ruido": 0.3}), (3.0, {"ruido": 0.3})]
    rec = recolectar(claves, rng=rng)
    c = C.centro(rec)
    assert c == pytest.approx((0.022, 0.556), abs=0.01)


def test_rangos_con_percentil_90_y_sentido():
    c = (0.022, 0.556)
    recs = {
        "der": recolectar([(0.0, {}), (1.0, {"yaw": 12.0}), (2.0, {"yaw": 12.0})]),
        "izq": recolectar([(0.0, {}), (1.0, {"yaw": -12.0}), (2.0, {"yaw": -12.0})]),
        "aba": recolectar([(0.0, {}), (1.0, {"pitch": 10.0}), (2.0, {"pitch": 10.0})]),
        "arr": recolectar([(0.0, {}), (1.0, {"pitch": -10.0}), (2.0, {"pitch": -10.0})]),
    }
    ext, pocos = C.rangos(c, recs)
    assert pocos == []
    max_der = medir_si_valida(cara(yaw=12.0), 640, 480).yaw_n
    assert c[0] < ext["der"] <= max_der + 1e-9
    assert ext["izq"] < c[0] and ext["aba"] > c[1] and ext["arr"] < c[1]


def test_poco_movimiento_usa_el_minimo_y_avisa():
    c = (0.022, 0.556)
    recs = {"der": recolectar([(0.0, {}), (2.0, {"yaw": 0.3})])}
    ext, pocos = C.rangos(c, recs)
    assert "der" in pocos and "izq" in pocos
    assert ext["der"] - c[0] == pytest.approx(0.02)


def test_signo_invertido_sale_de_la_calibracion():
    """Si al pedir "derecha" el yaw baja (cámara sin espejo), la calibración lo registra y el
    puntero igual va a la derecha."""
    c = (0.022, 0.556)
    recs = {"der": recolectar([(0.0, {}), (1.0, {"yaw": -12.0}), (2.0, {"yaw": -12.0})]),
            "izq": recolectar([(0.0, {}), (1.0, {"yaw": 12.0}), (2.0, {"yaw": 12.0})])}
    ext, _ = C.rangos(c, recs)
    assert ext["der"] < c[0] < ext["izq"]
    cal = C.construir(c, dict(ext, aba=0.65, arr=0.45), dict(C.BASE_REFERENCIA))
    assert cal["signo_x"] == -1.0
    m = MapeoCabeza(MONITOR_REFERENCIA, cal)
    yaw_derecha = medir_si_valida(cara(yaw=-8.0), 640, 480).yaw_n
    assert m.a_pixeles(yaw_derecha, 0.556)[0] > MONITOR_REFERENCIA.centro[0]


def test_bases_ignoran_los_parpadeos():
    claves = [(0.0, {}), (1.0, {}), (1.03, {"ojos": 0.0}), (1.2, {"ojos": 0.0}), (1.23, {}), (3.0, {})]
    b = C.bases(recolectar(claves))
    assert b["ear_der"] == pytest.approx(0.357, abs=0.01)
    assert b["ear_izq"] == pytest.approx(0.375, abs=0.01)
    assert b["mar"] == pytest.approx(0.016, abs=0.005)
    assert b["cejas"] == pytest.approx(0.356, abs=0.005)


def test_parpadeos_naturales_y_parpadeo_largo():
    claves = [(0.0, {})]
    t = 1.0
    for d in (0.15, 0.2, 0.25, 0.18):
        claves += [(t, {}), (t + 0.03, {"ojos": 0.0}), (t + d - 0.03, {"ojos": 0.0}), (t + d, {})]
        t += 2.0
    claves.append((t, {}))
    rec = recolectar(claves)
    base = C.bases(rec)
    durs = C.parpadeos_naturales(rec, base)
    assert len(durs) == 4
    assert max(durs) <= 250
    assert C.parpadeo_largo_ms(durs) == 600            # 2 × 0,25 s < 600 => 600
    assert C.parpadeo_largo_ms([450]) == 900
    assert C.parpadeo_largo_ms([1500]) == 2000
    assert C.parpadeo_largo_ms([]) == 800


def test_umbral_de_gesto_al_50_por_ciento():
    base = dict(C.BASE_REFERENCIA)
    assert C.umbral_gesto("boca", base, 0.716) == pytest.approx(0.016 + 0.35)
    # alguien que abre poco (pero de verdad): no baja de la mitad del umbral de fábrica
    assert C.umbral_gesto("boca", base, 0.18) == pytest.approx(0.016 + 0.125)
    # quien NO hizo el gesto (solo ruido): se queda el de fábrica, nunca más sensible
    assert C.umbral_gesto("boca", base, 0.1) is None
    assert C.umbral_gesto("boca", {"mar": 0.016}, 0.020) is None
    assert C.umbral_gesto("cejas", {"cejas": 0.356}, 0.358) is None
    assert not C.gesto_detectado("cejas", {"cejas": 0.356}, 0.358)
    assert C.gesto_detectado("boca", base, 0.5)
    assert C.umbral_gesto("cejas", base, 0.356 * 1.3) == pytest.approx(1.15)
    assert C.umbral_gesto("boca", base, 0.01) is None
    assert C.umbral_gesto("boca", base, None) is None
    assert C.umbral_gesto("guiño", base, 1.0) is None


def test_calibracion_completa_se_guarda_y_se_usa():
    c = (0.03, 0.55)
    ext = {"der": 0.12, "izq": -0.06, "aba": 0.65, "arr": 0.45}
    base = dict(C.BASE_REFERENCIA)
    cal = C.construir(c, ext, base, {"boca": 0.2, "cejas": None}, [150, 220])
    assert C.calibracion_valida(cal)
    assert cal["parpadeo_natural_max_ms"] == 220 and cal["parpadeos_min"] == 2
    assert "cejas" not in cal["umbrales"]
    # pasa la validación de la configuración (JSON sencillo)
    cfg = config.por_defecto()
    cfg["perfiles"]["Principal"]["calibracion"] = cal
    problemas = []
    out = config.validar(json.loads(json.dumps(cfg)), problemas=problemas)
    assert out["perfiles"]["Principal"]["calibracion"] == cal and not problemas
    # y la usan el mapeo y los gestos
    assert MapeoCabeza(MONITOR_REFERENCIA, cal).a_pixeles(*c) == pytest.approx(MONITOR_REFERENCIA.centro)
    g = Gestos(cfg["gestos"], cal)
    assert g._g["boca"].entrar == pytest.approx(0.2)


@pytest.mark.parametrize("mala", [None, 3, {}, {"centro": [0, "x"]}, {"centro": [0, 0.5], "izq": 1, "der": 1,
                                                                        "arr": 1, "aba": 1, "base": {"mar": -1}}])
def test_calibracion_invalida(mala):
    assert not C.calibracion_valida(mala)


def test_de_punta_a_punta_con_la_maquina():
    """Calibrar con la cara sintética y usar el resultado: mirar al frente = centro de la pantalla
    y mirar al extremo derecho calibrado = borde derecho."""
    rec_c = recolectar([(0.0, {}), (3.0, {})])
    c = C.centro(rec_c)
    recs = {lado: recolectar([(0.0, {}), (1.0, {k: v}), (2.0, {k: v})])
            for lado, k, v in (("der", "yaw", 10.0), ("izq", "yaw", -10.0), ("aba", "pitch", 10.0),
                               ("arr", "pitch", -10.0))}
    ext, pocos = C.rangos(c, recs)
    cal = C.construir(c, ext, C.bases(rec_c))
    s = Sim(calibracion=cal)
    s.quieto(1.5, yaw_n=c[0], pitch_n=c[1])
    cx, cy = s.monitor.centro
    assert abs(s.salida.cursor[0] - cx) <= 3 and abs(s.salida.cursor[1] - cy) <= 3
    s.quieto(1.5, yaw_n=ext["der"], pitch_n=c[1])
    assert s.salida.cursor[0] == s.monitor.ancho - 1
    assert s.maquina.estado == K.ACTIVO


def test_recolector_cuenta_cuadros_sin_cara():
    rec = C.Recolector(0.0)
    rec.agregar(0.1, None)
    rec.agregar(0.6, medidas())
    rec.agregar(0.7, medidas())
    assert rec.sin_cara == 1 and len(rec) == 2 and rec.duracion() == pytest.approx(0.1)
