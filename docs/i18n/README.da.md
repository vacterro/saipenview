<div align="right">
  🌍 <a href="../../README.md">EN</a> | <a href="README.ar.md">AR</a> | <a href="README.bg.md">BG</a> | <a href="README.cs.md">CS</a> | <strong>DA</strong> | <a href="README.de.md">DE</a> | <a href="README.ee.md">EE</a> | <a href="README.el.md">EL</a> | <a href="README.es.md">ES</a> | <a href="README.fi.md">FI</a> | <a href="README.fr.md">FR</a> | <a href="README.he.md">HE</a> | <a href="README.hi.md">HI</a> | <a href="README.hr.md">HR</a> | <a href="README.hu.md">HU</a> | <a href="README.id.md">ID</a> | <a href="README.it.md">IT</a> | <a href="README.ja.md">JA</a> | <a href="README.ko.md">KO</a> | <a href="README.nl.md">NL</a> | <a href="README.no.md">NO</a> | <a href="README.pl.md">PL</a> | <a href="README.pt.md">PT</a> | <a href="README.ro.md">RO</a> | <a href="README.ru.md">RU</a> | <a href="README.sk.md">SK</a> | <a href="README.sv.md">SV</a> | <a href="README.th.md">TH</a> | <a href="README.tr.md">TR</a> | <a href="README.uk.md">UK</a> | <a href="README.vi.md">VI</a> | <a href="README.zh.md">ZH</a> | <a href="README.zh-CN.md">ZH-CN</a> | <a href="README.ded.md">ДЕД</a>
</div>

<div align="center">
  <img src="../../screenshots/saipen_icon.png" alt="SAIPENVIEW" width="120" height="120">
  <h1 align="center">SAIPENVIEW</h1>
  <p align="center">
    <strong>Skrivebords-systembakkefremviser til alle SAIPEN-projekter på din maskine</strong>
    <br>
    Automatisk registrering af <code>.saipen/</code>-projekter på tværs af lokale drev — live fase, opgave, blokering, git-status, tickets og underagenter.
    <br>
    Ét mørkeguldfarvet instrumentbræt med vintage Win95-tema.
  </p>
  <p>
    <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.10%2B-blue?style=flat-square&logo=python&logoColor=white" alt="Python"></a>
    <a href="../../LICENSE"><img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="License"></a>
    <a href="https://github.com/vacterro/saipenview"><img src="https://img.shields.io/badge/platform-Windows-orange?style=flat-square&logo=windows&logoColor=white" alt="Platform"></a>
    <a href="https://github.com/vacterro/saipenview/releases"><img src="https://img.shields.io/github/v/release/vacterro/saipenview?style=flat-square&include_prereleases" alt="Release"></a>
    <a href="https://github.com/vacterro/saipenview/actions"><img src="https://img.shields.io/github/actions/workflow/status/vacterro/saipenview/ci.yml?branch=main&style=flat-square&logo=github" alt="CI"></a>
  </p>
</div>

<br>

---

## 🚀 Funktioner

<table>
<tr>
<td width="50%">

### 🔍 Registrering
- **Automatisk scanning** af lokale drev efter `.saipen/`-projekter
- **Tilpassede rødder** — vælg mapper eller hele drev
- **Smart ekskludering** — `node_modules`, `.git`, systemmapper
- **Baggrundsscanning** — konfigurerbart interval (standard 300s)
- **Linkede worktrees** — registrerer git-worktrees for nem opsætning

### 📊 Instrumentbræt
- Live **fase**, **opgave**, **næste handling**, **blokering**
- **Git-gren** + ændringsindikator pr. projekt
- **Filtrer** efter fase (Alle / Live / Færdig / Fastlåst / tilpasset)
- **Sortering** — Smart, Seneste, Ældste, A–Z, Z–A
- **Søgning** — navn/rod-filter + dyb ticket-søgning
- **Fastgør** projekter i toppen, **skjul** irrelevante
- **Blinkende fremhævning** — ændrede projekter gløder og fader over 20s
- **Varme-farvning** — forældede projekter køler af, friske projekter varmes op

</td>
<td width="50%">

### 🧩 Underagenter
- **Indrykket visning** — `saiwiki`, `saihunt`, `saitranslate` indrykket under overordnet
- **Udindbakke-antal** — klar/blokeret/udkast/gennemset ved et øjekast
- **Et-klik samling** — fold klar-elementer ind i hovedprojektet
- **Advarsel om forældelse** — registrerer forældede protokolfiler

- **Agent Engine** - start `claude-code` (eller andre motorer: codex, aider, gemini, cline, goose, agy, generic_cli) i et projekt
  - **Live status** - korende/afsluttet tilstand, CPU, forlobet tid pr. projekt
  - **Udgangskonsol** - bufferet agentudgang (standard 5000 linjer), stdin-input
  - **Kill / stop all** - dræb proces og global stop
  - **Enkeltinstans-beskyttelse** - kun én app-forekomst; anden start viser vinduet igen
### 🎮 Interaktion
- **Filviser** — læs & rediger STATE.md, BOARD.md, LOG.md
  - Kildetilstand (redigerbar) + Læsetilstand (renderet)
- **Interaktive tickets** — Start / Færdig-knapper opdaterer BOARD.md live
- **Hurtige handlinger** — kontekstuelle `npm run dev`, `cargo test` osv.
- **Tilpassede kommandoer** — brugerdefinerede handlingsknapper
- **Sammenklappelige sektioner** — pr. projekt, gemt
- **Justerbart sidepanel** — træk for at ændre størrelse

### ⌨️ Genvejstaster & Vindue
- **Vis/Skjul** — `Ctrl+Alt+X` (konfigurerbar)
- **Fastgør til hjørner** - `Ctrl+Q` skifter OV → OH → NV → NH
- **Zoom** — `Ctrl+Musehjul`, `Ctrl+`+`/`-`
- **Systembakke** — minimer til bakke, start skjult
- **Altid øverst**-skift
- **Automatisk start** — valgfri Windows-opstart
- **Rammeløs tilstand** — slå titellinje fra for ultra-minimalistisk visning

</td>
</tr>
</table>

<br>

---

<br>

## 🎯 Hurtig start

<table>
<tr>
<th width="33%">🐍 Kør fra kildekode</th>
<th width="33%">📜 Start-scripts</th>
<th width="33%">📦 Installation (fremtidig)</th>
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

| Script | Opførsel |
|---|---|
| `run.vbs` | Skjult (kun bakke), stille |
| `run.bat` | Start i bakken; konsollen ses kun under engangsopsætning af venv/afhængigheder |
Begge opretter automatisk `.venv` og installerer afhængigheder.

</td>
<td>

```bash
pip install saipenview
saipenview
```
Kommer snart ✨

</td>
</tr>
</table>

<br>

---

## ⌨️ Anvendelse

| Handling | Hvordan |
|---|---|
| **Vis / Skjul** | `Ctrl+Alt+X` eller `Alt+F15` (begge kan konfigureres) |
| **Fastgør til hjørne** | `Ctrl+Q` - skifter Øverst-venstre → Øverst-højre → Nederst-venstre → Nederst-højre |
| **Nødstop (Kill switch)** | `Ctrl+Shift+Alt+Q` — tving afslutning af processen |
| **Zoom ind / ud** | `Ctrl+Musehjul` eller `Ctrl` + `+` / `-` |
| **Nulstil zoom** | `Ctrl+0` |
| **Skift værktøjslinje** | `Alt+D` — fold værktøjslinjepanelet sammen/ud |
| **Søg projekter** | Skriv i søgefeltet; afkryds `D` for dyb ticket-søgning |
| **Filtrer** | Rullemenu: Alle / Live / Færdig / Fastlåst, eller klik på en fase-knap |
| **Sorter** | Smart / Seneste / Ældste / A–Z / Z–A |
| **Genindlæs (Rescan)** | Klik på `Rescan` eller vent på baggrundstimeren (standard 300s) |
| **Gennemse mappe** | Klik på `Browse` for at tilføje en mappe til scanningssættet |
| **Indstillinger** | ⚙-knap åbner indstillingsvinduet |
| **Hjælp-wiki** | `?`-knap åbner den indbyggede mini-wiki |
| **Højreklik på projekt** | Kopier sti til rod, filtrer efter fase, åbn mappe |
| **Dobbeltklik på sektion** | Åbner den tilknyttede fil (STATE.md, BOARD.md, LOG.md) |
| **Træk vindue** | Træk titellinjen (eller hvor som helst i rammeløs tilstand) |

### Modaler

| Modal | Hvad det gør |
|---|---|
| **Indstillinger** | Zoom, genvejstaster, scanningsjustering, autostart, altid øverst, skrifttype, blink-skift, standard filviser, tilpassede kommandoer, sprog, scanningsrødder |
| **Filviser** | Læs & rediger STATE.md, BOARD.md, LOG.md — Kilde (rå) eller Læse (renderet) tilstand |
| **Hjælp** | Omfattende mini-wiki, der dækker enhver funktion, genvej og koncept |
| **Bekræft** | Vintage-styled DOM-dialogboks (erstatter den indbyggede `confirm()`) |

<br>

---

## 🧬 SAIPEN-protokol

SAIPENVIEW er en ledsager til projekter, der bruger **SAIPEN-protokollen** — en tilstandsmaskine-ramme, der guider AI-agenter gennem projektarbejde i definerede faser:

```
INIT → PLAN → SCOUT → BUILD → REVIEW → VERIFY → SHIP → DONE
                 ↓              ↓
            HUNT / CLEAN    VALIDATE
```

`ADD`, `MARKHUNT`, `TRANSLATE`, `PREPARE` findes også - det fulde ordforråd og overgangstabellen ligger i `saipenview/protocol.py` (`BLOCKED` kan nås fra de fleste faser).
Hvert SAIPEN-projekt gemmer sin tilstand i tre kanoniske filer:

| Fil | Formål |
|---|---|
| `.saipen/STATE.md` | Maskinlæsbar frontmatter — fase, opgave, næste handling, blokering |
| `.saipen/BOARD.md` | Ticket-tavle — DOING / TODO / DONE / BLOCKED sektioner |
| `.saipen/LOG.md` | Kronologisk hændelseslog — enhver kommando og dens resultat |

**SubSaipen-agenter** (`saiwiki`, `saihunt`, `saitranslate`) findes i `.saipen/extensions/subs/` og kommunikerer via `kitchen/OUTBOX.md` — protokollens indbyggede beskedbus på tværs af agenter. SAIPENVIEW opdager dem alle og gengiver et samlet instrumentbræt.

### Overensstemmelse (Conformance)

At vise, hvad et projekt *siger*, er kun den halve sandhed. Et projekt kan se helt korrekt ud i listen — en fase, en opgave, en næste handling — mens det befinder sig i en tilstand, som protokollen afviser, og indtil du kørte `tools/validate.py` manuelt, var der ingen måde at skelne de to fra hinanden.

Hver række har et vurderingsmærke, og detaljepanelet lister, hvad der er galt:

| Vurdering | Betydning |
|---|---|
| `OK` | Intet fundet i dette projekts egne `.saipen/`-filer |
| `N WARNS` | Gyldigt, men afvigende — et forældet kontrolpunkt, et ustandardiseret LOG-verbum |
| `N FAILS` | En tilstand, som protokollen afviser: et `WAIT:` uden kategori, et afkrydsningsfelt, der er uenig med sin sektion, et `needs:`, der peger på en ticket, der ikke eksisterer, en UTF-16 `STATE.md`, som intet andet SAIPEN-værktøj kan læse |

Hvert fund angiver reglen, filen og linjen samt den paragraf, det stammer fra, så det kan slås op frem for blot at blive antaget.

Dette er en **ekstra vurdering, ikke en erstatning** for `tools/validate.py`. Den genkontrollerer kun, hvad et projekts egne filer kan afgøre, og den vurderer i forhold til en kopi af protokollens ordforråd — så den SAIPEN-version, den blev læst fra, udskrives under hver vurdering. Fremviseren må gerne halte efter protokollen. Den må bare ikke gøre det i stilhed.

> 💡 *Navnet "SAIPENVIEW" siger det hele — det giver et **kig (view)** ind i hvert eneste **SAIPEN**-projekt på din maskine.*

<br>

---

## ⚙️ Konfiguration

Konfigurationen er portabel — gemt ved siden af appen, ikke i `%APPDATA%`:

```
saipenview/_data/config.json
```

Vigtigste standardværdier (forkortet - den fulde `DEFAULTS`-ordbog ligger i `saipenview/config.py`):

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

Sæt `scan_roots: null` for automatisk at opdage alle lokale drev.  
Sæt til en liste over stier (f.eks. `["V:\\", "D:\\projects"]`) for at begrænse scanningen.  
`default_engine` / `engine_overrides` / `agent_output_buffer_size` styrer Agent Engine (se Funktioner).  
Alle indstillinger kan også konfigureres via **Indstillinger**-modalen i appen.

<br>

---

## 🏗️ Arkitektur

```
saipenview/
├── app.py              Indgangsforbindelse - bakke, hotkey, vindue, api, enkeltinstans-beskyttelse
├── api.py              JS-vendt pywebview-bro (66 offentlige metoder)
├── scanner.py          Gennemgang af drev + baggrundsscanningsloop
├── parser.py           Tolkning af STATE.md / BOARD.md / LOG.md
├── textio.py           En læser til enhver .saipen/-fil — BOM, UTF-16, cp1251
├── protocol.py         Protokollens lukkede ordforråd + BASELINE_VERSION
├── conformance.py      Vurderer et projekt mod disse ordforråd
├── config.py           Indlæsning/gemning af indstillinger (atomare skrivninger)
├── tray.py             pystray-systembakkeikon + menu
├── hotkey.py           Global registrering af genvejstaster (keyboard lib)
├── autostart.py        Håndtering af Windows Registreringsdatabase autostart
├── zone_picker.py      Ctrl+Q hjørne-fastgørelsesoverlejring (tkinter)
├── events.py           In-process hændelsesbus (EventBus)
├── guard.py            Enkeltinstans-lås + visning-anmodning overlevering
├── git_diff.py         Arbejdstræets diff / commit / revert for agenthandlinger
├── runtime.py          Agent Engine - processtyring for startede agenter
├── watcher.py          Watchdog-filovervåger på .saipen/-filer
├── engines/            Agent Engine - understøttede CLI-motorer (claude-code, codex,
│                       aider, gemini, cline, goose, agy, generic_cli)
├── ui/
│   ├── window.py       pywebview-vindue — vis/skjul/skift/fastgør
│   └── static/
│       ├── index.html
│       ├── style.css   Vintage mørkeguld Win95-tema
│       └── app.js      Frontend-logik (~3300 linjer)
├── assets/
│   └── tray_icon.png
├── screenshots/        README-skærmbilleder
└── _data/              Kørselstidskonfiguration + cache (gitignored)
```

### Designprincipper

- **Enkelt proces** — ingen baggrunds-IPC, ingen separat server; én Python-proces er vært for både WebView2-vinduet og scanningsloopet i en `ThreadPoolExecutor`
- **Atomare skrivninger** — enhver filskrivning bruger midlertidig fil + `os.replace`; et nedbrud kan aldrig afskære konfiguration eller cache
- **Sikker mod forældede læsninger** — UI-forespørgslen hvert 5. sekund kalder `refresh_known()` (genlæser kun `.saipen/`-filer, ingen mappe-gennemgang). Redigeringer i STATE.md vises inden for få sekunder uden at udløse en fuld drevscanning
- **Ingen CSS-overgange** — alle visuelle effekter (blink, varme, hover) er JavaScript-drevne `hexBlend`-genberegninger, der strengt følger vintage-temats begrænsning om nul animationer
- **Vintage-tema** — mørkebrune overflader, gylden tekst/accenter, 3D-affasede kanter, nul antialiasing, Verdana_m1-skrifttype

<br>

---

## 🧪 Udvikling

```bash
# Clone & enter
git clone https://github.com/vacterro/saipenview.git
cd saipenview

# Create venv & install
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# Run
python -m saipenview
```

For detaljeret opsætning, kodningskonventioner og PR-arbejdsgang, se [CONTRIBUTING.md](../../CONTRIBUTING.md).

### Krav

- **Windows 10 / 11** — WebView2 kørselstidsmiljø (forudinstalleret på Win11, installeres automatisk på Win10)
- **Python 3.10+**
- Afhængigheder: `pystray`, `keyboard`, `pywebview`, `Pillow`, `watchdog`, `psutil`

<br>

---

## 📄 Licens

MIT — se [LICENSE](../../LICENSE).

<br>

---

<div align="center">
  <sub>Bygget med 🐍 Python • 🖼️ pywebview • 🎨 Vintage Win95-æstetik</sub>

<br>

---

## 📸 Flere skærmbilleder

<p align="center">
  <img src="../../screenshots/detail-pane.png" alt="SAIPENVIEW Detaljepanel" width="85%" style="border-radius: 4px; border: 1px solid #3a3020;">
  <br>
  <em>Detaljepanel med tickets, underagenter og filviser.</em>
</p>

<br>

</div>
