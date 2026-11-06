// Actividad de agentes: qué preguntaron, qué recibieron y por qué. Graphtyn sólo ve lo que
// pasa por él; lo que el agente lee después no llega aquí, y el panel lo dice.
import { state, authHeaders } from './state.js';
import { applyFilter, clearWebFlow } from './graph.js';
import { setView } from './controls.js';

const POLL_MS = 3000;
const RIVER_SECONDS = 600;
const STAGE_KINDS = {E: 'llamada extraída', I: 'llamada inferida', S: 'comparte estado'};
const SOURCE_NAMES = {mcp: 'MCP', 'mcp-http': 'MCP HTTP', hook: 'hook'};
const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));

let timer = null;
let queries = [];
let selectedId = null;
let newestSeen = null;
let polledOnce = false;
let lastSignature = '';
let follow = false;
let requestId = 0;
let focusRetry = null;
let zoomTimers = [];

const panel = () => document.getElementById('activity-panel');
const clock = seconds => new Date(seconds * 1000).toLocaleTimeString([], {hour:'2-digit', minute:'2-digit', second:'2-digit'});

function renderLogging(enabled, retentionDays) {
  const box = document.getElementById('activity-logging');
  const note = document.getElementById('activity-logging-note');
  if (box) { box.checked = enabled; box.disabled = false; }
  if (note) note.textContent = enabled
    ? `Las preguntas se guardan en este equipo y se borran a los ${retentionDays} días.`
    : `Registro apagado para este proyecto: no se guardan consultas nuevas. Las anteriores se borran a los ${retentionDays} días.`;
}

export async function setActivityLogging(enabled) {
  const box = document.getElementById('activity-logging');
  if (box) box.disabled = true;
  try {
    const response = await fetch('/api/agent-activity/settings', {method:'POST',
      headers:authHeaders({'Content-Type':'application/json'}),
      body:JSON.stringify({path:state.activePath, logging:enabled})});
    const data = await response.json();
    if (!response.ok || data.ok === false) throw new Error(data.error || `HTTP ${response.status}`);
  } catch (error) {
    window.alert(`No se pudo cambiar el registro: ${error.message}`);
  }
  lastSignature = '';
  await poll();
}

function renderUsage(usage) {
  const el = document.getElementById('activity-usage');
  if (!el) return;
  if (!usage?.queries) {
    el.innerHTML = `<p class="activity-note">Sin consultas en los últimos ${esc(usage?.days ?? 7)} días. Aparecerán cuando un agente use <code>graph_query_intent</code> o el hook en este proyecto.</p>`;
    return;
  }
  const agents = Object.entries(usage.by_agent || {}).map(([name, count]) => `${esc(name)} ${esc(count)}`).join(' · ');
  const files = (usage.top_files || []).map(([file, count]) => `<li title="${esc(file)}"><span>${esc(file)}</span><b>${esc(count)}</b></li>`).join('');
  el.innerHTML = `<div class="activity-stats">
      <div><b>${esc(usage.queries)}</b><span>consultas</span></div>
      <div title="Graphtyn indicó que la evidencia bastaba (do_not_expand)"><b>${esc(usage.sufficient)}</b><span>suficientes</span></div>
      <div title="El agente pidió ampliar un paquete anterior (extends_context_id)"><b>${esc(usage.extended)}</b><span>ampliadas</span></div>
      <div title="El hook descartó el paquete por falta de evidencia"><b>${esc(usage.not_delivered)}</b><span>no entregadas</span></div>
    </div>
    <p class="activity-note">Últimos ${esc(usage.days)} días · ${agents}</p>
    ${files ? `<details class="activity-files"><summary>Archivos más entregados</summary><ul>${files}</ul></details>` : ''}
    ${renderAfterPackage(usage.after_package)}`;
}

function renderAfterPackage(after) {
  if (!after?.watched) {
    return `<p class="activity-note">Graphtyn sólo ve lo que pasa por él. Con <code>graphtyn tool-guard install --consent</code>, Claude Code registra también lo que lee y busca después de cada paquete.</p>`;
  }
  const outside = (after.top_outside_files || []).map(([file, count]) => `<li title="${esc(file)}"><span>${esc(file)}</span><b>${esc(count)}</b></li>`).join('');
  return `<div class="activity-stats">
      <div title="Consultas tras las que el agente leyó o buscó en los 15 minutos siguientes"><b>${esc(after.followed_by_tools)}</b><span>con lecturas después</span></div>
      <div title="Lecturas de archivos que el paquete no incluía"><b>${esc(after.reads_outside_package)}</b><span>fuera del paquete</span></div>
      <div title="Búsquedas tras un paquete"><b>${esc(after.searches_after)}</b><span>búsquedas después</span></div>
    </div>
    ${outside ? `<details class="activity-files"><summary>Lo que los paquetes no incluían</summary><ul>${outside}</ul></details>` : ''}`;
}

function renderRiver() {
  const el = document.getElementById('activity-river');
  if (!el) return;
  const now = Date.now() / 1000;
  const recent = queries.filter(query => now - query.timestamp <= RIVER_SECONDS);
  const agents = [...new Set(recent.map(query => query.agent || query.source))];
  el.innerHTML = agents.length ? agents.map(agent => `<div class="river-row"><span title="${esc(agent)}">${esc(agent)}</span><div class="river-track">${
    recent.filter(query => (query.agent || query.source) === agent).map(query =>
      `<button type="button" class="river-dot${query.id === selectedId ? ' selected' : ''}" style="left:${(100 - (now - query.timestamp) / RIVER_SECONDS * 100).toFixed(1)}%" title="${esc(clock(query.timestamp))} · ${esc(query.request)}" onclick="selectActivityQuery(${Number(query.id)})"></button>`).join('')
  }</div></div>`).join('') + '<div class="river-axis"><span>hace 10 min</span><span>ahora</span></div>'
    : '<p class="activity-note">Sin consultas en los últimos 10 minutos.</p>';
}

function renderList() {
  const el = document.getElementById('activity-list');
  if (!el) return;
  el.innerHTML = queries.map(query => {
    const status = query.delivered === false ? 'no entregada' : query.extends_context_id ? 'ampliación' : query.do_not_expand ? 'suficiente' : 'parcial';
    return `<button type="button" class="activity-item${query.id === selectedId ? ' selected' : ''}" onclick="selectActivityQuery(${Number(query.id)})">
      <span class="activity-meta">${esc(clock(query.timestamp))} · ${esc(query.agent || query.source)} · ${esc(SOURCE_NAMES[query.source] || query.source)}</span>
      <span class="activity-request">${esc(query.request || '(sin texto)')}</span>
      <span class="activity-meta">${esc(query.intent || '')} · ${(query.entities || []).length} entidades · ${esc(status)}</span>
    </button>`;
  }).join('');
}

function renderDetail() {
  const el = document.getElementById('activity-detail');
  if (!el) return;
  const query = queries.find(item => item.id === selectedId);
  el.hidden = !query;
  if (!query) return;
  const entities = (query.entities || []).map(item => `<li class="why-${esc(item.why?.kind || 'index')}">
      <button type="button" class="activity-entity" data-node-id="${esc(item.id)}" onclick="focusNode(this.dataset.nodeId)" title="Centrar en el grafo">${esc(item.name)}</button> <span class="activity-meta">${esc(item.kind)} · ${esc(item.file)}${item.line ? ':' + esc(item.line) : ''}</span>
      <span class="activity-why">${esc(item.why?.text || 'Registrada sin motivo')}</span></li>`).join('');
  const stages = (query.stages || []).map(item => `<li><strong>${esc(item.caller)}</strong> → <strong>${esc(item.callee)}</strong>
      <span class="activity-meta">${esc(item.file)}${item.line ? ':' + esc(item.line) : ''} · ${esc(STAGE_KINDS[item.kind] || item.kind)}</span></li>`).join('');
  const missing = (query.missing || []).length ? `<p class="activity-note">Falta: ${esc(query.missing.join(', '))}</p>` : '';
  el.innerHTML = `<div class="activity-detail-head"><strong>Lo que recibió</strong>
      <span><button class="btn-link" onclick="focusActivityQuery(${Number(query.id)})">Ver en el grafo</button>
      <button class="btn-link" onclick="resetActivityFocus()">Grafo completo</button></span></div>
    <p class="activity-request">${esc(query.request)}</p>${missing}
    <div id="activity-focus-status" class="activity-note"></div>
    ${entities ? `<div class="help-section">Entidades y por qué entraron</div><ul class="activity-entities">${entities}</ul>` : '<p class="activity-note">Esta consulta se registró antes de guardar sus entidades.</p>'}
    ${stages ? `<div class="help-section">Etapas siguientes (call_outline)</div><ul class="activity-entities">${stages}</ul>` : ''}`;
}

function packageNodeIds(query) {
  const nodes = state.fullData?.nodes || [];
  const ids = new Set(nodes.filter(node => (query.entities || []).some(item => item.id === node.id)).map(node => node.id));
  (query.stages || []).forEach(stage => {
    const match = nodes.find(node => node.name === stage.callee && node.file === stage.file && (!stage.line || node.line === stage.line))
      || nodes.find(node => node.name === stage.callee && node.file === stage.file);
    if (match) ids.add(match.id);
  });
  return ids;
}

// Al filtrar, la simulación recoloca los nodos durante unos segundos: encuadra hasta que se asienten.
function zoomWhileSettling(padding) {
  zoomTimers.forEach(clearTimeout);
  zoomTimers = [500, 1500, 3000].map(delay => setTimeout(() => state.graphInst?.zoomToFit?.(400, padding), delay));
}

function showPackage(query) {
  const ids = packageNodeIds(query);
  const status = document.getElementById('activity-focus-status');
  const expected = (query.entities || []).length + (query.stages || []).length;
  if (!ids.size) {
    if (status) status.textContent = 'Ninguna entidad está en el grafo actual; el índice pudo cambiar desde la consulta.';
    return;
  }
  state.webFlowNodeIds = ids;
  const reset = document.getElementById('reset-web-flow');
  if (reset) reset.style.display = 'block';
  // Sin esto, las entidades sin enlaces entre sí se repelen hasta dejar el resto diminuto.
  state.graphInst?.d3Force?.('x', d3.forceX().strength(0.12));
  state.graphInst?.d3Force?.('y', d3.forceY().strength(0.12));
  applyFilter();
  zoomWhileSettling(60);
  if (status) status.textContent = `${ids.size} nodos del paquete en el grafo (de ${expected} entidades y etapas).`;
}

export function focusActivityQuery(id) {
  const query = queries.find(item => item.id === id);
  if (!query) return;
  clearInterval(focusRetry);
  if (state.activeView === 'code' && state.fullData?.nodes?.length) { showPackage(query); return; }
  if (state.activeView !== 'code') setView('code');
  let attempts = 0;
  focusRetry = setInterval(() => {
    attempts += 1;
    if (state.activeView === 'code' && state.graphInst && state.fullData?.nodes?.length) {
      clearInterval(focusRetry);
      showPackage(query);
    } else if (attempts > 60) clearInterval(focusRetry);
  }, 500);
}

export function resetActivityFocus() {
  clearInterval(focusRetry);
  clearWebFlow();
  zoomWhileSettling(40);
  const status = document.getElementById('activity-focus-status');
  if (status) status.textContent = '';
}

export function selectActivityQuery(id) {
  selectedId = id;
  renderRiver(); renderList(); renderDetail();
}

export function setActivityFollow(checked) {
  follow = checked;
  if (follow && queries[0]) { selectActivityQuery(queries[0].id); focusActivityQuery(queries[0].id); }
}

async function poll() {
  if (!state.activePath) return;
  const current = ++requestId;
  const path = state.activePath;
  try {
    const response = await fetch('/api/agent-activity?path=' + encodeURIComponent(path), {headers:authHeaders(), cache:'no-store'});
    const data = await response.json();
    if (current !== requestId) return;
    if (!response.ok || data.ok === false) throw new Error(data.error || `HTTP ${response.status}`);
    // Redibujar sólo si cambió: si no, cada sondeo perdería la selección de texto del panel.
    const signature = JSON.stringify([data.queries, data.usage]);
    const changed = signature !== lastSignature;
    lastSignature = signature;
    queries = data.queries || [];
    renderRiver();
    if (changed) { renderUsage(data.usage); renderList(); renderLogging(data.logging !== false, data.retention_days); }
    const newest = queries[0]?.id ?? null;
    if (follow && polledOnce && newest !== null && newest !== newestSeen) {
      selectActivityQuery(newest);
      focusActivityQuery(newest);
    } else if (changed && selectedId !== null) {
      renderDetail();
    }
    newestSeen = newest;
    polledOnce = true;
  } catch (error) {
    if (current !== requestId) return;
    const el = document.getElementById('activity-usage');
    if (el) el.innerHTML = `<p class="activity-note">No se pudo cargar la actividad: ${esc(error.message)}</p>`;
  }
}

// El panel reserva su sitio: el lienzo se encoge para que no tape el paquete enfocado.
function fitGraphToContainer() {
  // Espera a la transición de 0,25 s del contenedor, igual que los paneles laterales.
  setTimeout(() => state.graphInst?.width?.(document.getElementById('graph-container').clientWidth), 260);
}

export function toggleActivityPanel(force) {
  const el = panel();
  if (!el) return;
  const open = typeof force === 'boolean' ? force : el.hidden;
  el.hidden = !open;
  document.body.classList.toggle('activity-open', open);
  fitGraphToContainer();
  clearInterval(timer);
  timer = null;
  if (open) { poll(); timer = setInterval(poll, POLL_MS); }
}

// Las consultas son de cada proyecto: al cambiarlo, el panel no debe seguir mostrando las del anterior.
export function resetActivityForProject() {
  queries = []; selectedId = null; newestSeen = null; polledOnce = false; lastSignature = '';
  clearInterval(focusRetry);
  renderRiver(); renderList(); renderDetail();
  if (!panel()?.hidden) poll();
}
