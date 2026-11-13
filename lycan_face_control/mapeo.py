"""Monitores y, en la Parte 2, el mapeo de la pose de la cabeza a la pantalla (sección 3.6).

``Monitor``, ``zona_segura`` y ``MONITOR_REFERENCIA`` se copian de Lycan Mouse Control.
"""
from __future__ import annotations

from dataclasses import dataclass, field

BARRA_TAREAS_PX = 48     # alto típico de la barra de tareas de Windows 11 (si no se conoce)


@dataclass(frozen=True)
class Monitor:
    x: int
    y: int
    ancho: int
    alto: int
    principal: bool = True
    # Área de trabajo (sin la barra de tareas) como (izq, arriba, der, abajo) exclusivo, o None.
    trabajo: tuple | None = field(default=None, compare=False)

    @property
    def rect(self):
        return (self.x, self.y, self.x + self.ancho, self.y + self.alto)

    @property
    def centro(self):
        return (self.x + (self.ancho - 1) / 2.0, self.y + (self.alto - 1) / 2.0)

    def zona_segura(self, margen: int = 60):
        """Rectángulo (x0, y0, x1, y1) inclusivo, lejos de los bordes y de la barra de tareas."""
        if self.trabajo is not None:
            l, t, r, b = self.trabajo
        else:
            l, t, r, b = self.x, self.y, self.x + self.ancho, self.y + self.alto - BARRA_TAREAS_PX
        l, t = max(l, self.x), max(t, self.y)
        r, b = min(r, self.x + self.ancho), min(b, self.y + self.alto)
        mx = min(margen, max((r - l) // 4, 0))
        my = min(margen, max((b - t) // 4, 0))
        return (l + mx, t + my, r - 1 - mx, b - 1 - my)

    def recortar(self, x: float, y: float):
        """(x, y) dentro del monitor."""
        return (min(max(x, self.x), self.x + self.ancho - 1), min(max(y, self.y), self.y + self.alto - 1))


MONITOR_REFERENCIA = Monitor(0, 0, 1366, 768, True)
