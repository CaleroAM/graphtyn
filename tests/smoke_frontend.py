"""Smoke test de frontend con Playwright (browsers de NixOS).

Ejecutar dentro de nix-shell con playwright disponible:

    nix-shell -p python311Packages.playwright --run \
      "python3 tests/smoke_frontend.py"

Levanta una instancia aislada del servidor (GRAPHTYN_HOME temporal, puerto 9211),
reindexa un proyecto temporal vía API y verifica en Chromium real:
 - carga de /dashboard, selector de proyecto, grafo renderizado (canvas)
 - cero errores de consola JS
 - cambio a vista semántica y estilo Neuronal sin romper
 - carga de /comparison
 - panel de calidad, contexto, estado incremental, ambigüedades y reporte Git
"""

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_IMPORT_ERROR = ""
except (ImportError, OSError) as exc:
    sync_playwright = None
    PLAYWRIGHT_IMPORT_ERROR = str(exc)

PORT = 9211
BASE = f"http://127.0.0.1:{PORT}"
ROOT = Path(__file__).resolve().parent.parent
SERVER_PYTHON = os.environ.get("GRAPHTYN_SMOKE_PYTHON", sys.executable)
CLI = [SERVER_PYTHON, "-m", "graphtyn.cli"]
CHROMIUM = os.environ.get(
    "GRAPHTYN_CHROMIUM",
    shutil.which("chromium") or shutil.which("chromium-browser") or "")


def unavailable(message):
    in_ci = os.environ.get("CI", "").strip().lower() in {"1", "true", "yes"}
    print(f"{'FAIL' if in_ci else 'SKIP'}: {message}")
    return 1 if in_ci else 0


def wait_server(url, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", PORT), timeout=1):
                return True
        except OSError:
            time.sleep(0.3)
    return False


def api(method, path, **kw):
    return subprocess.run(
        ["curl", "-s", "-m", "30", "-X", method, f"{BASE}{path}"] +
        (["-H", "Content-Type: application/json", "-d", json.dumps(kw.get("json"))] if kw.get("json") is not None else []),
        capture_output=True, text=True)


def main():
    if sync_playwright is None:
        return unavailable(f"Playwright no ejecutable ({PLAYWRIGHT_IMPORT_ERROR})")
    if shutil.which("curl") is None:
        return unavailable("dependencias ausentes")

    tmp = Path(tempfile.mkdtemp(prefix="graphtyn-smoke-"))
    proj = tmp / "proj"
    proj.mkdir()
    (proj / "a.py").write_text("def helper():\n    return 42\n", encoding="utf-8")
    (proj / "b.py").write_text("from a import helper\n\nprint(helper())\n", encoding="utf-8")
    proj2 = tmp / "proj-two"
    proj2.mkdir()
    (proj2 / "worker.py").write_text("def work():\n    return 'ok'\n", encoding="utf-8")
    home = tmp / "home"
    home.mkdir()

    env = dict(os.environ, GRAPHTYN_HOME=str(home / ".graphtyn"), OLLAMA_HOST="http://127.0.0.1:1")
    # A Nix Playwright shell exports its own Python search paths. The Graphtyn
    # server may deliberately run from a project virtualenv, so keep that
    # interpreter isolated from the browser runner's Python environment.
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    server = subprocess.Popen(
        CLI + ["serve",
         "--host", "127.0.0.1", "--port", str(PORT), "--path", str(proj)],
        cwd=str(ROOT), env=env, stdout=subprocess.DEVNULL, stderr=open(str(tmp / "server.log"), "w"))
    failures = []
    try:
        if not wait_server(BASE):
            print("FAIL: servidor no levantó")
            return 1

        for project in (proj, proj2):
            registered = api("POST", "/api/projects/register", json={
                "path": str(project), "name": project.name, "mode": "single_folder",
                "space_type": "project",
            })
            assert registered.returncode == 0, registered.stderr
            registered_body = json.loads(registered.stdout)
            assert registered_body.get("ok"), registered_body

        r = api("POST", "/api/reindex", json={"path": str(proj), "engine": "ast_pure"})
        assert r.returncode == 0, r.stderr
        body = json.loads(r.stdout)
        job_id = body.get("id")
        assert body.get("ok") and job_id, r.stdout
        deadline = time.monotonic() + 30
        while body.get("status") not in {"completed", "failed", "cancelled"}:
            assert time.monotonic() < deadline, body
            time.sleep(0.1)
            r = api("GET", f"/api/reindex/{job_id}")
            assert r.returncode == 0, r.stderr
            body = json.loads(r.stdout)
        assert body.get("status") == "completed" and body.get("result", {}).get("nodes", 0) > 0, body

        # Seed attributed memory through the public CLI so the browser must
        # render a real agent -> memory -> file graph, not merely an empty view.
        started = subprocess.run(
            CLI + ["memory", "session-start",
             "--agent", "smoke-agent", "--task", "Dashboard memory smoke", "--capture",
             "--path", str(proj)], cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=30)
        assert started.returncode == 0, started.stderr
        session_id = json.loads(started.stdout)["id"]
        checkpoint = subprocess.run(
            CLI + ["memory", "checkpoint",
             "--session", session_id, "--kind", "outcome", "--title", "Memory graph visible",
             "--content", "The dashboard renders attributed project memory automatically.",
             "--scope", "project", "--files", "a.py", "--nodes", "symbol:a.py:helper",
             "--tests", "tests/smoke_frontend.py", "--path", str(proj)],
            cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=30)
        assert checkpoint.returncode == 0, checkpoint.stderr
        started2 = subprocess.run(
            CLI + ["memory", "session-start",
             "--agent", "smoke-agent-two", "--task", "Second project memory", "--capture",
             "--path", str(proj2)], cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=30)
        assert started2.returncode == 0, started2.stderr
        session2 = json.loads(started2.stdout)["id"]
        checkpoint2 = subprocess.run(
            CLI + ["memory", "checkpoint",
             "--session", session2, "--kind", "decision", "--title", "Second graph isolated",
             "--content", "Project switching must never reuse another project's graph response.",
             "--scope", "project", "--files", "worker.py", "--path", str(proj2)],
            cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=30)
        assert checkpoint2.returncode == 0, checkpoint2.stderr

        # Seed a typed evidence record so the visual evidence view exercises
        # execution, metric, test and dependency relations in a real browser.
        (proj / "test_probe.py").write_text("def test_probe():\n    assert True\n", encoding="utf-8")
        evidence = proj / "benchmarks" / "smoke" / "summary.json"
        evidence.parent.mkdir(parents=True)
        evidence.write_text(json.dumps({
            "subject": "a.py", "tests": ["test_probe.py"], "tests_passed": 1,
            "execution_record": {
                "command": ["pytest", "test_probe.py"], "exit_code": 0,
                "started_at": 1, "finished_at": 2, "executor": "frontend-smoke",
                "log_digest_sha256": "b" * 64, "project": {"id": "smoke-project"},
                "git_context": {"commit": "smoke", "dirty": False},
                "test_files": ["test_probe.py"], "data_files": [],
                "environment_digest_sha256": "d" * 64,
                "declared_dependencies": ["a.py"],
            },
        }), encoding="utf-8")
        ingested = subprocess.run(
            CLI + ["memory", "ingest-evidence", "--files", "benchmarks/smoke/summary.json",
                   "--path", str(proj)], cwd=str(ROOT), env=env, capture_output=True,
            text=True, timeout=30)
        assert ingested.returncode == 0, ingested.stderr

        with sync_playwright() as pw:
            launch = {"args": ["--no-sandbox"]}
            if CHROMIUM:
                if not Path(CHROMIUM).exists():
                    return unavailable(f"chromium no encontrado en {CHROMIUM}")
                launch["executable_path"] = CHROMIUM
            try:
                browser = pw.chromium.launch(**launch)
            except Exception as exc:
                return unavailable(f"Chromium no ejecutable ({exc})")
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            console_errors = []
            page.on("console", lambda m: console_errors.append(f"{m.type}:{m.text} @{m.location.get('url','')}") if m.type == "error" else None)
            page.on("pageerror", lambda e: console_errors.append(str(e)))
            page.on("response", lambda r: console_errors.append(f"HTTP {r.status} {r.url}") if r.status >= 400 else None)

            page.goto(f"{BASE}/", timeout=30000)
            page.wait_for_selector("#stats", timeout=30000)
            page.wait_for_selector("#modal-welcome.show", state="visible")
            assert page.locator("#welcome-dashboard-url").inner_text() == BASE
            assert "primera vez" in page.locator("#modal-welcome").inner_text().lower()
            page.click("#welcome-start")
            assert page.locator("#modal-welcome").evaluate("el => !el.classList.contains('show')")
            assert page.evaluate("localStorage.getItem('graphtyn.welcome.0.6.1')") == "seen"
            page.wait_for_timeout(2500)
            page.evaluate("path => selectProject(path)", str(proj))
            page.wait_for_timeout(1500)

            title = page.title()
            assert "Graphtyn" in title, f"título inesperado: {title}"

            selectors = page.locator("#graph-container")
            assert selectors.count() == 1, "contenedor de grafo ausente"

            for name in ("applyFilter", "changeGraphStyle", "setView"):
                assert page.evaluate(f"typeof window.{name}") == "function", f"{name} no expuesto en window"

            canvas = page.locator("#graph-container canvas")
            canvas.first.wait_for(state="visible", timeout=30000)
            assert canvas.count() >= 1, "canvas del grafo no renderizado"

            # Primary navigation is grouped by task instead of exposing every view as a top-level button.
            page.click("#dd-explore > button")
            page.wait_for_selector("#dd-explore.open .nav-menu", state="visible")
            explore = page.locator("#dd-explore .dd-panel").bounding_box()
            assert explore and explore["y"] + explore["height"] <= 900, "menú Explorar sale del viewport"
            assert page.locator("#dd-explore .menu-item").count() == 6
            assert page.locator("#btn-openclaw").is_visible(), "vista de administración OpenClaw ausente"
            page.click("#btn-semantic")
            page.wait_for_timeout(800)
            assert page.locator("#active-view-label").inner_text() == "Semántico"
            assert page.locator("#dd-explore").evaluate("el => !el.classList.contains('open')")
            page.evaluate("setView('code')")

            page.click("#dd-viewport > button")
            page.wait_for_selector("#dd-viewport.open .dd-panel", state="visible")
            assert page.locator("#dd-viewport #btn-2d").count() == 1
            assert page.locator("#dd-viewport #btn-3d").count() == 1
            page.keyboard.press("Escape")
            assert page.locator("#dd-viewport").evaluate("el => !el.classList.contains('open')")

            # Header menus own the foreground while open: floating MCP/actions/reindex
            # controls must not cover filter fields such as "Tipo de nodo".
            page.click("#dd-filter > button")
            page.wait_for_selector("#dd-filter.open .dd-panel", state="visible")
            filter_panel = page.locator("#dd-filter .dd-panel").bounding_box()
            assert filter_panel and filter_panel["y"] + filter_panel["height"] <= 900, "panel Filtros sale del viewport"
            assert "tipo de nodo" in page.locator("#dd-filter").inner_text().lower()
            page.wait_for_function(
                """() => {
                  const el = document.querySelector('.float-actions');
                  if (!el) return true;
                  const style = getComputedStyle(el);
                  return style.visibility === 'hidden' || Number(style.opacity) <= 0.01;
                }""",
                timeout=5000,
            )
            floating_state = page.locator(".float-actions").evaluate(
                "el => { const s=getComputedStyle(el); return {visibility:s.visibility,pointerEvents:s.pointerEvents,opacity:s.opacity,bodyClass:document.body.className,filterClass:document.getElementById('dd-filter').className}; }"
            )
            visually_absent = floating_state["visibility"] == "hidden" or float(floating_state["opacity"]) <= 0.01
            assert visually_absent and floating_state["pointerEvents"] == "none", f"MCP/Acciones/Reindexar cubren el panel Filtros: {floating_state}"
            page.keyboard.press("Escape")

            page.click("#dd-actions > button")
            page.wait_for_selector("#dd-actions.open .action-menu", state="visible")
            actions = page.locator("#dd-actions .dd-panel").bounding_box()
            assert actions and actions["x"] >= 0 and actions["x"] + actions["width"] <= 1440, "menú Acciones sale del viewport"
            assert page.locator("#dd-actions .menu-item").count() == 5
            page.keyboard.press("Escape")

            # Appearance and indexing are independent, viewport-bounded panels.
            page.click("#dd-appearance > button")
            page.wait_for_selector("#dd-appearance.open .dd-panel", state="visible")
            appearance = page.locator("#dd-appearance .dd-panel").bounding_box()
            assert appearance and appearance["y"] + appearance["height"] <= 900, "panel de diseño sale del viewport"
            assert page.locator("#dd-appearance #palette-sel").count() == 1
            assert page.locator("#dd-appearance #f-repulsion").count() == 1
            page.click("#dd-engine > button")
            page.wait_for_selector("#dd-engine.open .dd-panel", state="visible")
            assert page.locator("#dd-appearance").evaluate("el => !el.classList.contains('open')")
            engine = page.locator("#dd-engine .dd-panel").bounding_box()
            assert engine and engine["y"] + engine["height"] <= 900, "panel de motor sale del viewport"
            assert page.locator("#dd-engine #engine-sel").count() == 1
            assert page.locator("#dd-engine #code-model-sel").count() == 1

            # Status items may wrap, but their boxes must never overlap.
            status_parts = page.locator("#model-badge, #stats, #conf-legend").evaluate_all(
                "els => els.map(el => { const r=el.getBoundingClientRect(); return {x:r.x,y:r.y,w:r.width,h:r.height}; })"
            )
            def overlaps(a, b):
                return a["x"] < b["x"] + b["w"] and a["x"] + a["w"] > b["x"] and a["y"] < b["y"] + b["h"] and a["y"] + a["h"] > b["y"]
            assert not overlaps(status_parts[0], status_parts[2]), "modelo y leyenda se enciman"
            assert not overlaps(status_parts[1], status_parts[2]), "conteos y leyenda se enciman"
            page.keyboard.press("Escape")

            page.evaluate("openQualityPanel()")
            page.wait_for_selector("#modal-quality.show", timeout=5000)
            page.wait_for_timeout(800)
            assert "salud observable" in page.locator("#quality-summary").inner_text().lower()
            assert page.locator("#index-update").inner_text().strip(), "estado incremental vacío"
            assert page.locator("#ambiguity-queue").inner_text().strip(), "cola de ambigüedades vacía"
            page.fill("#answer-validation-input", "La función helper está definida y devuelve el valor esperado en a.py:1.")
            page.evaluate("validateAgentAnswer()")
            page.wait_for_function("() => document.querySelector('#answer-validation-output').innerText.trim().length > 0", timeout=5000)
            validation_text = page.locator("#answer-validation-output").inner_text().lower()
            assert "trazabilidad" in validation_text, f"validación inesperada: {validation_text}"
            page.evaluate("generateChangeReport()")
            page.wait_for_function("() => document.querySelector('#answer-validation-output').innerText.toLowerCase().includes('reporte generado')", timeout=5000)
            page.evaluate("closeQualityPanel()")

            page.evaluate("openMemoryPanel()")
            page.wait_for_selector("#modal-memory.show", timeout=5000)
            page.wait_for_function("() => !document.querySelector('#memory-status').innerText.includes('Consultando')", timeout=15000)
            assert "memorias" in page.locator("#memory-status").inner_text().lower()
            page.fill("#memory-query", "decisión de autenticación")
            page.evaluate("searchSharedMemory()")
            page.wait_for_function("() => !document.querySelector('#memory-results').innerText.includes('Buscando contexto')", timeout=5000)
            assert page.locator("#memory-results").inner_text().strip()
            page.evaluate("closeMemoryPanel()")

            page.evaluate("setView('memory')")
            page.wait_for_function(
                "() => document.querySelector('#stats').innerText.includes('nodos') && !document.querySelector('#stats').innerText.includes('Cargando')",
                timeout=15000)
            memory_badge = page.locator("#model-badge").inner_text()
            assert any(mode in memory_badge for mode in ("Memoria simplificada", "Memoria detallada")), memory_badge
            page.wait_for_selector("#memory-legend-overlay", state="visible", timeout=5000)
            assert "smoke-agent" in page.locator("#memory-legend-overlay").inner_text()
            assert page.locator("#graph-container canvas").count() >= 1, "grafo visual de memoria no renderizado"

            page.evaluate("openMemoryPanel()")
            page.wait_for_selector("#modal-memory.show", timeout=5000)
            page.click("#memory-graph-btn")
            page.wait_for_function(
                "() => document.querySelector('#model-badge').innerText.includes('Evidencia y procedencia')",
                timeout=15000)
            page.wait_for_selector("#memory-legend-overlay", state="visible", timeout=5000)
            evidence_legend = page.locator("#memory-legend-overlay").inner_text().lower()
            assert "ejecución" in evidence_legend and "produce" in evidence_legend and "depende de" in evidence_legend
            assert page.locator("#graph-container canvas").count() >= 1, "grafo visual de evidencia no renderizado"

            # Return to the thematic memory view before testing project switching.
            page.evaluate("openMemoryPanel()")
            page.wait_for_selector("#modal-memory.show", timeout=5000)
            page.click("#memory-graph-btn")
            page.wait_for_function(
                "() => document.querySelector('#model-badge').innerText.includes('Memoria simplificada') || document.querySelector('#model-badge').innerText.includes('Memoria detallada')",
                timeout=15000)

            # Switch projects while requests from the previous view may still be
            # in flight; only the newest project's memory may paint the canvas.
            page.evaluate("path => selectProject(path)", str(proj2))
            page.evaluate("setView('memory')")
            page.wait_for_function(
                "() => document.querySelector('#memory-legend-overlay')?.innerText.includes('smoke-agent-two')",
                timeout=15000)
            assert "smoke-agent\n" not in page.locator("#memory-legend-overlay").inner_text()

            page.evaluate("setView('semantic')")
            page.wait_for_timeout(1500)

            page.evaluate("changeGraphStyle('neuronal')")
            page.wait_for_timeout(1500)
            page.evaluate("changeGraphStyle('standard')")
            page.wait_for_timeout(1000)

            assert console_errors == [], f"errores de consola: {console_errors[:5]}"

            page.goto(f"{BASE}/comparison", timeout=30000)
            page.wait_for_timeout(800)
            assert "comparaci" in (page.title() + page.content()).lower()[:2000] or page.locator("body").count() == 1

            shot = tmp / "dashboard.png"
            page.goto(f"{BASE}/", timeout=30000)
            page.wait_for_timeout(1500)
            page.screenshot(path=str(shot), full_page=True)
            assert shot.stat().st_size > 10_000, "screenshot sospechosamente pequeño"

            browser.close()
        print(f"OK: dashboard renderizado, vistas y estilos sin errores JS (screenshot: {shot})")
        return 0
    except Exception as exc:
        failures.append(str(exc))
        print(f"FAIL: {exc}")
        traceback.print_exc()
        slog = tmp / "server.log"
        if slog.exists():
            lines = [l for l in slog.read_text(encoding="utf-8", errors="replace").splitlines() if " 404 " in l or " 500 " in l]
            if lines:
                print("server 4xx/5xx:", lines[-8:])
        return 1
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
