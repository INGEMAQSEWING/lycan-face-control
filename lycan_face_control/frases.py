"""Frases rápidas por categoría, editables y validadas (sección 7.4). Lógica pura salvo leer y
guardar ``frases.json`` en la carpeta de datos.

Formato del archivo::

    {"version": 1,
     "categorias": [{"nombre": "Necesidades",
                     "frases": [{"texto": "Tengo sed", "urgente": false}, ...]}, ...]}

- Texto de 1 a 200 caracteres; máximo 12 categorías y 40 frases por categoría; nombre de
  categoría de 1 a 40 caracteres.
- ``{cuidador}`` se reemplaza por el nombre configurado (por defecto "alguien").
- Variante de género: ``{masculino|femenino}`` o ``{masculino|femenino|neutro}``. Con "neutro"
  se usa la tercera forma si existe; si no, la primera.
- La primera categoría ("Rápidas") llena la fila rápida del teclado, junto a Sí y No.
- Si el archivo se daña se aparta con otro nombre y se usan las frases de fábrica.
"""
from __future__ import annotations

import copy
import json
import logging
import re
from pathlib import Path

from .prediccion import _apartar, escribir_json, leer_con_reintentos

log = logging.getLogger("lycan")

VERSION_ARCHIVO = 1
MAX_CATEGORIAS = 12
MAX_FRASES = 40
MAX_TEXTO = 200
MAX_NOMBRE = 40
GENEROS = ("neutro", "masculino", "femenino")


def _f(texto: str, urgente: bool = False) -> dict:
    return {"texto": texto, "urgente": urgente}


FABRICA: dict = {
    "version": VERSION_ARCHIVO,
    "categorias": [
        {"nombre": "Rápidas", "frases": [
            # la urgencia va en la fila rápida: en barrido queda a pocos segundos (no a más de 40)
            _f("¡Ayuda, llamen a alguien!", True), _f("Tengo sed"), _f("Tengo dolor"),
            _f("Cambiarme de posición"), _f("Llamar a {cuidador}")]},
        {"nombre": "Básicas", "frases": [
            _f("Sí"), _f("No"), _f("No sé"), _f("Espere, estoy escribiendo"), _f("Gracias"), _f("Por favor"),
            _f("Otra vez"), _f("Ya está bien")]},
        {"nombre": "Necesidades", "frases": [
            _f("Tengo sed"), _f("Tengo hambre"), _f("Necesito ir al baño"), _f("Cambiarme de posición"),
            _f("Tengo calor"), _f("Tengo frío"), _f("Me pica"), _f("Acomódeme la cabeza"),
            _f("Límpieme la boca"), _f("Necesito que me aspiren"), _f("Ajústeme la máscara"),
            _f("Quiero descansar"), _f("Prenda o apague la luz"), _f("Súbale o bájele al televisor")]},
        {"nombre": "Dolor", "frases": [
            _f("Tengo dolor"), _f("Me duele la cabeza"), _f("Me duele el pecho"), _f("Me duele el estómago"),
            _f("Me duele la espalda"), _f("Me duelen las piernas"), _f("Me duelen los brazos"), _f("Es fuerte"),
            _f("Es leve")]},
        {"nombre": "Urgencia", "frases": [
            _f("¡Ayuda, llamen a alguien!", True), _f("Llamar a {cuidador}"), _f("Me falta el aire", True),
            _f("Llamen al médico", True)]},
        {"nombre": "Afecto", "frases": [
            _f("Te quiero"), _f("Estoy bien"), _f("{Estoy cansado|Estoy cansada|Siento cansancio}"),
            _f("Tengo miedo"), _f("Me alegra verte"),
            _f("{Quiero estar solo un rato|Quiero estar sola un rato|Quiero estar a solas un rato}"),
            _f("Gracias por cuidarme"), _f("No entiendo, repítalo")]},
    ],
}

_GRUPO = re.compile(r"\{([^{}|]*(?:\|[^{}|]*){1,2})\}")


def aplicar_genero(texto: str, genero: str = "neutro") -> str:
    def cambiar(m):
        partes = m.group(1).split("|")
        if genero == "femenino" and len(partes) >= 2:
            return partes[1]
        if genero == "neutro" and len(partes) >= 3:
            return partes[2]
        return partes[0]
    return _GRUPO.sub(cambiar, texto)


def texto_final(texto: str, genero: str = "neutro", cuidador: str = "alguien") -> str:
    """El texto que se dice y se muestra: con el género elegido y el nombre del cuidador."""
    nombre = (cuidador or "").strip() or "alguien"
    return aplicar_genero(texto, genero).replace("{cuidador}", nombre)


def _texto_valido(v, largo: int) -> bool:
    return isinstance(v, str) and 0 < len(v.strip()) <= largo and "\n" not in v and "\r" not in v


def validar(datos, problemas: list | None = None) -> dict:
    """Devuelve unas frases válidas. Lo que no sirve se descarta y se anota en ``problemas``.
    Lanza ValueError si la estructura no se puede usar en absoluto."""
    problemas = [] if problemas is None else problemas
    if not isinstance(datos, dict) or not isinstance(datos.get("categorias"), list):
        raise ValueError("estructura equivocada")
    cats = []
    for i, c in enumerate(datos["categorias"]):
        if len(cats) >= MAX_CATEGORIAS:
            problemas.append(f"más de {MAX_CATEGORIAS} categorías")
            break
        if not isinstance(c, dict) or not _texto_valido(c.get("nombre"), MAX_NOMBRE) \
                or not isinstance(c.get("frases"), list):
            problemas.append(f"categoría {i}: no válida")
            continue
        frases = []
        for j, fr in enumerate(c["frases"]):
            if len(frases) >= MAX_FRASES:
                problemas.append(f"{c['nombre']}: más de {MAX_FRASES} frases")
                break
            if isinstance(fr, str):
                fr = {"texto": fr}
            if not isinstance(fr, dict) or not _texto_valido(fr.get("texto"), MAX_TEXTO):
                problemas.append(f"{c['nombre']} frase {j}: no válida")
                continue
            urg = fr.get("urgente", False)
            frases.append({"texto": fr["texto"].strip(), "urgente": urg if isinstance(urg, bool) else False})
        cats.append({"nombre": c["nombre"].strip(), "frases": frases})
    if not cats:
        raise ValueError("sin categorías")
    return {"version": VERSION_ARCHIVO, "categorias": cats}


def ruta_frases() -> Path:
    from .config import carpeta_datos
    return carpeta_datos() / "frases.json"


class Frases:
    """Frases rápidas con su archivo. Los métodos de edición devuelven True si se pudo."""

    def __init__(self, ruta: Path | None = None):
        self.ruta = Path(ruta) if ruta else None
        self.datos: dict = copy.deepcopy(FABRICA)
        self.aviso: str | None = None
        self.problemas: list[str] = []
        self.solo_lectura = False          # no se pudo leer el archivo: no se escribe encima

    # ------------------------------------------------------------ archivo
    def cargar(self) -> dict:
        self.aviso = None
        self.problemas = []
        r = self.ruta
        if r is None or not r.exists():
            self.datos = copy.deepcopy(FABRICA)
            return self.datos
        try:
            crudo = json.loads(leer_con_reintentos(r))
            self.datos = validar(crudo, self.problemas)
            self.solo_lectura = False
        except (ValueError, UnicodeDecodeError, RecursionError, MemoryError, TypeError) as e:
            log.warning("Frases dañadas (%s); se usan las de fábrica.", type(e).__name__)
            self.aviso = "frases_danadas"
            _apartar(r)
            self.datos = copy.deepcopy(FABRICA)
        except FileNotFoundError:
            self.datos = copy.deepcopy(FABRICA)
        except OSError as e:
            log.warning("No se pudieron leer las frases (%s): en esta sesión no se escribe encima.", e)
            self.datos = copy.deepcopy(FABRICA)
            self.solo_lectura = True
            self.aviso = "frases_no_leidas"
        for p in self.problemas:
            log.warning("Frases: %s (se descartó)", p)
        return self.datos

    def guardar(self) -> bool:
        if self.ruta is None:
            return True
        if self.solo_lectura:
            log.warning("Las frases no se guardan: al abrir no se pudo leer el archivo")
            return False
        try:
            self.datos = validar(self.datos)
            escribir_json(self.ruta, self.datos)
            return True
        except (OSError, ValueError) as e:
            log.warning("No se pudieron guardar las frases: %s", e)
            return False

    def restaurar(self):
        self.datos = copy.deepcopy(FABRICA)

    # ------------------------------------------------------------ consultas
    @property
    def categorias(self) -> list[dict]:
        return self.datos["categorias"]

    def nombres(self) -> list[str]:
        return [c["nombre"] for c in self.categorias]

    def frases(self, cat: int) -> list[dict]:
        if 0 <= cat < len(self.categorias):
            return self.categorias[cat]["frases"]
        return []

    def rapidas(self, n: int = 5) -> list[dict]:
        """Las frases de la fila rápida (primera categoría), sin repetir Sí ni No."""
        if not self.categorias:
            return []
        out = [f for f in self.categorias[0]["frases"] if f["texto"].strip().lower() not in ("sí", "si", "no")]
        return out[:n]

    # ------------------------------------------------------------ edición
    def agregar(self, cat: int, texto: str, urgente: bool = False) -> bool:
        fr = self.frases(cat)
        if not (0 <= cat < len(self.categorias)) or len(fr) >= MAX_FRASES or not _texto_valido(texto, MAX_TEXTO):
            return False
        fr.append({"texto": texto.strip(), "urgente": bool(urgente)})
        return True

    def cambiar(self, cat: int, i: int, texto: str, urgente: bool | None = None) -> bool:
        fr = self.frases(cat)
        if not (0 <= i < len(fr)) or not _texto_valido(texto, MAX_TEXTO):
            return False
        fr[i]["texto"] = texto.strip()
        if urgente is not None:
            fr[i]["urgente"] = bool(urgente)
        return True

    def borrar(self, cat: int, i: int) -> bool:
        fr = self.frases(cat)
        if not (0 <= i < len(fr)):
            return False
        del fr[i]
        return True

    def mover(self, cat: int, i: int, delta: int) -> int:
        """Mueve una frase arriba (−1) o abajo (+1). Devuelve su nueva posición."""
        fr = self.frases(cat)
        j = i + delta
        if not (0 <= i < len(fr)) or not (0 <= j < len(fr)):
            return i
        fr[i], fr[j] = fr[j], fr[i]
        return j

    def agregar_categoria(self, nombre: str) -> bool:
        if len(self.categorias) >= MAX_CATEGORIAS or not _texto_valido(nombre, MAX_NOMBRE):
            return False
        self.categorias.append({"nombre": nombre.strip(), "frases": []})
        return True

    def renombrar_categoria(self, cat: int, nombre: str) -> bool:
        if not (0 <= cat < len(self.categorias)) or not _texto_valido(nombre, MAX_NOMBRE):
            return False
        self.categorias[cat]["nombre"] = nombre.strip()
        return True

    def borrar_categoria(self, cat: int) -> bool:
        if not (0 <= cat < len(self.categorias)) or len(self.categorias) <= 1:
            return False                   # siempre queda al menos una categoría
        del self.categorias[cat]
        return True
