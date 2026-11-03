import json
import re
from pathlib import Path

from graphtyn.api import main as api_main

WEB = Path(__file__).resolve().parents[1] / "graphtyn" / "web"


def _body(response):
    return json.loads(response.body)


def test_quality_endpoint_logic_without_http_lifespan(tmp_path, monkeypatch):
    monkeypatch.setattr(api_main, "INDEX_STORE", tmp_path / "store")
    project = tmp_path / "project"
    project.mkdir()
    (project / "a.py").write_text("def helper():\n    return 1\n")
    data = _body(api_main.get_index_quality(str(project)))
    assert data["ok"] is True
    assert data["nodes"] > 0
    assert 0 <= data["health_score"] <= 100
    assert "ground truth" in data["accuracy_note"]


def test_report_endpoint_returns_auditable_markdown(tmp_path, monkeypatch):
    monkeypatch.setattr(api_main, "INDEX_STORE", tmp_path / "store")
    project = tmp_path / "project"
    project.mkdir()
    (project / "README.md").write_text("# Demo\n\nDemo processes orders through a small local API for retail teams.\n")
    (project / "main.py").write_text("def main():\n    return 1\n")
    data = _body(api_main.get_graphtyn_report(str(project)))
    assert data["ok"] is True
    assert data["filename"] == "GRAPHTYN_REPORT.md"
    assert "Demo processes orders" in data["content"]
    assert "```mermaid" in data["content"]
    assert data["metrics"]["estimated_tokens"] > 0


def test_reindex_persists_report_next_to_index(tmp_path, monkeypatch):
    store = tmp_path / "store"
    monkeypatch.setattr(api_main, "INDEX_STORE", store)
    project = tmp_path / "project"
    project.mkdir()
    (project / "README.md").write_text("# Demo\n\nDemo manages inventory for independent stores and warehouses.\n")
    (project / "main.py").write_text("def main():\n    return 1\n")
    data = api_main._execute_reindex({"path": str(project), "engine": "ast_pure", "full": True})
    assert data["ok"] is True
    report = Path(data["report"])
    assert report.name == "GRAPHTYN_REPORT.md" and report.is_file()
    assert report.parent == api_main._index_dir(project)
    assert "manages inventory" in report.read_text(encoding="utf-8")


def test_context_endpoint_logic_and_bounds(tmp_path, monkeypatch):
    monkeypatch.setattr(api_main, "INDEX_STORE", tmp_path / "store")
    project = tmp_path / "project"
    project.mkdir()
    (project / "a.py").write_text("def helper():\n    return 1\n")
    data = _body(api_main.create_context_bundle({"path": str(project), "symbols": ["helper", "helper"], "depth": 99, "limit": 999}))
    assert data["ok"] is True
    assert data["symbols"] == ["helper"]
    assert data["contexts"][0]["symbol"] == "helper"
    assert data["reduction_rate"] <= 1
    assert data["unmatched_symbols"] == []


def test_context_uses_safe_nested_root_from_index_metadata(tmp_path, monkeypatch):
    monkeypatch.setattr(api_main, "INDEX_STORE", tmp_path / "store")
    outer = tmp_path / "outer"
    inner = outer / "inner"
    inner.mkdir(parents=True)
    source = inner / "a.py"
    source.write_text("def helper():\n    return 1\n")
    graph = api_main.parser.scan_directory(inner)
    graph.setdefault("metadata", {})["path"] = str(inner)
    index_dir = api_main._index_dir(outer)
    (index_dir / "index.json").write_text(json.dumps(graph))
    data = _body(api_main.create_context_bundle({"path": str(outer), "symbols": ["helper", "missing"]}))
    assert data["raw_context_tokens"] > 0
    assert data["unmatched_symbols"] == ["missing"]


def test_context_endpoint_rejects_bad_inputs(tmp_path):
    response = api_main.create_context_bundle({"path": str(tmp_path), "symbols": ["x"], "depth": "bad"})
    assert response.status_code == 400
    assert "enteros" in _body(response)["error"]


def test_raw_context_size_cannot_escape_project(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    outside = tmp_path / "secret.txt"
    outside.write_text("secret")
    assert api_main._safe_project_file_size(project, "../secret.txt") == 0
    assert api_main._safe_project_file_size(project, "missing.txt") == 0


def test_dashboard_quality_controls_are_wired_end_to_end():
    html = (WEB / "dashboard.html").read_text()
    dashboard = (WEB / "dashboard.js").read_text()
    graph = (WEB / "js" / "graph.js").read_text()
    handlers = (WEB / "js" / "__handlers.js").read_text()
    quality = (WEB / "js" / "quality.js").read_text()
    assert 'id="modal-quality"' in html and 'id="quality-summary"' in html
    assert 'id="context-selection"' in html and 'id="context-output"' in html
    assert "openQualityPanel" in dashboard and "generateContextBundle" in dashboard
    assert "addNodeToContext" in graph and "from './quality.js'" in handlers
    assert "/api/index-quality" in quality and "/api/context-bundle" in quality
    assert "accuracy_note" in quality and "token_estimation" in quality
    assert 'id="context-scope"' in html and "scope" in quality
    assert 'id="index-update"' in html and 'id="ambiguity-queue"' in html
    assert 'id="answer-validation-input"' in html
    for endpoint in ("/api/index-update", "/api/ambiguities", "/api/validate-answer", "/api/change-report"):
        assert endpoint in quality
    for handler in ("loadIndexUpdate", "loadAmbiguities", "reviewAmbiguity", "validateAgentAnswer", "generateChangeReport"):
        assert handler in dashboard and handler in handlers


def test_dashboard_shared_memory_is_separate_and_wired_end_to_end():
    html = (WEB / "dashboard.html").read_text()
    dashboard = (WEB / "dashboard.js").read_text()
    handlers = (WEB / "js" / "__handlers.js").read_text()
    memory = (WEB / "js" / "memory.js").read_text()
    css = (WEB / "dashboard.css").read_text()
    assert 'id="modal-memory"' in html and 'id="memory-results"' in html
    assert 'id="memory-sessions"' in html and 'id="memory-token"' in html
    assert "openMemoryPanel" in dashboard and "searchSharedMemory" in handlers
    for endpoint in ("/api/memory/status", "/api/memory/sessions", "/api/memory/search",
                     "/api/memory/correct", "/api/memory/forget", "/api/memory/graph"):
        assert endpoint in memory
    assert 'id="memory-graph-btn"' in html and 'id="memory-agent-legend"' in html
    assert "showSharedMemoryGraph" in handlers and "agent_color" in (WEB / "js" / "painters.js").read_text()
    assert 'id="memory-color-controls"' in html and 'id="memory-halo-color"' in html
    assert 'class="memory-color-actions"' in html and ".memory-color-actions" in css
    assert 'id="memory-palette-sel"' in html and 'value="custom">Personalizada' in html
    assert html.count('value="custom">Personalizada') == 2
    assert 'id="chk-radiance"' in html and 'toggleRadiance' in dashboard
    assert 'Parpadeo de Vértices</span>' in html and 'Dibujo orgánico</span>' in html
    assert "IDs de nodos" in (WEB / "js" / "graph.js").read_text()
    assert "renderCommunityNodes" in dashboard and "renderCommunityNodes" in handlers
    assert ".comm-node-id" in css and ".comm-node-details" in css
    painters = (WEB / "js" / "painters.js").read_text()
    styles = (WEB / "js" / "styles.js").read_text()
    state = (WEB / "js" / "state.js").read_text()
    graph = (WEB / "js" / "graph.js").read_text()
    assert "state.radianceOn" in painters and "state.radianceOn" in styles
    assert "state.vertexBlinkOn" in painters and "state.vertexBlinkOn" in styles
    assert "graphInst.refresh" in styles
    assert "linkHaloByDefault" in state and "MEMORY_CUSTOM_COLOR_KEY" in state
    assert "particleProfile" in state and "particleProfile" in graph and "particleProfile" in styles
    assert "linkDirectionalParticleOffset" in graph and "linkDirectionalParticleOffset" in styles
    assert "activeLinkColor" in graph and "memoryLinkColor(l, linkBase)" in graph
    assert "standard2DLinkColor" in graph and "standard2DLinkColor" in styles
    assert 'loadMoreMemoryTopics' in dashboard and 'focusMemorySession' in dashboard
    assert 'memoryFocusSession' in (WEB / "js" / "graph.js").read_text()
    assert 'f97316' in (WEB / "js" / "state.js").read_text()
    assert 'MEMORY_PALETTES' in (WEB / "js" / "state.js").read_text()
    assert 'id="btn-memory-view"' in html and "Memoria del proyecto" in html
    assert "state.activeView === 'memory'" in (WEB / "js" / "graph.js").read_text()
    assert "/api/memory/graph?path=" in (WEB / "js" / "graph.js").read_text()
    assert "textContent" in memory and "esc(" in memory
    assert ".memory-layout" in css and "grid-template-columns" in css
    assert 'id="memory-import-provider"' in html and 'id="memory-import-apply"' in html
    for element_id in ("memory-sync-btn", "memory-sync-all-btn", "memory-enrich-retry-btn", "memory-watch-btn"):
        assert f'id="{element_id}"' in html
    for handler in ("syncMemorySpace", "syncAllMemorySpaces", "retryMemoryEnrichment", "toggleMemoryWatch"):
        assert handler in memory and handler in dashboard and handler in handlers
    for endpoint in ("/api/memory/sync", "/api/memory/watch"):
        assert endpoint in memory
    assert "retry_failed" in memory
    assert "/api/v1/imports/discover" in memory and "/api/v1/imports" in memory
    assert "data.providers.includes('opencode') ? 'opencode'" in memory
    assert "state.activePath ? {path:state.activePath}" in memory
    assert "discoverHistoricalMemory" in dashboard and "applyHistoricalMemory" in handlers
    assert "saveHistoricalSource" in memory and "testHistoricalSource" in handlers
    assert "removeHistoricalSource" in memory and "saveMemoryAlias" in handlers
    assert 'id="memory-alias"' in html and 'id="memory-canonical"' in html
    assert ".memory-import-panel" in css


def test_dashboard_exposes_framework_flow_filters_and_route_metadata():
    html = (WEB / "dashboard.html").read_text()
    dashboard = (WEB / "dashboard.js").read_text()
    graph = (WEB / "js" / "graph.js").read_text()
    painters = (WEB / "js" / "painters.js").read_text()
    quality = (WEB / "js" / "quality.js").read_text()
    assert 'id="f-route"' in html
    assert html.count('class="f-relation"') == 14
    for relation in ("sustentada por", "resulta de", "genera resultado", "mide",
                     "produce", "declara", "verifica", "depende de", "invalida"):
        assert f'value="{relation}"' in html
    assert "AMBIGUOUS" in html and "AMBIGUOUS" in graph
    assert "focusWebFlow" in dashboard and "clearWebFlow" in dashboard
    assert "http_method" in graph and "node.path" in graph
    assert "k === 'route'" in painters
    assert "framework.resolved_routes" in quality


def test_dashboard_separates_graph_design_from_index_engine_and_wraps_status():
    html = (WEB / "dashboard.html").read_text()
    css = (WEB / "dashboard.css").read_text()
    ui = (WEB / "js" / "ui.js").read_text()
    assert 'id="dd-appearance"' in html and "Diseño del grafo" in html
    assert 'id="dd-engine"' in html and "Motor de índice" in html
    assert "Paleta & Motor" not in html and 'id="dd-settings"' not in html
    for element_id in ("palette-sel", "style-sel", "shape-sel", "link-style-sel",
                       "engine-sel", "code-model-sel", "vision-model-sel",
                       "f-repulsion", "f-distance"):
        assert html.count(f'id="{element_id}"') == 1
    assert 'class="graph-status"' in html
    assert html.count('class="confidence-item') == 3
    assert "flex-wrap:wrap" in css and "max-height:min(650px" in css
    assert "aria-expanded" in ui


def test_dashboard_groups_navigation_and_secondary_actions_into_menus():
    html = (WEB / "dashboard.html").read_text()
    css = (WEB / "dashboard.css").read_text()
    controls = (WEB / "js" / "controls.js").read_text()
    dashboard = (WEB / "dashboard.js").read_text()
    for menu_id in ("dd-explore", "dd-viewport", "dd-actions"):
        assert f'id="{menu_id}"' in html
    assert 'id="active-view-label"' in html
    assert 'class="dd-panel nav-menu"' in html
    assert 'class="dd-panel action-menu"' in html
    assert html.count('id="reindex-btn"') == 1
    assert "Calidad y contexto" in html and "Administrar memoria" in html
    assert "Exportar datos JSON" in html and "Exportar imagen PNG" in html
    assert ".menu-item" in css and ".dimension-switch" in css
    assert "activeLabel.textContent" in controls
    assert "closeDropdownMenus" in dashboard


def test_dashboard_control_ids_are_unique_and_dropdowns_are_accessible():
    html = (WEB / "dashboard.html").read_text()
    ids = re.findall(r'\bid="([^"]+)"', html)
    assert len(ids) == len(set(ids)), "duplicate element ids make controls unreliable"
    for menu_id in ("dd-explore", "dd-viewport", "dd-filter", "dd-appearance", "dd-engine", "dd-actions"):
        block = html[html.index(f'id="{menu_id}"'):]
        opening_button = block[:block.index("</button>")]
        assert 'aria-haspopup="true"' in opening_button
        assert 'aria-expanded="false"' in opening_button


def test_header_dropdowns_hide_floating_actions_to_prevent_overlap():
    css = (WEB / "dashboard.css").read_text()
    assert "header:has(.dd-wrap.open) + .float-actions" in css
    assert "body.header-menu-open .float-actions" in css
    assert "opacity:0; visibility:hidden; pointer-events:none" in css
    assert "z-index:80" in css


def test_first_run_welcome_explains_dashboard_address_and_is_persistent():
    html = (WEB / "dashboard.html").read_text()
    dashboard = (WEB / "dashboard.js").read_text()
    assert 'id="modal-welcome"' in html
    assert 'id="welcome-dashboard-url"' in html
    assert "http://127.0.0.1:9210" in html
    assert "Este mensaje sólo aparece la primera vez" in html
    assert "graphtyn.welcome.0.6.1" in dashboard
    assert "window.location.origin" in dashboard
    assert "localStorage.setItem" in dashboard


def test_graph_loading_cancels_stale_project_requests_and_has_memory_specific_empty_state():
    graph = (WEB / "js" / "graph.js").read_text()
    state = (WEB / "js" / "state.js").read_text()
    assert "graphLoadId" in state and "graphRequestController" in state
    assert "state.graphRequestController.abort()" in graph
    assert "loadId !== state.graphLoadId" in graph
    assert "err?.name === 'AbortError'" in graph
    assert "Sin memorias capturadas para este proyecto" in graph
    assert "Sin nodos de código" in graph


def test_memory_dashboard_lists_and_maps_historical_conversations():
    memory = (WEB / "js" / "memory.js").read_text()
    assert "/api/memory/sessions?path=${path}&limit=100" in memory
    assert "item.id.startsWith('ses_ext_') ? 'histórica · '" in memory


def test_changes_view_stays_below_header_and_explains_clean_repository():
    graph = (WEB / "js" / "graph.js").read_text()
    css = (WEB / "dashboard.css").read_text()
    assert 'class="changes-view"' in graph
    assert "padding:96px 26px 32px" in css
    assert "El repositorio está limpio" in graph
    assert "SIN CAMBIOS" in graph
    assert "Number.isFinite(d.impacted_count)" in graph


def test_dashboard_sends_the_stored_token_to_every_route_guarded_for_network_access():
    # Opened from a non-loopback address, the server requires the token on these routes.
    guarded = re.compile(r"fetch\((['`])/api/(graph|reindex|memory|v1/|harness/|projects/register|agents/register)")
    for script in (WEB / "js").glob("*.js"):
        source = script.read_text()
        for match in guarded.finditer(source):
            call = source[match.start():source.find(";", match.start())]
            assert "authHeaders(" in call or "headers" in call, f"{script.name}: {call[:90]}"
    graph = (WEB / "js" / "graph.js").read_text()
    assert "fetch(url, {headers:authHeaders(), signal:requestSignal})" in graph
    assert "Buscar en memoria" not in graph


def test_service_badge_reflects_the_server_instead_of_a_fixed_label():
    html = (WEB / "dashboard.html").read_text()
    service = (WEB / "js" / "service.js").read_text()
    assert "MCP Activo" not in html
    assert 'id="service-status-label"' in html and 'id="service-offline"' in html
    assert "fetch('/api/service'" in service
    assert "initServiceStatus()" in (WEB / "dashboard.js").read_text()


def test_dashboard_explains_node_colors_and_each_view():
    html = (WEB / "dashboard.html").read_text()
    legend = (WEB / "js" / "legend.js").read_text()
    controls = (WEB / "js" / "controls.js").read_text()
    assert 'id="kind-legend"' in html and 'id="view-hint"' in html
    assert "item(p.file, 'archivo'), item(p.class, 'clase'), item(p.func, 'función')" in legend
    assert set(("code:", "semantic:", "memory:", "agents:")) <= {line.strip().split(" ")[0] for line in legend.splitlines()}
    assert "refreshLegends();" in controls and "renderKindLegend();" in controls
    assert "COMUNIDADES" in html and "COMMUNITIES</div>" not in html


def test_view_specific_controls_and_empty_topology_are_explained():
    css = (WEB / "dashboard.css").read_text()
    graph = (WEB / "js" / "graph.js").read_text()
    assert ".memory-graph-view-control[hidden]{display:none}" in css
    assert "emptyTopology" in graph and "Aún no hay agentes observados" in graph
    assert "<summary><span>IDs de nodos</span></summary>" in graph


def test_help_overlay_shortcuts_and_anonymous_mode_are_wired():
    html = (WEB / "dashboard.html").read_text()
    help_js = (WEB / "js" / "help.js").read_text()
    dashboard = (WEB / "dashboard.js").read_text()
    css = (WEB / "dashboard.css").read_text()
    assert 'id="modal-help"' in html and 'onclick="openHelp()"' in html and 'id="anonymous-badge"' in html
    for key in ("'?'", "'/'", "'a'"):
        assert f"event.key === {key}" in help_js
    assert "['INPUT', 'TEXTAREA', 'SELECT']" in help_js
    assert "handleShortcut(e)" in dashboard and "closeHelp();" in dashboard
    assert "body.anonymous :is(#project-list" in css and ".modal-bg:not(#modal-help) .modal-box" in css
    assert "if (state.anonymous)" in (WEB / "js" / "graph.js").read_text()


def test_demo_is_offered_on_first_run_help_and_empty_dashboard():
    html = (WEB / "dashboard.html").read_text()
    assert 'id="welcome-demo"' in html and html.count("startDemo(this)") >= 2
    assert "startDemo(this)" in (WEB / "js" / "graph.js").read_text()
    assert "'/api/demo'" in (WEB / "js" / "help.js").read_text()
    assert '"/api/demo"' in (Path(api_main.__file__)).read_text()


def test_activity_panel_is_wired_and_states_what_it_cannot_see():
    html = (WEB / "dashboard.html").read_text()
    activity = (WEB / "js" / "activity.js").read_text()
    assert 'id="activity-panel"' in html and 'id="activity-follow"' in html and 'id="activity-btn"' in html
    assert "fetch('/api/agent-activity?path='" in activity and "headers:authHeaders()" in activity
    assert "no sabe qué archivos lee o busca el agente después" in activity
    assert "resetActivityForProject();" in (WEB / "js" / "ui.js").read_text()
    assert '"/api/agent-activity"' in Path(api_main.__file__).read_text()
    # Everything from a query comes from agents: it must be escaped before reaching innerHTML.
    assert "${esc(query.request)}" in activity and "${query.request}" not in activity
    # Node ids reach the handler through a data attribute, never spliced into inline JavaScript.
    assert 'data-node-id="${esc(item.id)}" onclick="focusNode(this.dataset.nodeId)"' in activity


def test_focused_packages_are_named_on_the_canvas_and_stay_anonymous():
    painters = (WEB / "js" / "painters.js").read_text()
    assert "state.anonymous ? anonymousName(node) : String(node.name || '')" in painters
    assert ".onRenderFramePost(paintFocusLabels)" in (WEB / "js" / "graph.js").read_text()
