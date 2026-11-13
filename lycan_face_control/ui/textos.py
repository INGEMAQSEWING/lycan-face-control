"""TODOS los textos de la interfaz (español de Colombia, trato de "usted", sin jerga, tono cálido
y digno). Una prueba revisa que no haya palabras técnicas en inglés ni tuteo.

Uso: ``t("clave", nombre="valor")``. Si falta una clave se devuelve la clave (y se anota).
"""
from __future__ import annotations

import logging

from .. import constantes as K

log = logging.getLogger("lycan")

# Palabras que no pueden aparecer (con espacios alrededor para no confundir partes de palabras)
PALABRAS_PROHIBIDAS = (" landmark", "threshold", "blendshape", " frame", " frames", " click", "setear",
                       "resetear", " dwell", " tracking", "mediapipe", "facemesh", " hz ", " fps", " mouse",
                       " ok ", " input", " widget", " default", " log ", " thread", " bug", " crash")
TUTEO = (" tú ", " haz ", " puedes ", " vos ", " tienes ", " quieres ", " mira ", " mueve tu", " tu cabeza",
         " tu cara", " cierra ", " abre ", " elige ", " sube ", " baja tu", " tus ", " estás ")

TXT: dict[str, str] = {
    # ---- estados (grandes, con ícono) ----
    "estado_ACTIVO": "Activo",
    "estado_PAUSA": "En pausa",
    "estado_SIN_CARA": "No veo su cara",
    "estado_CALIBRANDO": "Calibrando",
    "estado_DETENIDO": "Detenido",
    "icono_ACTIVO": "●",
    "icono_PAUSA": "❚❚",
    "icono_SIN_CARA": "✕",
    "icono_CALIBRANDO": "◎",
    "icono_DETENIDO": "■",
    "sub_ACTIVO": "Mueva la cabeza para llevar el puntero. Quédese quieto un momento para hacer clic.",
    "sub_PAUSA": "No muevo el puntero ni hago clic. Para seguir, elija «Reanudar» con la cabeza.",
    "sub_PAUSA_auto": "Pausa porque no veía su cara. Sigo solo cuando vuelva a verla un momento.",
    "sub_SIN_CARA": "Acérquese a la cámara o revise la luz. Ya solté todos los botones.",
    "sub_CALIBRANDO": "Siga las instrucciones de la ventana de calibración.",
    "sub_DETENIDO": "La detección se detuvo. Cierre y vuelva a abrir el programa.",
    "sub_TECLADO": "Teclado abierto: quédese quieto sobre una tecla para escribirla.",
    "sub_BARRIDO": "Barrido: cierre los ojos un momento largo para elegir lo que está iluminado.",
    "sub_SOLO_COMUNICACION": "Solo comunicación: el puntero no se mueve; use el teclado.",
    "sub_DESPLAZAR": "Desplazar: incline la cabeza arriba o abajo. Elija «Terminar» para salir.",
    "sub_ARRASTRE_INICIO": "Arrastrar: haga clic donde quiere agarrar.",
    "sub_ARRASTRANDO": "Arrastrando: quédese quieto donde quiere soltar.",
    "sub_recentrando": "Mire al frente y quédese quieto un momento…",
    "modo_ensayo": "Modo ensayo: no muevo el ratón real ni escribo nada.",

    # ---- ventana principal ----
    "btn_pausar": "Pausar",
    "btn_reanudar": "Reanudar",
    "btn_teclado": "Teclado",
    "btn_recentrar": "Recentrar",
    "btn_calibrar": "Calibrar",
    "btn_opciones": "Opciones",
    "btn_ayuda": "Ayuda",
    "btn_mini": "Pequeña",
    "btn_grande": "Agrandar",
    "btn_salir": "Salir",
    "btn_si_salir": "Sí, salir",
    "btn_no": "No",
    "btn_si": "Sí",
    "btn_cerrar": "Cerrar",
    "btn_cancelar": "Cancelar",
    "btn_guardar": "Guardar",
    "btn_siguiente": "Siguiente",
    "btn_anterior": "Anterior",
    "btn_terminar": "Terminar",
    "btn_repetir": "Repetir",
    "btn_omitir": "Omitir",
    "btn_mas_tarde": "Más tarde",
    "pregunta_salir": "¿Seguro que quiere salir? El programa dejará de responder a su cabeza.",
    "globo_pausa": "Pausar o reanudar. El cuidador también puede usar Ctrl+Alt+Espacio.",
    "globo_recentrar": "Si cambió de posición en la cama o la silla, mire al frente y elija Recentrar.",
    "globo_calibrar": "Repite la calibración guiada (más o menos un minuto).",
    "globo_mini": "Deja solo una tira pequeña con el estado y el botón Reanudar.",
    "globo_salir": "Cierro el programa. Antes suelto todos los botones del ratón.",
    "titulo_gestos": "Gestos",
    "gesto_boca": "Boca",
    "gesto_cejas": "Cejas",
    "gesto_sonrisa": "Sonrisa",
    "gesto_parpadeo": "Ojos",
    "vista_sin_cara": "Sin cara",
    "vista_video_apagado": "Solo se muestra la silueta.\nEl video nunca se guarda.",

    # ---- barra de acciones ----
    "barra_clic": "Clic",
    "barra_doble": "Doble",
    "barra_derecho": "Derecho",
    "barra_arrastrar": "Arrastrar",
    "barra_desplazar": "Desplazar",
    "barra_teclado": "Teclado",
    "barra_pausa": "Pausa",
    "barra_reanudar": "Reanudar",
    "barra_terminar": "Terminar",
    "barra_ocultar": "Ocultar",
    "barra_mostrar": "Barra",
    "icono_clic": "●",
    "icono_doble": "●●",
    "icono_derecho": "◑",
    "icono_arrastrar": "✥",
    "icono_desplazar": "↕",
    "icono_teclado": "⌨",
    "icono_pausa": "❚❚",
    "icono_reanudar": "▶",
    "icono_terminar": "■",
    "icono_ocultar": "»",

    # ---- indicador junto al cursor ----
    "ind_doble": "Doble",
    "ind_der": "Derecho",
    "ind_arrastrar": "Arrastrar",
    "ind_arrastrando": "Arrastrando",
    "ind_desplazar": "Desplazando",
    "ind_abra_ojos": "Abra los ojos",
    "ind_reanudar": "Reanudar…",

    # ---- avisos (los manda el motor) ----
    "aviso_pausa": "En pausa.",
    "aviso_activo": "Activo.",
    "aviso_sin_cara": "No veo su cara. Acérquese a la cámara o revise la luz.",
    "aviso_cara_vuelve": "Ya veo su cara otra vez.",
    "aviso_recomendar_calibrar": "Le recomiendo calibrar para que el puntero se ajuste a su forma de moverse.",
    "aviso_recentrando": "Mire al frente y quédese quieto un momento…",
    "aviso_recentrado": "Listo: el centro quedó donde usted está mirando ahora.",
    "aviso_recentrar_cancelado": "No pude tomar el centro. Intente otra vez mirando al frente.",
    "aviso_arrastrando": "Arrastrando: quédese quieto donde quiere soltar.",
    "aviso_arrastre_fin": "Soltado.",
    "aviso_arrastre_largo": "Solté el arrastre porque duró demasiado (por seguridad).",
    "aviso_desplazar": "Desplazar: incline la cabeza arriba o abajo.",
    "aviso_desplazar_fin": "Terminó el desplazamiento.",
    "aviso_sobre_ventana": "Aquí no hago clic: es una ventana de este programa.",
    "aviso_foco_propio": "Primero elija con la cabeza el programa donde quiere escribir.",
    "aviso_administrador": ("Ese programa está abierto como administrador; Windows no me deja escribir ni "
                            "hacer clic en él."),
    "aviso_error": "Algo falló; solté todo y quedé en pausa.",
    "aviso_bloqueo": "Windows no me deja mover el ratón ahora (pantalla bloqueada o aviso de seguridad). Sigo cuando lo permita.",
    "aviso_fatal": "Algo falló varias veces. Estoy reiniciando la detección.",
    "aviso_motor_caido": "Algo falló; estoy reiniciando la detección.",
    "aviso_motor_rendido": "No pude reiniciar la detección. Cierre y vuelva a abrir el programa.",
    "aviso_camara_perdida": "Perdí la cámara. Revise que esté conectada; sigo intentando.",
    "aviso_error_inicio": "No pude abrir la cámara ni la detección de la cara. Revise que la cámara esté conectada.",
    "aviso_no_camara": "No encuentro la cámara. Revise que esté conectada y que otro programa no la esté usando.",
    "aviso_camara_ocupada": "Otro programa está usando la cámara. Ciérrelo para que yo pueda verla.",
    "aviso_teclado_no_disponible": "El teclado en pantalla no está disponible en esta versión.",
    "aviso_sin_voz": "No encontré una voz en español en Windows; muestro el texto en grande.",
    "aviso_descanso": "Lleva un buen rato usando el computador. Si quiere, descanse el cuello un momento.",
    "aviso_atajos": "Algunos atajos del cuidador no se pudieron usar:",
    "aviso_no_guardo": "No pude guardar los cambios. Revise que la carpeta de datos no esté protegida.",
    "aviso_config_solo_lectura": ("No pude leer la configuración al abrir; los cambios de esta sesión no se "
                                  "guardan. Cierre y vuelva a abrir el programa."),
    "aviso_opciones_soltar": "Mientras están abiertas las Opciones suelto todo por seguridad.",
    "aviso_ya_abierto": "Lycan Face Control ya está abierto.",
    "aviso_no_abre": "Lycan Face Control no pudo abrir. El detalle quedó en el registro de errores.",
    "aviso_sin_registro": "No pude crear el registro de errores; el programa funciona igual.",

    # ---- calibración ----
    "cal_titulo": "Calibración guiada",
    "cal_intro_titulo": "Vamos a ajustar el programa a su forma de moverse",
    "cal_intro": ("Toma más o menos un minuto. Cada paso avanza solo; usted solo tiene que seguir las "
                  "instrucciones. Si algo no salió bien, el cuidador puede elegir «Repetir este paso»."),
    "cal_empezar": "Empezar",
    "cal_preparese": "Prepárese…",
    "cal_paso": "Paso {n} de {total}",
    "cal_posicion_titulo": "Posición",
    "cal_posicion": "Ponga la cara en el centro de la cámara, a un brazo de distancia.",
    "cal_posicion_lejos": "Acérquese un poco a la cámara.",
    "cal_posicion_cerca": "Aléjese un poco de la cámara.",
    "cal_posicion_bien": "Muy bien, quédese así.",
    "cal_posicion_timeout": "No logré verlo a buena distancia; sigo de todas formas.",
    "cal_centro_titulo": "Centro",
    "cal_centro": "Mire al frente, a la mitad de la pantalla, y quédese quieto.",
    "cal_izq_titulo": "Izquierda",
    "cal_izq": "Gire la cabeza hacia su izquierda, hasta donde le quede cómodo, sin forzar.",
    "cal_der_titulo": "Derecha",
    "cal_der": "Ahora gire la cabeza hacia su derecha, sin forzar.",
    "cal_arr_titulo": "Arriba",
    "cal_arr": "Levante un poco la cabeza, como mirando arriba de la pantalla, sin forzar.",
    "cal_aba_titulo": "Abajo",
    "cal_aba": "Baje un poco la cabeza, como mirando debajo de la pantalla, sin forzar.",
    "cal_reposo_titulo": "Cara en reposo",
    "cal_reposo": "Mire al frente con la cara relajada y la boca cerrada.",
    "cal_parpadeo_titulo": "Parpadeo natural",
    "cal_parpadeo": "Parpadee como siempre, sin pensarlo. Así aprendo a no confundir sus parpadeos con un clic.",
    "cal_gesto_boca_titulo": "Probar: abrir la boca",
    "cal_gesto_boca": "Abra la boca y ciérrela tres veces, despacio.",
    "cal_gesto_cejas_titulo": "Probar: levantar las cejas",
    "cal_gesto_cejas": "Levante las cejas y bájelas tres veces, despacio.",
    "cal_gesto_sonrisa_titulo": "Probar: sonreír",
    "cal_gesto_sonrisa": "Sonría y relaje la cara tres veces, con la boca cerrada.",
    "cal_sin_cara": "No veo su cara. Vuelva frente a la cámara y sigo donde íbamos.",
    "cal_repetir_paso": "Repetir este paso",
    "cal_atras": "Atrás",
    "cal_ayuda": ("Cada paso avanza solo cuando termina. El cuidador puede repetir un paso o volver atrás "
                  "con el ratón. Nada de esto se graba: solo guardo unos números."),
    "cal_poco_movimiento": ("Casi no detecté movimiento hacia {lados}. Si le cuesta, puede subir la velocidad "
                            "del puntero o usar el modo «palanca» en Opciones."),
    "cal_final_titulo": "Prueba final",
    "cal_final": "Lleve el puntero con la cabeza a cada círculo y quédese quieto sobre él.",
    "cal_final_resultado": "Alcanzó {n} de {total} círculos.",
    "cal_final_bien": "¡Muy bien! Ya puede usar el programa.",
    "cal_final_regular": "Si le costó, puede repetir la calibración o ajustar la velocidad en Opciones.",
    "cal_repetir_todo": "Repetir la calibración",
    "cal_listo": "Calibración guardada.",
    "cal_cancelada": "Calibración cancelada; sigo con los ajustes de antes.",
    "lado_izq": "la izquierda",
    "lado_der": "la derecha",
    "lado_arr": "arriba",
    "lado_aba": "abajo",

    # ---- asistente de primera vez ----
    "asis_titulo": "Bienvenida",
    "asis_1_titulo": "Bienvenido a Lycan Face Control",
    "asis_1": ("Este programa le permite manejar el computador solo con la cabeza y la cara: mover el "
               "puntero, hacer clic sin manos y escribir o hablar con un teclado en pantalla.\n\n"
               "Todo ocurre en este computador. No se usa internet y el video nunca se guarda."),
    "asis_2_titulo": "Para el cuidador: la cámara",
    "asis_2": ("• Ponga la cámara a la altura de los ojos, a 50 o 70 centímetros de la cara.\n"
               "• Que la luz venga de frente. Evite una ventana detrás de la persona.\n"
               "• Si usa gafas con reflejos, incline un poco la pantalla.\n"
               "• Puede pausar o reanudar en cualquier momento con Ctrl+Alt+Espacio."),
    "asis_3_titulo": "Cómo se hace clic",
    "asis_3": ("• Quedarse quieto un momento sobre algo hace clic (verá un anillo que se llena).\n"
               "• Abrir la boca también hace clic. Sostenerla abierta dos segundos pausa el programa.\n"
               "• Levantar las cejas hace clic derecho.\n"
               "• Los parpadeos normales nunca hacen clic.\n\n"
               "Todo esto se puede cambiar en Opciones."),
    "asis_4_titulo": "Ahora, la calibración",
    "asis_4": ("Vamos a ajustar el programa a su forma de moverse. Toma más o menos un minuto y cada paso "
               "avanza solo."),
    "asis_calibrar": "Empezar la calibración",

    # ---- opciones ----
    "op_titulo": "Opciones",
    "op_tab_puntero": "Puntero",
    "op_tab_clic": "Clic",
    "op_tab_gestos": "Gestos",
    "op_tab_teclado": "Teclado y voz",
    "op_tab_comodidad": "Comodidad",
    "op_tab_atajos": "Atajos",
    "op_fabrica": "Valores de fábrica",
    "op_fabrica_pregunta": "¿Volver a los valores de fábrica? La calibración y los atajos se conservan.",
    "op_fabrica_si": "Sí, volver a fábrica",
    "op_guardado": "Cambios guardados.",
    "op_cancelado": "No se guardó ningún cambio.",
    "op_ayuda": ("Elija «−» o «+» con la cabeza para cambiar un valor. Los cambios se prueban al instante; "
                 "«Cancelar» los deshace y «Guardar» los deja."),
    "op_si": "Sí",
    "op_no": "No",
    "op_velocidad": "Velocidad del puntero",
    "op_velocidad_ayuda": "1 = lento (hay que mover más la cabeza); 10 = rápido (basta un movimiento pequeño).",
    "op_suavidad": "Suavidad (quita el temblor)",
    "op_modo": "Forma de mover el puntero",
    "op_modo_absoluto": "Directo",
    "op_modo_relativo": "Como una almohadilla",
    "op_modo_joystick": "Palanca",
    "op_modo_ayuda": ("Directo: cada posición de la cabeza es un punto de la pantalla. Almohadilla: el puntero "
                      "avanza lo que mueva la cabeza. Palanca: para quien mueve poco el cuello; el puntero "
                      "sigue avanzando mientras la cabeza esté girada."),
    "op_perm_activa": "Clic al quedarse quieto",
    "op_perm_tiempo": "Tiempo quieto para hacer clic",
    "op_perm_radio": "Cuánto se puede mover sin cancelar",
    "op_perm_recuperacion": "Espera entre un clic y otro",
    "op_perm_sonido": "Sonido al hacer clic",
    "op_barra_tiempo": "Tiempo para elegir un botón",
    "op_barra_fijo": "El modo de la barra se queda puesto",
    "op_barra_fijo_ayuda": "Si dice «No», después de un doble clic o un clic derecho vuelve solo al clic normal.",
    "op_gesto_activo": "Encendido",
    "op_gesto_sens": "Sensibilidad",
    "op_gesto_sostener": "Tiempo que hay que sostenerlo",
    "op_gesto_corto": "Al hacerlo",
    "op_gesto_largo": "Al sostenerlo 2 segundos",
    "op_gesto_nivel": "Pruébelo ahora:",
    "op_parpadeo_largo": "Duración del parpadeo largo",
    "op_parpadeo_fuera": "Parpadeo largo fuera del teclado",
    "op_parpadeo_doble": "Exigir dos parpadeos largos",
    "op_parpadeo_nota": "Los parpadeos normales nunca hacen nada, sin importar lo que elija aquí.",
    "op_distribucion": "Orden de las letras",
    "op_dist_auto": "Automático",
    "op_dist_qwerty": "Como un teclado normal",
    "op_dist_frecuencia": "Las más usadas primero",
    "op_tecla_tiempo": "Tiempo para elegir una tecla",
    "op_barrido": "Barrido (las teclas se iluminan solas)",
    "op_barrido_paso": "Velocidad del barrido",
    "op_escritura": "Al escribir en otro programa",
    "op_escritura_mensaje": "Enviar el mensaje completo",
    "op_escritura_directo": "Cada letra al instante",
    "op_letra_teclado": "Tamaño de las teclas",
    "op_voz_volumen": "Volumen de la voz",
    "op_voz_velocidad": "Velocidad de la voz",
    "op_voz_frases": "Decir las frases en voz alta",
    "op_cuidador": "Nombre del cuidador (para «Llamar a…»)",
    "op_genero": "Frases en",
    "op_genero_neutro": "Neutro",
    "op_genero_masculino": "Masculino",
    "op_genero_femenino": "Femenino",
    "op_solo_com": "Solo comunicación (el puntero no se mueve)",
    "op_editar_frases": "Editar las frases rápidas",
    "op_escala": "Tamaño de la letra",
    "op_alto_contraste": "Alto contraste (negro y amarillo)",
    "op_barra_posicion": "Lugar de la barra",
    "op_pos_derecha": "Derecha",
    "op_pos_izquierda": "Izquierda",
    "op_pos_arriba": "Arriba",
    "op_pos_abajo": "Abajo",
    "op_barra_tam": "Tamaño de los botones de la barra",
    "op_barra_visible": "Mostrar la barra",
    "op_indicador_borde": "Franja de color arriba de la pantalla",
    "op_video": "Mostrar el video de la cámara",
    "op_sonidos": "Sonidos",
    "op_descanso": "Recordar descansar cada",
    "op_al_encender": "Abrir al encender el computador",
    "op_arranque": "Al abrir, empezar",
    "op_arranque_auto": "Activo si ya calibró",
    "op_arranque_activo": "Activo",
    "op_arranque_pausa": "En pausa",
    "op_atajos_ayuda": ("Atajos de teclado para el cuidador. Escriba por ejemplo Ctrl+Alt+Espacio. "
                        "Se aplican al guardar."),
    "op_atajo_pausar": "Pausar o reanudar",
    "op_atajo_teclado": "Abrir o cerrar el teclado",
    "op_atajo_recentrar": "Recentrar",
    "op_atajo_ventana": "Mostrar esta ventana",
    "op_atajo_salir": "Salir",
    "op_atajo_invalido": "El atajo «{texto}» no es válido: {motivo}.",
    "op_apagado": "Apagado",
    "op_minutos": "{n} min",
    "op_segundos": "{n} s",
    "op_porcentaje": "{n} %",
    "accion_ninguna": "Nada",
    "accion_clic": "Clic (el de la barra)",
    "accion_clic_izq": "Clic izquierdo",
    "accion_clic_der": "Clic derecho",
    "accion_doble": "Doble clic",
    "accion_arrastrar": "Arrastrar",
    "accion_pausar": "Pausar o reanudar",
    "accion_teclado": "Abrir el teclado",
    "accion_recentrar": "Recentrar",
    "accion_borrar": "Borrar (en el teclado)",
    "accion_elegir": "Elegir (barrido)",
    "accion_hablar": "Hablar (en el teclado)",
    "accion_siguiente": "Avanzar el barrido",

    # ---- ayuda ----
    "ayuda_titulo": "Ayuda",
    "ayuda_sec_gestos": "Gestos",
    "ayuda_sec_uso": "Cómo se usa",
    "ayuda_sec_cuidador": "Para el cuidador",
    "ayuda_sec_problemas": "Qué hacer si…",
    "ayuda_sec_acerca": "Acerca de",
    "ayuda_gestos_intro": "Así está configurado ahora:",
    "ayuda_gesto_boca": "Abrir la boca",
    "ayuda_gesto_cejas": "Levantar las cejas",
    "ayuda_gesto_sonrisa": "Sonreír",
    "ayuda_gesto_parpadeo": "Cerrar los ojos un momento largo",
    "ayuda_gesto_apagado": "apagado",
    "ayuda_gesto_largo": "sostenido 2 s: {accion}",
    "ayuda_uso": ("• Mover: gire la cabeza; el puntero la sigue.\n"
                  "• Clic: quédese quieto un momento (el anillo se llena) o haga el gesto de clic.\n"
                  "• Barra de acciones: elija Doble, Derecho, Arrastrar o Desplazar antes de hacer clic. "
                  "Después vuelve sola al clic normal.\n"
                  "• Teclado: escriba, hable con la voz del computador o use las frases rápidas.\n"
                  "• Pausa: sostenga la boca abierta dos segundos. Para reanudar, sosténgala tres segundos "
                  "o quédese quieto sobre «Reanudar».\n"
                  "• Si cambió de posición, elija «Recentrar» mirando al frente."),
    "ayuda_cuidador": ("• Instalación: no pide permisos de administrador.\n"
                       "• Cámara a la altura de los ojos, a 50 o 70 cm; luz de frente, sin ventana detrás.\n"
                       "• Calibre la primera vez y cuando cambie mucho la postura.\n"
                       "• Las frases rápidas se editan en Opciones › Teclado y voz.\n"
                       "• Atajos: Ctrl+Alt+Espacio = pausar o reanudar; Ctrl+Alt+T = teclado; "
                       "Ctrl+Alt+C = recentrar; Ctrl+Alt+Inicio = mostrar la ventana; Ctrl+Alt+Fin = salir.\n"
                       "• Si la persona se cansa: suba la velocidad del puntero para mover menos el cuello, "
                       "o use el barrido del teclado."),
    "ayuda_problemas": ("• «No veo su cara»: acerque la persona o mejore la luz de frente.\n"
                        "• El puntero tiembla: suba la suavidad en Opciones › Puntero.\n"
                        "• Hace clics sin querer: alargue el tiempo quieto en Opciones › Clic, o apague el "
                        "clic al quedarse quieto y use solo gestos.\n"
                        "• No llega a los bordes: repita la calibración o suba la velocidad.\n"
                        "• Con poca luz, sostenga el parpadeo largo un poco más.\n"
                        "• No escribe en un programa: puede estar abierto como administrador.\n\n"
                        "Con honestidad: si la persona pierde también el control de los párpados, este "
                        "programa ya no le sirve y hacen falta otros sistemas, como los seguidores de "
                        "mirada especializados."),
    "ayuda_acerca": ("Lycan Face Control {version}\nControl con la cara\nLycan Developments · EDWIN CNC\n\n"
                     "Programa de código abierto (licencia MIT), sin costo de licencia.\n"
                     "Todo funciona sin internet; el video nunca se guarda.\n\n"
                     "Lista de palabras: FrequencyWords (Hermit Dave, a partir de OpenSubtitles), "
                     "licencia CC BY-SA 4.0."),
    "ayuda_honestidad": "Si la persona pierde también el control de los párpados, hacen falta otros sistemas.",
}


def t(clave: str, **kw) -> str:
    txt = TXT.get(clave)
    if txt is None:
        log.warning("Falta el texto %s", clave)
        return clave
    if kw:
        try:
            return txt.format(**kw)
        except (KeyError, IndexError, ValueError):
            return txt
    return txt


def texto_aviso(aviso) -> str:
    """Texto para mostrar de un ``Aviso`` del motor (o vacío si no se muestra)."""
    clave = getattr(aviso, "clave", "") or ""
    return TXT.get(f"aviso_{clave}", "")


def nombre_accion(accion: str) -> str:
    return TXT.get(f"accion_{accion}", accion)


def texto_estado(estado: str) -> str:
    return TXT.get(f"estado_{estado}", estado)


def icono_estado(estado: str) -> str:
    return TXT.get(f"icono_{estado}", "●")


def subtitulo(vista) -> str:
    """Frase de ayuda bajo el estado grande, según el estado y el submodo."""
    if vista is None:
        return ""
    m = getattr(vista, "maquina", vista)
    if m.recentrando is not None:
        return TXT["sub_recentrando"]
    if m.estado == K.PAUSA:
        return TXT["sub_PAUSA_auto"] if m.pausa_auto else TXT["sub_PAUSA"]
    if m.estado == K.ACTIVO and m.submodo != K.NORMAL:
        return TXT.get(f"sub_{m.submodo}", TXT["sub_ACTIVO"])
    return TXT.get(f"sub_{m.estado}", "")
