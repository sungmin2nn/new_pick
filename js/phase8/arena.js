/* Phase 8 - Arena Tab Renderer (Single Scroll + 3-Depth Accordion) */

import { fetchCached } from './cache.js';
import {
  fmtNum, fmtMoney, fmtPct, fmtPctSigned, fmtDate,
  colorClass, $, $$, getTodayKST, getRecentDates
} from './ui.js';

// ============ 지표 툴팁 설명 ============
const METRIC_TIPS = {
  '일일수익률': '오늘 하루 전체 팀 평균 수익률',
  '승률': '수익 매매 수 / 전체 매매 수 × 100',
  'MDD': '최대 낙폭 — 고점 대비 가장 많이 빠진 비율. 낮을수록 안정적',
  '손익비': '총 수익 / 총 손실. 1 이상이면 수익 > 손실',
  '샤프 비율': '위험 조정 수익률. 1 이상 양호, 2 이상 우수',
  '평균 보유': '매수~매도까지 평균 보유 시간',
  '최고 수익': '단일 매매 중 가장 높은 수익률',
  '최대 손실': '단일 매매 중 가장 큰 손실률',
  '실현 손익': '매도 완료된 매매의 확정 손익',
  '미실현 손익': '보유 중인 종목의 평가 손익 (미확정)',
  'ELO': '팀 간 경쟁 레이팅. 1000 기준, 높을수록 강팀',
  '총 매매': '전체 매매 건수',
  '연승': '최대 연속 수익 기록',
  '연패': '현재 연속 손실 횟수',
};

function tip(label) {
  const desc = METRIC_TIPS[label];
  if (!desc) return label;
  return `${label} <span class="metric-tip" onclick="event.stopPropagation();this.classList.toggle('show');" data-tip="${desc}">?</span>`;
}

// 기본 팀 (strategy_config.json 로드 전 폴백)
const DEFAULT_TEAM_META = {
  team_a: { name: 'Alpha Momentum', desc: 'MA5 + 거래량 급증', color: '#EF4444', strategy: 'momentum' },
  team_b: { name: 'Beta Contrarian', desc: '대형주 RSI 역추세', color: '#3B82F6', strategy: 'largecap_contrarian' },
  team_c: { name: 'Gamma Disclosure', desc: 'DART 호재 공시', color: '#10B981', strategy: 'dart_disclosure' },
  team_d: { name: 'Delta Theme', desc: '테마/정책 + 섹터', color: '#F59E0B', strategy: 'theme_policy' },
  team_e: { name: 'Echo Frontier', desc: '시초가 갭 + surge', color: '#8B5CF6', strategy: 'frontier_gap' },
};
const TEAM_COLORS = {
  team_a: '#EF4444', team_b: '#3B82F6', team_c: '#10B981', team_d: '#F59E0B', team_e: '#8B5CF6',
  team_f: '#EC4899', team_g: '#14B8A6', team_h: '#F97316', team_i: '#6366F1', team_j: '#84CC16',
  team_k: '#D946EF', team_l: '#0EA5E9', team_m: '#F43F5E', team_n: '#22D3EE', team_o: '#A855F7',
};

let TEAM_META = { ...DEFAULT_TEAM_META };
let strategyConfig = null;

async function loadStrategyConfig() {
  try {
    const config = await fetchCached('data/arena/strategy_config.json');
    if (!config || !config.strategies) return;
    strategyConfig = config;
    const dynamicMeta = {};
    for (const [sid, entry] of Object.entries(config.strategies)) {
      if (!entry.enabled || !entry.team_id) continue;
      dynamicMeta[entry.team_id] = {
        name: entry.team_name, desc: entry.description,
        color: TEAM_COLORS[entry.team_id] || '#6B7280', strategy: sid,
      };
    }
    if (Object.keys(dynamicMeta).length > 0) {
      TEAM_META = dynamicMeta;
      TEAM_IDS = Object.keys(TEAM_META);
    }
  } catch (e) { console.warn('[Arena] strategy_config 로드 실패', e); }
}

const MEDALS = ['🥇', '🥈', '🥉', '4', '5', '6', '7', '8', '9', '10', '11', '12', '13', '14', '15'];
const NAVER_STOCK_URL = 'https://m.stock.naver.com/domestic/stock/';

function stockLink(code, label) {
  if (!code) return label || '-';
  return `<a href="${NAVER_STOCK_URL}${code}" target="_blank" rel="noopener" class="trade-name-link" onclick="event.stopPropagation();">${label || code}</a>`;
}

function stockCodeLink(code) {
  if (!code) return '-';
  return `<a href="${NAVER_STOCK_URL}${code}" target="_blank" rel="noopener" class="cand-code-link" onclick="event.stopPropagation();">${code} ↗</a>`;
}

function stockDetailLink(code, name) {
  if (!code) return '';
  return `<a href="${NAVER_STOCK_URL}${code}" target="_blank" rel="noopener" class="stock-link" onclick="event.stopPropagation();"><span class="stock-link-icon">📊</span> ${name || code} 네이버 증권</a>`;
}
let TEAM_IDS = Object.keys(TEAM_META);
const DATA_BASE = 'data/arena';

let state = {
  leaderboard: null,
  portfolios: {},
  health: null,
  candidates: {},
  history: {}, // tid -> [{date, summary, trades}, ...] (최근 → 과거 순)
};

// ============ Data loading (parallel) ============
export async function loadArenaData(force = false) {
  // strategy_config.json 먼저 로드하여 동적 팀 설정
  await loadStrategyConfig();

  const today = getTodayKST();
  const histDates = getRecentDates(7); // 14 → 7일 축소
  const recentHealthDates = [today, ...getRecentDates(7).slice(1)];

  // 1) 모든 fetch 동시 발사 (Promise.all)
  const [
    leaderboard,
    portfolios,
    healthLogs,
    candidates,
    historyRaw,
  ] = await Promise.all([
    fetchCached(`${DATA_BASE}/leaderboard.json`, force),

    Promise.all(TEAM_IDS.map(tid =>
      fetchCached(`${DATA_BASE}/${tid}/portfolio.json`, force).then(d => [tid, d])
    )),

    // 헬스: 8일치 동시 fetch (첫 번째 non-null 사용)
    Promise.all(recentHealthDates.map(d =>
      fetchCached(`${DATA_BASE}/healthcheck/health_${d}.json`, force)
    )),

    // 후보: 최근 7일치 병렬 fetch → 가장 최근 non-null 사용
    Promise.all(TEAM_IDS.map(async tid => {
      const sid = TEAM_META[tid].strategy;
      const results = await Promise.all(
        histDates.map(d => fetchCached(`data/paper_trading/candidates_${d}_${sid}.json`, force).then(data => ({ date: d, data })))
      );
      const found = results.find(r => r.data);
      return [sid, found ? found.data : null];
    })),

    // 매매 이력: 5팀 × 7일 × 2파일 = 70개 동시 fetch
    Promise.all(TEAM_IDS.flatMap(tid =>
      histDates.flatMap(date => [
        fetchCached(`${DATA_BASE}/${tid}/daily/${date}/summary.json`, force).then(d => ({ tid, date, kind: 'summary', data: d })),
        fetchCached(`${DATA_BASE}/${tid}/daily/${date}/trades.json`, force).then(d => ({ tid, date, kind: 'trades', data: d })),
      ])
    )),
  ]);

  // 2) 결과 정리
  state.leaderboard = leaderboard;
  state.portfolios = Object.fromEntries(portfolios);
  state.candidates = Object.fromEntries(candidates);
  state.health = healthLogs.find(h => h !== null) || null;

  // 매매 이력 재구성: tid → date 별로 summary + trades 묶기
  const histMap = {};
  for (const tid of TEAM_IDS) histMap[tid] = {};
  for (const item of historyRaw) {
    if (!item.data) continue;
    if (!histMap[item.tid][item.date]) histMap[item.tid][item.date] = { date: item.date };
    histMap[item.tid][item.date][item.kind] = item.data;
  }
  // summary 있는 것만 push (최근 → 과거 정렬)
  state.history = {};
  for (const tid of TEAM_IDS) {
    state.history[tid] = Object.values(histMap[tid])
      .filter(h => h.summary)
      .sort((a, b) => b.date.localeCompare(a.date));
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
    const initCap = pf.initial_capital ?? strategyConfig?.strategies?.[meta.strategy]?.initial_capital ?? 10000000;
    return {
      tid, name: meta.name, desc: meta.desc, color: meta.color,
      today_pct: todayRank?.total_return ?? 0,
      cum_pct: pf.total_return_pct ?? 0,
      capital: pf.current_capital ?? initCap,
      initial_capital: initCap,
      elo: lbTeam.elo ?? 1000,
      wins: pf.total_wins ?? 0,
      trades: pf.total_trades ?? 0,
      win_rate: wr,
      max_drawdown_pct: pf.max_drawdown_pct ?? 0,
      max_win_streak: pf.max_win_streak ?? 0,
      loss_streak: pf.loss_streak ?? 0,
      win_streak: pf.win_streak ?? 0,
    };
  });
}

// ============ Helpers: MDD, Profit Factor, Sparkline ============
function calcMDD() {
  const history = state.leaderboard?.daily_history || [];
  if (history.length === 0) return 0;
  // 팀 평균 total_return per day
  const avgReturns = history.map(d => {
    const ranking = d.ranking || [];
    if (ranking.length === 0) return 0;
    return ranking.reduce((s, r) => s + (r.total_return || 0), 0) / ranking.length;
  });
  let peak = -Infinity, mdd = 0;
  for (const v of avgReturns) {
    if (v > peak) peak = v;
    const dd = peak - v;
    if (dd > mdd) mdd = dd;
  }
  return -mdd; // negative value
}

function calcProfitFactor() {
  let totalProfit = 0, totalLoss = 0;
  for (const tid of TEAM_IDS) {
    const hist = state.history[tid] || [];
    for (const h of hist) {
      const results = h.trades?.results || [];
      for (const t of results) {
        const amt = t.return_amount || 0;
        if (amt > 0) totalProfit += amt;
        else if (amt < 0) totalLoss += Math.abs(amt);
      }
    }
  }
  return totalLoss > 0 ? totalProfit / totalLoss : totalProfit > 0 ? Infinity : 0;
}

// ============ Sharpe Ratio ============
function calcSharpeRatio() {
  const history = state.leaderboard?.daily_history || [];
  if (history.length < 2) return 0;
  // 팀 평균 total_return per day → daily returns (차분)
  const avgReturns = history.map(d => {
    const ranking = d.ranking || [];
    if (ranking.length === 0) return 0;
    return ranking.reduce((s, r) => s + (r.total_return || 0), 0) / ranking.length;
  });
  const dailyReturns = avgReturns.map((v, i) => i === 0 ? v : v - avgReturns[i - 1]);
  if (dailyReturns.length < 2) return 0;
  const mean = dailyReturns.reduce((s, v) => s + v, 0) / dailyReturns.length;
  const variance = dailyReturns.reduce((s, v) => s + (v - mean) ** 2, 0) / (dailyReturns.length - 1);
  const std = Math.sqrt(variance);
  if (std === 0) return mean > 0 ? Infinity : 0;
  const riskFreeDaily = 3.5 / 250; // 3.5% 연 → 일
  return ((mean - riskFreeDaily) / std) * Math.sqrt(250);
}

// ============ 평균 보유기간 (분 단위) ============
function calcAvgHoldingMinutes() {
  let totalMin = 0, count = 0;
  for (const tid of TEAM_IDS) {
    const hist = state.history[tid] || [];
    for (const h of hist) {
      const results = h.trades?.results || [];
      for (const t of results) {
        const mins = getHoldingMinutes(t.entry_time, t.exit_time);
        if (mins > 0) { totalMin += mins; count++; }
      }
    }
  }
  return count > 0 ? totalMin / count : 0;
}

function getHoldingMinutes(entry_time, exit_time) {
  if (!entry_time || !exit_time) return 0;
  try {
    if (entry_time.length <= 5 && exit_time.length <= 5) {
      const [eh, em] = entry_time.split(':').map(Number);
      const [xh, xm] = exit_time.split(':').map(Number);
      const diff = (xh * 60 + xm) - (eh * 60 + em);
      return diff > 0 ? diff : 0;
    }
    const entryDate = new Date(entry_time);
    const exitDate = new Date(exit_time);
    const diffMs = exitDate - entryDate;
    return !isNaN(diffMs) && diffMs > 0 ? Math.floor(diffMs / 60000) : 0;
  } catch { return 0; }
}

function fmtHoldingMinutes(mins) {
  if (mins <= 0) return '-';
  const h = Math.floor(mins / 60);
  const m = Math.round(mins % 60);
  return h > 0 ? `${h}시간 ${m}분` : `${m}분`;
}

// ============ 최대 단일 수익/손실 ============
function calcMaxSingleReturn() {
  let maxReturn = -Infinity, minReturn = Infinity;
  for (const tid of TEAM_IDS) {
    const hist = state.history[tid] || [];
    for (const h of hist) {
      const results = h.trades?.results || [];
      for (const t of results) {
        const r = t.return_pct ?? 0;
        if (r > maxReturn) maxReturn = r;
        if (r < minReturn) minReturn = r;
      }
    }
  }
  return {
    best: maxReturn === -Infinity ? 0 : maxReturn,
    worst: minReturn === Infinity ? 0 : minReturn,
  };
}

// ============ 월별 수익률 ============
function calcMonthlyReturns() {
  const history = state.leaderboard?.daily_history || [];
  if (history.length === 0) return [];
  // 팀 평균 total_return per day → daily returns
  const avgReturns = history.map(d => {
    const ranking = d.ranking || [];
    if (ranking.length === 0) return 0;
    return ranking.reduce((s, r) => s + (r.total_return || 0), 0) / ranking.length;
  });
  const dailyReturns = avgReturns.map((v, i) => i === 0 ? v : v - avgReturns[i - 1]);

  // 월별 그룹핑
  const monthMap = {};
  history.forEach((d, i) => {
    const dateStr = d.date || '';
    if (dateStr.length < 6) return;
    const monthKey = dateStr.slice(0, 6); // YYYYMM
    if (!monthMap[monthKey]) monthMap[monthKey] = 0;
    monthMap[monthKey] += dailyReturns[i] || 0;
  });

  return Object.entries(monthMap)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([key, ret]) => ({
      label: `${key.slice(0, 4)}.${key.slice(4, 6)}`,
      return_pct: ret,
    }));
}

function calcRealizedPnL() {
  let total = 0;
  for (const tid of TEAM_IDS) {
    const hist = state.history[tid] || [];
    for (const h of hist) {
      const results = h.trades?.results || [];
      for (const t of results) {
        total += t.return_amount || 0;
      }
    }
  }
  return total;
}

function calcUnrealizedPnL() {
  // portfolios don't have open positions in current data model
  // Unrealized = (current_capital - initial_capital) - realized
  const totalCapital = TEAM_IDS.reduce((s, tid) => {
    const pf = state.portfolios[tid] || {};
    return s + (pf.current_capital ?? pf.initial_capital ?? 10000000);
  }, 0);
  const totalInitial = TEAM_IDS.reduce((s, tid) => {
    const pf = state.portfolios[tid] || {};
    const meta = TEAM_META[tid];
    return s + (pf.initial_capital ?? strategyConfig?.strategies?.[meta.strategy]?.initial_capital ?? 10000000);
  }, 0);
  const totalPnL = totalCapital - totalInitial;
  const realized = calcRealizedPnL();
  return totalPnL - realized;
}

function buildSparklineSVG(values, width = 120, height = 32) {
  if (!values || values.length < 2) return '';
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const step = width / (values.length - 1);
  const points = values.map((v, i) => `${(i * step).toFixed(1)},${(height - ((v - min) / range) * (height - 4) - 2).toFixed(1)}`).join(' ');
  const last = values[values.length - 1];
  const colorCls = last >= (values[0] || 0) ? 'sparkline-up' : 'sparkline-down';
  return `<svg class="sparkline hero-sparkline ${colorCls}" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none">
    <polyline fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" points="${points}"/>
  </svg>`;
}

// ============ Sections ============
function renderKPI(rows) {
  const dailyAvg = rows.reduce((s, t) => s + t.today_pct, 0) / Math.max(rows.length, 1);
  const totalCapital = rows.reduce((s, t) => s + t.capital, 0);
  const totalInitial = rows.reduce((s, t) => s + t.initial_capital, 0);
  const totalCum = totalInitial > 0 ? ((totalCapital - totalInitial) / totalInitial) * 100 : 0;
  const dayN = state.leaderboard?.daily_history?.length ?? 0;
  const totalTrades = rows.reduce((s, t) => s + t.trades, 0);
  const totalWins = rows.reduce((s, t) => s + t.wins, 0);
  const winRate = totalTrades > 0 ? Math.round(totalWins / totalTrades * 100) : 0;
  const mdd = calcMDD();
  const pf = calcProfitFactor();

  // Sparkline: equity curve from daily_history (avg total_return)
  const history = state.leaderboard?.daily_history || [];
  const equityValues = history.map(d => {
    const ranking = d.ranking || [];
    if (ranking.length === 0) return 0;
    return ranking.reduce((s, r) => s + (r.total_return || 0), 0) / ranking.length;
  });

  // Realized / Unrealized P&L
  const realizedPnL = calcRealizedPnL();
  const unrealizedPnL = calcUnrealizedPnL();
  const totalPnL = totalCapital - totalInitial;
  const realizedPct = totalInitial > 0 ? (realizedPnL / totalInitial) * 100 : 0;
  const unrealizedPct = totalInitial > 0 ? (unrealizedPnL / totalInitial) * 100 : 0;

  return `
    <div class="section">
      <div class="hero-kpi">
        <div class="hero-kpi-main">
          <div class="hero-kpi-label">총 자산 <span class="hero-day-badge">Day ${dayN}</span></div>
          <div class="hero-kpi-value">${fmtMoney(totalCapital)}</div>
          <div class="hero-kpi-return ${colorClass(totalCum)}">
            ${fmtPctSigned(totalCum)}
            <span class="hero-kpi-amount">(${totalPnL >= 0 ? '+' : ''}${fmtMoney(totalPnL)})</span>
          </div>
          <div class="hero-sparkline-wrap">${buildSparklineSVG(equityValues)}</div>
        </div>
        <div class="hero-sub-row">
          <div class="hero-sub-kpi">
            <div class="hero-sub-label">${tip('일일수익률')}</div>
            <div class="hero-sub-value ${colorClass(dailyAvg)}">${fmtPctSigned(dailyAvg)}</div>
          </div>
          <div class="hero-sub-kpi">
            <div class="hero-sub-label">${tip('승률')}</div>
            <div class="hero-sub-value">${winRate}%</div>
          </div>
          <div class="hero-sub-kpi">
            <div class="hero-sub-label">${tip('MDD')}</div>
            <div class="hero-sub-value down">${mdd.toFixed(1)}%</div>
          </div>
          <div class="hero-sub-kpi">
            <div class="hero-sub-label">${tip('손익비')}</div>
            <div class="hero-sub-value">${pf === Infinity ? '∞' : pf.toFixed(2)}</div>
          </div>
        </div>
      </div>
      <div class="pnl-split-row">
        <div class="pnl-split-item">
          <div class="pnl-split-label">${tip('실현 손익')}</div>
          <div class="pnl-split-value ${colorClass(realizedPnL)}">${realizedPnL >= 0 ? '+' : ''}${fmtMoney(realizedPnL)}</div>
          <div class="pnl-split-pct ${colorClass(realizedPct)}">${fmtPctSigned(realizedPct)}</div>
        </div>
        <div class="pnl-split-divider"></div>
        <div class="pnl-split-item">
          <div class="pnl-split-label">${tip('미실현 손익')}</div>
          <div class="pnl-split-value ${colorClass(unrealizedPnL)}">${unrealizedPnL >= 0 ? '+' : ''}${fmtMoney(unrealizedPnL)}</div>
          <div class="pnl-split-pct ${colorClass(unrealizedPct)}">${fmtPctSigned(unrealizedPct)}</div>
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
            ${t.trades === 0 && t.today_pct === 0
              ? '<div class="ret neutral" style="font-size:12px;color:var(--text-tertiary);">시그널 대기</div>'
              : `<div class="ret ${colorClass(t.today_pct)}">${fmtPctSigned(t.today_pct)}</div>`}
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
              <div class="mini-kpi">
                <div class="mini-kpi-label">MDD</div>
                <div class="mini-kpi-value down">${t.max_drawdown_pct === 0 ? '0.0' : (-Math.abs(t.max_drawdown_pct)).toFixed(1)}%</div>
              </div>
              <div class="mini-kpi">
                <div class="mini-kpi-label">연승 / 연패</div>
                <div class="mini-kpi-value"><span class="up">${t.max_win_streak}</span> / <span class="down">${t.loss_streak}</span></div>
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
        <h2 class="section-title display">🏆 ${sorted.length}팀</h2>
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
  // 5전략 후보 카드 리스트
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

  // 전략별 그룹핑
  const teamGroups = {};
  for (const c of allRows) {
    const key = c._tid;
    if (!teamGroups[key]) teamGroups[key] = { name: c._team, color: c._color, items: [] };
    teamGroups[key].items.push(c);
  }

  // 전략 필터 탭
  const teamTabs = Object.entries(teamGroups).map(([tid, g]) =>
    `<button class="cand-filter-tab" data-filter="${tid}" style="border-color:${g.color}40;color:${g.color};">${g.name.split(' ')[0]} <span class="cand-filter-count">${g.items.length}</span></button>`
  ).join('');

  const renderCard = (c, i) => {
    const scoreW = Math.min(100, Math.max(0, (+c.score || 0) / 135 * 100)).toFixed(0);
    return `
      <div class="stock-card" data-idx="${i}" data-team="${c._tid}">
        <div class="stock-card-body">
          <div class="stock-card-left">
            <div class="stock-card-name">${stockLink(c.code, c.name || '-')} <span class="stock-card-code">${stockCodeLink(c.code)}</span></div>
            <div class="stock-card-strategy"><span class="team-pill" style="background:${c._color}15;color:${c._color};border-color:${c._color}40;">${c._team.split(' ')[0]}</span></div>
          </div>
          <div class="stock-card-right">
            <div class="stock-card-price">${fmtMoney(c.price)}</div>
            <div class="stock-card-change ${colorClass(c.change_pct)}">${fmtPctSigned(c.change_pct)}</div>
          </div>
        </div>
        <div class="stock-card-score">
          <div class="score-gauge" style="width:${scoreW}%;">${(+c.score).toFixed(1)}</div>
        </div>
      </div>
      <div class="stock-card-detail" data-idx="${i}" style="display:none;">
        ${renderCandDetail(c)}
      </div>`;
  };

  const cards = allRows.map((c, i) => renderCard(c, i)).join('');
  const DEFAULT_SHOW = 10;

  return `
    <div class="section">
      <div class="section-header">
        <h2 class="section-title display">📋 내일 후보</h2>
        <span class="section-subtitle">${Object.keys(teamGroups).length}전략 · ${allRows.length}종목</span>
      </div>
      <div class="cand-filter-bar" style="display:flex;gap:6px;overflow-x:auto;padding:0 0 var(--space-2);-webkit-overflow-scrolling:touch;">
        <button class="cand-filter-tab active" data-filter="all">전체 <span class="cand-filter-count">${allRows.length}</span></button>
        ${teamTabs}
      </div>
      <div class="stock-card-list" id="candCardList">${cards}</div>
      ${allRows.length > DEFAULT_SHOW ? `<button class="cand-show-more" id="candShowMore" style="display:block;width:100%;padding:var(--space-3);border:1px solid var(--border-default);border-radius:var(--radius-md);background:transparent;color:var(--text-secondary);font-size:var(--fs-sm);font-weight:600;cursor:pointer;margin-top:var(--space-2);">더보기 (${allRows.length - DEFAULT_SHOW}개)</button>` : ''}
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
      <div style="margin-bottom:var(--space-3);">${stockDetailLink(c.code, c.name)}</div>
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

function calcHoldingPeriod(entry_time, exit_time) {
  if (!entry_time || !exit_time) return '당일';
  // format: "HH:MM" or "YYYY-MM-DD HH:MM"
  try {
    // Simple HH:MM format (same day)
    if (entry_time.length <= 5 && exit_time.length <= 5) {
      const [eh, em] = entry_time.split(':').map(Number);
      const [xh, xm] = exit_time.split(':').map(Number);
      const diffMin = (xh * 60 + xm) - (eh * 60 + em);
      if (diffMin <= 0) return '당일';
      const h = Math.floor(diffMin / 60);
      const m = diffMin % 60;
      return h > 0 ? `${h}시간 ${m}분` : `${m}분`;
    }
    // Full datetime format
    const entryDate = new Date(entry_time);
    const exitDate = new Date(exit_time);
    const diffMs = exitDate - entryDate;
    if (isNaN(diffMs) || diffMs <= 0) return '당일';
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
    const diffHours = Math.floor((diffMs % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
    if (diffDays > 0) return `${diffDays}일 ${diffHours}시간`;
    const diffMin = Math.floor(diffMs / (1000 * 60));
    const h = Math.floor(diffMin / 60);
    const m = diffMin % 60;
    return h > 0 ? `${h}시간 ${m}분` : `${m}분`;
  } catch {
    return '당일';
  }
}

function renderTradeDetail(results, summary) {
  if (!results || results.length === 0) {
    return `<div class="sacc-detail"><div class="detail-h">매매 결과 없음</div></div>`;
  }
  const sim = summary?.simulation || {};
  const rows = results.map(t => {
    const cls = colorClass(t.return_pct);
    const holdingPeriod = calcHoldingPeriod(t.entry_time, t.exit_time);
    return `
      <div class="trade-row">
        <div class="trade-name">
          <b>${stockLink(t.code, t.name || '-')}</b>
          <div class="trade-code">${stockCodeLink(t.code)}</div>
        </div>
        <div class="trade-prices">
          <div class="num">${fmtMoney(t.entry_price)} → ${fmtMoney(t.exit_price)}</div>
          <div class="trade-meta">${t.exit_reason || ''} · ${t.quantity || 0}주 · <span class="trade-holding">⏱ ${holdingPeriod}</span></div>
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

// ============ Strategy KPI Row (MDD, Profit Factor, Benchmark) ============
export function renderStrategyKPIRow() {
  const mdd = calcMDD();
  const pf = calcProfitFactor();
  const sharpe = calcSharpeRatio();
  const avgHold = calcAvgHoldingMinutes();
  const singleRet = calcMaxSingleReturn();
  let totalTrades = 0, totalWins = 0;
  for (const tid of TEAM_IDS) {
    const hist = state.history[tid] || [];
    for (const h of hist) {
      totalTrades += h.summary?.simulation?.total_trades || 0;
      totalWins += h.summary?.simulation?.wins || 0;
    }
  }
  const winRate = totalTrades > 0 ? (totalWins / totalTrades * 100).toFixed(1) : '0.0';
  const sharpeStr = sharpe === Infinity ? '∞' : sharpe.toFixed(2);
  const sharpeClass = sharpe >= 1 ? 'up' : sharpe >= 0 ? '' : 'down';

  return `
    <div class="section">
      <div class="section-header">
        <h2 class="section-title display">📊 성과 지표</h2>
      </div>
      <div class="strategy-kpi-row">
        <div class="strategy-kpi-item">
          <div class="strategy-kpi-label">${tip('MDD')}</div>
          <div class="strategy-kpi-value down">${mdd.toFixed(1)}%</div>
        </div>
        <div class="strategy-kpi-item">
          <div class="strategy-kpi-label">${tip('손익비')}</div>
          <div class="strategy-kpi-value">${pf === Infinity ? '∞' : pf.toFixed(2)}</div>
        </div>
        <div class="strategy-kpi-item">
          <div class="strategy-kpi-label">${tip('총 매매')}</div>
          <div class="strategy-kpi-value">${totalTrades}건</div>
        </div>
        <div class="strategy-kpi-item">
          <div class="strategy-kpi-label">${tip('승률')}</div>
          <div class="strategy-kpi-value">${winRate}%</div>
        </div>
        <div class="strategy-kpi-item">
          <div class="strategy-kpi-label">${tip('샤프 비율')}</div>
          <div class="strategy-kpi-value ${sharpeClass}">${sharpeStr}</div>
        </div>
        <div class="strategy-kpi-item">
          <div class="strategy-kpi-label">${tip('평균 보유')}</div>
          <div class="strategy-kpi-value">${fmtHoldingMinutes(avgHold)}</div>
        </div>
        <div class="strategy-kpi-item">
          <div class="strategy-kpi-label">${tip('최고 수익')}</div>
          <div class="strategy-kpi-value up">${singleRet.best > 0 ? '+' : ''}${singleRet.best.toFixed(2)}%</div>
        </div>
        <div class="strategy-kpi-item">
          <div class="strategy-kpi-label">${tip('최대 손실')}</div>
          <div class="strategy-kpi-value down">${singleRet.worst.toFixed(2)}%</div>
        </div>
      </div>
    </div>
  `;
}

// ============ 월별 수익률 테이블 ============
export function renderMonthlyReturnsTable() {
  const monthly = calcMonthlyReturns();
  if (monthly.length === 0) {
    return `
      <div class="section">
        <div class="section-header">
          <h2 class="section-title display">📅 월별 수익률</h2>
        </div>
        <div class="empty"><div class="empty-icon">📭</div><div class="empty-text">데이터 없음</div></div>
      </div>`;
  }
  const cells = monthly.map(m => {
    const cls = m.return_pct >= 0 ? 'monthly-cell-up' : 'monthly-cell-down';
    return `<div class="monthly-cell ${cls}">
      <div class="monthly-cell-label">${m.label}</div>
      <div class="monthly-cell-value">${m.return_pct >= 0 ? '+' : ''}${m.return_pct.toFixed(2)}%</div>
    </div>`;
  }).join('');

  return `
    <div class="section">
      <div class="section-header">
        <h2 class="section-title display">📅 월별 수익률</h2>
      </div>
      <div class="monthly-grid">${cells}</div>
    </div>`;
}

export function renderStrategyPanel() {
  if (!strategyConfig || !strategyConfig.strategies) return '';
  const all = Object.entries(strategyConfig.strategies);
  const enabled = all.filter(([, e]) => e.enabled);

  const riskLabel = { low: '낮음', medium: '보통', high: '높음' };
  const riskPill = { low: 'pill-success', medium: 'pill-warning', high: 'pill-critical' };

  const cards = all.map(([sid, entry]) => {
    const on = entry.enabled;
    const src = entry.source === 'lab' ? 'Lab' : 'NTB';
    const srcCls = entry.source === 'lab' ? 'accent' : 'neutral';
    const teamColor = entry.team_id ? (TEAM_COLORS[entry.team_id] || '#6B7280') : '#9CA3AF';
    const activatedStr = entry.activated_at || '-';
    const capitalStr = entry.initial_capital ? (entry.initial_capital / 10000).toLocaleString() + '만' : '-';

    return `
      <div class="acc-strat" style="border-left-color:${teamColor};${on ? '' : 'opacity:0.6;'}">
        <div class="acc-strat-head">
          <span class="acc-chev">▶</span>
          <span style="width:10px;height:10px;border-radius:50%;background:${on ? 'var(--success)' : 'var(--text-disabled)'};flex-shrink:0;"></span>
          <div class="acc-info">
            <div class="acc-name">${entry.emoji || ''} ${entry.team_name || sid}</div>
            <div class="acc-summary">${entry.description || ''}</div>
          </div>
          <span class="team-pill" style="background:var(--${srcCls}-bg);color:var(--${srcCls === 'accent' ? 'accent-deep' : 'text-tertiary'});font-size:10px;padding:1px 6px;">${src}</span>
        </div>
        <div class="acc-strat-body">
          <div class="acc-strat-body-inner">
            <div class="detail-row"><span>카테고리</span><span class="pill pill-neutral" style="font-size:11px;">${entry.category || '-'}</span></div>
            <div class="detail-row"><span>리스크</span><span class="pill ${riskPill[entry.risk_level] || 'pill-neutral'}" style="font-size:11px;">${riskLabel[entry.risk_level] || entry.risk_level || '-'}</span></div>
            <div class="detail-row"><span>출처</span><span>${src}</span></div>
            <div class="detail-row"><span>활성화</span><span>${on ? '✅ ON' : '⬜ OFF'}</span></div>
            <div class="detail-row"><span>활성화 날짜</span><span class="num">${activatedStr}</span></div>
            <div class="detail-row"><span>초기 자본</span><span class="num">${capitalStr}</span></div>
            <div class="detail-row"><span>Top N</span><span class="num">${entry.top_n ?? '-'}</span></div>
            <div class="detail-row"><span>배정 팀</span><span>${entry.team_id || '미배정'}</span></div>
          </div>
        </div>
      </div>
    `;
  }).join('');

  return `
    <div class="section">
      <div class="section-header">
        <h2 class="section-title display">🧪 전략 Lab</h2>
        <span class="section-subtitle">${enabled.length}/${all.length} 활성</span>
      </div>
      <div class="acc-list">${cards}</div>
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

  try {
    const rows = buildTeamRows();
    container.innerHTML = `
      ${renderKPI(rows)}
      ${renderCandidatesTable()}
      ${renderTeamsAccordion(rows)}
      ${renderSystemMini()}
    `;
    bindAccordion();
    bindCandidateTable();
  } catch (e) {
    console.error('[Arena] 렌더링 오류:', e);
    container.innerHTML = `
      <div class="empty">
        <div class="empty-icon">⚠️</div>
        <div class="empty-text">대시보드 렌더링 중 오류가 발생했습니다</div>
        <div style="font-size:11px;color:var(--text-tertiary);margin-top:8px;">${e.message}</div>
      </div>`;
  }
}

function bindCandidateTable() {
  const DEFAULT_SHOW = 10;
  let currentFilter = 'all';
  let showAll = false;

  function applyFilter() {
    const cards = $$('.stock-card');
    const details = $$('.stock-card-detail');
    let visibleCount = 0;

    cards.forEach((card, i) => {
      const team = card.dataset.team;
      const matchFilter = currentFilter === 'all' || team === currentFilter;
      const withinLimit = showAll || visibleCount < DEFAULT_SHOW;

      if (matchFilter && withinLimit) {
        card.style.display = '';
        visibleCount++;
      } else {
        card.style.display = 'none';
      }
      // 상세도 숨기기
      if (details[i]) details[i].style.display = 'none';
      card.classList.remove('open');
    });

    // 더보기 버튼
    const moreBtn = $('#candShowMore');
    if (moreBtn) {
      const totalMatch = [...cards].filter(c => currentFilter === 'all' || c.dataset.team === currentFilter).length;
      if (showAll || totalMatch <= DEFAULT_SHOW) {
        moreBtn.style.display = 'none';
      } else {
        moreBtn.style.display = 'block';
        moreBtn.textContent = `더보기 (${totalMatch - DEFAULT_SHOW}개)`;
      }
    }
  }

  // 필터 탭 클릭
  $$('.cand-filter-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      $$('.cand-filter-tab').forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      currentFilter = tab.dataset.filter;
      showAll = false;
      applyFilter();
    });
  });

  // 더보기 버튼
  const moreBtn = $('#candShowMore');
  if (moreBtn) {
    moreBtn.addEventListener('click', () => {
      showAll = true;
      applyFilter();
    });
  }

  // 카드 클릭 → 상세 펼침
  $$('.stock-card').forEach(card => {
    card.addEventListener('click', (e) => {
      if (e.target.closest('a')) return; // 링크 클릭은 패스
      const idx = card.dataset.idx;
      const detail = document.querySelector(`.stock-card-detail[data-idx="${idx}"]`);
      if (!detail) return;
      const isOpen = detail.style.display !== 'none';
      $$('.stock-card-detail').forEach(d => d.style.display = 'none');
      $$('.stock-card').forEach(c => c.classList.remove('open'));
      if (!isOpen) {
        detail.style.display = '';
        card.classList.add('open');
      }
    });
  });

  // 초기 적용 (상위 10개만)
  applyFilter();
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
  try {
    await loadArenaData();
    renderArena();
  } catch (e) {
    console.error('[Arena] 초기화 실패:', e);
    const c = $('#arena-content');
    if (c) c.innerHTML = '<div class="empty"><div class="empty-icon">⚠️</div><div class="empty-text">데이터를 불러오지 못했습니다</div></div>';
  }
}

export async function refreshArena() {
  const btn = document.getElementById('refresh-btn');
  if (btn) { btn.textContent = '⟳'; btn.classList.add('spinning'); }
  try {
    await loadArenaData(true);
    renderArena();
  } catch (e) {
    console.error('[Arena] 새로고침 실패:', e);
  } finally {
    if (btn) { btn.textContent = '↻'; btn.classList.remove('spinning'); }
  }
}
