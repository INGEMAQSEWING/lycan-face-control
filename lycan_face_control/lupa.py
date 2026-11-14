"""Lupa para el clic preciso (versión 1.1, paquete A; como el "Adjust Target" de TD Control).
Lógica pura: sin tkinter, sin Windows y sin capturas.

Con el modo «Lupa» la siguiente permanencia libre no hace clic: se agranda la parte de la
pantalla alrededor del punto (la **zona**) en una ventana aparte, y quedarse quieto sobre la
imagen agrandada hace el clic en el punto real que corresponde.

- ``zona(origen, monitor, zona_px)``: el cuadrado alrededor del punto, corrido para que quede
  dentro del monitor.
- ``ubicar_ventana(zona, monitor, aumento)``: dónde va la ventana y, dentro de ella, la imagen.
  La ventana va pegada al borde del monitor **opuesto** a la zona y **nunca la tapa** (así el clic
  se puede hacer al instante, sin esperar a que la lupa se cierre). La imagen mide como mucho el
  70 % del alto del monitor. Si no cabe sin tapar la zona, devuelve None.
- ``a_pantalla(p, imagen, zona)``: un punto de la imagen agrandada -> el punto real de la pantalla.

Todas las coordenadas son píxeles físicos del escritorio virtual (el proceso es consciente del
DPI, ``sistema/dpi.py``): con dos monitores el origen puede ser negativo. Rectángulos como
(izquierda, arriba, derecha, abajo), con derecha y abajo exclusivos.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

MAX_ALTO_FRAC = 0.70          # la imagen agrandada mide como mucho el 70 % del alto del monitor
MARGEN_PX = 8                 # distancia de la ventana al borde del monitor
SEPARACION_PX = 16            # la ventana queda al menos a esta distancia de la zona
EXTRA_ARRIBA_PX = 64          # alto del texto de instrucciones sobre la imagen
EXTRA_ABAJO_PX = 100          # alto del botón «Cerrar lupa» (72 px o más) bajo la imagen
AUMENTO_MIN_REAL = 1.5        # si para que quepa habría que agrandar menos que esto, no vale la pena
REDUCCIONES = (1.0, 0.85, 0.7, 0.55)
PREFIJO_ABRIR = "lupa:abrir"
ID_ZONA = "lupa:zona"
ID_CERRAR = "lupa:cerrar"


@dataclass(frozen=True)
class Ubicacion:
    ventana: tuple            # toda la ventana (texto + imagen + botón)
    imagen: tuple             # solo la imagen agrandada


def _num(v) -> float:
    v = float(v)
    if not math.isfinite(v):
        raise ValueError("número no finito")
    return v


def _rect(r) -> tuple:
    l, t, d, b = (int(round(_num(v))) for v in r)
    return (l, t, d, b)


def se_cruzan(a, b, separacion: float = 0.0) -> bool:
    """¿Los rectángulos se tocan (o quedan a menos de ``separacion``)?"""
    return (a[0] < b[2] + separacion and b[0] < a[2] + separacion
            and a[1] < b[3] + separacion and b[1] < a[3] + separacion)


def zona(origen, monitor, zona_px) -> tuple:
    """Cuadrado de lado ``zona_px`` centrado en ``origen`` y corrido para quedar dentro del
    ``monitor`` (si el monitor es más chico que el lado, se recorta)."""
    ml, mt, mr, mb = _rect(monitor)
    lado = max(int(round(_num(zona_px))), 1)
    ax, ay = min(lado, mr - ml), min(lado, mb - mt)
    if ax <= 0 or ay <= 0:
        raise ValueError("monitor vacío")
    x = int(round(_num(origen[0]))) - ax // 2
    y = int(round(_num(origen[1]))) - ay // 2
    x = min(max(x, ml), mr - ax)
    y = min(max(y, mt), mb - ay)
    return (x, y, x + ax, y + ay)


def ubicar_ventana(zona_, monitor, aumento, extra_arriba: int = EXTRA_ARRIBA_PX,
                   extra_abajo: int = EXTRA_ABAJO_PX, separacion: int = SEPARACION_PX) -> Ubicacion | None:
    """Rectángulo de la ventana de la lupa (y de su imagen) que nunca tapa la zona."""
    zl, zt, zr, zb = _rect(zona_)
    ml, mt, mr, mb = _rect(monitor)
    zw, zh = zr - zl, zb - zt
    if zw <= 0 or zh <= 0 or mr - ml <= 0 or mb - mt <= 0:
        return None
    aum = _num(aumento)
    if aum < 1:
        return None
    extras = int(extra_arriba) + int(extra_abajo)
    alto_mon, ancho_mon = mb - mt, mr - ml
    # tamaño máximo de la imagen: 70 % del alto, y que la ventana entera quepa en el monitor
    f = min(1.0, MAX_ALTO_FRAC * alto_mon / (zh * aum), (alto_mon - 2 * MARGEN_PX - extras) / (zh * aum),
            (ancho_mon - 2 * MARGEN_PX) / (zw * aum))
    zcx, zcy = (zl + zr) / 2.0, (zt + zb) / 2.0
    mcx, mcy = (ml + mr) / 2.0, (mt + mb) / 2.0
    for red in REDUCCIONES:
        iw, ih = int(zw * aum * f * red), int(zh * aum * f * red)
        if iw < zw * AUMENTO_MIN_REAL or ih < zh * AUMENTO_MIN_REAL:
            return None
        W, H = iw, ih + extras

        def cy(lo=mt, hi=mb):
            return int(min(max(zcy - H / 2.0, lo + MARGEN_PX), hi - MARGEN_PX - H))

        def cx(lo=ml, hi=mr):
            return int(min(max(zcx - W / 2.0, lo + MARGEN_PX), hi - MARGEN_PX - W))

        derecha = (mr - MARGEN_PX - W, cy())
        izquierda = (ml + MARGEN_PX, cy())
        abajo = (cx(), mb - MARGEN_PX - H)
        arriba = (cx(), mt + MARGEN_PX)
        horiz = [derecha, izquierda] if zcx <= mcx else [izquierda, derecha]
        vert = [abajo, arriba] if zcy <= mcy else [arriba, abajo]
        # primero el lado opuesto a la zona (a lo ancho si el monitor es más ancho que alto)
        if ancho_mon >= alto_mon:
            orden = [horiz[0], vert[0], horiz[1], vert[1]]
        else:
            orden = [vert[0], horiz[0], vert[1], horiz[1]]
        for x, y in orden:
            ventana = (x, y, x + W, y + H)
            if ventana[0] < ml or ventana[1] < mt or ventana[2] > mr or ventana[3] > mb:
                continue
            if se_cruzan(ventana, (zl, zt, zr, zb), separacion):
                continue
            imagen = (x, y + int(extra_arriba), x + iw, y + int(extra_arriba) + ih)
            return Ubicacion(ventana, imagen)
    return None


def a_pantalla(p, imagen, zona_) -> tuple[int, int]:
    """Punto de la imagen agrandada -> punto real: ``origen_zona + (p − origen_imagen) / aumento``
    (el aumento sale de los dos rectángulos). El resultado queda siempre dentro de la zona."""
    il, it, ir, ib = _rect(imagen)
    zl, zt, zr, zb = _rect(zona_)
    iw, ih = max(ir - il, 1), max(ib - it, 1)
    zw, zh = zr - zl, zb - zt
    x = zl + (_num(p[0]) - il) * zw / iw
    y = zt + (_num(p[1]) - it) * zh / ih
    x = min(max(int(round(x)), zl), zr - 1)
    y = min(max(int(round(y)), zt), zb - 1)
    return x, y


def a_imagen(p, imagen, zona_) -> tuple[float, float]:
    """Lo contrario de ``a_pantalla`` (punto real -> punto de la imagen)."""
    il, it, ir, ib = _rect(imagen)
    zl, zt, zr, zb = _rect(zona_)
    return (il + (_num(p[0]) - zl) * (ir - il) / max(zr - zl, 1),
            it + (_num(p[1]) - zt) * (ib - it) / max(zb - zt, 1))


def id_abrir(zona_, ubicacion: Ubicacion) -> str:
    """Identificador de ``Elegir`` para abrir la lupa, con la zona, la ventana y la imagen."""
    partes = [",".join(str(int(v)) for v in r) for r in (zona_, ubicacion.ventana, ubicacion.imagen)]
    return PREFIJO_ABRIR + "@" + "@".join(partes)


def leer_id(ident: str):
    """(zona, ventana, imagen) desde el identificador de ``id_abrir`` (o None si no sirve)."""
    try:
        if not ident.startswith(PREFIJO_ABRIR + "@"):
            return None
        partes = ident.split("@")[1:]
        if len(partes) != 3:
            return None
        rects = []
        for p in partes:
            r = tuple(int(v) for v in p.split(","))
            if len(r) != 4 or r[2] <= r[0] or r[3] <= r[1]:
                return None
            rects.append(r)
        return tuple(rects)
    except (AttributeError, ValueError, TypeError):
        return None
