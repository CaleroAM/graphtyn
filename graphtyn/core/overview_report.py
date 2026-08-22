"""Auditable project overview and persistent Graphtyn report generation."""

from __future__ import annotations

from collections import Counter
import json
import re
from pathlib import Path
from typing import Any


def _safe_text(root: Path, relative: str, limit: int = 65536) -> str:
    path = (root / relative).resolve()
    try:
        path.relative_to(root.resolve())
        return path.read_text(encoding="utf-8", errors="ignore")[:limit]
    except (OSError, ValueError):
        return ""


def _readme_purpose(text: str) -> str:
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    paragraphs = re.split(r"\n\s*\n", text)
    for paragraph in paragraphs:
        if "img.shields.io" in paragraph or paragraph.count("http") >= 2:
            continue
        clean = re.sub(r"!\[[^]]*\]\([^)]*\)|<[^>]+>|\[[^]]+\]\([^)]*\)", "", paragraph)
        clean = re.sub(r"^\s*[#>*-]+\s*", "", clean, flags=re.M)
        clean = " ".join(clean.split()).strip(" *_`")
        if len(clean) >= 45 and not clean.lower().startswith(("build status", "license", "table of contents")):
            return clean[:600]
    return ""


def collect_project_evidence(root: Path) -> dict[str, Any]:
    """Read only high-value docs/manifests once per structural scan."""
    root = Path(root).resolve()
    readme = next((path for name in ("README.md", "README.rst", "README.txt", "README")
                   if (path := root / name).is_file()), None)
    documentation = [readme.name] if readme else []
    for name in ("ARCHITECTURE.md", "docs/architecture.md", "docs/ARCHITECTURE.md"):
        if (root / name).is_file():
            documentation.append(name)
    manifest_names = ("pyproject.toml", "package.json", "composer.json", "Cargo.toml", "go.mod", "pom.xml")
    manifests = [name for name in manifest_names if (root / name).is_file()]
    frameworks: set[str] = set()
    package_text = _safe_text(root, "package.json")
    if package_text:
        try:
            package = json.loads(package_text)
            dependencies = {**(package.get("dependencies") or {}), **(package.get("devDependencies") or {})}
            mapping = {"react": "React", "vue": "Vue", "next": "Next.js", "@angular/core": "Angular",
                       "express": "Express", "@nestjs/core": "NestJS", "@inertiajs/react": "Inertia.js",
                       "vite": "Vite", "typescript": "TypeScript"}
            frameworks.update(label for key, label in mapping.items() if key in dependencies)
        except (ValueError, TypeError):
            pass
    composer_text = _safe_text(root, "composer.json")
    if "laravel/framework" in composer_text:
        frameworks.add("Laravel")
    if "inertiajs/inertia-laravel" in composer_text:
        frameworks.add("Inertia.js")
    pyproject = _safe_text(root, "pyproject.toml").lower()
    for needle, label in (("fastapi", "FastAPI"), ("django", "Django"), ("flask", "Flask"),
                          ("tree-sitter", "Tree-sitter"), ("uvicorn", "Uvicorn"), ("pytest", "pytest")):
        if needle in pyproject:
            frameworks.add(label)
    return {
        "purpose": _readme_purpose(_safe_text(root, readme.name)) if readme else "",
        "purpose_source": readme.name if readme else None,
        "documentation": documentation,
        "manifests": manifests,
        "frameworks": sorted(frameworks),
    }


def derive_architecture(graph: dict, profile: dict) -> dict[str, Any]:
    subsystems = [str(item) for item in profile.get("subsystems", [])[:8]]
    lines = ["flowchart TD", "  ROOT[Project]"]
    aliases: dict[str, str] = {}
    for index, subsystem in enumerate(subsystems):
        safe = re.sub(r"[^A-Za-z0-9_ ]", "", subsystem) or f"Subsystem {index + 1}"
        lines.append(f"  ROOT --> S{index}[{safe}]")
        aliases[subsystem.lower()] = f"S{index}"
    nodes = {node.get("id"): node for node in graph.get("nodes", [])}

    def subsystem(node: dict) -> str | None:
        path = str(node.get("file") or node.get("details") or "").replace("\\", "/")
        path = re.sub(r"^(?:Carpeta|Folder):\s*", "", path, flags=re.I)
        parts = [part for part in path.split("/") if part]
        if not parts:
            return None
        for part in reversed(parts[:-1] if "." in parts[-1] else parts):
            if part.lower() in aliases:
                return part.lower()
        candidate = parts[1] if parts[0].lower() in ("src", "app", "graphtyn", "resources") and len(parts) > 1 else parts[0]
        return candidate.lower()

    crossings: Counter = Counter()
    for link in graph.get("links", []):
        if str(link.get("confidence") or "").upper() != "EXTRACTED":
            continue
        source = subsystem(nodes.get(link.get("source"), {}))
        target = subsystem(nodes.get(link.get("target"), {}))
        if source and target and source != target and source in aliases and target in aliases:
            crossings[(source, target)] += 1
    dependencies = []
    for (source, target), count in crossings.most_common(8):
        lines.append(f"  {aliases[source]} -->|{count}| {aliases[target]}")
        dependencies.append({"source": source, "target": target, "relations": count})
    return {"format": "mermaid", "diagram": "\n".join(lines), "subsystems": subsystems,
            "dependencies": dependencies}


def derive_flows(graph: dict, limit: int = 6) -> list[dict[str, Any]]:
    nodes = {node.get("id"): node for node in graph.get("nodes", [])}
    priority = {"invoca ruta": 0, "despacha": 1, "llama": 2, "valida con": 3,
                "crea": 4, "despacha evento": 5, "implementa": 6, "hereda": 7}
    candidates = [link for link in graph.get("links", []) if link.get("label") in priority]
    candidates.sort(key=lambda link: (priority[link.get("label")],
                                      0 if str(link.get("confidence") or "").upper() == "EXTRACTED" else 1,
                                      -int(nodes.get(link.get("source"), {}).get("degree") or 0)))
    flows = []
    source_counts: Counter = Counter()
    relation_counts: Counter = Counter()
    relation_cap = 1 if len({link.get("label") for link in candidates}) >= 3 else 3
    seen: set[tuple[str, str, str]] = set()
    for link in candidates:
        source, target = nodes.get(link.get("source")), nodes.get(link.get("target"))
        if not source or not target:
            continue
        source_path = str(source.get("file") or link.get("file") or "").replace("\\", "/")
        if re.search(r"(?:^|/)tests?(?:/|$)", source_path, re.I):
            continue
        key = (str(source.get("name")), str(link.get("label")), str(target.get("name")))
        if key in seen or source_counts[key[0]] >= 2 or relation_counts[key[1]] >= relation_cap:
            continue
        seen.add(key)
        source_counts[key[0]] += 1
        relation_counts[key[1]] += 1
        flows.append({"source": source.get("name"), "relation": link.get("label"),
                      "target": target.get("name"), "confidence": link.get("confidence", "EXTRACTED"),
                      "evidence": f"{link.get('file')}:{link.get('line')}" if link.get("file") else None})
        if len(flows) >= limit:
            break
    return flows


def derive_risks(graph: dict, profile: dict) -> list[dict[str, Any]]:
    links, nodes = graph.get("links", []), graph.get("nodes", [])
    confidence = Counter(str(link.get("confidence") or "UNKNOWN").upper() for link in links)
    risks = []
    if confidence["AMBIGUOUS"]:
        ambiguous_by_label = Counter(str(link.get("label") or "unknown") for link in links
                                     if str(link.get("confidence") or "").upper() == "AMBIGUOUS")
        risks.append({"level": "medium", "signal": "ambiguous_relations", "count": confidence["AMBIGUOUS"],
                      "by_relation": dict(ambiguous_by_label.most_common(6)),
                      "note": "Requieren verificación; no prueban un defecto."})
    if confidence["UNRESOLVED"]:
        risks.append({"level": "medium", "signal": "unresolved_relations", "count": confidence["UNRESOLVED"]})
    hotspot_candidates = sorted((node for node in nodes
                                 if node.get("kind") in ("class", "interface", "struct", "function", "method", "route")
                                 and int(node.get("degree") or 0) >= 20 and len(str(node.get("name") or "")) >= 3),
                                key=lambda node: -int(node.get("degree") or 0))
    hotspots, hotspot_names = [], set()
    for node in hotspot_candidates:
        name = str(node.get("name") or "").lower()
        if name not in hotspot_names:
            hotspots.append(node)
            hotspot_names.add(name)
        if len(hotspots) >= 5:
            break
    if hotspots:
        risks.append({"level": "review", "signal": "high_connectivity_hotspots",
                      "symbols": [node.get("name") for node in hotspots],
                      "note": "Alta conectividad implica mayor radio potencial, no deuda confirmada."})
    if not profile.get("documentation"):
        risks.append({"level": "low", "signal": "missing_architecture_documentation"})
    if not any(re.search(r"test", str(node.get("file") or ""), re.I) for node in nodes):
        risks.append({"level": "medium", "signal": "no_indexed_tests"})
    route_ids = {node.get("id") for node in nodes if node.get("kind") == "route"}
    dispatched = {link.get("source") for link in links if link.get("label") == "despacha"}
    if route_ids - dispatched:
        risks.append({"level": "review", "signal": "routes_without_resolved_controller",
                      "count": len(route_ids - dispatched),
                      "note": "Puede incluir closures o rutas deliberadamente no controladas."})
    return risks


def enrich_overview(graph: dict, result: dict) -> dict:
    profile = result.setdefault("project_profile", {})
    evidence = (graph.get("metadata") or {}).get("project_evidence") or {}
    for key in ("purpose", "purpose_source", "frameworks"):
        if evidence.get(key):
            profile[key] = evidence[key]
    for key in ("documentation", "manifests"):
        profile[key] = list(dict.fromkeys((evidence.get(key) or []) + (profile.get(key) or [])))
    profile["read_first"] = list(dict.fromkeys(profile.get("documentation", [])[:2] + profile.get("manifests", [])[:3]))
    result["architecture"] = derive_architecture(graph, profile)
    result["representative_flows"] = derive_flows(graph)
    result["risk_signals"] = derive_risks(graph, profile)
    observed = sum(bool(profile.get(key)) for key in ("purpose", "technologies", "frameworks", "entry_points", "subsystems", "key_symbols"))
    result["overview_quality"] = {
        "observable_coverage": round(observed / 6, 4),
        "basis": "presence of purpose, technologies, frameworks, entry points, subsystems and key symbols; not semantic accuracy",
    }
    return result


def render_report(root: Path, graph: dict, graphify_report: Path | None = None) -> tuple[str, dict]:
    from .change_analyst import query_intent

    metadata = graph.setdefault("metadata", {})
    if not metadata.get("project_evidence"):
        metadata["project_evidence"] = collect_project_evidence(Path(root))
    result = query_intent(graph, "Explain this repository purpose and architecture", "overview", 12)
    profile = result["project_profile"]
    lines = [f"# GRAPHTYN REPORT — {Path(root).name}", "", "## Purpose",
             profile.get("purpose") or "Purpose not confirmed; inspect the recommended documentation.", "",
             "## Technology profile",
             f"- Languages: {', '.join(profile.get('technologies') or []) or 'Not detected'}",
             f"- Frameworks/tools: {', '.join(profile.get('frameworks') or []) or 'Not detected'}",
             f"- Manifests: {', '.join(profile.get('manifests') or []) or 'None indexed'}", "",
             "## Entry points"]
    lines.extend(f"- `{item}`" for item in profile.get("entry_points", []))
    lines.extend(["", "## Architecture", "```mermaid", result["architecture"]["diagram"], "```", "",
                  "## Representative flows"])
    lines.extend(f"- **{flow['source']}** —{flow['relation']}→ **{flow['target']}** [{flow['confidence']}]"
                 + (f" · `{flow['evidence']}`" if flow.get("evidence") else "")
                 for flow in result["representative_flows"])
    lines.extend(["", "## Risk and technical-debt signals"])
    for risk in result["risk_signals"]:
        detail = risk.get("count")
        if detail is None and risk.get("symbols"):
            detail = ", ".join(risk["symbols"])
        if risk.get("by_relation"):
            detail = f"{detail} ({', '.join(f'{key}: {value}' for key, value in risk['by_relation'].items())})"
        lines.append(f"- **{risk['signal']}** ({risk['level']}): {detail or ''} {risk.get('note', '')}".rstrip())
    lines.extend(["", "## Key symbols"])
    lines.extend(f"- `{item}`" for item in profile.get("key_symbols", []))
    base = "\n".join(lines).rstrip() + "\n"
    source_chars = sum(len(_safe_text(Path(root), path)) for path in profile.get("read_first", []))
    metrics = {"estimated_tokens": len(base.encode("utf-8")) // 4,
               "selected_source_tokens": source_chars // 4,
               "observable_coverage": result["overview_quality"]["observable_coverage"]}
    metrics["reduction_vs_selected_source"] = round(
        1 - metrics["estimated_tokens"] / max(1, metrics["selected_source_tokens"]), 4
    )
    candidate = graphify_report or Path(root) / "graphify-out" / "GRAPH_REPORT.md"
    if candidate.is_file():
        graphify_text = candidate.read_text(encoding="utf-8", errors="ignore")
        metrics["graphify_report_tokens"] = len(graphify_text.encode("utf-8")) // 4
        metrics["token_difference_vs_graphify"] = metrics["estimated_tokens"] - metrics["graphify_report_tokens"]
        lower = graphify_text.lower()
        dimensions = (("purpose", "overview", "summary"), ("technology", "language", "framework"),
                      ("architecture", "community", "module"), ("flow", "call", "path"),
                      ("risk", "surprising", "ambiguous"), ("key concept", "god node", "central"))
        metrics["graphify_observable_coverage"] = round(
            sum(any(term in lower for term in dimension) for dimension in dimensions) / len(dimensions), 4
        )
    metrics["quality_note"] = "Coverage compares observable dimensions/headings, not ground-truth semantic correctness."
    report = base + "\n## Report metrics\n" + "\n".join(f"- {key}: `{value}`" for key, value in metrics.items()) + "\n"
    return report, metrics
