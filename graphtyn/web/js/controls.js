import { state, PALETTES } from './state.js';
import { destroyGraph, loadGraph, refreshStyleInPlace, toggleRotate } from './graph.js';

export function setView(v) {
      state.activeView = v;
      const labels = { code: 'Code AST', semantic: 'Semántico', memory: 'Memoria', agents: 'Harness', changes: 'Cambios' };
      const activeLabel = document.getElementById('active-view-label');
      if (activeLabel) activeLabel.textContent = labels[v] || v;
      const bCode = document.getElementById('btn-code');
      const bSem = document.getElementById('btn-semantic');
      const bMem = document.getElementById('btn-memory-view');
      const bAg = document.getElementById('btn-agents');
      const bCh = document.getElementById('btn-changes');
      if (bCode) bCode.classList.toggle('active', v === 'code');
      if (bSem) bSem.classList.toggle('active', v === 'semantic');
      if (bMem) bMem.classList.toggle('active', v === 'memory');
      if (bAg) bAg.classList.toggle('active', v === 'agents');
      if (bCh) bCh.classList.toggle('active', v === 'changes');
      const explore = document.getElementById('dd-explore');
      if (explore) {
        explore.classList.remove('open');
        const trigger = explore.querySelector(':scope > button');
        if (trigger) trigger.setAttribute('aria-expanded', 'false');
      }
      destroyGraph();
      loadGraph();
    }

export function setDim(d) {
      if (state.activeDim === d) return;
      state.activeDim = d;
      document.getElementById('btn-2d').classList.toggle('active', d === '2d');
      document.getElementById('btn-3d').classList.toggle('active', d === '3d');
      const rotBtn = document.getElementById('btn-rotate');
      if (rotBtn) rotBtn.style.display = (d === '3d') ? 'flex' : 'none';
      if (d === '2d' && state.isRotating) toggleRotate();
      destroyGraph();
      loadGraph();
    }



export function changePalette() {
      state.activePalette = document.getElementById('palette-sel').value;
      state.nodeColorHex = null;
      refreshStyleInPlace();
    }

export function updateLinkStyles() {
      const p = PALETTES[state.activePalette] || PALETTES.obsidian;
      const particlesEl = document.getElementById('chk-particles');
      const arrowsEl = document.getElementById('chk-arrows');
      const styleEl = document.getElementById('link-style-sel');

      state.showParticles = particlesEl ? particlesEl.checked : true;
      state.showArrows    = arrowsEl ? arrowsEl.checked : true;
      state.linkStyle     = styleEl ? styleEl.value : 'solid';

      if (state.graphInst) {
        state.graphInst
          .linkDirectionalParticles(state.showParticles ? 2 : 0)
          .linkDirectionalArrowLength(state.showArrows ? 5 : 0)
          .linkCurvature(state.linkStyle === 'curved' ? 0.2 : 0.0)
          .linkLineDash(l => ((state.linkStyle === 'dashed' || l.confidence === 'INFERRED') ? [4, 4] : null));
      }
    }

export function updatePhysics() {
      const rep = parseInt(document.getElementById('f-repulsion').value || -300);
      const dist = parseInt(document.getElementById('f-distance').value || 80);
      if (state.graphInst) {
        if (state.activeDim === '2d') {
          state.graphInst.d3Force('charge', d3.forceManyBody().strength(rep));
          state.graphInst.d3Force('link', d3.forceLink().distance(dist).strength(0.4));
        } else {
          state.graphInst.d3Force('charge').strength(rep);
          state.graphInst.d3Force('link').distance(dist);
        }
        state.graphInst.numDimensions && state.graphInst.numDimensions(state.activeDim === '2d' ? 2 : 3);
      }
    }

export function exportGraphData() {
      if (!state.fullData || !state.fullData.nodes.length) return alert('No hay datos de grafo para exportar');
      const jsonStr = JSON.stringify(state.fullData, null, 2);
      const blob = new Blob([jsonStr], { type: 'application/json' });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = `graphtyn-${state.activeView}-${Date.now()}.json`;
      a.click();
    }

export function exportGraphPNG() {
      const container = document.getElementById('graph-container');
      const canvas = container.querySelector('canvas');
      if (!canvas) { alert('Sin grafo para exportar'); return; }
      const doCapture = () => {
        try {
          const a = document.createElement('a');
          a.href = canvas.toDataURL('image/png');
          a.download = `graphtyn-${state.activeView}-${Date.now()}.png`;
          a.click();
        } catch (e) {
          alert('No se pudo exportar la imagen: ' + e.message);
        }
      };
      if (state.activeDim === '3d' && state.graphInst && state.graphInst.cameraPosition) {
        // Fuerza un re-render para que el frame WebGL esté disponible en el canvas
        const cam = state.graphInst.cameraPosition();
        state.graphInst.cameraPosition(cam);
        setTimeout(doCapture, 150);
      } else {
        doCapture();
      }
    }
