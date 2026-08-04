<div align="right">
  🌍 <a href="../../README.md">EN</a> | <a href="README.ar.md">AR</a> | <a href="README.bg.md">BG</a> | <a href="README.cs.md">CS</a> | <a href="README.da.md">DA</a> | <a href="README.de.md">DE</a> | <a href="README.ee.md">EE</a> | <a href="README.el.md">EL</a> | <a href="README.es.md">ES</a> | <a href="README.fi.md">FI</a> | <a href="README.fr.md">FR</a> | <a href="README.he.md">HE</a> | <a href="README.hi.md">HI</a> | <a href="README.hr.md">HR</a> | <a href="README.hu.md">HU</a> | <a href="README.id.md">ID</a> | <a href="README.it.md">IT</a> | <a href="README.ja.md">JA</a> | <a href="README.ko.md">KO</a> | <a href="README.nl.md">NL</a> | <a href="README.no.md">NO</a> | <a href="README.pl.md">PL</a> | <a href="README.pt.md">PT</a> | <a href="README.ro.md">RO</a> | <a href="README.ru.md">RU</a> | <a href="README.sk.md">SK</a> | <a href="README.sv.md">SV</a> | <a href="README.th.md">TH</a> | <a href="README.tr.md">TR</a> | <a href="README.uk.md">UK</a> | <a href="README.vi.md">VI</a> | <a href="README.zh.md">ZH</a> | <a href="README.zh-CN.md">ZH-CN</a> | <strong>ДЕД</strong>
</div>

<div align="center">
  <img src="../../screenshots/saipen_icon.png" alt="SAIPENVIEW" width="120" height="120">
  <h1 align="center">SAIPENVIEW</h1>
  <p align="center">
    <strong>Панель для всех SAIPEN-проектов твоей машины</strong>
    <br>
    Сам находит проекты с <code>.saipen/</code> по дискам — фаза, задача, блокер, git, тикеты, сабагенты.
    <br>
    Одна винтажная тёмно-золотая панель в духе Win95.
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

## 🚀 Что умеет

<table>
<tr>
<td width="50%">

### 🔍 Поиск
- **Автоскан** дисков на `.saipen/`-проекты
- **Свои корни** — хоть папки, хоть диски целиком
- **Умные исключения** — `node_modules`, `.git`, системное барахло
- **Фоновый рескан** — интервал настраивается (по умолчанию 300 с)
- **Worktree** — связанные гит-worktree видит, для настройки не бегает

### 📊 Панель
- Живые **фаза**, **задача**, **следующий шаг**, **блокер**
- **Ветка** + индикатор грязного дерева на каждый проект
- **Фильтр** по фазе (Все / Активные / Готовые / Застрявшие / свой)
- **Сортировка** — Smart, Recent, Oldest, А–Я, Я–А
- **Поиск** — по имени/корню + глубокий по тикетам
- **Закрепление** сверху, **скрытие** лишнего
- **Вспышка** — изменился, светится 20 с и гаснет
- **Тепловая окраска** — старьё холодное, свежак тёплый

</td>
<td width="50%">

### 🧩 Сабагенты
- **Вложенный показ** — `saiwiki`, `saihunt`, `saitranslate` под родителем
- **Счётчики OUTBOX** — ready/blocked/draft/reviewed сразу видно
- **Сбор в один клик** — готовое складывается в главный проект
- **Предупреждение** — устаревшие файлы протокола не прячутся
- **Agent Engine** — запуск `claude-code` (и codex, aider, gemini, cline, goose, agy, generic_cli) в проекте
  - **Живой статус** — работает/сдох, CPU, время
  - **Консоль** — вывод агента (по умолчанию 5000 строк), ввод в stdin
  - **Kill / stop all** — прибить процесс и глобальный стоп
  - **Защита от дублей** — второй экземпляр не заведётся, только окно покажет

### 🎮 Управление
- **Просмотр файлов** — STATE.md, BOARD.md, LOG.md читать и править
  - Режим исходника (правка) + режим чтения (красивый)
- **Интерактивные тикеты** — Start / Done правят BOARD.md на лету
- **Быстрые действия** — `npm run dev`, `cargo test` и так далее
- **Свои команды** — свои кнопки, свои дела
- **Сворачиваемые секции** — по проектам, запоминаются
- **Боковая панель** — тянется мышкой

### ⌨️ Клавиши и окно
- **Показать/Скрыть** — `Ctrl+Alt+X` (настраивается)
- **Привязка к углам** — `Alt+F14` гоняет по кругу ЛВ → ЛН → ПН → ПВ
- **Масштаб** — `Ctrl+Колесо`, `Ctrl+`+`/`-`
- **Трей** — сворачивается в трей, можно стартовать скрытым
- **Поверх всех окон** — переключатель
- **Автозапуск** — по желанию, при старте Windows
- **Безрамочный режим** — заголовок долой, минимализм

</td>
</tr>
</table>

<br>

---

<br>

## 🎯 Старт

<table>
<tr>
<th width="33%">🐍 Из исходников</th>
<th width="33%">📜 Скрипты</th>
<th width="33%">📦 Установка (скоро)</th>
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

| Скрипт | Что делает |
|---|---|
| `run.vbs` | Скрытый, только трей, тихий |
| `run.bat` | В трей; консоль видна только при разовом создании venv/зависимостей |
Оба сами создают `.venv` и ставят зависимости.

</td>
<td>

```bash
pip install saipenview
saipenview
```
Скоро ✨

</td>
</tr>
</table>

<br>

---

<br>

## ⌨️ Пользование

| Действие | Как |
|---|---|
| **Показать / Скрыть** | `Ctrl+Alt+X` или `Alt+F15` (оба настраиваются) |
| **Привязка к углу** | `Alt+F14` — цикл Верх-Лево → Верх-Право → Низ-Лево → Низ-Право |
| **Аварийный выход** | `Ctrl+Shift+Alt+Q` — принудительно, без соплей |
| **Масштаб** | `Ctrl+Колесо` или `Ctrl` + `+` / `-` |
| **Сброс масштаба** | `Ctrl+0` |
| **Панель инструментов** | `Alt+D` — свернуть/развернуть |
| **Поиск** | Поле поиска; `D` — глубокий поиск по тикетам |
| **Фильтр** | Все / Живые / Готовые / Застрявшие, или клик по фазе |
| **Сортировка** | Smart / Recent / Oldest / А–Я / Я–А |
| **Рескан** | Кнопка `Rescan` или таймер (по умолчанию 300 с) |
| **Папка** | `Browse` — добавить папку в сканирование |
| **Настройки** | Кнопка ⚙ |
| **Справка** | Кнопка `?` — встроенная мини-вики |
| **ПКМ по проекту** | Скопировать путь, фильтр по фазе, открыть папку |
| **Двойной клик по секции** | Открывает файл (STATE.md, BOARD.md, LOG.md) |
| **Перетаскивание** | За заголовок (или откуда угодно в безрамочном режиме) |

### Окна

| Окно | Что делает |
|---|---|
| **Настройки** | Масштаб, клавиши, скан, автозапуск, поверх всех, шрифт, вспышка, режим просмотра, свои команды, язык, корни |
| **Просмотр файлов** | STATE.md, BOARD.md, LOG.md — исходник или красивый режим |
| **Справка** | Мини-вики по всему, что есть |
| **Подтверждение** | Диалог в винтажном стиле (вместо нативного `confirm()`) |

<br>

---

<br>

## 🧬 Протокол SAIPEN

SAIPENVIEW — приставка к проектам на **протоколе SAIPEN** — конечный автомат, который гоняет агентов по фазам:

```
INIT → PLAN → SCOUT → BUILD → REVIEW → VERIFY → SHIP → DONE
                 ↓              ↓
            HUNT / CLEAN    VALIDATE
```
`ADD`, `MARKHUNT`, `TRANSLATE`, `PREPARE` тоже есть — полный словарь и таблица переходов в `saipenview/protocol.py` (`BLOCKED` достижим почти откуда угодно).

Состояние проекта — в трёх канонических файлах:

| Файл | Зачем |
|---|---|
| `.saipen/STATE.md` | Машиночитаемый frontmatter — фаза, задача, следующий шаг, блокер |
| `.saipen/BOARD.md` | Доска тикетов — DOING / TODO / DONE / BLOCKED |
| `.saipen/LOG.md` | Журнал событий — каждая команда и её исход |

**Сабагенты** (`saiwiki`, `saihunt`, `saitranslate`) сидят в `.saipen/extensions/subs/` и общаются через `kitchen/OUTBOX.md` — встроенная шина протокола. SAIPENVIEW их всех видит и рисует единую панель.

### Соответствие протоколу

Показывать, что проект *говорит* — полдела. Проект может красиво читаться
в списке — фаза, задача, следующий шаг — а состояние держать такое, что
протокол его плюёт на асфальт. И пока руками не запустишь
`tools/validate.py`, не отличишь.

Каждая строка несёт бейдж вердикта, панель деталей перечисляет, что не так:

| Вердикт | Значение |
|---|---|
| `OK` | В собственных `.saipen/`-файлах проекта чисто |
| `N WARNS` | Законно, но поплыло — устаревшая контрольная точка, нестандартный глагол в LOG |
| `N FAILS` | Протокол такое состояние не принимает: `WAIT:` без категории, чекбокс не в своей секции, `needs:` на несуществующий тикет, UTF-16 `STATE.md`, который никто из инструментов SAIPEN не читает |

Каждое замечание называет правило, файл, строку и пункт, из которого
вытекает — проверяй, а не верь на слово.

Это **второе мнение, не замена** `tools/validate.py`. Оно перепроверяет
только то, что решают файлы самого проекта, и оценивает по копии словарей
протокола — поэтому версия SAIPEN, с которой прочитано, печатается под
каждым вердиктом. Просмотрщику можно отставать от протокола. Молча —
нельзя.

> 💡 *Название говорит всё: SAIPENVIEW — это **взгляд** на каждый **SAIPEN**-проект машины.*

<br>

---

<br>

## ⚙️ Конфигурация

Конфиг портативный — лежит рядом с приложением, не в `%APPDATA%`:

```
saipenview/_data/config.json
```

Основные значения по умолчанию (сокращено — полный `DEFAULTS` в `saipenview/config.py`):

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

`scan_roots: null` — автоскан всех дисков.  
Список путей (например `["V:\\", "D:\\projects"]`) — ограничить скан.  
`default_engine` / `engine_overrides` / `agent_output_buffer_size` рулят Agent Engine (см. «Возможности»).  
Всё настраивается и через окно **Настройки**.

<br>

---

<br>

## 🏗️ Архитектура

```
saipenview/
├── app.py              Проводка: трей, хоткей, окно, api, защита от дублей
├── api.py              JS-мост pywebview (66 публичных методов)
├── scanner.py          Обход дисков + фоновый рескан
├── parser.py           Разбор STATE.md / BOARD.md / LOG.md
├── textio.py           Один читатель всех .saipen/-файлов — BOM, UTF-16, cp1251
├── protocol.py         Закрытые словари протокола + BASELINE_VERSION
├── conformance.py      Оценивает проект по этим словарям
├── config.py           Настройки: загрузка/сохранение (атомарно)
├── tray.py             Иконка pystray в трее + меню
├── hotkey.py           Глобальные хоткеи (keyboard)
├── autostart.py        Автозапуск через реестр Windows
├── zone_picker.py      Оверлей привязки к углу Alt+F14 (tkinter)
├── events.py           Внутрипроцессная шина событий (EventBus)
├── guard.py            Блокировка одиночного экземпляра + показ
├── git_diff.py         Diff / commit / revert рабочего дерева для агентов
├── runtime.py          Agent Engine — менеджер процессов агентов
├── watcher.py          Watchdog-наблюдатель за .saipen/-файлами
├── engines/            Agent Engine — CLI-движки (claude-code, codex,
│                       aider, gemini, cline, goose, agy, generic_cli)
├── ui/
│   ├── window.py       Окно pywebview — показать/скрыть/переключить/привязка
│   └── static/
│       ├── index.html
│       ├── style.css   Винтажная тёмно-золотая тема Win95
│       └── app.js      Фронтенд (~3300 строк)
├── assets/
│   └── tray_icon.png
├── screenshots/        Скрины для README
└── _data/              Конфиг и кэш (gitignored)
```

### Принципы

- **Один процесс** — никакого фонового IPC и серверов; один Python держит и окно WebView2, и скан-цикл в `ThreadPoolExecutor`
- **Атомарные записи** — temp-файл + `os.replace`; сбой не обрежет конфиг или кэш
- **Устойчивое чтение** — 5-секундный опрос зовёт `refresh_known()` (только `.saipen/`-файлы, без обхода дисков). Правки STATE.md видны за секунды
- **Ноль CSS-переходов** — все эффекты (вспышка, тепло, hover) — JS-пересчёт `hexBlend`, винтажная тема без анимаций
- **Винтаж** — тёмно-коричневые поверхности, золото, 3D-фаски, ноль сглаживания, Verdana_m1

<br>

---

<br>

## 🧪 Разработка

```bash
# Клонируй и заходи
git clone https://github.com/vacterro/saipenview.git
cd saipenview

# venv и зависимости
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# Запуск
python -m saipenview
```

Подробности: установка, конвенции, PR-процесс — в [CONTRIBUTING.md](../../CONTRIBUTING.md).

### Требования

- **Windows 10 / 11** — рантайм WebView2 (на Win11 предустановлен, на Win10 ставится сам)
- **Python 3.10+**
- Зависимости: `pystray`, `keyboard`, `pywebview`, `Pillow`, `watchdog`, `psutil`

<br>

---

<br>

## 📄 Лицензия

MIT — см. [LICENSE](../../LICENSE).

<br>

---

<br>

<div align="center">
  <sub>Собрано на 🐍 Python • 🖼️ pywebview • 🎨 Винтаж Win95</sub>

<br>

---

<br>

## 📸 Ещё скрины

<p align="center">
  <img src="../../screenshots/detail-pane.png" alt="Панель деталей SAIPENVIEW" width="85%" style="border-radius: 4px; border: 1px solid #3a3020;">
  <br>
  <em>Детали: тикеты, сабагенты, просмотр файлов.</em>
</p>

<br>

</div>
