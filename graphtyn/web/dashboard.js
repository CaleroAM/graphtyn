import {
  setView, setDim, toggleRotate, toggleVertexBlink, updateLinkStyles,
  focusNode, applyFilter, changeGraphStyle, changeNodeColor, changeNodeShape, changePalette,
  changeStyleColors, closeBlastPanel, doReindex, exportGraphData, exportGraphPNG, setPRBase,
  onFolderPicked, selectProject, toggleAllComm, toggleComm, toggleDD, toggleGitignore,
  toggleLeftSidebar, toggleOrganic3d, toggleRightSidebar, loadHistoryUI, toggleNodeDesc,
  openRegister, closeRegister, selMode, submitRegister, openTutorial, closeTutorial,
  loadProjects, updateModelEstimate, initWatchPolling, openQualityPanel, closeQualityPanel,
  addNodeToContext, removeNodeFromContext, clearContextSelection, generateContextBundle,
  copyContextBundle, focusWebFlow, clearWebFlow, loadIndexUpdate, loadAmbiguities,
  reviewAmbiguity, validateAgentAnswer, generateChangeReport
} from './js/__handlers.js';
import { state } from './js/state.js';

// ── Helpers ───────────────────────────────────────────────────────────────



    // ── Dropdown ──────────────────────────────────────────────────────────────


    document.addEventListener('click', e => {
      if (!e.target.closest('.dd-wrap')) document.querySelectorAll('.dd-wrap').forEach(d => d.classList.remove('open'));
    });
    document.addEventListener('keydown', e => {
      if (e.key === 'Escape') {
        closeQualityPanel();
        closeRegister();
        closeTutorial();
        closeBlastPanel();
      }
    });

    // ── Modals ────────────────────────────────────────────────────────────────



    // ── Projects ──────────────────────────────────────────────────────────────



    // ── View / Dim ────────────────────────────────────────────────────────────












    // ── Communities sidebar ───────────────────────────────────────────────────



    // ── Filter ────────────────────────────────────────────────────────────────



    // ── Graph render ──────────────────────────────────────────────────────────



    
    // ── Blast Radius & Interactive Node Inspector ───────────────────────────
    state.selectedNode = null;




    state.descExpanded = false;



    
// ── Boot ──────────────────────────────────────────────────────────────────
    let booted = false;
    function boot() {
      if (booted) return;
      booted = true;
      loadProjects(true);
      initWatchPolling();
    }
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', boot);
    } else {
      boot();
    }




function openFromChanges(nodeId) {
  setView('code');
  setTimeout(() => focusNode(nodeId), 500);
}

Object.assign(window, {applyFilter, changeGraphStyle, changeNodeColor, changeNodeShape, changePalette, changeStyleColors, closeBlastPanel, closeRegister, closeTutorial, doReindex, exportGraphData, exportGraphPNG, onFolderPicked, openRegister, openTutorial, selMode, setDim, setView, setPRBase, submitRegister, toggleAllComm, toggleComm, toggleDD, toggleGitignore, toggleLeftSidebar, toggleOrganic3d, toggleRightSidebar, toggleRotate, toggleVertexBlink, updateLinkStyles, focusNode, focusWebFlow, clearWebFlow, openFromChanges, selectProject, loadHistoryUI, toggleNodeDesc, updateModelEstimate, openQualityPanel, closeQualityPanel, addNodeToContext, removeNodeFromContext, clearContextSelection, generateContextBundle, copyContextBundle, loadIndexUpdate, loadAmbiguities, reviewAmbiguity, validateAgentAnswer, generateChangeReport});
