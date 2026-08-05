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
                    "val": 15,
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
                        "val": 10 if sym["kind"] == "class" else 6,
                        "color": "#f59e0b" if sym["kind"] == "class" else "#a78bfa",
                        "details": f"{sym['kind'].capitalize()} en {res['file']}:{sym['line']}"
                    })
                    node_ids.add(sym_id)
                links.append({
                    "source": f_id,
                    "target": sym_id,
                    "label": "contiene",
                    "color": "rgba(148,163,184,0.3)"
                })

        return {"nodes": nodes, "links": links}
