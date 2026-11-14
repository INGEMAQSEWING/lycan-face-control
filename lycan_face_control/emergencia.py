"""Emergencia (versión 1.1, paquete B): lógica pura del botón AYUDA, sin tkinter ni Windows.

- ``PlanAlarma`` dice en cada momento qué toca: la alarma, la voz o silencio. La alarma suena en
  bucle; cada ``repetir_s`` segundos se calla y la voz dice el mensaje (12, 24, 36...); al
  terminar la voz vuelve la alarma. Sin voz (o con ``repetir_voz`` apagado) la alarma es continua;
  si la alarma falla, solo queda la voz.
- ``mensaje_voz(cfg)`` y ``textos_pantalla(cfg)``: lo que dice la voz y lo que se lee en la
  pantalla roja (con el nombre del cuidador de Opciones > Teclado y voz).
- ``color_fondo(t, t0)``: el fondo alterna entre dos rojos **una vez por segundo** (menos de tres
  destellos por segundo: no provoca convulsiones, WCAG 2.3.1).

Nada de esto usa internet: avisar al celular del cuidador queda como idea futura
(docs/decisiones.md).
"""
from __future__ import annotations

import math

ROJO_CLARO = "#b00000"      # revisión de la 1.1: con #c00000 el blanco daba 6,5:1; así 7,4:1
ROJO_OSCURO = "#5a0000"
CAMBIO_COLOR_S = 1.0          # un cambio de color por segundo (WCAG 2.3.1: menos de 3 destellos/s)
VOZ_POR_LETRA_S = 0.08        # duración estimada de la voz: 0,08 s por letra + 1 s
VOZ_EXTRA_S = 1.0
ALARMA_MIN_S = 2.0            # entre dos mensajes la alarma suena al menos 2 s
PROBAR_S = 3.0                # «Probar la alarma (3 segundos)»

ALARMA, VOZ, SILENCIO = "alarma", "voz", "silencio"


def duracion_voz(texto: str) -> float:
    """Tiempo aproximado que tarda la voz en decir ``texto``."""
    return VOZ_POR_LETRA_S * len(texto or "") + VOZ_EXTRA_S


class PlanAlarma:
    """Qué suena en cada momento desde ``t0`` (segundos del reloj que use la interfaz)."""

    def __init__(self, t0: float, repetir_voz: bool = True, repetir_s: float = 12.0,
                 duracion_voz_s: float = 3.0, hay_voz: bool = True, hay_alarma: bool = True):
        self.t0 = float(t0)
        self.repetir_s = max(float(repetir_s), 1.0)
        self.con_voz = bool(repetir_voz) and bool(hay_voz)
        self.hay_alarma = bool(hay_alarma)
        # la voz nunca tapa toda la alarma: entre dos mensajes la alarma suena al menos 2 s
        dur = max(float(duracion_voz_s), 0.0)
        self.duracion_voz_s = min(dur, max(self.repetir_s - ALARMA_MIN_S, 0.5))

    def ciclo(self, t: float) -> int:
        """Número del mensaje de voz que toca (0 = todavía ninguno). El primero cae a los
        ``repetir_s`` segundos, el segundo al doble, etc."""
        if not self.con_voz:
            return 0
        d = float(t) - self.t0
        if not math.isfinite(d) or d < self.repetir_s - 1e-9:
            return 0
        return int((d + 1e-9) // self.repetir_s)

    def hablando(self, t: float) -> bool:
        n = self.ciclo(t)
        if n <= 0:
            return False
        return float(t) - (self.t0 + n * self.repetir_s) < self.duracion_voz_s - 1e-9

    def que_toca(self, t: float) -> str:
        """``"alarma"``, ``"voz"`` o ``"silencio"``."""
        if self.hablando(t):
            return VOZ
        return ALARMA if self.hay_alarma else SILENCIO

    def momentos_voz(self, hasta: float) -> list[float]:
        """Cuándo empieza cada mensaje de voz hasta ``hasta`` (para las pruebas y el registro)."""
        if not self.con_voz:
            return []
        out = []
        n = 1
        while self.t0 + n * self.repetir_s <= hasta + 1e-9:
            out.append(self.t0 + n * self.repetir_s)
            n += 1
        return out


def _cuidador(cfg: dict) -> str:
    c = str(((cfg or {}).get("teclado") or {}).get("cuidador") or "").strip()
    return c or "alguien"


def _mensaje(cfg: dict) -> str:
    m = str(((cfg or {}).get("emergencia") or {}).get("mensaje") or "").strip()
    m = m.rstrip(" .")
    return m or "Necesito ayuda"


def mensaje_voz(cfg: dict) -> str:
    """Lo que dice la voz: «Necesito ayuda. Por favor, que venga alguien.» con los valores de
    fábrica."""
    from .ui.textos import t
    return t("emergencia_voz", mensaje=_mensaje(cfg), cuidador=_cuidador(cfg))


def textos_pantalla(cfg: dict, atajo: str | None = None) -> dict:
    """Textos de la pantalla roja: título, a quién se llama, el botón y cómo apagarla."""
    from .ui.textos import t
    if atajo is None:
        atajo = str(((cfg or {}).get("atajos") or {}).get("emergencia") or "Ctrl+Alt+A")
    return {"titulo": t("emergencia_titulo"),
            "llamando": t("emergencia_llamando", cuidador=_cuidador(cfg)),
            "atendido": t("emergencia_atendido"),
            "como_parar": t("emergencia_como_parar", atajo=atajo)}


def color_fondo(t: float, t0: float) -> str:
    """Rojo claro y rojo oscuro, alternando una vez por segundo."""
    d = float(t) - float(t0)
    if not math.isfinite(d) or d < 0:
        return ROJO_CLARO
    return ROJO_CLARO if int(d // CAMBIO_COLOR_S) % 2 == 0 else ROJO_OSCURO
