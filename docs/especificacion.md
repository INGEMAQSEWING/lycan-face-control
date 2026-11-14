# Lycan Face Control: especificación v1.0

| Dato | Valor |
|---|---|
| Producto | Lycan Face Control, "Control con la cara" (Lycan Developments / EDWIN CNC) |
| Qué hace | Maneja el computador **solo con la cabeza y la cara**: mueve el puntero con la cabeza, hace clic sin manos (quedarse quieto o un gesto) y trae un teclado en pantalla para comunicarse, con voz sin internet |
| Para quién | Personas con ELA (esclerosis lateral amiotrófica) y otras discapacidades motoras, y su cuidador |
| Precio | Sin costo de licencia y de código abierto (ver decisiones: en la web no se escribe la palabra "gratis") |
| Equipo de referencia | Portátil con Windows 11, 8 GB de RAM (~1 GB libre), sin NVIDIA, cámara "HP TrueVision HD Camera" |
| Lenguaje | Python 3.10 (siempre `py -3.10`), mediapipe 0.10.14 (`mp.solutions.face_mesh`), opencv, numpy 2.2.6, Pillow, tkinter 8.6, ctypes. **Sin pynput ni pyautogui** |
| Carpeta | `C:\dev\lycan-face-control` (repo público futuro: `INGEMAQSEWING/lycan-face-control`) |
| Proyecto hermano | `C:\dev\lycan-mouse-control` (se copia y adapta; **no se modifica**) |
| Idioma | Todo lo que ve el usuario va en español de Colombia, trato de "usted", sin jerga, tono cálido y digno (nunca infantil ni lastimero) |
| Fecha | 2026-11-13 |

> Las decisiones tomadas sin el usuario (que dormía) y sus motivos están en `docs/decisiones.md`. Si este documento y `decisiones.md` no coinciden, manda `decisiones.md` y se corrige este.

---

## 1. Objetivo y alcance

### 1.1 Qué debe lograr la v1.0
1. **Mover el puntero con la cabeza** (giro a los lados y arriba-abajo), sin temblor, llegando a toda la pantalla sin forzar el cuello.
2. **Clic sin manos**:
   - clic por **permanencia** (quedarse quieto un momento);
   - **gestos de la cara** configurables: abrir la boca, levantar las cejas, sonreír, parpadeo largo voluntario;
   - **los parpadeos naturales nunca hacen clic** (regla absoluta).
3. **Barra de acciones** grande y flotante: Clic, Doble, Derecho, Arrastrar, Desplazar, Teclado, Pausa. Se elige con la cabeza.
4. **Teclado en pantalla para comunicarse**: teclas grandes en español (ñ, tildes); elección por permanencia con la cabeza **o** por **barrido** (filas y teclas avanzan solas; un parpadeo largo elige); predicción de palabras; frases rápidas editables; botones Hablar (voz de Windows sin internet), Escribir en el programa activo, Copiar, Borrar.
5. **Calibración guiada**: centro, rango cómodo, parpadeo natural, cara en reposo, prueba de gestos.
6. **Pausar y reanudar** con un gesto configurable y con un atajo de teclado (para el cuidador).
7. **"Abrir al encender el computador"**.
8. **Nunca dejar un botón ni una tecla presionados** si se pierde la cara, se pausa, se sale o falla algo.
9. Funcionar con fluidez en el portátil del usuario (15 a 20 cuadros procesados por segundo bastan) y con poca memoria (meta < 350 MB).
10. Entregarse como instalador de Windows (PyInstaller + Inno Setup, compilado en GitHub Actions) sin pedir permisos de administrador.

### 1.2 Fuera de alcance en la v1.0
- Seguimiento de la mirada (apuntar con los ojos): con cámara web no es preciso. Se cubre con el barrido.
- Guiño de un solo ojo como gesto (poco confiable con cámara web): se mide pero queda apagado y oculto (v1.1).
- Distribución "ABC" del teclado, barrido por mitades (estilo Look to Speak), voces OneCore (Raúl, Sabina OneCore), perfiles "mañana/tarde" automáticos: v1.1.
- Firma digital del ejecutable.
- Publicación, repositorio remoto y página web: los hace el agente principal al final, no las partes de construcción.

### 1.3 Honestidad con la persona
La ayuda y el manual dicen con claridad: si la persona pierde también el control de los párpados, este programa ya no le sirve y hacen falta otros sistemas (por ejemplo, seguidores de mirada especializados). No se promete lo que no se puede cumplir.

---

## 2. Arquitectura general

### 2.1 Hilos y flujo de datos

```
 [Hilo CÁMARA]                 [Hilo MOTOR]
 cv2.VideoCapture ─► cuadro ─► Detector (FaceMesh) ─► Medidas (cara.py) ─► Gestos (gestos.py)
 (solo guarda el    + t_captura                              │                   │
  último cuadro)                                             ▼                   ▼
                               Puntero (mapeo + One Euro) ─► Máquina de estados (estados.py) ─► Salida (SendInput)
                                                                     │        ▲
                                     Vista para pintar (cola de 1) ──┘        │ "objetivos" (botones de barra/teclado
                                                                              │  en coordenadas de pantalla)
 [Hilo INTERFAZ = principal, tkinter]: ventana, barra, teclado, anillo, calibración, opciones ──┘
 [Hilo ATAJOS]  RegisterHotKey + GetMessageW ─► cola de órdenes ─► Motor / Interfaz
 [Hilo VOZ]     COM propio (SAPI 5 por ctypes) ─► cola de frases; respaldo PowerShell System.Speech
 [Hilo SONIDOS] winsound (copiado del hermano)
```

- **Cámara** (`captura.py`): lee sin parar y guarda solo el cuadro más reciente con `t_captura = time.perf_counter()`. Nunca hace cola.
- **Motor** (`motor.py`): un solo bucle: toma el último cuadro, corre FaceMesh, calcula medidas y gestos, avanza la máquina de estados y aplica las acciones. Es el **único** que envía acciones de ratón/teclado, salvo `soltar_todo()` (seguro desde cualquier hilo) y la escritura de texto pedida por el teclado, que se pasa al motor como **orden** (`OrdenEscribir(texto)`), nunca se envía desde tkinter.
- **Interfaz** (`ui/`): tkinter en el hilo principal. Pinta lo que el motor deja en `queue.Queue(maxsize=1)` (se descarta lo viejo). Publica al motor la lista de **objetivos** (rectángulos en píxeles físicos de pantalla con su identificador: botones de la barra, teclas, frases) cada vez que cambia la distribución, mediante una estructura protegida con `threading.Lock`.
- **Atajos** (`sistema/atajos.py`): hilo propio, copiado del hermano.
- **Voz** (`sistema/voz.py`): hilo propio con su `CoInitializeEx`; recibe frases por cola. Una frase nueva corta la anterior.

### 2.2 Regla de oro
**La lógica es pura**: `cara.py`, `gestos.py`, `puntero.py`, `permanencia.py`, `estados.py`, `teclado_logica.py`, `barrido.py`, `prediccion.py` y `frases.py` reciben números y tiempos (en segundos reales, `perf_counter`) y devuelven estados o listas de **acciones** (`Mover`, `Bajar`, `Subir`, `Clic`, `Rueda`, `Tecla`, `TeclaVK`, `Texto`, `SoltarTodo`, `Aviso`, `Sonido`, `Hablar`, `Elegir(objetivo)`). No importan ctypes, cv2, tkinter ni mediapipe. Así todo se prueba con pytest sin cámara, sin mover el ratón real y sin mediapipe.

### 2.3 Estructura de carpetas

```
C:\dev\lycan-face-control\
  lanzar.py                       # from lycan_face_control.app import main; main()
  lycan_face_control.pyw          # lanzador sin consola (para HKCU\Run en modo código fuente)
  requirements.txt  requirements-dev.txt  README.md  LICENSE (MIT)  .gitignore
  lycan_face_control\
    __init__.py  __main__.py
    version.py                    # VERSION = "1.0.0"
    app.py                        # main(): DPI, registro, argumentos, mutex, arranque y cierre seguro
    constantes.py                 # índices FaceMesh, colores de estado, LYCAN_EXTRA, nombres de botones
    config.py                     # config.json validado (mecanismo copiado del hermano, contenido nuevo)
    registro.py                   # copiado, carpeta nueva
    captura.py                    # copiado + CamaraFalsa (misma interfaz) para pruebas y --simular
    detector.py                   # FaceMesh -> CaraDetectada (478x3 en píxeles + normalizados)
    cara.py                       # medidas puras: io, EAR, MAR, cejas, sonrisa, yaw_n, pitch_n, roll
    gestos.py                     # clasificador puro con histéresis y tiempos: boca, cejas, sonrisa, parpadeo largo
    filtros.py                    # copiado: OneEuro, Histeresis, Antirrebote, PromedioExp
    mapeo.py                      # Monitor, zona_segura (copiados) + mapeo por tramos pose->pantalla
    puntero.py                    # One Euro, zona muerta, ganancia por eje, aceleración, congelar/historial, reentrada
    permanencia.py                # temporizador de permanencia (radio, activación, recuperación, margen)
    estados.py                    # máquina de estados (sección 5)
    acciones.py                   # copiado + Texto, TeclaVK, Hablar, Elegir
    motor.py                      # bucle; une todo; fps y latencia; órdenes y avisos
    calibracion.py                # lógica pura de calibración (percentiles, umbrales por persona)
    teclado_logica.py             # distribuciones, tildes, texto en armado, objetivos
    barrido.py                    # barrido fila -> tecla, puro
    prediccion.py                 # sugerencias por prefijo + palabras aprendidas
    frases.py                     # frases rápidas por categoría, editables, validadas
    salida\  base.py  simulada.py  windows.py  __init__.py   # copiados + Unicode y teclas virtuales
    sistema\
      dpi.py  pantallas.py  sonidos.py  ventanas_win.py  atajos.py  inicio.py   # copiados/adaptados
      voz.py                      # SAPI 5 por ctypes + respaldo PowerShell
      portapapeles.py             # CF_UNICODETEXT por ctypes
    ui\
      comun.py                    # colores, letras grandes, ruta_recurso, Globo "?"
      textos.py                   # TODOS los textos en TXT, con t()
      ventana_principal.py        # estado, botones grandes, mini, vista de puntos (sin video por defecto)
      indicador.py                # anillo de permanencia y barra de cierre de ojos junto al cursor
      barra.py                    # barra de acciones flotante
      teclado.py                  # teclado en pantalla y frases
      calibracion.py              # asistente de calibración guiada
      opciones.py                 # pestañas con vista en vivo y Cancelar
      ayuda.py                    # chuleta de gestos con dibujos de cara
      editor_frases.py
  recursos\  lycan-face.ico  lycan-face.png  palabras_es.txt  sonidos\*.wav (opcionales)
  pruebas\
    pytest.ini  conftest.py
    sintetico\cara_sintetica.py   # generador de caras (sección 13.1)
    datos\cara_dibujada_base.json # 478 puntos reales de mediapipe (ya existe)
    test_*.py
  herramientas\  cara_dibujada.py  verificar_medidas.py   # ya existen; pruebas manuales SIN cámara
  empaquetado\  lycan-face-control.spec  rthook_sin_matplotlib.py  version_info.txt  lycan-face-control.iss
  .github\workflows\windows.yml
  docs\  especificacion.md  decisiones.md
```

---

## 3. Módulos en detalle

### 3.1 `app.py`: arranque y cierre
Mismo orden que el hermano:
1. `sistema.dpi.activar()` en la primera línea.
2. Registro de errores (`%APPDATA%\Lycan Face Control\registros\registro.txt`, 1 MB × 3).
3. Argumentos:
   - `--check`: importa mediapipe, crea `FaceMesh(static_image_mode=False, refine_landmarks=True, max_num_faces=1)`, procesa `np.zeros((480,640,3), np.uint8)`, comprueba que `sistema.voz` puede listar voces sin hablar (si no hay voz, solo lo anota), y sale con 0 (o 1). **Sin abrir la cámara ni mover el ratón.**
   - `--minimizado`: arranca en modo mini (para "Abrir al encender").
   - `--simular`: salida simulada (nada llega a Windows).
   - `--camara-falsa`: usa `CamaraFalsa` (cuadros negros); para soporte y pruebas sin cámara.
4. Mutex `Local\LycanFaceControl` (`ventanas_win.instancia_unica`); si ya corre, trae la otra ventana al frente y sale.
5. Cargar `config.json`.
6. Crear la salida, `atexit.register(salida.soltar_todo)`, manejadores de SIGINT y SIGBREAK.
7. Arrancar hilos: cámara, motor, atajos, voz, sonidos.
8. Crear la interfaz. Si `primera_vez`, abrir la calibración guiada (con la explicación previa para el cuidador).
9. `try/except/finally`: el `finally` llama `soltar_todo()`, detiene hilos, libera la cámara, termina el proceso de voz de respaldo si existe.

### 3.2 `captura.py`
Copiado: DSHOW y luego MSMF, MJPG, 640×480 a 30 fps pedidos, espejo una sola vez, reintento al perder la cámara, aviso de cámara ocupada. Nuevo: `CamaraFalsa(generador=None)` con la misma interfaz (`iniciar`, `ultimo() -> (cuadro, t)`, `detener`, `estado`), que entrega cuadros negros o los de un generador.

### 3.3 `detector.py`
- Copiar `_sin_matplotlib()` tal cual (PyInstaller).
- `FaceMesh(static_image_mode=False, refine_landmarks=True, max_num_faces=1, min_detection_confidence=0.5, min_tracking_confidence=0.5)`.
- Convierte BGR→RGB, `flags.writeable=False`.
- Devuelve `CaraDetectada(puntos: np.ndarray (N,3) en píxeles con P[i]=(x·ancho, y·alto, z·ancho), normalizados (N,3), ancho, alto, t)` o `None`.
- Medido: ~6 ms por cuadro de 640×480 en modo video en este PC.

### 3.4 `cara.py`: medidas puras (todas divididas por `io`)
Notación: `P[i]` punto 3D; `d(a,b)` distancia 3D; `d2` distancia 2D (x,y). Lados: 33/133/468 = ojo **derecho** de la persona; 263/362/473 = ojo **izquierdo**.

| Medida | Fórmula | Índices |
|---|---|---|
| Escala `io` | `d(P33, P263)` | 33, 263 |
| Ejes | `ex = unitario2D(P263 − P33)`, `ey = (−ex.y, ex.x)` | |
| Roll | `atan2(ex.y, ex.x)` en grados | |
| Yaw (lados) | `ojos = (P33+P263)/2`; `v = P1 − ojos`; `yaw_n = (v·ex)/io` (2D) | 1, 33, 263 |
| Pitch (arriba/abajo) | `boca = (P61+P291)/2`; `pitch_n = (v·ey)/((boca−ojos)·ey)` | 1, 33, 263, 61, 291 |
| EAR por ojo | `(d(p2,p6)+d(p3,p5)) / (2·d(p1,p4))` | der [33,160,158,133,153,144]; izq [362,385,387,263,373,380] |
| MAR (boca) | `d(P13,P14) / d(P78,P308)` | 13, 14, 78, 308 |
| Cejas | media de `d(ceja_k, centro_ojo)` / io; centro_ojo der = (P33+P133)/2, izq = (P362+P263)/2; se promedian ambos lados | der [70,63,105,66,107]; izq [300,293,334,296,336] |
| Sonrisa | `d(P61,P291) / io` | 61, 291 |

- Función `medir(puntos) -> Medidas(io_px, yaw_n, pitch_n, roll, ear_der, ear_izq, mar, cejas, sonrisa)` y `puntos_validos(puntos)` (sin NaN, `io_px ≥ 40`, cara dentro de la imagen).
- Comprobado: mover la cara 60 px, escalarla a 0,7 o inclinarla 15° casi no cambia `yaw_n`/`pitch_n`. Rango estimado con una cara real: `yaw_n ≈ ±0,12` para ±20°, `pitch_n` centro ≈ 0,55 ± 0,10 (por eso se calibra).
- Valores de la cara dibujada de referencia (base): EAR 0,357/0,375; MAR 0,016; cejas 0,356; sonrisa 0,557.

### 3.5 `gestos.py`: clasificador puro
Cada gesto compara con la **base de la persona** (mediana de ~1,5 s en reposo durante la calibración). Sin calibración se usan las bases de la cara de referencia y un aviso "Le recomiendo calibrar".

| Gesto | Señal | Entra (activo) | Sale (vuelve a reposo) | Sostener mínimo | Por defecto |
|---|---|---|---|---|---|
| Boca abierta | `MAR` | `MAR > base + 0,25·k` | `MAR < base + 0,15·k` | 350 ms | **encendido** |
| Cejas arriba | `r = cejas/base` | `r > 1 + 0,12·k` | `r < 1 + 0,06·k` | 350 ms | **encendido** |
| Sonrisa | `r = sonrisa/base` y `MAR < base + 0,15` | `r > 1 + 0,10·k` | `r < 1 + 0,05·k` | 400 ms | apagado |
| Ojos cerrados (ambos) | `r_d = EAR_d/base_d`, `r_i = EAR_i/base_i` | ambos `r < 0,55` | cualquiera `r > 0,70` | ver parpadeo | — |
| Guiño | uno `r < 0,55`, otro `r > 0,80` | | | 400 ms | apagado y oculto (v1.1) |

- `k` = **sensibilidad del gesto** (0,5 a 2,0; por defecto 1,0). La calibración puede fijar el umbral de entrada al 50 % entre la base y el máximo medido de la persona (si se midió); el de salida queda en el 60 % del de entrada (histéresis ~30 %, como recomienda la investigación).
- **Duraciones** (siempre en tiempo real, nunca contando cuadros):
  - Cada gesto produce eventos al **soltarse**: `GestoCorto(nombre)` si duró entre `sostener_ms` y `largo_ms`, `GestoLargo(nombre)` si se sostuvo ≥ `largo_ms` (por defecto 2000 ms). Esto evita choques: la boca corta puede ser "clic" y la boca larga "pausar".
  - Si al gesto **no** se le asignó acción larga, `GestoCorto` se emite al cumplir `sostener_ms`, sin esperar a soltar (más rápido).
  - Mientras un gesto está activo se emite `progreso(nombre, 0..1)` para la barra de cierre / anillo.
  - Tras cualquier evento, **refractario** de 600 ms (rango 300 a 2000): no se acepta otro gesto, y el mismo gesto debe volver a reposo antes de repetirse.
- **Parpadeo largo voluntario** (el más delicado):
  - Ambos ojos cerrados de forma continua. Un cuadro abierto en medio de < 80 ms no corta (tolerancia a ruido).
  - **Parpadeo natural**: cierre < `parpadeo_largo_ms` → **no hace nada, nunca**. Piso absoluto: `parpadeo_largo_ms` nunca baja de 400 ms aunque la config diga otra cosa.
  - Por defecto `parpadeo_largo_ms = 800` (rango 400 a 2000). Tras calibrar: `max(600, 2 × máximo natural medido)`, recortado a 2000.
  - El evento `ParpadeoLargo` se emite **al abrir los ojos** si el cierre duró entre `parpadeo_largo_ms` y `descanso_ms` (por defecto 4000, rango 2000 a 10000). Un cierre más largo es un descanso y se ignora. Al cumplirse `parpadeo_largo_ms` con los ojos aún cerrados, se emite `ParpadeoListo` (sonido suave opcional + barra llena: "ya puede abrir los ojos").
  - Opción "doble parpadeo largo" (apagada): exige dos parpadeos largos separados por ≤ 2,5 s.
  - Al **empezar** a cerrar (cualquier ojo `r < 0,70`) el motor congela el puntero y el barrido (ver 3.7 y 7.4).
- Sin cara: todos los gestos se reinician sin emitir eventos.

### 3.6 `mapeo.py`: de la pose de la cabeza a la pantalla
- Se copian `Monitor`, `zona_segura` y el recorte del hermano.
- Entrada: `yaw_n`, `pitch_n` filtrados. Calibración: `c = (yaw0, pitch0)` centro; extremos cómodos `izq, der, arr, aba` (percentil 90 del recorrido de cada lado, no el máximo).
- **Mapeo absoluto escalado por tramos** (por defecto): para x, `u = (yaw − yaw0)/(der − yaw0)` si `yaw ≥ yaw0`, si no `(yaw − yaw0)/(yaw0 − izq)`; igual para y con `pitch`. Luego `u ← u · sens_x`, `v ← v · sens_y`. Pantalla: `x = cx + u · (W/2)·(1 + margen)`, recortado a la pantalla (margen 10 %: el borde se alcanza un poco antes del extremo cómodo). La persona **mirando a la derecha** mueve el puntero **a la derecha** (se corrige el espejo según el signo de la calibración, no se adivina).
- Sensibilidad: `sens_x` 1,0 y `sens_y` 1,2 por defecto (rango 0,5 a 3,0 cada uno).
- **Zona muerta** alrededor del centro: 3 % de `u`/`v` (rango 0 a 10 %).
- Modo **relativo "joystick suave"** (opcional): fuera de la zona muerta, velocidad = `g · (|u| − zm)^1,5` px/s con `g` 600 a 3000 px/s; para personas con poco rango de movimiento.
- Monitor: el principal por defecto; elegible en Opciones.

### 3.7 `puntero.py`
- One Euro en píxeles: `min_cutoff 1,0 Hz`, `beta 0,02`, `d_cutoff 1,0`. Deslizador "Suavidad" de 5 niveles: min_cutoff = [2,0; 1,5; 1,0; 0,7; 0,5], beta = [0,04; 0,03; 0,02; 0,015; 0,01]; nivel 3 por defecto.
- Zona muerta en pantalla: 4 px a 1080 de alto, escalada `4 · alto/1080` (rango 0 a 15 px): si el cambio filtrado es menor, el puntero no se mueve.
- Aceleración: nivel 0 a 3 (por defecto 0 = apagada); ganancia × `(1 + k·v)` con k = [0; 0,0005; 0,001; 0,002] y v en px/s.
- **Historial** de las últimas 0,5 s de posiciones. **Congelar** (`congelar(t)`): fija el puntero en la posición de ~150 ms antes; se usa al empezar a cerrar los ojos y mientras haya un gesto de boca/cejas/sonrisa activo (esos gestos mueven la nariz). Al descongelar, la nueva posición se mezcla en 300 ms.
- **Reentrada** tras perder la cara: al volver, 500 ms de mezcla lineal desde la posición congelada hasta la nueva (no salta).
- No envía `Mover` si la posición entera no cambió.

### 3.8 `permanencia.py`: clic por quedarse quieto
Estado puro con `actualizar(pos, t, sobre_objetivo) -> (progreso 0..1, disparo: bool)`:
- **Radio**: 30 px (rango 10 a 80, escalado con la resolución como la zona muerta) alrededor del punto donde empezó la quietud. Salir del radio reinicia, salvo un **margen** de 150 ms (si vuelve dentro en ese tiempo, el contador sigue; estilo OptiKey).
- **Tiempo**: 1,0 s (rango 0,4 a 3,0, pasos de 0,1).
- **Activación**: el contador solo se arma si, desde el último disparo, el puntero se movió más de `2 × radio` (60 px por defecto). Evita clics repetidos mientras la persona descansa ("toque de Midas").
- **Recuperación**: 1,0 s sin disparos tras cada disparo (rango 0,3 a 3,0).
- **Anillo**: visible desde los 200 ms (antes no se dibuja, para que no parpadee con cada pausa pequeña); diámetro 48 px (40 a 80); se llena de forma continua.
- Sobre **objetivos propios** (barra, teclado, frases, ventana principal) la permanencia se calcula **por objetivo** (no por radio): el contador sigue mientras el puntero esté dentro del rectángulo ampliado con una franja de tolerancia del 12 % del ancho; para repetir la misma tecla hay que salir de ella o esperar otra permanencia completa. La activación por movimiento no se exige para pasar de una tecla a otra distinta. Tiempo propio del teclado: `teclado.permanencia_s` (1,0 por defecto).
- Puede apagarse (`permanencia.activa = false`): entonces solo hacen clic los gestos.

### 3.9 `estados.py`: ver sección 5.

### 3.10 `salida/`
- Copiada del hermano (`soltar_todo()` seguro desde cualquier hilo, nunca dos "abajo" seguidos, firma `LYCAN_EXTRA` en `dwExtraInfo`, nunca envía clics a ventanas propias).
- **Nuevo**:
  - `Texto(cadena)`: `KEYEVENTF_UNICODE` (0x0004) con `wVk=0`, `wScan=ord(c)`; cada carácter baja y sube **en el mismo `SendInput`**; los caracteres > U+FFFF se mandan como par sustituto; `\n` → `VK_RETURN` y `\t` → `VK_TAB` (el 0x0A Unicode no llega, comprobado); en trozos de 200 caracteres.
  - `TeclaVK(vk)`: pulsación completa de `VK_BACK`, `VK_RETURN`, `VK_SPACE`, `VK_TAB`, flechas, `VK_ESCAPE`.
  - Antes de escribir, comprobar que la ventana activa **no** es una propia (si lo es, se devuelve el foco a la última ventana externa registrada con `GetForegroundWindow` cada 250 ms; si no hay, aviso "Primero elija con la cabeza el programa donde quiere escribir").
  - Si la ventana activa es de administrador y el programa no (`es_elevado`/`yo_elevado`): aviso "Ese programa está abierto como administrador; Windows no me deja escribir ni hacer clic en él."

### 3.11 `sistema/voz.py`
- **Principal**: SAPI 5 por ctypes (sin dependencias; probado en este PC con "Microsoft Sabina Desktop" es-MX: empieza a hablar en ~150 ms). Hilo propio con `CoInitializeEx`. Métodos de la vtable de ISpVoice: Speak = 20, SetRate = 28, SetVolume = 30, WaitUntilDone = 32. Hablar con `SPF_ASYNC | SPF_PURGEBEFORESPEAK | SPF_IS_XML`, escapando `&`, `<` y `>`.
- **Elegir voz**: la guardada en config; si no, por nombre `Microsoft Sabina Desktop`; si falla (error 0x80045043), la primera con idioma que empiece por `es-` (`Language=80a`, `c0a`, etc.); al final la predeterminada. Nunca se exige Sabina.
- **Respaldo**: si no se puede crear el objeto COM, un proceso `powershell.exe -NoProfile -NonInteractive` con `CREATE_NO_WINDOW` que carga `System.Speech`, elige voz `es-*` y lee frases por stdin en UTF-8 (una por línea, `SpeakAsyncCancelAll` + `SpeakAsync`). Si ambos fallan: aviso "No encontré una voz en español en Windows" y el texto se muestra grande en pantalla (modo "mostrar en grande").
- Volumen 0 a 100 (80 por defecto), velocidad −5 a +5 (−1 por defecto), "Repetir" dice la última frase.
- Frase de urgencia: volumen 100 y sonido de alerta antes.

### 3.12 `prediccion.py`, `frases.py`, `teclado_logica.py`, `barrido.py`: ver sección 7.

### 3.13 `config.py`
Mecanismo copiado (escritura atómica, `config.dañado-AAAAMMDD-HHMMSS.json`, `validar()` con `RANGOS`, `ENTEROS`, `OPCIONES`, `MINIMO_SI_NO_CERO`, reintentos, `ErrorSoloLectura`, variable `LYCAN_FACE_DATOS` para pruebas). Carpeta `%APPDATA%\Lycan Face Control\`. Archivos aparte: `frases.json`, `palabras_usuario.json` (ambos validados; si se dañan se renombran y se usan los de fábrica). Contenido en la sección 9.

---

## 4. Medidas, umbrales y calibración (resumen operativo)

| Concepto | Por defecto | Rango | Fuente |
|---|---|---|---|
| Cuadros procesados | 20 por segundo como máximo | 10 a 30 | rendimiento |
| Cámara | 640×480, 30 fps pedidos | — | |
| Cara mínima | `io ≥ 40 px` | — | medidas |
| Sin cara → congelar | inmediato | — | |
| Sin cara → soltar todo | 300 ms | 150 a 1000 | |
| Sin cara → pausa automática | 10 s | 3 a 60 | |
| Reanudar tras pausa automática | cara estable 1 s | — | |
| Ojos cerrado / abierto | `r < 0,55` / `r > 0,70` | 0,35 a 0,75 / +0,10 a +0,25 | |
| Parpadeo largo | 800 ms | 400 a 2000 | |
| Descanso (cierre ignorado) | 4000 ms | 2000 a 10000 | |
| Boca, cejas sostener | 350 ms | 100 a 1000 | |
| Sonrisa sostener | 400 ms | 100 a 1000 | |
| Gesto largo | 2000 ms | 1000 a 4000 | |
| Refractario tras gesto | 600 ms | 300 a 2000 | |

### 4.1 Calibración guiada (lógica en `calibracion.py`, pantalla en `ui/calibracion.py`; 60 a 90 s)
Cada paso tiene instrucciones grandes, voz opcional (apagada por defecto en la calibración), botón "?" y "Repetir este paso"; todos se pueden completar **sin manos** (permanencia en los botones con el puntero en modo ensayo centrado) o los maneja el cuidador con el ratón.
1. **Posición**: cara centrada y a buena distancia: `io` entre el 9 % y el 22 % del ancho de la imagen (equivale a cara del 20 al 45 %); luz suficiente (`evaluar_luz` del hermano). Se sigue cuando se cumple 1 s seguido.
2. **Centro**: mirar al frente, quieto 3 s → `yaw0, pitch0` = mediana; se descartan los primeros 0,5 s.
3. **Rango cómodo**: izquierda, derecha, arriba y abajo "sin forzar", 2 s cada uno → percentil 90 del recorrido hacia ese lado. Si el recorrido de un lado es menor que 0,02 (yaw) o 0,03 (pitch), se avisa "Casi no detecté movimiento; si le cuesta, puede usar el modo joystick o subir la sensibilidad" y se usa un valor mínimo seguro.
4. **Cara en reposo, boca cerrada**: 3 s → bases de MAR, cejas, sonrisa, EAR (mediana con ojos abiertos).
5. **Parpadeo natural**: 15 s parpadeando con normalidad → duración máxima y frecuencia de los cierres naturales. `parpadeo_largo_ms = clamp(max(600, 2 × máximo), 600, 2000)`. Si no hubo parpadeos se deja 800.
6. **Probar gestos** (opcional, solo los encendidos): 3 veces cada uno → máximo medido; umbral de entrada al 50 % entre base y máximo (sin bajar de la mitad del valor de fábrica); se muestra una barra en vivo con la línea del umbral y un "Probar".
7. **Prueba final**: llevar el puntero a 4 objetivos grandes; se cuenta cuántos alcanzó y se ofrece "Repetir" o "Terminar".
- Perfiles: se guarda en `config["perfiles"]["<nombre>"]` (por defecto "Principal"); se pueden crear "Mañana"/"Tarde" a mano y cambiarlos desde la barra de Opciones.
- **Recentrar** rápido (botón en la ventana, atajo Ctrl+Alt+C, y gesto opcional): toma 1,5 s de centro y desplaza el mapeo sin repetir lo demás (la postura en cama o silla cambia durante el día).

---

## 5. Máquina de estados (`estados.py`)

### 5.1 Estados principales
| Estado | Qué pasa | Sale a |
|---|---|---|
| `PAUSA` | No mueve el puntero, no hace clic. Sí detecta: gesto de reanudar, permanencia sobre el botón "Reanudar" (2 s) y el atajo. El indicador del borde muestra "En pausa" | `ACTIVO` |
| `ACTIVO` | Mueve el puntero, permanencia y gestos según el submodo | `PAUSA`, `SIN_CARA`, `CALIBRANDO` |
| `SIN_CARA` | Puntero congelado; a los 300 ms `SoltarTodo` (corta arrastre y desplazamiento); aviso "No veo su cara" | al volver la cara: estado anterior (con mezcla de 500 ms); a los 10 s: `PAUSA` automática |
| `CALIBRANDO` | El motor entrega medidas a la calibración; no envía acciones a Windows | `PAUSA` o `ACTIVO` (según cómo estaba antes) |

- Arranque: en `ACTIVO` o `PAUSA` según `arranque.estado` (por defecto `ACTIVO` si ya hay calibración, `PAUSA` si no). Con `--minimizado` igual.
- **Pausa automática**: si se pausó por falta de cara, al volver la cara estable 1 s se reanuda solo. Si se pausó a propósito, no.

### 5.2 Submodos de `ACTIVO`
| Submodo | Entrada | Comportamiento | Salida |
|---|---|---|---|
| `NORMAL` | por defecto | Permanencia (fuera de ventanas propias) hace la **acción de clic actual** (`modo_clic`); los gestos hacen su acción asignada | — |
| `ARRASTRE_INICIO` | botón "Arrastrar" | La siguiente permanencia/gesto de clic hace `Bajar('izq')` → `ARRASTRANDO` | — |
| `ARRASTRANDO` | — | Mueve con el botón abajo; la siguiente permanencia (radio y tiempo normales, sin exigir activación) o gesto de clic hace `Subir('izq')` → `NORMAL`. Tope de seguridad: 60 s → `Subir` + aviso | `NORMAL` |
| `DESPLAZAR` | botón "Desplazar" | El puntero queda fijo; `pitch` fuera de la zona muerta envía `Rueda` (arriba/abajo) a velocidad proporcional (1 a 8 muescas/s); `yaw` envía rueda horizontal (opcional). Aparece un botón grande "Terminar" junto a la barra | permanencia en "Terminar", cualquier gesto de clic, o 10 s sin desplazar → `NORMAL` |
| `TECLADO` | botón "Teclado" o atajo | Igual que `NORMAL`, pero sobre el teclado la permanencia elige teclas por objetivo | cerrar el teclado |
| `BARRIDO` | teclado en modo barrido | El puntero **no** se mueve (o se oculta el anillo); el barrido avanza solo; `ParpadeoLargo` elige; otros gestos según asignación (p. ej. boca = Borrar) | tecla "Salir del barrido" o cerrar el teclado |
| `SOLO_COMUNICACION` | opción "Mouse apagado" | Como `BARRIDO` pero sin salir al ratón; pensado para ELA avanzada | Opciones o atajo |
| `LUPA` (1.1) | permanencia libre (o gesto de clic) con `modo_clic = "lupa"` | La máquina **no** hace clic: emite `Elegir("lupa:abrir@zona@ventana@imagen")` (`lupa.py`: zona de `lupa.zona_px` alrededor del punto, ventana de hasta el 70 % del alto en el lado opuesto, **nunca tapa la zona**). El puntero se mueve igual. Quieto `permanencia.tiempo_s` sobre `lupa:zona` (o gesto de clic) → `Mover` al punto real (`a_pantalla`) + `Clic(izq)` + `Elegir("lupa:cerrar")`; desarma tras deslizar y vuelve a `izq` (con `modo_fijo` sigue en `lupa`) | clic hecho; «Cerrar lupa», `lupa.espera_s` sin elegir, pausa, sin cara (300 ms), "mirando afuera", calibración, teclado, Opciones, otra configuración u otro botón: se cierra **sin clic** (aviso "Cerré la lupa sin hacer clic."). Si la captura falla o no cabe: aviso y `NORMAL` |

### 5.3 `modo_clic` (lo fija la barra)
`izq` (por defecto), `doble`, `der`, `arrastrar` (lleva a `ARRASTRE_INICIO`), `desplazar`, y en la 1.1 `ninguno` («Sin clic», modo lectura) y `lupa`.
- **`ninguno` (Sin clic)**: quedarse quieto **fuera** de las ventanas propias no hace nada (ni clic, ni sonido, ni anillo; el indicador dice "Sin clic"). Sobre los botones propios la permanencia sigue (para salir con «Clic»). Los gestos de clic **sí** hacen clic (son a propósito) y el modo sigue. Dura hasta elegir «Clic» u otro modo: `modo_fijo`, pausar, reanudar y cambiar Opciones no lo quitan. El puntero sigue la cabeza (no es pausa).
- **`lupa`**: ver `LUPA` en 5.2. Por defecto es **de un solo uso**: tras usarse vuelve a `izq`. Opción "dejar fijo" (`barra.modo_fijo = true`). El botón activo se ve resaltado en la barra.
- `doble`: `Clic('izq', 2)` con el intervalo de `GetDoubleClickTime()/3`.
- Clic izquierdo y derecho: `Bajar` y `Subir` en el **mismo** `SendInput` (nunca queda presionado).

### 5.4 Gestos y sus acciones (asignables en Opciones)
Acciones posibles: `ninguna`, `clic` (= `modo_clic` actual), `clic_izq`, `clic_der`, `doble`, `arrastrar`, `pausar` (alterna), `teclado`, `recentrar`, `borrar` (en el teclado), `elegir` (barrido), `hablar` (teclado).
| Gesto | Corto (por defecto) | Largo 2 s (por defecto) |
|---|---|---|
| Boca abierta | `clic` | `pausar` |
| Cejas arriba | `clic_der` | `ninguna` |
| Sonrisa (apagado) | `ninguna` | `ninguna` |
| Parpadeo largo | en `BARRIDO`/`SOLO_COMUNICACION`: `elegir`; fuera: `ninguna` (opcional `clic`) | — |
- **Reanudar desde `PAUSA`**: el gesto de pausa sostenido **3 s** (más que para pausar, para no reanudar sin querer), o 2 s de permanencia sobre el botón grande "Reanudar" que siempre está visible, o el atajo. En `SOLO_COMUNICACION`, un **doble parpadeo largo** también reanuda.
- Mientras un gesto está activo, el puntero se congela (3.7) y la permanencia se detiene.

### 5.5 Transiciones que sueltan todo (`SoltarTodo` siempre)
Entrar a `PAUSA`, a `SIN_CARA` (a los 300 ms), a `CALIBRANDO`; salir del programa; excepción en el motor; error de envío (`ErrorEnvio`); cambio de escritorio (pantalla de bloqueo/UAC); tope de 60 s de arrastre; abrir Opciones; cerrar sesión (`WM_QUERYENDSESSION`).

---

## 6. Interfaz

Principios: todo se puede usar **solo con la cabeza** (cada control propio es un objetivo de permanencia); letras grandes (mínimo 16 pt en ventanas, 20 pt en barra y teclado; escalables 100 % a 200 %); contraste ≥ 7:1 (fondo `#0b1a36`, texto `#ffffff`, acento cian `#22e3ff`, ámbar `#ffb020` para "pausa", verde `#3ddc84` para "activo", rojo `#ff5c5c` para "sin cara"); opción "alto contraste" (negro/amarillo); nunca solo color: cada estado tiene también texto e ícono. Ventanas propias con `no_activar()` (WS_EX_NOACTIVATE + TOPMOST + TOOLWINDOW) para no robar el foco.

### 6.1 Ventana principal (520×420 aprox., siempre visible, modo mini)
- Estado grande ("Activo", "En pausa", "No veo su cara") con su color e ícono.
- Vista de la cara como **puntos/silueta** (sin video por defecto; opción "Mostrar video de la cámara" apagada).
- Botones grandes: Pausar/Reanudar, Teclado, Recentrar, Calibrar, Opciones, Ayuda "?", Salir (Salir pide confirmación por permanencia en "Sí, salir").
- Barras pequeñas en vivo de cada gesto encendido (con línea de umbral).
- Modo **mini**: tira de 260×64 con estado y Reanudar.
- **Indicador permanente** en el borde superior (tira de 6 px del color del estado, atravesable por clics) — opcional, encendido por defecto.

### 6.2 Barra de acciones (`ui/barra.py`)
- Botones de 96 px (rango 72 a 140), separación 12 px, ícono + texto: **Clic, Doble, Derecho, Arrastrar, Desplazar, Teclado, Pausa**.
- Posición: derecha en vertical (por defecto), izquierda, arriba, abajo; se aparta del borde 8 px; siempre encima.
- Elegir un botón = permanencia por objetivo (`barra.permanencia_s`, 1,0 por defecto) o gesto de clic con el puntero encima. **Nunca** hace clic en lo que está detrás.
- 1.1: también **Sin clic** (⊘), **Lupa** (⊕) y **Minimizar** (▁) al final (los dos primeros se pueden quitar: `barra.boton_sin_clic`, `barra.boton_lupa`). Si no caben en una columna (o fila) sin bajar de 72 px, se arman en **dos columnas**, de arriba abajo y luego al lado (`medidas_barra` devuelve también las columnas). Con el teclado abierto la barra no muestra Sin clic ni Lupa (cabe en una columna y el teclado conserva su ancho).
- **Minimizar** esconde la barra y deja la pestaña «Barra» en el mismo borde (al menos 56 × 120 px, o 120 × 56 en horizontal, letra de 18 pt). Quieto **0,6 s** sobre la pestaña (`ui:barra_mostrar`, también en `PAUSA`) o el ratón del cuidador la abren. Lo minimizado **no se guarda**: al abrir manda `barra.visible` ("Mostrar la barra al abrir"). En `DESPLAZAR` no hay Minimizar y la barra siempre se ve ("Terminar").

### 6.3 Indicador del cursor (`ui/indicador.py`)
Toplevel sin bordes, atravesable, siempre encima, junto al cursor: anillo de permanencia (cian, 4 px de grosor, 48 px), barra de cierre de ojos (se llena; al llegar, cambia a verde "Abra los ojos"), etiqueta del `modo_clic` cuando no es `izq` ("Doble", "Derecho", "Arrastrando"; 1.1: "Sin clic", "Lupa").

### 6.4 Teclado en pantalla (`ui/teclado.py`), ver sección 7
Ventana grande (por defecto la mitad inferior de la pantalla; se puede mover arriba), con: área de texto (letra 28 pt), fila de sugerencias, filas de teclas, fila de acciones, panel de frases rápidas (pestaña o columna), botones **Sí** y **No** grandes y separados siempre visibles.
- 1.1: **Minimizar** (arriba a la derecha, junto a Hablar/Repetir/Escribir) esconde el teclado sin borrar lo escrito, vuelve a `NORMAL` y deja la pestaña «Teclado» (al menos 160 × 56 px) en su borde. Quieto 0,6 s sobre la pestaña (`ui:teclado_mostrar`), «Teclado» en la barra o el atajo lo **restauran** con el texto tal como estaba. «Cerrar» sigue cerrando. Con barrido o «Solo comunicación» **no se ofrece** (ni en la ventana ni en el barrido).

### 6.5 Calibración (`ui/calibracion.py`): ver 4.1. Pantalla completa opcional, con dibujo de la cara que indica qué hacer.

### 6.6 Opciones (`ui/opciones.py`)
1.1: en **Puntero**, la velocidad 1–10 se elige con dos botones grandes «◀ Más lento» / «Más rápido ▶» (76 px de alto) y "3 de 10" en el centro; escribe juntos `sens_x`, `sens_y = sens_x × ajuste_vertical` (entre 0,92 y 3,3) y `joystick_g` (tabla `JOYSTICK_VELOCIDAD`); no hay clave nueva (se deduce de `sens_x`) y la calibración no cambia. Debajo, "Velocidad arriba y abajo" (`puntero.ajuste_vertical`, 0,8–2,0, en %). En **Clic**: la lupa (aumento, tamaño de la zona, espera). En **Comodidad**: botones «Sin clic» y «Lupa» en la barra.
Pestañas con vista previa en vivo y "Cancelar" que revierte: **Puntero** (sensibilidad x/y, suavidad, zona muerta, aceleración, modo absoluto/joystick, monitor), **Clic** (permanencia sí/no, tiempo, radio, recuperación, sonido, modo de la barra fijo/un uso), **Gestos** (encender/apagar cada uno, sensibilidad, sostener, acción corta y larga, barras en vivo con "Probar"), **Teclado y voz** (distribución, permanencia del teclado, barrido sí/no y velocidad, voz, volumen, velocidad, "Probar voz", modo Mensaje/Directo), **Frases** (abre el editor), **Comodidad** (tamaño de letra, alto contraste, posición de la barra, indicador del borde, aviso de descanso, abrir al encender, arrancar activo o en pausa, mostrar video), **Atajos**. Todos los controles son botones grandes de "−" y "+" (no deslizadores finos), para que sean operables con la cabeza. "Volver a los valores de fábrica" pide confirmación.

### 6.7 Ayuda (`ui/ayuda.py`)
Chuleta con dibujos de cara generados (boca abierta, cejas arriba, sonrisa, ojos cerrados largo) y su acción actual; "?" en cada paso y cada pestaña con `Globo`; sección "Para el cuidador" (instalación, cámara a la altura de los ojos a 50-70 cm, luz de frente sin ventana detrás, calibración, frases, atajos); sección "Qué hacer si…". Acerca de: versión, licencia MIT, atribución de la lista de palabras (FrequencyWords, CC BY-SA 4.0).

### 6.8 Sonidos (copiados, en hilo aparte; activados por defecto)
Clic suave al disparar permanencia/gesto, tono al pausar y otro al reanudar, "listo" al cumplirse el parpadeo largo (opcional), alerta de urgencia.

### 6.9 Cansancio
Aviso de descanso cada 25 min (apagado por defecto, nunca bloquea); recentrar a mano; subir sensibilidad para mover menos el cuello; perfiles por momento del día.

### 6.10 Textos
Todos en `ui/textos.py` (`TXT`, `t()`), con la prueba que prohíbe jerga ("landmark", "threshold", "blendshape", "frame", "click" en inglés, "setear", etc.) y exige "usted" (no "tú", "vos", "puedes", "haz"). Ejemplos: "No veo su cara. Acérquese a la cámara o revise la luz.", "Quédese quieto un momento sobre el botón para elegirlo.", "Cierre los ojos un momento largo para elegir.".

---

## 7. Teclado, barrido, predicción, frases y voz

### 7.1 Distribuciones (`teclado_logica.py`)
- **QWERTY español** (por defecto con permanencia): `Q W E R T Y U I O P` / `A S D F G H J K L Ñ` / `Z X C V B N M , . ´` / `¿ ? ¡ ! Espacio(ancho 4) ↵`.
- **Frecuencia** (por defecto con barrido): `␣ E A O S R N .` / `I D L C T U M ,` / `P B G V Y Q H ¿ ?` / `F Z J Ñ X K W ´ ¡ !` (4 filas; ver decisiones, Parte 4).
- Mayúscula automática al inicio de frase (después de `. ? !` y al empezar); tecla `⇧` opcional para una mayúscula.
- **Tilde**: `´` deja pendiente la tilde; la siguiente vocal sale tildada (á é í ó ú); si la siguiente no es vocal, se escribe la letra sin tilde. `´` dos veces seguidas = diéresis en la siguiente u (ü).
- Fila de acciones: **Borrar** (una letra), **Borrar palabra**, **Deshacer**, **Copiar**, **Limpiar todo** (pide confirmación: "¿Borrar todo el texto?" Sí/No), **Frases**, **Barrido**, **Pausa**, **Cerrar teclado**. **Hablar**, **Repetir** y **Escribir** (en el programa activo) van junto al texto (ver decisiones, Parte 4).
- Teclas: mínimo 80 px, por defecto el mayor tamaño que quepa (objetivo 90 a 110 px) con separación de 8 px.
- La lógica produce `objetivos()` = lista de `(id, rect relativo)`; la interfaz la convierte a píxeles de pantalla.

### 7.2 Barrido (`barrido.py`, puro)
- Niveles: **filas** → **elementos** de la fila elegida.
- Orden de filas: 1) **Frases rápidas** (la fila de frases visibles), 2) sugerencias, 3) filas de letras, 4) acciones.
- Avance cada **1,5 s** (rango 0,5 a 4,0); el **primer** elemento de cada nivel se queda 1,5×.
- Elegir = `ParpadeoLargo`. Al **empezar a cerrar** los ojos el resaltado **se congela**; si el cierre resulta natural, el barrido sigue donde iba; si es largo, se elige lo que estaba resaltado al cerrar.
- Tras elegir: pausa 0,8 s; hay que abrir los ojos antes de poder elegir otra vez; vuelve a la primera fila.
- Cada fila termina en "↩ Volver". Tras **2 vueltas** dentro de una fila sin elegir → vuelve al nivel de filas. Tras **3 vueltas completas** de filas sin elegir nada → el barrido se detiene y muestra "Parpadee largo para continuar".
- Sí/No: en el nivel de filas, la fila de frases empieza por Sí y No.
- Opcional: un gesto (boca/cejas) asignado a `borrar` o a "siguiente" (avance manual).
- API: `Barrido(filas, paso_s).actualizar(t, ojos_cerrando: bool, evento) -> resaltado, elegido|None`.

### 7.3 Predicción (`prediccion.py`, puro)
- Lista `recursos/palabras_es.txt` (20 000 palabras con frecuencia; FrequencyWords/OpenSubtitles, CC BY-SA 4.0 — cabecera y Acerca de lo nombran).
- Vocabulario de cuidado con prioridad (se suma a la lista): cobija, sábana, almohada, pañal, aspirar, flemas, saliva, succión, oxígeno, máscara, BiPAP, ventilador, sonda, gastrostomía, medicamento, pastilla, enfermera, terapeuta, silla, cama, voltear, acomodar, rascar, picar, ducha, peinar, gafas, televisor, celular, ventana, cortina, luz.
- Prefijo comparado **sin tildes** y en minúsculas, búsqueda binaria en la lista ordenada; puntaje = `log(frecuencia+1) + 3·log(1+usos_persona) + 0,5·reciente + 2·cuidado`. 5 sugerencias; al elegir una se reemplaza la palabra en armado y se agrega espacio. Respeta la mayúscula inicial.
- Sin prefijo (después de espacio): siguiente palabra a partir de los pares aprendidos de la persona; si no hay, las 5 palabras más usadas por ella.
- Aprende al pulsar Espacio, Hablar o Escribir; guarda en `palabras_usuario.json` (máx. 5000 palabras y 10000 pares; se recortan las menos usadas). Botón "Olvidar las palabras aprendidas" (con confirmación).

### 7.4 Frases rápidas (`frases.py`)
Archivo `frases.json` (validado; texto 1 a 200 caracteres; máximo 12 categorías y 40 frases por categoría). Categorías por defecto (editables, con variante masculina/femenina donde aplica, elegida en Opciones):
- **Básicas**: Sí · No · No sé · Espere, estoy escribiendo · Gracias · Por favor · Otra vez · Ya está bien.
- **Necesidades**: Tengo sed · Tengo hambre · Necesito ir al baño · Cambiarme de posición · Tengo calor · Tengo frío · Me pica · Acomódeme la cabeza · Límpieme la boca · Necesito que me aspiren · Ajústeme la máscara · Quiero descansar · Prenda o apague la luz · Súbale o bájele al televisor.
- **Dolor**: Tengo dolor · Me duele la cabeza · Me duele el pecho · Me duele el estómago · Me duele la espalda · Me duelen las piernas · Me duelen los brazos · Es fuerte · Es leve.
- **Urgencia**: ¡Ayuda, llamen a alguien! (alerta + volumen máximo) · Llamar a {cuidador} · Me falta el aire · Llamen al médico.
- **Afecto**: Te quiero · Estoy bien · Estoy cansado/cansada · Tengo miedo · Me alegra verte · Quiero estar solo/sola un rato · Gracias por cuidarme · No entiendo, repítalo.
- Al elegir una frase: se dice en voz alta (por defecto) y se muestra grande. `{cuidador}` se reemplaza por el nombre configurado (por defecto "alguien").
- Editor (`ui/editor_frases.py`) para el cuidador con teclado y ratón: agregar, cambiar, borrar, ordenar, restaurar las de fábrica.

### 7.5 Escribir, copiar y hablar
- **Modo Mensaje** (por defecto): se arma el texto; "Escribir" lo envía completo al programa activo (`OrdenEscribir` → motor → `Texto`). **Modo Directo** (opcional): cada tecla se envía al instante (`Texto(c)` o `TeclaVK`).
- **Copiar**: `sistema/portapapeles.py` (OpenClipboard, EmptyClipboard, GlobalAlloc, CF_UNICODETEXT = 13), reintentos 5 × 50 ms si el portapapeles está ocupado.
- **Hablar**: `voz.hablar(texto)`; "Repetir" dice lo último.

---

## 8. Seguridad: "soltar todo" y fallos
1. `salida.soltar_todo()` libera botones izq/der/medio y teclas que el programa haya bajado; es idempotente y seguro desde cualquier hilo.
2. Se llama en todas las transiciones de 5.5, en `atexit`, en señales, en el `finally` de `main()` y del bucle del motor, y desde el atajo de pausa.
3. Clics y texto siempre como pares bajar/subir en un solo `SendInput`. El único botón que puede quedar abajo es el del arrastre, con tope de 60 s.
4. Sin cara 300 ms ⇒ soltar todo (aunque esté arrastrando).
5. Motor caído (sin vista nueva en 2 s) ⇒ la interfaz llama `soltar_todo()` y muestra "Algo falló; estoy reiniciando la detección" y reinicia el motor (hasta 3 veces; luego pausa).
6. Atajo de pausa del cuidador **siempre** funciona, aunque el motor esté trabado (se procesa en el hilo de atajos → `soltar_todo()` directo + orden de pausa).
7. Nunca se envían clics sobre ventanas propias (se comprueba con `WindowFromPoint` y el PID); la elección en ventanas propias es interna.

---

## 9. Configuración (`config.json`, versión 1)

```json
{
  "version": 1,
  "primera_vez": true,
  "perfil_activo": "Principal",
  "camara": {"indice": 0, "ancho": 640, "alto": 480, "fps": 30, "fps_proceso": 20, "espejo": true},
  "pantalla": {"monitor": "principal"},
  "puntero": {"modo": "absoluto", "sens_x": 1.0, "sens_y": 1.2, "suavidad": 3, "zona_muerta_px": 4,
              "zona_muerta_centro": 0.03, "aceleracion": 0, "margen": 0.10, "joystick_g": 1200},
  "permanencia": {"activa": true, "tiempo_s": 1.0, "radio_px": 30, "recuperacion_s": 1.0,
                  "margen_ms": 150, "anillo_px": 48, "anillo_desde_ms": 200, "sonido": true},
  "gestos": {
    "boca":     {"activo": true,  "sens": 1.0, "sostener_ms": 350, "corto": "clic",     "largo": "pausar"},
    "cejas":    {"activo": true,  "sens": 1.0, "sostener_ms": 350, "corto": "clic_der", "largo": "ninguna"},
    "sonrisa":  {"activo": false, "sens": 1.0, "sostener_ms": 400, "corto": "ninguna",  "largo": "ninguna"},
    "parpadeo": {"activo": true,  "largo_ms": 800, "descanso_ms": 4000, "doble": false,
                 "cerrado": 0.55, "abierto": 0.70, "fuera_barrido": "ninguna"},
    "largo_ms": 2000, "refractario_ms": 600, "reanudar_ms": 3000
  },
  "barra": {"visible": true, "posicion": "derecha", "boton_px": 96, "permanencia_s": 1.0, "modo_fijo": false},
  "teclado": {"distribucion": "auto", "permanencia_s": 1.0, "barrido": false, "barrido_paso_s": 1.5,
              "modo_escritura": "mensaje", "letra_pt": 28, "posicion": "abajo", "genero": "neutro",
              "cuidador": "alguien", "solo_comunicacion": false},
  "voz": {"nombre": null, "volumen": 80, "velocidad": -1, "hablar_frases": true},
  "seguridad": {"soltar_sin_cara_ms": 300, "pausa_sin_cara_s": 10, "arrastre_max_s": 60},
  "arranque": {"al_encender": false, "estado": "auto"},
  "atajos": {"pausar": "Ctrl+Alt+Espacio", "teclado": "Ctrl+Alt+T", "recentrar": "Ctrl+Alt+C",
             "ventana": "Ctrl+Alt+Inicio", "salir": "Ctrl+Alt+Fin"},
  "comodidad": {"escala_letra": 1.0, "alto_contraste": false, "indicador_borde": true,
                "mostrar_video": false, "descanso_min": 0, "sonidos": true},
  "ventana": {"x": null, "y": null, "mini": false},
  "perfiles": {"Principal": {"calibracion": null}}
}
```

1.1 paquete A (bloque aparte al final de `FABRICA`; una configuración 1.0 sin estas claves toma estos valores sin anotar problemas): `puntero.ajuste_vertical` = 1,2; `barra.boton_sin_clic` = true; `barra.boton_lupa` = true; `lupa` = `{"zona_px": 200, "aumento": 3, "espera_s": 8.0}`.

`calibracion` de un perfil: `{"fecha", "centro": [yaw0, pitch0], "izq", "der", "arr", "aba", "signo_x", "signo_y", "base": {"ear_der", "ear_izq", "mar", "cejas", "sonrisa"}, "umbrales": {...}, "parpadeo_natural_max_ms", "parpadeos_min"}`.

### 9.1 Rangos (`RANGOS`; fuera de rango ⇒ valor de fábrica + registro)
| Clave | Rango | Clave | Rango |
|---|---|---|---|
| camara.fps_proceso | 10–30 (entero) | permanencia.tiempo_s | 0,4–3,0 |
| puntero.sens_x / sens_y | 0,5–3,0 | permanencia.radio_px | 10–80 (entero) |
| puntero.suavidad | 1–5 (entero) | permanencia.recuperacion_s | 0,3–3,0 |
| puntero.zona_muerta_px | 0–15 | permanencia.margen_ms | 0–500 |
| puntero.zona_muerta_centro | 0–0,10 | permanencia.anillo_px | 40–80 |
| puntero.aceleracion | 0–3 (entero) | gestos.*.sens | 0,5–2,0 |
| puntero.margen | 0–0,25 | gestos.*.sostener_ms | 100–1000 |
| puntero.joystick_g | 600–3000 | gestos.parpadeo.largo_ms | 400–2000 (piso 400 siempre) |
| gestos.largo_ms | 1000–4000 | gestos.parpadeo.descanso_ms | 2000–10000 (y > largo_ms + 1000) |
| gestos.refractario_ms | 300–2000 | gestos.parpadeo.cerrado | 0,35–0,75 |
| gestos.reanudar_ms | 1500–5000 | gestos.parpadeo.abierto | cerrado+0,10 – cerrado+0,25 |
| barra.boton_px | 72–140 | teclado.barrido_paso_s | 0,5–4,0 |
| barra.permanencia_s / teclado.permanencia_s | 0,4–3,0 | teclado.letra_pt | 18–48 |
| voz.volumen | 0–100 | voz.velocidad | −5–5 |
| seguridad.soltar_sin_cara_ms | 150–1000 | seguridad.pausa_sin_cara_s | 3–60 |
| seguridad.arrastre_max_s | 10–300 | comodidad.escala_letra | 1,0–2,0 |
| comodidad.descanso_min | 0 o 10–120 (`MINIMO_SI_NO_CERO`) | | |
| puntero.ajuste_vertical (1.1) | 0,8–2,0 | lupa.zona_px (1.1) | 120–400 (entero) |
| lupa.aumento (1.1) | 2–5 (entero) | lupa.espera_s (1.1) | 4,0–20,0 |

`OPCIONES`: `puntero.modo` ∈ {absoluto, joystick}; `barra.posicion` ∈ {derecha, izquierda, arriba, abajo}; `teclado.distribucion` ∈ {auto, qwerty, frecuencia}; `teclado.modo_escritura` ∈ {mensaje, directo}; `teclado.posicion` ∈ {abajo, arriba}; `teclado.genero` ∈ {neutro, masculino, femenino}; `arranque.estado` ∈ {auto, activo, pausa}; acciones de gestos ∈ lista de 5.4. Si dos gestos activos quedan sin ninguna forma de reanudar (por ejemplo, ningún gesto con `pausar` y sin permanencia), la validación **vuelve a encender** la permanencia sobre el botón "Reanudar" (siempre existe).

---

## 10. Atajos globales (para el cuidador)
| Atajo | Acción |
|---|---|
| Ctrl+Alt+Espacio | Pausar / reanudar (siempre funciona; suelta todo) |
| Ctrl+Alt+T | Abrir / cerrar el teclado |
| Ctrl+Alt+C | Recentrar |
| Ctrl+Alt+Inicio | Mostrar la ventana principal |
| Ctrl+Alt+Fin | Salir (suelta todo) |
- Elegidos para no chocar con Lycan Mouse Control (Ctrl+Alt+M/X/O/D/P). `atajos.py` comprueba con `ToUnicode` que la combinación no produzca un carácter con AltGr en la distribución activa (teclado latinoamericano) y, si el atajo está ocupado, avisa y deja cambiarlo.

---

## 11. Privacidad
- Todo ocurre en el equipo: **sin internet**, sin cuentas, sin estadísticas de uso.
- El video **no se guarda nunca** y no se muestra por defecto (solo puntos/silueta).
- Lo único que se guarda: `config.json`, `frases.json`, `palabras_usuario.json` (palabras y pares aprendidos) y el registro de errores (sin texto escrito por la persona: el registro **nunca** contiene lo que se escribe ni lo que se habla).
- Botones "Olvidar las palabras aprendidas" y, al desinstalar, pregunta si se borran los datos (por defecto se conservan).
- Las pruebas y el desarrollo usan caras sintéticas; nunca la cámara real.

---

## 12. Rendimiento
- Procesar como máximo `fps_proceso` (20) cuadros por segundo; si el procesamiento tarda más, se procesa el último cuadro disponible (sin cola).
- Meta: latencia cámara→puntero p95 < 120 ms; CPU < 35 % de un portátil de 4 núcleos; memoria < 350 MB.
- `refine_landmarks=True` siempre (hacen falta ojos precisos para el parpadeo).
- La interfaz repinta a 30 Hz como máximo; la vista de puntos a 15 Hz.
- Línea de rendimiento en el registro cada 60 s (fps, latencia media y p95, CPU).

---

## 13. Plan de pruebas (pytest, `py -3.10 -m pytest -q pruebas`)
La mayoría **no** importa mediapipe; las que lo usen llevan la marca `mediapipe` y se saltan si no está. `pytest.ini` copiado (marca `manual` excluida).

### 13.1 Generador de caras sintéticas (`pruebas/sintetico/cara_sintetica.py`)
- Carga `pruebas/datos/cara_dibujada_base.json` (478×3, puntos reales de mediapipe).
- `cara(yaw=0, pitch=0, roll=0, ojo_der=1, ojo_izq=1, boca=0, cejas=0, sonrisa=0, escala=1, centro=(320,240), ruido=0, rng=None) -> np.ndarray (478,3)`:
  - ojos (0 cerrado..1 abierto): acerca los párpados superiores (der 159,160,161,158,157,56,28,27,29,30,247,246; izq 386,385,384,387,388,286,258,257,259,260,467,466) hacia los inferiores (der 145,144,153,154,155,163,7; izq 374,373,380,381,382,390,249);
  - boca (0..1): baja el labio inferior (14,87,178,88,95,317,402,318,324,15,16,17,84,181,91,146,314,405,321,375) y el mentón un poco;
  - cejas (0..1): sube los puntos de cejas ([70,63,105,66,107,46,53,52,65,55] y espejo [300,293,334,296,336,276,283,282,295,285]);
  - sonrisa (0..1): separa y sube las comisuras 61, 291 y vecinas;
  - cabeza: rotación 3D alrededor del centro de la cara (yaw/pitch/roll en grados) y proyección;
  - ruido gaussiano en píxeles.
- `linea_de_tiempo([(t, params), ...], fps)` → lista de `(t, puntos)` interpolados, para secuencias.
- `CamaraFalsa` + `DetectorFalso` (devuelve los puntos del generador) para probar el motor completo sin mediapipe.

### 13.2 Pruebas obligatorias
- **Medidas** (`test_cara.py`): EAR/MAR/cejas/sonrisa sobre la cara base ≈ valores de 3.4; invariancia de `yaw_n`/`pitch_n` a traslación 60 px, escala 0,7 y roll 15°; yaw crece al girar a la derecha (signo); `puntos_validos` rechaza NaN y `io < 40`.
- **Gestos** (`test_gestos.py`):
  - parpadeos naturales de 100, 150, 250 y 390 ms (y ráfagas de 3 seguidos) ⇒ **ningún** evento de clic ni de elegir, con fps 30, 15 y 8 (luz baja);
  - cierre de 900 ms ⇒ un `ParpadeoLargo` al abrir; cierre de 5 s ⇒ nada (descanso);
  - un solo ojo cerrado 1 s ⇒ nada;
  - hablar (boca 0,3–0,7 alternando cada 120 ms durante 3 s) ⇒ ningún clic;
  - boca 500 ms ⇒ `GestoCorto('boca')`; boca 2,2 s ⇒ solo `GestoLargo('boca')` (no también corto);
  - histéresis: señal oscilando en el umbral no produce rebotes; refractario respetado;
  - sonrisa con boca abierta no cuenta como sonrisa;
  - piso de 400 ms aunque la config diga 100.
- **Puntero y mapeo** (`test_puntero.py`, `test_mapeo.py`): centro ⇒ centro de pantalla; extremo calibrado ⇒ borde (con margen); zona muerta; congelar devuelve la posición de ~150 ms antes; reentrada sin saltos > 1/10 de la distancia por cuadro; recorte a la pantalla; sensibilidad por eje.
- **Permanencia** (`test_permanencia.py`): dispara a 1,0 s quieto; no dispara si se mueve más del radio; margen de 150 ms; no repite sin moverse 60 px; recuperación; por objetivo con franja de 12 %.
- **Estados** (`test_estados.py`, con `Sim` del conftest): pausa/reanuda con boca larga y con atajo; reanudar exige 3 s; arrastre completo (Bajar…Subir); **perder la cara a mitad de un arrastre ⇒ `SoltarTodo` a los 300 ms** y nunca queda botón abajo; pausa automática a 10 s y reanudación al estabilizar 1 s; desplazar envía `Rueda` y sale a los 10 s; `modo_clic` de un solo uso vuelve a `izq`; tope de arrastre 60 s; ninguna secuencia aleatoria (semillas, 200 corridas de 30 s) termina con botones abajo (`test_aleatorio.py`).
- **Teclado** (`test_teclado.py`): tilde + vocal = vocal tildada; mayúscula automática; borrar; objetivos sin solaparse y ≥ 80 px a 1366×768.
- **Barrido** (`test_barrido.py`): avanza solo con el tiempo (primer elemento 1,5×); parpadeo largo elige la fila y luego la tecla; parpadeo natural no elige y el barrido sigue; resaltado congelado al cerrar los ojos; "Volver"; salida a filas tras 2 vueltas; detención tras 3 vueltas.
- **Predicción** (`test_prediccion.py`): "sab" sugiere "sábana"; "cob" sugiere "cobija"; aprende palabras y sube su puesto; archivo dañado ⇒ se renombra y sigue; límite de tamaño.
- **Frases** (`test_frases.py`): editar, guardar y releer; validar (texto vacío, demasiado largo, tipos); `{cuidador}`; variante de género.
- **Salida** (`test_salida.py`): `Texto("¿Ñandú, pingüino? 👍")` genera los INPUT Unicode correctos (pares bajar/subir, par sustituto para el emoji); `\n` ⇒ VK_RETURN; `soltar_todo` idempotente; nada se envía a ventanas propias (simulado).
- **Config** (`test_config.py`): valores fuera de rango vuelven a fábrica; archivo dañado se renombra; validación de "siempre hay forma de reanudar".
- **Voz** (`test_voz.py`): escapado de `&`/`<`; elección de voz con lista simulada (sin Sabina ⇒ otra `es-*`; sin español ⇒ predeterminada); respaldo PowerShell construye el comando correcto (sin ejecutarlo). Prueba real de habla marcada `manual`.
- **Sistema** (`test_sistema.py`): atajos válidos y sin choque con AltGr; textos sin jerga y con "usted"; registro sin consola.
- **Motor** (`test_motor.py`): `CamaraFalsa` + `DetectorFalso` + `SalidaSimulada`: 3 s de secuencia mueven el puntero y hacen un clic por permanencia; detenerse suelta todo.
- **Con mediapipe** (marca `mediapipe`, opcional): la cara dibujada de `herramientas/cara_dibujada.py` produce medidas coherentes.

### 13.3 Prueba manual (antes de entregar; la hace una persona real, no los agentes)
Lista en el README: calibrar; mover a las 4 esquinas; clic por permanencia en el escritorio; boca = clic; cejas = derecho; arrastrar un archivo; desplazar una página; escribir "Hola, ¿cómo está? Ñandú" en el Bloc de notas con permanencia y con barrido; hablar una frase; pausar con la boca 2 s y con Ctrl+Alt+Espacio; taparse la cara a mitad de un arrastre; luz baja; 30 minutos de uso sin clics fantasma.

---

## 14. Empaquetado y CI
- Copiar del hermano y renombrar (`LycanMouseControl` → `LycanFaceControl`, `lycan_mouse_control` → `lycan_face_control`):
  - `empaquetado/lycan-face-control.spec`: `collect_data_files('mediapipe', includes=['modules/face_landmark/*','modules/face_detection/*'])` (si quedan solo los de mano, el .exe falla con "path does not exist ... face_landmark_front_cpu.binarypb"); `datas` + `recursos/` (ícono, `palabras_es.txt`, sonidos); mismos `excludes` (jax, jaxlib, matplotlib, sounddevice, scipy; **no** excluir `mediapipe.tasks`); sin `opencv_videoio_ffmpeg*.dll`; `upx=False`; `console=False`; modo carpeta.
  - `empaquetado/rthook_sin_matplotlib.py`: tal cual.
  - `empaquetado/version_info.txt`: textos de Lycan Face Control (0x240A).
  - `empaquetado/lycan-face-control.iss`: **AppId nuevo y fijo `{B4BABCB7-C4E4-4A96-88FE-6619BB585A56}`** (no cambiar nunca); `PrivilegesRequired=lowest`; carpeta de datos `{userappdata}\Lycan Face Control` (pregunta al desinstalar, por defecto conserva); valor Run "LycanFaceControl" con `--minimizado` (tarea "Abrir al encender el computador", desmarcada); `OutputBaseFilename=Lycan-Face-Control-{ver}-Windows-64-bits`; `CloseApplications=force`; borrado de `_internal` al actualizar.
- `.github/workflows/windows.yml`: Python 3.10 en windows-2025; venv limpio con versiones fijas (`mediapipe==0.10.14`, `numpy==2.2.6`, `opencv-python-headless==4.10.0.84`, `pyinstaller==6.22.3`); `pytest -q pruebas`; arrancador de PyInstaller compilado en el servidor; compilar; revisar que existan `mediapipe/modules/face_landmark/face_landmark_front_cpu.binarypb`, `face_landmark_with_attention.tflite`, `mediapipe/modules/face_detection/face_detection_short_range.tflite` y `recursos/palabras_es.txt`, y que **no** estén jax ni matplotlib; `--check` con `Start-Process -Wait -PassThru`; Inno Setup con `choco install innosetup`; instalador + ZIP portable con LEEME; artefactos 14 días; al empujar una etiqueta `v*` adjunta los archivos al release.
- Nombres: etiqueta `v1.0.0-prueba`; `Lycan-Face-Control-1.0.0-Windows-64-bits.exe` y `Lycan-Face-Control-1.0.0-portable.zip`.
- **No** se compila con PyInstaller en el portátil del usuario (poca memoria): solo en GitHub Actions.
- `requirements.txt` igual al hermano; `requirements-dev.txt` + pytest y pyinstaller==6.22.3. Sin pywin32, comtypes ni pyttsx3.
- SmartScreen: sin firma; el LEEME explica "Más información → Ejecutar de todas formas".

---

## 15. Plan de construcción (5 partes)
Cada parte termina con `py -3.10 -m pytest -q pruebas` en verde y un commit local. Nunca se abre la cámara real.

1. **Base + detector + medidas + caras sintéticas**: estructura de carpetas, `version.py`, `constantes.py`, `config.py` (con todo el `FABRICA` de la sección 9 y `RANGOS`), `registro.py`, `filtros.py`, `acciones.py`, `salida/` (con `Texto` y `TeclaVK`), `captura.py` + `CamaraFalsa`, `detector.py`, `cara.py`, `pruebas/sintetico/cara_sintetica.py`, `pytest.ini`, `conftest.py`; pruebas de medidas, filtros, salida y config. `.gitignore`, `requirements*.txt`, `lanzar.py`.
2. **Puntero + clics + gestos + permanencia**: `mapeo.py`, `puntero.py`, `gestos.py`, `permanencia.py`, `estados.py`, `calibracion.py` (lógica), `motor.py` (con `DetectorFalso`), `sistema/` copiados (dpi, pantallas, sonidos, ventanas_win, atajos, inicio); pruebas de 13.2 de gestos, puntero, permanencia, estados, aleatorias y motor.
3. **Interfaz + barra + calibración + opciones**: `app.py` (con `--check`, `--simular`, `--camara-falsa`, `--minimizado`), `ui/comun.py`, `ui/textos.py`, `ventana_principal.py`, `indicador.py`, `barra.py`, `ui/calibracion.py`, `opciones.py`, `ayuda.py`; prueba de textos; arranque de humo con `--simular --camara-falsa` cerrado por código a los pocos segundos (sin dejar procesos vivos).
4. **Teclado + barrido + predicción + voz + frases**: `teclado_logica.py`, `barrido.py`, `prediccion.py`, `frases.py`, `sistema/voz.py`, `sistema/portapapeles.py`, `ui/teclado.py`, `ui/editor_frases.py`, integración con estados (`TECLADO`, `BARRIDO`, `SOLO_COMUNICACION`) y con la barra; pruebas de teclado, barrido, predicción, frases y voz.
5. **Empaquetado + CI + README**: `empaquetado/*`, `.github/workflows/windows.yml`, `recursos/lycan-face.ico/.png`, `README.md` (qué es, para quién, instalación, primera vez, gestos, teclado, cuidador, atajos, seguridad, privacidad, límites honestos, licencia y atribuciones, prueba manual de 13.3), `LICENSE` (MIT). Revisión final de la sección 16.

---

## 16. Criterios de "terminado"
- Todas las pruebas de 13.2 pasan; ninguna importa mediapipe salvo las marcadas.
- `python -m lycan_face_control --check` sale con 0.
- Ningún camino deja botones o teclas abajo (pruebas aleatorias).
- Ningún parpadeo natural (< 400 ms) produce acción en ninguna prueba.
- Todo control propio es elegible por permanencia; letras ≥ 16 pt; contraste ≥ 7:1.
- Textos en `ui/textos.py`, en "usted", sin jerga.
- El workflow de GitHub produce instalador y ZIP (lo verifica el agente principal).

## 17. Riesgos conocidos
- Umbrales probados solo con caras dibujadas: la calibración por persona y los ajustes de sensibilidad son la defensa; la prueba con personas reales queda pendiente.
- Luz baja ⇒ menos cuadros por segundo: todos los tiempos son reales, no por cuadro.
- Gafas gruesas o reflejos pueden afectar el EAR: la calibración lo absorbe; si no, se recomienda el gesto de boca.
- Personas con movimientos involuntarios: subir suavidad, radio y tiempo de permanencia.
- Programas abiertos como administrador no reciben clics ni texto (aviso).
- La voz depende de las voces instaladas en Windows (respaldo: texto grande en pantalla).

## 18. Referencias
Project Gameface (Google), Camera Mouse (Boston College), Enable Viacam, Look to Speak (Google), OptiKey, Grid 3 / Tobii Dynavox, PRC-Saltillo (tiempos de barrido), estudio Nomon (arXiv 2204.01619), dinámica del parpadeo (Frontiers 2023), parpadeo voluntario/involuntario (arXiv 2402.07916), FrequencyWords (OpenSubtitles, CC BY-SA 4.0). Detalle y enlaces en `docs/decisiones.md`.
