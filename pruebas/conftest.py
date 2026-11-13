"""Ayudas comunes de las pruebas. Ninguna prueba abre la cámara real ni mueve el ratón real.

- La carpeta de datos se cambia a una temporal (LYCAN_FACE_DATOS) en TODAS las pruebas.
- ``verificar_invariantes(salida)``: reglas de seguridad sobre lo que se habría enviado.
- Las caras sintéticas están en ``pruebas/sintetico`` (``from sintetico import cara``).
- La Parte 2 agrega aquí el simulador ``Sim`` (motor + estados + salida simulada).
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

RAIZ = Path(__file__).resolve().parents[1]
PRUEBAS = Path(__file__).resolve().parent
for _p in (str(RAIZ), str(PRUEBAS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from lycan_face_control.salida.simulada import SalidaSimulada  # noqa: E402

HAY_MEDIAPIPE = importlib.util.find_spec("mediapipe") is not None


def verificar_invariantes(salida: SalidaSimulada, final: bool = True):
    """Invariantes de seguridad sobre los eventos enviados:
    - nunca dos "bajar" seguidos del mismo botón;
    - nunca rueda con Shift/Ctrl abajo;
    - teclas y caracteres bajan y suben en el mismo envío (lo revisa la salida simulada);
    - al final, nada queda presionado."""
    abajo_b, abajo_k = set(), set()
    for _, ev in salida.eventos:
        if ev[0] == "boton":
            if ev[2]:
                assert ev[1] not in abajo_b, f"dos 'bajar' seguidos del botón {ev[1]}"
                abajo_b.add(ev[1])
            else:
                abajo_b.discard(ev[1])
        elif ev[0] == "tecla":
            if ev[2]:
                abajo_k.add(ev[1])
            else:
                abajo_k.discard(ev[1])
        elif ev[0] in ("rueda", "rueda_h"):
            assert not (abajo_k & {"shift", "ctrl"}), "rueda con Shift/Ctrl abajo"
    assert not salida.violaciones, salida.violaciones
    if final:
        assert not abajo_b, f"quedaron botones abajo: {abajo_b}"
        assert not abajo_k, f"quedaron teclas abajo: {abajo_k}"
        assert salida.todo_suelto()


def pytest_collection_modifyitems(config, items):
    if HAY_MEDIAPIPE:
        return
    saltar = pytest.mark.skip(reason="mediapipe no está instalado")
    for item in items:
        if "mediapipe" in item.keywords:
            item.add_marker(saltar)


@pytest.fixture(autouse=True)
def _datos_temporales(tmp_path, monkeypatch):
    """Ninguna prueba toca la configuración real del usuario."""
    monkeypatch.setenv("LYCAN_FACE_DATOS", str(tmp_path / "datos"))
    yield


@pytest.fixture
def rng():
    return np.random.default_rng(1234)


@pytest.fixture
def salida_sim():
    return SalidaSimulada(escritorio=(0, 0, 1366, 768), cursor=(683, 384), reloj=lambda: 0.0)


# ---------------------------------------------------------------------------------------------
# Simulador de la Parte 2: máquina de estados + salida simulada, alimentados con caras
# sintéticas (o con medidas directas, más rápido, para las pruebas aleatorias).
# ---------------------------------------------------------------------------------------------
from lycan_face_control import config as _config  # noqa: E402
from lycan_face_control.cara import Medidas, medir_si_valida  # noqa: E402
from lycan_face_control.estados import Maquina  # noqa: E402
from lycan_face_control.mapeo import MONITOR_REFERENCIA  # noqa: E402

# Calibración que corresponde a la cara sintética: centro de frente y extremos cómodos a ±10°
# (medidos con pruebas/sintetico: yaw ±10° -> yaw_n 0,111 / -0,069; pitch ±10° -> 0,650 / 0,453)
CAL_SINTETICA = {
    "fecha": "2026-11-13 00:00", "centro": [0.022, 0.556], "izq": -0.069, "der": 0.111,
    "arr": 0.453, "aba": 0.650, "signo_x": 1.0, "signo_y": 1.0,
    "base": {"ear_der": 0.357, "ear_izq": 0.375, "mar": 0.016, "cejas": 0.356, "sonrisa": 0.557},
    "umbrales": {}, "parpadeo_natural_max_ms": 250.0, "parpadeos_min": 12,
}

# Medidas de la cara sintética en reposo (para construir Medidas sin generar la cara)
REPOSO = dict(io_px=124.656, yaw_n=0.022, pitch_n=0.556, roll=0.265, ear_der=0.357, ear_izq=0.375,
              mar=0.016, cejas=0.356, sonrisa=0.557)


def medidas(**kw) -> Medidas:
    """Medidas directas: ``medidas(yaw_n=0.05, mar=0.4)``."""
    d = dict(REPOSO)
    d.update(kw)
    return Medidas(**d)


def cfg_prueba(**cambios):
    """Configuración de fábrica con cambios por ruta: ``cfg_prueba(**{"gestos.boca.largo": "ninguna"})``."""
    cfg = _config.por_defecto()
    for ruta, v in cambios.items():
        d = cfg
        partes = ruta.split(".")
        for p in partes[:-1]:
            d = d[p]
        d[partes[-1]] = v
    return _config.validar(cfg)


class Sim:
    """Máquina + salida simulada con reloj propio. ``paso(medidas)`` avanza un cuadro."""

    def __init__(self, cfg=None, calibracion=CAL_SINTETICA, monitor=MONITOR_REFERENCIA, fps: float = 30.0,
                 t0: float = 100.0):
        self.cfg = cfg if cfg is not None else cfg_prueba()
        self.t = t0
        self.dt = 1.0 / fps
        self.monitor = monitor
        cx, cy = monitor.centro
        self.salida = SalidaSimulada(escritorio=(monitor.x, monitor.y, monitor.ancho, monitor.alto),
                                     cursor=(int(cx), int(cy)), reloj=lambda: self.t)
        self.salida.intervalo_doble_ms = 0
        self.maquina = Maquina(self.cfg, monitor, calibracion, pos_cursor=self.salida.posicion_cursor,
                               t0=t0, usar_calibracion_config=False)
        self.acciones = []        # (t, acción)
        self.vista = None

    def aplicar(self, acciones):
        for a in acciones:
            self.acciones.append((self.t, a))
        self.salida.aplicar(acciones)

    def paso(self, m):
        res = self.maquina.procesar(self.t, m)
        self.aplicar(res.acciones)
        self.vista = res.vista
        self.t += self.dt
        return res

    def cara(self, puntos):
        """Un cuadro con puntos de la cara sintética (None = sin cara)."""
        m = None if puntos is None else medir_si_valida(puntos, 640, 480)
        return self.paso(m)

    def durante(self, segundos: float, fuente):
        """``fuente(t_relativo) -> Medidas | None`` durante ``segundos``."""
        t_ini = self.t
        while self.t < t_ini + segundos - 1e-9:
            self.paso(fuente(self.t - t_ini))

    def quieto(self, segundos: float, **kw):
        m = medidas(**kw)
        self.durante(segundos, lambda _t: m)

    def orden(self, metodo: str, *args):
        acc = getattr(self.maquina, metodo)(self.t, *args)
        self.aplicar(acc)
        return acc

    # ---- consultas ----
    def de_tipo(self, tipo):
        return [a for _, a in self.acciones if isinstance(a, tipo)]

    def clics(self):
        from lycan_face_control.acciones import Clic
        return self.de_tipo(Clic)

    def elegidos(self):
        from lycan_face_control.acciones import Elegir
        return [a.objetivo for a in self.de_tipo(Elegir)]

    def avisos(self):
        from lycan_face_control.acciones import Aviso
        return [a.clave for a in self.de_tipo(Aviso)]

    def limpiar(self):
        self.acciones.clear()


@pytest.fixture
def sim():
    return Sim()
