"""Versión 1.1, paquete B: el plan de alarma y voz (lógica pura) y la alarma (sistema/alarma.py),
con un winsound simulado: en las pruebas nunca suena nada."""
import ast
import io
import struct
import time
import wave
from pathlib import Path

import pytest

from lycan_face_control import config as C
from lycan_face_control import emergencia as E
from lycan_face_control.sistema import alarma as A

RAIZ = Path(__file__).resolve().parents[1] / "lycan_face_control"


# =========================================================================== PlanAlarma
def test_la_voz_cae_cada_12_s_y_la_alarma_se_calla_mientras_habla():
    p = E.PlanAlarma(100.0, repetir_voz=True, repetir_s=12, duracion_voz_s=3.0)
    assert p.momentos_voz(140.0) == [112.0, 124.0, 136.0]
    assert p.que_toca(100.0) == E.ALARMA and p.que_toca(111.9) == E.ALARMA
    assert p.que_toca(112.0) == E.VOZ and p.que_toca(114.9) == E.VOZ
    assert p.que_toca(115.1) == E.ALARMA
    assert p.que_toca(124.5) == E.VOZ and p.ciclo(124.5) == 2
    assert p.ciclo(111.0) == 0 and p.ciclo(112.0) == 1 and p.ciclo(135.9) == 2
    # nunca alarma y voz a la vez, en ningún momento
    t = 100.0
    while t < 200.0:
        assert p.que_toca(t) in (E.ALARMA, E.VOZ)
        assert (p.que_toca(t) == E.VOZ) == p.hablando(t)
        t += 0.05


def test_sin_voz_la_alarma_es_continua_y_sin_repetir_nunca_hay_voz():
    for p in (E.PlanAlarma(0.0, repetir_voz=True, hay_voz=False),
              E.PlanAlarma(0.0, repetir_voz=False, hay_voz=True)):
        assert p.momentos_voz(600.0) == []
        assert all(p.que_toca(i * 0.1) == E.ALARMA for i in range(6000))


def test_si_falla_la_alarma_solo_queda_la_voz():
    p = E.PlanAlarma(0.0, repetir_s=5, duracion_voz_s=2.0, hay_alarma=False)
    assert p.que_toca(1.0) == E.SILENCIO and p.que_toca(5.5) == E.VOZ


def test_una_voz_larga_no_tapa_toda_la_alarma():
    p = E.PlanAlarma(0.0, repetir_s=5, duracion_voz_s=20.0)
    assert p.que_toca(5.5) == E.VOZ
    assert p.que_toca(5.0 + 3.1) == E.ALARMA          # al menos 2 s de alarma entre mensajes
    assert p.que_toca(float("nan")) == E.ALARMA


def test_mensaje_de_voz_y_textos_de_la_pantalla():
    cfg = C.por_defecto()
    assert E.mensaje_voz(cfg) == "Necesito ayuda. Por favor, que venga alguien."
    cfg["teclado"]["cuidador"] = "Marta"
    cfg["emergencia"]["mensaje"] = "Me duele mucho."
    assert E.mensaje_voz(cfg) == "Me duele mucho. Por favor, que venga Marta."
    tx = E.textos_pantalla(cfg)
    assert tx["titulo"] == "NECESITO AYUDA" and tx["llamando"] == "Por favor, que venga Marta."
    assert tx["atendido"] == "Ya me atendieron" and "Ctrl+Alt+A" in tx["como_parar"]
    cfg["teclado"]["cuidador"] = "   "
    cfg["emergencia"]["mensaje"] = ""
    assert E.mensaje_voz(cfg) == "Necesito ayuda. Por favor, que venga alguien."
    assert E.duracion_voz("") == 1.0
    assert E.duracion_voz("x" * 50) == pytest.approx(5.0)


def test_el_color_cambia_como_maximo_una_vez_por_segundo():
    cambios, antes = 0, None
    for i in range(0, 1000):                 # 10 s cada 10 ms
        c = E.color_fondo(i * 0.01, 0.0)
        assert c in (E.ROJO_CLARO, E.ROJO_OSCURO)
        if antes is not None and c != antes:
            cambios += 1
        antes = c
    assert cambios <= 10                     # menos de 3 destellos por segundo (WCAG 2.3.1)
    assert cambios >= 8                      # pero sí alterna
    assert E.color_fondo(-1, 0) == E.ROJO_CLARO and E.color_fondo(float("nan"), 0) == E.ROJO_CLARO


# =========================================================================== sonido
def _leer_wav(datos: bytes):
    with wave.open(io.BytesIO(datos), "rb") as w:
        n = w.getnframes()
        crudo = w.readframes(n)
        return w.getnchannels(), w.getsampwidth(), w.getframerate(), n, struct.unpack("<%dh" % n, crudo)


def test_el_wav_generado_es_valido_y_su_fuerza_sigue_al_volumen():
    canales, ancho, frec, n, muestras = _leer_wav(A.generar_wav(100))
    assert (canales, ancho, frec) == (1, 2, A.FRECUENCIA_MUESTREO)
    assert n == 2 * round(A.FRECUENCIA_MUESTREO * A.DURACION_TONO_S)
    assert n / frec == pytest.approx(0.70, abs=0.01)
    pico100 = max(abs(x) for x in muestras)
    pico50 = max(abs(x) for x in _leer_wav(A.generar_wav(50))[4])
    pico10 = max(abs(x) for x in _leer_wav(A.generar_wav(10))[4])
    assert 30000 <= pico100 <= 32767
    assert pico50 == pytest.approx(pico100 / 2, rel=0.02)
    assert pico10 == pytest.approx(pico100 / 10, rel=0.05)
    # valores raros: nunca revienta ni pasa del máximo
    for v in (float("nan"), "fuerte", -5, 500, None):
        assert 0 < A.amplitud(v) <= A.AMPLITUD_MAX


class WinsoundFalso:
    SND_FILENAME, SND_ASYNC, SND_LOOP = 0x20000, 0x1, 0x8

    def __init__(self, falla_play=False, con_beep=True):
        self.falla_play = falla_play
        self.llamadas = []
        self.beeps = []
        if not con_beep:
            self.Beep = None

    def PlaySound(self, sonido, flags):  # noqa: N802
        self.llamadas.append((sonido, flags))
        if self.falla_play and sonido is not None:
            raise RuntimeError("sin dispositivo de sonido")

    def Beep(self, f, ms):  # noqa: N802
        self.beeps.append((f, ms))
        time.sleep(ms / 10000.0)


def test_la_alarma_suena_en_bucle_desde_la_carpeta_de_datos_y_se_detiene(tmp_path):
    ws = WinsoundFalso()
    a = A.Alarma(80, carpeta=tmp_path, winsound_mod=ws)
    assert a.tocar() is True and a.sonando and not a.respaldo
    ruta, flags = ws.llamadas[-1]
    assert Path(ruta) == tmp_path / "alarma.wav" and Path(ruta).exists()
    assert flags == ws.SND_FILENAME | ws.SND_ASYNC | ws.SND_LOOP
    assert _leer_wav(Path(ruta).read_bytes())[0] == 1
    a.tocar()                                       # ya suena: no se vuelve a llamar
    assert len(ws.llamadas) == 1
    a.detener()
    assert ws.llamadas[-1] == (None, 0) and not a.sonando
    a.detener()                                     # detener dos veces no falla


def test_la_carpeta_de_datos_por_defecto_es_la_de_lycan_face_datos(tmp_path, monkeypatch):
    monkeypatch.setenv("LYCAN_FACE_DATOS", str(tmp_path / "datos"))
    a = A.Alarma(100, winsound_mod=WinsoundFalso())
    assert a.preparar() == tmp_path / "datos" / "alarma.wav"


def test_si_no_se_puede_escribir_en_la_carpeta_de_datos_usa_la_temporal(tmp_path, monkeypatch):
    archivo = tmp_path / "no_es_carpeta"
    archivo.write_text("x")
    temporal = tmp_path / "temporal"
    temporal.mkdir()
    monkeypatch.setattr(A.tempfile, "gettempdir", lambda: str(temporal))
    a = A.Alarma(100, carpeta=archivo, winsound_mod=WinsoundFalso())
    assert a.preparar() == temporal / "alarma.wav"
    # cambiar el volumen vuelve a escribir el archivo
    antes = (temporal / "alarma.wav").read_bytes()
    a.volumen = 30
    a.preparar()
    assert (temporal / "alarma.wav").read_bytes() != antes


def test_si_playsound_falla_suena_el_respaldo_y_se_detiene(tmp_path, caplog):
    ws = WinsoundFalso(falla_play=True)
    a = A.Alarma(100, carpeta=tmp_path, winsound_mod=ws)
    with caplog.at_level("WARNING", logger="lycan"):
        assert a.tocar() is True
    assert a.respaldo and a.sonando
    assert any("respaldo" in r.getMessage() for r in caplog.records)      # queda anotado
    fin = time.monotonic() + 2.0
    while not ws.beeps and time.monotonic() < fin:
        time.sleep(0.01)
    assert ws.beeps and {f for f, _ in ws.beeps} <= {A.TONO_ALTO, A.TONO_BAJO}
    a.detener()
    a._hilo.join(timeout=2.0)
    assert not a._hilo.is_alive() and not a.sonando


def test_sin_playsound_ni_beep_avisa_que_no_puede_sonar(tmp_path):
    a = A.Alarma(100, carpeta=tmp_path, winsound_mod=WinsoundFalso(falla_play=True, con_beep=False))
    assert a.tocar() is False and not a.sonando
    muda = A.AlarmaMuda(falla=True)
    assert muda.tocar() is False
    muda = A.AlarmaMuda()
    assert muda.tocar() is True and muda.sonando
    muda.detener()
    assert not muda.sonando and muda.veces_detener == 1


def _importa(ruta: Path) -> set:
    arbol = ast.parse(ruta.read_text("utf-8"))
    nombres = set()
    for n in ast.walk(arbol):
        if isinstance(n, ast.Import):
            nombres |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module:
            nombres.add(n.module.split(".")[0])
    return nombres


@pytest.mark.parametrize("archivo", ["sistema/alarma.py", "emergencia.py", "ui/emergencia.py"])
def test_la_emergencia_no_usa_la_red(archivo):
    usados = _importa(RAIZ / archivo)
    assert not usados & {"socket", "urllib", "http", "requests", "smtplib", "ssl", "asyncio"}, usados
