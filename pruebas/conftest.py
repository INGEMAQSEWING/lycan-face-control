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
