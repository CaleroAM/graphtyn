import json
import re
import ast
import subprocess
from pathlib import Path
from fastapi import FastAPI, Query, Body
from fastapi.responses import HTMLResponse, JSONResponse, Response
from ..core.ast_parser import ASTParser
from ..core.history import HistoryTracker

app = FastAPI(title="AetherGraph API", version="0.4.0")
parser = ASTParser()

# Central writable index store — user home ~/.aether-graph/
INDEX_STORE = Path.home() / ".aether-graph"
INDEX_STORE.mkdir(parents=True, exist_ok=True)

REGISTRATION_FILE = INDEX_STORE / "registered_projects.json"
DEFAULT_MASTER_DIR = Path.cwd()


def _index_dir(project_path: Path) -> Path:
    """Returns the writable index directory for a project."""
    slug = project_path.name
    d = INDEX_STORE / slug
    d.mkdir(parents=True, exist_ok=True)
    return d

def _project_config_path(project_path: Path) -> Path:
    return _index_dir(project_path) / "config.json"

def _load_project_config(project_path: Path) -> dict:
    try:
        return json.loads(_project_config_path(project_path).read_text(encoding="utf-8"))
    except Exception:
        return {}

def _save_project_config(project_path: Path, cfg: dict) -> dict:
    merged = _load_project_config(project_path)
    merged.update(cfg)
    _project_config_path(project_path).write_text(json.dumps(merged, indent=2), encoding="utf-8")
    return merged

def _is_indexed(project_path: Path) -> bool:
    return (_index_dir(project_path) / "index.json").exists()

_NOISE_DIRS = {"node_modules", "dist", "build", "__pycache__", ".git", ".venv", "venv", "obj", "bin", ".idea", ".vs"}
_PROJECT_MARKERS = {".git", "package.json", "pyproject.toml", "requirements.txt", "app.py", "index.js", "go.mod", "Cargo.toml", "pom.xml", ".aether-graph"}

def _has_project_marker(d: Path) -> bool:
    try:
        names = {c.name for c in d.iterdir()}
    except Exception:
        return False
    return bool(names & _PROJECT_MARKERS)

def _load_registered_projects() -> list[dict]:
    projects = []
    cwd = Path.cwd()
    projects.append({
        "id": cwd.name,
        "name": cwd.name,
        "path": str(cwd),
        "mode": "single_folder",
        "indexed": _is_indexed(cwd)
    })
    parent = cwd.parent
    if parent.exists() and parent.name.lower() in ("proyectos", "projects", "code", "dev", "workspace", "documentos"):
        for d in sorted(parent.iterdir()):
            if d.is_dir() and not d.name.startswith(".") and d != cwd:
                projects.append({
                    "id": d.name,
                    "name": d.name,
                    "path": str(d),
                    "mode": "master_folder",
                    "indexed": _is_indexed(d)
                })
                try:
                    for sub in sorted(d.iterdir()):
                        if len(projects) > 300:
                            break
                        if (sub.is_dir() and not sub.name.startswith(".")
                                and sub.name not in _NOISE_DIRS and _has_project_marker(sub)):
                            projects.append({
                                "id": sub.name,
                                "name": f"{d.name}/{sub.name}",
                                "path": str(sub),
                                "mode": "subfolder",
                                "indexed": _is_indexed(sub)
                            })
                except Exception:
                    pass
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
        p["respect_git"] = bool(_load_project_config(Path(p["path"])).get("respect_git", True))
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

import os, urllib.request

from .enrich import (
    _EXT_LANG, _llm_ask, _FEWSHOT_SYM, _role_hint_and_fix, _node_neighbors,
    _detect_changed_files, _maybe_compact, _clean_answer, _extract_symbol_source, _enrich_with_ai,
)
@app.post("/api/projects/config")
def set_project_config(payload: dict = Body(...)):
    project_path = payload.get("path")
    if not project_path:
        return JSONResponse({"ok": False, "error": "Falta la ruta del proyecto"}, status_code=400)
    root = Path(project_path).resolve()
    update = {}
    if "respect_git" in payload:
        update["respect_git"] = bool(payload["respect_git"])
    if not update:
        return JSONResponse({"ok": False, "error": "Nada que configurar"}, status_code=400)
    cfg = _save_project_config(root, update)
    return JSONResponse({"ok": True, "path": str(root), "config": cfg})

@app.get("/api/projects/config")
def get_project_config(path: str = "."):
    root = Path(path).resolve()
    return JSONResponse({"path": str(root), "config": _load_project_config(root)})

@app.post("/api/reindex")
def reindex_project(payload: dict = Body(...)):
    project_path = payload.get("path")
    engine = payload.get("engine", "ast_local_llm")
    force_full = bool(payload.get("full"))
    model_override = payload.get("model") or None
    vision_model_override = payload.get("vision_model") or None
    if not project_path:
        return JSONResponse({"ok": False, "error": "Falta la ruta del proyecto"}, status_code=400)
    root = Path(project_path).resolve()
    if not root.exists():
        return JSONResponse({"ok": False, "error": f"La ruta '{project_path}' no existe"}, status_code=404)

    project_cfg = _load_project_config(root)
    respect_git = bool(project_cfg.get("respect_git", True))

    graph = parser.scan_directory(root, respect_git=respect_git)
    graph["metadata"] = {"indexed_with": engine, "status": "ok", "path": str(root), "respect_git": respect_git}

    prev = None
    dot_dir = _index_dir(root)
    cached = dot_dir / "index.json"
    if cached.exists():
        try:
            prev = json.loads(cached.read_text(encoding="utf-8"))
        except Exception:
            prev = None

    changed = None
    if not force_full and engine == "ast_local_llm" and prev is not None:
        changed = _detect_changed_files(root)

    if prev is not None and not force_full:
        graph = _enrich_with_ai(graph, engine, root, prev=prev, changed=changed, model_override=model_override, vision_model_override=vision_model_override)
    else:
        graph = _enrich_with_ai(graph, engine, root, model_override=model_override, vision_model_override=vision_model_override)

    enriched_files = sum(
        1 for n in graph.get("nodes", [])
        if n.get("id", "").startswith("file:")
        and n.get("details", "") and n.get("details", "") != n["id"].replace("file:", "")
    )
    graph["metadata"]["reindex_mode"] = "incremental" if changed is not None else "full"
    if changed is not None:
        graph["metadata"]["changed_files"] = len(changed)
    graph["metadata"]["enriched_files"] = enriched_files

    (dot_dir / "index.json").write_text(json.dumps(graph, indent=2))
    return JSONResponse({
        "ok": True, "engine": engine,
        "nodes": len(graph["nodes"]), "links": len(graph["links"]),
        "mode": graph["metadata"]["reindex_mode"],
        "changed_files": len(changed) if changed is not None else None,
        "enriched_files": enriched_files,
        "metadata": graph["metadata"]
    })

def generate_semantic_graph(data: dict) -> dict:
    nodes = []
    links = []
    node_ids = set()

    meta = data.get("metadata", {})
    proj_name = Path(meta.get("path", "proyecto")).name
    ai_sum = meta.get("ai_summary") or f"Módulo principal del sistema {proj_name}"

    def community_of(rel_path: str) -> str:
        parts = rel_path.split("/")
        if "/" in rel_path:
            dir_parts = parts[:-1]
            return "/".join(dir_parts[:2]) if dir_parts else "raiz"
        return "raiz"

    # 1. Root Global Architecture Concept Node
    arch_id = "concept:global_arch"
    nodes.append({
        "id": arch_id,
        "name": f"Arquitectura Global: {proj_name}",
        "kind": "semantic_concept",
        "val": 18,
        "color": "#ec4899",
        "details": f"Propósito General: {ai_sum}"
    })
    node_ids.add(arch_id)

    # 2. Group real nodes into subsystem communities (no per-node mirrors)
    communities = {}
    real_nodes = []
    for n in data.get("nodes", []):
        kind = n.get("kind", "")
        if kind not in ("file", "class", "module"):
            continue
        nid = n.get("id", "")
        if nid.startswith("file:"):
            key = community_of(nid.replace("file:", ""))
        elif nid.startswith("symbol:"):
            key = community_of(nid.split(":")[1] if len(nid.split(":")) > 1 else "raiz")
        elif nid.startswith("dir:"):
            key = nid.replace("dir:", "") or "raiz"
            if key == "root":
                key = "raiz"
        else:
            key = "raiz"
        communities.setdefault(key, []).append(n)
        real_nodes.append(n)

    for key, members in communities.items():
        c_id = f"community:{key}"
        top_names = sorted(members, key=lambda m: m.get("degree", 0), reverse=True)[:4]
        top_txt = ", ".join(m["name"] for m in top_names)
        nodes.append({
            "id": c_id,
            "name": f"Subsistema: {key}",
            "kind": "community",
            "val": 12,
            "color": "#10b981",
            "details": f"{len(members)} elementos · nodos clave: {top_txt}"
        })
        node_ids.add(c_id)
        links.append({
            "source": arch_id, "target": c_id, "label": "agrupa",
            "color": "rgba(236, 72, 153, 0.35)", "confidence": "EXTRACTED"
        })
        for m in members:
            nodes.append(m)
            node_ids.add(m["id"])
            links.append({
                "source": c_id, "target": m["id"], "label": "pertenece",
                "color": "rgba(16, 185, 129, 0.35)", "confidence": "EXTRACTED"
            })

    # 3. God nodes: most-connected real concepts (highlight for agents)
    god_candidates = sorted(real_nodes, key=lambda m: m.get("degree", 0), reverse=True)[:6]
    god_ids = {m["id"] for m in god_candidates if m.get("degree", 0) > 0}
    for n in nodes:
        if n.get("id") in god_ids:
            n["god"] = True
            n["val"] = round(n.get("val", 3) + 6, 2)

    # 4. Include existing structural dependencies between real nodes
    for link in data.get("links", []):
        src = link.get("source")
        tgt = link.get("target")
        if src in node_ids and tgt in node_ids:
            links.append({
                "source": src,
                "target": tgt,
                "label": link.get("label", "conecta"),
                "color": "rgba(56, 189, 248, 0.4)",
                "confidence": link.get("confidence", "EXTRACTED")
            })

    parser = ASTParser()
    return parser._enrich_graph_with_degree({"nodes": nodes, "links": links})


@app.get("/health")
def health_check():
    return JSONResponse({"status": "ok", "service": "AetherGraph", "version": "0.4.0"})


@app.get("/api/history")
def get_history(path: str = ".", limit: int = 15):
    root = Path(path).resolve()
    ht = HistoryTracker(root)
    return JSONResponse({"timeline": ht.get_timeline(limit=limit)})


@app.get("/api/diff")
def get_diff(path: str = "."):
    root = Path(path).resolve()
    try:
        res = subprocess.run(
            ["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True, timeout=15
        )
        changed_files = [line.strip().split()[-1] for line in res.stdout.strip().splitlines() if line.strip()] if res.returncode == 0 else []
    except Exception:
        changed_files = []

    data = None
    dot_dir = _index_dir(root)
    cached = dot_dir / "index.json"
    if cached.exists():
        try:
            data = json.loads(cached.read_text(encoding="utf-8"))
        except Exception:
            pass
    if not data:
        data = parser.scan_directory(root, respect_git=bool(_load_project_config(root).get("respect_git", True)))

    impacted = {}
    for cf in changed_files:
        f_id = f"file:{cf}"
        for l in data.get("links", []):
            s = l.get("source")
            t = l.get("target")
            if s == f_id and t not in impacted and not t.startswith("file:"):
                impacted[t] = l.get("confidence", "EXTRACTED")
            elif t == f_id and s not in impacted and not s.startswith("file:"):
                impacted[s] = l.get("confidence", "EXTRACTED")

    nodes_map = {n["id"]: n for n in data.get("nodes", [])}
    impacted_nodes = [{"node": nodes_map.get(i, {"id": i}), "confidence": c} for i, c in impacted.items()]
    return JSONResponse({
        "path": str(root),
        "changed_files": changed_files,
        "impacted_nodes": impacted_nodes,
        "impacted_count": len(impacted_nodes)
    })


@app.get("/api/ollama/models")
def ollama_models():
    hosts = [
        os.environ.get("OLLAMA_HOST"),
        "http://localhost:11434",
        "http://127.0.0.1:11434",
        "http://172.17.0.1:11434",
        "http://host.docker.internal:11434"
    ]
    _VISION_KEYWORDS = ("vl", "vision", "minicpm-v", "llava", "bakllava", "moondream")
    _EMBED_KEYWORDS = ("embed", "nomic-embed", "mxbai-embed")
    for h in hosts:
        if not h:
            continue
        try:
            req = urllib.request.Request(f"{h}/api/tags")
            with urllib.request.urlopen(req, timeout=4) as r:
                m_data = json.loads(r.read().decode("utf-8"))
                all_models = [m["name"] for m in m_data.get("models", [])]
                code_models = []
                vision_models = []
                for m in all_models:
                    ml = m.lower()
                    if any(k in ml for k in _EMBED_KEYWORDS):
                        continue  # skip embedding-only models
                    if any(k in ml for k in _VISION_KEYWORDS):
                        vision_models.append(m)
                    else:
                        code_models.append(m)
                return JSONResponse({
                    "host": h,
                    "models": all_models,
                    "code_models": code_models,
                    "vision_models": vision_models
                })
        except Exception:
            continue
    return JSONResponse({"host": None, "models": [], "code_models": [], "vision_models": []})


@app.get("/api/graph")
def get_graph(path: str = ".", view: str = "code"):
    if view == "agents":
        return JSONResponse(parser.get_agent_topology_graph())
    root = Path(path).resolve()
    dot_dir = _index_dir(root)
    cached = dot_dir / "index.json"
    data = None
    if cached.exists():
        try:
            data = json.loads(cached.read_text(encoding="utf-8"))
        except Exception:
            pass
    if not data:
        data = parser.scan_directory(root, respect_git=bool(_load_project_config(root).get("respect_git", True)))
        try:
            (dot_dir / "index.json").write_text(json.dumps(data, indent=2))
        except OSError:
            pass

    _IMG_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".svg"}
    _MED_EXTS = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".opus", ".aac", ".mp4", ".mov", ".mkv", ".webm", ".avi", ".mpeg"}
    _DOC_EXTS = {".pdf", ".docx", ".xlsx", ".xlsm"}
    for n in (data or {}).get("nodes", []):
        name = n.get("name", "").lower()
        suffix = Path(name).suffix.lower()
        if suffix in _IMG_EXTS:
            n["kind"] = "image"
        elif suffix in _MED_EXTS:
            n["kind"] = "media"
        elif suffix in _DOC_EXTS:
            n["kind"] = "doc"

    if view == "semantic":
        return JSONResponse(generate_semantic_graph(data))

    return JSONResponse(data)


@app.get("/comparison")
def model_comparison():
    comparison_path = Path(__file__).resolve().parent.parent / "web" / "comparison.html"
    return HTMLResponse(content=comparison_path.read_text(encoding="utf-8"))


@app.get("/favicon.svg")
def favicon():
    svg_path = Path(__file__).resolve().parent.parent / "web" / "favicon.svg"
    return Response(content=svg_path.read_text(encoding="utf-8"), media_type="image/svg+xml")


@app.get("/")
def index():
    dashboard_html = Path(__file__).resolve().parent.parent / "web" / "dashboard.html"
    return HTMLResponse(content=dashboard_html.read_text(encoding="utf-8"), headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache", "Expires": "0"})


@app.get("/dashboard.css")
def dashboard_css():
    css_path = Path(__file__).resolve().parent.parent / "web" / "dashboard.css"
    return HTMLResponse(content=css_path.read_text(encoding="utf-8"), media_type="text/css", headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache", "Expires": "0"})


@app.get("/dashboard.js")
def dashboard_js():
    js_path = Path(__file__).resolve().parent.parent / "web" / "dashboard.js"
    return HTMLResponse(content=js_path.read_text(encoding="utf-8"), media_type="application/javascript", headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache", "Expires": "0"})


@app.get("/js/{file}")
def js_module(file: str):
    if not file.endswith(".js") or "/" in file or "\\" in file or ".." in file:
        return JSONResponse({"error": "invalid path"}, status_code=404)
    js_path = Path(__file__).resolve().parent.parent / "web" / "js" / file
    if not js_path.is_file():
        return JSONResponse({"error": "not found"}, status_code=404)
    return HTMLResponse(content=js_path.read_text(encoding="utf-8"), media_type="application/javascript", headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache", "Expires": "0"})



