import ast
import hashlib
import json
import re
import posixpath
from pathlib import Path
from typing import Dict, Any, List, Set, Optional
from .tree_sitter_backend import PARSER_VERSION, parse_file as parse_tree_sitter_file
from .overview_report import collect_project_evidence
from .graph_hygiene import normalize_graph
from .type_evidence import apply_type_evidence

_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")

_MEDIA_EXTS = (".mp3", ".wav", ".m4a", ".ogg", ".flac", ".opus", ".aac", ".mp4", ".mov", ".mkv", ".webm", ".avi", ".mpeg")

VALID_EXTS = (
    ".py", ".cs", ".php", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rs", ".rb", ".c", ".cpp", ".h", ".hpp",
    ".scala", ".lua", ".jl", ".zig", ".ex", ".exs", ".tf", ".tfvars", ".cls", ".trigger",
    ".kt", ".kts", ".swift", ".dart", ".sh", ".bash", ".sql", ".vue", ".svelte",
    ".md", ".mdx", ".rst", ".txt", ".pdf", ".docx", ".xlsx", ".xlsm",
    ".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp",
    ".mp3", ".wav", ".m4a", ".ogg", ".flac", ".opus", ".aac", ".mp4", ".mov", ".mkv", ".webm", ".avi", ".mpeg",
    ".unity", ".prefab", ".asset", ".asmdef", ".shader", ".uxml", ".json",
)

class ASTParser:
    """
    Deterministic zero-token standalone multi-language AST code symbol parser for Graphtyn.
    Parses Python, C#, PHP, JS/TS, Java, Go, Rust, Ruby, C/C++ classes, functions, methods,
    calls, inheritance and folder hierarchy without any external dependencies.
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

    def scan_directory(self, root_dir: Path, respect_git: bool = True, cache_path: Optional[Path] = None) -> Dict[str, Any]:
        root_dir = Path(root_dir)
        nodes: List[Dict[str, Any]] = []
        links: List[Dict[str, Any]] = []
        node_ids: Set[str] = set()
        symbol_name_map: Dict[str, str] = {}
        symbol_name_ids: Dict[str, Set[str]] = {}
        pending_inheritance: List[tuple] = []
        tree_calls: Dict[str, List[Dict[str, Any]]] = {}
        tree_imports: Dict[str, List[Dict[str, Any]]] = {}
        tree_members: Dict[str, List[Dict[str, Any]]] = {}
        file_namespaces: Dict[str, str] = {}
        tree_parsed_files: Set[str] = set()
        cache_hits = 0
        cache_misses = 0

        structural_cache = {"version": PARSER_VERSION, "files": {}}
        if cache_path and Path(cache_path).exists():
            try:
                loaded = json.loads(Path(cache_path).read_text(encoding="utf-8"))
                if loaded.get("version") == PARSER_VERSION:
                    structural_cache = loaded
            except (OSError, ValueError, TypeError):
                pass

        def _tree_facts(path: Path, rel_file: str) -> Optional[Dict[str, Any]]:
            nonlocal cache_hits, cache_misses
            if path.suffix.lower() not in (".cs", ".php", ".js", ".jsx", ".ts", ".tsx", ".py", ".java", ".go", ".rs"):
                return None
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            cached = structural_cache.get("files", {}).get(rel_file, {})
            if cached.get("sha256") == digest and cached.get("result", {}).get("parser") == "tree-sitter":
                cache_hits += 1
                return cached["result"]
            cache_misses += 1
            result = parse_tree_sitter_file(path, rel_file)
            if result is not None:
                structural_cache.setdefault("files", {})[rel_file] = {"sha256": digest, "result": result}
            return result

        def _register_symbol(name: str, sym_id: str) -> None:
            symbol_name_map[name] = sym_id
            symbol_name_ids.setdefault(name, set()).add(sym_id)

        def _add_tree_symbols(result: Dict[str, Any], f_id: str, namespace: str = "") -> None:
            rel_file = result["file"]
            tree_parsed_files.add(rel_file)
            tree_calls[rel_file] = result.get("calls", [])
            tree_imports[rel_file] = result.get("imports", [])
            import_evidence = list(dict.fromkeys(
                str(item.get("text") or "").strip()[:180]
                for item in result.get("imports", []) if str(item.get("text") or "").strip()
            ))[:24]
            file_node = next((node for node in nodes if node.get("id") == f_id), None)
            if file_node is not None and import_evidence:
                file_node["imports"] = import_evidence
            tree_members[rel_file] = result.get("members", [])
            namespace = result.get("namespace") or namespace or file_namespaces.get(rel_file, "")
            file_namespaces[rel_file] = namespace
            for sym in result.get("symbols", []):
                name = sym["name"]
                kind = sym["kind"]
                qualified = f"{namespace}.{name}" if namespace and kind in ("class", "interface", "struct", "enum") else name
                sym_id = f"symbol:{rel_file}:{qualified}"
                if sym_id in node_ids and kind in ("method", "function"):
                    arity = sym.get("parameter_count")
                    sym_id = f"{sym_id}/{arity if arity is not None else sym['line']}"
                if sym_id in node_ids:
                    continue
                symbol_node = {
                    "id": sym_id, "name": name, "kind": kind,
                    "val": 6 if kind in ("class", "interface") else (3 if kind in ("method", "function") else 4),
                    "color": "#f59e0b" if kind in ("class", "interface", "struct") else "#a78bfa",
                    "details": f"{kind.capitalize()} en {rel_file}:{sym['line']}",
                    "file": rel_file, "line": sym["line"], "end_line": sym.get("end_line", sym["line"]),
                    "evidence": sym.get("evidence", ""), "parser": "tree-sitter",
                    "namespace": namespace, "container": sym.get("container", ""),
                    "parameter_count": sym.get("parameter_count"), "signature": sym.get("signature", ""),
                    "required_parameter_count": sym.get("required_parameter_count"),
                    "is_constructor": sym.get("is_constructor", False),
                    "assembly": next((node.get("assembly") for node in nodes if node.get("id") == f_id), None),
                }
                if kind in ("class", "interface", "struct", "enum") and import_evidence:
                    symbol_node["imports"] = import_evidence
                nodes.append(symbol_node)
                node_ids.add(sym_id)
                _register_symbol(name, sym_id)
                links.append({
                    "source": f_id, "target": sym_id, "label": "contiene",
                    "color": "rgba(148, 163, 184, 0.2)", "confidence": "EXTRACTED",
                    "file": rel_file, "line": sym["line"], "evidence": sym.get("evidence", ""),
                })
                container = sym.get("container", "")
                if container:
                    owner = next((
                        node["id"] for node in nodes
                        if node.get("name") == container and node.get("file") == rel_file
                        and node.get("kind") in ("class", "interface", "struct")
                    ), None)
                    if owner:
                        links.append({
                            "source": owner, "target": sym_id, "label": "declara",
                            "color": "rgba(192, 132, 252, 0.3)", "confidence": "EXTRACTED",
                            "file": rel_file, "line": sym["line"], "evidence": sym.get("evidence", ""),
                        })
                for base in sym.get("bases", []):
                    pending_inheritance.append((sym_id, base, rel_file, sym["line"], sym.get("evidence", "")))
            for member in result.get("members", []):
                name = member.get("name", "")
                container = member.get("container", "")
                kind = member.get("kind", "field")
                if not name or not container:
                    continue
                sym_id = f"symbol:{rel_file}:{container}.{name}"
                if sym_id in node_ids:
                    continue
                member_type = member.get("type", "")
                nodes.append({
                    "id": sym_id, "name": name, "kind": kind,
                    "val": 2, "color": "#fb7185" if kind == "event" else "#c084fc",
                    "details": f"{kind.capitalize()} {member_type} en {rel_file}:{member['line']}",
                    "file": rel_file, "line": member["line"],
                    "end_line": member.get("end_line", member["line"]),
                    "evidence": member.get("evidence", ""), "parser": "tree-sitter",
                    "namespace": namespace, "container": container,
                    "member_type": member_type, "signature": member.get("signature", ""),
                    "assembly": next((node.get("assembly") for node in nodes if node.get("id") == f_id), None),
                })
                node_ids.add(sym_id)
                _register_symbol(name, sym_id)
                container_ids = [
                    node["id"] for node in nodes
                    if node.get("name") == container and node.get("file") == rel_file
                    and node.get("kind") in ("class", "interface", "struct")
                ]
                links.append({
                    "source": container_ids[0] if container_ids else f_id,
                    "target": sym_id, "label": "declara", "confidence": "EXTRACTED",
                    "file": rel_file, "line": member["line"],
                    "evidence": member.get("evidence", ""),
                    "color": "rgba(192, 132, 252, 0.3)",
                })
            # Keep method-body evidence bounded and attached to its declaring
            # callable. This preserves external/framework operations even when
            # no local target node exists, without creating noisy fake edges.
            seen_operations: Dict[str, Set[tuple]] = {}
            for operation in result.get("operations", []):
                caller = operation.get("caller", "")
                container = operation.get("container", "")
                line = int(operation.get("line") or 0)
                candidates = [
                    node for node in nodes
                    if node.get("file") == rel_file and node.get("name") == caller
                    and node.get("kind") in ("method", "function")
                    and (not container or node.get("container") == container)
                    and int(node.get("line") or 0) <= line <= int(node.get("end_line") or line)
                ]
                if not candidates:
                    continue
                owner = min(candidates, key=lambda node: int(node.get("end_line") or line) - int(node.get("line") or 0))
                key = (operation.get("kind"), operation.get("name"), line, operation.get("text"))
                bucket = seen_operations.setdefault(owner["id"], set())
                if key in bucket or len(bucket) >= 64:
                    continue
                bucket.add(key)
                owner.setdefault("operations", []).append({
                    "kind": operation.get("kind", "operation"),
                    "name": operation.get("name", ""),
                    "line": line,
                    "text": str(operation.get("text") or "")[:300],
                })
            for owner in (node for node in nodes if node.get("file") == rel_file and node.get("operations")):
                ops_text = " ".join(str(op.get("text") or "") for op in owner["operations"])
                signature = str(owner.get("signature") or "")
                if "TryGetValue(" in ops_text and re.search(r"\breturn\s+[A-Za-z_]\w*\s*;", ops_text):
                    return_type = signature.split("(", 1)[0].split()
                    if return_type and return_type[-2:-1] and return_type[-2] not in {
                        "bool", "byte", "sbyte", "short", "ushort", "int", "uint", "long", "ulong",
                        "float", "double", "decimal", "char", "void",
                    }:
                        owner.setdefault("semantic_hints", []).append({
                            "fact": "missing dictionary key returns default reference value (null)",
                            "confidence": "INFERRED", "basis": "TryGetValue(out value) followed by return value",
                        })

        ignored_parts = {
            "vendor", "venv", ".venv", "node_modules", "__pycache__", "Library",
            "Logs", "Temp", "obj", "bin", "dist", "build", ".git", ".idea", "Captures", ".vs"
        }

        tracked_files = None
        if respect_git and (root_dir / ".git").exists():
            try:
                import subprocess
                res = subprocess.run(
                    ["git", "ls-files"], cwd=root_dir, capture_output=True, text=True, timeout=30
                )
                if res.returncode == 0:
                    tracked_files = set(res.stdout.splitlines())
            except Exception:
                tracked_files = None

        csharp_files: List[tuple] = []
        python_files: List[tuple] = []
        php_files: List[tuple] = []
        terraform_files: List[tuple] = []
        doc_files: List[tuple] = []
        other_code_files: List[tuple] = []

        # Pass 1: Build folder hierarchy backbone & file/asset nodes
        for path in root_dir.rglob("*"):
            if not path.is_file():
                continue
            if any(part.startswith(".") or part in ignored_parts for part in path.parts):
                continue

            ext = path.suffix.lower()
            if ext not in VALID_EXTS:
                continue

            rel_file = str(path.relative_to(root_dir))
            if tracked_files is not None and rel_file not in tracked_files:
                continue
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
                kind = "asset" if ext in (".unity", ".prefab", ".asset", ".asmdef", ".shader", ".uxml") else ("image" if ext in _IMAGE_EXTS else ("media" if ext in _MEDIA_EXTS else ("doc" if ext in (".pdf", ".docx", ".xlsx", ".xlsm") else "file")))
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
            elif ext == ".php":
                php_files.append((path, rel_file, f_id))
            elif ext in (".tf", ".tfvars"):
                terraform_files.append((path, rel_file, f_id))
            elif ext in (".md", ".mdx", ".rst", ".txt"):
                doc_files.append((path, rel_file, f_id))
            elif ext in (".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rs", ".rb", ".c", ".cpp", ".kt", ".kts", ".swift", ".dart", ".sh", ".bash", ".sql", ".vue", ".svelte", ".scala", ".lua", ".jl", ".zig", ".ex", ".exs", ".cls", ".trigger"):
                other_code_files.append((path, rel_file, f_id, ext))

        file_contents: Dict[str, str] = {}

        # Unity assembly boundaries (.asmdef). A C# file belongs to the
        # nearest ancestor definition; files without one use Assembly-CSharp.
        asmdefs: Dict[str, Dict[str, Any]] = {}
        for asm_path in root_dir.rglob("*.asmdef"):
            rel_asm = str(asm_path.relative_to(root_dir))
            if tracked_files is not None and rel_asm not in tracked_files:
                continue
            try:
                cfg = json.loads(asm_path.read_text(encoding="utf-8"))
                name = cfg.get("name") or asm_path.stem
                asmdefs[str(asm_path.parent.resolve())] = {
                    "name": name, "file": rel_asm, "references": cfg.get("references", []),
                    "root_namespace": cfg.get("rootNamespace", ""),
                    "guid": "",
                }
                meta_path = asm_path.with_suffix(asm_path.suffix + ".meta")
                if meta_path.exists():
                    guid_match = re.search(r"^guid:\s*(\S+)", meta_path.read_text(encoding="utf-8", errors="ignore"), re.MULTILINE)
                    if guid_match:
                        asmdefs[str(asm_path.parent.resolve())]["guid"] = guid_match.group(1)
            except (OSError, ValueError, TypeError):
                continue

        node_by_id = {node["id"]: node for node in nodes}
        for path, rel_file, f_id in csharp_files:
            current = path.parent.resolve()
            assembly = None
            while current == root_dir.resolve() or root_dir.resolve() in current.parents:
                if str(current) in asmdefs:
                    assembly = asmdefs[str(current)]
                    break
                if current == root_dir.resolve():
                    break
                current = current.parent
            assembly_name = assembly["name"] if assembly else "Assembly-CSharp"
            if f_id in node_by_id:
                node_by_id[f_id]["assembly"] = assembly_name
            file_namespaces.setdefault(rel_file, assembly.get("root_namespace", "") if assembly else "")
        asm_name_to_file = {item["name"]: f"file:{item['file']}" for item in asmdefs.values()}
        asm_guid_to_file = {item["guid"]: f"file:{item['file']}" for item in asmdefs.values() if item["guid"]}
        for item in asmdefs.values():
            source = f"file:{item['file']}"
            for reference in item["references"]:
                ref_text = str(reference)
                target = asm_guid_to_file.get(ref_text.removeprefix("GUID:")) if ref_text.startswith("GUID:") else asm_name_to_file.get(ref_text)
                if target and target != source:
                    links.append({
                        "source": source, "target": target, "label": "referencia ensamblado",
                        "confidence": "EXTRACTED", "evidence": str(reference),
                        "color": "rgba(16, 185, 129, 0.35)",
                    })

        # Pass 2A: Extract PHP symbols
        for path, rel_file, f_id in php_files:
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
                file_contents[rel_file] = content
                ns_match = re.search(r"namespace\s+([A-Za-z0-9_\\]+);", content)
                ns = ns_match.group(1) if ns_match else ""

                tree_result = _tree_facts(path, rel_file)
                if tree_result is not None:
                    _add_tree_symbols(tree_result, f_id, ns)
                    continue

                for m in re.finditer(r"(class|interface|trait|enum)\s+([A-Za-z0-9_]+)(\s+extends\s+([A-Za-z0-9_\\]+))?", content):
                    kind = m.group(1)
                    cname = m.group(2)
                    base = m.group(4)
                    full_name = f"{ns}\\{cname}" if ns else cname
                    sym_id = f"symbol:{rel_file}:{full_name}"

                    if sym_id not in node_ids:
                        nodes.append({
                            "id": sym_id, "name": cname, "kind": kind,
                            "val": 6, "color": "#f59e0b", "details": full_name
                        })
                        node_ids.add(sym_id)
                        _register_symbol(cname, sym_id)
                        links.append({"source": f_id, "target": sym_id, "label": "contiene", "color": "rgba(148, 163, 184, 0.2)"})

                for m in re.finditer(r"(public|private|protected|static|\s)*function\s+([A-Za-z0-9_]+)\s*\(", content):
                    mname = m.group(2)
                    if not mname.startswith("__") or mname in ("__construct", "__invoke"):
                        sym_id = f"symbol:{rel_file}:{mname}"
                        if sym_id not in node_ids:
                            nodes.append({
                                "id": sym_id, "name": mname, "kind": "function",
                                "val": 3, "color": "#a78bfa", "details": f"Función/Método en {rel_file}"
                            })
                            node_ids.add(sym_id)
                            _register_symbol(mname, sym_id)
                            links.append({"source": f_id, "target": sym_id, "label": "contiene", "color": "rgba(148, 163, 184, 0.2)"})
            except Exception:
                pass

        # Pass 2B: Extract C# symbols, namespaces, methods, inheritance
        for path, rel_file, f_id in csharp_files:
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
                file_contents[rel_file] = content
                ns_match = re.search(r"namespace\s+([A-Za-z0-9_.]+)", content)
                ns = ns_match.group(1) if ns_match else ""

                tree_result = _tree_facts(path, rel_file)
                if tree_result is not None:
                    _add_tree_symbols(tree_result, f_id, ns)
                    continue

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
                        _register_symbol(cname, sym_id)
                        links.append({"source": f_id, "target": sym_id, "label": "contiene", "color": "rgba(148, 163, 184, 0.2)"})

                    if bases:
                        for base in bases.split(","):
                            base_name = base.strip().split()[-1]
                            if base_name in symbol_name_map:
                                links.append({"source": sym_id, "target": symbol_name_map[base_name], "label": "hereda", "color": "rgba(245, 158, 11, 0.4)"})

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
                            _register_symbol(mname, sym_id)
                            links.append({"source": f_id, "target": sym_id, "label": "contiene", "color": "rgba(148, 163, 184, 0.2)"})
            except Exception:
                pass

        # Pass 2C: Extract Terraform / HCL resources
        for path, rel_file, f_id in terraform_files:
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
                file_contents[rel_file] = content
                for m in re.finditer(r'(resource|data|module|variable|output)\s+"([^"]+)"(?:\s+"([^"]+)")?', content):
                    kind = m.group(1)
                    label = m.group(3) or m.group(2)
                    sym_id = f"symbol:{rel_file}:{kind}:{label}"
                    if sym_id not in node_ids:
                        nodes.append({
                            "id": sym_id, "name": label, "kind": "resource",
                            "val": 4, "color": "#34d399", "details": f"{kind} en {rel_file}"
                        })
                        node_ids.add(sym_id)
                        _register_symbol(label, sym_id)
                        links.append({"source": f_id, "target": sym_id, "label": "contiene", "color": "rgba(148, 163, 184, 0.2)"})
            except Exception:
                pass

        # Pass 2D: Extract document references (markdown links / wikilinks)
        for path, rel_file, f_id in doc_files:
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
                file_contents[rel_file] = content
                base = str(Path(rel_file).parent)
                seen_targets: Set[str] = set()
                for target in re.findall(r"\[[^\]]*\]\(([^)\s]+)\)", content):
                    t = target.split("#")[0]
                    if not t or t.startswith(("http://", "https://", "mailto:")):
                        continue
                    norm = posixpath.normpath(str(Path(base) / t) if base != "." else t)
                    if norm.startswith("..") or norm in (".", ""):
                        continue
                    tid = f"file:{norm}"
                    if tid in node_ids and tid != f_id and tid not in seen_targets:
                        seen_targets.add(tid)
                        links.append({"source": f_id, "target": tid, "label": "referencia", "color": "rgba(16, 185, 129, 0.3)", "confidence": "EXTRACTED"})
                for wl in re.findall(r"\[\[([^\]|]+)", content):
                    wl = wl.strip()
                    if not wl:
                        continue
                    candidates = [
                        nid for nid in node_ids
                        if nid.startswith("file:") and Path(nid[5:]).name.split(".")[0] == wl
                    ]
                    for tid in candidates[:1]:
                        if tid != f_id and tid not in seen_targets:
                            seen_targets.add(tid)
                            links.append({"source": f_id, "target": tid, "label": "referencia", "color": "rgba(16, 185, 129, 0.3)", "confidence": "EXTRACTED"})
            except Exception:
                pass

        # Pass 3: Extract Python AST symbols & calls
        for path, rel_file, f_id in python_files:
            try:
                file_contents[rel_file] = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                pass
            tree_result = _tree_facts(path, rel_file)
            if tree_result is not None:
                _add_tree_symbols(tree_result, f_id)
                continue
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
                    _register_symbol(sym["name"], sym_id)
                links.append({"source": f_id, "target": sym_id, "label": "contiene", "color": "rgba(148, 163, 184, 0.2)"})

        # Pass 3B: Extract JS/TS/Java/Go/Rust symbols
        for path, rel_file, f_id, ext in other_code_files:
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
                file_contents[rel_file] = content
                tree_result = _tree_facts(path, rel_file)
                if tree_result is not None:
                    _add_tree_symbols(tree_result, f_id)
                    continue
                if ext == ".sql":
                    sql_patterns = (
                        (r'\bCREATE\s+(?:OR\s+REPLACE\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?["`\[]?([A-Za-z_][\w.]*)', "table"),
                        (r'\bCREATE\s+(?:OR\s+REPLACE\s+)?VIEW\s+["`\[]?([A-Za-z_][\w.]*)', "view"),
                        (r'\bCREATE\s+(?:OR\s+REPLACE\s+)?(?:FUNCTION|PROCEDURE)\s+["`\[]?([A-Za-z_][\w.]*)', "procedure"),
                    )
                    for pattern, kind in sql_patterns:
                        for match in re.finditer(pattern, content, re.IGNORECASE):
                            name = match.group(1).rstrip('"`]')
                            sym_id = f"symbol:{rel_file}:{kind}:{name}"
                            if sym_id not in node_ids:
                                nodes.append({"id": sym_id, "name": name, "kind": kind, "val": 4,
                                              "color": "#34d399", "details": f"{kind} SQL en {rel_file}"})
                                node_ids.add(sym_id)
                                _register_symbol(name, sym_id)
                                links.append({"source": f_id, "target": sym_id, "label": "declara",
                                              "confidence": "EXTRACTED", "file": rel_file,
                                              "line": content[:match.start()].count("\n") + 1})
                    continue
                for m in re.finditer(r"(export function|case class|local function|defmodule|defmacro|class|interface|struct|type|function|fn|def|defp|func|fun|enum|protocol|extension|trait|object|macro|module|void)\s+([A-Za-z0-9_]+)", content):
                    kind = m.group(1).replace("export ", "")
                    if kind == "void":
                        kind = "function"
                    cname = m.group(2)
                    if cname not in ("if", "for", "while", "switch", "return"):
                        sym_id = f"symbol:{rel_file}:{cname}"
                        if sym_id not in node_ids:
                            nodes.append({
                                "id": sym_id, "name": cname, "kind": kind,
                                "val": 4, "color": "#f59e0b" if kind in ("class", "interface", "struct") else "#a78bfa",
                                "details": f"{kind} en {rel_file}"
                            })
                            node_ids.add(sym_id)
                            _register_symbol(cname, sym_id)
                            links.append({"source": f_id, "target": sym_id, "label": "contiene", "color": "rgba(148, 163, 184, 0.2)"})
            except Exception:
                pass

        # Pass 4: Resolve precise tree-sitter inheritance and call evidence.
        node_by_id = {node["id"]: node for node in nodes}

        def _simple_type(value: str) -> str:
            value = re.sub(r"\b(?:ref|out|in|params)\s+", "", str(value or "")).strip()
            value = re.sub(r"[?\[\]].*", "", value)
            value = value.split("<", 1)[0]
            return value.rsplit(".", 1)[-1]

        member_types: Dict[tuple[str, str], str] = {}
        for file_members in tree_members.values():
            for member in file_members:
                container = _simple_type(member.get("container", ""))
                name = member.get("name", "")
                member_type = _simple_type(member.get("type", ""))
                if container and name and member_type:
                    member_types[(container, name)] = member_type

        def _chain_receiver_type(call: Dict[str, Any]) -> str:
            chain = call.get("receiver_chain") or []
            if not chain:
                return call.get("receiver_type", "")
            current = _simple_type(call.get("receiver_type", ""))
            first = chain[0]
            if first in ("this", "base"):
                current = _simple_type(call.get("container", ""))
            elif first[:1].isupper():
                current = _simple_type(first)
            elif not current:
                return ""
            for member_name in chain[1:]:
                next_type = member_types.get((current, member_name))
                if not next_type:
                    return ""
                current = next_type
            return current

        def _imports_for(rel_file: str) -> tuple[Set[str], Dict[str, str]]:
            namespaces: Set[str] = set()
            aliases: Dict[str, str] = {}
            for item in tree_imports.get(rel_file, []):
                text = item.get("text", "")
                match = re.search(r"\busing\s+(?:(\w+)\s*=\s*)?([A-Za-z_][A-Za-z0-9_.]*)", text)
                if match:
                    if match.group(1):
                        aliases[match.group(1)] = match.group(2)
                    else:
                        namespaces.add(match.group(2))
            return namespaces, aliases

        def _rank_candidate(target_id: str, rel_file: str, container: str = "", receiver: str = "", arity: Any = None) -> int:
            target = node_by_id.get(target_id, {})
            score = 0
            if target.get("file") == rel_file:
                score += 4
            if container and target.get("container") == container:
                score += 5
            if receiver and receiver in {target.get("container"), target.get("name")}:
                score += 12
            if arity is not None:
                required = target.get("required_parameter_count")
                maximum = target.get("parameter_count")
                if maximum == arity:
                    score += 5
                elif required is not None and maximum is not None and required <= arity <= maximum:
                    score += 3
                    if required == arity:
                        # C# overload resolution generally prefers the viable
                        # overload that does not need omitted optional values.
                        score += 2
            source_assembly = node_by_id.get(f"file:{rel_file}", {}).get("assembly")
            if source_assembly and source_assembly == target.get("assembly"):
                score += 2
            imported, aliases = _imports_for(rel_file)
            namespace = target.get("namespace", "")
            if namespace and (namespace in imported or any(namespace.startswith(item + ".") for item in imported)):
                score += 3
            if receiver and aliases.get(receiver, "").endswith("." + target.get("container", "")):
                score += 12
            return score

        for source_id, base_name, rel_file, line, evidence in pending_inheritance:
            candidates = symbol_name_ids.get(base_name, set())
            if not candidates:
                continue
            ranked = sorted((( _rank_candidate(target, rel_file), target) for target in candidates if target != source_id), reverse=True)
            if not ranked:
                continue
            best_score = ranked[0][0]
            best = [target for score, target in ranked if score == best_score]
            for target_id in best:
                target_node = node_by_id.get(target_id, {})
                links.append({
                    "source": source_id, "target": target_id,
                    "label": "implementa" if target_node.get("kind") == "interface" else "hereda",
                    "color": "rgba(245, 158, 11, 0.4)",
                    "confidence": "AMBIGUOUS" if len(best) > 1 else ("EXTRACTED" if best_score >= 2 else "INFERRED"),
                    "file": rel_file, "line": line, "evidence": evidence,
                    "resolution": {"strategy": "namespace-assembly", "score": best_score, "candidates": len(candidates)},
                })

        for rel_file, calls in tree_calls.items():
            f_id = f"file:{rel_file}"
            seen_calls = set()
            for call in calls:
                targets = symbol_name_ids.get(call["name"], set())
                if not targets:
                    continue
                is_creation = call.get("call_kind") in ("new_expression", "object_creation_expression")
                if is_creation:
                    targets = {target for target in targets if node_by_id.get(target, {}).get("is_constructor")}
                else:
                    targets = {target for target in targets if node_by_id.get(target, {}).get("kind") in ("method", "function")}
                if not targets:
                    continue
                receiver_type = _chain_receiver_type(call) or call.get("receiver_type") or call.get("receiver", "")
                known_containers = {node_by_id.get(target, {}).get("container") for target in targets}
                # A typed receiver that matches none of the project candidates
                # is normally a framework/BCL call (e.g. enum.ToString), not a
                # call to an unrelated same-named method in this repository.
                if receiver_type and receiver_type not in known_containers and call.get("receiver"):
                    continue
                caller_ids = [
                    target for target in symbol_name_ids.get(call.get("caller", ""), set())
                    if node_by_id.get(target, {}).get("file") == rel_file
                    and (not call.get("container") or node_by_id.get(target, {}).get("container") == call.get("container"))
                ]
                source_id = caller_ids[0] if len(caller_ids) == 1 else f_id
                ranked = sorted((
                    (_rank_candidate(target, rel_file, call.get("container", ""), receiver_type, call.get("argument_count")), target)
                    for target in targets if target != source_id
                ), reverse=True)
                if not ranked:
                    continue
                best_score = ranked[0][0]
                best = [target for score, target in ranked if score == best_score]
                for target_id in best:
                    call_key = (source_id, target_id, call["line"])
                    if call_key in seen_calls:
                        continue
                    seen_calls.add(call_key)
                    exact = best_score >= 6
                    links.append({
                        "source": source_id, "target": target_id, "label": "llama",
                        "color": "rgba(56, 189, 248, 0.35)",
                        "confidence": "AMBIGUOUS" if len(best) > 1 else ("EXTRACTED" if exact else "INFERRED"),
                        "file": rel_file, "line": call["line"], "evidence": call.get("evidence", ""),
                        "resolution": {
                            "strategy": "receiver-container-arity-namespace-assembly",
                            "score": best_score, "candidates": len(targets),
                            "receiver": call.get("receiver", ""), "receiver_type": receiver_type,
                            "receiver_chain": call.get("receiver_chain", []),
                            "caller": call.get("caller", ""),
                        },
                    })

        # Pass 5: Cross-symbol fallback resolution for legacy parsers.
        from .laravel_resolver import add_laravel_relations
        laravel_stats = add_laravel_relations(nodes, links, file_contents)

        keyword_noise = {
            "for", "foreach", "if", "else", "in", "is", "as", "and", "or", "not", "new", "var",
            "int", "string", "bool", "void", "set", "get", "add", "remove", "this", "base",
            "out", "ref", "return", "do", "while", "switch", "case", "class", "struct", "enum",
            "interface", "public", "private", "protected", "static", "namespace", "using",
            "select", "where", "from", "join", "group", "order", "by", "into", "default",
            "value", "object", "true", "false", "null", "nameof", "typeof", "async", "await"
        }
        removed_ids = {
            n.get("id") for n in nodes
            if n.get("id", "").startswith("symbol:") and n.get("name", "").lower() in keyword_noise
        }
        if removed_ids:
            nodes = [n for n in nodes if n.get("id") not in removed_ids]
            links = [
                l for l in links
                if l.get("source") not in removed_ids and l.get("target") not in removed_ids
            ]
        for rel_file, content in file_contents.items():
            if rel_file in tree_parsed_files:
                continue
            f_id = f"file:{rel_file}"
            for cname, sym_id in symbol_name_map.items():
                if len(cname) < 4 or cname.lower() in keyword_noise:
                    continue
                if cname in content and not sym_id.startswith(f"symbol:{rel_file}:"):
                    if re.search(r"\b" + re.escape(cname) + r"\b", content):
                        ambiguous = len(symbol_name_ids.get(cname, {sym_id})) > 1
                        links.append({
                            "source": f_id, "target": sym_id, "label": "usa",
                            "color": "rgba(56, 189, 248, 0.25)",
                            "confidence": "AMBIGUOUS" if ambiguous else "INFERRED",
                        })

        for l in links:
            if "confidence" not in l:
                l["confidence"] = "INFERRED" if l.get("label") == "usa" else "EXTRACTED"

        if cache_path:
            try:
                active = set(file_contents) | {str(p.relative_to(root_dir)) for p, _, _ in csharp_files}
                structural_cache["files"] = {
                    key: value for key, value in structural_cache.get("files", {}).items() if key in active
                }
                Path(cache_path).parent.mkdir(parents=True, exist_ok=True)
                Path(cache_path).write_text(json.dumps(structural_cache, separators=(",", ":")), encoding="utf-8")
            except OSError:
                pass

        graph = {
            "nodes": nodes,
            "links": links,
            "metadata": {
                "structural_parser": "tree-sitter+fallback" if tree_parsed_files else "builtin-fallback",
                "tree_sitter_files": len(tree_parsed_files),
                "structural_cache": bool(cache_path),
                "incremental": {
                    "reused_files": cache_hits,
                    "parsed_files": cache_misses,
                    "invalidated_files": cache_misses,
                    "cache_version": PARSER_VERSION,
                },
                "laravel_routes": laravel_stats["routes"],
                "project_evidence": collect_project_evidence(root_dir),
            },
        }
        apply_type_evidence(graph, root_dir)
        normalize_graph(graph)
        return self._enrich_graph_with_degree(graph)

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
        nodes = [{
            "id": "agent:nexus", "name": "Nexus Orchestrator", "kind": "orchestrator_agent",
            "val": 30, "color": "#a855f7", "details": "Controlador principal Harness Orchestrator / OpenClaw"
        }]
        links = []

        evi_specialists = [
            ("agent:agent-alpha-code", "Agent-Code Agent", "Subagente especialista en generación y refactor de código", "#7c3aed"),
            ("agent:agent-alpha-db", "Agent-DB Agent", "Subagente especialista en bases de datos y persistencia", "#7c3aed"),
            ("agent:agent-alpha-design", "Agent-Design Agent", "Subagente especialista en UI/UX y tokens de diseño", "#7c3aed"),
            ("agent:agent-alpha-devops", "Agent-DevOps Agent", "Subagente especialista en CI/CD y despliegue Docker", "#7c3aed"),
            ("agent:agent-alpha-qa", "Agent-QA Agent", "Subagente especialista en pruebas unitarias y calidad", "#7c3aed"),
            ("agent:agent-alpha-security", "Agent-Security Agent", "Subagente especialista en auditoría de seguridad", "#7c3aed"),
            ("agent:agent-alpha-architect", "Agent-Architect Agent", "Subagente especialista en arquitectura del sistema", "#7c3aed"),
            ("agent:agent-alpha-coord", "Agent-Coord Agent", "Subagente especialista en coordinación de tareas", "#7c3aed"),
            ("agent:agent-alpha-docs", "Agent-Docs Agent", "Subagente especialista en documentación y ADRs", "#7c3aed"),
            ("agent:agent-alpha-career", "Agent-Career Agent", "Subagente especialista en gestión de carreras y empleos", "#7c3aed"),
            ("agent:agent-alpha-research", "Agent-Research Agent", "Subagente especialista en investigación profunda", "#7c3aed"),
        ]

        for aid, aname, adetails, color in evi_specialists:
            nodes.append({
                "id": aid, "name": aname, "kind": "sub_agent",
                "val": 15, "color": color, "details": adetails
            })
            links.append({
                "source": "agent:nexus", "target": aid, "label": "delegates",
                "color": "rgba(168, 85, 247, 0.4)", "confidence": "EXTRACTED"
            })

        ext_agents = [
            ("agent:hermes", "Hermes Autonomous Agent", "Agente autónomo Hermes IC", "#06b6d4", "spawns"),
            ("agent:antigravity", "Google Antigravity CLI", "Antigravity 2.0 (agy)", "#a78bfa", "spawns"),
            ("agent:claude-code", "Claude Code CLI", "Anthropic Claude Code", "#a78bfa", "spawns"),
            ("mcp:graphtyn", "Graphtyn MCP", "Servidor Contexto AST", "#38bdf8", "queries"),
        ]

        for aid, aname, adetails, color, rel in ext_agents:
            kind = "mcp_tool" if aid.startswith("mcp") else "sub_agent"
            nodes.append({
                "id": aid, "name": aname, "kind": kind,
                "val": 12, "color": color, "details": adetails
            })
            links.append({
                "source": "agent:nexus", "target": aid, "label": rel,
                "color": "rgba(6, 182, 212, 0.4)", "confidence": "EXTRACTED"
            })

        return ASTParser()._enrich_graph_with_degree({"nodes": nodes, "links": links})
