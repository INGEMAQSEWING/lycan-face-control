# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller: Lycan Face Control (modo carpeta, "one-dir").

Compilar (desde la raiz del proyecto; SOLO en GitHub Actions, no en el portatil de 8 GB):
    python -m PyInstaller empaquetado\lycan-face-control.spec --noconfirm
Resultado:
    dist\LycanFaceControl\LycanFaceControl.exe  (+ carpeta _internal)

Copiado del de Lycan Mouse Control (probado 2026-11-12 con mediapipe 0.10.14,
opencv-python-headless 4.10.0.84, numpy 2.2.6, PyInstaller 6.22.3, Python 3.10).
Cambia: los modelos de mediapipe son los de la CARA (face_mesh), no los de la mano.

Por que NO "onefile": cada arranque descomprimiria ~200 MB en %TEMP%
(5-15 s en un portatil de 8 GB) y los antivirus marcan mas a menudo los
.exe que se auto-extraen. El instalador Inno Setup ya entrega un solo archivo.

La voz NO necesita nada extra: es SAPI 5 por ctypes (ole32 y las voces son de
Windows) y el respaldo es powershell.exe (System.Speech), que trae Windows.
"""
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files

ROOT = Path(SPECPATH).resolve().parent          # raiz del proyecto
ENTRADA = str(ROOT / 'lanzar.py')               # from lycan_face_control.app import main; main()
ICONO = ROOT / 'recursos' / 'lycan-face.ico'

# ── Modelos de mediapipe ─────────────────────────────────────────────────────
# mp.solutions.face_mesh (refine_landmarks=True) usa:
#   modules/face_landmark/face_landmark_front_cpu.binarypb   (el grafo)
#   modules/face_landmark/face_landmark_with_attention.tflite (478 puntos, con iris)
#   modules/face_landmark/face_landmark.tflite               (468 puntos, sin refinar)
#   modules/face_detection/face_detection_short_range.tflite (encontrar la cara)
# Sin esto el .exe falla con
# "ValueError: The path does not exist: ...face_landmark_front_cpu.binarypb".
# (Equivale a --collect-data mediapipe pero sin los modelos de mano, pose, selfie...)
datas = collect_data_files(
    'mediapipe',
    includes=['modules/face_landmark/*', 'modules/face_detection/*'],
)
# Recursos propios: icono, lista de palabras (palabras_es.txt) y sonidos opcionales.
# config.ruta_recurso() los busca en sys._MEIPASS/recursos.
datas.append((str(ROOT / 'recursos'), 'recursos'))

# Todos los modulos propios (la interfaz y el teclado se importan dentro de funciones).
# Se listan leyendo las carpetas (sin importar nada al compilar).
PAQ = ROOT / 'lycan_face_control'
ocultos = sorted(
    '.'.join(('lycan_face_control',) + p.relative_to(PAQ).with_suffix('').parts).removesuffix('.__init__')
    for p in PAQ.rglob('*.py') if '__pycache__' not in p.parts and p.name != '__main__.py'
)

a = Analysis(
    [ENTRADA],
    pathex=[str(ROOT)],
    datas=datas,
    hiddenimports=ocultos,
    runtime_hooks=[str(Path(SPECPATH) / 'rthook_sin_matplotlib.py')],
    # mediapipe 0.10.14 pide jax, jaxlib, matplotlib y sounddevice como
    # dependencias, pero mp.solutions.face_mesh no los usa. OJO: NO excluir
    # 'mediapipe.tasks': mediapipe/__init__.py lo importa siempre
    # ("ModuleNotFoundError: No module named 'mediapipe.tasks'").
    excludes=[
        'jax', 'jaxlib', 'matplotlib', 'sounddevice', 'scipy', 'pandas',
        'IPython', 'PyQt5', 'PyQt6', 'PySide2', 'PySide6', 'tensorflow',
        'torch', 'mediapipe.model_maker', 'pytest',
    ],
    noarchive=False,
)

# opencv: la DLL de ffmpeg (~30 MB) solo sirve para leer/grabar ARCHIVOS de
# video; la camara usa MSMF/DirectShow, que vienen dentro de cv2.pyd.
a.binaries = [b for b in a.binaries if 'opencv_videoio_ffmpeg' not in b[0].lower()]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='LycanFaceControl',
    console=False,              # sin ventana negra. sys.stdout/stderr = None:
                                # el registro va a %APPDATA%\Lycan Face Control.
    upx=False,                  # UPX dispara falsos positivos de antivirus.
    icon=str(ICONO) if ICONO.exists() else None,
    version=str(Path(SPECPATH) / 'version_info.txt'),
    # "DPI aware": app.py llama a sistema.dpi.activar() antes de importar tkinter.
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    upx=False,
    name='LycanFaceControl',
)
