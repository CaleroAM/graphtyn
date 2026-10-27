"""Self-contained, offline `graph.html` for sharing a project graph.

The page embeds its data and a small canvas renderer, so it opens from disk,
can be attached to a pull request and never loads remote scripts. Large graphs
keep the most connected production symbols; the page states what was omitted.
"""
from __future__ import annotations

import html
import json
from typing import Any

from .communities import STRUCTURAL_LABELS, _production, detect_communities, file_graph, community_label

_PALETTE = ["#2563eb", "#16a34a", "#dc2626", "#9333ea", "#ea580c", "#0891b2", "#ca8a04",
            "#db2777", "#4f46e5", "#059669", "#7c3aed", "#b45309"]
_CONTAINERS = {"file", "module", "dir", "folder", "asset", "image", "media", "doc"}


def graph_payload(graph: dict[str, Any], node_limit: int = 1000) -> dict[str, Any]:
    weights = file_graph(graph)
    groups = detect_communities(weights)
    membership = {path: index for index, group in enumerate(groups) for path in group}
    labels = [community_label(group) for group in groups]
    degree: dict[str, int] = {}
    for link in graph.get("links", []):
        if str(link.get("label") or "").lower() in STRUCTURAL_LABELS:
            continue
        for end in (link.get("source"), link.get("target")):
            degree[str(end)] = degree.get(str(end), 0) + 1
    candidates = [node for node in graph.get("nodes", [])
                  if node.get("kind") not in _CONTAINERS and node.get("file") and _production(str(node["file"]))
                  and degree.get(str(node.get("id")))]
    candidates.sort(key=lambda node: (-degree[str(node["id"])], str(node.get("file")), int(node.get("line") or 0)))
    kept = candidates[:max(1, node_limit)]
    index = {str(node["id"]): position for position, node in enumerate(kept)}
    nodes = []
    for node in kept:
        community = membership.get(str(node["file"]), -1)
        nodes.append({
            "n": str(node.get("name") or ""), "k": str(node.get("kind") or ""),
            "f": str(node["file"]), "l": node.get("line"), "d": degree[str(node["id"])], "c": community,
            "w": [str(item.get("text") or "")[:160] for item in (node.get("rationale") or [])[:2]],
        })
    edges, seen = [], set()
    for link in graph.get("links", []):
        if str(link.get("label") or "").lower() in STRUCTURAL_LABELS:
            continue
        source, target = index.get(str(link.get("source"))), index.get(str(link.get("target")))
        if source is None or target is None or source == target or (source, target) in seen:
            continue
        seen.add((source, target))
        edges.append([source, target, str(link.get("label") or "")])
    return {"nodes": nodes, "edges": edges,
            "communities": [{"label": label, "color": _PALETTE[position % len(_PALETTE)]}
                            for position, label in enumerate(labels)],
            "omitted_symbols": max(0, len(candidates) - len(kept)), "total_symbols": len(candidates)}


def render_html(graph: dict[str, Any], title: str, node_limit: int = 1000) -> str:
    payload = graph_payload(graph, node_limit)
    # "</" inside a script element would end it early; JSON allows the escape.
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return _TEMPLATE.replace("__TITLE__", html.escape(title)).replace("__DATA__", data)


_TEMPLATE = r"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__ · Graphtyn</title>
<style>
:root{--bg:#ffffff;--fg:#0f172a;--muted:#64748b;--panel:#f8fafc;--line:#cbd5e1}
@media (prefers-color-scheme:dark){:root{--bg:#0b1120;--fg:#e2e8f0;--muted:#94a3b8;--panel:#111827;--line:#334155}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14px system-ui,sans-serif;display:flex;height:100vh}
#side{width:320px;max-width:42vw;padding:12px;overflow:auto;background:var(--panel);border-right:1px solid var(--line)}
#side h1{font-size:16px;margin:0 0 6px}#side p{color:var(--muted);margin:4px 0 10px}
input{width:100%;padding:6px 8px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--fg)}
#legend div{display:flex;gap:6px;align-items:center;margin:3px 0;cursor:pointer}#legend span{width:10px;height:10px;border-radius:50%;flex:none}
#detail{margin-top:12px;white-space:pre-wrap;word-break:break-word}canvas{flex:1;min-width:0}
@media (max-width:700px){body{flex-direction:column}#side{width:auto;max-width:none;max-height:40vh}}
</style></head><body>
<aside id="side"><h1>__TITLE__</h1><p id="summary"></p>
<input id="q" placeholder="Buscar símbolo o archivo" aria-label="Buscar">
<div id="legend"></div><div id="detail">Selecciona un nodo para ver su archivo, línea y razón declarada.</div></aside>
<canvas id="c" aria-label="Grafo del proyecto"></canvas>
<script type="application/json" id="data">__DATA__</script>
<script>
const D=JSON.parse(document.getElementById('data').textContent),cv=document.getElementById('c'),cx=cv.getContext('2d');
const N=D.nodes,E=D.edges,C=D.communities;let sel=-1,hidden=new Set(),query='',view={x:0,y:0,s:1};
document.getElementById('summary').textContent=`${N.length} símbolos y ${E.length} relaciones`+(D.omitted_symbols?` · ${D.omitted_symbols} símbolos menos conectados omitidos`:'');
const col=c=>c>=0&&C[c]?C[c].color:'#94a3b8';
N.forEach((n,i)=>{const a=(n.c>=0?n.c:C.length)*2.399,r=120+60*((n.c>=0?n.c:C.length)%4);n.x=Math.cos(a)*r+((i*37)%50-25);n.y=Math.sin(a)*r+((i*91)%50-25);n.vx=0;n.vy=0;n.r=3+Math.min(9,Math.sqrt(n.d))});
for(let t=0;t<120;t++){const k=1-t/120;for(let i=0;i<N.length;i++)for(let j=i+1;j<N.length;j++){const a=N[i],b=N[j];let dx=a.x-b.x,dy=a.y-b.y,d2=dx*dx+dy*dy+.01;if(d2>40000)continue;const f=60*k/d2;a.vx+=dx*f;a.vy+=dy*f;b.vx-=dx*f;b.vy-=dy*f}
for(const[s,t2]of E){const a=N[s],b=N[t2],dx=b.x-a.x,dy=b.y-a.y;a.vx+=dx*.004*k;a.vy+=dy*.004*k;b.vx-=dx*.004*k;b.vy-=dy*.004*k}
for(const n of N){n.vx-=n.x*.002*k;n.vy-=n.y*.002*k;n.x+=n.vx;n.y+=n.vy;n.vx*=.5;n.vy*=.5}}
const legend=document.getElementById('legend');C.forEach((c,i)=>{const d=document.createElement('div');d.innerHTML='<span></span>';d.firstChild.style.background=c.color;d.append(c.label);d.onclick=()=>{hidden.has(i)?hidden.delete(i):hidden.add(i);d.style.opacity=hidden.has(i)?.4:1;draw()};legend.append(d)});
function visible(n){return!hidden.has(n.c)&&(!query||n.n.toLowerCase().includes(query)||n.f.toLowerCase().includes(query))}
function size(){cv.width=cv.clientWidth*devicePixelRatio;cv.height=cv.clientHeight*devicePixelRatio;draw()}
function tx(n){return[(n.x*view.s+view.x)*devicePixelRatio+cv.width/2,(n.y*view.s+view.y)*devicePixelRatio+cv.height/2]}
function draw(){const st=getComputedStyle(document.body);cx.clearRect(0,0,cv.width,cv.height);cx.strokeStyle=st.getPropertyValue('--line');cx.globalAlpha=.5;cx.beginPath();
for(const[s,t]of E){const a=N[s],b=N[t];if(!visible(a)||!visible(b))continue;const[x1,y1]=tx(a),[x2,y2]=tx(b);cx.moveTo(x1,y1);cx.lineTo(x2,y2)}cx.stroke();cx.globalAlpha=1;
N.forEach((n,i)=>{if(!visible(n))return;const[x,y]=tx(n);cx.fillStyle=col(n.c);cx.beginPath();cx.arc(x,y,n.r*devicePixelRatio,0,7);cx.fill();if(i===sel||n.d>40){cx.fillStyle=st.getPropertyValue('--fg');cx.font=`${11*devicePixelRatio}px system-ui`;cx.fillText(n.n,x+n.r*devicePixelRatio+2,y)}})}
cv.onclick=e=>{const r=cv.getBoundingClientRect(),px=(e.clientX-r.left)*devicePixelRatio,py=(e.clientY-r.top)*devicePixelRatio;let best=-1,bd=400*devicePixelRatio;N.forEach((n,i)=>{if(!visible(n))return;const[x,y]=tx(n),d=(x-px)**2+(y-py)**2;if(d<bd){bd=d;best=i}});sel=best;
const det=document.getElementById('detail');if(best<0){det.textContent='';draw();return}const n=N[best],nb=E.filter(e=>e[0]===best||e[1]===best).slice(0,12).map(e=>`${e[2]} ${N[e[0]===best?e[1]:e[0]].n}`);
det.textContent=`${n.n} (${n.k})\n${n.f}:${n.l}\n${n.d} relaciones · ${n.c>=0&&C[n.c]?C[n.c].label:'sin comunidad'}`+(n.w.length?`\n\nPor qué:\n- ${n.w.join('\n- ')}`:'')+(nb.length?`\n\nConexiones:\n- ${nb.join('\n- ')}`:'');draw()};
let drag=null;cv.onmousedown=e=>drag=[e.clientX,e.clientY];onmouseup=()=>drag=null;onmousemove=e=>{if(!drag)return;view.x+=e.clientX-drag[0];view.y+=e.clientY-drag[1];drag=[e.clientX,e.clientY];draw()};
cv.onwheel=e=>{e.preventDefault();view.s*=e.deltaY<0?1.1:.9;draw()};document.getElementById('q').oninput=e=>{query=e.target.value.toLowerCase();draw()};
addEventListener('resize',size);size();
</script></body></html>
"""
