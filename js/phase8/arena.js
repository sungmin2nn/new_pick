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

  // 매매 이력: 최근 14일 시도 → 실제 존재하는 것만 (leaderboard 의존 X)
  const histDates = getRecentDates(14); // 오늘 → 14일 전 (내림차순)
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

function renderTeamsAccordion(rows) {
  // 5팀 순위 + 매매 이력 통합 (B안)
  const sorted = [...rows].sort((a, b) => b.today_pct - a.today_pct);

  const cards = sorted.map((t, i) => {
    const hist = state.history[t.tid] || [];
    const histDays = hist.length;
    const totalTrades = hist.reduce((s, h) => s + (h.summary?.simulation?.total_trades || 0), 0);
    const totalWins = hist.reduce((s, h) => s + (h.summary?.simulation?.wins || 0), 0);
    const winRate = totalTrades > 0 ? Math.round(totalWins / totalTrades * 100) : 0;

    const dayRows = hist.map(h => {
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

    const historyBody = histDays > 0 ? `
      <div class="detail-h">매매 이력 (${histDays}일 · ${totalTrades}건 · 승률 ${winRate}%)</div>
      ${dayRows}
    ` : `<div class="detail-h">매매 이력 없음</div>`;

    return `
      <div class="acc-strat" style="border-left-color:${t.color};">
        <div class="acc-strat-head">
          <span class="acc-chev">▶</span>
          <div class="team-medal-inline">${MEDALS[Math.min(i, 4)]}</div>
          <div class="acc-info">
            <div class="acc-name">${t.name}</div>
            <div class="acc-summary">${t.desc} · ELO ${t.elo}</div>
          </div>
          <div class="team-ret-block">
            <div class="ret ${colorClass(t.today_pct)}">${fmtPctSigned(t.today_pct)}</div>
            <div class="cum">누적 ${fmtPct(t.cum_pct)}</div>
          </div>
        </div>
        <div class="acc-strat-body">
          <div class="acc-strat-body-inner">
            <div class="team-detail-grid">
              <div class="mini-kpi">
                <div class="mini-kpi-label">잔고</div>
                <div class="mini-kpi-value">${fmtMoney(t.capital)}</div>
                <div class="mini-kpi-meta ${colorClass(t.cum_pct)}">${fmtPct(t.cum_pct)}</div>
              </div>
              <div class="mini-kpi">
                <div class="mini-kpi-label">매매</div>
                <div class="mini-kpi-value">${t.wins}/${t.trades}</div>
                <div class="mini-kpi-meta">승률 ${t.win_rate}%</div>
              </div>
            </div>
            ${historyBody}
          </div>
        </div>
      </div>
    `;
  }).join('');

  return `
    <div class="section">
      <div class="section-header">
        <h2 class="section-title display">🏆 5팀</h2>
        <span class="section-subtitle">순위 · 매매 이력</span>
      </div>
      <div class="acc-list">${cards}</div>
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

function renderCandidatesTable() {
  // 5전략 후보 통합 테이블 (전략 컬럼 포함)
  const allRows = [];
  for (const tid of TEAM_IDS) {
    const meta = TEAM_META[tid];
    const cands = state.candidates[meta.strategy];
    const candList = cands?.candidates || (Array.isArray(cands) ? cands : []) || [];
    for (const c of candList) {
      allRows.push({ ...c, _tid: tid, _team: meta.name, _color: meta.color });
    }
  }

  // 점수 내림차순 정렬
  allRows.sort((a, b) => (+b.score || 0) - (+a.score || 0));

  if (allRows.length === 0) {
    return `
      <div class="section">
        <div class="section-header">
          <h2 class="section-title display">📋 내일 후보</h2>
          <span class="section-subtitle">0종목</span>
        </div>
        <div class="empty"><div class="empty-icon">📭</div><div class="empty-text">후보 없음</div></div>
      </div>
    `;
  }

  const trs = allRows.map((c, i) => `
    <tr class="cand-row" data-idx="${i}">
      <td class="num right">${i + 1}</td>
      <td>
        <b>${c.name || '-'}</b>
        <div class="cand-code">${c.code || '-'}</div>
      </td>
      <td>
        <span class="team-pill" style="background:${c._color}15;color:${c._color};border-color:${c._color}40;">
          ${c._team.split(' ')[0]}
        </span>
      </td>
      <td class="num right">${(+c.score).toFixed(1)}</td>
      <td class="num right ${colorClass(c.change_pct)}">${fmtPctSigned(c.change_pct)}</td>
      <td class="num right">${fmtMoney(c.price)}</td>
    </tr>
    <tr class="cand-detail-row" data-idx="${i}" style="display:none;">
      <td colspan="6">${renderCandDetail(c)}</td>
    </tr>
  `).join('');

  return `
    <div class="section">
      <div class="section-header">
        <h2 class="section-title display">📋 내일 후보</h2>
        <span class="section-subtitle">5전략 · ${allRows.length}종목 (점수순)</span>
      </div>
      <div class="table-wrap">
        <table class="tbl cand-tbl">
          <thead>
            <tr>
              <th class="right">#</th>
              <th>종목</th>
              <th>전략</th>
              <th class="right">점수</th>
              <th class="right">등락률</th>
              <th class="right">가격</th>
            </tr>
          </thead>
          <tbody>${trs}</tbody>
        </table>
      </div>
    </div>
  `;
}

function renderCandDetail(c) {
  const sd = c.score_detail || {};
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
          <div class="mini-kpi-meta">${c._team}</div>
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
    ${renderCandidatesTable()}
    ${renderTeamsAccordion(rows)}
    ${renderSystemMini()}
  `;

  bindAccordion();
  bindCandidateTable();
}

function bindCandidateTable() {
  $$('.cand-row').forEach(row => {
    row.addEventListener('click', () => {
      const idx = row.dataset.idx;
      const detail = document.querySelector(`.cand-detail-row[data-idx="${idx}"]`);
      if (!detail) return;
      const isOpen = detail.style.display !== 'none';
      // 다른 펼침 닫기
      $$('.cand-detail-row').forEach(d => d.style.display = 'none');
      $$('.cand-row').forEach(r => r.classList.remove('open'));
      if (!isOpen) {
        detail.style.display = '';
        row.classList.add('open');
      }
    });
  });
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
