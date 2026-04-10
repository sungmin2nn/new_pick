/* Phase 8 - BNF Tab Renderer */

import { fetchCached } from './cache.js';
import {
  fmtNum, fmtMoney, fmtPct, fmtPctSigned, fmtDate,
  colorClass, $, $$, sparklineSVG
} from './ui.js';

const BNF_BASE = 'data/bnf';

let state = {
  candidates: null,
  positions: null,
  history: null,
};

// ============ Data loading ============
export async function loadBNFData(force = false) {
  state.candidates = await fetchCached(`${BNF_BASE}/candidates.json`, force);
  state.positions = await fetchCached(`${BNF_BASE}/positions.json`, force);
  state.history = await fetchCached(`${BNF_BASE}/trade_history.json`, force);
  return state;
}

// ============ Render: Strategy Info ============
export function renderBNFStrategy() {
  const container = $('#bnf-strategy');
  if (!container) return;
  container.innerHTML = `
    <div class="section">
      <div class="section-header">
        <h2 class="section-title display">📉 BNF 낙폭과대 역추세</h2>
        <span class="section-subtitle">분할매수 + 트레일링 스탑</span>
      </div>
      <div class="card">
        <div class="kpi-grid">
          <div class="kpi">
            <div class="kpi-label">대상 종목</div>
            <div class="kpi-value">시총 1조↑</div>
            <div class="kpi-meta">대형주 중심</div>
          </div>
          <div class="kpi">
            <div class="kpi-label">매수 진입</div>
            <div class="kpi-value">52주 -30%↓</div>
            <div class="kpi-meta">고점 대비 낙폭</div>
          </div>
          <div class="kpi">
            <div class="kpi-label">분할 매수</div>
            <div class="kpi-value">3단계</div>
            <div class="kpi-meta">30 / 40 / 30%</div>
          </div>
          <div class="kpi">
            <div class="kpi-label">익절 / 손절</div>
            <div class="kpi-value">+15~20% / -10%</div>
            <div class="kpi-meta">리스크 관리</div>
          </div>
        </div>
        <div style="margin-top:var(--space-4); padding-top:var(--space-4); border-top:1px solid var(--border-subtle); font-size:var(--fs-sm); color:var(--text-tertiary);">
          최대 5종목 보유 · 자금 80% 한도 · 트레일링 스탑 자동 청산
        </div>
      </div>
    </div>
  `;
}

// ============ Render: Capital Status ============
export function renderBNFCapital() {
  const container = $('#bnf-capital');
  if (!container) return;

  const stats = state.positions?.stats || {};
  const positions = state.positions?.positions || [];
  const totalCapital = stats.total_capital || 50_000_000;
  const usedCapital = stats.used_capital || 0;
  const usePct = totalCapital > 0 ? (usedCapital / totalCapital * 100) : 0;
  const totalReturn = stats.total_return || 0;
  const winRate = stats.win_rate || 0;
  const unrealized = stats.unrealized_pnl || 0;
  const totalTrades = stats.total_trades || 0;
  const avgReturn = stats.avg_return || 0;
  const openPositions = stats.open_positions || positions.length;

  container.innerHTML = `
    <div class="section">
      <div class="section-header">
        <h2 class="section-title display">💰 자본 현황</h2>
        <span class="section-subtitle">실시간 포지션 + 누적 통계</span>
      </div>
      <div class="card">
        <div class="kpi-grid">
          <div class="kpi">
            <div class="kpi-label">사용 자본</div>
            <div class="kpi-value">${fmtMoney(usedCapital)}</div>
            <div class="kpi-meta">${fmtPct(usePct)} of ${fmtMoney(totalCapital)}</div>
          </div>
          <div class="kpi">
            <div class="kpi-label">미실현 손익</div>
            <div class="kpi-value ${colorClass(unrealized)}">${fmtMoney(unrealized)}</div>
            <div class="kpi-meta">현재 보유 종목</div>
          </div>
          <div class="kpi">
            <div class="kpi-label">활성 포지션</div>
            <div class="kpi-value">${openPositions} / 5</div>
            <div class="kpi-meta">최대 보유수 대비</div>
          </div>
          <div class="kpi">
            <div class="kpi-label">총 수익률</div>
            <div class="kpi-value ${colorClass(totalReturn)}">${fmtPct(totalReturn)}</div>
            <div class="kpi-meta">${totalTrades}건 · ${winRate.toFixed(1)}% 승률</div>
          </div>
        </div>
      </div>
    </div>
  `;
}

// ============ Render: Candidates ============
export function renderBNFCandidates() {
  const container = $('#bnf-candidates');
  if (!container) return;

  const cands = state.candidates?.candidates || [];
  const date = state.candidates?.date || '-';
  const count = state.candidates?.count || cands.length;

  if (count === 0) {
    container.innerHTML = `
      <div class="section">
        <div class="section-header">
          <h2 class="section-title display">🎯 후보 종목</h2>
          <span class="section-subtitle">${fmtDate(date)} 선정 결과</span>
        </div>
        <div class="card empty"><div class="empty-icon">📭</div><div class="empty-text">조건 충족 종목 없음</div></div>
      </div>
    `;
    return;
  }

  const rows = cands.slice(0, 20).map(c => `
    <tr>
      <td>${c.rank || '-'}</td>
      <td><strong>${c.name || '-'}</strong> <code>${c.code || '-'}</code></td>
      <td class="num right">${fmtMoney(c.price)}</td>
      <td class="num right">${fmtMoney(c.high_20d || c.high_52w)}</td>
      <td class="num right cell-down">${fmtPct(c.drop_from_high)}</td>
      <td class="num right ${colorClass(c.drop_5d)}">${fmtPct(c.drop_5d)}</td>
      <td class="num right ${colorClass(c.drop_10d)}">${fmtPct(c.drop_10d)}</td>
      <td>${(c.reasons || []).join(', ') || '-'}</td>
    </tr>
  `).join('');

  container.innerHTML = `
    <div class="section">
      <div class="section-header">
        <h2 class="section-title display">🎯 후보 종목 (${count})</h2>
        <span class="section-subtitle">${fmtDate(date)} 선정 결과 · 낙폭 큰 순</span>
      </div>
      <div class="table-wrap">
        <table class="tbl">
          <thead>
            <tr>
              <th>#</th>
              <th>종목</th>
              <th class="right">현재가</th>
              <th class="right">고점</th>
              <th class="right">고점대비</th>
              <th class="right">5일</th>
              <th class="right">10일</th>
              <th>비고</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    </div>
  `;
}

// ============ Render: Positions ============
export function renderBNFPositions() {
  const container = $('#bnf-positions');
  if (!container) return;

  const positions = state.positions?.positions || [];

  if (positions.length === 0) {
    container.innerHTML = `
      <div class="section">
        <div class="section-header">
          <h2 class="section-title display">📊 보유 포지션</h2>
        </div>
        <div class="card empty"><div class="empty-icon">📭</div><div class="empty-text">현재 보유 종목 없음</div></div>
      </div>
    `;
    return;
  }

  const rows = positions.map(p => {
    const pnlPct = p.unrealized_pnl_pct ?? 0;
    const stateLabel = {
      FULL: '<span class="pill pill-accent">전량 진입</span>',
      PARTIAL: '<span class="pill pill-warning">부분 진입</span>',
      EXITING: '<span class="pill pill-critical">청산 중</span>',
    }[p.state] || `<span class="pill pill-neutral">${p.state || '-'}</span>`;

    return `
      <tr>
        <td><strong>${p.name}</strong> <code>${p.code}</code></td>
        <td class="center">${stateLabel}</td>
        <td class="num right">${fmtMoney(p.avg_price)}</td>
        <td class="num right">${fmtMoney(p.current_price)}</td>
        <td class="num right">${fmtNum(p.total_quantity)}주</td>
        <td class="num right ${colorClass(p.unrealized_pnl)}">${fmtMoney(p.unrealized_pnl)}</td>
        <td class="num right ${colorClass(pnlPct)}">${fmtPctSigned(pnlPct)}</td>
        <td>${p.entry_date || '-'}</td>
        <td>${p.selection_reason || '-'}</td>
      </tr>
    `;
  }).join('');

  container.innerHTML = `
    <div class="section">
      <div class="section-header">
        <h2 class="section-title display">📊 보유 포지션 (${positions.length})</h2>
        <span class="section-subtitle">실시간 미실현 손익</span>
      </div>
      <div class="table-wrap">
        <table class="tbl">
          <thead>
            <tr>
              <th>종목</th>
              <th class="center">상태</th>
              <th class="right">평균단가</th>
              <th class="right">현재가</th>
              <th class="right">수량</th>
              <th class="right">미실현</th>
              <th class="right">손익률</th>
              <th>진입일</th>
              <th>이유</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    </div>
  `;
}

// ============ Render: Trade History ============
export function renderBNFHistory() {
  const container = $('#bnf-history');
  if (!container) return;

  const trades = state.history?.trades || [];
  const stats = state.history?.stats || {};

  if (trades.length === 0) {
    container.innerHTML = `
      <div class="section">
        <div class="section-header">
          <h2 class="section-title display">📜 거래 이력</h2>
        </div>
        <div class="card empty"><div class="empty-icon">📭</div><div class="empty-text">거래 기록 없음</div></div>
      </div>
    `;
    return;
  }

  const rows = trades.slice(0, 50).map(t => `
    <tr>
      <td>${t.entry_date || '-'}</td>
      <td><strong>${t.name}</strong> <code>${t.code}</code></td>
      <td class="num right">${fmtMoney(t.entry_price)}</td>
      <td class="num right">${fmtMoney(t.exit_price)}</td>
      <td class="num right">${fmtNum(t.quantity)}</td>
      <td class="num right ${colorClass(t.profit)}">${fmtMoney(t.profit)}</td>
      <td class="num right ${colorClass(t.return_pct)}">${fmtPctSigned(t.return_pct)}</td>
      <td>${t.exit_reason || '-'}</td>
    </tr>
  `).join('');

  // 누적 sparkline
  let cumProfit = 0;
  const cumData = trades.slice().reverse().map(t => {
    cumProfit += (t.profit || 0);
    return cumProfit;
  });

  container.innerHTML = `
    <div class="section">
      <div class="section-header">
        <h2 class="section-title display">📜 거래 이력 (${stats.total_trades || trades.length})</h2>
        <span class="section-subtitle">${stats.win_count || 0}승 ${stats.loss_count || 0}패 · ${(stats.win_rate || 0).toFixed(1)}% 승률</span>
      </div>
      <div class="card" style="margin-bottom:var(--space-4);">
        <div class="label">누적 손익 추이</div>
        <div style="margin-top:var(--space-2); color:${cumProfit >= 0 ? 'var(--up)' : 'var(--down)'};">
          ${sparklineSVG(cumData, { width: 600, height: 80, color: cumProfit >= 0 ? '#EF4444' : '#3B82F6' })}
        </div>
      </div>
      <div class="table-wrap">
        <table class="tbl">
          <thead>
            <tr>
              <th>날짜</th>
              <th>종목</th>
              <th class="right">매수가</th>
              <th class="right">매도가</th>
              <th class="right">수량</th>
              <th class="right">손익</th>
              <th class="right">수익률</th>
              <th>청산 사유</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    </div>
  `;
}

// ============ 메인 ============
export async function initBNF() {
  await loadBNFData();
  renderBNFStrategy();
  renderBNFCapital();
  renderBNFCandidates();
  renderBNFPositions();
  renderBNFHistory();
}

export async function refreshBNF() {
  await loadBNFData(true);
  renderBNFStrategy();
  renderBNFCapital();
  renderBNFCandidates();
  renderBNFPositions();
  renderBNFHistory();
}
