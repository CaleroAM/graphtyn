import { state, PALETTES, getCommKey, hexRgb, mixColor } from './state.js';

export function isDocOrMedia(n) {
      if (!n) return false;
      const k = (n.kind || '').toLowerCase();
      if (k === 'image' || k === 'media' || k === 'doc') return true;
      const name = (n.name || '').toLowerCase();
      const id = (n.id || '').toLowerCase();
      const raw = name || id;
      return raw.endsWith('.png') || raw.endsWith('.jpg') || raw.endsWith('.jpeg') || raw.endsWith('.webp') ||
             raw.endsWith('.gif') || raw.endsWith('.bmp') || raw.endsWith('.svg') ||
             raw.endsWith('.mp3') || raw.endsWith('.wav') || raw.endsWith('.m4a') || raw.endsWith('.ogg') ||
             raw.endsWith('.mp4') || raw.endsWith('.mov') || raw.endsWith('.webm') ||
             raw.endsWith('.pdf') || raw.endsWith('.docx') || raw.endsWith('.xlsx') || raw.endsWith('.xlsm') ||
             raw.endsWith('.md') || raw.endsWith('.txt');
    }

export function nodeColor(n) {
      if (n.god) return '#f472b6';
      if (isDocOrMedia(n)) return '#ffffff';
      if (state.activePalette === 'community') {
        const commKey = getCommKey(n);
        return state.commColorMap[commKey] || '#38bdf8';
      }
      const p = PALETTES[state.activePalette] || PALETTES.obsidian;
      const k = n.kind || '';
      if (k.includes('orchestrator')) return '#a855f7';
      if (k.includes('agent'))        return '#7c3aed';
      if (k.includes('hermes'))       return '#06b6d4';
      if (k === 'community')          return '#10b981';
      if (k === 'semantic_concept')   return '#ec4899';
      if (k === 'route')              return '#14b8a6';
      if (k === 'file' || k === 'module' || k === 'scene') return p.file;
      if (k === 'class' || k === 'interface' || k === 'csharp' || k === 'struct') return p.class;
      if (k === 'function' || k === 'method') return p.func;
      if (k === 'asset' || k === 'ui' || k === 'enum') return p.asset;
      return p.file;
    }

export function nodeVal(n) {
      const k = n.kind || '';
      if (n.god) return state.activeDim === '2d' ? 16 : 18;
      if (k === 'community' || k === 'semantic_concept') return state.activeDim === '2d' ? 12 : 14;
      if (k.includes('orchestrator')) return state.activeDim === '2d' ? 22 : 26;
      if (k.includes('agent') || k.includes('hermes')) return state.activeDim === '2d' ? 14 : 16;
      if (k === 'class' || k === 'interface' || k === 'struct') return state.activeDim === '2d' ? 10 : 12;
      if (k === 'route') return state.activeDim === '2d' ? 11 : 13;
      if (k === 'file' || k === 'module') return state.activeDim === '2d' ? 8 : 10;
      if (isDocOrMedia(n)) return state.activeDim === '2d' ? 9 : 11;
      return state.activeDim === '2d' ? 7 : 9;
    }

export function squareNodePainter(node, ctx) {
      const isSelected = state.selectedNode && state.selectedNode.id === node.id;
      const isNeighbor = state.selectedNeighbors && state.selectedNeighbors.has(node.id);
      const hasSelection = !!state.selectedNode;

      ctx.save();
      if (hasSelection && !isSelected && !isNeighbor) {
        ctx.globalAlpha = 0.2;
      }
      const nx = node.x || 0, ny = node.y || 0;
      const base = Math.max(3.0, Math.sqrt(Math.max(0, nodeVal(node) || 1)) * 2.8);
      const size = base * 0.95 * (isSelected ? 1.4 : 1.0);
      ctx.translate(nx, ny);
      ctx.rotate(0.5 + (nx * 0.002));
      ctx.fillStyle = isSelected ? '#ff007f' : nodeColor(node);
      ctx.fillRect(-size / 2, -size / 2, size, size);
      ctx.strokeStyle = isSelected ? '#ffffff' : (isDocOrMedia(node) ? '#ffffff' : 'rgba(255,255,255,0.28)');
      ctx.lineWidth = isSelected ? 2.0 : 0.8;
      ctx.strokeRect(-size / 2, -size / 2, size, size);
      ctx.restore();
    }

export function neuralNodePainter(node, ctx) {
      const isSelected = state.selectedNode && state.selectedNode.id === node.id;
      const isNeighbor = state.selectedNeighbors && state.selectedNeighbors.has(node.id);
      const hasSelection = !!state.selectedNode;

      ctx.save();
      if (hasSelection && !isSelected && !isNeighbor) {
        ctx.globalAlpha = 0.2;
      }

      const nx = node.x || 0, ny = node.y || 0;
      const base = Math.max(3.0, Math.sqrt(Math.max(0, nodeVal(node) || 1)) * 2.8);
      const simE = state.pulseSim ? (state.pulseSim.energy.get(node.id) || 0) : 0;
      const glow = Math.min(1, (isSelected ? 1.0 : (node.god ? 0.9 : 0.18 + Math.min(0.6, (node.degree || 0) / 25))) + simE * 0.6);
      const breathe = 0.5 + 0.5 * Math.sin(state.neuralPhase + nx * 0.008 + (node.degree || 0) * 0.4);
      const a = isSelected ? 1.0 : (glow * (0.55 + 0.45 * breathe));
      const halo = base * (isSelected ? 3.5 : (2.4 + 1.2 * breathe));
      const isWhite = isDocOrMedia(node);

      const g = ctx.createRadialGradient(nx, ny, 0, nx, ny, halo);
      if (isSelected) {
        g.addColorStop(0, `rgba(255,0,128,1)`);
        g.addColorStop(0.5, `rgba(255,0,128,0.6)`);
        g.addColorStop(1, 'rgba(255,0,128,0)');
      } else if (isWhite) {
        g.addColorStop(0, `rgba(255,255,255,${Math.min(0.95, a)})`);
        g.addColorStop(0.4, `rgba(220,235,255,${Math.min(0.7, a * 0.7)})`);
        g.addColorStop(1, 'rgba(200,225,255,0)');
      } else {
        g.addColorStop(0, `rgba(255,190,225,${Math.min(0.9, a)})`);
        g.addColorStop(0.4, `rgba(255,90,175,${Math.min(0.6, a * 0.6)})`);
        g.addColorStop(1, 'rgba(255,90,175,0)');
      }
      ctx.fillStyle = g;
      ctx.beginPath(); ctx.arc(nx, ny, halo, 0, Math.PI * 2); ctx.fill();

      const bc = hexRgb(isSelected ? '#ff007f' : (isWhite ? '#ffffff' : (state.nodeColorHex || nodeColor(node))));
      const coreC = isSelected
        ? [255, 255, 255]
        : (node.god
          ? [255, 220, 240]
          : (isWhite
            ? [255, 255, 255]
            : [Math.round(bc[0] + (255 - bc[0]) * glow * 0.55), Math.round(bc[1] + (255 - bc[1]) * glow * 0.55), Math.round(bc[2] + (255 - bc[2]) * glow * 0.55)]));

      ctx.fillStyle = `rgb(${coreC[0]},${coreC[1]},${coreC[2]})`;
      if (state.nodeShape === 'squares') {
        ctx.save();
        ctx.translate(nx, ny);
        ctx.rotate(0.6);
        const s = base * 0.85;
        ctx.fillRect(-s / 2, -s / 2, s, s);
        ctx.restore();
      } else {
        ctx.beginPath(); ctx.arc(nx, ny, isSelected ? base * 0.85 : base * 0.65, 0, Math.PI * 2); ctx.fill();
      }

      if (isSelected) {
        ctx.strokeStyle = '#ffffff';
        ctx.lineWidth = 2.0;
        ctx.beginPath();
        ctx.arc(nx, ny, halo * 0.8, 0, Math.PI * 2);
        ctx.stroke();
      }

      ctx.restore();
    }

export function neuralLinkPainter(link, ctx) {
      const s = link.source || {}, t = link.target || {};
      const sid = typeof s === 'object' ? s.id : s;
      const tid = typeof t === 'object' ? t.id : t;
      const hasSelection = !!state.selectedNode;
      const isConnected = hasSelection && (state.selectedNode.id === sid || state.selectedNode.id === tid);

      ctx.save();
      if (hasSelection && !isConnected) {
        ctx.globalAlpha = 0.08;
      }
      const sx = s.x || 0, sy = s.y || 0, tx = t.x || 0, ty = t.y || 0;
      const dx = tx - sx, dy = ty - sy;
      const dist = Math.hypot(dx, dy) || 1;
      if (link._tw === undefined) link._tw = Math.random() * Math.PI * 2;
      const tw = state.vertexBlinkOn ? (0.72 + 0.28 * Math.sin(state.neuralPhase * 1.2 + link._tw)) : 1;
      const curved = state.linkStyle === 'curved';
      const dashed = state.linkStyle === 'dashed';
      const mx = (sx + tx) / 2, my = (sy + ty) / 2;
      const bend = dist * 0.16;
      const cx = mx + (-dy / dist) * bend, cy = my + (dx / dist) * bend;
      const qp = (tt) => {
        const mm = 1 - tt;
        return {
          x: mm * mm * sx + 2 * mm * tt * cx + tt * tt * tx,
          y: mm * mm * sy + 2 * mm * tt * cy + tt * tt * ty
        };
      };
      const lc = hexRgb(state.linkColorHex);
      const w = 0.7 + Math.min(2.6, ((s.degree || 0) + (t.degree || 0)) / 30) + (link.confidence === 'INFERRED' ? -0.2 : 0.2);
      const grad = ctx.createLinearGradient(sx, sy, tx, ty);
      grad.addColorStop(0, `rgba(${lc[0]},${lc[1]},${lc[2]},${(0.12 * tw).toFixed(3)})`);
      grad.addColorStop(0.5, `rgba(${Math.min(255, lc[0] + 50)},${Math.min(255, lc[1] + 50)},${Math.min(255, lc[2] + 50)},${(0.38 * tw).toFixed(3)})`);
      grad.addColorStop(1, `rgba(${lc[0]},${lc[1]},${lc[2]},${(0.30 * tw).toFixed(3)})`);
      ctx.strokeStyle = grad; ctx.lineWidth = isConnected ? w * 1.6 : w; ctx.lineCap = 'round';
      if (dashed) {
        ctx.setLineDash([4, 4]);
        ctx.lineDashOffset = -state.neuralPhase * 3;
      } else {
        ctx.setLineDash([]);
      }
      ctx.beginPath();
      if (curved) {
        ctx.moveTo(sx, sy); ctx.quadraticCurveTo(cx, cy, tx, ty);
      } else {
        ctx.moveTo(sx, sy); ctx.lineTo(tx, ty);
      }
      ctx.stroke();
      ctx.setLineDash([]);
      if (link._boutonT === undefined) link._boutonT = 0.18 + Math.random() * 0.64;
      const bt = link._boutonT, mt = 1 - bt;
      const bp = curved
        ? { x: mt * mt * sx + 2 * mt * bt * cx + bt * bt * tx, y: mt * mt * sy + 2 * mt * bt * cy + bt * bt * ty }
        : { x: sx + (tx - sx) * bt, y: sy + (ty - sy) * bt };
      ctx.fillStyle = `rgba(${lc[0]},${lc[1]},${lc[2]},${(0.8 * tw).toFixed(3)})`;
      ctx.beginPath(); ctx.arc(bp.x, bp.y, 1.7, 0, Math.PI * 2); ctx.fill();
      // PULSOS REALES de la simulacion (ráfagas viajando por la arista)
      if (state.pulseSim && state.graphStyle === 'neural') {
        const pc = hexRgb(state.pulseColorHex);
        for (const p of state.pulseSim.pulses) {
          if (p.link !== link) continue;
          const tt = p.from === s.id ? p.t : 1 - p.t;
          for (let k = 0; k < 5; k++) {
            const kk = Math.max(0, tt - k * 0.05);
            const pt = curved ? qp(kk) : { x: sx + (tx - sx) * kk, y: sy + (ty - sy) * kk };
            const fade = 1 - k / 5;
            const mix = k / 5;
            const cc = k === 0
              ? [255, 235, 245]
              : [Math.round(pc[0] + (255 - pc[0]) * (1 - mix)), Math.round(pc[1] + (255 - pc[1]) * (1 - mix)), Math.round(pc[2] + (255 - pc[2]) * (1 - mix))];
            const r = (k === 0 ? 11 : 6.5 - k);
            const g = ctx.createRadialGradient(pt.x, pt.y, 0, pt.x, pt.y, r);
            g.addColorStop(0, `rgba(${cc[0]},${cc[1]},${cc[2]},${(0.9 * fade).toFixed(3)})`);
            g.addColorStop(1, `rgba(${cc[0]},${cc[1]},${cc[2]},0)`);
            ctx.fillStyle = g;
            ctx.beginPath(); ctx.arc(pt.x, pt.y, r, 0, Math.PI * 2); ctx.fill();
          }
        }
      }
      ctx.restore();
    }

export function holoNodePainter(node, ctx) {
      const isSelected = state.selectedNode && state.selectedNode.id === node.id;
      const isNeighbor = state.selectedNeighbors && state.selectedNeighbors.has(node.id);
      const hasSelection = !!state.selectedNode;

      ctx.save();
      if (hasSelection && !isSelected && !isNeighbor) {
        ctx.globalAlpha = 0.35;
      }

      const nx = node.x || 0, ny = node.y || 0;
      const base = Math.max(3.0, Math.sqrt(Math.max(0, nodeVal(node) || 1)) * 2.8);
      const idle = 0.5 + 0.5 * Math.sin(state.neuralPhase * 0.9 + nx * 0.01 + (node.degree || 0) * 0.3);
      const simE = state.pulseSim ? (state.pulseSim.energy.get(node.id) || 0) : 0;
      const glow = Math.min(1, (isSelected ? 1.0 : (node.god ? 0.85 : 0.12 + Math.min(0.5, (node.degree || 0) / 25))) + simE * 0.6);
      const r = base * (0.8 + 0.3 * idle) * (node.god || isSelected ? 1.35 : 1);
      const isWhite = isDocOrMedia(node);

      const col = isSelected ? [255, 0, 128] : (isWhite ? [255, 255, 255] : (node.god ? [190, 240, 255] : [70, 210, 255]));
      const c = [
        Math.min(255, col[0] + (255 - col[0]) * glow),
        Math.min(255, col[1] + (255 - col[1]) * glow),
        Math.min(255, col[2] + (255 - col[2]) * glow)
      ];
      const haloR = r * (isSelected ? 3.8 : 3.2);
      const halo = ctx.createRadialGradient(nx, ny, 0, nx, ny, haloR);
      halo.addColorStop(0, `rgba(${c[0] | 0},${c[1] | 0},${c[2] | 0},${0.5 + glow * 0.3})`);
      halo.addColorStop(1, `rgba(${c[0] | 0},${c[1] | 0},${c[2] | 0},0)`);
      ctx.fillStyle = halo;
      ctx.beginPath(); ctx.arc(nx, ny, haloR, 0, Math.PI * 2); ctx.fill();
      const ang = state.neuralPhase * 0.5 + (nx * 0.01);
      const s2 = Math.max(0.8, r * 1.1);
      const bright = `rgba(${Math.min(255, c[0] + 60) | 0},${Math.min(255, c[1] + 60) | 0},${Math.min(255, c[2] + 60) | 0},0.95)`;
      ctx.save();
      ctx.translate(nx, ny);
      ctx.rotate(ang);
      ctx.fillStyle = bright;
      if (state.nodeShape === 'squares') {
        ctx.fillRect(-s2 * 0.8, -s2 * 0.8, s2 * 1.6, s2 * 1.6);
      } else {
        ctx.beginPath();
        ctx.moveTo(0, -s2); ctx.lineTo(s2, 0); ctx.lineTo(0, s2); ctx.lineTo(-s2, 0);
        ctx.closePath();
        ctx.fill();
      }
      ctx.restore();
      if (node.god || isSelected) {
        ctx.save();
        ctx.translate(nx, ny);
        ctx.rotate(-ang * 0.6);
        ctx.strokeStyle = isSelected ? '#ffffff' : `rgba(190,240,255,${0.35 + glow * 0.4})`;
        ctx.lineWidth = isSelected ? 1.5 : Math.max(0.4, 0.7);
        ctx.setLineDash([5, 3]);
        ctx.beginPath();
        ctx.ellipse(0, 0, r * 3.2, r * 3.2 * 0.82, 0, 0, Math.PI * 2);
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.restore();
      }
      ctx.restore();
    }

export function holoLinkPainter(link, ctx) {
      const s = link.source || {}, t = link.target || {};
      const sid = typeof s === 'object' ? s.id : s;
      const tid = typeof t === 'object' ? t.id : t;
      const hasSelection = !!state.selectedNode;
      const isConnected = hasSelection && (state.selectedNode.id === sid || state.selectedNode.id === tid);

      ctx.save();
      if (hasSelection && !isConnected) {
        ctx.globalAlpha = 0.08;
      }
      const sx = s.x || 0, sy = s.y || 0, tx = t.x || 0, ty = t.y || 0;
      if (link._dash === undefined) link._dash = Math.random() < 0.18;
      const act = 0.25 + 0.75 * Math.abs(Math.sin(state.neuralPhase * 0.6 + (link.index !== undefined ? link.index : 0) * 0.7));
      const w = (0.5 + Math.min(1.8, ((s.degree || 0) + (t.degree || 0)) / 30)) * (1 + 0.6 * act);
      const col = isConnected ? [255, 100, 200] : [30 + act * 200, 150 + act * 95, 220 + act * 35];
      ctx.strokeStyle = `rgba(${col[0] | 0},${col[1] | 0},${col[2] | 0},${isConnected ? 0.9 : 0.25 + 0.4 * act})`;
      ctx.lineWidth = isConnected ? Math.max(1.2, w * 1.6) : Math.max(0.3, w);
      if (link._dash) {
        ctx.setLineDash([4, 3]);
        ctx.lineDashOffset = -state.neuralPhase * 4;
      } else {
        ctx.setLineDash([]);
      }
      ctx.beginPath(); ctx.moveTo(sx, sy); ctx.lineTo(tx, ty); ctx.stroke();
      ctx.setLineDash([]);
      ctx.restore();
    }
