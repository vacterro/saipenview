<div align="right">

  🌍 <a href="../../README.md">EN</a> | <a href="README.ar.md">AR</a> | <a href="README.bg.md">BG</a> | <a href="README.cs.md">CS</a> | <a href="README.da.md">DA</a> | <a href="README.de.md">DE</a> | <a href="README.ee.md">EE</a> | <a href="README.el.md">EL</a> | <a href="README.es.md">ES</a> | <a href="README.fi.md">FI</a> | <strong>FR</strong> | <a href="README.he.md">HE</a> | <a href="README.hi.md">HI</a> | <a href="README.hr.md">HR</a> | <a href="README.hu.md">HU</a> | <a href="README.id.md">ID</a> | <a href="README.it.md">IT</a> | <a href="README.ja.md">JA</a> | <a href="README.ko.md">KO</a> | <a href="README.nl.md">NL</a> | <a href="README.no.md">NO</a> | <a href="README.pl.md">PL</a> | <a href="README.pt.md">PT</a> | <a href="README.ro.md">RO</a> | <a href="README.ru.md">RU</a> | <a href="README.sk.md">SK</a> | <a href="README.sv.md">SV</a> | <a href="README.th.md">TH</a> | <a href="README.tr.md">TR</a> | <a href="README.uk.md">UK</a> | <a href="README.vi.md">VI</a> | <a href="README.zh.md">ZH</a> | <a href="README.zh-CN.md">ZH-CN</a> | <a href="README.ded.md">ДЕД</a>
</div>
> **Note:** This is a translated copy. The canonical documentation is [README.md](../../README.md) — this translation may lag the English original.

<div align="center">
  <img src="../../screenshots/saipen_icon.png" alt="SAIPENVIEW" width="120" height="120">
  <h1 align="center">SAIPENVIEW</h1>
  <p align="center">
    <strong>Visualiseur dans la barre des tâches pour chaque projet SAIPEN sur votre machine</strong>
    <br>
    Découverte automatique des projets <code>.saipen/</code> sur les lecteurs locaux — phase en direct, tâche, bloqueur, statut git, tickets et sous-agents.
    <br>
    Un tableau de bord au thème vintage Win95 or sombre.
  </p>
  <p>
    <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.10%2B-blue?style=flat-square&logo=python&logoColor=white" alt="Python"></a>
    <a href="../../LICENSE"><img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="Licence"></a>
    <a href="https://github.com/vacterro/saipenview"><img src="https://img.shields.io/badge/platform-Windows-orange?style=flat-square&logo=windows&logoColor=white" alt="Plateforme"></a>
    <a href="https://github.com/vacterro/saipenview/releases"><img src="https://img.shields.io/github/v/release/vacterro/saipenview?style=flat-square&include_prereleases" alt="Version"></a>
    <a href="https://github.com/vacterro/saipenview/actions"><img src="https://img.shields.io/github/actions/workflow/status/vacterro/saipenview/ci.yml?branch=main&style=flat-square&logo=github" alt="CI"></a>
  </p>
</div>

<br>

---

## 🚀 Fonctionnalités

<table>
<tr>
<td width="50%">

### 🔍 Découverte
- **Analyse automatique** des lecteurs locaux pour les projets `.saipen/`
- **Racines personnalisées** — choisissez des dossiers ou des lecteurs entiers
- **Exclusions intelligentes** — `node_modules`, `.git`, dossiers système
- **Nouvelle analyse en arrière-plan** — intervalle configurable (par défaut 300s)
- **Worktrees liés** — détecte les worktrees git pour une configuration facile

### 📊 Tableau de bord
- **Phase**, **tâche**, **prochaine action**, **bloqueur** en direct
- **Branche Git** + indicateur d'état modifié par projet
- **Filtrer** par phase (Tous / Actif / Terminé / Bloqué / personnalisé)
- **Trier** — Intelligent, Récent, Plus ancien, A–Z, Z–A
- **Rechercher** — filtre nom/racine + recherche approfondie dans les tickets
- **Épingler** les projets en haut, **masquer** les non pertinents
- **Surlignage flash** — les projets modifiés brillent & s'estompent sur 20s
- **Coloration thermique** — les projets inactifs refroidissent, les projets récents se réchauffent

</td>
<td width="50%">

### 🧩 Sous-agents
- **Affichage imbriqué** — `saiwiki`, `saihunt`, `saitranslate` indentés sous le parent
- **Comptage outbox** — prêt/bloqué/brouillon/révisé en un coup d'œil
- **Collecte en un clic** — regroupe les entrées prêtes dans le projet principal
- **Avertissement de péremption** — détecte les fichiers de protocole obsolètes

- **Agent Engine** - lancer `claude-code` (ou d'autres moteurs : codex, aider, gemini, cline, goose, agy, generic_cli) dans un projet
  - **Statut en direct** - état en cours/arrêté, CPU, temps écoulé par projet
  - **Console de sortie** - sortie de l'agent en mémoire tampon (5000 lignes par défaut), entrée stdin
  - **Kill / stop all** - tuer le processus et arrêt global
  - **Protection d'instance unique** - une seule instance de l'application ; le second lancement réaffiche la fenêtre
### 🎮 Interaction
- **Visualiseur de fichiers** — lire & modifier STATE.md, BOARD.md, LOG.md
  - Mode Source (éditable) + Mode Lecteur (rendu)
- **Tickets interactifs** — les boutons Démarrer / Terminé mettent à jour BOARD.md en direct
- **Actions rapides** — `npm run dev`, `cargo test`, etc. contextuels
- **Commandes personnalisées** — boutons d'action définis par l'utilisateur
- **Sections repliables** — par projet, persistantes
- **Barre latérale redimensionnable** — faire glisser pour redimensionner

### ⌨️ Raccourcis & Fenêtre
- **Afficher/Masquer** — `Ctrl+Alt+X` (configurable)
- **Ancrage aux coins** - `Ctrl+Q` fait défiler HG → HD → BG → BD
- **Zoom** — `Ctrl+Molette`, `Ctrl+`+`/`-`
- **Barre des tâches** — réduire dans la barre, démarrer masqué
- Bascule **Toujours au premier plan**
- **Démarrage automatique** — démarrage Windows optionnel
- **Mode sans cadre** — désactiver la barre de titre pour une vue ultra-minimale

</td>
</tr>
</table>

<br>

---

<br>

## 🎯 Démarrage rapide

<table>
<tr>
<th width="33%">🐍 Exécuter depuis les sources</th>
<th width="33%">📜 Scripts de lancement</th>
<th width="33%">📦 Installer (futur)</th>
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

| Script | Comportement |
|---|---|
| `run.vbs` | Masqué (uniquement dans la barre), silencieux |
| `run.bat` | Lancement dans la barre ; console visible uniquement lors de la configuration unique venv/dépendances |
Les deux créent automatiquement `.venv` & installent les dépendances.

</td>
<td>

```bash
pip install saipenview
saipenview
```
Bientôt disponible ✨

</td>
</tr>
</table>

<br>

---

## ⌨️ Utilisation

| Action | Comment |
|---|---|
| **Afficher / Masquer** | `Ctrl+Alt+X` ou `Alt+F15` (les deux configurables) |
| **Ancrer au coin** | `Ctrl+Q` - défile Haut-Gauche → Haut-Droit → Bas-Gauche → Bas-Droit |
| **Arrêt d'urgence** | `Ctrl+Shift+Alt+Q` — quitte forcé du processus |
| **Zoom avant / arrière** | `Ctrl+Molette` ou `Ctrl` + `+` / `-` |
| **Réinitialiser le zoom** | `Ctrl+0` |
| **Bascule barre d'outils** | `Alt+D` — réduire/agrandir le panneau d'outils |
| **Rechercher des projets** | Taper dans la zone de recherche ; cocher `D` pour la recherche approfondie de tickets |
| **Filtrer** | Menu déroulant : Tous / Actif / Terminé / Bloqué, ou cliquer sur une pilule de phase |
| **Trier** | Intelligent / Récent / Plus ancien / A–Z / Z–A |
| **Re-analyser** | Cliquer sur `Re-analyser` ou attendre le minuteur en arrière-plan (par défaut 300s) |
| **Parcourir dossier** | Cliquer sur `Parcourir` pour ajouter un dossier à l'ensemble d'analyse |
| **Paramètres** | Le bouton ⚙ ouvre la fenêtre des paramètres |
| **Wiki d'aide** | Le bouton `?` ouvre le mini-wiki intégré |
| **Clic droit projet** | Copier le chemin racine, filtrer par phase, ouvrir le dossier |
| **Double-clic section** | Ouvre le fichier connecté (STATE.md, BOARD.md, LOG.md) |
| **Déplacer la fenêtre** | Faire glisser la barre de titre (ou n'importe où en mode sans cadre) |

### Modales

| Modale | Ce qu'elle fait |
|---|---|
| **Paramètres** | Zoom, raccourcis, réglage de l'analyse, démarrage automatique, toujours au premier plan, police, bascule de surlignage, visualiseur par défaut, commandes personnalisées, langue, racines d'analyse |
| **Visualiseur de fichiers** | Lire & modifier STATE.md, BOARD.md, LOG.md — Mode Source (brut) ou Lecteur (rendu) |
| **Aide** | Mini-wiki complet couvrant chaque fonctionnalité, raccourci et concept |
| **Confirmation** | Boîte de dialogue DOM au style vintage (remplace le `confirm()` natif) |

<br>

---

## 🧬 Protocole SAIPEN

SAIPENVIEW est un compagnon pour les projets utilisant le **Protocole SAIPEN** — un framework à états finis qui guide les agents IA à travers le travail sur un projet dans des phases définies :

```
INIT → PLAN → SCOUT → BUILD → REVIEW → VERIFY → SHIP → DONE
                 ↓              ↓
            HUNT / CLEAN    VALIDATE
```

`ADD`, `MARKHUNT`, `TRANSLATE`, `PREPARE` existent aussi - le vocabulaire complet et la table de transition vivent dans `saipenview/protocol.py` (`BLOCKED` est atteignable depuis la plupart des phases).
Chaque projet SAIPEN stocke son état dans trois fichiers canoniques :

| Fichier | Objectif |
|---|---|
| `.saipen/STATE.md` | Frontmatter lisible par machine — phase, tâche, prochaine action, bloqueur |
| `.saipen/BOARD.md` | Tableau de tickets — sections EN COURS / À FAIRE / TERMINÉ / BLOQUÉ |
| `.saipen/LOG.md` | Journal d'événements chronologique — chaque commande et son résultat |

Les **agents SubSaipen** (`saiwiki`, `saihunt`, `saitranslate`) résident dans `.saipen/extensions/subs/` et communiquent via `kitchen/OUTBOX.md` — le bus de messages inter-agents intégré au protocole. SAIPENVIEW les découvre tous et affiche un tableau de bord unifié.

### Conformité

Afficher ce qu'un projet *dit* n'est que la moitié du travail. Un projet peut sembler parfait dans la liste — une phase, une tâche, une prochaine action — tout en étant dans un état que le protocole rejette, et jusqu'à ce que vous exécutiez `tools/validate.py` à la main, il n'y avait aucun moyen de faire la différence.

Chaque ligne porte un badge de verdict, et le panneau de détails liste ce qui ne va pas :

| Verdict | Signification |
|---|---|
| `OK` | Rien à signaler dans les fichiers `.saipen/` propres à ce projet |
| `N WARNS` | Valide mais en dérive — un point de contrôle obsolète, un verbe LOG non standard |
| `N FAILS` | Un état rejeté par le protocole : un `WAIT:` sans catégorie, une case à cocher en désaccord avec sa section, un `needs:` pointant vers un ticket inexistant, un `STATE.md` en UTF-16 qu'aucun autre outil SAIPEN ne peut lire |

Chaque constatation nomme la règle, le fichier et la ligne, ainsi que la clause dont elle provient, afin de pouvoir être vérifiée plutôt qu'acceptée sur parole.

C'est un **second avis, pas un remplacement** de `tools/validate.py`. Il ne re-vérifie que ce que les propres fichiers d'un projet peuvent décider, et il évalue par rapport à une copie des vocabulaires du protocole — la version SAIPEN à partir de laquelle il a été lu est donc imprimée sous chaque verdict. Le visualiseur a le droit d'avoir du retard sur le protocole. Il n'a pas le droit d'avoir du retard en silence.

> 💡 *Le nom « SAIPENVIEW » dit tout — il offre une **vue** sur chaque projet **SAIPEN** de votre machine.*

<br>

---

## ⚙️ Configuration

La configuration est portable — stockée à côté de l'application, pas dans `%APPDATA%` :

```
saipenview/_data/config.json
```

Valeurs par défaut principales (abrégé - le dictionnaire complet `DEFAULTS` se trouve dans `saipenview/config.py`) :

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

Réglez `scan_roots: null` pour détecter automatiquement tous les lecteurs locaux.  
Réglez sur une liste de chemins (ex. `["V:\\", "D:\\projects"]`) pour limiter l'analyse.  
`default_engine` / `engine_overrides` / `agent_output_buffer_size` pilotent l'Agent Engine (voir Fonctionnalités).  
Tous les paramètres sont également configurables via la modale **Paramètres** dans l'application.

<br>

---

## 🏗️ Architecture

```
saipenview/
├── app.py              Câblage d'entrée - barre, hotkey, fenêtre, api, protection d'instance unique
├── api.py              Pont pywebview côté JS (89 méthodes publiques)
├── scanner.py          Parcours des lecteurs + boucle de re-analyse en arrière-plan
├── parser.py           Analyse de STATE.md / BOARD.md / LOG.md
├── textio.py           Un lecteur pour chaque fichier .saipen/ — BOM, UTF-16, cp1251
├── protocol.py         Les vocabulaires fermés du protocole + BASELINE_VERSION
├── conformance.py      Évalue un projet par rapport à ces vocabulaires
├── config.py           Chargement/sauvegarde des paramètres (écritures atomiques)
├── tray.py             Icône + menu dans la barre des tâches pystray
├── hotkey.py           Enregistrement global des raccourcis (bibliothèque keyboard)
├── autostart.py        Gestion du démarrage automatique du Registre Windows
├── zone_picker.py      Superposition d'ancrage de coin Ctrl+Q (tkinter)
├── events.py           Bus d'événements intra-processus (EventBus)
├── guard.py            Verrou d'instance unique + remise de demande d'affichage
├── git_diff.py         Diff / commit / revert de l'arbre de travail pour les actions des agents
├── runtime.py          Agent Engine - gestionnaire de processus des agents lancés
├── watcher.py          Surveillant de fichiers Watchdog sur les fichiers .saipen/
├── engines/            Agent Engine - moteurs CLI pris en charge (claude-code, codex,
│                       aider, gemini, cline, goose, agy, generic_cli)
├── ui/
│   ├── window.py       Fenêtre pywebview — afficher/masquer/basculer/ancrer
│   └── static/
│       ├── index.html
│       ├── style.css   Thème Win95 vintage or sombre
│       └── app.js      Logique du frontend (~3300 lignes)
├── assets/
│   └── tray_icon.png
├── screenshots/        Captures d'écran du README
└── _data/              Configuration d'exécution + cache (ignoré par git)
```

### Principes de conception

- **Processus unique** — pas d'IPC en arrière-plan, pas de serveur séparé ; un seul processus Python héberge à la fois la fenêtre WebView2 et la boucle d'analyse dans un `ThreadPoolExecutor`
- **Écritures atomiques** — chaque écriture de fichier utilise un fichier temporaire + `os.replace` ; un plantage ne peut jamais tronquer la configuration ou le cache
- **Sécurisé contre les lectures obsolètes** — le sondage UI de 5s appelle `refresh_known()` (re-lit uniquement les fichiers `.saipen/`, pas de parcours de répertoire). Les modifications de STATE.md apparaissent en quelques secondes sans déclencher une analyse complète du lecteur
- **Pas de transitions CSS** — tous les effets visuels (surlignage, chaleur, survol) sont des recalculs `hexBlend` pilotés par JavaScript, suivant strictement la contrainte zéro animation du thème vintage
- **Thème vintage** — surfaces brun sombre, textes/accents dorés, bordures biseautées 3D, zéro anti-crénelage, police Verdana_m1

<br>

---

## 🧪 Développement

```bash
# Cloner & entrer
git clone https://github.com/vacterro/saipenview.git
cd saipenview

# Créer l'environnement virtuel & installer
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# Exécuter
python -m saipenview
```

Pour la configuration détaillée, les conventions de code et le flux de travail des PR, consultez [CONTRIBUTING.md](../../CONTRIBUTING.md).

### Prérequis

- **Windows 10 / 11** — WebView2 runtime (préinstallé sur Win11, s'installe automatiquement sur Win10)
- **Python 3.10+**
- Dépendances : `pystray`, `keyboard`, `pywebview`, `Pillow`, `watchdog`, `psutil`

<br>

---

## 📄 Licence

MIT — voir [LICENSE](../../LICENSE).

<br>

---

<div align="center">
  <sub>Construit avec 🐍 Python • 🖼️ pywebview • 🎨 Esthétique Vintage Win95</sub>

<br>

---

## 📸 Plus de captures d'écran

<p align="center">
  <img src="../../screenshots/detail-pane.png" alt="Panneau de détails SAIPENVIEW" width="85%" style="border-radius: 4px; border: 1px solid #3a3020;">
  <br>
  <em>Panneau de détails avec tickets, sous-agents et visualiseur de fichiers.</em>
</p>

<br>

</div>
