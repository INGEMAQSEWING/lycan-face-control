"""Clic por permanencia (sección 3.8)."""
import pytest

from lycan_face_control.permanencia import Objetivo, Permanencia, buscar_objetivo, sobre_ventana_propia

FPS = 30.0


def perm(**kw):
    d = dict(tiempo_s=1.0, radio_px=30, recuperacion_s=1.0, margen_ms=150, anillo_desde_ms=200, alto_pantalla=1080)
    d.update(kw)
    return Permanencia(**d)


def correr(p, t0, dur, pos, objetivo=None, libre=True):
    """Devuelve (t_final, [(t, estado)])."""
    out = []
    n = int(round(dur * FPS))
    t = t0
    for i in range(n):
        t = t0 + i / FPS
        q = pos(t) if callable(pos) else pos
        out.append((t, p.actualizar(q, t, objetivo, libre)))
    return t0 + n / FPS, out


def disparos(r):
    return [t for t, e in r if e.disparo]


def armada(p, t0=0.0):
    """Se mueve para armar la permanencia (al empezar hay que moverse primero, y seguir lejos
    del punto de partida al menos 250 ms)."""
    t, _ = correr(p, t0, 0.45, lambda t: (100 + 500 * (t - t0), 100))
    return t


def test_al_empezar_hay_que_moverse_primero():
    p = perm()
    _, r = correr(p, 0.0, 3.0, (200, 200))
    assert disparos(r) == []


def test_dispara_al_segundo_quieto():
    p = perm()
    t = armada(p)
    t1, r = correr(p, t, 1.5, (300, 300))
    d = disparos(r)
    assert len(d) == 1
    assert d[0] - t == pytest.approx(1.0, abs=1.5 / FPS)


def test_anillo_visible_desde_200_ms_y_progreso_continuo():
    p = perm()
    t = armada(p)
    _, r = correr(p, t, 0.9, (300, 300))
    for tt, e in r:
        assert e.visible == (tt - t >= 0.2 - 1e-9)
    progs = [e.progreso for _, e in r]
    assert progs == sorted(progs)
    assert progs[-1] == pytest.approx(0.9 - 1 / FPS, abs=0.05)


def test_no_dispara_si_se_mueve_mas_que_el_radio():
    p = perm()
    t = armada(p)
    # deriva lenta de 60 px/s: sale del radio de 30 px antes del segundo
    _, r = correr(p, t, 3.0, lambda tt: (300 + 60 * (tt - t), 300))
    assert disparos(r) == []


def test_temblor_dentro_del_radio_si_dispara():
    import math
    p = perm()
    t = armada(p)
    _, r = correr(p, t, 1.5, lambda tt: (300 + 20 * math.sin((tt - t + 0.2) * 25), 300 + 20 * math.cos((tt - t + 0.2) * 17)))
    assert len(disparos(r)) == 1


def test_margen_de_150_ms_al_salirse_un_instante():
    p = perm()
    t = armada(p)

    def salto(tt):     # a los 0,5 s se sale 100 ms del radio y vuelve
        return (360, 300) if 0.5 <= tt - t < 0.6 else (300, 300)
    _, r = correr(p, t, 1.5, salto)
    d = disparos(r)
    assert len(d) == 1 and d[0] - t == pytest.approx(1.0, abs=2 / FPS)

    p2 = perm()
    t = armada(p2)

    def salto_largo(tt):   # fuera 300 ms: reinicia
        return (360, 300) if 0.5 <= tt - t < 0.8 else (300, 300)
    _, r = correr(p2, t, 1.5, salto_largo)
    assert disparos(r) == []


def test_no_repite_sin_moverse_60_px():
    p = perm()
    t = armada(p)
    t, r = correr(p, t, 5.0, (300, 300))
    assert len(disparos(r)) == 1
    # se mueve 40 px (menos de 2 × radio) y se queda: no repite
    t, r = correr(p, t, 3.0, (340, 300))
    assert disparos(r) == []
    # se aleja 70 px del punto del disparo: se arma y dispara otra vez
    t, r = correr(p, t, 3.0, (370, 300))
    assert len(disparos(r)) == 1


def test_recuperacion_tras_un_disparo():
    p = perm(recuperacion_s=1.0)
    t = armada(p)
    t, r = correr(p, t, 1.05, (300, 300))
    t_disp = disparos(r)[0]
    # se aleja enseguida y queda quieto: el nuevo contador no empieza hasta acabar la recuperación
    t, r = correr(p, t, 0.1, (500, 300))
    t, r = correr(p, t, 2.5, (500, 300))
    d = disparos(r)
    assert len(d) == 1
    assert d[0] - t_disp >= 1.0 + 1.0 - 1e-6


def test_libre_apagado_no_dispara():
    p = perm()
    t = armada(p)
    _, r = correr(p, t, 3.0, (300, 300), libre=False)
    assert disparos(r) == []


def test_por_objetivo_con_franja_de_12_por_ciento():
    teclas = [Objetivo("tecla:a", (100, 100, 200, 200)), Objetivo("tecla:b", (200, 100, 300, 200))]
    p = perm()
    actual = None
    t = 0.0
    eventos = []
    # entra a "a" y luego se pasa 10 px al borde de "b" (dentro de la franja de "a"): sigue en "a"
    for i in range(int(1.2 * FPS)):
        t = i / FPS
        pos = (150, 150) if t < 0.5 else (208, 150)
        actual = buscar_objetivo(pos, teclas, actual)
        e = p.actualizar(pos, t, actual)
        if e.disparo:
            eventos.append((t, e.objetivo))
    assert eventos and eventos[0][1] == "tecla:a"
    assert eventos[0][0] == pytest.approx(1.0, abs=1.5 / FPS)


def test_por_objetivo_no_exige_activacion_y_repetir_exige_otra_permanencia():
    teclas = [Objetivo("tecla:a", (100, 100, 200, 200)), Objetivo("tecla:b", (300, 100, 400, 200))]
    p = perm()
    actual = None
    elegidos = []
    for i in range(int(4.5 * FPS)):
        t = i / FPS
        pos = (150, 150) if t < 2.5 else (350, 150)
        actual = buscar_objetivo(pos, teclas, actual)
        e = p.actualizar(pos, t, actual)
        if e.disparo:
            elegidos.append((round(t, 2), e.objetivo))
    ids = [o for _, o in elegidos]
    # "a" a 1 s y otra vez a 2 s (otra permanencia completa); luego "b" sin moverse 60 px extra
    assert ids == ["tecla:a", "tecla:a", "tecla:b", "tecla:b"][:len(ids)]
    assert ids[:3] == ["tecla:a", "tecla:a", "tecla:b"]


def test_tiempo_propio_del_objetivo():
    o = Objetivo("reanudar", (0, 0, 100, 100), tiempo_s=2.0)
    p = perm()
    _, r = correr(p, 0.0, 2.5, (50, 50), objetivo=o)
    d = disparos(r)
    assert len(d) == 1 and d[0] == pytest.approx(2.0, abs=1.5 / FPS)


def test_ventana_propia_sin_boton():
    v = Objetivo("ventana:teclado", (0, 0, 500, 300), elegible=False)
    assert sobre_ventana_propia((10, 10), [v])
    assert buscar_objetivo((10, 10), [v]) is None
    assert not sobre_ventana_propia((600, 10), [v])


def test_radio_escalado_con_la_resolucion():
    assert perm(alto_pantalla=1080).radio == pytest.approx(30)
    assert perm(alto_pantalla=768).radio == pytest.approx(30 * 768 / 1080)
    assert perm(alto_pantalla=2160).distancia_activacion == pytest.approx(120)


def test_marcar_disparo_por_gesto_exige_moverse():
    p = perm()
    t = armada(p)
    p.marcar_disparo((300, 300), t)
    _, r = correr(p, t, 3.0, (300, 300))
    assert disparos(r) == []


def test_un_pico_suelto_del_temblor_no_arma():
    """Ronda 1: la cámara tiembla; un salto de un cuadro lejos del disparo no vuelve a armar."""
    p = perm()
    t = armada(p)
    t, r = correr(p, t, 1.5, (300, 300))
    assert len(disparos(r)) == 1
    for _ in range(20):                       # 20 picos de un cuadro a 100 px
        t, r1 = correr(p, t, 1 / FPS, (400, 300))
        t, r2 = correr(p, t, 1.2, (300, 300))
        assert disparos(r1 + r2) == []
    # alejarse de verdad (más de 250 ms) sí arma
    t, _ = correr(p, t, 0.4, (400, 300))
    t, r = correr(p, t, 1.5, (400, 300))
    assert len(disparos(r)) == 1
