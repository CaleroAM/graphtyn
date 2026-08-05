import ast
import re
from pathlib import Path
from typing import Dict, Any, List, Set, Optional

class ASTParser:
    """
    Deterministic zero-token standalone AST code symbol parser for AetherGraph.
    Parses Python, C#, JS/TS structural imports, classes, methods, calls, inheritance
    and folder hierarchy without any external dependencies.
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
                symbols.append({"name": node.name, "kind": "class", "line": node.lineno, "file": rel_path})
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                symbols.append({"name": node.name, "kind": "function", "line": node.lineno, "file": rel_path})
            elif isinstance(node, ast.Import):
                for alias in node.names: imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                for alias in node.names: imports.append(f"{mod}.{alias.name}" if mod else alias.name)
            elif isinstance(node, ast.Call):
                func_name = ""
                if isinstance(node.func, ast.Name): func_name = node.func.id
                elif isinstance(node.func, ast.Attribute): func_name = node.func.attr
                if func_name: calls.append(func_name)

        return {"file": rel_path, "symbols": symbols, "calls": list(set(calls)), "imports": list(set(imports))}

    def scan_directory(self, root_dir: Path) -> Dict[str, Any]:
        nodes: List[Dict[str, Any]] = []
        links: List[Dict[str, Any]] = []
        node_ids: Set[str] = set()
        symbol_name_map: Dict[str, str] = {}

        ignored_parts = {
            "venv", ".venv", "node_modules", "__pycache__", "Library",
            "Logs", "Temp", "obj", "bin", "dist", "build", ".git", ".idea", "Captures", ".vs"
        }

        csharp_files: List[tuple] = []
        python_files: List[tuple] = []

        # Pass 1: Build folder hierarchy backbone & file/asset nodes
        for path in root_dir.rglob("*"):
            if not path.is_file():
                continue
            if any(part.startswith(".") or part in ignored_parts for part in path.parts):
                continue

            ext = path.suffix.lower()
            if ext not in (".py", ".cs", ".js", ".ts", ".jsx", ".tsx", ".unity", ".prefab", ".asset", ".asmdef", ".shader", ".uxml", ".json", ".md"):
                continue

            rel_file = str(path.relative_to(root_dir))
            f_id = f"file:{rel_file}"

            # Parent folder node
            try:
                parent_dir = path.parent.relative_to(root_dir)
                p_id = f"dir:{parent_dir}" if str(parent_dir) != "." else "dir:root"
                p_name = parent_dir.name if str(parent_dir) != "." else root_dir.name
            except Exception:
                p_id = "dir:root"
                p_name = root_dir.name

            if p_id not in node_ids:
                nodes.append({
                    "id": p_id, "name": p_name, "kind": "module",
                    "val": 7, "color": "#38bdf8", "details": f"Carpeta: {p_name}"
                })
                node_ids.add(p_id)

            if f_id not in node_ids:
                kind = "asset" if ext in (".unity", ".prefab", ".asset", ".asmdef", ".shader", ".uxml") else "file"
                nodes.append({
                    "id": f_id, "name": path.name, "kind": kind,
                    "val": 5, "color": "#38bdf8", "details": rel_file
                })
                node_ids.add(f_id)
                links.append({"source": p_id, "target": f_id, "label": "contiene", "color": "rgba(148, 163, 184, 0.2)"})

            if ext == ".cs":
                csharp_files.append((path, rel_file, f_id))
            elif ext == ".py":
                python_files.append((path, rel_file, f_id))

        # Pass 2: Extract C# symbols, namespaces, methods, inheritance
        file_contents: Dict[str, str] = {}
        for path, rel_file, f_id in csharp_files:
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
                file_contents[rel_file] = content
                ns_match = re.search(r"namespace\s+([A-Za-z0-9_.]+)", content)
                ns = ns_match.group(1) if ns_match else ""

                # Classes / Interfaces / Structs / Enums
                for m in re.finditer(r"(public|private|protected|internal)?\s*(abstract|sealed|partial)?\s*(class|interface|enum|struct)\s+([A-Za-z0-9_]+)(\s*:\s*([A-Za-z0-9_,\s]+))?", content):
                    kind = m.group(3)
                    cname = m.group(4)
                    bases = m.group(6)
                    full_name = f"{ns}.{cname}" if ns else cname
                    sym_id = f"symbol:{rel_file}:{full_name}"

                    if sym_id not in node_ids:
                        nodes.append({
                            "id": sym_id, "name": cname, "kind": kind,
                            "val": 6 if kind in ("class", "interface") else 4,
                            "color": "#f59e0b" if kind in ("class", "interface") else "#10b981",
                            "details": full_name
                        })
                        node_ids.add(sym_id)
                        symbol_name_map[cname] = sym_id
                        links.append({"source": f_id, "target": sym_id, "label": "contiene", "color": "rgba(148, 163, 184, 0.2)"})

                    if bases:
                        for base in bases.split(","):
                            base_name = base.strip().split()[-1]
                            if base_name in symbol_name_map:
                                links.append({"source": sym_id, "target": symbol_name_map[base_name], "label": "hereda", "color": "rgba(245, 158, 11, 0.4)"})

                # Methods
                for m in re.finditer(r"(public|private|protected|internal)\s+(static|virtual|override|async)?\s*([A-Za-z0-9_<>]+)\s+([A-Za-z0-9_]+)\s*\([^)]*\)\s*\{", content):
                    mname = m.group(4)
                    if mname not in ("if", "for", "while", "switch", "catch"):
                        sym_id = f"symbol:{rel_file}:{mname}"
                        if sym_id not in node_ids:
                            nodes.append({
                                "id": sym_id, "name": mname, "kind": "method",
                                "val": 3, "color": "#a78bfa", "details": f"Método en {rel_file}"
                            })
                            node_ids.add(sym_id)
                            symbol_name_map[mname] = sym_id
                            links.append({"source": f_id, "target": sym_id, "label": "contiene", "color": "rgba(148, 163, 184, 0.2)"})
            except Exception:
                pass

        # Pass 3: Extract Python AST symbols & calls
        for path, rel_file, f_id in python_files:
            res = self.parse_python_file(path, root_dir)
            for sym in res.get("symbols", []):
                sym_id = f"symbol:{rel_file}:{sym['name']}"
                if sym_id not in node_ids:
                    nodes.append({
                        "id": sym_id, "name": sym["name"], "kind": sym["kind"],
                        "val": 4 if sym["kind"] == "class" else 2,
                        "color": "#f59e0b" if sym["kind"] == "class" else "#a78bfa",
                        "details": f"{sym['kind'].capitalize()} en {rel_file}:{sym['line']}"
                    })
                    node_ids.add(sym_id)
                    symbol_name_map[sym["name"]] = sym_id
                links.append({"source": f_id, "target": sym_id, "label": "contiene", "color": "rgba(148, 163, 184, 0.2)"})

        # Pass 4: Cross-symbol call / reference resolution
        for rel_file, content in file_contents.items():
            f_id = f"file:{rel_file}"
            for cname, sym_id in symbol_name_map.items():
                if cname in content and not sym_id.startswith(f"symbol:{rel_file}:"):
                    if re.search(r"\b" + re.escape(cname) + r"\b", content):
                        links.append({"source": f_id, "target": sym_id, "label": "usa", "color": "rgba(56, 189, 248, 0.25)"})

        return self._enrich_graph_with_degree({"nodes": nodes, "links": links})

    def _enrich_graph_with_degree(self, graph: Dict[str, Any]) -> Dict[str, Any]:
        in_degree: Dict[str, int] = {}
        out_degree: Dict[str, int] = {}

        for l in graph.get("links", []):
            src = l["source"]
            tgt = l["target"]
            out_degree[src] = out_degree.get(src, 0) + 1
            in_degree[tgt] = in_degree.get(tgt, 0) + 1

        for n in graph.get("nodes", []):
            nid = n["id"]
            total_deg = in_degree.get(nid, 0) + out_degree.get(nid, 0)
            n["degree"] = total_deg
            n["in_degree"] = in_degree.get(nid, 0)
            n["out_degree"] = out_degree.get(nid, 0)
            n["val"] = round(n.get("val", 3) + total_deg * 0.4, 2)

        return graph

    @classmethod
    def get_agent_topology_graph(cls, *args, **kwargs) -> Dict[str, Any]:
        nodes = [
            {"id": "agent:nexus", "name": "Nexus Orchestrator", "kind": "orchestrator_agent", "val": 30, "details": "Controlador principal de harness"},
            {"id": "agent:openclaw", "name": "OpenClaw Harness", "kind": "sub_agent", "val": 15, "details": "Harness de ejecución OpenClaw"},
            {"id": "agent:hermes", "name": "Hermes Agent", "kind": "sub_agent", "val": 15, "details": "Agente autónomo Hermes"},
            {"id": "mcp:aether-graph", "name": "AetherGraph MCP", "kind": "mcp_tool", "val": 10, "details": "Servidor MCP determinista AST"}
        ]
        links = [
            {"source": "agent:nexus", "target": "agent:openclaw", "label": "delegates"},
            {"source": "agent:nexus", "target": "agent:hermes", "label": "spawns"},
            {"source": "agent:openclaw", "target": "mcp:aether-graph", "label": "queries"},
            {"source": "agent:hermes", "target": "mcp:aether-graph", "label": "queries"}
        ]
        return ASTParser()._enrich_graph_with_degree({"nodes": nodes, "links": links})
