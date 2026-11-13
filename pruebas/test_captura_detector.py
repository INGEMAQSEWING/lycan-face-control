"""Cámara falsa, detector falso y CaraDetectada (sin cámara real y sin mediapipe)."""
import sys

import numpy as np

from lycan_face_control import captura
from lycan_face_control.captura import CamaraFalsa, Camara
from lycan_face_control.cara import medir_si_valida
from lycan_face_control.detector import CaraDetectada, DetectorFalso
from sintetico import cara, linea_de_tiempo
from sintetico.cara_sintetica import FuenteSecuencia


class Reloj:
    def __init__(self, t=0.0):
        self.t = t

    def __call__(self):
        return self.t


def test_camara_falsa_entrega_cuadros_negros_numerados():
    reloj = Reloj(10.0)
    cam = CamaraFalsa(reloj=reloj, tiempo_real=False)
    assert cam.ultimo() is None                 # antes de iniciar no hay cuadros
    cam.start()
    assert cam.is_alive() and cam.estado == captura.FUNCIONANDO
    c1 = cam.ultimo()
    reloj.t = 10.05
    c2 = cam.ultimo()
    assert c1.imagen.shape == (480, 640, 3) and c1.imagen.dtype == np.uint8
    assert not c1.imagen.any()
    assert (c1.numero, c2.numero) == (1, 2)
    assert c1.t_captura == 10.0 and c2.t_captura == 10.05
    cam.detener()
    cam.join()
    assert cam.ultimo() is None and not cam.is_alive()
    assert cam.estado == captura.DETENIDA


def test_camara_falsa_con_generador():
    img = np.full((240, 320, 3), 7, np.uint8)
    cam = CamaraFalsa(generador=lambda t: img if t > 1 else None, ancho=320, alto=240,
                      reloj=Reloj(2.0), tiempo_real=False)
    cam.iniciar()
    assert cam.ultimo().imagen is img


def test_camara_falsa_en_tiempo_real_respeta_los_fps():
    import time
    cam = CamaraFalsa(fps=50, tiempo_real=True)
    cam.start()
    t0 = time.perf_counter()
    numeros = []
    while time.perf_counter() - t0 < 0.2:
        c = cam.ultimo(espera=0.05)
        if c:
            numeros.append(c.numero)
    cam.detener()
    assert 5 <= len(numeros) <= 12          # ~10 cuadros en 0,2 s a 50 por segundo
    assert numeros == sorted(numeros)


def test_camara_real_no_se_abre_al_crearla():
    # crear el objeto no abre la cámara (solo run() la abre); aquí nunca se llama start()
    cam = Camara(indice=0, espejo=False)
    assert cam.estado == captura.ABRIENDO and cam.cap is None and cam.espejo is False
    assert cam.ultimo(espera=0.0) is None


def test_cara_detectada_conversiones():
    P = cara()
    c = CaraDetectada.desde_pixeles(P, 640, 480, 3.0)
    np.testing.assert_allclose(c.normalizados[:, 0], P[:, 0] / 640)
    np.testing.assert_allclose(c.normalizados[:, 1], P[:, 1] / 480)
    np.testing.assert_allclose(c.normalizados[:, 2], P[:, 2] / 640)
    c2 = CaraDetectada.desde_normalizados(c.normalizados, 640, 480, 3.0)
    np.testing.assert_allclose(c2.puntos, P)
    assert c2.t == 3.0 and c2.ancho == 640


def test_detector_falso_con_secuencia_y_camara_falsa():
    cuadros = linea_de_tiempo([(0.0, {}), (0.5, {"boca": 1.0}), (0.6, None), (1.0, None)], fps=30)
    det = DetectorFalso(FuenteSecuencia(cuadros))
    reloj = Reloj(0.0)
    cam = CamaraFalsa(reloj=reloj, tiempo_real=False)
    cam.start()
    vistos = []
    for k in range(30):
        reloj.t = k / 30
        c = cam.ultimo()
        r = det.procesar(c.imagen, c.t_captura)
        vistos.append(r)
    assert vistos[0] is not None and vistos[-1] is None
    m0 = medir_si_valida(vistos[0].puntos, vistos[0].ancho, vistos[0].alto)
    m15 = medir_si_valida(vistos[15].puntos, 640, 480)
    assert m0.mar < 0.05 and m15.mar > 0.5
    assert vistos[0].t == 0.0
    assert det.llamadas == 30
    cam.detener()


def test_detector_falso_sin_imagen():
    det = DetectorFalso(lambda t: cara(), ancho=800, alto=600)
    r = det.procesar(None, 1.0)
    assert r.ancho == 800 and r.alto == 600
    det.cerrar()


def test_las_pruebas_no_cargan_mediapipe_ni_cv2_por_importar():
    """Importar la lógica, el detector, la captura y la salida no carga mediapipe, cv2 ni
    tkinter (se revisa en un proceso aparte porque otra prueba marcada puede haberlos cargado)."""
    import subprocess
    codigo = ("import sys; sys.path.insert(0, r'%s');"
              "import lycan_face_control.cara, lycan_face_control.detector, lycan_face_control.captura,"
              "lycan_face_control.config, lycan_face_control.salida, lycan_face_control.acciones;"
              "print('mediapipe' in sys.modules, 'cv2' in sys.modules, 'tkinter' in sys.modules)")
    from pathlib import Path
    raiz = str(Path(__file__).resolve().parents[1])
    r = subprocess.run([sys.executable, "-c", codigo % raiz], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    assert r.stdout.split() == ["False", "False", "False"]
