from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from ..core.ast_parser import ASTParser

app = FastAPI(title="AetherGraph API", version="0.1.0")
parser = ASTParser()

@app.get("/api/graph")
def get_graph(path: str = "."):
    root = Path(path).resolve()
    data = parser.scan_directory(root)
    return JSONResponse(data)

from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from ..core.ast_parser import ASTParser

app = FastAPI(title="AetherGraph API", version="0.1.0")
parser = ASTParser()

@app.get("/api/graph")
def get_graph(path: str = "."):
    root = Path(path).resolve()
    data = parser.scan_directory(root)
    return JSONResponse(data)

@app.get("/", response_class=HTMLResponse)
def index():
    return """<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <title>AetherGraph — Visualizador 3D/2D</title>
  <script src="//unpkg.com/3d-force-graph"></script>
  <style>
    * { box-sizing: border-box; }
    body { margin: 0; padding: 0; background: #0b0d12; color: #f8fafc; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; overflow: hidden; }
    header {
      position: absolute; top: 0; left: 0; right: 0; height: 52px; z-index: 50;
      background: rgba(15, 23, 42, 0.85); backdrop-filter: blur(12px);
      border-bottom: 1px solid rgba(148, 163, 184, 0.15);
      display: flex; align-items: center; justify-content: space-between; px: 20px; padding: 0 20px;
    }
    .brand { font-weight: 700; font-size: 14px; color: #38bdf8; display: flex; align-items: center; gap: 8px; }
    .brand span { color: #94a3b8; font-weight: 400; font-size: 11px; }
    .controls { display: flex; align-items: center; gap: 12px; font-size: 11px; }
    .btn {
      background: rgba(30, 41, 59, 0.6); border: 1px solid rgba(148, 163, 184, 0.2);
      color: #cbd5e1; padding: 5px 10px; border-radius: 6px; cursor: pointer; transition: all 0.2s;
    }
    .btn:hover { background: rgba(51, 65, 85, 0.8); color: #fff; }
    .btn.active { border-color: #38bdf8; color: #38bdf8; background: rgba(56, 189, 248, 0.1); }
    #stats { color: #94a3b8; font-size: 11px; }
    #graph-container { width: 100vw; height: 100vh; pt: 52px; }
    #drawer {
      position: absolute; top: 64px; right: 16px; width: 300px; max-height: calc(100vh - 80px);
      background: rgba(15, 23, 42, 0.92); border: 1px solid rgba(148, 163, 184, 0.2);
      border-radius: 10px; padding: 16px; backdrop-filter: blur(16px);
      box-shadow: 0 10px 25px rgba(0,0,0,0.5); display: none; flex-direction: column; gap: 10px; z-index: 40;
    }
    #drawer h4 { margin: 0; color: #f8fafc; font-size: 13px; word-break: break-all; }
    #drawer p { margin: 0; color: #cbd5e1; font-size: 11px; line-height: 1.4; background: rgba(30, 41, 59, 0.5); padding: 8px; border-radius: 6px; }
    .close-btn { align-self: flex-end; background: none; border: none; color: #94a3b8; cursor: pointer; font-size: 12px; }
    .legend { display: flex; gap: 12px; font-size: 10px; color: #94a3b8; }
    .dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; margin-right: 4px; }
  </style>
</head>
<body>
  <header>
    <div class="brand">
      🌌 AetherGraph <span>· Motor AST Determinista</span>
    </div>
    <div class="legend">
      <span><span class="dot" style="background:#38bdf8"></span>Archivo</span>
      <span><span class="dot" style="background:#f59e0b"></span>Clase</span>
      <span><span class="dot" style="background:#a78bfa"></span>Función</span>
    </div>
    <div class="controls">
      <span id="stats">Cargando grafo…</span>
    </div>
  </header>

  <div id="graph-container"></div>

  <div id="drawer">
    <div style="display:flex; justify-content:space-between; align-items:center;">
      <h4 id="node-name">Símbolo</h4>
      <button class="close-btn" onclick="document.getElementById('drawer').style.display='none'">✕</button>
    </div>
    <p id="node-details">Detalles...</p>
    <div style="font-size:10px; color:#64748b;" id="node-id">ID</div>
  </div>

  <script>
    let graphInstance = null;
    fetch('/api/graph')
      .then(res => res.json())
      .then(data => {
        document.getElementById('stats').innerText = `${data.nodes.length} nodos · ${data.links.length} enlaces`;
        
        graphInstance = ForceGraph3D()(document.getElementById('graph-container'))
          .graphData(data)
          .nodeId('id')
          .nodeLabel(n => `${n.name}\n${n.details}`)
          .nodeColor(n => n.color || '#38bdf8')
          .linkColor(l => l.color || 'rgba(148,163,184,0.3)')
          .onNodeClick(node => {
            document.getElementById('node-name').innerText = node.name;
            document.getElementById('node-details').innerText = node.details;
            document.getElementById('node-id').innerText = node.id;
            document.getElementById('drawer').style.display = 'flex';
          });
      })
      .catch(err => {
        document.getElementById('stats').innerText = 'Error al cargar el grafo';
      });
  </script>
</body>
</html>
"""

