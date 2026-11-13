"""Barrido (sección 7.2): las filas y luego las teclas se iluminan solas; un parpadeo largo elige.
Lógica pura (tiempos reales en segundos).

- Niveles: **filas** -> **elementos** de la fila elegida. Cada fila termina en "↩ Volver".
- Avance cada ``paso_s`` (1,5 s por defecto); el primer elemento de cada nivel se queda 1,5×.
- Al **empezar a cerrar los ojos** el resaltado se congela (el tiempo no corre). Si el cierre fue
  natural, el barrido sigue donde iba; si fue un parpadeo largo, se elige lo que estaba
  iluminado cuando se cerraron los ojos.
- Tras elegir: pausa de 0,8 s y se vuelve a la primera fila.
- Dos vueltas dentro de una fila sin elegir -> vuelve al nivel de filas. Tres vueltas completas
  de filas sin elegir nada -> se detiene ("Parpadee largo para continuar").

API: ``Barrido(filas, paso_s).actualizar(t, ojos_cerrando, evento) -> EstadoBarrido``, con
``evento`` en (None, "elegir", "siguiente"). ``EstadoBarrido.elegido`` trae el identificador
elegido (solo en la llamada en que se eligió).
"""
from __future__ import annotations

from dataclasses import dataclass

VOLVER = "barrido:volver"
FILAS = "filas"
ELEMENTOS = "elementos"
PASO_MIN, PASO_MAX = 0.5, 4.0
FACTOR_PRIMERO = 1.5
PAUSA_ELEGIR_S = 0.8
VUELTAS_FILA = 2
VUELTAS_FILAS = 3
RECORDAR_CIERRE_S = 0.5       # tras abrir los ojos, "elegir" usa lo iluminado al cerrarlos
CONGELAR_MAX_S = 4.0          # un cierre más largo es descanso: el barrido sigue (no se traba)


@dataclass(frozen=True)
class EstadoBarrido:
    nivel: str = FILAS               # "filas" | "elementos"
    fila: int = 0
    elemento: int = -1               # -1 en el nivel de filas
    resaltado: tuple = ()            # identificadores iluminados (toda la fila o un elemento)
    volver: bool = False             # está iluminado "↩ Volver"
    detenido: bool = False
    congelado: bool = False
    en_pausa: bool = False           # pausa tras elegir
    elegido: str | None = None
    entro_fila: bool = False         # en esta llamada se entró a una fila
    progreso: float = 0.0            # 0..1 del paso actual


class Barrido:
    def __init__(self, filas: list[list[str]], paso_s: float = 1.5, t0: float = 0.0):
        self.paso_s = min(max(float(paso_s), PASO_MIN), PASO_MAX)
        self.filas: list[list[str]] = []
        self._t = t0
        self.poner_filas(filas, t0)
        self._cerrando_antes = False
        self._al_cerrar = None          # (nivel, fila, elemento) al empezar a cerrar los ojos
        self._t_abrio = None
        self._t_cerro = None            # desde cuándo están cerrados (para el tope)

    # ------------------------------------------------------------ armado
    def poner_filas(self, filas: list[list[str]], t: float | None = None, conservar: bool = False):
        """Cambian las filas (otra página, otras sugerencias, un aviso que tapa las sugerencias).
        Con ``conservar`` se queda donde iba si se puede (ronda 3): la fila actual se busca por su
        contenido (aunque cambie el número de filas) y, si la persona ya estaba dentro de una
        fila, sigue dentro y en el mismo elemento. Si no se puede, vuelve a la primera fila."""
        nuevas = [list(f) for f in filas if f]
        if conservar and self.filas and nuevas and self._conservar(nuevas):
            return
        self.filas = nuevas
        pausa = getattr(self, "_pausa_hasta", None)
        self.reiniciar(self._t if t is None else t)
        self._pausa_hasta = pausa            # la pausa de 0,8 s tras elegir se respeta

    def _conservar(self, nuevas: list) -> bool:
        nivel = getattr(self, "nivel", FILAS)
        fila = getattr(self, "fila", 0)
        actual = self.filas[fila] if 0 <= fila < len(self.filas) else None
        iguales = [i for i, f in enumerate(nuevas) if actual is not None and f == actual]
        if iguales:
            nueva_fila = min(iguales, key=lambda i: abs(i - fila))
        elif len(nuevas) == len(self.filas):
            nueva_fila = fila                 # la misma fila con otro contenido (sugerencias nuevas)
        elif nivel == FILAS:
            nueva_fila = min(fila, len(nuevas) - 1)   # la fila desapareció: la que ocupa su lugar
        else:
            return False
        if nivel != FILAS and self.elemento >= len(nuevas[nueva_fila]) + 1:
            return False
        self.filas = nuevas
        self.fila = nueva_fila
        return True

    def reiniciar(self, t: float):
        self.nivel = FILAS
        self.fila = 0
        self.elemento = -1
        self._acum = 0.0
        self._t = t
        self._vueltas = 0
        self._detenido = False
        self._pausa_hasta = None
        self._al_cerrar = None

    def cambiar_paso(self, paso_s: float):
        self.paso_s = min(max(float(paso_s), PASO_MIN), PASO_MAX)

    # ------------------------------------------------------------ consultas
    def _n(self) -> int:
        """Cantidad de posiciones en el nivel actual (en una fila, + "Volver")."""
        if self.nivel == FILAS:
            return len(self.filas)
        return len(self.filas[self.fila]) + 1

    def _duracion(self) -> float:
        primero = (self.fila == 0) if self.nivel == FILAS else (self.elemento == 0)
        return self.paso_s * (FACTOR_PRIMERO if primero else 1.0)

    def _resaltado(self) -> tuple:
        if not self.filas or self._detenido:
            return ()
        if self.nivel == FILAS:
            return tuple(self.filas[self.fila])
        if self.elemento >= len(self.filas[self.fila]):
            return ()
        return (self.filas[self.fila][self.elemento],)

    def _estado(self, t: float, congelado: bool, elegido: str | None = None, entro: bool = False) -> EstadoBarrido:
        volver = self.nivel == ELEMENTOS and self.elemento >= len(self.filas[self.fila]) if self.filas else False
        en_pausa = self._pausa_hasta is not None and t < self._pausa_hasta
        return EstadoBarrido(self.nivel, self.fila, self.elemento, self._resaltado() if not en_pausa else (),
                             volver and not en_pausa, self._detenido, congelado, en_pausa, elegido, entro,
                             min(self._acum / self._duracion(), 1.0) if self.filas else 0.0)

    # ------------------------------------------------------------ avance
    def _avanzar(self):
        self._acum = 0.0
        n = self._n()
        if self.nivel == FILAS:
            self.fila += 1
            if self.fila >= n:
                self.fila = 0
                self._vueltas += 1
                if self._vueltas >= VUELTAS_FILAS:
                    self._detenido = True
        else:
            self.elemento += 1
            if self.elemento >= n:
                self.elemento = 0
                self._vueltas += 1
                if self._vueltas >= VUELTAS_FILA:
                    # dos vueltas en la fila sin elegir: de vuelta a las filas (en esta misma fila)
                    self.nivel = FILAS
                    self.elemento = -1
                    self._vueltas = 0

    def _elegir(self, t: float, nivel: str, fila: int, elemento: int):
        """Devuelve (elegido, entro_fila)."""
        if not self.filas:
            return None, False
        fila = min(fila, len(self.filas) - 1)
        if nivel == FILAS:
            self.nivel = ELEMENTOS
            self.fila = fila
            self.elemento = 0
            self._acum = 0.0
            self._vueltas = 0
            return None, True
        if elemento >= len(self.filas[fila]):
            # "↩ Volver": a las filas, desde esta misma fila
            self.nivel = FILAS
            self.fila = fila
            self.elemento = -1
            self._acum = 0.0
            self._vueltas = 0
            return VOLVER, False
        elegido = self.filas[fila][elemento]
        self.nivel = FILAS
        self.fila = 0
        self.elemento = -1
        self._acum = 0.0
        self._vueltas = 0
        self._pausa_hasta = t + PAUSA_ELEGIR_S
        return elegido, False

    def actualizar(self, t: float, ojos_cerrando: bool = False, evento: str | None = None) -> EstadoBarrido:
        dt = max(t - self._t, 0.0)
        self._t = t
        if not self.filas:
            return EstadoBarrido(detenido=True)
        # congelar al empezar a cerrar los ojos (y recordar lo iluminado)
        if ojos_cerrando and not self._cerrando_antes:
            self._al_cerrar = (self.nivel, self.fila, self.elemento, self._detenido)
            self._t_cerro = t
        if not ojos_cerrando and self._cerrando_antes:
            self._t_abrio = t
            self._t_cerro = None
        self._cerrando_antes = ojos_cerrando
        if ojos_cerrando and self._t_cerro is not None and t - self._t_cerro > CONGELAR_MAX_S:
            ojos_cerrando = False       # tope: con los ojos cerrados tanto rato el barrido sigue
        en_pausa = self._pausa_hasta is not None and t < self._pausa_hasta
        if self._pausa_hasta is not None and not en_pausa:
            self._pausa_hasta = None
            self._acum = 0.0
        if evento == "elegir":
            if en_pausa:
                return self._estado(t, ojos_cerrando)
            nivel, fila, elemento, detenido = self.nivel, self.fila, self.elemento, self._detenido
            if self._al_cerrar is not None and (ojos_cerrando or (self._t_abrio is not None
                                                                  and t - self._t_abrio <= RECORDAR_CIERRE_S)):
                nivel, fila, elemento, detenido = self._al_cerrar
            self._al_cerrar = None
            if detenido or self._detenido:
                # detenido: un parpadeo largo lo vuelve a poner en marcha desde la primera fila
                self.reiniciar(t)
                return self._estado(t, ojos_cerrando)
            elegido, entro = self._elegir(t, nivel, fila, elemento)
            return self._estado(t, ojos_cerrando, elegido, entro)
        if evento == "siguiente":
            if self._detenido:
                self.reiniciar(t)
            elif not en_pausa:
                self._avanzar()
            return self._estado(t, ojos_cerrando)
        if ojos_cerrando or en_pausa or self._detenido:
            return self._estado(t, ojos_cerrando)
        self._acum += dt
        # un salto grande de tiempo (ventana trabada) avanza como mucho un paso
        if self._acum >= self._duracion():
            self._avanzar()
        return self._estado(t, ojos_cerrando)
