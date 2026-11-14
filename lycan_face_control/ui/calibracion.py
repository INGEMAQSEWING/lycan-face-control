"""Calibración guiada (secciones 4.1 y 6.5): ventana grande con instrucciones, un dibujo de la cara
que muestra qué hacer, la silueta en vivo y una barra de avance.

- Presentación con «Empezar» (elegible con la cabeza: la máquina sigue activa).
- Al empezar, la máquina pasa a CALIBRANDO (suelta todo y no envía nada a Windows) y el motor
  entrega las medidas por ``motor.cola_calibracion``; ``calibracion_guiada.Guia`` decide los pasos,
  que **avanzan solos** (sin manos). El cuidador puede repetir un paso, volver atrás u omitir la
  prueba de un gesto con el ratón.
- Al terminar se guarda la calibración en el perfil activo y se hace la **prueba final**: cuatro
  círculos que se eligen con la cabeza (ya con el puntero calibrado). Luego «Terminar» o
  «Repetir la calibración».
- «Cancelar» devuelve todo como estaba.
- Con el barrido o «Solo comunicación» (quien solo parpadea): el paso «Parpadeo largo» muestra la
  barra del cierre (verde = ya puede abrir los ojos) y cuántos se reconocieron; la prueba final no
  son círculos para la cabeza sino el resultado de ese paso, y la ventana se cierra sola.
- 1.1 paquete C: en la presentación, «Mover el puntero con» (La cabeza / Los ojos / Ojos y
  cabeza). Con los ojos se agregan los pasos de la mirada, que se muestran a pantalla completa
  (``calibracion_mirada.VentanaMirada``); al final se dice en palabras cuánto se equivocan los ojos.
  La fuente elegida se guarda solo al terminar (con «Cancelar» no cambia nada).
"""
from __future__ import annotations

import copy
import logging
import queue
import tkinter as tk
import tkinter.font as tkfont

from ..calibracion_guiada import PARPADEOS_LARGOS, PASOS_MIRADA, Guia
from ..config import FUENTES, PARPADEO_LARGO_PISO_MS, validar
from ..mapeo import MONITOR_REFERENCIA
from .comun import BotonGrande, area_libre, boton_ayuda, dibujar_cara, dibujar_puntos, letra, no_activar, tema
from .textos import t

log = logging.getLogger("lycan")

SELECTOR_IPADY = 12         # ◀ y ▶ de la presentación: al menos 72 px de alto
REFRESCO_MS = 50
DIBUJO = {"posicion": ("reposo", None), "centro": ("reposo", None), "izq": ("mirar", "izq"),
          "der": ("mirar", "der"), "arr": ("mirar", "arr"), "aba": ("mirar", "aba"), "reposo": ("reposo", None),
          "parpadeo": ("ojos", None), "parpadeo_largo": ("ojos", None), "gesto_boca": ("boca", None), "gesto_cejas": ("cejas", None),
          "gesto_sonrisa": ("sonrisa", None),
          # 1.1 paquete C
          "mirada_centro": ("reposo", None), "mirada_puntos": ("reposo", None),
          "mirada_cabeza": ("reposo", None), "mirada_validar": ("reposo", None)}
N_OBJETIVOS = 4
CIERRE_SOLO_MS = 12000          # con barrido: la prueba final se cierra sola (la persona no tiene manos)


class VentanaCalibracion:
    def __init__(self, root, app, al_terminar=None, empezar_ya: bool = False):
        self.root = root
        self.app = app
        self.al_terminar = al_terminar
        self.guia: Guia | None = None
        self.fase = "intro"            # intro | pasos | final | cerrada
        self.alcanzados: set = set()
        self.pocos: list = []
        self._ult_t = None
        self._ult_medidas = None
        # 1.1 paquete C: con qué se moverá el puntero (se guarda solo al terminar)
        self.fuente = (app.cfg.datos.get("puntero") or {}).get("fuente", "cabeza")
        if self.fuente not in FUENTES:
            self.fuente = "cabeza"
        self.ventana_mirada = None
        self.texto_mirada = None
        T = self.tema = tema(app.cfg.datos)
        w = self.win = tk.Toplevel(root)
        w.title(t("cal_titulo"))
        w.configure(bg=T.fondo)
        w.attributes("-topmost", True)
        w.protocol("WM_DELETE_WINDOW", self.cancelar)
        l, a, d, ab = area_libre(app, root)
        self.W = min(int((d - l) * 0.86), 1100)
        self.H = min(int((ab - a) * 0.9), 720)
        w.geometry(f"{self.W}x{self.H}+{l + (d - l - self.W) // 2}+{a + (ab - a - self.H) // 2}")
        w.resizable(False, False)
        self.cuerpo = tk.Frame(w, bg=T.fondo)
        self.cuerpo.pack(fill="both", expand=True, padx=16, pady=12)
        app.registro.ventana("calibracion", w)
        self._pantalla_intro()
        no_activar(w)
        self._loop = w.after(REFRESCO_MS, self._refrescar)
        if empezar_ya:
            self.empezar()

    @property
    def cfg(self):
        return self.app.cfg.datos

    # ------------------------------------------------------------ pantallas
    def _limpiar(self):
        for c in self.cuerpo.winfo_children():
            c.destroy()

    def _boton(self, padre, clave_texto, ident, accion, color=None, **pack):
        b = BotonGrande(padre, t(clave_texto) if clave_texto in _TXT_KEYS() else clave_texto,
                        self.app.registro.comando(ident), self.tema, letra(self.cfg, 18, True), color=color)
        self.app.registro.agregar(ident, b, accion)
        if pack:
            b.pack(**pack)
        return b

    def _pantalla_intro(self):
        """Presentación. Revisión de la 1.1: los botones (Empezar/Cancelar y el selector ◀ ▶) se
        empacan primero, así nunca son lo que se recorta en una pantalla chica; el dibujo de la cara
        se achica (o no va) si falta alto, y la etiqueta del selector tiene ancho fijo para que ◀ y ▶
        no cambien de lugar bajo el puntero al elegir."""
        self._limpiar()
        T = self.tema
        fila = tk.Frame(self.cuerpo, bg=T.fondo)
        fila.pack(side="bottom", fill="x", pady=8)
        # 1.1 paquete C: «Mover el puntero con  ◀ La cabeza ▶»
        sel = tk.Frame(self.cuerpo, bg=T.fondo)
        sel.pack(side="bottom", pady=4)
        f18 = letra(self.cfg, 18)
        f18b = letra(self.cfg, 18, True)
        tk.Label(sel, text=t("cal_fuente"), bg=T.fondo, fg=T.texto, font=f18).pack(side="left", padx=8)
        self._boton(sel, "◀", "cal:fuente:menos", lambda e=None: self.cambiar_fuente(-1), side="left", padx=4,
                    ipady=SELECTOR_IPADY, ipadx=8)
        medida = tkfont.Font(root=self.root, font=f18b)
        ancho = max(medida.measure(t(f"op_fuente_{f}")) for f in FUENTES) + 16
        caja = tk.Frame(sel, bg=T.fondo, width=ancho, height=medida.metrics("linespace") + 8)
        caja.pack_propagate(False)
        caja.pack(side="left", padx=8)
        self.lbl_fuente = tk.Label(caja, text=t(f"op_fuente_{self.fuente}"), bg=T.fondo, fg=T.acento, font=f18b)
        self.lbl_fuente.pack(expand=True)
        self._boton(sel, "▶", "cal:fuente:mas", lambda e=None: self.cambiar_fuente(+1), side="left", padx=4,
                    ipady=SELECTOR_IPADY, ipadx=8)
        self._boton(fila, "cal_empezar", "cal:empezar", self.empezar, color=T.verde, side="left", expand=True,
                    fill="x", padx=8)
        self._boton(fila, "btn_cancelar", "cal:cancelar", self.cancelar, side="left", expand=True, fill="x", padx=8)
        boton_ayuda(fila, t("cal_ayuda"), self.cfg, T).pack(side="left", padx=8)
        tk.Label(self.cuerpo, text=t("cal_intro_titulo"), bg=T.fondo, fg=T.texto, font=letra(self.cfg, 26, True),
                 wraplength=self.W - 60, justify="center").pack(pady=(10, 10))
        tk.Label(self.cuerpo, text=t("cal_intro"), bg=T.fondo, fg=T.texto, font=f18,
                 wraplength=self.W - 80, justify="center").pack(side="bottom", pady=10)
        # el dibujo, solo con el alto que sobra (240 px, 160 px o nada)
        self.cuerpo.update_idletasks()
        usado = sum(c.winfo_reqheight() + 20 for c in self.cuerpo.winfo_children())
        sobra = self.H - 24 - usado
        lado = 240 if sobra >= 250 else (160 if sobra >= 170 else 0)
        self.lado_intro = lado
        if lado:
            c = tk.Canvas(self.cuerpo, width=lado, height=lado, bg=T.fondo, highlightthickness=0)
            c.pack()
            dibujar_cara(c, lado / 2, lado * 0.48, lado * 0.79, T.acento)

    def _pantalla_pasos(self):
        self._limpiar()
        T = self.tema
        arriba = tk.Frame(self.cuerpo, bg=T.fondo)
        arriba.pack(fill="x")
        self.lbl_num = tk.Label(arriba, text="", bg=T.fondo, fg=T.texto_suave, font=letra(self.cfg, 16))
        self.lbl_num.pack(side="left")
        boton_ayuda(arriba, t("cal_ayuda"), self.cfg, T).pack(side="right")
        self.lbl_titulo = tk.Label(self.cuerpo, text="", bg=T.fondo, fg=T.acento, font=letra(self.cfg, 28, True))
        self.lbl_titulo.pack(pady=(4, 2))
        self.lbl_instr = tk.Label(self.cuerpo, text="", bg=T.fondo, fg=T.texto, font=letra(self.cfg, 22, True),
                                  wraplength=self.W - 60, justify="center")
        self.lbl_instr.pack(pady=(0, 6))
        medio = tk.Frame(self.cuerpo, bg=T.fondo)
        medio.pack(pady=4)
        lado = max(min(int(self.H * 0.36), 260), 150)
        self.lado = lado
        self.c_dibujo = tk.Canvas(medio, width=lado, height=lado, bg=T.fondo, highlightthickness=0)
        self.c_dibujo.pack(side="left", padx=20)
        self.c_vivo = tk.Canvas(medio, width=lado, height=lado, bg=T.fondo_2, highlightthickness=2,
                                highlightbackground=T.texto_suave)
        self.c_vivo.pack(side="left", padx=20)
        self.lbl_estado = tk.Label(self.cuerpo, text="", bg=T.fondo, fg=T.ambar, font=letra(self.cfg, 18, True),
                                   wraplength=self.W - 60)
        self.lbl_estado.pack(pady=2)
        self.c_avance = tk.Canvas(self.cuerpo, width=self.W - 120, height=26, bg=T.fondo_2, highlightthickness=1,
                                  highlightbackground=T.texto_suave)
        self.c_avance.pack(pady=4)
        fila = tk.Frame(self.cuerpo, bg=T.fondo)
        fila.pack(side="bottom", fill="x", pady=6)
        self._boton(fila, "cal_repetir_paso", "cal:repetir_paso", self.repetir_paso, side="left", expand=True,
                    fill="x", padx=6)
        self._boton(fila, "cal_atras", "cal:atras", self.atras, side="left", expand=True, fill="x", padx=6)
        self.b_omitir = self._boton(fila, "btn_omitir", "cal:omitir", self.omitir)
        self.b_omitir.pack(side="left", expand=True, fill="x", padx=6)
        self._boton(fila, "btn_cancelar", "cal:cancelar", self.cancelar, side="left", expand=True, fill="x", padx=6)
        self._paso_dibujado = None

    def _pantalla_final(self):
        self._limpiar()
        T = self.tema
        tk.Label(self.cuerpo, text=t("cal_final_titulo"), bg=T.fondo, fg=T.acento,
                 font=letra(self.cfg, 28, True)).pack(pady=(4, 2))
        self.lbl_final = tk.Label(self.cuerpo, text=t("cal_final"), bg=T.fondo, fg=T.texto,
                                  font=letra(self.cfg, 20, True), wraplength=self.W - 300, justify="center")
        self.lbl_final.pack(pady=4)
        if self.texto_mirada:
            # 1.1 paquete C: cuánto se equivocan los ojos, en palabras
            texto, aviso = self.texto_mirada
            tk.Label(self.cuerpo, text=texto, bg=T.aviso_fondo if aviso else T.fondo,
                     fg=T.aviso_texto if aviso else T.verde, font=letra(self.cfg, 16, True),
                     wraplength=self.W - 300, justify="center", padx=8, pady=4).pack(pady=4)
        if self.pocos:
            lados = ", ".join(t(f"lado_{p}") for p in self.pocos)
            tk.Label(self.cuerpo, text=t("cal_poco_movimiento", lados=lados), bg=T.aviso_fondo, fg=T.aviso_texto,
                     font=letra(self.cfg, 16), wraplength=self.W - 300, justify="left", padx=8,
                     pady=4).pack(pady=4)
        if getattr(self, "no_detectados", None):
            gestos = ", ".join(t(f"cal_gesto_nombre_{g}") for g in self.no_detectados)
            tk.Label(self.cuerpo, text=t("cal_gesto_no_detectado", gestos=gestos), bg=T.aviso_fondo,
                     fg=T.aviso_texto, font=letra(self.cfg, 16), wraplength=self.W - 300, justify="left",
                     padx=8, pady=4).pack(pady=4)
        n_largos = getattr(self, "parpadeos_largos", None)
        if n_largos is not None:
            # quien solo parpadea: la prueba final es el parpadeo largo (no puede ir a círculos)
            if n_largos >= PARPADEOS_LARGOS:
                texto, fondo, fg = t("cal_final_barrido_bien"), T.fondo, T.verde
            else:
                texto = t("cal_parpadeo_largo_no", n=n_largos, total=PARPADEOS_LARGOS)
                fondo, fg = T.aviso_fondo, T.aviso_texto
            self.lbl_final.configure(text=texto, bg=fondo, fg=fg)
            tk.Label(self.cuerpo, text=t("cal_final_auto"), bg=T.fondo, fg=T.texto_suave,
                     font=letra(self.cfg, 16), wraplength=self.W - 300).pack(pady=4)
            fila = tk.Frame(self.cuerpo, bg=T.fondo)
            fila.pack(side="bottom", pady=8)
            self._boton(fila, "btn_terminar", "cal:terminar", self.terminar, color=T.verde, side="left", padx=8)
            self._boton(fila, "cal_repetir_todo", "cal:repetir", self.repetir_todo, side="left", padx=8)
            self.circulos = {}
            self._cierre_solo = self.win.after(CIERRE_SOLO_MS, self._cerrar_solo)
            return
        self.zona = tk.Frame(self.cuerpo, bg=T.fondo)
        self.zona.pack(fill="both", expand=True)
        self.circulos = {}
        posiciones = ((0.0, 0.0, "nw"), (1.0, 0.0, "ne"), (0.0, 1.0, "sw"), (1.0, 1.0, "se"))
        for i, (rx, ry, ancla) in enumerate(posiciones[:N_OBJETIVOS], start=1):
            ident = f"cal:objetivo:{i}"
            b = BotonGrande(self.zona, f"◯ {i}", self.app.registro.comando(ident), T, letra(self.cfg, 26, True))
            b.place(relx=rx, rely=ry, anchor=ancla, width=150, height=110)
            self.app.registro.agregar(ident, b, lambda i=i: self.alcanzar(i))
            self.circulos[i] = b
        fila = tk.Frame(self.zona, bg=T.fondo)
        fila.place(relx=0.5, rely=1.0, anchor="s")
        self._boton(fila, "btn_terminar", "cal:terminar", self.terminar, color=T.verde, side="left", padx=8)
        self._boton(fila, "cal_repetir_todo", "cal:repetir", self.repetir_todo, side="left", padx=8)

    # ------------------------------------------------------------ 1.1 paquete C: ojos
    def cambiar_fuente(self, signo: int):
        if self.fase != "intro":
            return
        i = FUENTES.index(self.fuente) if self.fuente in FUENTES else 0
        self.fuente = FUENTES[(i + signo) % len(FUENTES)]
        try:
            self.lbl_fuente.configure(text=t(f"op_fuente_{self.fuente}"))
        except (tk.TclError, AttributeError):
            pass

    def _cfg_guia(self) -> dict:
        datos = copy.deepcopy(self.cfg)
        datos.setdefault("puntero", {})["fuente"] = self.fuente
        return datos

    def _monitor(self):
        try:
            return self.app.motor.maquina.mapeo.monitor
        except AttributeError:
            return MONITOR_REFERENCIA

    def _pintar_mirada(self, est):
        """Los pasos de la mirada van en la ventana a pantalla completa; los demás, aquí."""
        if est.paso in PASOS_MIRADA and est.fase != "terminado":
            if self.ventana_mirada is None:
                from .calibracion_mirada import VentanaMirada
                self.ventana_mirada = VentanaMirada(self.root, self.app, self._monitor(), self.repetir_paso,
                                                    self.atras, self.cancelar)
            self.ventana_mirada.actualizar(est)
        else:
            self._cerrar_mirada()

    def _cerrar_mirada(self):
        v, self.ventana_mirada = self.ventana_mirada, None
        if v is not None:
            v.cerrar()

    # ------------------------------------------------------------ acciones
    def empezar(self):
        if self.fase == "pasos":
            return
        self._vaciar_cola()
        self.app.orden("calibrar", True)
        self.fase = "pasos"
        self.guia = None          # se crea con el primer tiempo del motor
        self._pantalla_pasos()

    def repetir_paso(self):
        if self.guia is not None and self._ult_t is not None:
            self.guia.repetir(self._ult_t)
            self._paso_dibujado = None

    def atras(self):
        if self.guia is not None and self._ult_t is not None:
            self.guia.atras(self._ult_t)
            self._paso_dibujado = None

    def omitir(self):
        if self.guia is not None and self._ult_t is not None:
            self.guia.omitir(self._ult_t)
            self._paso_dibujado = None

    def alcanzar(self, i: int):
        if self.fase != "final" or i in self.alcanzados:
            return
        self.alcanzados.add(i)
        b = self.circulos.get(i)
        if b is not None:
            b.poner_texto(f"✓ {i}")
            b.poner_color(self.tema.verde)
        n = len(self.alcanzados)
        texto = t("cal_final_resultado", n=n, total=N_OBJETIVOS)
        if n >= N_OBJETIVOS:
            texto += " " + t("cal_final_bien")
        else:
            texto += " " + t("cal_final_regular")
        self.lbl_final.configure(text=texto)

    def _cerrar_solo(self):
        if self.fase == "final":
            self.terminar()

    def repetir_todo(self):
        c = getattr(self, "_cierre_solo", None)
        if c is not None:
            try:
                self.win.after_cancel(c)
            except (tk.TclError, ValueError):
                pass
            self._cierre_solo = None
        self.fase = "intro"
        self.alcanzados = set()
        self.empezar()

    def terminar(self):
        """Fin de la prueba final (la calibración ya quedó guardada)."""
        self.fase = "cerrada"
        self.app.mostrar_aviso(t("cal_listo"))
        self._cerrar(ok=True)

    def cancelar(self):
        if self.fase == "pasos":
            self.app.orden("calibrar", False)
            self.app.mostrar_aviso(t("cal_cancelada"))
        self.fase = "cerrada"
        self._cerrar(ok=False)

    def _cerrar(self, ok: bool):
        self._cerrar_mirada()
        try:
            self.win.after_cancel(self._loop)
        except (tk.TclError, ValueError):
            pass
        try:
            self.win.destroy()
        except tk.TclError:
            pass
        self.app.calibracion_cerrada(self)
        if self.al_terminar is not None:
            try:
                self.al_terminar(ok)
            except Exception:  # noqa: BLE001
                log.exception("al terminar la calibración")

    # ------------------------------------------------------------ medidas
    def _cola(self):
        return getattr(self.app.motor, "cola_calibracion", None)

    def _vaciar_cola(self):
        q = self._cola()
        if q is None:
            return
        while True:
            try:
                q.get_nowait()
            except queue.Empty:
                return

    def alimentar(self, t_, medidas, io_fr=None):
        """Un dato del motor (también lo usan las pruebas)."""
        self._ult_t = t_
        self._ult_medidas = medidas
        if self.guia is None:
            self.guia = Guia(self._cfg_guia(), t_, monitor=self._monitor())
        return self.guia.alimentar(t_, medidas, io_fr)

    def _refrescar(self):
        if self.fase == "cerrada":
            return
        try:
            if self.fase == "pasos":
                q = self._cola()
                est = None
                n = 0
                while q is not None and n < 200:
                    try:
                        dato = q.get_nowait()
                    except queue.Empty:
                        break
                    n += 1
                    t_, medidas, io_fr = dato[0], dato[1], dato[2]
                    est = self.alimentar(t_, medidas, io_fr)
                if est is None and self.guia is not None and self._ult_t is not None:
                    est = self.guia.estado(self._ult_t)
                if est is not None:
                    self._pintar(est)
                    self._pintar_mirada(est)
                    if self.guia.terminado:
                        self._finalizar_pasos()
            self._loop = self.win.after(REFRESCO_MS, self._refrescar)
        except tk.TclError:
            pass
        except Exception:  # noqa: BLE001
            # un error inesperado no puede dejar la máquina en CALIBRANDO para siempre (sin tope)
            log.exception("Error en la calibración: se cancela y se vuelve a lo de antes")
            try:
                self.cancelar()
            except Exception:  # noqa: BLE001
                log.exception("Tampoco se pudo cancelar la calibración")
                self.app.orden("calibrar", False)

    def _pintar(self, est):
        T = self.tema
        p = est.paso
        self.lbl_num.configure(text=t("cal_paso", n=est.indice + 1, total=est.total))
        self.lbl_titulo.configure(text=t(f"cal_{p}_titulo"))
        if p == "posicion" and est.fase == "medir" and est.posicion:
            instr = t(f"cal_posicion_{est.posicion}")
        else:
            instr = t(f"cal_{p}")
        if self.lbl_instr.cget("text") != instr:
            self.lbl_instr.configure(text=instr)
        if est.sin_cara and est.fase == "medir":
            self.lbl_estado.configure(text=t("cal_sin_cara"), fg=T.rojo_texto)
        elif est.fase == "preparar":
            self.lbl_estado.configure(text=t("cal_preparese"), fg=T.ambar)
        else:
            self.lbl_estado.configure(text="", fg=T.ambar)
        if p != self._paso_dibujado:
            self._paso_dibujado = p
            c = self.c_dibujo
            c.delete("all")
            gesto, flecha = DIBUJO.get(p, ("reposo", None))
            dibujar_cara(c, self.lado / 2, self.lado * 0.45, self.lado * 0.62, T.acento, gesto, flecha)
            omitible = p.startswith("gesto_")
            if omitible and not self.b_omitir.winfo_ismapped():
                self.b_omitir.pack(side="left", expand=True, fill="x", padx=6)
            elif not omitible and self.b_omitir.winfo_ismapped():
                self.b_omitir.pack_forget()
        c = self.c_vivo
        c.delete("all")
        vista = getattr(self.app, "ultima_vista", None)
        puntos = getattr(vista, "puntos", None) if vista is not None else None
        if puntos is not None:
            dibujar_puntos(c, puntos, self.lado, self.lado, T.verde)
        else:
            c.create_text(self.lado / 2, self.lado / 2, text=t("vista_sin_cara"), fill=T.rojo_texto,
                          font=letra(self.cfg, 16, True))
        if p == "parpadeo_largo" and est.fase == "medir" and not est.sin_cara:
            # barra del cierre: se llena mientras tiene los ojos cerrados y se pone verde al llegar
            h = self.lado - 20
            frac = min(max(est.parpadeo or 0.0, 0.0), 1.0)
            color = T.verde if est.parpadeo_listo else T.ambar
            c.create_rectangle(self.lado - 30, 10 + h * (1 - frac), self.lado - 6, 10 + h, fill=color, outline="")
            self.lbl_estado.configure(text=t("cal_parpadeo_largo_contador", n=est.contador, total=PARPADEOS_LARGOS),
                                      fg=T.verde if est.parpadeo_listo else T.ambar)
        if est.nivel is not None:
            # nivel del gesto en vivo: barra vertical a la derecha
            h = self.lado - 20
            frac = min(max(est.nivel / 0.5, 0.0), 1.0)
            c.create_rectangle(self.lado - 22, 10 + h * (1 - frac), self.lado - 8, 10 + h, fill=T.acento, outline="")
        a = self.c_avance
        a.delete("all")
        ancho = int(a.cget("width"))
        color = T.ambar if est.fase == "preparar" else T.verde
        a.create_rectangle(0, 0, ancho * est.progreso, 26, fill=color, outline="")

    def _finalizar_pasos(self):
        res = self.guia.resultado()
        if res is None:
            log.warning("Calibración sin centro: se repite")
            self.guia = None
            self._pantalla_pasos()
            return
        cal, largo_ms, pocos = res
        self._cerrar_mirada()
        self.pocos = pocos
        self.no_detectados = list(getattr(self.guia, "gestos_no_detectados", []) or [])
        self.parpadeos_largos = getattr(self.guia, "parpadeos_largos", None)
        datos = copy.deepcopy(self.cfg)
        perfil = datos.get("perfil_activo") or "Principal"
        datos.setdefault("perfiles", {}).setdefault(perfil, {})["calibracion"] = cal
        datos["gestos"]["parpadeo"]["largo_ms"] = max(int(largo_ms), PARPADEO_LARGO_PISO_MS)
        datos["primera_vez"] = False
        # 1.1 paquete C: la fuente elegida; si los ojos no se pudieron calibrar, queda la cabeza
        self.texto_mirada = None
        fuente = self.fuente
        if fuente != "cabeza" and not datos.get("teclado", {}).get("solo_comunicacion"):
            info = getattr(self.guia, "mirada_info", None)
            if "mirada" not in cal:
                fuente = "cabeza"
                self.texto_mirada = (t("cal_mirada_fallo"), True)
            elif info and info.get("cm") is not None:
                if info.get("impreciso"):
                    self.texto_mirada = (t("cal_mirada_impreciso", cm=info["cm"]), True)
                else:
                    self.texto_mirada = (t("cal_mirada_resultado", cm=info["cm"], boton=info["boton"]), False)
        elif fuente != "cabeza":
            fuente = "cabeza"            # «Solo comunicación» no usa el puntero
        datos.setdefault("puntero", {})["fuente"] = fuente
        datos = validar(datos)
        self.app.cfg.datos = datos
        self.app.guardar_config()
        cal_ok = datos["perfiles"][perfil]["calibracion"]
        self.app.orden("calibrar", False, cal_ok, copy.deepcopy(datos))
        self.app.orden("reanudar", "calibración")
        self.fase = "final"
        self._pantalla_final()


def _TXT_KEYS():
    from .textos import TXT
    return TXT
