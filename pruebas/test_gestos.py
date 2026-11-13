"""Gestos de la cara (sección 3.5) con caras sintéticas. La regla absoluta: los parpadeos
naturales NUNCA producen nada."""
import pytest

from conftest import CAL_SINTETICA, cfg_prueba, medidas
from lycan_face_control.cara import medir_si_valida
from lycan_face_control.gestos import (DobleParpadeoLargo, Gestos, ParpadeoLargo,
                                       ParpadeoListo)
from sintetico import linea_de_tiempo

FPS_TODOS = (30, 15, 8)


def secuencia(claves, fps=30):
    """[(t, Medidas | None)] a partir de claves de la cara sintética."""
    out = []
    for t, P in linea_de_tiempo(claves, fps):
        out.append((t, None if P is None else medir_si_valida(P, 640, 480)))
    return out


def correr(seq, cfg=None, cal=CAL_SINTETICA):
    g = Gestos((cfg or cfg_prueba())["gestos"], cal)
    eventos = []
    resultados = []
    for t, m in seq:
        r = g.actualizar(m, t)
        eventos += [(t, e) for e in r.eventos]
        resultados.append((t, r))
    return eventos, resultados, g


def parpadeo(t0, dur, cierre=0.03):
    """Claves de un parpadeo: cierra en ``cierre`` s, queda cerrado y abre en ``cierre`` s."""
    return [(t0, {}), (t0 + cierre, {"ojos": 0.0}), (t0 + dur - cierre, {"ojos": 0.0}), (t0 + dur, {})]


def boca(t0, dur, nivel=1.0, rampa=0.05):
    return [(t0, {}), (t0 + rampa, {"boca": nivel}), (t0 + dur - rampa, {"boca": nivel}), (t0 + dur, {})]


def tipos(eventos):
    return [type(e).__name__ + (f":{e.nombre}" if hasattr(e, "nombre") else "") for _, e in eventos]


# ---------------------------------------------------------------- parpadeo
@pytest.mark.parametrize("fps", FPS_TODOS)
@pytest.mark.parametrize("dur_ms", [100, 150, 250, 390])
def test_parpadeos_naturales_nunca_hacen_nada(fps, dur_ms):
    claves = [(0.0, {})]
    t = 1.0
    for _ in range(4):                         # varios sueltos
        claves += parpadeo(t, dur_ms / 1000)
        t += 1.3
    for _ in range(3):                         # ráfaga de 3 seguidos
        claves += parpadeo(t, dur_ms / 1000)
        t += dur_ms / 1000 + 0.12
    claves.append((t + 1.0, {}))
    eventos, res, _ = correr(secuencia(claves, fps))
    assert eventos == [], tipos(eventos)
    assert not any(r.parpadeo_listo for _, r in res)


@pytest.mark.parametrize("fps", FPS_TODOS)
def test_parpadeos_naturales_con_ruido_y_movimiento(fps):
    import numpy as np
    rng = np.random.default_rng(11)
    claves = [(0.0, {"ruido": 0.4})]
    t = 0.5
    for i in range(12):
        d = float(rng.uniform(0.08, 0.39))
        claves += [(t, {"ruido": 0.4, "yaw": 3 * np.sin(i)}), (t + 0.03, {"ojos": 0.0, "ruido": 0.4}),
                   (t + d - 0.03, {"ojos": 0.0, "ruido": 0.4}), (t + d, {"ruido": 0.4, "yaw": -2 * np.cos(i)})]
        t += d + float(rng.uniform(0.15, 1.5))
    claves.append((t + 0.5, {"ruido": 0.4}))
    seq = [(tt, None if P is None else medir_si_valida(P, 640, 480))
           for tt, P in linea_de_tiempo(claves, fps, rng=rng)]
    eventos, _, _ = correr(seq)
    assert [e for e in eventos if isinstance(e[1], (ParpadeoLargo, ParpadeoListo))] == []


@pytest.mark.parametrize("fps", (30, 15))
def test_cierre_de_900_ms_es_un_parpadeo_largo_al_abrir(fps):
    claves = [(0.0, {})] + parpadeo(1.0, 0.9) + [(3.0, {})]
    eventos, res, _ = correr(secuencia(claves, fps))
    largos = [(t, e) for t, e in eventos if isinstance(e, ParpadeoLargo)]
    listos = [(t, e) for t, e in eventos if isinstance(e, ParpadeoListo)]
    assert len(largos) == 1 and len(listos) == 1
    # "Listo" sale con los ojos aún cerrados; el largo, al abrirlos
    assert listos[0][0] < 1.9
    assert largos[0][0] >= 1.9
    assert largos[0][0] <= 1.9 + 0.08 + 2 / fps


def test_cierre_largo_a_8_cuadros_por_segundo():
    claves = [(0.0, {})] + parpadeo(1.0, 1.1) + [(3.0, {})]
    eventos, _, _ = correr(secuencia(claves, 8))
    assert len([e for _, e in eventos if isinstance(e, ParpadeoLargo)]) == 1


def test_cierre_de_5_s_es_descanso_y_no_hace_nada():
    claves = [(0.0, {})] + parpadeo(1.0, 5.0) + [(7.0, {})]
    eventos, _, _ = correr(secuencia(claves))
    assert [e for _, e in eventos if isinstance(e, ParpadeoLargo)] == []


def test_un_solo_ojo_cerrado_no_hace_nada():
    for ojo in ("ojo_der", "ojo_izq"):
        claves = [(0.0, {}), (1.0, {}), (1.03, {ojo: 0.0}), (2.0, {ojo: 0.0}), (2.03, {}), (3.0, {})]
        eventos, res, _ = correr(secuencia(claves))
        assert eventos == []
        # un solo ojo (párpado caído, ojo entrecerrado) no congela ni el puntero ni el barrido
        assert not any(r.ojos_cerrando for _, r in res)


def test_piso_de_400_ms_aunque_la_config_diga_100():
    cfg = cfg_prueba()
    cfg["gestos"]["parpadeo"]["largo_ms"] = 100            # saltándose la validación a propósito
    claves = [(0.0, {})] + parpadeo(1.0, 0.25) + parpadeo(2.0, 0.39) + [(3.0, {})]
    eventos, _, g = correr(secuencia(claves), cfg)
    assert g.parpadeo_largo_s == pytest.approx(0.4)
    assert eventos == []
    claves = [(0.0, {})] + parpadeo(1.0, 0.5) + [(2.5, {})]
    eventos, _, _ = correr(secuencia(claves), cfg)
    assert len([e for _, e in eventos if isinstance(e, ParpadeoLargo)]) == 1


def test_un_instante_abierto_en_medio_no_corta_el_cierre():
    claves = [(0.0, {}), (1.0, {}), (1.03, {"ojos": 0.0}), (1.5, {"ojos": 0.0}), (1.51, {}), (1.54, {"ojos": 0.0}),
              (2.1, {"ojos": 0.0}), (2.13, {}), (3.0, {})]
    eventos, _, _ = correr(secuencia(claves, 30))
    largos = [e for _, e in eventos if isinstance(e, ParpadeoLargo)]
    assert len(largos) == 1 and largos[0].duracion_ms >= 1000


def test_ojos_cerrando_marca_el_inicio_del_cierre():
    claves = [(0.0, {}), (1.0, {}), (1.1, {"ojos": 0.6}), (1.2, {})]
    _, res, _ = correr(secuencia(claves))
    assert any(r.ojos_cerrando for t, r in res if 1.05 < t < 1.2)
    assert not any(r.ojos_cerrando for t, r in res if t < 1.0)


def test_doble_parpadeo_largo():
    cfg = cfg_prueba(**{"gestos.parpadeo.doble": True})
    claves = [(0.0, {})] + parpadeo(1.0, 1.0) + parpadeo(3.0, 1.0) + [(5.0, {})]
    eventos, _, _ = correr(secuencia(claves), cfg)
    ts = tipos(eventos)
    assert ts.count("ParpadeoLargo") == 1 and ts.count("DobleParpadeoLargo") == 1
    # separados por más de 2,5 s: ninguno
    claves = [(0.0, {})] + parpadeo(1.0, 1.0) + parpadeo(5.0, 1.0) + [(7.0, {})]
    eventos, _, _ = correr(secuencia(claves), cfg)
    assert [e for _, e in eventos if isinstance(e, (ParpadeoLargo, DobleParpadeoLargo))] == []


def test_doble_sin_la_opcion_igual_se_informa():
    claves = [(0.0, {})] + parpadeo(1.0, 1.0) + parpadeo(3.0, 1.0) + [(5.0, {})]
    eventos, _, _ = correr(secuencia(claves))
    ts = tipos(eventos)
    assert ts.count("ParpadeoLargo") == 2 and ts.count("DobleParpadeoLargo") == 1


# ---------------------------------------------------------------- boca, cejas, sonrisa
def test_boca_800_ms_es_corto_al_soltar():
    claves = [(0.0, {})] + boca(1.0, 0.8) + [(2.5, {})]
    eventos, _, _ = correr(secuencia(claves))
    assert tipos(eventos) == ["GestoCorto:boca"]
    assert eventos[0][0] >= 1.7             # al soltar (tiene acción larga)


def test_boca_2200_ms_es_solo_largo():
    claves = [(0.0, {})] + boca(1.0, 2.2) + [(4.0, {})]
    eventos, _, _ = correr(secuencia(claves))
    assert tipos(eventos) == ["GestoLargo:boca"]


def test_boca_sin_accion_larga_dispara_al_cumplir_sostener():
    cfg = cfg_prueba(**{"gestos.boca.largo": "ninguna"})
    claves = [(0.0, {})] + boca(1.0, 2.0) + [(4.0, {})]
    eventos, _, _ = correr(secuencia(claves), cfg)
    assert tipos(eventos) == ["GestoCorto:boca"]
    assert eventos[0][0] < 1.75


def test_boca_muy_corta_no_hace_nada():
    claves = [(0.0, {})] + boca(1.0, 0.3) + [(2.0, {})]
    eventos, _, _ = correr(secuencia(claves))
    assert eventos == []


@pytest.mark.parametrize("fps", (30, 15))
def test_hablar_no_hace_clic(fps):
    claves = [(0.0, {}), (1.0, {})]
    t, nivel = 1.0, 0.3
    while t < 4.0:
        t += 0.12
        nivel = 0.7 if nivel == 0.3 else 0.3
        claves.append((t, {"boca": nivel}))
    claves += [(t + 0.1, {}), (5.0, {})]
    eventos, _, _ = correr(secuencia(claves, fps))
    assert eventos == [], tipos(eventos)


def test_histeresis_sin_rebotes():
    """Señal temblando justo en el umbral de entrada: ningún evento; y tras un evento, quedarse
    entre "salir" y "entrar" no permite repetir."""
    import math
    g = Gestos(cfg_prueba()["gestos"], CAL_SINTETICA)
    entrar = g._g["boca"].entrar
    salir = g._g["boca"].salir
    ev = []
    for i in range(150):
        t = i / 30
        mar = entrar + 0.01 * math.sin(i * 2.1)
        ev += g.actualizar(medidas(mar=mar), t).eventos
    assert ev == []
    # un gesto completo, luego entre salir y entrar varias veces
    g = Gestos(cfg_prueba(**{"gestos.boca.largo": "ninguna"})["gestos"], CAL_SINTETICA)
    ev = []
    for i in range(300):
        t = i / 30
        if t < 1.0:
            mar = 0.6
        else:
            mar = (salir + entrar) / 2 + (0.6 - entrar) * (1 if (i // 15) % 2 else -0.1)
        ev += g.actualizar(medidas(mar=max(mar, salir + 0.005)), t).eventos
    assert [type(e).__name__ for e in ev] == ["GestoCorto"]


def test_refractario_entre_gestos():
    cfg = cfg_prueba(**{"gestos.cejas.largo": "ninguna"})
    # boca termina a 1,5 s; cejas empiezan a 1,6 s (dentro de los 600 ms): no cuentan
    claves = [(0.0, {}), (1.0, {}), (1.05, {"boca": 1.0}), (1.75, {"boca": 1.0}), (1.8, {}),
              (1.9, {}), (1.95, {"cejas": 1.0}), (2.4, {"cejas": 1.0}), (2.45, {}),
              (3.0, {}), (3.05, {"cejas": 1.0}), (3.8, {"cejas": 1.0}), (3.85, {}), (4.7, {})]
    eventos, _, _ = correr(secuencia(claves), cfg)
    assert tipos(eventos) == ["GestoCorto:boca", "GestoCorto:cejas"]
    assert eventos[1][0] > 3.0


def test_cejas_arriba_es_clic_derecho_por_defecto():
    claves = [(0.0, {})] + [(1.0, {}), (1.05, {"cejas": 1.0}), (1.8, {"cejas": 1.0}), (1.85, {})] + [(2.5, {})]
    eventos, _, _ = correr(secuencia(claves))
    assert tipos(eventos) == ["GestoCorto:cejas"]
    assert eventos[0][0] < 1.75             # sin acción larga: no espera a soltar (600 ms)


def test_sonrisa_con_boca_abierta_no_es_sonrisa():
    cfg = cfg_prueba(**{"gestos.sonrisa.activo": True, "gestos.sonrisa.corto": "clic", "gestos.boca.activo": False})
    claves = [(0.0, {}), (1.0, {}), (1.05, {"sonrisa": 1.0, "boca": 1.0}), (2.0, {"sonrisa": 1.0, "boca": 1.0}),
              (2.05, {}), (3.0, {})]
    eventos, _, _ = correr(secuencia(claves), cfg)
    assert eventos == []
    claves = [(0.0, {}), (1.0, {}), (1.05, {"sonrisa": 1.0}), (2.0, {"sonrisa": 1.0}), (2.05, {}), (3.0, {})]
    eventos, _, _ = correr(secuencia(claves), cfg)
    assert tipos(eventos) == ["GestoCorto:sonrisa"]


def test_gesto_apagado_no_hace_nada():
    cfg = cfg_prueba(**{"gestos.boca.activo": False})
    claves = [(0.0, {})] + boca(1.0, 0.8) + [(2.5, {})]
    eventos, res, _ = correr(secuencia(claves), cfg)
    assert eventos == []
    assert not any(r.gesto_activo for _, r in res)


def test_perder_la_cara_reinicia_sin_eventos():
    claves = [(0.0, {}), (1.0, {}), (1.05, {"boca": 1.0}), (1.8, {"boca": 1.0}), (1.85, None), (2.5, {}),
              (3.5, {})]
    eventos, _, _ = correr(secuencia(claves))
    assert eventos == []
    claves = [(0.0, {}), (1.0, {}), (1.03, {"ojos": 0.0}), (1.9, {"ojos": 0.0}), (1.95, None), (2.5, {}), (3.0, {})]
    eventos, _, _ = correr(secuencia(claves))
    assert [e for _, e in eventos if isinstance(e, ParpadeoLargo)] == []


def test_sensibilidad_y_umbral_calibrado():
    claves = [(0.0, {})] + boca(1.0, 0.8, nivel=0.25) + [(2.5, {})]
    eventos, _, _ = correr(secuencia(claves))
    assert eventos == []                     # boca a medias: no llega con sensibilidad 1
    cfg = cfg_prueba(**{"gestos.boca.sens": 2.0})
    eventos, _, _ = correr(secuencia(claves), cfg)
    assert tipos(eventos) == ["GestoCorto:boca"]
    cal = dict(CAL_SINTETICA, umbrales={"boca": 0.12})
    eventos, _, _ = correr(secuencia(claves), cfg_prueba(), cal)
    assert tipos(eventos) == ["GestoCorto:boca"]


def test_sin_calibracion_usa_la_base_de_referencia():
    claves = [(0.0, {})] + boca(1.0, 0.8) + [(2.5, {})]
    eventos, _, g = correr(secuencia(claves), cal=None)
    assert not g.calibrado
    assert tipos(eventos) == ["GestoCorto:boca"]


def test_progreso_y_nivel_para_la_interfaz():
    claves = [(0.0, {})] + boca(1.0, 1.0) + [(2.5, {})]
    _, res, _ = correr(secuencia(claves))
    progs = [r.progreso.get("boca", 0) for t, r in res if 1.05 < t < 1.9]
    assert progs[0] < 0.5 and max(progs) == 1.0
    assert any(r.nivel["boca"] > 1 for _, r in res)
    assert all(r.progreso.get("boca", 0) == 0 for t, r in res if t < 1.0)


def test_duracion_sostenida_y_consumir():
    g = Gestos(cfg_prueba()["gestos"], CAL_SINTETICA)
    ev = []
    for i in range(int(3.5 * 30)):
        t = i / 30
        ev += g.actualizar(medidas(mar=0.6), t).eventos
        if t >= 3.0:
            break
    assert g.duracion_sostenida("boca", t) >= 2.9
    g.consumir("boca")
    assert g.duracion_sostenida("boca", t) == 0
    for i in range(30):
        ev += g.actualizar(medidas(), t + (i + 1) / 30).eventos
    assert ev == []                          # consumido: al soltar no hay GestoLargo


# ---------------------------------------------------------------- ronda 1 de arreglos (clics falsos)
REP = dict(ear_der=0.357, ear_izq=0.375)


def _correr_medidas(pasos, cfg=None, fps=30, t0=0.0):
    """``pasos``: [(segundos, dict de medidas | None)]. Devuelve (eventos, resultados)."""
    g = Gestos((cfg or cfg_prueba())["gestos"], CAL_SINTETICA)
    t, dt = t0, 1.0 / fps
    eventos, res = [], []
    for seg, kw in pasos:
        fin = t + seg - 1e-9
        primero = True
        while t < fin or primero:
            primero = False
            r = g.actualizar(None if kw is None else medidas(**kw), t)
            eventos += [(t, e) for e in r.eventos]
            res.append((t, r))
            t += dt
            if kw is None:
                break                     # un solo cuadro sin cara
    return eventos, res


CERRADOS = dict(ear_der=0.1, ear_izq=0.1)


def test_cejas_sostenidas_con_caras_perdidas_dan_un_solo_clic():
    pasos = [(1.0, {})]
    for _ in range(5):
        pasos += [(2.0, {"cejas": 0.356 * 1.25}), (0, None)]
    pasos.append((1.0, {}))
    eventos, _ = _correr_medidas(pasos)
    assert tipos(eventos) == ["GestoCorto:cejas"]


def test_boca_sin_largo_sostenida_con_caras_perdidas_un_solo_evento():
    cfg = cfg_prueba(**{"gestos.boca.largo": "ninguna"})
    pasos = [(1.0, {})]
    for _ in range(4):
        pasos += [(1.5, {"mar": 0.6}), (0, None), (0, None)]
    pasos.append((1.0, {}))
    eventos, _ = _correr_medidas(pasos, cfg)
    assert tipos(eventos) == ["GestoCorto:boca"]
    # tras volver a reposo con la cara presente, sí vuelve a funcionar
    pasos += [(0.8, {"mar": 0.6}), (1.0, {})]
    eventos, _ = _correr_medidas(pasos, cfg)
    assert tipos(eventos) == ["GestoCorto:boca", "GestoCorto:boca"]


def test_gesto_que_ya_esta_arriba_al_volver_la_cara_no_cuenta():
    cfg = cfg_prueba(**{"gestos.boca.largo": "ninguna"})
    eventos, _ = _correr_medidas([(1.0, {}), (0, None), (1.0, {"mar": 0.6}), (1.0, {})], cfg)
    assert eventos == []


def test_descanso_con_cara_perdida_un_cuadro_no_es_parpadeo_largo():
    pasos = [(1.0, {}), (8.0, CERRADOS), (0, None), (1.0, CERRADOS), (1.0, {})]
    eventos, _ = _correr_medidas(pasos)
    assert [e for _, e in eventos if isinstance(e, ParpadeoLargo)] == []
    assert len([e for _, e in eventos if isinstance(e, ParpadeoListo)]) == 1     # solo el del comienzo


def test_hueco_corto_sin_cara_no_corta_un_parpadeo_largo_de_verdad():
    pasos = [(1.0, {}), (0.5, CERRADOS), (0, None), (0.5, CERRADOS), (1.0, {})]
    eventos, _ = _correr_medidas(pasos)
    assert len([e for _, e in eventos if isinstance(e, ParpadeoLargo)]) == 1


def test_hueco_largo_sin_cara_anula_el_cierre():
    pasos = [(1.0, {}), (0.5, CERRADOS)] + [(0, None)] * 15 + [(0.8, CERRADOS), (1.0, {})]
    eventos, _ = _correr_medidas(pasos)
    assert [e for _, e in eventos if isinstance(e, ParpadeoLargo)] == []
    # y uno que ya viene cerrado al volver la cara tampoco
    pasos = [(1.0, {})] + [(0, None)] * 15 + [(1.2, CERRADOS), (1.0, {})]
    eventos, _ = _correr_medidas(pasos)
    assert [e for _, e in eventos if isinstance(e, ParpadeoLargo)] == []


def test_rafaga_con_reapertura_parcial_no_se_junta_en_un_largo():
    a = dict(ear_der=0.357 * 0.65, ear_izq=0.375 * 0.65)
    pasos = [(1.0, {})] + [(0.15, CERRADOS), (0.25, a)] * 4 + [(1.0, {})]
    eventos, _ = _correr_medidas(pasos, fps=20)
    assert [e for _, e in eventos if isinstance(e, (ParpadeoLargo, ParpadeoListo))] == []


@pytest.mark.parametrize("fps", (30, 20))
def test_rafaga_rapida_con_dos_cuadros_abiertos_no_se_junta(fps):
    pasos = [(1.0, {})] + [(0.2, CERRADOS), (2.0 / fps, {})] * 4 + [(1.0, {})]
    eventos, _ = _correr_medidas(pasos, fps=fps)
    assert [e for _, e in eventos if isinstance(e, (ParpadeoLargo, ParpadeoListo))] == []


def test_ojos_entrecerrados_no_son_parpadeo_largo():
    medio = dict(ear_der=0.357 * 0.5, ear_izq=0.375 * 0.5)
    eventos, res = _correr_medidas([(1.0, {}), (2.0, medio), (1.0, {})], fps=20)
    assert [e for _, e in eventos if isinstance(e, (ParpadeoLargo, ParpadeoListo))] == []
    assert not any(r.parpadeo_listo for _, r in res)


def test_bostezo_con_ojos_cerrados_no_elige_ni_hace_gesto_de_boca():
    pasos = [(1.0, {}), (0.5, {"mar": 0.7}), (1.2, dict(CERRADOS, mar=0.7)), (1.3, {"mar": 0.7}), (1.0, {})]
    eventos, _ = _correr_medidas(pasos)
    assert eventos == [], tipos(eventos)


def test_cierre_con_cejas_arriba_no_es_parpadeo_largo():
    pasos = [(1.0, {}), (1.0, dict(CERRADOS, cejas=0.356 * 1.25)), (1.0, {})]
    eventos, _ = _correr_medidas(pasos, cfg_prueba(**{"gestos.cejas.activo": False}))
    assert [e for _, e in eventos if isinstance(e, ParpadeoLargo)] == []


def test_boca_abierta_mas_de_cinco_segundos_no_es_gesto_largo():
    eventos, _ = _correr_medidas([(1.0, {}), (5.5, {"mar": 0.7}), (1.0, {})])
    assert eventos == []
    eventos, res = _correr_medidas([(1.0, {}), (3.0, {"mar": 0.7}), (1.0, {})])
    assert tipos(eventos) == ["GestoLargo:boca"]
    soltados = [s for _, r in res for s in r.soltados]
    assert len(soltados) == 1 and soltados[0].nombre == "boca" and 2900 <= soltados[0].duracion_ms <= 3100
