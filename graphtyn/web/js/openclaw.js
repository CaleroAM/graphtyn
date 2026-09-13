import { state } from './state.js';

const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
let requestId = 0;
let controller = null;

function headers() {
  const token = document.getElementById('memory-token')?.value.trim() ||
    localStorage.getItem('graphtyn-memory-token') || '';
  return {'Content-Type':'application/json', ...(token ? {'Authorization':`Bearer ${token}`} : {})};
}

async function request(url, options = {}) {
  const response = await fetch(url, {...options, headers:{...headers(), ...(options.headers || {})}});
  const data = await response.json();
  if (!response.ok || data.ok === false) throw new Error(data.error || `HTTP ${response.status}`);
  return data;
}

function when(value) {
  const timestamp = Number(value);
  if (!Number.isFinite(timestamp) || timestamp <= 0) return 'Sin datos';
  return new Date(timestamp * 1000).toLocaleString();
}

function relationship(agent) {
  const status = String(agent.relation_status || 'pending');
  const labels = {root:'Cerebro raíz', independent:'Independiente', confirmed:'Subagente confirmado',
    proposed:'Relación sugerida', pending:'Pendiente de clasificar'};
  const color = status === 'confirmed' || status === 'root' || status === 'independent' ? 'ok' : 'pending';
  const parent = agent.parent_id ? ` · padre: ${agent.parent_id}` : '';
  return `<span class="oc-badge ${color}">${esc(labels[status] || status)}${esc(parent)}</span>`;
}

function watcherSummary(memoryStatus) {
  const own = memoryStatus?.own || {};
  const watchers = own.capture_watchers || own.sync_watchers || [];
  const active = watchers.filter(item => item.active);
  const errors = watchers.filter(item => item.error || item.status === 'error');
  const lastRun = watchers.reduce((max, item) => Math.max(max, Number(item.heartbeat || 0)), 0);
  return {own, active, errors, lastRun};
}

function renderAgent(agent) {
  const status = agent.memory_status;
  const watcher = watcherSummary(status);
  const memoryEnabled = agent.memory_enabled !== false;
  const capture = !memoryEnabled
    ? `<span class="oc-state disabled">Memoria desactivada en esta instalación</span>`
    : watcher.active.length
      ? `<span class="oc-state ok">Sincronizador activo</span>`
      : `<span class="oc-state muted">Sin sincronizador periódico</span>`;
  const captureAt = !memoryEnabled ? 'Desactivada por política local'
    : status?.own?.last_capture_at ? when(status.own.last_capture_at) : 'Sin capturas registradas';
  const watchAt = !memoryEnabled ? 'No participa en sincronización'
    : watcher.lastRun ? when(watcher.lastRun) : 'Sin actividad del sincronizador';
  const statusError = agent.memory_status_error
    ? `<div class="oc-error">No se pudo consultar este cerebro: ${esc(agent.memory_status_error)}</div>` : '';
  const watcherErrors = watcher.errors.map(item => `<div class="oc-error">${esc(item.error || 'Falló el sincronizador')} · ${esc(item.kind || 'captura')}</div>`).join('');
  const unavailable = !status && !agent.memory_status_error ? '<div class="oc-error">Estado del cerebro no disponible.</div>' : '';
  const own = status?.own || {};
  const path = agent.brain_path || '';
  return `<article class="oc-agent">
    <div class="oc-agent-title"><div><strong>${esc(agent.display_name || agent.id)}</strong><code>openclaw/${esc(agent.id)}</code></div>${relationship(agent)}</div>
    <div class="oc-agent-stats">
      <span>${Number(own.sessions || 0)} sesiones</span><span>${Number(own.memories || 0)} memorias</span>
      <span>${capture}</span>
    </div>
    <div class="oc-agent-detail"><span>Última captura: <b>${esc(captureAt)}</b></span><span>Actividad de sync: <b>${esc(watchAt)}</b></span></div>
    ${path ? `<div class="oc-brain-path" title="Almacén privado de este agente">Cerebro privado · <code>${esc(path)}</code></div>` : ''}
    ${statusError}${watcherErrors}${unavailable}
    <div class="oc-agent-actions"><button class="btn-action" data-installation="${esc(agent.installation_id || '')}" data-agent="${esc(agent.agent_id || `openclaw/${agent.id}`)}" data-path="${esc(path)}" onclick="openOpenClawBrain(this)">Abrir memoria</button></div>
  </article>`;
}

function renderInstallation(installation) {
  const agents = installation.agents || [];
  const pending = agents.filter(agent => !['root','confirmed','independent'].includes(agent.relation_status)).length;
  const hasErrors = agents.some(agent => agent.memory_status_error ||
    (agent.memory_status?.own?.capture_watchers || []).some(item => item.error || item.status === 'error'));
  const syncLabel = hasErrors ? 'Reintentar sincronización' : 'Sincronizar ahora';
  const syncKey = encodeURIComponent(installation.id);
  const kind = installation.kind === 'ssh' ? 'OpenClaw remoto · SSH' : 'OpenClaw local';
  const target = installation.target ? ` · ${esc(installation.target)}` : '';
  return `<section class="oc-installation">
    <div class="oc-install-head"><div><span class="oc-kicker">${esc(kind)}${target}</span><h2>${esc(installation.id)}</h2>
      <div class="oc-subtitle">${esc(installation.version || 'Versión no informada')} · ${agents.length} agentes · ${pending} relaciones pendientes</div></div>
      <button class="btn-action btn-primary" data-installation="${esc(installation.id)}" data-openclaw-sync="true" data-label="${syncLabel}" onclick="syncOpenClaw(this.dataset.installation)">${syncLabel}</button>
    </div>
    ${pending ? `<div class="oc-notice">${pending} agente${pending === 1 ? '' : 's'} conserva${pending === 1 ? '' : 'n'} un cerebro aislado hasta revisar su relación. Graphtyn no comparte sus memorias automáticamente.</div>` : ''}
    <div id="oc-sync-status-${syncKey}" class="oc-sync-status" aria-live="polite"></div>
    <div class="oc-agent-grid">${agents.map(renderAgent).join('') || '<div class="oc-empty">La instalación no tiene agentes registrados.</div>'}</div>
  </section>`;
}

function render(data) {
  const container = document.getElementById('graph-container');
  if (!container) return;
  const installations = data.installations || [];
  const agentCount = installations.reduce((sum, item) => sum + (item.agents || []).length, 0);
  const pending = installations.reduce((sum, item) => sum + (item.agents || []).filter(agent =>
    !['root','confirmed','independent'].includes(agent.relation_status)).length, 0);
  container.innerHTML = `<div class="openclaw-dashboard">
    <div class="oc-page-head"><div><span class="oc-kicker">INTEGRACIÓN NATIVA</span><h1>OpenClaw</h1>
      <p>Instalaciones conectadas, aislamiento de cerebros, captura y estado de sincronización.</p></div>
      <button class="btn-action" onclick="loadOpenClawPanel()">Actualizar estado</button></div>
    <div class="oc-overview"><div><b>${installations.length}</b><span>instalaciones</span></div><div><b>${agentCount}</b><span>agentes</span></div><div><b>${pending}</b><span>relaciones por revisar</span></div></div>
    ${installations.length ? installations.map(renderInstallation).join('') : `<section class="oc-empty-state"><h2>No hay una instalación OpenClaw conectada</h2>
      <p>Desde la máquina donde Graphtyn tiene acceso al harness, detecta y registra la instalación. Las nuevas identidades se conservan separadas hasta que confirmes sus relaciones.</p>
      <code>graphtyn harness openclaw discover</code><code>graphtyn harness openclaw connect --installation openclaw-&lt;id&gt;</code>
      <p>Después vuelve aquí para revisar agentes, cerebros y captura.</p></section>`}
    <div class="oc-footnote">La última captura refleja el dato más reciente guardado en el cerebro. La actividad de sync refleja el heartbeat del capturador; son indicadores distintos.</div>
  </div>`;
}

export async function loadOpenClawPanel() {
  const container = document.getElementById('graph-container');
  if (!container || state.activeView !== 'openclaw') return;
  const current = ++requestId;
  if (controller) controller.abort();
  controller = new AbortController();
  container.classList.add('openclaw-manager');
  container.innerHTML = '<div class="oc-loading"><span></span><b>Consultando instalaciones OpenClaw…</b></div>';
  try {
    const response = await fetch('/api/harness/openclaw', {headers:headers(), signal:controller.signal});
    const data = await response.json();
    if (!response.ok || data.ok === false) throw new Error(data.error || `HTTP ${response.status}`);
    if (current === requestId && state.activeView === 'openclaw') render(data);
  } catch (error) {
    if (error.name === 'AbortError' || current !== requestId || state.activeView !== 'openclaw') return;
    container.innerHTML = `<div class="oc-error-state"><h2>No se pudo consultar OpenClaw</h2><p>${esc(error.message)}</p><div class="oc-error-actions"><button class="btn-action" onclick="openMemoryPanel()">Configurar token</button><button class="btn-action" onclick="loadOpenClawPanel()">Reintentar</button></div></div>`;
  }
}

async function waitForJob(jobId, installationId) {
  while (true) {
    const response = await request(`/api/v1/imports/${encodeURIComponent(jobId)}`);
    const job = response.job || {};
    const status = document.getElementById(`oc-sync-status-${encodeURIComponent(installationId)}`);
    if (status) status.textContent = job.status === 'running' || job.status === 'pending'
      ? `${job.message || 'Sincronización en curso'} · ${job.progress || 0}%` : status.textContent;
    if (['completed','failed','cancelled'].includes(job.status)) return job;
    await new Promise(resolve => setTimeout(resolve, 700));
  }
}

export async function syncOpenClaw(installationId) {
  const button = [...document.querySelectorAll('[data-installation]')].find(item =>
    item.dataset.installation === installationId && item.dataset.openclawSync === 'true');
  const status = document.getElementById(`oc-sync-status-${encodeURIComponent(installationId)}`);
  if (button) { button.disabled = true; button.textContent = 'Iniciando…'; }
  if (status) status.textContent = 'Iniciando sincronización incremental…';
  try {
    const started = await request(`/api/harness/openclaw/${encodeURIComponent(installationId)}/sync`, {method:'POST'});
    const job = await waitForJob(started.job.id, installationId);
    if (job.status !== 'completed') throw new Error(job.error || job.status);
    const result = job.result || {};
    const failures = (result.agents || []).filter(agent => !agent.ok || (agent.errors || []).length);
    const failureDetails = failures.slice(0, 3).map(agent => {
      const errors = (agent.errors || []).slice(0, 2).map(item => typeof item === 'string' ? item : item.error || JSON.stringify(item));
      return `${agent.display_name || agent.agent_id}: ${errors.join('; ') || 'fallo reportado por el adaptador'}`;
    }).join(' · ');
    const outcome = failures.length
      ? `Sincronización terminada con ${failures.length} cerebro(s) con errores. ${failureDetails}`
      : `Sincronización completada · ${result.agent_count || 0} agentes procesados.`;
    await loadOpenClawPanel();
    const refreshedStatus = document.getElementById(`oc-sync-status-${encodeURIComponent(installationId)}`);
    if (refreshedStatus) refreshedStatus.textContent = outcome;
  } catch (error) {
    if (status) status.textContent = `No se pudo sincronizar: ${error.message}`;
  } finally {
    if (button) { button.disabled = false; button.textContent = button.dataset.label || 'Sincronizar ahora'; }
  }
}

export function openOpenClawBrain(button) {
  const path = button?.dataset.path;
  const agent = button?.dataset.agent;
  if (!path || !agent) return;
  state.activePath = path;
  state.activeAgentId = agent;
  state.activeSpaceType = 'agent_brain';
  state.memoryFocusSession = null;
  state.contextSelection = [];
  window.loadBrains?.();
  if (typeof window.setView === 'function') window.setView('memory');
}
