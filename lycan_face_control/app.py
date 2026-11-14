"""Arranque y cierre seguro de Lycan Face Control (sección 3.1).

Orden obligatorio: DPI en la primera línea (antes de tkinter) -> registro -> argumentos ->
mutex -> configuración -> salida + atexit + señales -> hilos -> interfaz. Todo dentro de
try/finally: el finally suelta todo, detiene los hilos y libera la cámara.

Parte 1: argumentos y ``--check`` (sin cámara ni ratón). Parte 3: el programa completo (ventanas,
hilos, motor y atajos) está en ``ui/aplicacion.py`` y se abre con ``_arrancar``.
"""
from __future__ import annotations

import sys

from .sistema import dpi as _dpi

_NIVEL_DPI = _dpi.activar()   # PRIMERO: antes de importar tkinter o leer medidas de pantalla

import argparse  # noqa: E402
import logging  # noqa: E402
import time  # noqa: E402

from . import constantes as K  # noqa: E402
from . import registro  # noqa: E402
from .version import VERSION  # noqa: E402

log = logging.getLogger("lycan")


def argumentos(argv=None):
    p = argparse.ArgumentParser(prog="lycan_face_control",
                                description="Lycan Face Control: maneje el computador con la cabeza y la cara.")
    p.add_argument("--check", action="store_true",
                   help="Comprueba que el programa y la detección de la cara cargan (sin cámara ni ratón) y sale.")
    p.add_argument("--minimizado", action="store_true", help="Arranca con la ventana pequeña.")
    p.add_argument("--simular", action="store_true",
                   help="Modo ensayo: no mueve el ratón real ni escribe nada en Windows.")
    p.add_argument("--camara-falsa", action="store_true",
                   help="Usa una cámara falsa (imagen negra) en vez de la cámara real.")
    p.add_argument("--prueba-segundos", type=float, default=0.0,
                   help="Cierra solo después de N segundos (pruebas).")
    p.add_argument("--camara", type=int, default=None, help="Número de cámara (0, 1, ...).")
    p.add_argument("--sin-atajos", action="store_true", help="No registra los atajos globales.")
    p.add_argument("--version", action="version", version=f"{K.NOMBRE_APP} {VERSION}")
    return p.parse_args(argv)


def _comprobar_voz() -> str:
    """Lista las voces de Windows sin hablar. Si no hay voz (o el módulo aún no existe) solo se
    anota: el programa igual sirve (el texto se muestra en grande)."""
    try:
        from .sistema import voz  # Parte 4
    except ImportError:
        return "módulo de voz no disponible"
    try:
        listar = getattr(voz, "listar_voces", None)
        if listar is None:
            return "módulo de voz sin listar_voces"
        voces = listar()
        return f"{len(voces)} voces" if voces else "sin voces"
    except Exception as e:  # noqa: BLE001
        return f"no se pudieron listar las voces: {e}"


def check(verbose: bool = True) -> int:
    """Autoprueba de la instalación. No abre la cámara ni mueve el ratón. 0 = bien, 1 = falla.

    1. Configuración de fábrica válida y lista de palabras presente.
    2. MediaPipe FaceMesh en modo video procesa una imagen negra 640x480 (sin cara).
    3. FaceMesh reconoce la cara dibujada de ``autoprueba`` (478 puntos) y las medidas salen
       coherentes: esto prueba que los modelos de la cara vienen en el paquete.
    4. Voz: se listan las voces sin hablar (solo se anota).
    """
    def decir(texto):
        log.info("--check: %s", texto)
        if verbose:
            try:
                print(texto)
            except Exception:  # noqa: BLE001
                pass

    try:
        import numpy as np

        from .cara import medir, puntos_validos
        from .config import FABRICA, ruta_recurso, validar
        from .detector import Detector

        problemas: list = []
        validar(FABRICA, problemas=problemas)
        if problemas:
            raise RuntimeError(f"la configuración de fábrica no es válida: {problemas}")
        palabras = ruta_recurso("palabras_es.txt")
        if not palabras.exists():
            raise RuntimeError(f"falta la lista de palabras: {palabras}")
        decir("Configuración y recursos: bien")

        t0 = time.perf_counter()
        d = Detector()
        try:
            cara = d.procesar(np.zeros((480, 640, 3), np.uint8))
        finally:
            d.cerrar()
        decir(f"Detección en modo video: bien ({(time.perf_counter() - t0) * 1000:.0f} ms al cargar; "
              f"imagen negra: {'sin cara' if cara is None else 'cara'})")

        from .autoprueba import cara_dibujada
        d = Detector(imagen_fija=True, deteccion=0.3)
        try:
            cara = d.procesar(cara_dibujada())
        finally:
            d.cerrar()
        if cara is None or len(cara.puntos) != K.N_PUNTOS:
            raise RuntimeError("no se reconoció la cara de prueba (¿faltan los modelos de la cara?)")
        if not puntos_validos(cara.puntos, cara.ancho, cara.alto):
            raise RuntimeError("la cara de prueba dio puntos inválidos")
        m = medir(cara.puntos)
        if not (0.2 < m.ear_der < 0.6 and 0.2 < m.ear_izq < 0.6 and m.mar < 0.2 and 0.3 < m.pitch_n < 0.8):
            raise RuntimeError(f"medidas fuera de lo esperado: {m}")
        decir(f"Cara de prueba: {len(cara.puntos)} puntos, ojos {m.ear_der:.2f}/{m.ear_izq:.2f}, "
              f"boca {m.mar:.3f}")

        decir(f"Voz: {_comprobar_voz()}")
        # 1.1 paquete B: el sonido de la alarma de AYUDA se arma en memoria (aquí no suena)
        from .sistema.alarma import generar_wav
        if len(generar_wav(100)) < 1000:
            raise RuntimeError("no se pudo armar el sonido de la alarma de AYUDA")
        decir("Alarma de AYUDA: bien (en esta prueba no suena)")
        decir("--check correcto")
        return 0
    except Exception as e:  # noqa: BLE001
        log.exception("--check falló")
        if verbose:
            try:
                print(f"--check falló: {e}")
            except Exception:  # noqa: BLE001
                pass
        return 1


def _arrancar(args) -> int:
    """Abre el programa completo. Lo completan las Partes 2 (motor) y 3 (interfaz)."""
    try:
        from .ui import aplicacion  # Parte 3
    except ImportError:
        log.error("La interfaz todavía no está construida (Parte 3).")
        try:
            print("La interfaz todavía no está construida. Use --check para probar la instalación.")
        except Exception:  # noqa: BLE001
            pass
        return 1
    return aplicacion.correr(args)


def main(argv=None):
    registro.proteger_salida_estandar()
    args = argumentos(argv)
    registro.configurar()
    if args.check:
        registro.anotar_inicio({"modo": "--check", "DPI": _NIVEL_DPI})
        sys.exit(check())
    registro.anotar_inicio({"DPI": _NIVEL_DPI, "Simular": args.simular, "Cámara falsa": args.camara_falsa})
    sys.exit(_arrancar(args))


if __name__ == "__main__":
    main()
