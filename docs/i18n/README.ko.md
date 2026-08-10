<div align="right">

  🌍 <a href="../../README.md">EN</a> | <a href="README.ar.md">AR</a> | <a href="README.bg.md">BG</a> | <a href="README.cs.md">CS</a> | <a href="README.da.md">DA</a> | <a href="README.de.md">DE</a> | <a href="README.ee.md">EE</a> | <a href="README.el.md">EL</a> | <a href="README.es.md">ES</a> | <a href="README.fi.md">FI</a> | <a href="README.fr.md">FR</a> | <a href="README.he.md">HE</a> | <a href="README.hi.md">HI</a> | <a href="README.hr.md">HR</a> | <a href="README.hu.md">HU</a> | <a href="README.id.md">ID</a> | <a href="README.it.md">IT</a> | <a href="README.ja.md">JA</a> | <strong>KO</strong> | <a href="README.nl.md">NL</a> | <a href="README.no.md">NO</a> | <a href="README.pl.md">PL</a> | <a href="README.pt.md">PT</a> | <a href="README.ro.md">RO</a> | <a href="README.ru.md">RU</a> | <a href="README.sk.md">SK</a> | <a href="README.sv.md">SV</a> | <a href="README.th.md">TH</a> | <a href="README.tr.md">TR</a> | <a href="README.uk.md">UK</a> | <a href="README.vi.md">VI</a> | <a href="README.zh.md">ZH</a> | <a href="README.zh-CN.md">ZH-CN</a> | <a href="README.ded.md">ДЕД</a>
</div>
> **Note:** This is a translated copy. The canonical documentation is [README.md](../../README.md) — this translation may lag the English original.

<div align="center">
  <img src="../../screenshots/saipen_icon.png" alt="SAIPENVIEW" width="120" height="120">
  <h1 align="center">SAIPENVIEW</h1>
  <p align="center">
    <strong>내 컴퓨터의 모든 SAIPEN 프로젝트를 위한 데스크톱 트레이 뷰어</strong>
    <br>
    로컬 드라이브의 <code>.saipen/</code> 프로젝트 자동 탐지 — 실시간 페이즈, 태스크, 블로커, git 상태, 티켓 및 서브 에이전트.
    <br>
    클래식 다크 골드 Win95 테마의 단일 대시보드.
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

## 🚀 주요 기능

<table>
<tr>
<td width="50%">

### 🔍 자동 탐지
- **자동 스캔** — 로컬 드라이브에서 `.saipen/` 프로젝트 자동 탐색
- **사용자 지정 루트** — 특정 폴더 또는 전체 드라이브 선택
- **스마트 제외** — `node_modules`, `.git`, 시스템 디렉터리 제외
- **백그라운드 재스캔** — 간격 설정 가능 (기본값 300초)
- **연결된 워크트리** — 빠른 설정을 위한 git 워크트리 탐지

### 📊 대시보드
- 실시간 **페이즈(phase)**, **태스크(task)**, **다음 작업(next action)**, **블로커(blocker)**
- 프로젝트별 **Git 브랜치** + 변경사항(dirty-state) 표시
- 페이즈별 **필터링** (전체 / 진행 중 / 완료 / 차단됨 / 사용자 지정)
- **정렬** — 스마트, 최신순, 오래된순, A–Z, Z–A
- **검색** — 이름/루트 필터 + 티켓 상세 검색
- 프로젝트 **고정(Pin)** 및 불필요한 프로젝트 **숨기기**
- **플래시 하이라이트** — 변경된 프로젝트가 20초간 강조 후 서서히 사라짐
- **히트 컬러링** — 오래된 프로젝트는 차갑게, 최신 프로젝트는 따뜻하게 표시

</td>
<td width="50%">

### 🧩 서브 에이전트
- **계층형 표시** — 상위 프로젝트 하위에 `saiwiki`, `saihunt`, `saitranslate` 들여쓰기 표시
- **아웃박스 개수** — 준비됨/차단됨/초안/검토됨 한눈에 확인
- **원클릭 수집** — 준비된 항목을 메인 프로젝트로 병합
- **만료 경고** — 오래된 프로토콜 파일 탐지

- **Agent Engine** - 프로젝트에서 `claude-code`(또는 다른 엔진: codex, aider, gemini, cline, goose, agy, generic_cli) 실행
  - **실시간 상태** - 실행/종료 상태, CPU, 프로젝트별 경과 시간
  - **출력 콘솔** - 버퍼링된 에이전트 출력(기본 5000줄), stdin 입력
  - **Kill / stop all** - 프로세스 종료 및 전체 중지
  - **단일 인스턴스 보호** - 앱 인스턴스 하나만; 두 번째 실행은 창을 다시 표시
### 🎮 상호작용
- **파일 뷰어** — STATE.md, BOARD.md, LOG.md 조회 및 편집
  - 소스 모드 (편집 가능) + 리더 모드 (렌더링됨)
- **대화형 티켓** — 시작 / 완료 버튼으로 BOARD.md 실시간 업데이트
- **빠른 실행** — 컨텍스트 기반 `npm run dev`, `cargo test` 등
- **사용자 지정 명령** — 사용자 정의 액션 버튼
- **접을 수 있는 섹션** — 프로젝트별 설정 유지
- **크기 조절 가능한 사이드바** — 드래그하여 크기 조절

### ⌨️ 단축키 및 창 관리
- **표시/숨기기** — `Ctrl+Alt+X` (설정 가능)
- **모서리 맞춤** - `Ctrl+Q` 순환: 좌상 → 우상 → 좌하 → 우하
- **확대/축소** — `Ctrl+마우스휠`, `Ctrl+`+`/`-`
- **시스템 트레이** — 트레이로 최소화, 숨김 상태로 시작
- **최상단 고정** 토글
- **자동 시작** — Windows 시작 시 자동 실행 옵션
- **프레임리스 모드** — 타이틀바를 숨겨 울트라 미니멀 뷰 제공

</td>
</tr>
</table>

<br>

---

<br>

## 🎯 빠른 시작

<table>
<tr>
<th width="33%">🐍 소스에서 실행</th>
<th width="33%">📜 실행 스크립트</th>
<th width="33%">📦 설치 (예정)</th>
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

| 스크립트 | 동작 |
|---|---|
| `run.vbs` | 숨김(트레이 전용), 조용함 |
| `run.bat` | 트레이로 실행; 콘솔은 1회성 venv/의존성 설정 중에만 표시 |
둘 다 `.venv`를 자동 생성하고 의존성을 설치합니다.

</td>
<td>

```bash
pip install saipenview
saipenview
```
출시 예정 ✨

</td>
</tr>
</table>

<br>

---

## ⌨️ 사용법

| 작업 | 방법 |
|---|---|
| **표시 / 숨기기** | `Ctrl+Alt+X` 또는 `Alt+F15` (둘 다 변경 가능) |
| **모서리 맞춤** | `Ctrl+Q` - 순환: 왼쪽-위 → 오른쪽-위 → 왼쪽-아래 → 오른쪽-아래 |
| **강제 종료** | `Ctrl+Shift+Alt+Q` — 프로세스 강제 종료 |
| **확대 / 축소** | `Ctrl+마우스휠` 또는 `Ctrl` + `+` / `-` |
| **확대/축소 초기화** | `Ctrl+0` |
| **툴바 토글** | `Alt+D` — 툴바 패널 접기/펼치기 |
| **프로젝트 검색** | 검색창에 입력; 티켓 상세 검색은 `D` 체크 |
| **필터** | 드롭다운: 전체 / 진행 중 / 완료 / 차단됨, 또는 페이즈 알약 클릭 |
| **정렬** | 스마트 / 최신순 / 오래된순 / A–Z / Z–A |
| **재스캔** | `Rescan` 클릭 또는 백그라운드 타이머 대기 (기본값 300초) |
| **폴더 탐색** | `Browse`를 클릭하여 스캔 대상 폴더 추가 |
| **설정** | ⚙ 버튼을 눌러 설정 모달 열기 |
| **도움말 위키** | `?` 버튼을 눌러 내장 미니 위키 열기 |
| **프로젝트 우클릭** | 루트 경로 복사, 페이즈별 필터링, 폴더 열기 |
| **섹션 더블클릭** | 연결된 파일 열기 (STATE.md, BOARD.md, LOG.md) |
| **창 드래그** | 타이틀 바 드래그 (프레임리스 모드에서는 어디서나 가능) |

### 모달

| 모달 | 기능 |
|---|---|
| **설정** | 확대/축소, 단축키, 스캔 조정, 자동 시작, 최상단 고정, 폰트, 플래시 토글, 기본 파일 뷰어, 사용자 지정 명령, 언어 설정, 스캔 루트 |
| **파일 뷰어** | STATE.md, BOARD.md, LOG.md 읽기 및 편집 — 소스(원본) 또는 리더(렌더링) 모드 |
| **도움말** | 모든 기능, 단축키, 개념을 다루는 종합 미니 위키 |
| **확인** | 빈티지 스타일 DOM 대화상자 (네이티브 `confirm()` 대체) |

<br>

---

## 🧬 SAIPEN 프로토콜

SAIPENVIEW는 정의된 페이즈를 통해 AI 에이전트의 프로젝트 작업을 안내하는 상태 머신 프레임워크인 **SAIPEN 프로토콜**을 사용하는 프로젝트의 동반 도구입니다:

```
INIT → PLAN → SCOUT → BUILD → REVIEW → VERIFY → SHIP → DONE
                 ↓              ↓
            HUNT / CLEAN    VALIDATE
```

`ADD`, `MARKHUNT`, `TRANSLATE`, `PREPARE`도 존재합니다 - 전체 어휘와 전이 테이블은 `saipenview/protocol.py`에 있습니다(`BLOCKED`는 대부분의 단계에서 도달 가능).
각 SAIPEN 프로젝트는 세 개의 표준 파일에 상태를 저장합니다:

| 파일 | 용도 |
|---|---|
| `.saipen/STATE.md` | 머신 가독형 프론트매터 — 페이즈, 태스크, 다음 작업, 블로커 |
| `.saipen/BOARD.md` | 티켓 보드 — DOING / TODO / DONE / BLOCKED 섹션 |
| `.saipen/LOG.md` | 시간순 이벤트 로그 — 모든 명령 및 결과 |

**SubSaipen 에이전트** (`saiwiki`, `saihunt`, `saitranslate`)는 `.saipen/extensions/subs/`에 위치하며, 프로토콜의 내장 에이전트 간 메시지 버스인 `kitchen/OUTBOX.md`를 통해 통신합니다. SAIPENVIEW는 이들을 모두 탐지하여 통합 대시보드로 렌더링합니다.

### 적합성 (Conformance)

프로젝트가 *말하는* 내용을 보여주는 것은 절반에 불과합니다. 목록에서 페이즈, 태스크, 다음 작업이 완벽하게 보일 수 있지만 프로토콜이 거부하는 상태일 수 있으며, 직접 `tools/validate.py`를 실행하기 전까지는 이 둘을 구분할 방법이 없었습니다.

각 행에는 판정 배지가 표시되며, 상세 패널에는 잘못된 항목이 나열됩니다:

| 판정 | 의미 |
|---|---|
| `OK` | 프로젝트의 `.saipen/` 파일에서 문제 없음 |
| `N WARNS` | 규격에 맞지만 이탈 발생 — 오래된 체크포인트, 비표준 LOG 동사 사용 |
| `N FAILS` | 프로토콜이 거부하는 상태 — 카테고리가 없는 `WAIT:`, 섹션과 일치하지 않는 체크박스, 존재하지 않는 티켓을 가리키는 `needs:`, 다른 SAIPEN 도구가 읽을 수 없는 UTF-16 `STATE.md` 등 |

각 항목은 규칙, 파일 및 줄 번호, 출처 조항을 명시하므로 맹목적으로 받아들이지 않고 직접 확인할 수 있습니다.

이것은 `tools/validate.py`를 대체하는 것이 아닌 **보조적인 확인 기능**입니다. 프로젝트 자체 파일로 판단할 수 있는 항목만 재검증하며 프로토콜 어휘 사본을 기준으로 평가하므로, 각 판정 아래에 읽어온 SAIPEN 버전이 표시됩니다. 뷰어가 프로토콜보다 지연되는 것은 허용되지만, 조용히 지연되는 것은 허용되지 않습니다.

> 💡 *"SAIPENVIEW"라는 이름 그대로 — 컴퓨터의 모든 **SAIPEN** 프로젝트에 대한 **뷰(view)**를 제공합니다.*

<br>

---

## ⚙️ 설정

설정은 이식 가능하며, `%APPDATA%`가 아닌 앱과 동일한 위치에 저장됩니다:

```
saipenview/_data/config.json
```

주요 기본값(축약 - 전체 `DEFAULTS` 사전은 `saipenview/config.py`에 있음):

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

모든 로컬 드라이브를 자동 탐지하려면 `scan_roots: null`로 설정하세요.  
스캔 대상을 제한하려면 경로 목록(예: `["V:\\", "D:\\projects"]`)을 지정하세요.  
`default_engine` / `engine_overrides` / `agent_output_buffer_size`가 Agent Engine을 구동합니다(기능 참조).  
모든 설정은 앱 내 **설정(Settings)** 모달을 통해서도 변경할 수 있습니다.

<br>

---

## 🏗️ 아키텍처

```
saipenview/
├── app.py              진입 배선 - 트레이, 단축키, 창, api, 단일 인스턴스 보호
├── api.py              JS 지향 pywebview 브리지(공개 메서드 66개)
├── scanner.py          드라이브 탐색 + 백그라운드 재스캔 루프
├── parser.py           STATE.md / BOARD.md / LOG.md 파싱
├── textio.py           모든 .saipen/ 파일 단일 리더 — BOM, UTF-16, cp1251
├── protocol.py         프로토콜의 폐쇄형 어휘 + BASELINE_VERSION
├── conformance.py      어휘 기준 프로젝트 적합성 평가
├── config.py           설정 로드/저장 (원자적 쓰기)
├── tray.py             pystray 시스템 트레이 아이콘 + 메뉴
├── hotkey.py           전역 단축키 등록 (keyboard 라이브러리)
├── autostart.py        Windows 레지스트리 자동 시작 관리
├── zone_picker.py      Ctrl+Q 모서리 맞춤 오버레이(tkinter)
├── events.py           프로세스 내 이벤트 버스(EventBus)
├── guard.py            단일 인스턴스 잠금 + 표시 요청 전달
├── git_diff.py         에이전트 작업용 작업 트리 diff / commit / revert
├── runtime.py          Agent Engine - 실행된 에이전트의 프로세스 관리자
├── watcher.py          .saipen/ 파일 감시용 Watchdog 파일 감시자
├── engines/            Agent Engine - 지원 CLI 엔진(claude-code, codex,
│                       aider, gemini, cline, goose, agy, generic_cli)
├── ui/
│   ├── window.py       pywebview 창 — 표시/숨기기/토글/스냅
│   └── static/
│       ├── index.html
│       ├── style.css   빈티지 다크 골드 Win95 테마
│       └── app.js      프론트엔드 로직(약 3300줄)
├── assets/
│   └── tray_icon.png
├── screenshots/        README 스크린샷
└── _data/              런타임 설정 + 캐시 (gitignored)
```

### 설계 원칙

- **단일 프로세스** — 백그라운드 IPC 및 별도 서버 없음; 단일 Python 프로세스가 WebView2 창과 `ThreadPoolExecutor` 스캔 루프를 모두 호스팅
- **원자적 쓰기** — 모든 파일 쓰기는 임시 파일 + `os.replace`를 사용하여 비정상 종료 시에도 설정이나 캐시 손상 방지
- **지연 읽기 안전성** — 5초 UI 폴링이 `refresh_known()`을 호출(전체 디렉터리 탐색 없이 `.saipen/` 파일만 재읽기). 전체 드라이브 스캔 없이 몇 초 내에 STATE.md 변경 사항 반영
- **CSS 트랜지션 없음** — 모든 시각 효과(플래시, 히트, 호버)는 자바스크립트 기반 `hexBlend` 재계산으로 처리되며 빈티지 테마의 애니메이션 제로 제약을 엄격히 준수
- **빈티지 테마** — 다크 브라운 표면, 골드 텍스트/포인트, 3D 입체 테두리, 안티앨리어싱 없음, Verdana_m1 폰트

<br>

---

## 🧪 개발

```bash
# 클론 및 이동
git clone https://github.com/vacterro/saipenview.git
cd saipenview

# venv 생성 및 설치
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# 실행
python -m saipenview
```

자세한 환경 설정, 코딩 컨벤션 및 PR 워크플로는 [CONTRIBUTING.md](../../CONTRIBUTING.md)를 참고하세요.

### 요구 사항

- **Windows 10 / 11** — WebView2 런타임 (Win11 기본 탑재, Win10 자동 설치)
- **Python 3.10 이상**
- 의존성 패키지: `pystray`, `keyboard`, `pywebview`, `Pillow`, `watchdog`, `psutil`

<br>

---

## 📄 라이선스

MIT — [LICENSE](../../LICENSE) 참고.

<br>

---

<div align="center">
  <sub>🐍 Python • 🖼️ pywebview • 🎨 빈티지 Win95 감성으로 제작됨</sub>

<br>

---

## 📸 추가 스크린샷

<p align="center">
  <img src="../../screenshots/detail-pane.png" alt="SAIPENVIEW Detail Pane" width="85%" style="border-radius: 4px; border: 1px solid #3a3020;">
  <br>
  <em>티켓, 서브 에이전트 및 파일 뷰어가 포함된 상세 패널.</em>
</p>

<br>

</div>
