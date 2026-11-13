"""Editor de frases rápidas (sección 7.4), pensado para el cuidador con teclado y ratón: agregar,
cambiar, borrar y ordenar frases; crear, renombrar y borrar categorías; volver a las de fábrica;
y "Olvidar las palabras aprendidas" (con confirmación).

La ventana SÍ toma el foco (hay que escribir en ella). Se registra como ``ventana:editor`` para que
la cabeza nunca haga clic encima; sus botones también se pueden elegir con la cabeza.
"""
from __future__ import annotations

import logging
import tkinter as tk

from .comun import BotonGrande, area_libre, letra, poner_icono, tema
from .textos import t

log = logging.getLogger("lycan")


class EditorFrases:
    def __init__(self, root, app):
        self.root = root
        self.app = app
        self.frases = app.obtener_frases()
        self.cat = 0
        self.preguntando = None          # "fabrica" | "olvidar" | None
        cfg = app.cfg.datos
        T = self.tema = tema(cfg)
        reg = app.registro
        w = self.win = tk.Toplevel(root)
        w.title(t("ed_titulo"))
        w.configure(bg=T.fondo)
        w.attributes("-topmost", True)
        poner_icono(w)
        w.protocol("WM_DELETE_WINDOW", self.cerrar)
        f16, f16n = letra(cfg, 16, True), letra(cfg, 16)
        tk.Label(w, text=t("ed_titulo"), bg=T.fondo, fg=T.texto, font=letra(cfg, 22, True)).pack(anchor="w", padx=16,
                                                                                               pady=(12, 0))
        tk.Label(w, text=t("ed_ayuda"), bg=T.fondo, fg=T.texto_suave, font=f16n, wraplength=900,
                 justify="left").pack(anchor="w", padx=16, pady=(4, 8))
        cuerpo = tk.Frame(w, bg=T.fondo)
        cuerpo.pack(fill="both", expand=True, padx=16)
        # categorías
        izq = tk.Frame(cuerpo, bg=T.fondo)
        izq.pack(side="left", fill="y")
        tk.Label(izq, text=t("ed_categorias"), bg=T.fondo, fg=T.acento, font=f16).pack(anchor="w")
        self.lst_cat = tk.Listbox(izq, font=f16n, width=18, height=9, exportselection=False, bg="#ffffff",
                                  fg="#000000", selectbackground=T.acento, selectforeground="#000000")
        self.lst_cat.pack(fill="y", expand=True, pady=4)
        self.lst_cat.bind("<<ListboxSelect>>", self._cat_elegida)
        # frases
        der = tk.Frame(cuerpo, bg=T.fondo)
        der.pack(side="left", fill="both", expand=True, padx=(16, 0))
        tk.Label(der, text=t("ed_frases"), bg=T.fondo, fg=T.acento, font=f16).pack(anchor="w")
        self.lst = tk.Listbox(der, font=f16n, width=48, height=9, exportselection=False, bg="#ffffff",
                              fg="#000000", selectbackground=T.acento, selectforeground="#000000")
        self.lst.pack(fill="both", expand=True, pady=4)
        self.lst.bind("<<ListboxSelect>>", self._frase_elegida)
        fila = tk.Frame(der, bg=T.fondo)
        fila.pack(fill="x", pady=4)
        tk.Label(fila, text=t("ed_texto"), bg=T.fondo, fg=T.texto, font=f16).pack(side="left")
        self.var = tk.StringVar()
        self.entrada = tk.Entry(fila, textvariable=self.var, font=f16n, bg="#ffffff", fg="#000000",
                                insertbackground="#000000")
        self.entrada.pack(side="left", fill="x", expand=True, padx=8)
        self.var_urg = tk.BooleanVar(value=False)
        tk.Checkbutton(der, text=t("ed_urgente"), variable=self.var_urg, bg=T.fondo, fg=T.texto,
                       selectcolor=T.fondo_2, activebackground=T.fondo, activeforeground=T.texto,
                       font=f16n).pack(anchor="w")
        self.lbl_aviso = tk.Label(w, text="", bg=T.fondo, fg=T.ambar, font=f16, wraplength=900, justify="left")
        self.lbl_aviso.pack(anchor="w", padx=16, pady=4)
        # botones
        self.botones = {}
        for fila_ids in (("agregar", "cambiar", "borrar", "subir", "bajar"),
                         ("nueva_cat", "renombrar", "borrar_cat", "fabrica", "olvidar"),
                         ("guardar", "cerrar")):
            fr = tk.Frame(w, bg=T.fondo)
            fr.pack(fill="x", padx=16, pady=4)
            for ident in fila_ids:
                texto = t("btn_guardar") if ident == "guardar" else (t("btn_cerrar") if ident == "cerrar"
                                                                    else t(f"ed_{ident}"))
                b = BotonGrande(fr, texto, reg.comando(f"ed:{ident}"), T, f16)
                b.pack(side="left", padx=4)
                reg.agregar(f"ed:{ident}", b, getattr(self, ident))
                self.botones[ident] = b
        self._pintar()
        w.update_idletasks()
        try:
            l, a, d, ab = area_libre(app, w)
            ww, hh = w.winfo_reqwidth(), w.winfo_reqheight()
            w.geometry(f"+{l + max((d - l - ww) // 2, 0)}+{a + max((ab - a - hh) // 2, 0)}")
        except tk.TclError:
            pass
        reg.ventana("editor", w)

    # ------------------------------------------------------------ pintar
    def _pintar(self, elegir: int | None = None):
        self.lst_cat.delete(0, "end")
        for n in self.frases.nombres():
            self.lst_cat.insert("end", n)
        self.cat = min(self.cat, len(self.frases.nombres()) - 1)
        self.lst_cat.selection_clear(0, "end")
        self.lst_cat.selection_set(self.cat)
        self.lst.delete(0, "end")
        for fr in self.frases.frases(self.cat):
            self.lst.insert("end", ("⚠ " if fr.get("urgente") else "") + fr["texto"])
        if elegir is not None and 0 <= elegir < self.lst.size():
            self.lst.selection_set(elegir)
            self.lst.see(elegir)

    def _aviso(self, clave: str):
        self.lbl_aviso.configure(text=t(clave) if clave else "")

    def _sel(self) -> int | None:
        s = self.lst.curselection()
        return int(s[0]) if s else None

    def _cat_elegida(self, _e=None):
        s = self.lst_cat.curselection()
        if s:
            self.cat = int(s[0])
            self._pintar()
            if self.preguntando is None:
                self._aviso("")

    def _frase_elegida(self, _e=None):
        i = self._sel()
        if i is None:
            return
        fr = self.frases.frases(self.cat)[i]
        self.var.set(fr["texto"])
        self.var_urg.set(bool(fr.get("urgente")))

    # ------------------------------------------------------------ acciones
    def _resultado(self, ok: bool, elegir: int | None = None, clave_mal: str = "ed_no_valido"):
        self.preguntando = None
        self._pintar(elegir)
        self._aviso("" if ok else clave_mal)

    def agregar(self):
        ok = self.frases.agregar(self.cat, self.var.get(), self.var_urg.get())
        self._resultado(ok, len(self.frases.frases(self.cat)) - 1,
                        "ed_limite" if len(self.frases.frases(self.cat)) >= 40 else "ed_no_valido")
        if ok:
            self.var.set("")

    def cambiar(self):
        i = self._sel()
        if i is None:
            return
        self._resultado(self.frases.cambiar(self.cat, i, self.var.get(), self.var_urg.get()), i)

    def borrar(self):
        i = self._sel()
        if i is None:
            return
        self._resultado(self.frases.borrar(self.cat, i), max(i - 1, 0))

    def subir(self):
        i = self._sel()
        if i is not None:
            self._resultado(True, self.frases.mover(self.cat, i, -1))

    def bajar(self):
        i = self._sel()
        if i is not None:
            self._resultado(True, self.frases.mover(self.cat, i, +1))

    def nueva_cat(self):
        ok = self.frases.agregar_categoria(self.var.get())
        if ok:
            self.cat = len(self.frases.nombres()) - 1
            self.var.set("")
        self._resultado(ok, None, "ed_limite" if len(self.frases.nombres()) >= 12 else "ed_no_valido")

    def renombrar(self):
        self._resultado(self.frases.renombrar_categoria(self.cat, self.var.get()))

    def borrar_cat(self):
        ok = self.frases.borrar_categoria(self.cat)
        self.cat = max(self.cat - 1, 0)
        self._resultado(ok, None, "ed_limite")

    def fabrica(self):
        if self.preguntando != "fabrica":
            self.preguntando = "fabrica"
            self._aviso("ed_fabrica_pregunta")
            self.botones["fabrica"].poner_color(self.tema.ambar)
            return
        self.frases.restaurar()
        self.cat = 0
        self.botones["fabrica"].poner_color(None)
        self._resultado(True)

    def olvidar(self):
        if self.preguntando != "olvidar":
            self.preguntando = "olvidar"
            self._aviso("ed_olvidar_pregunta")
            self.botones["olvidar"].poner_color(self.tema.ambar)
            return
        self.preguntando = None
        self.botones["olvidar"].poner_color(None)
        p = getattr(self.app, "obtener_prediccion", lambda: None)()
        ok = p.olvidar() if p is not None else True
        self._aviso("ed_olvidadas" if ok else "ed_no_guardo")

    def guardar(self):
        ok = self.frases.guardar()
        self._aviso("ed_guardado" if ok else "ed_no_guardo")
        tec = getattr(self.app, "teclado", None)
        if ok and tec is not None and hasattr(tec, "construir"):
            try:
                tec.construir()
            except Exception:  # noqa: BLE001
                log.exception("No se pudo rehacer el teclado")
        return ok

    def cerrar(self):
        # lo que no se guardó se descarta: se vuelve a leer el archivo
        try:
            self.frases.cargar()
        except Exception:  # noqa: BLE001
            pass
        try:
            self.win.destroy()
        except tk.TclError:
            pass
        f = getattr(self.app, "editor_cerrado", None)
        if f is not None:
            f(self)
