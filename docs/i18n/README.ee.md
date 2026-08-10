<div align="right">

  🌍 <a href="../../README.md">EN</a> | <a href="README.ar.md">AR</a> | <a href="README.bg.md">BG</a> | <a href="README.cs.md">CS</a> | <a href="README.da.md">DA</a> | <a href="README.de.md">DE</a> | <strong>EE</strong> | <a href="README.el.md">EL</a> | <a href="README.es.md">ES</a> | <a href="README.fi.md">FI</a> | <a href="README.fr.md">FR</a> | <a href="README.he.md">HE</a> | <a href="README.hi.md">HI</a> | <a href="README.hr.md">HR</a> | <a href="README.hu.md">HU</a> | <a href="README.id.md">ID</a> | <a href="README.it.md">IT</a> | <a href="README.ja.md">JA</a> | <a href="README.ko.md">KO</a> | <a href="README.nl.md">NL</a> | <a href="README.no.md">NO</a> | <a href="README.pl.md">PL</a> | <a href="README.pt.md">PT</a> | <a href="README.ro.md">RO</a> | <a href="README.ru.md">RU</a> | <a href="README.sk.md">SK</a> | <a href="README.sv.md">SV</a> | <a href="README.th.md">TH</a> | <a href="README.tr.md">TR</a> | <a href="README.uk.md">UK</a> | <a href="README.vi.md">VI</a> | <a href="README.zh.md">ZH</a> | <a href="README.zh-CN.md">ZH-CN</a> | <a href="README.ded.md">ДЕД</a>
</div>
> **Note:** This is a translated copy. The canonical documentation is [README.md](../../README.md) — this translation may lag the English original.

<div align="center">
  <img src="../../screenshots/saipen_icon.png" alt="SAIPENVIEW" width="120" height="120">
  <h1 align="center">SAIPENVIEW</h1>
  <p align="center">
    <strong>Töölaua salvevaatur igale SAIPEN-projektile sinu masinas</strong>
    <br>
    Leiab automaatselt <code>.saipen/</code>-projektid kohalikelt ketastelt — elus faas, ülesanne, blokeerija, git-seisund, piletid ja alamagentid.
    <br>
    Üks vintage tume-kuldne Win95-temaatiline armatuurlaud.
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

## 🚀 Funktsioonid

<table>
<tr>
<td width="50%">

### 🔍 Avastamine
- **Automaatskaneerimine** — `.saipen/`-projektide otsing kohalikelt ketastelt
- **Kohandatud juured** — vali kaustu või terveid kettaid
- **Nutikad erandid** — `node_modules`, `.git`, süsteemikaustad
- **Taustaskaneerimine** — seadistatav intervall (vaikimisi 300 s)
- **Seotud worktree'd** — tuvastab git-worktree'd lihtsaks seadistuseks

### 📊 Armatuurlaud
- Elus **faas**, **ülesanne**, **järgmine tegevus**, **blokeerija**
- **Git-haru** + määrdunud-seisundi indikaator projekti kohta
- **Filter** faasi järgi (Kõik / Aktiivsed / Valmis / Kinni / oma)
- **Sortimine** — Smart, Recent, Oldest, A–Z, Z–A
- **Otsing** — nime/juure filter + süvaotsing piletites
- **Kinnitamine** — projektid üles, **peitmine** — mittevajalikud
- **Muutuse esiletõstmine** — muutunud projektid helendavad ja kustuvad 20 s jooksul
- **Kuumusvärvid** — vanad projektid jahedad, värsked soojad

</td>
<td width="50%">

### 🧩 Alamagendid
- **Pesastatud kuva** — `saiwiki`, `saihunt`, `saitranslate` taande all
- **OUTBOX-loendurid** — ready/blocked/draft/reviewed ühe pilguga
- **Üheklõpiline kogumine** — valmis kirjed pannakse põhiprojekti
- **Aegumise hoiatus** — märkab aegunud protokollifaile
- **Agent Engine** — `claude-code` (või muud mootorid: codex, aider, gemini, cline, goose, agy, generic_cli) käivitamine projektis
  - **Elus staatus** — käivitamise/väljumise olek, CPU, kulunud aeg projekti kohta
  - **Väljundkonsool** — puhverdatud agendi väljund (vaikimisi 5000 rida), stdin-sisend
  - **Kill / stop all** — projekti tapmine ja globaalne peatus
  - **Ühekordne kaitsja** — ainult üks rakenduse eksemplar; teine käivitus näitab akent

### 🎮 Suhtlus
- **Failivaatur** — STATE.md, BOARD.md, LOG.md lugemine ja muutmine
  - Lähterežiim (redigeeritav) + lugemisrežiim (renderdatud)
- **Interaktiivsed piletid** — Start / Done nupud uuendavad BOARD.md reaalajas
- **Kiirtegevused** — kontekstuaalsed `npm run dev`, `cargo test` jne.
- **Kohandatud käsud** — kasutaja määratud tegevusnupud
- **Ahendatavad sektsioonid** — projekti kaupa, salvestuvad
- **Reguleeritav külgriba** — lohistamisega

### ⌨️ Kiirklahvid ja aken
- **Kuva / Peida** — `Ctrl+Alt+X` (seadistatav)
- **Nurga klõps** — `Ctrl+Q` tsüklina VP → VN → AN → AP
- **Suum** — `Ctrl+Hiireratas`, `Ctrl+`+`/`-`
- **Süsteemsalv** — minimeerimine salve, peidetud käivitus
- **Alati ees** — lüliti
- **Automaatkäivitus** — valikuline Windowsi käivitumisel
- **Raamita režiim** — pealkirjariba peitmine minimaalseks vaateks

</td>
</tr>
</table>

<br>

---

<br>

## 🎯 Kiirkäivitus

<table>
<tr>
<th width="33%">🐍 Lähtekoodist</th>
<th width="33%">📜 Käivitusfailid</th>
<th width="33%">📦 Install (tulevikus)</th>
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

| Fail | Käitumine |
|---|---|
| `run.vbs` | Peidetud (ainult salv), vaikne |
| `run.bat` | Ainult salv; konsool nähtav vaid ühekordsel venv/sõltuvuste seadistamisel |
Mõlemad loovad `.venv` ja paigaldavad sõltuvused ise.

</td>
<td>

```bash
pip install saipenview
saipenview
```
Varsti ✨

</td>
</tr>
</table>

<br>

---

<br>

## ⌨️ Kasutamine

| Tegevus | Kuidas |
|---|---|
| **Kuva / Peida** | `Ctrl+Alt+X` või `Alt+F15` (mõlemad seadistatavad) |
| **Nurga klõps** | `Ctrl+Q` — tsükkel Üles-Vasak → Üles-Parem → Alla-Vasak → Alla-Parem |
| **Hädasulge** | `Ctrl+Shift+Alt+Q` — protsessi sundlõpetamine |
| **Suum sisse / välja** | `Ctrl+Hiireratas` või `Ctrl` + `+` / `-` |
| **Suumi lähtestus** | `Ctrl+0` |
| **Tööriistariba lüliti** | `Alt+D` — paneeli ahendamine/lahtivoltimine |
| **Projektiotsing** | Otsinguväli; `D` märkige süvaotsinguks piletites |
| **Filter** | Ripamenüü: Kõik / Elus / Valmis / Kinni, või klõps faasipillile |
| **Sortimine** | Smart / Recent / Oldest / A–Z / Z–A |
| **Uuesti skaneeri** | `Rescan` nupp või taustatimer (vaikimisi 300 s) |
| **Kausta sirvimine** | `Browse` lisab kausta skaneerimishulka |
| **Seaded** | ⚙ nupp avab seadete akna |
| **Abi** | `?` nupp avab sisseehitatud mini-viki |
| **Paremklõps projektil** | Juurtee kopeerimine, faasifilter, kausta avamine |
| **Topeltklõps sektsioonil** | Avab seotud faili (STATE.md, BOARD.md, LOG.md) |
| **Akna lohistamine** | Pealkirjaribast (või ükskõik kust raamita režiimis) |

### Aknad

| Aken | Mida teeb |
|---|---|
| **Seaded** | Suum, kiirklahvid, skaneerimise häälestus, automaatkäivitus, alati ees, font, muutuse esiletõstmine, failivaaturi vaikerežiim, kohandatud käsud, keel, skaneerimisjuured |
| **Failivaatur** | STATE.md, BOARD.md, LOG.md lugemine ja muutmine — lähte- või renderdatud režiim |
| **Abi** | Mini-viki iga funktsiooni, otsetee ja mõiste kohta |
| **Kinnitus** | Vintage-stiilis DOM-dialoog (asendab natiivse `confirm()`) |

<br>

---

<br>

## 🧬 SAIPEN-protokoll

SAIPENVIEW on kaaslane **SAIPEN-protokolli** projektidele — olekumasina raamistik, mis juhib AI-agente faaside kaupa:

```
INIT → PLAN → SCOUT → BUILD → REVIEW → VERIFY → SHIP → DONE
                 ↓              ↓
            HUNT / CLEAN    VALIDATE
```
`ADD`, `MARKHUNT`, `TRANSLATE`, `PREPARE` on samuti olemas — täielik sõnavara ja üleminekutabel on `saipenview/protocol.py`-s (`BLOCKED` saavutatav enamikust faasidest).

Iga SAIPEN-projekt hoiab olekut kolmes kanoonilises failis:

| Fail | Otstarve |
|---|---|
| `.saipen/STATE.md` | Masinloetav frontmatter — faas, ülesanne, järgmine tegevus, blokeerija |
| `.saipen/BOARD.md` | Piletilaud — DOING / TODO / DONE / BLOCKED sektsioonid |
| `.saipen/LOG.md` | Kronoloogiline sündmuste logi — iga käsk ja selle tulemus |

**Alamagendid** (`saiwiki`, `saihunt`, `saitranslate`) elavad `.saipen/extensions/subs/`-s ja suhtlevad `kitchen/OUTBOX.md` kaudu — protokolli sisseehitatud sõnumisiin. SAIPENVIEW leiab need kõik ja kuvab ühtse armatuurlaua.

### Vastavus protokollile

Näidata, mida projekt *ütleb*, on vaid pool asja. Projekt võib nimekirjas
suurepäraselt lugeda — faas, ülesanne, järgmine tegevus — ja olla samal ajal
olekus, mille protokoll tagasi lükkab, ning kuni sa käsitsi
`tools/validate.py` ei käivitanud, polnud neil vahet.

Iga rida kannab otsuse märki ja detailipaneel loetleb, mis on valesti:

| Otsus | Tähendus |
|---|---|
| `OK` | Projekti enda `.saipen/`-failidest midagi ei leitud |
| `N WARNS` | Seaduslik, kuid triivib — aegunud kontrollpunkt, mittestandardne LOG-verb |
| `N FAILS` | Olek, mille protokoll lükkab tagasi: kategooriata `WAIT:`, ruut, mis vaidleb oma sektsiooniga, `needs:` osutamas olematule piletile, UTF-16 `STATE.md`, mida ükski teine SAIPEN-tööriist ei loe |

Iga leid nimetab reegli, faili ja rea ning punkti, millest see tuleneb — et
seda saaks kontrollida, mitte uskuda.

See on **teine arvamus, mitte asendus** `tools/validate.py`-le. See
kontrollib üle vaid seda, mida projekti enda failid otsustavad, ja hindab
protokolli sõnavarade koopia vastu — seega prinditakse SAIPEN-i versioon,
millest see loeti, iga otsuse alla. Vaaturil on lubatud protokollist maha
jääda. Ei ole lubatud vaikides maha jääda.

> 💡 *Nimi ütleb kõik — SAIPENVIEW annab **vaate** igale **SAIPEN**-projektile sinu masinas.*

<br>

---

<br>

## ⚙️ Seadistamine

Konfig on portatiivne — salvestatud rakenduse kõrvale, mitte `%APPDATA%`-sse:

```
saipenview/_data/config.json
```

Peamised vaikimisi väärtused (lühendatud — täielik `DEFAULTS`-sõnastik on `saipenview/config.py`-s):

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

`scan_roots: null` — kõigi kohalike ketaste automaatotsing.  
Loendina (nt `["V:\\", "D:\\projects"]`) — skaneerimise piiramine.  
`default_engine` / `engine_overrides` / `agent_output_buffer_size` juhivad Agent Engine'it (vt Funktsioonid).  
Kõik seaded on kättesaadavad ka rakenduse **Seaded**-aknast.

<br>

---

<br>

## 🏗️ Arhitektuur

```
saipenview/
├── app.py              Sisenemispunkti ühendus — salv, kiirklahv, aken, api, ühekordne kaitsja
├── api.py              JS-vastane pywebview sild (66 avalikku meetodit)
├── scanner.py          Ketta läbikäik + taustal skaneerimistsükkel
├── parser.py           STATE.md / BOARD.md / LOG.md parsimine
├── textio.py           Üks lugeja kõikidele .saipen/-failidele — BOM, UTF-16, cp1251
├── protocol.py         Protokolli suletud sõnavarad + BASELINE_VERSION
├── conformance.py      Hindab projekti nende sõnavarade vastu
├── config.py           Seadete salvestamine/laadimine (aatomilised kirjed)
├── tray.py             pystray salveikoon + menüü
├── hotkey.py           Globaalsete kiirklahvide registreerimine (keyboard)
├── autostart.py        Windowsi registri automaatkäivituse haldus
├── zone_picker.py      Ctrl+Q nurga-klõpsu ülekate (tkinter)
├── events.py           Protsisisisene sündmussiin (EventBus)
├── guard.py            Ühekordse eksemplari lukk + näitamistaotluse edastus
├── git_diff.py         Tööpuu diff / commit / revert agentide tegevuste jaoks
├── runtime.py          Agent Engine — käivitatud agentide protsessihaldur
├── watcher.py          Watchdog-failivaatur .saipen/-failidele
├── engines/            Agent Engine — toetatud CLI-mootorid (claude-code, codex,
│                       aider, gemini, cline, goose, agy, generic_cli)
├── ui/
│   ├── window.py       pywebview aken — kuva/peida/lülita/klõps
│   └── static/
│       ├── index.html
│       ├── style.css   Vintage tume-kuldne Win95 teema
│       └── app.js      Frontendi loogika (~3300 rida)
├── assets/
│   └── tray_icon.png
├── screenshots/        README ekraanipildid
└── _data/              Runtimikofig ja vahemälu (gitignored)
```

### Disainipõhimõtted

- **Üks protsess** — pole tausta-IPC-d ega eraldi serverit; üks Python-protsess hoiab nii WebView2 akent kui ka skaneerimistsüklit `ThreadPoolExecutor`-is
- **Aatomilised kirjed** — iga failikirje temp-faili + `os.replace` kaudu; krahh ei saa konfigi ega vahemälu kärpida
- **Aegunud-lugemise kindlus** — 5-sekundiline UI-poll kutsub `refresh_known()` (loeb üle vaid `.saipen/`-faile, ilma kettaläbikäiguta). STATE.md muudatused ilmuvad sekunditega ilma täisskaneerimiseta
- **CSS-üleminekuteta** — kõik visuaalsed efektid (välk, kuumus, hover) on JS-i `hexBlend`-arvutused, rangelt vintage-teema null-animatsiooni piirides
- **Vintage-teema** — tume-pruunid pinnad, kuldne tekst/aktsendid, 3D-rahvid, null silumist, Verdana_m1 font

<br>

---

<br>

## 🧪 Arendus

```bash
# Kloonimine ja sisenemine
git clone https://github.com/vacterro/saipenview.git
cd saipenview

# Venv loomine ja install
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# Käivitamine
python -m saipenview
```

Üksikasjalik seadistus, koodikonventsioonid ja PR-i töövoog: [CONTRIBUTING.md](../../CONTRIBUTING.md).

### Nõuded

- **Windows 10 / 11** — WebView2 käituskeskkond (Win11-l eelinstallitud, Win10-l autoinstall)
- **Python 3.10+**
- Sõltuvused: `pystray`, `keyboard`, `pywebview`, `Pillow`, `watchdog`, `psutil`

<br>

---

<br>

## 📄 Litsents

MIT — vt [LICENSE](../../LICENSE).

<br>

---

<br>

<div align="center">
  <sub>Tehtud: 🐍 Python • 🖼️ pywebview • 🎨 Vintage Win95 esteetika</sub>

<br>

---

<br>

## 📸 Rohkem ekraanipilte

<p align="center">
  <img src="../../screenshots/detail-pane.png" alt="SAIPENVIEW detailipaneel" width="85%" style="border-radius: 4px; border: 1px solid #3a3020;">
  <br>
  <em>Detailipaneel: piletid, alamagendid ja failivaatur.</em>
</p>

<br>

</div>
