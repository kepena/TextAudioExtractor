# Requerimientos del cliente — TextAudioExtractor

Creado: 2026-07-29

Documento de alcance y requerimientos para operar la solución en el entorno de un
cliente. Deriva del roadmap (`docs/roadmap.md`) y de los pendientes cerrados
(`docs/pendientes.md`). Léase junto con los **invariantes** del proyecto en
`CLAUDE.md`.

---

## 1. Funcionalidades de la solución

Lo que la solución hace o hará, agrupado por área.

### Entrada de video
- Carga de video **local** por diálogo de archivo.
- Carga por **drag-and-drop** desde el Explorador (filtra por extensiones de video).
- Descarga desde **YouTube / plataformas online** vía `yt-dlp` (URL individual).
- **Playlists en lote**: procesa varias URLs; un fallo por ítem no aborta el lote
  y se reporta clasificado.
- Soporte de **cookies** (nombre de navegador o `cookies.txt`) para videos con
  login, restricción de edad o anti-bot.

### Extracción de texto
- **Detección de subtítulos incrustados**: si el video los trae, extrae la pista
  (ffmpeg / pista del creador en online) sin transcribir.
- Si no hay subtítulos, **transcripción del audio con Whisper local**
  (faster-whisper) en **GPU NVIDIA** (degrada a CPU sin morir).
- Opción `--force-transcribe` para transcribir aunque existan subtítulos.
- **Diarización de hablantes** opt-in (whisperX, `--diarize`), con `SPEAKER_00:`
  en la salida y `--speakers N` para fijar el número de voces.
- Detección de **idioma** automática.

### Salidas
- Texto **plano** (`.txt`).
- Texto con **marcas de tiempo** (`.srt`).
- **Audio separado** (`.mp3`).

### Interfaz / operación
- GUI PySide6 con marca Kaiketek: barra de progreso 0→100 %, etiquetas de etapa,
  bloqueo de inputs durante el proceso, botón **Cancelar** limpio y **Abrir carpeta**.
- CLI equivalente: `tae local <video>` y `tae url <URL>`.
- Motor **headless reutilizable** (core sin dependencia de la GUI), pensado para
  escalar a producto/servicio.
- Detección y aviso claro cuando falta un binario del sistema
  (`ffmpeg` / `whisper` / `yt-dlp`) o un **runtime JS** (deno/node/bun) para YouTube.

### Pendiente activo
- **P11**: torch con CUDA para que la diarización corra en GPU (hoy corre en CPU).

---

## 2. Requerimientos a solicitar / que debe cumplir el cliente

### Hardware
- **GPU NVIDIA** con CUDA (referencia probada: RTX 4050) para tiempos usables de
  transcripción y diarización. Sin GPU funciona, pero 3–5× el tiempo del video.
- Disco suficiente para modelos de Whisper + medios descargados.

### Software / binarios de sistema (no son pip, se instalan aparte)
- **ffmpeg** en el PATH.
- **yt-dlp** (para el módulo online).
- **Runtime JS** (Node / Deno / Bun) en el PATH — YouTube lo exige actualmente.
- Drivers NVIDIA + CUDA compatibles con el torch CUDA.
- Sistema operativo **Windows** (la app está construida y verificada ahí).

### Credenciales y accesos (solo módulo online)
- **Token de Hugging Face** para descargar los modelos de diarización (whisperX).
- Un `cookies.txt` de una **cuenta desechable de Google/YouTube** (no la principal)
  para videos con login, restricción de edad o cuando aparezca el anti-bot.
  Hallazgo verificado: en Brave sobre Windows `--cookies-from-browser` es poco
  fiable; el `cookies.txt` exportado sí funciona.

### Insumos que debe entregar el cliente
- Los **videos** o las **URLs** a procesar (con derecho de uso sobre ese contenido).
- Preferencia de salidas (texto plano / SRT / audio) y si quiere diarización.

### Restricciones de alcance que el cliente debe aceptar (invariantes del proyecto)
- **Todo local, nada a la nube**: no se sube audio ni video a terceros (sin APIs de
  transcripción cloud).
- **No se edita el video**: solo se extrae texto y audio; nada de cortar,
  recomprimir ni recodificar.
- Traducción automática **no** está incluida (por decidir, no comprometida).
