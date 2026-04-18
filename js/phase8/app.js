/* Phase 8 - App Main (라우팅 + 탭 토글 + PTR + Swipe)
 * Note: BNF 탭은 iframe으로 bnf_dashboard.html을 인페이지 렌더
 */

import { $, $$, fmtTime, getTodayKST, fmtDate } from './ui.js';
import { initArena, refreshArena } from './arena.js';
import { initTelegram, refreshTelegram } from './telegram.js';
import { clearCache } from './cache.js';

// ============ Tab management ============
const TABS = ['arena', 'telegram', 'bnf'];
// 하단 네비에서 arena 내부 섹션으로 스크롤하는 가상 탭
const SECTION_TABS = { candidates: '📋 내일 후보', trades: '📜 매매 내역' };

let currentTab = 'arena';

function showMainTab(tab) {
  // arena 내부 섹션 가상 탭 처리
  if (SECTION_TABS[tab]) {
    currentTab = 'arena';
    $$('.main-tab').forEach(b => b.classList.toggle('active', b.dataset.tab === 'arena'));
    $$('.bottom-tab').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
    $$('.main-pane').forEach(p => p.classList.toggle('active', p.id === 'pane-arena'));
    setTimeout(() => {
      const keyword = SECTION_TABS[tab];
      const searchText = keyword.replace(/^.\s*/, '');
      const sections = document.querySelectorAll('#arena-content .section, #arena-content .card');
      for (const sec of sections) {
        const title = sec.querySelector('.section-title');
        if (title && title.textContent.includes(searchText)) {
          sec.scrollIntoView({ behavior: 'smooth', block: 'start' });
          return;
        }
      }
      window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });
    }, 100);
    return;
  }

  if (!TABS.includes(tab)) {
    console.warn('[Tab] 미등록 탭:', tab, 'TABS:', TABS);
    return;
  }
  console.log('[Tab] 전환:', tab);
  currentTab = tab;
  $$('.main-tab').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
  $$('.bottom-tab').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
  $$('.main-pane').forEach(p => {
    const isActive = p.id === `pane-${tab}`;
    p.classList.toggle('active', isActive);
    if (isActive) console.log('[Tab] pane 활성화:', p.id);
  });

  if (window.location.hash !== `#${tab}`) {
    history.replaceState(null, '', `#${tab}`);
  }
  // BNF/볼린저 탭 전환 시 iframe 처리
  if (tab === 'bnf') {
    setTimeout(() => {
      const iframe = $('#bnf-iframe');
      if (iframe && iframe.contentWindow) {
        iframe.contentWindow.scrollTo({ top: 0, behavior: 'smooth' });
      }
    }, 200);
  }
  window.scrollTo({ top: 0, behavior: 'smooth' });
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
    await Promise.all([refreshArena(), refreshTelegram()]);
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

// ============ Dark Mode ============
function initTheme() {
  const saved = localStorage.getItem('theme');
  const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
  const theme = saved || (prefersDark ? 'dark' : 'light');
  applyTheme(theme);
}

function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  localStorage.setItem('theme', theme);
  const btn = $('#theme-toggle');
  if (btn) btn.textContent = theme === 'dark' ? '☀️' : '🌙';
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.content = theme === 'dark' ? '#0f1419' : '#F8FAFB';
}

function toggleTheme() {
  const current = document.documentElement.getAttribute('data-theme') || 'light';
  applyTheme(current === 'dark' ? 'light' : 'dark');
}

// ============ Init ============
async function init() {
  // Theme
  initTheme();
  const themeBtn = $('#theme-toggle');
  if (themeBtn) themeBtn.addEventListener('click', toggleTheme);

  // Tab listeners
  $$('.main-tab').forEach(btn => {
    btn.addEventListener('click', () => showMainTab(btn.dataset.tab));
  });
  $$('.bottom-tab').forEach(btn => {
    if (btn.tagName === 'A') return; // skip link tabs
    btn.addEventListener('click', () => showMainTab(btn.dataset.tab));
  });

  // Refresh button
  const refreshBtn = $('#refresh-btn');
  if (refreshBtn) refreshBtn.addEventListener('click', refreshAll);

  // Init data
  await Promise.all([initArena(), initTelegram()]);
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
