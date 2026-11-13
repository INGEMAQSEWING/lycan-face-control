"""Verifica (SIN cámara) que mediapipe face_mesh y los índices de las medidas funcionan.

Dibuja una cara sencilla con OpenCV (herramientas/cara_dibujada.py), la pasa por FaceMesh
(refine_landmarks=True) e imprime las medidas. Con --guardar escribe los 478 puntos de la cara
base en pruebas/datos/cara_dibujada_base.json para que las pruebas no necesiten mediapipe.

Uso:  py -3.10 herramientas/verificar_medidas.py [--guardar]
"""
import json, os, sys
import cv2
import numpy as np
sys.path.insert(0, os.path.dirname(__file__))
from cara_dibujada import cara  # noqa: E402
import mediapipe as mp  # noqa: E402

OJO_DER = [33, 160, 158, 133, 153, 144]   # ojo derecho de la persona (lado izquierdo de la imagen)
OJO_IZQ = [362, 385, 387, 263, 373, 380]  # ojo izquierdo de la persona


def puntos(img, fm):
    h, w = img.shape[:2]
    r = fm.process(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    if not r.multi_face_landmarks:
        return None
    lm = r.multi_face_landmarks[0].landmark
    # x, y en píxeles; z en la misma escala que x (mediapipe la da relativa al ancho)
    return np.array([[p.x * w, p.y * h, p.z * w] for p in lm]), [[p.x, p.y, p.z] for p in lm]


CEJA_DER = [70, 63, 105, 66, 107]
CEJA_IZQ = [300, 293, 334, 296, 336]


def ceja(P, io):
    """Distancia media ceja -> centro de las comisuras del ojo (33-133 / 362-263), / io.
    Se usa el centro de las comisuras (no el párpado 159) porque el párpado baja al cerrar el ojo."""
    def lado(cj, a, b):
        m = (P[a] + P[b]) / 2
        return float(np.mean([np.linalg.norm(P[i] - m) for i in cj]))
    return (lado(CEJA_DER, 33, 133) + lado(CEJA_IZQ, 362, 263)) / 2 / io


def medidas(P):
    d = lambda a, b: float(np.linalg.norm(P[a] - P[b]))
    io = d(33, 263)
    ear = lambda o: (d(o[1], o[5]) + d(o[2], o[4])) / (2 * d(o[0], o[3]))
    ojos = (P[33] + P[263]) / 2
    boca = (P[61] + P[291]) / 2
    ex = (P[263] - P[33])[:2]; ex /= np.linalg.norm(ex)
    ey = np.array([-ex[1], ex[0]])
    v = (P[1] - ojos)[:2]
    return {
        "puntos": len(P), "io_px": round(io, 1),
        "ear_der": round(ear(OJO_DER), 3), "ear_izq": round(ear(OJO_IZQ), 3),
        "mar": round(d(13, 14) / d(78, 308), 3),
        "ceja": round(ceja(P, io), 3),
        "sonrisa": round(d(61, 291) / io, 3),
        "yaw_n": round(float(v @ ex) / io, 3),
        "pitch_n": round(float(v @ ey) / float((boca - ojos)[:2] @ ey), 3),
        "roll_grados": round(float(np.degrees(np.arctan2(ex[1], ex[0]))), 1),
    }


def main():
    fm = mp.solutions.face_mesh.FaceMesh(static_image_mode=True, refine_landmarks=True,
                                         max_num_faces=1, min_detection_confidence=0.3)
    try:
        for nombre, kw in [("base", {}), ("boca_abierta", {"boca": 28}),
                           ("ojos_cerrados", {"ojo": 1}), ("cejas_arriba", {"ceja": 12})]:
            res = puntos(cara(**kw), fm)
            print(nombre, medidas(res[0]) if res else "SIN CARA")
            if nombre == "base" and res and "--guardar" in sys.argv:
                ruta = os.path.join(os.path.dirname(__file__), "..", "pruebas", "datos", "cara_dibujada_base.json")
                with open(ruta, "w", encoding="utf-8") as f:
                    json.dump({"ancho": 640, "alto": 480, "nota": "x,y normalizados 0..1; z relativo al ancho",
                               "puntos": [[round(c, 5) for c in p] for p in res[1]]}, f)
                print("guardado", os.path.abspath(ruta))
    finally:
        fm.close()


if __name__ == "__main__":
    main()
