# Spec — Extractor de texto y audio de video (MVP)

Fecha: 2026-07-26
Estado: **aprobado (2026-07-26)**

## 1. Overview

App de escritorio para Windows que recibe un video y devuelve dos cosas: su
**texto** y su **audio**. Si el video trae subtítulos incrustados, los extrae tal
cual; si no, transcribe el audio hablado con Whisper local (GPU). El texto se
entrega en dos formatos: plano (solo palabras) y con marcas de tiempo tipo `.srt`.
Se construye como motor headless reutilizable con una GUI delgada encima, para uso
interno de Kaiketek ahora y con vistas a volverse producto.

## 2. Usuarios específicos

- **Kike y el equipo de Kaiketek (uso interno, arranque).** Alguien que tiene un
  archivo de video en su PC (una grabación, una clase, un webinar, una llamada) y
  necesita el texto para reutilizarlo —notas, subtítulos, contenido— y/o el audio
  suelto. Sabe usar Windows pero **no** quiere tocar línea de comandos.
- **A futuro (fuera del MVP como público objetivo, pero la arquitectura no lo
  impide):** un cliente externo que reciba la app empaquetada.

El motor (`core`) tiene un segundo "usuario" implícito: **el propio desarrollador**
que lo invoca por CLI/tests sin la GUI. Por eso el motor debe ser usable solo.

## 3. Contexto del problema

Hoy sacar el texto de un video es un proceso manual y fragmentado: subir el archivo
a un servicio en la nube (con el costo y el problema de privacidad de mandar
material propio a un tercero), o pelearse con `ffmpeg` y Whisper a mano en la
terminal. No hay una herramienta local, de un clic, que resuelva los dos casos
—video con subtítulos y video sin ellos— y que además entregue el audio separado.

El disparador: Kike necesita esto para su propio flujo de trabajo y quiere una base
técnica limpia que pueda convertirse en producto Kaiketek más adelante.

## 4. Alcance versión 1

### Incluye

- **Entrada:** un archivo de video local (formatos comunes: mp4, mkv, mov, avi,
  webm). Un video a la vez.
- **Detección automática** de si el video trae una o más pistas de subtítulos
  incrustadas.
- **Extracción de subtítulos** cuando existen, sin transcribir.
- **Transcripción local con faster-whisper (GPU NVIDIA)** cuando no hay subtítulos,
  o cuando el usuario la fuerza aunque haya subtítulos.
- **Extracción del audio** a un archivo independiente.
- **Salidas de texto en dos formatos:** plano (`.txt`) y con timestamps (`.srt`).
- **Carpeta de salida configurable:** hay una carpeta por defecto, pero el usuario
  puede elegir otra **antes** de procesar el video.
- **Selección de idioma:** automático (que Whisper lo detecte) o elegido por el
  usuario.
- **Selección del modelo de Whisper** (p. ej. `small` / `medium` / `large`) para
  cambiar el balance velocidad/precisión.
- **GUI delgada (PySide6):** arrastrar o elegir el video, marcar qué salidas se
  quieren, botón de iniciar, barra de progreso, y acceso a la carpeta de resultados.
- **Motor headless (CLI)** equivalente, sin depender de la GUI.

### No incluye (explícito)

- **Edición de video** (cortar, recomprimir, re-codificar el video original).
- **Transcripción en la nube** (ninguna API externa; todo local).
- **Módulo de YouTube / plataformas online.** Queda para una fase posterior; el
  motor se diseña para poder enchufarlo, pero no se construye en el MVP.
- **Traducción automática** a otro idioma. *(No descartada para el futuro; no está
  en V1.)*
- **Diarización de hablantes** (quién dice qué). *(Igual: futuro, no V1.)*
- **Procesamiento por lotes** (varios videos en cola). V1 es de a un video.

## 5. Comportamiento esperado

### Flujo principal (GUI)

1. El usuario abre la app. Ve una ventana con una zona para **arrastrar un video**
   (o un botón "Elegir archivo").
2. Al soltar el video, la app muestra su nombre, duración y **si detectó
   subtítulos incrustados** (y en qué idiomas, si hay varios).
3. El usuario elige las **salidas** que quiere, con casillas:
   - Texto plano (`.txt`)
   - Texto con timestamps (`.srt`)
   - Audio separado
4. El usuario ve la **carpeta de salida** con un valor por defecto (una subcarpeta
   junto al video original, con el nombre del video) y un botón para **cambiarla**
   antes de procesar. Lo que elija aquí es donde caerán los resultados.
5. Según el estado del video:
   - **Si hay subtítulos incrustados:** la app ofrece por defecto **extraerlos**
     (rápido). El usuario puede, si quiere, marcar "transcribir de todos modos" para
     ignorar la pista y usar Whisper.
   - **Si no hay subtítulos:** la app indica que hará **transcripción con Whisper**,
     y muestra los controles de **idioma** (auto / elegir) y **modelo**
     (velocidad vs precisión).
6. El usuario pulsa **Iniciar**. Aparece una **barra de progreso** con el paso
   actual en texto claro ("Extrayendo audio…", "Transcribiendo… 40%").
7. Al terminar, la app muestra un resumen de los archivos generados y un botón para
   **abrir la carpeta de resultados** (la que el usuario haya fijado en el paso 4).

### Comportamiento del texto

- **Texto plano (`.txt`):** solo el contenido hablado/subtitulado, en párrafos
  legibles, sin marcas de tiempo.
- **Texto con timestamps (`.srt`):** formato de subtítulos estándar, con numeración
  de bloques e intervalos `HH:MM:SS,mmm --> HH:MM:SS,mmm`, de modo que sirva
  directamente como archivo de subtítulos reproducible.
- Ambos formatos salen de la misma fuente (la pista extraída o la transcripción), de
  modo que el `.txt` es el `.srt` sin las marcas.

### Flujo equivalente por CLI (motor)

- El motor expone un comando que recibe la ruta del video y flags para: qué salidas
  generar, forzar transcripción, idioma, modelo, y carpeta de salida. Hace lo mismo
  que la GUI y sirve para pruebas automatizadas. La GUI solo llama a este motor.

### Rendimiento esperado

- Con la GPU NVIDIA disponible y `faster-whisper`, la transcripción debe correr
  **más rápido que el tiempo real del video** en modelos hasta `medium`. `large` es
  más lento pero más preciso: es decisión del usuario vía el selector de modelo.
- La extracción de subtítulos incrustados y de audio es cuestión de segundos
  (no reprocesa el video, solo copia/convierte pistas).

## 6. Posibles errores y mitigaciones

- **Falta `ffmpeg` en el sistema.** Al abrir, la app verifica su presencia. Si no
  está, muestra un mensaje claro con cómo instalarlo y **no** deja iniciar, en vez
  de reventar a mitad del proceso.
- **No hay GPU NVIDIA / drivers CUDA.** El motor **no crashea**: avisa que correrá
  en CPU (más lento) y deja continuar. Nunca muere silenciosamente ni finge que hubo
  GPU. (Invariante 3 del repo.)
- **Formato de video no soportado / archivo corrupto.** Mensaje claro ("No pude leer
  este video, ¿está completo?"), sin traceback crudo. El usuario puede intentar con
  otro archivo.
- **El video no tiene pista de audio** (p. ej. una pantalla grabada muda). La app lo
  detecta antes de transcribir y avisa que no hay nada que transcribir; si pidió solo
  audio, informa que no existe.
- **Subtítulos incrustados en un formato raro o dañado.** Si la extracción falla, la
  app lo dice y ofrece **transcribir con Whisper** como alternativa, en vez de
  quedarse sin salida.
- **Idioma mal detectado.** Como el usuario puede fijar el idioma manualmente, si el
  auto falla tiene una salida clara: re-correr fijando el idioma.
- **Sin espacio en disco o sin permiso de escritura en la carpeta destino.** La app
  avisa antes o durante, y permite elegir otra carpeta de salida.
- **Modelo de Whisper no descargado aún (primera vez).** La primera transcripción
  con un modelo nuevo lo descarga; la app muestra "Descargando modelo…" para que el
  usuario no crea que se colgó.
- **El usuario cierra la app a mitad del proceso.** Se cancela de forma limpia; los
  archivos parciales no se dan por válidos (se descartan o se marcan como
  incompletos).

---

**¿Este spec queda aprobado tal cual, o hay algo que ajustar antes de pasar al
plan?**
