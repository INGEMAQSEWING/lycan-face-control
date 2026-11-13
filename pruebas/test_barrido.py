"""Parte 4: barrido (sección 7.2), con tiempos reales simulados."""
from __future__ import annotations

import pytest

from lycan_face_control.barrido import ELEMENTOS, FILAS, VOLVER, Barrido

FILAS_EJ = [["si", "no", "sed"], ["a", "b"], ["borrar", "hablar"]]
PASO = 1.0


def correr(b: Barrido, t: float, hasta: float, dt: float = 0.05, ojos=False):
    est = None
    while t < hasta - 1e-9:
        t = round(t + dt, 6)
        est = b.actualizar(t, ojos, None)
    return t, est


def test_avanza_solo_y_el_primero_se_queda_un_50_por_ciento_mas():
    b = Barrido(FILAS_EJ, PASO, t0=0.0)
    t, est = correr(b, 0.0, 1.45)
    assert est.nivel == FILAS and est.fila == 0 and est.resaltado == ("si", "no", "sed")
    t, est = correr(b, t, 1.55)
    assert est.fila == 1                                   # el primero duró 1,5 s
    t, est = correr(b, t, 2.5)
    assert est.fila == 2                                   # los demás 1,0 s
    t, est = correr(b, t, 3.55)
    assert est.fila == 0                                   # vuelve a empezar


def test_parpadeo_largo_elige_fila_y_luego_elemento():
    b = Barrido(FILAS_EJ, PASO, t0=0.0)
    t, _ = correr(b, 0.0, 1.6)                             # fila 1 iluminada
    est = b.actualizar(t, False, "elegir")
    assert est.entro_fila and est.nivel == ELEMENTOS and est.resaltado == ("a",)
    t, est = correr(b, t, t + 1.6)                         # el primero 1,5 s -> "b"
    assert est.resaltado == ("b",)
    est = b.actualizar(t, False, "elegir")
    assert est.elegido == "b"
    # pausa de 0,8 s y vuelve a la primera fila
    assert est.en_pausa and est.resaltado == ()
    assert b.actualizar(t + 0.3, False, "elegir").elegido is None      # en la pausa no se elige
    t, est = correr(b, t, t + 0.9)
    assert est.nivel == FILAS and est.fila == 0 and not est.en_pausa


def test_ojos_cerrando_congela_y_se_elige_lo_que_estaba_al_cerrar():
    b = Barrido(FILAS_EJ, PASO, t0=0.0)
    t, _ = correr(b, 0.0, 1.4)                              # fila 0, a punto de pasar
    # cierra los ojos 0,9 s: el resaltado no cambia aunque pase el tiempo
    t, est = correr(b, t, t + 0.9, ojos=True)
    assert est.congelado and est.fila == 0
    # al abrir llega el parpadeo largo un poco después; elige la fila 0 (la del cierre)
    t, est = correr(b, t, t + 0.1)
    est = b.actualizar(t + 0.05, False, "elegir")
    assert est.nivel == ELEMENTOS and est.fila == 0


def test_parpadeo_natural_no_elige_y_el_barrido_sigue():
    b = Barrido(FILAS_EJ, PASO, t0=0.0)
    t, _ = correr(b, 0.0, 0.5)
    t, est = correr(b, t, t + 0.2, ojos=True)               # parpadeo natural de 200 ms
    assert est.fila == 0
    t, est = correr(b, t, t + 1.2)
    assert est.fila == 1 and est.nivel == FILAS and est.elegido is None


def test_volver_al_final_de_la_fila():
    b = Barrido(FILAS_EJ, PASO, t0=0.0)
    est = b.actualizar(0.1, False, "elegir")                # entra a la fila 0
    t, est = correr(b, 0.1, 0.1 + 1.5 + 1.0 + 1.0 + 0.05)  # si(1,5) no(1) sed(1) -> Volver
    assert est.volver and est.resaltado == ()
    est = b.actualizar(t, False, "elegir")
    assert est.elegido == VOLVER and est.nivel == FILAS and est.fila == 0


def test_dos_vueltas_en_una_fila_vuelve_a_las_filas():
    b = Barrido(FILAS_EJ, PASO, t0=0.0)
    b.actualizar(0.0, False, "elegir")                      # fila 0: 3 elementos + Volver
    # una vuelta = 1,5 + 1 + 1 + 1 = 4,5 s; dos vueltas = 9 s
    t, est = correr(b, 0.0, 8.9)
    assert est.nivel == ELEMENTOS
    t, est = correr(b, t, 9.1)
    assert est.nivel == FILAS


def test_tres_vueltas_sin_elegir_se_detiene_y_un_parpadeo_lo_reanuda():
    b = Barrido(FILAS_EJ, PASO, t0=0.0)
    vuelta = 1.5 + 1.0 + 1.0
    t, est = correr(b, 0.0, 3 * vuelta - 0.1)
    assert not est.detenido
    t, est = correr(b, t, 3 * vuelta + 0.1)
    assert est.detenido and est.resaltado == ()
    t, est = correr(b, t, t + 10)                           # detenido: no avanza
    assert est.detenido
    est = b.actualizar(t, False, "elegir")
    assert not est.detenido and est.fila == 0 and est.elegido is None


def test_siguiente_avanza_a_mano():
    b = Barrido(FILAS_EJ, PASO, t0=0.0)
    est = b.actualizar(0.1, False, "siguiente")
    assert est.fila == 1
    est = b.actualizar(0.2, False, "siguiente")
    assert est.fila == 2


def test_cambiar_las_filas_y_el_paso():
    b = Barrido(FILAS_EJ, 0.1, t0=0.0)
    assert b.paso_s == 0.5                                  # rango 0,5 a 4,0
    b.cambiar_paso(9)
    assert b.paso_s == 4.0
    b.poner_filas([["x"], [], ["y", "z"]], 1.0)
    assert b.filas == [["x"], ["y", "z"]]                   # las filas vacías se quitan
    vacio = Barrido([], 1.0)
    assert vacio.actualizar(1.0, False, "elegir").detenido


@pytest.mark.parametrize("fps", [30, 15, 8])
def test_tiempos_reales_con_pocos_cuadros(fps):
    b = Barrido(FILAS_EJ, PASO, t0=0.0)
    _, est = correr(b, 0.0, 1.6, dt=1.0 / fps)
    assert est.fila == 1
