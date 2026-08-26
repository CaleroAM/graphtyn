import { state } from './state.js';
import { setView } from './controls.js';
import { focusNode } from './graph.js';

const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const arg = value => encodeURIComponent(String(value ?? '')).replace(/'/g, '%27');
const AGENT_COLORS = ['#22d3ee','#f59e0b','#a78bfa','#34d399','#fb7185','#60a5fa','#f97316','#c084fc','#2dd4bf','#e879f9','#84cc16','#facc15'];
const agentColor = value => AGENT_COLORS[Array.from(String(value || '')).reduce((sum, char, index) => sum + (index + 1) * char.codePointAt(0), 0) % AGENT_COLORS.length];
let historicalDiscovery = null;

function headers() {
  const token = document.getElementById('memory-token')?.value.trim() || localStorage.getItem('graphtyn-memory-token') || '';
  if (token) localStorage.setItem('graphtyn-memory-token', token);
  return {'Content-Type':'application/json', ...(token ? {'Authorization':`Bearer ${token}`} : {})};
}

async function request(url, options={}) {
  const response = await fetch(url, {...options, headers:{...headers(), ...(options.headers || {})}});
  const data = await response.json();
  if (!response.ok || data.ok === false) throw new Error(data.error || `HTTP ${response.status}`);
  return data;
}

export function openMemoryPanel() {
  document.getElementById('modal-memory').classList.add('show');
  const saved = localStorage.getItem('graphtyn-memory-token');
  if (saved) document.getElementById('memory-token').value = saved;
  loadHistoricalSources();
  loadMemoryOverview();
}

async function loadHistoricalSources() {
  try {
    const data = await request('/api/v1/imports/sources');
    const list = document.getElementById('memory-import-providers');
    if (list) list.innerHTML = (data.providers || []).map(value => `<option value="${esc(value)}"></option>`).join('');
    const provider = document.getElementById('memory-import-provider');
    if (provider && !provider.value && data.providers?.length) provider.value = data.providers[0];
  } catch (_) { /* El campo sigue aceptando adaptadores personalizados. */ }
}

function historicalInput() {
  return {provider:document.getElementById('memory-import-provider').value.trim(),
          source:document.getElementById('memory-import-source').value.trim()};
}

export async function saveHistoricalSource() {
  const output = document.getElementById('memory-import-status'), value = historicalInput();
  if (!value.provider || !value.source) { output.textContent = 'Proveedor y fuente son obligatorios.'; return; }
  try { await request('/api/v1/imports/sources', {method:'POST', body:JSON.stringify(value)});
    output.textContent = 'Fuente guardada.'; await loadHistoricalSources();
  } catch (error) { output.textContent = `No se pudo guardar: ${error.message}`; }
}

export async function testHistoricalSource() {
  const output = document.getElementById('memory-import-status'), value = historicalInput();
  output.textContent = 'Probando fuente sin modificarla…';
  try { const data = await request('/api/v1/imports/sources/test', {method:'POST', body:JSON.stringify(value)});
    output.textContent = `${data.sessions} sesiones · ${data.messages} mensajes · ${data.projects} proyectos · ${(data.errors || []).length} errores`;
  } catch (error) { output.textContent = `Conexión fallida: ${error.message}`; }
}

export async function removeHistoricalSource() {
  const output = document.getElementById('memory-import-status'), value = historicalInput();
  if (!confirm('¿Eliminar esta fuente de la configuración? Los historiales originales no se tocarán.')) return;
  try { await request(`/api/v1/imports/sources?provider=${encodeURIComponent(value.provider)}&source=${encodeURIComponent(value.source)}`, {method:'DELETE'});
    output.textContent = 'Fuente eliminada de la configuración.';
  } catch (error) { output.textContent = `No se pudo eliminar: ${error.message}`; }
}

export async function saveMemoryAlias() {
  const alias = document.getElementById('memory-alias').value.trim();
  const canonical = document.getElementById('memory-canonical').value.trim();
  const output = document.getElementById('memory-import-status');
  if (!state.activePath || !alias || !canonical) { output.textContent = 'Proyecto, alias e identidad son obligatorios.'; return; }
  try { await request('/api/v1/memory/aliases', {method:'POST', body:JSON.stringify({path:state.activePath, alias, canonical})});
    output.textContent = `Alias ${alias} → ${canonical} guardado.`;
  } catch (error) { output.textContent = `No se pudo guardar el alias: ${error.message}`; }
}

export function closeMemoryPanel() { document.getElementById('modal-memory').classList.remove('show'); }

async function waitImportJob(jobId) {
  for (;;) {
    const data = await request(`/api/v1/imports/${encodeURIComponent(jobId)}`);
    const job = data.job;
    document.getElementById('memory-import-status').textContent = `${job.message || job.status} · ${job.progress}%`;
    if (['completed','failed','cancelled'].includes(job.status)) return job;
    await new Promise(resolve => setTimeout(resolve, 350));
  }
}

export async function discoverHistoricalMemory() {
  const output = document.getElementById('memory-import-status');
  const provider = document.getElementById('memory-import-provider').value;
  const source = document.getElementById('memory-import-source').value.trim();
  output.textContent = 'Descubriendo historiales sin modificar la memoria…';
  try {
    const data = await request('/api/v1/imports/discover', {method:'POST', body:JSON.stringify({provider, sources:source ? [source] : []})});
    const job = await waitImportJob(data.job.id);
    if (job.status !== 'completed') throw new Error(job.error || job.status);
    historicalDiscovery = job;
    const result = job.result || {};
    output.textContent = `${result.count || 0} sesiones encontradas · ${(result.errors || []).length} errores · revise antes de importar`;
    document.getElementById('memory-import-apply').disabled = !(result.sessions || []).length;
  } catch (error) { output.textContent = `No se pudo descubrir: ${error.message}`; }
}

export async function applyHistoricalMemory() {
  const output = document.getElementById('memory-import-status');
  if (!state.activePath || !historicalDiscovery) { output.textContent = 'Selecciona proyecto y ejecuta Previsualizar.'; return; }
  if (!confirm('¿Autorizar la importación saneada de estas conversaciones al proyecto seleccionado?')) return;
  output.textContent = 'Importando, compactando y generando embeddings…';
  try {
    const data = await request('/api/v1/imports', {method:'POST', body:JSON.stringify({
      path:state.activePath, discovery_job_id:historicalDiscovery.id, consent:true, provider:'deterministic'})});
    const job = await waitImportJob(data.job.id);
    if (job.status !== 'completed') throw new Error(job.error || job.status);
    const result = job.result || {};
    output.textContent = `${(result.imported || []).length} importadas · ${(result.reused || []).length} ya existentes · ${(result.ambiguous || []).length} ambiguas · ${(result.errors || []).length} errores`;
    await loadMemoryOverview();
  } catch (error) { output.textContent = `No se pudo importar: ${error.message}`; }
}

export async function loadMemoryOverview() {
  const status = document.getElementById('memory-status');
  if (!state.activePath) { status.textContent = 'Selecciona un proyecto.'; return; }
    status.textContent = 'Consultando memoria…';
    try {
      const path = encodeURIComponent(state.activePath);
      const [info, sessions] = await Promise.all([
        request(`/api/memory/status?path=${path}`), request(`/api/memory/sessions?path=${path}&limit=20`)
      ]);
      let freshness = '';
      if (info.last_capture_at) {
        const days = (Date.now() / 1000 - info.last_capture_at) / 86400;
        freshness = days < 1 ? ' · capturado hoy' : ` · última captura: hace ${Math.floor(days)} día${days >= 2 ? 's' : ''}`;
      }
      status.textContent = `${info.memories} memorias · ${info.sessions} sesiones · ${info.agents} agentes · ${info.embedding_provider}${freshness}`;
    const legend = document.getElementById('memory-agent-legend');
    if (legend) legend.innerHTML = '<div class="memory-empty">Abre el mapa para ver la atribución por agente.</div>';
    document.getElementById('memory-sessions').innerHTML = sessions.sessions.length ? sessions.sessions.map(item => `
      <article class="memory-card memory-session-card" data-session-id="${esc(item.id)}" onclick="openSessionDetail(this.dataset.sessionId)">
        <div class="memory-card-head"><span>${esc(item.agent_id)}</span><span class="memory-pill">${esc(item.status)}</span></div>
        <div class="memory-card-content">${esc(item.task)}</div>
        <div class="memory-card-meta">${esc(item.branch || 'sin rama')} · ${item.memories} memorias · ver detalle →</div></article>`).join('') : '<div class="memory-empty">Sin sesiones registradas.</div>';
  } catch (error) { status.textContent = `No se pudo cargar: ${error.message}`; }
}

export async function showSharedMemoryGraph() {
  const status = document.getElementById('memory-status');
  if (!state.activePath || !state.graphInst) { status.textContent = 'Selecciona un proyecto y espera a que cargue el grafo.'; return; }
  status.textContent = 'Construyendo mapa de autoría y recuperación…';
  try {
    const agent = document.getElementById('memory-agent').value.trim() || 'dashboard';
    const data = await request(`/api/memory/graph?path=${encodeURIComponent(state.activePath)}&requester_agent=${encodeURIComponent(agent)}&limit=400`);
    state.activeView = 'memory';
    state.fullData = {nodes:data.nodes || [], links:data.links || []};
    state.selectedNode = null; state.selectedNeighbors = null;
    state.graphInst.graphData(state.fullData);
    setTimeout(() => state.graphInst?.zoomToFit?.(700, 55), 80);
    const legend = document.getElementById('memory-agent-legend');
    if (legend) {
      const keyHtml = item => `<span class="memory-agent-key"><i style="background:${esc(item.color)}"></i>${esc(item.id)}</span>`;
      const html = (data.agents || []).map(keyHtml).join('')
        + ((data.consulters || []).length ? '<span class="memory-agent-key">· sólo consulta:</span>'
          + data.consulters.map(keyHtml).join('') : '');
      legend.innerHTML = html || '<div class="memory-empty">No hay agentes atribuidos.</div>';
    }
    status.textContent = `${data.nodes.length} nodos de memoria · ${data.links.length} relaciones · colores por agente`;
    closeMemoryPanel();
  } catch (error) { status.textContent = `No se pudo generar el mapa: ${error.message}`; }
}

export async function searchSharedMemory() {
  const query = document.getElementById('memory-query').value.trim();
  const output = document.getElementById('memory-results');
  if (!state.activePath || !query) { output.innerHTML = '<div class="memory-empty">Selecciona proyecto y escribe una consulta.</div>'; return; }
  output.innerHTML = '<div class="memory-empty">Buscando contexto híbrido…</div>';
  try {
    const agent = document.getElementById('memory-agent').value.trim() || 'dashboard';
    let data;
    if (document.getElementById('memory-search-all')?.checked) {
      let paths = [state.activePath];
      try {
        const projects = await (await fetch('/api/projects')).json();
        const extra = (Array.isArray(projects) ? projects : [])
          .map(p => p.path).filter(Boolean);
        paths = [...new Set([...paths, ...extra])];
      } catch (_) { /* federado con el espacio activo si falla el listado */ }
      data = await request('/api/memory/search-all', {method:'POST', body:JSON.stringify({paths, query,
        requester_agent:agent, include_stale:document.getElementById('memory-include-stale').checked, limit:12})});
    } else {
      data = await request('/api/memory/search', {method:'POST', body:JSON.stringify({path:state.activePath, query,
        requester_agent:agent, include_stale:document.getElementById('memory-include-stale').checked, limit:12})});
    }
    output.innerHTML = data.results.length ? data.results.map(renderMemory).join('') : '<div class="memory-empty">No se encontraron recuerdos para esta consulta.</div>';
  } catch (error) { output.innerHTML = `<div class="memory-empty">No se pudo buscar: ${esc(error.message)}</div>`; }
}

export async function openSessionDetail(sessionId) {
  sessionId = decodeURIComponent(sessionId);
  const box = document.getElementById('memory-sessions');
  if (!box) return;
  box.innerHTML = '<div class="memory-empty">Cargando sesión…</div>';
  try {
    const data = await request(`/api/memory/session?path=${encodeURIComponent(state.activePath)}&session_id=${arg(sessionId)}`);
    const s = data.session || {};
    const msgs = (data.messages || []).map(m => `
      <article class="memory-card memory-msg"><span class="memory-msg-role">${esc(m.role)}</span>
      <div class="memory-card-content">${esc(m.content)}</div></article>`).join('');
    const mems = (data.memories || []).map(m => `
      <div class="memory-card-meta"><span class="memory-author-dot" style="background:${agentColor(m.agent_id)}"></span>${esc(m.title)} · ${esc(m.kind)}${m.stale ? ' · OBSOLETO' : ''}</div>`).join('');
    box.innerHTML = `
      <button class="btn-link" onclick="loadMemoryOverview()">← Volver a sesiones</button>
      <article class="memory-card"><div class="memory-card-head"><span>${esc(s.agent_id)}</span><span class="memory-pill">${esc(s.status)}</span></div>
        <div class="memory-card-content">${esc(s.task)}</div>
        <div class="memory-card-meta">${esc(s.branch || 'sin rama')} · ${(data.messages || []).length} mensajes · ${(data.memories || []).length} memorias</div></article>
      ${mems ? `<h4 class="memory-section-title">Memorias de la sesión</h4>${mems}` : ''}
      ${msgs ? `<h4 class="memory-section-title">Conversación</h4>${msgs}` : ''}`;
  } catch (error) {
    box.innerHTML = `<div class="memory-empty">No se pudo abrir la sesión: ${esc(error.message)}</div><button class="btn-link" onclick="loadMemoryOverview()">← Volver a sesiones</button>`;
  }
}

function renderMemory(item) {
  const revision = item.stale ? ' · OBSOLETO' : '';
  return `<article class="memory-card ${item.stale ? 'stale' : ''}" data-memory-id="${esc(item.id)}">
    <div class="memory-card-head"><span>${esc(item.title)}</span><span class="memory-pill">${esc(item.kind)}</span></div>
    <div class="memory-card-meta"><span class="memory-author-dot" style="background:${agentColor(item.agent_id)}"></span>${esc(item.agent_id)} · ${esc(item.session_id)} · ${esc(item.branch || 'sin rama')}${revision}</div>
    <div class="memory-card-content">${esc(item.content)}</div>
    <div class="memory-card-meta">score ${esc(item.score)} · ${esc(item.retrieval)}${item.store ? ' · ' + esc(item.store.split('/').pop()) : ''}</div>
    <div class="memory-card-actions"><button class="btn-link" onclick="focusMemoryNode('${arg(item.id)}')">Ver nodo</button><button class="btn-link" onclick="correctSharedMemory('${arg(item.id)}','${arg(item.session_id)}')">Corregir</button><button class="btn-link" onclick="forgetSharedMemory('${arg(item.id)}','${arg(item.agent_id)}')">Olvidar</button></div>
  </article>`;
}

export async function correctSharedMemory(memoryId, sessionId) {
  memoryId = decodeURIComponent(memoryId); sessionId = decodeURIComponent(sessionId);
  const title = prompt('Título de la corrección:');
  if (!title) return;
  const content = prompt('Contenido corregido:');
  if (!content) return;
  try {
    await request('/api/memory/correct', {method:'POST', body:JSON.stringify({path:state.activePath, memory_id:memoryId, session_id:sessionId, title, content})});
    await searchSharedMemory(); await loadMemoryOverview();
  } catch (error) { alert(`No se pudo corregir: ${error.message}`); }
}

export async function forgetSharedMemory(memoryId, author) {
  memoryId = decodeURIComponent(memoryId); author = decodeURIComponent(author);
  const requester = document.getElementById('memory-agent').value.trim();
  if (requester !== author) { alert(`Sólo ${author} puede olvidar esta memoria.`); return; }
  if (!confirm('¿Invalidar esta memoria? La auditoría se conservará.')) return;
  try {
    await request('/api/memory/forget', {method:'POST', body:JSON.stringify({path:state.activePath, memory_id:memoryId, requester_agent:requester})});
    await searchSharedMemory(); await loadMemoryOverview();
  } catch (error) { alert(`No se pudo olvidar: ${error.message}`); }
}

export async function linkAgentProfile() {
  const wsInput = document.getElementById('memory-agent-ws');
  const workspace = wsInput?.value.trim();
  const status = document.getElementById('memory-status');
  if (!state.activePath || !workspace) { if (status) status.textContent = 'Selecciona un proyecto y escribe la ruta del workspace del agente.'; return; }
  if (status) status.textContent = 'Leyendo identidad del agente…';
  try {
    const data = await request('/api/memory/agent-profile', {method:'POST', body:JSON.stringify({path:state.activePath, agent_workspace:workspace})});
    const sel = document.getElementById('memory-agent');
    if (sel && !sel.value.trim()) sel.value = data.agent_id;
    if (status) status.textContent = `Agente vinculado: ${data.name} (${data.agent_id})${data.role ? ' · ' + data.role : ''}`;
    await loadMemoryOverview();
  } catch (error) { if (status) status.textContent = `No se pudo vincular el agente: ${error.message}`; }
}

export async function focusMemoryNode(memoryId) {
  closeMemoryPanel();
  const nodeId = 'memory:' + decodeURIComponent(memoryId);
  const findNode = () => state.graphInst && typeof state.graphInst.graphData === 'function'
    ? (state.graphInst.graphData().nodes || []).find(n => n.id === nodeId) : null;
  if (state.activeView !== 'memory') setView('memory');
  let node = findNode(), tries = 0;
  while (!node && tries < 50) { await new Promise(r => setTimeout(r, 100)); node = findNode(); tries++; }
  if (!node) { alert('No se encontró el nodo en el mapa de memoria. Abre la pestaña "Memoria del proyecto" y vuelve a intentarlo.'); return; }
  state.selectedNode = node;
  const links = state.fullData?.links || [];
  state.selectedNeighbors = new Set([node.id]);
  for (const l of links) {
    if (l.source === nodeId || l.target === nodeId || l.source?.id === nodeId || l.target?.id === nodeId) {
      state.selectedNeighbors.add(l.source?.id ?? l.source);
      state.selectedNeighbors.add(l.target?.id ?? l.target);
    }
  }
  focusNode(nodeId);
}
