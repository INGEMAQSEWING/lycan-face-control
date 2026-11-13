"""Secuencias aleatorias (200 corridas de 30 s con semillas fijas): ningún camino deja botones o
teclas abajo, y un botón solo está abajo mientras hay un arrastre en curso (sección 8)."""
import math

import numpy as np
import pytest

from conftest import REPOSO, Sim, cfg_prueba, medidas, verificar_invariantes
from lycan_face_control import constantes as K

Y0, P0 = REPOSO["yaw_n"], REPOSO["pitch_n"]
CORRIDAS = 200
DURACION_S = 30.0
FPS = 15.0

CONFIGS = [
    {},
    {"gestos.boca.corto": "arrastrar"},
    {"permanencia.activa": False, "gestos.cejas.corto": "arrastrar"},
    {"puntero.modo": "relativo", "puntero.aceleracion": 3},
    {"puntero.modo": "joystick", "gestos.parpadeo.fuera_barrido": "clic"},
    {"barra.modo_fijo": True, "permanencia.tiempo_s": 0.4, "permanencia.recuperacion_s": 0.3},
    {"seguridad.arrastre_max_s": 10, "seguridad.pausa_sin_cara_s": 3, "gestos.boca.largo": "ninguna"},
    {"teclado.solo_comunicacion": True},
]

ORDENES = ["alternar_pausa", "elegir:barra:arrastrar", "elegir:barra:desplazar", "elegir:barra:doble",
           "elegir:barra:derecho", "elegir:barra:pausa", "elegir:reanudar", "submodo:TECLADO", "submodo:BARRIDO",
           "submodo:NORMAL", "recentrar", "calibrar", "error"]


def tramo_aleatorio(rng):
    """(duración, función t -> Medidas | None) de un comportamiento al azar."""
    dur = float(rng.uniform(0.1, 3.0))
    y1, p1 = Y0 + rng.uniform(-0.15, 0.15), P0 + rng.uniform(-0.15, 0.15)
    y2, p2 = Y0 + rng.uniform(-0.15, 0.15), P0 + rng.uniform(-0.15, 0.15)
    tipo = rng.choice(["quieto", "mover", "boca", "cejas", "sonrisa", "parpadeo", "sin_cara", "temblor", "hablar"])
    ruido = float(rng.uniform(0, 0.003))

    def base(t):
        f = min(t / dur, 1.0) if tipo == "mover" else 0.0
        return dict(yaw_n=y1 + (y2 - y1) * f + rng.normal(0, ruido), pitch_n=p1 + (p2 - p1) * f + rng.normal(0, ruido))

    if tipo == "sin_cara":
        return dur, lambda t: None
    if tipo == "boca":
        return dur, lambda t: medidas(mar=0.6, **base(t))
    if tipo == "cejas":
        return dur, lambda t: medidas(cejas=0.356 * 1.3, **base(t))
    if tipo == "sonrisa":
        return dur, lambda t: medidas(sonrisa=0.557 * 1.3, **base(t))
    if tipo == "parpadeo":
        return dur, lambda t: medidas(ear_der=0.03, ear_izq=0.03, **base(t))
    if tipo == "temblor":
        return dur, lambda t: medidas(yaw_n=y1 + 0.03 * math.sin(t * 20), pitch_n=p1 + 0.02 * math.cos(t * 15))
    if tipo == "hablar":
        return dur, lambda t: medidas(mar=0.016 + 0.4 * abs(math.sin(t * 12)), **base(t))
    return dur, lambda t: medidas(**base(t))


def revisar_paso(s: Sim):
    m = s.maquina
    abajo = s.salida.botones_abajo
    if abajo:
        assert abajo == ["izq"], abajo
        assert m.submodo == K.ARRASTRANDO, (m.estado, m.submodo)
        assert m.estado in (K.ACTIVO, K.SIN_CARA), m.estado
        if m.estado == K.SIN_CARA:
            assert m.vista.sin_cara_s <= s.cfg["seguridad"]["soltar_sin_cara_ms"] / 1000.0 + 1e-6
        assert m.vista.arrastre_s <= s.cfg["seguridad"]["arrastre_max_s"] + 1e-6
    assert not s.salida.teclas_abajo
    if m.estado in (K.PAUSA, K.CALIBRANDO):
        assert not abajo


@pytest.mark.parametrize("bloque", range(8))
def test_secuencias_aleatorias_nunca_dejan_nada_abajo(bloque):
    por_bloque = CORRIDAS // 8
    for corrida in range(bloque * por_bloque, (bloque + 1) * por_bloque):
        rng = np.random.default_rng(1000 + corrida)
        cfg = cfg_prueba(**CONFIGS[corrida % len(CONFIGS)])
        s = Sim(cfg, fps=FPS)
        t_fin = s.t + DURACION_S
        calibrando = False
        while s.t < t_fin:
            if rng.random() < 0.15:
                o = str(rng.choice(ORDENES))
                if o == "alternar_pausa":
                    s.orden("alternar_pausa")
                elif o.startswith("elegir:"):
                    s.orden("elegir", o.split(":", 1)[1])
                elif o.startswith("submodo:"):
                    s.orden("poner_submodo", getattr(K, o.split(":")[1]))
                elif o == "recentrar":
                    s.orden("recentrar")
                elif o == "calibrar":
                    s.orden("terminar_calibracion" if calibrando else "iniciar_calibracion")
                    calibrando = not calibrando
                elif o == "error" and rng.random() < 0.2:
                    s.orden("por_error", RuntimeError("prueba"))
                revisar_paso(s)
            dur, fuente = tramo_aleatorio(rng)
            t0 = s.t
            while s.t < t0 + dur and s.t < t_fin:
                s.paso(fuente(s.t - t0))
                revisar_paso(s)
        verificar_invariantes(s.salida, final=False)
        # al salir del programa se suelta todo
        s.salida.soltar_todo("salir")
        verificar_invariantes(s.salida, final=True)
