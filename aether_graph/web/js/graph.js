import { state, PALETTES, COMM_COLORS, getCommKey, safePaint } from './state.js';
import { nodeColor, nodeVal, squareNodePainter, isDocOrMedia } from './painters.js';
import { buildPulseSim } from './sim.js';
import { apply2DStyle, apply3DStyle, paintNodePointerArea } from './styles.js';

export function destroyGraph() {
      stop3DRotation();
      if (state.neuralTimer) { clearInterval(state.neuralTimer); state.neuralTimer = null; }
      if (state.pulse3dRaf) { cancelAnimationFrame(state.pulse3dRaf); state.pulse3dRaf = null; }
      state.pulseSim = null;
      if (state.holoBgRo) { state.holoBgRo.disconnect(); state.holoBgRo = null; }
      uninstallReliableNodeDrag();
      if (state.graphInst) {
        try { state.graphInst._destructor && state.graphInst._destructor(); } catch(e){}
        state.graphInst = null;
      }
      document.getElementById('graph-container').innerHTML = '';
    }

export function showGraphSpinner(msg) {
      document.getElementById('graph-container').innerHTML =
        '<div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;gap:14px;">' +
        '<div style="width:36px;height:36px;border:3px solid #1e293b;border-top-color:#38bdf8;border-radius:50%;animation:spin 0.8s linear infinite;"></div>' +
        '<div style="color:#475569;font-size:12px;">' + msg + '</div>' +
        '</div>' +
        '<style>@keyframes spin{to{transform:rotate(360deg)}}</style>';
    }

export function buildCommunities(data) {
      // Build community groups by folder
      const groups = {};
      data.nodes.forEach(n => {
        const key = getCommKey(n);
        if (!groups[key]) groups[key] = 0;
        groups[key]++;
      });

      const sorted = Object.entries(groups).sort((a,b) => b[1] - a[1]);

      // Build stable color map: community key -> fixed color (not affected by palette)
      state.commColorMap = {};
      sorted.forEach(([name], idx) => {
        state.commColorMap[name] = COMM_COLORS[idx % COMM_COLORS.length];
      });

      const el = document.getElementById('community-list');
      el.innerHTML = sorted.map(([name, count]) => {
        const color = state.commColorMap[name];
        return `
          <div class="community-item" onclick="toggleComm('${name}')">
            <div class="comm-left">
              <label class="chk-wrap" onclick="event.stopPropagation()">
                <input type="checkbox" class="comm-chk" data-comm="${name}" checked onchange="applyFilter()">
                <span class="chk-box"><svg viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"/></svg></span>
              </label>
              <span class="comm-dot" style="background:${color};"></span>
              <span class="comm-name" title="${name}">${name}</span>
            </div>
            <span class="comm-badge">${count}</span>
          </div>`;
      }).join('');
    }

export function toggleComm(name) {
      const chk = document.querySelector(`.comm-chk[data-comm="${name}"]`);
      if (chk) { chk.checked = !chk.checked; applyFilter(); }
    }

export function toggleAllComm(checked) {
      document.querySelectorAll('.comm-chk').forEach(c => c.checked = checked);
      applyFilter();
    }

export function escapeHtml(text) {
      if (text === null || text === undefined) return '';
      const div = document.createElement('div');
      div.textContent = String(text);
      return div.innerHTML;
    }

export function applyFilter() {
      const q        = (document.getElementById('search-box')?.value || '').toLowerCase();
      const showFile = document.getElementById('f-file')?.checked ?? true;
      const showMedia = document.getElementById('f-media')?.checked ?? true;
      const showCls  = document.getElementById('f-class')?.checked ?? true;
      const showFn   = document.getElementById('f-func')?.checked ?? true;
      const showAgt  = document.getElementById('f-agent')?.checked ?? true;
      const minDeg   = parseInt(document.getElementById('f-deg')?.value || 0);
      const hideIso  = document.getElementById('f-isolated')?.checked ?? false;

      const activeComms = new Set(
        Array.from(document.querySelectorAll('.comm-chk:checked')).map(c => c.dataset.comm)
      );

      const filteredNodes = state.fullData.nodes.filter(n => {
        const k = n.kind || '';
        const isDocMedia = isDocOrMedia(n);

        if (isDocMedia && !showMedia) return false;
        if ((k === 'file' || k === 'module' || k === 'scene' || k === 'asset' || k === 'ui' || k === 'enum') && !isDocMedia && !showFile) return false;
        if ((k === 'class' || k === 'interface' || k === 'csharp' || k === 'struct') && !showCls) return false;
        if ((k === 'function' || k === 'method') && !showFn) return false;
        if ((k.includes('agent') || k.includes('orchestrator') || k.includes('hermes')) && !showAgt) return false;
        if ((n.degree || 0) < minDeg)  return false;
        if (hideIso && (n.degree || 0) === 0) return false;

        // Community filter — match by folder name or name prefix
        if (activeComms.size > 0) {
          const key = getCommKey(n);
          if (!activeComms.has(key)) return false;
        }

        if (q && !n.name.toLowerCase().includes(q) && !(n.details||'').toLowerCase().includes(q)) return false;
        return true;
      });

      const ids = new Set(filteredNodes.map(n => n.id));
      const filteredLinks = state.fullData.links.filter(l => {
        const s = typeof l.source === 'object' ? l.source.id : l.source;
        const t = typeof l.target === 'object' ? l.target.id : l.target;
        return ids.has(s) && ids.has(t);
      });

      if (state.graphInst) state.graphInst.graphData({ nodes: filteredNodes, links: filteredLinks });
      if (state.pulseSim && state.graphStyle === 'neural') {
        state.pulseSim = buildPulseSim({ nodes: filteredNodes, links: filteredLinks });
      }

      const statsEl = document.getElementById('stats');
      if (statsEl && state.fullData && state.fullData.nodes) {
        if (filteredNodes.length === state.fullData.nodes.length && filteredLinks.length === state.fullData.links.length) {
          statsEl.textContent = `${state.fullData.nodes.length} nodos · ${state.fullData.links.length} conectores`;
        } else {
          statsEl.textContent = `${filteredNodes.length} / ${state.fullData.nodes.length} nodos · ${filteredLinks.length} / ${state.fullData.links.length} conectores`;
        }
      }
    }

export function onNodeClick(node) {
      if (!node) return closeBlastPanel();
      state.selectedNode = node;

      // Find direct neighbors
      const neighbors = new Set();
      const connectedLinks = [];
      const allLinks = (state.fullData && state.fullData.links) || [];
      const allNodes = (state.fullData && state.fullData.nodes) || [];
      allLinks.forEach(l => {
        const s = typeof l.source === 'object' ? l.source.id : l.source;
        const t = typeof l.target === 'object' ? l.target.id : l.target;
        if (s === node.id) { neighbors.add(t); connectedLinks.push(l); }
        if (t === node.id) { neighbors.add(s); connectedLinks.push(l); }
      });
      state.selectedNeighbors = neighbors;

      const neighborNodes = allNodes.filter(n => neighbors.has(n.id));

      // Link info (label + confidence) per neighbor
      const linkInfo = {};
      connectedLinks.forEach(l => {
        const s = typeof l.source === 'object' ? l.source.id : l.source;
        const t = typeof l.target === 'object' ? l.target.id : l.target;
        const other = s === node.id ? t : s;
        const info = (l.label || 'conecta') + ' · ' + ((l.confidence || 'EXTRACTED') === 'INFERRED' ? 'INFERRED' : 'EXTRACTED');
        if (!linkInfo[other]) linkInfo[other] = [];
        if (!linkInfo[other].includes(info)) linkInfo[other].push(info);
      });

      const panel = document.getElementById('blast-panel');
      const body = document.getElementById('blast-content');
      if (panel) panel.style.display = 'block';
      if (!body) return;

      const safeName = escapeHtml(node.name || node.id || 'Sin nombre');
      const safeKind = escapeHtml(node.kind || 'nodo');
      const safeId = escapeHtml(node.id || '');
      const sourceBlock = node.file
        ? '<div><strong>Origen:</strong> <span style="color:#94a3b8;overflow-wrap:anywhere;">' +
          escapeHtml(node.file) + (node.line ? ':' + node.line : '') + '</span></div>'
        : '';
      const evidenceBlock = node.evidence
        ? '<div style="margin:4px 0;padding:5px 7px;background:#0b1220;border-left:2px solid #10b981;border-radius:4px;overflow-wrap:anywhere;">' +
          '<strong style="color:#10b981;font-size:9px;display:block;margin-bottom:2px;">EVIDENCIA ' +
          escapeHtml((node.parser || 'estructural').toUpperCase()) + '</strong>' +
          '<code style="color:#cbd5e1;font-size:9px;white-space:pre-wrap;">' + escapeHtml(node.evidence) + '</code></div>'
        : '';

      const descText = node.details || (node.id ? node.id.replace(/^(file|symbol):/, '') : 'Sin detalles disponibles');
      const descBlock = (function(){
        state.descExpanded = false;
        const raw = escapeHtml(descText);
        if (raw.length > 130) {
          const shortText = raw.substring(0, 130) + '...';
          return '<div style="margin:5px 0;padding:6px 8px;background:#1e293b;border-radius:6px;border:1px solid #334155;">' +
            '<strong style="color:#38bdf8;font-size:10px;display:block;margin-bottom:2px;">Descripción / Detalle:</strong>' +
            '<span id="desc-short" style="color:#f8fafc;font-size:11px;line-height:1.4;overflow-wrap:anywhere;">' + shortText + '</span>' +
            '<span id="desc-full" style="color:#f8fafc;font-size:11px;line-height:1.4;display:none;overflow-wrap:anywhere;">' + raw + '</span>' +
            '<div><button id="btn-toggle-desc" onclick="toggleNodeDesc()" style="background:none;border:none;color:#38bdf8;cursor:pointer;font-size:10px;padding:2px 0 0 0;font-weight:600;">Ver más ▼</button></div>' +
            '</div>';
        } else {
          return '<div style="margin:5px 0;padding:6px 8px;background:#1e293b;border-radius:6px;border:1px solid #334155;"><strong style="color:#38bdf8;font-size:10px;display:block;margin-bottom:2px;">Descripción / Detalle:</strong><span style="color:#f8fafc;font-size:11px;line-height:1.4;">' + raw + '</span></div>';
        }
      })();

      body.innerHTML =
        '<div><strong>Símbolo:</strong> <span style="color:#38bdf8;">' + safeName + '</span></div>' +
        '<div><strong>Tipo:</strong> <span style="color:#f59e0b;">' + safeKind + '</span></div>' +
        sourceBlock +
        evidenceBlock +
        descBlock +
        '<div style="display:flex;gap:12px;margin-top:2px;">' +
          '<span>Grado Total: <strong style="color:#10b981;">' + (node.degree || 0) + '</strong></span>' +
          '<span>Impacto Directo: <strong style="color:#a78bfa;">' + neighborNodes.length + '</strong></span>' +
        '</div>' +
        '<button class="btn-action btn-primary" style="margin-top:4px;justify-content:center;" data-node-id="' + safeId + '" onclick="focusNode(this.dataset.nodeId)">Centrar y Enfocar</button>' +
        '<hr style="border:none;border-top:1px solid #1e293b;margin:4px 0;">' +
        '<div style="font-weight:700;color:#64748b;font-size:10px;">VECINOS DIRECTOS (BLAST RADIUS):</div>' +
        '<div style="max-height:110px;overflow-y:auto;display:flex;flex-direction:column;gap:3px;">' +
        (neighborNodes.length ? neighborNodes.slice(0, 15).map(n =>
          '<div style="display:grid;grid-template-columns:minmax(0,1fr);gap:2px;background:#1a2234;padding:5px 6px;border-radius:4px;cursor:pointer;min-width:0;" data-node-id="' + escapeHtml(n.id) + '" onclick="focusNode(this.dataset.nodeId)">' +
            '<span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0;">' + escapeHtml(n.name) + '</span>' +
            '<span style="color:#64748b;font-size:9px;line-height:1.3;min-width:0;overflow-wrap:anywhere;word-break:break-word;">' + escapeHtml(n.kind || '') + (linkInfo[n.id] ? ' · ' + escapeHtml(linkInfo[n.id].join(', ')) : '') + '</span>' +
          '</div>'
        ).join('') : '<div style="color:#64748b;">Sin conexiones directas</div>') +
        '</div>';

      // Highlight neighbors by dimming others in standard 2D and 3D
      if (state.graphInst) {
        state.graphInst.nodeColor(n => {
          if (n.id === node.id) return '#ff007f';
          if (neighbors.has(n.id)) return nodeColor(n);
          return 'rgba(255,255,255,0.22)';
        });
      }
    }

export function nearestNodeAtPointer(event, fallbackNode = null) {
      if (!event || !state.graphInst || state.activeDim !== '2d' ||
          typeof state.graphInst.graph2ScreenCoords !== 'function') return fallbackNode;
      const container = document.getElementById('graph-container');
      if (!container) return fallbackNode;
      const rect = container.getBoundingClientRect();
      const px = event.clientX - rect.left;
      const py = event.clientY - rect.top;
      if (!Number.isFinite(px) || !Number.isFinite(py)) return fallbackNode;

      const nodes = state.graphInst.graphData().nodes || [];
      let nearest = null;
      let nearestDistance = Infinity;
      for (const candidate of nodes) {
        if (!Number.isFinite(candidate.x) || !Number.isFinite(candidate.y)) continue;
        const point = state.graphInst.graph2ScreenCoords(candidate.x, candidate.y);
        if (!point) continue;
        const distance = Math.hypot(point.x - px, point.y - py);
        if (distance < nearestDistance) {
          nearest = candidate;
          nearestDistance = distance;
        }
      }

      // This also recovers clicks that ForceGraph classified as background.
      // A small screen-space limit avoids opening distant nodes on empty space.
      return nearest && nearestDistance <= 16 ? nearest : fallbackNode;
    }

export function handleGraphNodeClick(node, event) {
      onNodeClick(nearestNodeAtPointer(event, node));
    }

export function handleGraphBackgroundClick(event) {
      const nearest = nearestNodeAtPointer(event);
      if (nearest) onNodeClick(nearest);
      else closeBlastPanel();
    }

export function uninstallReliableNodeDrag() {
      const container = document.getElementById('graph-container');
      const handlers = container && container._aetherDragHandlers;
      if (!handlers) return;
      container.removeEventListener('pointerdown', handlers.down, true);
      container.removeEventListener('pointermove', handlers.move, true);
      container.removeEventListener('pointerup', handlers.up, true);
      container.removeEventListener('pointercancel', handlers.cancel, true);
      container.removeEventListener('click', handlers.click, true);
      delete container._aetherDragHandlers;
    }

export function installReliableNodeDrag() {
      const container = document.getElementById('graph-container');
      if (!container || state.activeDim !== '2d') return;
      uninstallReliableNodeDrag();

      let drag = null;
      let suppressClickUntil = 0;
      const finish = (event, cancelled) => {
        if (!drag || event.pointerId !== drag.pointerId) return;
        event.preventDefault();
        event.stopImmediatePropagation();
        const node = drag.node;
        const moved = drag.moved;
        node.fx = undefined;
        node.fy = undefined;
        try { container.releasePointerCapture(event.pointerId); } catch (_) {}
        drag = null;
        suppressClickUntil = performance.now() + 350;
        if (!cancelled && !moved) onNodeClick(node);
      };
      const handlers = {
        down(event) {
          if (event.button !== 0 || !state.graphInst || state.activeDim !== '2d') return;
          const node = nearestNodeAtPointer(event);
          if (!node) return; // Preserve normal canvas pan/zoom on empty space.
          event.preventDefault();
          event.stopImmediatePropagation();
          drag = { node, pointerId: event.pointerId, startX: event.clientX, startY: event.clientY, moved: false };
          node.fx = node.x;
          node.fy = node.y;
          try { container.setPointerCapture(event.pointerId); } catch (_) {}
        },
        move(event) {
          if (!drag || event.pointerId !== drag.pointerId || !state.graphInst) return;
          event.preventDefault();
          event.stopImmediatePropagation();
          if (Math.hypot(event.clientX - drag.startX, event.clientY - drag.startY) > 3) drag.moved = true;
          const rect = container.getBoundingClientRect();
          const point = state.graphInst.screen2GraphCoords(event.clientX - rect.left, event.clientY - rect.top);
          if (!point) return;
          drag.node.fx = point.x;
          drag.node.fy = point.y;
          drag.node.x = point.x;
          drag.node.y = point.y;
          if (typeof state.graphInst.d3ReheatSimulation === 'function') state.graphInst.d3ReheatSimulation();
        },
        up(event) { finish(event, false); },
        cancel(event) { finish(event, true); },
        click(event) {
          if (performance.now() < suppressClickUntil) {
            event.preventDefault();
            event.stopImmediatePropagation();
          }
        }
      };
      container._aetherDragHandlers = handlers;
      container.addEventListener('pointerdown', handlers.down, true);
      container.addEventListener('pointermove', handlers.move, true);
      container.addEventListener('pointerup', handlers.up, true);
      container.addEventListener('pointercancel', handlers.cancel, true);
      container.addEventListener('click', handlers.click, true);
    }

export function closeBlastPanel() {
      state.selectedNode = null;
      state.selectedNeighbors = null;
      const panel = document.getElementById('blast-panel');
      if (panel) panel.style.display = 'none';
      if (state.graphInst) {
        state.graphInst.nodeColor(n => nodeColor(n));
      }
    }

export function focusNode(nodeId) {
      if (!nodeId) return;
      let activeNodes = (state.graphInst && typeof state.graphInst.graphData === 'function')
        ? (state.graphInst.graphData().nodes || [])
        : [];
      let node = activeNodes.find(n => n.id === nodeId);
      if (!node) {
        node = (state.fullData && state.fullData.nodes) ? state.fullData.nodes.find(n => n.id === nodeId) : null;
      }
      if (!node) return;

      if (state.graphInst) {
        if (state.activeDim === '2d') {
          if (Number.isFinite(node.x) && Number.isFinite(node.y)) {
            state.graphInst.centerAt(node.x, node.y, 400);
            state.graphInst.zoom(2.5, 400);
          }
        } else {
          if (Number.isFinite(node.x) && Number.isFinite(node.y) && Number.isFinite(node.z)) {
            const dist = 120;
            const h = Math.hypot(node.x, node.y, node.z) || 1;
            const ratio = 1 + dist / h;
            state.graphInst.cameraPosition(
              { x: node.x * ratio, y: node.y * ratio, z: node.z * ratio },
              node,
              1000
            );
          }
        }
      }
      onNodeClick(node);
    }

export function toggleNodeDesc() {
      state.descExpanded = !state.descExpanded;
      const fullEl = document.getElementById('desc-full');
      const shortEl = document.getElementById('desc-short');
      const btn = document.getElementById('btn-toggle-desc');
      if (fullEl && shortEl && btn) {
        fullEl.style.display = state.descExpanded ? 'inline' : 'none';
        shortEl.style.display = state.descExpanded ? 'none' : 'inline';
        btn.textContent = state.descExpanded ? 'Ver menos' : 'Ver más';
      }
    }

export function loadChangesView() {
      if (!state.activePath) {
        document.getElementById('graph-container').innerHTML =
          '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#475569;font-size:13px;">Selecciona un proyecto</div>';
        return;
      }
      showGraphSpinner('Calculando cambios e impacto...');
      const baseParam = state.prBase ? '&base=' + encodeURIComponent(state.prBase) : '';
      fetch('/api/diff?path=' + encodeURIComponent(state.activePath) + baseParam).then(r => r.json()).then(d => {
        const container = document.getElementById('graph-container');
        const impacted = d.impacted_nodes || [];
        const files = d.changed_files || [];
        const risk = d.risk || {level:'low', score:0, direct:0, transitive:0};
        const conflicts = d.conflicts || [];
        document.getElementById('stats').textContent = files.length + ' cambiados · ' + impacted.length + ' impactados';
        container.innerHTML =
          '<div style="height:100%;overflow-y:auto;padding:20px 26px;max-width:880px;">' +
          '<div style="display:flex;gap:8px;margin-bottom:12px;"><input id="pr-base-input" value="' + String(state.prBase || '').replace(/"/g, '&quot;') + '" placeholder="Rama base (ej. main)" style="flex:1;background:#111827;border:1px solid #374151;color:#e2e8f0;padding:7px;border-radius:6px;"><button class="btn-action" onclick="setPRBase(document.getElementById(\'pr-base-input\').value)">Analizar PR</button></div>' +
          '<div style="display:flex;gap:8px;align-items:center;margin-bottom:16px;"><span class="proj-badge ' + (risk.level === 'high' ? 'pend' : 'ok') + '">RIESGO ' + String(risk.level).toUpperCase() + ' · ' + risk.score + '/100</span>' +
          '<span style="font-size:11px;color:#94a3b8;">' + risk.direct + ' directos · ' + risk.transitive + ' transitivos</span></div>' +
          '<div style="font-weight:700;color:#38bdf8;font-size:14px;margin-bottom:10px;">Cambios sin commitear (git status)</div>' +
          (files.length ? files.slice(0, 40).map(f => '<div style="color:#cbd5e1;font-size:12px;padding:3px 0;border-bottom:1px solid #1e293b;font-family:monospace;">' + f + '</div>').join('')
            : '<div style="color:#64748b;font-size:12px;">Sin archivos modificados.</div>') +
          '<div style="font-weight:700;color:#a78bfa;font-size:14px;margin:18px 0 10px;">Radio de impacto (nodos conectados a los cambios)</div>' +
          (impacted.length ? impacted.slice(0, 60).map(i =>
            '<div class="project-item" style="margin-bottom:4px;" data-node-id="' + String(i.node.id || '').replace(/"/g, '&quot;') + '" onclick="openFromChanges(this.dataset.nodeId)">' +
              '<span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">' + i.node.name + '</span>' +
              '<span class="proj-badge ' + (i.confidence === 'INFERRED' ? 'pend' : 'ok') + '">' + i.confidence + '</span>' +
            '</div>').join('')
            : '<div style="color:#64748b;font-size:12px;">Sin impacto conocido.</div>') +
          '<div style="font-weight:700;color:#f59e0b;font-size:14px;margin:18px 0 10px;">Conflictos Git potenciales</div>' +
          (conflicts.length ? conflicts.map(f => '<div style="font:12px monospace;color:#fca5a5;padding:3px 0;">' + f + '</div>').join('') : '<div style="color:#64748b;font-size:12px;">Ninguno detectado. ' + (d.conflict_detection || '') + '</div>') +
          '</div>';
      }).catch(err => {
        document.getElementById('graph-container').innerHTML =
          '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#ef4444;font-size:13px;">Error al calcular cambios: ' + (err.message || err) + '</div>';
      });
    }

export function setPRBase(base) {
      state.prBase = String(base || '').trim();
      loadChangesView();
    }

export function loadGraph() {
      if (state.activeView === 'changes') { loadChangesView(); return; }
      if (!state.activePath && state.activeView === 'code') {
        document.getElementById('stats').textContent = 'Selecciona un proyecto';
        document.getElementById('graph-container').innerHTML =
          '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#475569;font-size:13px;">Selecciona un proyecto de la lista izquierda</div>';
        return;
      }
      const url = state.activeView === 'agents'
        ? '/api/graph?view=agents'
        : state.activeView === 'semantic'
        ? '/api/graph?view=semantic&path=' + encodeURIComponent(state.activePath)
        : '/api/graph?path=' + encodeURIComponent(state.activePath);

      showGraphSpinner(state.activeView === 'agents' ? 'Cargando topologia de agentes...' : 'Escaneando proyecto...');
      document.getElementById('stats').textContent = 'Cargando...';

      fetch(url).then(r => r.json()).then(data => {
        if (!data.nodes || data.nodes.length === 0) {
          document.getElementById('graph-container').innerHTML =
            '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#475569;font-size:13px;">Sin nodos. Haz clic en Reindexar para escanear el proyecto.</div>';
          document.getElementById('stats').textContent = '0 nodos';
          buildCommunities(data); updateEstTime();
          return;
        }
        state.fullData = data;
        state.pulseSim = buildPulseSim(data);
        const p = PALETTES[state.activePalette];
        document.getElementById('stats').textContent =
          `${data.nodes.length} nodos · ${data.links.length} conectores`;
        const meta = data.metadata || {};
        const badge = document.getElementById('model-badge');
        if (badge) {
          badge.textContent =
            (meta.ai_model ? meta.ai_model : '') +
            (meta.reindex_mode ? ' · ' + meta.reindex_mode : '');
        }

        if (state.graphStyle !== 'standard' && badge) {
          badge.textContent = (state.graphStyle === 'neural' ? 'Neuronal' : 'Holograma') + ' · ' + (meta.ai_model || state.activeView);
        }

        buildCommunities(data); updateEstTime();

        const container = document.getElementById('graph-container');

        const tooltip = n => {
          const hasDesc = n.details && n.details.length > 0;
          const safeName = escapeHtml(n.name || '');
          const safeKind = escapeHtml(n.kind || '');
          const safeDetails = hasDesc ? escapeHtml(n.details) : '';
          const detailsHtml = hasDesc ? `<br/><span style="color:#38bdf8;font-size:11px;line-height:1.3;display:block;margin-top:3px;">${safeDetails}</span>` : '';
          return `<div style="background:#111827;border:1px solid #374151;border-radius:6px;padding:7px 11px;font-size:12px;color:#f8fafc;max-width:320px;max-height:180px;overflow-y:auto;box-shadow:0 8px 24px rgba(0,0,0,0.5);pointer-events:none;user-select:none;">` +
            `<strong>${safeName}</strong> <span style="color:#64748b;font-size:10px;">(${safeKind})</span>` +
            detailsHtml +
            `<div style="margin-top:5px;font-size:10px;"><span style="color:${nodeColor(n)};font-weight:600;">●</span> <span style="color:#94a3b8;">Conexiones: ${n.degree || 0}</span></div>` +
            `</div>`;
        };

        try {
          if (state.activeDim === '2d') {
            state.graphInst = ForceGraph()(container)
            .backgroundColor('#0b0e17')
            .nodeId('id')
            .nodeVal(nodeVal)
            .nodeRelSize(5)
            .nodeCanvasObjectMode(() => 'after')
            .linkCanvasObjectMode(() => 'replace')
            .nodePointerAreaPaint(paintNodePointerArea)
            .autoPauseRedraw(false)
            .enableNodeDrag(true)
            .onNodeDragEnd(node => {
              node.fx = undefined;
              node.fy = undefined;
            })
            .linkHoverPrecision(0)
            .linkPointerAreaPaint(() => {})
            .nodeLabel(tooltip)
            .onNodeClick(handleGraphNodeClick)
            .onBackgroundClick(handleGraphBackgroundClick)
            .linkColor(l => (l.confidence === 'INFERRED' ? 'rgba(148,163,184,0.22)' : p.link))
            .linkWidth(l => (l.confidence === 'INFERRED' ? p.linkW * 0.7 : p.linkW))
            .linkDirectionalParticles(() => (state.showParticles ? 2 : 0))
            .linkDirectionalParticleWidth(2.5)
            .linkDirectionalParticleSpeed(0.006)
            .linkDirectionalParticleColor(() => p.particle)
            .linkDirectionalArrowLength(() => (state.showArrows ? 5 : 0))
            .linkDirectionalArrowRelPos(0.95)
            .linkCurvature(() => (state.linkStyle === 'curved' ? 0.2 : 0.0))
            .linkLineDash(l => ((state.linkStyle === 'dashed' || l.confidence === 'INFERRED') ? [4, 4] : null))
            .d3AlphaDecay(0.012)
            .d3VelocityDecay(0.22)
            .d3Force('charge', d3.forceManyBody().strength(-300))
            .d3Force('link',   d3.forceLink().distance(80).strength(0.4))
            .d3Force('collide', d3.forceCollide().radius(22))
            .graphData(data);

            apply2DStyle();
            installReliableNodeDrag();
        } else {
          // Assign initial 3D positions so nodes spread in X, Y, Z sphere
          data.nodes.forEach(n => {
            if (n.x === undefined) n.x = (Math.random() - 0.5) * 600;
            if (n.y === undefined) n.y = (Math.random() - 0.5) * 600;
            if (n.z === undefined) n.z = (Math.random() - 0.5) * 600;
          });
          state.graphInst = ForceGraph3D()(container)
            .backgroundColor('#0b0e17')
            .nodeId('id')
            .nodeVal(nodeVal)
            .nodeRelSize(8)
            .nodeColor(n => {
              if (state.selectedNode) {
                if (n.id === state.selectedNode.id) return '#ff007f';
                if (state.selectedNeighbors && state.selectedNeighbors.has(n.id)) return nodeColor(n);
                return 'rgba(255,255,255,0.22)';
              }
              return nodeColor(n);
            })
            .linkHoverPrecision(0)
            .nodeLabel(tooltip).onNodeClick(handleGraphNodeClick).onBackgroundClick(handleGraphBackgroundClick)
            .linkColor(l => (l.confidence === 'INFERRED' ? 'rgba(148,163,184,0.22)' : p.link))
            .linkWidth(l => (l.confidence === 'INFERRED' ? p.linkW * 0.7 : p.linkW))
            .linkDirectionalParticles(() => (state.showParticles ? 2 : (state.linkStyle === 'dashed' ? 3 : 0)))
            .linkDirectionalParticleWidth(() => (state.linkStyle === 'dashed' ? 1.8 : 2.5))
            .linkDirectionalParticleSpeed(0.006)
            .linkDirectionalArrowLength(() => (state.showArrows ? 5 : 0))
            .linkDirectionalArrowRelPos(0.95)
            .linkCurvature(() => (state.linkStyle === 'curved' ? 0.25 : (state.linkStyle === 'dashed' ? 0.15 : 0.0)))
            .graphData(data);

          // Use 3D internal force engine (prevents 2D planar flattening)
          state.graphInst.d3Force('charge').strength(-250);
          state.graphInst.d3Force('link').distance(75);

          apply3DStyle();
        }

        applyFilter();
        } catch(err) {
          console.error("Graph render error:", err);
          document.getElementById('graph-container').innerHTML =
            '<div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;color:#ef4444;font-size:13px;padding:20px;text-align:center;">' +
            '<strong>Error al renderizar el grafo</strong><br/><span style="color:#94a3b8;font-size:11px;margin-top:6px;">' + err.message + '</span></div>';
        }
      }).catch(err => {
        console.error("Fetch error:", err);
        document.getElementById('graph-container').innerHTML =
          '<div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;color:#ef4444;font-size:13px;">Error al conectar con la API</div>';
      });
    }

export function refreshStyleInPlace() {
      if (!state.graphInst) return;
      if (state.activeDim === '2d') {
        apply2DStyle();
        return;
      }
      if (state.graphStyle === 'standard') {
        if (state.nodeShape === 'squares') {
          apply3DStyle();
        } else {
          state.graphInst.nodeColor(n => nodeColor(n));
        }
        return;
      }
      apply3DStyle();
    }

export function changeGraphStyle() {
      state.graphStyle = document.getElementById('style-sel') ? document.getElementById('style-sel').value : 'standard';
      destroyGraph();
      loadGraph();
    }

export function changeNodeShape() {
      state.nodeShape = document.getElementById('shape-sel') ? document.getElementById('shape-sel').value : 'circles';
      destroyGraph();
      loadGraph();
    }

export function changeNodeColor() {
      const nc = document.getElementById('node-color');
      state.nodeColorHex = nc ? nc.value : null;
      refreshStyleInPlace();
    }

export function changeStyleColors() {
      const pc = document.getElementById('pulse-color');
      const lc = document.getElementById('link-color');
      if (pc) state.pulseColorHex = pc.value;
      if (lc) state.linkColorHex = lc.value;
      refreshStyleInPlace();
    }

export function toggleVertexBlink(on) {
      state.vertexBlinkOn = on;
      refreshStyleInPlace();
    }

export function toggleOrganic3d(on) {
      state.organic3dOn = on;
      refreshStyleInPlace();
    }


export function toggleRotate() {
      state.isRotating = !state.isRotating;
      const btn = document.getElementById('btn-rotate');
      if (btn) btn.classList.toggle('active', state.isRotating);
      if (state.isRotating) start3DRotation();
      else stop3DRotation();
    }


export function start3DRotation() {
      if (state.rotateRaf) cancelAnimationFrame(state.rotateRaf);
      const tick = () => {
        if (!state.isRotating || state.activeDim !== '3d' || !state.graphInst || !state.graphInst.cameraPosition) return;
        const p = state.graphInst.cameraPosition();
        const r = Math.max(Math.hypot(p.x || 0, p.z || 0) || 500, 150);
        state.rotateAngle += 0.0035;
        state.graphInst.cameraPosition({ x: r * Math.sin(state.rotateAngle), y: p.y || 100, z: r * Math.cos(state.rotateAngle) }, undefined, 0);
        state.rotateRaf = requestAnimationFrame(tick);
      };
      state.rotateRaf = requestAnimationFrame(tick);
    }


export function stop3DRotation() {
      if (state.rotateRaf) { cancelAnimationFrame(state.rotateRaf); state.rotateRaf = null; }
    }


export function updateEstTime() {
      const valEl = document.getElementById('est-time-val');
      if (!valEl) return;
      const engine = document.getElementById('engine-sel') ? document.getElementById('engine-sel').value : 'ast_local_llm';
      if (engine === 'ast_pure') {
        valEl.textContent = '< 1 segundo';
        return;
      }
      const nodeCount = (state.fullData && state.fullData.nodes) ? state.fullData.nodes.length : 20;
      if (engine === 'ast_cloud') {
        const sec = Math.ceil(nodeCount * 0.15);
        valEl.textContent = sec >= 60 ? `~${Math.ceil(sec/60)} min` : `~${sec} seg`;
        return;
      }
      if (engine === 'ast_local_llm') {
        const codeNodes = (state.fullData && state.fullData.nodes) ? state.fullData.nodes.filter(n => n.kind !== 'module' && n.kind !== 'dir').length : nodeCount;
        const totalSec = Math.ceil(codeNodes * 0.7);
        if (totalSec < 60) {
          valEl.textContent = `~${totalSec} seg`;
        } else {
          const mins = Math.ceil(totalSec / 60);
          valEl.textContent = `~${mins} min`;
        }
      }
    }
