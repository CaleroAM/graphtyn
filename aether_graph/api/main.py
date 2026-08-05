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
<html>
<head>
  <title>AetherGraph — Visualizer</title>
  <script src="//unpkg.com/3d-force-graph"></script>
  <style>
    body { margin: 0; background: #0b0d12; color: #f8fafc; font-family: monospace; }
    #header { padding: 12px 20px; background: rgba(15,23,42,0.8); border-bottom: 1px solid #1e293b; display: flex; justify-content: space-between; }
    #3d-graph { width: 100vw; height: calc(100vh - 50px); }
  </style>
</head>
<body>
  <div id="header">
    <div><strong>AetherGraph</strong> <span>· Zero-Token AST Agent Graph</span></div>
    <div id="stats">Cargando...</div>
  </div>
  <div id="3d-graph"></div>

  <script>
    fetch('/api/graph')
      .then(res => res.json())
      .then(data => {
        document.getElementById('stats').innerText = `${data.nodes.length} nodos · ${data.links.length} enlaces`;
        const Graph = ForceGraph3D()
          (document.getElementById('3d-graph'))
            .graphData(data)
            .nodeId('id')
            .nodeLabel(n => `${n.name}\n${n.details}`)
            .nodeColor(n => n.color || '#38bdf8')
            .linkColor(l => l.color || 'rgba(148,163,184,0.3)');
      });
  </script>
</body>
</html>
"""
