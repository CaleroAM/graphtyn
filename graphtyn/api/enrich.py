import json
import re
import ast
import os
import subprocess
import urllib.request
from pathlib import Path

_EXT_LANG = {
    ".py": "Python", ".cs": "C#", ".php": "PHP", ".js": "JavaScript", ".ts": "TypeScript",
    ".jsx": "JSX", ".tsx": "TSX", ".java": "Java", ".go": "Go", ".rs": "Rust", ".rb": "Ruby",
    ".c": "C", ".cpp": "C++", ".h": "C/C++", ".hpp": "C++", ".kt": "Kotlin", ".kts": "Kotlin",
    ".swift": "Swift", ".dart": "Dart", ".sh": "Shell", ".bash": "Bash", ".sql": "SQL",
    ".vue": "Vue", ".svelte": "Svelte", ".md": "Markdown", ".json": "JSON",
    ".scala": "Scala", ".lua": "Lua", ".jl": "Julia", ".zig": "Zig", ".ex": "Elixir", ".exs": "Elixir",
    ".tf": "Terraform", ".tfvars": "Terraform", ".cls": "Apex", ".trigger": "Apex",
    ".rst": "reStructuredText", ".txt": "texto plano",
    ".pdf": "documento PDF", ".docx": "documento Word", ".xlsx": "hoja de cálculo Excel",
    ".unity": "Unity asset", ".prefab": "Unity prefab", ".asset": "Unity asset",
    ".asmdef": "Unity assembly definition", ".shader": "Shader", ".uxml": "Unity UI Toolkit",
}

_DOC_EXTS = (".pdf", ".docx", ".xlsx", ".xlsm")

_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")

_MEDIA_EXTS = (".mp3", ".wav", ".m4a", ".ogg", ".flac", ".opus", ".aac", ".mp4", ".mov", ".mkv", ".webm", ".avi", ".mpeg")

def _vision_ask(host: str, model: str, image_path: Path, timeout: int = 60) -> str:
    try:
        import base64
        try:
            from PIL import Image
            import io
            im = Image.open(image_path)
            im.thumbnail((512, 512))
            buf = io.BytesIO()
            im.convert("RGB").save(buf, format="JPEG", quality=80)
            b64 = base64.b64encode(buf.getvalue()).decode()
        except Exception:
            b64 = base64.b64encode(image_path.read_bytes()).decode()
    except Exception:
        return ""
    prompt = ("Describe en UNA frase corta y densa en espanol: QUE muestra esta imagen "
              "y PARA QUE sirve como artefacto tecnico en un proyecto de software. "
              "Responde SOLO con la frase, sin etiquetas, sin prefijos, sin 'Esta imagen'.")
    # VL models need more tokens because they may use internal reasoning before answering
    num_predict = 500 if "vl" in model.lower() else 150
    try:
        req = urllib.request.Request(f"{host}/api/chat", data=json.dumps({
            "model": model,
            "messages": [{"role": "user", "content": prompt, "images": [b64]}],
            "stream": False, "think": False,
            "options": {"temperature": 0.2, "num_predict": num_predict}
        }).encode('utf-8'), headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            res = json.loads(resp.read().decode('utf-8'))
            msg = res.get("message", {}) or {}
            content = (msg.get("content") or "").strip()
            # Strip <think>...</think> blocks (qwen3-vl reasoning)
            content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
            if not content:
                return ""
            # Trim to first sentence if too long
            if len(content) > 180:
                idx = content.find(". ")
                if idx > 30:
                    content = content[:idx + 1]
                else:
                    content = content[:180]
            return content
    except Exception as e:
        print(f"[AI Enrich] Vision request failed for {image_path.name} with '{model}': {e}")
def _llm_ask(host: str, model: str, prompt: str, timeout: int = 45, temperature: float = 0.3) -> str:
    try:
        req = urllib.request.Request(f"{host}/api/generate", data=json.dumps({
            "model": model, "prompt": prompt, "stream": False,
            "options": {"temperature": temperature, "num_predict": 200}
        }).encode('utf-8'), headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            res = json.loads(resp.read().decode('utf-8'))
            answer = res.get("response", "").strip()
            # Strip <think>...</think> blocks
            answer = re.sub(r"<think>.*?</think>", "", answer, flags=re.DOTALL).strip()
            return answer
    except Exception as e:
        print(f"[AI Enrich] LLM request failed: {e}")
        return ""

_FEWSHOT_SYM = (
    "EJEMPLO DE ESTILO (solo formato; el contenido del ejemplo NO tiene relacion con tu codigo): "
    "para una clase de persistencia seria: \"Guarda y recupera los registros usando una base local, con estrategia segun permisos.\"\n"
)

def _role_hint_and_fix(full_text: str, answer: str) -> tuple:
    hints = ""
    role_label = None
    if "argparse" in full_text and ("add_parser" in full_text or "ArgumentParser" in full_text):
        hints += " PISTA: este archivo es una interfaz de linea de comandos (CLI) con argparse y subcomandos."
        role_label = "CLI"
    if "FastAPI" in full_text or "@app." in full_text or "uvicorn" in full_text:
        hints += " PISTA: este archivo define un servidor web/API con FastAPI (endpoints HTTP)."
        role_label = "API FastAPI"
    if "pytest" in full_text or "def test_" in full_text:
        hints += " PISTA: este archivo contiene pruebas unitarias automatizadas."
        role_label = "pruebas"
    if "sqlite3" in full_text:
        hints += " PISTA: este archivo usa SQLite como base de datos local."
    if 'if __name__ == "__main__"' in full_text:
        hints += " PISTA: contiene el punto de entrada principal (__main__)."
    fix = ""
    if role_label == "CLI" and not re.search(r"cli|interfaz de linea|comandos|argparse", answer, re.I):
        fix = "CLI que "
    elif role_label == "API FastAPI" and not re.search(r"fastapi|servidor|api|web", answer, re.I):
        fix = "API FastAPI que "
    return hints, fix

def _node_neighbors(graph: dict, node_id: str, limit: int = 6) -> list:
    nbs = set()
    for l in graph.get("links", []):
        s = l.get("source")
        t = l.get("target")
        if s == node_id:
            nbs.add(t)
        elif t == node_id:
            nbs.add(s)
    names = []
    for n in graph.get("nodes", []):
        if n.get("id") in nbs and n.get("id") != node_id:
            names.append(n.get("name", n.get("id", "")))
        if len(names) >= limit:
            break
    return names

def _detect_changed_files(root: Path):
    try:
        res = subprocess.run(
            ["git", "status", "--porcelain", "-z"],
            cwd=root, capture_output=True, text=True, timeout=15
        )
        if res.returncode != 0:
            return None
        changed = set()
        for entry in res.stdout.split("\0"):
            if len(entry) > 3:
                path = entry[3:].strip()
                if path.startswith(".graphtyn/"):
                    continue
                changed.add(path)
        return changed
    except Exception:
        return None

def _maybe_compact(host: str, model: str, ans: str) -> str:
    if os.environ.get("GRAPHTYN_COMPACT", "0") != "1":
        return ans
    if len(ans) <= 140:
        return ans
    comp = _llm_ask(host, model,
                    f"Comprime el siguiente texto a MAXIMO 100 caracteres, en espanol, conservando el significado tecnico:\n{ans}",
                    temperature=0.2)
    if comp:
        ans = _clean_answer(comp)
    if len(ans) > 140:
        cut = ans[:140]
        idx = cut.rfind(". ")
        if idx > 60:
            cut = cut[:idx + 1]
        ans = cut
    return ans

def _clean_answer(text: str) -> str:
    text = re.sub(r"\s+", " ", text.strip())
    text = re.sub(r"^[\"'\u201c\u201d]+|[\"'\u201c\u201d]+$", "", text).strip()
    # Strip markdown bolding / headers
    text = re.sub(r"^\s*#+\s*", "", text)
    text = re.sub(r"^\s*[-*]\s*", "", text)
    text = re.sub(
        r"^(?:esta|este|la|el)?\s*(?:la\s+)?(?:imagen|captura|textura|diagrama|grafico|gráfico)\s+"
        r"(?:muestra|representa|es|contiene|presenta|describe)\s*",
        "", text, flags=re.I)
    text = re.sub(
        r"^(?:esta|este|la|el)?\s*(?:la\s+)?(?:funcion|función|clase|metodo|método|archivo|modulo|módulo)\s+"
        r"(?:`[^`]+`|'[^']+'|\S+)\s*(?:en\s+\S+)?\s*[:\-]?\s*",
        "", text, flags=re.I)
    text = re.sub(
        r"^(?:este|esta|el|la|un|una|se trata de un|se trata de una)\s+"
        r"(?:archivo|funcion|función|clase|metodo|método|modulo|módulo)\s+"
        r"(?:python|c#|php|javascript|typescript|java|go|rust|ruby|markdown|json|shell|bash|sql|shader|unity|swift|dart|kotlin|svelte|vue)\s*",
        "", text, flags=re.I)
    text = re.sub(r"^(?:en resumen|en conclusion|en definitiva)[,:\s]+", "", text, flags=re.I)
    text = text[:1].upper() + text[1:] if text else text
    return text.strip()

def _extract_symbol_source(root_dir: Path, rel_path: str, sym_name: str, kind: str = None) -> str:
    fpath = root_dir / rel_path
    try:
        content = fpath.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""
    lines = content.splitlines()
    if not lines:
        return ""
    if fpath.suffix.lower() == ".py":
        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == sym_name:
                    return "\n".join(lines[node.lineno - 1:node.end_lineno])[:2000]
        except Exception:
            return ""
        return ""
    kw_noise = {
        "for", "foreach", "if", "else", "in", "is", "as", "and", "or", "not", "new", "var",
        "int", "string", "bool", "void", "set", "get", "add", "remove", "this", "base",
        "out", "ref", "return", "do", "while", "switch", "case", "class", "struct", "enum",
        "interface", "public", "private", "protected", "static", "namespace", "using",
        "select", "where", "from", "join", "group", "order", "by", "into", "default",
        "value", "object", "true", "false", "null", "nameof", "typeof", "async", "await"
    }
    if sym_name.lower() in kw_noise:
        return ""
    m = None
    if fpath.suffix.lower() in (".cs", ".cpp", ".c", ".h", ".hpp", ".java", ".go", ".rs"):
        method_pat = re.compile(
            r"^\s*(?:(?:public|private|protected|internal|static|virtual|override|abstract|async|sealed|partial|extern|final)\s+)+"
            r"(?:[A-Za-z_][\w.<>\[\]?]*\s+)?"
            + re.escape(sym_name) + r"\s*\(",
            re.M)
        m = method_pat.search(content)
    if not m:
        kw_pat = re.compile(
            r"^\s*(?:(?:export|default|public|private|protected|static|abstract|async|sealed|partial|internal|virtual|override|final)\s+)*"
            r"(?:class|interface|struct|enum|def|function|fn|func|fun|protocol|extension|trait)\s+"
            + re.escape(sym_name) + r"\b", re.M)
        m = kw_pat.search(content)
    if not m:
        return ""
    start = content[:m.start()].count("\n")
    depth = 0
    end = start
    for i in range(start, min(start + 60, len(lines))):
        depth += lines[i].count("{") - lines[i].count("}")
        end = i
        if i > start and depth <= 0:
            break
    return "\n".join(lines[start:end + 1])[:2000]
    m = kw_pat.search(content)
    if not m:
        return ""
    start = content[:m.start()].count("\n")
    depth = 0
    end = start
    for i in range(start, min(start + 60, len(lines))):
        depth += lines[i].count("{") - lines[i].count("}")
        end = i
        if i > start and depth <= 0:
            break
    return "\n".join(lines[start:end + 1])[:2000]

def _enrich_with_ai(graph: dict, engine: str, root_dir: Path = None, prev: dict = None, changed: set = None, model_override: str = None, vision_model_override: str = None):
    ai_calls = 0
    if not root_dir:
        return graph
    if "metadata" not in graph:
        graph["metadata"] = {}

    prev_files = {n.get("id"): n.get("details", "") for n in (prev or {}).get("nodes", []) if n.get("id", "").startswith("file:")}
    prev_syms = {n.get("id"): n.get("details", "") for n in (prev or {}).get("nodes", []) if n.get("id", "").startswith("symbol:")}
    prev_meta = (prev or {}).get("metadata", {}) or {}

    # 1. Fallback & preserve previous cached details for all nodes (images, docs, files, symbols, modules)
    for n in graph.get("nodes", []):
        nid = n.get("id", "")
        if n.get("kind") in ("module", "dir") and not n.get("details"):
            n["details"] = f"Carpeta de módulos: {n.get('name')}"
        elif nid.startswith("file:") and nid in prev_files and prev_files[nid]:
            rel_path = nid.replace("file:", "")
            prev_desc = prev_files[nid]
            is_enriched = bool(
                prev_desc and
                prev_desc != rel_path and
                not prev_desc.startswith("Imagen en ") and
                not prev_desc.startswith("Audio/Video en ")
            )
            if is_enriched and (changed is None or rel_path not in changed):
                n["details"] = prev_desc
        elif nid.startswith("symbol:") and nid in prev_syms and prev_syms[nid]:
            parts = nid.split(":")
            if len(parts) >= 2:
                rel_path = parts[1]
                prev_desc = prev_syms[nid]
                is_sym_enriched = bool(prev_desc and not prev_desc.startswith("Función/Método en "))
                if (changed is not None and rel_path not in changed and prev_desc) or (changed is None and is_sym_enriched):
                    n["details"] = prev_desc

    if engine == "ast_pure":
        # A structural-only refresh must not discard semantic context already
        # generated by a previous local or cloud reindex.
        for key in ("ai_summary", "ai_model"):
            if prev_meta.get(key) and not graph["metadata"].get(key):
                graph["metadata"][key] = prev_meta[key]
        return graph

    # Filter code file & class nodes for individual code snippet analysis
    top_code_nodes = [
        n for n in graph.get("nodes", [])
        if n.get("kind") in ("file", "class", "function", "method") and n.get("id", "").startswith("file:")
    ]
    top_code_nodes = sorted(top_code_nodes, key=lambda n: n.get("degree", 0), reverse=True)[:6]

    if engine == "ast_local_llm":
        ollama_hosts = [
            os.environ.get("OLLAMA_HOST"),
            "http://localhost:11434",
            "http://127.0.0.1:11434",
            "http://172.17.0.1:11434",
            "http://host.docker.internal:11434"
        ]
        connected_host = None
        available_models = []
        forced_model = model_override or os.environ.get("OLLAMA_MODEL")
        model_name = forced_model or "llama3.2:latest"

        for host in ollama_hosts:
            if not host: continue
            try:
                req_m = urllib.request.Request(f"{host}/api/tags")
                with urllib.request.urlopen(req_m, timeout=4) as r:
                    m_data = json.loads(r.read().decode('utf-8'))
                    models = [m["name"] for m in m_data.get("models", [])]
                    available_models = models
                    if forced_model:
                        if any(m == forced_model or m.split(":")[0] == forced_model.split(":")[0] for m in models):
                            model_name = forced_model
                        elif models:
                            print(f"[AI Enrich] OLLAMA_MODEL='{forced_model}' no está en Ollama; usando '{models[0]}'. Disponibles: {models}")
                            model_name = models[0]
                    else:
                        small = [m for m in models if "3b" in m.lower() or "3.2" in m.lower()]
                        if small:
                            model_name = small[0]
                        else:
                            fast_models = [m for m in models if "coder" in m.lower() or "llama" in m.lower()]
                            model_name = fast_models[0] if fast_models else (models[0] if models else model_name)
                connected_host = host
                break
            except Exception:
                pass

        if connected_host:
            print(f"[AI Enrich] Connecting to Ollama at {connected_host} using model '{model_name}'...")
            # Pre-warm model load (60s timeout to allow initial cold load)
            try:
                req_warm = urllib.request.Request(f"{connected_host}/api/generate", data=json.dumps({
                    "model": model_name, "prompt": "hola", "stream": False
                }).encode('utf-8'), headers={'Content-Type': 'application/json'})
                with urllib.request.urlopen(req_warm, timeout=60) as r:
                    pass
            except Exception:
                pass

            # 2. Semantic summaries for every code file (language-aware; incremental reuses unchanged)
            all_code_nodes = [n for n in graph.get("nodes", []) if n.get("kind") not in ("module", "dir")]
            file_limit = int(os.environ.get("GRAPHTYN_FILE_LIMIT", "0"))
            file_nodes = sorted(
                [n for n in all_code_nodes if n.get("id", "").startswith("file:")],
                key=lambda n: n.get("degree", 0), reverse=True
            )
            if file_limit > 0 and changed is None:
                file_nodes = file_nodes[:file_limit]
            image_limit = int(os.environ.get("GRAPHTYN_IMAGE_LIMIT", "0"))
            image_count = 0
            media_limit = int(os.environ.get("GRAPHTYN_MEDIA_LIMIT", "0"))
            media_count = 0
            for n in file_nodes:
                nid = n.get("id", "")
                rel_path = nid.replace("file:", "")
                prev_desc = prev_files.get(nid, "")
                is_enriched = bool(
                    prev_desc and
                    prev_desc != rel_path and
                    not prev_desc.startswith("Imagen en ") and
                    not prev_desc.startswith("Audio/Video en ")
                )
                if is_enriched and (changed is None or rel_path not in changed):
                    n["details"] = prev_desc
                    continue
                file_path = root_dir / rel_path
                if not file_path.is_file():
                    continue
                lang = _EXT_LANG.get(file_path.suffix.lower(), "código")
                if file_path.suffix.lower() in _IMAGE_EXTS:
                    image_count += 1
                    if image_limit > 0 and image_count > image_limit:
                        n["details"] = f"Imagen en {rel_path}"
                        continue
                    # Vision model selection: user override > env var > auto-detect
                    vision_model = vision_model_override or os.environ.get("GRAPHTYN_VISION_MODEL")
                    vision_fallback = None
                    if not vision_model:
                        # Auto-detect best available vision model
                        _VISION_PRIORITY = ("minicpm-v4.6:1b", "qwen3-vl:2b", "qwen2.5-vl", "llava", "bakllava", "moondream", "llama3.2-vision")
                        for vm in _VISION_PRIORITY:
                            if any(vm in m.lower() for m in available_models):
                                vision_model = next(m for m in available_models if vm in m.lower())
                                break
                        if not vision_model:
                            vision_model = "minicpm-v4.6:1b" if "minicpm-v4.6:1b" in available_models else "qwen3-vl:2b"
                    else:
                        # Build fallback: pick next available vision model different from primary
                        _VISION_PRIORITY = ("minicpm-v4.6:1b", "qwen3-vl:2b", "qwen2.5-vl", "llava", "bakllava", "moondream")
                        for vm in _VISION_PRIORITY:
                            if any(vm in m.lower() for m in available_models):
                                candidate = next(m for m in available_models if vm in m.lower())
                                if candidate != vision_model:
                                    vision_fallback = candidate
                                    break
                    ans = _vision_ask(connected_host, vision_model, file_path)
                    ai_calls += 1
                    if not ans and vision_fallback:
                        print(f"[AI Enrich] Vision primary '{vision_model}' failed for {rel_path}, trying fallback '{vision_fallback}'...")
                        ans = _vision_ask(connected_host, vision_fallback, file_path)
                        ai_calls += 1
                    if ans:
                        n["details"] = f"{_clean_answer(ans)} ({rel_path})"
                    else:
                        n["details"] = f"Imagen en {rel_path}"
                    continue
                if file_path.suffix.lower() in _MEDIA_EXTS:
                    media_count += 1
                    if media_limit > 0 and media_count > media_limit:
                        n["details"] = f"Audio/Video en {rel_path}"
                        continue
                    from ..core.docreader import transcribe_media
                    whisper_model = os.environ.get("GRAPHTYN_WHISPER_MODEL", "small")
                    transcript = transcribe_media(file_path, model_size=whisper_model)
                    if transcript:
                        ans = _llm_ask(connected_host, model_name,
                                       f"En UNA sola frase corta y densa en espanol: QUE trata este audio/video y PARA QUE sirve como unidad del sistema. "
                                       f"Responde SOLO con la frase.\n\nTranscripcion:\n{transcript[:1600]}",
                                       temperature=0.2)
                        ai_calls += 1
                        n["details"] = f"{_clean_answer(ans) if ans else transcript[:200]} ({rel_path})"
                    else:
                        n["details"] = f"Audio/Video en {rel_path}"
                    continue
                try:
                    if file_path.suffix.lower() in _DOC_EXTS:
                        from ..core.docreader import extract_document_text
                        full_text = extract_document_text(file_path)
                        if not full_text:
                            continue
                    else:
                        full_text = file_path.read_text(encoding="utf-8", errors="ignore")
                    if len(full_text) > 1600:
                        code_snippet = full_text[:1300] + "\n... [recorte] ...\n" + full_text[-300:]
                    else:
                        code_snippet = full_text[:1600]
                except Exception:
                    continue
                hints, _ = _role_hint_and_fix(full_text, "")
                prompt = (f"Eres un ingeniero senior. "
                          f"Analiza el codigo REAL de abajo. "
                          f"En UNA sola frase corta y densa en espanol: QUE hace este archivo {lang} y PARA QUE sirve como unidad del sistema.{hints} "
                          f"Usa vocabulario tecnico preciso. Responde SOLO con la frase, sin etiquetas, sin 'Este archivo', sin repetir el nombre.\n\n{code_snippet}")
                ans = _llm_ask(connected_host, model_name, prompt, temperature=0.2)
                ai_calls += 1
                if ans:
                    hints2, fix2 = _role_hint_and_fix(full_text, ans)
                    ans = fix2 + ans
                    n["details"] = f"{_maybe_compact(connected_host, model_name, _clean_answer(ans))} ({rel_path})"

            # 3. Semantic descriptions for symbol nodes (functions/classes/methods)
            symbol_limit = int(os.environ.get("GRAPHTYN_SYMBOL_LIMIT", "0"))
            symbol_nodes = sorted(
                [n for n in all_code_nodes if n.get("id", "").startswith("symbol:")],
                key=lambda n: n.get("degree", 0), reverse=True
            )
            if symbol_limit > 0:
                symbol_nodes = symbol_nodes[:symbol_limit]
            for n in symbol_nodes:
                parts = n.get("id", "").split(":")
                if len(parts) < 3:
                    continue
                rel_path = parts[1]
                sym_name = parts[2]
                if sym_name.startswith("__"):
                    continue
                nid = n.get("id", "")
                prev_desc = prev_syms.get(nid, "")
                is_sym_enriched = bool(
                    prev_desc and
                    " " in prev_desc and
                    not prev_desc.startswith("Función/Método en ") and
                    not prev_desc.startswith("Método en ") and
                    not prev_desc.startswith("Clase en ") and
                    not prev_desc.startswith("Función en ") and
                    not prev_desc.startswith("Enum en ") and
                    not prev_desc.startswith("Struct en ") and
                    not prev_desc.startswith("Símbolo en ") and
                    prev_desc != f"{rel_path}:{sym_name}" and
                    prev_desc != sym_name and
                    not prev_desc.startswith(rel_path) and
                    not (prev_desc.count(".") >= 2 and " " not in prev_desc)
                )
                if is_sym_enriched and (changed is None or rel_path not in changed):
                    n["details"] = prev_desc
                    continue
                sym_kind = n.get("kind", "símbolo")
                actual_sym_name = sym_name.split(".")[-1]
                snippet = _extract_symbol_source(root_dir, rel_path, actual_sym_name, kind=sym_kind)
                if not snippet:
                    continue
                fctx = ""
                try:
                    fcontent = (root_dir / rel_path).read_text(encoding="utf-8", errors="ignore")
                    fctx = "\n".join([ln for ln in fcontent.splitlines()[:12] if ln.strip()][:6])[:400]
                except Exception:
                    pass
                neigh = _node_neighbors(graph, n.get("id", ""), 6)
                neigh_txt = ", ".join(neigh) if neigh else "ningun vecino conocido"
                prompt = (f"Eres un ingeniero senior. {_FEWSHOT_SYM}"
                          f"AHORA analiza el codigo REAL de abajo y describe SOLO ese codigo (no el ejemplo). "
                          f"El {sym_kind} '{actual_sym_name}' esta definido en {rel_path}.\n"
                          f"Contexto del archivo (primeras lineas):\n{fctx or 'sin contexto disponible'}\n"
                          f"En el grafo del proyecto se relaciona con: {neigh_txt}.\n"
                          f"Codigo del {sym_kind}:\n{snippet}\n\n"
                          f"En UNA sola frase corta y densa en espanol: QUE hace y PARA QUE sirve dentro del sistema. "
                          f"Responde SOLO con la frase, sin 'La funcion', 'El metodo', 'La clase' ni repetir el nombre '{actual_sym_name}' ni la ruta.")
                ans = _llm_ask(connected_host, model_name, prompt, temperature=0.2)
                ai_calls += 1
                if ans:
                    n["details"] = f"{_maybe_compact(connected_host, model_name, _clean_answer(ans))} ({rel_path}:{actual_sym_name})"

            # 4. Global architecture summary grounded in real enriched context
            if changed is not None and not changed and prev_meta.get("ai_summary"):
                graph["metadata"]["ai_summary"] = prev_meta["ai_summary"]
                graph["metadata"]["ai_model"] = prev_meta.get("ai_model", model_name)
            else:
                enriched = sorted(
                    [n for n in graph.get("nodes", []) if n.get("details") and n.get("kind") not in ("module", "dir")],
                    key=lambda n: n.get("degree", 0), reverse=True
                )[:10]
                components = "; ".join(f"{n['name']} ({n.get('details', '')[:90]})" for n in enriched)
                prompt = ("Resume en 1 sola frase corta en espanol el proposito general de un proyecto de software "
                          f"cuyos componentes principales son: {components}")
                summary = _llm_ask(connected_host, model_name, prompt, timeout=60)
                ai_calls += 1
                if summary:
                    graph["metadata"]["ai_summary"] = _clean_answer(summary)
                graph["metadata"]["ai_model"] = model_name

    elif engine == "ast_cloud":
        gemini_key = os.environ.get("GEMINI_API_KEY")
        if gemini_key:
            try:
                top_names = [n['name'] for n in graph.get("nodes", [])[:10]]
                g_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={gemini_key}"
                req = urllib.request.Request(g_url, data=json.dumps({
                    "contents": [{"parts": [{"text": f"Resume en 1 frase la arquitectura de: {top_names}"}]}]
                }).encode('utf-8'), headers={'Content-Type': 'application/json'})
                with urllib.request.urlopen(req, timeout=5) as resp:
                    res = json.loads(resp.read().decode('utf-8'))
                    text = res.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                    if text: graph["metadata"]["ai_summary"] = text.strip()
            except Exception as e:
                graph["metadata"]["ai_note"] = f"Gemini API Error ({e})"

    graph.setdefault("metadata", {})["local_ai_calls"] = ai_calls
    graph["metadata"]["ai_policy"] = {
        "role": "selective_enrichment_only",
        "structural_relations": "deterministic_parser",
        "eligible_files": "new_or_modified_when_incremental",
        "paid_provider_tokens": 0 if engine != "ast_cloud" else None,
    }
    return graph
