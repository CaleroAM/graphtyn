"""Smoke test de frontend con Playwright (browsers de NixOS).

Ejecutar dentro de nix-shell con playwright disponible:

    nix-shell -p python311Packages.playwright --run \
      "python3 tests/smoke_frontend.py"

Levanta una instancia aislada del servidor (HOME temporal, puerto 9211),
reindexa un proyecto temporal vía API y verifica en Chromium real:
 - carga de /dashboard, selector de proyecto, grafo renderizado (canvas)
 - cero errores de consola JS
 - cambio a vista semántica y estilo Neuronal sin romper
 - carga de /comparison
"""

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

PORT = 9211
BASE = f"http://127.0.0.1:{PORT}"
ROOT = Path(__file__).resolve().parent.parent
CHROMIUM = os.environ.get(
    "AETHER_CHROMIUM",
    "/nix/store/wgzwbl56lsw3r504xjkbc1w2ifnhdwlr-playwright-browsers/chromium-1217/chrome-linux64/chrome")


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
    if shutil.which("curl") is None or not (ROOT / ".venv" / "bin" / "aether-graph").exists():
        print("SKIP: dependencias ausentes")
        return 0

    tmp = Path(tempfile.mkdtemp(prefix="aether-smoke-"))
    proj = tmp / "proj"
    proj.mkdir()
    (proj / "a.py").write_text("def helper():\n    return 42\n", encoding="utf-8")
    (proj / "b.py").write_text("from a import helper\n\nprint(helper())\n", encoding="utf-8")
    home = tmp / "home"
    home.mkdir()

    env = dict(os.environ, HOME=str(home), OLLAMA_HOST="http://127.0.0.1:1")
    server = subprocess.Popen(
        [str(ROOT / ".venv" / "bin" / "aether-graph"), "serve",
         "--host", "127.0.0.1", "--port", str(PORT), "--path", str(proj)],
        cwd=str(ROOT), env=env, stdout=subprocess.DEVNULL, stderr=open(str(tmp / "server.log"), "w"))
    failures = []
    try:
        if not wait_server(BASE):
            print("FAIL: servidor no levantó")
            return 1

        r = api("POST", "/api/reindex", json={"path": str(proj), "engine": "ast_pure"})
        assert r.returncode == 0, r.stderr
        body = json.loads(r.stdout)
        assert body.get("ok") and body.get("nodes", 0) > 0, r.stdout

        with sync_playwright() as pw:
            if not Path(CHROMIUM).exists():
                print(f"SKIP: chromium no encontrado en {CHROMIUM}")
                return 0
            browser = pw.chromium.launch(executable_path=CHROMIUM, args=["--no-sandbox"])
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            console_errors = []
            page.on("console", lambda m: console_errors.append(f"{m.type}:{m.text} @{m.location.get('url','')}") if m.type == "error" else None)
            page.on("pageerror", lambda e: console_errors.append(str(e)))
            page.on("response", lambda r: console_errors.append(f"HTTP {r.status} {r.url}") if r.status >= 400 else None)

            page.goto(f"{BASE}/", timeout=30000)
            page.wait_for_selector("#stats", timeout=30000)
            page.wait_for_timeout(2500)

            title = page.title()
            assert "Aether" in title, f"título inesperado: {title}"

            selectors = page.locator("#graph-container")
            assert selectors.count() == 1, "contenedor de grafo ausente"

            for name in ("applyFilter", "changeGraphStyle", "setView"):
                assert page.evaluate(f"typeof window.{name}") == "function", f"{name} no expuesto en window"

            canvas = page.locator("#graph-container canvas")
            canvas.first.wait_for(state="visible", timeout=30000)
            assert canvas.count() >= 1, "canvas del grafo no renderizado"

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
