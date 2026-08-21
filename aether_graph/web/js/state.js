// Estado compartido del dashboard (mutable por todos los módulos)
export const state = {
  activePath: null,
  activeView: 'code',
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
  fullData: { nodes: [], links: [] },
  respectMap: {},
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
  organic3dOn: true,
  commColorMap: {},
  selectedNode: null,
  selectedNeighbors: null,
  descExpanded: false,
  watchVersions: {},
  watchTimer: null,
  prBase: '',
};

    export const PALETTES = {
      obsidian  : { file:'#38bdf8', class:'#f59e0b', func:'#a78bfa', agent:'#a855f7', asset:'#10b981', link:'rgba(148,163,184,0.30)', linkW:1.4, particle:'rgba(56,189,248,0.8)' },
      cyberpunk : { file:'#00f0ff', class:'#ffe600', func:'#ff007f', agent:'#9b00ff', asset:'#00ff7f', link:'rgba(0,240,255,0.25)',   linkW:1.4, particle:'rgba(0,240,255,0.9)' },
      dracula   : { file:'#ff79c6', class:'#bd93f9', func:'#8be9fd', agent:'#ffb86c', asset:'#50fa7b', link:'rgba(189,147,249,0.30)', linkW:1.4, particle:'rgba(255,121,198,0.9)' },
      solarized : { file:'#268bd2', class:'#b58900', func:'#d33682', agent:'#6c71c4', asset:'#2aa198', link:'rgba(38,139,210,0.30)',  linkW:1.4, particle:'rgba(42,161,152,0.9)' },
      nordic    : { file:'#88c0d0', class:'#ebcb8b', func:'#b48ead', agent:'#d08770', asset:'#a3be8c', link:'rgba(136,192,208,0.30)', linkW:1.4, particle:'rgba(235,203,139,0.9)' },
      vaporwave : { file:'#ff71ce', class:'#fffb96', func:'#b967ff', agent:'#fe75fe', asset:'#05ffa1', link:'rgba(255,113,206,0.30)', linkW:1.4, particle:'rgba(5,255,161,0.9)' },
      mono      : { file:'#e2e8f0', class:'#cbd5e1', func:'#94a3b8', agent:'#64748b', asset:'#f8fafc', link:'rgba(226,232,240,0.18)', linkW:0.9, particle:'rgba(226,232,240,0.7)' },
      matrix    : { file:'#22c55e', class:'#4ade80', func:'#16a34a', agent:'#15803d', asset:'#86efac', link:'rgba(34,197,94,0.25)',   linkW:1.4, particle:'rgba(34,197,94,0.9)' },
      community : { link:'rgba(148,163,184,0.30)', linkW:1.4, particle:'rgba(56,189,248,0.8)' }
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
