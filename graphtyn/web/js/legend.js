// Explica lo que se ve: color de cada tipo de nodo y una línea por vista.
import { state, PALETTES } from './state.js';

const HINT_KEY = 'graphtyn-view-hints-hidden-v1';
// Cambios y OpenClaw ya abren con su propia cabecera explicativa.
export const VIEW_HINTS = {
  code: 'Archivos, clases y funciones extraídos del código, unidos por llamadas, imports y herencia. Haz clic en un nodo para ver su radio de impacto.',
  semantic: 'Agrupa el código por carpeta (verde: subsistema, rosa: arquitectura global) y une elementos de contenido parecido. Esas uniones son inferidas: compruébalas en el código.',
  memory: 'Temas, decisiones y sesiones que los agentes guardaron en la memoria de este proyecto. Haz clic en un nodo para ver de qué conversación viene.',
  agents: 'Agentes registrados u observados, los proyectos a los que están vinculados y las fuentes de historial configuradas.',
};

const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const item = (color, label) => `<span class="kind-item"><i style="background:${esc(color)}"></i>${esc(label)}</span>`;

export function renderKindLegend() {
  const el = document.getElementById('kind-legend');
  if (!el) return;
  const visible = state.activeView === 'code' || state.activeView === 'semantic';
  el.hidden = !visible;
  if (!visible) return;
  if (state.nodeColorHex) {
    el.innerHTML = item(state.nodeColorHex, 'color único elegido en Diseño del grafo');
    return;
  }
  if (state.activePalette === 'community') {
    el.innerHTML = '<span class="kind-item">Color = comunidad del panel derecho</span>';
    return;
  }
  const p = PALETTES[state.activePalette] || PALETTES.obsidian;
  const items = [item(p.file, 'archivo'), item(p.class, 'clase'), item(p.func, 'función'), item('#ffffff', 'doc / medio')];
  if (state.activeView === 'semantic') items.push(item('#10b981', 'subsistema'), item('#ec4899', 'arquitectura'));
  el.innerHTML = items.join('');
}

function hiddenHints() {
  try { return new Set(JSON.parse(localStorage.getItem(HINT_KEY) || '[]')); } catch (_) { return new Set(); }
}

export function renderViewHint() {
  const el = document.getElementById('view-hint');
  if (!el) return;
  const text = VIEW_HINTS[state.activeView];
  el.hidden = !text || hiddenHints().has(state.activeView);
  const label = el.querySelector('.view-hint-text');
  if (label) label.textContent = text || '';
}

export function dismissViewHint() {
  const hidden = hiddenHints();
  hidden.add(state.activeView);
  try { localStorage.setItem(HINT_KEY, JSON.stringify([...hidden])); } catch (_) { /* storage opcional */ }
  renderViewHint();
}

export function refreshLegends() {
  renderKindLegend();
  renderViewHint();
}
