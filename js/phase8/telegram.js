/* Phase 8 - Telegram History Viewer
 * 일별 발송 이력 조회 + 날짜 네비게이션 + 아코디언 상세
 */

import { $, $$, el, fmtDate } from './ui.js';
import { fetchCached } from './cache.js';

// ============ State ============
let currentDate = getTodayStr();

function getTodayStr() {
  const now = new Date();
  const kst = new Date(now.getTime() + 9 * 60 * 60 * 1000);
  return kst.toISOString().slice(0, 10); // YYYY-MM-DD
}

function shiftDate(dateStr, days) {
  const d = new Date(dateStr + 'T00:00:00+09:00');
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

function formatDisplayDate(dateStr) {
  const [y, m, d] = dateStr.split('-');
  const dow = ['일', '월', '화', '수', '목', '금', '토'];
  const dt = new Date(dateStr + 'T00:00:00+09:00');
  return `${y}.${m}.${d} (${dow[dt.getDay()]})`;
}

// ============ Data fetch ============
async function fetchTelegramLog(dateStr) {
  const path = `logs/telegram/${dateStr}.jsonl`;
  const raw = await fetchCached(path, true);
  if (!raw || typeof raw !== 'string') return [];
  return raw.trim().split('\n').filter(Boolean).map(line => {
    try { return JSON.parse(line); }
    catch { return null; }
  }).filter(Boolean);
}

// ============ Render ============
function renderTelegramPane(entries) {
  const container = $('#telegram-content');
  if (!container) return;

  // 통계
  const total = entries.length;
  const success = entries.filter(e => e.success).length;
  const failed = total - success;

  // 빈 상태
  if (total === 0) {
    container.innerHTML = `
      <div class="card" style="text-align:center; padding:var(--space-8);">
        <div style="font-size:2rem; margin-bottom:var(--space-3);">📭</div>
        <div style="color:var(--text-secondary); font-size:var(--fs-sm);">
          이 날짜에 발송된 알림이 없습니다
        </div>
      </div>`;
    updateStats(0, 0, 0);
    return;
  }

  // 통계 업데이트
  updateStats(total, success, failed);

  // 아이템 리스트
  let html = '<div class="tg-list">';
  entries.forEach((entry, idx) => {
    const statusIcon = entry.success ? '✅' : '❌';
    const statusClass = entry.success ? 'tg-success' : 'tg-fail';
    const emoji = entry.emoji || '📨';
    const label = entry.label || entry.type || 'unknown';
    const time = entry.time || entry.timestamp?.slice(11, 19) || '';
    const preview = escapeHtml(entry.preview || '').slice(0, 60);
    const errorBadge = entry.error
      ? `<span class="tg-error-badge">${escapeHtml(entry.error).slice(0, 40)}</span>`
      : '';

    // 상세 메시지 (아코디언)
    const message = escapeHtml(entry.message || entry.preview || '');

    html += `
      <div class="tg-item ${statusClass}" data-idx="${idx}">
        <div class="tg-item-header" onclick="this.parentElement.classList.toggle('open')">
          <div class="tg-item-left">
            <span class="tg-status">${statusIcon}</span>
            <span class="tg-time num">${time}</span>
            <span class="tg-emoji">${emoji}</span>
            <span class="tg-label">${label}</span>
            ${errorBadge}
          </div>
          <div class="tg-item-right">
            <span class="tg-chevron">›</span>
          </div>
        </div>
        <div class="tg-item-body">
          <pre class="tg-message">${message}</pre>
        </div>
      </div>`;
  });
  html += '</div>';
  container.innerHTML = html;
}

function updateStats(total, success, failed) {
  const el = $('#tg-stats');
  if (!el) return;
  const pct = total > 0 ? Math.round(success / total * 100) : 0;
  const pctClass = pct === 100 ? 'up' : pct >= 80 ? 'neutral' : 'down';
  el.innerHTML = `
    <span class="tg-stat">${total}건</span>
    <span class="tg-stat-divider">·</span>
    <span class="tg-stat success">성공 ${success}</span>
    <span class="tg-stat-divider">·</span>
    <span class="tg-stat fail">실패 ${failed}</span>
    <span class="tg-stat-divider">·</span>
    <span class="tg-stat ${pctClass}">${pct}%</span>`;
}

function escapeHtml(s) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// ============ Navigation ============
async function goToDate(dateStr) {
  currentDate = dateStr;

  // 날짜 표시 업데이트
  const dateDisplay = $('#tg-date-display');
  if (dateDisplay) dateDisplay.textContent = formatDisplayDate(dateStr);

  // 오늘인지 표시
  const todayBadge = $('#tg-today-badge');
  if (todayBadge) todayBadge.style.display = dateStr === getTodayStr() ? '' : 'none';

  // 미래 차단
  const nextBtn = $('#tg-next');
  if (nextBtn) nextBtn.disabled = dateStr >= getTodayStr();

  // 데이터 로드 & 렌더
  const entries = await fetchTelegramLog(dateStr);
  renderTelegramPane(entries);
}

// ============ Init ============
export async function initTelegram() {
  const prevBtn = $('#tg-prev');
  const nextBtn = $('#tg-next');
  const todayBtn = $('#tg-today');

  if (prevBtn) prevBtn.addEventListener('click', () => goToDate(shiftDate(currentDate, -1)));
  if (nextBtn) nextBtn.addEventListener('click', () => goToDate(shiftDate(currentDate, 1)));
  if (todayBtn) todayBtn.addEventListener('click', () => goToDate(getTodayStr()));

  await goToDate(getTodayStr());
}

export async function refreshTelegram() {
  await goToDate(currentDate);
}
