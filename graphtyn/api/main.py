import json
import os
import re
import ast
import subprocess
import hmac
import time
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Query, Body, Header
from fastapi.responses import HTMLResponse, JSONResponse, Response
from ..core.ast_parser import ASTParser
from ..core.history import HistoryTracker
from ..core.watcher import WatchManager
from ..core.impact import analyze_impact
from ..core.change_analyst import analyze_change, query_intent
from ..core.work_memory import attach_learning
from ..core.index_quality import index_quality
from ..core.overview_report import render_report
from ..core.answer_validation import validate_answer
from ..core.ambiguity_review import ambiguity_queue, apply_decisions, save_decision
from ..core.change_report import render_change_report
from ..core.incremental_status import build_update_status, save_update_status
from ..core.verification import verification_plan
from ..core.storage import data_home, project_store_dir
from ..core.graph_scope import filter_graph_scope
from ..mcp_server import blast_radius, context_bundle, get_workspace_graph, neighborhood_subgraph, _prune_node

parser = ASTParser()
watch_manager = WatchManager()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if _watch_enabled():
        root = Path(os.environ.get("GRAPHTYN_WATCH_PATH", str(DEFAULT_MASTER_DIR))).resolve()
        watch_manager.ensure(root, _index_dir(root))
    yield
    watch_manager.stop_all()


app = FastAPI(title="Graphtyn API", version="0.5.0", lifespan=lifespan)

# Central writable index store — user home ~/.graphtyn/
INDEX_STORE = data_home()
INDEX_STORE.mkdir(parents=True, exist_ok=True)

REGISTRATION_FILE = INDEX_STORE / "registered_projects.json"
DEFAULT_MASTER_DIR = Path.cwd()


def _index_dir(project_path: Path) -> Path:
    """Returns the writable index directory for a project."""
    return project_store_dir(INDEX_STORE, project_path)


def _watch_enabled() -> bool:
    return os.environ.get("GRAPHTYN_WATCH", "0").lower() in ("1", "true", "yes", "on")


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
_PROJECT_MARKERS = {".git", "package.json", "pyproject.toml", "requirements.txt", "app.py", "index.js", "go.mod", "Cargo.toml", "pom.xml", ".graphtyn"}

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
                if not p_path.exists():
                    continue
                registered = {
                    "id": cp.get("id", p_path.name),
                    "name": cp.get("name", p_path.name),
                    "path": str(p_path),
                    "mode": cp.get("mode", "single_folder"),
                    "indexed": _is_indexed(p_path),
                }
                existing = next((p for p in projects if p["path"] == str(p_path)), None)
                if existing is None:
                    projects.append(registered)
                else:
                    # An explicit registration is authoritative for display name
                    # and id, even when the project is also auto-discovered.
                    existing.update(registered)
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

    existing = next((cp for cp in custom_projects if cp["path"] == str(target_path)), None)
    if existing is None:
        custom_projects.append(new_entry)
    else:
        existing.update(new_entry)
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
    started_at = time.monotonic()
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

    dot_dir = _index_dir(root)
    graph = parser.scan_directory(root, respect_git=respect_git, cache_path=dot_dir / "structural_cache.json")
    graph.setdefault("metadata", {}).update({
        "indexed_with": engine, "status": "ok", "path": str(root), "respect_git": respect_git
    })

    prev = None
    cached = dot_dir / "index.json"
    if cached.exists():
        try:
            prev = json.loads(cached.read_text(encoding="utf-8"))
        except Exception:
            prev = None

    changed = None
    if not force_full and engine == "ast_local_llm" and prev is not None:
        changed = _detect_changed_files(root)

    if prev is not None and (not force_full or engine == "ast_pure"):
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

    graph = apply_decisions(graph, root)
    update_status = build_update_status(
        graph, prev, mode=graph["metadata"]["reindex_mode"], started_at=started_at,
        enriched_files=enriched_files, ai_calls=(graph.get("metadata") or {}).get("local_ai_calls"),
    )
    graph["metadata"]["last_update"] = update_status

    (dot_dir / "index.json").write_text(json.dumps(graph, indent=2))
    update_path = save_update_status(dot_dir, update_status)
    report, report_metrics = render_report(root, graph)
    report_path = dot_dir / "GRAPHTYN_REPORT.md"
    report_path.write_text(report, encoding="utf-8")
    return JSONResponse({
        "ok": True, "engine": engine,
        "nodes": len(graph["nodes"]), "links": len(graph["links"]),
        "mode": graph["metadata"]["reindex_mode"],
        "changed_files": len(changed) if changed is not None else None,
        "enriched_files": enriched_files,
        "metadata": graph["metadata"],
        "report": str(report_path),
        "report_metrics": report_metrics,
        "update": update_status,
        "update_status": str(update_path),
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
    semantic_content = []
    content_kinds = {"image", "media", "doc"}
    for n in data.get("nodes", []):
        kind = n.get("kind", "")
        if kind not in {"file", "class", "module", *content_kinds}:
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
        if kind in content_kinds:
            semantic_content.append(n)

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

    # 3. Infer bounded semantic relationships between enriched documents/media.
    # Descriptions are generated during reindexing; this view only compares the
    # cached text and therefore does not invoke the local model again.
    stopwords = {
        "para", "como", "este", "esta", "estos", "estas", "desde", "hasta", "entre", "sobre",
        "archivo", "imagen", "documento", "audio", "video", "muestra", "define", "contiene",
        "sirve", "serve", "utiliza", "permite", "proyecto", "proyectos", "software", "sistema",
        "artefacto", "tecnico", "técnico", "tecnica", "técnica", "mediante", "basado", "basada",
        "unitycommercedemo", "assets", "project", "resources", "file", "docs", "media"
    }

    def semantic_tokens(node: dict) -> set[str]:
        name = Path(node.get("name", "")).stem
        details = node.get("details", "") or ""
        # Enriched descriptions append the path in parentheses. Paths group by
        # location, not meaning, so exclude that suffix from similarity.
        details = re.sub(r"\s*\([^()]+[/\\][^()]+\)\s*$", "", details)
        text = re.sub(r"([a-záéíóúñ])([A-ZÁÉÍÓÚÑ])", r"\1 \2", f"{name} {details}").lower()
        return {
            token for token in re.findall(r"[a-záéíóúüñ0-9]+", text)
            if len(token) >= 4 and token not in stopwords and not token.isdigit()
        }

    token_sets = [semantic_tokens(n) for n in semantic_content]
    token_index = {}
    for idx, tokens in enumerate(token_sets):
        for token in tokens:
            token_index.setdefault(token, []).append(idx)

    shared_counts = {}
    for indexes in token_index.values():
        # Very frequent words are poor semantic signals and create quadratic
        # edge explosions in repositories containing thousands of textures.
        if len(indexes) > 50:
            continue
        for pos, left in enumerate(indexes):
            for right in indexes[pos + 1:]:
                shared_counts[(left, right)] = shared_counts.get((left, right), 0) + 1

    candidates_by_node = {i: [] for i in range(len(semantic_content))}
    for (left, right), common in shared_counts.items():
        if common < 2:
            continue
        denom = (len(token_sets[left]) * len(token_sets[right])) ** 0.5 or 1
        score = common / denom
        if score < 0.28:
            continue
        candidates_by_node[left].append((score, right))
        candidates_by_node[right].append((score, left))

    selected_pairs = set()
    for left, candidates in candidates_by_node.items():
        for score, right in sorted(candidates, reverse=True)[:2]:
            pair = (min(left, right), max(left, right))
            if pair in selected_pairs:
                continue
            selected_pairs.add(pair)
            left_node = semantic_content[pair[0]]
            right_node = semantic_content[pair[1]]
            shared_terms = sorted(token_sets[pair[0]] & token_sets[pair[1]])[:10]
            links.append({
                "source": left_node["id"],
                "target": right_node["id"],
                "label": f"similitud semántica · {round(score * 100)}%",
                "color": "rgba(236, 72, 153, 0.4)",
                "confidence": "INFERRED",
                "evidence": {
                    "method": "cached-description-token-overlap",
                    "shared_terms": shared_terms,
                    "source_excerpt": (left_node.get("details") or "")[:240],
                    "target_excerpt": (right_node.get("details") or "")[:240],
                },
                "explanation": f"Comparten términos descriptivos: {', '.join(shared_terms)}",
            })

    # 4. God nodes: most-connected real concepts (highlight for agents)
    god_candidates = sorted(real_nodes, key=lambda m: m.get("degree", 0), reverse=True)[:6]
    god_ids = {m["id"] for m in god_candidates if m.get("degree", 0) > 0}
    for n in nodes:
        if n.get("id") in god_ids:
            n["god"] = True
            n["val"] = round(n.get("val", 3) + 6, 2)

    # 5. Include existing structural dependencies between real nodes
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
    return JSONResponse({"status": "ok", "service": "Graphtyn", "version": "0.5.0"})


@app.get("/api/history")
def get_history(path: str = ".", limit: int = 15):
    root = Path(path).resolve()
    ht = HistoryTracker(root)
    return JSONResponse({"timeline": ht.get_timeline(limit=limit)})


@app.get("/api/diff")
def get_diff(path: str = ".", base: str | None = None):
    root = Path(path).resolve()
    data = None
    dot_dir = _index_dir(root)
    cached = dot_dir / "index.json"
    if cached.exists():
        try:
            data = json.loads(cached.read_text(encoding="utf-8"))
        except Exception:
            pass
    if not data:
        data = parser.scan_directory(
            root,
            respect_git=bool(_load_project_config(root).get("respect_git", True)),
            cache_path=dot_dir / "structural_cache.json",
        )

    report = analyze_impact(root, data, base=base)
    report["path"] = str(root)
    return JSONResponse(report)


@app.get("/api/index-update")
def get_index_update(path: str = Query(..., min_length=1)):
    root = Path(path).resolve()
    target = _index_dir(root) / "last-update.json"
    try:
        return JSONResponse({"ok": True, **json.loads(target.read_text(encoding="utf-8"))})
    except (OSError, json.JSONDecodeError):
        return JSONResponse({"ok": False, "error": "No hay una actualización registrada"}, status_code=404)


@app.get("/api/ambiguities")
def get_ambiguities(path: str = Query(..., min_length=1)):
    try:
        root, graph = _load_index_for_api(path)
    except ValueError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=404)
    return JSONResponse(ambiguity_queue(graph, root))


@app.post("/api/ambiguities/review")
def review_ambiguity(payload: dict = Body(...)):
    path, key, decision = payload.get("path"), payload.get("key"), payload.get("decision")
    if not path or not key or not decision:
        return JSONResponse({"ok": False, "error": "path, key y decision son obligatorios"}, status_code=400)
    root = Path(path).resolve()
    try:
        saved = save_decision(root, str(key), str(decision), str(payload.get("note") or ""))
    except ValueError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
    cached = _index_dir(root) / "index.json"
    if cached.exists():
        try:
            graph = apply_decisions(json.loads(cached.read_text(encoding="utf-8")), root)
            cached.write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")
        except (OSError, json.JSONDecodeError):
            pass
    return JSONResponse({"ok": True, "key": key, "review": saved})


@app.post("/api/validate-answer")
def validate_agent_answer(payload: dict = Body(...)):
    if not payload.get("path") or not payload.get("answer"):
        return JSONResponse({"ok": False, "error": "path y answer son obligatorios"}, status_code=400)
    try:
        root, graph = _load_index_for_api(str(payload["path"]))
    except ValueError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=404)
    return JSONResponse(validate_answer(apply_decisions(graph, root), str(payload["answer"]), payload.get("claims")))


@app.post("/api/change-report")
def generate_change_report(payload: dict = Body(...)):
    if not payload.get("path"):
        return JSONResponse({"ok": False, "error": "path es obligatorio"}, status_code=400)
    try:
        root, graph = _load_index_for_api(str(payload["path"]))
    except ValueError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=404)
    impact = analyze_impact(root, apply_decisions(graph, root), base=payload.get("base") or "HEAD")
    impact["verification_plan"] = verification_plan(impact)
    output = (root / str(payload.get("output") or "GRAPHTYN_CHANGE_REPORT.md")).resolve()
    try:
        output.relative_to(root)
    except ValueError:
        return JSONResponse({"ok": False, "error": "El reporte debe escribirse dentro del proyecto"}, status_code=400)
    output.write_text(render_change_report(root, impact), encoding="utf-8")
    return JSONResponse({"ok": True, "report": str(output), **impact})


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
    if _watch_enabled():
        watch_manager.ensure(root, dot_dir)
    cached = dot_dir / "index.json"
    data = None
    if cached.exists():
        try:
            data = json.loads(cached.read_text(encoding="utf-8"))
        except Exception:
            pass
    if not data:
        data = parser.scan_directory(
            root,
            respect_git=bool(_load_project_config(root).get("respect_git", True)),
            cache_path=dot_dir / "structural_cache.json",
        )
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


def _load_index_for_api(project_path: str) -> tuple[Path, dict]:
    root = Path(project_path).resolve()
    if not root.exists() or not root.is_dir():
        raise ValueError("La ruta del proyecto no existe o no es una carpeta")
    cached = _index_dir(root) / "index.json"
    if cached.exists():
        try:
            graph = json.loads(cached.read_text(encoding="utf-8"))
            indexed_path = str((graph.get("metadata") or {}).get("path") or "").strip()
            if indexed_path:
                indexed_root = Path(indexed_path).resolve()
                try:
                    indexed_root.relative_to(root)
                    if indexed_root.is_dir():
                        root = indexed_root
                except ValueError:
                    pass
            return root, graph
        except (OSError, json.JSONDecodeError):
            pass
    graph = parser.scan_directory(root, respect_git=bool(_load_project_config(root).get("respect_git", True)))
    return root, graph


def _safe_project_file_size(root: Path, relative: str) -> int:
    try:
        candidate = (root / relative).resolve()
        candidate.relative_to(root)
        return candidate.stat().st_size if candidate.is_file() else 0
    except (OSError, ValueError):
        return 0


@app.get("/api/index-quality")
def get_index_quality(path: str = Query(..., min_length=1), scope: str = "all"):
    try:
        _root, graph = _load_index_for_api(path)
    except ValueError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=404)
    scoped = filter_graph_scope(graph, scope)
    return JSONResponse({"ok": True, "scope": scope, **index_quality(scoped)})


@app.get("/api/report")
def get_graphtyn_report(path: str = Query(..., min_length=1)):
    try:
        root, graph = _load_index_for_api(path)
    except ValueError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=404)
    report, metrics = render_report(root, graph)
    return JSONResponse({"ok": True, "path": str(root), "filename": "GRAPHTYN_REPORT.md",
                         "content": report, "metrics": metrics})


@app.post("/api/context-bundle")
def create_context_bundle(payload: dict = Body(...)):
    project_path = str(payload.get("path") or "").strip()
    symbols = payload.get("symbols")
    if not project_path:
        return JSONResponse({"ok": False, "error": "Falta la ruta del proyecto"}, status_code=400)
    if not isinstance(symbols, list) or not symbols:
        return JSONResponse({"ok": False, "error": "Selecciona al menos un símbolo"}, status_code=400)
    clean_symbols = list(dict.fromkeys(str(s).strip() for s in symbols if str(s).strip()))[:10]
    if not clean_symbols:
        return JSONResponse({"ok": False, "error": "Selecciona al menos un símbolo válido"}, status_code=400)
    try:
        depth = min(3, max(0, int(payload.get("depth", 1))))
        limit = min(100, max(1, int(payload.get("limit", 12))))
    except (TypeError, ValueError):
        return JSONResponse({"ok": False, "error": "depth y limit deben ser enteros"}, status_code=400)
    try:
        root, graph = _load_index_for_api(project_path)
    except ValueError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=404)
    scope = str(payload.get("scope") or "all")
    graph = filter_graph_scope(graph, scope)
    result = context_bundle(graph, clean_symbols, depth, limit)
    result["scope"] = scope if scope in {"all", "production", "tests", "legacy"} else "all"
    result["unmatched_symbols"] = [ctx["symbol"] for ctx in result.get("contexts", []) if not ctx.get("matched_ids")]
    files = {n.get("file") for n in result.get("nodes", []) if n.get("file")}
    files.update(str(n.get("id"))[5:] for n in result.get("nodes", []) if str(n.get("id", "")).startswith("file:"))
    raw_chars = sum(_safe_project_file_size(root, str(rel)) for rel in files)
    raw_tokens = raw_chars // 4
    compact_tokens = int(result.get("estimated_tokens") or 0)
    result.update({
        "ok": True,
        "raw_context_tokens": raw_tokens,
        "tokens_saved": raw_tokens - compact_tokens,
        "reduction_rate": round((raw_tokens - compact_tokens) / max(1, raw_tokens), 4),
        "token_estimation": "caracteres UTF-8 / 4; estimación, no facturación del proveedor",
    })
    return JSONResponse(result)


@app.get("/api/watch/status")
def watch_status():
    return JSONResponse({"enabled": _watch_enabled(), "projects": watch_manager.statuses()})


_HTTP_MCP_TOOLS = [
    {"name": "graph_query_intent", "description": "Consulta de una ronda optimizada para overview/flow/bindings/persistence/tests/impact.", "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}, "request": {"type": "string"}, "intent": {"type": "string", "enum": ["auto", "overview", "flow", "bindings", "persistence", "tests", "impact"]}, "limit": {"type": "integer"}}, "required": ["request"]}},
    {"name": "graph_analyze_change", "description": "Plan verificable de cambio: targets, contratos, estado, pruebas y riesgos.", "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}, "request": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["request"]}},
    {"name": "graph_context_bundle", "description": "Vecindad e impacto de varios símbolos en una llamada compacta.", "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}, "symbols": {"type": "array", "items": {"type": "string"}, "maxItems": 10}, "depth": {"type": "integer"}, "limit": {"type": "integer"}}, "required": ["symbols"]}},
    {"name": "graph_neighborhood", "description": "Subgrafo alrededor de un símbolo.", "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}, "symbol": {"type": "string"}, "depth": {"type": "integer"}}}},
    {"name": "graph_blast_radius", "description": "Radio de impacto de un símbolo.", "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}, "symbol": {"type": "string"}, "depth": {"type": "integer"}}, "required": ["symbol"]}},
    {"name": "graph_search_concepts", "description": "Busca nombres y descripciones semánticas.", "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}, "query": {"type": "string"}}, "required": ["query"]}},
    {"name": "graph_pr_impact", "description": "Analiza riesgo e impacto Git/PR.", "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}, "base": {"type": "string"}}}},
]


@app.post("/mcp")
def mcp_http(payload: dict = Body(...), authorization: str | None = Header(default=None)):
    """Authenticated JSON-RPC MCP transport for trusted team clients."""
    token = os.environ.get("GRAPHTYN_MCP_TOKEN", "")
    supplied = authorization.removeprefix("Bearer ") if authorization else ""
    if not token:
        return JSONResponse({"error": "MCP HTTP deshabilitado: configura GRAPHTYN_MCP_TOKEN"}, status_code=503)
    if not hmac.compare_digest(token, supplied):
        return JSONResponse({"error": "No autorizado"}, status_code=401, headers={"WWW-Authenticate": "Bearer"})
    req_id = payload.get("id")
    method = payload.get("method")
    if method == "initialize":
        result = {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}, "serverInfo": {"name": "graphtyn-http", "version": "0.5.0"}}
    elif method == "tools/list":
        result = {"tools": _HTTP_MCP_TOOLS}
    elif method == "tools/call":
        params = payload.get("params", {})
        name = params.get("name")
        args = params.get("arguments", {})
        root = Path(args.get("path") or os.environ.get("GRAPHTYN_MCP_PATH", str(DEFAULT_MASTER_DIR))).resolve()
        if not root.is_dir():
            return JSONResponse({"jsonrpc": "2.0", "id": req_id, "error": {"code": -32602, "message": "Ruta de proyecto inválida"}})
        graph = get_workspace_graph(root, parser)
        if name == "graph_query_intent":
            data = attach_learning(query_intent(graph, str(args.get("request") or ""), str(args.get("intent") or "auto"), max(4, min(24, int(args.get("limit") or 10)))), root)
        elif name == "graph_analyze_change":
            data = analyze_change(graph, str(args.get("request") or ""), max(6, min(40, int(args.get("limit") or 18))))
        elif name == "graph_context_bundle":
            data = context_bundle(graph, args.get("symbols") or [], int(args.get("depth", 1)), int(args.get("limit") or 20))
        elif name == "graph_neighborhood":
            symbol = str(args.get("symbol", "")).strip()
            data = neighborhood_subgraph(graph, symbol, int(args.get("depth", 1))) if symbol else {"nodes": [_prune_node(n) for n in graph.get("nodes", [])], "links": graph.get("links", [])}
        elif name == "graph_blast_radius":
            data = blast_radius(graph, str(args.get("symbol", "")), int(args.get("depth", 2)))
        elif name == "graph_search_concepts":
            query = str(args.get("query", "")).lower()
            data = {"query": query, "matches": [_prune_node(n) for n in graph.get("nodes", []) if query in n.get("name", "").lower() or query in n.get("details", "").lower()]}
        elif name == "graph_pr_impact":
            data = analyze_impact(root, graph, args.get("base"))
        else:
            return JSONResponse({"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": "Tool desconocida"}})
        result = {"content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False)}]}
    else:
        return JSONResponse({"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": "Método desconocido"}})
    return JSONResponse({"jsonrpc": "2.0", "id": req_id, "result": result})


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
