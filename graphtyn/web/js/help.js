// Ayuda con atajos, modo anónimo para compartir pantalla y proyecto de ejemplo.
import { state, authHeaders } from './state.js';
import { VIEW_HINTS } from './legend.js';
import { loadProjects, selectProject } from './ui.js';

const VIEW_NAMES = {code: 'Code AST', semantic: 'Semántico', memory: 'Memoria del proyecto', agents: 'Topología',
  changes: 'Cambios', openclaw: 'OpenClaw'};
const EXTRA_VIEWS = {
  changes: 'Compara el working tree con Git y recorre quién consume lo que cambió.',
  openclaw: 'Instalaciones de OpenClaw conectadas, sus cerebros y el estado de la captura.',
};
const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));

export function openHelp() {
  const views = document.getElementById('help-views');
  if (views) views.innerHTML = Object.entries(VIEW_NAMES).map(([key, name]) =>
    `<dt>${esc(name)}</dt><dd>${esc(VIEW_HINTS[key] || EXTRA_VIEWS[key] || '')}</dd>`).join('');
  document.getElementById('modal-help')?.classList.add('show');
}

export function closeHelp() { document.getElementById('modal-help')?.classList.remove('show'); }

export function toggleAnonymous(force) {
  state.anonymous = typeof force === 'boolean' ? force : !state.anonymous;
  document.body.classList.toggle('anonymous', state.anonymous);
  const badge = document.getElementById('anonymous-badge');
  if (badge) badge.hidden = !state.anonymous;
}

// Nombre estable y genérico para enseñar el grafo sin revelar archivos ni símbolos.
export function anonymousName(node) {
  const id = String(node?.id || '');
  let hash = 0;
  for (let index = 0; index < id.length; index++) hash = (hash * 31 + id.charCodeAt(index)) >>> 0;
  return `${node?.kind || 'nodo'} ${hash % 1000}`;
}

export async function startDemo(button) {
  if (button) { button.disabled = true; button.textContent = 'Preparando ejemplo…'; }
  try {
    const prepared = await (await fetch('/api/demo', {method:'POST', headers:authHeaders()})).json();
    if (!prepared.ok) throw new Error(prepared.error || 'No se pudo preparar el ejemplo');
    const response = await fetch('/api/projects/register', {method:'POST',
      headers:authHeaders({'Content-Type':'application/json'}),
      body:JSON.stringify({path:prepared.path, name:'Tienda de ejemplo', mode:'single_folder', space_type:'project'})});
    const registered = await response.json();
    if (!response.ok || registered.ok === false) throw new Error(registered.error || `HTTP ${response.status}`);
    // Indexa antes de refrescar la lista: así aparece como listo y no como pendiente.
    await fetch('/api/graph?path=' + encodeURIComponent(prepared.path), {headers:authHeaders()});
    document.querySelectorAll('.modal-bg.show').forEach(modal => modal.classList.remove('show'));
    loadProjects();
    selectProject(prepared.path);
  } catch (error) {
    window.alert(`No se pudo abrir el ejemplo: ${error.message}`);
  } finally {
    if (button) { button.disabled = false; button.textContent = 'Probar con un proyecto de ejemplo'; }
  }
}

export function handleShortcut(event) {
  const target = event.target;
  if (event.ctrlKey || event.metaKey || event.altKey) return false;
  if (target && (target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName))) return false;
  if (event.key === '?') { openHelp(); return true; }
  if (event.key === '/') { document.getElementById('search-box')?.focus(); return true; }
  if (event.key === 'a' || event.key === 'A') { toggleAnonymous(); return true; }
  return false;
}
