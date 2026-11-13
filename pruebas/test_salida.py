"""Salida (sección 13.2, test_salida.py), sin mover el ratón real ni escribir nada en Windows:
fórmula de coordenadas, estructuras INPUT, texto Unicode, teclas virtuales, doble clic, rueda
horizontal, soltar todo, ventanas propias, fallos de SendInput y salida simulada."""
import ctypes
import threading

import pytest

from conftest import verificar_invariantes
from lycan_face_control import constantes as K
from lycan_face_control.acciones import (Aviso, Bajar, Clic, Esperar, Hablar, Mover, MoverDelta, Rueda, SoltarTodo,
                                         Subir, Tecla, TeclaVK, Texto, describir, es_de_entrada)
from lycan_face_control.salida import ErrorEnvio, crear, eventos_texto
from lycan_face_control.salida import windows as W
from lycan_face_control.salida.simulada import SalidaSimulada


@pytest.mark.parametrize("vx,vw", [(0, 1366), (0, 1920), (0, 3840), (-1920, 3840)])
def test_formula_de_coordenadas_sin_errores(vx, vw):
    for x in range(vx, vx + vw):
        nx, _ = W.a_absoluto(x, 0, vx, 0, vw, 768)
        assert 0 <= nx <= 65535
        assert W.de_absoluto(nx, 0, vx, 0, vw, 768)[0] == x


def test_estructura_input_de_40_bytes():
    assert ctypes.sizeof(W.INPUT) == 40


class SalidaWindowsSinEnviar(W.SalidaWindows):
    """Construye los INPUT pero no llama a SendInput (ni mira ventanas reales)."""

    def __init__(self, escritorio=(0, 0, 1366, 768), invertidos=False):
        super(W.SalidaWindows, self).__init__()
        self.escritorio = escritorio
        self.invertidos = invertidos
        self.lotes = []
        self.cursor = (100, 100)
        self.falla = False

    def _limitar(self, x, y):
        return super(W.SalidaWindows, self)._limitar(x, y)

    def posicion_cursor(self):
        return self.cursor

    def _enviar(self, eventos):
        ins = self.construir(eventos)
        if self.falla:
            raise ErrorEnvio(5, "bloqueado")
        self.lotes.append(ins)
        return len(ins)


def test_construir_banderas_correctas():
    s = SalidaWindowsSinEnviar()
    s.aplicar([Mover(683, 384), Bajar("izq"), Subir("izq"), Clic("der"), Rueda(120), Rueda(-240),
               Rueda(120, horizontal=True), Tecla("shift", True), Tecla("shift", False)])
    planos = [i for lote in s.lotes for i in lote]
    m = planos[0]
    assert m.type == 0 and m.mi.dwFlags == 0x0001 | 0x8000 | 0x4000
    assert m.mi.dwExtraInfo == K.LYCAN_EXTRA == 0x4C594643
    assert [p.mi.dwFlags for p in planos[1:5]] == [0x02, 0x04, 0x08, 0x10]
    assert planos[5].mi.dwFlags == 0x0800 and planos[5].mi.mouseData == 120
    assert ctypes.c_int32(planos[6].mi.mouseData).value == -240
    assert planos[7].mi.dwFlags == 0x1000                       # rueda horizontal
    assert planos[8].type == 1 and planos[8].ki.wVk == 0xA0 and planos[8].ki.dwFlags == 0
    assert planos[9].ki.dwFlags == 0x0002
    # el clic va en UNA sola llamada (bajar + subir)
    assert any(len(l) == 2 and l[0].mi.dwFlags == 0x08 and l[1].mi.dwFlags == 0x10 for l in s.lotes)


def test_texto_unicode_en_input():
    """Texto("¿Ñandú, pingüino? 👍") -> INPUT Unicode correctos, pares bajar/subir y par sustituto."""
    s = SalidaWindowsSinEnviar()
    texto = "¿Ñandú, pingüino? 👍"
    s.aplicar([Texto(texto)])
    planos = [i for lote in s.lotes for i in lote]
    assert all(p.type == 1 for p in planos)
    assert all(p.ki.wVk == 0 for p in planos)
    assert all(p.ki.dwFlags & 0x0004 for p in planos)            # KEYEVENTF_UNICODE
    assert all(p.ki.dwExtraInfo == K.LYCAN_EXTRA for p in planos)
    bajadas = [p.ki.wScan for p in planos if not p.ki.dwFlags & 0x0002]
    subidas = [p.ki.wScan for p in planos if p.ki.dwFlags & 0x0002]
    assert bajadas == subidas
    unidades = list(texto.encode("utf-16-le"))
    esperado = [unidades[i] | (unidades[i + 1] << 8) for i in range(0, len(unidades), 2)]
    assert bajadas == esperado
    assert 0xD83D in bajadas and 0xDC4D in bajadas                  # 👍 como par sustituto
    assert len(s.lotes) == 1                                         # un solo envío (< 200 caracteres)


def test_eventos_texto_pares_y_saltos_de_linea():
    envios = eventos_texto("a\nb\r\nc\td")
    planos = [e for envio in envios for e in envio]
    assert planos[:2] == [("unicode", ord("a"), True), ("unicode", ord("a"), False)]
    assert planos[2:4] == [("vk", K.VK_RETURN, True), ("vk", K.VK_RETURN, False)]
    vks = [e[1] for e in planos if e[0] == "vk" and e[2]]
    assert vks == [K.VK_RETURN, K.VK_RETURN, K.VK_TAB]               # \r\n cuenta como un solo Enter
    assert not any(e[0] == "unicode" and e[1] in (0x0A, 0x0D, 0x09) for e in planos)


def test_texto_largo_en_trozos_de_200_sin_partir_caracteres():
    texto = ("ñ" * 150) + ("👍" * 100) + "fin"
    envios = eventos_texto(texto)
    assert len(envios) == 2
    for envio in envios:
        # en cada envío todo lo que baja sube
        bal = {}
        for tipo, u, abajo in envio:
            bal[u] = bal.get(u, 0) + (1 if abajo else -1)
        assert all(v == 0 for v in bal.values())
    s = SalidaSimulada()
    s.aplicar([Texto(texto)])
    assert s.texto() == texto
    assert s.llamadas == 2
    verificar_invariantes(s)


def test_tecla_vk_completa_y_extendida():
    s = SalidaWindowsSinEnviar()
    s.aplicar([TeclaVK(K.VK_BACK), TeclaVK(K.VK_LEFT)])
    assert len(s.lotes) == 2
    borrar, flecha = s.lotes
    assert [p.ki.wVk for p in borrar] == [K.VK_BACK, K.VK_BACK]
    assert [p.ki.dwFlags & 0x0002 for p in borrar] == [0, 0x0002]
    assert not borrar[0].ki.dwFlags & 0x0001
    assert all(p.ki.dwFlags & 0x0001 for p in flecha)               # KEYEVENTF_EXTENDEDKEY


def test_tecla_vk_no_permitida_se_ignora():
    s = SalidaSimulada()
    s.aplicar([TeclaVK(0x5B)])          # tecla Windows: no permitida
    assert s.n_eventos == 0


def test_simulada_reconstruye_texto_con_borrar():
    s = SalidaSimulada()
    s.aplicar([Texto("Hola"), TeclaVK(K.VK_BACK), Texto("a, ¿cómo está?\n"), TeclaVK(K.VK_RETURN)])
    assert s.texto() == "Hola, ¿cómo está?\n\n"
    s2 = SalidaSimulada()
    s2.aplicar([Texto("ok👍"), TeclaVK(K.VK_BACK)])
    assert s2.texto() == "ok"
    verificar_invariantes(s)


def test_no_escribe_en_ventana_propia_ni_de_administrador():
    s = SalidaSimulada()
    s.foco_propio = True
    avisos = s.aplicar([Texto("hola"), TeclaVK(K.VK_RETURN)])
    assert [a.clave for a in avisos] == ["foco_propio", "foco_propio"]
    assert s.n_eventos == 0
    s.foco_propio = False
    s.revisar_destino = lambda: "administrador"
    avisos = s.aplicar([Texto("hola")])
    assert avisos == [Aviso("administrador")]
    assert s.n_eventos == 0
    s.revisar_destino = lambda: None
    s.aplicar([Texto("hola")])
    assert s.texto() == "hola"


def test_nada_de_clics_sobre_ventanas_propias():
    s = SalidaSimulada(cursor=(50, 50))
    s.es_propia_en = lambda x, y: x < 100
    avisos = s.aplicar([Clic("izq"), Bajar("izq"), Clic("der", 2)])
    assert all(a.clave == "sobre_ventana" for a in avisos) and len(avisos) == 3
    assert s.botones() == []
    s.cursor = (500, 500)
    s.aplicar([Clic("izq")])
    assert s.botones() == [("izq", True), ("izq", False)]
    # respaldo por rectángulo
    s2 = SalidaSimulada(cursor=(10, 10))
    s2.rect_propio = (0, 0, 20, 20)
    assert s2.aplicar([Clic("izq")]) == [Aviso("sobre_ventana")]


def test_es_propia_en_que_falla_no_rompe():
    s = SalidaSimulada()

    def falla(x, y):
        raise OSError("sin ventanas")
    s.es_propia_en = falla
    s.aplicar([Clic("izq")])
    assert s.botones() == [("izq", True), ("izq", False)]


def test_doble_clic_dos_pares_con_espera():
    s = SalidaSimulada()
    s.intervalo_doble_ms = 166
    s.aplicar([Clic("izq", 2)])
    evs = [ev for _, ev in s.eventos]
    assert evs == [("boton", "izq", True), ("boton", "izq", False), ("esperar", 166),
                   ("boton", "izq", True), ("boton", "izq", False)]
    assert s.llamadas == 2
    verificar_invariantes(s)


def test_doble_clic_no_baja_si_el_boton_ya_esta_abajo():
    s = SalidaSimulada()
    s.aplicar([Bajar("izq"), Clic("izq", 2), Clic("izq")])
    assert s.botones() == [("izq", True)]
    s.soltar_todo()
    verificar_invariantes(s)


def test_botones_invertidos_para_zurdos():
    s = SalidaWindowsSinEnviar(invertidos=True)
    s.aplicar([Clic("izq")])
    assert s.lotes[0][0].mi.dwFlags == 0x08


def test_soltar_todo_en_una_llamada_botones_primero():
    s = SalidaWindowsSinEnviar()
    s.aplicar([Tecla("shift", True), Bajar("medio"), Bajar("izq")])
    n = len(s.lotes)
    s.soltar_todo("prueba")
    assert len(s.lotes) == n + 1
    lote = s.lotes[-1]
    tipos = [i.type for i in lote]
    assert tipos == sorted(tipos)
    assert {i.mi.dwFlags for i in lote if i.type == 0} == {0x04, 0x40}
    assert {i.ki.wVk for i in lote if i.type == 1} == {0xA0, 0xA2, 0xA4}
    assert s.todo_suelto()


def test_bajar_dos_veces_no_envia_dos_bajar():
    s = SalidaSimulada()
    s.aplicar([Bajar("izq"), Bajar("izq"), Subir("izq"), Subir("izq")])
    assert s.botones() == [("izq", True), ("izq", False)]


def test_mover_y_mover_delta_se_limitan_al_escritorio():
    s = SalidaSimulada(escritorio=(0, 0, 1366, 768), cursor=(1360, 10))
    s.aplicar([MoverDelta(50, -50)])
    assert s.cursor == (1365, 0)
    s.aplicar([Mover(-30, 5000)])
    assert s.cursor == (0, 767)


def test_soltar_todo_idempotente_en_todos_los_estados():
    for previas in ([], [Bajar("izq")], [Bajar("medio"), Tecla("shift", True)],
                    [Tecla("ctrl", True)], [Bajar("der"), Bajar("izq"), Bajar("medio")]):
        s = SalidaSimulada()
        s.aplicar(previas)
        s.aplicar([SoltarTodo("prueba")])
        assert s.todo_suelto()
        antes = s.contador_soltar
        s.soltar_todo("otra vez")
        s.soltar_todo("y otra")
        assert s.todo_suelto() and s.contador_soltar == antes + 2
        verificar_invariantes(s)


def test_soltar_todo_seguro_desde_otro_hilo():
    s = SalidaSimulada()
    s.aplicar([Bajar("izq"), Tecla("shift", True)])
    h = threading.Thread(target=s.soltar_todo, args=("hilo",))
    h.start()
    h.join()
    assert s.todo_suelto()


def test_rueda_con_modificador_suelta_antes():
    s = SalidaSimulada()
    s.aplicar([Tecla("ctrl", True), Rueda(120)])
    assert s.todo_suelto()
    verificar_invariantes(s)


def test_fallo_de_sendinput_lanza_error_y_soltar_no_rompe():
    s = SalidaSimulada()
    s.aplicar([Bajar("izq")])
    s.fallar = True
    with pytest.raises(ErrorEnvio):
        s.aplicar([Mover(1, 1)])
    s.soltar_todo("falla")
    assert s.todo_suelto()
    assert s.probar() is False
    s.fallar = False
    assert s.probar() is True


def test_esperar_no_bloquea_en_la_simulada():
    s = SalidaSimulada()
    s.aplicar([Esperar(20)])
    assert s.eventos[-1][1] == ("esperar", 20)


def test_acciones_que_no_son_de_entrada_se_ignoran():
    s = SalidaSimulada()
    assert not es_de_entrada(Hablar("hola"))
    s.aplicar([Hablar("hola"), Aviso("x"), None])
    assert s.n_eventos == 0


def test_describir_no_revela_el_texto():
    assert "secreto" not in describir(Texto("mi secreto"))
    assert describir(Texto("abc")) == "Escribir 3 caracteres"
    assert "secreto" not in describir(Hablar("secreto"))
    assert describir(Clic("izq", 2)) == "Doble clic izquierdo"
    assert describir(TeclaVK(K.VK_BACK)) == "Tecla Borrar"


def test_crear_simulada():
    assert isinstance(crear(True), SalidaSimulada)


def test_salida_windows_real_se_construye_sin_enviar():
    s = W.SalidaWindows()
    vx, vy, vw, vh = s.escritorio
    assert vw > 0 and vh > 0
    assert 30 <= s.intervalo_doble_ms <= 250
    x, y = s.posicion_cursor()
    assert isinstance(x, int)
