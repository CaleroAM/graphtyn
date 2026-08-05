from pathlib import Path
from fastapi import FastAPI, Query, Body
from fastapi.responses import HTMLResponse, JSONResponse
from ..core.ast_parser import ASTParser

app = FastAPI(title="AetherGraph API", version="0.3.0")
parser = ASTParser()

# Registro dinámico de proyectos (memoria local .aether-graph/registered_projects.json)
REGISTRATION_FILE = Path(".aether-graph/registered_projects.json")
DEFAULT_MASTER_DIR = Path("/workspace") if Path("/workspace").exists() else Path("/home/developer/Documentos/docker/PROYECTOS")

def _load_registered_projects() -> list[dict]:
    projects = []
    # 1. Proyectos descubiertos en la Carpeta Maestra por defecto
    if DEFAULT_MASTER_DIR.exists():
        for d in sorted(DEFAULT_MASTER_DIR.iterdir()):
            if d.is_dir() and not d.name.startswith("."):
                projects.append({
                    "id": d.name,
                    "name": d.name,
                    "path": str(d),
                    "mode": "master_folder",
                    "indexed": (d / ".aether-graph" / "index.json").exists()
                })
    # 2. Cargar proyectos añadidos dinámicamente (single_folder o agent_discovered)
    if REGISTRATION_FILE.exists():
        try:
            custom = json.loads(REGISTRATION_FILE.read_text(encoding="utf-8"))
            for cp in custom:
                p_path = Path(cp["path"])
                if p_path.exists() and not any(p["path"] == str(p_path) for p in projects):
                    projects.append({
                        "id": cp.get("id", p_path.name),
                        "name": cp.get("name", p_path.name),
                        "path": str(p_path),
                        "mode": cp.get("mode", "single_folder"),
                        "indexed": (p_path / ".aether-graph" / "index.json").exists()
                    })
        except Exception:
            pass
    return projects

@app.get("/api/projects")
def list_projects():
    projects = _load_registered_projects()
    for p in projects:
        p["status"] = "🟢 Indexado" if p["indexed"] else "🔴 No Indexado"
    return JSONResponse(projects)

@app.post("/api/projects/register")
def register_project(payload: dict = Body(...)):
    """
    Soporta 3 modalidades de registro:
    1. master_folder: Establece la carpeta contenedora maestra.
    2. single_folder: Registra una carpeta específica como un proyecto individual.
    3. agent_discovered: Invocado autónomamente por agentes de IA.
    """
    mode = payload.get("mode", "single_folder")
    path_str = payload.get("path")
    name = payload.get("name")

    if not path_str:
        return JSONResponse({"ok": False, "error": "Falta el parámetro 'path'"}, status_code=400)
    
    target_path = Path(path_str).resolve()
    if not target_path.exists():
        return JSONResponse({"ok": False, "error": f"La ruta '{path_str}' no existe en el sistema"}, status_code=404)

    REGISTRATION_FILE.parent.mkdir(exist_ok=True)
    custom_projects = []
    if REGISTRATION_FILE.exists():
        try:
            custom_projects = json.loads(REGISTRATION_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass

    new_entry = {
        "id": target_path.name,
        "name": name or target_path.name,
        "path": str(target_path),
        "mode": mode
    }

    if not any(cp["path"] == str(target_path) for cp in custom_projects):
        custom_projects.append(new_entry)
        REGISTRATION_FILE.write_text(json.dumps(custom_projects, indent=2), encoding="utf-8")

    return JSONResponse({"ok": True, "registered": new_entry, "mode": mode})

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
    (dot_dir / "index.json").write_text(json.dumps(graph, indent=2))
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
  <title>AetherGraph — Graphify Style Engine</title>
  <script src="//unpkg.com/force-graph"></script>
  <script src="//unpkg.com/3d-force-graph"></script>
  <style>
    * { box-sizing: border-box; }
    body { margin: 0; padding: 0; background: #0f172a; color: #f8fafc; font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; overflow: hidden; }
    header {
      position: absolute; top: 0; left: 260px; right: 0; height: 52px; z-index: 50;
      background: rgba(15, 23, 42, 0.9); backdrop-filter: blur(12px);
      border-bottom: 1px solid #1e293b;
      display: flex; align-items: center; justify-content: space-between; padding: 0 20px;
    }
    aside {
      position: absolute; top: 0; left: 0; bottom: 0; width: 260px; z-index: 60;
      background: #0f172a; border-right: 1px solid #1e293b;
      display: flex; flex-direction: column; justify-content: space-between; padding: 16px 14px;
    }
    .brand { font-weight: 700; font-size: 15px; color: #38bdf8; display: flex; align-items: center; gap: 8px; margin-bottom: 16px; letter-spacing: -0.5px; }
    .brand span { color: #64748b; font-weight: 500; font-size: 10px; }
    .section-title { font-size: 10px; text-transform: uppercase; color: #64748b; letter-spacing: 1px; margin-bottom: 8px; font-weight: 700; }
    .project-list { flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 4px; padding-right: 2px; }
    .project-item {
      padding: 8px 12px; border-radius: 6px; font-size: 12px; color: #94a3b8; cursor: pointer;
      display: flex; justify-content: space-between; align-items: center; transition: all 0.15s; border: 1px solid transparent; background: #1e293b;
    }
    .project-item:hover { background: #334155; color: #f8fafc; border-color: #475569; }
    .project-item.active { background: rgba(56, 189, 248, 0.1); border-color: #38bdf8; color: #38bdf8; font-weight: 600; }
    .filter-panel { background: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 10px; margin-top: 10px; }
    .filter-group { display: flex; flex-direction: column; gap: 6px; font-size: 11px; color: #cbd5e1; }
    .filter-group label { display: flex; align-items: center; gap: 6px; cursor: pointer; }
    .btn-action {
      width: 100%; padding: 9px; border-radius: 6px; border: 1px solid #334155;
      background: #1e293b; color: #f8fafc; font-weight: 600; font-size: 11px;
      cursor: pointer; transition: all 0.15s; margin-top: 6px;
    }
    .btn-action:hover { background: #334155; border-color: #475569; }
    .mode-btn {
      background: #1e293b; border: 1px solid #334155; color: #94a3b8;
      padding: 6px 12px; border-radius: 6px; cursor: pointer; font-size: 11px; font-weight: 600; transition: all 0.15s;
    }
    .mode-btn.active { border-color: #38bdf8; color: #38bdf8; background: rgba(56, 189, 248, 0.1); }
    .search-input {
      background: #1e293b; border: 1px solid #334155; color: #f8fafc;
      padding: 6px 12px; border-radius: 6px; font-size: 11px; outline: none; width: 160px;
    }
    .search-input:focus { border-color: #38bdf8; }
    #graph-container { width: calc(100vw - 260px); margin-left: 260px; height: 100vh; pt: 52px; }
  </style>
</head>
<body>
  <aside>
    <div>
      <div class="brand">🌌 AetherGraph <span>Graphify Edition</span></div>
      <div class="section-title">Proyectos Registrados</div>
      <div class="project-list" id="project-list">Cargando...</div>
      
      <div class="filter-panel">
        <div class="section-title">Filtros de Graphify</div>
        <div class="filter-group">
          <label><input type="checkbox" id="f-file" checked onchange="filterGraph()"> 📄 Archivos</label>
          <label><input type="checkbox" id="f-class" checked onchange="filterGraph()"> 📦 Clases</label>
          <label><input type="checkbox" id="f-func" checked onchange="filterGraph()"> ⚡ Funciones</label>
          <label><input type="checkbox" id="f-agent" checked onchange="filterGraph()"> 🤖 Agentes</label>
          <hr style="border:none; border-top:1px solid #334155; margin:4px 0;">
          <label>Min Conexiones: <span id="min-deg-val">0</span></label>
          <input type="range" id="min-degree" min="0" max="10" value="0" oninput="document.getElementById('min-deg-val').innerText=this.value; filterGraph();">
          <label><input type="checkbox" id="f-hide-isolated" onchange="filterGraph()"> 🚫 Ocultar Nodos Aislados</label>
        </div>
      </div>
    </div>
    <div>
      <button class="btn-action" onclick="promptRegisterProject()">➕ Registrar Proyecto / Carpeta</button>
      <button class="btn-action" id="reindex-btn" onclick="reindexCurrent()">⚡ Reindexar Grafo AST</button>
    </div>
  </aside>

  <header>
    <div style="display:flex; gap:8px; align-items:center;">
      <button class="mode-btn active" id="tab-code" onclick="setView('code')">🕸️ Code AST</button>
      <button class="mode-btn" id="tab-agents" onclick="setView('agents')">🤖 Harness Topology</button>
      <div style="width:1px; height:18px; background:#334155; margin:0 4px;"></div>
      <button class="mode-btn active" id="dim-2d" onclick="setDimension('2d')">2D Canvas</button>
      <button class="mode-btn" id="dim-3d" onclick="setDimension('3d')">3D Force</button>
      <input type="text" class="search-input" id="search-box" placeholder="🔍 Filtrar nodo..." oninput="filterGraph()">
    </div>
    <div id="stats" style="font-size:11px; color:#64748b;">Cargando grafo...</div>
  </header>

  <div id="graph-container"></div>

  <script>
    let activePath = ".";
    let activeView = "code";
    let dimensionMode = "2d";
    let graphInstance = null;
    let fullData = { nodes: [], links: [] };

    function loadProjects() {
      fetch('/api/projects')
        .then(r => r.json())
        .then(projects => {
          const listEl = document.getElementById('project-list');
          listEl.innerHTML = projects.map(p => `
            <div class="project-item ${p.path === activePath ? 'active' : ''}" onclick="selectProject('${p.path}')">
              <span style="overflow:hidden; text-overflow:ellipsis; white-space:nowrap; max-width:130px;">${p.name}</span>
              <span style="font-size:9px; color:${p.indexed ? '#10b981' : '#ef4444'};">${p.indexed ? '🟢' : '🔴'}</span>
            </div>
          `).join('');
        });
    }

    function promptRegisterProject() {
      const mode = prompt("Selecciona modalidad (1: Single Folder, 2: Master Folder, 3: Agent Discovered):", "1");
      const path = prompt("Ingresa la ruta absoluta del proyecto o carpeta contenedora:");
      if (path) {
        const modeKey = mode === "2" ? "master_folder" : (mode === "3" ? "agent_discovered" : "single_folder");
        fetch('/api/projects/register', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({path: path, mode: modeKey})
        })
        .then(r => r.json())
        .then(res => {
          if (res.ok) {
            loadProjects();
            selectProject(path);
          } else {
            alert("Error: " + res.error);
          }
        });
      }
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

    function setDimension(dim) {
      if (dimensionMode === dim) return;
      dimensionMode = dim;
      document.getElementById('dim-2d').classList.toggle('active', dim === '2d');
      document.getElementById('dim-3d').classList.toggle('active', dim === '3d');
      if (graphInstance) {
        document.getElementById('graph-container').innerHTML = '';
        graphInstance = null;
      }
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
        btn.innerText = '⚡ Reindexar Grafo AST';
        loadProjects();
        loadGraph();
      });
    }

    function filterGraph() {
      const q = document.getElementById('search-box').value.toLowerCase();
      const showFile = document.getElementById('f-file').checked;
      const showClass = document.getElementById('f-class').checked;
      const showFunc = document.getElementById('f-func').checked;
      const showAgent = document.getElementById('f-agent').checked;
      const minDegree = parseInt(document.getElementById('min-degree').value) || 0;
      const hideIsolated = document.getElementById('f-hide-isolated').checked;

      const filteredNodes = fullData.nodes.filter(n => {
        const kind = n.kind || '';
        if (kind === 'file' && !showFile) return false;
        if (kind === 'class' && !showClass) return false;
        if (kind === 'function' && !showFunc) return false;
        if ((kind.includes('agent') || kind.includes('orchestrator')) && !showAgent) return false;
        if ((n.degree || 0) < minDegree) return false;
        if (hideIsolated && (n.degree || 0) === 0) return false;
        if (q && !n.name.toLowerCase().includes(q) && !(n.details && n.details.toLowerCase().includes(q))) return false;
        return true;
      });

      const nodeIds = new Set(filteredNodes.map(n => n.id));
      const filteredLinks = fullData.links.filter(l => {
        const src = typeof l.source === 'object' ? l.source.id : l.source;
        const tgt = typeof l.target === 'object' ? l.target.id : l.target;
        return nodeIds.has(src) && nodeIds.has(tgt);
      });

      graphInstance.graphData({ nodes: filteredNodes, links: filteredLinks });
    }

    function loadGraph() {
      const url = activeView === 'agents' ? '/api/graph?view=agents' : `/api/graph?path=${encodeURIComponent(activePath)}`;
      fetch(url)
        .then(res => res.json())
        .then(data => {
          fullData = data;
          document.getElementById('stats').innerText = `${data.nodes.length} nodos · ${data.links.length} conectores (${dimensionMode.toUpperCase()} Graphify Style)`;

          const container = document.getElementById('graph-container');

          if (dimensionMode === '2d') {
            if (!graphInstance) {
              graphInstance = ForceGraph()(container);
            }
            graphInstance
              .backgroundColor('#0f172a')
              .graphData(data)
              .nodeId('id')
              .nodeVal(n => n.val || (4 + (n.degree || 0) * 1.5))
              .nodeLabel(n => `${n.name}\n${n.details || ''}\n📊 Conexiones: ${n.degree || 0}`)
              .nodeColor(n => n.color || '#38bdf8')
              .linkColor(() => 'rgba(148, 163, 184, 0.25)')
              .linkWidth(1.2)
              .linkDirectionalArrowLength(3.5)
              .linkDirectionalArrowRelPos(0.95)
              .d3Force('charge', d3.forceManyBody().strength(-200))
              .d3Force('link', d3.forceLink().distance(60))
              .d3Force('collide', d3.forceCollide().radius(n => 14 + (n.degree || 0) * 2));
          } else {
            if (!graphInstance) {
              graphInstance = ForceGraph3D()(container);
            }
            graphInstance
              .backgroundColor('#0f172a')
              .graphData(data)
              .nodeId('id')
              .nodeVal(n => n.val || (6 + (n.degree || 0) * 2))
              .nodeLabel(n => `${n.name}\n${n.details || ''}\n📊 Conexiones: ${n.degree || 0}`)
              .nodeColor(n => n.color || '#38bdf8')
              .linkColor(() => 'rgba(148, 163, 184, 0.3)')
              .linkWidth(1.5)
              .linkDirectionalArrowLength(4.0)
              .linkDirectionalArrowRelPos(0.95);
          }

          filterGraph();
        });
    }

    loadProjects();
    loadGraph();
  </script>
</body>
</html>
"""



