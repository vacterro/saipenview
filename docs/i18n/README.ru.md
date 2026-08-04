<div align="right">
  🌍 <a href="../../README.md">EN</a> | <a href="README.ar.md">AR</a> | <a href="README.bg.md">BG</a> | <a href="README.cs.md">CS</a> | <a href="README.da.md">DA</a> | <a href="README.de.md">DE</a> | <a href="README.ee.md">EE</a> | <a href="README.el.md">EL</a> | <a href="README.es.md">ES</a> | <a href="README.fi.md">FI</a> | <a href="README.fr.md">FR</a> | <a href="README.he.md">HE</a> | <a href="README.hi.md">HI</a> | <a href="README.hr.md">HR</a> | <a href="README.hu.md">HU</a> | <a href="README.id.md">ID</a> | <a href="README.it.md">IT</a> | <a href="README.ja.md">JA</a> | <a href="README.ko.md">KO</a> | <a href="README.nl.md">NL</a> | <a href="README.no.md">NO</a> | <a href="README.pl.md">PL</a> | <a href="README.pt.md">PT</a> | <a href="README.ro.md">RO</a> | <strong>RU</strong> | <a href="README.sk.md">SK</a> | <a href="README.sv.md">SV</a> | <a href="README.th.md">TH</a> | <a href="README.tr.md">TR</a> | <a href="README.uk.md">UK</a> | <a href="README.vi.md">VI</a> | <a href="README.zh.md">ZH</a> | <a href="README.zh-CN.md">ZH-CN</a> | <a href="README.ded.md">ДЕД</a>
</div>

<div align="center">
  <img src="../../screenshots/saipen_icon.png" alt="SAIPENVIEW" width="120" height="120">
  <h1 align="center">SAIPENVIEW</h1>
  <p align="center">
    <strong>Настольный трей-просмотрщик всех SAIPEN-проектов на вашей машине</strong>
    <br>
    Автонаходит проекты с <code>.saipen/</code> по локальным дискам — живая фаза, задача, блокер, git-статус, тикеты и сабагенты.
    <br>
    Единая панель в винтажной тёмно-золотой теме Win95.
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

## 🚀 Возможности

<table>
<tr>
<td width="50%">

### 🔍 Обнаружение
- **Автосканирование** локальных дисков на проекты с `.saipen/`
- **Свои корни** — выбирайте папки или целые диски
- **Умные исключения** — `node_modules`, `.git`, системные папки
- **Фоновое пересканирование** — настраиваемый интервал (по умолчанию 300 с)
- **Связанные worktree** — определяет git-worktree для быстрой настройки

### 📊 Панель
- Живые **фаза**, **задача**, **следующее действие**, **блокер**
- **Git-ветка** + индикатор грязного состояния на каждый проект
- **Фильтр** по фазе (Все / Активные / Готовые / Застрявшие / свой)
- **Сортировка** — Smart, Recent, Oldest, А–Я, Я–А
- **Поиск** — фильтр по имени/корню + глубокий поиск по тикетам
- **Закрепление** проектов сверху, **скрытие** ненужных
- **Подсветка изменений** — изменённые проекты светятся и гаснут за 20 с
- **Тепловая окраска** — старые проекты холодные, свежие тёплые

</td>
<td width="50%">

### 🧩 Сабагенты
- **Вложенный показ** — `saiwiki`, `saihunt`, `saitranslate` с отступом под родителем
- **Счётчики OUTBOX** — ready/blocked/draft/reviewed с одного взгляда
- **Сбор в один клик** — готовые записи складываются в главный проект
- **Предупреждение об устаревании** — замечает устаревшие файлы протокола
- **Agent Engine** — запуск `claude-code` (или других движков: codex, aider, gemini, cline, goose, agy, generic_cli) в проекте
  - **Живой статус** — состояние запуска/выхода, CPU, время на проект
  - **Консоль вывода** — буфер вывода агента (по умолчанию 5000 строк), ввод в stdin
  - **Kill / stop all** — убить процесс в проекте и глобальная остановка
  - **Защита от дублей** — только один экземпляр приложения; повторный запуск показывает окно

### 🎮 Взаимодействие
- **Просмотр файлов** — чтение и правка STATE.md, BOARD.md, LOG.md
  - Режим исходника (редактируемый) + режим чтения (отрисованный)
- **Интерактивные тикеты** — кнопки Start / Done обновляют BOARD.md на лету
- **Быстрые действия** — контекстные `npm run dev`, `cargo test` и т.п.
- **Свои команды** — задаваемые пользователем кнопки действий
- **Сворачиваемые секции** — по каждому проекту, сохраняются
- **Изменяемая боковая панель** — перетаскиванием

### ⌨️ Горячие клавиши и окно
- **Показать/Скрыть** — `Ctrl+Alt+X` (настраивается)
- **Привязка к углам** — `Alt+F14` циклически ЛВ → ЛН → ПН → ПВ
- **Масштаб** — `Ctrl+Колесо мыши`, `Ctrl+`+`/`-`
- **Системный трей** — сворачивание в трей, запуск скрытым
- **Поверх всех окон** — переключатель
- **Автозапуск** — опционально при старте Windows
- **Безрамочный режим** — заголовок окна скрывается для минимализма

</td>
</tr>
</table>

<br>

---

<br>

## 🎯 Быстрый старт

<table>
<tr>
<th width="33%">🐍 Из исходников</th>
<th width="33%">📜 Скрипты запуска</th>
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

| Скрипт | Поведение |
|---|---|
| `run.vbs` | Скрытый (только трей), тихий |
| `run.bat` | Запуск в трей; консоль видна только при разовой настройке venv/зависимостей |
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

## ⌨️ Использование

| Действие | Как |
|---|---|
| **Показать / Скрыть** | `Ctrl+Alt+X` или `Alt+F15` (оба настраиваются) |
| **Привязка к углу** | `Alt+F14` — цикл Верх-Лево → Верх-Право → Низ-Лево → Низ-Право |
| **Аварийный выход** | `Ctrl+Shift+Alt+Q` — принудительно завершить процесс |
| **Масштаб + / -** | `Ctrl+Колесо мыши` или `Ctrl` + `+` / `-` |
| **Сброс масштаба** | `Ctrl+0` |
| **Свернуть панель** | `Alt+D` — сжать/развернуть панель инструментов |
| **Поиск проектов** | Поле поиска; отметьте `D` для глубокого поиска по тикетам |
| **Фильтр** | Выпадающий список: Все / Живые / Готовые / Застрявшие, или клик по фазе |
| **Сортировка** | Smart / Recent / Oldest / А–Я / Я–А |
| **Пересканировать** | Кнопка `Rescan` или фоновый таймер (по умолчанию 300 с) |
| **Папка** | Кнопка `Browse` добавляет папку в набор сканирования |
| **Настройки** | Кнопка ⚙ открывает окно настроек |
| **Справка** | Кнопка `?` открывает встроенную мини-вики |
| **ПКМ по проекту** | Копировать путь, фильтр по фазе, открыть папку |
| **Двойной клик по секции** | Открывает связанный файл (STATE.md, BOARD.md, LOG.md) |
| **Перетаскивание окна** | За заголовок (или в любом месте в безрамочном режиме) |

### Окна

| Окно | Что делает |
|---|---|
| **Настройки** | Масштаб, горячие клавиши, настройка сканирования, автозапуск, поверх всех окон, шрифт, подсветка изменений, режим просмотра файлов, свои команды, язык, корни сканирования |
| **Просмотр файлов** | Чтение и правка STATE.md, BOARD.md, LOG.md — исходник или отрисованный режим |
| **Справка** | Мини-вики по всем функциям, клавишам и понятиям |
| **Подтверждение** | Диалог в винтажном стиле (заменяет нативный `confirm()`) |

<br>

---

<br>

## 🧬 Протокол SAIPEN

SAIPENVIEW — компаньон для проектов на **протоколе SAIPEN** — фреймворке-конечном автомате, который ведёт агентов по фазам:

```
INIT → PLAN → SCOUT → BUILD → REVIEW → VERIFY → SHIP → DONE
                 ↓              ↓
            HUNT / CLEAN    VALIDATE
```
`ADD`, `MARKHUNT`, `TRANSLATE`, `PREPARE` тоже существуют — полный словарь и таблица переходов в `saipenview/protocol.py` (`BLOCKED` достижим почти из любой фазы).

Каждый SAIPEN-проект хранит состояние в трёх канонических файлах:

| Файл | Назначение |
|---|---|
| `.saipen/STATE.md` | Машиночитаемый frontmatter — фаза, задача, следующее действие, блокер |
| `.saipen/BOARD.md` | Доска тикетов — секции DOING / TODO / DONE / BLOCKED |
| `.saipen/LOG.md` | Хронологический журнал событий — каждая команда и её исход |

**Сабагенты** (`saiwiki`, `saihunt`, `saitranslate`) живут в `.saipen/extensions/subs/` и общаются через `kitchen/OUTBOX.md` — встроенную шину сообщений протокола. SAIPENVIEW находит их всех и показывает единую панель.

### Соответствие протоколу

Показывать, что проект *говорит* — лишь половина дела. Проект может отлично
читаться в списке — фаза, задача, следующее действие — и при этом быть в
состоянии, которое протокол отвергает, и пока вы не запустите
`tools/validate.py` вручную, их не отличить.

Каждая строка несёт бейдж вердикта, панель деталей перечисляет, что не так:

| Вердикт | Значение |
|---|---|
| `OK` | В собственных файлах `.saipen/` проекта ничего не найдено |
| `N WARNS` | Законно, но плывёт — устаревшая контрольная точка, нестандартный глагол LOG |
| `N FAILS` | Состояние, которое протокол отвергает: `WAIT:` без категории, чекбокс, спорящий со своей секцией, `needs:` указывающий на несуществующий тикет, UTF-16 `STATE.md`, который не читает ни один другой инструмент SAIPEN |

Каждое замечание называет правило, файл и строку и пункт, из которого оно
вытекает — чтобы можно было проверить, а не поверить на слово.

Это **второе мнение, не замена** `tools/validate.py`. Оно перепроверяет только
то, что решают собственные файлы проекта, и оценивает по копии словарей
протокола — поэтому версия SAIPEN, с которой оно прочитано, печатается под
каждым вердиктом. Просмотрщику позволено отставать от протокола. Ему не
позволено отставать молча.

> 💡 *Название говорит само за себя — SAIPENVIEW даёт **вид** на каждый **SAIPEN**-проект вашей машины.*

<br>

---

<br>

## ⚙️ Конфигурация

Конфиг портативный — хранится рядом с приложением, не в `%APPDATA%`:

```
saipenview/_data/config.json
```

Основные значения по умолчанию (сокращено — полный словарь `DEFAULTS` в `saipenview/config.py`):

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

`scan_roots: null` — автопоиск всех локальных дисков.  
Список путей (например `["V:\\", "D:\\projects"]`) — ограничить сканирование.  
`default_engine` / `engine_overrides` / `agent_output_buffer_size` управляют Agent Engine (см. «Возможности»).  
Все настройки также доступны через окно **Настройки** в приложении.

<br>

---

<br>

## 🏗️ Архитектура

```
saipenview/
├── app.py              Проводка входа — трей, хоткей, окно, api, защита от дублей
├── api.py              JS-мост pywebview (66 публичных методов)
├── scanner.py          Обход дисков + фоновое пересканирование
├── parser.py           Разбор STATE.md / BOARD.md / LOG.md
├── textio.py           Единый читатель всех .saipen/-файлов — BOM, UTF-16, cp1251
├── protocol.py         Закрытые словари протокола + BASELINE_VERSION
├── conformance.py      Оценивает проект по этим словарям
├── config.py           Загрузка/сохранение настроек (атомарная запись)
├── tray.py             Иконка pystray в трее + меню
├── hotkey.py           Регистрация глобальных хоткеев (keyboard)
├── autostart.py        Автозапуск через реестр Windows
├── zone_picker.py      Оверлей привязки к углу Alt+F14 (tkinter)
├── events.py           Внутрипроцессная шина событий (EventBus)
├── guard.py            Блокировка одиночного экземпляра + передача показа
├── git_diff.py         Diff / commit / revert рабочего дерева для действий агентов
├── runtime.py          Agent Engine — менеджер процессов запущенных агентов
├── watcher.py          Watchdog-наблюдатель за .saipen/-файлами
├── engines/            Agent Engine — поддерживаемые CLI-движки (claude-code, codex,
│                       aider, gemini, cline, goose, agy, generic_cli)
├── ui/
│   ├── window.py       Окно pywebview — показать/скрыть/переключить/привязка
│   └── static/
│       ├── index.html
│       ├── style.css   Винтажная тёмно-золотая тема Win95
│       └── app.js      Логика фронтенда (~3300 строк)
├── assets/
│   └── tray_icon.png
├── screenshots/        Скриншоты README
└── _data/              Рантайм-конфиг и кэш (gitignored)
```

### Принципы дизайна

- **Один процесс** — нет фонового IPC и отдельного сервера; один Python-процесс держит и окно WebView2, и цикл сканирования в `ThreadPoolExecutor`
- **Атомарные записи** — каждая запись через temp-файл + `os.replace`; сбой не может обрезать конфиг или кэш
- **Устойчивость к устаревшему чтению** — 5-секундный опрос UI зовёт `refresh_known()` (перечитывает только `.saipen/`-файлы, без обхода дисков). Правки STATE.md видны за секунды без полного сканирования
- **Ноль CSS-переходов** — все эффекты (вспышка, тепло, hover) — JS-пересчёты `hexBlend`, строго в рамках нулевой анимации винтажной темы
- **Винтажная тема** — тёмно-коричневые поверхности, золотой текст/акценты, 3D-фаски, ноль сглаживания, шрифт Verdana_m1

<br>

---

<br>

## 🧪 Разработка

```bash
# Клонировать и зайти
git clone https://github.com/vacterro/saipenview.git
cd saipenview

# Создать venv и установить
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# Запуск
python -m saipenview
```

Подробности установки, конвенции кода и PR-процесс — в [CONTRIBUTING.md](../../CONTRIBUTING.md).

### Требования

- **Windows 10 / 11** — рантайм WebView2 (предустановлен на Win11, автоустановка на Win10)
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
  <sub>Сделано с 🐍 Python • 🖼️ pywebview • 🎨 Винтажная эстетика Win95</sub>

<br>

---

<br>

## 📸 Ещё скриншоты

<p align="center">
  <img src="../../screenshots/detail-pane.png" alt="Панель деталей SAIPENVIEW" width="85%" style="border-radius: 4px; border: 1px solid #3a3020;">
  <br>
  <em>Панель деталей: тикеты, сабагенты и просмотр файлов.</em>
</p>

<br>

</div>
