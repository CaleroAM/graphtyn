import {
  setView, setDim, setMemoryGraphMode, toggleRotate, toggleVertexBlink, updateLinkStyles,
  refreshMemoryColorControls, selectMemoryColorKind, selectMemoryPalette, changeMemoryColor, toggleMemoryHaloLink,
  toggleRadiance, resetMemoryColorType, resetMemoryColorSettings, focusNode, applyFilter, renderCommunityNodes, changeGraphStyle, changeNodeColor, changeNodeShape, changePalette,
  changeStyleColors, closeBlastPanel, doReindex, exportGraphData, exportGraphPNG, setPRBase,
  onFolderPicked, selectProject, toggleAllComm, toggleComm, toggleDD, toggleGitignore,
  toggleLeftSidebar, toggleOrganic3d, toggleRightSidebar, loadHistoryUI, toggleNodeDesc,
  openRegister, closeRegister, selMode, submitRegister, openTutorial, closeTutorial,
  loadProjects, loadAgents, selectAgent, openAgentRegister, closeAgentRegister, submitAgentRegister,
  updateModelEstimate, initWatchPolling, openQualityPanel, closeQualityPanel,
  addNodeToContext, removeNodeFromContext, clearContextSelection, generateContextBundle,
  copyContextBundle, focusWebFlow, clearWebFlow, loadIndexUpdate, loadAmbiguities,
  reviewAmbiguity, validateAgentAnswer, generateChangeReport, openMemoryPanel,
  closeMemoryPanel, loadMemoryOverview, searchSharedMemory, correctSharedMemory, forgetSharedMemory,
  showSharedMemoryGraph, openSessionDetail, focusMemoryNode, focusMemorySession, clearMemorySessionFocus,
  loadMoreMemoryTopics, searchMemorySessions, loadMoreMemorySessions, linkAgentProfile,
  discoverHistoricalMemory, applyHistoricalMemory, copyNodeReference, syncMemorySpace,
  syncAllMemorySpaces, retryMemoryEnrichment, toggleMemoryWatch
} from './js/__handlers.js';
import { state } from './js/state.js';

// ── Helpers ───────────────────────────────────────────────────────────────



    // ── Dropdown ──────────────────────────────────────────────────────────────


    function closeDropdownMenus() {
      document.querySelectorAll('.dd-wrap').forEach(d => {
        d.classList.remove('open');
        const button = d.querySelector(':scope > button');
        if (button) button.setAttribute('aria-expanded', 'false');
      });
      document.body.classList.remove('header-menu-open');
    }
    document.addEventListener('click', e => {
      if (!e.target.closest('.dd-wrap')) closeDropdownMenus();
    });
    document.addEventListener('keydown', e => {
      if (e.key === 'Escape') {
        closeDropdownMenus();
        closeQualityPanel();
        closeMemoryPanel();
        closeRegister();
        closeAgentRegister();
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
    const WELCOME_KEY = 'graphtyn.welcome.0.6.1';
    function showWelcomeOnce() {
      try {
        if (localStorage.getItem(WELCOME_KEY)) return;
      } catch (_) { /* El dashboard sigue funcionando si el almacenamiento está bloqueado. */ }
      const url = document.getElementById('welcome-dashboard-url');
      if (url) url.textContent = window.location.origin;
      document.getElementById('modal-welcome')?.classList.add('show');
    }
    function closeWelcome() {
      document.getElementById('modal-welcome')?.classList.remove('show');
      try { localStorage.setItem(WELCOME_KEY, 'seen'); } catch (_) {}
    }

    let booted = false;
    function boot() {
      if (booted) return;
      booted = true;
      refreshMemoryColorControls();
      showWelcomeOnce();
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

Object.assign(window, {applyFilter, renderCommunityNodes, changeGraphStyle, changeNodeColor, changeNodeShape, changePalette, changeStyleColors, refreshMemoryColorControls, selectMemoryColorKind, selectMemoryPalette, changeMemoryColor, toggleMemoryHaloLink, toggleRadiance, resetMemoryColorType, resetMemoryColorSettings, closeBlastPanel, closeRegister, closeAgentRegister, closeTutorial, closeWelcome, doReindex, exportGraphData, exportGraphPNG, onFolderPicked, openRegister, openAgentRegister, openTutorial, selMode, setDim, setView, setMemoryGraphMode, setPRBase, submitRegister, submitAgentRegister, toggleAllComm, toggleComm, toggleDD, toggleGitignore, toggleLeftSidebar, toggleOrganic3d, toggleRightSidebar, toggleRotate, toggleVertexBlink, updateLinkStyles, focusNode, focusWebFlow, clearWebFlow, copyNodeReference, openFromChanges, selectProject, loadAgents, selectAgent, loadHistoryUI, toggleNodeDesc, updateModelEstimate, openQualityPanel, closeQualityPanel, addNodeToContext, removeNodeFromContext, clearContextSelection, generateContextBundle, copyContextBundle, loadIndexUpdate, loadAmbiguities, reviewAmbiguity, validateAgentAnswer, generateChangeReport, openMemoryPanel, closeMemoryPanel, loadMemoryOverview, searchSharedMemory, searchMemorySessions, loadMoreMemorySessions, loadMoreMemoryTopics, correctSharedMemory, forgetSharedMemory, showSharedMemoryGraph, openSessionDetail, focusMemoryNode, focusMemorySession, clearMemorySessionFocus, linkAgentProfile, discoverHistoricalMemory, applyHistoricalMemory, syncMemorySpace, syncAllMemorySpaces, retryMemoryEnrichment, toggleMemoryWatch});
