"""PERF-004 / T-845: historical transcript restore must batch its DOM commit."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

APP_JS = Path(__file__).resolve().parent.parent / "saipenview" / "ui" / "static" / "app.js"


def _extract(name: str, src: str) -> str:
    start = src.index(f"function {name}")
    brace = src.index("{", start)
    depth = 0
    i = brace
    while i < len(src):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                return src[start : i + 1]
        i += 1
    raise AssertionError(f"function {name} never closes")


def _node_ok() -> bool:
    try:
        return subprocess.run(["node", "--version"], capture_output=True).returncode == 0
    except OSError:
        return False


def _run(code: str, tmp_path: Path) -> subprocess.CompletedProcess:
    p = tmp_path / "h.js"
    p.write_text(code, encoding="utf-8")
    return subprocess.run(["node", str(p)], capture_output=True, text=True)


@pytest.mark.skipif(not _node_ok(), reason="node not on PATH")
def test_historical_2000_lines_batches_as_one_commit(tmp_path):
    src = APP_JS.read_text(encoding="utf-8")
    fns = _extract("isCurrentProjectPanel", src) + "\n" + _extract("restoreLastTranscript", src)
    lines = ", ".join(f"'l{i}'" for i in range(2000))
    code = f"""
class FakeNode {{
  constructor(tag) {{ this.tagName=tag; this.className=''; this.textContent=''; this.children=[]; this.isFragment=false; }}
  appendChild(n) {{ if(n&&n.isFragment){{ for(const c of n.children) this.appendChild(c); n.children=[]; return n; }} this.children.push(n); return n; }}
  get childElementCount() {{ return this.children.length; }}
}}
class FakeFragment {{ constructor(){{ this.children=[]; this.isFragment=true; }} appendChild(n){{ this.children.push(n); return n; }} }}
class FakeContainer extends FakeNode {{
  constructor(){{ super('div'); this.containerAppends=0; this.parentElement={{scrollTop:0,scrollHeight:100}}; this.innerHTML=''; }}
  appendChild(n){{ this.containerAppends++; if(n&&n.isFragment){{ this.children.push(...n.children); n.children=[]; return n; }} this.children.push(n); return n; }}
  get textSeq(){{ return this.children.map(c=>c.textContent); }}
}}
const __currentRoot='A';
const __container=new FakeContainer();
const __meta={{textContent:''}};
globalThis.document={{
  createDocumentFragment: () => {{ const f=new FakeFragment(); f.isFragment=true; return f; }},
  createElement: (tag) => new FakeNode(tag),
  getElementById: (id) => {{
    if(id==='agentOutputLines') return __container;
    if(id==='agentOutputMeta') return __meta;
    if(id==='agentPanelContainer') return {{ querySelector:(s)=> s==='.agent-panel'?{{dataset:{{root:__currentRoot}}}}:null }};
    return null;
  }},
}};
globalThis.window={{ SaiApi:{{ get_last_agent_transcript: () => Promise.resolve({{found:false}}), ready:true }} }};
globalThis.t=()=>'RESTORED';
globalThis.formatLocalTime=()=>'now';
globalThis.agentRestoredRoots=new Set();
globalThis.agentStatusCache={{}};
globalThis.currentDetailRoot=__currentRoot;
{fns}
window.SaiApi.get_last_agent_transcript = () => Promise.resolve({{ found:true, run:{{}}, total:2000, lines:[{lines}] }});
restoreLastTranscript('A', {{}});
setTimeout(()=>{{
  if(__container.containerAppends!==1){{ console.error('appends='+__container.containerAppends); process.exit(1); }}
  if(__container.children.length!==2001){{ console.error('count='+__container.children.length); process.exit(2); }}
  const orderOk=__container.children.every((c,i)=> i===0?c.className==='agent-output-restored':c.textContent===('l'+(i-1)));
  if(!orderOk){{ console.error('order wrong'); process.exit(3); }}
  if(!__container.textSeq[0].includes('RESTORED')){{ console.error('header wrong'); process.exit(4); }}
  console.log(JSON.stringify({{appends:__container.containerAppends, count:__container.children.length}}));
}},80);
"""
    res = _run(code, tmp_path)
    assert res.returncode == 0, res.stderr


@pytest.mark.skipif(not _node_ok(), reason="node not on PATH")
def test_load_history_500_lines_single_commit_and_header(tmp_path):
    src = APP_JS.read_text(encoding="utf-8")
    fns = _extract("isCurrentProjectPanel", src) + "\n" + _extract("loadAgentRun", src)
    lines = ", ".join(f"'h{i}'" for i in range(500))
    code = f"""
class FakeNode {{ constructor(tag){{ this.tagName=tag; this.className=''; this.textContent=''; this.children=[]; this.isFragment=false; }} appendChild(n){{ if(n&&n.isFragment){{ for(const c of n.children) this.appendChild(c); n.children=[]; return n; }} this.children.push(n); return n; }} get childElementCount(){{ return this.children.length; }} }}
class FakeFragment {{ constructor(){{ this.children=[]; this.isFragment=true; }} appendChild(n){{ this.children.push(n); return n; }} }}
class FakeContainer extends FakeNode {{ constructor(){{ super('div'); this.containerAppends=0; this.parentElement={{scrollTop:0,scrollHeight:100}}; this.innerHTML=''; }} appendChild(n){{ this.containerAppends++; if(n&&n.isFragment){{ this.children.push(...n.children); n.children=[]; return n; }} this.children.push(n); return n; }} }}
const __currentRoot='A';
const __container=new FakeContainer(); __container.innerHTML='old';
const __meta={{textContent:''}};
globalThis.document={{
  createDocumentFragment: () => {{ const f=new FakeFragment(); f.isFragment=true; return f; }},
  createElement: (tag) => new FakeNode(tag),
  getElementById: (id) => {{
    if(id==='agentOutputLines') return __container;
    if(id==='agentOutputMeta') return __meta;
    if(id==='agentPanelContainer') return {{ querySelector:(s)=> s==='.agent-panel'?{{dataset:{{root:__currentRoot}}}}:null }};
    return null;
  }},
}};
globalThis.window={{ SaiApi:{{ get_agent_transcript: (id) => Promise.resolve({{found:false}}), get_last_agent_transcript: () => Promise.resolve({{found:false}}), ready:true }} }};
globalThis.t=()=>'HIST';
globalThis.formatLocalTime=()=>'now';
globalThis.agentRestoredRoots=new Set();
globalThis.currentDetailRoot=__currentRoot;
globalThis._agentRunReq={{}};
{fns}
window.SaiApi.get_agent_transcript = () => Promise.resolve({{ found:true, total:500, lines:[{lines}] }});
loadAgentRun('A','run-1');
setTimeout(()=>{{
  if(__container.containerAppends!==1){{ console.error('appends='+__container.containerAppends); process.exit(1); }}
  if(__container.children.length!==501){{ console.error('count='+__container.children.length); process.exit(2); }}
  if(__container.children[0].className!=='agent-output-restored'){{ console.error('header missing'); process.exit(3); }}
  const seq=__container.children.slice(1).map(c=>c.textContent).join(',');
  const expect=Array.from({{length:500}},(_,i)=>'h'+i).join(',');
  if(seq!==expect){{ console.error('order wrong'); process.exit(4); }}
  if(__container.children.slice(1).some(c=>c.className!=='agent-output-line')){{ console.error('class wrong'); process.exit(5); }}
  console.log(JSON.stringify({{appends:__container.containerAppends}}));
}},80);
"""
    res = _run(code, tmp_path)
    assert res.returncode == 0, res.stderr


@pytest.mark.skipif(not _node_ok(), reason="node not on PATH")
def test_switching_project_prevents_stale_batch_insertion(tmp_path):
    src = APP_JS.read_text(encoding="utf-8")
    fns = _extract("isCurrentProjectPanel", src) + "\n" + _extract("restoreLastTranscript", src)
    code = f"""
class FakeNode {{ constructor(tag){{ this.tagName=tag; this.className=''; this.textContent=''; this.children=[]; this.isFragment=false; }} appendChild(n){{ if(n&&n.isFragment){{ for(const c of n.children) this.appendChild(c); n.children=[]; return n; }} this.children.push(n); return n; }} }}
class FakeFragment {{ constructor(){{ this.children=[]; this.isFragment=true; }} appendChild(n){{ this.children.push(n); return n; }} }}
let __currentRootVar='A';
let __panelRoot='A';
let __written=false;
const __container=new (class extends FakeNode {{ constructor(){{ super('div'); this.parentElement={{scrollTop:0,scrollHeight:100}}; this.innerHTML=''; }} appendChild(n){{ __written=true; return super.appendChild(n); }} }})();
const __meta={{textContent:''}};
globalThis.document={{
  createDocumentFragment: () => {{ const f=new FakeFragment(); f.isFragment=true; return f; }},
  createElement: (tag) => new FakeNode(tag),
  getElementById: (id) => {{
    if(id==='agentOutputLines') return __container;
    if(id==='agentOutputMeta') return __meta;
    if(id==='agentPanelContainer') return {{ querySelector:(s)=> s==='.agent-panel'?{{dataset:{{root:__panelRoot}}}}:null }};
    return null;
  }},
}};
Object.defineProperty(globalThis,'currentDetailRoot',{{ get(){{ return __currentRootVar; }}, set(v){{ __currentRootVar=v; }} }});
globalThis.window={{ SaiApi:{{ get_last_agent_transcript: () => new Promise(r=>{{ globalThis.__res=r; }}), ready:true }} }};
globalThis.t=()=>'RESTORED';
globalThis.formatLocalTime=()=>'now';
globalThis.agentRestoredRoots=new Set();
globalThis.agentStatusCache={{}};
{fns}
window.SaiApi.get_last_agent_transcript = () => new Promise(r=>{{ globalThis.__res=r; }});
restoreLastTranscript('A', {{}});
__currentRootVar='B'; __panelRoot='B';
globalThis.__res({{ found:true, run:{{}}, total:2, lines:['x','y'] }});
setTimeout(()=>{{ if(__written){{ console.error('stale insertion'); process.exit(1); }} console.log('ok'); }},80);
"""
    res = _run(code, tmp_path)
    assert res.returncode == 0, res.stderr


@pytest.mark.skipif(not _node_ok(), reason="node not on PATH")
def test_historical_rendering_does_not_invoke_parseTestLine(tmp_path):
    src = APP_JS.read_text(encoding="utf-8")
    fns = _extract("isCurrentProjectPanel", src) + "\n" + _extract("restoreLastTranscript", src) + "\n" + _extract("loadAgentRun", src)
    lines = ", ".join(f"'p{i}'" for i in range(10))
    code = f"""
class FakeNode {{ constructor(tag){{ this.tagName=tag; this.className=''; this.textContent=''; this.children=[]; this.isFragment=false; }} appendChild(n){{ if(n&&n.isFragment){{ for(const c of n.children) this.appendChild(c); n.children=[]; return n; }} this.children.push(n); return n; }} }}
class FakeFragment {{ constructor(){{ this.children=[]; this.isFragment=true; }} appendChild(n){{ this.children.push(n); return n; }} }}
class FakeContainer extends FakeNode {{ constructor(){{ super('div'); this.parentElement={{scrollTop:0,scrollHeight:100}}; this.innerHTML=''; }} }}
const __currentRoot='A';
const __container=new FakeContainer();
const __meta={{textContent:''}};
let __parseCalls=0;
globalThis.parseTestLine=() => {{ __parseCalls++; }};
globalThis.document={{
  createDocumentFragment: () => {{ const f=new FakeFragment(); f.isFragment=true; return f; }},
  createElement: (tag) => new FakeNode(tag),
  getElementById: (id) => {{
    if(id==='agentOutputLines') return __container;
    if(id==='agentOutputMeta') return __meta;
    if(id==='agentPanelContainer') return {{ querySelector:(s)=> s==='.agent-panel'?{{dataset:{{root:__currentRoot}}}}:null }};
    return null;
  }},
}};
globalThis.window={{ SaiApi:{{ get_last_agent_transcript: () => Promise.resolve({{found:true, run:{{}}, total:10, lines:[{lines}]}}), get_agent_transcript: (id) => Promise.resolve({{found:true, total:10, lines:[{lines}]}}), ready:true }} }};
globalThis.t=()=>'H';
globalThis.formatLocalTime=()=>'now';
globalThis.agentRestoredRoots=new Set();
globalThis.agentStatusCache={{}};
globalThis.currentDetailRoot='A';
globalThis._agentRunReq={{}};
{fns}
restoreLastTranscript('A', {{}});
loadAgentRun('A','run-x');
setTimeout(()=>{{ if(__parseCalls!==0){{ console.error('parseTestLine '+__parseCalls); process.exit(1); }} console.log('ok'); }},120);
"""
    res = _run(code, tmp_path)
    assert res.returncode == 0, res.stderr
