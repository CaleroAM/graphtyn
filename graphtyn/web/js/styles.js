import { state, hexRgb, mixColor, showStyleErr, safePaint } from './state.js';
import { nodeColor, nodeVal, isDocOrMedia, squareNodePainter, neuralNodePainter, neuralLinkPainter, holoNodePainter, holoLinkPainter } from './painters.js';
import { buildPulseSim } from './sim.js';

export function holoBgEnsure() {
      const container = document.getElementById('graph-container');
      if (!container) return;
      let bg = document.getElementById('holo-bg');
      if (!bg) {
        bg = document.createElement('canvas');
        bg.id = 'holo-bg';
        bg.style.cssText = 'position:absolute;top:0;left:0;width:100%;height:100%;pointer-events:none;';
        container.insertBefore(bg, container.firstChild);
        if (state.holoBgRo) { state.holoBgRo.disconnect(); }
        state.holoBgRo = new ResizeObserver(() => holoBgDraw());
        state.holoBgRo.observe(container);
      }
      holoBgDraw();
      if (state.graphInst) state.graphInst.backgroundColor('rgba(0,0,0,0)');
    }

export function holoBgDraw() {
      const bg = document.getElementById('holo-bg');
      if (!bg) return;
      const w = bg.clientWidth || (bg.parentElement && bg.parentElement.clientWidth) || 800;
      const h = bg.clientHeight || (bg.parentElement && bg.parentElement.clientHeight) || 600;
      bg.width = w; bg.height = h;
      const ctx = bg.getContext('2d');
      const g = ctx.createRadialGradient(w * 0.5, h * 0.45, 10, w * 0.5, h * 0.5, Math.max(w, h) * 0.75);
      g.addColorStop(0, '#071018');
      g.addColorStop(0.55, '#020308');
      g.addColorStop(1, '#000000');
      ctx.fillStyle = g;
      ctx.fillRect(0, 0, w, h);
      for (let k = 0; k < 220; k++) {
        const x = Math.random() * w, y = Math.random() * h;
        ctx.fillStyle = `rgba(190,225,255,${0.08 + Math.random() * 0.22})`;
        ctx.beginPath(); ctx.arc(x, y, Math.random() * 1.2 + 0.3, 0, Math.PI * 2); ctx.fill();
      }
      const gy = h * 0.8;
      ctx.strokeStyle = 'rgba(35,130,200,0.16)';
      ctx.lineWidth = 1;
      for (let x = 0; x <= w; x += 62) {
        ctx.beginPath(); ctx.moveTo(x, gy); ctx.lineTo(x + (w * 0.2), h); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(x, gy); ctx.lineTo(x - (w * 0.2), h); ctx.stroke();
      }
      for (let z = gy; z <= h; z += 62) {
        ctx.beginPath(); ctx.moveTo(0, z); ctx.lineTo(w, z); ctx.stroke();
      }
      const pat = document.createElement('canvas');
      pat.width = 2; pat.height = 4;
      const pctx = pat.getContext('2d');
      pctx.fillStyle = 'rgba(150,220,255,0.035)';
      pctx.fillRect(0, 0, 2, 1);
      ctx.fillStyle = ctx.createPattern(pat, 'repeat');
      ctx.fillRect(0, 0, w, h);
    }

export function applyHitArea(inst) {
      if (!inst) return;
      // Re-apply nodePointerAreaPaint: this sets shadowGraph.nodeCanvasObject
      // to paint solid __indexColor circles (overriding the visual painter
      // that nodeCanvasObject() propagated to shadowGraph).
      if (typeof inst.nodePointerAreaPaint === 'function') {
        inst.nodePointerAreaPaint(paintNodePointerArea);
      }
      // Re-apply linkPointerAreaPaint: this sets shadowGraph.linkCanvasObject
      // to an empty function so links NEVER occlude node hit areas.
      // Without this, linkCanvasObject(neuralLinkPainter) propagates to
      // shadowGraph and paints wide glowing lines that block node detection.
      if (typeof inst.linkPointerAreaPaint === 'function') {
        inst.linkPointerAreaPaint(() => {});
      }
    }

export function paintNodePointerArea(node, color, ctx, globalScale) {
      const base = Math.max(3.5, Math.sqrt(Math.max(0, nodeVal(node) || 1)) * 3.0);
      const gs = Math.max(0.08, globalScale || 1);
      // Keep a usable target at low zoom without creating large, overlapping
      // invisible circles. Overlaps make the last painted node steal clicks
      // from nearby nodes in ForceGraph's colour-picking canvas.
      const r = Math.max(7 / gs, base * 1.15);
      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.arc(Number.isFinite(node.x) ? node.x : 0, Number.isFinite(node.y) ? node.y : 0, r, 0, 2 * Math.PI, false);
      ctx.fill();
    }

export function apply2DStyle() {
      if (state.neuralTimer) { clearInterval(state.neuralTimer); state.neuralTimer = null; }
      if (!state.graphInst) return;
      if (state.graphStyle === 'standard') {
        state.graphInst.backgroundColor('#0b0e17');
        if (state.nodeShape === 'squares') {
          state.graphInst
            .nodeCanvasObjectMode(() => 'replace')
            .nodeCanvasObject(safePaint(squareNodePainter, 'cuadrados'));
        } else {
          state.graphInst
            .nodeCanvasObjectMode(() => 'replace')
            .nodeCanvasObject(null);
        }
        state.graphInst.linkCanvasObject(null);
        applyHitArea(state.graphInst);
        return;
      }
      if (state.graphStyle === 'holo') {
        holoBgEnsure();
      } else {
        state.graphInst.backgroundColor('#0b0e17');
      }
      const paintNode = state.graphStyle === 'holo' ? holoNodePainter : neuralNodePainter;
      const paintLink = state.graphStyle === 'holo' ? holoLinkPainter : neuralLinkPainter;
      const safeNode = safePaint(paintNode, 'nodo');
      const safeLink = safePaint(paintLink, 'enlace');
      state.graphInst
        .nodeCanvasObjectMode(() => 'after')
        .nodeCanvasObject(safeNode)
        .linkCanvasObjectMode(() => 'replace')
        .linkCanvasObject(safeLink);
      applyHitArea(state.graphInst);
      state.graphInst._stylePaintNode = safeNode;
      state.graphInst._stylePaintLink = safeLink;
      state.graphInst.linkDirectionalParticles(state.showParticles ? 2 : 0)
        .linkDirectionalParticleWidth(2.4)
        .linkDirectionalParticleColor(() => (state.graphStyle === 'holo' ? '#7fd7ff' : '#ff5aaf'))
        .linkDirectionalParticleSpeed(state.graphStyle === 'holo' ? 0.02 : 0.012);
      state.neuralTimer = setInterval(() => {
        state.neuralPhase += 0.5;
        if (state.pulseSim && state.graphStyle === 'neural') state.pulseSim.update(90, performance.now());
      }, 90);
    }

export function apply3DStyle() {
      if (!state.graphInst) return;
      if (state.graphStyle === 'standard') {
        if (state.nodeShape === 'squares' && typeof THREE !== 'undefined') {
          state.graphInst.nodeThreeObject(n => {
            if (!n._cube) {
              n._cube = new THREE.Mesh(
                new THREE.BoxGeometry(2, 2, 2),
                new THREE.MeshBasicMaterial({ color: '#38bdf8' })
              );
            }
            n._cube.material.color.set(nodeColor(n));
            return n._cube;
          }).nodeThreeObjectExtend(false);
        }
        return;
      }

      // ── NEURONAL 3D ──
      const linkBase = hexRgb(state.linkColorHex);
      const container3d = document.getElementById('graph-container');
      let overlay = document.getElementById('pulse3d');
      if (!overlay && container3d) {
        overlay = document.createElement('canvas');
        overlay.id = 'pulse3d';
        overlay.style.cssText = 'position:absolute;top:0;left:0;width:100%;height:100%;pointer-events:none;z-index:5;';
        container3d.appendChild(overlay);
      }

      if (state.organic3dOn && overlay && typeof state.graphInst.graph2ScreenCoords === 'function') {
        // ── MODO ORGÁNICO: el estilo 2D Neuronal dibujado sobre el grafo 3D ──
        // Base 3D con esfera de interacción amplia para raycasting confiable
        state.graphInst.nodeThreeObject(null)
          .nodeRelSize(8)
          .linkColor(() => 'rgb(20,22,40)')
          .linkOpacity ? state.graphInst.linkOpacity(() => 0.04) : null;
        state.graphInst.linkDirectionalParticles(0);

        const octx = overlay.getContext('2d');
        const screen = (x, y, z) => {
          const s = state.graphInst.graph2ScreenCoords(x, y, z);
          return s || { x: -9999, y: -9999 };
        };
        const drawOrganic3D = (w, h) => {
          octx.clearRect(0, 0, w, h);
          octx.globalCompositeOperation = 'lighter';
          const pc = hexRgb(state.pulseColorHex);
          const lc = hexRgb(state.linkColorHex);
          const visNodes = state.graphInst.graphData().nodes || [];
          const visLinks = state.graphInst.graphData().links || [];
          // proyectar nodos visibles
          const pts = {};
          visNodes.forEach(n => {
            pts[n.id] = screen(n.x || 0, n.y || 0, n.z || 0);
          });
          // enlaces curvos orgánicos (curva bezier en pantalla)
          const linkDraw = [];
          visLinks.forEach(l => {
            const a = pts[l.source && l.source.id !== undefined ? l.source.id : l.source];
            const b = pts[l.target && l.target.id !== undefined ? l.target.id : l.target];
            if (!a || !b) return;
            const d = Math.hypot(b.x - a.x, b.y - a.y) || 1;
            linkDraw.push({ l, a, b, d, z: ((l.source && l.source.z) || 0) + ((l.target && l.target.z) || 0) });
          });
          linkDraw.sort((x, y) => x.z - y.z);
          const curved = state.linkStyle === 'curved';
          const dashed = state.linkStyle === 'dashed';
          for (const { l, a, b, d } of linkDraw) {
            if (l._side === undefined) l._side = Math.random() < 0.5 ? -1 : 1;
            if (l._bt === undefined) l._bt = 0.15 + Math.random() * 0.7;
            const bend = d * 0.16 * l._side;
            const nx = -(b.y - a.y) / d, ny = (b.x - a.x) / d;
            const cx = (a.x + b.x) / 2 + nx * bend, cy = (a.y + b.y) / 2 + ny * bend;
            const qp = (tt) => {
              if (!curved) return { x: a.x + (b.x - a.x) * tt, y: a.y + (b.y - a.y) * tt };
              const m = 1 - tt;
              return { x: m * m * a.x + 2 * m * tt * cx + tt * tt * b.x, y: m * m * a.y + 2 * m * tt * cy + tt * tt * b.y };
            };
            const act = l._activity || 0;
            const tw = state.vertexBlinkOn ? (0.72 + 0.28 * Math.sin(state.neuralPhase * 1.2 + (l._tw !== undefined ? l._tw : (l._tw = Math.random() * Math.PI * 2)))) : 1;
            const wBase = 0.7 + Math.min(2.4, (((l.source && l.source.degree) || 0) + ((l.target && l.target.degree) || 0)) / 30);
            const grad = octx.createLinearGradient(a.x, a.y, b.x, b.y);
            grad.addColorStop(0, `rgba(${lc[0]},${lc[1]},${lc[2]},${(0.10 * tw + 0.25 * act).toFixed(3)})`);
            grad.addColorStop(0.5, `rgba(${Math.min(255, lc[0] + 60)},${Math.min(255, lc[1] + 60)},${Math.min(255, lc[2] + 60)},${(0.40 * tw + 0.5 * act).toFixed(3)})`);
            grad.addColorStop(1, `rgba(${lc[0]},${lc[1]},${lc[2]},${(0.12 * tw + 0.3 * act).toFixed(3)})`);
            octx.strokeStyle = grad;
            octx.lineWidth = wBase * (1 + act * 1.2);
            octx.lineCap = 'round';
            if (dashed) {
              octx.setLineDash([5, 4]);
              octx.lineDashOffset = -state.neuralPhase * 4;
            }
            octx.beginPath();
            octx.moveTo(a.x, a.y);
            if (curved) {
              octx.quadraticCurveTo(cx, cy, b.x, b.y);
            } else {
              octx.lineTo(b.x, b.y);
            }
            octx.stroke();
            octx.setLineDash([]);
            // botón sináptico
            const bp = qp(l._bt);
            const bglow = 0.55 + 0.45 * Math.sin(state.neuralPhase * 1.6 + l._bt * 6.28);
            const bg = octx.createRadialGradient(bp.x, bp.y, 0, bp.x, bp.y, 5);
            bg.addColorStop(0, `rgba(${pc[0]},${pc[1]},${pc[2]},${(0.8 * bglow).toFixed(3)})`);
            bg.addColorStop(1, `rgba(${pc[0]},${pc[1]},${pc[2]},0)`);
            octx.fillStyle = bg;
            octx.beginPath(); octx.arc(bp.x, bp.y, 5, 0, Math.PI * 2); octx.fill();
            // cometas de la simulación
            if (state.pulseSim) {
              for (const p of state.pulseSim.pulses) {
                if (p.link !== l) continue;
                const tt = p.from === (l.source && l.source.id) ? p.t : 1 - p.t;
                const head = qp(tt);
                const tail = qp(Math.max(0, tt - 0.14));
                const glowG = octx.createLinearGradient(tail.x, tail.y, head.x, head.y);
                glowG.addColorStop(0, `rgba(${pc[0]},${pc[1]},${pc[2]},0)`);
                glowG.addColorStop(1, `rgba(${pc[0]},${pc[1]},${pc[2]},0.55)`);
                octx.strokeStyle = glowG;
                octx.lineWidth = 6;
                octx.beginPath(); octx.moveTo(tail.x, tail.y); octx.lineTo(head.x, head.y); octx.stroke();
                const coreG = octx.createLinearGradient(tail.x, tail.y, head.x, head.y);
                coreG.addColorStop(0, `rgba(${pc[0]},${pc[1]},${pc[2]},0)`);
                coreG.addColorStop(1, 'rgba(255,235,245,0.95)');
                octx.strokeStyle = coreG;
                octx.lineWidth = 2.2;
                octx.beginPath(); octx.moveTo(tail.x, tail.y); octx.lineTo(head.x, head.y); octx.stroke();
                const hg = octx.createRadialGradient(head.x, head.y, 0, head.x, head.y, 12);
                hg.addColorStop(0, `rgba(${pc[0]},${pc[1]},${pc[2]},0.85)`);
                hg.addColorStop(1, `rgba(${pc[0]},${pc[1]},${pc[2]},0)`);
                octx.fillStyle = hg;
                octx.beginPath(); octx.arc(head.x, head.y, 12, 0, Math.PI * 2); octx.fill();
                octx.fillStyle = 'rgba(255,242,248,0.95)';
                octx.beginPath(); octx.arc(head.x, head.y, 2.2, 0, Math.PI * 2); octx.fill();
              }
            }
          }
          // nodos: halos orgánicos con energía
          const nodeOrder = visNodes.slice().sort((a, b) => ((a.z || 0) - (b.z || 0)));
          for (const n of nodeOrder) {
            const sc = pts[n.id];
            if (!sc || sc.x < -100 || sc.x > w + 100 || sc.y < -100 || sc.y > h + 100) continue;
            const energy = state.pulseSim ? (state.pulseSim.energy.get(n.id) || 0) : 0;
            const breathe = 0.5 + 0.5 * Math.sin(state.neuralPhase * 1.3 + (n.degree || 0) * 0.4);
            const glow = Math.min(1, (n.god ? 0.85 : 0.15 + Math.min(0.5, (n.degree || 0) / 25)) + energy * 0.65);
            const isSelected = state.selectedNode && state.selectedNode.id === n.id;
            const isWhite = isDocOrMedia(n);
            const base = (n.god ? 7 : (isWhite ? 5.5 : 4.5)) * (0.8 + 0.3 * breathe) * (1 + energy * 0.6);
            const halo = base * (isSelected ? 3.5 : (2.6 + 1.2 * breathe));
            const g = octx.createRadialGradient(sc.x, sc.y, 0, sc.x, sc.y, halo);
            if (isSelected) {
              g.addColorStop(0, 'rgba(255,0,128,0.95)');
              g.addColorStop(0.5, 'rgba(255,0,128,0.5)');
              g.addColorStop(1, 'rgba(255,0,128,0)');
            } else if (isWhite) {
              g.addColorStop(0, `rgba(255,255,255,${Math.min(0.95, glow * 0.9).toFixed(3)})`);
              g.addColorStop(0.4, `rgba(220,235,255,${Math.min(0.7, glow * 0.6).toFixed(3)})`);
              g.addColorStop(1, 'rgba(200,225,255,0)');
            } else {
              g.addColorStop(0, `rgba(255,190,225,${Math.min(0.85, glow * 0.75).toFixed(3)})`);
              g.addColorStop(0.4, `rgba(${pc[0]},${pc[1]},${pc[2]},${Math.min(0.5, glow * 0.5).toFixed(3)})`);
              g.addColorStop(1, `rgba(${pc[0]},${pc[1]},${pc[2]},0)`);
            }
            octx.fillStyle = g;
            octx.beginPath(); octx.arc(sc.x, sc.y, halo, 0, Math.PI * 2); octx.fill();
            const bc = hexRgb(isSelected ? '#ff007f' : (isWhite ? '#ffffff' : (state.nodeColorHex || nodeColor(n))));
            const cc = isSelected ? [255, 255, 255] : (isWhite ? [255, 255, 255] : [
              Math.round(bc[0] + (255 - bc[0]) * glow * 0.6),
              Math.round(bc[1] + (255 - bc[1]) * glow * 0.6),
              Math.round(bc[2] + (255 - bc[2]) * glow * 0.6)
            ]);
            octx.fillStyle = `rgb(${cc[0]},${cc[1]},${cc[2]})`;
            if (state.nodeShape === 'squares') {
              octx.save();
              octx.translate(sc.x, sc.y);
              octx.rotate(0.6 + sc.x * 0.002);
              const s = base * 0.85;
              octx.fillRect(-s / 2, -s / 2, s, s);
              octx.restore();
            } else {
              octx.beginPath(); octx.arc(sc.x, sc.y, base * 0.45, 0, Math.PI * 2); octx.fill();
            }
          }
          octx.globalCompositeOperation = 'source-over';
        };

        if (state.pulse3dRaf) cancelAnimationFrame(state.pulse3dRaf);
        if (state.neuralTimer) { clearInterval(state.neuralTimer); state.neuralTimer = null; }
        let last3d = performance.now();
        const loop = (now) => {
          if (!state.graphInst || state.graphStyle !== 'neural' || !state.organic3dOn) { state.pulse3dRaf = null; return; }
          try {
            const dt = Math.min(120, now - last3d);
            last3d = now;
            state.neuralPhase += dt / 160;
            if (state.pulseSim) state.pulseSim.update(dt, now);
            const w = overlay.clientWidth || container3d.clientWidth || 800;
            const h = overlay.clientHeight || container3d.clientHeight || 600;
            if (overlay.width !== w) overlay.width = w;
            if (overlay.height !== h) overlay.height = h;
            drawOrganic3D(w, h);
          } catch (e) {
            showStyleErr('Orgánico3D: ' + (e && e.message ? e.message : e));
            console.error('[Orgánico3D]', e);
            state.pulse3dRaf = null;
            return;
          }
          state.pulse3dRaf = requestAnimationFrame(loop);
        };
        state.pulse3dRaf = requestAnimationFrame(loop);
        return;
      }

      // ── MODO COMETAS (sin orgánico): vista Estándar + luces ──
      const pulseLinkColor = l => {
        const off = l.index !== undefined ? l.index : 0;
        const blink = state.vertexBlinkOn ? (0.5 + 0.5 * Math.sin(state.neuralPhase * 2.4 - off * 1.1)) : 0.5;
        const act = l._activity || 0;
        const bright = 0.45 + 0.55 * blink + 0.85 * act;
        const r = Math.min(255, Math.round(linkBase[0] * bright));
        const g = Math.min(255, Math.round(linkBase[1] * bright));
        const b = Math.min(255, Math.round(linkBase[2] * bright));
        return `rgb(${r},${g},${b})`;
      };
      const pulseOpacity = l => {
        const off = l.index !== undefined ? l.index : 0;
        const blink = state.vertexBlinkOn ? (0.5 + 0.5 * Math.sin(state.neuralPhase * 2.4 - off * 1.1)) : 0.5;
        const act = l._activity || 0;
        return Math.min(1, 0.3 + 0.4 * blink + 0.3 * act);
      };
      const pulseNodeColor = n => {
        const energy = state.pulseSim ? (state.pulseSim.energy.get(n.id) || 0) : 0;
        const breathe = 0.5 + 0.5 * Math.sin(state.neuralPhase * 1.4 + (n.degree || 0) * 0.35);
        const glow = Math.min(1, 0.15 + 0.15 * breathe + energy * 0.85);
        return mixColor(state.nodeColorHex || nodeColor(n), glow);
      };
      try {
        state.graphInst.linkColor(pulseLinkColor);
        if (state.graphInst.linkOpacity) state.graphInst.linkOpacity(pulseOpacity);
        state.graphInst.nodeColor(pulseNodeColor);
        state.graphInst.linkWidth(l => 0.8 + Math.min(2.5, ((l.source && l.source.degree || 0) + (l.target && l.target.degree || 0)) / 30));
      } catch (e) { console.warn('linkStyle3D', e); }

      if (overlay && typeof state.graphInst.graph2ScreenCoords === 'function') {
        const octx = overlay.getContext('2d');
        const drawPulses3D = (w, h) => {
          octx.clearRect(0, 0, w, h);
          if (!state.pulseSim || !state.graphInst) return;
          const pc = hexRgb(state.pulseColorHex);
          octx.lineCap = 'round';
          for (const p of state.pulseSim.pulses) {
            const s = p.link.source || {}, t = p.link.target || {};
            const a = { x: s.x || 0, y: s.y || 0, z: s.z || 0 };
            const b = { x: t.x || 0, y: t.y || 0, z: t.z || 0 };
            const tt = p.from === s.id ? p.t : 1 - p.t;
            const tailT = Math.max(0, tt - 0.16);
            const scH = state.graphInst.graph2ScreenCoords(a.x + (b.x - a.x) * tt, a.y + (b.y - a.y) * tt, a.z + (b.z - a.z) * tt);
            const scT = state.graphInst.graph2ScreenCoords(a.x + (b.x - a.x) * tailT, a.y + (b.y - a.y) * tailT, a.z + (b.z - a.z) * tailT);
            if (!scH || !scT) continue;
            if (scH.x < -80 || scH.x > w + 80 || scH.y < -80 || scH.y > h + 80) continue;
            const glowGrad = octx.createLinearGradient(scT.x, scT.y, scH.x, scH.y);
            glowGrad.addColorStop(0, `rgba(${pc[0]},${pc[1]},${pc[2]},0)`);
            glowGrad.addColorStop(0.6, `rgba(${pc[0]},${pc[1]},${pc[2]},0.28)`);
            glowGrad.addColorStop(1, `rgba(${pc[0]},${pc[1]},${pc[2]},0.55)`);
            octx.strokeStyle = glowGrad;
            octx.lineWidth = 6;
            octx.beginPath(); octx.moveTo(scT.x, scT.y); octx.lineTo(scH.x, scH.y); octx.stroke();
            const coreGrad = octx.createLinearGradient(scT.x, scT.y, scH.x, scH.y);
            coreGrad.addColorStop(0, `rgba(${pc[0]},${pc[1]},${pc[2]},0)`);
            coreGrad.addColorStop(1, 'rgba(255,235,245,0.95)');
            octx.strokeStyle = coreGrad;
            octx.lineWidth = 2.2;
            octx.beginPath(); octx.moveTo(scT.x, scT.y); octx.lineTo(scH.x, scH.y); octx.stroke();
            const hg = octx.createRadialGradient(scH.x, scH.y, 0, scH.x, scH.y, 13);
            hg.addColorStop(0, `rgba(${pc[0]},${pc[1]},${pc[2]},0.85)`);
            hg.addColorStop(1, `rgba(${pc[0]},${pc[1]},${pc[2]},0)`);
            octx.fillStyle = hg;
            octx.beginPath(); octx.arc(scH.x, scH.y, 13, 0, Math.PI * 2); octx.fill();
            octx.fillStyle = 'rgba(255,242,248,0.95)';
            octx.beginPath(); octx.arc(scH.x, scH.y, 2.2, 0, Math.PI * 2); octx.fill();
          }
        };
        if (state.pulse3dRaf) cancelAnimationFrame(state.pulse3dRaf);
        let last3d = performance.now();
        const pulse3dLoop = (now) => {
          if (!state.graphInst || state.graphStyle !== 'neural') { state.pulse3dRaf = null; return; }
          try {
            const dt = Math.min(120, now - last3d);
            last3d = now;
            if (state.pulseSim) state.pulseSim.update(dt, now);
            const w = overlay.clientWidth || container3d.clientWidth || 800;
            const h = overlay.clientHeight || container3d.clientHeight || 600;
            if (overlay.width !== w) overlay.width = w;
            if (overlay.height !== h) overlay.height = h;
            drawPulses3D(w, h);
          } catch (e) {
            showStyleErr('3D: ' + (e && e.message ? e.message : e));
            console.error('[3D loop]', e);
            state.pulse3dRaf = null;
            return;
          }
          state.pulse3dRaf = requestAnimationFrame(pulse3dLoop);
        };
        state.pulse3dRaf = requestAnimationFrame(pulse3dLoop);
      }

      if (state.neuralTimer) { clearInterval(state.neuralTimer); state.neuralTimer = null; }
      state.neuralTimer = setInterval(() => {
        state.neuralPhase += 0.5;
        if (!state.graphInst || state.graphStyle !== 'neural') return;
        try {
          state.graphInst.linkColor(pulseLinkColor);
          if (state.graphInst.linkOpacity) state.graphInst.linkOpacity(pulseOpacity);
          state.graphInst.nodeColor(pulseNodeColor);
          if (state.nodeShape === 'squares' && typeof THREE !== 'undefined') {
            state.fullData.nodes.forEach(n => {
              const energy = state.pulseSim ? (state.pulseSim.energy.get(n.id) || 0) : 0;
              const breathe = 0.5 + 0.5 * Math.sin(state.neuralPhase * 1.4 + (n.degree || 0) * 0.35);
              const glow = Math.min(1, 0.15 + 0.15 * breathe + energy * 0.85);
              const cc = new THREE.Color(mixColor(state.nodeColorHex || nodeColor(n), glow));
              if (n._cube) n._cube.material.color.set(cc);
            });
          }
        } catch (e) {
          console.warn('[3D lights]', e);
        }
      }, 100);
    }


