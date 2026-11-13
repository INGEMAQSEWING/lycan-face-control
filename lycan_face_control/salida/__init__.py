"""Salidas: Windows real (SendInput) y simulada (pruebas, calibración y --simular)."""
from .base import ErrorEnvio, SalidaBase, eventos_texto
from .simulada import SalidaSimulada

__all__ = ["ErrorEnvio", "SalidaBase", "SalidaSimulada", "crear", "eventos_texto"]


def crear(simular: bool):
    if simular:
        return SalidaSimulada(max_eventos=2000)
    from .windows import SalidaWindows
    return SalidaWindows()
