import ast
from pathlib import Path
from typing import Dict, Any, List, Set

class ASTParser:
    """
    Deterministic zero-token AST code symbol parser.
    Parses Python, JS/TS structural imports, classes, functions, calls and dependencies.
    """

    def parse_python_file(self, file_path: Path, root_dir: Path) -> Dict[str, Any]:
        rel_path = str(file_path.relative_to(root_dir))
        symbols = []
        calls = []
        imports = []

        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(content, filename=str(file_path))
        except Exception as e:
            return {"file": rel_path, "error": str(e), "symbols": [], "calls": [], "imports": []}

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                symbols.append({
                    "name": node.name,
                    "kind": "class",
                    "line": node.lineno,
                    "file": rel_path
                })
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                symbols.append({
                    "name": node.name,
                    "kind": "function",
                    "line": node.lineno,
                    "file": rel_path
                })
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                for alias in node.names:
                    imports.append(f"{mod}.{alias.name}" if mod else alias.name)
            elif isinstance(node, ast.Call):
                func_name = ""
                if isinstance(node.func, ast.Name):
                    func_name = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    func_name = node.func.attr
                if func_name:
                    calls.append(func_name)

        return {
            "file": rel_path,
            "symbols": symbols,
            "calls": list(set(calls)),
            "imports": list(set(imports))
        }

    def scan_directory(self, root_dir: Path) -> Dict[str, Any]:
        nodes = []
        links = []
        node_ids: Set[str] = set()

        for path in root_dir.rglob("*.py"):
            if any(part.startswith(".") or part in ("venv", "node_modules", "__pycache__") for part in path.parts):
                continue
            
            res = self.parse_python_file(path, root_dir)
            f_id = f"file:{res['file']}"
            
            if f_id not in node_ids:
                nodes.append({
                    "id": f_id,
                    "name": Path(res['file']).name,
                    "kind": "file",
                    "val": 5,
                    "color": "#38bdf8",
                    "details": f"Archivo de código: {res['file']}"
                })
                node_ids.add(f_id)

            for sym in res.get("symbols", []):
                sym_id = f"symbol:{res['file']}:{sym['name']}"
                if sym_id not in node_ids:
                    nodes.append({
                        "id": sym_id,
                        "name": sym["name"],
                        "kind": sym["kind"],
                        "val": 4 if sym["kind"] == "class" else 2,
                        "color": "#f59e0b" if sym["kind"] == "class" else "#a78bfa",
                        "details": f"{sym['kind'].capitalize()} en {res['file']}:{sym['line']}"
                    })
                    node_ids.add(sym_id)
                links.append({
                    "source": f_id,
                    "target": sym_id,
                    "label": "contiene",
                    "color": "rgba(148, 163, 184, 0.2)"
                })

            # Add import and call links
            for imp in res.get("imports", []):
                imp_clean = imp.split(".")[0]
                for other_path in root_dir.rglob("*.py"):
                    if other_path != path and imp_clean in other_path.stem:
                        other_rel = str(other_path.relative_to(root_dir))
                        other_fid = f"file:{other_rel}"
                        links.append({
                            "source": f_id,
                            "target": other_fid,
                            "label": "importa",
                            "color": "rgba(234, 179, 8, 0.25)"
                        })
                        break

            for call_name in res.get("calls", []):
                for node_item in nodes:
                    if node_item["kind"] == "function" and node_item["name"] == call_name and node_item["id"] != f_id:
                        links.append({
                            "source": f_id,
                            "target": node_item["id"],
                            "label": "llama",
                            "color": "rgba(236, 72, 153, 0.25)"
                        })
                        break

        return self._enrich_graph_with_degree({"nodes": nodes, "links": links})

    def _enrich_graph_with_degree(self, graph: Dict[str, Any]) -> Dict[str, Any]:
        """Calcula in-degree, out-degree y escala moderadamente el valor del nodo."""
        in_degree: Dict[str, int] = {}
        out_degree: Dict[str, int] = {}

        for link in graph.get("links", []):
            src = link.get("source")
            tgt = link.get("target")
            if src:
                out_degree[src] = out_degree.get(src, 0) + 1
            if tgt:
                in_degree[tgt] = in_degree.get(tgt, 0) + 1

        for node in graph.get("nodes", []):
            nid = node.get("id")
            in_d = in_degree.get(nid, 0)
            out_d = out_degree.get(nid, 0)
            total_d = in_d + out_d
            node["in_degree"] = in_d
            node["out_degree"] = out_d
            node["degree"] = total_d
            
            # Moderated scaling for clean Graphify dots
            base_val = node.get("val", 3)
            node["val"] = base_val + (total_d * 0.4)

        return graph

    def get_agent_topology_graph(self) -> Dict[str, Any]:
        """
        Descubre dinámicamente la topología de agentes del arnés:
        - Solo OpenClaw (si existe data/workspace)
        - Solo Hermes (si existe hermes-data/profiles)
        - Híbrido (si existen ambos)
        - Modo AST Standalone (si no existe ninguno)
        """
        nodes = []
        links = []
        node_ids: Set[str] = set()

        possible_workspace_dirs = [
            Path("/openclaw/data/workspace"),
            Path("/workspace/data/workspace"),
            Path("/home/developer/Documentos/openclaw/data/workspace"),
        ]
        workspace_dir = next((d for d in possible_workspace_dirs if d.exists()), None)

        possible_hermes_dirs = [
            Path("/openclaw/hermes-data/profiles"),
            Path("/workspace/hermes-data/profiles"),
            Path("/home/developer/Documentos/openclaw/hermes-data/profiles"),
        ]
        hermes_dir = next((d for d in possible_hermes_dirs if d.exists()), None)

        has_openclaw = workspace_dir is not None
        has_hermes = hermes_dir is not None

        # 1. OpenClaw Harness Detection
        if has_openclaw:
            nodes.append({
                "id": "agent:nexus",
                "name": "Orchestrator (Nexus)",
                "kind": "orchestrator",
                "val": 30,
                "color": "#a855f7",
                "details": "Orquestador Conversacional Principal (OpenClaw)"
            })
            node_ids.add("agent:nexus")

            for sub_dir in sorted(workspace_dir.iterdir()):
                if sub_dir.is_dir() and not sub_dir.name.startswith("."):
                    role_id = sub_dir.name
                    if role_id == "nexus":
                        continue
                    
                    ident_file = sub_dir / "IDENTITY.md"
                    display_name = f"Agent-{role_id.capitalize()}"
                    if ident_file.exists():
                        for line in ident_file.read_text(encoding="utf-8", errors="ignore").splitlines():
                            if line.startswith("- **Name:**") or line.startswith("- **Nombre:**"):
                                display_name = line.split(":", 1)[1].strip()
                                break
                    
                    agent_node_id = f"agent:{role_id}"
                    if agent_node_id not in node_ids:
                        color_map = {
                            "code": "#38bdf8", "db": "#f59e0b", "architect": "#6366f1",
                            "devops": "#10b981", "security": "#ef4444", "qa": "#14b8a6",
                            "design": "#f43f5e", "docs": "#8b5cf6", "career": "#ec4899", "coord": "#eab308"
                        }
                        nodes.append({
                            "id": agent_node_id,
                            "name": display_name,
                            "kind": "subagent",
                            "val": 22,
                            "color": color_map.get(role_id, "#38bdf8"),
                            "details": f"Subagente Especialista ({role_id})"
                        })
                        node_ids.add(agent_node_id)
                        
                        links.append({
                            "source": "agent:nexus",
                            "target": agent_node_id,
                            "label": "orquesta",
                            "color": "rgba(168, 85, 247, 0.85)"
                        })

        # 2. Hermes Harness Detection
        if has_hermes:
            hermes_root_id = "agent:hermes_gateway"
            if not has_openclaw:
                nodes.append({
                    "id": hermes_root_id,
                    "name": "Hermes Gateway",
                    "kind": "orchestrator",
                    "val": 30,
                    "color": "#06b6d4",
                    "details": "Orquestador Principal de Perfiles Hermes"
                })
                node_ids.add(hermes_root_id)

            for h_dir in sorted(hermes_dir.iterdir()):
                if h_dir.is_dir() and not h_dir.name.startswith("."):
                    h_id = f"hermes:{h_dir.name}"
                    if h_id not in node_ids:
                        nodes.append({
                            "id": h_id,
                            "name": f"Hermes-{h_dir.name}",
                            "kind": "hermes_subagent",
                            "val": 18,
                            "color": "#06b6d4",
                            "details": f"Perfil Hermes ({h_dir.name})"
                        })
                        node_ids.add(h_id)
                        parent_id = "agent:nexus" if has_openclaw else hermes_root_id
                        links.append({
                            "source": parent_id,
                            "target": h_id,
                            "label": "perfil_hermes",
                            "color": "rgba(6, 182, 212, 0.75)"
                        })

        # 3. Fallback: No harness active
        if not has_openclaw and not has_hermes:
            nodes.append({
                "id": "mode:standalone",
                "name": "Modo AST Standalone",
                "kind": "notice",
                "val": 20,
                "color": "#64748b",
                "details": "Sin arnés agéntico (Modo puro de análisis de código)"
            })

        return self._enrich_graph_with_degree({"nodes": nodes, "links": links})

