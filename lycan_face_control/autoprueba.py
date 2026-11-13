"""Cara dibujada con OpenCV para la autoprueba de ``--check`` (sin cámara).

Es la misma cara de herramientas/cara_dibujada.py: MediaPipe FaceMesh la reconoce y entrega los
478 puntos. Así ``--check`` comprueba que los modelos de la cara vienen dentro del programa
instalado (si faltan, el .exe falla con "face_landmark_front_cpu.binarypb ... does not exist").
"""
from __future__ import annotations

import numpy as np


def cara_dibujada(boca: int = 6, ojo: int = 9, ceja: int = 0, ancho: int = 640, alto: int = 480) -> np.ndarray:
    import cv2
    W, H = ancho, alto
    img = np.full((H, W, 3), (200, 205, 210), np.uint8)
    cx, cy = W // 2, H // 2
    cv2.ellipse(img, (cx, cy - 40), (125, 150), 0, 180, 360, (40, 35, 30), -1)          # cabello
    cv2.rectangle(img, (cx - 45, cy + 120), (cx + 45, H), (120, 150, 190), -1)          # cuello
    mask = np.zeros((H, W), np.uint8)
    cv2.ellipse(mask, (cx, cy), (110, 145), 0, 0, 360, 255, -1)
    yy, xx = np.mgrid[0:H, 0:W]
    d = np.sqrt(((xx - cx) / 110.0) ** 2 + ((yy - cy) / 145.0) ** 2)
    sombra = np.clip(1.0 - 0.35 * d ** 2, 0, 1)
    piel = np.array([140, 170, 215], float)
    rostro = (piel[None, None, :] * sombra[..., None]).astype(np.uint8)
    img[mask > 0] = rostro[mask > 0]
    for s in (-1, 1):                                                                    # orejas
        cv2.ellipse(img, (cx + s * 112, cy + 5), (14, 30), 0, 0, 360, (120, 150, 195), -1)
    for s in (-1, 1):                                                                    # ojos y cejas
        ex, ey = cx + s * 42, cy - 25
        cv2.ellipse(img, (ex, ey), (22, ojo), 0, 0, 360, (245, 245, 245), -1)
        if ojo > 2:
            cv2.circle(img, (ex, ey), min(9, ojo), (60, 40, 30), -1)
            cv2.circle(img, (ex, ey), min(4, ojo), (10, 10, 10), -1)
        cv2.ellipse(img, (ex, ey), (22, max(ojo, 1)), 0, 180, 360, (50, 60, 80), 2)
        cv2.ellipse(img, (ex, ey - 22 - ceja), (26, 8), 0, 200, 340, (40, 35, 30), 5)
    pts = np.array([[cx, cy - 15], [cx - 14, cy + 30], [cx + 14, cy + 30]], np.int32)   # nariz
    cv2.polylines(img, [pts], False, (90, 120, 170), 2)
    cv2.ellipse(img, (cx, cy + 30), (16, 7), 0, 0, 180, (90, 115, 160), 2)
    cv2.ellipse(img, (cx, cy + 70), (34, boca), 0, 0, 360, (60, 60, 150), -1)           # boca
    if boca > 6:
        cv2.ellipse(img, (cx, cy + 70), (30, boca - 4), 0, 0, 360, (30, 20, 60), -1)
    return cv2.GaussianBlur(img, (5, 5), 0)
