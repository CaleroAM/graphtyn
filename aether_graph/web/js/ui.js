import { state } from './state.js';
import { setView } from './controls.js';
import { loadGraph, focusNode } from './graph.js';

export function toggleDD(id) {
      const el = document.getElementById(id);
      const was = el.classList.contains('open');
      document.querySelectorAll('.dd-wrap').forEach(d => d.classList.remove('open'));
      if (!was) el.classList.add('open');
    }

export function openRegister() {
      document.getElementById('reg-path').value = state.activePath || '';
      document.getElementById('modal-reg').classList.add('show');
    }

export function closeRegister() { document.getElementById('modal-reg').classList.remove('show'); }

export function selMode(m) {
      state.regMode = m;
      ['single_folder','master_folder','agent_discovered'].forEach(x => {
        const id = x === 'single_folder' ? 'mc-single' : x === 'master_folder' ? 'mc-master' : 'mc-agent';
        document.getElementById(id).classList.toggle('sel', x === m);
      });
    }

export function submitRegister() {
      const path = document.getElementById('reg-path').value.trim();
      if (!path) return;
      fetch('/api/projects/register', {
        method: 'POST', headers: {'Content-Type':'application/json'},
        body: JSON.stringify({ path, mode: state.regMode })
      }).then(r => r.json()).then(res => {
        if (res.ok) { closeRegister(); loadProjects(); selectProject(path); }
        else alert('Error: ' + res.error);
      });
    }

export function openTutorial()  { document.getElementById('modal-tutorial').classList.add('show'); }

export function closeTutorial() { document.getElementById('modal-tutorial').classList.remove('show'); }

export function loadProjects(thenLoadGraph) {
      console.log("Fetching /api/projects...");
      fetch('/api/projects').then(r => r.json()).then(projects => {
        console.log("Projects received:", projects);
        projects.forEach(p => { if (p.path) state.respectMap[p.path] = p.respect_git !== false; });
        const el = document.getElementById('project-list');
        if (!Array.isArray(projects) || !projects.length) {
          el.innerHTML = `
            <div style="padding:14px 10px;text-align:center;background:#111827;border:1px dashed #374151;border-radius:8px;margin-top:6px;">
              <div style="font-size:22px;margin-bottom:6px;">[...]</div>
              <div style="font-size:12px;font-weight:700;color:#f8fafc;margin-bottom:4px;">Sin Proyectos Aún</div>
              <div style="font-size:10px;color:#94a3b8;margin-bottom:12px;line-height:1.4;">Por favor, añade alguna carpeta de código para empezar.</div>
              <button class="btn-action btn-primary" style="width:100%;justify-content:center;font-size:11px;padding:7px 10px;" onclick="openRegister()">
                ➕ Registrar Proyecto
              </button>
            </div>
          `;
          return;
        }
        if (!state.activePath && projects.length) state.activePath = projects[0].path;
        el.innerHTML = projects.map(p => {
          const pPath = (p.path || '').replace(/"/g, '&quot;');
          const pName = p.name || p.id || 'Sin nombre';
          const isActive = state.activePath && (p.path === state.activePath || pPath === state.activePath);
          return '<div class="project-item ' + (isActive ? 'active' : '') + '" onclick="selectProject(this.dataset.path)" data-path="' + pPath + '">' +
            '<span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:148px;">' + pName + '</span>' +
            '<span class="proj-badge ' + (p.indexed ? 'ok' : 'pend') + '">' + (p.indexed ? 'OK' : 'PEND') + '</span>' +
            '</div>';
        }).join('');
        if (thenLoadGraph) loadGraph();
      }).catch(err => {
        console.error("Projects fetch error:", err);
        document.getElementById('project-list').innerHTML =
          '<div style="color:#ef4444;font-size:11px;padding:4px;">Error: ' + (err.message || err) + '</div>';
      });
    }

export function selectProject(path) {
      state.activePath = path;
      const gi = document.getElementById('chk-gitignore');
      if (gi) gi.checked = state.respectMap[path] !== false;
      if (state.activeView === 'agents' || state.activeView === 'changes') setView('code'); // switch to code view when selecting a project
      else { loadProjects(); loadGraph(); }
    }

export function initWatchPolling() {
      if (state.watchTimer) clearInterval(state.watchTimer);
      const poll = () => fetch('/api/watch/status').then(r => r.json()).then(data => {
        if (!data.enabled || !Array.isArray(data.projects)) return;
        data.projects.forEach(project => {
          const previous = state.watchVersions[project.path];
          state.watchVersions[project.path] = project.version || 0;
          if (previous !== undefined && project.version > previous && project.path === state.activePath) {
            loadProjects();
            loadGraph();
          }
        });
      }).catch(() => {});
      poll();
      state.watchTimer = setInterval(poll, 1500);
    }

export function doReindex(full) {
      const btn = document.getElementById('reindex-btn');
      const engineSel = document.getElementById('engine-sel');
      const engineVal = engineSel ? engineSel.value : 'ast_local_llm';
      const engine = engineVal;
      const codeModelSel = document.getElementById('code-model-sel');
      const visionModelSel = document.getElementById('vision-model-sel');
      const codeModel = codeModelSel ? codeModelSel.value : '';
      const visionModel = visionModelSel ? visionModelSel.value : '';
      const estVal = document.getElementById('est-time-val') ? document.getElementById('est-time-val').textContent : '';
      btn.innerHTML = 'Indexando (' + estVal + ')…';
      const body = { path: state.activePath, engine, full: !!full };
      if (codeModel) body.model = codeModel;
      if (visionModel) body.vision_model = visionModel;
      fetch('/api/reindex', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify(body)
      }).then(r => r.json()).then(() => {
        btn.innerHTML = '<svg class="svg-ico" viewBox="0 0 24 24"><path d="M12 4V1L8 5l4 4V6c3.31 0 6 2.69 6 6 0 1.01-.25 1.97-.7 2.8l1.46 1.46A7.93 7.93 0 0020 12c0-4.42-3.58-8-8-8zm0 14c-3.31 0-6-2.69-6-6 0-1.01.25-1.97.7-2.8L5.24 7.74A7.93 7.93 0 004 12c0 4.42 3.58 8 8 8v3l4-4-4-4v3z"/></svg>Reindexar';
        loadProjects(); loadGraph();
      });
    }

export function toggleGitignore(checked) {
      if (!state.activePath) return;
      state.respectMap[state.activePath] = checked;
      fetch('/api/projects/config', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({ path: state.activePath, respect_git: checked })
      }).then(r => r.json()).then(res => {
        if (res.ok) doReindex(true);
      });
    }

export function loadOllamaModels() {
      fetch('/api/ollama/models').then(r => r.json()).then(d => {
        if (!d.code_models && !d.vision_models) return;
        // Populate code model selector
        const codeSel = document.getElementById('code-model-sel');
        if (codeSel && d.code_models) {
          let html = '<option value="">Auto-detectar</option>';
          d.code_models.forEach(m => { html += '<option value="' + m + '">'+m+'</option>'; });
          codeSel.innerHTML = html;
          // Auto-select qwen2.5-coder:3b if available
          const preferred = d.code_models.find(m => m.includes('qwen2.5-coder:3b'));
          if (preferred) codeSel.value = preferred;
        }
        // Populate vision model selector
        const visSel = document.getElementById('vision-model-sel');
        if (visSel && d.vision_models) {
          let html = '<option value="">Auto-detectar</option>';
          d.vision_models.forEach(m => { html += '<option value="' + m + '">'+m+'</option>'; });
          // Also allow code models as vision fallback option
          if (d.code_models) {
            d.code_models.forEach(m => { html += '<option value="' + m + '">' + m + ' (texto)</option>'; });
          }
          visSel.innerHTML = html;
          // Auto-select qwen3-vl if available, else minicpm
          const preferredVis = d.vision_models.find(m => m.includes('qwen3-vl')) || d.vision_models.find(m => m.includes('minicpm'));
          if (preferredVis) visSel.value = preferredVis;
        }
        // Update est-time hint
        updateModelEstimate();
      }).catch(() => {});
    }

export function updateModelEstimate() {
      const codeSel = document.getElementById('code-model-sel');
      const visSel = document.getElementById('vision-model-sel');
      const estEl = document.getElementById('est-time-val');
      if (!estEl) return;
      const codeM = codeSel ? codeSel.value : '';
      const visM = visSel ? visSel.value : '';
      const is3b = codeM.includes('3b') || codeM.includes('3.2') || !codeM;
      const isFastVis = visM.includes('minicpm') || !visM;
      estEl.textContent = (is3b ? '⚡ Código: ~1-2s (GPU)' : '🐢 Código: ~10-20s (CPU)') + ' · ' + (isFastVis ? '⚡ Visión: ~2-3s' : '🐢 Visión: ~15-40s');
    }

export async function onFolderPicked(e) {
      if (!e.target.files || e.target.files.length === 0) return;
      const file = e.target.files[0];
      let fullPath = '';
      const rootFolder = file.webkitRelativePath ? file.webkitRelativePath.split('/')[0] : '';

      // 1. If browser exposes absolute path (Electron, Native webviews)
      if (file.path) {
        const sep = file.path.includes('\\') ? '\\' : '/';
        const parts = file.path.split(sep);
        if (rootFolder && parts.includes(rootFolder)) {
          const rootIdx = parts.lastIndexOf(rootFolder);
          fullPath = parts.slice(0, rootIdx + 1).join(sep);
        } else {
          parts.pop();
          fullPath = parts.join(sep);
        }
      } else if (rootFolder) {
        // 2. Cross-platform dynamic parent directory calculation (No hardcoded paths)
        let currentInput = (document.getElementById('reg-path').value || state.activePath || '').trim();
        const sep = currentInput.includes('\\') ? '\\' : '/';
        currentInput = currentInput.replace(/[/\\]+$/, '');
        
        if (currentInput) {
          const lastIndex = currentInput.lastIndexOf(sep);
          if (lastIndex > 0) {
            const parentDir = currentInput.substring(0, lastIndex);
            fullPath = parentDir + sep + rootFolder;
          } else {
            fullPath = currentInput + sep + rootFolder;
          }
        } else {
          fullPath = rootFolder;
        }
      }

      if (fullPath) {
        document.getElementById('reg-path').value = fullPath;
      }
    }

export async function loadHistoryUI() {
      const container = document.getElementById('hist-list');
      if (!container) return;
      try {
        const res = await fetch('/api/history?path=' + encodeURIComponent(state.activePath));
        const data = await res.json();
        const timeline = data.timeline || [];
        if (timeline.length === 0) {
          container.innerHTML = '<div style="font-size:11px;color:#64748b;">Sin acciones registradas aún.</div>';
          return;
        }
        container.innerHTML = timeline.map(ev => {
          const dateStr = new Date(ev.timestamp * 1000).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
          return `
            <div style="background:#1a2234;border:1px solid #2d3748;border-radius:6px;padding:6px 8px;">
              <div style="display:flex;justify-content:space-between;font-size:10px;color:#38bdf8;font-weight:700;">
                <span>${ev.action_type.toUpperCase()}</span>
                <span style="color:#64748b;">${dateStr}</span>
              </div>
              <div style="font-size:11px;color:#e2e8f0;margin-top:3px;">${ev.summary}</div>
            </div>
          `;
        }).join('');
      } catch (e) {
        container.innerHTML = '<div style="font-size:11px;color:#ef4444;">Error al cargar historial.</div>';
      }
    }

export function focusHistoryEvent(sum) {
      if (!state.fullData || !state.fullData.nodes) return;
      const lowerSum = sum.lower ? sum.lower() : sum.toLowerCase();
      const match = state.fullData.nodes.find(n => lowerSum.includes(n.name.toLowerCase()));
      if (match) {
        focusNode(match);
      }
    }

export function toggleLeftSidebar() {
      const isCollapsed = document.body.classList.toggle('left-collapsed');
      document.querySelector('aside.left-aside').classList.toggle('collapsed', isCollapsed);
      document.getElementById('btn-toggle-left').textContent = isCollapsed ? '▶' : '◀';
      if (state.graphInst && typeof state.graphInst.width === 'function') {
        setTimeout(() => state.graphInst.width(document.getElementById('graph-container').clientWidth), 260);
      }
    }

export function toggleRightSidebar() {
      const isCollapsed = document.body.classList.toggle('right-collapsed');
      document.querySelector('aside.right-aside').classList.toggle('collapsed', isCollapsed);
      document.getElementById('btn-toggle-right').textContent = isCollapsed ? '◀' : '▶';
      if (state.graphInst && typeof state.graphInst.width === 'function') {
        setTimeout(() => state.graphInst.width(document.getElementById('graph-container').clientWidth), 260);
      }
    }


document.addEventListener('click', e => {
  if (!e.target.closest('.dd-wrap')) document.querySelectorAll('.dd-wrap').forEach(d => d.classList.remove('open'));
});
loadOllamaModels();
