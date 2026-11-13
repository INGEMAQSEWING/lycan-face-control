"""Filtros puros copiados de Lycan Mouse Control (One Euro, histéresis, antirrebote, promedio)."""
import math

import numpy as np
import pytest

from lycan_face_control.filtros import Antirrebote, Histeresis, OneEuro, PromedioExp


def test_one_euro_quieto_tiembla_menos_de_2px():
    rng = np.random.default_rng(1)
    f = OneEuro(0.5, 0.015, 1.0)
    t, errores = 0.0, []
    for k in range(600):
        t += 1 / 30
        y = f(683.0 + rng.normal(0, 6), t)
        if k > 60:
            errores.append(abs(y - 683.0))
    assert np.mean(errores) < 2.0


def test_one_euro_retraso_a_300px_por_s_menor_de_60ms():
    f = OneEuro(0.5, 0.015, 1.0)
    t, v = 0.0, 300.0
    retrasos = []
    for k in range(150):
        t += 1 / 30
        real = v * t
        y = f(real, t)
        if k > 60:
            retrasos.append((real - y) / v * 1000)
    assert np.mean(retrasos) < 60


def test_one_euro_dt_variable_sin_saltos():
    rng = np.random.default_rng(2)
    f = OneEuro(0.5, 0.015, 1.0)
    t, ant = 0.0, None
    for k in range(300):
        t += float(rng.choice([1 / 30, 1 / 15, 1 / 20]))
        y = f(100.0 * t, t)
        if ant is not None:
            assert y >= ant - 1e-9           # sigue una rampa: nunca retrocede
            assert y - ant < 100.0 * (1 / 15) * 3
        ant = y


def test_one_euro_reset_evita_latigazo():
    f = OneEuro(0.5, 0.015, 1.0)
    for k in range(60):
        f(0.0, k / 30)
    f.reset()
    assert f(1000.0, 3.0) == 1000.0       # tras reset arranca en el valor nuevo


def test_one_euro_valor_no_finito_se_ignora():
    f = OneEuro()
    f(10.0, 0.0)
    assert f(float("nan"), 0.033) == 10.0


@pytest.mark.parametrize("valores,esperado", [
    ([0.5, 0.3, 0.27, 0.35, 0.41, 0.43, 0.3], [False, False, True, True, True, False, False]),
    ([0.2, 0.41, 0.2, 0.5], [True, True, True, False]),
    ([float("nan"), 0.1, float("nan")], [False, True, True]),
])
def test_histeresis_tabla(valores, esperado):
    h = Histeresis(0.28, 0.42, menor_es_dentro=True)
    assert [h.actualizar(v) for v in valores] == esperado


def test_histeresis_mayor_es_dentro():
    h = Histeresis(1.9, 1.6, menor_es_dentro=False)
    assert [h.actualizar(v) for v in (1.0, 2.0, 1.7, 1.5, 1.8)] == [False, True, True, False, False]


def test_antirrebote_en_milisegundos():
    a = Antirrebote(66, 66)
    assert a.actualizar(True, 0.000) is False
    assert a.actualizar(True, 0.033) is False
    assert a.actualizar(True, 0.066) is True
    assert a.t_inicio_crudo == pytest.approx(0.0)
    assert a.actualizar(False, 0.100) is True
    assert a.actualizar(True, 0.120) is True     # rebote corto: no sale
    assert a.actualizar(False, 0.130) is True
    assert a.actualizar(False, 0.200) is False


def test_antirrebote_igual_si_bajan_los_cuadros_a_la_mitad():
    """Caída de 30 a 15 cuadros/s a mitad de una seña: el tiempo para confirmar es el mismo."""
    a = Antirrebote(66, 66)
    t = 0.0
    tiempos = [0.0, 1 / 30, 1 / 30 + 1 / 15, 1 / 30 + 2 / 15]
    salida = [a.actualizar(True, x) for x in tiempos]
    assert salida == [False, False, True, True]


def test_promedio_exponencial():
    p = PromedioExp(0.5)
    assert p.actualizar(1.0) == 1.0
    assert p.actualizar(0.0) == 0.5
    assert p.actualizar(float("nan")) == 0.5
