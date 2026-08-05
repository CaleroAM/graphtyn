import json
from pathlib import Path
from fastapi import FastAPI, Query, Body
from fastapi.responses import HTMLResponse, JSONResponse
from ..core.ast_parser import ASTParser

app = FastAPI(title="AetherGraph API", version="0.4.0")
parser = ASTParser()

# Central writable index store — inside container at /app/.aether-graph/
# This avoids OSError on read-only workspace mounts.
INDEX_STORE = Path("/app/.aether-graph")
INDEX_STORE.mkdir(parents=True, exist_ok=True)

REGISTRATION_FILE = INDEX_STORE / "registered_projects.json"
DEFAULT_MASTER_DIR = Path("/workspace") if Path("/workspace").exists() else Path("/home/developer/Documentos/docker/PROYECTOS")

def _index_dir(project_path: Path) -> Path:
    """Returns the writable index directory for a project."""
    slug = project_path.name
    d = INDEX_STORE / slug
    d.mkdir(parents=True, exist_ok=True)
    return d

def _is_indexed(project_path: Path) -> bool:
    return (_index_dir(project_path) / "index.json").exists()

def _load_registered_projects() -> list[dict]:
    projects = []
    if DEFAULT_MASTER_DIR.exists():
        for d in sorted(DEFAULT_MASTER_DIR.iterdir()):
            if d.is_dir() and not d.name.startswith("."):
                projects.append({
                    "id": d.name,
                    "name": d.name,
                    "path": str(d),
                    "mode": "master_folder",
                    "indexed": _is_indexed(d)
                })
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
                        "indexed": _is_indexed(p_path)
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
    engine = payload.get("engine", "ast_local_llm")
    if not project_path:
        return JSONResponse({"ok": False, "error": "Falta la ruta del proyecto"}, status_code=400)
    root = Path(project_path).resolve()
    if not root.exists():
        return JSONResponse({"ok": False, "error": f"La ruta '{project_path}' no existe"}, status_code=404)

    graph = parser.scan_directory(root)
    graph["metadata"] = {"indexed_with": engine, "status": "ok", "path": str(root)}
    dot_dir = _index_dir(root)
    (dot_dir / "index.json").write_text(json.dumps(graph, indent=2))
    return JSONResponse({"ok": True, "engine": engine, "nodes": len(graph["nodes"]), "links": len(graph["links"])})

@app.get("/api/graph")
def get_graph(path: str = ".", view: str = "code"):
    if view == "agents":
        return JSONResponse(parser.get_agent_topology_graph())
    root = Path(path).resolve()
    data = parser.scan_directory(root)
    # Try to save index — but workspace is read-only so store in central index dir
    try:
        dot_dir = _index_dir(root)
        (dot_dir / "index.json").write_text(json.dumps(data, indent=2))
    except OSError:
        pass  # Read-only mount — index won't be persisted but graph still renders
    return JSONResponse(data)

@app.get("/", response_class=HTMLResponse)
def index():
    return """<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <title>AetherGraph — Engine & Dashboard</title>
  <script src="https://unpkg.com/d3@7"></script>
  <script src="https://unpkg.com/force-graph@1"></script>
  <script src="https://unpkg.com/3d-force-graph@1"></script>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    * { box-sizing: border-box; }
    body { margin:0; padding:0; background:#0b0e17; color:#f8fafc; font-family:'Inter',ui-sans-serif,sans-serif; overflow:hidden; }

    /* Thin dark scrollbar */
    ::-webkit-scrollbar { width:4px; height:4px; }
    ::-webkit-scrollbar-track { background:transparent; }
    ::-webkit-scrollbar-thumb { background:#2d3748; border-radius:4px; }
    ::-webkit-scrollbar-thumb:hover { background:#38bdf8; }

    header {
      position:absolute; top:0; left:240px; right:260px; height:52px; z-index:50;
      background:rgba(11,14,23,0.97); backdrop-filter:blur(16px);
      border-bottom:1px solid #1e293b;
      display:flex; align-items:center; justify-content:space-between; padding:0 14px; gap:6px;
    }

    aside.left-aside {
      position:absolute; top:0; left:0; bottom:0; width:240px; z-index:60;
      background:#0d1117; border-right:1px solid #1e293b;
      display:flex; flex-direction:column; padding:14px;
    }
    aside.right-aside {
      position:absolute; top:0; right:0; bottom:0; width:260px; z-index:60;
      background:#0d1117; border-left:1px solid #1e293b;
      display:flex; flex-direction:column; padding:14px;
      overflow:hidden;
    }

    .brand { font-weight:700; font-size:14px; color:#38bdf8; display:flex; align-items:center; gap:7px; margin-bottom:14px; }
    .section-label { font-size:9px; text-transform:uppercase; letter-spacing:1.4px; color:#475569; font-weight:700; margin-bottom:8px; }

    /* Left: project list */
    .project-list { flex:1; overflow-y:auto; display:flex; flex-direction:column; gap:3px; }
    .project-item {
      padding:7px 9px; border-radius:6px; font-size:11px; color:#94a3b8; cursor:pointer;
      display:flex; justify-content:space-between; align-items:center;
      transition:all 0.12s; border:1px solid transparent; background:#111827;
    }
    .project-item:hover { background:#1a2234; color:#e2e8f0; border-color:#2d3748; }
    .project-item.active { background:rgba(56,189,248,0.1); border-color:#38bdf8; color:#38bdf8; font-weight:600; }
    .proj-badge { font-size:9px; font-weight:700; padding:1px 5px; border-radius:4px; flex-shrink:0; }
    .proj-badge.ok { color:#10b981; background:rgba(16,185,129,0.12); }
    .proj-badge.pend { color:#f59e0b; background:rgba(245,158,11,0.12); }

    /* Right: communities */
    .comm-header { display:flex; align-items:center; justify-content:space-between; margin-bottom:10px; }
    .comm-select-all { font-size:10px; color:#64748b; cursor:pointer; display:flex; align-items:center; gap:5px; }
    .community-list { flex:1; overflow-y:auto; display:flex; flex-direction:column; gap:1px; padding-right:2px; }
    .community-item {
      display:flex; align-items:center; justify-content:space-between;
      padding:4px 4px; border-radius:5px; transition:background 0.1s; cursor:pointer;
    }
    .community-item:hover { background:#111827; }
    .comm-left { display:flex; align-items:center; gap:6px; flex:1; min-width:0; }
    .comm-dot { width:8px; height:8px; border-radius:50%; flex-shrink:0; }
    .comm-name { font-size:11px; color:#cbd5e1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
    .comm-badge { font-size:9px; font-weight:700; color:#64748b; background:#1f2937; padding:1px 6px; border-radius:8px; flex-shrink:0; margin-left:4px; }

    /* Custom checkbox */
    .chk-wrap { display:flex; align-items:center; flex-shrink:0; }
    .chk-wrap input { display:none; }
    .chk-box {
      width:13px; height:13px; border-radius:3px; border:1px solid #4b5563;
      background:#1f2937; display:flex; align-items:center; justify-content:center;
      transition:all 0.12s; flex-shrink:0; cursor:pointer;
    }
    .chk-wrap input:checked + .chk-box { background:#0284c7; border-color:#38bdf8; }
    .chk-box svg { width:8px; height:8px; stroke:#fff; stroke-width:3; fill:none; display:none; }
    .chk-wrap input:checked + .chk-box svg { display:block; }

    /* Header buttons */
    .mode-btn {
      background:#1a2234; border:1px solid #2d3748; color:#94a3b8;
      padding:5px 10px; border-radius:5px; cursor:pointer; font-size:11px; font-weight:600;
      transition:all 0.12s; white-space:nowrap;
    }
    .mode-btn:hover { border-color:#475569; color:#e2e8f0; }
    .mode-btn.active { border-color:#38bdf8; color:#38bdf8; background:rgba(56,189,248,0.12); }
    .sep { width:1px; height:16px; background:#1e293b; flex-shrink:0; }

    .btn-action {
      padding:5px 10px; border-radius:5px; border:1px solid #2d3748;
      background:#1a2234; color:#e2e8f0; font-weight:600; font-size:11px;
      cursor:pointer; transition:all 0.12s; display:flex; align-items:center; gap:5px; white-space:nowrap;
    }
    .btn-action:hover { border-color:#38bdf8; color:#38bdf8; }
    .btn-primary { background:#0369a1; border-color:#0284c7; color:#fff; }
    .btn-primary:hover { background:#0284c7; border-color:#38bdf8; }
    .search-input {
      background:#1a2234; border:1px solid #2d3748; color:#f8fafc;
      padding:5px 9px; border-radius:5px; font-size:11px; outline:none; width:130px;
    }
    .search-input:focus { border-color:#38bdf8; }
    .svg-ico { width:13px; height:13px; fill:currentColor; flex-shrink:0; }

    /* Dropdowns */
    .dd-wrap { position:relative; }
    .dd-panel {
      position:absolute; top:calc(100% + 6px); left:0; z-index:200;
      background:#111827; border:1px solid #2d3748; border-radius:8px; padding:12px;
      width:240px; box-shadow:0 12px 30px rgba(0,0,0,0.6); display:none;
    }
    .dd-wrap.open .dd-panel { display:block; }
    .filter-section { display:flex; flex-direction:column; gap:5px; }
    .filter-row { display:flex; align-items:center; justify-content:space-between; font-size:11px; color:#cbd5e1; padding:2px 0; }

    /* Floating actions */
    .float-actions { position:absolute; top:60px; right:270px; z-index:70; display:flex; gap:7px; }

    /* Modals */
    .modal-bg {
      position:fixed; inset:0; background:rgba(0,0,0,0.75); backdrop-filter:blur(8px);
      z-index:300; display:none; align-items:center; justify-content:center;
    }
    .modal-bg.show { display:flex; }
    .modal-box {
      background:#111827; border:1px solid #374151; border-radius:12px;
      width:460px; max-width:92vw; padding:22px; box-shadow:0 24px 50px rgba(0,0,0,0.7);
    }
    .modal-hdr { font-weight:700; font-size:14px; color:#f8fafc; margin-bottom:14px; display:flex; justify-content:space-between; align-items:center; }
    .modal-close { background:none; border:none; color:#64748b; cursor:pointer; font-size:16px; line-height:1; }
    .modal-close:hover { color:#f8fafc; }
    .card-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:8px; margin-bottom:14px; }
    .reg-card {
      background:#1a2234; border:1px solid #2d3748; border-radius:8px; padding:12px 8px;
      cursor:pointer; text-align:center; font-size:11px; color:#94a3b8; transition:all 0.14s;
    }
    .reg-card:hover { border-color:#475569; color:#e2e8f0; }
    .reg-card.sel { border-color:#38bdf8; background:rgba(56,189,248,0.12); color:#38bdf8; font-weight:700; }
    .reg-card .icon { font-size:18px; margin-bottom:5px; }
    .text-inp {
      background:#1a2234; border:1px solid #2d3748; color:#f8fafc;
      padding:7px 10px; border-radius:6px; font-size:11px; outline:none; width:100%;
    }
    .text-inp:focus { border-color:#38bdf8; }

    #graph-container { position:absolute; top:0; left:240px; right:260px; bottom:0; }
  </style>
</head>
<body>

  <!-- ===== LEFT SIDEBAR ===== -->
  <aside class="left-aside">
    <div class="brand">
      <svg class="svg-ico" style="width:16px;height:16px;" viewBox="0 0 24 24"><path d="M12 2L2 7l10 5 10-5-10-5zm0 9l10-5v10l-10 5V11zM2 17l10 5 10-5"/></svg>
      AetherGraph
    </div>
    <div class="section-label">PROYECTOS REGISTRADOS</div>
    <div class="project-list" id="project-list">
      <div style="color:#475569;font-size:11px;">Cargando...</div>
    </div>
  </aside>

  <!-- ===== RIGHT SIDEBAR: COMMUNITIES ===== -->
  <aside class="right-aside">
    <div class="comm-header">
      <div class="section-label" style="margin:0;">COMMUNITIES</div>
      <label class="comm-select-all">
        <span>Todo</span>
        <span class="chk-wrap">
          <input type="checkbox" id="sel-all-comm" checked onchange="toggleAllComm(this.checked)">
          <span class="chk-box"><svg viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"/></svg></span>
        </span>
      </label>
    </div>
    <div class="community-list" id="community-list">
      <div style="color:#475569;font-size:11px;">Cargando...</div>
    </div>
  </aside>

  <!-- ===== HEADER ===== -->
  <header>
    <div style="display:flex;align-items:center;gap:5px;flex-wrap:nowrap;min-width:0;">
      <!-- View tabs -->
      <button class="mode-btn active" id="btn-code" onclick="setView('code')">Code AST</button>
      <button class="mode-btn" id="btn-agents" onclick="setView('agents')">Harness Topology</button>
      <div class="sep"></div>
      <!-- Dimension tabs -->
      <button class="mode-btn active" id="btn-2d" onclick="setDim('2d')">2D</button>
      <button class="mode-btn" id="btn-3d" onclick="setDim('3d')">3D</button>
      <button class="mode-btn" id="btn-rotate" style="display:none;" onclick="toggleRotate()">⟳ Rotar 3D</button>
      <div class="sep"></div>

      <!-- Node Filters dropdown -->
      <div class="dd-wrap" id="dd-filter">
        <button class="btn-action" onclick="toggleDD('dd-filter')">
          <svg class="svg-ico" viewBox="0 0 24 24"><path d="M10 18h4v-2h-4v2zM3 6v2h18V6H3zm3 7h12v-2H6v2z"/></svg>
          Filtros ▾
        </button>
        <div class="dd-panel">
          <div class="section-label">Tipo de Nodo</div>
          <div class="filter-section">
            <div class="filter-row">
              <span>Archivos</span>
              <label class="chk-wrap"><input type="checkbox" id="f-file" checked onchange="applyFilter()"><span class="chk-box"><svg viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"/></svg></span></label>
            </div>
            <div class="filter-row">
              <span>Clases</span>
              <label class="chk-wrap"><input type="checkbox" id="f-class" checked onchange="applyFilter()"><span class="chk-box"><svg viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"/></svg></span></label>
            </div>
            <div class="filter-row">
              <span>Funciones / Métodos</span>
              <label class="chk-wrap"><input type="checkbox" id="f-func" checked onchange="applyFilter()"><span class="chk-box"><svg viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"/></svg></span></label>
            </div>
            <div class="filter-row">
              <span>Agentes</span>
              <label class="chk-wrap"><input type="checkbox" id="f-agent" checked onchange="applyFilter()"><span class="chk-box"><svg viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"/></svg></span></label>
            </div>
            <hr style="border:none;border-top:1px solid #1e293b;margin:6px 0;">
            <div class="filter-row">
              <span>Min conexiones: <strong id="deg-val" style="color:#38bdf8;">0</strong></span>
            </div>
            <input type="range" id="f-deg" min="0" max="20" value="0" style="width:100%;"
              oninput="document.getElementById('deg-val').textContent=this.value;applyFilter();">
            <div class="filter-row" style="margin-top:4px;">
              <span>Ocultar aislados</span>
              <label class="chk-wrap"><input type="checkbox" id="f-isolated" onchange="applyFilter()"><span class="chk-box"><svg viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"/></svg></span></label>
            </div>
            <hr style="border:none;border-top:1px solid #1e293b;margin:6px 0;">
            <div class="section-label">Físicas del Grafo</div>
            <div class="filter-row">
              <span>Repulsión: <strong id="rep-val" style="color:#38bdf8;">-300</strong></span>
            </div>
            <input type="range" id="f-repulsion" min="-600" max="-50" value="-300" step="25" style="width:100%;"
              oninput="document.getElementById('rep-val').textContent=this.value;updatePhysics();">
            <div class="filter-row" style="margin-top:4px;">
              <span>Distancia Enlaces: <strong id="dist-val" style="color:#38bdf8;">80</strong></span>
            </div>
            <input type="range" id="f-distance" min="30" max="180" value="80" step="5" style="width:100%;"
              oninput="document.getElementById('dist-val').textContent=this.value;updatePhysics();">
          </div>
        </div>
      </div>

      <!-- Settings dropdown -->
      <div class="dd-wrap" id="dd-settings">
        <button class="btn-action" onclick="toggleDD('dd-settings')">
          <svg class="svg-ico" viewBox="0 0 24 24"><path d="M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58c.18-.14.23-.41.12-.61l-1.92-3.32c-.12-.22-.37-.29-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54c-.04-.24-.24-.41-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.09.63-.09.94s.02.64.07.94l-2.03 1.58c-.18.14-.23.41-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.5c-1.93 0-3.5-1.57-3.5-3.5s1.57-3.5 3.5-3.5 3.5 1.57 3.5 3.5-1.57 3.5-3.5 3.5z"/></svg>
          Paleta & Motor ▾
        </button>
        <div class="dd-panel">
          <div class="filter-section">
            <label class="section-label">Paleta de Color</label>
            <select id="palette-sel" style="background:#1a2234;border:1px solid #2d3748;color:#f8fafc;padding:5px 8px;border-radius:5px;font-size:11px;width:100%;" onchange="changePalette()">
              <option value="obsidian" selected>Obsidian Dark</option>
              <option value="cyberpunk">Neon Cyberpunk</option>
              <option value="dracula">Dracula Synthwave</option>
              <option value="solarized">Solarized Dark</option>
              <option value="nordic">Nordic Aurora</option>
              <option value="vaporwave">Vaporwave Sunset</option>
              <option value="mono">Monochrome Slate</option>
              <option value="matrix">Emerald Matrix</option>
              <option value="community">Por Comunidad (Carpetas)</option>
            </select>
            <label class="section-label" style="margin-top:8px;">Motor IA</label>
            <select id="engine-sel" style="background:#1a2234;border:1px solid #2d3748;color:#f8fafc;padding:5px 8px;border-radius:5px;font-size:11px;width:100%;">
              <option value="ast_local_llm" selected>AST + Local (Ollama Qwen2.5)</option>
              <option value="ast_cloud">AST + Cloud API (Gemini/Claude)</option>
              <option value="ast_pure">Solo AST (cero tokens)</option>
            </select>
            <button class="btn-action" style="margin-top:8px;justify-content:center;width:100%;" onclick="openTutorial()">
              📖 Tutorial Conexión IA
            </button>
          </div>
        </div>
      </div>

      <input type="text" class="search-input" id="search-box" placeholder="Buscar nodo…" oninput="applyFilter()">
    </div>
    <div id="stats" style="font-size:11px;color:#475569;white-space:nowrap;padding-left:8px;">—</div>
  </header>

  <!-- Floating quick actions -->
  <div class="float-actions">
    <div style="font-size:10px;font-weight:700;color:#10b981;background:rgba(16,185,129,0.12);padding:4px 8px;border-radius:6px;border:1px solid rgba(16,185,129,0.25);display:flex;align-items:center;gap:5px;">
      <span style="width:6px;height:6px;border-radius:50%;background:#10b981;box-shadow:0 0 8px #10b981;"></span> MCP Activo
    </div>
    <button class="btn-action" onclick="exportGraphData()" title="Descargar datos del grafo en JSON">
      <svg class="svg-ico" viewBox="0 0 24 24"><path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/></svg>
      Exportar
    </button>
    <button class="btn-action btn-primary" onclick="openRegister()">
      <svg class="svg-ico" viewBox="0 0 24 24"><path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z"/></svg>
      Registrar
    </button>
    <button class="btn-action" id="reindex-btn" onclick="doReindex()">
      <svg class="svg-ico" viewBox="0 0 24 24"><path d="M12 4V1L8 5l4 4V6c3.31 0 6 2.69 6 6 0 1.01-.25 1.97-.7 2.8l1.46 1.46A7.93 7.93 0 0020 12c0-4.42-3.58-8-8-8zm0 14c-3.31 0-6-2.69-6-6 0-1.01.25-1.97.7-2.8L5.24 7.74A7.93 7.93 0 004 12c0 4.42 3.58 8 8 8v3l4-4-4-4v3z"/></svg>
      Reindexar
    </button>
  </div>

  <!-- ===== GRAPH CANVAS ===== -->
  <div id="graph-container"></div>

  <!-- ===== FLOATING BLAST RADIUS PANEL ===== -->
  <div id="blast-panel" style="position:absolute;bottom:16px;right:276px;z-index:90;background:#111827;border:1px solid #374151;border-radius:10px;padding:12px 14px;width:280px;box-shadow:0 16px 36px rgba(0,0,0,0.6);display:none;">
    <div style="font-weight:700;font-size:12px;color:#38bdf8;display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
      <span style="display:flex;align-items:center;gap:5px;">🎯 Radio de Impacto</span>
      <button onclick="closeBlastPanel()" style="background:none;border:none;color:#64748b;cursor:pointer;font-size:14px;">✕</button>
    </div>
    <div id="blast-content" style="font-size:11px;color:#cbd5e1;display:flex;flex-direction:column;gap:6px;"></div>
  </div>

  <!-- ===== MODAL: Register ===== -->
  <div class="modal-bg" id="modal-reg">
    <div class="modal-box">
      <div class="modal-hdr">
        Registrar Proyecto
        <button class="modal-close" onclick="closeRegister()">✕</button>
      </div>
      <div style="font-size:11px;color:#64748b;margin-bottom:10px;">Selecciona el modo de registro:</div>
      <div class="card-grid">
        <div class="reg-card sel" id="mc-single" onclick="selMode('single_folder')">
          <div class="icon">📦</div><div>Carpeta Única</div>
        </div>
        <div class="reg-card" id="mc-master" onclick="selMode('master_folder')">
          <div class="icon">📂</div><div>Carpeta Maestra</div>
        </div>
        <div class="reg-card" id="mc-agent" onclick="selMode('agent_discovered')">
          <div class="icon">🤖</div><div>Por Agente</div>
        </div>
      </div>
      <div style="font-size:11px;color:#64748b;margin-bottom:5px;">Ruta absoluta:</div>
      <input class="text-inp" id="reg-path" placeholder="/home/…/mi-proyecto">
      <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:14px;">
        <button class="btn-action" onclick="closeRegister()">Cancelar</button>
        <button class="btn-action btn-primary" onclick="submitRegister()">Registrar e Indexar</button>
      </div>
    </div>
  </div>

  <!-- ===== MODAL: Tutorial ===== -->
  <div class="modal-bg" id="modal-tutorial">
    <div class="modal-box" style="width:520px;">
      <div class="modal-hdr">
        Tutorial — Conexión IA (Local vs Cloud)
        <button class="modal-close" onclick="closeTutorial()">✕</button>
      </div>
      <div style="display:flex;flex-direction:column;gap:10px;font-size:12px;color:#cbd5e1;">
        <div style="background:#0d1117;border:1px solid #1e293b;border-left:3px solid #38bdf8;border-radius:6px;padding:10px;">
          <div style="font-weight:700;color:#38bdf8;margin-bottom:6px;">IA Local — $0 / Privacidad total</div>
          <div>1. Instala Ollama: <code style="background:#1a2234;padding:2px 5px;border-radius:3px;">curl -fsSL https://ollama.com/install.sh | sh</code></div>
          <div style="margin-top:4px;">2. Descarga el modelo: <code style="background:#1a2234;padding:2px 5px;border-radius:3px;">ollama run qwen2.5-coder</code></div>
          <div style="margin-top:4px;">3. AetherGraph se conecta automáticamente a <code style="color:#10b981;">http://localhost:11434</code></div>
        </div>
        <div style="background:#0d1117;border:1px solid #1e293b;border-left:3px solid #f59e0b;border-radius:6px;padding:10px;">
          <div style="font-weight:700;color:#f59e0b;margin-bottom:6px;">IA Cloud — Gemini / Claude / OpenAI</div>
          <div>Declara la variable de entorno antes de iniciar AetherGraph:</div>
          <div style="background:#1a2234;padding:6px 8px;border-radius:4px;font-family:monospace;margin-top:4px;">export GEMINI_API_KEY="AIzaSy..."</div>
          <div style="margin-top:4px;">O añade las llaves en el archivo <code style="background:#1a2234;padding:2px 5px;border-radius:3px;">.env</code> (ver <strong>.env.example</strong>)</div>
        </div>
      </div>
      <div style="display:flex;justify-content:flex-end;margin-top:14px;">
        <button class="btn-action btn-primary" onclick="closeTutorial()">Entendido</button>
      </div>
    </div>
  </div>

  <script>
    // ── State ─────────────────────────────────────────────────────────────────
    let activePath    = null;   // null until first project loaded
    let activeView    = 'code';
    let activeDim     = '2d';
    let isRotating    = false;
    let rotateRaf     = null;
    let rotateAngle   = 0;
    let activePalette = 'obsidian';
    let regMode       = 'single_folder';
    let graphInst     = null;
    let fullData      = { nodes: [], links: [] };

    const PALETTES = {
      obsidian  : { file:'#38bdf8', class:'#f59e0b', func:'#a78bfa', agent:'#a855f7', asset:'#10b981', link:'rgba(148,163,184,0.30)', linkW:1.4, particle:'rgba(56,189,248,0.8)' },
      cyberpunk : { file:'#00f0ff', class:'#ffe600', func:'#ff007f', agent:'#9b00ff', asset:'#00ff7f', link:'rgba(0,240,255,0.25)',   linkW:1.4, particle:'rgba(0,240,255,0.9)' },
      dracula   : { file:'#ff79c6', class:'#bd93f9', func:'#8be9fd', agent:'#ffb86c', asset:'#50fa7b', link:'rgba(189,147,249,0.30)', linkW:1.4, particle:'rgba(255,121,198,0.9)' },
      solarized : { file:'#268bd2', class:'#b58900', func:'#d33682', agent:'#6c71c4', asset:'#2aa198', link:'rgba(38,139,210,0.30)',  linkW:1.4, particle:'rgba(42,161,152,0.9)' },
      nordic    : { file:'#88c0d0', class:'#ebcb8b', func:'#b48ead', agent:'#d08770', asset:'#a3be8c', link:'rgba(136,192,208,0.30)', linkW:1.4, particle:'rgba(235,203,139,0.9)' },
      vaporwave : { file:'#ff71ce', class:'#fffb96', func:'#b967ff', agent:'#fe75fe', asset:'#05ffa1', link:'rgba(255,113,206,0.30)', linkW:1.4, particle:'rgba(5,255,161,0.9)' },
      mono      : { file:'#e2e8f0', class:'#cbd5e1', func:'#94a3b8', agent:'#64748b', asset:'#f8fafc', link:'rgba(226,232,240,0.18)', linkW:0.9, particle:'rgba(226,232,240,0.7)' },
      matrix    : { file:'#22c55e', class:'#4ade80', func:'#16a34a', agent:'#15803d', asset:'#86efac', link:'rgba(34,197,94,0.25)',   linkW:1.4, particle:'rgba(34,197,94,0.9)' },
      community : { link:'rgba(148,163,184,0.30)', linkW:1.4, particle:'rgba(56,189,248,0.8)' }
    };
    // 12 distinct community colors (fixed — not affected by palette)
    const COMM_COLORS = ['#38bdf8','#f59e0b','#ef4444','#10b981','#a78bfa','#ec4899','#06b6d4','#84cc16','#eab308','#6366f1','#f97316','#14b8a6'];
    // Map: communityKey -> color (built when graph loads)
    let commColorMap = {};

    // ── Helpers ───────────────────────────────────────────────────────────────
    function getCommKey(n) {
      const raw = (n.details && n.kind === 'file') ? n.details : (n.details || n.name || 'general');
      const sep = raw.includes('/') ? '/' : '\\\\';
      const parts = raw.split(sep).filter(Boolean);
      if (parts.length > 1) return parts[parts.length - 2];
      const leaf = parts[0] || 'general';
      const dotIdx = leaf.indexOf('.');
      return dotIdx > 0 ? leaf.substring(0, dotIdx) : leaf;
    }

    function nodeColor(n) {
      if (activePalette === 'community') {
        const commKey = getCommKey(n);
        return commColorMap[commKey] || '#38bdf8';
      }
      const p = PALETTES[activePalette] || PALETTES.obsidian;
      const k = n.kind || '';
      if (k.includes('orchestrator')) return '#a855f7';
      if (k.includes('agent'))        return '#7c3aed';
      if (k.includes('hermes'))       return '#06b6d4';
      if (k === 'file' || k === 'module' || k === 'scene') return p.file;
      if (k === 'class' || k === 'interface' || k === 'csharp' || k === 'struct') return p.class;
      if (k === 'function' || k === 'method') return p.func;
      if (k === 'asset' || k === 'ui' || k === 'enum') return p.asset;
      return p.file;
    }

    function destroyGraph() {
      stop3DRotation();
      if (graphInst) {
        try { graphInst._destructor && graphInst._destructor(); } catch(e){}
        graphInst = null;
      }
      document.getElementById('graph-container').innerHTML = '';
    }

    // ── Dropdown ──────────────────────────────────────────────────────────────
    function toggleDD(id) {
      const el = document.getElementById(id);
      const was = el.classList.contains('open');
      document.querySelectorAll('.dd-wrap').forEach(d => d.classList.remove('open'));
      if (!was) el.classList.add('open');
    }
    document.addEventListener('click', e => {
      if (!e.target.closest('.dd-wrap')) document.querySelectorAll('.dd-wrap').forEach(d => d.classList.remove('open'));
    });

    // ── Modals ────────────────────────────────────────────────────────────────
    function openRegister() {
      document.getElementById('reg-path').value = activePath || '';
      document.getElementById('modal-reg').classList.add('show');
    }
    function closeRegister() { document.getElementById('modal-reg').classList.remove('show'); }

    function selMode(m) {
      regMode = m;
      ['single_folder','master_folder','agent_discovered'].forEach(x => {
        const id = x === 'single_folder' ? 'mc-single' : x === 'master_folder' ? 'mc-master' : 'mc-agent';
        document.getElementById(id).classList.toggle('sel', x === m);
      });
    }

    function submitRegister() {
      const path = document.getElementById('reg-path').value.trim();
      if (!path) return;
      fetch('/api/projects/register', {
        method: 'POST', headers: {'Content-Type':'application/json'},
        body: JSON.stringify({ path, mode: regMode })
      }).then(r => r.json()).then(res => {
        if (res.ok) { closeRegister(); loadProjects(); selectProject(path); }
        else alert('Error: ' + res.error);
      });
    }

    function openTutorial()  { document.getElementById('modal-tutorial').classList.add('show'); }
    function closeTutorial() { document.getElementById('modal-tutorial').classList.remove('show'); }

    // ── Projects ──────────────────────────────────────────────────────────────
    function loadProjects(thenLoadGraph) {
      fetch('/api/projects').then(r => r.json()).then(projects => {
        const el = document.getElementById('project-list');
        if (!projects.length) {
          el.innerHTML = '<div style="color:#475569;font-size:11px;">Sin proyectos registrados</div>';
          return;
        }
        if (!activePath && projects.length) activePath = projects[0].path;
        el.innerHTML = projects.map(p =>
          '<div class="project-item ' + (p.path === activePath ? 'active' : '') + '" onclick="selectProject(this.dataset.path)" data-path="' + p.path.replace(/"/g,'&quot;') + '">' +
          '<span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:148px;">' + p.name + '</span>' +
          '<span class="proj-badge ' + (p.indexed ? 'ok' : 'pend') + '">' + (p.indexed ? 'OK' : 'PEND') + '</span>' +
          '</div>'
        ).join('');
        if (thenLoadGraph) loadGraph();
      }).catch(() => {
        document.getElementById('project-list').innerHTML =
          '<div style="color:#ef4444;font-size:11px;">Error al cargar proyectos</div>';
      });
    }

    function selectProject(path) {
      activePath = path;
      if (activeView === 'agents') setView('code'); // switch to code view when selecting a project
      else { loadProjects(); loadGraph(); }
    }

    // ── View / Dim ────────────────────────────────────────────────────────────
    function setView(v) {
      activeView = v;
      document.getElementById('btn-code').classList.toggle('active', v === 'code');
      document.getElementById('btn-agents').classList.toggle('active', v === 'agents');
      destroyGraph();
      loadProjects();
      loadGraph();
    }

    function setDim(d) {
      if (activeDim === d) return;
      activeDim = d;
      document.getElementById('btn-2d').classList.toggle('active', d === '2d');
      document.getElementById('btn-3d').classList.toggle('active', d === '3d');
      const rotBtn = document.getElementById('btn-rotate');
      if (rotBtn) rotBtn.style.display = (d === '3d') ? 'inline-block' : 'none';
      if (d === '2d' && isRotating) toggleRotate();
      destroyGraph();
      loadGraph();
    }

    function toggleRotate() {
      isRotating = !isRotating;
      const btn = document.getElementById('btn-rotate');
      if (btn) btn.classList.toggle('active', isRotating);
      if (isRotating) start3DRotation();
      else stop3DRotation();
    }

    function start3DRotation() {
      if (rotateRaf) cancelAnimationFrame(rotateRaf);
      const tick = () => {
        if (!isRotating || activeDim !== '3d' || !graphInst || !graphInst.cameraPosition) return;
        const p = graphInst.cameraPosition();
        const r = Math.max(Math.hypot(p.x || 0, p.z || 0) || 500, 150);
        rotateAngle += 0.0035;
        graphInst.cameraPosition({ x: r * Math.sin(rotateAngle), y: p.y || 100, z: r * Math.cos(rotateAngle) }, undefined, 0);
        rotateRaf = requestAnimationFrame(tick);
      };
      rotateRaf = requestAnimationFrame(tick);
    }

    function stop3DRotation() {
      if (rotateRaf) { cancelAnimationFrame(rotateRaf); rotateRaf = null; }
    }

    function changePalette() {
      activePalette = document.getElementById('palette-sel').value;
      if (graphInst) {
        const p = PALETTES[activePalette];
        graphInst.nodeColor(n => nodeColor(n)).linkColor(() => p.link);
      }
    }

    function doReindex() {
      const btn = document.getElementById('reindex-btn');
      const engine = document.getElementById('engine-sel').value;
      btn.textContent = 'Indexando…';
      fetch('/api/reindex', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({ path: activePath, engine })
      }).then(r => r.json()).then(() => {
        btn.innerHTML = '<svg class="svg-ico" viewBox="0 0 24 24"><path d="M12 4V1L8 5l4 4V6c3.31 0 6 2.69 6 6 0 1.01-.25 1.97-.7 2.8l1.46 1.46A7.93 7.93 0 0020 12c0-4.42-3.58-8-8-8zm0 14c-3.31 0-6-2.69-6-6 0-1.01.25-1.97.7-2.8L5.24 7.74A7.93 7.93 0 004 12c0 4.42 3.58 8 8 8v3l4-4-4-4v3z"/></svg>Reindexar';
        loadProjects(); loadGraph();
      });
    }

    // ── Communities sidebar ───────────────────────────────────────────────────
    function buildCommunities(data) {
      // Build community groups by folder
      const groups = {};
      data.nodes.forEach(n => {
        const key = getCommKey(n);
        if (!groups[key]) groups[key] = 0;
        groups[key]++;
      });

      const sorted = Object.entries(groups).sort((a,b) => b[1] - a[1]);

      // Build stable color map: community key -> fixed color (not affected by palette)
      commColorMap = {};
      sorted.forEach(([name], idx) => {
        commColorMap[name] = COMM_COLORS[idx % COMM_COLORS.length];
      });

      const el = document.getElementById('community-list');
      el.innerHTML = sorted.map(([name, count]) => {
        const color = commColorMap[name];
        return `
          <div class="community-item" onclick="toggleComm('${name}')">
            <div class="comm-left">
              <label class="chk-wrap" onclick="event.stopPropagation()">
                <input type="checkbox" class="comm-chk" data-comm="${name}" checked onchange="applyFilter()">
                <span class="chk-box"><svg viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"/></svg></span>
              </label>
              <span class="comm-dot" style="background:${color};"></span>
              <span class="comm-name" title="${name}">${name}</span>
            </div>
            <span class="comm-badge">${count}</span>
          </div>`;
      }).join('');
    }

    function toggleComm(name) {
      const chk = document.querySelector(`.comm-chk[data-comm="${name}"]`);
      if (chk) { chk.checked = !chk.checked; applyFilter(); }
    }

    function toggleAllComm(checked) {
      document.querySelectorAll('.comm-chk').forEach(c => c.checked = checked);
      applyFilter();
    }

    // ── Filter ────────────────────────────────────────────────────────────────
    function applyFilter() {
      const q        = (document.getElementById('search-box').value || '').toLowerCase();
      const showFile = document.getElementById('f-file')?.checked ?? true;
      const showCls  = document.getElementById('f-class')?.checked ?? true;
      const showFn   = document.getElementById('f-func')?.checked ?? true;
      const showAgt  = document.getElementById('f-agent')?.checked ?? true;
      const minDeg   = parseInt(document.getElementById('f-deg')?.value || 0);
      const hideIso  = document.getElementById('f-isolated')?.checked ?? false;

      const activeComms = new Set(
        Array.from(document.querySelectorAll('.comm-chk:checked')).map(c => c.dataset.comm)
      );

      const filteredNodes = fullData.nodes.filter(n => {
        const k = n.kind || '';
        if ((k === 'file' || k === 'module' || k === 'scene') && !showFile) return false;
        if ((k === 'class' || k === 'interface' || k === 'csharp' || k === 'struct') && !showCls) return false;
        if ((k === 'function' || k === 'method') && !showFn) return false;
        if ((k.includes('agent') || k.includes('orchestrator') || k.includes('hermes') || k === 'asset' || k === 'ui') && !showAgt) return false;
        if ((n.degree || 0) < minDeg)  return false;
        if (hideIso && (n.degree || 0) === 0) return false;

        // Community filter — match by folder name or name prefix
        if (activeComms.size > 0) {
          const key = getCommKey(n);
          if (!activeComms.has(key)) return false;
        }

        if (q && !n.name.toLowerCase().includes(q) && !(n.details||'').toLowerCase().includes(q)) return false;
        return true;
      });

      const ids = new Set(filteredNodes.map(n => n.id));
      const filteredLinks = fullData.links.filter(l => {
        const s = typeof l.source === 'object' ? l.source.id : l.source;
        const t = typeof l.target === 'object' ? l.target.id : l.target;
        return ids.has(s) && ids.has(t);
      });

      if (graphInst) graphInst.graphData({ nodes: filteredNodes, links: filteredLinks });

      const statsEl = document.getElementById('stats');
      if (statsEl && fullData && fullData.nodes) {
        if (filteredNodes.length === fullData.nodes.length && filteredLinks.length === fullData.links.length) {
          statsEl.textContent = `${fullData.nodes.length} nodos · ${fullData.links.length} conectores`;
        } else {
          statsEl.textContent = `${filteredNodes.length} / ${fullData.nodes.length} nodos · ${filteredLinks.length} / ${fullData.links.length} conectores`;
        }
      }
    }

    // ── Graph render ──────────────────────────────────────────────────────────
    function showGraphSpinner(msg) {
      document.getElementById('graph-container').innerHTML =
        '<div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;gap:14px;">' +
        '<div style="width:36px;height:36px;border:3px solid #1e293b;border-top-color:#38bdf8;border-radius:50%;animation:spin 0.8s linear infinite;"></div>' +
        '<div style="color:#475569;font-size:12px;">' + msg + '</div>' +
        '</div>' +
        '<style>@keyframes spin{to{transform:rotate(360deg)}}</style>';
    }

    
    // ── Blast Radius & Interactive Node Inspector ───────────────────────────
    let selectedNode = null;

    function onNodeClick(node) {
      selectedNode = node;
      if (!node) return closeBlastPanel();

      // Find direct neighbors
      const neighbors = new Set();
      const connectedLinks = [];
      fullData.links.forEach(l => {
        const s = typeof l.source === 'object' ? l.source.id : l.source;
        const t = typeof l.target === 'object' ? l.target.id : l.target;
        if (s === node.id) { neighbors.add(t); connectedLinks.push(l); }
        if (t === node.id) { neighbors.add(s); connectedLinks.push(l); }
      });

      const neighborNodes = fullData.nodes.filter(n => neighbors.has(n.id));

      const panel = document.getElementById('blast-panel');
      const body = document.getElementById('blast-content');
      panel.style.display = 'block';

      body.innerHTML =
        '<div><strong>Símbolo:</strong> <span style="color:#38bdf8;">' + node.name + '</span></div>' +
        '<div><strong>Tipo:</strong> <span style="color:#f59e0b;">' + (node.kind || 'nodo') + '</span></div>' +
        (node.details ? '<div><strong>Ruta:</strong> <span style="color:#94a3b8;font-size:10px;">' + node.details + '</span></div>' : '') +
        '<div style="display:flex;gap:12px;margin-top:2px;">' +
          '<span>Grado Total: <strong style="color:#10b981;">' + (node.degree || 0) + '</strong></span>' +
          '<span>Impacto Directo: <strong style="color:#a78bfa;">' + neighborNodes.length + '</strong></span>' +
        '</div>' +
        '<button class="btn-action btn-primary" style="margin-top:4px;justify-content:center;" data-node-id="' + node.id.replace(/"/g, '&quot;') + '" onclick="focusNode(this.dataset.nodeId)">🎯 Centrar y Enfocar</button>' +
        '<hr style="border:none;border-top:1px solid #1e293b;margin:4px 0;">' +
        '<div style="font-weight:700;color:#64748b;font-size:10px;">VECINOS DIRECTOS (BLAST RADIUS):</div>' +
        '<div style="max-height:110px;overflow-y:auto;display:flex;flex-direction:column;gap:3px;">' +
        (neighborNodes.length ? neighborNodes.slice(0, 15).map(n =>
          '<div style="display:flex;justify-content:space-between;background:#1a2234;padding:3px 6px;border-radius:4px;cursor:pointer;" data-node-id="' + n.id.replace(/"/g, '&quot;') + '" onclick="focusNode(this.dataset.nodeId)">' +
            '<span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:180px;">' + n.name + '</span>' +
            '<span style="color:#64748b;font-size:9px;">' + (n.kind || '') + '</span>' +
          '</div>'
        ).join('') : '<div style="color:#64748b;">Sin conexiones directas</div>') +
        '</div>';

      // Highlight neighbors by dimming others
      if (graphInst && activeDim === '2d') {
        graphInst.nodeColor(n => {
          if (n.id === node.id) return '#ff007f';
          if (neighbors.has(n.id)) return nodeColor(n);
          return 'rgba(255,255,255,0.08)';
        });
      }
    }

    function closeBlastPanel() {
      selectedNode = null;
      document.getElementById('blast-panel').style.display = 'none';
      if (graphInst) {
        graphInst.nodeColor(n => nodeColor(n));
      }
    }

    function focusNode(nodeId) {
      const node = fullData.nodes.find(n => n.id === nodeId);
      if (node && graphInst) {
        if (activeDim === '2d') {
          graphInst.centerAt(node.x, node.y, 400);
          graphInst.zoom(3, 400);
        } else {
          const dist = 120;
          const ratio = 1 + dist / Math.hypot(node.x, node.y, node.z);
          graphInst.cameraPosition(
            { x: node.x * ratio, y: node.y * ratio, z: node.z * ratio },
            node,
            1200
          );
        }
        onNodeClick(node);
      }
    }

    function updatePhysics() {
      const rep = parseInt(document.getElementById('f-repulsion').value || -300);
      const dist = parseInt(document.getElementById('f-distance').value || 80);
      if (graphInst) {
        if (activeDim === '2d') {
          graphInst.d3Force('charge', d3.forceManyBody().strength(rep));
          graphInst.d3Force('link', d3.forceLink().distance(dist).strength(0.4));
        } else {
          graphInst.d3Force('charge').strength(rep);
          graphInst.d3Force('link').distance(dist);
        }
        graphInst.numDimensions && graphInst.numDimensions(activeDim === '2d' ? 2 : 3);
      }
    }

    function exportGraphData() {
      if (!fullData || !fullData.nodes.length) return alert('No hay datos de grafo para exportar');
      const jsonStr = JSON.stringify(fullData, null, 2);
      const blob = new Blob([jsonStr], { type: 'application/json' });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = `aether-graph-${activeView}-${Date.now()}.json`;
      a.click();
    }

function loadGraph() {
      if (!activePath && activeView === 'code') {
        document.getElementById('stats').textContent = 'Selecciona un proyecto';
        document.getElementById('graph-container').innerHTML =
          '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#475569;font-size:13px;">Selecciona un proyecto de la lista izquierda</div>';
        return;
      }
      const url = activeView === 'agents'
        ? '/api/graph?view=agents'
        : '/api/graph?path=' + encodeURIComponent(activePath);

      showGraphSpinner(activeView === 'agents' ? 'Cargando topologia de agentes...' : 'Escaneando proyecto...');
      document.getElementById('stats').textContent = 'Cargando...';

      fetch(url).then(r => r.json()).then(data => {
        if (!data.nodes || data.nodes.length === 0) {
          document.getElementById('graph-container').innerHTML =
            '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#475569;font-size:13px;">Sin nodos. Haz clic en Reindexar para escanear el proyecto.</div>';
          document.getElementById('stats').textContent = '0 nodos';
          buildCommunities(data);
          return;
        }
        fullData = data;
        const p = PALETTES[activePalette];
        document.getElementById('stats').textContent =
          `${data.nodes.length} nodos · ${data.links.length} conectores`;

        buildCommunities(data);

        const container = document.getElementById('graph-container');

        const nodeVal = n => {
          const k = n.kind || '';
          if (k.includes('orchestrator')) return activeDim === '2d' ? 20 : 24;
          if (k.includes('agent') || k.includes('hermes')) return activeDim === '2d' ? 12 : 14;
          if (k === 'class' || k === 'interface') return activeDim === '2d' ? 8 : 9;
          if (k === 'file') return activeDim === '2d' ? 6 : 7;
          return activeDim === '2d' ? 3 : 4;
        };
        const tooltip = n =>
          `<div style="background:#111827;border:1px solid #374151;border-radius:6px;padding:7px 11px;font-size:12px;color:#f8fafc;max-width:220px;">` +
          `<strong>${n.name}</strong>` +
          `<br/><span style="color:#64748b;font-size:10px;">${n.kind || ''}</span>` +
          (n.details ? `<br/><span style="color:#94a3b8;font-size:10px;">${n.details}</span>` : '') +
          `<br/><span style="color:${nodeColor(n)};font-weight:600;">●</span> <span style="color:#38bdf8;">Conexiones: ${n.degree || 0}</span>` +
          `</div>`;

        try {
          if (activeDim === '2d') {
            graphInst = ForceGraph()(container)
            .backgroundColor('#0b0e17')
            .graphData(data)
            .nodeId('id')
            .nodeVal(nodeVal)
            .nodeColor(n => nodeColor(n))
            .nodeLabel(tooltip).onNodeClick(onNodeClick)
            .linkColor(() => p.link)
            .linkWidth(p.linkW)
            .linkDirectionalParticles(2)
            .linkDirectionalParticleWidth(2.0)
            .linkDirectionalParticleSpeed(0.006)
            .linkDirectionalArrowLength(4)
            .linkDirectionalArrowRelPos(0.95)
            .linkDirectionalParticles(2)
            .linkDirectionalParticleWidth(2.5)
            .linkDirectionalParticleSpeed(0.006)
            .linkDirectionalParticleColor(() => p.particle)
            .linkDirectionalArrowLength(5)
            .linkDirectionalArrowRelPos(0.95)
            .d3AlphaDecay(0.012)
            .d3VelocityDecay(0.22)
            .d3Force('charge', d3.forceManyBody().strength(-300))
            .d3Force('link',   d3.forceLink().distance(80).strength(0.4))
            .d3Force('collide', d3.forceCollide().radius(22));
        } else {
          // Assign initial 3D positions so nodes spread in X, Y, Z sphere
          data.nodes.forEach(n => {
            if (n.x === undefined) n.x = (Math.random() - 0.5) * 600;
            if (n.y === undefined) n.y = (Math.random() - 0.5) * 600;
            if (n.z === undefined) n.z = (Math.random() - 0.5) * 600;
          });
          graphInst = ForceGraph3D()(container)
            .backgroundColor('#0b0e17')
            .graphData(data)
            .nodeId('id')
            .nodeVal(nodeVal)
            .nodeColor(n => nodeColor(n))
            .nodeLabel(n => `${n.name} (${n.kind || ''}) — ${n.degree || 0} conexiones`).onNodeClick(onNodeClick)
            .linkColor(() => p.link)
            .linkWidth(p.linkW)
            .linkDirectionalParticles(2)
            .linkDirectionalParticleWidth(2.5)
            .linkDirectionalParticleSpeed(0.006)
            .linkDirectionalArrowLength(5)
            .linkDirectionalArrowRelPos(0.95)
            .nodeRelSize(5);

          // Use 3D internal force engine (prevents 2D planar flattening)
          graphInst.d3Force('charge').strength(-250);
          graphInst.d3Force('link').distance(75);
        }

        applyFilter();
        } catch(err) {
          console.error("Graph render error:", err);
          document.getElementById('graph-container').innerHTML =
            '<div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;color:#ef4444;font-size:13px;padding:20px;text-align:center;">' +
            '<strong>Error al renderizar el grafo</strong><br/><span style="color:#94a3b8;font-size:11px;margin-top:6px;">' + err.message + '</span></div>';
        }
      }).catch(err => {
        console.error("Fetch error:", err);
        document.getElementById('graph-container').innerHTML =
          '<div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;color:#ef4444;font-size:13px;">Error al conectar con la API</div>';
      });
    }

    // ── Boot ──────────────────────────────────────────────────────────────────
    document.getElementById('graph-container').innerHTML =
      '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#475569;font-size:13px;">Cargando proyectos...</div>';
    loadProjects(true);  // true = load graph after projects are ready
  </script>
</body>
</html>
"""

