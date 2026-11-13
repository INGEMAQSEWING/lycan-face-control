# Lycan Face Control

**Maneje el computador solo con la cabeza y la cara.** Mueva el puntero girando la cabeza, haga clic
quedándose quieto o con un gesto (abrir la boca, levantar las cejas) y escriba o hable con un teclado
grande en pantalla, con voz de Windows que funciona sin internet.

Lycan Developments / EDWIN CNC — versión 1.0.0 — código abierto (licencia MIT), sin costo de licencia.

> Está pensado para personas con **ELA** (esclerosis lateral amiotrófica) y otras discapacidades
> motoras, y para quien las cuida. Nació de una historia de familia: nadie debería tener que pagar
> una fortuna para poder decir "tengo sed" o "gracias".

---

## Qué puede hacer

| Para | Cómo |
|---|---|
| Mover el puntero | Gire la cabeza a los lados y arriba o abajo, con movimientos cómodos |
| Hacer clic | Quédese quieto un momento sobre algo (se llena un anillo) **o** abra la boca un momento (más de medio segundo) |
| Clic derecho | Levante las cejas |
| Doble clic, arrastrar | Elíjalos con la cabeza en la **barra de acciones** grande y luego haga clic donde quiera |
| Desplazar una página | Elija **Desplazar** en la barra e incline la cabeza hacia arriba o hacia abajo; para salir elija **Terminar** (también termina solo si no desplaza un rato) |
| Escribir y hablar | Abra el **Teclado**: teclas grandes en español (ñ, tildes), sugerencias de palabras, frases rápidas ("Sí", "No", "Tengo sed", "Tengo dolor"…) y los botones Hablar, Escribir, Copiar y Borrar |
| Si solo puede parpadear | Use el **modo barrido** (vea *Si la persona solo puede parpadear*, abajo): las filas y las teclas se iluminan solas y un **parpadeo largo** elige |
| Pausar | Mantenga la boca abierta 2 segundos y ciérrela. Para reanudar, ábrala unos 3 segundos y ciérrela, o quédese quieto sobre el botón grande "Reanudar". Un bostezo muy largo, o con los ojos cerrados, no cuenta |

**Los parpadeos naturales nunca hacen nada.** Solo cuenta un parpadeo largo y voluntario (por fábrica,
0,8 segundos; la calibración lo ajusta a cada persona). Mientras cierra los ojos, una barra se llena y
se pone verde cuando ya puede abrirlos.

**Seguridad:** si la cámara deja de ver la cara, si se pausa, si se cierra el programa o si algo falla,
el programa suelta cualquier botón o tecla que estuviera presionado. A los 10 segundos sin ver la cara
se pausa solo, y se reanuda solo cuando la cara vuelve.

---

## Instalación

1. Descargue `Lycan-Face-Control-1.0.0-Windows-64-bits.exe` desde la página de descargas
   (sección *Releases* de este repositorio).
2. Ábralo. Si Windows dice "Windows protegió su PC", elija **Más información** y luego
   **Ejecutar de todas formas** (el programa no tiene firma digital, que tiene un costo anual).
3. No pide permiso de administrador. Puede marcar **"Abrir Lycan Face Control al encender el computador"**.

¿Prefiere no instalar? Descargue `Lycan-Face-Control-1.0.0-portable.zip`, descomprímalo y abra
`LycanFaceControl.exe`.

**Requisitos:** Windows 10 u 11 de 64 bits, una cámara (la del portátil sirve) y unos 300 MB libres.
No necesita internet ni tarjeta de video especial.

---

## La primera vez

Se abre una bienvenida y luego la **calibración guiada** (unos dos minutos). Cada paso avanza solo:

1. **Posición**: la cara centrada y a buena distancia.
2. **Centro**: mire de frente y quédese quieto.
3. **Rango cómodo**: gire la cabeza hasta donde le resulte cómodo, sin forzar el cuello.
4. **Cara en reposo** y **parpadeo natural**: el programa aprende cómo parpadea usted sin querer,
   para no confundirlo nunca con un clic.
5. **Parpadeo largo** (solo con el barrido o "Solo comunicación"): la persona cierra los ojos hasta
   que la barra se pone verde, tres veces. Si no se logra, la pantalla final lo dice y sugiere qué
   ajustar. Con "Solo comunicación" no se piden los giros de la cabeza.
6. **Gestos** (puede omitir los que no use). Si la persona no logra hacer un gesto, se deja con el ajuste
   de fábrica y la pantalla final lo dice: así ese gesto no queda más sensible de la cuenta.
7. **Prueba final**: elija cuatro círculos con la cabeza. Con el barrido, la prueba es el parpadeo largo
   y la ventana se cierra sola.

Se puede repetir cuando quiera desde la ventana principal.

---

## Para el cuidador

- **Cámara** a la altura de los ojos, a unos 50 a 70 cm de la cara.
- **Luz** de frente o de lado; evite una ventana detrás de la persona.
- Calibre de nuevo si cambia la posición de la cama o la silla, o si la persona está cansada.
- Las **frases rápidas** se editan desde Opciones (puede poner el nombre del cuidador para "Llamar a…").
- Si la persona tiene movimientos involuntarios: suba la suavidad (Opciones › Puntero) y, en
  Opciones › Clic, «Cuánto se puede mover sin cancelar» y «Tiempo quieto para hacer clic».
- El programa ya no cuenta como clic la boca abierta con una sacudida de la cabeza (tos, estornudo) ni
  con los ojos achinados (risa, bostezo). Si aun así hace clics sin querer, suba el tiempo de la boca en
  Opciones › Gestos o apague ese gesto.
- Cuando **usted** pausa (con el atajo o con el ratón), abrir la boca no la quita: así un bostezo, la comida
  o el aseo no reactivan el puntero. La quitan el botón "Reanudar" (con la cabeza) y el atajo.
- Si otra persona se pone frente a la cámara, el programa suelta todo y espera un momento. Si esa cara no
  se parece a la de la persona (tamaño y proporciones), se pausa solo y sigue cuando vuelve la persona;
  si es la misma persona (por ejemplo, la acomodaron más cerca), elija «Reanudar».
- Si la persona voltea la cabeza mucho más allá de lo cómodo (para mirarlo a usted, a la televisión o
  para comer), el puntero se queda quieto y no hace clics hasta que vuelva a mirar la pantalla.
- Si dice «No encuentro la cámara» con la cámara conectada, revise en Configuración de Windows ›
  Privacidad y seguridad › Cámara que esté activado «Permitir que las aplicaciones de escritorio accedan
  a la cámara».

### Si la persona solo puede parpadear

En **Opciones › Teclado y voz** ponga **"Solo comunicación"** en Sí. El teclado queda siempre abierto con
barrido: las filas y luego las teclas se iluminan solas, **un parpadeo largo elige** y, si la persona
pausa, **dos parpadeos largos seguidos** la quitan. La primera fila trae Sí, No y "¡Ayuda, llamen a
alguien!" (suena con alerta y a todo volumen, aunque "Decir las frases en voz alta" esté en No).
Después de "Hablar", la primera letra empieza un mensaje nuevo (Deshacer recupera el anterior); la
tecla "123" abre los números y signos; los avisos ("No veo su cara", la pausa) salen en una franja
del propio teclado. Con el barrido encendido desde Opciones, las acciones
"Salir del barrido" y "Cerrar" no entran al barrido, para que la persona no quede sin forma de volver;
usted las tiene con el ratón.

### Atajos de teclado (se pueden cambiar en Opciones; la Ayuda muestra siempre los que estén puestos)

| Atajo | Hace |
|---|---|
| Ctrl+Alt+Espacio | Pausar o reanudar |
| Ctrl+Alt+T | Abrir o cerrar el teclado |
| Ctrl+Alt+C | Recentrar (tomar la posición actual como centro) |
| Ctrl+Alt+Inicio | Mostrar la ventana principal |
| Ctrl+Alt+Fin | Cerrar el programa |

---

## Privacidad

- La imagen de la cámara **se procesa en el computador y nunca se guarda ni se envía** a ningún lado.
  El programa no usa internet.
- Por defecto ni siquiera se muestra el video: se ve una silueta de puntos de la cara.
- Lo que la persona escribe o dice **no se anota** en los registros.
- Para mejorar las sugerencias, el programa guarda en `palabras_usuario.json` **las palabras que la persona
  escribe, cuántas veces usó cada una, si la usó hace poco (sí o no) y qué palabras van seguidas** (por
  ejemplo "tengo sed"). No guarda el orden en que se escribió, pero quien abra la carpeta de datos podría
  adivinar partes de lo escrito por las palabras que van juntas. Se apaga en Opciones ("Aprender mis
  palabras") y se borra con "Olvidar las palabras aprendidas".
- La configuración vive en `%APPDATA%\Lycan Face Control`. Al desinstalar, el programa pregunta si
  borrarla (por defecto la conserva).

---

## Lo que este programa no puede hacer (con honestidad)

- **No sigue la mirada.** Con una cámara web común no es preciso; para quien no puede mover la cabeza
  está el modo barrido con parpadeo largo.
- Si la persona pierde también el control de los párpados, este programa ya no le sirve: hacen falta
  sistemas especializados (por ejemplo, seguidores de mirada con cámara infrarroja). Consulte con su
  equipo de salud.
- Los programas abiertos "como administrador" no reciben clics ni texto de este programa (Windows lo impide).
- La voz depende de las voces instaladas en Windows. Si no hay voz en español, el programa avisa, usa la
  voz que haya (puede sonar en otro idioma) y muestra la frase en grande.
- Los umbrales se probaron con caras dibujadas; la prueba con personas reales está pendiente. Si algo no
  responde bien, la calibración y los ajustes de sensibilidad de Opciones son la primera ayuda.

---

## Para desarrolladores

Python 3.10, `mediapipe==0.10.14` (`mp.solutions.face_mesh`), `numpy==2.2.6`,
`opencv-python-headless==4.10.0.84`, Pillow, tkinter y ctypes. Sin pynput, pyautogui, pywin32,
comtypes ni pyttsx3 (la voz es SAPI 5 por ctypes, con PowerShell System.Speech de respaldo).

```
py -3.10 -m pip install -r requirements-dev.txt
py -3.10 -m lycan_face_control                       # abrir el programa
py -3.10 -m lycan_face_control --simular             # ensayo: no mueve el ratón ni escribe en Windows
py -3.10 -m lycan_face_control --simular --camara-falsa   # ensayo sin cámara
py -3.10 -m lycan_face_control --check               # revisar que todo carga (sin cámara) y salir
py -3.10 -m pytest -q pruebas                        # pruebas (sin cámara; la mayoría sin mediapipe)
```

- Especificación: `docs/especificacion.md`. Decisiones y sus motivos: `docs/decisiones.md`.
- Ícono: `py -3.10 herramientas\crear_icono.py` (genera `recursos/lycan-face.ico` y `.png`).
- **Compilación**: la hace GitHub Actions (`.github/workflows/windows.yml`) al empujar una etiqueta `v*`
  (o a mano desde la pestaña Actions): corre las pruebas, compila con PyInstaller
  (`empaquetado/lycan-face-control.spec`), revisa que los modelos de la cara estén dentro, prueba el
  `.exe` con `--check`, arma el instalador con Inno Setup (`empaquetado/lycan-face-control.iss`) y el
  ZIP portable, y los deja como *artifacts* del run por 14 días. Al cambiar la versión, cambie
  `lycan_face_control/version.py` **y** `empaquetado/version_info.txt` (el workflow lo comprueba).

### Prueba manual con una persona (pendiente antes de recomendarlo)

Calibrar; mover a las 4 esquinas; clic por permanencia en el escritorio; boca = clic; cejas = clic
derecho; arrastrar un archivo; desplazar una página; escribir "Hola, ¿cómo está? Ñandú" en el Bloc de
notas con permanencia y con barrido; hablar una frase; pausar con la boca 2 s y con Ctrl+Alt+Espacio;
taparse la cara a mitad de un arrastre; luz baja; 30 minutos de uso sin clics fantasma.

---

## Licencia y atribuciones

- Código: licencia MIT (ver `LICENSE`). © 2026 Lycan Developments / EDWIN CNC.
- Lista de palabras para las sugerencias (`recursos/palabras_es.txt`): FrequencyWords de Hermit Dave,
  a partir de subtítulos de OpenSubtitles.org, licencia CC BY-SA 4.0.
- Detección de la cara: MediaPipe de Google (licencia Apache 2.0).
