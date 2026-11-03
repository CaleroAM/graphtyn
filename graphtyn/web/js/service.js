// Estado real del servicio que sirve el dashboard. Los clientes que lanzan
// `graphtyn mcp` por stdio corren en su propio proceso y no dependen de él.
import { state } from './state.js';
import { loadProjects } from './ui.js';
import { loadGraph } from './graph.js';

const POLL_MS = 10000;
const TIMEOUT_MS = 5000;
let offline = false;

function render(data) {
  const badge = document.getElementById('service-status');
  const label = document.getElementById('service-status-label');
  const banner = document.getElementById('service-offline');
  if (!badge || !label) return;
  badge.classList.toggle('offline', !data);
  if (banner) banner.hidden = !!data;
  if (!data) {
    label.textContent = 'Servicio sin respuesta';
    badge.title = 'El servidor del dashboard no responde. Los agentes que usan graphtyn mcp por stdio no dependen de él.';
    return;
  }
  label.textContent = data.mcp_http ? 'En línea · MCP HTTP' : 'En línea';
  badge.title = `Graphtyn ${data.version} responde. MCP por HTTP (/mcp): ` +
    (data.mcp_http ? 'habilitado.' : 'deshabilitado; configura GRAPHTYN_MCP_TOKEN o tokens por agente.') +
    ' Los agentes que usan graphtyn mcp por stdio no dependen de este servicio.';
}

async function poll() {
  let data = null;
  try {
    const response = await fetch('/api/service', {cache:'no-store', signal:AbortSignal.timeout(TIMEOUT_MS)});
    if (response.ok) data = await response.json();
  } catch (_) { /* sin respuesta */ }
  render(data);
  if (data && offline) {
    loadProjects();
    if (state.activePath) loadGraph();
  }
  offline = !data;
}

export function initServiceStatus() {
  poll();
  setInterval(poll, POLL_MS);
}
