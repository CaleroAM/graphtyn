import { state } from './state.js';

const esc = value => String(value ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));

export function openQualityPanel() {
  document.getElementById('modal-quality')?.classList.add('show');
  renderContextSelection();
  loadIndexQuality();
}
export function closeQualityPanel() { document.getElementById('modal-quality')?.classList.remove('show'); }

export async function loadIndexQuality() {
  const box = document.getElementById('quality-summary');
  if (!box) return;
  if (!state.activePath) { box.textContent = 'Selecciona un proyecto.'; return; }
  box.textContent = 'Calculando salud del índice…';
  try {
    const scope = document.getElementById('context-scope')?.value || 'all';
    const response = await fetch('/api/index-quality?path=' + encodeURIComponent(state.activePath) + '&scope=' + encodeURIComponent(scope));
    const data = await response.json();
    if (!response.ok || !data.ok) throw new Error(data.error || 'No se pudo medir el índice');
    const conf = data.confidence || {};
    box.innerHTML = `<div class="quality-score"><strong>${esc(data.health_score)}%</strong><span>salud observable</span></div>
      <div class="quality-grid"><div><strong>${esc(data.parser)}</strong><span>Parser</span></div><div><strong>${esc(data.tree_sitter_files)}</strong><span>Archivos Tree-sitter</span></div><div><strong>${esc(conf.EXTRACTED || 0)}</strong><span>Extraídas</span></div><div><strong>${esc(conf.INFERRED || 0)}</strong><span>Inferidas</span></div><div><strong>${esc(conf.AMBIGUOUS || 0)}</strong><span>Ambiguas</span></div><div><strong>${Math.round((data.location_coverage || 0) * 100)}%</strong><span>Evidencia ubicada</span></div></div>
      <div class="quality-note">${esc(data.accuracy_note)}</div>${(data.warnings || []).map(w => `<div class="quality-warning">${esc(w)}</div>`).join('')}`;
  } catch (error) { box.innerHTML = `<div class="quality-error">${esc(error.message)}</div>`; }
}

export function addNodeToContext(nodeOrId) {
  const id = typeof nodeOrId === 'string' ? nodeOrId : nodeOrId?.id;
  const node = (state.fullData?.nodes || []).find(n => n.id === id) || nodeOrId;
  if (!node?.id || state.contextSelection.some(item => item.id === node.id) || state.contextSelection.length >= 10) return;
  state.contextSelection.push({id: node.id, name: node.name || node.id, container: node.container || ''});
  renderContextSelection();
}
export function removeNodeFromContext(id) { state.contextSelection = state.contextSelection.filter(node => node.id !== id); renderContextSelection(); }
export function clearContextSelection() { state.contextSelection = []; state.lastContextBundle = null; renderContextSelection(); const out = document.getElementById('context-output'); if (out) out.innerHTML = ''; }
export function renderContextSelection() {
  const list = document.getElementById('context-selection');
  const count = document.getElementById('context-count');
  if (count) count.textContent = String(state.contextSelection.length);
  if (!list) return;
  list.innerHTML = state.contextSelection.length ? state.contextSelection.map(node => `<div class="context-chip"><span>${esc(node.container ? node.container + '.' + node.name : node.name)}</span><button data-context-id="${esc(node.id)}" onclick="removeNodeFromContext(this.dataset.contextId)" aria-label="Quitar símbolo">×</button></div>`).join('') : '<div class="quality-note">Abre un nodo y pulsa “Añadir al contexto”.</div>';
}

export async function generateContextBundle() {
  const out = document.getElementById('context-output');
  if (!out) return;
  if (!state.activePath || !state.contextSelection.length) { out.innerHTML = '<div class="quality-warning">Selecciona al menos un símbolo.</div>'; return; }
  out.textContent = 'Generando contexto compacto…';
  const symbols = state.contextSelection.map(n => n.container ? `${n.container}.${n.name}` : n.name);
  const scope = document.getElementById('context-scope')?.value || 'all';
  try {
    const response = await fetch('/api/context-bundle', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({path:state.activePath, symbols, depth:1, limit:12, scope})});
    const data = await response.json();
    if (!response.ok || !data.ok) throw new Error(data.error || 'No se pudo generar el contexto');
    state.lastContextBundle = data;
    const unmatched = (data.unmatched_symbols || []).length ? `<div class="quality-warning">Sin coincidencia: ${data.unmatched_symbols.map(esc).join(', ')}</div>` : '';
    const rate = Math.round((data.reduction_rate || 0) * 100);
    out.innerHTML = `<div class="context-stats"><div><strong>${esc(data.estimated_tokens)}</strong><span>Tokens compactos</span></div><div><strong>${esc(data.raw_context_tokens)}</strong><span>Contexto bruto</span></div><div><strong>${rate}%</strong><span>${rate >= 0 ? 'Ahorro estimado' : 'Expansión estimada'}</span></div></div>${unmatched}<div class="quality-note">${esc(data.token_estimation)}</div><textarea id="context-json" readonly aria-label="Contexto compacto JSON">${esc(JSON.stringify(data, null, 2))}</textarea>`;
  } catch (error) { out.innerHTML = `<div class="quality-error">${esc(error.message)}</div>`; }
}
export async function copyContextBundle() {
  if (!state.lastContextBundle) return;
  await navigator.clipboard.writeText(JSON.stringify(state.lastContextBundle, null, 2));
  const button = document.getElementById('copy-context-btn');
  if (button) { button.textContent = 'Copiado'; setTimeout(() => { button.textContent = 'Copiar JSON'; }, 1200); }
}
