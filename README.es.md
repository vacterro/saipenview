<div align="right">
  🌍 <strong>EN</strong> | <a href="README.ru.md">RU</a> | <a href="README.ee.md">EE</a> | <a href="README.ded.md">ДЕД</a> | <a href="README.ja.md">JA</a>
</div>

<div align="center">
  <img src="screenshots/saipen_icon.png" alt="SAIPENVIEW" width="120" height="120">
  <h1 align="center">SAIPENVIEW</h1>
  <p align="center">
    <strong>Visor en la bandeja del sistema para cada proyecto SAIPEN en tu equipo</strong>
    <br>
    Descubre automáticamente proyectos <code>.saipen/</code> en tus unidades locales: fase en vivo, tarea, bloqueador, estado de git, tickets y subagentes.
    <br>
    Un panel de control de estilo vintage Win95 en tono dorado oscuro.
  </p>
  <p>
    <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.10%2B-blue?style=flat-square&logo=python&logoColor=white" alt="Python"></a>
    <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="Licencia"></a>
    <a href="https://github.com/vacterro/saipenview"><img src="https://img.shields.io/badge/platform-Windows-orange?style=flat-square&logo=windows&logoColor=white" alt="Plataforma"></a>
    <a href="https://github.com/vacterro/saipenview/releases"><img src="https://img.shields.io/github/v/release/vacterro/saipenview?style=flat-square&include_prereleases" alt="Versión"></a>
    <a href="https://github.com/vacterro/saipenview/actions"><img src="https://img.shields.io/github/actions/workflow/status/vacterro/saipenview/ci.yml?branch=main&style=flat-square&logo=github" alt="CI"></a>
    [🤍 Apoyar al desarrollador](https://buymeacoffee.com/vacuum34)
  </p>
</div>

<br>

---

<br>

## ✨ De un vistazo

<p align="center">
  <img src="screenshots/dashboard.png" alt="Captura de pantalla del panel SAIPENVIEW" width="85%" style="border-radius: 4px; border: 1px solid #3a3020;">
  <br>
  <em>Cada proyecto SAIPEN, subagente, ticket y estado de git — todo en una sola vista.</em>
</p>

<br>

---

## 🚀 Características

<table>
<tr>
<td width="50%">

### 🔍 Detección
- **Escaner automático** de unidades locales buscando proyectos `.saipen/`
- **Rutas personalizadas** — elige carpetas o unidades completas
- **Exclusiones inteligentes** — `node_modules`, `.git`, directorios del sistema
- **Reescaneo en segundo plano** — intervalo configurable (predeterminado 300s)
- **Worktrees enlazados** — detecta worktrees de git para una fácil configuración

### 📊 Panel de control
- **Fase**, **tarea**, **siguiente acción** y **bloqueador** en tiempo real
- **Rama de Git** + indicador de estado con cambios (dirty) por proyecto
- **Filtro** por fase (Todas / Activas / Completadas / Bloqueadas / personalizada)
- **Ordenación** — Inteligente, Reciente, Más antigua, A–Z, Z–A
- **Búsqueda** — filtro por nombre/ruta + búsqueda profunda en tickets
- **Fijar** proyectos arriba, **ocultar** los irrelevantes
- **Resaltado por parpadeo** — los proyectos modificados brillan y se atenúan en 20s
- **Color según actividad (Calor)** — los proyectos inactivos se enfrían, los recientes se calientan

</td>
<td width="50%">

### 🧩 Subagentes
- **Visualización anidada** — `saiwiki`, `saihunt`, `saitranslate` sangrados bajo el padre
- **Conteos de bandeja de salida** — listos/bloqueados/borradores/revisados de un vistazo
- **Recopilación en un clic** — integra entradas listas en el proyecto principal
- **Aviso de obsolescencia** — detecta archivos de protocolo desactualizados

- **Agent Engine** - lanzar `claude-code` (u otros motores: codex, aider, gemini, cline, goose, agy, generic_cli) en un proyecto
  - **Estado en vivo** - estado de ejecución/salida, CPU, tiempo transcurrido por proyecto
  - **Consola de salida** - salida del agente en búfer (5000 líneas por defecto), entrada stdin
  - **Kill / stop all** - matar proceso y parada global
  - **Protección de instancia única** - solo una instancia de la app; el segundo lanzamiento vuelve a mostrar la ventana
### 🎮 Interacción
- **Visor de archivos** — lee y edita STATE.md, BOARD.md, LOG.md
  - Modo Fuente (editable) + Modo Lector (renderizado)
- **Tickets interactivos** — los botones Iniciar / Hecho actualizan BOARD.md en vivo
- **Acciones rápidas** — `npm run dev`, `cargo test`, etc. contextuales
- **Comandos personalizados** — botones de acción definidos por el usuario
- **Secciones colapsables** — por proyecto, persistentes
- **Barra lateral redimensionable** — arrastra para redimensionar

### ⌨️ Atajos de teclado y Ventana
- **Mostrar/Ocultar** — `Ctrl+Alt+X` (configurable)
- **Ajuste a esquinas** - `Alt+F14` alterna SI → SD → II → ID
- **Zoom** — `Ctrl+RuedaDelRatón`, `Ctrl+`+`/`-`
- **Bandeja del sistema** — minimizar a la bandeja, iniciar oculto
- **Siempre visible** — conmutador
- **Inicio automático** — inicio opcional en Windows
- **Modo sin marco** — desactiva la barra de título para una vista ultra-mínima

</td>
</tr>
</table>

<br>

---

<br>

## 🎯 Inicio rápido

<table>
<tr>
<th width="33%">🐍 Ejecutar desde el código fuente</th>
<th width="33%">📜 Scripts de inicio</th>
<th width="33%">📦 Instalación (próximamente)</th>
</tr>
<tr>
<td>

```bash
git clone https://github.com/vacterro/saipenview.git
cd saipenview
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m saipenview
```

</td>
<td>

| Script | Comportamiento |
|---|---|
| `run.vbs` | Oculto (solo bandeja), silencioso |
| `run.bat` | Lanzamiento a la bandeja; consola visible solo durante la configuración única de venv/dependencias |
Ambos crean automáticamente `.venv` e instalan dependencias.

</td>
<td>

```bash
pip install saipenview
saipenview
```
Próximamente ✨

</td>
</tr>
</table>

<br>

---

## ⌨️ Uso

| Acción | Cómo |
|---|---|
| **Mostrar / Ocultar** | `Ctrl+Alt+X` o `Alt+F15` (ambos configurables) |
| **Ajuste a esquina** | `Alt+F14` - alterna Superior-Izquierda → Superior-Derecha → Inferior-Izquierda → Inferior-Derecha |
| **Interruptor de apagado** | `Ctrl+Shift+Alt+Q` — fuerza el cierre del proceso |
| **Acercar / Alejar zoom** | `Ctrl+RuedaDelRatón` o `Ctrl` + `+` / `-` |
| **Restablecer zoom** | `Ctrl+0` |
| **Alternar barra de herramientas** | `Alt+D` — colapsar/expandir el panel de la barra de herramientas |
| **Buscar proyectos** | Escribe en el cuadro de búsqueda; marca `D` para búsqueda profunda en tickets |
| **Filtrar** | Desplegable: Todos / En vivo / Hecho / Bloqueado, o haz clic en una etiqueta de fase |
| **Ordenar** | Inteligente / Reciente / Más antigua / A–Z / Z–A |
| **Reescanear** | Haz clic en `Reescanear` o espera al temporizador en segundo plano (predeterminado 300s) |
| **Explorar carpeta** | Haz clic en `Explorar` para añadir una carpeta al conjunto de escaneo |
| **Configuración** | El botón ⚙ abre la ventana modal de configuración |
| **Wiki de ayuda** | El botón `?` abre la mini-wiki integrada |
| **Clic derecho en proyecto** | Copiar ruta raíz, filtrar por fase, abrir carpeta |
| **Doble clic en sección** | Abre el archivo conectado (STATE.md, BOARD.md, LOG.md) |
| **Arrastrar ventana** | Arrastra la barra de título (o cualquier lugar en modo sin marco) |

### Ventanas modales

| Modal | Qué hace |
|---|---|
| **Configuración** | Zoom, atajos, ajuste de escaneo, inicio automático, siempre visible, fuente, alternar parpadeo, modo predeterminado del visor de archivos, comandos personalizados, idioma, rutas de escaneo |
| **Visor de archivos** | Lee y edita STATE.md, BOARD.md, LOG.md — Modo Fuente (sin formato) o Lector (renderizado) |
| **Ayuda** | Mini-wiki completa que cubre cada característica, atajo y concepto |
| **Confirmación** | Diálogo DOM de estilo vintage (reemplaza al `confirm()` nativo) |

<br>

---

## 🧬 Protocolo SAIPEN

SAIPENVIEW es un complemento para proyectos que utilizan el **Protocolo SAIPEN** — un marco de máquina de estados que guía a los agentes de IA a través del trabajo del proyecto en fases definidas:

```
INIT → PLAN → SCOUT → BUILD → REVIEW → VERIFY → SHIP → DONE
                 ↓              ↓
            HUNT / CLEAN    VALIDATE
```

`ADD`, `MARKHUNT`, `TRANSLATE`, `PREPARE` también existen - el vocabulario completo y la tabla de transiciones viven en `saipenview/protocol.py` (`BLOCKED` es alcanzable desde la mayoría de las fases).
Cada proyecto SAIPEN almacena su estado en tres archivos canónicos:

| Archivo | Propósito |
|---|---|
| `.saipen/STATE.md` | Frontmatter legible por máquina — fase, tarea, siguiente acción, bloqueador |
| `.saipen/BOARD.md` | Tablero de tickets — secciones DOING / TODO / DONE / BLOCKED |
| `.saipen/LOG.md` | Registro cronológico de eventos — cada comando y su resultado |

Los **agentes SubSaipen** (`saiwiki`, `saihunt`, `saitranslate`) residen en `.saipen/extensions/subs/` y se comunican a través de `kitchen/OUTBOX.md` — el bus de mensajes entre agentes integrado en el protocolo. SAIPENVIEW los descubre a todos y presenta un panel de control unificado.

### Conformidad

Mostrar lo que un proyecto *dice* es solo la mitad del trabajo. Un proyecto puede verse perfectamente en la lista — una fase, una tarea, una siguiente acción — mientras se encuentra en un estado que el protocolo rechaza, y hasta que ejecutabas `tools/validate.py` manualmente no había forma de distinguirlos.

Cada fila lleva una insignia de veredicto, y el panel de detalles enumera lo que está mal:

| Veredicto | Significado |
|---|---|
| `OK` | No se encontró nada inusual en los archivos `.saipen/` de este proyecto |
| `N WARNS` | Válido, pero con desviaciones — un punto de control obsoleto, un verbo no estándar en LOG |
| `N FAILS` | Un estado que el protocolo rechaza: un `WAIT:` sin categoría, una casilla que no coincide con su sección, un `needs:` apuntando a un ticket inexistente, un `STATE.md` en UTF-16 que ninguna otra herramienta SAIPEN puede leer |

Cada hallazgo menciona la regla, el archivo y la línea, así como la cláusula de la que proviene, para que se pueda consultar en lugar de darlo por sentado.

Esta es una **segunda opinión, no un reemplazo** de `tools/validate.py`. Solo vuelve a comprobar lo que los archivos propios del proyecto pueden decidir, y califica frente a una copia de los vocabularios del protocolo — por lo que la versión de SAIPEN desde la que se leyó se muestra debajo de cada veredicto. El visor tiene permitido ir rezagado respecto al protocolo. No tiene permitido ir rezagado en silencio.

> 💡 *El nombre "SAIPENVIEW" lo dice todo — proporciona una vista (**view**) de cada proyecto **SAIPEN** en tu equipo.*

<br>

---

## ⚙️ Configuración

La configuración es portable — se almacena junto a la aplicación, no en `%APPDATA%`:

```
saipenview/_data/config.json
```

Valores por defecto clave (resumido - el diccionario completo `DEFAULTS` está en `saipenview/config.py`):

```json
{
  "hotkeys":          ["ctrl+alt+x", "alt+f15"],
  "snap_hotkey":      ["alt+f14"],
  "zoom_level":       1.0,
  "font_family":      "Verdana_m1",
  "scan_roots":       null,
  "rescan_interval":  300,
  "scan_depth":       6,
  "scan_delay_ms":    10,
  "exclude_dirs":     [],
  "auto_scan":        true,
  "show_on_launch":   true,
  "always_on_top":    true,
  "frameless":        true,
  "flash_changes":    true,
  "locale":           "en",
  "default_engine":   "claude-code",
  "file_viewer_default": "source",
  "layout_swap":      false
}
```

Establece `scan_roots: null` para autodetectar todas las unidades locales.  
Establece una lista de rutas (ej. `["V:\\", "D:\\projects"]`) para limitar el escaneo.  
`default_engine` / `engine_overrides` / `agent_output_buffer_size` controlan el Agent Engine (ver Funciones).  
Todas las opciones también se pueden configurar a través de la ventana modal de **Configuración** en la app.

<br>

---

## 🏗️ Arquitectura

```
saipenview/
├── app.py              Cableado de entrada - bandeja, hotkey, ventana, api, protección de instancia única
├── api.py              Puente pywebview orientado a JS (66 métodos públicos)
├── scanner.py          Recorrido de unidades + bucle de reescaneo en segundo plano
├── parser.py           Análisis de STATE.md / BOARD.md / LOG.md
├── textio.py           Un lector único para cada archivo .saipen/ — BOM, UTF-16, cp1251
├── protocol.py         Vocabularios cerrados del protocolo + BASELINE_VERSION
├── conformance.py      Califica un proyecto en función de dichos vocabularios
├── config.py           Carga/guardado de configuración (escrituras atómicas)
├── tray.py             Icono de bandeja del sistema pystray + menú
├── hotkey.py           Registro global de atajos de teclado (librería keyboard)
├── autostart.py        Gestión de inicio automático en el Registro de Windows
├── zone_picker.py      Superposición de ajuste a esquina Alt+F14 (tkinter)
├── events.py           Bus de eventos en proceso (EventBus)
├── guard.py            Bloqueo de instancia única + entrega de solicitud de mostrar
├── git_diff.py         Diff / commit / revert del árbol de trabajo para acciones de agentes
├── runtime.py          Agent Engine - gestor de procesos de agentes lanzados
├── watcher.py          Vigilante de archivos Watchdog sobre archivos .saipen/
├── engines/            Agent Engine - motores CLI soportados (claude-code, codex,
│                       aider, gemini, cline, goose, agy, generic_cli)
├── ui/
│   ├── window.py       Ventana pywebview — mostrar/ocultar/alternar/ajustar
│   └── static/
│       ├── index.html
│       ├── style.css   Tema vintage Win95 dorado oscuro
│       └── app.js      Lógica del frontend (~3300 líneas)
├── assets/
│   └── tray_icon.png
├── screenshots/        Capturas de pantalla del README
└── _data/              Configuración de tiempo de ejecución + caché (gitignored)
```

### Principios de diseño

- **Proceso único** — sin IPC en segundo plano, sin servidor independiente; un solo proceso de Python alberga tanto la ventana WebView2 como el bucle de escaneo en un `ThreadPoolExecutor`
- **Escrituras atómicas** — cada escritura de archivo utiliza archivo temporal + `os.replace`; un bloqueo nunca puede truncar la configuración o la caché
- **Lectura segura de datos obsoletos** — la comprobación de la interfaz cada 5s llama a `refresh_known()` (solo re-lee archivos `.saipen/`, sin recorrer directorios). Las ediciones en STATE.md aparecen en segundos sin activar un escaneo completo de la unidad
- **Sin transiciones CSS** — todos los efectos visuales (parpadeo, calor, estado al pasar el ratón) son recalculados con `hexBlend` mediante JavaScript, siguiendo estrictamente la restricción de cero animaciones del tema vintage
- **Tema vintage** — superficies marrón oscuro, texto/detalles dorados, bordes biselados en 3D, cero suavizado de fuentes (anti-aliasing), fuente Verdana_m1

<br>

---

## 🧪 Desarrollo

```bash
# Clonar e ingresar
git clone https://github.com/vacterro/saipenview.git
cd saipenview

# Crear venv e instalar
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# Ejecutar
python -m saipenview
```

Para obtener información detallada sobre la configuración, convenciones de código y el flujo de trabajo de solicitudes de extracción (PR), consulta [CONTRIBUTING.md](CONTRIBUTING.md).

### Requisitos

- **Windows 10 / 11** — WebView2 runtime (preinstalado en Win11, se instala automáticamente en Win10)
- **Python 3.10+**
- Dependencias: `pystray`, `keyboard`, `pywebview`, `Pillow`, `watchdog`, `psutil`

<br>

---

## 📄 Licencia

MIT — consulta [LICENSE](LICENSE).

<br>

---

<div align="center">
  <sub>Construido con 🐍 Python • 🖼️ pywebview • 🎨 Estética vintage Win95</sub>

<br>

---

## 📸 Más capturas de pantalla

<p align="center">
  <img src="screenshots/detail-pane.png" alt="Panel de detalles de SAIPENVIEW" width="85%" style="border-radius: 4px; border: 1px solid #3a3020;">
  <br>
  <em>Panel de detalles con tickets, subagentes y visor de archivos.</em>
</p>

<br>

</div>
