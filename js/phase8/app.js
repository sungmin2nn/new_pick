/* Phase 8 - App Main (라우팅 + 탭 토글 + PTR + Swipe)
 * Note: BNF는 별도 페이지(bnf_dashboard.html)로 분리. 메인 페이지는 Arena만.
 */

import { $, $$, fmtTime, getTodayKST, fmtDate } from './ui.js';
import { initArena, refreshArena } from './arena.js';
import { clearCache } from './cache.js';

// ============ Tab management ============
const TABS = ['arena'];  // BNF is external link
let currentTab = 'arena';

function showMainTab(tab) {
  if (!TABS.includes(tab)) return;
  currentTab = tab;
  $$('.main-tab').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
  $$('.bottom-tab').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
  $$('.main-pane').forEach(p => p.classList.toggle('active', p.id === `pane-${tab}`));
  // URL hash 업데이트
  if (window.location.hash !== `#${tab}`) {
    history.replaceState(null, '', `#${tab}`);
  }
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function showSubTab(tab, sectionId) {
  // tab: 'arena' or 'bnf', sectionId: target sub-pane id
  const tabsContainer = document.getElementById(`${tab}-subtabs`);
  if (!tabsContainer) return;
  $$('.sub-tab', tabsContainer).forEach(b => b.classList.toggle('active', b.dataset.section === sectionId));
  const pane = document.getElementById(`pane-${tab}`);
  if (!pane) return;
  $$('.sub-pane', pane).forEach(p => p.classList.toggle('active', p.id === sectionId));
}

// ============ Status bar update ============
function updateStatusBar() {
  const lastEl = $('#status-last-refresh');
  if (lastEl) lastEl.textContent = fmtTime();

  const dateEl = $('#status-date');
  if (dateEl) dateEl.textContent = fmtDate(getTodayKST());
}

// ============ Refresh ============
async function refreshAll() {
  const btn = $('#refresh-btn');
  if (btn) btn.disabled = true;
  clearCache();
  try {
    await refreshArena();
    updateStatusBar();
  } finally {
    if (btn) btn.disabled = false;
  }
}

// ============ Auto-refresh (5분) ============
function startAutoRefresh() {
  setInterval(refreshAll, 5 * 60 * 1000);
}

// ============ Swipe gestures ============
function initSwipe() {
  let startX = 0, startY = 0, startT = 0;

  document.addEventListener('touchstart', (e) => {
    startX = e.touches[0].clientX;
    startY = e.touches[0].clientY;
    startT = Date.now();
  }, { passive: true });

  document.addEventListener('touchend', (e) => {
    const dx = e.changedTouches[0].clientX - startX;
    const dy = e.changedTouches[0].clientY - startY;
    const dt = Date.now() - startT;

    // Horizontal swipe, fast
    if (Math.abs(dx) < 80 || Math.abs(dy) > Math.abs(dx) * 0.6 || dt > 500) return;

    // Skip if inside scrollable
    if (e.target.closest('.no-scrollbar') || e.target.closest('.table-wrap')) return;

    const idx = TABS.indexOf(currentTab);
    if (idx === -1) return;
    const next = dx < 0 ? idx + 1 : idx - 1;
    if (next >= 0 && next < TABS.length) {
      showMainTab(TABS[next]);
    }
  }, { passive: true });
}

// ============ Pull-to-Refresh ============
function initPTR() {
  const ptr = $('#ptr');
  if (!ptr) return;
  let startY = 0, pulled = 0, pulling = false;

  document.addEventListener('touchstart', (e) => {
    if (window.scrollY > 0) return;
    startY = e.touches[0].clientY;
    pulling = true;
  }, { passive: true });

  document.addEventListener('touchmove', (e) => {
    if (!pulling) return;
    pulled = e.touches[0].clientY - startY;
    if (pulled > 0 && pulled < 100) {
      ptr.style.transform = `translateY(${pulled}px)`;
      ptr.style.opacity = String(Math.min(pulled / 60, 1));
    }
  }, { passive: true });

  document.addEventListener('touchend', () => {
    if (!pulling) return;
    pulling = false;
    if (pulled > 60) {
      ptr.textContent = '새로고침 중...';
      refreshAll().then(() => {
        ptr.textContent = '당겨서 새로고침';
      });
    }
    ptr.style.transform = 'translateY(0)';
    ptr.style.opacity = '0';
    pulled = 0;
  }, { passive: true });
}

// ============ Init ============
async function init() {
  // Tab listeners
  $$('.main-tab').forEach(btn => {
    btn.addEventListener('click', () => showMainTab(btn.dataset.tab));
  });
  $$('.bottom-tab').forEach(btn => {
    btn.addEventListener('click', () => showMainTab(btn.dataset.tab));
  });

  // Sub-tab listeners (delegated)
  document.addEventListener('click', (e) => {
    const subBtn = e.target.closest('.sub-tab');
    if (!subBtn) return;
    const tabsContainer = subBtn.closest('.sub-tabs');
    if (!tabsContainer) return;
    const tab = tabsContainer.dataset.tab;
    const section = subBtn.dataset.section;
    if (tab && section) showSubTab(tab, section);
  });

  // Refresh button
  const refreshBtn = $('#refresh-btn');
  if (refreshBtn) refreshBtn.addEventListener('click', refreshAll);

  // Init data (Arena only - BNF is external link)
  await initArena();
  updateStatusBar();

  // Hash routing
  const hash = window.location.hash.replace('#', '');
  if (TABS.includes(hash)) showMainTab(hash);

  // Status bar clock
  setInterval(updateStatusBar, 60 * 1000);

  // Auto refresh
  startAutoRefresh();

  // Mobile gestures
  initSwipe();
  initPTR();
}

document.addEventListener('DOMContentLoaded', init);
