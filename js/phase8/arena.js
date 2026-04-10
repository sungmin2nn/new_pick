/* Phase 8 - Arena Tab Renderer */

import { fetchCached } from './cache.js';
import {
  fmtNum, fmtMoney, fmtPct, fmtPctSigned, fmtDate,
  colorClass, $, $$, el, getTodayKST, getRecentDates, sparklineSVG
} from './ui.js';

const TEAM_META = {
  team_a: { name: 'Alpha Momentum', desc: '모멘텀 + MA5 + 거래량 급증', color: '#EF4444', strategy: 'momentum' },
  team_b: { name: 'Beta Contrarian', desc: '대형주 역추세 + RSI + 시장모드', color: '#3B82F6', strategy: 'largecap_contrarian' },
  team_c: { name: 'Gamma Disclosure', desc: 'DART 호재 공시 (정제)', color: '#10B981', strategy: 'dart_disclosure' },
  team_d: { name: 'Delta Theme', desc: '테마/정책 + 섹터 모멘텀', color: '#F59E0B', strategy: 'theme_policy' },
  team_e: { name: 'Echo Frontier', desc: '시초가 갭 + 거래량 surge', color: '#8B5CF6', strategy: 'frontier_gap' },
};

const MEDALS = ['🥇', '🥈', '🥉', '4', '5'];
const TEAM_IDS = Object.keys(TEAM_META);
const DATA_BASE = 'data/arena';

let state = {
  leaderboard: null,
  portfolios: {},
  health: null,
  candidates: {},
  arenaReport: null,
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

  state.arenaReport = await fetchCached(`${DATA_BASE}/daily/${today}/arena_report.json`, force);

  return state;
}

// ============ Render: Today section ============
export function renderToday() {
  const container = $('#arena-today');
  if (!container) return;

  // 5팀 데이터 정리
  const rows = TEAM_IDS.map(tid => {
    const meta = TEAM_META[tid];
    const pf = state.portfolios[tid] || {};
    const lbTeam = state.leaderboard?.teams?.[tid] || {};
    const todayHist = state.leaderboard?.daily_history?.slice(-1)[0];
    const todayRank = todayHist?.ranking?.find(r => r.team_id === tid);
    return {
      tid, name: meta.name, desc: meta.desc, color: meta.color,
      today_pct: todayRank?.total_return ?? 0,
      cum_pct: pf.total_return_pct ?? 0,
      capital: pf.current_capital ?? 10000000,
      elo: lbTeam.elo ?? 1000,
      wins: pf.total_wins ?? 0,
      trades: pf.total_trades ?? 0,
      trading_days: pf.trading_days ?? 0,
    };
  }).sort((a, b) => b.today_pct - a.today_pct);

  // KPI 4개
  const dailyAvg = rows.reduce((s, t) => s + t.today_pct, 0) / Math.max(rows.length, 1);
  const maxRow = rows[0];
  const minRow = rows[rows.length - 1];
  const totalCapital = rows.reduce((s, t) => s + t.capital, 0);
  const totalCum = ((totalCapital - 10000000 * rows.length) / (10000000 * rows.length)) * 100;
  const dayN = state.leaderboard?.daily_history?.length ?? 0;

  const kpis = `
    <div class="kpi">
      <div class="kpi-label">5팀 평균</div>
      <div class="kpi-value ${colorClass(dailyAvg)}">${fmtPctSigned(dailyAvg)}</div>
      <div class="kpi-meta">5팀 일일 평균 수익률</div>
    </div>
    <div class="kpi">
      <div class="kpi-label">최고</div>
      <div class="kpi-value up">${fmtPctSigned(maxRow.today_pct)}</div>
      <div class="kpi-meta">${maxRow.name}</div>
    </div>
    <div class="kpi">
      <div class="kpi-label">최저</div>
      <div class="kpi-value ${colorClass(minRow.today_pct)}">${fmtPctSigned(minRow.today_pct)}</div>
      <div class="kpi-meta">${minRow.name}</div>
    </div>
    <div class="kpi">
      <div class="kpi-label">총 자산</div>
      <div class="kpi-value">${fmtMoney(totalCapital)}</div>
      <div class="kpi-meta ${colorClass(totalCum)}">누적 ${fmtPct(totalCum)} · Day ${dayN}</div>
    </div>
  `;

  // 5팀 순위 카드
  const rankList = rows.map((t, i) => {
    const m = MEDALS[Math.min(i, 4)];
    return `
      <div class="team-card" data-rank="${i + 1}" style="border-left-color:${t.color};">
        <div class="team-medal">${m}</div>
        <div class="name">${t.name}</div>
        <div class="desc">${t.desc}</div>
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
    `;
  }).join('');

  container.innerHTML = `
    <div class="section">
      <div class="section-header">
        <h2 class="section-title display">📊 Today</h2>
        <span class="section-subtitle">${fmtDate(getTodayKST())} · Day ${dayN}</span>
      </div>
      <div class="kpi-grid">${kpis}</div>
    </div>

    <div class="section">
      <div class="section-header">
        <h2 class="section-title display">🏆 오늘 순위</h2>
        <span class="section-subtitle">5팀 일일 수익률 기준</span>
      </div>
      <div class="team-grid">${rankList}</div>
    </div>
  `;
}

// ============ Render: Leaderboard section ============
export function renderLeaderboard() {
  const container = $('#arena-leaderboard');
  if (!container) return;

  // ELO 정렬
  const teams = Object.values(state.leaderboard?.teams || {})
    .map(t => ({ ...t, meta: TEAM_META[t.team_id] || {} }))
    .sort((a, b) => (b.elo || 1000) - (a.elo || 1000));

  // H2H Top 2
  let h2hHtml = '';
  if (teams.length >= 2) {
    const t1 = teams[0], t2 = teams[1];
    const pf1 = state.portfolios[t1.team_id] || {};
    const pf2 = state.portfolios[t2.team_id] || {};
    const todayHist = state.leaderboard?.daily_history?.slice(-1)[0];
    const today1 = todayHist?.ranking?.find(r => r.team_id === t1.team_id);
    const today2 = todayHist?.ranking?.find(r => r.team_id === t2.team_id);
    const ret1 = today1?.total_return ?? 0;
    const ret2 = today2?.total_return ?? 0;
    const wr1 = pf1.total_trades > 0 ? Math.round(pf1.total_wins / pf1.total_trades * 100) : 0;
    const wr2 = pf2.total_trades > 0 ? Math.round(pf2.total_wins / pf2.total_trades * 100) : 0;
    const gap = Math.abs(ret1 - ret2);

    h2hHtml = `
      <div class="h2h">
        <div class="h2h-header">🏆 TOP 2 HEAD-TO-HEAD</div>
        <div class="h2h-body">
          <div class="h2h-team">
            <div class="h2h-badge" style="color:${t1.meta.color};background:${t1.meta.color}15;">1</div>
            <div class="h2h-name">${t1.team_name}</div>
            <div class="h2h-desc">${t1.meta.desc || ''}</div>
            <div class="h2h-return ${colorClass(ret1)}">${fmtPctSigned(ret1)}</div>
            <div class="h2h-meta">ELO <b>${t1.elo}</b> · 승률 <b>${wr1}%</b></div>
          </div>
          <div class="h2h-vs">VS</div>
          <div class="h2h-team">
            <div class="h2h-badge" style="color:${t2.meta.color};background:${t2.meta.color}15;">2</div>
            <div class="h2h-name">${t2.team_name}</div>
            <div class="h2h-desc">${t2.meta.desc || ''}</div>
            <div class="h2h-return ${colorClass(ret2)}">${fmtPctSigned(ret2)}</div>
            <div class="h2h-meta">ELO <b>${t2.elo}</b> · 승률 <b>${wr2}%</b></div>
          </div>
        </div>
        <div class="h2h-gap">
          리드 격차 <span class="h2h-gap-pill">${gap.toFixed(2)}%p</span>
        </div>
      </div>
    `;
  }

  // 5팀 ELO 순위 카드
  const cards = teams.map((t, i) => {
    const pf = state.portfolios[t.team_id] || {};
    const m = MEDALS[Math.min(i, 4)];
    const wr = pf.total_trades > 0 ? Math.round(pf.total_wins / pf.total_trades * 100) : 0;
    const cumPct = pf.total_return_pct ?? 0;
    return `
      <div class="team-card" data-rank="${i + 1}" style="border-left-color:${t.meta.color};">
        <div class="team-medal">${m}</div>
        <div class="name">${t.team_name}</div>
        <div class="desc">${t.meta.desc || ''}</div>
        <div class="team-stats">
          <div class="team-stat">
            <span class="team-stat-label">ELO</span>
            <span class="team-stat-value">${t.elo}</span>
          </div>
          <div class="team-stat">
            <span class="team-stat-label">누적</span>
            <span class="team-stat-value ${colorClass(cumPct)}">${fmtPct(cumPct)}</span>
          </div>
          <div class="team-stat">
            <span class="team-stat-label">잔고</span>
            <span class="team-stat-value">${fmtMoney(pf.current_capital ?? 10000000)}</span>
          </div>
          <div class="team-stat">
            <span class="team-stat-label">승률</span>
            <span class="team-stat-value">${wr}% (${pf.total_wins ?? 0}/${pf.total_trades ?? 0})</span>
          </div>
        </div>
      </div>
    `;
  }).join('');

  container.innerHTML = `
    ${h2hHtml}
    <div class="section">
      <div class="section-header">
        <h2 class="section-title display">🏆 ELO 랭킹</h2>
        <span class="section-subtitle">5팀 누적 ELO 기준</span>
      </div>
      <div class="team-grid">${cards}</div>
    </div>
  `;
}

// ============ Render: Strategies (5전략 후보) ============
export function renderStrategies() {
  const container = $('#arena-strategies');
  if (!container) return;

  const today = getTodayKST();
  const sections = TEAM_IDS.map(tid => {
    const meta = TEAM_META[tid];
    const cands = state.candidates[meta.strategy];
    const candList = cands?.candidates || cands || [];
    const count = Array.isArray(candList) ? candList.length : 0;

    const rows = (Array.isArray(candList) ? candList : []).slice(0, 5).map(c => `
      <tr>
        <td>${c.rank || '-'}</td>
        <td><strong>${c.name || '-'}</strong> <code>${c.code || '-'}</code></td>
        <td class="num right ${colorClass(c.change_pct)}">${fmtPctSigned(c.change_pct)}</td>
        <td class="num right">${fmtNum(c.score?.toFixed?.(1) ?? c.score)}</td>
        <td class="num right">${fmtMoney(c.price)}</td>
      </tr>
    `).join('');

    return `
      <div class="section">
        <div class="section-header">
          <h2 class="section-title display" style="color:${meta.color};">${meta.name}</h2>
          <span class="section-subtitle">${meta.desc} · ${count}종목</span>
        </div>
        ${count > 0 ? `
        <div class="table-wrap">
          <table class="tbl">
            <thead>
              <tr><th>#</th><th>종목</th><th class="right">등락률</th><th class="right">점수</th><th class="right">가격</th></tr>
            </thead>
            <tbody>${rows}</tbody>
          </table>
        </div>` : `<div class="empty"><div class="empty-icon">📭</div><div class="empty-text">오늘 후보 없음</div></div>`}
      </div>
    `;
  }).join('');

  container.innerHTML = sections;
}

// ============ Render: System ============
export function renderSystem() {
  const container = $('#arena-system');
  if (!container) return;

  const h = state.health || {};
  const status = h.status || 'unknown';
  const checks = h.checks || [];
  const issues = h.issues || [];

  const statusPill = {
    healthy: '<span class="pill pill-success"><span class="pill-dot pulse-dot"></span> 정상</span>',
    warning: '<span class="pill pill-warning"><span class="pill-dot pulse-dot"></span> 경고</span>',
    unhealthy: '<span class="pill pill-critical"><span class="pill-dot pulse-dot"></span> 위험</span>',
    unknown: '<span class="pill pill-neutral"><span class="pill-dot"></span> 정보 없음</span>',
  }[status] || `<span class="pill pill-neutral">${status}</span>`;

  const checkRows = checks.map(c => `
    <tr>
      <td>${c.check_type || c.check || '-'}</td>
      <td class="center">${c.status === 'pass' ? '<span class="pill pill-success">통과</span>' : '<span class="pill pill-critical">실패</span>'}</td>
      <td>${c.details || c.description || '-'}</td>
    </tr>
  `).join('');

  const issueList = issues.length > 0 ? `
    <div class="section">
      <div class="section-header">
        <h2 class="section-title display">⚠️ 이슈 ${issues.length}건</h2>
      </div>
      <div class="stack">
        ${issues.map(i => `
          <div class="card" style="border-left:4px solid var(--warning);">
            <strong>${i.description || i.check || '이슈'}</strong>
            <div style="font-size:var(--fs-sm); color:var(--text-tertiary); margin-top:4px;">${i.details || ''}</div>
          </div>
        `).join('')}
      </div>
    </div>
  ` : '';

  // 워크플로우 목록
  const workflows = [
    { name: 'paper-trading.yml', desc: 'Arena 매매 정산 + 종목 선정', sched: '16:10 KST' },
    { name: 'paper-trading-check.yml', desc: '헬스체크', sched: '10/12/14/17 KST' },
    { name: 'paper-trading-select.yml', desc: '종목 재선정', sched: '16:30 KST' },
    { name: 'bnf-selection.yml', desc: 'BNF 후보 선정', sched: '16:30 KST' },
    { name: 'bnf-simulation.yml', desc: 'BNF 시뮬레이션', sched: '09:30 + 15:30 KST' },
    { name: 'theme-snapshot.yml', desc: '테마 스냅샷', sched: '16:30 KST' },
  ];

  container.innerHTML = `
    <div class="section">
      <div class="section-header">
        <h2 class="section-title display">⚙️ 시스템 상태</h2>
        ${statusPill}
      </div>
      <div class="kpi-grid">
        <div class="kpi">
          <div class="kpi-label">체크 항목</div>
          <div class="kpi-value">${checks.length}</div>
          <div class="kpi-meta">${h.checked_at || '-'}</div>
        </div>
        <div class="kpi">
          <div class="kpi-label">이슈</div>
          <div class="kpi-value ${issues.length > 0 ? 'warning' : 'success'}">${issues.length}</div>
          <div class="kpi-meta">${issues.length === 0 ? '문제 없음' : '확인 필요'}</div>
        </div>
        <div class="kpi">
          <div class="kpi-label">활성 팀</div>
          <div class="kpi-value">5 / 5</div>
          <div class="kpi-meta">Arena 전체 가동 중</div>
        </div>
        <div class="kpi">
          <div class="kpi-label">총 매매</div>
          <div class="kpi-value">${TEAM_IDS.reduce((s, t) => s + (state.portfolios[t]?.total_trades || 0), 0)}건</div>
          <div class="kpi-meta">5팀 누적</div>
        </div>
      </div>
    </div>

    ${issueList}

    ${checks.length > 0 ? `
    <div class="section">
      <div class="section-header">
        <h2 class="section-title display">🏥 헬스체크</h2>
      </div>
      <div class="table-wrap">
        <table class="tbl">
          <thead><tr><th>항목</th><th class="center">상태</th><th>상세</th></tr></thead>
          <tbody>${checkRows}</tbody>
        </table>
      </div>
    </div>` : ''}

    <div class="section">
      <div class="section-header">
        <h2 class="section-title display">📅 워크플로우</h2>
      </div>
      <div class="table-wrap">
        <table class="tbl">
          <thead><tr><th>워크플로우</th><th>설명</th><th>스케줄</th></tr></thead>
          <tbody>
            ${workflows.map(w => `<tr><td><code>${w.name}</code></td><td>${w.desc}</td><td>${w.sched}</td></tr>`).join('')}
          </tbody>
        </table>
      </div>
    </div>
  `;
}

// ============ Render: Teams (drilldown) ============
export function renderTeams() {
  const container = $('#arena-teams');
  if (!container) return;

  const today = getTodayKST();

  const sections = TEAM_IDS.map(tid => {
    const meta = TEAM_META[tid];
    const pf = state.portfolios[tid] || {};
    const lbTeam = state.leaderboard?.teams?.[tid] || {};
    const dailyHistory = state.leaderboard?.daily_history?.slice(-10) || [];

    // 최근 10일 spark
    const sparkData = dailyHistory.map(h => {
      const r = h.ranking?.find(x => x.team_id === tid);
      return r?.total_return ?? 0;
    });

    return `
      <details class="card" style="border-left:4px solid ${meta.color}; padding:0;" ${tid === 'team_a' ? 'open' : ''}>
        <summary style="padding:var(--space-4); cursor:pointer; list-style:none;">
          <div class="inline justify-between flex-wrap">
            <div>
              <div class="inline">
                <span style="display:inline-block; width:10px; height:10px; border-radius:50%; background:${meta.color};"></span>
                <strong style="font-size:var(--fs-lg);">${meta.name}</strong>
              </div>
              <div style="font-size:var(--fs-xs); color:var(--text-tertiary); margin-top:4px;">${meta.desc}</div>
            </div>
            <div class="inline-md">
              <div style="text-align:right;">
                <div class="num ${colorClass(pf.total_return_pct)}" style="font-weight:700;">${fmtPct(pf.total_return_pct ?? 0)}</div>
                <div style="font-size:var(--fs-xs); color:var(--text-tertiary);">ELO ${lbTeam.elo ?? 1000}</div>
              </div>
              <span style="font-size:0.8em;">▼</span>
            </div>
          </div>
        </summary>
        <div style="padding:0 var(--space-4) var(--space-4); border-top:1px solid var(--border-subtle);">
          <div class="kpi-grid" style="margin-top:var(--space-4);">
            <div class="kpi">
              <div class="kpi-label">잔고</div>
              <div class="kpi-value">${fmtMoney(pf.current_capital ?? 10000000)}</div>
            </div>
            <div class="kpi">
              <div class="kpi-label">매매</div>
              <div class="kpi-value">${pf.total_wins ?? 0}/${pf.total_trades ?? 0}</div>
              <div class="kpi-meta">${pf.total_trades > 0 ? Math.round(pf.total_wins / pf.total_trades * 100) : 0}% 승률</div>
            </div>
            <div class="kpi">
              <div class="kpi-label">최대 연승</div>
              <div class="kpi-value">${pf.max_win_streak ?? 0}</div>
            </div>
            <div class="kpi">
              <div class="kpi-label">MDD</div>
              <div class="kpi-value down">${(pf.max_drawdown_pct ?? 0).toFixed(1)}%</div>
            </div>
          </div>
          ${sparkData.length >= 2 ? `
          <div style="margin-top:var(--space-4);">
            <div class="label">최근 10일 일일 수익률 추이</div>
            <div style="margin-top:var(--space-2); color:${meta.color};">
              ${sparklineSVG(sparkData, { width: 400, height: 60, color: meta.color })}
            </div>
          </div>` : ''}
        </div>
      </details>
    `;
  }).join('');

  container.innerHTML = `
    <div class="section">
      <div class="section-header">
        <h2 class="section-title display">👥 팀별 상세</h2>
        <span class="section-subtitle">클릭하여 펼치기/접기</span>
      </div>
      <div class="stack">${sections}</div>
    </div>
  `;
}

// ============ 메인 ============
export async function initArena() {
  await loadArenaData();
  renderToday();
  renderLeaderboard();
  renderTeams();
  renderStrategies();
  renderSystem();
}

export async function refreshArena() {
  await loadArenaData(true);
  renderToday();
  renderLeaderboard();
  renderTeams();
  renderStrategies();
  renderSystem();
}
