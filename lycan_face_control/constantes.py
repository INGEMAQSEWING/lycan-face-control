"""Índices de los puntos de la cara (MediaPipe FaceMesh, 478 puntos con refine_landmarks=True)
y valores fijos del programa.

Lados: 33/133/468 = ojo DERECHO de la persona (a la izquierda de la imagen sin espejo);
263/362/473 = ojo IZQUIERDO. Ver docs/decisiones.md, "Medidas de la cara".
"""

# ---- Puntos de la cara ----
N_PUNTOS = 478            # con refine_landmarks=True (468 + 10 del iris)
N_PUNTOS_MIN = 468        # sin iris también se puede medir todo

NARIZ = 1
OJO_DER_EXT, OJO_DER_INT = 33, 133       # comisuras del ojo derecho de la persona
OJO_IZQ_INT, OJO_IZQ_EXT = 362, 263      # comisuras del ojo izquierdo de la persona
IRIS_DER, IRIS_IZQ = 468, 473
# ---- 1.1 paquete C: mover con los ojos ----
# Anillo del iris (4 puntos alrededor del centro 468/473) y párpado medio (superior, inferior).
# NO van en PUNTOS_CLAVE: una cara de 468 puntos (sin iris) sigue siendo válida.
IRIS_DER_ANILLO = (469, 470, 471, 472)
IRIS_IZQ_ANILLO = (474, 475, 476, 477)
PARPADO_MEDIO_DER = (159, 145)
PARPADO_MEDIO_IZQ = (386, 374)

COMISURA_DER, COMISURA_IZQ = 61, 291     # comisuras externas de la boca
BOCA_INT_DER, BOCA_INT_IZQ = 78, 308     # comisuras internas
LABIO_SUP, LABIO_INF = 13, 14            # centro interno de los labios

# EAR: [p1, p2, p3, p4, p5, p6] (p1-p4 = comisuras; p2-p6 y p3-p5 = párpados)
EAR_DER = (33, 160, 158, 133, 153, 144)
EAR_IZQ = (362, 385, 387, 263, 373, 380)

CEJA_DER = (70, 63, 105, 66, 107)
CEJA_IZQ = (300, 293, 334, 296, 336)

# Contorno de la cara (para dibujar la silueta en la ventana, sin video)
OVALO_CARA = (10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288, 397, 365, 379, 378, 400,
              377, 152, 148, 176, 149, 150, 136, 172, 58, 132, 93, 234, 127, 162, 21, 54, 103, 67, 109)

# Puntos que deben quedar dentro de la imagen para confiar en las medidas
PUNTOS_CLAVE = tuple(sorted({NARIZ, OJO_DER_EXT, OJO_DER_INT, OJO_IZQ_INT, OJO_IZQ_EXT,
                             COMISURA_DER, COMISURA_IZQ, BOCA_INT_DER, BOCA_INT_IZQ, LABIO_SUP, LABIO_INF,
                             *EAR_DER, *EAR_IZQ, *CEJA_DER, *CEJA_IZQ}))

IO_MIN_PX = 40.0          # cara demasiado lejos o pequeña por debajo de esto

# ---- Estados principales (sección 5.1) ----
PAUSA = "PAUSA"
ACTIVO = "ACTIVO"
SIN_CARA = "SIN_CARA"
CALIBRANDO = "CALIBRANDO"
ESTADOS = (PAUSA, ACTIVO, SIN_CARA, CALIBRANDO)

# ---- Submodos de ACTIVO (sección 5.2) ----
NORMAL = "NORMAL"
ARRASTRE_INICIO = "ARRASTRE_INICIO"
ARRASTRANDO = "ARRASTRANDO"
DESPLAZAR = "DESPLAZAR"
TECLADO = "TECLADO"
BARRIDO = "BARRIDO"
SOLO_COMUNICACION = "SOLO_COMUNICACION"
SUBMODOS = (NORMAL, ARRASTRE_INICIO, ARRASTRANDO, DESPLAZAR, TECLADO, BARRIDO, SOLO_COMUNICACION)
# ---- 1.1 paquete A: lupa para el clic preciso (la ventana agrandada está abierta) ----
LUPA = "LUPA"
SUBMODOS = SUBMODOS + (LUPA,)

# ---- Colores (contraste >= 7:1 sobre el fondo) ----
FONDO = "#0b1a36"
TEXTO = "#ffffff"
ACENTO = "#22e3ff"
AMBAR = "#ffb020"
VERDE = "#3ddc84"
ROJO = "#ff5c5c"
# Alto contraste
AC_FONDO = "#000000"
AC_TEXTO = "#ffff00"

COLORES_ESTADO = {
    ACTIVO: VERDE,
    PAUSA: AMBAR,
    SIN_CARA: ROJO,
    CALIBRANDO: ACENTO,
}

# ---- Botones del ratón y teclas (nombres internos) ----
IZQ, DER, MEDIO = "izq", "der", "medio"
BOTONES = (IZQ, DER, MEDIO)
SHIFT, CTRL, ALT = "shift", "ctrl", "alt"
TECLAS = (SHIFT, CTRL, ALT)

WHEEL_DELTA = 120

# Teclas virtuales de Windows que el teclado en pantalla puede pulsar (TeclaVK)
VK_BACK = 0x08
VK_TAB = 0x09
VK_RETURN = 0x0D
VK_ESCAPE = 0x1B
VK_SPACE = 0x20
VK_END = 0x23
VK_HOME = 0x24
VK_LEFT, VK_UP, VK_RIGHT, VK_DOWN = 0x25, 0x26, 0x27, 0x28
VK_DELETE = 0x2E
VK_PERMITIDAS = frozenset({VK_BACK, VK_TAB, VK_RETURN, VK_ESCAPE, VK_SPACE, VK_END, VK_HOME,
                           VK_LEFT, VK_UP, VK_RIGHT, VK_DOWN, VK_DELETE})
# Teclas "extendidas": necesitan KEYEVENTF_EXTENDEDKEY para no confundirse con el teclado numérico
VK_EXTENDIDAS = frozenset({VK_END, VK_HOME, VK_LEFT, VK_UP, VK_RIGHT, VK_DOWN, VK_DELETE})

# Firma de los eventos propios en dwExtraInfo: 'LYFC' (distinta de la de Lycan Mouse Control,
# 'LYCN', para que cada programa reconozca solo los suyos si ambos están abiertos)
LYCAN_EXTRA = 0x4C594643

# ---- Botones de la barra de acciones (identificador interno, texto) ----
BOTONES_BARRA = (
    ("clic", "Clic"),
    ("doble", "Doble"),
    ("derecho", "Derecho"),
    ("arrastrar", "Arrastrar"),
    ("desplazar", "Desplazar"),
    ("teclado", "Teclado"),
    ("pausa", "Pausa"),
)
# ---- 1.1 paquete A: Sin clic (modo lectura), Lupa (clic preciso) y Minimizar ----
BOTONES_BARRA = BOTONES_BARRA + (
    ("sin_clic", "Sin clic"),
    ("lupa", "Lupa"),
    ("minimizar", "Minimizar"),
)
# ---- 1.1 paquete B: botón AYUDA (emergencia), siempre al final y en rojo ----
BOTONES_BARRA = BOTONES_BARRA + (
    ("ayuda", "AYUDA"),
)
ID_EMERGENCIA_BARRA = "barra:ayuda"
ID_EMERGENCIA_TECLADO = "teclado:ayuda"
ID_EMERGENCIA_PESTANA = "pestana:ayuda"      # en la pestaña de la barra minimizada
ID_ATENDIDO = "emergencia:atendido"          # «Ya me atendieron» en la pantalla roja
IDS_EMERGENCIA = (ID_EMERGENCIA_BARRA, ID_EMERGENCIA_TECLADO, ID_EMERGENCIA_PESTANA)

# ---- Gestos y acciones asignables (sección 5.4) ----
GESTOS = ("boca", "cejas", "sonrisa", "parpadeo")
ACCIONES_GESTO = ("ninguna", "clic", "clic_izq", "clic_der", "doble", "arrastrar", "pausar", "teclado",
                  "recentrar", "borrar", "elegir", "hablar", "siguiente")
# ---- 1.1 paquete B: emergencia (botón AYUDA) ----
# "emergencia" solo vale en el gesto LARGO (la validación pasa un gesto corto a "ninguna") y nunca
# en el parpadeo: un parpadeo largo de sueño no debe hacer sonar una alarma de noche.
ACCIONES_GESTO = ACCIONES_GESTO + ("emergencia",)

# ---- Nombres del programa ----
NOMBRE_APP = "Lycan Face Control"
NOMBRE_CORTO = "Control con la cara"
CARPETA_DATOS = "Lycan Face Control"
MUTEX = "Local\\LycanFaceControl"
NOMBRE_RUN = "LycanFaceControl"
