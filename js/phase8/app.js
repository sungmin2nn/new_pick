/* Phase 8 - App Main (라우팅 + 탭 토글 + PTR + Swipe)
 * Note: BNF 탭은 iframe으로 bnf_dashboard.html을 인페이지 렌더
 */

import { $, $$, fmtTime, getTodayKST, fmtDate } from './ui.js';
import { initArena, refreshArena } from './arena.js';
import { initTelegram, refreshTelegram } from './telegram.js';
import { clearCache } from './cache.js';

// ============ Tab management ============
const TABS = ['arena', 'swing', 'strategy'];
// 하단 네비에서 arena 내부 섹션으로 스크롤하는 가상 탭
const SECTION_TABS = { candidates: '📋 내일 후보', trades: '📜 매매 내역' };

let equityChartInstance = null;
let dailyPnlChartInstance = null;
let strategyChartsBuilt = false;

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
  // Swing 탭 전환 시 iframe 처리
  if (tab === 'swing') {
    setTimeout(() => {
      const iframe = $('#bnf-iframe');
      if (iframe && iframe.contentWindow) {
        iframe.contentWindow.scrollTo({ top: 0, behavior: 'smooth' });
      }
    }, 200);
  }
  // Strategy 탭 전환 시 차트 + 전략 Lab 렌더
  if (tab === 'strategy') {
    const labDiv = document.getElementById('strategy-lab-content');
    if (labDiv && !labDiv.innerHTML.trim()) {
      import('./arena.js').then(m => {
        const kpiHtml = m.renderStrategyKPIRow ? m.renderStrategyKPIRow() : '';
        const monthlyHtml = m.renderMonthlyReturnsTable ? m.renderMonthlyReturnsTable() : '';
        const panelHtml = m.renderStrategyPanel ? m.renderStrategyPanel() : '';
        labDiv.innerHTML = kpiHtml + monthlyHtml + panelHtml;
        // 전략 Lab 아코디언 바인딩
        labDiv.querySelectorAll('.acc-strat-head').forEach(head => {
          head.addEventListener('click', () => {
            const strat = head.closest('.acc-strat');
            if (strat) strat.classList.toggle('open');
          });
        });
      });
    }
    buildStrategyCharts();
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

// ============ Strategy Charts (Chart.js) ============
async function buildStrategyCharts() {
  if (strategyChartsBuilt) return;
  if (typeof Chart === 'undefined') {
    console.warn('[Chart] Chart.js 미로드');
    return;
  }

  try {
    const { fetchCached } = await import('./cache.js');
    const lb = await fetchCached('data/arena/leaderboard.json');
    console.log('[Chart] leaderboard:', lb ? `${(lb.daily_history||[]).length}일` : 'null');
    if (!lb || !lb.daily_history || lb.daily_history.length === 0) {
      console.warn('[Chart] daily_history 없음');
      return;
    }

    const history = lb.daily_history;
    const dates = history.map(d => {
      const s = d.date;
      return s ? s.slice(4,6) + '/' + s.slice(6,8) : '';
    });

    // ranking 배열에서 팀 ID 수집
    const teamIdSet = new Set();
    history.forEach(d => {
      (d.ranking || []).forEach(r => { if (r.team_id) teamIdSet.add(r.team_id); });
    });
    const teamIds = [...teamIdSet].sort();

    const COLORS = {
      team_a: '#EF4444', team_b: '#3B82F6', team_c: '#10B981',
      team_d: '#F59E0B', team_e: '#8B5CF6', team_f: '#EC4899',
      team_g: '#14B8A6', team_h: '#F97316', team_i: '#6366F1',
    };
    const NAMES = lb.teams || {};

    // --- Benchmark (KOSPI) data ---
    let benchmarkData = null;
    try {
      benchmarkData = await fetchCached('data/arena/benchmark.json');
    } catch (e) { /* benchmark 파일 없으면 스킵 */ }

    // --- Equity Curve ---
    const equityCtx = document.getElementById('equityChart');
    if (equityCtx && teamIds.length > 0) {
      if (equityChartInstance) equityChartInstance.destroy();
      const datasets = teamIds.map(tid => {
        const teamName = NAMES[tid]?.team_name?.split(' ')[0] || tid;
        return {
          label: teamName,
          data: history.map(d => {
            const r = (d.ranking || []).find(x => x.team_id === tid);
            return r ? r.total_return : null;
          }),
          borderColor: COLORS[tid] || '#6B7280',
          backgroundColor: 'transparent',
          borderWidth: 2,
          pointRadius: 3,
          pointBackgroundColor: COLORS[tid] || '#6B7280',
          tension: 0.3,
          spanGaps: true,
        };
      });

      // KOSPI 벤치마크 라인 추가 (benchmark.json이 있으면)
      if (benchmarkData && benchmarkData.daily) {
        const kospiReturns = history.map(d => {
          const dateStr = d.date || '';
          const entry = benchmarkData.daily.find(b => b.date === dateStr);
          return entry ? entry.return_pct : null;
        });
        datasets.push({
          label: 'KOSPI',
          data: kospiReturns,
          borderColor: '#9CA3AF',
          backgroundColor: 'transparent',
          borderWidth: 2,
          borderDash: [6, 3],
          pointRadius: 0,
          tension: 0.3,
          spanGaps: true,
        });
      }

      equityChartInstance = new Chart(equityCtx, {
        type: 'line',
        data: { labels: dates, datasets },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { position: 'bottom', labels: { boxWidth: 10, font: { size: 10 }, padding: 8 } },
            tooltip: {
              callbacks: { label: c => `${c.dataset.label}: ${c.parsed.y >= 0 ? '+' : ''}${c.parsed.y.toFixed(2)}%` }
            }
          },
          scales: {
            x: { grid: { display: false }, ticks: { font: { size: 10 } } },
            y: { grid: { color: 'rgba(0,0,0,0.05)' }, ticks: { font: { size: 10 }, callback: v => v.toFixed(1) + '%' } },
          },
        },
      });
    }

    // --- Daily P&L Bar ---
    const pnlCtx = document.getElementById('dailyPnlChart');
    if (pnlCtx && history.length > 0) {
      if (dailyPnlChartInstance) dailyPnlChartInstance.destroy();
      const avgReturns = history.map(d => {
        const ranking = d.ranking || [];
        if (ranking.length === 0) return 0;
        return ranking.reduce((s, r) => s + (r.total_return || 0), 0) / ranking.length;
      });
      const dailyPnl = avgReturns.map((v, i) => i === 0 ? v : v - avgReturns[i - 1]);

      dailyPnlChartInstance = new Chart(pnlCtx, {
        type: 'bar',
        data: {
          labels: dates,
          datasets: [{
            label: '일별 평균',
            data: dailyPnl,
            backgroundColor: dailyPnl.map(v => v >= 0 ? 'rgba(16,185,129,0.7)' : 'rgba(239,68,68,0.7)'),
            borderRadius: 4,
            barPercentage: 0.6,
          }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { display: false },
            tooltip: { callbacks: { label: c => `${c.parsed.y >= 0 ? '+' : ''}${c.parsed.y.toFixed(2)}%` } }
          },
          scales: {
            x: { grid: { display: false }, ticks: { font: { size: 10 } } },
            y: { grid: { color: 'rgba(0,0,0,0.05)' }, ticks: { font: { size: 10 }, callback: v => v.toFixed(1) + '%' } },
          },
        },
      });
    }

    strategyChartsBuilt = true;
  } catch (e) {
    console.warn('[Strategy] 차트 빌드 실패:', e);
  }
}

// ============ Init ============
async function init() {
  // Theme
  initTheme();
  const themeBtn = $('#theme-toggle');
  if (themeBtn) themeBtn.addEventListener('click', toggleTheme);

  // 툴팁 닫기 (다른 곳 터치 시)
  document.addEventListener('click', (e) => {
    if (!e.target.classList.contains('metric-tip')) {
      document.querySelectorAll('.metric-tip.show').forEach(t => t.classList.remove('show'));
    }
  });

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
  if (TABS.includes(hash) || SECTION_TABS[hash]) showMainTab(hash);

  // Status bar clock
  setInterval(updateStatusBar, 60 * 1000);

  // Auto refresh
  startAutoRefresh();

  // Mobile gestures
  // initSwipe(); // 스와이프 탭 전환 비활성 (필터 탭 수평 스크롤과 충돌)
  initPTR();
}

document.addEventListener('DOMContentLoaded', init);
