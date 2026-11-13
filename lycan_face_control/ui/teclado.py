"""Teclado en pantalla para comunicarse (secciones 6.4 y 7).

Ventana grande, siempre encima y sin robar el foco, con (de arriba abajo):

1. el texto en armado (letra grande) + **Hablar**, **Repetir** y **Escribir**;
2. **Sí** y **No** grandes y separados, y las frases rápidas;
3. cinco palabras sugeridas (sin internet);
4. las letras (QWERTY o "las más usadas primero") o, en la página de frases, las categorías y
   sus frases;
5. las acciones: Borrar, Borrar palabra, Deshacer, Copiar, Limpiar, Frases, Barrido, Pausa, Cerrar.

Cada botón es un objetivo de la cabeza (``tecla:``, ``frase:``, ``sugerencia:``, ``accion:``) que
la máquina de estados elige por permanencia o con un gesto; nunca se hace clic en la ventana.
En **barrido** las filas y luego los botones se iluminan solos y un parpadeo largo (o un gesto de
clic) elige: la máquina avisa ``Elegir("barrido:elegir")`` y aquí se resuelve qué estaba
iluminado (``barrido.Barrido``).

"Escribir" devuelve el foco al programa que la persona estaba usando y le pasa el texto al motor
(``app.motor.escribir``), que lo envía con SendInput Unicode. En modo Directo cada tecla se envía
al instante (Borrar = tecla Retroceso).
"""
from __future__ import annotations

import logging
import time
import tkinter as tk

from .. import constantes as K
from ..barrido import VOLVER, Barrido
from ..frases import Frases, texto_final
from ..teclado_logica import (ACCIONES, ACCIONES_TEXTO, MAX_TEXTO, N_RAPIDAS, N_SUGERENCIAS, Escritura, buscar_tecla,
                              disposicion, distribucion, nombre_distribucion)
from .comun import LETRA, BotonGrande, area_de_trabajo, letra, no_activar, tema
from .textos import t

log = logging.getLogger("lycan")

PREFIJOS = ("tecla:", "frase:", "sugerencia:", "accion:")
GRANDE_S = 6.0                 # tiempo que se muestra en grande una frase dicha
# modo Directo: tope de retrocesos de una vez = el largo máximo del texto (así "Limpiar todo" borra
# allá todo lo que se escribió y el teclado y el programa no quedan desfasados)
MAX_RETROCESOS = MAX_TEXTO
FRASES_POR_FILA = 3
CATEGORIAS_POR_FILA = 6
MARGEN = 8


class VentanaTeclado:
    gestiona_submodo = False

    def __init__(self, root, app):
        self.root = root
        self.app = app
        self.win = None
        self.escritura = Escritura()
        self.botones: dict[str, BotonGrande] = {}
        self.pagina = "letras"
        self.cat = 0
        self.cat_pagina = 0
        self.frase_pagina = 0
        self.confirmando = False
        self.ultimo_dicho = ""
        self._grande_hasta = None
        self._resaltados: set = set()
        self._volver_visible = False
        self._directo_enviado = False
        self._sugerencias: list[str] = []
        self._frases_visibles: dict[str, dict] = {}
        self._cats_visibles: dict[str, int] = {}
        self.prediccion = _obtener(app, "obtener_prediccion")
        self.frases = _obtener(app, "obtener_frases") or Frases()
        cfg = self.cfg
        self.barrido_activo = bool(cfg["teclado"].get("barrido")) or self.solo_comunicacion
        self.barrido = None
        app.registro.manejador("barrido:", self._evento_barrido)
        if getattr(app, "sistema", False) and getattr(app, "voz", None) is None and hasattr(app, "_crear_voz"):
            app._crear_voz()           # la voz arranca en su hilo mientras se usa el teclado
        self.construir()

    # ------------------------------------------------------------ datos
    @property
    def cfg(self):
        return self.app.cfg.datos

    @property
    def solo_comunicacion(self) -> bool:
        return bool(self.cfg["teclado"].get("solo_comunicacion"))

    def submodo_inicial(self) -> str:
        if self.solo_comunicacion:
            return K.SOLO_COMUNICACION
        return K.BARRIDO if self.barrido_activo else K.TECLADO

    def _directo(self) -> bool:
        return self.cfg["teclado"].get("modo_escritura") == "directo"

    # ------------------------------------------------------------ construcción
    def destruir_ventana(self):
        reg = self.app.registro
        for p in PREFIJOS:
            reg.quitar(p)
        reg.quitar_ventana("teclado")
        if self.win is not None:
            try:
                self.win.destroy()
            except tk.TclError:
                pass
        self.win = None
        self.botones = {}
        self._resaltados = set()

    def _geometria(self):
        """(x, y, ancho, alto_max) del teclado: todo el ancho libre (sin la barra) y abajo o arriba."""
        l, a, d, ab = area_de_trabajo(self.root)
        barra = getattr(self.app, "barra", None)
        win = getattr(barra, "win", None)
        try:
            if win is not None and win.winfo_exists() and win.winfo_viewable():
                pos = self.cfg["barra"].get("posicion", "derecha")
                bx, by = win.winfo_rootx(), win.winfo_rooty()
                bw, bh = win.winfo_width(), win.winfo_height()
                if pos == "derecha":
                    d = min(d, bx - MARGEN)
                elif pos == "izquierda":
                    l = max(l, bx + bw + MARGEN)
                elif pos == "arriba":
                    a = max(a, by + bh + MARGEN)
                else:
                    ab = min(ab, by - MARGEN)
        except (tk.TclError, AttributeError):
            pass
        return l, a, d - l, ab - a

    def _filas_cuerpo_frases(self, n_filas: int) -> list:
        """Página de frases: una fila de categorías y las frases de la categoría elegida."""
        nombres = self.frases.nombres()
        self.cat = min(self.cat, len(nombres) - 1)
        filas = []
        # categorías (6 por fila; si hay más, "Más…" pasa a las siguientes)
        hay_mas_cat = len(nombres) > CATEGORIAS_POR_FILA
        por_pag = CATEGORIAS_POR_FILA - 1 if hay_mas_cat else CATEGORIAS_POR_FILA
        inicio = (self.cat_pagina * por_pag) % max(len(nombres), 1)
        cats = list(range(inicio, min(inicio + por_pag, len(nombres))))
        self._cats_visibles = {f"frase:cat:{i}": i for i in cats}
        fila = [(f"frase:cat:{i}", 1.0) for i in cats]
        if hay_mas_cat:
            fila.append(("accion:mas_categorias", 1.0))
        filas.append(fila)
        # frases (3 por fila); si no caben, la última casilla es "Más frases"
        lista = self.frases.frases(self.cat)
        casillas = max(n_filas - 1, 1) * FRASES_POR_FILA
        hay_mas = len(lista) > casillas
        por_pag = casillas - 1 if hay_mas else casillas
        paginas = max((len(lista) + por_pag - 1) // por_pag, 1)
        self.frase_pagina %= paginas
        ini = self.frase_pagina * por_pag
        visibles = list(range(ini, min(ini + por_pag, len(lista))))
        self._frases_visibles = {f"frase:{self.cat}:{i}": lista[i] for i in visibles}
        ids = [(f"frase:{self.cat}:{i}", 1.0) for i in visibles]
        if hay_mas:
            ids.append(("accion:mas_frases", 1.0))
        for k in range(max(n_filas - 1, 1)):
            parte = ids[k * FRASES_POR_FILA:(k + 1) * FRASES_POR_FILA]
            if parte:
                filas.append(parte)
        return filas

    def construir(self):
        self.destruir_ventana()
        cfg = self.cfg
        T = self.tema = tema(cfg)
        reg = self.app.registro
        self.nombre_dist = nombre_distribucion(cfg["teclado"], self.barrido_activo)
        self.filas_letras = distribucion(self.nombre_dist)
        x, y, ancho, alto_max = self._geometria()
        filas_cuerpo = None
        if self.pagina == "frases":
            filas_cuerpo = self._filas_cuerpo_frases(len(self.filas_letras))
        self.disp = d = disposicion(self.filas_letras, ancho, alto_max, pagina=self.pagina,
                                    filas_cuerpo=filas_cuerpo)
        h = d.tecla_alto
        w = self.win = tk.Toplevel(self.root)
        w.overrideredirect(True)
        w.attributes("-topmost", True)
        w.configure(bg=T.fondo)
        w.title(t("tec_titulo"))
        alto = d.alto
        yy = y if cfg["teclado"].get("posicion") == "arriba" else max(y + alto_max - alto, y)
        w.geometry(f"{ancho}x{alto}+{x}+{yy}")
        # letras: entre 20 y 32 pt según el alto de la tecla (nunca menos de 20)
        pt_tecla = max(20, min(32, int(h * 0.30)))
        self.f_tecla = letra(cfg, pt_tecla, True, minimo=20)
        self.f_accion = (LETRA, max(20, min(22, int(h * 0.22))), "bold")
        self.f_accion_fila = (LETRA, 20)          # fila de acciones: 9 botones, sin negrita para que quepan
        ids_fila_acciones = {c.id for c in d.fila("acciones")}
        self.f_frase = (LETRA, max(20, min(22, int(h * 0.22))), "bold")
        for caja in d.cajas():
            if caja.id == "texto":
                self._crear_texto(caja)
                continue
            fuente = self.f_accion_fila if caja.id in ids_fila_acciones else self._fuente(caja.id)
            b = BotonGrande(w, "", reg.comando(caja.id), T, fuente)
            if caja.id in ids_fila_acciones:
                b.configure(padx=2)
            b.configure(wraplength=max(caja.ancho - 12, 40))
            b.place(x=caja.x, y=caja.y, width=caja.ancho, height=caja.alto)
            reg.agregar(caja.id, b, (lambda i=caja.id: self.elegir(i)))
            self.botones[caja.id] = b
        # "↩ Volver" del barrido (se pone sobre el final de la fila iluminada)
        self.lbl_volver = tk.Label(w, text=t("tec_volver"), bg=T.ambar, fg=T.sobre_color,
                                   font=self.f_accion, bd=0, highlightthickness=4,
                                   highlightbackground=T.resalte)
        # texto grande (frases dichas) sobre la fila del texto
        self.lbl_grande = tk.Label(w, text="", bg=T.aviso_fondo, fg=T.aviso_texto,
                                   font=letra(cfg, 40, True, minimo=28), anchor="w", justify="left", padx=16)
        reg.ventana("teclado", w)
        no_activar(w)
        self._en_pausa = False
        self._pintar_todo()
        self._preparar_barrido()

    def reconstruir(self):
        """Opciones guardadas (distribución, barrido, tamaño...): se rehace la ventana."""
        self.barrido_activo = bool(self.cfg["teclado"].get("barrido")) or self.solo_comunicacion
        if self.prediccion is not None:
            self.prediccion.aprender_activo = bool(self.cfg["teclado"].get("aprender", True))
        self.construir()

    def _fuente(self, ident: str):
        if ident.startswith("tecla:"):
            return self.f_tecla
        if ident.startswith("frase:"):
            return self.f_frase
        return self.f_accion

    def _crear_texto(self, caja):
        T = self.tema
        pt = int(self.cfg["teclado"].get("letra_pt", 28))
        marco = tk.Frame(self.win, bg=T.texto, bd=0)
        marco.place(x=caja.x, y=caja.y, width=caja.ancho, height=caja.alto)
        self.txt = tk.Text(marco, bg="#ffffff", fg="#000000", font=letra(self.cfg, pt, False, minimo=18),
                           wrap="word", bd=0, padx=10, pady=4, highlightthickness=0, cursor="arrow",
                           takefocus=0)
        self.txt.pack(fill="both", expand=True, padx=3, pady=3)
        self.txt.tag_configure("guia", foreground="#4a4a4a")
        self.txt.tag_configure("pendiente", foreground="#8a4b00")
        self.txt.configure(state="disabled")
        self.caja_texto = caja

    # ------------------------------------------------------------ pintar
    def _pintar_todo(self):
        T = self.tema
        for ident, b in self.botones.items():
            if ident.startswith("tecla:"):
                continue
            if ident.startswith("accion:"):
                nombre = ident.split(":", 1)[1]
                b.poner_texto(*self._texto_accion(nombre))
        self._pintar_rapidas()
        if self.pagina == "frases":
            for ident, i in self._cats_visibles.items():
                b = self.botones.get(ident)
                if b is not None:
                    b.poner_texto(self.frases.nombres()[i])
                    b.poner_color(T.acento if i == self.cat else None)
            for ident, fr in self._frases_visibles.items():
                b = self.botones.get(ident)
                if b is not None:
                    b.poner_texto(self._texto_frase(fr))
                    b.poner_color(T.rojo if fr.get("urgente") else None)
        self._pintar_texto()

    def _texto_accion(self, nombre: str):
        if nombre == "frases" and self.pagina == "frases":
            clave = "letras"
        elif nombre == "barrido" and self.barrido_activo:
            clave = "salir_barrido"
        elif nombre == "escribir" and self._directo():
            clave = "nuevo"
        elif nombre == "mas_frases":
            return t("tec_mas_frases"), "▶"
        elif nombre == "mas_categorias":
            return t("tec_mas_categorias"), "▶"
        else:
            clave = nombre
        return t(f"tec_{clave}"), t(f"icono_tec_{clave}")

    def _texto_frase(self, fr: dict) -> str:
        tc = self.cfg["teclado"]
        return texto_final(fr.get("texto", ""), tc.get("genero", "neutro"), tc.get("cuidador", "alguien"))

    def _pintar_rapidas(self):
        T = self.tema
        si, no = self.botones.get("frase:si"), self.botones.get("frase:no")
        if si is not None:
            si.poner_texto(t("tec_si_borrar") if self.confirmando else t("tec_si"))
            si.poner_color(T.verde)
        if no is not None:
            no.poner_texto(t("tec_no_borrar") if self.confirmando else t("tec_no"))
            no.poner_color(T.rojo)
        rapidas = self.frases.rapidas(N_RAPIDAS)
        for i in range(N_RAPIDAS):
            b = self.botones.get(f"frase:rapida:{i}")
            if b is None:
                continue
            if i < len(rapidas):
                b.poner_texto(self._texto_frase(rapidas[i]))
                b.poner_color(T.rojo if rapidas[i].get("urgente") else None)
            else:
                b.poner_texto("")
            self._activar(f"frase:rapida:{i}", i < len(rapidas))

    def _activar(self, ident: str, si: bool):
        for e in self.app.registro.entradas:
            if e.ident == ident:
                e.activo = si

    def _pintar_texto(self):
        e = self.escritura
        try:
            self.txt.configure(state="normal")
            self.txt.delete("1.0", "end")
            if self.confirmando:
                self.txt.insert("end", t("tec_limpiar_pregunta"), "pendiente")
            elif e.texto:
                self.txt.insert("end", e.texto)
                marca = "´" if e.tilde == 1 else ("¨" if e.tilde == 2 else ("⇧" if e.mayus else ""))
                self.txt.insert("end", marca + "▏", "pendiente")
            else:
                self.txt.insert("end", t("tec_vacio_barrido") if self.barrido_activo else t("tec_vacio"), "guia")
            self.txt.see("end")
            self.txt.configure(state="disabled")
        except tk.TclError:
            pass
        self._pintar_letras()
        self._pintar_sugerencias()
        for nombre, b in (("tilde", self.botones.get("tecla:tilde")), ("mayus", self.botones.get("tecla:mayus"))):
            if b is not None:
                pendiente = (e.tilde > 0) if nombre == "tilde" else e.mayus
                b.poner_color(self.tema.ambar if pendiente else None)

    def _pintar_letras(self):
        mayus = self.escritura.proxima_mayuscula()
        clave = (mayus, self.escritura.tilde)
        if getattr(self, "_clave_letras", None) == clave and getattr(self, "_win_letras", None) is self.win:
            return
        self._clave_letras, self._win_letras = clave, self.win
        for ident, b in self.botones.items():
            if not ident.startswith("tecla:"):
                continue
            tec = buscar_tecla(ident)
            if tec is None:
                continue
            if tec.tipo == "letra":
                v = tec.valor
                if self.escritura.tilde == 1:
                    v = {"a": "á", "e": "é", "i": "í", "o": "ó", "u": "ú"}.get(v, v)
                elif self.escritura.tilde == 2 and v == "u":
                    v = "ü"
                b.poner_texto(v.upper() if mayus else v)
            else:
                b.poner_texto(tec.texto)

    def _pintar_sugerencias(self):
        e = self.escritura
        try:
            sug = self.prediccion.sugerir(e.palabra_actual(), e.palabra_anterior()) if self.prediccion else []
        except Exception:  # noqa: BLE001
            log.exception("La predicción falló")
            sug = []
        mayus = (e.palabra_actual()[:1].isupper()) or (not e.palabra_actual() and e.proxima_mayuscula())
        self._sugerencias = sug
        for i in range(N_SUGERENCIAS):
            b = self.botones.get(f"sugerencia:{i}")
            if b is None:
                continue
            if i < len(sug):
                p = sug[i]
                b.poner_texto(p[:1].upper() + p[1:] if mayus else p)
            else:
                b.poner_texto("")
            self._activar(f"sugerencia:{i}", i < len(sug))
        if self.barrido is not None:
            self._preparar_barrido(conservar=True)

    def mostrar_grande(self, texto: str, segundos: float = GRANDE_S):
        c = self.caja_texto
        try:
            self.lbl_grande.configure(text=texto, wraplength=max(c.ancho - 32, 100))
            self.lbl_grande.place(x=c.x, y=c.y, width=c.ancho, height=c.alto)
            self.lbl_grande.lift()
        except tk.TclError:
            return
        self._grande_hasta = _ahora() + segundos

    def _ocultar_grande(self):
        self._grande_hasta = None
        try:
            self.lbl_grande.place_forget()
        except tk.TclError:
            pass

    # ------------------------------------------------------------ barrido
    def filas_barrido(self) -> list[list[str]]:
        """Orden del barrido: frases rápidas (empieza por Sí y No), sugerencias, letras (o frases),
        Hablar/Repetir/Escribir y acciones."""
        activos = {e.ident for e in self.app.registro.entradas if e.activo}
        d = self.disp
        filas = []
        rap = [c.id for c in d.fila("rapidas")]
        rap = [i for i in rap if i in activos]
        # Sí y No primero
        filas.append([i for i in ("frase:si", "frase:no") if i in rap] + [i for i in rap if i not in ("frase:si", "frase:no")])
        filas.append([c.id for c in d.fila("sugerencias") if c.id in activos])
        for nombre, fila in d.filas:
            if nombre.startswith("cuerpo:"):
                filas.append([c.id for c in fila if c.id in activos])
        filas.append([f"accion:{a}" for a in ACCIONES_TEXTO])
        # Quien depende del barrido (Opciones: Barrido o Solo comunicación) no puede volver solo si
        # lo saca del barrido o cierra el teclado: esas dos acciones no entran al barrido (el
        # cuidador las tiene con el ratón). "Pausa" sí: se quita con dos parpadeos largos.
        fuera = ("accion:barrido", "accion:cerrar") if self._depende_del_barrido() else ()
        filas.append([c.id for c in d.fila("acciones") if c.id in activos and c.id not in fuera])
        return [f for f in filas if f]

    def _depende_del_barrido(self) -> bool:
        tec = self.cfg["teclado"]
        return bool(tec.get("barrido")) or self.solo_comunicacion

    def _preparar_barrido(self, conservar: bool = False):
        if not self.barrido_activo:
            self.barrido = None
            self._pintar_barrido(None)
            return
        filas = self.filas_barrido()
        paso = float(self.cfg["teclado"].get("barrido_paso_s", 1.5))
        if self.barrido is None:
            self.barrido = Barrido(filas, paso, _ahora())
        else:
            self.barrido.cambiar_paso(paso)
            self.barrido.poner_filas(filas, _ahora(), conservar=conservar)

    def _pintar_barrido(self, est):
        nuevos = set(est.resaltado) if est is not None else set()
        for ident in self._resaltados - nuevos:
            b = self.botones.get(ident)
            if b is not None:
                b.activo(False)
        for ident in nuevos - self._resaltados:
            b = self.botones.get(ident)
            if b is not None:
                b.activo(True)
        self._resaltados = nuevos
        volver = est is not None and est.volver
        if volver:
            try:
                fila = self.barrido.filas[est.fila]
                ultimo = self.botones.get(fila[-1])
                if ultimo is not None:
                    x, y = ultimo.winfo_x(), ultimo.winfo_y()
                    w, h = ultimo.winfo_width(), ultimo.winfo_height()
                    self.lbl_volver.place(x=x, y=y, width=max(w, 120), height=h)
                    self.lbl_volver.lift()
            except (tk.TclError, IndexError):
                pass
        elif self._volver_visible:
            try:
                self.lbl_volver.place_forget()
            except tk.TclError:
                pass
        self._volver_visible = volver
        detenido = est is not None and est.detenido
        if detenido != getattr(self, "_detenido_mostrado", False):
            self._detenido_mostrado = detenido
            if detenido:
                self.mostrar_grande(t("tec_barrido_detenido"), 3600)
            else:
                self._ocultar_grande()

    def _atender_estado_barrido(self, est):
        self._pintar_barrido(est)
        if est.elegido and est.elegido != VOLVER:
            self.app.registro.elegir(est.elegido, "cabeza")

    def _evento_barrido(self, ident: str) -> bool:
        """``barrido:elegir`` (parpadeo largo o gesto de clic) y ``barrido:siguiente``."""
        if self.barrido is None:
            return False
        ev = "elegir" if ident.endswith("elegir") else ("siguiente" if ident.endswith("siguiente") else None)
        if ev is None:
            return False
        ojos = False
        v = getattr(self.app, "ultima_vista", None)
        m = getattr(v, "maquina", None)
        if m is not None:
            ojos = bool(m.gestos.ojos_cerrados)
        est = self.barrido.actualizar(_ahora(), ojos, ev)
        self._atender_estado_barrido(est)
        return True

    # ------------------------------------------------------------ cada refresco
    def _pintar_pausa(self, en_pausa: bool, con_parpadeo: bool = False):
        """En pausa el botón "Pausa" del teclado se vuelve "Reanudar" (el teclado puede tapar la
        ventana principal): es el objetivo ``teclado:reanudar`` que atiende la máquina (2 s quieto)."""
        if en_pausa == self._en_pausa:
            return
        self._en_pausa = en_pausa
        # quien usa el barrido no puede elegir "Reanudar" con la cabeza: se le dice cómo seguir
        if en_pausa and con_parpadeo:
            self.mostrar_grande(t("sub_PAUSA_parpadeo"), 3600)
            self._grande_pausa = True
        elif not en_pausa and getattr(self, "_grande_pausa", False):
            self._grande_pausa = False
            self._ocultar_grande()
        b = self.botones.get("accion:pausa")
        if b is None:
            return
        reg = self.app.registro
        if en_pausa:
            reg.cambiar_id(b, "teclado:reanudar", interno=True)
            b.poner_texto(t("btn_reanudar"), t("icono_reanudar"))
            b.poner_color(self.tema.verde)
        else:
            reg.cambiar_id(b, "accion:pausa", accion=(lambda: self.elegir("accion:pausa")), interno=False)
            b.poner_texto(*self._texto_accion("pausa"))
            b.poner_color(None)
        b.comando = reg.comando("teclado:reanudar" if en_pausa else "accion:pausa")

    def actualizar(self, vista):
        if self.win is None:
            return
        ahora = _ahora()
        if self._grande_hasta is not None and ahora >= self._grande_hasta:
            self._ocultar_grande()
        m0 = getattr(vista, "maquina", None) if vista is not None else None
        if m0 is not None:
            self._pintar_pausa(m0.estado == K.PAUSA, bool(getattr(m0, "reanuda_parpadeo", False)))
        if self.barrido is None:
            return
        m = getattr(vista, "maquina", None) if vista is not None else None
        if m is None or m.estado != K.ACTIVO:
            # en pausa o sin cara el barrido no avanza (el tiempo no cuenta)
            self.barrido._t = ahora
            return
        est = self.barrido.actualizar(ahora, bool(m.gestos.ojos_cerrados), None)
        self._atender_estado_barrido(est)

    # ------------------------------------------------------------ elegir
    def elegir(self, ident: str):
        if self.win is None:
            return
        if self._grande_hasta is not None and not getattr(self, "_detenido_mostrado", False):
            self._ocultar_grande()
        try:
            if ident.startswith("tecla:"):
                self._tecla(ident)
            elif ident.startswith("sugerencia:"):
                self._sugerencia(int(ident.split(":")[1]))
            elif ident in ("frase:si", "frase:no"):
                self._si_no(ident == "frase:si")
            elif ident.startswith("frase:rapida:"):
                rap = self.frases.rapidas(N_RAPIDAS)
                i = int(ident.rsplit(":", 1)[1])
                if i < len(rap):
                    self.decir_frase(rap[i])
            elif ident.startswith("frase:cat:"):
                self.cat = int(ident.rsplit(":", 1)[1])
                self.frase_pagina = 0
                self.construir()
            elif ident.startswith("frase:"):
                fr = self._frases_visibles.get(ident)
                if fr is not None:
                    self.decir_frase(fr)
            elif ident.startswith("accion:"):
                self.accion(ident.split(":", 1)[1])
        except Exception:  # noqa: BLE001
            log.exception("Error en el teclado")

    def _aplicar(self, cambio):
        if self._directo() and not cambio.vacio:
            self._enviar_cambio(cambio)
        self._pintar_texto()

    def _tecla(self, ident: str):
        tec = buscar_tecla(ident)
        if tec is None:
            return
        if self.confirmando:
            self.confirmando = False
        e = self.escritura
        anterior, palabra = e.palabra_anterior(), e.palabra_actual()
        cambio = e.pulsar(tec)
        if tec.tipo in ("espacio", "enter") or (tec.tipo == "signo" and tec.valor in ".,?!"):
            if palabra and self.prediccion is not None:
                self.prediccion.aprender_par(anterior, palabra)
        self._aplicar(cambio)

    def _sugerencia(self, i: int):
        if i >= len(self._sugerencias):
            return
        e = self.escritura
        anterior = e.palabra_anterior()
        p = self._sugerencias[i]
        cambio = e.elegir_sugerencia(p)
        if self.prediccion is not None:
            self.prediccion.aprender_par(anterior, p)
        self._aplicar(cambio)

    def _si_no(self, si: bool):
        if self.confirmando:
            self.confirmando = False
            if si:
                self._aplicar(self.escritura.limpiar())
            self._pintar_rapidas()
            self._pintar_texto()
            return
        self.decir(t("tec_si") if si else t("tec_no"), siempre=False)

    def decir(self, texto: str, urgente: bool = False, siempre: bool = True):
        """Dice en voz alta (si corresponde) y muestra en grande."""
        texto = (texto or "").strip()
        if not texto:
            return
        self.ultimo_dicho = texto
        self.mostrar_grande(texto)
        if siempre or self.cfg["voz"].get("hablar_frases", True):
            self.app.hablar(texto, urgente=urgente)

    def decir_frase(self, fr: dict):
        self.decir(self._texto_frase(fr), urgente=bool(fr.get("urgente")), siempre=False)

    def _aprender_ultima(self):
        e = self.escritura
        if self.prediccion is not None and e.palabra_actual():
            self.prediccion.aprender_par(e.palabra_anterior(), e.palabra_actual())

    def accion(self, nombre: str):
        e = self.escritura
        if nombre != "limpiar" and self.confirmando and nombre not in ("pausa",):
            self.confirmando = False
            self._pintar_rapidas()
        if nombre == "borrar":
            self._aplicar(e.borrar())
        elif nombre == "palabra":
            self._aplicar(e.borrar_palabra())
        elif nombre == "deshacer":
            self._aplicar(e.deshacer())
        elif nombre == "limpiar":
            if e.texto:
                self.confirmando = True
                self._pintar_rapidas()
                self._pintar_texto()
        elif nombre == "hablar":
            texto = e.texto.strip()
            if not texto:
                self.mostrar_grande(t("tec_nada_que_decir"), 3)
                return
            self._aprender_ultima()
            self.ultimo_dicho = texto
            self.app.hablar(texto)
            self._guardar_palabras()
        elif nombre == "repetir":
            if self.ultimo_dicho:
                self.app.hablar(self.ultimo_dicho)
                self.mostrar_grande(self.ultimo_dicho)
            else:
                self.mostrar_grande(t("tec_nada_que_decir"), 3)
        elif nombre == "escribir":
            self._escribir()
        elif nombre == "copiar":
            self._copiar()
        elif nombre == "frases":
            self.pagina = "letras" if self.pagina == "frases" else "frases"
            self.frase_pagina = 0
            self.construir()
        elif nombre == "mas_frases":
            self.frase_pagina += 1
            self.construir()
        elif nombre == "mas_categorias":
            self.cat_pagina += 1
            self.construir()
        elif nombre == "barrido":
            if self.solo_comunicacion:
                self.mostrar_grande(t("tec_solo_com_cerrar"), 5)
                return
            self.barrido_activo = not self.barrido_activo
            self.construir()
            self.app.orden("submodo", self.submodo_inicial())
        elif nombre == "pausa":
            self.app.pausar()
        elif nombre == "cerrar":
            if self.solo_comunicacion:
                self.mostrar_grande(t("tec_solo_com_cerrar"), 5)
                return
            self.app.cerrar_teclado()

    # ------------------------------------------------------------ hacia otros programas
    def _devolver_foco(self):
        if not getattr(self.app, "sistema", False):
            return
        hwnd = getattr(self.app, "ultima_externa", None)
        if not hwnd:
            return
        try:
            from ..sistema import ventanas_win as vw
            if vw.devolver_foco(hwnd):
                self.app.salida.foco_propio = False
        except Exception:  # noqa: BLE001
            log.exception("No se pudo devolver el foco")

    def _escribir(self):
        e = self.escritura
        if self._directo():
            # lo escrito ya está en el otro programa: se empieza un mensaje nuevo sin borrar allá
            if e.texto:
                self._aprender_ultima()
                e.nuevo_mensaje()
                self._pintar_texto()
                self.mostrar_grande(t("tec_nuevo_mensaje"), 3)
            return
        texto = e.texto
        if not texto.strip():
            self.mostrar_grande(t("tec_nada_que_decir"), 3)
            return
        self._aprender_ultima()
        self._devolver_foco()
        self.app.motor.escribir(texto)
        self._guardar_palabras()

    def _enviar_cambio(self, cambio):
        self._devolver_foco()
        for _ in range(min(cambio.borrar, MAX_RETROCESOS)):
            self.app.orden("tecla_vk", K.VK_BACK)
        if cambio.texto:
            self.app.motor.escribir(cambio.texto)

    def _copiar(self):
        texto = self.escritura.texto
        if not texto.strip():
            self.mostrar_grande(t("tec_nada_que_decir"), 3)
            return
        ok = False
        try:
            if getattr(self.app, "sistema", False):
                from ..sistema import portapapeles
                ok = portapapeles.copiar(texto)
            else:
                f = getattr(self.app, "copiar_prueba", None)
                ok = bool(f(texto)) if f is not None else False
        except Exception:  # noqa: BLE001
            log.exception("No se pudo copiar")
        self.mostrar_grande(t("tec_copiado") if ok else t("tec_no_copiado"), 4)

    def _guardar_palabras(self):
        if self.prediccion is not None:
            try:
                self.prediccion.guardar()
            except Exception:  # noqa: BLE001
                log.exception("No se pudieron guardar las palabras")

    # ------------------------------------------------------------ cerrar
    def cerrar(self):
        self._guardar_palabras()
        reg = self.app.registro
        reg.manejadores = [(p, f) for p, f in reg.manejadores if p != "barrido:"]
        self.destruir_ventana()
        self.barrido = None


def _ahora() -> float:
    """Reloj del teclado (las pruebas lo reemplazan para manejar el barrido)."""
    return time.monotonic()


def _obtener(app, nombre):
    f = getattr(app, nombre, None)
    if f is None:
        return None
    try:
        return f()
    except Exception:  # noqa: BLE001
        log.exception("No se pudo preparar %s", nombre)
        return None
