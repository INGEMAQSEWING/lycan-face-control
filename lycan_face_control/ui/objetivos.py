"""Registro de los botones propios que se eligen con la cabeza (sección 2.1 y 3.8).

Cada ventana propia registra aquí sus botones con un identificador. El registro:

1. calcula sus rectángulos en píxeles físicos de pantalla (tkinter con DPI activado) y se los
   publica al motor (``motor.poner_objetivos``) solo cuando cambian;
2. publica también el rectángulo de cada ventana propia como ``ventana:<nombre>`` con
   ``elegible=False`` (ahí no hay clic ni permanencia libre: nunca se hace clic en lo propio);
3. cuando el motor avisa ``Elegir(id)`` (permanencia o gesto con la cabeza) llama a la acción del
   botón; cuando el cuidador hace clic con el ratón, hace lo mismo.

Botones **internos** (``interno=True``): los atiende la máquina de estados (``barra:clic``,
``barra:doble``, ``reanudar``, ``desplazar:terminar``...). Elegidos con la cabeza, la máquina ya
hizo lo suyo y aquí solo se marca el botón; con el ratón se le pide a la máquina con la orden
``("elegir", id)``. Así nunca se hace dos veces.

Para la Parte 4 (teclado): ``manejador(prefijo, funcion)`` atiende identificadores que no son de
un botón registrado (``barrido:elegir``, ``barrido:siguiente``, ``accion:borrar``...).
"""
from __future__ import annotations

import logging
import tkinter as tk
from dataclasses import dataclass

from ..permanencia import Objetivo

log = logging.getLogger("lycan")


@dataclass
class Entrada:
    ident: str
    widget: object
    accion: object = None            # callable() o None
    interno: bool = False
    tiempo_s: float | None = None
    repetir: bool | None = None
    activo: bool = True              # se puede desactivar sin quitarlo


class Registro:
    def __init__(self, publicar=None, orden=None):
        """``publicar(lista_de_Objetivo)``: normalmente ``motor.poner_objetivos``.
        ``orden(*args)``: normalmente ``app.orden`` (para los botones internos elegidos con el ratón)."""
        self.publicar_fn = publicar
        self.orden_fn = orden
        self.entradas: list[Entrada] = []
        self.ventanas: dict[str, object] = {}
        self.manejadores: list[tuple[str, object]] = []
        self._ultimo: list | None = None
        self._resaltado: str | None = None

    # ------------------------------------------------------------ alta y baja
    def agregar(self, ident: str, widget, accion=None, interno: bool = False, tiempo_s: float | None = None,
                repetir: bool | None = None) -> Entrada:
        e = Entrada(ident, widget, accion, interno, tiempo_s, repetir)
        self.entradas.append(e)
        try:
            widget.bind("<Destroy>", lambda _ev, w=widget: self.quitar_widget(w), add="+")
        except (tk.TclError, AttributeError):
            pass
        return e

    def quitar_widget(self, widget):
        self.entradas = [e for e in self.entradas if e.widget is not widget]

    def quitar(self, prefijo: str):
        self.entradas = [e for e in self.entradas if not e.ident.startswith(prefijo)]

    def cambiar_id(self, widget, ident: str, accion=None, interno: bool | None = None):
        """Un mismo botón que cambia de función (Pausar <-> Reanudar)."""
        for e in self.entradas:
            if e.widget is widget:
                e.ident = ident
                if accion is not None:
                    e.accion = accion
                if interno is not None:
                    e.interno = interno

    def ventana(self, nombre: str, toplevel):
        self.ventanas[nombre] = toplevel
        try:
            toplevel.bind("<Destroy>", lambda ev, n=nombre, w=toplevel: self._ventana_destruida(ev, n, w),
                          add="+")
        except (tk.TclError, AttributeError):
            pass

    def _ventana_destruida(self, ev, nombre, toplevel):
        if getattr(ev, "widget", None) is toplevel and self.ventanas.get(nombre) is toplevel:
            del self.ventanas[nombre]

    def quitar_ventana(self, nombre: str):
        self.ventanas.pop(nombre, None)

    def manejador(self, prefijo: str, funcion):
        """``funcion(ident)`` atiende los identificadores que empiezan por ``prefijo`` y no son de
        un botón registrado. Devuelve True si lo atendió."""
        self.manejadores = [(p, f) for p, f in self.manejadores if p != prefijo]
        self.manejadores.append((prefijo, funcion))

    # ------------------------------------------------------------ cálculo
    @staticmethod
    def _rect(widget):
        try:
            if not widget.winfo_exists() or not widget.winfo_viewable():
                return None
            w, h = widget.winfo_width(), widget.winfo_height()
            if w <= 1 or h <= 1:
                return None
            x, y = widget.winfo_rootx(), widget.winfo_rooty()
        except (tk.TclError, AttributeError, RuntimeError):
            return None
        return (int(x), int(y), int(x + w), int(y + h))

    def calcular(self) -> list:
        objs = []
        vistos = set()
        for e in self.entradas:
            if not e.activo or e.ident in vistos:
                continue
            r = self._rect(e.widget)
            if r is None:
                continue
            vistos.add(e.ident)
            objs.append(Objetivo(e.ident, r, e.tiempo_s, True, e.repetir))
        for nombre, top in list(self.ventanas.items()):
            r = self._rect(top)
            if r is not None:
                objs.append(Objetivo(f"ventana:{nombre}", r, None, False))
        return objs

    def publicar(self, forzar: bool = False) -> bool:
        objs = self.calcular()
        clave = [(o.id, o.rect, o.tiempo_s, o.elegible, o.repetir) for o in objs]
        if not forzar and clave == self._ultimo:
            return False
        self._ultimo = clave
        if self.publicar_fn is not None:
            try:
                self.publicar_fn(objs)
            except Exception:  # noqa: BLE001
                log.exception("No se pudieron publicar los botones")
        return True

    # ------------------------------------------------------------ elegir
    def buscar(self, ident: str) -> Entrada | None:
        candidatos = [e for e in self.entradas if e.ident == ident and e.activo]
        for e in candidatos:
            if self._rect(e.widget) is not None:
                return e
        return candidatos[0] if candidatos else None

    def elegir(self, ident: str, origen: str = "cabeza") -> bool:
        """``origen`` = 'cabeza' (Elegir del motor) o 'raton' (clic del cuidador)."""
        e = self.buscar(ident)
        if e is not None:
            self._destello(e.widget)
            if e.interno:
                if origen == "raton" and self.orden_fn is not None:
                    self.orden_fn("elegir", ident)
                return True
            if e.accion is not None:
                try:
                    e.accion()
                except Exception:  # noqa: BLE001
                    log.exception("Error al elegir %s", ident)
            return True
        for prefijo, f in self.manejadores:
            if ident.startswith(prefijo):
                try:
                    if f(ident):
                        return True
                except Exception:  # noqa: BLE001
                    log.exception("Error al atender %s", ident)
        return False

    def comando(self, ident: str):
        """Función para el ``command`` de un botón: el clic del ratón pasa por el registro."""
        return lambda: self.elegir(ident, "raton")

    def resaltar(self, ident: str | None):
        """Borde de color en el botón al que apunta la cabeza."""
        if ident == self._resaltado:
            return
        for e in self.entradas:
            if hasattr(e.widget, "resaltar") and e.ident in (ident, self._resaltado):
                try:
                    e.widget.resaltar(e.ident == ident)
                except tk.TclError:
                    pass
        self._resaltado = ident

    @staticmethod
    def _destello(widget):
        """Señal visible de "elegido" durante 250 ms."""
        try:
            if not hasattr(widget, "activo"):
                return
            antes = getattr(widget, "_activo", False)
            widget.activo(not antes)
            widget.after(250, lambda: widget.winfo_exists() and widget.activo(antes))
        except (tk.TclError, AttributeError):
            pass
