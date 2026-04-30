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
  // 헬스: 배열이면 마지막 항목 사용 (날짜별 누적 구조)
  const rawHealth = healthLogs.find(h => h !== null) || null;
  if (Array.isArray(rawHealth) && rawHealth.length > 0) {
    state.health = rawHealth[rawHealth.length - 1];
  } else {
    state.health = rawHealth;
  }

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
          <div class="hero-kpi-label">누적 손익 (원금 제외) <span class="hero-day-badge">Day ${dayN}</span></div>
          <div class="hero-kpi-value ${colorClass(totalPnL)}">${totalPnL >= 0 ? '+' : ''}${fmtMoney(totalPnL)}</div>
          <div class="hero-kpi-return ${colorClass(totalCum)}">
            ${fmtPctSigned(totalCum)}
            <span class="hero-kpi-amount">평가자산 ${fmtMoney(totalCapital)}</span>
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

  const DEFAULT_SHOW = 10;

  const trs = allRows.map((c, i) => {
    const scoreW = Math.min(100, Math.max(0, (+c.score || 0) / 135 * 100)).toFixed(0);
    return `
      <tr class="cand-row" data-idx="${i}" data-team="${c._tid}" data-score="${c.score||0}" data-change="${c.change_pct||0}" data-price="${c.price||0}">
        <td class="num right">${i + 1}</td>
        <td>
          <b>${stockLink(c.code, c.name || '-')}</b>
          <div class="cand-code">${stockCodeLink(c.code)}</div>
        </td>
        <td><span class="team-pill" style="background:${c._color}15;color:${c._color};border-color:${c._color}40;">${c._team.split(' ')[0]}</span></td>
        <td class="num right">
          <div class="score-gauge-inline" style="width:${scoreW}%;">${(+c.score).toFixed(1)}</div>
        </td>
        <td class="num right ${colorClass(c.change_pct)}">${fmtPctSigned(c.change_pct)}</td>
        <td class="num right">${fmtMoney(c.price)}</td>
      </tr>
      <tr class="cand-detail-row" data-idx="${i}" style="display:none;">
        <td colspan="6">${renderCandDetail(c)}</td>
      </tr>`;
  }).join('');

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
      <div class="table-wrap">
        <table class="tbl cand-tbl" id="candTable">
          <thead>
            <tr>
              <th class="right cand-sort" data-sort="idx">#</th>
              <th class="cand-sort" data-sort="name">종목</th>
              <th class="cand-sort" data-sort="team">전략</th>
              <th class="right cand-sort" data-sort="score">점수 ▼</th>
              <th class="right cand-sort" data-sort="change">등락률</th>
              <th class="right cand-sort" data-sort="price">가격</th>
            </tr>
          </thead>
          <tbody id="candBody">${trs}</tbody>
        </table>
      </div>
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

// exit_type → 한국어 라벨 매핑. exit_reason 우선, 없으면 exit_type 매핑.
const EXIT_TYPE_LABEL = { profit: '익절', loss: '손절', close: '종가청산', trailing: '트레일링' };
function exitLabel(t) {
  if (t && t.exit_reason) return t.exit_reason;
  if (t && t.exit_type) return EXIT_TYPE_LABEL[t.exit_type] || t.exit_type;
  return '';
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
          <div class="trade-meta">${exitLabel(t)} · ${t.quantity || 0}주 · <span class="trade-holding">⏱ ${holdingPeriod}</span></div>
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

// 전략별 규칙 설명
const STRATEGY_RULES = {
  momentum: {
    name: 'Alpha Momentum',
    summary: '주가가 상승 추세에 있고 거래량이 폭발적으로 증가한 종목을 찾습니다. 5일 이동평균선 위에서 거래량이 평소 3배 이상 터지면, 시장의 관심이 집중되며 추가 상승할 가능성이 높다는 논리입니다.',
    signal: 'MA5 위 + 거래량 5일평균 3배 급증',
    entry: '시초가 매수 (09:00~09:05)',
    exit_profit: '+5% 익절',
    exit_loss: '-2% 손절',
    exit_deadline: '14:30 강제 청산',
    filter: '가격 ≥3,000원 / 거래대금 ≥30억 / 등락률 +3~15%',
    scoring: '등락률(35) + 거래대금(30) + 거래량급증(20) + 가격대(15) = 100점',
  },
  largecap_contrarian: {
    name: 'Beta Contrarian',
    summary: '대형주(시총 1조 이상)가 과도하게 하락했을 때 반등을 노리는 역발상 전략입니다. RSI 지표가 35 이하로 떨어지면 "팔 사람은 다 팔았다"는 신호이며, 대형주는 쉽게 망하지 않으므로 반등 확률이 높습니다.',
    signal: 'RSI(14) ≤ 35 과매도 + 대형주',
    entry: '시초가 매수',
    exit_profit: '+5% 익절',
    exit_loss: '-2% 손절',
    exit_deadline: '14:30 강제 청산',
    filter: '시총 ≥1조 / 거래대금 ≥50억 / 하락률 -1.5% 이상 / KOSPI -2% 시 진입 차단',
    scoring: '시총(30) + 하락폭(25) + 거래대금(20) + 가격대(15) + 변동성(10) = 100점',
  },
  dart_disclosure: {
    name: 'Gamma Disclosure',
    summary: '전날 저녁~당일 아침 사이에 DART(전자공시)에 올라온 호재성 공시를 빠르게 포착합니다. 좋은 공시(실적 개선, 대규모 계약 등)가 나오면 장 시작과 함께 주가가 반응하는데, 이 타이밍을 잡습니다.',
    signal: 'DART 호재 공시 (전일 18시~당일 08:30)',
    entry: '시초가 매수',
    exit_profit: '+5% 익절',
    exit_loss: '-2% 손절',
    exit_deadline: '14:30 강제 청산',
    filter: '시총 1,000억~10조 / 거래대금 ≥10억',
    scoring: '공시점수(40) + 등락률(25) + 거래대금(20) + 시총(15) = 100점',
  },
  theme_policy: {
    name: 'Delta Theme',
    summary: '그날 시장에서 가장 뜨거운 테마(예: AI, 방산, 2차전지)의 선도주를 매매합니다. 네이버 금융에서 실시간 급상승 테마를 감지하고, 해당 테마를 이끄는 대장주에 올라탑니다.',
    signal: '네이버 실시간 급상승 테마 TOP10 관련주',
    entry: '시초가 매수',
    exit_profit: '+5% 익절',
    exit_loss: '-2% 손절',
    exit_deadline: '14:30 강제 청산',
    filter: '테마 등락률 >0.5% / 활성 테마 종목',
    scoring: '테마관련도(40) + 등락률(25) + 거래대금(20) + 테마강도(15) = 100점',
  },
  frontier_gap: {
    name: 'Echo Frontier',
    summary: '장 시작 시 전일 종가보다 2~5% 높게 시작하는 종목(갭 상승)을 매수합니다. 갭 상승은 밤사이 호재가 있었다는 의미이고, 장 시작 30분이 거래대금의 38%가 집중되는 "골든타임"이라 추가 상승을 기대합니다.',
    signal: '시초가 갭 +2~5% + 거래량 5일평균 2배',
    entry: '시초가 매수 (골든타임 09:00~09:30)',
    exit_profit: '+5% 익절',
    exit_loss: '-2% 손절',
    exit_deadline: '14:30 강제 청산',
    filter: '가격 ≥3,000원 / 거래대금 ≥50억 / 갭 5% 초과 제외 (exhaustion)',
    scoring: '갭크기(40) + 거래량배수(35) + 거래대금(15) + 가격대(10) = 100점',
  },
  hybrid_alpha_delta: {
    name: 'Alpha-Delta Hybrid',
    summary: '모멘텀(Alpha)과 테마(Delta) 두 전략의 점수를 합산하여, 상승 추세와 시장 테마를 동시에 만족하는 종목만 선별합니다. 한 가지 기준보다 두 가지를 동시에 충족하면 신뢰도가 높아집니다.',
    signal: '모멘텀 + 테마 전략의 가중평균 조합',
    entry: '시초가 매수',
    exit_profit: '+5% 익절',
    exit_loss: '-2% 손절',
    exit_deadline: '14:30 강제 청산',
    filter: '두 전략 모두 통과한 종목 우선',
    scoring: '모멘텀점수(50%) + 테마점수(50%) 가중평균',
  },
  volatility_breakout_lw: {
    name: 'Zeta Volatility',
    summary: '전설적 트레이더 래리 윌리엄스의 변동성 돌파 전략입니다. 전일 고가-저가 변동폭의 절반만큼 시초가에서 상승하면 "오늘은 상승하는 날"이라 판단하고 매수합니다.',
    signal: '전일 변동폭 × K(0.5) 돌파 + 거래량 1.5배',
    entry: '시초가 매수',
    exit_profit: '+5% 익절',
    exit_loss: '-2% 손절',
    exit_deadline: '14:30 강제 청산',
    filter: '시총 ≥500억 / 거래대금 ≥50억',
    scoring: '돌파강도(45) + 거래량폭발(30) + 거래대금(15) + 가격대(10) = 100점',
  },
  turtle_breakout_short: {
    name: 'Kappa Turtle',
    summary: '최근 5일간 최고가를 돌파한 종목을 매수합니다. 신고가 돌파는 저항선이 깨졌다는 의미로, 새로운 상승 추세의 시작 신호입니다. 거래량이 1.5배 이상 동반되면 돌파의 신뢰도가 높아집니다.',
    signal: '5일 신고가 돌파 + 거래량 1.5배 동반',
    entry: '시초가 매수',
    exit_profit: '+5% 익절',
    exit_loss: '-2% 손절',
    exit_deadline: '14:30 강제 청산',
    filter: '양봉 ≥1.0% / 시총 ≥1,000억 / 거래대금 ≥50억',
    scoring: '신고가갱신강도(35) + 거래량폭발(30) + 거래대금(20) + 모멘텀(15) = 100점',
  },
  sector_rotation: {
    name: 'Theta Sector',
    summary: '그날 가장 강하게 오르는 업종(섹터)을 찾고, 그 업종의 대장주를 매수합니다. 업종이 오를 때 대장주가 가장 많이 오르는 경향이 있어, "강한 업종의 1등"을 타는 전략입니다.',
    signal: 'KOSPI 강세 업종 TOP5 → 시총 상위 대장주',
    entry: '시초가 매수',
    exit_profit: '+5% 익절',
    exit_loss: '-2% 손절',
    exit_deadline: '14:30 강제 청산',
    filter: 'KOSPI 종목만 / 등락률 ≥0.5% / 시총 ≥1,000억',
    scoring: '섹터강세(35) + 종목모멘텀(30) + 시총순위(20) + 거래량(15) = 100점',
  },
  eod_reversal_korean: {
    name: 'Eta Reversal',
    summary: '장중에 -3~8% 크게 하락했지만 저점에서 30% 이상 회복한 종목을 매수합니다. 하루 크게 빠졌다 반등하는 것은 매도 압력이 소진되었다는 신호이며, 다음날 추가 반등을 기대합니다.',
    signal: '당일 -3~8% 하락 + 저점 30% 회복',
    entry: '종가 근접 매수',
    exit_profit: '다음날 시초가 매도',
    exit_loss: '-5% 손절',
    exit_deadline: '1일 보유',
    filter: '시총 ≥1,000억 / 거래대금 ≥50억',
    scoring: '손실크기(30) + 저점회복(35) + 거래대금(20) + 시총(15) = 100점',
  },
  foreign_flow_momentum: {
    name: 'Iota Flow',
    summary: '외국인 투자자가 3일 연속 순매수하면서 주가도 상승하는 종목을 찾습니다. 외국인은 정보력이 뛰어난 "스마트 머니"로 불리며, 연속 매수는 확신이 있다는 신호입니다.',
    signal: '외국인 3일 연속 순매수 + 가격 상승',
    entry: '시초가 매수',
    exit_profit: '+5% 익절',
    exit_loss: '-3% 손절',
    exit_deadline: '2일 보유',
    filter: '시총 ≥2,000억 / 거래대금 ≥100억 / 시총 상위 100',
    scoring: '연속순매수(35) + 순매수규모(30) + 가격모멘텀(20) + 거래대금(15) = 100점',
  },
  bollinger_reversal: {
    name: 'Pi Bollinger (단타)',
    summary: '볼린저밴드 하단에 닿으면서 RSI도 30 이하인 극도의 과매도 종목을 매수합니다. 통계적으로 평균 가격대로 돌아오려는 성질(평균 회귀)을 이용하며, 양봉 전환이 확인되면 반등이 시작된 것으로 봅니다.',
    signal: 'BB(15) %B < 0.2 + RSI(14) < 30 + 양봉',
    entry: '시초가 매수',
    exit_profit: '+5% 익절',
    exit_loss: '-2% 손절',
    exit_deadline: '14:30 강제 청산',
    filter: '시총 ≥1,000억 / 거래대금 ≥30억',
    scoring: '%B(35) + 반등강도(30) + 거래량(20) + 거래대금(15) = 100점',
  },
  overnight_etf_reversal: {
    name: 'Omicron ETF',
    summary: '장 마감 전에 약세인 KOSPI200 ETF를 매수하고 다음날 시초가에 매도합니다. 학술 연구에서 검증된 전략으로, 한국 ETF 시장에서 종가→시초가 사이 양의 수익률이 관찰됩니다. 리스크가 가장 낮은 전략입니다.',
    signal: 'KOSPI200 ETF 종가매수 → 다음날 시초가 매도',
    entry: '종가 매수 (ETF)',
    exit_profit: '다음날 시초가 매도',
    exit_loss: '-3% 손절',
    exit_deadline: 'Overnight (16h)',
    filter: 'ETF만 (KODEX/TIGER/KINDEX 등) / 당일 약세(-0.3%)',
    scoring: '당일약세(35) + 거래대금(25) + 시총(20) + KOSPI200추종(20) = 100점',
  },
};

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

    const rules = STRATEGY_RULES[sid];
    const rulesHtml = rules ? `
            <div style="padding:var(--space-3);background:var(--bg-tinted);border-radius:var(--radius-md);margin:var(--space-2) 0;font-size:var(--fs-sm);line-height:1.6;color:var(--text-secondary);">
              💡 ${rules.summary}
            </div>
            <div class="detail-h">매매 규칙</div>
            <div class="detail-row"><span>📡 시그널</span><span>${rules.signal}</span></div>
            <div class="detail-row"><span>🟢 진입</span><span>${rules.entry}</span></div>
            <div class="detail-row"><span>🎯 익절</span><span>${rules.exit_profit}</span></div>
            <div class="detail-row"><span>🛑 손절</span><span>${rules.exit_loss}</span></div>
            <div class="detail-row"><span>⏰ 마감</span><span>${rules.exit_deadline}</span></div>
            <div class="detail-row"><span>🔍 필터</span><span style="font-size:10px;">${rules.filter}</span></div>
            <div class="detail-row"><span>📊 스코어링</span><span style="font-size:10px;">${rules.scoring}</span></div>
    ` : '';

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
            ${rulesHtml}
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
  let sortKey = 'score';
  let sortAsc = false; // 기본 내림차순

  function getRows() { return [...$$('#candBody .cand-row')]; }

  function applyFilter() {
    const rows = getRows();
    let visibleCount = 0;

    rows.forEach(row => {
      const team = row.dataset.team;
      const matchFilter = currentFilter === 'all' || team === currentFilter;
      const withinLimit = showAll || visibleCount < DEFAULT_SHOW;
      const detail = document.querySelector(`.cand-detail-row[data-idx="${row.dataset.idx}"]`);

      if (matchFilter && withinLimit) {
        row.style.display = '';
        visibleCount++;
      } else {
        row.style.display = 'none';
      }
      if (detail) detail.style.display = 'none';
      row.classList.remove('open');
    });

    const moreBtn = $('#candShowMore');
    if (moreBtn) {
      const totalMatch = rows.filter(r => currentFilter === 'all' || r.dataset.team === currentFilter).length;
      if (showAll || totalMatch <= DEFAULT_SHOW) {
        moreBtn.style.display = 'none';
      } else {
        moreBtn.style.display = 'block';
        moreBtn.textContent = `더보기 (${totalMatch - DEFAULT_SHOW}개)`;
      }
    }
  }

  function applySort() {
    const tbody = $('#candBody');
    if (!tbody) return;
    const rows = getRows();
    const details = [...$$('#candBody .cand-detail-row')];

    // 정렬용 값 추출
    rows.sort((a, b) => {
      let va, vb;
      switch (sortKey) {
        case 'name': va = a.querySelector('b')?.textContent || ''; vb = b.querySelector('b')?.textContent || ''; return sortAsc ? va.localeCompare(vb) : vb.localeCompare(va);
        case 'team': va = a.querySelector('.team-pill')?.textContent || ''; vb = b.querySelector('.team-pill')?.textContent || ''; return sortAsc ? va.localeCompare(vb) : vb.localeCompare(va);
        case 'score': va = +a.dataset.score || 0; vb = +b.dataset.score || 0; break;
        case 'change': va = +a.dataset.change || 0; vb = +b.dataset.change || 0; break;
        case 'price': va = +a.dataset.price || 0; vb = +b.dataset.price || 0; break;
        default: va = +a.dataset.idx; vb = +b.dataset.idx; break;
      }
      return sortAsc ? va - vb : vb - va;
    });

    // DOM 재배치 (행 + 상세행 쌍으로)
    rows.forEach((row, i) => {
      const idx = row.dataset.idx;
      const detail = details.find(d => d.dataset.idx === idx);
      tbody.appendChild(row);
      if (detail) tbody.appendChild(detail);
      // 순번 업데이트
      const numCell = row.querySelector('.num.right');
      if (numCell && numCell === row.cells[0]) numCell.textContent = i + 1;
    });

    // 헤더 정렬 표시
    $$('.cand-sort').forEach(th => {
      const key = th.dataset.sort;
      th.textContent = th.textContent.replace(/ [▲▼]/g, '');
      if (key === sortKey) {
        th.textContent += sortAsc ? ' ▲' : ' ▼';
      }
    });

    applyFilter();
  }

  // 정렬 클릭
  $$('.cand-sort').forEach(th => {
    th.style.cursor = 'pointer';
    th.addEventListener('click', () => {
      const key = th.dataset.sort;
      if (sortKey === key) {
        sortAsc = !sortAsc;
      } else {
        sortKey = key;
        sortAsc = key === 'name' || key === 'team'; // 텍스트는 오름차순 기본
      }
      applySort();
    });
  });

  // 필터 탭
  $$('.cand-filter-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      $$('.cand-filter-tab').forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      currentFilter = tab.dataset.filter;
      showAll = false;
      applyFilter();
    });
  });

  // 더보기
  const moreBtn = $('#candShowMore');
  if (moreBtn) {
    moreBtn.addEventListener('click', () => { showAll = true; applyFilter(); });
  }

  // 행 클릭 → 아코디언
  $$('.cand-row').forEach(row => {
    row.addEventListener('click', (e) => {
      if (e.target.closest('a')) return;
      const idx = row.dataset.idx;
      const detail = document.querySelector(`.cand-detail-row[data-idx="${idx}"]`);
      if (!detail) return;
      const isOpen = detail.style.display !== 'none';
      $$('.cand-detail-row').forEach(d => d.style.display = 'none');
      $$('.cand-row').forEach(r => r.classList.remove('open'));
      if (!isOpen) {
        detail.style.display = '';
        row.classList.add('open');
      }
    });
  });

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
