<div align="right">
  🌍 <strong>EN</strong> | <a href="README.ru.md">RU</a> | <a href="README.ee.md">EE</a> | <a href="README.ded.md">ДЕД</a> | <a href="README.ja.md">JA</a>
</div>

<div align="center">
  <img src="screenshots/saipen_icon.png" alt="SAIPENVIEW" width="120" height="120">
  <h1 align="center">SAIPENVIEW</h1>
  <p align="center">
    <strong>Asztali tálca-megjelenítő a gépeden lévő összes SAIPEN projekthez</strong>
    <br>
    Automautikusan felderíti a <code>.saipen/</code> projekteket a helyi meghajtókon — élő fázis, feladat, elakadás, git státusz, hibajegyek és al-ágensek.
    <br>
    Egyetlen klasszikus sötét-arany Win95 stílusú vezérlőpult.
  </p>
  <p>
    <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.10%2B-blue?style=flat-square&logo=python&logoColor=white" alt="Python"></a>
    <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="License"></a>
    <a href="https://github.com/vacterro/saipenview"><img src="https://img.shields.io/badge/platform-Windows-orange?style=flat-square&logo=windows&logoColor=white" alt="Platform"></a>
    <a href="https://github.com/vacterro/saipenview/releases"><img src="https://img.shields.io/github/v/release/vacterro/saipenview?style=flat-square&include_prereleases" alt="Release"></a>
    <a href="https://github.com/vacterro/saipenview/actions"><img src="https://img.shields.io/github/actions/workflow/status/vacterro/saipenview/ci.yml?branch=main&style=flat-square&logo=github" alt="CI"></a>
    [🤍 Fejlesztő támogatása](https://buymeacoffee.com/vacuum34)
  </p>
</div>

<br>

---

<br>

## ✨ Gyors áttekintés

<p align="center">
  <img src="screenshots/dashboard.png" alt="SAIPENVIEW Dashboard Screenshot" width="85%" style="border-radius: 4px; border: 1px solid #3a3020;">
  <br>
  <em>Minden SAIPEN projekt, al-ágens, hibajegy és git státusz — egyetlen nézetben.</em>
</p>

<br>

---

## 🚀 Funkciók

<table>
<tr>
<td width="50%">

### 🔍 Felderítés
- **Automata szkennelés** a helyi meghajtókon a `.saipen/` projektek után
- **Egyéni gyökérkönyvtárak** — válassz mappákat vagy teljes meghajtókat
- **Okos kizárások** — `node_modules`, `.git`, rendszerkönyvtárak
- **Háttérbeli újraszkennelés** — testreszabható időköz (alapértelmezett 300s)
- **Kapcsolt worktree-k** — felismeri a git worktree-ket a könnyű beállításért

### 📊 Vezérlőpult
- Élő **fázis**, **feladat**, **következő lépés**, **elakadás**
- **Git ág** + módosított állapot jelző projektenként
- **Szűrés** fázis szerint (Mind / Élő / Kész / Elakadt / egyéni)
- **Rendezés** — Okos, Legújabb, Legrégebbi, A–Z, Z–A
- **Keresés** — név/útvonal szűrő + mély hibajegy-keresés
- Projektek **rögzítése** felülre, irrelevánsak **elrejtése**
- **Villogó kiemelés** — a megváltozott projektek világítanak és 20mp alatt elhalványulnak
- **Hőmérsékleti színezés** — inaktív projektek hűlnek, friss projektek melegszenek

</td>
<td width="50%">

### 🧩 Al-ágensek
- **Beágyazott megjelenítés** — `saiwiki`, `saihunt`, `saitranslate` a szülő alatt behúzva
- **Kimenő fiók számlálók** — ready/blocked/draft/reviewed egy pillantásra
- **Egykattintásos gyűjtés** — kész elemek bevonása a főprojektbe
- **Elévülési figyelmeztetés** — felismeri az elavult protokollfájlokat

- **Agent Engine** - `claude-code` indítása (vagy más motorok: codex, aider, gemini, cline, goose, agy, generic_cli) egy projektben
  - **Élő állapot** - futó/kilépett állapot, CPU, eltelt idő projektenként
  - **Kimeneti konzol** - pufferelt ügynökkimenet (alapértelmezés 5000 sor), stdin bemenet
  - **Kill / stop all** - folyamat leállítása és globális megállítás
  - **Egypéldányos védelem** - csak egy alkalmazáspéldány; a második indítás újra megmutatja az ablakot
### 🎮 Interakció
- **Fájlmegjelenítő** — STATE.md, BOARD.md, LOG.md olvasása és szerkesztése
  - Forrás mód (szerkeszthető) + Olvasó mód (renderelt)
- **Interaktív hibajegyek** — a Start / Kész gombok élőben frissítik a BOARD.md-t
- **Gyorsműveletek** — kontextusfüggő `npm run dev`, `cargo test`, stb.
- **Egyéni parancsok** — felhasználó által definiált műveletgombok
- **Összecsukható szakaszok** — projektenként, megőrizve
- **Átméretezhető oldalsáv** — húzással átméretezhető

### ⌨️ Gyorsbillentyűk és Ablak
- **Megjelenítés/Elrejtés** — `Ctrl+Alt+X` (beállítható)
- **Sarokhoz igazítás** - `Alt+F14` leptet: BF → JF → BA → JA
- **Nagyítás** — `Ctrl+Egérgörgő`, `Ctrl+`+`/`-`
- **Rendszertálca** — kicsinyítés a tálcára, indítás rejtve
- **Mindig felül** kapcsoló
- **Automatikus indítás** — opcionális Windows indításkor
- **Keret nélküli mód** — címsor kikapcsolása az ultra-minimális nézethez

</td>
</tr>
</table>

<br>

---

<br>

## 🎯 Gyorsútmutató

<table>
<tr>
<th width="33%">🐍 Futtatás forrásból</th>
<th width="33%">📜 Indítószkriptek</th>
<th width="33%">📦 Telepítés (jövőbeli)</th>
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

| Szkript | Viselkedés |
|---|---|
| `run.vbs` | Rejtett (csak tálca), csendes |
| `run.bat` | Indítás a tálcára; konzol csak az egyszeri venv/függőség beállításkor látható |
Mindkettő automatikusan létrehozza a `.venv`-et és telepíti a függőségeket.

</td>
<td>

```bash
pip install saipenview
saipenview
```
Hamarosan ✨

</td>
</tr>
</table>

<br>

---

## ⌨️ Használat

| Művelet | Hogyan |
|---|---|
| **Megjelenítés / Elrejtés** | `Ctrl+Alt+X` vagy `Alt+F15` (mindkettő beállítható) |
| **Sarokhoz igazítás** | `Alt+F14` - leptet: Bal-Fent → Jobb-Fent → Bal-Lent → Jobb-Lent |
| **Kényszerített kilépés** | `Ctrl+Shift+Alt+Q` — a folyamat azonnali leállítása |
| **Nagyítás / Kicsinyítés** | `Ctrl+Egérgörgő` vagy `Ctrl` + `+` / `-` |
| **Nagyítás alaphelyzetbe** | `Ctrl+0` |
| **Eszköztár összecsukása** | `Alt+D` — az eszköztár panel összecsukása/kibontása |
| **Projektek keresése** | Írj a keresőmezőbe; jelöld be a `D`-t a mély hibajegy-kereséshez |
| **Szűrés** | Lekapcsolható lista: Mind / Élő / Kész / Elakadt, vagy kattints egy fázis jelvényre |
| **Rendezés** | Okos / Legújabb / Legrégebbi / A–Z / Z–A |
| **Újraszkennelés** | Kattints az `Újraszkennelés` gombra vagy várd meg a háttéridőzítőt (alapértelmezett 300s) |
| **Mappa tallózása** | Kattints a `Tallózás` gombra mappa hozzáadásához a szkennelési készlethez |
| **Beállítások** | A ⚙ gomb megnyitja a beállítások ablakot |
| **Súgó wiki** | A `?` gomb megnyitja a beépített mini-wikit |
| **Jobb klikk a projekten** | Gyökérútvonal másolása, szűrés fázis szerint, mappa megnyitása |
| **Dupla klikk a szakaszon** | Megnyitja a kapcsolódó fájlt (STATE.md, BOARD.md, LOG.md) |
| **Ablak húzása** | Húzd a címsort (vagy bárhol keret nélküli módban) |

### Párbeszédablakok

| Párbeszédablak | Mit csinál |
|---|---|
| **Beállítások** | Nagyítás, gyorsbillentyűk, szkennelés finomhangolása, automatikus indítás, mindig felül, betűtípus, villogás kapcsoló, alapértelmezett fájlmegjelenítő, egyéni parancsok, nyelv, szkennelési gyökerek |
| **Fájlmegjelenítő** | STATE.md, BOARD.md, LOG.md olvasása és szerkesztése — Forrás (nyers) vagy Olvasó (renderelt) mód |
| **Súgó** | Részletes mini-wiki minden funkcióról, billentyűparancsról és koncepcióról |
| **Megerősítés** | Klasszikus stílusú DOM párbeszédablak (helyettesíti a natív `confirm()`-ot) |

<br>

---

## 🧬 SAIPEN Protokoll

A SAIPENVIEW a **SAIPEN Protokollt** használó projektek kísérője — egy állapotgép keretrendszer, amely meghatározott fázisokban vezeti az AI ágenseket a projektmunkán keresztül:

```
INIT → PLAN → SCOUT → BUILD → REVIEW → VERIFY → SHIP → DONE
                 ↓              ↓
            HUNT / CLEAN    VALIDATE
```

Az `ADD`, `MARKHUNT`, `TRANSLATE`, `PREPARE` is létezik - a teljes szókincs és átmenettábla a `saipenview/protocol.py`-ben van (`BLOCKED` a legtöbb fázisból elérhető).
Minden SAIPEN projekt három kanonikus fájlban tárolja az állapotát:

| Fájl | Cél |
|---|---|
| `.saipen/STATE.md` | Géppel olvasható lényeg — fázis, feladat, következő lépés, elakadás |
| `.saipen/BOARD.md` | Hibajegy tábla — DOING / TODO / DONE / BLOCKED szakaszok |
| `.saipen/LOG.md` | Kronológiai eseménynapló — minden parancs és annak eredménye |

A **SubSaipen ágensek** (`saiwiki`, `saihunt`, `saitranslate`) a `.saipen/extensions/subs/` könyvtárban élnek, és a `kitchen/OUTBOX.md`-n keresztül kommunikálnak — ez a protokoll beépített ágensek közötti üzenetbusza. A SAIPENVIEW mindegyiket felderíti és egy egységes vezérlőpultot jelenít meg.

### Megfelelőség (Conformance)

Az, hogy a projekt mit *állít*, még csak a féligazság. Egy projekt tökéletesen olvashatónak tűnhet a listában — fázis, feladat, következő lépés —, miközben olyan állapotban van, amit a protokoll visszautasít, és amíg kézzel nem futtattad a `tools/validate.py`-t, nem lehetett megkülönböztetni a kettőt.

Minden sor tartalmaz egy ítélet jelvényt, és a részletek panel felsorolja a hibákat:

| Ítélet | Jelentés |
|---|---|
| `OK` | Nincs hiba a projekt saját `.saipen/` fájljaiban |
| `N WARNS` | Szabályos, de eltérő — elavult ellenőrzési pont, nem szabványos LOG ige |
| `N FAILS` | A protokoll által elutasított állapot: kategória nélküli `WAIT:`, a szakaszával ellentmondó jelölőnégyzet, nem létező hibajegyre mutató `needs:`, vagy olyan UTF-16 `STATE.md`, amelyet más SAIPEN eszköz nem tud elolvasni |

Minden megállapítás megnevezi a szabályt, a fájlt és a sort, valamint a záradékot, ahonnan származik, így vakbizalom helyett kikereshető.

Ez egy **másodlagos vélemény, nem pedig a `tools/validate.py` helyettesítése**. Csak azt ellenőrzi újra, amit a projekt saját fájljai el tudnak dönteni, és a protokoll szókincsének másolata alapján értékel — így az a SAIPEN verzió, amelyből beolvasták, minden ítélet alatt megjelenik. A megjelenítő lemaradhat a protokolltól. Csendben lemaradnia viszont nem szabad.

> 💡 *A "SAIPENVIEW" név mindent elmond — **betekintést (view)** nyújt a gépeden lévő összes **SAIPEN** projektbe.*

<br>

---

## ⚙️ Beállítások

A konfiguráció hordozható — az alkalmazás mellett van tárolva, nem a `%APPDATA%` mappában:

```
saipenview/_data/config.json
```

Fő alapértelmezett értékek (rövidítve - a teljes `DEFAULTS` szótár a `saipenview/config.py`-ben van):

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

Állítsd a `scan_roots: null` értéket a helyi meghajtók automatikus felderítéséhez.  
Állítsd útvonalak listájára (pl. `["V:\\", "D:\\projects"]`) a szkennelés korlátozásához.  
A `default_engine` / `engine_overrides` / `agent_output_buffer_size` vezérli az Agent Engine-t (lásd Funkciók).  
Minden beállítás módosítható az alkalmazás **Beállítások** ablakában is.

<br>

---

## 🏗️ Architektúra

```
saipenview/
├── app.py              Belépési bekötés - tálca, gyorsbillentyű, ablak, api, egypéldányos védelem
├── api.py              JS-felőli pywebview híd (66 publikus metódus)
├── scanner.py          Meghajtó bejárás + háttérbeli újraszkennelési ciklus
├── parser.py           STATE.md / BOARD.md / LOG.md feldolgozás
├── textio.py           Egységes olvasó minden .saipen/ fájlhoz — BOM, UTF-16, cp1251
├── protocol.py         A protokoll zárt szókincsei + BASELINE_VERSION
├── conformance.py      A projekt értékelése a szókincsek alapján
├── config.py           Beállítások betöltése/mentése (atomi írások)
├── tray.py             pystray rendszertálca ikon + menü
├── hotkey.py           Globális gyorsbillentyű regisztráció (keyboard lib)
├── autostart.py        Windows Registry automatikus indítás kezelése
├── zone_picker.py      Alt+F14 sarokhoz igazítás overlay (tkinter)
├── events.py           Folyamaton belüli eseménybusz (EventBus)
├── guard.py            Egypéldányos zár + megjelenítési kérelem átadása
├── git_diff.py         Munkafa diff / commit / revert ügynökműveletekhez
├── runtime.py          Agent Engine - indított ügynökök folyamatkezelője
├── watcher.py          Watchdog fájlfigyelő a .saipen/ fájlokra
├── engines/            Agent Engine - támogatott CLI-motorok (claude-code, codex,
│                       aider, gemini, cline, goose, agy, generic_cli)
├── ui/
│   ├── window.py       pywebview ablak — megjelenítés/elrejtés/kapcsolás/igazítás
│   └── static/
│       ├── index.html
│       ├── style.css   Klasszikus sötét-arany Win95 téma
│       └── app.js      Frontend logika (~3300 sor)
├── assets/
│   └── tray_icon.png
├── screenshots/        README képernyőképek
└── _data/              Futtatási konfiguráció + gyorsítótár (gitignored)
```

### Tervezési elvek

- **Egyetlen folyamat** — nincs háttérbeli IPC, nincs külön szerver; egyetlen Python folyamat gazdája a WebView2 ablaknak és a szkennelési ciklusnak egy `ThreadPoolExecutor`-ban
- **Atomi írások** — minden fájlírás ideiglenes fájlt + `os.replace`-t használ; az összeomlás sosem csonkíthatja a konfigurációt vagy a gyorsítótárat
- **Elavult olvasás elleni védelem** — az 5 másodperces UI lekérdezés a `refresh_known()`-t hívja (csak a `.saipen/` fájlokat olvassa újra, nem járja be a könyvtárat). A STATE.md szerkesztései másodperceken belül megjelennek anélkül, hogy teljes meghajtó-szkennelést váltanának ki
- **Nincsenek CSS átmenetek** — minden vizuális effektus (villanás, hőmérséklet, lebegés) JavaScript által vezérelt `hexBlend` újraszámítás, szigorúan követve a klasszikus téma animációmentes megkötését
- **Klasszikus téma** — sötétbarna felületek, arany szövegek/kiemelések, 3D ferde szegélyek, élsimítás nélkül, Verdana_m1 betűtípus

<br>

---

## 🧪 Fejlesztés

```bash
# Klónozás és belépés
git clone https://github.com/vacterro/saipenview.git
cd saipenview

# Venv létrehozása és telepítés
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# Futtatás
python -m saipenview
```

A részletes beállításokért, kódolási konvenciókért és a PR munkamenetért lásd a [CONTRIBUTING.md](CONTRIBUTING.md) fájlt.

### Követelmények

- **Windows 10 / 11** — WebView2 futtatókörnyezet (előre telepítve Win11-en, automatikusan települ Win10-en)
- **Python 3.10+**
- Függőségek: `pystray`, `keyboard`, `pywebview`, `Pillow`, `watchdog`, `psutil`

<br>

---

## 📄 Licenc

MIT — lásd: [LICENSE](LICENSE).

<br>

---

<div align="center">
  <sub>Készült: 🐍 Python • 🖼️ pywebview • 🎨 Klasszikus Win95 esztétika</sub>

<br>

---

## 📸 További képernyőképek

<p align="center">
  <img src="screenshots/detail-pane.png" alt="SAIPENVIEW Detail Pane" width="85%" style="border-radius: 4px; border: 1px solid #3a3020;">
  <br>
  <em>Részletek panel hibajegyekkel, al-ágensekkel és fájlmegjelenítővel.</em>
</p>

<br>

</div>
