"""Sistema (parte de la sección 13.2, test_sistema.py): atajos válidos y sin choque con AltGr,
"abrir al encender" (sin tocar el registro de Windows), registro sin consola, sonidos, DPI,
pantallas y el lanzador. Nada de esto mueve el ratón ni abre la cámara."""
import logging
import queue
import sys
from pathlib import Path

import pytest

from lycan_face_control import constantes as K
from lycan_face_control import registro
from lycan_face_control.config import FABRICA
from lycan_face_control.sistema import atajos, dpi, inicio, pantallas, sonidos, ventanas_win

RAIZ = Path(__file__).resolve().parents[1]


def test_atajos_de_fabrica_se_interpretan():
    usados = set()
    for nombre, texto in FABRICA["atajos"].items():
        mods, vk = atajos.interpretar(texto)
        assert mods & atajos.MOD_CONTROL and mods & atajos.MOD_ALT
        assert (mods, vk) not in usados, f"atajo repetido: {texto}"
        usados.add((mods, vk))
        # se puede volver a escribir y leer igual
        assert atajos.interpretar(atajos.texto_atajo(mods, vk)) == (mods, vk)
        assert nombre in atajos.NOMBRES_FUNCION


def test_atajos_no_chocan_con_lycan_mouse_control():
    del_mouse = {"Ctrl+Alt+M", "Ctrl+Alt+X", "Ctrl+Alt+O", "Ctrl+Alt+D", "Ctrl+Alt+P"}
    propios = {atajos.interpretar(t) for t in FABRICA["atajos"].values()}
    ajenos = {atajos.interpretar(t) for t in del_mouse}
    assert not (propios & ajenos)


@pytest.mark.parametrize("texto", ["", "Ctrl+Alt", "Alt+Ñ+Q", "T", "Shift+T", "Ctrl+Alt+Volar"])
def test_atajos_invalidos(texto):
    with pytest.raises(atajos.AtajoInvalido):
        atajos.interpretar(texto)


def test_atajos_de_fabrica_no_escriben_caracteres_con_altgr():
    """En el teclado latinoamericano Ctrl+Alt = AltGr (Ctrl+Alt+Q = @). Ningún atajo de fábrica
    puede producir un carácter."""
    hkl = atajos.teclado_latinoamericano()
    teclados = [hkl] if hkl else []
    teclados.append(atajos.teclado_actual())
    for h in teclados:
        for texto in FABRICA["atajos"].values():
            mods, vk = atajos.interpretar(texto)
            assert atajos.produce_caracter(mods, vk, h) is None, (texto, hex(h or 0))


def test_hilo_atajos_se_crea_sin_registrar():
    h = atajos.HiloAtajos(FABRICA["atajos"], queue.Queue())
    assert not h.is_alive()
    orden = atajos.orden_registro(FABRICA["atajos"])
    assert orden[0][1] == "salir"           # el atajo de seguridad se registra primero


def test_inicio_comando_usa_el_lanzador_de_face_control(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    cmd = inicio.comando()
    assert "lycan_face_control.pyw" in cmd and cmd.endswith("--minimizado")
    assert (RAIZ / "lycan_face_control.pyw").exists()
    assert inicio.NOMBRE == K.NOMBRE_RUN == "LycanFaceControl"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert inicio.comando() == f'"{sys.executable}" --minimizado'


def test_inicio_no_toca_el_registro_en_pruebas(monkeypatch):
    escrito = {}

    class ClaveFalsa:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class WinregFalso:
        HKEY_CURRENT_USER = 1
        KEY_SET_VALUE = 2
        REG_SZ = 1

        @staticmethod
        def OpenKey(*a):
            return ClaveFalsa()

        @staticmethod
        def SetValueEx(k, nombre, _r, _t, valor):
            escrito[nombre] = valor

        @staticmethod
        def DeleteValue(k, nombre):
            escrito.pop(nombre, None)

        @staticmethod
        def QueryValueEx(k, nombre):
            if nombre not in escrito:
                raise FileNotFoundError
            return escrito[nombre], 1

    monkeypatch.setitem(sys.modules, "winreg", WinregFalso)
    assert inicio.poner(True)
    assert "LycanFaceControl" in escrito and inicio.activo()
    assert inicio.poner(False)
    assert not inicio.activo()


def test_registro_sin_consola(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    registro.proteger_salida_estandar()
    print("no revienta")                     # con pythonw stdout es None
    ruta = registro.configurar(tmp_path / "reg")
    registro.anotar_inicio({"prueba": 1})
    logging.getLogger("lycan").info("hola")
    for h in logging.getLogger("lycan").handlers:
        h.flush()
    texto = ruta.read_text(encoding="utf-8")
    assert "Lycan Face Control" in texto and "hola" in texto
    assert registro.carpeta_registros().name == "registros"


def test_sonidos_sin_hilo_ni_ruido():
    s = sonidos.Sonidos(activos=False, arrancar=False)
    s.tocar("clic")
    assert s._cola.empty()
    s.tocar("alerta")                        # la urgencia suena aunque estén apagados
    assert not s._cola.empty() or sonidos.winsound is None
    s2 = sonidos.Sonidos(activos=True, arrancar=False)
    s2.tocar("no_existe")
    assert s2._cola.empty()
    for nombre in ("activar", "pausar", "clic", "perdida", "listo", "alerta"):
        assert nombre in sonidos.TONOS


def test_dpi_y_pantallas():
    assert dpi.activar() in ("per-monitor-v2", "ya-fijado", "per-monitor", "system", "ninguno")
    mons = pantallas.monitores()
    assert mons and all(m.ancho > 0 and m.alto > 0 for m in mons)
    principal = pantallas.elegir("principal")
    assert principal.principal or len(mons) == 1
    assert pantallas.elegir("todo").ancho >= principal.ancho
    assert pantallas.elegir("99") in mons or pantallas.elegir("99").principal


def test_ventanas_win_basico():
    assert ventanas_win.tiempo_doble_clic_ms() > 0
    assert isinstance(ventanas_win.es_propia_en(-100000, -100000), bool)
    assert isinstance(ventanas_win.ventana_en(10, 10), int)


def test_monitor_zona_segura_y_recorte():
    from lycan_face_control.mapeo import Monitor
    m = Monitor(0, 0, 1366, 768)
    x0, y0, x1, y1 = m.zona_segura()
    assert 0 < x0 < x1 < 1366 and 0 < y0 < y1 < 768
    assert m.recortar(-5, 9000) == (0, 767)
    assert m.centro == (682.5, 383.5)


def test_constantes_de_la_cara():
    assert K.EAR_DER[0] == K.OJO_DER_EXT and K.EAR_IZQ[3] == K.OJO_IZQ_EXT
    assert all(0 <= i < K.N_PUNTOS_MIN for i in K.PUNTOS_CLAVE)
    assert len(set(K.OVALO_CARA)) == len(K.OVALO_CARA)
    assert set(K.COLORES_ESTADO) == set(K.ESTADOS)
    assert K.LYCAN_EXTRA != 0x4C59434E       # distinta de la de Lycan Mouse Control
    assert [b for b, _ in K.BOTONES_BARRA] == ["clic", "doble", "derecho", "arrastrar", "desplazar",
                                               "teclado", "pausa"]


def test_version_y_argumentos():
    from lycan_face_control import VERSION
    from lycan_face_control.app import argumentos
    assert VERSION == "1.0.0"
    a = argumentos(["--simular", "--camara-falsa", "--minimizado"])
    assert a.simular and a.camara_falsa and a.minimizado and not a.check
    assert argumentos(["--check"]).check
