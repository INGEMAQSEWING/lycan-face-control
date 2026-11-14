"""Piezas comunes de la interfaz: tema de colores (normal y alto contraste), letras grandes
escalables, botones grandes elegibles con la cabeza, el globo de ayuda "?" y el dibujo de la cara.

Reglas (sección 6): letras de 16 pt como mínimo en ventanas y 20 pt en la barra y el teclado,
escalables del 100 % al 200 % (``comodidad.escala_letra``); contraste de 7:1 o más; nunca solo
color (cada estado lleva también texto e ícono).
"""
from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass

from .. import constantes as K
from ..config import ruta_recurso

LETRA = "Segoe UI"
LETRA_SIMBOLOS = "Segoe UI Symbol"
MIN_PT_VENTANA = 16
MIN_PT_BARRA = 20


@dataclass(frozen=True)
class Tema:
    fondo: str
    fondo_2: str            # paneles
    texto: str
    texto_suave: str
    acento: str
    boton: str              # fondo de los botones
    boton_texto: str
    resalte: str            # borde del botón al que apunta la cabeza
    ambar: str
    verde: str
    rojo: str               # fondos con texto negro encima (7:1); las tiras usan K.ROJO
    rojo_texto: str         # rojo legible sobre el fondo oscuro (7:1)
    sobre_color: str        # texto sobre ámbar, verde, cian o rojo
    aviso_fondo: str
    aviso_texto: str
    alto_contraste: bool = False

    def color_estado(self, estado: str) -> str:
        return {K.ACTIVO: self.verde, K.PAUSA: self.ambar, K.SIN_CARA: self.rojo,
                K.CALIBRANDO: self.acento}.get(estado, self.acento)

    def texto_estado(self, estado: str) -> str:
        """Color para ESCRIBIR el estado sobre el fondo (el rojo de las tiras no llega a 7:1)."""
        if estado == K.SIN_CARA:
            return self.rojo_texto
        return self.color_estado(estado)


TEMA_NORMAL = Tema(fondo=K.FONDO, fondo_2="#132a52", texto=K.TEXTO, texto_suave="#d5def0", acento=K.ACENTO,
                   boton="#1d3a70", boton_texto=K.TEXTO, resalte=K.ACENTO, ambar=K.AMBAR, verde=K.VERDE,
                   rojo="#ff6b6b", rojo_texto="#ff8a8a", sobre_color="#000000", aviso_fondo="#3a2a00",
                   aviso_texto="#ffe7a8")

TEMA_ALTO_CONTRASTE = Tema(fondo=K.AC_FONDO, fondo_2="#000000", texto=K.AC_TEXTO, texto_suave=K.AC_TEXTO,
                           acento=K.AC_TEXTO, boton="#000000", boton_texto=K.AC_TEXTO, resalte="#ffffff",
                           ambar=K.AC_TEXTO, verde=K.AC_TEXTO, rojo=K.AC_TEXTO, rojo_texto=K.AC_TEXTO,
                           sobre_color="#000000", aviso_fondo="#000000", aviso_texto=K.AC_TEXTO,
                           alto_contraste=True)


def tema(cfg: dict | None) -> Tema:
    com = (cfg or {}).get("comodidad", {})
    return TEMA_ALTO_CONTRASTE if com.get("alto_contraste") else TEMA_NORMAL


def escala(cfg: dict | None) -> float:
    try:
        e = float((cfg or {}).get("comodidad", {}).get("escala_letra", 1.0))
    except (TypeError, ValueError):
        e = 1.0
    return min(max(e, 1.0), 2.0)


def letra(cfg: dict | None, pt: int = MIN_PT_VENTANA, negrita: bool = False, minimo: int = MIN_PT_VENTANA):
    """Tupla de letra escalada. Nunca baja de ``minimo`` puntos."""
    tam = max(int(round(pt * escala(cfg))), minimo)
    return (LETRA, tam, "bold") if negrita else (LETRA, tam)


# --------------------------------------------------------------------------- contraste (WCAG)
def _lineal(c: float) -> float:
    c = c / 255.0
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def luminancia(color: str) -> float:
    color = color.lstrip("#")
    r, g, b = (int(color[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _lineal(r) + 0.7152 * _lineal(g) + 0.0722 * _lineal(b)


def contraste(a: str, b: str) -> float:
    la, lb = sorted((luminancia(a), luminancia(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


# --------------------------------------------------------------------------- ventanas
def poner_icono(ventana):
    ruta = ruta_recurso("lycan-face.ico")
    if ruta.exists():
        try:
            ventana.iconbitmap(str(ruta))
        except tk.TclError:
            pass


def no_activar(ventana) -> int | None:
    """WS_EX_NOACTIVATE + TOPMOST + TOOLWINDOW: la ventana no le quita el foco al programa en el
    que la persona trabaja. Devuelve el identificador de la ventana de Windows (o None)."""
    try:
        ventana.update_idletasks()
        from ..sistema import ventanas_win as vw
        hwnd = vw.raiz(ventana.winfo_id())
        vw.no_activar(hwnd)
        return hwnd
    except Exception:  # noqa: BLE001
        return None


def atravesable(ventana) -> bool:
    """Los clics atraviesan la ventana (indicador junto al cursor, tira del borde)."""
    try:
        ventana.update_idletasks()
        from ..sistema import ventanas_win as vw
        vw.atravesable(vw.raiz(ventana.winfo_id()))
        return True
    except Exception:  # noqa: BLE001
        return False


def area_de_trabajo(ventana) -> tuple[int, int, int, int]:
    """(izq, arriba, der, abajo) del área de trabajo del monitor principal (sin la barra de tareas)."""
    try:
        from ..sistema import pantallas
        m = pantallas.elegir("principal")
        if m.trabajo:
            return tuple(int(v) for v in m.trabajo)
        return (m.x, m.y, m.x + m.ancho, m.y + m.alto)
    except Exception:  # noqa: BLE001
        return (0, 0, ventana.winfo_screenwidth(), ventana.winfo_screenheight() - 40)


def area_libre(app, ventana) -> tuple[int, int, int, int]:
    """Área de trabajo sin la franja de la barra de acciones, para que las ventanas grandes
    (Opciones, Ayuda, Calibración) no queden debajo de la barra."""
    l, a, d, ab = area_de_trabajo(ventana)
    barra = getattr(app, "barra", None)
    win = getattr(barra, "win", None)
    try:
        if win is not None and win.winfo_exists() and win.winfo_viewable():
            pos = app.cfg.datos["barra"].get("posicion", "derecha")
            w, h = win.winfo_width(), win.winfo_height()
            if pos in ("derecha", "izquierda"):
                # se deja el mismo margen a ambos lados para que la ventana quede centrada
                d -= w + 16
                l += w + 16
            elif pos == "arriba":
                a += h + 16
            else:
                ab -= h + 16
    except (tk.TclError, AttributeError, KeyError):
        pass
    if d - l < 600:
        return area_de_trabajo(ventana)
    return l, a, d, ab


# --------------------------------------------------------------------------- botón grande
class BotonGrande(tk.Label):
    """Botón grande hecho con una etiqueta (se ve igual en todos los Windows y se puede resaltar).

    - Con el ratón: un clic llama a ``comando`` (el cuidador).
    - Con la cabeza: la aplicación lo registra como objetivo (``Registro.agregar``) y el motor lo
      elige por permanencia o por un gesto; la aplicación llama al mismo ``comando``.
    - ``resaltar(True)`` le pone un borde de color cuando la cabeza apunta a él.
    """

    def __init__(self, padre, texto: str, comando=None, tema_: Tema = TEMA_NORMAL, fuente=None,
                 icono: str = "", ancho: int | None = None, alto: int | None = None, color: str | None = None,
                 texto_color: str | None = None, **kw):
        self.tema = tema_
        self.comando = comando
        self._icono = icono
        self._texto = texto
        self._color = color or tema_.boton
        self._texto_color = texto_color or (tema_.sobre_color if color else tema_.boton_texto)
        super().__init__(padre, text=self._componer(), bg=self._color, fg=self._texto_color,
                         font=fuente or (LETRA, MIN_PT_VENTANA, "bold"), padx=10, pady=6, bd=0,
                         highlightthickness=4, highlightbackground=self._borde_reposo(),
                         highlightcolor=self._borde_reposo(), cursor="hand2", justify="center", **kw)
        if ancho:
            self.configure(width=ancho)
        if alto:
            self.configure(height=alto)
        self._resaltado = False
        self._activo = False
        self.bind("<Button-1>", self._clic, add="+")
        self.bind("<Enter>", lambda e=None: self._hover(True), add="+")
        self.bind("<Leave>", lambda e=None: self._hover(False), add="+")

    def _borde_reposo(self):
        return self.tema.texto if self.tema.alto_contraste else self.tema.fondo

    def _componer(self) -> str:
        return f"{self._icono}\n{self._texto}" if self._icono else self._texto

    def poner_texto(self, texto: str, icono: str | None = None):
        if icono is not None:
            self._icono = icono
        if texto != self._texto or icono is not None:
            self._texto = texto
            self.configure(text=self._componer())

    @property
    def texto(self) -> str:
        return self._texto

    def poner_color(self, color: str | None, texto_color: str | None = None):
        self._color = color or self.tema.boton
        self._texto_color = texto_color or (self.tema.sobre_color if color else self.tema.boton_texto)
        self._pintar_fondo()           # si está encendido (barrido, modo de la barra) sigue viéndose así

    def activo(self, si: bool):
        """Botón "encendido" (por ejemplo, el modo de clic elegido en la barra)."""
        if si == self._activo:
            return
        self._activo = si
        if si:
            self.configure(bg=self.tema.acento, fg=self.tema.sobre_color)
        else:
            self.configure(bg=self._color, fg=self._texto_color)

    def _pintar_fondo(self):
        if self._activo:
            self.configure(bg=self.tema.acento, fg=self.tema.sobre_color)
        else:
            self.configure(bg=self._color, fg=self._texto_color)

    def destello(self):
        """Señal visible de "elegido" durante 250 ms (no cambia el estado del botón)."""
        try:
            self.configure(bg=self.tema.texto, fg=self.tema.fondo)
            self.after(250, lambda: self.winfo_exists() and self._pintar_fondo())
        except tk.TclError:
            pass

    def resaltar(self, si: bool):
        if si == self._resaltado:
            return
        self._resaltado = si
        borde = self.tema.resalte if si else self._borde_reposo()
        try:
            self.configure(highlightbackground=borde, highlightcolor=borde)
        except tk.TclError:
            pass

    def _hover(self, dentro: bool):
        if not self._resaltado:
            borde = self.tema.texto_suave if dentro else self._borde_reposo()
            try:
                self.configure(highlightbackground=borde, highlightcolor=borde)
            except tk.TclError:
                pass

    def _clic(self, _e=None):
        if self.comando is not None:
            self.comando()

    def invocar(self):
        self._clic()


# --------------------------------------------------------------------------- globo "?"
class Globo:
    """Globo de ayuda que aparece al pasar el ratón o al elegir el botón "?"."""

    def __init__(self, widget, texto: str, al_clic: bool = False, cfg: dict | None = None):
        self.widget = widget
        self.texto = texto
        self.cfg = cfg
        self.tip = None
        if al_clic:
            widget.bind("<Button-1>", self.alternar, add="+")
        else:
            widget.bind("<Enter>", self.mostrar, add="+")
            widget.bind("<Leave>", self.ocultar, add="+")

    def alternar(self, _e=None):
        if self.tip:
            self.ocultar()
        else:
            self.mostrar()

    def mostrar(self, _e=None):
        if self.tip or not self.texto:
            return
        try:
            x = self.widget.winfo_rootx() + 10
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
            self.tip = tw = tk.Toplevel(self.widget)
        except tk.TclError:
            return
        tw.wm_overrideredirect(True)
        tw.attributes("-topmost", True)
        tk.Label(tw, text=self.texto, justify="left", wraplength=420, bg="#fff8dc", fg="#000000",
                 relief="solid", bd=1, font=letra(self.cfg, 14, minimo=14), padx=10, pady=8).pack()
        tw.update_idletasks()
        sw, sh = tw.winfo_screenwidth(), tw.winfo_screenheight()
        w, h = tw.winfo_reqwidth(), tw.winfo_reqheight()
        x = min(x, sw - w - 8)
        if y + h > sh - 40:
            y = max(self.widget.winfo_rooty() - h - 4, 0)
        tw.wm_geometry(f"+{max(x, 0)}+{y}")
        no_activar(tw)
        tw.after(10000, self.ocultar)

    def ocultar(self, _e=None):
        if self.tip:
            try:
                self.tip.destroy()
            except tk.TclError:
                pass
            self.tip = None


def boton_ayuda(padre, texto: str, cfg: dict | None = None, tema_: Tema = TEMA_NORMAL):
    b = tk.Label(padre, text="?", bg=tema_.acento, fg=tema_.sobre_color, font=letra(cfg, 16, True),
                 width=2, cursor="hand2")
    Globo(b, texto, al_clic=True, cfg=cfg)
    return b


# --------------------------------------------------------------------------- dibujo de la cara
def dibujar_cara(canvas: tk.Canvas, x: float, y: float, tam: float, color: str, gesto: str = "reposo",
                 flecha: str | None = None, etiqueta: str = "") -> None:
    """Cara de línea (sin foto) que muestra un gesto: 'reposo', 'boca', 'cejas', 'sonrisa',
    'ojos' (cerrados) o 'mirar' con ``flecha`` = 'izq' | 'der' | 'arr' | 'aba'."""
    r = tam / 2
    w = max(int(tam / 40), 2)
    dx = dy = 0.0
    if gesto == "mirar" and flecha:
        dx = {"izq": -0.18, "der": 0.18}.get(flecha, 0.0) * r
        dy = {"arr": -0.15, "aba": 0.15}.get(flecha, 0.0) * r
    canvas.create_oval(x - r * 0.8, y - r, x + r * 0.8, y + r, outline=color, width=w)
    ojo_y = y - r * 0.2 + dy
    for s in (-1, 1):
        ox = x + s * r * 0.32 + dx
        if gesto == "ojos":
            canvas.create_line(ox - r * 0.14, ojo_y, ox + r * 0.14, ojo_y, fill=color, width=w)
        else:
            canvas.create_oval(ox - r * 0.13, ojo_y - r * 0.08, ox + r * 0.13, ojo_y + r * 0.08,
                               outline=color, width=w)
            canvas.create_oval(ox - r * 0.04, ojo_y - r * 0.04, ox + r * 0.04, ojo_y + r * 0.04, fill=color,
                               outline="")
        ceja_y = ojo_y - r * (0.33 if gesto == "cejas" else 0.2)
        canvas.create_line(ox - r * 0.16, ceja_y + r * 0.03, ox, ceja_y - r * 0.02, ox + r * 0.16,
                           ceja_y + r * 0.03, fill=color, width=w, smooth=True)
    canvas.create_line(x + dx, y - r * 0.05 + dy, x - r * 0.06 + dx, y + r * 0.18 + dy, x + r * 0.06 + dx,
                       y + r * 0.18 + dy, fill=color, width=w)
    by = y + r * 0.48 + dy
    if gesto == "boca":
        canvas.create_oval(x - r * 0.16 + dx, by - r * 0.14, x + r * 0.16 + dx, by + r * 0.2, outline=color,
                           width=w)
    elif gesto == "sonrisa":
        canvas.create_arc(x - r * 0.34 + dx, by - r * 0.22, x + r * 0.34 + dx, by + r * 0.14, start=200,
                          extent=140, style="arc", outline=color, width=w)
    else:
        canvas.create_line(x - r * 0.2 + dx, by, x + r * 0.2 + dx, by, fill=color, width=w)
    if flecha:
        largo = r * 0.55
        fx, fy = {"izq": (-1, 0), "der": (1, 0), "arr": (0, -1), "aba": (0, 1)}[flecha]
        ax, ay = x + fx * (r * 0.95), y + fy * (r * 1.1)
        canvas.create_line(ax, ay, ax + fx * largo, ay + fy * largo, fill=color, width=w * 2, arrow="last",
                           arrowshape=(w * 6, w * 7, w * 3))
    if etiqueta:
        canvas.create_text(x, y + r + 16, text=etiqueta, fill=color, font=(LETRA, 14, "bold"), anchor="n")


def dibujar_puntos(canvas: tk.Canvas, puntos, ancho: int, alto: int, color: str, espejo: bool = False) -> None:
    """Silueta de la cara a partir de los puntos normalizados (sin video): óvalo, ojos, cejas,
    nariz y boca. ``puntos``: (N, 3) en 0..1."""
    if puntos is None:
        return
    try:
        n = len(puntos)
    except TypeError:
        return
    if n < K.N_PUNTOS_MIN:
        return
    xs = [float(p[0]) for p in puntos]
    ys = [float(p[1]) for p in puntos]
    # encuadre: la cara ocupa el 80 % del alto del lienzo
    idx = K.OVALO_CARA
    xmin, xmax = min(xs[i] for i in idx), max(xs[i] for i in idx)
    ymin, ymax = min(ys[i] for i in idx), max(ys[i] for i in idx)
    alto_cara = max(ymax - ymin, 1e-6)
    s = 0.8 * alto / alto_cara
    cx, cy = (xmin + xmax) / 2, (ymin + ymax) / 2

    def P(i):
        x = (xs[i] - cx) * s
        if espejo:
            x = -x
        return ancho / 2 + x, alto / 2 + (ys[i] - cy) * s

    def linea(ids, cerrar=True, w=2):
        pts = []
        for i in ids:
            pts.extend(P(i))
        if cerrar:
            pts.extend(P(ids[0]))
        if len(pts) >= 4:
            canvas.create_line(*pts, fill=color, width=w, smooth=False)

    linea(idx, True, 2)
    linea(K.EAR_DER, True, 2)       # 33-160-158-133-153-144: contorno del ojo en orden
    linea(K.EAR_IZQ, True, 2)
    linea(K.CEJA_DER, False, 3)
    linea(K.CEJA_IZQ, False, 3)
    linea((K.COMISURA_DER, K.LABIO_SUP, K.COMISURA_IZQ, K.LABIO_INF), True, 2)
    nx, ny = P(K.NARIZ)
    canvas.create_oval(nx - 4, ny - 4, nx + 4, ny + 4, fill=color, outline="")
