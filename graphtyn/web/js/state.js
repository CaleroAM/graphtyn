// Estado compartido del dashboard (mutable por todos los módulos)
export const state = {
  activePath: null,
  activeAgentId: null,
  activeSpaceType: 'project',
  brainSpaces: {},
  activeView: 'code',
  memoryGraphMode: 'simplified',
  activeDim: '2d',
  isRotating: false,
  rotateRaf: null,
  rotateAngle: 0,
  activePalette: 'obsidian',
  showParticles: true,
  showArrows: true,
  linkStyle: 'solid',
  regMode: 'single_folder',
  graphInst: null,
  graphLoadId: 0,
  graphRequestController: null,
  fullData: { nodes: [], links: [] },
  respectMap: {},
  nonAutoloadPaths: new Set(),
  graphStyle: 'standard',
  nodeShape: 'circles',
  neuralPhase: 0,
  neuralTimer: null,
  holoBgRo: null,
  pulseSim: null,
  pulse3dRaf: null,
  pulseColorHex: '#ff5aaf',
  linkColorHex: '#8c96eb',
  nodeColorHex: null,
  vertexBlinkOn: true,
  radianceOn: true,
  organic3dOn: true,
  commColorMap: {},
  communityNodes: {},
  selectedNode: null,
  selectedNeighbors: null,
  contextSelection: [],
  lastContextBundle: null,
  descExpanded: false,
  watchVersions: {},
  watchTimer: null,
  prBase: '',
  webFlowNodeIds: null,
  memoryFocusSession: null,
  memoryGraphMeta: null,
  memoryColors: null,
  memoryPalette: null,
};

export const MEMORY_COLOR_DEFAULTS = {
  memory_topic:  { label: 'Tema',     node: '#38bdf8', halo: '#38bdf8', linkedHalo: true },
  memory_session:{ label: 'Sesión',   node: '#f97316', halo: '#f97316', linkedHalo: true },
  memory_agent:  { label: 'Agente',   node: '#7c3aed', halo: '#7c3aed', linkedHalo: true },
  memory_episode:{ label: 'Episodio', node: '#22c55e', halo: '#22c55e', linkedHalo: true },
  memory_entity: { label: 'Entidad',  node: '#14b8a6', halo: '#14b8a6', linkedHalo: true },
};

// Paletas específicas de «Memoria del proyecto». Conservan la semántica de
// los tipos de memoria, pero permiten cambiar el lenguaje visual completo con
// un solo selector. «custom» siempre representa los colores editados a mano.
export const MEMORY_PALETTES = {
  obsidian: {
    memory_topic: {node:'#38bdf8', halo:'#38bdf8'}, memory_session:{node:'#f97316', halo:'#f97316'},
    memory_agent:{node:'#7c3aed', halo:'#7c3aed'}, memory_episode:{node:'#22c55e', halo:'#22c55e'}, memory_entity:{node:'#14b8a6', halo:'#14b8a6'}
  },
  cyberpunk: {
    memory_topic: {node:'#00f0ff', halo:'#67e8f9'}, memory_session:{node:'#ff007f', halo:'#f472b6'},
    memory_agent:{node:'#9b00ff', halo:'#c084fc'}, memory_episode:{node:'#00ff7f', halo:'#86efac'}, memory_entity:{node:'#ffe600', halo:'#fef08a'}
  },
  dracula: {
    memory_topic: {node:'#8be9fd', halo:'#c4f1ff'}, memory_session:{node:'#ffb86c', halo:'#ffd19a'},
    memory_agent:{node:'#bd93f9', halo:'#d8b4fe'}, memory_episode:{node:'#50fa7b', halo:'#a7f3d0'}, memory_entity:{node:'#ff79c6', halo:'#f9a8d4'}
  },
  solarized: {
    memory_topic: {node:'#268bd2', halo:'#7dc4f2'}, memory_session:{node:'#b58900', halo:'#e9c46a'},
    memory_agent:{node:'#6c71c4', halo:'#a5a9e2'}, memory_episode:{node:'#2aa198', halo:'#74d8d1'}, memory_entity:{node:'#d33682', halo:'#ec8fba'}
  },
  nordic: {
    memory_topic: {node:'#88c0d0', halo:'#b7dce5'}, memory_session:{node:'#d08770', halo:'#e5ac99'},
    memory_agent:{node:'#b48ead', halo:'#d3b8cc'}, memory_episode:{node:'#a3be8c', halo:'#c7ddb5'}, memory_entity:{node:'#8fbcbb', halo:'#b7dedd'}
  },
  vaporwave: {
    memory_topic: {node:'#ff71ce', halo:'#ffb3e5'}, memory_session:{node:'#fe75fe', halo:'#ffb4ff'},
    memory_agent:{node:'#b967ff', halo:'#d3a3ff'}, memory_episode:{node:'#05ffa1', halo:'#82ffd0'}, memory_entity:{node:'#fffb96', halo:'#fffcc9'}
  },
  mono: {
    memory_topic: {node:'#e2e8f0', halo:'#f8fafc'}, memory_session:{node:'#94a3b8', halo:'#cbd5e1'},
    memory_agent:{node:'#64748b', halo:'#94a3b8'}, memory_episode:{node:'#cbd5e1', halo:'#e2e8f0'}, memory_entity:{node:'#f8fafc', halo:'#ffffff'}
  },
  matrix: {
    memory_topic: {node:'#22c55e', halo:'#86efac'}, memory_session:{node:'#16a34a', halo:'#4ade80'},
    memory_agent:{node:'#15803d', halo:'#22c55e'}, memory_episode:{node:'#4ade80', halo:'#bbf7d0'}, memory_entity:{node:'#a3e635', halo:'#d9f99d'}
  },
  community: {
    memory_topic: {node:'#38bdf8', halo:'#7dd3fc'}, memory_session:{node:'#f59e0b', halo:'#fbbf24'},
    memory_agent:{node:'#a78bfa', halo:'#c4b5fd'}, memory_episode:{node:'#10b981', halo:'#6ee7b7'}, memory_entity:{node:'#14b8a6', halo:'#5eead4'}
  },
};

const MEMORY_COLOR_KEY = 'graphtyn-memory-colors-v1';
const MEMORY_CUSTOM_COLOR_KEY = 'graphtyn-memory-custom-colors-v1';
const MEMORY_PALETTE_KEY = 'graphtyn-memory-palette-v1';
const VISUAL_PREF_KEY = 'graphtyn-visual-prefs-v1';
const HEX_COLOR = /^#[0-9a-f]{6}$/i;

function readJsonStorage(key) {
  try { return JSON.parse(localStorage.getItem(key) || 'null'); } catch (_) { return null; }
}

function writeJsonStorage(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch (_) { /* storage opcional */ }
}

export function loadVisualPreferences() {
  const saved = readJsonStorage(VISUAL_PREF_KEY);
  if (saved && typeof saved === 'object') {
    if (typeof saved.radianceOn === 'boolean') state.radianceOn = saved.radianceOn;
    if (typeof saved.vertexBlinkOn === 'boolean') state.vertexBlinkOn = saved.vertexBlinkOn;
  }
}

export function saveVisualPreferences() {
  writeJsonStorage(VISUAL_PREF_KEY, {radianceOn: state.radianceOn, vertexBlinkOn: state.vertexBlinkOn});
}

loadVisualPreferences();

function cloneMemoryColors(value, linkHaloByDefault = true) {
  return Object.fromEntries(Object.entries(MEMORY_COLOR_DEFAULTS).map(([kind, defaults]) => {
    const saved = value && typeof value[kind] === 'object' ? value[kind] : {};
    const node = HEX_COLOR.test(saved.node || '') ? saved.node : defaults.node;
    const halo = HEX_COLOR.test(saved.halo || '') ? saved.halo : defaults.halo;
    const linkedHalo = Object.prototype.hasOwnProperty.call(saved, 'linkedHalo')
      ? saved.linkedHalo !== false
      : linkHaloByDefault;
    return [kind, { ...defaults, node, halo, linkedHalo }];
  }));
}

export function getMemoryColors() {
  if (state.memoryColors) return state.memoryColors;
  const saved = readJsonStorage(MEMORY_COLOR_KEY);
  state.memoryColors = cloneMemoryColors(saved);
  return state.memoryColors;
}

export function getMemoryPalette() {
  if (state.memoryPalette) return state.memoryPalette;
  let saved = null;
  try { saved = localStorage.getItem(MEMORY_PALETTE_KEY); } catch (_) { /* valores por defecto */ }
  state.memoryPalette = (saved && (MEMORY_PALETTES[saved] || saved === 'custom')) ? saved : 'obsidian';
  return state.memoryPalette;
}

export function getMemoryColor(kind, part = 'node') {
  const colors = getMemoryColors();
  const item = colors[kind] || colors.memory_topic;
  if (part === 'halo' && item.linkedHalo) return item.node;
  return item[part] || item.node;
}

export function saveMemoryColors() {
  writeJsonStorage(MEMORY_COLOR_KEY, getMemoryColors());
  if (getMemoryPalette() === 'custom') writeJsonStorage(MEMORY_CUSTOM_COLOR_KEY, getMemoryColors());
}

function saveMemoryPalette() {
  try { localStorage.setItem(MEMORY_PALETTE_KEY, getMemoryPalette()); } catch (_) { /* storage opcional */ }
}

function markMemoryCustom() {
  state.memoryPalette = 'custom';
  saveMemoryPalette();
  writeJsonStorage(MEMORY_CUSTOM_COLOR_KEY, getMemoryColors());
}

export function markMemoryColorsCustom() {
  markMemoryCustom();
  saveMemoryColors();
}

export function updateMemoryColor(kind, part, value) {
  const colors = getMemoryColors();
  if (!colors[kind] || !HEX_COLOR.test(value || '')) return;
  colors[kind][part] = value;
  if (part === 'node' && colors[kind].linkedHalo) colors[kind].halo = value;
  markMemoryCustom();
  saveMemoryColors();
}

export function applyMemoryPalette(name) {
  const palette = String(name || '').toLowerCase();
  if (palette === 'custom') {
    const saved = readJsonStorage(MEMORY_CUSTOM_COLOR_KEY);
    if (saved) state.memoryColors = cloneMemoryColors(saved);
    state.memoryPalette = 'custom';
    saveMemoryPalette();
    saveMemoryColors();
    return;
  }
  if (!MEMORY_PALETTES[palette]) return;
  if (getMemoryPalette() === 'custom') writeJsonStorage(MEMORY_CUSTOM_COLOR_KEY, getMemoryColors());
  // Presets intentionally carry independent halo colors. Manual settings
  // keep their explicit linked/unlinked choice through the saved snapshot.
  state.memoryColors = cloneMemoryColors(MEMORY_PALETTES[palette], false);
  state.memoryPalette = palette;
  saveMemoryPalette();
  saveMemoryColors();
}

export function resetMemoryColor(kind) {
  const colors = getMemoryColors();
  if (!MEMORY_COLOR_DEFAULTS[kind]) return;
  colors[kind] = { ...MEMORY_COLOR_DEFAULTS[kind] };
  markMemoryCustom();
  saveMemoryColors();
}

export function resetMemoryColors() {
  state.memoryColors = cloneMemoryColors(MEMORY_PALETTES.obsidian, false);
  state.memoryPalette = 'obsidian';
  saveMemoryPalette();
  saveMemoryColors();
}

    export const PALETTES = {
      obsidian  : { file:'#38bdf8', class:'#f59e0b', func:'#a78bfa', agent:'#a855f7', asset:'#10b981', link:'rgba(148,163,184,0.30)', linkW:1.4, particle:'rgba(56,189,248,0.8)' },
      cyberpunk : { file:'#00f0ff', class:'#ffe600', func:'#ff007f', agent:'#9b00ff', asset:'#00ff7f', link:'rgba(0,240,255,0.25)',   linkW:1.4, particle:'rgba(0,240,255,0.9)' },
      dracula   : { file:'#ff79c6', class:'#bd93f9', func:'#8be9fd', agent:'#ffb86c', asset:'#50fa7b', link:'rgba(189,147,249,0.30)', linkW:1.4, particle:'rgba(255,121,198,0.9)' },
      solarized : { file:'#268bd2', class:'#b58900', func:'#d33682', agent:'#6c71c4', asset:'#2aa198', link:'rgba(38,139,210,0.30)',  linkW:1.4, particle:'rgba(42,161,152,0.9)' },
      nordic    : { file:'#88c0d0', class:'#ebcb8b', func:'#b48ead', agent:'#d08770', asset:'#a3be8c', link:'rgba(136,192,208,0.30)', linkW:1.4, particle:'rgba(235,203,139,0.9)' },
      vaporwave : { file:'#ff71ce', class:'#fffb96', func:'#b967ff', agent:'#fe75fe', asset:'#05ffa1', link:'rgba(255,113,206,0.30)', linkW:1.4, particle:'rgba(5,255,161,0.9)' },
      mono      : { file:'#e2e8f0', class:'#cbd5e1', func:'#94a3b8', agent:'#64748b', asset:'#f8fafc', link:'rgba(226,232,240,0.18)', linkW:0.9, particle:'rgba(226,232,240,0.7)' },
      matrix    : { file:'#22c55e', class:'#4ade80', func:'#16a34a', agent:'#15803d', asset:'#86efac', link:'rgba(34,197,94,0.25)',   linkW:1.4, particle:'rgba(34,197,94,0.9)' },
      community : { link:'rgba(148,163,184,0.30)', linkW:1.4, particle:'rgba(56,189,248,0.8)' },
      custom    : { file:'#38bdf8', class:'#f59e0b', func:'#a78bfa', agent:'#a855f7', asset:'#10b981', link:'rgba(148,163,184,0.30)', linkW:1.4, particle:'rgba(56,189,248,0.8)' }
    }
    export const COMM_COLORS = ['#38bdf8','#f59e0b','#ef4444','#10b981','#a78bfa','#ec4899','#06b6d4','#84cc16','#eab308','#6366f1','#f97316','#14b8a6'];;

export function getCommKey(n) {
      if (!n) return 'general';
      let path = n.path || '';
      if (!path && n.id) {
        const parts = n.id.split(':');
        if (parts.length >= 2) {
          path = parts[1];
        } else {
          path = n.id;
        }
      }
      if (!path) path = n.name || 'general';
      const sep = path.includes('/') ? '/' : '\\\\';
      const segments = path.split(sep).filter(Boolean);
      if (segments.length > 1) {
        return segments[segments.length - 2];
      }
      const leaf = segments[0] || 'general';
      const dotIdx = leaf.indexOf('.');
      return dotIdx > 0 ? leaf.substring(0, dotIdx) : leaf;
    }

export function mixColor(hex, f) {
      const m = /^#?([0-9a-f]{6})$/i.exec(hex || '');
      if (!m) return hex;
      const n = parseInt(m[1], 16);
      const r = (n >> 16) & 255, g = (n >> 8) & 255, b = n & 255;
      const lr = Math.round(r + (255 - r) * f);
      const lg = Math.round(g + (255 - g) * f);
      const lb = Math.round(b + (255 - b) * f);
      return `rgb(${lr},${lg},${lb})`;
    }

export function hexRgb(hex) {
      const m = /^#?([0-9a-f]{6})$/i.exec(hex || '');
      if (!m) return [255, 90, 175];
      const n = parseInt(m[1], 16);
      return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
    }

// ForceGraph otherwise advances every directional particle with the same
// global clock. A stable profile per link gives each signal its own phase,
// speed and particle count, so departures and arrivals are staggered without
// random jitter on every repaint.
function particleSeed(link) {
      const source = link && typeof link.source === 'object' ? link.source.id : link?.source;
      const target = link && typeof link.target === 'object' ? link.target.id : link?.target;
      const raw = String(link?.id || `${source || ''}>${target || ''}:${link?.label || ''}`);
      let hash = 2166136261;
      for (let i = 0; i < raw.length; i++) {
        hash ^= raw.charCodeAt(i);
        hash = Math.imul(hash, 16777619);
      }
      return (hash >>> 0) / 4294967295;
    }

export function particleProfile(link, baseSpeed = 0.006) {
      if (!link || typeof link !== 'object') return {speed: baseSpeed, count: 2};
      if (!link._particleProfile || link._particleProfile.baseSpeed !== baseSpeed) {
        const seed = particleSeed(link);
        const offsetSeed = particleSeed({
          id: `${link.id || ''}:offset`, source: link.source, target: link.target, label: link.label
        });
        const countSeed = particleSeed({
          id: `${link.id || ''}:count`, source: link.source, target: link.target, label: link.label
        });
        link._particleProfile = {
          baseSpeed,
          speed: baseSpeed * (0.58 + seed * 0.84),
          offset: 0.05 + offsetSeed * 0.9,
          count: countSeed < 0.22 ? 1 : (countSeed < 0.82 ? 2 : 3)
        };
      }
      return link._particleProfile;
    }

export function showStyleErr(msg) {
      const box = document.createElement('div');
      box.style.cssText = 'position:absolute;bottom:70px;left:16px;z-index:500;background:#7f1d1d;color:#fecaca;padding:8px 12px;border-radius:8px;font-size:12px;border:1px solid #ef4444;';
      box.textContent = 'Estilo: ' + msg;
      document.body.appendChild(box);
      setTimeout(() => box.remove(), 7000);
    }

export function safePaint(fn, label) {
      let reported = false;
      return function (...args) {
        try { return fn.apply(this, args); }
        catch (e) {
          if (!reported) { reported = true; showStyleErr(label + ': ' + (e && e.message ? e.message : e)); console.error('[estilo:' + label + ']', e); }
        }
      };
    }
