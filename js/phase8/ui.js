/* Phase 8 - UI Helpers (format, count-up, DOM 등) */

// ============ 한국식 숫자 포맷 ============
export function fmtNum(n) {
  if (n == null || isNaN(n)) return '-';
  return Number(n).toLocaleString('ko-KR');
}

export function fmtMoney(n) {
  if (n == null || isNaN(n)) return '-';
  return Number(n).toLocaleString('ko-KR') + '원';
}

export function fmtPct(n, decimals = 2) {
  if (n == null || isNaN(n)) return '-';
  const sign = n >= 0 ? '+' : '';
  return sign + Number(n).toFixed(decimals) + '%';
}

export function fmtPctSigned(n, decimals = 2) {
  if (n == null || isNaN(n)) return '─';
  const arrow = n > 0 ? '▲' : n < 0 ? '▼' : '─';
  const sign = n >= 0 ? '+' : '';
  return `${arrow} ${sign}${Number(n).toFixed(decimals)}%`;
}

export function fmtDate(s) {
  if (!s) return '-';
  if (typeof s === 'string' && s.length === 8) {
    return `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}`;
  }
  return s;
}

export function fmtTime(d = new Date()) {
  return d.toLocaleTimeString('ko-KR', { hour12: false });
}

// ============ 색상 클래스 ============
export function colorClass(n) {
  if (n == null || isNaN(n)) return 'neutral';
  if (n > 0) return 'up';
  if (n < 0) return 'down';
  return 'neutral';
}

// ============ DOM ============
export function $(sel, root = document) {
  return root.querySelector(sel);
}

export function $$(sel, root = document) {
  return Array.from(root.querySelectorAll(sel));
}

export function el(tag, attrs = {}, ...children) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'class') e.className = v;
    else if (k === 'html') e.innerHTML = v;
    else if (k.startsWith('on') && typeof v === 'function') e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v);
  }
  for (const c of children) {
    if (c == null) continue;
    e.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
  }
  return e;
}

// ============ Count-up animation ============
export function countUp(el, target, duration = 800, decimals = 2) {
  const start = Date.now();
  const initial = parseFloat(el.dataset.current || '0');
  const delta = target - initial;
  el.dataset.current = String(target);

  function frame() {
    const elapsed = Date.now() - start;
    const progress = Math.min(elapsed / duration, 1);
    // cubic-bezier(0.16, 1, 0.3, 1) approx
    const eased = 1 - Math.pow(1 - progress, 3);
    el.textContent = (initial + delta * eased).toFixed(decimals);
    if (progress < 1) requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
}

// ============ Sparkline (inline SVG) ============
export function sparklineSVG(data, options = {}) {
  if (!data || data.length < 2) return '';
  const w = options.width || 80;
  const h = options.height || 32;
  const color = options.color || 'currentColor';
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const points = data.map((v, i) => {
    const x = (i / (data.length - 1)) * w;
    const y = h - ((v - min) / range) * h;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
  return `<svg class="sparkline" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">
    <polyline points="${points}" fill="none" stroke="${color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
  </svg>`;
}

// ============ Date helpers ============
export function getTodayKST() {
  const now = new Date();
  const kst = new Date(now.getTime() + 9 * 60 * 60 * 1000);
  return kst.toISOString().slice(0, 10).replace(/-/g, '');
}

export function getRecentDates(n) {
  const out = [];
  const now = new Date();
  for (let i = 0; i < n; i++) {
    const d = new Date(now.getTime() + 9 * 60 * 60 * 1000 - i * 86400000);
    out.push(d.toISOString().slice(0, 10).replace(/-/g, ''));
  }
  return out;
}

// ============ Render helpers ============
export function showSection(id) {
  $$('.sub-pane').forEach(p => p.classList.remove('active'));
  const pane = document.getElementById(id);
  if (pane) pane.classList.add('active');
}

export function activateTab(btn, group = '.sub-tab') {
  if (!btn) return;
  const target = btn.closest('.sub-tabs') || document;
  $$(group, target).forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
}
