"""Acciones que produce la lógica pura y que la salida convierte en eventos de Windows.

La lógica (gestos, permanencia, estados, teclado) nunca toca Windows: devuelve listas de estas
acciones. Solo las "de entrada" llegan a Windows (o a la salida simulada); el resto son para la
interfaz (avisos, sonidos, voz, elegir un botón propio).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Mover:
    """Mover el puntero a un píxel absoluto del escritorio virtual."""
    x: int
    y: int


@dataclass(frozen=True)
class MoverDelta:
    """Mover el puntero desde donde esté ahora + (dx, dy)."""
    dx: int
    dy: int


@dataclass(frozen=True)
class Bajar:
    boton: str  # 'izq' | 'der' | 'medio'


@dataclass(frozen=True)
class Subir:
    boton: str


@dataclass(frozen=True)
class Clic:
    """Bajar + subir en una sola llamada (nunca queda presionado). veces=2 es doble clic."""
    boton: str
    veces: int = 1


@dataclass(frozen=True)
class Rueda:
    delta: int                 # múltiplos de 120 (positivo = hacia arriba / derecha)
    horizontal: bool = False


@dataclass(frozen=True)
class Tecla:
    """Mantener o soltar un modificador ('shift' | 'ctrl' | 'alt')."""
    tecla: str
    abajo: bool


@dataclass(frozen=True)
class TeclaVK:
    """Pulsación completa (bajar y subir en el mismo envío) de una tecla virtual permitida:
    Borrar, Enter, Espacio, Tab, flechas, Esc, Inicio, Fin, Supr."""
    vk: int


@dataclass(frozen=True)
class Texto:
    """Escribir texto Unicode en el programa activo (tildes, ñ, ¿, emoji). Cada carácter baja y
    sube en el mismo envío; salto de línea = Enter y tabulador = Tab."""
    texto: str


@dataclass(frozen=True)
class Esperar:
    ms: int


@dataclass(frozen=True)
class SoltarTodo:
    motivo: str = ""


@dataclass(frozen=True)
class Aviso:
    """Mensaje para la interfaz (no llega a Windows)."""
    clave: str
    texto: str = ""


@dataclass(frozen=True)
class Sonido:
    """Sonido para la interfaz: 'activar', 'pausar', 'clic', 'perdida', 'listo', 'alerta'."""
    nombre: str


@dataclass(frozen=True)
class Hablar:
    """Decir un texto en voz alta (voz de Windows sin internet)."""
    texto: str
    urgente: bool = False


@dataclass(frozen=True)
class Elegir:
    """Elegir un objetivo propio (botón de la barra, tecla, frase). Lo atiende la interfaz,
    nunca se envía un clic a una ventana propia."""
    objetivo: str


ACCIONES_DE_ENTRADA = (Mover, MoverDelta, Bajar, Subir, Clic, Rueda, Tecla, TeclaVK, Texto, Esperar,
                       SoltarTodo)


def es_de_entrada(a) -> bool:
    """True si la acción llega a Windows (o a la salida simulada)."""
    return isinstance(a, ACCIONES_DE_ENTRADA)


_NOMBRES_VK = {0x08: "Borrar", 0x09: "Tabulador", 0x0D: "Enter", 0x1B: "Escape", 0x20: "Espacio",
               0x23: "Fin", 0x24: "Inicio", 0x25: "Flecha izquierda", 0x26: "Flecha arriba",
               0x27: "Flecha derecha", 0x28: "Flecha abajo", 0x2E: "Suprimir"}


def describir(a) -> str:
    """Texto corto en español para el modo ensayo y el registro.

    Nunca incluye lo que la persona escribe o dice (privacidad: el registro no guarda texto)."""
    nombres = {"izq": "izquierdo", "der": "derecho", "medio": "del medio"}
    if isinstance(a, Mover):
        return f"Mover a ({a.x}, {a.y})"
    if isinstance(a, MoverDelta):
        return f"Mover {a.dx:+d}, {a.dy:+d}"
    if isinstance(a, Bajar):
        return f"Presionar botón {nombres.get(a.boton, a.boton)}"
    if isinstance(a, Subir):
        return f"Soltar botón {nombres.get(a.boton, a.boton)}"
    if isinstance(a, Clic):
        return ("Doble clic " if a.veces == 2 else "Clic ") + nombres.get(a.boton, a.boton)
    if isinstance(a, Rueda):
        if a.horizontal:
            return f"Desplazar {'a la derecha' if a.delta > 0 else 'a la izquierda'}"
        return f"Desplazar {'hacia arriba' if a.delta > 0 else 'hacia abajo'}"
    if isinstance(a, Tecla):
        return f"{'Presionar' if a.abajo else 'Soltar'} {a.tecla.capitalize()}"
    if isinstance(a, TeclaVK):
        return f"Tecla {_NOMBRES_VK.get(a.vk, hex(a.vk))}"
    if isinstance(a, Texto):
        return f"Escribir {len(a.texto)} caracteres"
    if isinstance(a, Esperar):
        return f"Esperar {a.ms} ms"
    if isinstance(a, SoltarTodo):
        return "Soltar todo" + (f" ({a.motivo})" if a.motivo else "")
    if isinstance(a, Aviso):
        return a.texto or a.clave
    if isinstance(a, Sonido):
        return f"Sonido {a.nombre}"
    if isinstance(a, Hablar):
        return "Hablar" + (" (urgente)" if a.urgente else "")
    if isinstance(a, Elegir):
        return f"Elegir {a.objetivo}"
    return repr(a)
