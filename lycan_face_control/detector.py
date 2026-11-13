"""MediaPipe FaceMesh -> ``CaraDetectada`` (478 puntos en píxeles y normalizados). Sección 3.3.

- ``FaceMesh(static_image_mode=False, refine_landmarks=True, max_num_faces=1)``: los modelos van
  dentro del paquete mediapipe (no se descarga nada).
- Puntos en píxeles: P[i] = (x·ancho, y·alto, z·ancho) (MediaPipe da z en la escala de x).
- ``DetectorFalso`` tiene la misma interfaz y entrega los puntos de una función (caras
  sintéticas): sirve para probar el motor completo sin mediapipe y sin cámara.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np


@dataclass
class CaraDetectada:
    puntos: np.ndarray          # (N, 3) en píxeles: (x·ancho, y·alto, z·ancho)
    normalizados: np.ndarray    # (N, 3) como los da MediaPipe (x, y en 0..1; z relativo al ancho)
    ancho: int
    alto: int
    t: float                    # momento de la captura del cuadro (perf_counter)

    @classmethod
    def desde_normalizados(cls, norm, ancho: int, alto: int, t: float) -> "CaraDetectada":
        norm = np.asarray(norm, dtype=float)
        px = norm * np.array([ancho, alto, ancho], dtype=float)
        return cls(puntos=px, normalizados=norm, ancho=int(ancho), alto=int(alto), t=float(t))

    @classmethod
    def desde_pixeles(cls, puntos, ancho: int, alto: int, t: float) -> "CaraDetectada":
        px = np.asarray(puntos, dtype=float)
        norm = px / np.array([ancho, alto, ancho], dtype=float)
        return cls(puntos=px, normalizados=norm, ancho=int(ancho), alto=int(alto), t=float(t))


def _sin_matplotlib():
    """mediapipe.solutions.drawing_utils importa matplotlib sin usarlo: se evita cargarlo
    (pesa y el paquete de PyInstaller no lo lleva)."""
    import sys
    import types
    if "matplotlib" not in sys.modules:
        try:
            import importlib.util
            if importlib.util.find_spec("matplotlib") is not None:
                return
        except (ImportError, ValueError):
            pass
        mpl = types.ModuleType("matplotlib")
        plt = types.ModuleType("matplotlib.pyplot")
        mpl.pyplot = plt
        sys.modules["matplotlib"] = mpl
        sys.modules["matplotlib.pyplot"] = plt


class Detector:
    def __init__(self, deteccion: float = 0.5, seguimiento: float = 0.5, imagen_fija: bool = False):
        _sin_matplotlib()
        import mediapipe as mp
        self._malla = mp.solutions.face_mesh.FaceMesh(
            static_image_mode=imagen_fija, refine_landmarks=True, max_num_faces=1,
            min_detection_confidence=deteccion, min_tracking_confidence=seguimiento)
        self.t_fin = 0.0
        self.ms_ultimo = 0.0

    def procesar(self, imagen_bgr: np.ndarray, t: float | None = None) -> CaraDetectada | None:
        """Una imagen BGR -> la cara (o None si no hay). ``t`` = momento de la captura."""
        import cv2
        t0 = time.perf_counter()
        alto, ancho = imagen_bgr.shape[:2]
        rgb = cv2.cvtColor(imagen_bgr, cv2.COLOR_BGR2RGB)
        rgb.flags.writeable = False
        res = self._malla.process(rgb)
        self.t_fin = time.perf_counter()
        self.ms_ultimo = (self.t_fin - t0) * 1000.0
        if not res.multi_face_landmarks:
            return None
        lm = res.multi_face_landmarks[0].landmark
        norm = np.array([(p.x, p.y, p.z) for p in lm], dtype=float)
        return CaraDetectada.desde_normalizados(norm, ancho, alto, t0 if t is None else t)

    def cerrar(self):
        try:
            self._malla.close()
        except Exception:  # noqa: BLE001
            pass


class DetectorFalso:
    """Misma interfaz que ``Detector``, sin mediapipe.

    ``fuente(t) -> puntos (N, 3) en píxeles | None`` (por ejemplo, el generador de caras
    sintéticas de pruebas/sintetico). La imagen se ignora salvo para saber su tamaño.
    """

    def __init__(self, fuente, ancho: int = 640, alto: int = 480):
        self.fuente = fuente
        self.ancho, self.alto = int(ancho), int(alto)
        self.ms_ultimo = 0.0
        self.t_fin = 0.0
        self.llamadas = 0

    def procesar(self, imagen_bgr=None, t: float | None = None) -> CaraDetectada | None:
        self.llamadas += 1
        t = time.perf_counter() if t is None else t
        ancho, alto = self.ancho, self.alto
        if imagen_bgr is not None and getattr(imagen_bgr, "ndim", 0) >= 2:
            alto, ancho = imagen_bgr.shape[:2]
        puntos = self.fuente(t)
        self.t_fin = t
        if puntos is None:
            return None
        return CaraDetectada.desde_pixeles(puntos, ancho, alto, t)

    def cerrar(self):
        pass
