/* Phase 8 - Arena Tab Renderer (Single Scroll + 3-Depth Accordion) */

import { fetchCached } from './cache.js';
import {
  fmtNum, fmtMoney, fmtPct, fmtPctSigned, fmtDate,
  colorClass, $, $$, getTodayKST, getRecentDates
} from './ui.js';

const TEAM_META = {
  team_a: { name: 'Alpha Momentum', desc: 'MA5 + 거래량 급증', color: '#EF4444', strategy: 'momentum' },
  team_b: { name: 'Beta Contrarian', desc: '대형주 RSI 역추세', color: '#3B82F6', strategy: 'largecap_contrarian' },
  team_c: { name: 'Gamma Disclosure', desc: 'DART 호재 공시', color: '#10B981', strategy: 'dart_disclosure' },
  team_d: { name: 'Delta Theme', desc: '테마/정책 + 섹터', color: '#F59E0B', strategy: 'theme_policy' },
  team_e: { name: 'Echo Frontier', desc: '시초가 갭 + surge', color: '#8B5CF6', strategy: 'frontier_gap' },
};

const MEDALS = ['🥇', '🥈', '🥉', '4', '5'];
const TEAM_IDS = Object.keys(TEAM_META);
const DATA_BASE = 'data/arena';

let state = {
  leaderboard: null,
  portfolios: {},
  health: null,
  candidates: {},
  history: {}, // tid -> [{date, summary, trades}, ...] (최근 → 과거 순)
};

// ============ Data loading ============
export async function loadArenaData(force = false) {
  const today = getTodayKST();

  state.leaderboard = await fetchCached(`${DATA_BASE}/leaderboard.json`, force);

  for (const tid of TEAM_IDS) {
    state.portfolios[tid] = await fetchCached(`${DATA_BASE}/${tid}/portfolio.json`, force);
  }

  // Health: 오늘 → 최근 7일 fallback
  state.health = await fetchCached(`${DATA_BASE}/healthcheck/health_${today}.json`, force);
  if (!state.health) {
    for (const d of getRecentDates(7).slice(1)) {
      const log = await fetchCached(`${DATA_BASE}/healthcheck/health_${d}.json`, force);
      if (log) { state.health = log; break; }
    }
  }

  // Tomorrow candidates
  for (const tid of TEAM_IDS) {
    const sid = TEAM_META[tid].strategy;
    const path = `data/paper_trading/candidates_${today}_${sid}.json`;
    state.candidates[sid] = await fetchCached(path, force);
  }

  // 매매 이력: leaderboard.daily_history 의 날짜 기준 (최근 → 과거)
  // 각 팀의 daily/{date}/summary.json + trades.json fetch
  const histDates = (state.leaderboard?.daily_history || [])
    .map(h => h.date)
    .filter(Boolean)
    .reverse(); // 최근 우선
  for (const tid of TEAM_IDS) {
    state.history[tid] = [];
    for (const date of histDates) {
      const summary = await fetchCached(`${DATA_BASE}/${tid}/daily/${date}/summary.json`, force);
      if (!summary) continue;
      const trades = await fetchCached(`${DATA_BASE}/${tid}/daily/${date}/trades.json`, force);
      state.history[tid].push({ date, summary, trades });
    }
  }

  return state;
}

// ============ Helper: rows with portfolio + leaderboard combined ============
function buildTeamRows() {
  const todayHist = state.leaderboard?.daily_history?.slice(-1)[0];
  return TEAM_IDS.map(tid => {
    const meta = TEAM_META[tid];
    const pf = state.portfolios[tid] || {};
    const lbTeam = state.leaderboard?.teams?.[tid] || {};
    const todayRank = todayHist?.ranking?.find(r => r.team_id === tid);
    const wr = pf.total_trades > 0 ? Math.round(pf.total_wins / pf.total_trades * 100) : 0;
    return {
      tid, name: meta.name, desc: meta.desc, color: meta.color,
      today_pct: todayRank?.total_return ?? 0,
      cum_pct: pf.total_return_pct ?? 0,
      capital: pf.current_capital ?? 10000000,
      elo: lbTeam.elo ?? 1000,
      wins: pf.total_wins ?? 0,
      trades: pf.total_trades ?? 0,
      win_rate: wr,
    };
  });
}

// ============ Sections ============
function renderKPI(rows) {
  const dailyAvg = rows.reduce((s, t) => s + t.today_pct, 0) / Math.max(rows.length, 1);
  const sorted = [...rows].sort((a, b) => b.today_pct - a.today_pct);
  const maxRow = sorted[0];
  const totalCapital = rows.reduce((s, t) => s + t.capital, 0);
  const totalCum = ((totalCapital - 10000000 * rows.length) / (10000000 * rows.length)) * 100;
  const dayN = state.leaderboard?.daily_history?.length ?? 0;
  const totalTrades = rows.reduce((s, t) => s + t.trades, 0);
  const totalWins = rows.reduce((s, t) => s + t.wins, 0);

  return `
    <div class="section">
      <div class="kpi-grid">
        <div class="kpi">
          <div class="kpi-label">5팀 평균</div>
          <div class="kpi-value ${colorClass(dailyAvg)}">${fmtPctSigned(dailyAvg)}</div>
          <div class="kpi-meta">Day ${dayN}</div>
        </div>
        <div class="kpi">
          <div class="kpi-label">최고</div>
          <div class="kpi-value up">${fmtPctSigned(maxRow.today_pct)}</div>
          <div class="kpi-meta">${maxRow.name.split(' ')[0]}</div>
        </div>
        <div class="kpi">
          <div class="kpi-label">총 자산</div>
          <div class="kpi-value">${fmtMoney(totalCapital)}</div>
          <div class="kpi-meta ${colorClass(totalCum)}">누적 ${fmtPct(totalCum)}</div>
        </div>
        <div class="kpi">
          <div class="kpi-label">총 매매</div>
          <div class="kpi-value">${totalTrades}건</div>
          <div class="kpi-meta">${totalWins}승 ${totalTrades - totalWins}패</div>
        </div>
      </div>
    </div>
  `;
}

function renderH2H(rows) {
  const sorted = [...rows].sort((a, b) => b.elo - a.elo);
  if (sorted.length < 2) return '';
  const t1 = sorted[0], t2 = sorted[1];
  const gap = Math.abs(t1.today_pct - t2.today_pct);

  return `
    <div class="h2h">
      <div class="h2h-header">🏆 TOP 2 HEAD-TO-HEAD</div>
      <div class="h2h-body">
        <div class="h2h-team">
          <div class="h2h-badge" style="color:${t1.color};background:${t1.color}15;">1</div>
          <div class="h2h-name">${t1.name.split(' ')[0]}</div>
          <div class="h2h-return ${colorClass(t1.today_pct)}">${fmtPctSigned(t1.today_pct)}</div>
          <div class="h2h-meta">ELO ${t1.elo} · 승률 ${t1.win_rate}%</div>
        </div>
        <div class="h2h-vs">VS</div>
        <div class="h2h-team">
          <div class="h2h-badge" style="color:${t2.color};background:${t2.color}15;">2</div>
          <div class="h2h-name">${t2.name.split(' ')[0]}</div>
          <div class="h2h-return ${colorClass(t2.today_pct)}">${fmtPctSigned(t2.today_pct)}</div>
          <div class="h2h-meta">ELO ${t2.elo} · 승률 ${t2.win_rate}%</div>
        </div>
      </div>
      <div class="h2h-gap">리드 격차 <span class="h2h-gap-pill">${gap.toFixed(2)}%p</span></div>
    </div>
  `;
}

function renderRanking(rows) {
  const sorted = [...rows].sort((a, b) => b.today_pct - a.today_pct);
  const cards = sorted.map((t, i) => `
    <div class="team-card" style="border-left-color:${t.color};">
      <div class="team-medal">${MEDALS[Math.min(i, 4)]}</div>
      <div class="name">${t.name}</div>
      <div class="desc">${t.desc}</div>
      <div class="team-card-side">
        <div class="ret ${colorClass(t.today_pct)}">${fmtPctSigned(t.today_pct)}</div>
        <div class="cum">누적 ${fmtPct(t.cum_pct)} · ELO ${t.elo}</div>
      </div>
      <div class="team-stats">
        <div class="team-stat">
          <span class="team-stat-label">금일</span>
          <span class="team-stat-value ${colorClass(t.today_pct)}">${fmtPctSigned(t.today_pct)}</span>
        </div>
        <div class="team-stat">
          <span class="team-stat-label">누적</span>
          <span class="team-stat-value ${colorClass(t.cum_pct)}">${fmtPct(t.cum_pct)}</span>
        </div>
        <div class="team-stat">
          <span class="team-stat-label">잔고</span>
          <span class="team-stat-value">${fmtMoney(t.capital)}</span>
        </div>
        <div class="team-stat">
          <span class="team-stat-label">ELO</span>
          <span class="team-stat-value">${t.elo}</span>
        </div>
      </div>
    </div>
  `).join('');

  return `
    <div class="section">
      <div class="section-header">
        <h2 class="section-title display">🏆 오늘 순위</h2>
        <span class="section-subtitle">5팀 일일 수익률</span>
      </div>
      <div class="team-grid">${cards}</div>
    </div>
  `;
}

// ============ Strategy Accordion (Depth 1 → 2 → 3) ============
// 전략별 점수 분해 키 → 표시 라벨 + 만점
const SCORE_KEY_META = {
  change_pct: { label: '등락률', max: 35 },
  trading_value: { label: '거래대금', max: 30 },
  volume_surge: { label: '거래량 급증', max: 20 },
  market_cap: { label: '시가총액', max: 30 },
  price_level: { label: '가격대', max: 15 },
  rsi: { label: 'RSI', max: 20 },
  category: { label: '카테고리', max: 30 },
  timing: { label: '시점', max: 20 },
  theme_strength: { label: '테마 강도', max: 25 },
  gap: { label: '시초가 갭', max: 25 },
  volume: { label: '거래량', max: 20 },
};

function renderScoreBar(label, val, max) {
  const w = Math.min(100, Math.max(0, val / max * 100)).toFixed(0);
  return `
    <div class="score-bar">
      <span class="score-bar-label">${label}</span>
      <div class="score-bar-track"><div class="score-bar-fill" style="width:${w}%;"></div></div>
      <span class="score-bar-val">${(+val).toFixed(1)}</span>
    </div>`;
}

function renderStockDetail(c, totalCount) {
  const sd = c.score_detail || {};
  // 실제 존재하는 키만 렌더 (전략마다 다름)
  const bars = Object.entries(sd).map(([key, val]) => {
    const meta = SCORE_KEY_META[key] || { label: key, max: 30 };
    return renderScoreBar(meta.label, +val || 0, meta.max);
  }).join('');

  return `
    <div class="sacc-detail">
      <div class="mini-kpi-grid">
        <div class="mini-kpi">
          <div class="mini-kpi-label">현재가</div>
          <div class="mini-kpi-value">${fmtMoney(c.price)}</div>
          <div class="mini-kpi-meta ${colorClass(c.change_pct)}">${c.change_pct >= 0 ? '▲ ' : '▼ '}${fmtPctSigned(c.change_pct)}</div>
        </div>
        <div class="mini-kpi">
          <div class="mini-kpi-label">종합 점수</div>
          <div class="mini-kpi-value">${(+c.score).toFixed(1)}</div>
          <div class="mini-kpi-meta">${totalCount}종목 중 ${c.rank}위</div>
        </div>
      </div>
      ${bars ? `<div class="detail-h">점수 분해</div>${bars}` : ''}
      ${c.trading_value ? `
      <div class="detail-h">거래 정보</div>
      <div class="detail-row"><span>거래대금</span><span class="num">${fmtMoney(c.trading_value)}</span></div>
      ${c.volume ? `<div class="detail-row"><span>거래량</span><span class="num">${fmtNum(c.volume)}</span></div>` : ''}
      ` : ''}
    </div>
  `;
}

function renderStrategiesAccordion(rows) {
  // ELO 1위 전략을 기본 펼침
  const sortedRows = [...rows].sort((a, b) => b.today_pct - a.today_pct);
  const topTid = sortedRows[0]?.tid;

  let totalStocks = 0;
  const accs = TEAM_IDS.map((tid) => {
    const meta = TEAM_META[tid];
    const cands = state.candidates[meta.strategy];
    const candList = cands?.candidates || (Array.isArray(cands) ? cands : []) || [];
    const count = candList.length;
    totalStocks += count;

    if (count === 0) {
      return `
        <div class="acc-strat" style="border-left-color:${meta.color};">
          <div class="acc-strat-head">
            <span class="acc-chev">▶</span>
            <div class="acc-info">
              <div class="acc-name">${meta.name}</div>
              <div class="acc-summary">${meta.desc} · 후보 없음</div>
            </div>
            <span class="acc-count">0</span>
          </div>
        </div>
      `;
    }

    const avgScore = candList.reduce((s, c) => s + (+c.score || 0), 0) / count;
    const avgPct = candList.reduce((s, c) => s + (+c.change_pct || 0), 0) / count;
    const isOpen = tid === topTid;

    const stockRows = candList.map((c, idx) => `
      <div class="sacc">
        <div class="sacc-head">
          <div class="sacc-rank">${idx + 1}</div>
          <div class="sacc-info">
            <b>${c.name || '-'}</b>
            <div class="sacc-code">${c.code || '-'}</div>
          </div>
          <div class="sacc-score">${(+c.score).toFixed(1)}</div>
          <div class="sacc-pct ${colorClass(c.change_pct)}">${fmtPctSigned(c.change_pct)}</div>
          <span class="sacc-chev">›</span>
        </div>
        <div class="sacc-body">
          ${renderStockDetail(c, count)}
        </div>
      </div>
    `).join('');

    return `
      <div class="acc-strat${isOpen ? ' open' : ''}" style="border-left-color:${meta.color};">
        <div class="acc-strat-head">
          <span class="acc-chev">▶</span>
          <div class="acc-info">
            <div class="acc-name">${meta.name}</div>
            <div class="acc-summary">
              평균점수 <span class="num">${avgScore.toFixed(1)}</span> · 평균 <span class="num ${colorClass(avgPct)}">${fmtPctSigned(avgPct)}</span>
            </div>
          </div>
          <span class="acc-count">${count}개</span>
        </div>
        <div class="acc-strat-body">
          <div class="acc-strat-body-inner">${stockRows}</div>
        </div>
      </div>
    `;
  }).join('');

  return `
    <div class="section">
      <div class="section-header">
        <h2 class="section-title display">📋 내일 후보</h2>
        <span class="section-subtitle">5전략 · ${totalStocks}종목</span>
      </div>
      <div class="acc-list">${accs}</div>
    </div>
  `;
}

// ============ History Section (전략별 매매 내역) ============
function renderHistorySection() {
  // 팀별로 history가 있는지 확인
  const hasAny = TEAM_IDS.some(tid => (state.history[tid] || []).length > 0);
  if (!hasAny) {
    return `
      <div class="section">
        <div class="section-header">
          <h2 class="section-title display">📜 매매 내역</h2>
          <span class="section-subtitle">아직 기록 없음</span>
        </div>
      </div>
    `;
  }

  let totalDays = 0;
  const accs = TEAM_IDS.map(tid => {
    const meta = TEAM_META[tid];
    const hist = state.history[tid] || [];
    if (hist.length === 0) {
      return `
        <div class="acc-strat" style="border-left-color:${meta.color};">
          <div class="acc-strat-head">
            <span class="acc-chev">▶</span>
            <div class="acc-info">
              <div class="acc-name">${meta.name}</div>
              <div class="acc-summary">매매 기록 없음</div>
            </div>
            <span class="acc-count">0</span>
          </div>
        </div>
      `;
    }
    totalDays += hist.length;

    // 최근 N일 총합 계산
    const totalTrades = hist.reduce((s, h) => s + (h.summary?.simulation?.total_trades || 0), 0);
    const totalWins = hist.reduce((s, h) => s + (h.summary?.simulation?.wins || 0), 0);
    const winRate = totalTrades > 0 ? (totalWins / totalTrades * 100).toFixed(0) : 0;

    const dayRows = hist.map((h, idx) => {
      const sim = h.summary?.simulation || {};
      const ret = sim.total_return ?? 0;
      const trades = sim.total_trades ?? 0;
      const wins = sim.wins ?? 0;
      const dateStr = h.date ? `${h.date.slice(4,6)}/${h.date.slice(6,8)}` : '-';
      const tradeResults = h.trades?.results || [];

      return `
        <div class="sacc">
          <div class="sacc-head">
            <div class="sacc-rank">${dateStr}</div>
            <div class="sacc-info">
              <b>${trades}건</b>
              <div class="sacc-code">${wins}승 ${trades - wins}패</div>
            </div>
            <div class="sacc-pct ${colorClass(ret)}">${fmtPctSigned(ret)}</div>
            <span class="sacc-chev">›</span>
          </div>
          <div class="sacc-body">
            ${renderTradeDetail(tradeResults, h.summary)}
          </div>
        </div>
      `;
    }).join('');

    return `
      <div class="acc-strat" style="border-left-color:${meta.color};">
        <div class="acc-strat-head">
          <span class="acc-chev">▶</span>
          <div class="acc-info">
            <div class="acc-name">${meta.name}</div>
            <div class="acc-summary">
              ${hist.length}일 · ${totalTrades}건 · 승률 <span class="num">${winRate}%</span>
            </div>
          </div>
          <span class="acc-count">${hist.length}일</span>
        </div>
        <div class="acc-strat-body">
          <div class="acc-strat-body-inner">${dayRows}</div>
        </div>
      </div>
    `;
  }).join('');

  return `
    <div class="section">
      <div class="section-header">
        <h2 class="section-title display">📜 매매 내역</h2>
        <span class="section-subtitle">최근 ${totalDays}건</span>
      </div>
      <div class="acc-list">${accs}</div>
    </div>
  `;
}

function renderTradeDetail(results, summary) {
  if (!results || results.length === 0) {
    return `<div class="sacc-detail"><div class="detail-h">매매 결과 없음</div></div>`;
  }
  const sim = summary?.simulation || {};
  const rows = results.map(t => {
    const cls = colorClass(t.return_pct);
    return `
      <div class="trade-row">
        <div class="trade-name">
          <b>${t.name || '-'}</b>
          <div class="trade-code">${t.code || '-'}</div>
        </div>
        <div class="trade-prices">
          <div class="num">${fmtMoney(t.entry_price)} → ${fmtMoney(t.exit_price)}</div>
          <div class="trade-meta">${t.exit_reason || ''} · ${t.quantity || 0}주</div>
        </div>
        <div class="trade-ret ${cls}">
          ${fmtPctSigned(t.return_pct)}
          <div class="trade-amount num">${(t.return_amount || 0) >= 0 ? '+' : ''}${fmtMoney(t.return_amount)}</div>
        </div>
      </div>
    `;
  }).join('');

  return `
    <div class="sacc-detail">
      <div class="mini-kpi-grid">
        <div class="mini-kpi">
          <div class="mini-kpi-label">일일 수익률</div>
          <div class="mini-kpi-value ${colorClass(sim.total_return)}">${fmtPctSigned(sim.total_return ?? 0)}</div>
          <div class="mini-kpi-meta">${fmtMoney(sim.total_return_amount ?? 0)}원</div>
        </div>
        <div class="mini-kpi">
          <div class="mini-kpi-label">승률</div>
          <div class="mini-kpi-value">${(sim.win_rate ?? 0).toFixed(0)}%</div>
          <div class="mini-kpi-meta">${sim.wins ?? 0}승 ${(sim.total_trades ?? 0) - (sim.wins ?? 0)}패</div>
        </div>
      </div>
      <div class="detail-h">매매 ${results.length}건</div>
      <div class="trade-list">${rows}</div>
    </div>
  `;
}

function renderSystemMini() {
  const h = state.health || {};
  const checks = h.checks || [];
  const passed = checks.filter(c => c.status === 'pass').length;
  const issues = h.issues || [];
  const status = h.status || 'unknown';
  const pillClass = {
    healthy: 'pill-success', warning: 'pill-warning',
    unhealthy: 'pill-critical', unknown: 'pill-neutral'
  }[status] || 'pill-neutral';
  const label = { healthy: '정상', warning: '경고', unhealthy: '위험', unknown: '정보 없음' }[status] || status;

  return `
    <div class="card system-mini">
      <span class="pill ${pillClass}"><span class="pill-dot pulse-dot"></span> ${label}</span>
      <div class="system-mini-text">헬스 ${passed}/${checks.length} · 이슈 ${issues.length}건</div>
    </div>
  `;
}

// ============ Main render ============
export function renderArena() {
  const container = $('#arena-content');
  if (!container) return;

  const rows = buildTeamRows();

  container.innerHTML = `
    ${renderKPI(rows)}
    ${renderH2H(rows)}
    ${renderRanking(rows)}
    ${renderStrategiesAccordion(rows)}
    ${renderHistorySection()}
    ${renderSystemMini()}
  `;

  bindAccordion();
}

// ============ Accordion event binding ============
function bindAccordion() {
  // 전략 accordion (Depth 1 → 2)
  $$('.acc-strat-head').forEach(head => {
    head.addEventListener('click', () => {
      head.closest('.acc-strat').classList.toggle('open');
    });
  });

  // 종목 accordion (Depth 2 → 3) — 같은 전략 내 한 번에 하나만
  $$('.sacc-head').forEach(head => {
    head.addEventListener('click', () => {
      const sacc = head.closest('.sacc');
      const wasOpen = sacc.classList.contains('open');
      const parent = sacc.closest('.acc-strat-body-inner');
      if (parent) {
        parent.querySelectorAll('.sacc.open').forEach(other => {
          if (other !== sacc) other.classList.remove('open');
        });
      }
      sacc.classList.toggle('open', !wasOpen);
    });
  });
}

// ============ Init / Refresh ============
export async function initArena() {
  await loadArenaData();
  renderArena();
}

export async function refreshArena() {
  await loadArenaData(true);
  renderArena();
}
