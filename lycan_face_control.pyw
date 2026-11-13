"""Doble clic aquí para abrir Lycan Face Control sin ventana negra (usa pythonw).

También es el lanzador de "Abrir al encender el computador" en modo código fuente (HKCU\Run).
Equivale a:  py -3.10 -m lycan_face_control
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lycan_face_control.app import main  # noqa: E402

if __name__ == "__main__":
    main()
