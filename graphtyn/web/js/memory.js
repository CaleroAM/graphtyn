import { state, getMemoryColor } from './state.js';
import { setView } from './controls.js';
import { destroyGraph, focusNode, loadGraph, refreshStyleInPlace, updateMemoryFocusBanner } from './graph.js';
import { buildPulseSim } from './sim.js';

const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const arg = value => encodeURIComponent(String(value ?? '')).replace(/'/g, '%27');
const AGENT_COLORS = ['#22d3ee','#f59e0b','#a78bfa','#34d399','#fb7185','#60a5fa','#f97316','#c084fc','#2dd4bf','#e879f9','#84cc16','#facc15'];
const agentColor = value => AGENT_COLORS[Array.from(String(value || '')).reduce((sum, char, index) => sum + (index + 1) * char.codePointAt(0), 0) % AGENT_COLORS.length];
let historicalDiscovery = null;
let sessionOffset = 0;

function renderMemorySessions(data, append = false) {
  const box = document.getElementById('memory-sessions');
  if (!box) return;
  const items = (data.sessions || []).map(item => `
    <article class="memory-card memory-session-card" data-session-id="${esc(item.id)}" onclick="openSessionDetail(this.dataset.sessionId)">
      <div class="memory-card-head"><span>${esc(item.agent_id)}</span><span class="memory-pill">${item.id.startsWith('ses_ext_') ? 'histórica · ' : ''}${esc(item.status)}</span></div>
      <div class="memory-card-content">${esc(item.task || 'Sesión de conversación')}</div>
      <div class="memory-card-meta">${esc(item.branch || 'sin rama')} · ${item.message_count || 0} mensajes · ${item.topic_count || 0} temas · <code>${esc(item.reference || '')}</code> · ver detalle →</div></article>`).join('');
  if (!append) box.innerHTML = '';
  box.insertAdjacentHTML('beforeend', items || (!append ? '<div class="memory-empty">Sin sesiones registradas.</div>' : ''));
  const more = document.getElementById('memory-sessions-more');
  if (more) { more.hidden = data.next_offset === null || data.next_offset === undefined; more.dataset.offset = data.next_offset ?? ''; }
  const count = document.getElementById('memory-sessions-count');
  if (count) count.textContent = `${Math.min((data.offset || 0) + (data.sessions || []).length, data.total || 0)} de ${data.total || 0}`;
}

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
  initializeTopics();
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
    if (provider && !provider.value && data.providers?.length)
      provider.value = data.providers.includes('opencode') ? 'opencode' : data.providers[0];
  } catch (_) { /* El campo sigue aceptando adaptadores personalizados. */ }
}

function historicalInput() {
  return {provider:document.getElementById('memory-import-provider').value.trim(),
          source:document.getElementById('memory-import-source').value.trim()};
}

export async function saveHistoricalSource() {
  const output = document.getElementById('memory-import-status'), value = historicalInput();
  if (!value.provider || !value.source) { output.textContent = 'Proveedor y fuente son obligatorios.'; return; }
  try { await request('/api/v1/imports/sources', {method:'POST', body:JSON.stringify({...value, path:state.activePath})});
    output.textContent = 'Fuente guardada para este espacio.'; await loadHistoricalSources();
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
    const data = await request('/api/v1/imports/discover', {method:'POST', body:JSON.stringify({
      provider, sources:source ? [source] : [], ...(!source && state.activePath ? {path:state.activePath} : {})})});
    const job = await waitImportJob(data.job.id);
    if (job.status !== 'completed') throw new Error(job.error || job.status);
    historicalDiscovery = job;
    const result = job.result || {};
    const sessions = result.sessions || [];
    const exactProjectMatches = sessions.filter(item => item.workspace && state.activePath &&
      String(item.workspace).replace(/\\/g, '/').replace(/\/$/, '') ===
      String(state.activePath).replace(/\\/g, '/').replace(/\/$/, '')).length;
    output.textContent = `${result.count || 0} sesiones encontradas · ${exactProjectMatches} con ruta exacta de este proyecto · ${(result.errors || []).length} errores · revise antes de importar`;
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

export async function loadMemoryOverview(append = false) {
  const status = document.getElementById('memory-status');
  if (!state.activePath) { status.textContent = 'Selecciona un proyecto.'; return; }
    if (!append) sessionOffset = 0;
    status.textContent = 'Consultando memoria…';
    try {
      const path = encodeURIComponent(state.activePath);
      const query = document.getElementById('memory-session-query')?.value.trim() || '';
      const requester = document.getElementById('memory-agent')?.value.trim() || 'dashboard';
      const [info, sessions] = await Promise.all([
        request(`/api/memory/status?path=${path}`), request(`/api/memory/sessions?path=${path}&limit=100&offset=${sessionOffset}&query=${encodeURIComponent(query)}&requester_agent=${encodeURIComponent(requester)}`)
      ]);
      let freshness = '';
      if (info.last_capture_at) {
        const days = (Date.now() / 1000 - info.last_capture_at) / 86400;
        freshness = days < 1 ? ' · capturado hoy' : ` · última captura: hace ${Math.floor(days)} día${days >= 2 ? 's' : ''}`;
      }
      const topicAi = info.topic_enrichment?.configured
        ? `IA temática local: ${info.topic_enrichment.model}${info.topic_enrichment.coverage ? ` · ${info.topic_enrichment.coverage.enriched}/${info.topic_enrichment.coverage.discovered} temas enriquecidos · ${info.topic_enrichment.coverage.pending || 0} pendientes` : ''}${info.topic_enrichment.enriched_events ? ` · ${info.topic_enrichment.enriched_events} enriquecimientos` : ''}${info.topic_enrichment.reviewed_candidates ? ` · ${info.topic_enrichment.reviewed_candidates} candidatas revisadas` : ''}${!info.topic_enrichment.enriched_events && !info.topic_enrichment.reviewed_candidates ? ' · pendiente de ejecutar' : ''}`
        : 'IA temática: determinista';
      const watcher = (info.sync_watchers || []).find(item => item.active);
      const watchButton = document.getElementById('memory-watch-btn');
      if (watchButton) {
        watchButton.textContent = watcher ? 'Desactivar captura continua' : 'Activar captura continua';
        watchButton.dataset.enabled = watcher ? 'true' : 'false';
        watchButton.title = watcher ? `Activa · intervalo ${watcher.interval || 30}s` : 'La captura queda asociada a este espacio';
      }
      const failed = info.topic_enrichment?.coverage?.failed || 0;
      const failureText = failed ? ` · ${failed} fallos de IA` : '';
      const capture = info.continuous_capture_active ? ' · captura continua activa' : ' · captura continua inactiva';
      const lastRetrieval = info.last_context_retrieval;
      const retrieval = lastRetrieval
        ? ` · último contexto consultado por ${lastRetrieval.agent_id || 'agente'} · ${lastRetrieval.recent_activity_count || 0} actualizaciones recientes`
        : ' · ningún agente ha consultado el contexto todavía';
      status.textContent = `${info.memories} memorias · ${info.sessions} sesiones · ${info.agents} agentes · ${info.embedding_provider}${freshness}${capture}${retrieval}${failureText} · ${topicAi}`;
      const integrationStatus = document.getElementById('memory-integration-status');
      if (integrationStatus) {
      const integration = info.project_integrations || {};
      const clients = integration.clients || [];
      const verifyButton = document.getElementById('memory-mcp-verify-btn');
      if (verifyButton) verifyButton.hidden = state.activeSpaceType === 'agent_brain'
        || state.activeSpaceType === 'agent'
        || !clients.some(item => item.status === 'configured' || item.status === 'command_unavailable');
        const stateLabel = item => ({
          configured: `MCP configurado${item.restart_recommended ? ' · recarga el cliente' : ''}`,
          command_unavailable: 'config presente; Graphtyn no aparece en el PATH de este dashboard',
          verified: 'MCP verificado',
          dynamic_scope: 'usa selección dinámica del proyecto',
          instructions_only: 'instrucciones instaladas; MCP manual',
          needs_review: `requiere revisión: ${item.note || 'conflicto de configuración'}`,
          missing_or_mismatched: 'configuración MCP falta o apunta a otra ruta',
          missing: 'archivo MCP ausente',
          removed: 'desconectado',
        }[item.status] || item.status || 'desconocido');
        if (state.activeSpaceType === 'agent_brain' || state.activeSpaceType === 'agent') {
          integrationStatus.textContent = 'Las conexiones MCP por proyecto se configuran desde la carpeta del repositorio; este es un cerebro privado.';
        } else if (!integration.project_id) {
          integrationStatus.textContent = 'Sin identidad de proyecto persistida. Registra el proyecto o instala un agente para asignar su ID.';
        } else {
          const connections = clients.length
            ? clients.map(item => `${item.platform}: ${stateLabel(item)}`).join(' · ')
            : 'sin clientes MCP configurados; usa graphtyn agent-install <cliente> --path .';
          const verification = integration.mcp_verification?.ok
            ? `Handshake del servidor: correcto · ${integration.mcp_verification.tool_count} herramientas`
            : 'Handshake del servidor: pendiente de prueba';
          integrationStatus.textContent = `Proyecto ${integration.project_id} · ${integration.mcp_server || ''} · ${connections}. ${verification}. Si el cliente no muestra las herramientas, recárgalo. Captura e importación histórica son independientes.`;
        }
      }
    const legend = document.getElementById('memory-agent-legend');
    if (legend) legend.innerHTML = '<div class="memory-empty">Abre el mapa para ver la atribución por agente.</div>';
    renderMemorySessions(sessions, append);
  } catch (error) { status.textContent = `No se pudo cargar: ${error.message}`; }
}

export async function verifyProjectMcp() {
  const button = document.getElementById('memory-mcp-verify-btn');
  const status = document.getElementById('memory-integration-status');
  if (!state.activePath) { if (status) status.textContent = 'Selecciona un proyecto para probar MCP.'; return; }
  if (button) { button.disabled = true; button.textContent = 'Probando MCP…'; }
  if (status) status.textContent = 'Iniciando servidor Graphtyn y comprobando handshake…';
  try {
    const result = await request('/api/memory/integrations/verify', {
      method: 'POST', body: JSON.stringify({path: state.activePath})
    });
    if (status) status.textContent = `Handshake correcto · ${result.tool_count} herramientas · ${result.server}. Si el cliente aún no las muestra, recárgalo.`;
    await loadMemoryOverview();
  } catch (error) {
    if (status) status.textContent = `No se pudo verificar el servidor MCP: ${error.message}`;
  } finally {
    if (button) { button.disabled = false; button.textContent = 'Probar servidor MCP del proyecto'; }
  }
}

async function runMemorySync(allSpaces) {
  const output = document.getElementById('memory-status');
  if (!state.activePath && !allSpaces) { output.textContent = 'Selecciona un espacio de memoria.'; return; }
  const button = document.getElementById(allSpaces ? 'memory-sync-all-btn' : 'memory-sync-btn');
  if (button) { button.disabled = true; button.textContent = allSpaces ? 'Actualizando espacios…' : 'Actualizando memoria…'; }
  try {
    const response = await request('/api/memory/sync', {method:'POST', body:JSON.stringify({
      path:state.activePath, all_spaces:allSpaces, consent:true, provider_model:'auto', enrich:true})});
    const job = await waitImportJob(response.job.id);
    if (job.status !== 'completed') throw new Error(job.error || job.status);
    const results = (job.result || {}).spaces || [];
    const errors = results.reduce((total, item) => total + (item.errors || []).length, 0);
    output.textContent = `${results.length || 1} espacio${results.length === 1 ? '' : 's'} actualizado${results.length === 1 ? '' : 's'} · ${errors} errores · IA incremental aplicada`;
    await loadMemoryOverview();
  } catch (error) { output.textContent = `No se pudo actualizar: ${error.message}`; }
  finally { if (button) { button.disabled = false; button.textContent = allSpaces ? 'Actualizar todos los espacios' : 'Actualizar memoria'; } }
}

export function syncMemorySpace() { return runMemorySync(false); }
export function syncAllMemorySpaces() { return runMemorySync(true); }

export async function retryMemoryEnrichment() {
  const output = document.getElementById('memory-status');
  if (!state.activePath) { output.textContent = 'Selecciona un espacio de memoria.'; return; }
  const button = document.getElementById('memory-enrich-retry-btn');
  if (button) { button.disabled = true; button.textContent = 'Reintentando IA…'; }
  try {
    const response = await request('/api/memory/topics/enrich', {method:'POST', body:JSON.stringify({
      path:state.activePath, consent:true, provider:'ollama', force:true, retry_failed:true})});
    const job = await waitImportJob(response.job.id);
    if (job.status !== 'completed') throw new Error(job.error || job.status);
    const result = job.result || {};
    output.textContent = `IA reintentada · ${result.ai_enriched || 0} enriquecidos · ${result.failed || 0} fallos restantes`;
    await loadMemoryOverview();
  } catch (error) { output.textContent = `No se pudo reintentar la IA: ${error.message}`; }
  finally { if (button) { button.disabled = false; button.textContent = 'Reintentar IA'; } }
}

export async function toggleMemoryWatch() {
  if (!state.activePath) { document.getElementById('memory-status').textContent = 'Selecciona un espacio de memoria.'; return; }
  const button = document.getElementById('memory-watch-btn');
  const enabled = button?.dataset.enabled !== 'true';
  if (button) { button.disabled = true; button.textContent = enabled ? 'Activando…' : 'Desactivando…'; }
  try {
    await request('/api/memory/watch', {method:'POST', body:JSON.stringify({path:state.activePath, enabled, consent:true, interval:30, provider_model:'auto'})});
    await loadMemoryOverview();
  } catch (error) { document.getElementById('memory-status').textContent = `No se pudo cambiar la captura: ${error.message}`; }
  finally { if (button) button.disabled = false; }
}

export function searchMemorySessions() {
  sessionOffset = 0;
  loadMemoryOverview(false);
}

export function loadMoreMemorySessions() {
  const more = document.getElementById('memory-sessions-more');
  if (!more || more.hidden || more.dataset.offset === '') return;
  sessionOffset = Number(more.dataset.offset) || 0;
  loadMemoryOverview(true);
}

export async function showSharedMemoryGraph() {
  const status = document.getElementById('memory-status');
  if (!state.activePath || !state.graphInst) { status.textContent = 'Selecciona un proyecto y espera a que cargue el grafo.'; return; }
  status.textContent = 'Construyendo mapa de autoría y recuperación…';
  try {
    const agent = document.getElementById('memory-agent').value.trim() || 'dashboard';
    const sessionParam = state.memoryFocusSession ? `&session_id=${encodeURIComponent(state.memoryFocusSession)}` : '';
    const data = await request(`/api/memory/graph?path=${encodeURIComponent(state.activePath)}&requester_agent=${encodeURIComponent(agent)}&view=topics&detail=${state.memoryGraphMode === 'detailed'}&limit=400&session_limit=100${sessionParam}`);
    state.activeView = 'memory';
    state.fullData = {nodes:data.nodes || [], links:data.links || []};
    state.memoryGraphMeta = data.metadata || null;
    state.selectedNode = null; state.selectedNeighbors = null;
    state.graphInst.graphData(state.fullData);
    refreshStyleInPlace();
    window.refreshMemoryColorControls?.();
    updateMemoryFocusBanner(data);
    setTimeout(() => state.graphInst?.zoomToFit?.(700, 55), 80);
    const legend = document.getElementById('memory-agent-legend');
    if (legend) {
      const keyHtml = item => `<span class="memory-agent-key"><i data-memory-legend-kind="memory_agent" style="background:${esc(getMemoryColor('memory_agent', 'node'))}"></i>${esc(item.id)}</span>`;
      const html = '<span class="memory-agent-key"><i data-memory-legend-kind="memory_topic" style="background:' + esc(getMemoryColor('memory_topic', 'node')) + '"></i>tema</span>' +
        '<span class="memory-agent-key"><i data-memory-legend-kind="memory_session" style="background:' + esc(getMemoryColor('memory_session', 'node')) + '"></i>sesión</span>' +
        '<span class="memory-agent-key"><i data-memory-legend-kind="memory_episode" style="background:' + esc(getMemoryColor('memory_episode', 'node')) + '"></i>episodio</span>' +
        '<span class="memory-agent-key"><i data-memory-legend-kind="memory_entity" style="background:' + esc(getMemoryColor('memory_entity', 'node')) + '"></i>entidad</span>' +
        (data.agents || []).map(keyHtml).join('')
        + ((data.consulters || []).length ? '<span class="memory-agent-key">· sólo consulta:</span>'
          + data.consulters.map(keyHtml).join('') : '');
      legend.innerHTML = html || '<div class="memory-empty">No hay agentes atribuidos.</div>';
    }
    status.textContent = `${data.metadata?.mode === 'detailed' ? 'Vista detallada' : 'Vista simplificada'} · ${(data.metadata?.topic_returned ?? data.metadata?.topic_count) || 0}/${(data.metadata?.topic_total ?? data.metadata?.topic_count) || 0} temas · ${(data.metadata?.session_returned ?? 0) || 0}/${(data.metadata?.session_total ?? 0) || 0} sesiones · ${data.nodes.length} nodos · ${data.links.length} relaciones`;
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
    const requester = document.getElementById('memory-agent')?.value.trim() || 'dashboard';
    const data = await request(`/api/memory/session?path=${encodeURIComponent(state.activePath)}&session_id=${arg(sessionId)}&requester_agent=${encodeURIComponent(requester)}`);
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
        <div class="memory-card-meta">${esc(s.branch || 'sin rama')} · ${(data.messages || []).length} mensajes · ${(data.memories || []).length} memorias</div>
        <div class="memory-card-actions"><button class="btn-action btn-primary" data-session-id="${esc(sessionId)}" onclick="event.stopPropagation();focusMemorySession(this.dataset.sessionId)">Explorar en el grafo</button></div></article>
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

export function focusMemorySession(sessionId) {
  state.memoryFocusSession = decodeURIComponent(String(sessionId || '')).replace(/^session:/, '');
  closeMemoryPanel();
  setView('memory');
}

export function clearMemorySessionFocus() {
  state.memoryFocusSession = null;
  state.memoryGraphMeta = null;
  setView('memory');
}

function mergeMemoryGraphPage(data) {
  const nodes = new Map((state.fullData?.nodes || []).map(node => [node.id, node]));
  for (const node of (data.nodes || [])) nodes.set(node.id, {...nodes.get(node.id), ...node});
  const links = new Map();
  const linkKey = link => {
    const source = typeof link.source === 'object' ? link.source.id : link.source;
    const target = typeof link.target === 'object' ? link.target.id : link.target;
    return `${source}|${target}|${link.label || ''}`;
  };
  for (const link of [...(state.fullData?.links || []), ...(data.links || [])]) links.set(linkKey(link), link);
  state.fullData = {nodes:[...nodes.values()], links:[...links.values()]};
  const incoming = data.metadata || {};
  const previous = state.memoryGraphMeta || {};
  const incomingLoaded = Number(incoming.topic_offset || 0) + Number(incoming.topic_returned || incoming.topic_count || 0);
  const previousLoaded = Number(previous.topic_returned || previous.topic_count || 0);
  const topicCount = [...nodes.values()].filter(node => node.kind === 'memory_topic').length;
  state.memoryGraphMeta = {...incoming,
    topic_returned: Math.max(previousLoaded, incomingLoaded),
    topic_count: Math.max(Number(previous.topic_count || 0), topicCount),
  };
  state.pulseSim = buildPulseSim(state.fullData);
  if (state.graphInst) {
    state.graphInst.graphData(state.fullData);
    state.graphInst.d3ReheatSimulation?.();
  }
  updateMemoryFocusBanner({metadata: state.memoryGraphMeta});
}

export async function loadMoreMemoryTopics() {
  if (state.activeView !== 'memory' || !state.memoryGraphMeta || !state.activePath) return;
  const next = state.memoryGraphMeta.next_topic_offset;
  if (next === null || next === undefined) return;
  const status = document.getElementById('memory-status');
  if (status) status.textContent = state.memoryFocusSession ? 'Cargando más temas de la sesión…' : 'Cargando más temas del proyecto…';
  try {
    const agent = document.getElementById('memory-agent')?.value.trim() || 'dashboard';
    const focusParam = state.memoryFocusSession ? `&session_limit=1&session_id=${encodeURIComponent(state.memoryFocusSession)}` : '&session_limit=100';
    const data = await request(`/api/memory/graph?path=${encodeURIComponent(state.activePath)}&requester_agent=${encodeURIComponent(agent)}&view=topics&detail=${state.memoryGraphMode === 'detailed'}&limit=400${focusParam}&topic_offset=${next}`);
    mergeMemoryGraphPage(data);
    if (status) status.textContent = `${state.memoryFocusSession ? 'Sesión enfocada' : 'Proyecto'} · ${(state.memoryGraphMeta?.topic_returned ?? 0)}/${(state.memoryGraphMeta?.topic_total ?? 0)} temas · ${state.fullData.nodes.length} nodos · ${state.fullData.links.length} relaciones`;
  } catch (error) {
    if (status) status.textContent = `No se pudieron cargar más temas: ${error.message}`;
  }
}

let topicRequest;
let conversationRequest;
let relationRequest;
async function loadTopics(offset = 0) {
  topicRequest?.abort();
  topicRequest = new AbortController();
  const host = document.getElementById('memory-topic-list');
  if (!host || !state.activePath) return;
  const params = new URLSearchParams({path: state.activePath, offset, limit: 20});
  for (const [id, key] of [['memory-topic-query','query'], ['memory-topic-state','state'], ['memory-topic-agent','agent_id'], ['memory-topic-session','session_id']]) {
    const value = document.getElementById(id)?.value.trim();
    if (value) params.set(key, value);
  }
  for (const [id, key] of [['memory-topic-since','since'], ['memory-topic-until','until']]) {
    const value = document.getElementById(id)?.value;
    if (value) params.set(key, Date.parse(value) / 1000 + (key === 'until' ? 86399 : 0));
  }
  host.textContent = 'Cargando asuntos…';
  try {
    const data = await request(`/api/memory/topics?${params}`, {signal: topicRequest.signal});
    host.replaceChildren();
    const coverage = document.createElement('p');
    coverage.textContent = `${data.coverage.processed}/${data.coverage.discovered} mensajes guardados procesados · ${data.coverage.pending} pendientes · extracción limitada · exclusiones de fuente sin medir`;
    host.append(coverage);
    for (const topic of data.topics) {
      const card = document.createElement('details');
      card.className = 'memory-card';
      const title = document.createElement('summary');
      title.textContent = `${topic.reference || topic.public_id || topic.id} · ${topic.title} · ${topic.state} · ${topic.verification}`;
      card.append(title);
      const body = document.createElement('div');
      card.append(body);
      const loadEpisodes = async (page = 0) => {
        body.textContent = 'Cargando episodios…';
        try {
          const p = new URLSearchParams({path: state.activePath, topic_id: topic.id, offset: page});
          const detail = await request(`/api/memory/topic?${p}`, {signal: topicRequest.signal});
          body.replaceChildren();
          for (const episode of detail.episodes) {
            const text = document.createElement('p');
            text.style.whiteSpace = 'pre-wrap';
            text.textContent = `${episode.reference || episode.public_id || episode.id}\nParticipante: ${episode.agent_id}\nSesión: ${episode.session_id}\nPetición: ${episode.problem}\nDecisiones: ${episode.decisions || 'Sin extraer'}\nResultado declarado: ${episode.result || 'Sin resultado registrado'}`;
            body.append(text);
            if (episode.message_ids.length) {
              const view = document.createElement('button');
              view.textContent = 'Ver conversación';
              view.onclick = () => showTopicConversation(episode.message_ids[0]);
              body.append(view);
            }
          }
          if (detail.next_offset !== null) {
            const next = document.createElement('button'); next.textContent = 'Más episodios';
            next.onclick = () => loadEpisodes(detail.next_offset); body.append(next);
          }
        } catch (error) { if (error.name !== 'AbortError') retry(body, error, () => loadEpisodes(page)); }
      };
      card.addEventListener('toggle', () => { if (card.open && !body.childNodes.length) loadEpisodes(); });
      host.append(card);
    }
    if (!data.topics.length) host.append(document.createTextNode('Sin temas para estos filtros.'));
    if (offset) { const prev = document.createElement('button'); prev.textContent = 'Anterior'; prev.onclick = () => loadTopics(Math.max(0, offset - 20)); host.append(prev); }
    if (data.next_offset !== null) { const next = document.createElement('button'); next.textContent = 'Más temas'; next.onclick = () => loadTopics(data.next_offset); host.append(next); }
  } catch (error) { if (error.name !== 'AbortError') retry(host, error, () => loadTopics(offset)); }
}
async function loadRelationCandidates() {
  relationRequest?.abort(); relationRequest = new AbortController();
  const host = document.getElementById('memory-relation-review');
  if (!host || !state.activePath) return;
  host.textContent = 'Buscando candidatas…';
  try {
    const params = new URLSearchParams({path: state.activePath, status: 'pending', limit: 20});
    const data = await request(`/api/memory/relation-candidates?${params}`, {signal: relationRequest.signal});
    host.replaceChildren();
    if (!data.candidates?.length) { host.textContent = 'No hay relaciones pendientes de revisión.'; return; }
    data.candidates.forEach(candidate => {
      const card = document.createElement('div'); card.className = 'memory-card';
      const evidence = candidate.evidence?.shared_terms?.join(', ') || 'evidencia textual limitada';
      card.innerHTML = `<strong>${esc(candidate.source_reference)} · ${esc(candidate.source_title)}</strong><br><strong>${esc(candidate.target_reference)} · ${esc(candidate.target_title)}</strong><br><small>${esc(candidate.reason)} · términos: ${esc(evidence)}</small>`;
      const actions = document.createElement('div'); actions.style.cssText = 'display:flex;gap:6px;margin-top:5px;';
      for (const [status, label] of [['accepted','Aceptar relación'],['rejected','Rechazar']]) {
        const button = document.createElement('button'); button.className = status === 'accepted' ? 'btn-action btn-primary' : 'btn-action'; button.textContent = label;
        button.onclick = async () => {
          button.disabled = true;
          try { await request('/api/memory/relation-review', {method:'POST', body:JSON.stringify({path:state.activePath, relation_id:candidate.id, status, requester_agent:'dashboard', reason: status === 'accepted' ? 'Revisada en el dashboard' : 'No representa el mismo asunto'})}); loadRelationCandidates(); if (state.activeView === 'memory') window.dispatchEvent(new Event('graphtyn-memory-refresh')); }
          catch (error) { button.disabled = false; retry(card, error, loadRelationCandidates); }
        };
        actions.append(button);
      }
      card.append(actions); host.append(card);
    });
  } catch (error) { if (error.name !== 'AbortError') retry(host, error, loadRelationCandidates); }
}
function retry(host, error, action) {
  host.textContent = `No se pudo cargar: ${error.message} `;
  const button = document.createElement('button'); button.textContent = 'Reintentar'; button.onclick = action; host.append(button);
}
async function showTopicConversation(messageId) {
  conversationRequest?.abort(); conversationRequest = new AbortController();
  const panel = document.getElementById('memory-conversation-panel');
  panel.hidden = false; panel.textContent = 'Cargando conversación…';
  try {
    const params = new URLSearchParams({path: state.activePath, message_id: messageId});
    const data = await request(`/api/memory/window?${params}`, {signal: conversationRequest.signal});
    panel.replaceChildren();
    const close = document.createElement('button'); close.textContent = 'Cerrar conversación'; close.onclick = () => { conversationRequest?.abort(); panel.hidden = true; }; panel.append(close);
    for (const msg of data.messages) {
      const block = document.createElement('p'); block.style.whiteSpace = 'pre-wrap';
      block.textContent = `${msg.role} · ${msg.agent_id}\n${msg.content}${msg.content_truncated ? '\n[Texto recortado por presupuesto]' : ''}`; panel.append(block);
    }
    const note = document.createElement('p'); note.textContent = `${data.estimated_tokens}/${data.token_budget} presupuesto conservador${data.truncated ? ' · ventana recortada' : ''}`; panel.append(note);
    for (const [key, label] of [['previous_cursor','10 antes'], ['next_cursor','10 después']]) {
      if (data[key]) { const btn = document.createElement('button'); btn.textContent = label; btn.onclick = () => showTopicConversation(data[key]); panel.append(btn); }
    }
  } catch (error) { if (error.name !== 'AbortError') retry(panel, error, () => showTopicConversation(messageId)); }
}
function initializeTopics() {
  if (document.getElementById('memory-topic-list')) { loadTopics(); return; }
  const host = document.getElementById('memory-results')?.parentElement?.parentElement;
  if (!host) return;
  const section = document.createElement('section');
  section.style.gridColumn = '1 / -1';
  section.innerHTML = `<h3>Memoria del proyecto</h3><div class="memory-options">
    <input id="memory-topic-query" aria-label="Buscar asunto" placeholder="Buscar asunto">
    <select id="memory-topic-state" aria-label="Estado"><option value="">Todos los estados</option>${['abierto','en investigación','resuelto','reabierto','archivado'].map(x => `<option>${x}</option>`).join('')}</select>
    <input id="memory-topic-agent" aria-label="Agente participante" placeholder="Agente participante">
    <input id="memory-topic-session" aria-label="Sesión" placeholder="Sesión">
    <label>Desde <input id="memory-topic-since" type="date"></label><label>Hasta <input id="memory-topic-until" type="date"></label>
    <button id="memory-topic-filter">Filtrar</button></div><div id="memory-topic-list" aria-live="polite"></div>
    <div class="memory-review-block"><div style="display:flex;justify-content:space-between;align-items:center;"><strong>Relaciones candidatas</strong><button id="memory-relation-refresh" class="btn-link">Recargar</button></div><div id="memory-relation-review" aria-live="polite"></div></div>
    <aside id="memory-conversation-panel" aria-label="Conversación histórica" hidden></aside>`;
  host.prepend(section);
  document.getElementById('memory-topic-filter').onclick = () => loadTopics();
  document.getElementById('memory-relation-refresh').onclick = loadRelationCandidates;
  loadTopics();
  loadRelationCandidates();
}
