from pathlib import Path
from fastapi import FastAPI, Query, Body
from fastapi.responses import HTMLResponse, JSONResponse
from ..core.ast_parser import ASTParser

app = FastAPI(title="AetherGraph API", version="0.2.0")
parser = ASTParser()
PROYECTOS_DIR = Path("/workspace") if Path("/workspace").exists() else Path("/home/developer/Documentos/docker/PROYECTOS")

@app.get("/api/projects")
def list_projects():
    projects = []
    if PROYECTOS_DIR.exists():
        for d in sorted(PROYECTOS_DIR.iterdir()):
            if d.is_dir() and not d.name.startswith("."):
                has_index = (d / ".aether-graph" / "index.json").exists()
                projects.append({
                    "id": d.name,
                    "name": d.name,
                    "path": str(d),
                    "indexed": has_index,
                    "status": "🟢 Indexado" if has_index else "🔴 No Indexado"
                })
    return JSONResponse(projects)

@app.post("/api/reindex")
def reindex_project(payload: dict = Body(...)):
    project_path = payload.get("path")
    if not project_path:
        return JSONResponse({"ok": False, "error": "Falta la ruta del proyecto"}, status_code=400)
    root = Path(project_path).resolve()
    if not root.exists():
        return JSONResponse({"ok": False, "error": f"La ruta '{project_path}' no existe"}, status_code=404)
    
    graph = parser.scan_directory(root)
    dot_dir = root / ".aether-graph"
    dot_dir.mkdir(exist_ok=True)
    (dot_dir / "index.json").write_text(parser.scan_directory(root).__str__())
    return JSONResponse({"ok": True, "nodes": len(graph["nodes"]), "links": len(graph["links"])})

@app.get("/api/graph")
def get_graph(path: str = ".", view: str = "code"):
    if view == "agents":
        return JSONResponse(parser.get_agent_topology_graph())
    root = Path(path).resolve()
    data = parser.scan_directory(root)
    return JSONResponse(data)

@app.get("/", response_class=HTMLResponse)
def index():
    return """<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <title>AetherGraph — Engine & Dashboard</title>
  <script src="//unpkg.com/3d-force-graph"></script>
  <style>
    * { box-sizing: border-box; }
    body { margin: 0; padding: 0; background: #0b0d12; color: #f8fafc; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; overflow: hidden; }
    header {
      position: absolute; top: 0; left: 260px; right: 0; height: 52px; z-index: 50;
      background: rgba(15, 23, 42, 0.85); backdrop-filter: blur(12px);
      border-bottom: 1px solid rgba(148, 163, 184, 0.15);
      display: flex; align-items: center; justify-content: space-between; padding: 0 20px;
    }
    aside {
      position: absolute; top: 0; left: 0; bottom: 0; width: 260px; z-index: 60;
      background: rgba(15, 23, 42, 0.95); backdrop-filter: blur(16px);
      border-right: 1px solid rgba(148, 163, 184, 0.15);
      display: flex; flex-direction: column; justify-content: space-between; padding: 16px 12px;
    }
    .brand { font-weight: 700; font-size: 14px; color: #38bdf8; display: flex; align-items: center; gap: 8px; margin-bottom: 16px; }
    .brand span { color: #94a3b8; font-weight: 400; font-size: 10px; }
    .section-title { font-size: 10px; text-transform: uppercase; color: #64748b; letter-spacing: 1px; margin-bottom: 8px; }
    .project-list { flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 4px; }
    .project-item {
      padding: 8px 10px; border-radius: 6px; font-size: 11px; color: #cbd5e1; cursor: pointer;
      display: flex; justify-content: space-between; align-items: center; transition: all 0.15s; border: 1px solid transparent;
    }
    .project-item:hover { background: rgba(30, 41, 59, 0.6); border-color: rgba(148, 163, 184, 0.2); }
    .project-item.active { background: rgba(56, 189, 248, 0.15); border-color: #38bdf8; color: #38bdf8; font-weight: 600; }
    .btn-reindex {
      width: 100%; padding: 10px; border-radius: 8px; border: none;
      background: linear-gradient(135deg, #6366f1, #8b5cf6); color: #fff; font-weight: 700; font-size: 11px;
      cursor: pointer; transition: all 0.2s; box-shadow: 0 4px 14px rgba(99, 102, 241, 0.4);
    }
    .btn-reindex:hover { transform: translateY(-1px); filter: brightness(1.1); }
    .tab-btn {
      background: rgba(30, 41, 59, 0.6); border: 1px solid rgba(148, 163, 184, 0.2);
      color: #cbd5e1; padding: 6px 12px; border-radius: 6px; cursor: pointer; font-size: 11px; font-family: monospace;
    }
    .tab-btn.active { border-color: #00f0ff; color: #00f0ff; background: rgba(0, 240, 255, 0.12); font-weight: 700; }
    #graph-container { width: calc(100vw - 260px); margin-left: 260px; height: 100vh; pt: 52px; }
  </style>
</head>
<body>
  <aside>
    <div>
      <div class="brand">🌌 AetherGraph <span>v0.2.0</span></div>
      <div class="section-title">Proyectos Indexados</div>
      <div class="project-list" id="project-list">Cargando...</div>
    </div>
    <div>
      <button class="btn-reindex" id="reindex-btn" onclick="reindexCurrent()">⚡ Reindexar Proyecto</button>
    </div>
  </aside>

  <header>
    <div style="display:flex; gap:8px;">
      <button class="tab-btn active" id="tab-code" onclick="setView('code')">Code AST Graph</button>
      <button class="tab-btn" id="tab-agents" onclick="setView('agents')">Agent Harness Topology</button>
    </div>
    <div id="stats" style="font-size:11px; color:#94a3b8;">Cargando grafo...</div>
  </header>

  <div id="graph-container"></div>

  <script>
    let activePath = ".";
    let activeView = "code";
    let graphInstance = null;

    function loadProjects() {
      fetch('/api/projects')
        .then(r => r.json())
        .then(projects => {
          const listEl = document.getElementById('project-list');
          listEl.innerHTML = projects.map(p => `
            <div class="project-item ${p.path === activePath ? 'active' : ''}" onclick="selectProject('${p.path}')">
              <span style="overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${p.name}</span>
              <span style="font-size:9px;">${p.status}</span>
            </div>
          `).join('');
        });
    }

    function selectProject(path) {
      activePath = path;
      loadProjects();
      loadGraph();
    }

    function setView(view) {
      activeView = view;
      document.getElementById('tab-code').classList.toggle('active', view === 'code');
      document.getElementById('tab-agents').classList.toggle('active', view === 'agents');
      loadGraph();
    }

    function reindexCurrent() {
      const btn = document.getElementById('reindex-btn');
      btn.innerText = '⚡ Indexando...';
      fetch('/api/reindex', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({path: activePath})
      })
      .then(r => r.json())
      .then(() => {
        btn.innerText = '⚡ Reindexar Proyecto';
        loadProjects();
        loadGraph();
      });
    }

    function loadGraph() {
      const url = activeView === 'agents' ? '/api/graph?view=agents' : `/api/graph?path=${encodeURIComponent(activePath)}`;
      fetch(url)
        .then(res => res.json())
        .then(data => {
          document.getElementById('stats').innerText = `${data.nodes.length} nodos · ${data.links.length} conectores (Alto Contraste)`;
          
          if (!graphInstance) {
            graphInstance = ForceGraph3D()(document.getElementById('graph-container'));
          }

          graphInstance
            .graphData(data)
            .nodeId('id')
            .nodeLabel(n => `${n.name}\n${n.details}`)
            .nodeColor(n => n.color || '#38bdf8')
            .linkColor(l => l.color || 'rgba(0, 240, 255, 0.85)')
            .linkWidth(2.0);
        });
    }

    loadProjects();
    loadGraph();
  </script>
</body>
</html>
"""


