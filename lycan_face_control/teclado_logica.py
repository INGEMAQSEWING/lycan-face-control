"""Teclado en pantalla: distribuciones, tildes, mayúsculas, texto en armado y medidas de las teclas
(sección 7.1). Lógica pura: no importa tkinter ni Windows.

- ``distribucion(nombre)``: filas de teclas ("qwerty" o "frecuencia").
- ``Escritura``: el texto que la persona va armando, con tilde pendiente (``´`` y la vocal),
  diéresis (``´`` dos veces y la ``u``), mayúscula automática al empezar una frase, ``⇧`` para
  una sola mayúscula, borrar, borrar palabra, deshacer y elegir una sugerencia. Cada operación
  devuelve un ``Cambio`` (cuántos caracteres borrar y qué escribir) para el modo Directo.
- ``NUMEROS``: página de números y signos (0-9, @, -, /, :, $, %, +...) que se abre con la tecla
  ``123`` y se cierra con ``abc`` (ronda 2 de arreglos: sin ella no se podía escribir una hora,
  una dosis, un teléfono o un correo).
- ``disposicion(...)``: rectángulos de todas las filas (texto, frases rápidas, sugerencias,
  letras y acciones) dentro del área del teclado, sin solaparse y con teclas de 80 px o más.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field

MAX_TEXTO = 2000            # caracteres en armado (un mensaje largo cabe de sobra)
MAX_DESHACER = 100
TECLA_MIN_PX = 80
TECLA_MAX_PX = 112
SEPARACION = 8

TILDES = {"a": "á", "e": "é", "i": "í", "o": "ó", "u": "ú",
          "A": "Á", "E": "É", "I": "Í", "O": "Ó", "U": "Ú"}
DIERESIS = {"u": "ü", "U": "Ü"}
FIN_DE_FRASE = ".?!\n"
APERTURA = "¿¡\"(«"
PUNTUACION_PEGADA = ",.;:?!»)"      # va pegada a la palabra anterior (se quita el espacio automático)


@dataclass(frozen=True)
class Tecla:
    id: str                # "tecla:q", "tecla:espacio", "tecla:tilde"...
    valor: str             # lo que escribe ("" para las teclas especiales)
    tipo: str              # letra | signo | espacio | tilde | enter | mayus
    ancho: int = 1         # en unidades de tecla
    etiqueta: str = ""     # lo que se ve (si no, el valor en mayúscula)

    @property
    def texto(self) -> str:
        return self.etiqueta or self.valor.upper()


def _letra(c: str) -> Tecla:
    return Tecla(f"tecla:{c}", c, "letra")


def _signo(c: str) -> Tecla:
    return Tecla(f"tecla:{c}", c, "signo", etiqueta=c)


ESPACIO = Tecla("tecla:espacio", " ", "espacio", 4, "Espacio")
ESPACIO_CORTO = Tecla("tecla:espacio", " ", "espacio", 1, "␣")
TILDE = Tecla("tecla:tilde", "", "tilde", 1, "´")
ENTER = Tecla("tecla:enter", "\n", "enter", 1, "↵")
MAYUS = Tecla("tecla:mayus", "", "mayus", 1, "⇧")
NUMEROS_TECLA = Tecla("tecla:numeros", "", "pagina", 1, "123")
LETRAS_TECLA = Tecla("tecla:letras", "", "pagina", 2, "abc")


def _fila(cadena: str) -> list[Tecla]:
    out = []
    for c in cadena.split():
        if c == "´":
            out.append(TILDE)
        elif c == "␣":
            out.append(ESPACIO_CORTO)
        elif c.isalpha():
            out.append(_letra(c.lower()))
        else:
            out.append(_signo(c))
    return out


DISTRIBUCIONES = {
    # QWERTY español (por defecto con permanencia)
    "qwerty": [
        _fila("q w e r t y u i o p"),
        _fila("a s d f g h j k l ñ"),
        _fila("z x c v b n m , . ´"),
        [MAYUS, NUMEROS_TECLA] + _fila("¿ ? ¡ !") + [ESPACIO, ENTER],
    ],
    # Las letras más usadas del español primero (por defecto con barrido). Los signos van al final
    # de cada fila (no en una quinta fila) para que el teclado quepa en 1366×768 con teclas de 80 px.
    "frecuencia": [
        _fila("␣ e a o s r n .") + [NUMEROS_TECLA],
        _fila("i d l c t u m ,"),
        _fila("p b g v y q h ¿ ?"),
        _fila("f z j ñ x k w ´ ¡ !"),
    ],
}

# Página de números y signos (mismas 4 filas que las letras: el teclado no cambia de tamaño)
NUMEROS = [
    _fila("1 2 3 4 5 6 7 8 9 0"),
    _fila("@ - / : $ % + = ( )"),
    _fila(". , ; ? ¿ ! ¡ \" * #"),
    [LETRAS_TECLA, ESPACIO, ENTER],
]


def nombre_distribucion(cfg_teclado: dict, barrido: bool) -> str:
    """"auto" = QWERTY con la cabeza y "frecuencia" con el barrido."""
    d = (cfg_teclado or {}).get("distribucion", "auto")
    if d in DISTRIBUCIONES:
        return d
    return "frecuencia" if barrido else "qwerty"


def distribucion(nombre: str) -> list[list[Tecla]]:
    return DISTRIBUCIONES.get(nombre, DISTRIBUCIONES["qwerty"])


def buscar_tecla(ident: str) -> Tecla | None:
    for filas in list(DISTRIBUCIONES.values()) + [NUMEROS]:
        for fila in filas:
            for t in fila:
                if t.id == ident:
                    return t
    return None


# --------------------------------------------------------------------------- texto
def sin_tildes(s: str) -> str:
    """'Sábana' -> 'sabana' (la ñ se conserva: no es una tilde)."""
    out = []
    for c in s.lower():
        if c == "ñ":
            out.append(c)
            continue
        d = unicodedata.normalize("NFD", c)
        out.append("".join(x for x in d if unicodedata.category(x) != "Mn"))
    return "".join(out)


def es_letra(c: str) -> bool:
    return c.isalpha()


@dataclass(frozen=True)
class Cambio:
    """Lo que hay que hacer en el programa activo para pasar del texto viejo al nuevo:
    borrar ``borrar`` caracteres al final y luego escribir ``texto``."""
    borrar: int = 0
    texto: str = ""

    @property
    def vacio(self) -> bool:
        return self.borrar == 0 and not self.texto


def diferencia(antes: str, despues: str) -> Cambio:
    p = 0
    n = min(len(antes), len(despues))
    while p < n and antes[p] == despues[p]:
        p += 1
    return Cambio(len(antes) - p, despues[p:])


@dataclass
class _Estado:
    texto: str
    tilde: int
    mayus: bool
    espacio_auto: bool


@dataclass
class Escritura:
    texto: str = ""
    tilde: int = 0                 # 0 nada, 1 tilde pendiente, 2 diéresis pendiente
    mayus: bool = False            # ⇧: la siguiente letra en mayúscula
    mayuscula_auto: bool = True
    espacio_auto: bool = False     # el último espacio lo puso una sugerencia
    _deshacer: list = field(default_factory=list)

    # ------------------------------------------------------------ consultas
    def proxima_mayuscula(self, texto: str | None = None) -> bool:
        """True si la siguiente letra sale en mayúscula (⇧ o inicio de frase)."""
        if self.mayus:
            return True
        if not self.mayuscula_auto:
            return False
        antes = (self.texto if texto is None else texto).rstrip(" ")
        while antes and antes[-1] in APERTURA:
            antes = antes[:-1].rstrip(" ")
        return not antes or antes[-1] in FIN_DE_FRASE

    def palabra_actual(self) -> str:
        """Las letras al final del texto (la palabra que se está escribiendo)."""
        i = len(self.texto)
        while i > 0 and es_letra(self.texto[i - 1]):
            i -= 1
        return self.texto[i:]

    def palabra_anterior(self) -> str | None:
        """La última palabra terminada (para predecir la siguiente). None al empezar una frase.
        Los signos que van pegados a la palabra (coma, punto y coma...) se saltan: después de
        "Hola, " la palabra anterior sigue siendo "Hola"."""
        cuerpo = self.texto[:len(self.texto) - len(self.palabra_actual())].rstrip(" ")
        if not cuerpo or cuerpo[-1] in FIN_DE_FRASE:
            return None
        while cuerpo and cuerpo[-1] in PUNTUACION_PEGADA and cuerpo[-1] not in FIN_DE_FRASE:
            cuerpo = cuerpo[:-1].rstrip(" ")
        if not cuerpo or cuerpo[-1] in FIN_DE_FRASE:
            return None
        i = len(cuerpo)
        while i > 0 and es_letra(cuerpo[i - 1]):
            i -= 1
        p = cuerpo[i:]
        return p or None

    # ------------------------------------------------------------ deshacer
    def _guardar(self):
        self._deshacer.append(_Estado(self.texto, self.tilde, self.mayus, self.espacio_auto))
        if len(self._deshacer) > MAX_DESHACER:
            del self._deshacer[0]

    def puede_deshacer(self) -> bool:
        return bool(self._deshacer)

    def deshacer(self) -> Cambio:
        if not self._deshacer:
            return Cambio()
        antes = self.texto
        e = self._deshacer.pop()
        self.texto, self.tilde, self.mayus, self.espacio_auto = e.texto, e.tilde, e.mayus, e.espacio_auto
        return diferencia(antes, self.texto)

    def _cambiar(self, nuevo: str) -> Cambio:
        antes = self.texto
        self.texto = nuevo[:MAX_TEXTO]
        return diferencia(antes, self.texto)

    # ------------------------------------------------------------ teclas
    def pulsar(self, tecla: Tecla) -> Cambio:
        if tecla.tipo == "tilde":
            self._guardar()
            self.tilde = 2 if self.tilde == 1 else 1
            return Cambio()
        if tecla.tipo == "mayus":
            self._guardar()
            self.mayus = not self.mayus
            return Cambio()
        if tecla.tipo == "pagina":
            return Cambio()                 # 123 / abc: solo cambia la página (la interfaz)
        if tecla.tipo == "espacio":
            return self.espacio()
        if tecla.tipo == "enter":
            return self.escribir_caracter("\n")
        return self.escribir_caracter(tecla.valor)

    def escribir_caracter(self, c: str) -> Cambio:
        if not c or len(self.texto) >= MAX_TEXTO:
            self.tilde = 0
            return Cambio()
        self._guardar()
        nuevo = self.texto
        if c.isalpha():
            if self.tilde == 1:
                c = TILDES.get(c, c)
            elif self.tilde == 2:
                c = DIERESIS.get(c, TILDES.get(c, c))
            if self.proxima_mayuscula():
                c = c.upper()
            self.mayus = False
        elif c in PUNTUACION_PEGADA and self.espacio_auto and nuevo.endswith(" "):
            nuevo = nuevo[:-1]                       # "hola ." -> "hola."
        self.tilde = 0
        self.espacio_auto = False
        return self._cambiar(nuevo + c)

    def espacio(self) -> Cambio:
        if len(self.texto) >= MAX_TEXTO:
            return Cambio()
        if self.espacio_auto and self.texto.endswith(" "):
            self.espacio_auto = False       # la sugerencia ya puso el espacio: no dos seguidos
            return Cambio()
        self._guardar()
        self.tilde = 0
        self.espacio_auto = False
        return self._cambiar(self.texto + " ")

    def borrar(self) -> Cambio:
        """Borra una letra. Si había una tilde o ⇧ pendiente, primero se cancela eso."""
        if self.tilde or self.mayus:
            self._guardar()
            self.tilde = 0
            self.mayus = False
            return Cambio()
        if not self.texto:
            return Cambio()
        self._guardar()
        self.espacio_auto = False
        t = self.texto
        # un emoji (par sustituto en Windows) o una letra con su marca combinada se borran enteros
        n = 1
        while n < len(t) and unicodedata.category(t[-n]) == "Mn":
            n += 1
        return self._cambiar(t[:-n])

    def borrar_palabra(self) -> Cambio:
        if not self.texto:
            self.tilde = 0
            return Cambio()
        self._guardar()
        self.tilde = 0
        self.espacio_auto = False
        t = self.texto.rstrip(" ")
        i = len(t)
        if i and not es_letra(t[i - 1]):
            i -= 1                                    # un signo suelto se borra solo
        else:
            while i > 0 and es_letra(t[i - 1]):
                i -= 1
        return self._cambiar(t[:i])

    def limpiar(self) -> Cambio:
        if not self.texto and not self.tilde and not self.mayus:
            return Cambio()
        self._guardar()
        self.tilde = 0
        self.mayus = False
        self.espacio_auto = False
        return self._cambiar("")

    def nuevo_mensaje(self):
        """Modo Directo, botón "Nuevo": lo escrito ya quedó en el otro programa. Se empieza vacío y
        SIN pasos de deshacer: deshacer no puede volver a mandar el mensaje anterior (quedaría
        duplicado allá)."""
        self.texto = ""
        self.tilde = 0
        self.mayus = False
        self.espacio_auto = False
        self._deshacer.clear()

    def poner_texto(self, nuevo: str) -> Cambio:
        self._guardar()
        self.tilde = 0
        self.espacio_auto = False
        return self._cambiar(nuevo)

    def elegir_sugerencia(self, palabra: str) -> Cambio:
        """Reemplaza la palabra en armado por ``palabra`` y agrega un espacio. Respeta la
        mayúscula inicial (la escrita o la del inicio de frase)."""
        if not palabra:
            return Cambio()
        actual = self.palabra_actual()
        base = self.texto[:len(self.texto) - len(actual)]
        if not actual and base and base[-1] in PUNTUACION_PEGADA:
            base += " "                     # "Hola." + "quiero" -> "Hola. Quiero"
        self._guardar()
        mayuscula = actual[:1].isupper() or self.proxima_mayuscula(base)
        if mayuscula:
            palabra = palabra[:1].upper() + palabra[1:]
        elif palabra[:1].isupper() and not _es_sigla(palabra):
            palabra = palabra[:1].lower() + palabra[1:]
        self.tilde = 0
        self.mayus = False
        cambio = self._cambiar(base + palabra + " ")
        self.espacio_auto = True
        return cambio


def _es_sigla(p: str) -> bool:
    return sum(1 for c in p if c.isupper()) >= 2        # "BiPAP"


# --------------------------------------------------------------------------- medidas
@dataclass(frozen=True)
class Caja:
    id: str
    x: int
    y: int
    ancho: int
    alto: int

    @property
    def rect(self) -> tuple[int, int, int, int]:
        return (self.x, self.y, self.x + self.ancho, self.y + self.alto)

    def se_solapa(self, otra: "Caja") -> bool:
        a, b = self.rect, otra.rect
        return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


ACCIONES = ("borrar", "palabra", "deshacer", "copiar", "limpiar", "frases", "barrido", "pausa", "ayuda", "cerrar")
ACCIONES_TEXTO = ("hablar", "repetir", "escribir")
N_SUGERENCIAS = 5
N_RAPIDAS = 5               # frases de la fila rápida además de Sí y No


@dataclass
class Disposicion:
    ancho: int
    alto: int
    tecla_alto: int
    filas: list = field(default_factory=list)     # [(nombre, [Caja, ...]), ...] en orden de arriba abajo

    def cajas(self) -> list[Caja]:
        return [c for _, fila in self.filas for c in fila]

    def fila(self, nombre: str) -> list[Caja]:
        for n, f in self.filas:
            if n == nombre:
                return f
        return []


def _repartir(ids_anchos: list[tuple[str, float]], x0: int, y: int, ancho: int, alto: int,
              sep: int = SEPARACION) -> list[Caja]:
    """Reparte el ancho entre las cajas según su peso (sin huecos acumulados por redondeo)."""
    total = sum(w for _, w in ids_anchos) or 1
    util = ancho - sep * (len(ids_anchos) - 1)
    out = []
    acum = 0.0
    x = x0
    for i, (ident, w) in enumerate(ids_anchos):
        acum += w
        fin = x0 + round(util * acum / total) + sep * i
        out.append(Caja(ident, x, y, max(fin - x, 1), alto))
        x = fin + sep
    return out


def disposicion(filas_teclas: list[list[Tecla]], ancho: int, alto_max: int, sep: int = SEPARACION,
                texto_alto: int | None = None, pagina: str = "letras", filas_cuerpo: list | None = None,
                acciones: tuple = ACCIONES, n_sugerencias: int = N_SUGERENCIAS,
                n_rapidas: int = N_RAPIDAS) -> Disposicion:
    """Medidas de todo el teclado dentro de ``ancho`` × ``alto_max`` píxeles.

    Filas, de arriba abajo:
      1. ``texto``: el texto en armado (ancho) + Hablar, Repetir y Escribir;
      2. ``rapidas``: Sí, No y las frases rápidas;
      3. ``sugerencias``: 5 palabras sugeridas;
      4. el cuerpo: filas de letras (``pagina="letras"``) o ``filas_cuerpo`` = [[(id, peso), ...], ...]
         (página de frases);
      5. ``acciones``.
    La altura de las teclas es la mayor que quepa entre 80 y 112 px. Si ni con 80 px cabe,
    se queda en 80 (la ventana crece; nunca se achican las teclas por debajo del mínimo)."""
    if pagina == "letras":
        cuerpo = [[(t.id, t.ancho) for t in fila] for fila in filas_teclas]
    else:
        cuerpo = filas_cuerpo or []
    n_filas = 3 + len(cuerpo) + 1               # texto, rápidas, sugerencias, cuerpo, acciones
    disponible = alto_max - sep * (n_filas + 1)
    h = int(disponible / n_filas)
    h = max(TECLA_MIN_PX, min(TECLA_MAX_PX, h))
    th = max(texto_alto or h, TECLA_MIN_PX)
    d = Disposicion(ancho=ancho, alto=0, tecla_alto=h)
    y = sep
    util = ancho - 2 * sep
    # 1. texto + botones grandes
    fila = _repartir([("texto", 6.0)] + [(f"accion:{a}", 1.4) for a in ACCIONES_TEXTO], sep, y, util, th, sep)
    d.filas.append(("texto", fila))
    y += th + sep
    # 2. Sí, No y frases rápidas (Sí y No más anchos y separados por las frases)
    ids = [("frase:si", 1.4)] + [(f"frase:rapida:{i}", 2.0) for i in range(n_rapidas)] + [("frase:no", 1.4)]
    d.filas.append(("rapidas", _repartir(ids, sep, y, util, h, sep)))
    y += h + sep
    # 3. sugerencias
    d.filas.append(("sugerencias",
                    _repartir([(f"sugerencia:{i}", 1.0) for i in range(n_sugerencias)], sep, y, util, h, sep)))
    y += h + sep
    # 4. cuerpo
    for i, f in enumerate(cuerpo):
        d.filas.append((f"cuerpo:{i}", _repartir(list(f), sep, y, util, h, sep)))
        y += h + sep
    # 5. acciones
    d.filas.append(("acciones", _repartir([(f"accion:{a}", 1.0) for a in acciones], sep, y, util, h, sep)))
    y += h + sep
    d.alto = y
    return d
