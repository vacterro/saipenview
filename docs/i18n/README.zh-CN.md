<div align="right">
  🌍 <a href="../../README.md">EN</a> | <a href="README.ar.md">AR</a> | <a href="README.bg.md">BG</a> | <a href="README.cs.md">CS</a> | <a href="README.da.md">DA</a> | <a href="README.de.md">DE</a> | <a href="README.ee.md">EE</a> | <a href="README.el.md">EL</a> | <a href="README.es.md">ES</a> | <a href="README.fi.md">FI</a> | <a href="README.fr.md">FR</a> | <a href="README.he.md">HE</a> | <a href="README.hi.md">HI</a> | <a href="README.hr.md">HR</a> | <a href="README.hu.md">HU</a> | <a href="README.id.md">ID</a> | <a href="README.it.md">IT</a> | <a href="README.ja.md">JA</a> | <a href="README.ko.md">KO</a> | <a href="README.nl.md">NL</a> | <a href="README.no.md">NO</a> | <a href="README.pl.md">PL</a> | <a href="README.pt.md">PT</a> | <a href="README.ro.md">RO</a> | <a href="README.ru.md">RU</a> | <a href="README.sk.md">SK</a> | <a href="README.sv.md">SV</a> | <a href="README.th.md">TH</a> | <a href="README.tr.md">TR</a> | <a href="README.uk.md">UK</a> | <a href="README.vi.md">VI</a> | <a href="README.zh.md">ZH</a> | <strong>ZH-CN</strong> | <a href="README.ded.md">ДЕД</a>
</div>

<div align="center">
  <img src="../../screenshots/saipen_icon.png" alt="SAIPENVIEW" width="120" height="120">
  <h1 align="center">SAIPENVIEW</h1>
  <p align="center">
    <strong>适用于本机的所有 SAIPEN 项目托盘视图查看器</strong>
    <br>
    自动扫描本地磁盘中的 <code>.saipen/</code> 项目 —— 实时显示阶段 (phase)、任务 (task)、阻塞项 (blocker)、git 状态、工单 (tickets) 以及子 Agent。
    <br>
    复古暗金 Windows 95 主题一体化仪表盘。
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

## 🚀 功能特性

<table>
<tr>
<td width="50%">

### 🔍 项目发现
- **自动扫描** 本地磁盘中的 `.saipen/` 项目
- **自定义扫描根目录** —— 可选择特定文件夹或整个磁盘
- **智能排除** —— 自动忽略 `node_modules`、`.git` 及系统目录
- **后台重新扫描** —— 可配置扫描间隔（默认 300 秒）
- **关联的 Worktrees** —— 自动检测 Git worktree 方便配置

### 📊 仪表盘
- 实时 **阶段 (phase)**、**任务 (task)**、**下一步行动 (next action)**、**阻塞项 (blocker)**
- 项目级别的 **Git 分支** 与未提交状态指示器
- 按阶段 **筛选**（全部 / 进行中 / 已完成 / 阻塞 / 自定义）
- **排序** —— 智能、最近、最旧、A–Z、Z–A
- **搜索** —— 名称/路径筛选 + 工单深度搜索
- **置顶** 重点项目，**隐藏** 不相关项目
- **闪烁高亮** —— 有变更的项目高亮闪烁并在 20 秒内渐隐
- **热度着色** —— 久未更新的项目呈现冷色，活跃项目呈现暖色

</td>
<td width="50%">

### 🧩 子 Agent
- **嵌套显示** —— `saiwiki`、`saihunt`、`saitranslate` 缩进悬挂在主项目下方
- **发件箱计数** —— 就绪/阻塞/草稿/已评审状态一目了然
- **一键合并** —— 将就绪的产出合并回主项目
- **过期警告** —— 自动检测过期的协议文件

- **Agent Engine** - 在项目中启动 `claude-code`（或其他引擎：codex, aider, gemini, cline, goose, agy, generic_cli）
  - **实时状态** - 运行/退出状态、CPU、每个项目的耗时
  - **输出控制台** - 缓冲的代理输出（默认 5000 行）、stdin 输入
  - **Kill / stop all** - 终止进程和全局停止
  - **单实例保护** - 仅一个应用实例；第二次启动重新显示窗口
### 🎮 交互控制
- **文件查看器** —— 查看与编辑 STATE.md、BOARD.md、LOG.md
  - 源码模式（可编辑） + 阅读模式（已渲染）
- **交互式工单** —— Start / Done 按钮实时更新 BOARD.md
- **快捷动作** —— 上下文感知执行 `npm run dev`、`cargo test` 等
- **自定义命令** —— 用户自定义的操作按钮
- **可折叠区块** —— 按项目独立持久化保存
- **可调侧边栏** —— 拖拽调整大小

### ⌨️ 快捷键与窗口
- **显示/隐藏** —— `Ctrl+Alt+X`（可配置）
- **贴靠角落** - `Alt+F14` 循环：左上 → 右上 → 左下 → 右下
- **缩放** —— `Ctrl+鼠标滚轮`，`Ctrl` + `+` / `-`
- **系统托盘** —— 最小化至托盘，支持静默启动
- **窗口置顶** 切换
- **开机自启** —— 可选 Windows 开机自动运行
- **无边框模式** —— 隐藏标题栏以获得极简视图

</td>
</tr>
</table>

<br>

---

<br>

## 🎯 快速开始

<table>
<tr>
<th width="33%">🐍 从源码运行</th>
<th width="33%">📜 启动脚本</th>
<th width="33%">📦 安装（计划中）</th>
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

| 脚本 | 运行行为 |
|---|---|
| `run.vbs` | 隐藏（仅托盘），静默 |
| `run.bat` | 启动到托盘；仅一次性 venv/依赖设置时显示控制台 |
均会自动创建 `.venv` 并安装依赖。

</td>
<td>

```bash
pip install saipenview
saipenview
```
即将推出 ✨

</td>
</tr>
</table>

<br>

---

## ⌨️ 使用指南

| 操作 | 方式 |
|---|---|
| **显示 / 隐藏** | `Ctrl+Alt+X` 或 `Alt+F15`（均可配置） |
| **贴靠角落** | `Alt+F14` - 循环：左上 → 右上 → 左下 → 右下 |
| **紧急强退** | `Ctrl+Shift+Alt+Q` —— 强制退出程序进程 |
| **放大 / 缩小** | `Ctrl+鼠标滚轮` 或 `Ctrl` + `+` / `-` |
| **重置缩放** | `Ctrl+0` |
| **切换工具栏** | `Alt+D` —— 折叠/展开工具栏面板 |
| **搜索项目** | 在搜索框中输入；勾选 `D` 可开启工单深度搜索 |
| **筛选** | 下拉菜单：全部 / 进行中 / 已完成 / 阻塞，或点击阶段标签 |
| **排序** | 智能 / 最近 / 最旧 / A–Z / Z–A |
| **重新扫描** | 点击 `Rescan` 或等待后台定时器（默认 300s） |
| **浏览文件夹** | 点击 `Browse` 添加文件夹至扫描列表 |
| **设置** | ⚙ 按钮打开设置弹窗 |
| **帮助 Wiki** | `?` 按钮打开内置微型 Wiki |
| **右键项目** | 复制根目录路径、按阶段筛选、打开文件夹 |
| **双击区块** | 打开对应的关联文件 (STATE.md, BOARD.md, LOG.md) |
| **拖拽窗口** | 拖拽标题栏（无边框模式下可拖拽任意位置） |

### 弹窗界面

| 弹窗 | 功能说明 |
|---|---|
| **设置** | 缩放、快捷键、扫描微调、开机自启、窗口置顶、字体、闪烁切换、默认文件查看器、自定义命令、语言、扫描根目录 |
| **文件查看器** | 查看与编辑 STATE.md、BOARD.md、LOG.md —— 源码（原始）或阅读（渲染）模式 |
| **帮助** | 涵盖所有功能、快捷键和概念的完整微型 Wiki |
| **确认框** | 复古风格 DOM 对话框（替代原生 `confirm()`） |

<br>

---

## 🧬 SAIPEN 协议

SAIPENVIEW 是基于 **SAIPEN 协议** 开发的配套工具。SAIPEN 协议是一个状态机框架，引导 AI Agent 按既定阶段推进项目工作：

```
INIT → PLAN → SCOUT → BUILD → REVIEW → VERIFY → SHIP → DONE
                 ↓              ↓
            HUNT / CLEAN    VALIDATE
```

`ADD`、`MARKHUNT`、`TRANSLATE`、`PREPARE` 也存在 - 完整词汇表和状态转移表位于 `saipenview/protocol.py`（`BLOCKED` 可从大多数阶段到达）。
每个 SAIPEN 项目都会在三个规范文件中存储其状态：

| 文件 | 用途 |
|---|---|
| `.saipen/STATE.md` | 机器可读的前置元数据 —— 阶段 (phase)、任务 (task)、下一步行动 (next action)、阻塞项 (blocker) |
| `.saipen/BOARD.md` | 工单看板 —— DOING / TODO / DONE / BLOCKED 区块 |
| `.saipen/LOG.md` | 按时间顺序记录的事件日志 —— 记录每个命令及其运行结果 |

**SubSaipen Agent**（`saiwiki`、`saihunt`、`saitranslate`）存放于 `.saipen/extensions/subs/` 中，并通过 `kitchen/OUTBOX.md`（协议内置的跨 Agent 消息总线）进行通信。SAIPENVIEW 能自动发现所有子 Agent 并渲染统一的仪表盘。

### 规范一致性校验 (Conformance)

仅仅展示项目“表象”只做对了一半。一个项目可能在列表中展示正常（阶段、任务、下一步行动均在），但其状态却可能违反了协议规定。在手动运行 `tools/validate.py` 之前，你无法区分这两者。

每一行项目都带有合规判定徽章，详情面板会列出具体存在的问题：

| 判定 | 含义 |
|---|---|
| `OK` | 未在该项目的 `.saipen/` 文件中发现任何问题 |
| `N WARNS` | 合规但存在偏离 —— 如检查点过旧、LOG 中使用了非标准动词 |
| `N FAILS` | 协议拒绝的状态 —— 如未说明类别的 `WAIT:`、与所在区块状态矛盾的复选框、指向不存在工单的 `needs:`，或者其他 SAIPEN 工具无法读取的 UTF-16 格式 `STATE.md` |

每条检查结果都会明确指出规则名称、文件名与行号以及对应的协议条款，以便有据可查而非凭空推断。

这是针对 `tools/validate.py` 的**辅助判定而非替代品**。它仅对项目自身文件可决定的内容进行重新检查，并依据协议词汇表副本进行评分 —— 因此每次判定下方都会打印所依据的 SAIPEN 版本。允许查看器版本滞后于协议规范，但不允许静默滞后。

> 💡 *“SAIPENVIEW” 的名称代表了一切 —— 它为本机的每个 **SAIPEN** 项目提供清晰直观的 **视图** (view)。*

<br>

---

## ⚙️ 配置说明

配置文件为便携式 —— 存储在应用同级目录下，而非 `%APPDATA%`：

```
saipenview/_data/config.json
```

主要默认值（节选 - 完整 `DEFAULTS` 字典位于 `saipenview/config.py`）：

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

设置 `scan_roots: null` 将自动检测所有本地磁盘。  
设置为路径列表（例如 `["V:\\", "D:\\projects"]`）可限定扫描范围。  
`default_engine` / `engine_overrides` / `agent_output_buffer_size` 驱动 Agent Engine（见功能）。  
所有设置项均可在应用内的 **设置** 弹窗中进行配置。

<br>

---

## 🏗️ 架构设计

```
saipenview/
├── app.py              入口接线 - 托盘、热键、窗口、api、单实例保护
├── api.py              面向 JS 的 pywebview 桥接（66 个公共方法）
├── scanner.py          磁盘遍历 + 后台重新扫描循环
├── parser.py           STATE.md / BOARD.md / LOG.md 解析器
├── textio.py           统一的 .saipen/ 文件读取器 —— 处理 BOM、UTF-16、cp1251
├── protocol.py         协议的封闭词汇表 + BASELINE_VERSION
├── conformance.py      对照词汇表校验项目规范合规性
├── config.py           配置加载/保存（原子化写入）
├── tray.py             pystray 系统托盘图标与菜单
├── hotkey.py           全局快捷键注册 (keyboard 库)
├── autostart.py        Windows 注册表开机自启管理
├── zone_picker.py      Alt+F14 贴靠角落覆盖层（tkinter）
├── events.py           进程内事件总线（EventBus）
├── guard.py            单实例锁 + 显示请求交接
├── git_diff.py         用于代理操作的工作树 diff / commit / revert
├── runtime.py          Agent Engine - 已启动代理的进程管理器
├── watcher.py          监视 .saipen/ 文件的 Watchdog 文件监视器
├── engines/            Agent Engine - 支持的 CLI 引擎（claude-code, codex,
│                       aider, gemini, cline, goose, agy, generic_cli)
├── ui/
│   ├── window.py       pywebview 窗口 —— 显示/隐藏/切换/吸附
│   └── static/
│       ├── index.html
│       ├── style.css   复古暗金 Win95 主题
│       └── app.js      前端逻辑（约 3300 行）
├── assets/
│   └── tray_icon.png
├── screenshots/        README 截图
└── _data/              运行时配置与缓存 (.gitignore 已忽略)
```

### 设计原则

- **单进程设计** —— 无后台 IPC，无独立服务器；单个 Python 进程通过 `ThreadPoolExecutor` 同时承载 WebView2 窗口与扫描循环
- **原子化写入** —— 每次文件写入均采用临时文件 + `os.replace`；程序崩溃绝不会导致配置或缓存文件损坏截断
- **防过期读取安全机制** —— 5 秒一次的前端轮询调用 `refresh_known()`（仅重新读取 `.saipen/` 文件，无需遍历目录）。对 STATE.md 的修改会在数秒内显示，且不会触发完整磁盘扫描
- **无 CSS 过渡动画** —— 所有视觉效果（闪烁、热度、悬停）均由 JavaScript 驱动的 `hexBlend` 重新计算，严格遵循复古主题零动画的约束
- **复古主题风格** —— 深棕色表面、金色文本/高亮、3D 凸起边框、零抗锯齿、Verdana_m1 字体

<br>

---

## 🧪 开发指南

```bash
# 克隆仓库并进入目录
git clone https://github.com/vacterro/saipenview.git
cd saipenview

# 创建虚拟环境并安装依赖
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# 运行程序
python -m saipenview
```

有关详细设置、代码规范和 PR 工作流，请参阅 [CONTRIBUTING.md](../../CONTRIBUTING.md)。

### 环境要求

- **Windows 10 / 11** —— WebView2 运行时（Win11 预装，Win10 自动安装）
- **Python 3.10+**
- 依赖项：`pystray`、`keyboard`、`pywebview`、`Pillow`、`watchdog`、`psutil`

<br>

---

## 📄 开源协议

MIT 协议 —— 详情参见 [LICENSE](../../LICENSE)。

<br>

---

<div align="center">
  <sub>基于 🐍 Python • 🖼️ pywebview • 🎨 复古 Win95 美学构建</sub>

<br>

---

## 📸 更多截图

<p align="center">
  <img src="../../screenshots/detail-pane.png" alt="SAIPENVIEW 详情面板" width="85%" style="border-radius: 4px; border: 1px solid #3a3020;">
  <br>
  <em>包含工单、子 Agent 及文件查看器的详情面板。</em>
</p>

<br>

</div>
