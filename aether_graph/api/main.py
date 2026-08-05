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
  <title>AetherGraph — Obsidian & Graphify Style Engine</title>
  <script src="//unpkg.com/3d-force-graph"></script>
  <style>
    * { box-sizing: border-box; }
    body { margin: 0; padding: 0; background: #0b0d12; color: #f8fafc; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; overflow: hidden; }
    header {
      position: absolute; top: 0; left: 280px; right: 0; height: 56px; z-index: 50;
      background: rgba(11, 13, 18, 0.88); backdrop-filter: blur(16px);
      border-bottom: 1px solid rgba(56, 189, 248, 0.15);
      display: flex; align-items: center; justify-content: space-between; padding: 0 20px;
    }
    aside {
      position: absolute; top: 0; left: 0; bottom: 0; width: 280px; z-index: 60;
      background: rgba(15, 23, 42, 0.96); backdrop-filter: blur(20px);
      border-right: 1px solid rgba(56, 189, 248, 0.15);
      display: flex; flex-direction: column; justify-content: space-between; padding: 16px 14px;
    }
    .brand { font-weight: 800; font-size: 15px; color: #00f0ff; text-shadow: 0 0 12px rgba(0,240,255,0.4); display: flex; align-items: center; gap: 8px; margin-bottom: 16px; }
    .brand span { color: #94a3b8; font-weight: 400; font-size: 10px; text-shadow: none; }
    .section-title { font-size: 10px; text-transform: uppercase; color: #64748b; letter-spacing: 1.5px; margin-bottom: 10px; font-weight: 700; }
    .project-list { flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 6px; padding-right: 4px; }
    .project-item {
      padding: 9px 12px; border-radius: 8px; font-size: 11px; color: #cbd5e1; cursor: pointer;
      display: flex; justify-content: space-between; align-items: center; transition: all 0.2s; border: 1px solid rgba(148,163,184,0.08); background: rgba(30, 41, 59, 0.3);
    }
    .project-item:hover { background: rgba(30, 41, 59, 0.8); border-color: rgba(0, 240, 255, 0.3); color: #fff; transform: translateX(2px); }
    .project-item.active { background: rgba(0, 240, 255, 0.12); border-color: #00f0ff; color: #00f0ff; font-weight: 700; box-shadow: 0 0 15px rgba(0,240,255,0.15); }
    .btn-action {
      width: 100%; padding: 10px; border-radius: 8px; border: 1px solid rgba(168, 85, 247, 0.4);
      background: linear-gradient(135deg, rgba(99, 102, 241, 0.2), rgba(168, 85, 247, 0.3)); color: #f8fafc; font-weight: 700; font-size: 11px;
      cursor: pointer; transition: all 0.2s; box-shadow: 0 4px 14px rgba(168, 85, 247, 0.2); margin-top: 8px;
    }
    .btn-action:hover { filter: brightness(1.2); border-color: #a855f7; transform: translateY(-1px); }
    .tab-btn {
      background: rgba(30, 41, 59, 0.5); border: 1px solid rgba(148, 163, 184, 0.2);
      color: #cbd5e1; padding: 7px 14px; border-radius: 8px; cursor: pointer; font-size: 11px; font-family: monospace; transition: all 0.2s;
    }
    .tab-btn.active { border-color: #00f0ff; color: #00f0ff; background: rgba(0, 240, 255, 0.15); font-weight: 700; box-shadow: 0 0 10px rgba(0,240,255,0.2); }
    .search-input {
      background: rgba(15, 23, 42, 0.8); border: 1px solid rgba(148, 163, 184, 0.2); color: #f8fafc;
      padding: 6px 12px; border-radius: 8px; font-size: 11px; outline: none; width: 180px; transition: all 0.2s;
    }
    .search-input:focus { border-color: #00f0ff; box-shadow: 0 0 8px rgba(0,240,255,0.3); }
    #graph-container { width: calc(100vw - 280px); margin-left: 280px; height: 100vh; pt: 56px; }
  </style>
</head>
<body>
  <aside>
    <div>
      <div class="brand">🌌 AetherGraph <span>Obsidian Edition</span></div>
      <div class="section-title">Proyectos Registrados</div>
      <div class="project-list" id="project-list">Cargando...</div>
    </div>
    <div>
      <button class="btn-action" onclick="promptRegisterProject()">➕ Registrar Proyecto / Carpeta</button>
      <button class="btn-action" id="reindex-btn" onclick="reindexCurrent()">⚡ Reindexar Grafo AST</button>
    </div>
  </aside>

  <header>
    <div style="display:flex; gap:10px; align-items:center;">
      <button class="tab-btn active" id="tab-code" onclick="setView('code')">🕸️ Obsidian Code AST</button>
      <button class="tab-btn" id="tab-agents" onclick="setView('agents')">🤖 Agent Harness Topology</button>
      <input type="text" class="search-input" id="search-box" placeholder="🔍 Buscar nodo..." oninput="filterGraph()">
    </div>
    <div id="stats" style="font-size:11px; color:#94a3b8;">Cargando grafo...</div>
  </header>

  <div id="graph-container"></div>

  <script>
    let activePath = ".";
    let activeView = "code";
    let graphInstance = null;
    let fullData = { nodes: [], links: [] };

    function loadProjects() {
      fetch('/api/projects')
        .then(r => r.json())
        .then(projects => {
          const listEl = document.getElementById('project-list');
          listEl.innerHTML = projects.map(p => `
            <div class="project-item ${p.path === activePath ? 'active' : ''}" onclick="selectProject('${p.path}')">
              <span style="overflow:hidden; text-overflow:ellipsis; white-space:nowrap; max-width:140px;">${p.name}</span>
              <span style="font-size:9px;">${p.status}</span>
            </div>
          `).join('');
        });
    }

    function promptRegisterProject() {
      const mode = prompt("Escoge modo (1: Single Folder, 2: Master Folder, 3: Agent Discovered):", "1");
      const path = prompt("Ingresa la ruta completa del proyecto o carpeta contenedora:");
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
      if (!q) {
        graphInstance.graphData(fullData);
        return;
      }
      const filteredNodes = fullData.nodes.filter(n => n.name.toLowerCase().includes(q) || n.details.toLowerCase().includes(q));
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
          document.getElementById('stats').innerText = `${data.nodes.length} nodos · ${data.links.length} conectores (Estilo Obsidian / Graphify)`;

          if (!graphInstance) {
            graphInstance = ForceGraph3D()(document.getElementById('graph-container'));
          }

          graphInstance
            .graphData(data)
            .nodeId('id')
            .nodeVal(n => n.val || (8 + (n.degree || 0) * 3))
            .nodeLabel(n => `${n.name}\n${n.details}\n📊 Conexiones: ${n.degree || 0}`)
            .nodeColor(n => n.color || '#00f0ff')
            .linkCurvature(0.2)
            .linkColor(l => l.color || 'rgba(0, 240, 255, 0.75)')
            .linkWidth(2.0)
            .linkDirectionalArrowLength(5.0)
            .linkDirectionalArrowRelPos(0.95)
            .linkDirectionalParticles(3)
            .linkDirectionalParticleWidth(2.5)
            .linkDirectionalParticleSpeed(0.007)
            .linkDirectionalParticleColor(l => l.color || '#00f0ff');
        });
    }

    loadProjects();
    loadGraph();
  </script>
</body>
</html>
"""



