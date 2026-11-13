"""Predicción de palabras sin internet (sección 7.3). Lógica pura salvo leer y guardar archivos.

- Lista general: ``recursos/palabras_es.txt`` (20 000 palabras con su frecuencia; FrequencyWords
  a partir de OpenSubtitles, CC BY-SA 4.0).
- Vocabulario de cuidado (cobija, sábana, flemas, BiPAP...) con prioridad.
- Palabras de la persona (historial local opcional): aprende al pulsar Espacio, Hablar o
  Escribir y lo guarda en ``palabras_usuario.json`` (máx. 5000 palabras y 10 000 pares).
  **Privacidad** (ronda 1): el archivo guarda cada palabra con cuántas veces se usó y si se usó
  hace poco (sí/no), y los pares de palabras seguidas. **No** guarda el orden exacto en que se
  escribieron (antes un contador permitía rearmar la última frase). Los pares sí dejan ver qué
  palabras van juntas: el README y la ayuda lo dicen tal cual.

El prefijo se compara sin tildes y en minúsculas (búsqueda binaria en la lista ordenada), así
"sab" sugiere "sábana". Puntaje:
``log(frecuencia+1) + 3·log(1+usos) + 0,5·reciente + 2·cuidado (+ pares con la palabra anterior)``.
De las 5 sugerencias, hasta 2 puestos se reservan para palabras de cuidado o de la persona que
coincidan (ver decisiones: con solo el puntaje, "sab" nunca mostraría "sábana" frente a
"saber", "sabes", "sabe"...).
"""
from __future__ import annotations

import bisect
import json
import logging
import math
import os
import time
from pathlib import Path

from .teclado_logica import sin_tildes

log = logging.getLogger("lycan")

N_SUGERENCIAS = 5
RESERVADAS = 2
MAX_PALABRAS = 5000
MAX_PARES = 10000
MAX_LARGO_PALABRA = 30
RECIENTE_N = 200            # una palabra usada en las últimas 200 cuenta como reciente
VERSION_ARCHIVO = 2          # 2: "reciente" sí/no en vez del orden exacto de uso

VOCABULARIO_CUIDADO = (
    "cobija", "sábana", "almohada", "pañal", "aspirar", "flemas", "saliva", "succión", "oxígeno", "máscara",
    "BiPAP", "ventilador", "sonda", "gastrostomía", "medicamento", "pastilla", "enfermera", "terapeuta",
    "silla", "cama", "voltear", "acomodar", "rascar", "picar", "ducha", "peinar", "gafas", "televisor",
    "celular", "ventana", "cortina", "luz",
)
# Groserías y palabras ofensivas que trae la lista general (sacada de subtítulos de películas): no
# se sugieren nunca por sí solas. Si la persona las escribe, se aprenden como suyas y entonces sí
# aparecen (es su forma de hablar, no la del programa).
GROSERIAS = frozenset("""
puta puto putas putos putita putito putitas putitos mierda mierdas marica maricas maricón maricones
pendejo pendejos pendeja pendejas pendejada culo culos culito verga vergas mamada mamadas coño coños
joder jodido jodida jodidos jodidas jodidamente jodan jodas joda jode jodió joderme jodiste jodete jódete
carajo carajos cabrón cabrona cabrones pinche pinches polla pollas zorra zorras perra perras bastardo
bastarda bastardos follar follando follado cojones cagar cagado cagada cagando cagué caga cagó cago
teta tetas gilipollas gilipolleces capullo capullos chingar chinga chingada chingado chingón hijueputa
hijueputas hijoputa malparido malparida malparidos gonorrea
""".split())
# Pares en los que la forma sin tilde también es una palabra correcta y común: se dejan las dos.
TILDE_LEGITIMA = frozenset("""
si mi tu el se te de mas aun solo que como donde cuando quien quienes cual cuales cuanto cuanta cuantos
cuantas porque adonde este esta estas estos ese esa esos esas aquel aquella sabana termino practico calculo
numero limite animo publico ultimo deposito critico continuo transito
""".split())
TILDE_FACTOR = 3                # la forma con tilde tiene que ser al menos 3 veces más usada


def _plano(p: str) -> str:
    """Sin tildes, sin diéresis y con la ñ como n (para juntar 'nina' con 'niña')."""
    return sin_tildes(p).replace("ñ", "n")


def _solo_tilde_final(sin: str, con: str) -> bool:
    """'esta'/'está', 'llego'/'llegó', 'papa'/'papá': la única diferencia es la tilde de la última
    vocal (casi siempre dos palabras correctas, p. ej. un verbo en presente y en pasado)."""
    return len(sin) == len(con) and sin[:-1] == con[:-1] and con[-1] in "áéó" and sin[-1] in "aeo"


def limpiar_lista(frec: dict) -> dict:
    """Quita de la lista general las groserías y las formas sin tilde que son faltas de
    ortografía ('ningun', 'nina', 'verguenza'...). La frecuencia de la forma mal escrita se suma
    a la correcta."""
    out = {p: f for p, f in frec.items() if p.lower() not in GROSERIAS}
    grupos: dict[str, list[str]] = {}
    for p in out:
        grupos.setdefault(_plano(p), []).append(p)
    for clave, formas in grupos.items():
        if len(formas) < 2:
            continue
        sin = [p for p in formas if p == clave]
        con = [p for p in formas if p != clave]
        if not sin or not con:
            continue
        s = sin[0]
        if s in TILDE_LEGITIMA:
            continue
        mejor = max(con, key=lambda p: out[p])
        if _solo_tilde_final(s, mejor):
            continue
        if out[mejor] >= TILDE_FACTOR * max(out[s], 1):
            out[mejor] += out.pop(s)
    return out


# para empezar una frase cuando la persona aún no tiene palabras propias
INICIOS = ("Quiero", "Necesito", "Tengo", "Me", "Estoy")


def leer_con_reintentos(ruta: Path) -> str:
    """Lee un archivo de texto; si otro programa lo tiene bloqueado un momento (antivirus,
    OneDrive, copia de seguridad) reintenta como la configuración: 3 veces con 0,2 s. Si aun así
    no se puede, lanza el OSError (el que llama NO debe escribir encima en esa sesión)."""
    from .config import PAUSA_REINTENTO_S, REINTENTOS_LECTURA
    ultimo = None
    for i in range(REINTENTOS_LECTURA):
        try:
            return ruta.read_text(encoding="utf-8-sig")   # con o sin BOM
        except FileNotFoundError:
            raise
        except OSError as e:
            ultimo = e
            if i < REINTENTOS_LECTURA - 1:
                time.sleep(PAUSA_REINTENTO_S)
    raise ultimo


def palabras_de(texto: str) -> list[str]:
    """Palabras (solo letras) de un texto, en orden."""
    out, actual = [], []
    for c in texto:
        if c.isalpha():
            actual.append(c)
        else:
            if actual:
                out.append("".join(actual))
                actual = []
    if actual:
        out.append("".join(actual))
    return out


def _normal_para_guardar(p: str) -> str:
    """Se guarda en minúsculas salvo las siglas (BiPAP)."""
    if sum(1 for c in p if c.isupper()) >= 2:
        return p
    return p.lower()


def cargar_lista(ruta: Path | None = None) -> list[tuple[str, int]]:
    """[(palabra, frecuencia), ...] de ``palabras_es.txt`` (líneas ``palabra<TAB>frecuencia``;
    las que empiezan con # son comentarios). Si no existe, lista vacía (se anota)."""
    if ruta is None:
        from .config import ruta_recurso
        ruta = ruta_recurso("palabras_es.txt")
    out = []
    try:
        with open(ruta, encoding="utf-8") as f:
            for linea in f:
                if not linea.strip() or linea.startswith("#"):
                    continue
                partes = linea.rstrip("\n").split("\t")
                palabra = partes[0].strip()
                if not palabra:
                    continue
                try:
                    frec = int(partes[1]) if len(partes) > 1 else 1
                except ValueError:
                    frec = 1
                out.append((palabra, max(frec, 0)))
    except OSError as e:
        log.warning("No se pudo leer la lista de palabras: %s", e)
    return out


class Prediccion:
    def __init__(self, lista: list[tuple[str, int]] | None = None, ruta_usuario: Path | None = None,
                 aprender: bool = True, cuidado=VOCABULARIO_CUIDADO):
        """``lista``: [(palabra, frecuencia)] (None = leer ``recursos/palabras_es.txt``).
        ``ruta_usuario``: archivo de palabras aprendidas (None = no se guarda nada)."""
        if lista is None:
            lista = cargar_lista()
        self.ruta = Path(ruta_usuario) if ruta_usuario else None
        self.aprender_activo = bool(aprender)
        self.aviso: str | None = None
        self.solo_lectura = False          # no se pudo leer el archivo: no se escribe encima
        frec: dict[str, int] = {}
        for p, f in lista:
            if p not in frec or frec[p] < f:
                frec[p] = f
        frec = limpiar_lista(frec)
        self.cuidado = {p.lower(): p for p in cuidado}
        mediana = sorted(frec.values())[len(frec) // 2] if frec else 1
        for p in cuidado:
            if p not in frec and p.lower() not in frec:
                frec[p] = mediana
        self.frec = frec
        # clave plana (sin tildes y ñ -> n): "manan" encuentra "mañana" y "nin" encuentra "niño"
        entradas = sorted((_plano(p), p) for p in frec)
        self._claves = [c for c, _ in entradas]
        self._palabras = [p for _, p in entradas]
        self._top_general = [p for p, _ in sorted(frec.items(), key=lambda x: -x[1]) if len(p) > 1][:50]
        # de la persona
        self.usos: dict[str, int] = {}
        self.ultimo: dict[str, int] = {}
        self.pares: dict[str, int] = {}
        self.contador = 0
        self._cambios = 0
        if self.ruta is not None:
            self.cargar_usuario()

    # ------------------------------------------------------------ sugerir
    def _rango(self, prefijo: str) -> range:
        i = bisect.bisect_left(self._claves, prefijo)
        j = bisect.bisect_left(self._claves, prefijo + "\U0010ffff")
        return range(i, j)

    def _puntaje(self, p: str, anterior: str | None) -> float:
        clave = _normal_para_guardar(p)
        usos = self.usos.get(clave, 0)
        reciente = 0.0
        if clave in self.ultimo:
            reciente = max(0.0, 1.0 - (self.contador - self.ultimo[clave]) / RECIENTE_N)
        s = math.log(self.frec.get(p, 0) + 1) + 3.0 * math.log(1 + usos) + 0.5 * reciente
        if p.lower() in self.cuidado:
            s += 2.0
        if anterior:
            par = self.pares.get(f"{_normal_para_guardar(anterior)} {clave}", 0)
            if par:
                s += 2.0 * math.log(1 + par)
        return s

    def sugerir(self, prefijo: str, anterior: str | None = None, n: int = N_SUGERENCIAS) -> list[str]:
        """Hasta ``n`` palabras para el ``prefijo`` (sin tildes, sin importar mayúsculas).
        Sin prefijo: la siguiente palabra según los pares aprendidos (o las más usadas)."""
        estricto = sin_tildes(prefijo or "").strip()
        pre = _plano(prefijo or "").strip()
        if not pre:
            return self._siguiente(anterior, n)
        # si la persona sí escribió la ñ, solo las palabras con ñ ahí ("mañ" no da "mano")
        con_ene = "ñ" in estricto
        candidatos: dict[str, float] = {}
        especiales: dict[str, float] = {}
        for k in self._rango(pre):
            p = self._palabras[k]
            if con_ene and not sin_tildes(p).startswith(estricto):
                continue
            candidatos[p] = self._puntaje(p, anterior)
        for p in self.usos:
            if p in candidatos:
                continue
            if (sin_tildes(p).startswith(estricto) if con_ene else _plano(p).startswith(pre)):
                candidatos[p] = self._puntaje(p, anterior)
        escrito = (prefijo or "").lower()
        candidatos = {p: s for p, s in candidatos.items() if p.lower() != escrito}
        for p, s in candidatos.items():
            if p.lower() in self.cuidado or self.usos.get(_normal_para_guardar(p), 0) > 0:
                especiales[p] = s
        orden = sorted(candidatos, key=lambda p: (-candidatos[p], p))
        elegidas = orden[:n]
        # puestos reservados para cuidado y palabras de la persona
        reservar = [p for p in sorted(especiales, key=lambda p: (-especiales[p], p)) if p not in elegidas]
        reservar = reservar[:max(0, RESERVADAS - sum(1 for p in elegidas if p in especiales))]
        for p in reservar:
            for i in range(len(elegidas) - 1, -1, -1):
                if elegidas[i] not in especiales:
                    elegidas[i] = p
                    break
            else:
                if len(elegidas) < n:
                    elegidas.append(p)
        elegidas.sort(key=lambda p: (-candidatos[p], p))
        return _sin_repetir(elegidas)[:n]

    def _siguiente(self, anterior: str | None, n: int) -> list[str]:
        out: list[str] = []
        evitar = {anterior.lower()} if anterior else set()
        if anterior:
            a = _normal_para_guardar(anterior) + " "
            pares = sorted(((c, k[len(a):]) for k, c in self.pares.items() if k.startswith(a)),
                           key=lambda x: (-x[0], x[1]))
            out += [p for _, p in pares]
        if len(out) < n + 1:
            propias = sorted(self.usos, key=lambda p: (-self.usos[p], p))
            out += propias
        if len(out) < n + 1:
            out += list(INICIOS if not anterior else self._top_general)
        return [p for p in _sin_repetir(out) if p.lower() not in evitar][:n]

    # ------------------------------------------------------------ aprender
    def aprender(self, texto: str):
        """Aprende las palabras de ``texto`` (y los pares de palabras seguidas)."""
        if not self.aprender_activo:
            return
        palabras = [_normal_para_guardar(p) for p in palabras_de(texto) if 1 < len(p) <= MAX_LARGO_PALABRA]
        anterior = None
        for p in palabras:
            self.contador += 1
            self.usos[p] = self.usos.get(p, 0) + 1
            self.ultimo[p] = self.contador
            if anterior:
                k = f"{anterior} {p}"
                self.pares[k] = self.pares.get(k, 0) + 1
            anterior = p
            self._cambios += 1
        self._recortar()

    def aprender_par(self, anterior: str | None, palabra: str):
        """Aprende una palabra recién terminada (al pulsar Espacio) y su par con la anterior."""
        if not self.aprender_activo or not palabra or not (1 < len(palabra) <= MAX_LARGO_PALABRA):
            return
        if not all(c.isalpha() for c in palabra):
            return
        p = _normal_para_guardar(palabra)
        self.contador += 1
        self.usos[p] = self.usos.get(p, 0) + 1
        self.ultimo[p] = self.contador
        if anterior and all(c.isalpha() for c in anterior):
            k = f"{_normal_para_guardar(anterior)} {p}"
            self.pares[k] = self.pares.get(k, 0) + 1
        self._cambios += 1
        self._recortar()

    def _recortar(self):
        if len(self.usos) > MAX_PALABRAS:
            quedan = sorted(self.usos, key=lambda p: (-self.usos[p], -self.ultimo.get(p, 0)))[:MAX_PALABRAS]
            q = set(quedan)
            self.usos = {p: self.usos[p] for p in quedan}
            self.ultimo = {p: v for p, v in self.ultimo.items() if p in q}
        if len(self.pares) > MAX_PARES:
            quedan = sorted(self.pares, key=lambda k: -self.pares[k])[:MAX_PARES]
            self.pares = {k: self.pares[k] for k in quedan}

    def olvidar(self) -> bool:
        """Borra todo lo aprendido (y el archivo). True si quedó borrado."""
        self.solo_lectura = False            # la persona pidió borrarlo: ya se puede escribir
        self.usos, self.ultimo, self.pares = {}, {}, {}
        self.contador = 0
        self._cambios = 0
        if self.ruta is not None:
            try:
                if self.ruta.exists():
                    self.ruta.unlink()
            except OSError as e:
                log.warning("No se pudo borrar el archivo de palabras aprendidas: %s", e)
                return False
            # también las copias apartadas cuando el archivo se dañó y el temporal que haya
            # quedado: tienen las mismas palabras de la persona ("olvidar" es olvidar todo)
            ok = True
            otros = list(self.ruta.parent.glob(f"{self.ruta.stem}.dañado-*.json"))
            otros.append(self.ruta.with_name(self.ruta.name + ".tmp"))
            for f in otros:
                try:
                    if f.exists():
                        f.unlink()
                except OSError as e:
                    log.warning("No se pudo borrar %s: %s", f.name, e)
                    ok = False
            return ok
        return True

    # ------------------------------------------------------------ archivo
    def _reciente(self, p: str) -> int:
        u = self.ultimo.get(p)
        return 1 if u is not None and self.contador - u < RECIENTE_N else 0

    def datos(self) -> dict:
        """Lo que se guarda: por palabra [usos, reciente 0/1] (sin el orden en que se escribió) y
        los pares. Las palabras van ordenadas alfabéticamente."""
        return {"version": VERSION_ARCHIVO,
                "palabras": {p: [self.usos[p], self._reciente(p)] for p in sorted(self.usos)},
                "pares": {k: self.pares[k] for k in sorted(self.pares)}}

    def cargar_usuario(self):
        """Lee ``palabras_usuario.json``. Si está dañado se aparta con otro nombre y se empieza
        de cero (nunca impide escribir)."""
        r = self.ruta
        if r is None or not r.exists():
            return
        try:
            crudo = json.loads(leer_con_reintentos(r))
            if not isinstance(crudo, dict) or not isinstance(crudo.get("palabras", {}), dict) \
                    or not isinstance(crudo.get("pares", {}), dict):
                raise ValueError("estructura equivocada")
            usos, ultimo, pares = {}, {}, {}
            version = crudo.get("version", 1)
            c_viejo = crudo.get("contador", 0)
            c_viejo = c_viejo if isinstance(c_viejo, int) and not isinstance(c_viejo, bool) else 0
            for p, v in crudo.get("palabras", {}).items():
                if not isinstance(p, str) or not p or len(p) > MAX_LARGO_PALABRA or not all(c.isalpha() for c in p):
                    continue
                if isinstance(v, list) and len(v) == 2 and all(isinstance(x, int) and not isinstance(x, bool)
                                                              and x >= 0 for x in v):
                    usos[p] = v[0]
                    if version == 1:
                        reciente = c_viejo - v[1] < RECIENTE_N      # archivo viejo: orden exacto
                    else:
                        reciente = v[1] >= 1
                    if reciente:
                        ultimo[p] = 0
                elif isinstance(v, int) and not isinstance(v, bool) and v >= 0:
                    usos[p] = v
            for k, v in crudo.get("pares", {}).items():
                if isinstance(k, str) and k.count(" ") == 1 and isinstance(v, int) and not isinstance(v, bool) \
                        and v > 0 and len(k) <= 2 * MAX_LARGO_PALABRA + 1:
                    pares[k] = v
            # las "recientes" quedan todas en 0 y el contador empieza en 0: se van enfriando
            # mientras se escribe, sin saber en qué orden se usaron
            self.contador = 0
            self.usos, self.ultimo, self.pares = usos, ultimo, pares
            self._recortar()
            if version == 1:
                self._cambios += 1          # se reescribe pronto en el formato sin orden
        except (ValueError, UnicodeDecodeError, RecursionError, MemoryError, TypeError, AttributeError) as e:
            log.warning("Archivo de palabras aprendidas dañado (%s); se empieza de cero.", type(e).__name__)
            self.aviso = "palabras_danadas"
            _apartar(r)
        except FileNotFoundError:
            pass
        except OSError as e:
            log.warning("No se pudo leer el archivo de palabras aprendidas (%s): en esta sesión no se "
                        "escribe encima.", e)
            self.solo_lectura = True
            self.aviso = "palabras_no_leidas"

    def guardar(self, forzar: bool = False) -> bool:
        if self.ruta is None or (not forzar and self._cambios == 0):
            return True
        if self.solo_lectura:
            return False                    # el archivo bueno sigue allá: no se pisa
        if not self.aprender_activo and not self.usos:
            return True
        try:
            escribir_json(self.ruta, self.datos())
            self._cambios = 0
            return True
        except OSError as e:
            log.warning("No se pudieron guardar las palabras aprendidas: %s", e)
            return False


def _sin_repetir(palabras) -> list[str]:
    vistos, out = set(), []
    for p in palabras:
        k = p.lower()
        if p and k not in vistos:
            vistos.add(k)
            out.append(p)
    return out


def _apartar(ruta: Path) -> bool:
    """Renombra un archivo dañado a ``<nombre>.dañado-AAAAMMDD-HHMMSS.json``."""
    try:
        sello = time.strftime("%Y%m%d-%H%M%S")
        destino = ruta.with_name(f"{ruta.stem}.dañado-{sello}.json")
        n = 1
        while destino.exists():
            destino = ruta.with_name(f"{ruta.stem}.dañado-{sello}-{n}.json")
            n += 1
        os.replace(ruta, destino)
        return True
    except OSError as e:
        log.warning("No se pudo apartar el archivo dañado: %s", e)
        return False


def escribir_json(ruta: Path, datos) -> None:
    """Escritura atómica (archivo temporal fijo + reemplazo), como la configuración."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_name(ruta.name + ".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False, indent=1)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, ruta)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def ruta_palabras_usuario() -> Path:
    from .config import carpeta_datos
    return carpeta_datos() / "palabras_usuario.json"
