<div align="right">
  <a href="README.md">EN</a> | <a href="README.ru.md">RU</a> | рџЊЌ <strong>EE</strong> | <a href="README.ded.md">Р”Р•Р”</a> | <a href="README.ja.md">JA</a>
</div>

<div align="center">
  <img src="screenshots/saipen_icon.png" alt="SAIPENVIEW" width="120" height="120">
  <h1 align="center">SAIPENVIEW</h1>
  <p align="center">
    <strong>TГ¶Г¶laua salvevaatur iga SAIPEN projekti jaoks sinu masinas</strong>
    <br>
    Tuvastab automaatselt <code>.saipen/</code> projektid kohalikel ketastel вЂ” reaalajas faas, Гјlesanded, blokeerijad, giti staatus, piletid ja alam-agendid.
    <br>
    Гњks vintage tumekuldne Win95-stiilis juhtpaneel.
  </p>
  <p>
    <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.10%2B-blue?style=flat-square&logo=python&logoColor=white" alt="Python"></a>
    <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="Litsents"></a>
    <a href="https://github.com/vacterro/saipenview"><img src="https://img.shields.io/badge/platform-Windows-orange?style=flat-square&logo=windows&logoColor=white" alt="Platvorm"></a>
    <a href="https://github.com/vacterro/saipenview/releases"><img src="https://img.shields.io/github/v/release/vacterro/saipenview?style=flat-square&include_prereleases" alt="VГ¤ljalase"></a>
    <a href="https://github.com/vacterro/saipenview/actions"><img src="https://img.shields.io/github/actions/workflow/status/vacterro/saipenview/ci.yml?branch=main&style=flat-square&logo=github" alt="CI"></a>
    [рџ¤Ќ Toeta arendajat](https://buymeacoffee.com/vacuum34)
  </p>
</div>

<br>

---

<br>

## вњЁ Esmapilgul

<p align="center">
  <img src="screenshots/dashboard.png" alt="SAIPENVIEW armatuurlaua ekraanipilt" width="85%" style="border-radius: 4px; border: 1px solid #3a3020;">
  <br>
  <em>Iga SAIPEN projekt, alam-agent, pilet ja git staatus вЂ” kГµik Гјhes vaates.</em>
</p>

<br>

---

## рџљЂ Funktsioonid

<table>
<tr>
<td width="50%">

### рџ”Ќ Avastamine
- **Automaatne skannimine** kohalikel ketastel `.saipen/` projektide leidmiseks
- **Kohandatud teed** вЂ” vali kaustad vГµi terved kettad
- **Nutikas vГ¤listamine** вЂ” jГ¤tab vahele `node_modules`, `.git`, sГјsteemikaustad
- **Taustaskannimine** вЂ” seadistatav intervall (vaikimisi 300s)
- **Seotud tГ¶Г¶puud** вЂ” tuvastab git tГ¶Г¶puud (worktrees)

### рџ“Љ Juhtpaneel
- Reaalajas **faas**, **Гјlesanne**, **jГ¤rgmine tegevus**, **blokeerija**
- **Giti haru** + mustade muudatuste indikaator iga projekti kohta
- **Filtreeri** faasi jГ¤rgi (KГµik / Aktiivsed / Valmis / Blokeeritud / kohandatud)
- **Sorteeri** вЂ” Nutikas, Hiljutised, Vanimad, AвЂ“Z, ZвЂ“A
- **Otsi** вЂ” nime/tee filter + piletite sГјvaotsing
- **Kinnita** projektid Гјles, **peida** ebaolulised
- **EsiletГµstu sГ¤hvatus** вЂ” muudetud projektid hГµГµguvad 20s
- **SoojusvГ¤rvid** вЂ” vanad projektid jahtuvad, vГ¤rsked soojenevad

</td>
<td width="50%">

### рџ§© Alam-agendid
- **Pesastatud kuva** вЂ” `saiwiki`, `saihunt`, `saitranslate` kuvatakse emaprojekti all
- **Outboxi loendurid** вЂ” nГ¤itab, mis on valmis, blokeeritud, mustand vГµi Гјlevaadatud
- **Гњhe klГµpsuga kogumine** вЂ” tГµmba valmis kanded pГµhiprojekti
- **Vananemise hoiatus** вЂ” tuvastab aegunud protokolli failid

### рџЋ® Suhtlus
- **Failivaatleja** вЂ” loe ja muuda STATE.md, BOARD.md, LOG.md
  - LГ¤htekoodi reЕѕiim (muudetav) + Lugeja reЕѕiim (renderdatud)
- **Interaktiivsed piletid** вЂ” Start / Done nupud uuendavad BOARD.md otse
- **Kiired tegevused** вЂ” kontekstipГµhised `npm run dev`, `cargo test` jne
- **Kohandatud kГ¤sud** вЂ” kasutaja mГ¤Г¤ratud tegevusnupud
- **Ahendatavad jaotised** вЂ” projektipГµhiselt salvestatud
- **Muudetava suurusega kГјlgriba** вЂ” lohista suuruse muutmiseks

### вЊЁпёЏ Kiirklahvid ja Aken
- **NГ¤ita/Peida** вЂ” `Ctrl+Alt+X` (seadistatav)
- **Kinnita nurka** вЂ” `Ctrl+Q` liigub ГњV в†’ ГњP в†’ AV в†’ AP
- **Suumi** вЂ” `Ctrl+Hiirerullik`, `Ctrl+`+`/`-`
- **SГјsteemisalv** вЂ” minimeerib salve, kГ¤ivitub peidetult
- **Alati peal** lГјliti
- **Automaatne kГ¤ivitus** вЂ” valikuline Windowsi sisselogimisel
- **Raamita reЕѕiim** вЂ” peida tiitliriba minimalistliku vaate jaoks

</td>
</tr>
</table>

<br>

---

<br>

## рџЋЇ Kiire alustamine

<table>
<tr>
<th width="33%">рџђЌ KГ¤ivita lГ¤htekoodist</th>
<th width="33%">рџ“њ KГ¤ivitusskriptid</th>
<th width="33%">рџ“¦ Paigalda (tulemas)</th>
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

| Skript | KГ¤itumine |
|---|---|
| `run.vbs` | Peidetud (ainult salves) |
| `run.bat` | NГ¤htav (konsool avatud) |
MГµlemad loovad `.venv` ja paigaldavad sГµltuvused.

</td>
<td>

```bash
pip install saipenview
saipenview
```
Varsti saadaval вњЁ

</td>
</tr>
</table>

<br>

---

## вЊЁпёЏ Kasutamine

| Tegevus | Kuidas |
|---|---|
| **NГ¤ita / Peida** | `Ctrl+Alt+X` vГµi `Alt+F15` (mГµlemad seadistatavad) |
| **Nurka kinnitamine** | `Ctrl+Q` вЂ” liigub Гњlemine-Vasak в†’ Гњlemine-Parem в†’ Alumine-Vasak в†’ Alumine-Parem |
| **HГ¤dapeatamine** | `Ctrl+Shift+Alt+Q` вЂ” sunnib protsessi sulgema |
| **Suumi sisse / vГ¤lja** | `Ctrl+Hiirerullik` vГµi `Ctrl` + `+` / `-` |
| **Suumi nullimine** | `Ctrl+0` |
| **TГ¶Г¶riistariba lГјlitamine** | `Alt+D` вЂ” ahenda/laienda paneeli |
| **Otsi projekte** | Kirjuta otsingukasti; mГ¤rgi `S` piletite sГјvaotsinguks |
| **Filtreeri** | RippmenГјГј: KГµik / Aktiivsed / Valmis / Blokeeritud |
| **Sorteeri** | Nutikas / Hiljutised / Vanimad / AвЂ“Z / ZвЂ“A |
| **Reskanni** | KlГµpsa `Reskanni` vГµi oota taustataimerit (vaikimisi 300s) |
| **Sirvi kausta** | KlГµpsa `Sirvi` kausta lisamiseks skannimisalasse |
| **Seaded** | вљ™ nupp avab seadete akna |
| **Abi ja viki** | `?` nupp avab sisseehitatud viki |
| **ParemklГµps projektil** | Kopeeri juurtee, filtreeri faasi jГ¤rgi, ava kaust |
| **TopeltklГµps jaotisel** | Avab seotud faili (STATE.md, BOARD.md, LOG.md) |
| **Lohista akent** | Lohista tiitliribast (vГµi ГјkskГµik kust raamita reЕѕiimis) |

### Modaalid

| Modaal | Mida see teeb |
|---|---|
| **Seaded** | Suum, kiirklahvid, skannimise hГ¤Г¤lestus, automaatkГ¤ivitus, font, kohandatud kГ¤sud jne |
| **Failivaatleja** | Loe ja muuda STATE, BOARD, LOG вЂ” Allika (toores) vГµi Lugeja (renderdatud) reЕѕiim |
| **Abi** | Sisseehitatud miniviki kГµigi funktsioonide ja mГµistetega |
| **Kinnitus** | Vintage-stiilis DOM dialoog |

<br>

---

## рџ§¬ SAIPEN Protokoll

SAIPENVIEW on kaaslane projektidele, mis kasutavad **SAIPEN Protokolli** вЂ” olekumasina raamistikku, mis juhib tehisintellekti agente lГ¤bi tГ¶Г¶faaside:

```
INIT в†’ PLAN в†’ SCOUT в†’ BUILD в†’ REVIEW в†’ VERIFY в†’ SHIP в†’ DONE
                         в†“
                    HUNT / CLEAN
```

Iga projekt hoiab oma olekut kolmes failis:

| Fail | EesmГ¤rk |
|---|---|
| `.saipen/STATE.md` | Masinloetav pГ¤is вЂ” faas, Гјlesanne, jГ¤rgmine tegevus, blokeerija |
| `.saipen/BOARD.md` | Piletitahvel вЂ” DOING / TODO / DONE / BLOCKED jaotised |
| `.saipen/LOG.md` | SГјndmuste logi вЂ” iga kГ¤sk ja selle tulemus |

**Alam-agendid** (`saiwiki`, `saihunt`, `saitranslate`) elavad `.saipen/extensions/subs/` kaustas ja suhtlevad lГ¤bi `kitchen/OUTBOX.md`. SAIPENVIEW tuvastab nad kГµik.

### Vastavus (Conformance)

See, mida projekt *Гјtleb*, on ainult pool pilti. Igal real on kohtuotsuse mГ¤rk:

| MГ¤rk | TГ¤hendus |
|---|---|
| `OK` | Selles projektis pole probleeme leitud |
| `N WARNS` | Legaalne, kuid esineb hГ¤lbeid (nГ¤iteks vana logi tegusГµna) |
| `N FAILS` | Olek, mille protokoll tagasi lГјkkab (valed kastid, puuduvad piletid) |

> рџ’Ў *Nimi "SAIPENVIEW" Гјtleb kГµik вЂ” see pakub **vaadet** igale **SAIPEN** projektile sinu masinas.*

<br>

---

## вљ™пёЏ Konfiguratsioon

Konfiguratsioon asub rakenduse kГµrval:

```
saipenview/_data/config.json
```

Seadista `scan_roots: null` kГµigi ketaste automaatseks leidmiseks.  
MГ¤Г¤ra loendina (nt `["V:\\", "D:\\projects"]`) skannimise piiramiseks.

<br>

---

## рџЏ—пёЏ Arhitektuur

- **Гњks protsess** вЂ” ei mingit tausta-IPC-d, Гјks Pythoni protsess majutab nii WebView2 akent kui ka skannimistsГјklit.
- **Aatomilised kirjutamised** вЂ” failide salvestamine on turvaline ka krahhi korral.
- **Ajast ja arust stiil** вЂ” tumepruunid pinnad, kuldne tekst, 3D raamid, ei mingeid CSS-animatsioone, Verdana_m1 font.

<br>

---

## рџ§Є Arendus

Vaata lisaks [CONTRIBUTING.md](CONTRIBUTING.md).

### NГµuded
- **Windows 10 / 11** вЂ” WebView2 runtime
- **Python 3.10+**
- S�ltuvused: \pystray\, \keyboard\, \pywebview\, \Pillow\, \watchdog\, \psutil\n
<br>

---

## рџ“„ Litsents

MIT вЂ” vaata [LICENSE](LICENSE).

