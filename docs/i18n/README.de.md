<div align="right">
  🌍 <a href="../../README.md">EN</a> | <a href="README.ar.md">AR</a> | <a href="README.bg.md">BG</a> | <a href="README.cs.md">CS</a> | <a href="README.da.md">DA</a> | <strong>DE</strong> | <a href="README.ee.md">EE</a> | <a href="README.el.md">EL</a> | <a href="README.es.md">ES</a> | <a href="README.fi.md">FI</a> | <a href="README.fr.md">FR</a> | <a href="README.he.md">HE</a> | <a href="README.hi.md">HI</a> | <a href="README.hr.md">HR</a> | <a href="README.hu.md">HU</a> | <a href="README.id.md">ID</a> | <a href="README.it.md">IT</a> | <a href="README.ja.md">JA</a> | <a href="README.ko.md">KO</a> | <a href="README.nl.md">NL</a> | <a href="README.no.md">NO</a> | <a href="README.pl.md">PL</a> | <a href="README.pt.md">PT</a> | <a href="README.ro.md">RO</a> | <a href="README.ru.md">RU</a> | <a href="README.sk.md">SK</a> | <a href="README.sv.md">SV</a> | <a href="README.th.md">TH</a> | <a href="README.tr.md">TR</a> | <a href="README.uk.md">UK</a> | <a href="README.vi.md">VI</a> | <a href="README.zh.md">ZH</a> | <a href="README.zh-CN.md">ZH-CN</a> | <a href="README.ded.md">ДЕД</a>
</div>

<div align="center">
  <img src="../../screenshots/saipen_icon.png" alt="SAIPENVIEW" width="120" height="120">
  <h1 align="center">SAIPENVIEW</h1>
  <p align="center">
    <strong>Desktop-Tray-Viewer für jedes SAIPEN-Projekt auf Ihrem Computer</strong>
    <br>
    Automatische Erkennung von <code>.saipen/</code>-Projekten auf lokalen Laufwerken — Live-Phase, Aufgabe, Blocker, Git-Status, Tickets und Sub-Agenten.
    <br>
    Ein Dashboard im düster-goldenen Win95-Vintage-Stil.
  </p>
  <p>
    <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.10%2B-blue?style=flat-square&logo=python&logoColor=white" alt="Python"></a>
    <a href="../../LICENSE"><img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="Lizenz"></a>
    <a href="https://github.com/vacterro/saipenview"><img src="https://img.shields.io/badge/platform-Windows-orange?style=flat-square&logo=windows&logoColor=white" alt="Plattform"></a>
    <a href="https://github.com/vacterro/saipenview/releases"><img src="https://img.shields.io/github/v/release/vacterro/saipenview?style=flat-square&include_prereleases" alt="Release"></a>
    <a href="https://github.com/vacterro/saipenview/actions"><img src="https://img.shields.io/github/actions/workflow/status/vacterro/saipenview/ci.yml?branch=main&style=flat-square&logo=github" alt="CI"></a>
  </p>
</div>

<br>

---

## 🚀 Funktionen

<table>
<tr>
<td width="50%">

### 🔍 Erkennung
- **Automatischer Scan** lokaler Laufwerke nach `.saipen/`-Projekten
- **Benutzerdefinierte Stammverzeichnisse** — Ordner oder ganze Laufwerke auswählen
- **Intelligente Ausschlüsse** — `node_modules`, `.git`, Systemverzeichnisse
- **Hintergrund-Neuscan** — konfigurierbares Intervall (Standard: 300s)
- **Verknüpfte Worktrees** — erkennt Git-Worktrees für einfache Einrichtung

### 📊 Dashboard
- Live-**Phase**, **Aufgabe**, **nächste Aktion**, **Blocker**
- **Git-Branch** + Anzeige des Dirty-Status pro Projekt
- **Filtern** nach Phase (Alle / Aktiv / Erledigt / Blockiert / benutzerdefiniert)
- **Sortieren** — Intelligent, Neueste, Älteste, A–Z, Z–A
- **Suchen** — Name/Pfad-Filter + Tiefensuche in Tickets
- Projekte oben **anheften**, irrelevante **ausblenden**
- **Blink-Hervorhebung** — geänderte Projekte leuchten auf & verblassen über 20s
- **Wärme-Farbgebung** — inaktive Projekte kühlen ab, frische Projekte werden warm

</td>
<td width="50%">

### 🧩 Sub-Agenten
- **Verschachtelte Anzeige** — `saiwiki`, `saihunt`, `saitranslate` unter dem Elternprojekt eingerückt
- **Postausgang-Anzahl** — bereit/blockiert/Entwurf/überprüft auf einen Blick
- **Ein-Klick-Einsammeln** — bereitstehende Einträge in das Hauptprojekt zusammenführen
- **Veraltet-Warnung** — erkennt veraltete Protokolldateien

- **Agent Engine** - Start von `claude-code` (oder anderen Engines: codex, aider, gemini, cline, goose, agy, generic_cli) in einem Projekt
  - **Live-Status** - Ausfuhren/Exit-Zustand, CPU, verstrichene Zeit pro Projekt
  - **Ausgabekonsole** - gepufferte Agent-Ausgabe (Standard 5000 Zeilen), stdin-Eingabe
  - **Kill / stop all** - Prozess beenden und globaler Stopp
  - **Einzelinstanz-Schutz** - nur eine App-Instanz; zweiter Start zeigt das Fenster erneut
### 🎮 Interaktion
- **Dateibetrachter** — lesen & bearbeiten von STATE.md, BOARD.md, LOG.md
  - Quellcode-Modus (bearbeitbar) + Lese-Modus (gerendert)
- **Interaktive Tickets** — Start / Erledigt-Schaltflächen aktualisieren BOARD.md live
- **Schnellaktionen** — kontextbezogene Befehle wie `npm run dev`, `cargo test` etc.
- **Benutzerdefinierte Befehle** — eigene Aktions-Schaltflächen
- **Einklappbare Abschnitte** — pro Projekt, dauerhaft gespeichert
- **Größenverstellbare Seitenleiste** — durch Ziehen anpassen

### ⌨️ Tastenkombinationen & Fenster
- **Anzeigen/Ausblenden** — `Strg+Alt+X` (konfigurierbar)
- **Ecken-Einrasten** - `Ctrl+Q` wechselt OL → OR → UL → UR
- **Zoom** — `Strg+Mausrad`, `Strg+`+`/`-`
- **System-Tray** — in den Tray minimieren, versteckt starten
- **Immer im Vordergrund**-Umschalter
- **Autostart** — optionaler Windows-Systemstart
- **Rahmenloser Modus** — Titelleiste für ultraminimalistische Ansicht ausblenden

</td>
</tr>
</table>

<br>

---

<br>

## 🎯 Schnellstart

<table>
<tr>
<th width="33%">🐍 Aus Quellcode ausführen</th>
<th width="33%">📜 Start-Skripte</th>
<th width="33%">📦 Installieren (Zukunft)</th>
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

| Skript | Verhalten |
|---|---|
| `run.vbs` | Versteckt (nur Tray), still |
| `run.bat` | Start in den Tray; Konsole nur beim einmaligen Einrichten von venv/Abhangigkeiten sichtbar |
Beide erstellen `.venv` automatisch & installieren Abhängigkeiten.

</td>
<td>

```bash
pip install saipenview
saipenview
```
Demnächst verfügbar ✨

</td>
</tr>
</table>

<br>

---

## ⌨️ Bedienung

| Aktion | Wie |
|---|---|
| **Anzeigen / Ausblenden** | `Strg+Alt+X` oder `Alt+F15` (beide konfigurierbar) |
| **Ecke einrasten** | `Ctrl+Q` - wechselt Oben-Links → Oben-Rechts → Unten-Links → Unten-Rechts |
| **Not-Aus (Kill Switch)** | `Strg+Umschalt+Alt+Q` — Prozess sofort beenden |
| **Vergrößern / Verkleinern** | `Strg+Mausrad` oder `Strg` + `+` / `-` |
| **Zoom zurücksetzen** | `Strg+0` |
| **Werkzeugleiste umschalten** | `Alt+D` — Werkzeugleiste ein-/ausklappen |
| **Projekte suchen** | Im Suchfeld tippen; `D` aktivieren für Ticket-Tiefensuche |
| **Filtern** | Dropdown: Alle / Aktiv / Erledigt / Blockiert, oder auf eine Phasen-Pille klicken |
| **Sortieren** | Intelligent / Neueste / Älteste / A–Z / Z–A |
| **Neuscan** | Auf `Neuscan` klicken oder auf Hintergrund-Timer warten (Standard: 300s) |
| **Ordner durchsuchen** | Auf `Durchsuchen` klicken, um einen Ordner zum Scan-Set hinzuzufügen |
| **Einstellungen** | ⚙-Schaltfläche öffnet das Einstellungsfenster |
| **Hilfe-Wiki** | `?`-Schaltfläche öffnet das integrierte Mini-Wiki |
| **Rechtsklick auf Projekt** | Stamm-Pfad kopieren, nach Phase filtern, Ordner öffnen |
| **Doppelklick auf Abschnitt** | Öffnet die verbundene Datei (STATE.md, BOARD.md, LOG.md) |
| **Fenster ziehen** | Titelleiste ziehen (oder überall im rahmenlosen Modus) |

### Dialogfenster (Modals)

| Dialog | Funktion |
|---|---|
| **Einstellungen** | Zoom, Tastenkombinationen, Scan-Feineinstellung, Autostart, Immer im Vordergrund, Schriftart, Blink-Umschalter, Standard-Dateibetrachter, benutzerdefinierte Befehle, Sprache, Scan-Pfade |
| **Dateibetrachter** | Lesen & Bearbeiten von STATE.md, BOARD.md, LOG.md — Quellcode- (roh) oder Lese-Modus (gerendert) |
| **Hilfe** | Umfassendes Mini-Wiki zu allen Funktionen, Tastenkombinationen und Konzepten |
| **Bestätigung** | Vintage-gestalteter DOM-Dialog (ersetzt natives `confirm()`) |

<br>

---

## 🧬 SAIPEN-Protokoll

SAIPENVIEW ist ein Begleiter für Projekte, die das **SAIPEN-Protokoll** verwenden — ein Zustandsautomaten-Framework, das KI-Agenten in definierten Phasen durch die Projektarbeit führt:

```
INIT → PLAN → SCOUT → BUILD → REVIEW → VERIFY → SHIP → DONE
                 ↓              ↓
            HUNT / CLEAN    VALIDATE
```

`ADD`, `MARKHUNT`, `TRANSLATE`, `PREPARE` existieren ebenfalls - das vollstandige Vokabular und die Ubergangstabelle befinden sich in `saipenview/protocol.py` (`BLOCKED` ist aus den meisten Phasen erreichbar).
Jedes SAIPEN-Projekt speichert seinen Zustand in drei kanonischen Dateien:

| Datei | Zweck |
|---|---|
| `.saipen/STATE.md` | Maschinenlesbarer Header (Frontmatter) — Phase, Aufgabe, nächste Aktion, Blocker |
| `.saipen/BOARD.md` | Ticket-Board — Abschnitte DOING / TODO / DONE / BLOCKED |
| `.saipen/LOG.md` | Chronologisches Ereignisprotokoll — jeder Befehl und sein Ergebnis |

**SubSaipen-Agenten** (`saiwiki`, `saihunt`, `saitranslate`) befinden sich in `.saipen/extensions/subs/` und kommunizieren über `kitchen/OUTBOX.md` — den integrierten agentenübergreifenden Nachrichtenbus des Protokolls. SAIPENVIEW erkennt sie alle und stellt ein einheitliches Dashboard dar.

### Konformität

Zu zeigen, was ein Projekt *sagt*, ist nur die halbe Miete. Ein Projekt kann in der Liste perfekt aussehen — eine Phase, eine Aufgabe, eine nächste Aktion —, während es sich in einem Zustand befindet, den das Protokoll ablehnt. Bis man `tools/validate.py` manuell ausführt, gab es keine Möglichkeit, diese beiden Fälle zu unterscheiden.

Jede Zeile trägt ein Konformitätsabzeichen (Verdict Badge), und das Detailmenü listet auf, was nicht stimmt:

| Ergebnis | Bedeutung |
|---|---|
| `OK` | Keine Fehler in den eigenen `.saipen/`-Dateien dieses Projekts gefunden |
| `N WARNS` | Erlaubt, aber Abweichungen vorhanden — ein veralteter Kontrollpunkt, ein nicht-standardmäßiges LOG-Verb |
| `N FAILS` | Ein Zustand, den das Protokoll ablehnt: ein `WAIT:` ohne Kategorie, ein Kontrollkästchen, das nicht mit seinem Abschnitt übereinstimmt, ein `needs:`, das auf ein nicht existierendes Ticket verweist, eine UTF-16-`STATE.md`, die kein anderes SAIPEN-Tool lesen kann |

Jeder Befund nennt die Regel, die Datei und Zeile sowie die Klausel, aus der er stammt, sodass er nachgeschlagen werden kann, anstatt ihn einfach hinzunehmen.

Dies ist eine **zweite Meinung, kein Ersatz** für `tools/validate.py`. Es prüft nur das erneut, was die Dateien eines Projekts selbst entscheiden können, und es bewertet anhand einer Kopie des Protokoll-Vokabulars — daher wird die SAIPEN-Version, von der gelesen wurde, unter jedem Ergebnis gedruckt. Der Viewer darf dem Protokoll hinterherhinken. Er darf ihm nur nicht stillschweigend hinterherhinken.

> 💡 *Der Name "SAIPENVIEW" sagt alles — er bietet eine **Ansicht** (View) in jedes **SAIPEN**-Projekt auf Ihrem Computer.*

<br>

---

## ⚙️ Konfiguration

Die Konfiguration ist übertragbar — sie wird neben der Anwendung gespeichert, nicht in `%APPDATA%`:

```
saipenview/_data/config.json
```

Wichtige Standardwerte (gekurzt - das vollstandige `DEFAULTS`-Worterbuch befindet sich in `saipenview/config.py`):

```json
{
  "hotkeys":          ["ctrl+alt+x", "alt+f15"],
  "snap_hotkey":      ["ctrl+q"],
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

Setzen Sie `scan_roots: null`, um alle lokalen Laufwerke automatisch zu erkennen.  
Setzen Sie eine Liste von Pfaden (z. B. `["V:\\", "D:\\projects"]`), um den Scan einzuschränken.  
`default_engine` / `engine_overrides` / `agent_output_buffer_size` steuern den Agent Engine (siehe Funktionen).  
Alle Einstellungen können auch über das **Einstellungen**-Dialogfenster in der App konfiguriert werden.

<br>

---

## 🏗️ Architektur

```
saipenview/
├── app.py              Einstiegsverdrahtung - Tray, Hotkey, Fenster, API, Einzelinstanz-Schutz
├── api.py              JS-seitige pywebview-Brucke (66 offentliche Methoden)
├── scanner.py          Laufwerks-Durchlauf + Hintergrund-Neuscan-Schleife
├── parser.py           Parsing von STATE.md / BOARD.md / LOG.md
├── textio.py           Ein Reader für jede .saipen/-Datei — BOM, UTF-16, cp1251
├── protocol.py         Geschlossene Vokabulare des Protokolls + BASELINE_VERSION
├── conformance.py      Bewertet ein Projekt anhand dieser Vokabulare
├── config.py           Laden/Speichern von Einstellungen (atomare Schreibvorgänge)
├── tray.py             pystray System-Tray-Symbol + Menü
├── hotkey.py           Globale Hotkey-Registrierung (keyboard-Bibliothek)
├── autostart.py        Windows-Registrierungs-Autostart-Verwaltung
├── zone_picker.py      Ctrl+Q Ecken-Einrast-Overlay (tkinter)
├── events.py           Prozessinterner Ereignisbus (EventBus)
├── guard.py            Einzelinstanz-Sperre + Anzeige-Anfrage-Ubergabe
├── git_diff.py         Arbeitsbaum-Diff / Commit / Revert fur Agent-Aktionen
├── runtime.py          Agent Engine - Prozessmanager fur gestartete Agenten
├── watcher.py          Watchdog-Dateiüberwachung auf .saipen/-Dateien
├── engines/            Agent Engine - unterstutzte CLI-Engines (claude-code, codex,
│                       aider, gemini, cline, goose, agy, generic_cli)
├── ui/
│   ├── window.py       pywebview-Fenster — anzeigen/ausblenden/umschalten/einrasten
│   └── static/
│       ├── index.html
│       ├── style.css   Düstres, goldenes Win95-Vintage-Theme
│       └── app.js      Frontend-Logik (~3300 Zeilen)
├── assets/
│   └── tray_icon.png
├── screenshots/        README-Screenshots
└── _data/              Laufzeit-Konfiguration + Cache (in .gitignore)
```

### Design-Prinzipien

- **Einzelprozess** — keine Hintergrund-IPC, kein separater Server; ein einziger Python-Prozess hostet sowohl das WebView2-Fenster als auch die Scan-Schleife in einem `ThreadPoolExecutor`
- **Atomare Schreibvorgänge** — jeder Schreibvorgang nutzt eine temporäre Datei + `os.replace`; ein Absturz kann Konfiguration oder Cache niemals beschädigen
- **Sicher vor veralteten Daten** — die 5s UI-Abfrage ruft `refresh_known()` auf (liest nur `.saipen/`-Dateien neu, kein Laufwerksdurchlauf). Änderungen an STATE.md erscheinen innerhalb von Sekunden ohne vollständigen Laufwerksscan
- **Keine CSS-Übergänge** — alle visuellen Effekte (Blinken, Wärme, Hover) sind JavaScript-gesteuerte `hexBlend`-Neuberechnungen, die strikt der Vorgabe des Vintage-Themes ohne Animationen folgen
- **Vintage-Theme** — dunkle braune Oberflächen, goldene Texte/Akzente, 3D-abgeschrägte Ränder, kein Anti-Aliasing, Schriftart Verdana_m1

<br>

---

## 🧪 Entwicklung

```bash
# Klonen & Verzeichnis betreten
git clone https://github.com/vacterro/saipenview.git
cd saipenview

# venv erstellen & installieren
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# Ausführen
python -m saipenview
```

Detaillierte Informationen zu Einrichtung, Konventionen und PR-Workflow finden Sie unter [CONTRIBUTING.md](../../CONTRIBUTING.md).

### Voraussetzungen

- **Windows 10 / 11** — WebView2-Laufzeitumgebung (auf Win11 vorinstalliert, wird auf Win10 auto-installiert)
- **Python 3.10+**
- Abhängigkeiten: `pystray`, `keyboard`, `pywebview`, `Pillow`, `watchdog`, `psutil`

<br>

---

## 📄 Lizenz

MIT — siehe [LICENSE](../../LICENSE).

<br>

---

<div align="center">
  <sub>Erstellt mit 🐍 Python • 🖼️ pywebview • 🎨 Vintage Win95-Ästhetik</sub>

<br>

---

## 📸 Weitere Screenshots

<p align="center">
  <img src="../../screenshots/detail-pane.png" alt="SAIPENVIEW Detailbereich" width="85%" style="border-radius: 4px; border: 1px solid #3a3020;">
  <br>
  <em>Detailbereich mit Tickets, Sub-Agenten und Dateibetrachter.</em>
</p>

<br>

</div>
