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
                    "color": "rgba(56, 189, 248, 0.75)"
                })

        return {"nodes": nodes, "links": links}

    def get_agent_topology_graph(self) -> Dict[str, Any]:
        """Genera el grafo de topología de agentes del arnés y sus capacidades."""
        nodes = [
            {"id": "agent:nexus", "name": "Orchestrator (Nexus)", "kind": "orchestrator", "val": 28, "color": "#a855f7", "details": "Orquestador Conversacional Principal"},
            {"id": "agent:career", "name": "Agent-Beta (Career)", "kind": "agent", "val": 20, "color": "#ec4899", "details": "Mentora de Carrera & Coach de Inglés"},
            {"id": "agent:coord", "name": "Eva (Coord)", "kind": "agent", "val": 20, "color": "#eab308", "details": "Coordinadora de Proyectos"},
            {"id": "agent:code", "name": "Agent-Code", "kind": "agent", "val": 20, "color": "#38bdf8", "details": "Estratega & Arquitecto de Código"},
            {"id": "agent:db", "name": "Agent-DB", "kind": "agent", "val": 20, "color": "#f59e0b", "details": "Estratega de Bases de Datos & SQL"},
            {"id": "agent:architect", "name": "Agent-Architect", "kind": "agent", "val": 20, "color": "#6366f1", "details": "Director Técnico & ADRs"},
            {"id": "agent:devops", "name": "Agent-DevOps", "kind": "agent", "val": 20, "color": "#10b981", "details": "Estratega de Infraestructura & CI/CD"},
            {"id": "agent:security", "name": "Agent-Security", "kind": "agent", "val": 20, "color": "#ef4444", "details": "Auditor DevSecOps & Zero-Trust"},
            {"id": "agent:qa", "name": "Agent-QA", "kind": "agent", "val": 20, "color": "#14b8a6", "details": "Estratega de Testing & Visual QA"},
            {"id": "agent:design", "name": "Agent-Design", "kind": "agent", "val": 20, "color": "#f43f5e", "details": "Estratega & Diseñador UI/UX"},
            {"id": "agent:docs", "name": "Agent-Docs", "kind": "agent", "val": 20, "color": "#8b5cf6", "details": "Estratega de Documentación"},

            {"id": "cap:file_operation", "name": "Gestión de Archivos", "kind": "capability", "val": 12, "color": "#94a3b8", "details": "Operaciones AST y Filesystem"},
            {"id": "cap:data_operation", "name": "Operación de Datos", "kind": "capability", "val": 12, "color": "#94a3b8", "details": "Consultas SQLite y Schemas"},
            {"id": "cap:security_audit", "name": "Auditoría de Seguridad", "kind": "capability", "val": 12, "color": "#94a3b8", "details": "Escaneo de vulnerabilidades y políticas"},
            {"id": "cap:quality_assurance", "name": "Quality Assurance", "kind": "capability", "val": 12, "color": "#94a3b8", "details": "Pruebas unitarias y visual testing"},
        ]

        links = [
            {"source": "agent:nexus", "target": "agent:code", "label": "orquesta", "color": "rgba(168, 85, 247, 0.85)"},
            {"source": "agent:nexus", "target": "agent:db", "label": "orquesta", "color": "rgba(168, 85, 247, 0.85)"},
            {"source": "agent:nexus", "target": "agent:security", "label": "orquesta", "color": "rgba(168, 85, 247, 0.85)"},
            {"source": "agent:nexus", "target": "agent:qa", "label": "orquesta", "color": "rgba(168, 85, 247, 0.85)"},
            {"source": "agent:nexus", "target": "agent:design", "label": "orquesta", "color": "rgba(168, 85, 247, 0.85)"},
            {"source": "agent:code", "target": "cap:file_operation", "label": "ejecuta", "color": "rgba(56, 189, 248, 0.85)"},
            {"source": "agent:db", "target": "cap:data_operation", "label": "ejecuta", "color": "rgba(245, 158, 11, 0.85)"},
            {"source": "agent:security", "target": "cap:security_audit", "label": "ejecuta", "color": "rgba(239, 68, 68, 0.85)"},
            {"source": "agent:qa", "target": "cap:quality_assurance", "label": "ejecuta", "color": "rgba(20, 184, 166, 0.85)"},
        ]
        return {"nodes": nodes, "links": links}
