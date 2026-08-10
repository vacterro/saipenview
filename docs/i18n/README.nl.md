<div align="right">

  🌍 <a href="../../README.md">EN</a> | <a href="README.ar.md">AR</a> | <a href="README.bg.md">BG</a> | <a href="README.cs.md">CS</a> | <a href="README.da.md">DA</a> | <a href="README.de.md">DE</a> | <a href="README.ee.md">EE</a> | <a href="README.el.md">EL</a> | <a href="README.es.md">ES</a> | <a href="README.fi.md">FI</a> | <a href="README.fr.md">FR</a> | <a href="README.he.md">HE</a> | <a href="README.hi.md">HI</a> | <a href="README.hr.md">HR</a> | <a href="README.hu.md">HU</a> | <a href="README.id.md">ID</a> | <a href="README.it.md">IT</a> | <a href="README.ja.md">JA</a> | <a href="README.ko.md">KO</a> | <strong>NL</strong> | <a href="README.no.md">NO</a> | <a href="README.pl.md">PL</a> | <a href="README.pt.md">PT</a> | <a href="README.ro.md">RO</a> | <a href="README.ru.md">RU</a> | <a href="README.sk.md">SK</a> | <a href="README.sv.md">SV</a> | <a href="README.th.md">TH</a> | <a href="README.tr.md">TR</a> | <a href="README.uk.md">UK</a> | <a href="README.vi.md">VI</a> | <a href="README.zh.md">ZH</a> | <a href="README.zh-CN.md">ZH-CN</a> | <a href="README.ded.md">ДЕД</a>
</div>
> **Note:** This is a translated copy. The canonical documentation is [README.md](../../README.md) — this translation may lag the English original.

<div align="center">
  <img src="../../screenshots/saipen_icon.png" alt="SAIPENVIEW" width="120" height="120">
  <h1 align="center">SAIPENVIEW</h1>
  <p align="center">
    <strong>Desktop tray-viewer voor elk SAIPEN-project op je computer</strong>
    <br>
    Detecteert automatisch <code>.saipen/</code> projecten op lokale schijven — live fase, taak, blocker, git-status, tickets en sub-agents.
    <br>
    Eén vintage donkergouden Win95-geïnspireerd dashboard.
  </p>
  <p>
    <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.10%2B-blue?style=flat-square&logo=python&logoColor=white" alt="Python"></a>
    <a href="../../LICENSE"><img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="Licentie"></a>
    <a href="https://github.com/vacterro/saipenview"><img src="https://img.shields.io/badge/platform-Windows-orange?style=flat-square&logo=windows&logoColor=white" alt="Platform"></a>
    <a href="https://github.com/vacterro/saipenview/releases"><img src="https://img.shields.io/github/v/release/vacterro/saipenview?style=flat-square&include_prereleases" alt="Release"></a>
    <a href="https://github.com/vacterro/saipenview/actions"><img src="https://img.shields.io/github/actions/workflow/status/vacterro/saipenview/ci.yml?branch=main&style=flat-square&logo=github" alt="CI"></a>
  </p>
</div>

<br>

---

## 🚀 Functies

<table>
<tr>
<td width="50%">

### 🔍 Detectie
- **Auto-scan** van lokale schijven op `.saipen/` projecten
- **Aangepaste mappen** — kies specifieke mappen of volledige schijven
- **Slim uitsluiten** — `node_modules`, `.git`, systeemmappen
- **Achtergrond-rescan** — instelbaar interval (standaard 300s)
- **Gekoppelde worktrees** — detecteert git worktrees voor eenvoudige configuratie

### 📊 Dashboard
- Live **fase**, **taak**, **volgende actie**, **blocker**
- **Git branch** + statusindicator (dirty/clean) per project
- **Filter** op fase (Alles / Actief / Voltooid / Gevangen / aangepast)
- **Sorteren** — Slim, Recent, Oudste, A–Z, Z–A
- **Zoeken** — naam/pad filter + diep zoeken in tickets
- **Vastpinnen** van projecten bovenaan, **verbergen** van irrelevante projecten
- **Knippermarkering** — gewijzigde projecten lichten op & vervagen in 20s
- **Warmtekleuring** — verouderde projecten koelen af, recente projecten worden warm

</td>
<td width="50%">

### 🧩 Sub-Agents
- **Geneste weergave** — `saiwiki`, `saihunt`, `saitranslate` ingesprongen onder hoofdproject
- **Outbox-aantallen** — gereed/geblokkeerd/concept/beoordeeld in één oogopslag
- **Verzamelen met één klik** — voeg gereed zijnde items samen in het hoofdproject
- **Verouderingswaarschuwing** — detecteert verouderde protocolbestanden

- **Agent Engine** - start `claude-code` (of andere engines: codex, aider, gemini, cline, goose, agy, generic_cli) in een project
  - **Live status** - draaiend/gestopt, CPU, verstreken tijd per project
  - **Uitvoerconsole** - gebufferde agentuitvoer (standaard 5000 regels), stdin-invoer
  - **Kill / stop all** - proces doden en globale stop
  - **Enkelvoudige instantie** - slechts één app-instantie; tweede start toont het venster opnieuw
### 🎮 Interactie
- **Bestandsviewer** — lees & bewerk STATE.md, BOARD.md, LOG.md
  - Bronmodus (bewerkbaar) + Leesmodus (geformatteerd)
- **Interactieve tickets** — Start / Voltooid knoppen werken BOARD.md live bij
- **Snelle acties** — contextuele `npm run dev`, `cargo test`, enz.
- **Aangepaste commando's** — door gebruiker gedefinieerde actieknoppen
- **Inklapbare secties** — per project, onthouden
- **Aanpasbare zijbalk** — slepen om het formaat te wijzigen

### ⌨️ Sneltoetsen & Venster
- **Tonen/Verbergen** — `Ctrl+Alt+X` (instelbaar)
- **Hoek-snapping** - `Ctrl+Q` wisselt LB → RB → LO → RO
- **Zoom** — `Ctrl+Muiswiel`, `Ctrl+`+`/`-`
- **Systeemvak (Tray)** — minimaliseren naar systeemvak, verborgen starten
- **Altijd op voorgrond** schakelaar
- **Automatisch starten** — optioneel met Windows opstarten
- **Kaderloze modus** — titelbalk uitschakelen voor een ultra-minimale weergave

</td>
</tr>
</table>

<br>

---

<br>

## 🎯 Snelstart

<table>
<tr>
<th width="33%">🐍 Uitvoeren vanaf broncode</th>
<th width="33%">📜 Opstartscripts</th>
<th width="33%">📦 Installeren (toekomst)</th>
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

| Script | Gedrag |
|---|---|
| `run.vbs` | Verborgen (alleen systeemvak), stil |
| `run.bat` | Start naar het systeemvak; console alleen zichtbaar tijdens eenmalige venv/afhankelijkheden-instelling |
Beide maken automatisch `.venv` aan & installeren afhankelijkheden.

</td>
<td>

```bash
pip install saipenview
saipenview
```
Binnenkort beschikbaar ✨

</td>
</tr>
</table>

<br>

---

## ⌨️ Gebruik

| Actie | Hoe |
|---|---|
| **Tonen / Verbergen** | `Ctrl+Alt+X` of `Alt+F15` (beide instelbaar) |
| **Hoek-snapping** | `Ctrl+Q` - wisselt Links-Boven → Rechts-Boven → Links-Onder → Rechts-Onder |
| **Noodstop (Kill switch)** | `Ctrl+Shift+Alt+Q` — proces geforceerd beëindigen |
| **In- / uitzoomen** | `Ctrl+Muiswiel` of `Ctrl` + `+` / `-` |
| **Zoom herstellen** | `Ctrl+0` |
| **Werkbalk in-/uitklappen** | `Alt+D` — klap het werkbalkpaneel in of uit |
| **Projecten zoeken** | Typ in de zoekbalk; vink `D` aan voor diep zoeken in tickets |
| **Filteren** | Keuzemenu: Alles / Live / Voltooid / Gevangen, of klik op een fase-pill |
| **Sorteren** | Slim / Recent / Oudste / A–Z / Z–A |
| **Opnieuw scannen** | Klik op `Opnieuw scannen` of wacht op achtergrondtimer (standaard 300s) |
| **Map bladeren** | Klik op `Bladeren` om een map toe te voegen aan de scanset |
| **Instellingen** | ⚙ knop opent het instellingenvenster |
| **Help-wiki** | `?` knop opent de ingebouwde mini-wiki |
| **Rechtermuisklik op project** | Kopieer pad, filter op fase, open map |
| **Dubbelklik op sectie** | Opent het gekoppelde bestand (STATE.md, BOARD.md, LOG.md) |
| **Venster slepen** | Sleep de titelbalk (of willekeurig in kaderloze modus) |

### Modale vensters

| Venster | Wat het doet |
|---|---|
| **Instellingen** | Zoom, sneltoetsen, scan-afstemming, automatisch starten, altijd op voorgrond, lettertype, knipperschakelaar, standaard bestandsviewer, aangepaste commando's, taal, scanmappen |
| **Bestandsviewer** | Lees & bewerk STATE.md, BOARD.md, LOG.md — Bron (ruw) of Lezer (geformatteerd) modus |
| **Help** | Uitgebreide mini-wiki die elke functie, sneltoets en concept behandelt |
| **Bevestigen** | Vintage-gestijld DOM-dialog (vervangt systeemeigen `confirm()`) |

<br>

---

## 🧬 SAIPEN Protocol

SAIPENVIEW is een hulpprogramma voor projecten die gebruikmaken van het **SAIPEN Protocol** — een toestandsmachine-framework dat AI-agents door projectwerk leidt in gedefinieerde fasen:

```
INIT → PLAN → SCOUT → BUILD → REVIEW → VERIFY → SHIP → DONE
                 ↓              ↓
            HUNT / CLEAN    VALIDATE
```

`ADD`, `MARKHUNT`, `TRANSLATE`, `PREPARE` bestaan ook - de volledige vocabulaire en de overgangstabel staan in `saipenview/protocol.py` (`BLOCKED` is bereikbaar vanuit de meeste fasen).
Elk SAIPEN-project slaat zijn status op in drie canonieke bestanden:

| Bestand | Doel |
|---|---|
| `.saipen/STATE.md` | Machinaal leesbare frontmatter — fase, taak, volgende actie, blocker |
| `.saipen/BOARD.md` | Ticketbord — DOING / TODO / DONE / BLOCKED secties |
| `.saipen/LOG.md` | Chronologisch gebeurtenissenlogboek — elk commando en de uitkomst ervan |

**SubSaipen agents** (`saiwiki`, `saihunt`, `saitranslate`) bevinden zich in `.saipen/extensions/subs/` en communiceren via `kitchen/OUTBOX.md` — de ingebouwde berichtenbus van het protocol tussen agents. SAIPENVIEW detecteert ze allemaal en toont een geïntegreerd dashboard.

### Conformiteit

Laten zien wat een project *zegt* is slechts de helft van het werk. Een project kan er perfect uitzien in de lijst — een fase, een taak, een volgende actie — terwijl het zich in een status bevindt die het protocol weigert, en totdat je handmatig `tools/validate.py` uitvoerde, was er geen manier om die twee van elkaar te onderscheiden.

Elke rij bevat een oordeel-badge, en het detailpaneel vermeldt wat er mis is:

| Oordeel | Betekenis |
|---|---|
| `OK` | Niets gevonden in de eigen `.saipen/`-bestanden van dit project |
| `N WARNS` | Toegestaan, maar afwijkend — een verouderde checkpoint, een niet-standaard LOG-werkwoord |
| `N FAILS` | Een status die het protocol weigert: een `WAIT:` zonder categorie, een selectievakje dat niet overeenkomt met de sectie, een `needs:` die verwijst naar een niet-bestaand ticket, een UTF-16 `STATE.md` die geen enkele andere SAIPEN-tool kan lezen |

Elke bevinding vermeldt de regel, het bestand en het regelnummer, en de clausule waar het vandaan komt, zodat het kan worden opgezocht in plaats van op goed geloof te worden aangenomen.

Dit is een **second opinion, geen vervanging** voor `tools/validate.py`. Het controleert alleen opnieuw wat de bestanden van het project zelf kunnen bepalen, en het beoordeelt aan de hand van een kopie van de vocabulaire van het protocol — dus de SAIPEN-versie waarvan het is gelezen, wordt onder elk oordeel afgedrukt. Het weergaveprogramma mag achterlopen op het protocol. Het mag niet stilzwijgend achterlopen.

> 💡 *De naam "SAIPENVIEW" zegt het al — het biedt een **weergave (view)** van elk **SAIPEN**-project op je computer.*

<br>

---

## ⚙️ Configuratie

De configuratie is draagbaar — opgeslagen naast de applicatie, niet in `%APPDATA%`:

```
saipenview/_data/config.json
```

Belangrijkste standaardwaarden (verkort - het volledige `DEFAULTS`-woordenboek staat in `saipenview/config.py`):

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

Stel `scan_roots: null` in om automatisch alle lokale schijven te detecteren.  
Stel in op een lijst met paden (bijv. `["V:\\", "D:\\projects"]`) om het scannen te beperken.  
`default_engine` / `engine_overrides` / `agent_output_buffer_size` sturen de Agent Engine (zie Functies).  
Alle instellingen zijn ook te configureren via het modale venster **Instellingen** in de app.

<br>

---

## 🏗️ Architectuur

```
saipenview/
├── app.py              Ingangsbedrading - systeemvak, hotkey, venster, api, enkelvoudige-instantiebeveiliging
├── api.py              JS-gerichte pywebview-brug (66 openbare methoden)
├── scanner.py          Schijfscan + achtergrond-rescanlus
├── parser.py           STATE.md / BOARD.md / LOG.md verwerking
├── textio.py           Eén lezer voor elk .saipen/-bestand — BOM, UTF-16, cp1251
├── protocol.py         Besloten vocabulaire van het protocol + BASELINE_VERSION
├── conformance.py      Beoordeelt een project aan de hand van die vocabulaire
├── config.py           Instellingen laden/opslaan (atomaire schrijfopdrachten)
├── tray.py             pystray systeemvak-icoon + menu
├── hotkey.py           Globale sneltoetsregistratie (keyboard lib)
├── autostart.py        Windows Registry automatische opstartbeheer
├── zone_picker.py      Ctrl+Q hoek-snap overlay (tkinter)
├── events.py           In-process gebeurtenisbus (EventBus)
├── guard.py            Enkelvoudige-instantieslot + tonen-verzoek overdracht
├── git_diff.py         Werkboom diff / commit / revert voor agentacties
├── runtime.py          Agent Engine - procesbeheerder voor gestarte agents
├── watcher.py          Watchdog-bestandswaker op .saipen/-bestanden
├── engines/            Agent Engine - ondersteunde CLI-engines (claude-code, codex,
│                       aider, gemini, cline, goose, agy, generic_cli)
├── ui/
│   ├── window.py       pywebview venster — tonen/verbergen/schakelen/snappen
│   └── static/
│       ├── index.html
│       ├── style.css   Vintage donkergouden Win95-thema
│       └── app.js      Frontend-logica (~3300 regels)
├── assets/
│   └── tray_icon.png
├── screenshots/        README screenshots
└── _data/              Runtime configuratie + cache (gitignored)
```

### Ontwerpprincipes

- **Enkel proces** — geen achtergrond-IPC, geen afzonderlijke server; één Python-proces host zowel het WebView2-venster als de scanlus in een `ThreadPoolExecutor`
- **Atomaire schrijfopdrachten** — elke bestandsschrijfopdracht gebruikt een tijdelijk bestand + `os.replace`; een crash kan de configuratie of cache nooit beschadigen
- **Veilig voor verouderde weergave** — de 5s UI-poll roept `refresh_known()` aan (herleest alleen `.saipen/`-bestanden, geen map-scan). Bewerkingsacties in STATE.md verschijnen binnen enkele seconden zonder een volledige schijfscan te starten
- **Geen CSS-transities** — alle visuele effecten (knipperen, warmte, hover) zijn door JavaScript aangestuurde `hexBlend` herberekeningen, strikt volgens de voorwaarde van het vintage thema zonder animaties
- **Vintage thema** — donkerbruine oppervlakken, gouden tekst/accenten, 3D schuine randen, geen anti-aliasing, Verdana_m1 lettertype

<br>

---

## 🧪 Ontwikkeling

```bash
# Kloon & open
git clone https://github.com/vacterro/saipenview.git
cd saipenview

# Maak venv aan & installeer
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# Uitvoeren
python -m saipenview
```

Voor gedetailleerde installatie, codeerconventies en PR-workflow, zie [CONTRIBUTING.md](../../CONTRIBUTING.md).

### Vereisten

- **Windows 10 / 11** — WebView2 runtime (vooraf geïnstalleerd op Win11, wordt automatisch geïnstalleerd op Win10)
- **Python 3.10+**
- Afhankelijkheden: `pystray`, `keyboard`, `pywebview`, `Pillow`, `watchdog`, `psutil`

<br>

---

## 📄 Licentie

MIT — zie [LICENSE](../../LICENSE).

<br>

---

<div align="center">
  <sub>Gemaakt met 🐍 Python • 🖼️ pywebview • 🎨 Vintage Win95 esthetiek</sub>

<br>

---

## 📸 Meer Screenshots

<p align="center">
  <img src="../../screenshots/detail-pane.png" alt="SAIPENVIEW Detail Pane" width="85%" style="border-radius: 4px; border: 1px solid #3a3020;">
  <br>
  <em>Detailpaneel met tickets, sub-agents en bestandsviewer.</em>
</p>

<br>

</div>
