"""Ronda 1 de arreglos: clics falsos y trampas de la máquina de estados (bostezos, pausa del
cuidador, otra cara en el cuadro, quien solo puede parpadear)."""
from conftest import REPOSO, Sim, cfg_prueba
from lycan_face_control import constantes as K
from lycan_face_control.acciones import Aviso, SoltarTodo

CERRADOS = dict(ear_der=0.1, ear_izq=0.1)


def parpadeo(s, dur):
    s.quieto(dur, **CERRADOS)
    s.quieto(0.4)


# ------------------------------------------------------------------ bostezos y pausa del cuidador
def test_bostezo_no_reanuda_una_pausa_del_cuidador():
    s = Sim()
    s.quieto(1.0)
    s.orden("alternar_pausa")
    for dur in (3.2, 4.0, 5.0):
        s.quieto(dur, mar=0.7)
        s.quieto(1.0)
        assert s.maquina.estado == K.PAUSA
    # el cuidador con el ratón ("cuidador") tampoco se quita con la boca
    s.orden("alternar_pausa")
    assert s.maquina.estado == K.ACTIVO
    s.orden("elegir", "barra:pausa")
    assert s.maquina.estado == K.PAUSA and s.maquina.motivo_pausa == "cuidador"
    s.quieto(3.5, mar=0.7)
    s.quieto(1.0)
    assert s.maquina.estado == K.PAUSA


def test_reanudar_con_la_boca_se_decide_al_soltar_y_no_con_un_bostezo_muy_largo():
    s = Sim()
    s.quieto(1.0)
    s.quieto(2.3, mar=0.6)
    s.quieto(0.5)
    assert s.maquina.estado == K.PAUSA and s.maquina.motivo_pausa == "gesto"
    s.quieto(6.5, mar=0.7)                   # bostezo largo / descanso con la boca abierta
    s.quieto(1.0)
    assert s.maquina.estado == K.PAUSA
    s.quieto(3.4, mar=0.6)
    assert s.maquina.estado == K.PAUSA       # todavía no soltó
    s.quieto(0.3)
    assert s.maquina.estado == K.ACTIVO


def test_bostezo_con_ojos_cerrados_no_pausa_ni_reanuda():
    s = Sim()
    s.quieto(1.0)
    s.quieto(0.5, mar=0.7)
    s.quieto(1.5, mar=0.7, **CERRADOS)
    s.quieto(1.5, mar=0.7)
    s.quieto(1.0)
    assert s.maquina.estado == K.ACTIVO
    assert s.clics() == []


def test_bostezo_muy_largo_estando_activo_no_pausa():
    s = Sim()
    s.quieto(1.0)
    s.quieto(6.0, mar=0.7)
    s.quieto(1.0)
    assert s.maquina.estado == K.ACTIVO
    assert s.clics() == []


def test_tos_corta_no_hace_clic_con_los_valores_de_fabrica():
    s = Sim()
    s.quieto(1.0)
    s.quieto(0.45, mar=0.5)
    s.quieto(1.0)
    assert s.clics() == []


# ------------------------------------------------------------------ barrido: siempre se puede volver
def test_pausa_desde_el_barrido_se_quita_con_dos_parpadeos_largos():
    s = Sim(cfg_prueba(**{"teclado.barrido": True}))
    s.quieto(1.0)
    s.orden("poner_submodo", K.BARRIDO)
    s.orden("pausar", "botón Pausar")
    assert s.maquina.estado == K.PAUSA
    assert s.maquina.reanuda_con_parpadeo()
    parpadeo(s, 1.0)
    assert s.maquina.estado == K.PAUSA
    parpadeo(s, 1.0)
    assert s.maquina.estado == K.ACTIVO
    assert s.maquina.submodo == K.BARRIDO


def test_con_barrido_encendido_dos_parpadeos_quitan_incluso_la_pausa_del_cuidador():
    s = Sim(cfg_prueba(**{"teclado.barrido": True}))
    s.quieto(1.0)
    s.orden("alternar_pausa")
    parpadeo(s, 1.0)
    parpadeo(s, 1.0)
    assert s.maquina.estado == K.ACTIVO


def test_sin_barrido_dos_parpadeos_no_reanudan():
    s = Sim()
    s.quieto(1.0)
    s.orden("alternar_pausa")
    assert not s.maquina.reanuda_con_parpadeo()
    parpadeo(s, 1.0)
    parpadeo(s, 1.0)
    assert s.maquina.estado == K.PAUSA


# ------------------------------------------------------------------ otra cara en el cuadro
def test_otra_cara_que_entra_suelta_todo_y_espera_antes_de_aceptar_clics():
    s = Sim(fps=20)
    s.quieto(1.0)
    s.limpiar()
    s.quieto(0.05, io_px=80.0, yaw_n=0.08)
    assert any(isinstance(a, SoltarTodo) for a in s.de_tipo(SoltarTodo))
    assert "cara_distinta" in s.avisos()
    # durante el primer segundo, abrir la boca (hablar fuerte) no hace nada
    s.quieto(0.7, io_px=80.0, yaw_n=0.08, mar=0.6)
    s.quieto(0.3, io_px=80.0, yaw_n=0.08)
    assert s.clics() == []


def test_un_salto_de_posicion_tambien_es_otra_cara():
    from lycan_face_control.cara import Medidas
    s = Sim(fps=20)
    base = dict(REPOSO)

    def m(cx):
        return Medidas(**base, centro=(cx, 240.0))
    for _ in range(20):
        s.paso(m(320.0))
    s.limpiar()
    s.paso(m(320.0 + 0.8 * base["io_px"]))
    assert "cara_distinta" in s.avisos()
    s.limpiar()
    for i in range(20):
        s.paso(m(320.0 + 0.8 * base["io_px"] + i * 2))   # moverse despacio no es otra cara
    assert "cara_distinta" not in s.avisos()


def test_acercarse_despacio_no_es_otra_cara():
    s = Sim(fps=20)
    s.quieto(0.5)
    s.limpiar()
    io = REPOSO["io_px"]
    s.durante(2.0, lambda t: __import__("conftest").medidas(io_px=io * (1 + 0.4 * t / 2.0)))
    assert "cara_distinta" not in s.avisos()
