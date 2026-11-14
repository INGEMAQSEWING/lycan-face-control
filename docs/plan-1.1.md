# Plan de la versión 1.1.0 de Lycan Face Control

Fecha: 2026-11-14. Punto de partida: versión 1.0.0, commit `3ad1841`, 669 pruebas en verde.

El usuario pidió cinco cosas:
1. mover el puntero con los ojos;
2. graduar la velocidad del puntero;
3. traer lo que sirva de TD Control;
4. un botón de AYUDA (emergencia);
5. un botón para minimizar.

Al final se actualizan el manual web y el video.

El trabajo se divide en **tres paquetes**, que se hacen **uno después de otro, en el orden A, B, C**, en el mismo repositorio. Cada paquete termina con todas las pruebas en verde y su propio commit (sin push). El siguiente paquete parte de ese commit.

Fuentes de este plan:
- el informe de TD Control y de los otros programas de control por mirada o cabeza;
- el informe "Mover el mouse con los ojos";
- la lectura del código actual: `config.py`, `constantes.py`, `estados.py`, `puntero.py`, `mapeo.py`, `permanencia.py`, `ui/barra.py`, `ui/opciones.py`, `ui/teclado.py`, `ui/textos.py`, `ui/aplicacion.py`, `ui/ventana_principal.py`, `sistema/sonidos.py`, `sistema/voz.py`, `sistema/atajos.py`, `calibracion_guiada.py`, `cara.py` y `pruebas/sintetico/cara_sintetica.py`.

---

## 0. Reglas que valen para los tres paquetes

- **Todo en español**: código, comentarios, textos y commits. Los textos van en `ui/textos.py`, con trato de "usted" y sin jerga (la prueba de `PALABRAS_PROHIBIDAS` y `TUTEO` debe seguir pasando).
- **Nunca se abre la cámara real.** Las pruebas usan `pruebas/sintetico` y `LYCAN_FACE_DATOS`.
- **Seguridad para la persona con ELA**:
  - siempre hay forma de reanudar y de deshacer sin manos;
  - los parpadeos naturales nunca hacen nada;
  - ninguna acción peligrosa puede ocurrir por accidente;
  - toda transición nueva que cambie de modo suelta todo (`SoltarTodo`).
- **Configuración**: cada clave nueva va en `FABRICA` y en `RANGOS` u `OPCIONES` (o `LARGO_TEXTO`) de `config.py`, y tiene prueba de validación. Hay que probar el valor fuera de rango, el tipo equivocado, NaN, el texto vacío y la clave ausente en una configuración vieja.
- **Pruebas de todas las reglas**, no solo del camino feliz: datos que faltan, errores (falla Windows, falla el sonido, falla la captura), tecleo real del cuidador y cambios de estado a mitad de camino.
- **8 GB de RAM**: las pruebas se corren con un solo proceso (`py -3.10 -m pytest -q -x`), sin nada pesado en paralelo.
- **Decisiones**: cada decisión nueva se anota en `docs/decisiones.md`, en una sección "Versión 1.1, paquete X" con la fecha.
- **Especificación**: `docs/especificacion.md` se actualiza en las secciones que cambien (5.2, 5.3, 5.4, 6.2, 6.6, 9, 9.1 y 10).
- **Commit** al final de cada paquete. El mensaje va en español y termina con la línea `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

### 0.1 Archivos que comparten los paquetes y cómo evitar choques

| Archivo | A | B | C |
|---|---|---|---|
| `config.py` | `puntero.ajuste_vertical`, `barra.boton_sin_clic`, `barra.boton_lupa`, bloque `lupa` | bloque `emergencia`, `atajos.emergencia`, regla de coherencia del gesto corto | `puntero.fuente`, bloque `ojos`, regla `ojos.puntos_cal` |
| `constantes.py` | `BOTONES_BARRA` (Sin clic, Lupa, Minimizar), submodo `LUPA` | `"emergencia"` en `ACCIONES_GESTO` e identificadores `ID_EMERGENCIA*` | puntos del anillo del iris y del párpado medio |
| `ui/textos.py` | textos de velocidad, Sin clic, Lupa y Minimizar | textos de AYUDA y emergencia; "Ayuda" pasa a "Cómo usar" | textos de ojos y de la calibración de mirada |
| `ui/opciones.py` | fila de velocidad con botones grandes, ajuste vertical y lupa | pestaña "Emergencia" y botón "Probar la alarma" | selector de fuente y opciones de ojos |
| `estados.py` | modo de clic `ninguno` y `lupa`, submodo `LUPA` | estado de emergencia; AYUDA elegible en pausa | iris en `puntero.actualizar`, congelado, "afuera" y tope del radio |
| `ui/barra.py` | botones nuevos, dos columnas, Minimizar y pestaña | botón AYUDA rojo y AYUDA en la pestaña | — |
| `ui/teclado.py` y `teclado_logica.py` | Minimizar el teclado | botón AYUDA en el teclado | — |
| `ui/aplicacion.py` | ventana de la lupa, teclado minimizado | ventana de emergencia, alarma y atajo | aviso de calibrar la mirada |
| `ui/indicador.py` | etiquetas "Sin clic" y "Lupa" junto al cursor | — | (imán: dibuja el puntero pegado) |
| `ui/calibracion.py` y `calibracion_guiada.py` | — | — | pasos de la mirada y pantalla completa |
| `sistema/atajos.py` | — | atajo `emergencia` | — |

Cómo evitar choques:
1. **Orden fijo A → B → C.** Nadie empieza el paquete siguiente sin el commit del anterior. Antes de empezar se hace `git log -1` y se corren las pruebas para confirmar el punto de partida (A: 669 pruebas; B y C: lo que deje el anterior).
2. **Bloques marcados.** En los diccionarios compartidos (`FABRICA`, `RANGOS`, `OPCIONES`, `LARGO_TEXTO`, `TXT`, `BOTONES_BARRA`, `ACCIONES_GESTO`) cada paquete agrega sus claves en un bloque nuevo al final, precedido de un comentario `# ---- 1.1 paquete A: ... ----`. No se reordena ni se reformatea lo que ya existe.
3. **Archivos nuevos por paquete.** La lógica nueva va en módulos propios:
   - A: `lupa.py`, `ui/lupa.py`;
   - B: `emergencia.py`, `ui/emergencia.py`, `sistema/alarma.py`;
   - C: `mirada.py`, `ui/calibracion_mirada.py`.

   En los archivos compartidos solo se hacen los "enganches".
4. **Pruebas en archivos nuevos**: `pruebas/test_v11_a_*.py`, `test_v11_b_*.py` y `test_v11_c_*.py`. Una prueba vieja se toca solo si el cambio de comportamiento es intencional; por ejemplo, la barra pasa de 7 a 11 botones. En ese caso se anota en `decisiones.md`.
5. **`estados.py` es el punto más delicado** (lo tocan los tres). Cada paquete agrega métodos propios (`_paso_lupa`, `_paso_emergencia`, `_fuente_ojos...`) y en los métodos existentes cambia solo las líneas indispensables.

---

## PAQUETE A: "Velocidad, minimizar y extras de TD Control"

Objetivo: graduar la velocidad de forma coherente y minimizar la barra y el teclado. Además, traer de TD Control y de los otros programas tres extras de bajo riesgo:
1. **Sin clic** (modo lectura);
2. **Lupa** para clic preciso;
3. **Velocidad arriba y abajo** aparte.

Las demás ideas del informe (perfiles en la interfaz, permanencia adaptativa, zonas excluidas, Ctrl sostenido, copiar y pegar en la barra) quedan como ideas para después.

### A.1 Archivos a tocar
- `lycan_face_control/config.py`: claves nuevas (A.2).
- `lycan_face_control/constantes.py`:
  - `BOTONES_BARRA` con `("sin_clic", "Sin clic")`, `("lupa", "Lupa")` y `("minimizar", "Minimizar")`;
  - submodo `LUPA = "LUPA"` agregado a `SUBMODOS`.
- `lycan_face_control/ui/opciones.py`:
  - `sens_de_velocidad(n, ajuste_vertical)` devuelve `(sens_x, sens_y, joystick_g)`, con la tabla `JOYSTICK_VELOCIDAD`;
  - fila "vel" con botones grandes y filas nuevas.
- `lycan_face_control/estados.py`:
  - `MODOS_CLIC` agrega `"ninguno"` y `"lupa"`;
  - en `_elegir`, los casos `barra:sin_clic` y `barra:lupa`;
  - método nuevo `_paso_lupa`;
  - el disparo de la permanencia libre respeta los modos `ninguno` y `lupa`;
  - en pausa también es elegible `ui:barra_mostrar`.
- `lycan_face_control/lupa.py` (nuevo, lógica pura): zona, ubicación de la ventana y conversión de un punto de la lupa a un punto real de la pantalla.
- `lycan_face_control/ui/lupa.py` (nuevo): captura con Pillow `ImageGrab`, ventana `Toplevel` sin foco y objetivos `lupa:zona` y `lupa:cerrar`.
- `lycan_face_control/ui/barra.py`: botones nuevos, armado en dos columnas cuando no caben, botón Minimizar y pestaña más grande que se abre al posar el puntero.
- `lycan_face_control/teclado_logica.py`: `"minimizar"` en `ACCIONES`.
- `lycan_face_control/ui/teclado.py`: `minimizar()` y `restaurar()`, con una pestaña "Teclado" que conserva el texto escrito.
- `lycan_face_control/ui/aplicacion.py`:
  - crear y cerrar la lupa al recibir `Elegir("lupa:...")`;
  - `alternar_teclado()` restaura el teclado minimizado en vez de abrir uno nuevo.
- `lycan_face_control/ui/indicador.py`: etiqueta "Sin clic" o "Lupa" junto al cursor, igual que hoy "Doble" o "Derecho".
- `lycan_face_control/ui/textos.py`, `docs/especificacion.md` y `docs/decisiones.md`.

### A.2 Claves de configuración nuevas

| Clave | Fábrica | Rango u opciones | Para qué |
|---|---|---|---|
| `puntero.ajuste_vertical` | `1.2` | `(0.8, 2.0)`, paso 0,1 en Opciones | `sens_y = sens_x × ajuste`. Hoy está fijo en 1,2. |
| `barra.boton_sin_clic` | `True` | sí o no | Mostrar el botón "Sin clic" en la barra. |
| `barra.boton_lupa` | `True` | sí o no | Mostrar el botón "Lupa" en la barra. |
| `lupa.zona_px` | `200` | `(120, 400)` | Lado de la zona que se agranda, en píxeles reales. |
| `lupa.aumento` | `3` | `(2, 5)`, entero | Cuántas veces se agranda. |
| `lupa.espera_s` | `8.0` | `(4.0, 20.0)` | Sin elegir nada en ese tiempo, la lupa se cierra sola sin hacer nada. |

**Velocidad sin clave nueva.** La velocidad 1–10 se sigue deduciendo de `puntero.sens_x` con `velocidad_de_sens`. Así una configuración 1.0 se lee igual y no hace falta migrarla. Al cambiar la velocidad en Opciones se escriben los tres valores juntos:
- `sens_x = SENS_VELOCIDAD[n-1]`, la tabla actual (0,92 … 2,75);
- `sens_y = redondear(max(min(sens_x × ajuste_vertical, 3.3), 0.92), 2)`;
- `joystick_g = JOYSTICK_VELOCIDAD[n-1]`, con `JOYSTICK_VELOCIDAD = (1000, 1050, 1200, 1400, 1600, 1800, 2000, 2300, 2600, 3000)`. El nivel 3 es 1200, el valor de fábrica, y todos caben en el rango (600, 3000).

El piso de 0,92 en la vertical sigue la regla que ya está en el código: por debajo de 1,0 el puntero empieza a no llegar a los bordes, y los niveles 1 y 2 apenas bajan. **La calibración del perfil no se toca**: solo cambian las ganancias.

### A.3 Textos exactos en pantalla (claves de `TXT`)

Velocidad (pestaña Puntero):
- `op_velocidad`: "Velocidad del puntero" (ya existe)
- `op_velocidad_valor`: "{n} de 10"
- `op_mas_lento`: "◀ Más lento"
- `op_mas_rapido`: "Más rápido ▶"
- `op_velocidad_ayuda` (se cambia): "1 = más lento; 10 = rápido (basta un movimiento pequeño). Con cualquier valor se llega a toda la pantalla girando la cabeza dentro de su rango cómodo. La calibración no cambia."
- `op_ajuste_vertical`: "Velocidad arriba y abajo"
- `op_ajuste_vertical_igual`: "Igual que a los lados"
- `op_ajuste_vertical_valor`: "{n} % de la de los lados"
- `op_ajuste_vertical_ayuda`: "Si le cuesta más subir y bajar la cabeza que girarla, súbalo."

Lupa (pestaña Clic):
- `op_lupa_aumento`: "La lupa agranda"
- `op_lupa_aumento_valor`: "{n} veces"
- `op_lupa_zona`: "Tamaño de la parte que agranda la lupa"
- `op_lupa_espera`: "La lupa se cierra sola si no elige en"

Botones de la barra (pestaña Comodidad):
- `op_boton_sin_clic`: "Botón «Sin clic» en la barra"
- `op_boton_lupa`: "Botón «Lupa» en la barra"

Barra:
- `barra_sin_clic`: "Sin clic"; `icono_sin_clic`: "⊘"
- `barra_lupa`: "Lupa"; `icono_lupa`: "⊕"
- `barra_minimizar`: "Minimizar"; `icono_minimizar`: "▁"
- `barra_mostrar` (se cambia): "Barra"; `icono_mostrar`: "«" (o la flecha que apunte hacia adentro según el lado)
- `globo_minimizar`: "Esconde la barra en el borde. Para volver a abrirla, deje el puntero un momento sobre la pestaña «Barra»."

Indicador junto al cursor:
- `ind_sin_clic`: "Sin clic"
- `ind_lupa`: "Lupa"

Lupa:
- `lupa_cerrar`: "Cerrar lupa"
- `lupa_instruccion`: "Lleve el puntero al punto exacto y quédese quieto para hacer clic."
- `aviso_lupa_no_captura`: "No pude agrandar esa parte de la pantalla. Intente otra vez o use el clic normal."
- `aviso_lupa_cerrada`: "Cerré la lupa sin hacer clic."
- `aviso_sin_clic`: "Sin clic: puede leer tranquilo; quedarse quieto no hace clic. Para volver, elija «Clic» en la barra."

Teclado:
- `tec_minimizar`: "Minimizar"; `icono_tec_minimizar`: "▁"
- `tec_pestana`: "Teclado"
- `globo_tec_minimizar`: "Esconde el teclado sin borrar lo escrito."

### A.4 Comportamiento

**Velocidad.**
- En la pestaña Puntero, la fila "Velocidad del puntero" muestra dos botones grandes, «◀ Más lento» y «Más rápido ▶» (de al menos 72 px de alto, elegibles con la cabeza), con el valor "3 de 10" en el centro.
- Cada cambio se prueba en vivo, como ya pasa con `_vista_previa`. «Cancelar» lo revierte.
- Debajo va la fila "Velocidad arriba y abajo", con «−» y «+», paso 0,1, mostrada como porcentaje.
- Al cambiar el ajuste vertical, `sens_y` se recalcula con la velocidad actual.

**Minimizar la barra.**
- El botón "Minimizar" va siempre en la barra, al final y antes de AYUDA (que agrega el paquete B). Reemplaza al botón "Ocultar" que hoy aparece solo con `barra.visible = False`.
- Al elegirlo, la barra se esconde y queda la pestaña "Barra" en el mismo borde. La pestaña mide al menos 56 × 120 px en vertical (o 120 × 56 px en horizontal), con letra de 18 pt o más.
- Posar el puntero sobre la pestaña la vuelve a abrir. Es un objetivo `ui:barra_mostrar` con `tiempo_s = 0,6` s propio (abrir la barra no tiene riesgo). Funciona también en pausa.
- La pestaña también se abre con el ratón del cuidador.
- Lo minimizado **no se guarda**: al abrir el programa, la barra sigue `barra.visible`, cuyo texto en Opciones queda como "Mostrar la barra al abrir".
- En el modo Desplazar no se puede minimizar, porque "Terminar" tiene que quedar a la vista. Por eso el botón no aparece en ese modo.

**Barra en dos columnas.**
- Con 11 botones (7 de hoy, más Sin clic, Lupa, Minimizar y AYUDA del paquete B), una sola columna no cabe en 1366×768 con botones de 72 px o más.
- `medidas_barra` pasa a devolver también el número de columnas (o filas, en la barra horizontal). Si `n` botones de `ALTO_MIN` no caben en el largo disponible, se arman en 2 columnas, de arriba abajo y luego a la derecha.
- Nunca se baja de `ALTO_MIN` (72 px).

**Sin clic (modo lectura).**
- "Sin clic" pone `modo_clic = "ninguno"` y queda resaltado en la barra.
- En ese modo, quedarse quieto **fuera** de las ventanas propias no hace nada: ni clic ni sonido. El anillo no se dibuja (el indicador muestra "Sin clic").
- Sobre los botones propios la permanencia sigue funcionando, así la persona puede salir eligiendo "Clic".
- Los gestos de clic (boca, cejas) **sí** hacen clic, porque son a propósito. Así lo dice la Ayuda.
- El modo dura hasta elegir "Clic" u otro modo: `modo_fijo` no lo afecta y reanudar no lo borra.
- El puntero sigue la cabeza, que es la diferencia con Pausa.

**Lupa (clic preciso, como el "Adjust Target" de TD Control).**
1. "Lupa" pone `modo_clic = "lupa"` (resaltado; el indicador dice "Lupa").
2. La siguiente permanencia libre (fuera de las ventanas propias) **no hace clic**:
   - la máquina emite `Elegir("lupa:abrir")` con el punto y entra al submodo `LUPA`;
   - `lupa.zona(origen, monitor, zona_px)` da el cuadrado alrededor del punto, recortado al monitor;
   - `lupa.ubicar_ventana(zona, monitor, lado)` da el rectángulo de la ventana, de lado `zona_px × aumento` (como máximo el 70 % del alto del monitor), en la mitad del monitor **opuesta** a la zona y **sin taparla nunca**. Si no cabe sin taparla, devuelve None, sale `aviso_lupa_no_captura` y se vuelve a NORMAL.
3. La interfaz captura la zona **antes** de mostrar la ventana, para no fotografiarse a sí misma. La imagen se agranda con Pillow y se muestra en un `Toplevel` sin foco (`no_activar`), con:
   - una mira en el centro;
   - el botón "Cerrar lupa" debajo;
   - el texto `lupa_instruccion` arriba.

   La imagen solo vive en memoria y **nunca se guarda en disco** (privacidad).
4. En `LUPA` el puntero se mueve igual que siempre. Quedarse quieto el tiempo de `permanencia.tiempo_s` sobre `lupa:zona` (o hacer el gesto de clic) hace esto:
   - convierte el punto con `lupa.a_pantalla(p, ventana, zona)`: `origen_zona + (p − origen_ventana) / aumento`;
   - emite `Mover(x, y)` y `Clic(izq)` en el punto real, que no queda tapado por la lupa;
   - emite `Elegir("lupa:cerrar")`;
   - fija el puntero en el punto real y desarma la permanencia tras deslizar (`_desarmar_tras_deslizar`);
   - vuelve a `modo_clic = "izq"`, salvo con `barra.modo_fijo`, donde sigue en "lupa".
5. La lupa se cierra **sin hacer nada** en cualquiera de estos casos:
   - con "Cerrar lupa";
   - después de `lupa.espera_s`;
   - con pausa, sin cara, "mirando afuera", calibración, el teclado u Opciones;
   - con cualquier `SoltarTodo`.

   En todos se dice `aviso_lupa_cerrada` y se vuelve a NORMAL.
6. Si la captura falla (pantalla protegida, error de Pillow), sale `aviso_lupa_no_captura`, se vuelve a NORMAL y no se hace ningún clic.
7. Las coordenadas son físicas. El proceso ya es consciente del DPI (`sistema/dpi.py`). Se prueba con un monitor simulado al 125 % y con dos monitores.
8. El paquete C reutiliza esta misma lupa para los ojos.

**Minimizar el teclado.**
- El teclado tiene la acción "Minimizar" junto a "Cerrar". Al elegirla:
  - la ventana se esconde (`withdraw`) y la escritura no se borra;
  - la máquina vuelve a `NORMAL` con `poner_submodo`, así el puntero manda otra vez;
  - aparece la pestaña "Teclado" en el borde del teclado (abajo o arriba según `teclado.posicion`), de al menos 160 × 56 px.
- Posar el puntero 0,6 s sobre la pestaña, elegir "Teclado" en la barra o usar el atajo del teclado lo **restauran** con el texto tal como estaba.
- "Cerrar" sigue cerrando como hoy.
- **Seguridad:** en el barrido y en "Solo comunicación", "Minimizar" **no se ofrece** (sale de `filas_barrido` y de la disposición). Quien solo parpadea no podría volver a abrir una pestaña con el puntero.

### A.5 Pruebas (nuevas, `pruebas/test_v11_a_*.py`)

Velocidad:
- `sens_de_velocidad` es monótona en los tres valores. El nivel 3 da (1,0; 1,2; 1200).
- Ningún nivel deja `sens_y` por debajo de 0,92 ni por encima de 3,3, para cualquier `ajuste_vertical` del rango.
- Todos los valores pasan por `validar` sin correcciones.
- Cambiar la velocidad o el ajuste vertical deja intacta `perfiles.*.calibracion`.
- Con una configuración 1.0 sin `ajuste_vertical`, la velocidad leída no cambia y la clave toma 1,2.
- `ajuste_vertical` con NaN, texto o 5,0 vuelve a 1,2.
- En una cara sintética que gira hasta el extremo calibrado, el puntero llega al borde con la velocidad 1 y el ajuste 0,8.
- En la pestaña Puntero de Opciones, "Más rápido" diez veces se queda en "10 de 10" y "Más lento" en "1 de 10". «Cancelar» devuelve la configuración anterior al motor.

Barra:
- `medidas_barra` arma 11 botones en 1366×768, 1280×720 y 1920×1080, con la letra al 100 % y al 200 %, en los cuatro lados. Ningún botón mide menos de 72 px, todo cabe en el área de trabajo y usa 2 columnas cuando hace falta.
- Minimizar esconde la barra y muestra la pestaña.
- `ui:barra_mostrar` se elige quedándose quieto 0,6 s en ACTIVO y en PAUSA.
- Pasar por encima de la pestaña sin quedarse quieto no la abre.
- En el modo Desplazar no hay botón Minimizar.

Sin clic:
- En "ninguno", 5 minutos de cabeza quieta con ruido real (las series de `pruebas/datos`) sobre un punto externo dan **0 clics**.
- Sobre `barra:clic`, la permanencia sí elige y vuelve a "izq".
- Un gesto de boca hace clic.
- Pausar y reanudar conserva el modo "ninguno".

Lupa (lógica pura):
- La zona se recorta en las cuatro esquinas del monitor.
- La ventana nunca se cruza con la zona (prueba con muchos puntos al azar y semilla fija).
- `a_pantalla` es la inversa exacta de la conversión de la zona a la ventana (ida y vuelta con un error de ±1 px).
- Con dos monitores y un origen negativo, las coordenadas son correctas.

Lupa (máquina):
- En el modo "lupa", la permanencia libre emite `Elegir("lupa:abrir")` y **ningún** `Clic`.
- La permanencia sobre `lupa:zona` emite `Mover` al punto convertido y `Clic(izq)` una sola vez.
- `espera_s` sin elegir cierra sin clic.
- Pausa, sin cara o "mirando afuera" cierran sin clic.
- Si la captura falla (simulada), se vuelve a NORMAL sin clic.
- Con `modo_fijo`, el modo sigue en "lupa".

Teclado:
- Minimizar conserva el texto y restaurar lo devuelve.
- La barra "Teclado" restaura en vez de abrir uno vacío.
- En el barrido y en "Solo comunicación" no está la acción "minimizar".
- Los rótulos "Minimizar" y "Cerrar" caben en 1196×720.

Configuración: rangos de `lupa.*` y valores booleanos de los botones (con tipo equivocado vuelven al de fábrica).

Toda la suite actual sigue en verde. Las pruebas que cuentan 7 botones se actualizan, y eso se anota en `decisiones.md`.

### A.6 Decisiones a anotar
- La velocidad no tiene clave propia: se deduce de `sens_x` y escribe tres valores.
- "Sin clic" deja funcionar los gestos de clic.
- La lupa nunca tapa la zona que agranda, para poder hacer clic al instante sin esperar a que se cierre.
- La imagen de la lupa no se guarda.
- Lo minimizado no se guarda.
- No se ofrece minimizar en el barrido.
- La barra se arma en dos columnas.

---

## PAQUETE B: "Emergencia" (botón AYUDA)

Objetivo: que la persona pueda pedir ayuda sin manos en cualquier momento, **también en pausa**, con:
- pantalla roja;
- alarma fuerte que funciona sin internet;
- voz.

Que no pueda dispararse por un parpadeo natural ni por pasar el puntero por encima. Que se apague fácil: la persona con "Ya me atendieron" y el cuidador con Esc, el ratón o Ctrl+Alt+A.

Sin internet en esta versión. Avisar por WhatsApp, SMS o correo queda anotado como idea futura en `decisiones.md`.

### B.1 Archivos a tocar
- `lycan_face_control/config.py`: bloque `emergencia`, `atajos.emergencia` y `LARGO_TEXTO["emergencia.mensaje"]`. En `_coherencia`, un gesto **corto** con la acción "emergencia" pasa a "ninguna" y queda anotado (solo se permite en el gesto largo).
- `lycan_face_control/constantes.py`:
  - `"emergencia"` al final de `ACCIONES_GESTO`;
  - `ID_EMERGENCIA_BARRA = "barra:ayuda"`, `ID_EMERGENCIA_TECLADO = "teclado:ayuda"`, `ID_EMERGENCIA_PESTANA = "pestana:ayuda"` e `ID_ATENDIDO = "emergencia:atendido"`;
  - `IDS_EMERGENCIA` con los tres primeros.
- `lycan_face_control/emergencia.py` (nuevo, lógica pura y sin tkinter):
  - `PlanAlarma(t0, repetir_voz, repetir_s, duracion_voz_s)` dice en cada momento si toca alarma, voz o silencio;
  - `mensaje_voz(cfg)` y `textos_pantalla(cfg)`.
- `lycan_face_control/sistema/alarma.py` (nuevo):
  - genera un WAV en memoria con `wave` y `struct`: dos tonos que se alternan (960 y 640 Hz, 0,35 s cada uno, amplitud según `emergencia.volumen`);
  - la primera vez lo escribe en `carpeta_datos()/alarma.wav`; si no se puede, usa la carpeta temporal;
  - lo toca con `winsound.PlaySound(ruta, SND_FILENAME | SND_ASYNC | SND_LOOP)`;
  - `detener()` llama a `PlaySound(None, 0)`;
  - si falla, usa como respaldo `winsound.Beep` en un hilo.

  No usa internet, no hay archivos binarios en el repositorio y no se toca el volumen de Windows.
- `lycan_face_control/estados.py`:
  - atributo `self.emergencia` (False o True), con `self._estado_antes_emergencia`;
  - métodos `pedir_ayuda(t, origen)`, `atendido(t, origen)` y `_paso_emergencia`;
  - en `_en_pausa`, los candidatos son `IDS_REANUDAR + IDS_EMERGENCIA`;
  - en `_en_activo`, los objetivos `IDS_EMERGENCIA` usan `emergencia.permanencia_s`;
  - `_accion_gesto("emergencia")` y la misma acción en pausa.
- `lycan_face_control/motor.py`: `atajo("emergencia")` emite la orden `("atendido",)`. En el hilo de atajos también se detiene la alarma al instante, como ya se suelta todo con "pausar".
- `lycan_face_control/sistema/atajos.py`: el nombre `emergencia` entra en `orden_registro`.
- `lycan_face_control/ui/emergencia.py` (nuevo): ventana de pantalla completa.
- `lycan_face_control/ui/barra.py`: botón AYUDA rojo, al final, con doble separación antes. La pestaña de la barra minimizada lleva también un botón AYUDA rojo de al menos 72 px.
- `lycan_face_control/teclado_logica.py` y `ui/teclado.py`:
  - acción `"emergencia"` en la **primera fila de acciones**, para que el barrido la alcance en pocos segundos;
  - en el barrido y en "Solo comunicación" queda en el primer grupo que se ilumina.
- `lycan_face_control/ui/aplicacion.py`: atiende `Aviso("emergencia")` y `Aviso("emergencia_fin")`, abre y cierra la ventana, arranca el plan de alarma y voz con `root.after`, y detiene todo en `finalizar()` y `salir_seguro()`.
- `lycan_face_control/ui/opciones.py`: pestaña nueva `"emergencia"` y botón "Probar la alarma (3 segundos)".
- `lycan_face_control/ui/textos.py`:
  - textos nuevos;
  - `btn_ayuda` y `tec_ayuda_btn` pasan de "Ayuda" a **"Cómo usar"**, para que la palabra AYUDA solo signifique emergencia.

  La Ayuda (ventana) explica el botón AYUDA.
- `lycan_face_control/ui/ayuda.py` (página nueva "Botón AYUDA"), `docs/especificacion.md` y `docs/decisiones.md`.

### B.2 Claves de configuración nuevas

| Clave | Fábrica | Rango u opciones | Para qué |
|---|---|---|---|
| `emergencia.activa` | `True` | sí o no | Mostrar el botón AYUDA (barra, pestaña y teclado). |
| `emergencia.mensaje` | `"Necesito ayuda"` | texto de 1 a 60 caracteres (`LARGO_TEXTO`) | Lo que dice la voz. |
| `emergencia.volumen` | `100` | `(10, 100)` | Fuerza de la alarma (amplitud del sonido). |
| `emergencia.repetir_voz` | `True` | sí o no | Decir el mensaje entre las alarmas. |
| `emergencia.repetir_s` | `12` | `(5, 60)`, entero | Cada cuánto se repite la voz. |
| `emergencia.permanencia_s` | `2.5` | `(1.5, 5.0)` | Tiempo quieto sobre AYUDA para pedir ayuda (más largo que un botón normal, que es 1,0). |
| `emergencia.detener_s` | `3.0` | `(2.0, 5.0)` | Tiempo quieto sobre "Ya me atendieron". |
| `atajos.emergencia` | `"Ctrl+Alt+A"` | se valida como los demás atajos (`atajos_validos`, `produce_caracter`) | El cuidador apaga la alarma. |

`ACCIONES_GESTO` suma `"emergencia"`, que se puede asignar al **gesto largo** de boca, cejas o sonrisa. **No** se agrega a `ACCIONES_PARPADEO`, porque un parpadeo largo de sueño o cansancio no debe hacer sonar una alarma de noche. Quien solo parpadea tiene AYUDA en el primer grupo del barrido.

### B.3 Textos exactos en pantalla
- `barra_ayuda`: "AYUDA"; `icono_ayuda`: "!"
- `tec_emergencia`: "AYUDA"; `icono_tec_emergencia`: "!"
- `btn_ayuda` (se cambia): "Cómo usar"; `tec_ayuda_btn` (se cambia): "Cómo usar"
- `globo_ayuda_emergencia`: "Para pedir ayuda: quédese quieto sobre AYUDA hasta que se llene el círculo."
- `emergencia_titulo`: "NECESITO AYUDA"
- `emergencia_llamando`: "Por favor, que venga {cuidador}."
- `emergencia_voz`: "{mensaje}. Por favor, que venga {cuidador}."; con los valores de fábrica dice "Necesito ayuda. Por favor, que venga alguien."
- `emergencia_atendido`: "Ya me atendieron"
- `emergencia_como_parar`: "Quédese quieto sobre «Ya me atendieron». Quien cuida puede presionar Esc, hacer clic en ese botón o usar {atajo}."
- `aviso_emergencia_fin`: "Alarma apagada."
- `aviso_alarma_falla`: "No pude hacer sonar la alarma. La pantalla roja y la voz siguen."
- `aviso_emergencia_apagada`: "Sin el botón AYUDA, la persona no podrá pedir ayuda con la cabeza."
- `op_pestana_emergencia`: "Emergencia"
- `op_emergencia_activa`: "Botón AYUDA (emergencia)"
- `op_emergencia_mensaje`: "Lo que dice la voz cuando pide ayuda"
- `op_emergencia_volumen`: "Volumen de la alarma"
- `op_emergencia_voz`: "Decir el mensaje en voz alta"
- `op_emergencia_cada`: "Repetir el mensaje cada"
- `op_emergencia_tiempo`: "Tiempo quieto sobre AYUDA para pedir ayuda"
- `op_emergencia_detener`: "Tiempo quieto sobre «Ya me atendieron»"
- `op_emergencia_probar`: "Probar la alarma (3 segundos)"
- `op_emergencia_nota`: "La alarma usa los parlantes del computador: deje el volumen de Windows alto. No envía mensajes por internet."
- `op_atajo_emergencia`: "Apagar la alarma de AYUDA"
- `accion_emergencia`: "Pedir AYUDA (alarma)"

### B.4 Comportamiento

**Cómo se pide ayuda.**
- **Con la cabeza**: quedarse quieto `emergencia.permanencia_s` (2,5 s) sobre AYUDA en la barra, en la pestaña o en el teclado.
  - El anillo se llena como siempre. Pasar por encima no basta.
  - Vale en ACTIVO (todos los submodos con puntero) **y en PAUSA**, incluida la pausa que puso el cuidador y la pausa automática.
  - En el modo Sin clic y en el modo Lupa también vale, porque es un botón propio.
- **En el barrido**: elegir AYUDA (primer grupo) con el parpadeo largo, como cualquier tecla.
- **Con un gesto largo** asignado a "emergencia": vale en ACTIVO y en PAUSA. En pausa se cuenta solo el gesto largo completo, así un bostezo corto no basta. Un gesto con los ojos cerrando se ignora, como hoy.
- **Lo que no pide ayuda**: un parpadeo natural o largo, el gesto corto (la validación lo impide) o pasar por encima del botón.

**Al activarse.**
1. La máquina:
   - emite `SoltarTodo("emergencia")`;
   - sale de los submodos con botón (arrastre, desplazar, lupa);
   - guarda el estado anterior y pone `self.emergencia = True`;
   - emite `Aviso("emergencia")`.

   El registro anota "Emergencia activada (botón | gesto | barrido)", sin ningún texto de la persona.
2. La interfaz abre `ui/emergencia.py`:
   - un `Toplevel` a pantalla completa en el monitor del mapeo, siempre encima;
   - fondo rojo `#c00000` que alterna con `#5a0000` **una vez por segundo**. Es menos de 3 destellos por segundo, por seguridad ante las convulsiones (WCAG 2.3.1);
   - "NECESITO AYUDA" en letra de 72 pt o más, en blanco;
   - debajo, "Por favor, que venga {cuidador}.";
   - un botón grande "Ya me atendieron" (al menos 300 × 120 px), en verde sobre fondo oscuro, que es el objetivo `emergencia:atendido`;
   - abajo, el texto `emergencia_como_parar`.

   Esta ventana **sí toma el foco**, a diferencia de las demás (`focus_force`), para que Esc llegue. Ya se soltó todo y nadie está escribiendo.
3. Alarma y voz según `PlanAlarma`:
   - la alarma suena en bucle;
   - cada `repetir_s` se detiene, la voz dice `emergencia_voz` con `urgente=True` (volumen 100) y, al terminar, vuelve la alarma. La duración de la voz se calcula con `0,08 s × letras + 1 s`;
   - si `repetir_voz` es False, solo suena la alarma;
   - si la voz no existe, solo la alarma; si la alarma falla, `aviso_alarma_falla` y solo la voz.
4. Mientras dura la emergencia:
   - el puntero se mueve, pero **ningún** clic llega a Windows (ni por permanencia ni por gesto);
   - el único objetivo elegible es `emergencia:atendido`, con `emergencia.detener_s`;
   - la cara perdida no detiene nada;
   - "mirando afuera" no detiene nada.

**Cómo se apaga.**
- La persona se queda quieta `detener_s` sobre "Ya me atendieron".
- El cuidador tiene tres caminos:
  - Esc en la ventana;
  - clic con el ratón en "Ya me atendieron";
  - el atajo `atajos.emergencia` (Ctrl+Alt+A) desde cualquier programa. El atajo detiene el sonido ya en el hilo de atajos.
- Salir del programa también la detiene: `finalizar()` llama a `alarma.detener()`.
- Al apagarse:
  - la máquina vuelve al estado anterior (ACTIVO o PAUSA), con `_desarmar_tras_deslizar` y los botones AYUDA bloqueados hasta que el puntero salga de ellos, igual que hoy `IDS_PAUSA`;
  - sale el aviso "Alarma apagada.";
  - el atajo, cuando no hay emergencia, no hace nada.
- **Probar la alarma** (en Opciones) hace sonar la alarma 3 s y muestra la ventana roja 3 s. Se detiene sola y no cambia el estado.

**Si el motor está caído** (detección rendida): la barra y el teclado siguen en pantalla. Elegir AYUDA con el ratón (el cuidador) abre la emergencia directo desde la interfaz.

**Idea futura** (no en 1.1): avisar al celular del cuidador sin internet propio, por ejemplo con un timbre Bluetooth o un mensaje por la red de la casa, y una alarma si no se ve la cara de noche durante X minutos.

### B.5 Pruebas (nuevas, `pruebas/test_v11_b_*.py`)

Configuración:
- los rangos de `emergencia.*`;
- un mensaje vacío o de 200 caracteres vuelve al de fábrica;
- `gestos.boca.corto = "emergencia"` pasa a "ninguna" con problema anotado, y en el gesto largo se acepta;
- una configuración vieja sin el bloque `emergencia` toma los valores de fábrica;
- `atajos.emergencia` inválido o repetido con otro atajo da el aviso correspondiente.

Máquina, con caras sintéticas:
- quieto 2,4 s sobre `barra:ayuda` no dispara y 2,5 s sí;
- pasar por encima sin parar (barrido de la cabeza a 300 px/s) no dispara;
- en PAUSA puesta por el cuidador, quieto sobre AYUDA dispara;
- con la pausa automática por falta de cara, al volver la cara y quedarse quieto sobre AYUDA, dispara;
- durante la emergencia, 60 s de movimiento y gestos de boca y cejas dan **cero** `Clic`, `Bajar` o `Rueda`;
- quieto `detener_s` sobre `emergencia:atendido` vuelve al estado anterior;
- el atajo `atendido` también;
- después, AYUDA queda bloqueado hasta salir del botón (no se vuelve a disparar quieto encima);
- el gesto largo "emergencia" dispara en ACTIVO y en PAUSA, y el gesto corto nunca;
- 5 minutos de parpadeos naturales y largos con barrido apagado no disparan nunca;
- en el barrido, AYUDA está en el primer grupo y se elige con un parpadeo largo;
- en el modo Desplazar y en el arrastre, pedir ayuda suelta el botón (`Subir`) antes de todo.

`PlanAlarma`:
- con `repetir_s = 12`, la voz cae en 12, 24, 36… y la alarma se calla mientras habla;
- sin voz, la alarma es continua;
- con `repetir_voz = False`, nunca hay voz.

`sistema/alarma.py`:
- el WAV generado es válido (cabecera, 16 bits, duración esperada) y su amplitud escala con `volumen`;
- si no se puede escribir en la carpeta de datos, usa la temporal;
- con `PlaySound` simulado que falla, se usa el respaldo y se avisa;
- no se usa ninguna red: se revisa que el módulo no importe `socket`, `urllib` ni `http`.

Interfaz (Tk, sin cámara):
- la ventana abre a pantalla completa;
- Esc la cierra;
- el clic en el botón la cierra;
- el color alterna como máximo 1 vez por segundo;
- "NECESITO AYUDA" y el nombre del cuidador aparecen;
- "Cómo usar" reemplaza a "Ayuda" en la ventana principal y en el teclado;
- con `emergencia.activa = False` no hay botones AYUDA.

Textos: sin tuteo ni palabras prohibidas.

### B.6 Decisiones a anotar
- Se usa permanencia larga (2,5 s) en vez de confirmación en dos pasos: en una urgencia real, un segundo paso puede fallar, y una falsa alarma se apaga fácil.
- El parpadeo no puede pedir ayuda (fuera del barrido).
- El gesto corto tampoco.
- La ventana de emergencia es la única que toma el foco.
- El destello es de 1 vez por segundo.
- No se toca el volumen de Windows.
- Sin internet.
- "Ayuda" pasa a "Cómo usar".

---

## PAQUETE C: "Mover con los ojos"

Objetivo: elegir con qué se mueve el puntero: **la cabeza**, **los ojos** o **ojos y cabeza** (recomendado: los ojos saltan y la cabeza afina). Para eso hacen falta:
- medidas del iris;
- calibración de mirada guiada con puntos en pantalla;
- filtro de fijación y sacada;
- radio de permanencia mayor;
- imán hacia los botones propios;
- la lupa del paquete A;
- un texto honesto sobre la precisión.

Con la fuente "cabeza" (la de fábrica), el programa se comporta **exactamente** igual que hoy.

### C.1 Archivos a tocar
- `lycan_face_control/constantes.py`:
  - `IRIS_DER_ANILLO = (469, 470, 471, 472)` e `IRIS_IZQ_ANILLO = (474, 475, 476, 477)`;
  - `PARPADO_MEDIO_DER = (159, 145)` y `PARPADO_MEDIO_IZQ = (386, 374)`;
  - **no** se agregan a `PUNTOS_CLAVE`: una cara de 468 puntos sigue siendo válida.
- `lycan_face_control/cara.py`:
  - campos nuevos **al final** de `Medidas`, todos con valor por defecto: `iris_x`, `iris_y`, `iris_der`, `iris_izq` (None);
  - cálculo en el marco del ojo, dividido por su ancho, con el eje global 33→263, ponderado por el EAR y descartando el ojo que esté más cerrado (EAR menor que 0,6 × el del otro);
  - devuelve None si hay menos de 478 puntos o NaN;
  - `medir_si_valida` **no** exige el iris.
- `lycan_face_control/mirada.py` (nuevo, lógica pura con numpy):
  - `rasgos(m)`;
  - `ModeloMirada`: lineal con 5 puntos y `[1, ix, iy, dyaw, dpitch]`; polinomio de 2.º grado con 9 puntos, más dyaw y dpitch; con ridge λ = 1e-3 sobre rasgos estandarizados. Métodos `ajustar`, `predecir`, `ganancia_px`, `como_dict` y `desde_dict`. Devuelve None si la matriz está mal condicionada;
  - `FiltroFijacion`: dos OneEuro más el detector de sacada por velocidad; reinicio en la sacada; `en_fijacion` y `t_fijacion_desde`.
- `lycan_face_control/puntero.py`:
  - `actualizar(t, yaw, pitch, iris=None)`;
  - clase interna `_FuenteMirada` con la misma interfaz que el mapeo;
  - fuente "ojos": fuerza el modo absoluto y queda quieta si `iris` es None;
  - fuente "cabeza_y_ojos": la cabeza en modo relativo con `ojos.ganancia_fina`, y salto a la mirada tras una fijación de `ojos.fijacion_ms` lejos de más de `ojos.salto_px`, con una mezcla de unos 150 ms.
- `lycan_face_control/estados.py`:
  - pasa `(m.iris_x, m.iris_y)` en las dos llamadas a `puntero.actualizar`;
  - en las fuentes con ojos congela **siempre** con `g.ojos_cerrando`, porque FaceMesh baja el iris al cerrar los ojos;
  - `_mirando_afuera` con la mirada fuera del monitor más de un 15 %, con histéresis;
  - `RADIO_MAX_OJOS = 120` px como tope de `ajustar_radio_minimo`;
  - después de un salto, `_desarmar_tras_deslizar`;
  - permanencia propia `ojos.permanencia_s`;
  - imán con `ojos.franja` en `buscar_objetivo`;
  - con `ojos.lupa`, la permanencia libre abre la lupa del paquete A en vez de hacer clic.
- `lycan_face_control/permanencia.py`: `ajustar_radio_minimo(minimo, factor, tope=None)`.
- `lycan_face_control/calibracion_guiada.py`: pasos `mirada_centro`, `mirada_puntos`, `mirada_cabeza` (el paso de los ojos quietos con la cabeza en movimiento) y `mirada_validar`, después de "aba", solo si `puntero.fuente != "cabeza"`. Un punto con la cabeza movida más de 3 × su temblor se repite. El reloj solo corre con la cara y los dos ojos abiertos.
- `lycan_face_control/calibracion.py`:
  - `calibracion_valida` revisa `cal["mirada"]` aparte. Si falta o no sirve, la fuente vuelve a "cabeza" con aviso, sin romper la calibración de la cabeza;
  - la calibración de mirada queda inválida si cambian el monitor o la resolución de la cámara.
- `lycan_face_control/ui/calibracion_mirada.py` (nuevo): `Toplevel` a pantalla completa, siempre encima y sin activar, en el monitor del mapeo. Dibuja puntos que se encogen, en coordenadas reales, con un margen del 8 %.
- `lycan_face_control/ui/calibracion.py`: selector "Mover el puntero con" en la pantalla de inicio; los pasos de mirada se muestran en la ventana nueva; el resultado se dice en palabras.
- `lycan_face_control/ui/opciones.py`: en la pestaña Puntero, la fila "Mover el puntero con" y las filas de ojos (página 2). Al elegir ojos, una sugerencia de subir la cámara a 1280×720.
- `lycan_face_control/ui/indicador.py`: con el imán, el anillo se dibuja en el centro del botón pegado.
- `lycan_face_control/ui/textos.py`, `ui/ayuda.py` (página "Mover con los ojos"), `docs/especificacion.md` y `docs/decisiones.md`.
- `pruebas/sintetico/cara_sintetica.py`:
  - en `cara()`, los parámetros `ojo_yaw=0`, `ojo_pitch=0` y `ruido_iris=0`. El iris se mueve R·sin(ángulo), con R = 0,40 × el ancho del ojo, y el anillo se encoge por cos(ojo_yaw);
  - opcionales: `parpado_sigue` y la bajada del iris al cerrar el ojo;
  - las tres claves nuevas en `_NUMERICOS` y `POR_DEFECTO`;
  - ayudante `mirar_a(px, py, cabeza_yaw, cabeza_pitch, monitor, distancia_cm=60, px_por_cm)`.

### C.2 Claves de configuración nuevas

| Clave | Fábrica | Rango u opciones |
|---|---|---|
| `puntero.fuente` | `"cabeza"` | `("cabeza", "ojos", "cabeza_y_ojos")` en `OPCIONES` |
| `ojos.suavidad` | `3` | `(1, 5)` |
| `ojos.puntos_cal` | `9` | `(5, 9)` y además solo 5 o 9 (regla en `_coherencia`: otro valor pasa a 9) |
| `ojos.fijacion_ms` | `250` | `(100, 800)` |
| `ojos.salto_px` | `200` | `(80, 600)` |
| `ojos.ganancia_fina` | `0.4` | `(0.2, 1.0)` |
| `ojos.permanencia_s` | `1.3` | `(0.6, 3.0)` |
| `ojos.franja` | `0.35` | `(0.12, 0.6)` |
| `ojos.iman` | `True` | sí o no |
| `ojos.iman_px` | `80` | `(0, 200)` |
| `ojos.lupa` | `True` | sí o no (usa `lupa.aumento` y `lupa.zona_px` del paquete A, sin claves repetidas) |

Una configuración vieja sin estas claves toma los valores de fábrica, y la fuente queda en "cabeza". Si `puntero.fuente` no es "cabeza" y el perfil no tiene `cal["mirada"]` válida, el motor usa "cabeza" y avisa `aviso_ojos_sin_calibrar`. La opción guardada no se borra.

Calibración guardada en `perfiles.<perfil>.calibracion.mirada`: `{"tipo", "coef_x", "coef_y", "media", "escala", "cabeza0", "temblor_iris", "error_px", "error_grados", "io_fraccion", "monitor", "camara", "fecha"}`. `_json_seguro` ya la acepta.

### C.3 Textos exactos en pantalla
- `op_fuente`: "Mover el puntero con"
- `op_fuente_cabeza`: "La cabeza"
- `op_fuente_ojos`: "Los ojos"
- `op_fuente_cabeza_y_ojos`: "Ojos y cabeza (recomendado)"
- `op_fuente_ayuda`: "Con los ojos el puntero llega rápido, pero cae a unos 3 a 5 cm de donde mira. «Ojos y cabeza»: los ojos lo llevan cerca y un movimiento pequeño de la cabeza lo deja justo encima."
- `op_ojos_suavidad`: "Suavidad con los ojos"
- `op_ojos_permanencia`: "Tiempo quieto para hacer clic con los ojos"
- `op_ojos_salto`: "Distancia para que el puntero salte a donde mira"
- `op_ojos_fina`: "Velocidad del ajuste con la cabeza"
- `op_ojos_iman`: "Pegar el puntero a los botones grandes"
- `op_ojos_lupa`: "Abrir la lupa antes de cada clic con los ojos"
- `op_ojos_puntos`: "Puntos para calibrar los ojos"
- `op_ojos_camara`: "Con los ojos funciona mejor con la cámara en 1280 × 720 (usa más el procesador). ¿Cambiarla?"
- `cal_fuente`: "Mover el puntero con"
- `cal_mirada_centro_titulo`: "Ojos: centro"
- `cal_mirada_centro`: "Mire el punto del centro sin mover la cabeza."
- `cal_mirada_puntos_titulo`: "Ojos: puntos"
- `cal_mirada_puntos`: "Siga el punto solo con los ojos. Deje la cabeza quieta."
- `cal_mirada_cabeza_titulo`: "Ojos fijos, cabeza en movimiento"
- `cal_mirada_cabeza`: "Mire el punto del centro y, sin dejar de mirarlo, mueva la cabeza despacio a los lados y arriba y abajo."
- `cal_mirada_validar_titulo`: "Ojos: comprobar"
- `cal_mirada_validar`: "Mire cada punto nuevo."
- `cal_mirada_repetir`: "Mueva solo los ojos y deje la cabeza quieta. Repito este punto."
- `cal_mirada_sin_ojos`: "No veo bien sus ojos. Abra los ojos, quite los reflejos de los lentes o mejore la luz de frente."
- `cal_mirada_resultado`: "Con los ojos, el puntero cae a unos {cm} cm de donde usted mira. Use botones de al menos {boton} cm o la lupa."
- `cal_mirada_impreciso`: "Con esta cámara los ojos quedaron poco precisos (unos {cm} cm). Le recomiendo «Ojos y cabeza» o «La cabeza»."
- `aviso_ojos_sin_calibrar`: "Para mover el puntero con los ojos primero hay que calibrarlos. Mientras tanto uso la cabeza."
- `aviso_ojos_distancia`: "Acérquese o aléjese hasta quedar como cuando calibró los ojos."
- `aviso_ojos_recentrar`: "Mire el punto del centro un segundo…"
- `ayuda_ojos` (página de la Ayuda, texto honesto): "Con la cámara del computador, los ojos sirven para decir «quiero ir allá» más que para apuntar exacto. El puntero cae a unos 3 a 5 cm de donde mira, como el ancho de un dedo pulgar o un poco más. Sirve muy bien para el teclado de la pantalla, la barra de botones y para cruzar la pantalla rápido sin mover el cuello. Para cosas pequeñas, como la X de una ventana o un menú, use la lupa o «Ojos y cabeza». Funciona mejor con buena luz de frente, la cara a unos 50 a 60 cm, sin reflejos en los lentes. Con el tiempo se corre un poco: use «Recentrar» mirando el centro, y calibre de nuevo si cambia de silla, de cama o de pantalla. No es tan preciso como un aparato especial para los ojos. Mirar a propósito cansa: tome descansos."

### C.4 Comportamiento
- **Fuente "cabeza"**: sin cambios en ningún módulo. Los caminos nuevos se activan solo con otra fuente.
- **Fuente "ojos"**:
  - el puntero va a donde predice el modelo, con `FiltroFijacion` (en la fijación suaviza fuerte; en la sacada salta sin retraso), y después pasa por `_paso_absoluto` (zona muerta, recorte y mezclas);
  - sin iris (ojo cerrado, NaN, 468 puntos), el puntero queda quieto y nunca cae a la cabeza;
  - permanencia `ojos.permanencia_s`, radio ≥ 4 × temblor_px con tope de 120 px;
  - con `ojos.lupa`, la permanencia libre abre la lupa y el clic se hace dentro de ella.
- **Fuente "cabeza_y_ojos"**:
  - la cabeza mueve en modo relativo con `ganancia_fina`;
  - una fijación de `fijacion_ms` o más, a más de `salto_px` del puntero, lo hace saltar a la mirada (mezcla de unos 150 ms) **sin hacer clic** (`_desarmar_tras_deslizar`);
  - el temblor de la mirada cerca del puntero no hace nada.
- **Imán**: en las fuentes con ojos, cerca (≤ `iman_px`) de un botón propio elegible el puntero se dibuja en su centro. Se suelta al salir de la franja más un 20 %. No hay imán sobre otros programas.
- **Recentrar** (el mismo atajo y gesto de hoy): en las fuentes con ojos, pide mirar el punto del centro 1 s y corrige solo el desplazamiento.
- **Parpadeo**: congela el puntero 150 ms hacia atrás (`congelar`) siempre que haya `ojos_cerrando`. Los parpadeos naturales siguen sin hacer nada.
- **Calibración de mirada** (solo si la fuente usa ojos):
  1. 2 s en el centro (temblor del iris);
  2. 9 puntos (o 5): 1,0 s de preparación y 1,2 s de medida, descartando los primeros 0,4 s, con la mediana;
  3. 4 s mirando el centro con la cabeza en movimiento;
  4. 4 puntos de validación con el error real.

  Cada paso tiene su botón "?" con la ayuda, como los pasos actuales, y "Repetir este paso" o "Atrás". Si el error pasa de unos 250 px, se dice `cal_mirada_impreciso`. Si `io_fraccion` cambia más de un 20 % al usarla, se dice `aviso_ojos_distancia`.
- Las reglas de seguridad no cambian:
  - sin cara: pausa;
  - otra cara: pausa;
  - "mirando afuera": congela;
  - la emergencia del paquete B vale igual con cualquier fuente.

### C.5 Pruebas (nuevas, `pruebas/test_v11_c_*.py`, todas con caras sintéticas)

a) **Cara**:
- `iris_x` crece de forma monótona con `ojo_yaw` y es 0 ± ε con la mirada al frente;
- no cambia con la escala, el centro ni la inclinación lateral de ±15°;
- con 468 puntos, `iris_x is None` y el resto se mide igual;
- con NaN en el iris da None sin fallar;
- con un ojo cerrado se usa el otro.

b) **Modelo**:
- 9 puntos sin ruido dan un error menor que 5 px;
- con `ruido_iris = 0,3` px queda bajo un tope documentado;
- con 5 puntos se usa el modelo lineal;
- puntos iguales, NaN o pocos puntos dan None;
- ida y vuelta por `como_dict` y `desde_dict`;
- cambiar el monitor o la cámara invalida el modelo.

c) **Cabeza en movimiento**: con el paso de la cabeza, mirar fijo mientras la cabeza gira ±8° da un error menor que un tope. Sin ese paso, el error es claramente mayor.

d) **Fuente "ojos"**:
- 5 minutos de fijación con ruido no dan clics fantasma;
- una sacada de 600 px llega en menos de unos 150 ms;
- un parpadeo con el iris bajando no mueve el puntero;
- sin iris, el puntero queda quieto;
- el radio nunca pasa de 120 px.

e) **Fuente "cabeza_y_ojos"**:
- el ruido de la mirada cerca del puntero no provoca saltos;
- una fijación lejana de 250 ms hace saltar el puntero sin clic;
- la cabeza mueve con `ganancia_fina`.

f) **Guía**:
- una secuencia sintética de 9 puntos da `cal["mirada"]` válida;
- un punto con la cabeza movida se repite;
- sin ver los ojos, el reloj se detiene;
- con `puntos_cal = 7`, se corrige a 9.

g) **Imán y lupa**:
- cerca de un botón, el puntero se pega a su centro y se suelta con histéresis;
- la permanencia libre con ojos abre la lupa y el clic dentro cae en el punto correcto.

h) **Configuración**:
- rangos de `ojos.*`;
- una fuente inválida vuelve a "cabeza";
- `ojos` sin calibrar usa "cabeza" con aviso;
- una configuración 1.0 sin las claves queda en "cabeza".

i) Toda la suite (la de 1.0 y la de los paquetes A y B) en verde con la fuente "cabeza".

A mano, después del paquete (lo hace una persona, no los agentes): grabar una serie quieta real con iris, como `pruebas/datos/serie_quieta_facemesh.json`, para fijar `TEMBLOR_IRIS_FABRICA` con datos reales. Mientras tanto se usa un valor supuesto, y así queda anotado.

### C.6 Decisiones a anotar
- Ojos para lo grueso y cabeza para lo fino (la idea de "MAGIC pointing"); no al revés.
- Sin iris, el puntero queda quieto.
- La calibración tiene el paso de la cabeza en movimiento.
- Tope del radio en 120 px.
- Imán solo en las ventanas propias.
- Se reutiliza la lupa del paquete A.
- Las medidas son en el marco del ojo.
- Precisión esperada con cámara web: 3 a 5°.

---

## Cierre de la versión (después del paquete C)

Esto no es un cuarto paquete, sino lo que pidió el usuario al final ("actualiza y modifica manuales y videos").

1. **Versión**: `version.py` y `empaquetado/version_info.txt` pasan a 1.1.0. Se revisa que el `.iss` y el workflow armen `Lycan-Face-Control-1.1.0-...`. Commit en `lycan-face-control` (sin push). **El release lo publica el usuario.**
2. **Manual web** (`C:\dev\portafolio\lycan-face-control\index.html`):
   - secciones nuevas o cambiadas:
     - Velocidad del puntero (Más lento / Más rápido, arriba y abajo);
     - Minimizar la barra y el teclado;
     - Sin clic;
     - Lupa;
     - Botón AYUDA (cómo se pide, cómo se apaga, volumen de Windows, sin internet);
     - Mover con los ojos (con el texto honesto de C.3);
     - "Cómo usar" en vez de "Ayuda";
   - en "Con honestidad" se **corrige** la frase "no sigue la mirada" por los límites reales de los ojos;
   - las descargas apuntan a 1.1.0;
   - los dibujos nuevos salen de `C:\dev\portafolio\herramientas\dibujos-cara\dibujos.py`: ojos mirando a los lados, la lupa, el botón AYUDA y la pantalla roja.
3. **Video** (`C:\dev\portafolio\herramientas\video-tutorial-cara\`):
   - escenas nuevas en `escenas.py` (velocidad, minimizar, sin clic, lupa, AYUDA, ojos);
   - capturas nuevas con `capturar_ventanas.py`, siempre con `--simular --camara-falsa`, **sin la cámara real** y **sin sonido de la alarma**: barra de 11 botones, pestaña, lupa, pantalla de emergencia, calibración de mirada y Opciones de Emergencia;
   - se rehacen la voz y los subtítulos (.vtt y .srt) y se vuelve a armar el sitio con `armar_sitio.py`;
   - se revisan los rótulos cortados del teclado (riesgo conocido).
4. Commit en el repositorio del portafolio (sin push) y anotación en `docs/decisiones.md` y en el historial.
5. **Prueba manual con una persona real** (no la hacen los agentes):
   - velocidad 1 y 10;
   - Minimizar y abrir de nuevo;
   - Sin clic leyendo 5 minutos;
   - Lupa sobre una X de cerrar;
   - AYUDA en pausa y apagarla de las tres formas;
   - ojos con buena y con mala luz.
