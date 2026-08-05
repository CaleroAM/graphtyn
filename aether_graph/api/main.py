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
    engine = payload.get("engine", "ast_local_llm") # ast_pure | ast_local_llm | ast_cloud_api
    if not project_path:
        return JSONResponse({"ok": False, "error": "Falta la ruta del proyecto"}, status_code=400)
    root = Path(project_path).resolve()
    if not root.exists():
        return JSONResponse({"ok": False, "error": f"La ruta '{project_path}' no existe"}, status_code=404)
    
    graph = parser.scan_directory(root)
    dot_dir = root / ".aether-graph"
    dot_dir.mkdir(exist_ok=True)
    graph["metadata"] = {"indexed_with": engine, "status": "ok"}
    (dot_dir / "index.json").write_text(json.dumps(graph, indent=2))
    return JSONResponse({"ok": True, "engine": engine, "nodes": len(graph["nodes"]), "links": len(graph["links"])})

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
    body { margin: 0; padding: 0; background: #0b0e17; color: #f8fafc; font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; overflow: hidden; }
    header {
      position: absolute; top: 0; left: 240px; right: 260px; height: 50px; z-index: 50;
      background: rgba(11, 14, 23, 0.9); backdrop-filter: blur(12px);
      border-bottom: 1px solid #1e293b;
      display: flex; align-items: center; justify-content: space-between; padding: 0 16px;
    }
    aside.left-aside {
      position: absolute; top: 0; left: 0; bottom: 0; width: 240px; z-index: 60;
      background: #0b0e17; border-right: 1px solid #1e293b;
      display: flex; flex-direction: column; padding: 14px;
    }
    aside.right-aside {
      position: absolute; top: 0; right: 0; bottom: 0; width: 260px; z-index: 60;
      background: #0b0e17; border-left: 1px solid #1e293b;
      display: flex; flex-direction: column; padding: 14px; overflow-y: auto;
    }
    .brand { font-weight: 700; font-size: 15px; color: #38bdf8; display: flex; align-items: center; gap: 8px; margin-bottom: 14px; letter-spacing: -0.5px; }
    .section-title { font-size: 10px; text-transform: uppercase; color: #64748b; letter-spacing: 1.2px; margin-bottom: 8px; font-weight: 700; }
    .project-list, .community-list { flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 4px; padding-right: 2px; }
    .project-item {
      padding: 8px 10px; border-radius: 6px; font-size: 11px; color: #94a3b8; cursor: pointer;
      display: flex; justify-content: space-between; align-items: center; transition: all 0.15s; border: 1px solid #1e293b; background: #111827;
    }
    .project-item:hover { background: #1f2937; color: #f8fafc; border-color: #374151; }
    .project-item.active { background: rgba(56, 189, 248, 0.1); border-color: #38bdf8; color: #38bdf8; font-weight: 600; }
    .community-item {
      display: flex; align-items: center; justify-content: space-between; font-size: 12px; color: #cbd5e1; padding: 5px 0; cursor: pointer;
    }
    .community-item label { display: flex; align-items: center; gap: 8px; cursor: pointer; flex: 1; overflow: hidden; }
    .comm-dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; flex-shrink: 0; }
    
    /* Floating Action Buttons Top Right */
    .floating-top-actions {
      position: absolute; top: 62px; right: 280px; z-index: 70; display: flex; gap: 8px;
    }
    
    .select-input, .btn-action {
      padding: 7px 12px; border-radius: 6px; border: 1px solid #374151;
      background: #1f2937; color: #f8fafc; font-weight: 600; font-size: 11px; outline: none;
      cursor: pointer; transition: all 0.15s; display: flex; align-items: center; gap: 6px;
    }
    .btn-action:hover { background: #374151; border-color: #4b5569; }
    .btn-primary { background: #0284c7; border-color: #0284c7; color: #fff; }
    .btn-primary:hover { background: #0369a1; }
    .mode-btn {
      background: #1f2937; border: 1px solid #374151; color: #94a3b8;
      padding: 5px 10px; border-radius: 6px; cursor: pointer; font-size: 11px; font-weight: 600; transition: all 0.15s;
    }
    .mode-btn.active { border-color: #38bdf8; color: #38bdf8; background: rgba(56, 189, 248, 0.1); }
    .search-input {
      background: #1f2937; border: 1px solid #374151; color: #f8fafc;
      padding: 5px 10px; border-radius: 6px; font-size: 11px; outline: none; width: 140px;
    }
    .search-input:focus { border-color: #38bdf8; }
    #graph-container { width: calc(100vw - 500px); margin-left: 240px; height: 100vh; pt: 50px; }
    .svg-ico { width: 14px; height: 14px; fill: currentColor; }
  </style>
</head>
<body>
  <!-- Left Sidebar: Projects -->
  <aside class="left-aside">
    <div class="brand">
      <svg class="svg-ico" viewBox="0 0 24 24"><path d="M12 2L2 7l10 5 10-5-10-5zm0 9l10-5v10l-10 5V11zm0 0L2 6v10l10 5V11z"/></svg>
      AetherGraph
    </div>
    <div class="section-title">PROYECTOS REGISTRADOS</div>
    <div class="project-list" id="project-list">Cargando...</div>
  </aside>

  <!-- Right Sidebar: Communities (Graphify Style 2.png) -->
  <aside class="right-aside">
    <div class="section-title">COMMUNITIES</div>
    <div style="margin-bottom:10px;">
      <label style="font-size:12px; color:#cbd5e1; display:flex; align-items:center; gap:8px; cursor:pointer; font-weight:600;">
        <input type="checkbox" id="select-all-comm" checked onchange="toggleSelectAllComm(this.checked)"> Select All
      </label>
    </div>
    <div class="community-list" id="community-list">Cargando...</div>
  </aside>

  <header>
    <div style="display:flex; gap:6px; align-items:center;">
      <button class="mode-btn active" id="tab-code" onclick="setView('code')">Code AST</button>
      <button class="mode-btn" id="tab-agents" onclick="setView('agents')">Harness Topology</button>
      <div style="width:1px; height:16px; background:#334155; margin:0 2px;"></div>
      <button class="mode-btn active" id="dim-2d" onclick="setDimension('2d')">2D Canvas</button>
      <button class="mode-btn" id="dim-3d" onclick="setDimension('3d')">3D Force</button>
      <input type="text" class="search-input" id="search-box" placeholder="Filtrar nodo..." oninput="filterGraph()">
    </div>
    <div id="stats" style="font-size:11px; color:#64748b;">Cargando grafo...</div>
  </header>

  <!-- Floating Quick Actions Top-Right -->
  <div class="floating-top-actions">
    <button class="btn-action btn-primary" onclick="promptRegisterProject()">
      <svg class="svg-ico" viewBox="0 0 24 24"><path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z"/></svg>
      Registrar Proyecto
    </button>
    <button class="btn-action" id="reindex-btn" onclick="reindexCurrent()">
      <svg class="svg-ico" viewBox="0 0 24 24"><path d="M12 4V1L8 5l4 4V6c3.31 0 6 2.69 6 6 0 1.01-.25 1.97-.7 2.8l1.46 1.46A7.93 7.93 0 0020 12c0-4.42-3.58-8-8-8zm0 14c-3.31 0-6-2.69-6-6 0-1.01.25-1.97.7-2.8L5.24 7.74A7.93 7.93 0 004 12c0 4.42 3.58 8 8 8v3l4-4-4-4v3z"/></svg>
      Reindexar Grafo
    </button>
  </div>

  <div id="graph-container"></div>

  <script>
    let activePath = ".";
    let activeView = "code";
    let dimensionMode = "2d";
    let graphInstance = null;
    let fullData = { nodes: [], links: [] };

    const COMM_COLORS = ['#38bdf8', '#f59e0b', '#ef4444', '#10b981', '#a78bfa', '#ec4899', '#06b6d4', '#84cc16', '#eab308', '#6366f1'];

    function loadProjects() {
      fetch('/api/projects')
        .then(r => r.json())
        .then(projects => {
          const listEl = document.getElementById('project-list');
          listEl.innerHTML = projects.map(p => `
            <div class="project-item ${p.path === activePath ? 'active' : ''}" onclick="selectProject('${p.path}')">
              <span style="overflow:hidden; text-overflow:ellipsis; white-space:nowrap; max-width:140px;">${p.name}</span>
              <span style="font-size:9px; color:${p.indexed ? '#10b981' : '#ef4444'}; font-weight:700;">${p.indexed ? 'OK' : 'PEND'}</span>
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
      btn.innerText = 'Indexando...';
      fetch('/api/reindex', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({path: activePath})
      })
      .then(r => r.json())
      .then(() => {
        btn.innerText = 'Reindexar Grafo';
        loadProjects();
        loadGraph();
      });
    }

    function renderCommunitiesSidebar(data) {
      const commMap = {};
      data.nodes.forEach(n => {
        const cName = n.name ? n.name.split('.')[0] : 'general';
        commMap[cName] = (commMap[cName] || 0) + 1;
      });

      const sortedComms = Object.keys(commMap).sort((a,b) => commMap[b] - commMap[a]);
      const listEl = document.getElementById('community-list');
      
      listEl.innerHTML = sortedComms.map((c, idx) => {
        const color = COMM_COLORS[idx % COMM_COLORS.length];
        return `
          <div class="community-item">
            <label>
              <input type="checkbox" class="comm-chk" data-comm="${c}" checked onchange="filterGraph()">
              <span class="comm-dot" style="background:${color};"></span>
              <span style="overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${c}</span>
            </label>
            <span style="font-size:11px; color:#64748b;">${commMap[c]}</span>
          </div>
        `;
      }).join('');
    }

    function toggleSelectAllComm(checked) {
      document.querySelectorAll('.comm-chk').forEach(c => c.checked = checked);
      filterGraph();
    }

    function filterGraph() {
      const q = document.getElementById('search-box').value.toLowerCase();
      const activeComms = new Set(
        Array.from(document.querySelectorAll('.comm-chk:checked')).map(c => c.getAttribute('data-comm'))
      );

      const filteredNodes = fullData.nodes.filter(n => {
        const cName = n.name ? n.name.split('.')[0] : 'general';
        if (activeComms.size > 0 && !activeComms.has(cName)) return false;
        if (q && !n.name.toLowerCase().includes(q) && !(n.details && n.details.toLowerCase().includes(q))) return false;
        return true;
      });

      const nodeIds = new Set(filteredNodes.map(n => n.id));
      const filteredLinks = fullData.links.filter(l => {
        const src = typeof l.source === 'object' ? l.source.id : l.source;
        const tgt = typeof l.target === 'object' ? l.target.id : l.target;
        return nodeIds.has(src) && nodeIds.has(tgt);
      });

      if (graphInstance) {
        graphInstance.graphData({ nodes: filteredNodes, links: filteredLinks });
      }
    }

    function loadGraph() {
      const url = activeView === 'agents' ? '/api/graph?view=agents' : `/api/graph?path=${encodeURIComponent(activePath)}`;
      fetch(url)
        .then(res => res.json())
        .then(data => {
          fullData = data;
          document.getElementById('stats').innerText = `${data.nodes.length} nodos · ${data.links.length} conectores (${dimensionMode.toUpperCase()})`;
          renderCommunitiesSidebar(data);

          const container = document.getElementById('graph-container');

          if (dimensionMode === '2d') {
            if (!graphInstance) {
              graphInstance = ForceGraph()(container);
            }
            graphInstance
              .backgroundColor('#0b0e17')
              .graphData(data)
              .nodeId('id')
              .nodeVal(n => Math.max(2, Math.min(6, (n.degree || 1) * 0.8)))
              .nodeLabel(n => `${n.name}\n${n.details || ''}\nConexiones: ${n.degree || 0}`)
              .nodeColor(n => n.color || '#38bdf8')
              .linkColor(() => 'rgba(255, 255, 255, 0.12)')
              .linkWidth(0.8)
              .d3AlphaDecay(0.02)
              .d3VelocityDecay(0.3)
              .d3Force('charge', d3.forceManyBody().strength(-80))
              .d3Force('link', d3.forceLink().distance(35))
              .d3Force('collide', d3.forceCollide().radius(10));
          } else {
            if (!graphInstance) {
              graphInstance = ForceGraph3D()(container);
            }
            graphInstance
              .backgroundColor('#0b0e17')
              .graphData(data)
              .nodeId('id')
              .nodeVal(n => Math.max(3, Math.min(8, (n.degree || 1) * 1.0)))
              .nodeLabel(n => `${n.name}\n${n.details || ''}\nConexiones: ${n.degree || 0}`)
              .nodeColor(n => n.color || '#38bdf8')
              .linkColor(() => 'rgba(255, 255, 255, 0.15)')
              .linkWidth(1.0);
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



