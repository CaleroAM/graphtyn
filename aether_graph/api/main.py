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
  <title>AetherGraph — Engine & Dashboard</title>
  <script src="//unpkg.com/force-graph"></script>
  <script src="//unpkg.com/3d-force-graph"></script>
  <style>
    * { box-sizing: border-box; }
    body { margin: 0; padding: 0; background: #0b0e17; color: #f8fafc; font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; overflow: hidden; }
    header {
      position: absolute; top: 0; left: 240px; right: 260px; height: 50px; z-index: 50;
      background: rgba(11, 14, 23, 0.92); backdrop-filter: blur(12px);
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
    
    /* Custom SVG Checkbox Toggle */
    .custom-chk { display: flex; align-items: center; justify-content: space-between; font-size: 11px; color: #cbd5e1; cursor: pointer; padding: 4px 0; }
    .custom-chk input { display: none; }
    .chk-box { width: 16px; height: 16px; border-radius: 4px; border: 1px solid #4b5563; background: #1f2937; display: flex; align-items: center; justify-content: center; transition: all 0.15s; flex-shrink: 0; }
    .custom-chk input:checked + .chk-box { background: #0284c7; border-color: #38bdf8; }
    .chk-box svg { width: 10px; height: 10px; stroke: #fff; stroke-width: 3; fill: none; display: none; }
    .custom-chk input:checked + .chk-box svg { display: block; }
    
    /* Dropdown Menus */
    .dropdown-container { position: relative; display: inline-block; }
    .dropdown-menu {
      position: absolute; top: 100%; left: 0; margin-top: 6px; z-index: 100;
      background: #111827; border: 1px solid #374151; border-radius: 8px; padding: 12px;
      width: 250px; box-shadow: 0 10px 25px rgba(0,0,0,0.5); display: none;
    }
    .dropdown-container.open .dropdown-menu { display: block; }
    .filter-group { display: flex; flex-direction: column; gap: 6px; font-size: 11px; color: #cbd5e1; }

    /* Custom Modal Overlay */
    .modal-overlay {
      position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.7);
      backdrop-filter: blur(8px); z-index: 200; display: none; align-items: center; justify-content: center;
    }
    .modal-overlay.active { display: flex; }
    .modal-card {
      background: #111827; border: 1px solid #374151; border-radius: 12px; width: 440px; max-width: 90vw; padding: 20px; box-shadow: 0 20px 40px rgba(0,0,0,0.6);
    }
    .modal-title { font-weight: 700; font-size: 15px; color: #f8fafc; margin-bottom: 14px; display: flex; justify-content: space-between; align-items: center; }
    .mode-card-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px; margin-bottom: 14px; }
    .mode-card {
      background: #1f2937; border: 1px solid #374151; border-radius: 8px; padding: 10px; cursor: pointer; text-align: center; font-size: 11px; transition: all 0.15s;
    }
    .mode-card:hover { border-color: #4b5569; background: #374151; }
    .mode-card.selected { border-color: #38bdf8; background: rgba(56, 189, 248, 0.15); color: #38bdf8; font-weight: 700; }

    .floating-top-actions { position: absolute; top: 62px; right: 280px; z-index: 70; display: flex; gap: 8px; }
    .select-input, .btn-action {
      padding: 6px 12px; border-radius: 6px; border: 1px solid #374151;
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
    .search-input, .text-input {
      background: #1f2937; border: 1px solid #374151; color: #f8fafc;
      padding: 7px 10px; border-radius: 6px; font-size: 11px; outline: none; width: 100%;
    }
    .search-input:focus, .text-input:focus { border-color: #38bdf8; }
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
      <label class="custom-chk" style="font-weight:700;">
        <span>Select All</span>
        <input type="checkbox" id="select-all-comm" checked onchange="toggleSelectAllComm(this.checked)">
        <span class="chk-box"><svg viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"/></svg></span>
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
      
      <!-- Dropdown Menu: Node Filters -->
      <div class="dropdown-container" id="filter-dd">
        <button class="btn-action" onclick="toggleDropdown('filter-dd')">
          <svg class="svg-ico" viewBox="0 0 24 24"><path d="M10 18h4v-2h-4v2zM3 6v2h18V6H3zm3 7h12v-2H6v2z"/></svg>
          Filtros de Nodo ▾
        </button>
        <div class="dropdown-menu">
          <div class="section-title" style="margin-bottom:8px;">Tipo de Nodo</div>
          <div class="filter-group">
            <label class="custom-chk">
              <span>Archivos</span>
              <input type="checkbox" id="f-file" checked onchange="filterGraph()">
              <span class="chk-box"><svg viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"/></svg></span>
            </label>
            <label class="custom-chk">
              <span>Clases</span>
              <input type="checkbox" id="f-class" checked onchange="filterGraph()">
              <span class="chk-box"><svg viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"/></svg></span>
            </label>
            <label class="custom-chk">
              <span>Funciones</span>
              <input type="checkbox" id="f-func" checked onchange="filterGraph()">
              <span class="chk-box"><svg viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"/></svg></span>
            </label>
            <label class="custom-chk">
              <span>Agentes</span>
              <input type="checkbox" id="f-agent" checked onchange="filterGraph()">
              <span class="chk-box"><svg viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"/></svg></span>
            </label>
            <hr style="border:none; border-top:1px solid #374151; margin:6px 0;">
            <div style="display:flex; justify-content:space-between; font-size:11px;">
              <span>Min Conexiones:</span>
              <span id="min-deg-val" style="color:#38bdf8; font-weight:700;">0</span>
            </div>
            <input type="range" id="min-degree" min="0" max="10" value="0" style="width:100%;" oninput="document.getElementById('min-deg-val').innerText=this.value; filterGraph();">
            <label class="custom-chk" style="margin-top:4px;">
              <span>Ocultar Aislados</span>
              <input type="checkbox" id="f-hide-isolated" onchange="filterGraph()">
              <span class="chk-box"><svg viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"/></svg></span>
            </label>
          </div>
        </div>
      </div>

      <!-- Dropdown Menu: Settings -->
      <div class="dropdown-container" id="settings-dd">
        <button class="btn-action" onclick="toggleDropdown('settings-dd')">
          <svg class="svg-ico" viewBox="0 0 24 24"><path d="M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58c.18-.14.23-.41.12-.61l-1.92-3.32c-.12-.22-.37-.29-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54c-.04-.24-.24-.41-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.09.63-.09.94s.02.64.07.94l-2.03 1.58c-.18.14-.23.41-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.5c-1.93 0-3.5-1.57-3.5-3.5s1.57-3.5 3.5-3.5 3.5 1.57 3.5 3.5-1.57 3.5-3.5 3.5z"/></svg>
          Paleta & Motor ▾
        </button>
        <div class="dropdown-menu">
          <div class="filter-group">
            <label style="display:block;">Paleta de Color:</label>
            <select id="palette-select" class="select-input" onchange="changePalette()">
              <option value="obsidian" selected>Obsidian Dark</option>
              <option value="cyberpunk">Neon Cyberpunk</option>
              <option value="monochrome">Monochrome Slate</option>
              <option value="matrix">Emerald Matrix</option>
            </select>
            <label style="display:block; margin-top:6px;">Motor de Reindexación:</label>
            <select id="engine-select" class="select-input">
              <option value="ast_local_llm" selected>AST + IA Local (Ollama Qwen2.5)</option>
              <option value="ast_cloud_api">AST + IA Cloud API (Gemini/Claude)</option>
              <option value="ast_pure">AST Cero Tokens (Pure AST)</option>
            </select>
            <button class="btn-action" style="margin-top:8px; justify-content:center;" onclick="openTutorialModal()">
              📖 Guía / Tutorial Conexión IA
            </button>
          </div>
        </div>
      </div>

      <input type="text" class="search-input" id="search-box" placeholder="Buscar nodo..." oninput="filterGraph()">
    </div>
    <div id="stats" style="font-size:11px; color:#64748b;">Cargando grafo...</div>
  </header>

  <!-- Floating Quick Actions Top-Right -->
  <div class="floating-top-actions">
    <button class="btn-action btn-primary" onclick="openRegisterModal()">
      <svg class="svg-ico" viewBox="0 0 24 24"><path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z"/></svg>
      Registrar Proyecto
    </button>
    <button class="btn-action" id="reindex-btn" onclick="reindexCurrent()">
      <svg class="svg-ico" viewBox="0 0 24 24"><path d="M12 4V1L8 5l4 4V6c3.31 0 6 2.69 6 6 0 1.01-.25 1.97-.7 2.8l1.46 1.46A7.93 7.93 0 0020 12c0-4.42-3.58-8-8-8zm0 14c-3.31 0-6-2.69-6-6 0-1.01.25-1.97.7-2.8L5.24 7.74A7.93 7.93 0 004 12c0 4.42 3.58 8 8 8v3l4-4-4-4v3z"/></svg>
      Reindexar Grafo
    </button>
  </div>

  <!-- Custom Registration Modal (Replaces native prompt) -->
  <div class="modal-overlay" id="register-modal">
    <div class="modal-card">
      <div class="modal-title">
        <span>➕ Registrar Proyecto / Carpeta</span>
        <button style="background:none; border:none; color:#94a3b8; cursor:pointer;" onclick="closeRegisterModal()">✕</button>
      </div>
      <div style="font-size:11px; color:#94a3b8; margin-bottom:8px;">Selecciona la modalidad de registro:</div>
      <div class="mode-card-grid">
        <div class="mode-card selected" id="mc-single" onclick="selectRegMode('single_folder')">
          <div style="font-size:16px; margin-bottom:4px;">📦</div>
          <div>Carpeta Única</div>
        </div>
        <div class="mode-card" id="mc-master" onclick="selectRegMode('master_folder')">
          <div style="font-size:16px; margin-bottom:4px;">📂</div>
          <div>Carpeta Maestra</div>
        </div>
        <div class="mode-card" id="mc-agent" onclick="selectRegMode('agent_discovered')">
          <div style="font-size:16px; margin-bottom:4px;">🤖</div>
          <div>Por Agente</div>
        </div>
      </div>
      <div style="font-size:11px; color:#94a3b8; margin-bottom:6px;">Ruta absoluta en el disco:</div>
      <input type="text" class="text-input" id="reg-path-input" placeholder="/home/usuario/Documentos/mi-proyecto">
      <div style="display:flex; justify-content:flex-end; gap:8px; margin-top:16px;">
        <button class="btn-action" onclick="closeRegisterModal()">Cancelar</button>
        <button class="btn-action btn-primary" onclick="submitRegisterModal()">Registrar e Indexar</button>
      </div>
    </div>
  </div>

  <!-- Custom AI Connection Tutorial Modal -->
  <div class="modal-overlay" id="tutorial-modal">
    <div class="modal-card" style="width:520px;">
      <div class="modal-title">
        <span>📖 Guía de Conexión de IA (Local vs Cloud)</span>
        <button style="background:none; border:none; color:#94a3b8; cursor:pointer;" onclick="closeTutorialModal()">✕</button>
      </div>
      <div style="font-size:12px; color:#cbd5e1; display:flex; flex-direction:column; gap:12px;">
        <div style="background:#1f2937; padding:10px; border-radius:8px; border:1px solid #374151;">
          <div style="font-weight:700; color:#38bdf8; margin-bottom:4px;">1. Conectar IA Local (Ollama Qwen2.5 / $0 Costo)</div>
          <div>1. Instala Ollama: <code style="background:#111827; padding:2px 4px; border-radius:4px;">curl -fsSL https://ollama.com/install.sh | sh</code></div>
          <div>2. Levanta el modelo: <code style="background:#111827; padding:2px 4px; border-radius:4px;">ollama run qwen2.5-coder</code></div>
          <div>3. AetherGraph se conecta automáticamente a <code style="color:#10b981;">http://localhost:11434</code> sin API keys.</div>
        </div>
        <div style="background:#1f2937; padding:10px; border-radius:8px; border:1px solid #374151;">
          <div style="font-weight:700; color:#f59e0b; margin-bottom:4px;">2. Conectar IA Cloud API (Gemini / Claude)</div>
          <div>1. Declara tu llave en la terminal donde corre AetherGraph:</div>
          <div style="background:#111827; padding:6px; border-radius:4px; font-family:monospace; margin:4px 0;">export GEMINI_API_KEY="AIzaSy..."</div>
          <div>2. O crea un archivo <code style="background:#111827; padding:2px 4px; border-radius:4px;">.env</code> en la carpeta de AetherGraph.</div>
        </div>
      </div>
      <div style="display:flex; justify-content:flex-end; margin-top:16px;">
        <button class="btn-action btn-primary" onclick="closeTutorialModal()">Entendido</button>
      </div>
    </div>
  </div>

  <div id="graph-container"></div>

  <script>
    let activePath = ".";
    let activeView = "code";
    let dimensionMode = "2d";
    let activePalette = "obsidian";
    let selectedRegMode = "single_folder";
    let graphInstance = null;
    let fullData = { nodes: [], links: [] };

    const PALETTES = {
      obsidian: { file: '#38bdf8', class: '#f59e0b', func: '#a78bfa', agent: '#a855f7', link: 'rgba(255, 255, 255, 0.12)' },
      cyberpunk: { file: '#00f0ff', class: '#ffe600', func: '#ff007f', agent: '#7000ff', link: 'rgba(0, 240, 255, 0.18)' },
      monochrome: { file: '#f8fafc', class: '#cbd5e1', func: '#94a3b8', agent: '#64748b', link: 'rgba(203, 213, 225, 0.12)' },
      matrix: { file: '#10b981', class: '#34d399', func: '#059669', agent: '#047857', link: 'rgba(16, 185, 129, 0.18)' }
    };

    const COMM_COLORS = ['#38bdf8', '#f59e0b', '#ef4444', '#10b981', '#a78bfa', '#ec4899', '#06b6d4', '#84cc16', '#eab308', '#6366f1'];

    function toggleDropdown(id) {
      const el = document.getElementById(id);
      const isOpen = el.classList.contains('open');
      document.querySelectorAll('.dropdown-container').forEach(d => d.classList.remove('open'));
      if (!isOpen) {
        el.classList.add('open');
      }
    }

    document.addEventListener('click', (e) => {
      if (!e.target.closest('.dropdown-container')) {
        document.querySelectorAll('.dropdown-container').forEach(d => d.classList.remove('open'));
      }
    });

    function openRegisterModal() {
      document.getElementById('reg-path-input').value = activePath !== '.' ? activePath : '/home/developer/Documentos/docker/PROYECTOS/';
      document.getElementById('register-modal').classList.add('active');
    }
    function closeRegisterModal() {
      document.getElementById('register-modal').classList.remove('active');
    }
    function selectRegMode(mode) {
      selectedRegMode = mode;
      document.getElementById('mc-single').classList.toggle('selected', mode === 'single_folder');
      document.getElementById('mc-master').classList.toggle('selected', mode === 'master_folder');
      document.getElementById('mc-agent').classList.toggle('selected', mode === 'agent_discovered');
    }
    function submitRegisterModal() {
      const path = document.getElementById('reg-path-input').value.trim();
      if (!path) return alert("Por favor ingresa una ruta válida");
      fetch('/api/projects/register', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({path: path, mode: selectedRegMode})
      })
      .then(r => r.json())
      .then(res => {
        if (res.ok) {
          closeRegisterModal();
          loadProjects();
          selectProject(path);
        } else {
          alert("Error: " + res.error);
        }
      });
    }

    function openTutorialModal() { document.getElementById('tutorial-modal').classList.add('active'); }
    function closeTutorialModal() { document.getElementById('tutorial-modal').classList.remove('active'); }

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

    function changePalette() {
      activePalette = document.getElementById('palette-select').value;
      if (graphInstance) {
        const p = PALETTES[activePalette] || PALETTES.obsidian;
        graphInstance.nodeColor(n => getNodeColor(n)).linkColor(() => p.link);
      }
    }

    function reindexCurrent() {
      const btn = document.getElementById('reindex-btn');
      const engine = document.getElementById('engine-select').value;
      btn.innerText = 'Indexando...';
      fetch('/api/reindex', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({path: activePath, engine: engine})
      })
      .then(r => r.json())
      .then(() => {
        btn.innerText = 'Reindexar Grafo';
        loadProjects();
        loadGraph();
      });
    }

    function getNodeColor(n) {
      const p = PALETTES[activePalette] || PALETTES.obsidian;
      const k = n.kind || '';
      if (k === 'file') return p.file;
      if (k === 'class') return p.class;
      if (k === 'function') return p.func;
      if (k.includes('agent') || k.includes('orchestrator')) return p.agent;
      return p.file;
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
            <label class="custom-chk" style="flex:1;">
              <input type="checkbox" class="comm-chk" data-comm="${c}" checked onchange="filterGraph()">
              <span class="chk-box"><svg viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"/></svg></span>
              <span class="comm-dot" style="background:${color}; margin-left:6px;"></span>
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
      const showFile = document.getElementById('f-file') ? document.getElementById('f-file').checked : true;
      const showClass = document.getElementById('f-class') ? document.getElementById('f-class').checked : true;
      const showFunc = document.getElementById('f-func') ? document.getElementById('f-func').checked : true;
      const showAgent = document.getElementById('f-agent') ? document.getElementById('f-agent').checked : true;
      const minDegree = document.getElementById('min-degree') ? parseInt(document.getElementById('min-degree').value) || 0 : 0;
      const hideIsolated = document.getElementById('f-hide-isolated') ? document.getElementById('f-hide-isolated').checked : false;

      const activeComms = new Set(
        Array.from(document.querySelectorAll('.comm-chk:checked')).map(c => c.getAttribute('data-comm'))
      );

      const filteredNodes = fullData.nodes.filter(n => {
        const kind = n.kind || '';
        if (kind === 'file' && !showFile) return false;
        if (kind === 'class' && !showClass) return false;
        if (kind === 'function' && !showFunc) return false;
        if ((kind.includes('agent') || kind.includes('orchestrator')) && !showAgent) return false;
        if ((n.degree || 0) < minDegree) return false;
        if (hideIsolated && (n.degree || 0) === 0) return false;

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
          const p = PALETTES[activePalette] || PALETTES.obsidian;

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
              .nodeColor(n => getNodeColor(n))
              .linkColor(() => p.link)
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
              .nodeColor(n => getNodeColor(n))
              .linkColor(() => p.link)
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



