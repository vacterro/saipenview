<div align="right">
  🌍 <strong>EN</strong> | <a href="README.ru.md">RU</a> | <a href="README.ee.md">EE</a> | <a href="README.ded.md">ДЕД</a> | <a href="README.ja.md">JA</a>
</div>

<div align="center">
  <img src="screenshots/saipen_icon.png" alt="SAIPENVIEW" width="120" height="120">
  <h1 align="center">SAIPENVIEW</h1>
  <p align="center">
    <strong>Työpöydän ilmoitusalueen katseluohjelma jokaiselle koneesi SAIPEN-projektille</strong>
    <br>
    Löytää automaattisesti <code>.saipen/</code>-projektit paikallisilta asemilta — reaaliaikainen vaihe, tehtävä, estäjä, git-tila, tiketit ja alagentit.
    <br>
    Yksi retrohenkinen tummakultainen Win95-teemainen ohjauspaneeli.
  </p>
  <p>
    <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.10%2B-blue?style=flat-square&logo=python&logoColor=white" alt="Python"></a>
    <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="Lisenssi"></a>
    <a href="https://github.com/vacterro/saipenview"><img src="https://img.shields.io/badge/platform-Windows-orange?style=flat-square&logo=windows&logoColor=white" alt="Alusta"></a>
    <a href="https://github.com/vacterro/saipenview/releases"><img src="https://img.shields.io/github/v/release/vacterro/saipenview?style=flat-square&include_prereleases" alt="Julkaisu"></a>
    <a href="https://github.com/vacterro/saipenview/actions"><img src="https://img.shields.io/github/actions/workflow/status/vacterro/saipenview/ci.yml?branch=main&style=flat-square&logo=github" alt="CI"></a>
    [🤍 Tue kehittäjää](https://buymeacoffee.com/vacuum34)
  </p>
</div>

<br>

---

<br>

## ✨ Yleiskatsaus

<p align="center">
  <img src="screenshots/dashboard.png" alt="SAIPENVIEW Ohjauspaneelin kuvakaappaus" width="85%" style="border-radius: 4px; border: 1px solid #3a3020;">
  <br>
  <em>Jokainen SAIPEN-projekti, alagenti, tiketti ja git-tila — kaikki yhdessä näkymässä.</em>
</p>

<br>

---

## 🚀 Ominaisuudet

<table>
<tr>
<td width="50%">

### 🔍 Automaattinen etsintä
- **Automaattiskannaus** paikallisilta asemilta `.saipen/`-projekteille
- **Mukautetut juurikansiot** — valitse kansioita tai kokonaisia asemia
- **Älykäs poissulku** — `node_modules`, `.git`, järjestelmäkansiot
- **Taustaskannaus** — määritettävissä oleva aikaväli (oletus 300 s)
- **Linkitetyt worktret** — havaitsee git-worktreet helppoa käyttöönottoa varten

### 📊 Ohjauspaneeli
- Reaaliaikainen **vaihe**, **tehtävä**, **seuraava toimenpide**, **estäjä**
- **Git-haara** + muokkaustilan ilmaisin projektikohtaisesti
- **Suodatus** vaiheen mukaan (Kaikki / Aktiivinen / Valmis / Jumissa / mukautettu)
- **Lajittelu** — Älykäs, Viimeisimmät, Vanhimmat, A–Z, Z–A
- **Haku** — nimen/juuren suodatus + syvähaku tiketeistä
- **Kiinnitä** projekteja kärkeen, **piilota** tarpeettomat
- **Korostusvälähdys** — muuttuneet projektit hehkuvat ja haalistuvat 20 sekunnissa
- **Lämpöväritys** — vanhentuneet projektit viilenevät, tuoreet lämpenevät

</td>
<td width="50%">

### 🧩 Alagentit
- **Sisennetty näyttö** — `saiwiki`, `saihunt`, `saitranslate` sisennettynä emoprojektin alle
- **Outbox-laskurit** — valmiit/estetyt/luonnokset/tarkistetut yhdellä silmäyksellä
- **Keräys yhdellä napsautuksella** — yhdistä valmiit merkinnät pääprojektiin
- **Varoitus vanhentumisesta** — havaitsee vanhentuneet protokoliatiedostot

### 🎮 Vuorovaikutus
- **Tiedostokatselin** — lue ja muokkaa STATE.md, BOARD.md, LOG.md
  - Lähdekooditila (muokattava) + Lukutila (renderoitu)
- **Interaktiiviset tiketit** — Aloita / Valmis -painikkeet päivittävät BOARD.md-tiedostoa suoraan
- **Pikatoiminnot** — kontekstuaaliset `npm run dev`, `cargo test` jne.
- **Mukautetut komennot** — käyttäjän määrittämät toimintopainikkeet
- **Kokoonpantavat osiot** — projektikohtaiset, tallentuvat
- **Kokoa muutettava sivupalkki** — muuta kokoa vetämällä

### ⌨️ Pikanäppäimet & Ikkuna
- **Näytä/Piilota** — `Ctrl+Alt+X` (määritettävissä)
- **Kiinnitä kulmiin** — `Ctrl+Q` vaihtaa YV → YO → AV → AO
- **Mittakaava** — `Ctrl+HiirenRulla`, `Ctrl+`+`/`-`
- **Ilmoitusalue** — pienennä ilmoitusalueelle, käynnistä piilotettuna
- **Aina päällimmäisenä** -kytkin
- **Automaattikäynnistys** — valinnainen Windowsin käynnistyksen yhteydessä
- **Kehytön tila** — poista otsikkopalkki käytöstä ultra-minimaalista näkymää varten

</td>
</tr>
</table>

<br>

---

<br>

## 🎯 Pika-aloitus

<table>
<tr>
<th width="33%">🐍 Suorita lähdekoodista</th>
<th width="33%">📜 Käynnistysskriptit</th>
<th width="33%">📦 Asenna (tulevaisuudessa)</th>
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

| Skripti | Toiminta |
|---|---|
| `run.vbs` | Piilotettu (vain ilmoitusalue) |
| `run.bat` | Näkyvä (konsoli auki) |
Molemmat luovat automaattisesti `.venv`-ympäristön ja asentavat riippuvuudet.

</td>
<td>

```bash
pip install saipenview
saipenview
```
Tulossa piakkoin ✨

</td>
</tr>
</table>

<br>

---

## ⌨️ Käyttö

| Toiminto | Miten |
|---|---|
| **Näytä / Piilota** | `Ctrl+Alt+X` tai `Alt+F15` (molemmat määritettävissä) |
| **Kiinnitä kulmaan** | `Ctrl+Q` — vaihtaa Ylä-vasen → Ylä-oikea → Ala-vasen → Ala-oikea |
| **Hätäsammutus** | `Ctrl+Shift+Alt+Q` — pakkolopeta prosessi |
| **Lähennä / Loitonna** | `Ctrl+HiirenRulla` tai `Ctrl` + `+` / `-` |
| **Palauta mittakaava** | `Ctrl+0` |
| **Vaihda työkalupalkkia** | `Alt+D` — pienennä/laajenna työkalupalkkipaneeli |
| **Etsi projekteja** | Kirjoita hakukenttään; valitse `D` syvällistä tikettihakua varten |
| **Suodata** | Pudotusvalikko: Kaikki / Aktiivinen / Valmis / Jumissa, tai napsauta vaihenappia |
| **Lajittele** | Älykäs / Viimeisimmät / Vanhimmat / A–Z / Z–A |
| **Skannaa uudelleen** | Napsauta `Päivitä` tai odota tausta-ajastinta (oletus 300 s) |
| **Selaa kansiota** | Napsauta `Selaa` lisätäksesi kansion skannausjoukkoon |
| **Asetukset** | ⚙-painike avaa asetukset-ikkunan |
| **Ohje-wiki** | `?`-painike avaa sisäänrakennetun mini-wikin |
| **Napsauta hiiren kakkospainikkeella** | Kopioi juuripolku, suodata vaiheen mukaan, avaa kansio |
| **Kaksoisnapsauta osiota** | Avaa liittyvän tiedoston (STATE.md, BOARD.md, LOG.md) |
| **Vedä ikkunaa** | Vedä otsikkopalkista (tai mistä tahansa kehyksettömässä tilassa) |

### Ikkunat (Modals)

| Ikkuna | Mitä se tekee |
|---|---|
| **Asetukset** | Mittakaava, pikanäppäimet, skannauksen hienosäätö, automaattikäynnistys, aina päällimmäisenä, fontti, korostusvälähdyksen kytkin, tiedostokatselimen oletus, mukautetut komennot, kieli, skannausjuuret |
| **Tiedostokatselin** | Lue ja muokkaa STATE.md, BOARD.md, LOG.md — Lähdekoodi (raaka) tai Lukutila (renderoitu) |
| **Ohje** | Kattava mini-wiki, joka kattaa jokaisen ominaisuuden, oikotien ja käsitteen |
| **Vahvista** | Retrotyylinen DOM-dialogi (korvaa natiivin `confirm()`-funktion) |

<br>

---

## 🧬 SAIPEN-protokolla

SAIPENVIEW on kumppaniohjelmisto projekteille, jotka käyttävät **SAIPEN-protokollaa** — tilakonekehystä, joka ohjaa tekoälyagentteja projektityössä määriteltyjen vaiheiden läpi:

```
INIT → PLAN → SCOUT → BUILD → REVIEW → VERIFY → SHIP → DONE
                         ↓
                    HUNT / CLEAN
```

Jokainen SAIPEN-projekti tallentaa tilansa kolmeen kanoniseen tiedostoon:

| Tiedosto | Käyttötarkoitus |
|---|---|
| `.saipen/STATE.md` | Koneellisesti luettava frontmatter — vaihe, tehtävä, seuraava toimenpide, estäjä |
| `.saipen/BOARD.md` | Tikettitaulu — DOING / TODO / DONE / BLOCKED -osiot |
| `.saipen/LOG.md` | Aikajärjestyksessä oleva tapahtumaloki — jokainen komento ja sen tulos |

**SubSaipen-agentit** (`saiwiki`, `saihunt`, `saitranslate`) sijaitsevat hakemistossa `.saipen/extensions/subs/` ja viestivät tiedoston `kitchen/OUTBOX.md` kautta — protokollan sisäänrakennettu agenttien välinen viestinvälitys. SAIPENVIEW löytää ne kaikki ja renderoi yhtenäisen ohjauspaneelin.

### Vaatimustenmukaisuus (Conformance)

Se mitä projekti *sanoo*, on vasta puolet totuudesta. Projekti voi näyttää luettelossa täydelliseltä — vaihe, tehtävä, seuraava toimenpide — vaikka se olisi tilassa, jonka protokolla hylkää, eikä näitä kahta voinut erottaa toisistaan ilman `tools/validate.py`-skriptin suorittamista käsin.

Jokaisessa rivissä on päätöslätkä (verdict badge), ja yksityiskohtapaneeli luettelee mahdolliset virheet:

| Päätös | Merkitys |
|---|---|
| `OK` | Mitään virheitä ei löytynyt tämän projektin omista `.saipen/`-tiedostoista |
| `N WARNS` | Sallittu, mutta poikkeava — vanhentunut tarkistuspiste, ei-standardi LOG-verbi |
| `N FAILS` | Tila, jonka protokolla hylkää: `WAIT:` ilman kategoriaa, valintaruutu joka on ristiriidassa osionsa kanssa, olematomaan tikettiin osoittava `needs:`, tai UTF-16-muotoinen `STATE.md`, jota mikään muu SAIPEN-työkalu ei pysty lukemaan |

Jokainen löydös ilmoittaa säännön, tiedoston ja rivin sekä lausekkeen, josta se on peräisin, jotta se voidaan tarkistaa sokean luottamuksen sijaan.

Tämä on **toinen mielipide, ei korvaaja** `tools/validate.py`-työkalulle. Se tarkistaa uudelleen vain sen, mitä projektin omat tiedostot voivat määrittää, ja se arvioi protokollan sanastojen kopiota vasten — joten SAIPEN-versio, josta se luettiin, tulostetaan jokaisen päätöksen alle. Katseluohjelma saa olla protokollaa jäljessä. Se ei saa olla sitä jäljessä hiljaisesti.

> 💡 *Nimi "SAIPENVIEW" sanoo kaiken — se tarjoaa näkymän (view) jokaiseen koneellasi olevaan SAIPEN-projektiin.*

<br>

---

## ⚙️ Asetukset

Asetukset ovat siirrettäviä — tallennettuna sovelluksen viereen, ei `%APPDATA%`-hakemistoon:

```
saipenview/_data/config.json
```

Keskeiset oletusarvot:

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
  "auto_scan":        true,
  "show_on_launch":   true,
  "always_on_top":    true,
  "flash_changes":    true,
  "locale":           "en"
}
```

Aseta `scan_roots: null` havaitaksesi kaikki paikalliset asemat automaattisesti.  
Aseta polkuluetteloksi (esim. `["V:\\", "D:\\projects"]`) rajoittaaksesi skannausta.  
Kaikki asetukset ovat myös määritettävissä sovelluksen **Asetukset**-ikkunan kautta.

<br>

---

## 🏗️ Arkkitehtuuri

```
saipenview/
├── app.py              Syötteiden kytkentä — ilmoitusalue, pikanäppäin, ikkuna, API
├── api.py              JS-suuntainen pywebview-silta (30+ metodia)
├── scanner.py          Asemakierros + taustaskannauksen silmukka
├── parser.py           STATE.md / BOARD.md / LOG.md -jäsennys
├── textio.py           Yksi lukija jokaiselle .saipen/-tiedostolle — BOM, UTF-16, cp1251
├── protocol.py         Protokollan suljetut sanastot + BASELINE_VERSION
├── conformance.py      Arvioi projektin kyseisiä sanastoja vasten
├── config.py           Asetusten lataus/tallennus (atomiset kirjoitukset)
├── tray.py             pystray ilmoitusalueen kuvake + valikko
├── hotkey.py           Globaali pikanäppäinten rekisteröinti (keyboard-kirjasto)
├── autostart.py        Windows Rekisterin automaattikäynnistyksen hallinta
├── zone_picker.py      Ctrl+Q kulmaan kiinnityksen kerrosnäyttö (tkinter)
├── ui/
│   ├── window.py       pywebview-ikkuna — näytä/piilota/vaihda/kiinnitä
│   └── static/
│       ├── index.html
│       ├── style.css   Retro tummakultainen Win95-teema
│       └── app.js      Frontend-logiikka (~2600 riviä)
├── assets/
│   └── tray_icon.png
├── screenshots/        README-kuvakaappaukset
└── _data/              Suoritusaikaiset asetukset + välimuisti (git-ignoroitu)
```

### Suunnitteluperiaatteet

- **Yksi prosessi** — ei tausta-IPC:tä, ei erillistä palvelinta; yksi Python-prosessi isännöi sekä WebView2-ikkunaa että skannaussilmukkaa `ThreadPoolExecutor`-säikeistössä
- **Atomiset kirjoitukset** — jokainen tiedoston kirjoitus käyttää väliaikaistiedostoa + `os.replace`-komentoa; kaatuminen ei voi koskaan katkaista asetuksia tai välimuistia
- **Turvallinen vanhentuneille luenneille** — käyttöliittymän 5 sekunnin kysely kutsuu `refresh_known()`-funktiota (lukee uudelleen vain `.saipen/`-tiedostot ilman hakemistokierrosta). Muutokset STATE.md-tiedostoon näkyvät sekunneissa ilman koko aseman skannausta
- **Ei CSS-siirtymiä** — kaikki visuaaliset efektit (välähdys, lämpö, leijutus) ovat JavaScript-pohjaisia `hexBlend`-uudenlaskentoja, jotka noudattavat tiukasti retro-teeman animaatiottomuussääntöä
- **Retro-teema** — tummanruskeat pinnat, kultainen teksti/korostukset, 3D-viistetyt reunat, ei reunantasoitusta, Verdana_m1-fontti

<br>

---

## 🧪 Kehitys

```bash
# Kloonaa & siirry
git clone https://github.com/vacterro/saipenview.git
cd saipenview

# Luokaa venv & asenna
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# Suorita
python -m saipenview
```

Yksityiskohtaiset asennusohjeet, koodauskäytännöt ja PR-työnkulun löydät tiedostosta [CONTRIBUTING.md](CONTRIBUTING.md).

### Vaatimukset

- **Windows 10 / 11** — WebView2-suoritusympäristö (esiasennettu Win11:ssä, asentuu automaattisesti Win10:ssä)
- **Python 3.10+**
- Riippuvuudet: `pystray`, `keyboard`, `pywebview`, `Pillow`, `watchdog`, `psutil`

<br>

---

## 📄 Lisenssi

MIT — katso [LICENSE](LICENSE).

<br>

---

<div align="center">
  <sub>Rakennettu 🐍 Pythonilla • 🖼️ pywebview • 🎨 Retro Win95 -estetiikka</sub>

<br>

---

## 📸 Lisää kuvakaappauksia

<p align="center">
  <img src="screenshots/detail-pane.png" alt="SAIPENVIEW Yksityiskohtapaneeli" width="85%" style="border-radius: 4px; border: 1px solid #3a3020;">
  <br>
  <em>Yksityiskohtapaneeli tiketteineen, alagetteineen ja tiedostokatselimineen.</em>
</p>

<br>

</div>
