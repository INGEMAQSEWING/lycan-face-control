"""Pruebas CON mediapipe (marca ``mediapipe``; se saltan si no está instalado). Sin cámara: usan la
cara dibujada con OpenCV. Cargan mediapipe una sola vez para todo el archivo."""
import numpy as np
import pytest

pytestmark = pytest.mark.mediapipe


@pytest.fixture(scope="module")
def detector_fijo():
    from lycan_face_control.detector import Detector
    d = Detector(imagen_fija=True, deteccion=0.3)
    yield d
    d.cerrar()


def test_check_sale_con_cero():
    """``--check`` completo, en este mismo proceso (sin cámara ni ratón)."""
    from lycan_face_control.app import check
    assert check(verbose=False) == 0


def test_imagen_negra_sin_cara(detector_fijo):
    assert detector_fijo.procesar(np.zeros((480, 640, 3), np.uint8), t=1.0) is None


def test_cara_dibujada_medidas_coherentes(detector_fijo):
    """La cara dibujada produce medidas coherentes y reacciona a boca, ojos y cejas
    (como herramientas/verificar_medidas.py)."""
    from lycan_face_control.autoprueba import cara_dibujada
    from lycan_face_control.cara import medir, puntos_validos
    base = detector_fijo.procesar(cara_dibujada(), t=2.0)
    assert base is not None and base.puntos.shape == (478, 3) and base.t == 2.0
    assert puntos_validos(base.puntos, base.ancho, base.alto)
    mb = medir(base.puntos)
    # parecida a la cara de referencia guardada en pruebas/datos
    assert mb.ear_der == pytest.approx(0.357, abs=0.03)
    assert mb.mar == pytest.approx(0.016, abs=0.02)
    assert mb.cejas == pytest.approx(0.356, abs=0.03)
    boca = medir(detector_fijo.procesar(cara_dibujada(boca=28)).puntos)
    assert boca.mar > mb.mar + 0.1
    ojos = medir(detector_fijo.procesar(cara_dibujada(ojo=1)).puntos)
    assert ojos.ear_der < mb.ear_der * 0.8 and ojos.ear_izq < mb.ear_izq * 0.8
    cejas = medir(detector_fijo.procesar(cara_dibujada(ceja=12)).puntos)
    assert cejas.cejas > mb.cejas * 1.03
