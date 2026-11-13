"""Copiar texto al portapapeles de Windows (CF_UNICODETEXT = 13) por ctypes (sección 7.5).

Si el portapapeles está ocupado por otro programa se reintenta 5 veces cada 50 ms.
Nunca se anota en el registro lo que se copia.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import logging
import time

log = logging.getLogger("lycan")

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
REINTENTOS = 5
ESPERA_S = 0.05


class _Api:
    """Las funciones de Windows (las pruebas pueden pasar otras falsas)."""

    def __init__(self):
        u = ctypes.WinDLL("user32", use_last_error=True)
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        u.OpenClipboard.argtypes = (wt.HWND,)
        u.OpenClipboard.restype = wt.BOOL
        u.CloseClipboard.restype = wt.BOOL
        u.EmptyClipboard.restype = wt.BOOL
        u.SetClipboardData.argtypes = (wt.UINT, wt.HANDLE)
        u.SetClipboardData.restype = wt.HANDLE
        u.GetClipboardData.argtypes = (wt.UINT,)
        u.GetClipboardData.restype = wt.HANDLE
        k.GlobalAlloc.argtypes = (wt.UINT, ctypes.c_size_t)
        k.GlobalAlloc.restype = wt.HGLOBAL
        k.GlobalLock.argtypes = (wt.HGLOBAL,)
        k.GlobalLock.restype = ctypes.c_void_p
        k.GlobalUnlock.argtypes = (wt.HGLOBAL,)
        k.GlobalUnlock.restype = wt.BOOL
        k.GlobalFree.argtypes = (wt.HGLOBAL,)
        k.GlobalFree.restype = wt.HGLOBAL
        self.u, self.k = u, k

    def abrir(self) -> bool:
        return bool(self.u.OpenClipboard(None))

    def cerrar(self):
        self.u.CloseClipboard()

    def vaciar(self) -> bool:
        return bool(self.u.EmptyClipboard())

    def poner(self, texto: str) -> bool:
        datos = ctypes.create_unicode_buffer(texto)          # con el cero final
        tam = ctypes.sizeof(datos)
        h = self.k.GlobalAlloc(GMEM_MOVEABLE, tam)
        if not h:
            return False
        p = self.k.GlobalLock(h)
        if not p:
            self.k.GlobalFree(h)
            return False
        ctypes.memmove(p, datos, tam)
        self.k.GlobalUnlock(h)
        if not self.u.SetClipboardData(CF_UNICODETEXT, h):
            self.k.GlobalFree(h)                             # si Windows no lo tomó, se libera aquí
            return False
        return True

    def leer(self) -> str | None:
        h = self.u.GetClipboardData(CF_UNICODETEXT)
        if not h:
            return None
        p = self.k.GlobalLock(h)
        if not p:
            return None
        try:
            return ctypes.wstring_at(p)
        finally:
            self.k.GlobalUnlock(h)


_API = None


def _api():
    global _API
    if _API is None:
        _API = _Api()
    return _API


def copiar(texto: str, api=None, dormir=time.sleep) -> bool:
    """Pone ``texto`` en el portapapeles. True si se pudo."""
    api = api or _api()
    for intento in range(REINTENTOS):
        if api.abrir():
            try:
                if not api.vaciar():
                    return False
                return api.poner(str(texto))
            finally:
                api.cerrar()
        if intento < REINTENTOS - 1:
            dormir(ESPERA_S)
    log.warning("El portapapeles está ocupado por otro programa")
    return False


def leer(api=None, dormir=time.sleep) -> str | None:
    """Texto del portapapeles (para pruebas manuales)."""
    api = api or _api()
    for intento in range(REINTENTOS):
        if api.abrir():
            try:
                return api.leer()
            finally:
                api.cerrar()
        if intento < REINTENTOS - 1:
            dormir(ESPERA_S)
    return None
