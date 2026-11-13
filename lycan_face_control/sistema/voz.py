"""Voz de Windows sin internet (sección 3.11).

- **Principal**: SAPI 5 por ctypes (sin dependencias). Hilo propio con ``CoInitializeEx``. Métodos de
  la tabla de ISpVoice: Speak = 20, SetRate = 28, SetVolume = 30, WaitUntilDone = 32. Se habla con
  ``SPF_ASYNC | SPF_PURGEBEFORESPEAK | SPF_IS_XML`` (una frase nueva corta la anterior), con ``&``,
  ``<`` y ``>`` escapados.
- **Elegir voz**: la guardada en la configuración; si no, "Microsoft Sabina Desktop"; si no existe,
  la primera en español (idioma 80a, c0a, 40a...); al final la predeterminada. Nunca se exige Sabina.
- **Respaldo**: si no se puede crear el objeto COM, un proceso ``powershell.exe`` sin ventana que
  carga System.Speech y lee frases por la entrada estándar (una por línea, en UTF-8).
- Si nada funciona, ``hablar`` devuelve False y la interfaz muestra el texto en grande.
- Si la voz falla **después** de arrancar (Speak devuelve error, el proceso de PowerShell se
  cerró), se intenta recrear una vez; si tampoco, la voz queda apagada (el siguiente ``hablar``
  devuelve False) y la frase que no se oyó va a ``fallidos`` para que la interfaz la muestre en
  grande (ronda 2 de arreglos).
- ``voz_espanol`` dice si la voz elegida es en español. Si Windows solo tiene voces en otro
  idioma, se usa la que haya (se entiende algo) y la interfaz avisa una vez y muestra el texto en
  grande.
- Largo: hasta 2000 caracteres, igual que el teclado; si hay que cortar, se corta en un espacio.

Nunca se anota en el registro lo que se dice (privacidad).
"""
from __future__ import annotations

import ctypes
import json
import logging
import queue
import subprocess
import threading

log = logging.getLogger("lycan")

SABINA = "Microsoft Sabina Desktop"
CLAVES_VOCES = (r"SOFTWARE\Microsoft\Speech\Voices\Tokens",)
SPF_ASYNC = 1
SPF_PURGEBEFORESPEAK = 2
SPF_IS_XML = 8
SPF_IS_NOT_XML = 0x10
FLAGS_HABLAR = SPF_ASYNC | SPF_PURGEBEFORESPEAK | SPF_IS_XML
SPERR_NOT_FOUND = 0x80045043 - (1 << 32)        # como HRESULT con signo
VT_SPEAK, VT_SETRATE, VT_SETVOLUME, VT_WAIT = 20, 28, 30, 32
CLSID_SPVOICE = "{96749377-3391-11D2-9EE3-00C04F797396}"
IID_ISPVOICE = "{6C44DF74-72B9-4992-A1EC-EF996E0422D4}"
CREATE_NO_WINDOW = 0x08000000
ESPERA_INICIO_S = 0.3          # no congela la interfaz si la voz tarda en arrancar (la frase
                               # que se pide mientras tanto queda en la cola o va a ``fallidos``)
MAX_TEXTO = 2000           # igual que teclado_logica.MAX_TEXTO


def recortar(texto: str, maximo: int = MAX_TEXTO) -> str:
    """Espacios normalizados y, si pasa de ``maximo``, cortado en el último espacio (no en media
    palabra)."""
    limpio = " ".join(str(texto or "").split())
    if len(limpio) <= maximo:
        return limpio
    corte = limpio.rfind(" ", 0, maximo + 1)
    return limpio[:corte if corte > maximo // 2 else maximo]


# --------------------------------------------------------------------------- funciones puras
def escapar_xml(texto: str) -> str:
    """Escapa ``&``, ``<`` y ``>`` y quita caracteres de control (SAPI con SPF_IS_XML)."""
    limpio = "".join(c if (c >= " " or c in "\t") else " " for c in str(texto))
    return limpio.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def es_espanol(idioma: str) -> bool:
    """``idioma`` como en el registro de Windows ("80A", "c0a", "409;9") o "es-MX"."""
    if not idioma:
        return False
    s = str(idioma).strip().lower()
    if s.startswith("es"):
        return True
    for parte in s.replace(",", ";").split(";"):
        try:
            if int(parte.strip(), 16) & 0x3FF == 0x0A:
                return True
        except ValueError:
            continue
    return False


def elegir_voz(voces: list[dict], preferida: str | None = None) -> str | None:
    """Nombre de la voz a usar entre ``voces`` = [{"nombre", "idioma"}]; None = la predeterminada."""
    nombres = [v.get("nombre") for v in voces if v.get("nombre")]
    if preferida and preferida in nombres:
        return preferida
    if SABINA in nombres:
        return SABINA
    for v in voces:
        if v.get("nombre") and es_espanol(v.get("idioma", "")):
            return v["nombre"]
    return None


def xml_para(texto: str, voz: str | None) -> str:
    cuerpo = escapar_xml(texto)
    if voz:
        nombre = escapar_xml(voz).replace('"', "")
        return f'<voice required="Name={nombre}">{cuerpo}</voice>'
    return cuerpo


def limitar(v, lo, hi, defecto):
    try:
        v = int(round(float(v)))
    except (TypeError, ValueError):
        return defecto
    return min(max(v, lo), hi)


def listar_voces() -> list[dict]:
    """Voces SAPI 5 instaladas (registro de Windows; no habla ni crea objetos COM)."""
    try:
        import winreg
    except ImportError:
        return []
    out = []
    for raiz in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for base in CLAVES_VOCES:
            try:
                k = winreg.OpenKey(raiz, base)
            except OSError:
                continue
            i = 0
            while True:
                try:
                    token = winreg.EnumKey(k, i)
                except OSError:
                    break
                i += 1
                try:
                    a = winreg.OpenKey(k, token + r"\Attributes")
                    nombre = winreg.QueryValueEx(a, "Name")[0]
                    try:
                        idioma = winreg.QueryValueEx(a, "Language")[0]
                    except OSError:
                        idioma = ""
                    if nombre and all(v["nombre"] != nombre for v in out):
                        out.append({"nombre": str(nombre), "idioma": str(idioma), "token": token})
                except OSError:
                    continue
    return out


GUION_POWERSHELL = r"""
$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$pref = '__VOZ__'
$voces = $s.GetInstalledVoices() | Where-Object { $_.Enabled }
$v = $voces | Where-Object { $_.VoiceInfo.Name -eq $pref } | Select-Object -First 1
if (-not $v) { $v = $voces | Where-Object { $_.VoiceInfo.Culture.Name -like 'es-*' } | Select-Object -First 1 }
if ($v) { $s.SelectVoice($v.VoiceInfo.Name) }
[Console]::Out.WriteLine('listo')
[Console]::Out.Flush()
while ($null -ne ($l = [Console]::In.ReadLine())) {
  try {
    $o = $l | ConvertFrom-Json
    $s.SpeakAsyncCancelAll()
    $s.Volume = [int]$o.v
    $s.Rate = [int]$o.r
    if ($o.t) { [void]$s.SpeakAsync([string]$o.t) }
  } catch { }
}
"""


def comando_powershell(voz: str | None = None) -> list[str]:
    """Comando del proceso de respaldo (no se ejecuta aquí)."""
    nombre = (voz or SABINA).replace("'", "")
    guion = GUION_POWERSHELL.replace("__VOZ__", nombre)
    return ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", guion]


def linea_powershell(texto: str, volumen: int, velocidad: int) -> str:
    """Una orden para el proceso de respaldo: JSON en una sola línea."""
    limpio = recortar(texto)
    return json.dumps({"t": limpio, "v": int(volumen), "r": int(velocidad)}, ensure_ascii=False)


# --------------------------------------------------------------------------- SAPI por ctypes
class _GUID(ctypes.Structure):
    _fields_ = [("Data1", ctypes.c_ulong), ("Data2", ctypes.c_ushort), ("Data3", ctypes.c_ushort),
                ("Data4", ctypes.c_ubyte * 8)]


def _guid(texto: str) -> _GUID:
    g = _GUID()
    ctypes.oledll.ole32.CLSIDFromString(ctypes.c_wchar_p(texto), ctypes.byref(g))
    return g


class MotorSapi:
    """ISpVoice por su tabla de métodos. Debe crearse, usarse y cerrarse en el MISMO hilo."""

    def __init__(self):
        self.ptr = ctypes.c_void_p()
        self._com = False
        ole32 = ctypes.windll.ole32
        hr = ole32.CoInitializeEx(None, 0x0)           # COINIT_MULTITHREADED (SpVoice acepta ambos)
        self._com = hr in (0, 1)                       # S_OK o S_FALSE: hay que llamar CoUninitialize
        clsid, iid = _guid(CLSID_SPVOICE), _guid(IID_ISPVOICE)
        hr = ole32.CoCreateInstance(ctypes.byref(clsid), None, 0x17, ctypes.byref(iid), ctypes.byref(self.ptr))
        if hr != 0 or not self.ptr.value:
            self.cerrar()
            raise OSError(f"No se pudo crear SpVoice (0x{hr & 0xFFFFFFFF:08x})")

    def _metodo(self, indice: int, *argtypes):
        vtbl = ctypes.cast(self.ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))[0]
        proto = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *argtypes)
        return proto(vtbl[indice])

    def velocidad(self, v: int) -> int:
        return self._metodo(VT_SETRATE, ctypes.c_long)(self.ptr, int(v))

    def volumen(self, v: int) -> int:
        return self._metodo(VT_SETVOLUME, ctypes.c_ushort)(self.ptr, int(v))

    def hablar(self, xml: str, flags: int = FLAGS_HABLAR) -> int:
        f = self._metodo(VT_SPEAK, ctypes.c_wchar_p, ctypes.c_ulong, ctypes.c_void_p)
        return f(self.ptr, xml, flags, None)

    def esperar(self, ms: int) -> int:
        return self._metodo(VT_WAIT, ctypes.c_ulong)(self.ptr, int(ms))

    def cerrar(self):
        if self.ptr.value:
            try:
                self._metodo(2)(self.ptr)                # Release
            except Exception:  # noqa: BLE001
                pass
            self.ptr = ctypes.c_void_p()
        if self._com:
            try:
                ctypes.windll.ole32.CoUninitialize()
            except Exception:  # noqa: BLE001
                pass
            self._com = False


class MotorPowerShell:
    def __init__(self, voz: str | None = None, popen=subprocess.Popen):
        self.proc = popen(comando_powershell(voz), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW, encoding="utf-8",
                          errors="replace")
        primera = self.proc.stdout.readline() if self.proc.stdout is not None else ""
        if "listo" not in (primera or ""):
            self.cerrar()
            raise OSError("El respaldo de voz no arrancó")

    def hablar(self, texto: str, volumen: int, velocidad: int):
        if self.proc.poll() is not None:
            raise OSError("El respaldo de voz se cerró")
        self.proc.stdin.write(linea_powershell(texto, volumen, velocidad) + "\n")
        self.proc.stdin.flush()

    def cerrar(self):
        p = getattr(self, "proc", None)
        if p is None:
            return
        try:
            if p.stdin:
                p.stdin.close()
        except OSError:
            pass
        try:
            p.wait(timeout=1.0)
        except Exception:  # noqa: BLE001
            try:
                p.kill()
            except Exception:  # noqa: BLE001
                pass
        self.proc = None


# --------------------------------------------------------------------------- hilo de voz
class Voz:
    """Voz con hilo propio. ``hablar(texto, urgente=False)`` devuelve False si no hay ninguna voz
    (entonces la interfaz muestra el texto en grande)."""

    def __init__(self, cfg_voz: dict | None = None, crear_sapi=MotorSapi, crear_respaldo=MotorPowerShell,
                 listar=listar_voces, arrancar: bool = True):
        self.cfg = dict(cfg_voz or {})
        self._crear_sapi = crear_sapi
        self._crear_respaldo = crear_respaldo
        self._listar = listar
        self.cola: queue.Queue = queue.Queue()
        self.listo = threading.Event()
        self.motor = None              # "sapi" | "powershell" | None
        self.nombre_voz: str | None = None
        self.voz_espanol: bool | None = None   # None = todavía no se sabe
        self.ultimo = ""
        self.fallidos: queue.Queue = queue.Queue()   # frases que no se pudieron decir (para la interfaz)
        self._hilo = None
        if arrancar:
            self._hilo = threading.Thread(target=self._correr, name="voz", daemon=True)
            self._hilo.start()

    @property
    def disponible(self) -> bool:
        return not self.listo.is_set() or self.motor is not None

    def configurar(self, cfg_voz: dict):
        self.cfg = dict(cfg_voz or {})
        self.cola.put(("config",))

    def hablar(self, texto: str, urgente: bool = False) -> bool:
        texto = recortar(texto)
        if not texto:
            return True
        if not self.listo.is_set():
            self.listo.wait(ESPERA_INICIO_S)
        if self.listo.is_set() and self.motor is None:
            return False
        self.ultimo = texto
        self.cola.put(("hablar", texto, bool(urgente)))
        return True

    def repetir(self) -> bool:
        return self.hablar(self.ultimo) if self.ultimo else True

    def callar(self):
        self.cola.put(("hablar", "", False))

    def cerrar(self):
        self.cola.put(("cerrar",))
        if self._hilo is not None:
            self._hilo.join(timeout=2.0)

    # ------------------------------------------------------------ dentro del hilo
    def _volumen(self, urgente: bool) -> int:
        return 100 if urgente else limitar(self.cfg.get("volumen", 80), 0, 100, 80)

    def _velocidad(self) -> int:
        return limitar(self.cfg.get("velocidad", -1), -10, 10, -1)

    def _iniciar(self):
        sapi = None
        try:
            voces = self._listar() or []
        except Exception:  # noqa: BLE001
            voces = []
        self.nombre_voz = elegir_voz(voces, self.cfg.get("nombre"))
        idioma = next((v.get("idioma", "") for v in voces if v.get("nombre") == self.nombre_voz), "")
        self.voz_espanol = bool(self.nombre_voz) and es_espanol(idioma)
        if not self.voz_espanol:
            log.warning("No hay voz en español instalada: se usa la predeterminada de Windows")
        try:
            sapi = self._crear_sapi()
            self.motor = "sapi"
            log.info("Voz lista (SAPI): %s", self.nombre_voz or "predeterminada")
            return sapi
        except Exception as e:  # noqa: BLE001
            log.warning("SAPI no disponible (%s); se prueba el respaldo de PowerShell", e)
        try:
            sapi = self._crear_respaldo(self.nombre_voz)
            self.motor = "powershell"
            log.info("Voz lista (respaldo PowerShell)")
            return sapi
        except Exception as e:  # noqa: BLE001
            log.warning("No hay voz disponible: %s", e)
            self.motor = None
            return None

    def _recrear(self, m):
        """La voz falló: se cierra y se crea otra vez la misma clase de motor (una vez)."""
        try:
            if m is not None:
                m.cerrar()
        except Exception:  # noqa: BLE001
            pass
        crear = self._crear_sapi if self.motor == "sapi" else self._crear_respaldo
        try:
            return crear() if self.motor == "sapi" else crear(self.nombre_voz)
        except Exception as e:  # noqa: BLE001
            log.warning("No se pudo recrear la voz: %s", type(e).__name__)
            return None

    def _decir_seguro(self, m, texto: str, urgente: bool):
        """Dice el texto; si falla, recrea la voz y lo intenta otra vez. Devuelve el motor que
        queda (None = sin voz: la frase va a ``fallidos``)."""
        try:
            self._decir(m, texto, urgente)
            return m
        except Exception as e:  # noqa: BLE001
            log.warning("La voz falló: %s", type(e).__name__)
        m = self._recrear(m)
        if m is not None:
            try:
                self._decir(m, texto, urgente)
                log.info("La voz se recuperó")
                return m
            except Exception as e:  # noqa: BLE001
                log.warning("La voz volvió a fallar: %s", type(e).__name__)
                try:
                    m.cerrar()
                except Exception:  # noqa: BLE001
                    pass
        self.motor = None                    # el próximo hablar() devuelve False
        if texto:
            self.fallidos.put(texto)
        return None

    def _decir(self, m, texto: str, urgente: bool):
        if self.motor == "sapi":
            m.volumen(self._volumen(urgente))
            m.velocidad(self._velocidad())
            hr = m.hablar(xml_para(texto, self.nombre_voz))
            if hr != 0 and self.nombre_voz:
                log.warning("La voz %s no respondió (0x%08x); se usa la predeterminada",
                            self.nombre_voz, hr & 0xFFFFFFFF)
                self.nombre_voz = None
                hr = m.hablar(xml_para(texto, None))
            if hr != 0 and texto:
                raise OSError(f"Speak 0x{hr & 0xFFFFFFFF:08x}")
        else:
            m.hablar(texto, self._volumen(urgente), self._velocidad())

    def _correr(self):
        m = None
        try:
            m = self._iniciar()
        finally:
            self.listo.set()
        try:
            while True:
                orden = self.cola.get()
                if orden[0] == "cerrar":
                    break
                if m is None:
                    # sin ningún motor: la frase que se pidió mientras arrancaba no se pierde en
                    # silencio (ronda 3), va a ``fallidos`` y la interfaz la muestra en grande
                    if orden[0] == "hablar" and orden[1]:
                        self.fallidos.put(orden[1])
                    continue
                if orden[0] == "config":
                    pref = self.cfg.get("nombre")
                    if pref:
                        try:
                            self.nombre_voz = elegir_voz(self._listar() or [], pref)
                        except Exception:  # noqa: BLE001
                            pass
                    continue
                if orden[0] == "hablar":
                    # si llegaron varias, solo vale la última (una frase nueva corta la anterior);
                    # las demás órdenes (cambio de voz, cerrar) se vuelven a poner en la cola
                    otras = []
                    try:
                        while True:
                            sig = self.cola.get_nowait()
                            if sig[0] == "hablar":
                                orden = sig
                            else:
                                otras.append(sig)
                                if sig[0] == "cerrar":
                                    break
                    except queue.Empty:
                        pass
                    for o in otras:
                        self.cola.put(o)
                    m = self._decir_seguro(m, orden[1], orden[2])
        finally:
            if m is not None:
                try:
                    if self.motor == "sapi":
                        m.hablar("", SPF_ASYNC | SPF_PURGEBEFORESPEAK)      # cortar lo que esté diciendo
                    m.cerrar()
                except Exception:  # noqa: BLE001
                    pass
