<div align="right">

  🌍 <a href="../../README.md">EN</a> | <a href="README.ar.md">AR</a> | <a href="README.bg.md">BG</a> | <a href="README.cs.md">CS</a> | <a href="README.da.md">DA</a> | <a href="README.de.md">DE</a> | <a href="README.ee.md">EE</a> | <a href="README.el.md">EL</a> | <a href="README.es.md">ES</a> | <a href="README.fi.md">FI</a> | <a href="README.fr.md">FR</a> | <a href="README.he.md">HE</a> | <a href="README.hi.md">HI</a> | <a href="README.hr.md">HR</a> | <a href="README.hu.md">HU</a> | <a href="README.id.md">ID</a> | <a href="README.it.md">IT</a> | <a href="README.ja.md">JA</a> | <a href="README.ko.md">KO</a> | <a href="README.nl.md">NL</a> | <a href="README.no.md">NO</a> | <a href="README.pl.md">PL</a> | <strong>PT</strong> | <a href="README.ro.md">RO</a> | <a href="README.ru.md">RU</a> | <a href="README.sk.md">SK</a> | <a href="README.sv.md">SV</a> | <a href="README.th.md">TH</a> | <a href="README.tr.md">TR</a> | <a href="README.uk.md">UK</a> | <a href="README.vi.md">VI</a> | <a href="README.zh.md">ZH</a> | <a href="README.zh-CN.md">ZH-CN</a> | <a href="README.ded.md">ДЕД</a>
</div>
> **Note:** This is a translated copy. The canonical documentation is [README.md](../../README.md) — this translation may lag the English original.

<div align="center">
  <img src="../../screenshots/saipen_icon.png" alt="SAIPENVIEW" width="120" height="120">
  <h1 align="center">SAIPENVIEW</h1>
  <p align="center">
    <strong>Visualizador na bandeja do sistema para todos os projetos SAIPEN na sua máquina</strong>
    <br>
    Descoberta automática de projetos <code>.saipen/</code> em unidades locais — fase em tempo real, tarefa, bloqueio, status git, tickets e subagentes.
    <br>
    Um painel vintage com tema Win95 escuro-dourado.
  </p>
  <p>
    <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.10%2B-blue?style=flat-square&logo=python&logoColor=white" alt="Python"></a>
    <a href="../../LICENSE"><img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="Licença"></a>
    <a href="https://github.com/vacterro/saipenview"><img src="https://img.shields.io/badge/platform-Windows-orange?style=flat-square&logo=windows&logoColor=white" alt="Plataforma"></a>
    <a href="https://github.com/vacterro/saipenview/releases"><img src="https://img.shields.io/github/v/release/vacterro/saipenview?style=flat-square&include_prereleases" alt="Versão"></a>
    <a href="https://github.com/vacterro/saipenview/actions"><img src="https://img.shields.io/github/actions/workflow/status/vacterro/saipenview/ci.yml?branch=main&style=flat-square&logo=github" alt="CI"></a>
  </p>
</div>

<br>

---

## 🚀 Funcionalidades

<table>
<tr>
<td width="50%">

### 🔍 Descoberta
- **Verificação automática** de unidades locais em busca de projetos `.saipen/`
- **Raízes personalizadas** — escolha pastas ou unidades inteiras
- **Exclusões inteligentes** — `node_modules`, `.git`, diretórios de sistema
- **Reverificação em segundo plano** — intervalo configurável (padrão 300s)
- **Worktrees vinculados** — deteta worktrees do git para configuração fácil

### 📊 Painel de Controle
- **Fase**, **tarefa**, **próxima ação**, **bloqueio** em tempo real
- **Ramo Git** + indicador de alterações por projeto
- **Filtro** por fase (Tudo / Ativo / Concluído / Bloqueado / personalizado)
- **Ordenação** — Inteligente, Recente, Mais antigo, A–Z, Z–A
- **Pesquisa** — filtro por nome/raiz + pesquisa profunda de tickets
- **Fixar** projetos no topo, **ocultar** os irrelevantes
- **Destaque por brilho** — projetos alterados brilham e esvanecem em 20s
- **Coloração térmica** — projetos inativos arrefecem, projetos recentes aquecem

</td>
<td width="50%">

### 🧩 Subagentes
- **Exibição em árvore** — `saiwiki`, `saihunt`, `saitranslate` recuados sob o principal
- **Contagem da caixa de saída** — pronto/bloqueado/rascunho/revisto num relance
- **Coleta num clique** — incorpora entradas prontas no projeto principal
- **Aviso de obsolescência** — deteta ficheiros de protocolo desatualizados

- **Agent Engine** - iniciar `claude-code` (ou outros motores: codex, aider, gemini, cline, goose, agy, generic_cli) em um projeto
  - **Status ao vivo** - estado em execução/saída, CPU, tempo decorrido por projeto
  - **Console de saída** - saída do agente em buffer (padrão 5000 linhas), entrada stdin
  - **Kill / stop all** - matar processo e parada global
  - **Proteção de instância única** - apenas uma instância do app; segundo início reexibe a janela
### 🎮 Interação
- **Visualizador de ficheiros** — ler e editar STATE.md, BOARD.md, LOG.md
  - Modo Código Fonte (editável) + Modo Leitor (renderizado)
- **Tickets interativos** — botões Iniciar / Concluído atualizam o BOARD.md em tempo real
- **Ações rápidas** — contextuais `npm run dev`, `cargo test`, etc.
- **Comandos personalizados** — botões de ação definidos pelo utilizador
- **Secções recolhíveis** — por projeto, persistidas
- **Barra lateral redimensionável** — arraste para redimensionar

### ⌨️ Atalhos e Janela
- **Mostrar/Ocultar** — `Ctrl+Alt+X` (configurável)
- **Fixar nos cantos** - `Ctrl+Q` alterna SE → SD → IE → ID
- **Zoom** — `Ctrl+RodaDoRato`, `Ctrl`+`+`/`-`
- **Bandeja do sistema** — minimizar para a bandeja, iniciar oculto
- Alternar **Sempre no topo**
- **Início automático** — inicialização opcional no Windows
- **Modo sem moldura** — desativa a barra de título para uma visualização ultra-minimalista

</td>
</tr>
</table>

<br>

---

<br>

## 🎯 Início Rápido

<table>
<tr>
<th width="33%">🐍 Executar a partir do código-fonte</th>
<th width="33%">📜 Scripts de inicialização</th>
<th width="33%">📦 Instalar (futuro)</th>
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

| Script | Comportamento |
|---|---|
| `run.vbs` | Oculto (somente bandeja), silencioso |
| `run.bat` | Início na bandeja; console visível apenas durante a configuração única de venv/dependências |
Ambos criam automaticamente o `.venv` e instalam dependências.

</td>
<td>

```bash
pip install saipenview
saipenview
```
Em breve ✨

</td>
</tr>
</table>

<br>

---

## ⌨️ Utilização

| Ação | Como |
|---|---|
| **Mostrar / Ocultar** | `Ctrl+Alt+X` ou `Alt+F15` (ambos configuráveis) |
| **Fixar no canto** | `Ctrl+Q` - alterna Sup. Esquerdo → Sup. Direito → Inf. Esquerdo → Inf. Direito |
| **Interrupção de emergência** | `Ctrl+Shift+Alt+Q` — forçar o encerramento do processo |
| **Aumentar / reduzir zoom** | `Ctrl+RodaDoRato` ou `Ctrl` + `+` / `-` |
| **Redefinir zoom** | `Ctrl+0` |
| **Alternar barra de ferramentas** | `Alt+D` — recolher/expandir o painel da barra de ferramentas |
| **Pesquisar projetos** | Escreva na caixa de pesquisa; marque `D` para pesquisa profunda em tickets |
| **Filtrar** | Menu suspenso: Tudo / Ativo / Concluído / Bloqueado, ou clique na etiqueta de fase |
| **Ordenar** | Inteligente / Recente / Mais antigo / A–Z / Z–A |
| **Reverificar** | Clique em `Reverificar` ou aguarde o temporizador em segundo plano (padrão 300s) |
| **Procurar pasta** | Clique em `Procurar` para adicionar uma pasta ao conjunto de verificação |
| **Definições** | O botão ⚙ abre a janela de definições |
| **Wiki de ajuda** | O botão `?` abre a mini-wiki integrada |
| **Clique direito no projeto** | Copiar caminho raiz, filtrar por fase, abrir pasta |
| **Duplo clique na secção** | Abre o ficheiro associado (STATE.md, BOARD.md, LOG.md) |
| **Arrastar janela** | Arraste a barra de título (ou qualquer local no modo sem moldura) |

### Janelas Modais

| Modal | O que faz |
|---|---|
| **Definições** | Zoom, atalhos, ajuste de verificação, início automático, sempre no topo, fonte, alternar brilho, modo padrão do visualizador, comandos personalizados, idioma, raízes de verificação |
| **Visualizador de Ficheiros** | Ler e editar STATE.md, BOARD.md, LOG.md — Modo Fonte (bruto) ou Leitor (renderizado) |
| **Ajuda** | Mini-wiki abrangente cobrindo cada funcionalidade, atalho e conceito |
| **Confirmação** | Caixas de diálogo DOM em estilo vintage (substitui o `confirm()` nativo) |

<br>

---

## 🧬 Protocolo SAIPEN

O SAIPENVIEW é um complemento para projetos que utilizam o **Protocolo SAIPEN** — uma estrutura de máquina de estados que guia agentes de IA no trabalho de projetos em fases definidas:

```
INIT → PLAN → SCOUT → BUILD → REVIEW → VERIFY → SHIP → DONE
                 ↓              ↓
            HUNT / CLEAN    VALIDATE
```

`ADD`, `MARKHUNT`, `TRANSLATE`, `PREPARE` também existem - o vocabulário completo e a tabela de transições vivem em `saipenview/protocol.py` (`BLOCKED` é alcançável pela maioria das fases).
Cada projeto SAIPEN guarda o seu estado em três ficheiros canónicos:

| Ficheiro | Finalidade |
|---|---|
| `.saipen/STATE.md` | Frontmatter legível por máquina — fase, tarefa, próxima ação, bloqueio |
| `.saipen/BOARD.md` | Quadro de tickets — secções FAZENDO / A FAZER / CONCLUÍDO / BLOQUEADO |
| `.saipen/LOG.md` | Registo cronológico de eventos — cada comando e o seu resultado |

Os **agentes SubSaipen** (`saiwiki`, `saihunt`, `saitranslate`) residem em `.saipen/extensions/subs/` e comunicam através de `kitchen/OUTBOX.md` — o barramento de mensagens entre agentes integrado no protocolo. O SAIPENVIEW descobre todos eles e renderiza um painel unificado.

### Conformidade

Mostrar o que um projeto *diz* é apenas metade da questão. Um projeto pode parecer perfeito na lista — uma fase, uma tarefa, uma próxima ação — enquanto está num estado rejeitado pelo protocolo; até executar `tools/validate.py` manualmente, não havia forma de os distinguir.

Cada linha exibe um selo de veredito, e o painel de detalhes lista o que está errado:

| Veredito | Significado |
|---|---|
| `OK` | Nenhuma irregularidade encontrada nos ficheiros `.saipen/` deste projeto |
| `N WARNS` | Válido, mas com desvios — um ponto de controlo antigo, um verbo de LOG não padrão |
| `N FAILS` | Um estado rejeitado pelo protocolo: um `WAIT:` sem categoria, uma caixa de seleção em desacordo com a sua secção, um `needs:` a apontar para um ticket inexistente, um `STATE.md` em UTF-16 que nenhuma outra ferramenta SAIPEN consegue ler |

Cada ocorrência indica a regra, o ficheiro e linha, e a cláusula de onde provém, para que possa ser verificada em vez de aceite cegamente.

Esta é uma **segunda opinião, não uma substituição** do `tools/validate.py`. Re-verifica apenas o que os próprios ficheiros do projeto podem decidir e avalia contra uma cópia dos vocabulários do protocolo — assim, a versão do SAIPEN lida é exibida sob cada veredito. O visualizador pode estar desatualizado em relação ao protocolo; o que não pode é estar desatualizado silenciosamente.

> 💡 *O nome "SAIPENVIEW" diz tudo — oferece uma **visualização (view)** de cada projeto **SAIPEN** na sua máquina.*

<br>

---

## ⚙️ Configuração

A configuração é portátil — guardada junto à aplicação, não em `%APPDATA%`:

```
saipenview/_data/config.json
```

Valores padrão principais (abreviado - o dicionário completo `DEFAULTS` está em `saipenview/config.py`):

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

Defina `scan_roots: null` para detetar automaticamente todas as unidades locais.  
Defina como uma lista de caminhos (ex: `["V:\\", "D:\\projects"]`) para limitar a verificação.  
`default_engine` / `engine_overrides` / `agent_output_buffer_size` dirigem o Agent Engine (ver Recursos).  
Todas as definições também são configuráveis através da janela de **Definições** na aplicação.

<br>

---

## 🏗️ Arquitetura

```
saipenview/
├── app.py              Cabeamento de entrada - bandeja, hotkey, janela, api, proteção de instância única
├── api.py              Ponte pywebview voltada a JS (66 métodos públicos)
├── scanner.py          Varredura de unidades + ciclo de reverificação em segundo plano
├── parser.py           Análise de STATE.md / BOARD.md / LOG.md
├── textio.py           Um leitor para cada ficheiro .saipen/ — BOM, UTF-16, cp1251
├── protocol.py         Vocabulários fechados do protocolo + BASELINE_VERSION
├── conformance.py      Avalia um projeto em relação a esses vocabulários
├── config.py           Carregar/guardar definições (escritas atómicas)
├── tray.py             Ícone de bandeja do sistema pystray + menu
├── hotkey.py           Registo global de atalhos (biblioteca keyboard)
├── autostart.py        Gestão de início automático no Registo do Windows
├── zone_picker.py      Sobreposição de fixação no canto Ctrl+Q (tkinter)
├── events.py           Barramento de eventos no processo (EventBus)
├── guard.py            Trava de instância única + entrega de solicitação de exibição
├── git_diff.py         Diff / commit / revert da árvore de trabalho para ações de agentes
├── runtime.py          Agent Engine - gerenciador de processos dos agentes iniciados
├── watcher.py          Vigia de arquivos Watchdog sobre arquivos .saipen/
├── engines/            Agent Engine - motores CLI suportados (claude-code, codex,
│                       aider, gemini, cline, goose, agy, generic_cli)
├── ui/
│   ├── window.py       Janela pywebview — mostrar/ocultar/alternar/fixar
│   └── static/
│       ├── index.html
│       ├── style.css   Tema vintage Win95 escuro-dourado
│       └── app.js      Lógica do frontend (~3300 linhas)
├── assets/
│   └── tray_icon.png
├── screenshots/        Capturas de ecrã do README
└── _data/              Configuração em tempo de execução + cache (no gitignore)
```

### Princípios de design

- **Processo único** — sem IPC em segundo plano, sem servidor separado; um único processo Python aloja a janela WebView2 e o ciclo de verificação num `ThreadPoolExecutor`
- **Escritas atómicas** — cada escrita de ficheiro usa um ficheiro temporário + `os.replace`; uma falha nunca truncará a configuração ou o cache
- **Seguro contra leituras desatualizadas** — a sondagem da UI a cada 5s chama `refresh_known()` (re-lê apenas ficheiros `.saipen/`, sem varredura de diretórios). Alterações no STATE.md aparecem em segundos sem disparar uma verificação completa da unidade
- **Sem transições CSS** — todos os efeitos visuais (brilho, calor, passar do rato) são recomputações `hexBlend` via JavaScript, seguindo estritamente a restrição de zero animações do tema vintage
- **Tema vintage** — superfícies castanho-escuras, texto/acentos dourados, bordas biseladas em 3D, zero anti-aliasing, fonte Verdana_m1

<br>

---

## 🧪 Desenvolvimento

```bash
# Clone & enter
git clone https://github.com/vacterro/saipenview.git
cd saipenview

# Create venv & install
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# Run
python -m saipenview
```

Para detalhes sobre configuração, convenções de código e fluxo de trabalho de PR, consulte [CONTRIBUTING.md](../../CONTRIBUTING.md).

### Requisitos

- **Windows 10 / 11** — WebView2 runtime (pré-instalado no Win11, instalação automática no Win10)
- **Python 3.10+**
- Dependências: `pystray`, `keyboard`, `pywebview`, `Pillow`, `watchdog`, `psutil`

<br>

---

## 📄 Licença

MIT — consulte a [LICENÇA](../../LICENSE).

<br>

---

<div align="center">
  <sub>Desenvolvido com 🐍 Python • 🖼️ pywebview • 🎨 Estética Vintage Win95</sub>

<br>

---

## 📸 Mais Capturas de Ecrã

<p align="center">
  <img src="../../screenshots/detail-pane.png" alt="Painel de Detalhes do SAIPENVIEW" width="85%" style="border-radius: 4px; border: 1px solid #3a3020;">
  <br>
  <em>Painel de detalhes com tickets, subagentes e visualizador de ficheiros.</em>
</p>

<br>

</div>
