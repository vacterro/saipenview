<div align="right">
  🌍 <strong>EN</strong> | <a href="README.ru.md">RU</a> | <a href="README.ee.md">EE</a> | <a href="README.ded.md">ДЕД</a> | <a href="README.ja.md">JA</a>
</div>

<div align="center">
  <img src="screenshots/saipen_icon.png" alt="SAIPENVIEW" width="120" height="120">
  <h1 align="center">SAIPENVIEW</h1>
  <p align="center">
    <strong>Skrivebordsvisning i oppgavelinjen for alle SAIPEN-prosjekter på maskinen din</strong>
    <br>
    Oppdager automatisk <code>.saipen/</code>-prosjekter over lokale stasjoner — sanntidsfase, oppgave, blokkering, git-status, billetter og underagenter.
    <br>
    Ett mørk-gyldent instrumentpanel med vintage Win95-tema.
  </p>
  <p>
    <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.10%2B-blue?style=flat-square&logo=python&logoColor=white" alt="Python"></a>
    <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="License"></a>
    <a href="https://github.com/vacterro/saipenview"><img src="https://img.shields.io/badge/platform-Windows-orange?style=flat-square&logo=windows&logoColor=white" alt="Platform"></a>
    <a href="https://github.com/vacterro/saipenview/releases"><img src="https://img.shields.io/github/v/release/vacterro/saipenview?style=flat-square&include_prereleases" alt="Release"></a>
    <a href="https://github.com/vacterro/saipenview/actions"><img src="https://img.shields.io/github/actions/workflow/status/vacterro/saipenview/ci.yml?branch=main&style=flat-square&logo=github" alt="CI"></a>
    [🤍 Støtt utvikleren](https://buymeacoffee.com/vacuum34)
  </p>
</div>

<br>

---

<br>

## ✨ Oversikt

<p align="center">
  <img src="screenshots/dashboard.png" alt="SAIPENVIEW Dashboard Screenshot" width="85%" style="border-radius: 4px; border: 1px solid #3a3020;">
  <br>
  <em>Hvert SAIPEN-prosjekt, underagent, billett og git-status — alt i én visning.</em>
</p>

<br>

---

## 🚀 Funksjoner

<table>
<tr>
<td width="50%">

### 🔍 Oppdaging
- **Automatisk skanning** av lokale stasjoner for `.saipen/`-prosjekter
- **Tilpassede røtter** — velg mapper eller hele stasjoner
- **Smarte ekskluderinger** — `node_modules`, `.git`, systemmapper
- **Bakgrunnsskanning** — konfigurerbart intervall (standard 300s)
- **Koblede arbeidstrær** — oppdager git worktrees for enkelt oppsett

### 📊 Instrumentpanel
- Sanntids **fase**, **oppgave**, **neste handling**, **blokkering**
- **Git-gren** + uendret/endret-statusindikator per prosjekt
- **Filtrer** etter fase (Alle / Aktiv / Fullført / Blokkert / tilpasset)
- **Sorter** — Smart, Nyeste, Eldste, A–Å, Å–A
- **Søk** — navn/rot-filter + dypsøk i billetter
- **Fest** prosjekter til toppen, **skjul** uaktuelle
- **Blinkende utheving** — endrede prosjekter lyser og toners ut over 20s
- **Varmefarging** — inaktive prosjekter kjøles ned, ferske prosjekter varmes opp

</td>
<td width="50%">

### 🧩 Underagenter
- **Innrykket visning** — `saiwiki`, `saihunt`, `saitranslate` innrykket under forelder
- **Outbox-antall** — klar/blokkert/utkast/gjennomgått ved et øyekast
- **Ett-klikk-samling** — samle klare oppføringer inn i hovedprosjektet
- **Foreldelsesadvarsel** — oppdager utdaterte protokollfiler

- **Agent Engine** - start `claude-code` (eller andre motorer: codex, aider, gemini, cline, goose, agy, generic_cli) i et prosjekt
  - **Live status** - kjorende/avsluttet tilstand, CPU, forlopt tid per prosjekt
  - **Utgangskonsoll** - bufret agentutgang (standard 5000 linjer), stdin-inndata
  - **Kill / stop all** - drep prosess og global stopp
  - **Enkeltinstans-beskyttelse** - bare én app-forekomst; andre start viser vinduet igjen
### 🎮 Interaksjon
- **Filviser** — les og rediger STATE.md, BOARD.md, LOG.md
  - Kildemodus (redigerbar) + Lesemodus (rendret)
- **Interaktive billetter** — Start / Fullført-knapper oppdaterer BOARD.md direkte
- **Hurtighandlinger** — kontekstuelle `npm run dev`, `cargo test` osv.
- **Tilpassede kommandoer** — brukerdefinerte handlingsknapper
- **Sammenleggbare seksjoner** — per prosjekt, lagret
- **Endre størrelse på sidefelt** — dra for å endre størrelse

### ⌨️ Snarveier og vindu
- **Vis/skjul** — `Ctrl+Alt+X` (konfigurerbar)
- **Fest til hjorner** - `Alt+F14` veksler OV → OH → NV → NH
- **Zoom** — `Ctrl+Mushjul`, `Ctrl`+`+`/`-`
- **Systemfelt** — minimer til systemfelt, start skjult
- **Alltid øverst**-bryter
- **Automatisk start** — valgfri Windows-oppstart
- **Rammeløs modus** — slå av tittellinje for ultra-minimal visning

</td>
</tr>
</table>

<br>

---

<br>

## 🎯 Hurtigstart

<table>
<tr>
<th width="33%">🐍 Kjør fra kildekode</th>
<th width="33%">📜 Oppstartsskript</th>
<th width="33%">📦 Installer (fremtidig)</th>
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

| Skript | Oppførsel |
|---|---|
| `run.vbs` | Skjult (kun skuff), stille |
| `run.bat` | Start til skuffen; konsollen er synlig bare under engangsoppsett av venv/avhengigheter |
Begge oppretter automatisk `.venv` og installerer avhengigheter.

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

## ⌨️ Bruk

| Handling | Hvordan |
|---|---|
| **Vis / Skjul** | `Ctrl+Alt+X` eller `Alt+F15` (begge konfigurerbare) |
| **Fest til hjorne** | `Alt+F14` - veksler Overst-venstre → Overst-hoyre → Nederst-venstre → Nederst-hoyre |
| **Nødstopp** | `Ctrl+Shift+Alt+Q` — tving avslutning av prosessen |
| **Zoom inn / ut** | `Ctrl+Mushjul` eller `Ctrl` + `+` / `-` |
| **Tilbakestill zoom** | `Ctrl+0` |
| **Veksle verktøylinje** | `Alt+D` — skjul/utvid verktøylinjepanelet |
| **Søk i prosjekter** | Skriv i søkefeltet; kyss av `D` for dypsøk i billetter |
| **Filtrer** | Rullgardinmeny: Alle / Aktiv / Fullført / Blokkert, eller klikk på en fasepille |
| **Sorter** | Smart / Nyeste / Eldste / A–Å / Å–A |
| **Ny skanning** | Klikk `Ny skanning` eller vent på bakgrunnstidtaker (standard 300 s) |
| **Bla gjennom mappe** | Klikk `Bla gjennom` for å legge til en mappe i skannesettet |
| **Innstillinger** | ⚙-knapp åpner innstillingsmodalen |
| **Hjelpe-wiki** | `?`-knapp åpner den innebygde minivikien |
| **Høyreklikk prosjekt** | Kopier rotsti, filtrer etter fase, åpne mappe |
| **Dobbeltklikk seksjon** | Åpner den tilknyttede filen (STATE.md, BOARD.md, LOG.md) |
| **Dra vindu** | Dra tittellinjen (eller hvor som helst i rammeløs modus) |

### Modaler

| Modal | Hva den gjør |
|---|---|
| **Innstillinger** | Zoom, snarveier, skannejustering, automatisk start, alltid øverst, skrifttype, blinkveksling, standard filviser, tilpassede kommandoer, språk, skannerøtter |
| **Filviser** | Les og rediger STATE.md, BOARD.md, LOG.md — Kilde (rå) eller Leser (rendret) modus |
| **Hjelp** | Omfattende miniviki som dekker hver funksjon, snarvei og konsept |
| **Bekreft** | Vintage-stilt DOM-dialogboks (erstatter innebygd `confirm()`) |

<br>

---

## 🧬 SAIPEN-protokoll

SAIPENVIEW er en følgesvenn for prosjekter som bruker **SAIPEN-protokollen** — et tilstandsmaskin-rammeverk som veileder AI-agenter gjennom prosjektarbeid i definerte faser:

```
INIT → PLAN → SCOUT → BUILD → REVIEW → VERIFY → SHIP → DONE
                 ↓              ↓
            HUNT / CLEAN    VALIDATE
```

`ADD`, `MARKHUNT`, `TRANSLATE`, `PREPARE` finnes også - det fulle vokabularet og overgangstabellen ligger i `saipenview/protocol.py` (`BLOCKED` kan nås fra de fleste faser).
Hvert SAIPEN-prosjekt lagrer sin tilstand i tre kanoniske filer:

| Fil | Formål |
|---|---|
| `.saipen/STATE.md` | Maskinlesbar ingress — fase, oppgave, neste handling, blokkering |
| `.saipen/BOARD.md` | Billettavdeling — seksjoner for PÅGÅR / GJØREMÅL / FULLFØRT / BLOKKERT |
| `.saipen/LOG.md` | Kronologisk hendelseslogg — hver kommando og dens resultat |

**SubSaipen-agenter** (`saiwiki`, `saihunt`, `saitranslate`) bor i `.saipen/extensions/subs/` og kommuniserer via `kitchen/OUTBOX.md` — protokollens innebygde meldingsbuss mellom agenter. SAIPENVIEW oppdager alle sammen og viser et enhetlig instrumentpanel.

### Samsvar

Å vise hva et prosjekt *sier* er bare halvparten. Et prosjekt kan se helt fint ut i listen — en fase, en oppgave, en neste handling — mens det befinner seg i en tilstand protokollen avviser, og før du kjørte `tools/validate.py` manuelt var det ingen måte å skille de to fra hverandre.

Hver rad har et vurderingsmerke, og detaljpanelet lister opp hva som er galt:

| Vurdering | Betydning |
|---|---|
| `OK` | Ingenting funnet i dette prosjektets egne `.saipen/`-filer |
| `N WARNS` | Lovlig, men på avveie — et utdatert kontrollpunkt, et ikke-standard LOG-verb |
| `N FAILS` | En tilstand protokollen avviser: en `WAIT:` uten kategori, en avkrysningsboks som er uenig med sin seksjon, en `needs:` som peker på en billett som ikke finnes, en UTF-16 `STATE.md` ingen andre SAIPEN-verktøy kan lese |

Hvert funn oppgir regelen, filen og linjen, samt klausulen det kommer fra, slik at det kan slås opp heller enn å tas på tro og ære.

Dette er en **vurdering nummer to, ikke en erstatning** for `tools/validate.py`. Den re-sjekker bare det prosjektets egne filer kan avgjøre, og den vurderer mot en kopi av protokollens vokabularer — så SAIPEN-versjonen den ble lest fra trykkes under hver vurdering. Visningsprogrammet har lov til å ligge etter protokollen. Det har ikke lov til å ligge etter i det stille.

> 💡 *Navnet "SAIPENVIEW" sier alt — det gir en **visning** (view) av hvert **SAIPEN**-prosjekt på maskinen din.*

<br>

---

## ⚙️ Konfigurasjon

Konfigurasjonen er portabel — lagres ved siden av appen, ikke i `%APPDATA%`:

```
saipenview/_data/config.json
```

Viktigste standardverdier (forkortet - den fulle `DEFAULTS`-ordboken ligger i `saipenview/config.py`):

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

Sett `scan_roots: null` for å oppdage alle lokale stasjoner automatisk.  
Sett til en liste med stier (f.eks. `["V:\\", "D:\\projects"]`) for å begrense skanningen.  
`default_engine` / `engine_overrides` / `agent_output_buffer_size` styrer Agent Engine (se Funksjoner).  
Alle innstillinger er også konfigurerbare gjennom **Innstillinger**-modalen i appen.

<br>

---

## 🏗️ Arkitektur

```
saipenview/
├── app.py              Inngangsforbindelse - skuff, hotkey, vindu, api, enkeltinstans-beskyttelse
├── api.py              JS-vendt pywebview-bro (66 offentlige metoder)
├── scanner.py          Stasjonsgjennomgang + bakgrunnsskanningsløkke
├── parser.py           Tolkning av STATE.md / BOARD.md / LOG.md
├── textio.py           Én leser for hver .saipen/-fil — BOM, UTF-16, cp1251
├── protocol.py         Protokollens lukkede vokabularer + BASELINE_VERSION
├── conformance.py      Vurderer et prosjekt mot disse vokabularene
├── config.py           Lading/lagring av innstillinger (atomiske skrivinger)
├── tray.py             pystray-systemfeltikon + meny
├── hotkey.py           Global snarveiregistrering (keyboard-bibliotek)
├── autostart.py        Håndtering av Windows Registry-oppstart
├── zone_picker.py      Alt+F14 hjornefestingsvisning (tkinter)
├── events.py           In-process hendelsesbuss (EventBus)
├── guard.py            Enkeltinstans-lås + vising-foresporsel overlevering
├── git_diff.py         Arbeidstre diff / commit / revert for agenthandlinger
├── runtime.py          Agent Engine - prosesshåndtering for startede agenter
├── watcher.py          Watchdog-filvakt på .saipen/-filer
├── engines/            Agent Engine - stottede CLI-motorer (claude-code, codex,
│                       aider, gemini, cline, goose, agy, generic_cli)
├── ui/
│   ├── window.py       pywebview-vindu — vis/skjul/veksle/fest
│   └── static/
│       ├── index.html
│       ├── style.css   Mørk-gyldent vintage Win95-tema
│       └── app.js      Frontend-logikk (~3300 linjer)
├── assets/
│   └── tray_icon.png
├── screenshots/        Skjermbilder for README
└── _data/              Kjøretidskonfigurasjon + hurtigbuffer (gitignorert)
```

### Designprinsipper

- **Én enkelt prosess** — ingen bakgrunns-IPC, ingen separat tjener; én Python-prosess er vert for både WebView2-vinduet og skanneløkken i en `ThreadPoolExecutor`
- **Atomiske skrivinger** — hver filskriving bruker midlertidig fil + `os.replace`; et krasj kan aldri avkorte konfigurasjon eller hurtigbuffer
- **Trygg mot foreldet lesing** — 5s UI-oppdatering kaller `refresh_known()` (leser bare `.saipen/`-filer på nytt, ingen mappeliste). Endringer i STATE.md vises innen sekunder uten å utløse en full stasjonsskanning
- **Ingen CSS-overganger** — alle visuelle effekter (blink, varme, peker) er JavaScript-drevne `hexBlend`-omregninger som strengt følger vintagetemaets null-animasjonsbegrensning
- **Vintagetema** — mørkebrune flater, gylden tekst/aksenter, 3D-skråkanter, null kantutjevning, Verdana_m1-skrifttype

<br>

---

## 🧪 Utvikling

```bash
# Klon og gå inn
git clone https://github.com/vacterro/saipenview.git
cd saipenview

# Opprett venv og installer
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# Kjør
python -m saipenview
```

For detaljert oppsett, kodekonvensjoner og PR-arbeidsflyt, se [CONTRIBUTING.md](CONTRIBUTING.md).

### Krav

- **Windows 10 / 11** — WebView2 runtime (forhåndsinstallert på Win11, installeres automatisk på Win10)
- **Python 3.10+**
- Avhengigheter: `pystray`, `keyboard`, `pywebview`, `Pillow`, `watchdog`, `psutil`

<br>

---

## 📄 Lisens

MIT — se [LICENSE](LICENSE).

<br>

---

<div align="center">
  <sub>Bygget med 🐍 Python • 🖼️ pywebview • 🎨 Vintage Win95-estetikk</sub>

<br>

---

## 📸 Flere skjermbilder

<p align="center">
  <img src="screenshots/detail-pane.png" alt="SAIPENVIEW Detail Pane" width="85%" style="border-radius: 4px; border: 1px solid #3a3020;">
  <br>
  <em>Detaljpanel med billetter, underagenter og filviser.</em>
</p>

<br>

</div>
