"""Dibuja el ícono de Lycan Face Control con Pillow (recursos/lycan-face.png y .ico).

Mismo estilo que el de Lycan Mouse Control (cuadro oscuro redondeado, aro azul y punto verde de
"activo"), pero con una cara sencilla de lobo: cabeza clara con dos orejas, ojos y una sonrisa.
Se dibuja a 1024 px y se reduce (bordes suaves). Uso:

    py -3.10 herramientas\\crear_icono.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

RAIZ = Path(__file__).resolve().parents[1]
FONDO = (21, 24, 29, 255)
AZUL = (52, 120, 246, 255)
BLANCO = (242, 244, 247, 255)
VERDE = (34, 168, 84, 255)
GRANDE = 1024


def dibujar(tam: int = GRANDE) -> Image.Image:
    s = tam / 256.0

    def e(v):  # escala de la cuadrícula de 256 a la de dibujo
        return v * s

    im = Image.new("RGBA", (tam, tam), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    # Cuadro oscuro redondeado
    d.rounded_rectangle((e(8), e(8), e(248), e(248)), radius=e(44), fill=FONDO)
    # Aro azul (como el del mouse)
    d.ellipse((e(38), e(38), e(218), e(218)), outline=AZUL, width=int(e(14)))
    # Cabeza de lobo: orejas en punta, mejillas anchas y hocico hacia abajo
    d.polygon([(e(76), e(114)), (e(82), e(54)), (e(114), e(86)), (e(142), e(86)), (e(174), e(54)),
               (e(180), e(114)), (e(174), e(146)), (e(128), e(200)), (e(82), e(146))], fill=BLANCO)
    # Ojos (redondos: mirada tranquila)
    d.ellipse((e(98), e(114), e(114), e(130)), fill=FONDO)
    d.ellipse((e(142), e(114), e(158), e(130)), fill=FONDO)
    # Nariz y sonrisa
    d.polygon([(e(116), e(160)), (e(140), e(160)), (e(128), e(174))], fill=FONDO)
    d.arc((e(110), e(160), e(146), e(188)), start=30, end=150, fill=FONDO, width=int(e(6)))
    # Punto verde de "activo"
    d.ellipse((e(168), e(46), e(204), e(82)), fill=VERDE)
    return im


def main() -> None:
    destino = RAIZ / "recursos"
    destino.mkdir(exist_ok=True)
    grande = dibujar()
    png = grande.resize((256, 256), Image.LANCZOS)
    png.save(destino / "lycan-face.png")
    tamanos = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    png.save(destino / "lycan-face.ico", sizes=tamanos)
    print("Listo:", destino / "lycan-face.png", destino / "lycan-face.ico")


if __name__ == "__main__":
    main()
