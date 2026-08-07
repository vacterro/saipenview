<div align="right">
  🌍 <a href="../../README.md">EN</a> | <a href="README.ar.md">AR</a> | <a href="README.bg.md">BG</a> | <a href="README.cs.md">CS</a> | <a href="README.da.md">DA</a> | <a href="README.de.md">DE</a> | <a href="README.ee.md">EE</a> | <a href="README.el.md">EL</a> | <a href="README.es.md">ES</a> | <a href="README.fi.md">FI</a> | <a href="README.fr.md">FR</a> | <a href="README.he.md">HE</a> | <a href="README.hi.md">HI</a> | <a href="README.hr.md">HR</a> | <a href="README.hu.md">HU</a> | <a href="README.id.md">ID</a> | <a href="README.it.md">IT</a> | <a href="README.ja.md">JA</a> | <a href="README.ko.md">KO</a> | <a href="README.nl.md">NL</a> | <a href="README.no.md">NO</a> | <a href="README.pl.md">PL</a> | <a href="README.pt.md">PT</a> | <strong>RO</strong> | <a href="README.ru.md">RU</a> | <a href="README.sk.md">SK</a> | <a href="README.sv.md">SV</a> | <a href="README.th.md">TH</a> | <a href="README.tr.md">TR</a> | <a href="README.uk.md">UK</a> | <a href="README.vi.md">VI</a> | <a href="README.zh.md">ZH</a> | <a href="README.zh-CN.md">ZH-CN</a> | <a href="README.ded.md">ДЕД</a>
</div>

<div align="center">
  <img src="../../screenshots/saipen_icon.png" alt="SAIPENVIEW" width="120" height="120">
  <h1 align="center">SAIPENVIEW</h1>
  <p align="center">
    <strong>Vizualizator în tray-ul desktop pentru fiecare proiect SAIPEN de pe calculatorul tău</strong>
    <br>
    Auto-descoperă proiectele <code>.saipen/</code> pe unitățile locale — fază în timp real, sarcină, blocaj, status git, tichete și sub-agenți.
    <br>
    Un tablou de bord vintage în stil Win95 auriu-întunecat.
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

## 🚀 Funcționalități

<table>
<tr>
<td width="50%">

### 🔍 Descoperire
- **Auto-scanare** a unităților locale pentru proiecte `.saipen/`
- **Rădăcini personalizate** — alege foldere sau unități întregi
- **Excluderi inteligente** — `node_modules`, `.git`, directoare de sistem
- **Rescanare în fundal** — interval configurabil (implicit 300s)
- **Worktree-uri conectate** — detectează git worktree-uri pentru o configurare ușoară

### 📊 Tablou de bord
- **Fază**, **sarcină**, **următoarea acțiune**, **blocaj** în timp real
- **Ramură Git** + indicator de stare modificată per proiect
- **Filtrare** după fază (Toate / Active / Finalizate / Blocate / personalizat)
- **Sortare** — Inteligentă, Recente, Cele mai vechi, A–Z, Z–A
- **Căutare** — filtru după nume/rădăcină + căutare profundă în tichete
- **Fixare** proiecte sus, **ascundere** cele irelevante
- **Evidențiere prin sclipire** — proiectele modificate luminează și dispar treptat în 20s
- **Colorare după activitate** — proiectele inactive se răcesc, cele proaspete se încălzesc

</td>
<td width="50%">

### 🧩 Sub-Agenți
- **Afișare imbricată** — `saiwiki`, `saihunt`, `saitranslate` indentate sub părinte
- **Contoare Outbox** — pregătite/blocate/schițe/revizuite dintr-o privire
- **Colectare cu un singur clic** — pliază intrările gata în proiectul principal
- **Avertisment de învechire** — detectează fișierele de protocol neactualizate

- **Agent Engine** - lansare `claude-code` (sau alte motoare: codex, aider, gemini, cline, goose, agy, generic_cli) într-un proiect
  - **Stare live** - stare de rulare/ieșire, CPU, timp scurs per proiect
  - **Consolă de ieșire** - ieșire tamponată a agentului (implicit 5000 linii), intrare stdin
  - **Kill / stop all** - oprirea procesului și oprire globală
  - **Protecție instanță unică** - o singură instanță a aplicației; a doua lansare reafișează fereastra
### 🎮 Interacțiune
- **Vizualizator de fișiere** — citește & editează STATE.md, BOARD.md, LOG.md
  - Mod Sursă (editabil) + Mod Cititor (rendat)
- **Tichete interactive** — butoanele Start / Finalizat actualizează BOARD.md în timp real
- **Acțiuni rapide** — contextual `npm run dev`, `cargo test`, etc.
- **Comenzi personalizate** — butoane de acțiune definite de utilizator
- **Secțiuni pliabile** — per proiect, persistente
- **Bara laterală redimensionabilă** — trage pentru redimensionare

### ⌨️ Comenzi rapide & Fereastră
- **Afișare/Ascundere** — `Ctrl+Alt+X` (configurabil)
- **Fixare la colțuri** - `Ctrl+Q` rotește SS → SD → JS → JD
- **Zoom** — `Ctrl+MouseWheel`, `Ctrl+`+`/`-`
- **Tray de sistem** — minimizare în tray, pornire ascunsă
- **Mereu deasupra** (Always-on-top) comutator
- **Pornire automată** — opțională la startul Windows
- **Mod fără cadre** — dezactivează bara de titlu pentru o vizualizare ultra-minimală

</td>
</tr>
</table>

<br>

---

<br>

## 🎯 Start Rapid

<table>
<tr>
<th width="33%">🐍 Rulare din sursă</th>
<th width="33%">📜 Scripturi de lansare</th>
<th width="33%">📦 Instalare (viitor)</th>
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

| Script | Comportament |
|---|---|
| `run.vbs` | Ascuns (doar tavă), tăcut |
| `run.bat` | Lansare în tavă; consola vizibilă doar la configurarea unică venv/dependențe |
Ambele creează automat `.venv` și instalează dependențele.

</td>
<td>

```bash
pip install saipenview
saipenview
```
În curând ✨

</td>
</tr>
</table>

<br>

---

## ⌨️ Utilizare

| Acțiune | Cum |
|---|---|
| **Afișare / Ascundere** | `Ctrl+Alt+X` sau `Alt+F15` (ambele configurabile) |
| **Fixare în colț** | `Ctrl+Q` - rotește Sus-Stânga → Sus-Dreapta → Jos-Stânga → Jos-Dreapta |
| **Oprire de urgență** | `Ctrl+Shift+Alt+Q` — închide forțat procesul |
| **Mărire / Micșorare** | `Ctrl+MouseWheel` sau `Ctrl` + `+` / `-` |
| **Resetare zoom** | `Ctrl+0` |
| **Comutare bară de instrumente** | `Alt+D` — restrânge/extinde panoul barei de instrumente |
| **Căutare proiecte** | Tastează în caseta de căutare; bifează `D` pentru căutare profundă în tichete |
| **Filtrare** | Meniu derulant: Toate / Active / Finalizate / Blocate, sau clic pe o pastilă de fază |
| **Sortare** | Inteligentă / Recente / Cele mai vechi / A–Z / Z–A |
| **Rescanare** | Clic pe `Rescanare` sau așteaptă temporizatorul în fundal (implicit 300s) |
| **Răsfoire folder** | Clic pe `Răsfoire` pentru a adăuga un folder la setul de scanare |
| **Setări** | Butonul ⚙ deschide fereastra modală de setări |
| **Wiki ajutor** | Butonul `?` deschide mini-wiki-ul integrat |
| **Clic dreapta pe proiect** | Copiază calea rădăcină, filtrează după fază, deschide folderul |
| **Dublu clic pe secțiune** | Deschide fișierul conectat (STATE.md, BOARD.md, LOG.md) |
| **Tragere fereastră** | Trage bara de titlu (sau oriunde în modul fără cadre) |

### Ferestre Modale

| Modal | Ce face |
|---|---|
| **Setări** | Zoom, comenzi rapide, ajustare scanare, pornire automată, mereu deasupra, font, comutator sclipire, mod implicit vizualizator fișiere, comenzi personalizate, localizare, rădăcini scanare |
| **Vizualizator Fișiere** | Citește & editează STATE.md, BOARD.md, LOG.md — mod Sursă (brut) sau Cititor (rendat) |
| **Ajutor** | Mini-wiki complet ce acoperă fiecare funcționalitate, comandă rapidă și concept |
| **Confirmare** | Dialog DOM în stil vintage (înlocuiește native-ul `confirm()`) |

<br>

---

## 🧬 Protocolul SAIPEN

SAIPENVIEW este un companion pentru proiectele care utilizează **Protocolul SAIPEN** — un cadru de tip automat cu stări finite care ghidează agenții AI prin activitatea proiectului în faze definite:

```
INIT → PLAN → SCOUT → BUILD → REVIEW → VERIFY → SHIP → DONE
                 ↓              ↓
            HUNT / CLEAN    VALIDATE
```

`ADD`, `MARKHUNT`, `TRANSLATE`, `PREPARE` există de asemenea - vocabularul complet și tabelul de tranziții sunt în `saipenview/protocol.py` (`BLOCKED` este accesibil din majoritatea fazelor).
Fiecare proiect SAIPEN își stochează starea în trei fișiere canonice:

| Fișier | Scop |
|---|---|
| `.saipen/STATE.md` | Frontmatter lizibil de mașină — fază, sarcină, următoarea acțiune, blocaj |
| `.saipen/BOARD.md` | Tablou de tichete — secțiunile ÎN CURS / DE FĂCUT / FINALIZAT / BLOCAT |
| `.saipen/LOG.md` | Jurnal cronologic de evenimente — fiecare comandă și rezultatul ei |

**Agenții SubSaipen** (`saiwiki`, `saihunt`, `saitranslate`) trăiesc în `.saipen/extensions/subs/` și comunică prin `kitchen/OUTBOX.md` — magistrala de mesaje între agenți integrată în protocol. SAIPENVIEW le descoperă pe toate și rendează un tablou de bord unic.

### Conformitate

A arăta ceea ce *spune* un proiect este doar jumătate din poveste. Un proiect poate fi citit perfect
în listă — o fază, o sarcină, o următoare acțiune — în timp ce se află într-o stare pe care protocolul
o respinge, și până când nu rulai `tools/validate.py` manual nu exista niciun mod de a le deosebi
pe cele două.

Fiecare rând poartă o insignă de verdict, iar panoul de detalii listează ce este în neregulă:

| Verdict | Semnificație |
|---|---|
| `OK` | Nimic deosebit găsit în fișierele `.saipen/` proprii ale acestui proiect |
| `N WARNS` | Legal, dar în derivă — un punct de control învechit, un verb LOG nestandard |
| `N FAILS` | O stare pe care protocolul o respinge: un `WAIT:` fără categorie, o casetă de bifat neconformă cu secțiunea sa, un `needs:` care indică un tichet inexistent, un `STATE.md` în UTF-16 pe care niciun alt instrument SAIPEN nu îl poate citi |

Fiecare constatare numește regula, fișierul și linia, precum și clauza din care provine,
astfel încât să poată fi verificată mai degrabă decât luată pe încredere.

Aceasta este o **a doua opinie, nu un înlocuitor** pentru `tools/validate.py`. Re-verifică
doar ceea ce fișierele proprii ale unui proiect pot decide și evaluează în raport cu o copie
a vocabularului protocolului — astfel încât versiunea SAIPEN din care a fost citită este
tipărită sub fiecare verdict. Vizualizatorul are voie să rămână în urmă față de protocol. Nu îi este
permis să rămână în urmă în tăcere.

> 💡 *Numele „SAIPENVIEW” spune totul — oferă o **perspective (view)** în fiecare proiect **SAIPEN** de pe calculatorul tău.*

<br>

---

## ⚙️ Configurare

Configurația este portabilă — stocată lângă aplicație, nu în `%APPDATA%`:

```
saipenview/_data/config.json
```

Valori implicite principale (abreviat - dicționarul complet `DEFAULTS` este în `saipenview/config.py`):

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

Setează `scan_roots: null` pentru a autodetecta toate unitățile locale.  
Setează o listă de căi (de ex. `["V:\\", "D:\\proiecte"]`) pentru a limita scanarea.  
`default_engine` / `engine_overrides` / `agent_output_buffer_size` conduc Agent Engine (vezi Funcții).  
Toate setările sunt de asemenea configurabile prin modalul **Setări** din aplicație.

<br>

---

## 🏗️ Arhitectură

```
saipenview/
├── app.py              Cablaj de intrare - tavă, hotkey, fereastră, api, protecție instanță unică
├── api.py              Pod pywebview orientat JS (66 metode publice)
├── scanner.py          Parcurgere unități + buclă de rescanare în fundal
├── parser.py           Analiză STATE.md / BOARD.md / LOG.md
├── textio.py           Un singur cititor pentru fiecare fișier .saipen/ — BOM, UTF-16, cp1251
├── protocol.py         Vocabularul închis al protocolului + BASELINE_VERSION
├── conformance.py      Evaluează un proiect în raport cu acest vocabular
├── config.py           Încărcare/salvare setări (scrieri atomice)
├── tray.py             Iconiță de tray pystray + meniu
├── hotkey.py           Înregistrare comenzi rapide globale (biblioteca keyboard)
├── autostart.py        Gestionare pornire automată în Registrul Windows
├── zone_picker.py      Suprapunere fixare colț Ctrl+Q (tkinter)
├── events.py           Bus de evenimente în proces (EventBus)
├── guard.py            Blocare instanță unică + predarea cererii de afișare
├── git_diff.py         Diff / commit / revert al arborelui de lucru pentru acțiuni agenți
├── runtime.py          Agent Engine - manager de procese pentru agenții lansați
├── watcher.py          Supraveghetor de fișiere Watchdog pentru fișierele .saipen/
├── engines/            Agent Engine - motoare CLI suportate (claude-code, codex,
│                       aider, gemini, cline, goose, agy, generic_cli)
├── ui/
│   ├── window.py       Fereastră pywebview — afișare/ascundere/comutare/fixare
│   └── static/
│       ├── index.html
│       ├── style.css   Temei vintage Win95 auriu-întunecat
│       └── app.js      Logică frontend (~3300 linii)
├── assets/
│   └── tray_icon.png
├── screenshots/        Capturi de ecran README
└── _data/              Configurație runtime + cache (ignorate de git)
```

### Principii de proiectare

- **Proces unic** — fără IPC în fundal, fără server separat; un singur proces Python găzduiește atât fereastra WebView2, cât și bucla de scanare într-un `ThreadPoolExecutor`
- **Scrieri atomice** — fiecare scriere de fișier folosește fișier temporar + `os.replace`; o prăbușire nu poate trunchia niciodată configurația sau cache-ul
- **Siguranță la citiri învechite** — sondarea UI la 5 secunde apelează `refresh_known()` (recitește doar fișierele `.saipen/`, fără parcurgere de directoare). Editările în STATE.md apar în câteva secunde fără a declanșa o scanare completă a unității
- **Fără tranziții CSS** — toate efectele vizuale (sclipire, căldură, survol) sunt recalculări `hexBlend` gestionate din JavaScript, respectând cu strictețe constrângerea de zero animații a temei vintage
- **Temei Vintage** — suprafețe maro închis, text/accentuări aurii, borduri 3D bizotate, zero anti-aliasing, font Verdana_m1

<br>

---

## 🧪 Dezvoltare

```bash
# Clonare & intrare
git clone https://github.com/vacterro/saipenview.git
cd saipenview

# Creare venv & instalare
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# Rulare
python -m saipenview
```

Pentru configurare detaliată, convenții de cod și flux de lucru PR, vezi [CONTRIBUTING.md](../../CONTRIBUTING.md).

### Cerințe

- **Windows 10 / 11** — Mediu de rulare WebView2 (preinstalat pe Win11, se instalează automat pe Win10)
- **Python 3.10+**
- Dependențe: `pystray`, `keyboard`, `pywebview`, `Pillow`, `watchdog`, `psutil`

<br>

---

## 📄 Licență

MIT — vezi [LICENSE](../../LICENSE).

<br>

---

<div align="center">
  <sub>Construit cu 🐍 Python • 🖼️ pywebview • 🎨 Estetică Vintage Win95</sub>

<br>

---

## 📸 Mai multe capturi de ecran

<p align="center">
  <img src="../../screenshots/detail-pane.png" alt="Panou de detalii SAIPENVIEW" width="85%" style="border-radius: 4px; border: 1px solid #3a3020;">
  <br>
  <em>Panou de detalii cu tichete, sub-agenți și vizualizator de fișiere.</em>
</p>

<br>

</div>
