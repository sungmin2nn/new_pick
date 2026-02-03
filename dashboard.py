"""
뉴스 트레이딩 봇 대시보드 (모바일 최적화)
- 단일 페이지 통합 뷰
- Entry Check (매수 여부) 표시
- Actual vs Virtual 결과 비교
- 스케줄 모니터링 및 수동 실행
"""

import streamlit as st
import pandas as pd
import json
import os
import glob
import requests
from datetime import datetime, timedelta
import pytz

# GitHub 설정
GITHUB_REPO = "sungmin2nn/new_pick"
GITHUB_RAW_BASE = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main"
GITHUB_API_BASE = f"https://api.github.com/repos/{GITHUB_REPO}"

# 한국 시간대
KST = pytz.timezone('Asia/Seoul')

# 페이지 설정 (모바일 최적화)
st.set_page_config(
    page_title="뉴스봇",
    page_icon="📈",
    layout="centered",  # 모바일에 적합
    initial_sidebar_state="collapsed"
)

# 모바일 최적화 스타일
st.markdown("""
<style>
    /* 전체 폰트 크기 조정 */
    .main { padding: 0.5rem; }

    /* 헤더 */
    .header {
        font-size: 1.5rem;
        font-weight: bold;
        color: #667eea;
        padding: 0.5rem 0;
        border-bottom: 2px solid #667eea;
        margin-bottom: 1rem;
    }

    /* 카드 스타일 */
    .card {
        background: #f8f9fa;
        border-radius: 12px;
        padding: 1rem;
        margin-bottom: 0.75rem;
        border-left: 4px solid #667eea;
    }
    .card-profit { border-left-color: #e74c3c; background: #fff5f5; }
    .card-loss { border-left-color: #3498db; background: #f0f7ff; }
    .card-skip { border-left-color: #95a5a6; background: #f5f5f5; }

    /* 수익/손실 텍스트 */
    .profit { color: #e74c3c; font-weight: bold; }
    .loss { color: #3498db; font-weight: bold; }
    .neutral { color: #666; }

    /* 태그 */
    .tag {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 10px;
        font-size: 0.7rem;
        margin: 2px;
    }
    .tag-buy { background: #e8f5e9; color: #2e7d32; }
    .tag-skip { background: #ffebee; color: #c62828; }
    .tag-profit { background: #ffebee; color: #c62828; }
    .tag-loss { background: #e3f2fd; color: #1565c0; }
    .tag-none { background: #f5f5f5; color: #757575; }
    .tag-theme { background: #e8f4fd; color: #1976d2; }

    /* 통계 박스 */
    .stat-box {
        text-align: center;
        padding: 0.5rem;
        background: white;
        border-radius: 8px;
        margin: 0.25rem;
    }
    .stat-value { font-size: 1.5rem; font-weight: bold; }
    .stat-label { font-size: 0.7rem; color: #666; }

    /* 스킵 사유 */
    .skip-reason {
        background: #fff3cd;
        padding: 0.5rem;
        border-radius: 6px;
        font-size: 0.8rem;
        margin-top: 0.5rem;
    }

    /* 숨김 처리 */
    #MainMenu, footer, header { visibility: hidden; }
    .stDeployButton { display: none; }

    /* 버튼 간격 */
    .stButton > button { width: 100%; }

    /* 스케줄 상태 카드 */
    .schedule-card {
        background: white;
        border-radius: 10px;
        padding: 0.75rem;
        margin-bottom: 0.5rem;
        border: 1px solid #e0e0e0;
    }
    .schedule-ok { border-left: 4px solid #4caf50; }
    .schedule-warn { border-left: 4px solid #ff9800; }
    .schedule-error { border-left: 4px solid #f44336; }
    .schedule-pending { border-left: 4px solid #9e9e9e; }

    .status-dot {
        display: inline-block;
        width: 10px;
        height: 10px;
        border-radius: 50%;
        margin-right: 6px;
    }
    .dot-green { background: #4caf50; }
    .dot-yellow { background: #ff9800; }
    .dot-red { background: #f44336; }
    .dot-gray { background: #9e9e9e; }
</style>
""", unsafe_allow_html=True)


# ============================================================
# 데이터 로드 함수
# ============================================================
def fetch_github(path):
    """GitHub에서 JSON 로드"""
    try:
        url = f"{GITHUB_RAW_BASE}/{path}"
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            return r.json()
    except:
        pass
    return None


def fetch_github_intraday_list():
    """GitHub intraday 파일 목록"""
    try:
        api_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/data/intraday"
        r = requests.get(api_url, timeout=10)
        if r.status_code == 200:
            return [f['name'] for f in r.json() if f['name'].startswith('intraday_')]
    except:
        pass
    return []


def get_workflow_runs(workflow_name, limit=5):
    """GitHub Actions 워크플로우 실행 기록 조회"""
    try:
        url = f"{GITHUB_API_BASE}/actions/workflows/{workflow_name}/runs?per_page={limit}"
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            return r.json().get('workflow_runs', [])
    except:
        pass
    return []


def trigger_workflow(workflow_name, token):
    """GitHub Actions 워크플로우 수동 트리거"""
    try:
        url = f"{GITHUB_API_BASE}/actions/workflows/{workflow_name}/dispatches"
        headers = {
            'Authorization': f'token {token}',
            'Accept': 'application/vnd.github.v3+json'
        }
        data = {'ref': 'main'}
        r = requests.post(url, headers=headers, json=data, timeout=10)
        return r.status_code == 204
    except:
        return False


def check_data_status(date_str, data_type='morning'):
    """특정 날짜의 데이터 존재 여부 확인"""
    if data_type == 'morning':
        # morning_candidates.json의 날짜 확인
        today_data = load_today('remote')
        if today_data:
            return today_data.get('date', '') == date_str
        return False
    else:
        # intraday 데이터 확인
        intraday = load_intraday('remote')
        return date_str in intraday


def get_schedule_status():
    """오늘 스케줄 실행 상태 확인"""
    now = datetime.now(KST)
    today_str = now.strftime('%Y-%m-%d')
    today_ymd = now.strftime('%Y%m%d')

    status = {
        'morning': {
            'name': '장전 스캔',
            'schedule_time': '08:30',
            'workflow': 'morning-scan.yml',
            'status': 'pending',  # pending, running, success, failed, missed
            'last_run': None,
            'data_exists': False,
            'data_count': 0
        },
        'afternoon': {
            'name': '장후 수집',
            'schedule_time': '16:30',
            'workflow': 'afternoon-collect.yml',
            'status': 'pending',
            'last_run': None,
            'data_exists': False,
            'data_count': 0
        }
    }

    # 장전 스캔 상태 확인
    morning_runs = get_workflow_runs('morning-scan.yml', limit=3)
    if morning_runs:
        latest = morning_runs[0]
        run_time = datetime.fromisoformat(latest['created_at'].replace('Z', '+00:00'))
        run_time_kst = run_time.astimezone(KST)

        status['morning']['last_run'] = run_time_kst.strftime('%m/%d %H:%M')

        if run_time_kst.date() == now.date():
            if latest['status'] == 'completed':
                status['morning']['status'] = 'success' if latest['conclusion'] == 'success' else 'failed'
            elif latest['status'] in ['queued', 'in_progress']:
                status['morning']['status'] = 'running'
        elif now.hour >= 9:
            status['morning']['status'] = 'missed'

    # 장전 데이터 확인
    today_data = load_today('remote')
    if today_data and today_data.get('date') == today_str:
        status['morning']['data_exists'] = True
        status['morning']['data_count'] = today_data.get('count', 0)

    # 장후 수집 상태 확인
    afternoon_runs = get_workflow_runs('afternoon-collect.yml', limit=3)
    if afternoon_runs:
        latest = afternoon_runs[0]
        run_time = datetime.fromisoformat(latest['created_at'].replace('Z', '+00:00'))
        run_time_kst = run_time.astimezone(KST)

        status['afternoon']['last_run'] = run_time_kst.strftime('%m/%d %H:%M')

        if run_time_kst.date() == now.date():
            if latest['status'] == 'completed':
                status['afternoon']['status'] = 'success' if latest['conclusion'] == 'success' else 'failed'
            elif latest['status'] in ['queued', 'in_progress']:
                status['afternoon']['status'] = 'running'
        elif now.hour >= 17:
            status['afternoon']['status'] = 'missed'

    # 장후 데이터 확인
    intraday = load_intraday('remote')
    if today_str in intraday:
        status['afternoon']['data_exists'] = True
        status['afternoon']['data_count'] = intraday[today_str].get('count', 0)

    return status


@st.cache_data(ttl=60)
def load_intraday(source='local'):
    """장중 결과 데이터 로드"""
    all_data = {}

    if source == 'remote':
        files = fetch_github_intraday_list()
        for fname in files:
            data = fetch_github(f'data/intraday/{fname}')
            if data:
                date = data.get('date', '')
                date_key = f"{date[:4]}-{date[4:6]}-{date[6:]}" if len(date) == 8 else date
                all_data[date_key] = data
    else:
        base = os.path.dirname(__file__)
        pattern = os.path.join(base, 'data', 'intraday', 'intraday_*.json')
        for filepath in sorted(glob.glob(pattern), reverse=True):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    date = data.get('date', '')
                    date_key = f"{date[:4]}-{date[4:6]}-{date[6:]}" if len(date) == 8 else date
                    all_data[date_key] = data
            except:
                pass

    return all_data


@st.cache_data(ttl=60)
def load_today(source='local'):
    """오늘 선정 종목"""
    if source == 'remote':
        return fetch_github('data/morning_candidates.json')
    try:
        path = os.path.join(os.path.dirname(__file__), 'data', 'morning_candidates.json')
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return None


# ============================================================
# 유틸 함수
# ============================================================
def get_weekday(date_str):
    """요일 반환"""
    weekdays = ['월', '화', '수', '목', '금', '토', '일']
    try:
        if '-' in date_str:
            dt = datetime.strptime(date_str, '%Y-%m-%d')
        else:
            dt = datetime.strptime(date_str, '%Y%m%d')
        return weekdays[dt.weekday()]
    except:
        return ''


def format_pct(val):
    """퍼센트 포맷"""
    if val is None:
        return '-'
    return f"+{val:.2f}%" if val >= 0 else f"{val:.2f}%"


def format_price(val):
    """가격 포맷"""
    if not val:
        return '-'
    return f"{val:,.0f}원"


# ============================================================
# 메인 UI
# ============================================================

# 헤더
col1, col2 = st.columns([3, 1])
with col1:
    st.markdown('<div class="header">📈 뉴스봇</div>', unsafe_allow_html=True)
with col2:
    if st.button("🔄", help="새로고침"):
        st.cache_data.clear()
        st.rerun()

# 데이터 소스 토글
source_col1, source_col2 = st.columns(2)
with source_col1:
    is_remote = st.toggle("GitHub", value=False, help="원격 데이터 사용")
source = 'remote' if is_remote else 'local'

# 데이터 로드
intraday_all = load_intraday(source)
today_data = load_today(source)

# ============================================================
# 스케줄 모니터링 섹션
# ============================================================
with st.expander("🕐 오늘 스케줄 현황", expanded=False):
    schedule_status = get_schedule_status()
    now_kst = datetime.now(KST)

    for key, info in schedule_status.items():
        status = info['status']
        data_ok = info['data_exists']

        # 상태에 따른 스타일
        if status == 'success' and data_ok:
            card_class = 'schedule-ok'
            dot_class = 'dot-green'
            status_text = '✅ 완료'
        elif status == 'running':
            card_class = 'schedule-pending'
            dot_class = 'dot-yellow'
            status_text = '⏳ 실행중'
        elif status == 'failed':
            card_class = 'schedule-error'
            dot_class = 'dot-red'
            status_text = '❌ 실패'
        elif status == 'missed':
            card_class = 'schedule-warn'
            dot_class = 'dot-yellow'
            status_text = '⚠️ 미실행'
        else:
            card_class = 'schedule-pending'
            dot_class = 'dot-gray'
            status_text = '⏸️ 대기'

        # 데이터 상태
        if data_ok:
            data_text = f"✅ {info['data_count']}개"
        else:
            data_text = "❌ 없음"

        st.markdown(f"""
        <div class="schedule-card {card_class}">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <span class="status-dot {dot_class}"></span>
                    <b>{info['name']}</b>
                    <small>({info['schedule_time']})</small>
                </div>
                <div>{status_text}</div>
            </div>
            <div style="margin-top: 0.5rem; font-size: 0.8rem; color: #666;">
                마지막 실행: {info['last_run'] or '-'} | 데이터: {data_text}
            </div>
        </div>
        """, unsafe_allow_html=True)

    # 수동 실행 버튼
    st.markdown("---")
    st.markdown("**수동 실행** (GitHub Token 필요)")

    # GitHub Token 입력 (세션 상태 사용)
    if 'github_token' not in st.session_state:
        st.session_state.github_token = ''

    token = st.text_input(
        "GitHub Personal Access Token",
        type="password",
        value=st.session_state.github_token,
        help="repo, workflow 권한 필요"
    )
    st.session_state.github_token = token

    col1, col2 = st.columns(2)

    with col1:
        morning_disabled = not token or schedule_status['morning']['status'] == 'running'
        if st.button("🌅 장전 스캔", disabled=morning_disabled, key="btn_morning"):
            with st.spinner("트리거 중..."):
                if trigger_workflow('morning-scan.yml', token):
                    st.success("장전 스캔 트리거됨!")
                    st.cache_data.clear()
                else:
                    st.error("실패. 토큰 확인 필요")

    with col2:
        afternoon_disabled = not token or schedule_status['afternoon']['status'] == 'running'
        if st.button("🌆 장후 수집", disabled=afternoon_disabled, key="btn_afternoon"):
            with st.spinner("트리거 중..."):
                if trigger_workflow('afternoon-collect.yml', token):
                    st.success("장후 수집 트리거됨!")
                    st.cache_data.clear()
                else:
                    st.error("실패. 토큰 확인 필요")

    if not token:
        st.caption("💡 토큰 없이도 상태 확인은 가능합니다")

st.markdown("---")

# 날짜 선택
dates = sorted(intraday_all.keys(), reverse=True)
if today_data:
    today_date = today_data.get('date', '')
    if today_date and len(today_date) == 10:
        if today_date not in dates:
            dates.insert(0, today_date)

if dates:
    selected_date = st.selectbox(
        "날짜",
        dates,
        format_func=lambda x: f"{x} ({get_weekday(x)})"
    )
else:
    selected_date = None
    st.warning("데이터 없음")

if not selected_date:
    st.stop()

# ============================================================
# 선택 날짜 데이터 표시
# ============================================================
day_data = intraday_all.get(selected_date)

if not day_data:
    # 오늘 선정만 있는 경우
    if today_data and today_data.get('date') == selected_date:
        st.info("📋 오늘 선정 종목 (결과 대기)")
        candidates = today_data.get('candidates', [])
        for i, stock in enumerate(candidates, 1):
            st.markdown(f"""
            <div class="card">
                <b>{i}. {stock.get('name', '')}</b> ({stock.get('code', '')})<br>
                <small>점수: {stock.get('total_score', 0):.0f}점</small>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.warning("결과 데이터 없음")
    st.stop()

# 결과 데이터 파싱
stocks = day_data.get('stocks', {})
results = []

for code, info in stocks.items():
    pl = info.get('profit_loss_analysis', {})
    entry = pl.get('entry_check', {})

    # 새 포맷인지 확인
    has_entry_check = bool(entry)
    should_buy = entry.get('should_buy', True) if has_entry_check else True
    skip_reason = entry.get('skip_reason', None) if has_entry_check else None

    # 실제/가상 결과
    actual = pl.get('actual_result', {}) if has_entry_check else None
    virtual = pl.get('virtual_result', {}) if has_entry_check else None

    # 하위 호환: 기존 포맷이면 직접 사용
    if not has_entry_check:
        actual = {
            'first_hit': pl.get('first_hit', 'none'),
            'first_hit_time': pl.get('first_hit_time'),
            'closing_percent': pl.get('closing_percent', 0),
            'max_profit_percent': pl.get('max_profit_percent', 0),
            'max_loss_percent': pl.get('max_loss_percent', 0),
        }

    results.append({
        'code': code,
        'name': info.get('name', ''),
        'score': info.get('selection_score', 0),
        'reason': info.get('selection_reason', ''),
        'opening_price': pl.get('opening_price', 0),
        'closing_price': pl.get('closing_price', 0),
        'should_buy': should_buy,
        'skip_reason': skip_reason,
        'entry_check': entry,
        'actual': actual,
        'virtual': virtual,
        'first_hit': actual.get('first_hit', 'none') if actual else 'none',
        'closing_percent': actual.get('closing_percent', 0) if actual else (virtual.get('closing_percent', 0) if virtual else 0),
    })

# ============================================================
# 요약 통계
# ============================================================
total = len(results)
buy_list = [r for r in results if r['should_buy']]
skip_list = [r for r in results if not r['should_buy']]

buy_profit = sum(1 for r in buy_list if r['actual'] and r['actual'].get('first_hit') == 'profit')
buy_loss = sum(1 for r in buy_list if r['actual'] and r['actual'].get('first_hit') == 'loss')

# 전체 (필터 미적용) 가상 승률
all_profit = sum(1 for r in results if (r['actual'] or r['virtual'] or {}).get('first_hit') == 'profit')

st.markdown(f"### {selected_date} ({get_weekday(selected_date)})")

# 통계 카드
stat_cols = st.columns(4)
with stat_cols[0]:
    st.markdown(f"""
    <div class="stat-box">
        <div class="stat-value">{len(buy_list)}/{total}</div>
        <div class="stat-label">매수/전체</div>
    </div>
    """, unsafe_allow_html=True)

with stat_cols[1]:
    win_rate = (buy_profit / len(buy_list) * 100) if buy_list else 0
    st.markdown(f"""
    <div class="stat-box">
        <div class="stat-value" style="color: {'#e74c3c' if win_rate >= 50 else '#666'}">{win_rate:.0f}%</div>
        <div class="stat-label">필터 승률</div>
    </div>
    """, unsafe_allow_html=True)

with stat_cols[2]:
    all_win_rate = (all_profit / total * 100) if total else 0
    st.markdown(f"""
    <div class="stat-box">
        <div class="stat-value">{all_win_rate:.0f}%</div>
        <div class="stat-label">전체 승률</div>
    </div>
    """, unsafe_allow_html=True)

with stat_cols[3]:
    avg_return = sum(r['closing_percent'] for r in buy_list) / len(buy_list) if buy_list else 0
    color = '#e74c3c' if avg_return >= 0 else '#3498db'
    st.markdown(f"""
    <div class="stat-box">
        <div class="stat-value" style="color: {color}">{format_pct(avg_return)}</div>
        <div class="stat-label">평균 수익</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("---")

# ============================================================
# 탭: 매수 종목 / 스킵 종목
# ============================================================
tab1, tab2, tab3 = st.tabs([f"✅ 매수 ({len(buy_list)})", f"⏭️ 스킵 ({len(skip_list)})", "📊 설정"])

# 매수 종목 탭
with tab1:
    if not buy_list:
        st.info("매수 조건 충족 종목 없음")
    else:
        for r in sorted(buy_list, key=lambda x: x['score'], reverse=True):
            actual = r['actual'] or {}
            first_hit = actual.get('first_hit', 'none')
            hit_time = actual.get('first_hit_time', '')

            card_class = 'card-profit' if first_hit == 'profit' else ('card-loss' if first_hit == 'loss' else 'card')

            # 태그
            if first_hit == 'profit':
                result_tag = f'<span class="tag tag-profit">✅ 익절 {hit_time}</span>'
            elif first_hit == 'loss':
                result_tag = f'<span class="tag tag-loss">❌ 손절 {hit_time}</span>'
            else:
                result_tag = '<span class="tag tag-none">⏸️ 미도달</span>'

            closing_pct = actual.get('closing_percent', 0)
            closing_class = 'profit' if closing_pct >= 0 else 'loss'

            st.markdown(f"""
            <div class="{card_class}">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <b>{r['name']}</b> <small>({r['code']})</small>
                    </div>
                    <div>
                        {result_tag}
                    </div>
                </div>
                <div style="margin-top: 0.5rem; font-size: 0.85rem;">
                    <span class="neutral">점수: {r['score']:.0f}점</span> |
                    <span class="neutral">시가: {format_price(r['opening_price'])}</span> |
                    <span class="{closing_class}">종가: {format_pct(closing_pct)}</span>
                </div>
                <div style="margin-top: 0.25rem; font-size: 0.75rem; color: #666;">
                    {r['reason']}
                </div>
            </div>
            """, unsafe_allow_html=True)

# 스킵 종목 탭
with tab2:
    if not skip_list:
        st.info("스킵 종목 없음 (모두 매수)")
    else:
        for r in sorted(skip_list, key=lambda x: x['score'], reverse=True):
            virtual = r['virtual'] or {}
            first_hit = virtual.get('first_hit', 'none')

            # 가상 결과 태그
            if first_hit == 'profit':
                virt_tag = '<span class="tag tag-profit">🔮 (익절)</span>'
            elif first_hit == 'loss':
                virt_tag = '<span class="tag tag-loss">🔮 (손절)</span>'
            else:
                virt_tag = '<span class="tag tag-none">🔮 (미도달)</span>'

            skip_reason = r['skip_reason'] or '조건 미충족'
            closing_pct = virtual.get('closing_percent', 0)

            st.markdown(f"""
            <div class="card card-skip">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <b>{r['name']}</b> <small>({r['code']})</small>
                    </div>
                    <div>
                        <span class="tag tag-skip">⏭️ 스킵</span>
                        {virt_tag}
                    </div>
                </div>
                <div style="margin-top: 0.5rem; font-size: 0.85rem;">
                    <span class="neutral">점수: {r['score']:.0f}점</span> |
                    <span class="neutral">가상 종가: {format_pct(closing_pct)}</span>
                </div>
                <div class="skip-reason">
                    ⚠️ 스킵 사유: {skip_reason}
                </div>
            </div>
            """, unsafe_allow_html=True)

# 설정 탭
with tab3:
    st.markdown("### 📐 점수 배점 (135점)")

    score_weights = {
        '공시': 25, '뉴스': 20, '테마': 10, '거래대금': 20,
        '외국인/기관': 15, '시총': 10, '거래량급증': 15,
        '모멘텀': 5, '회전율': 5, '재료중복': 5, '뉴스시간': 5,
    }

    cols = st.columns(3)
    for i, (k, v) in enumerate(score_weights.items()):
        with cols[i % 3]:
            st.markdown(f"**{k}**: {v}점")

    st.markdown("---")
    st.markdown("### ⚙️ 트레이딩 설정")

    st.markdown("""
    | 항목 | 값 |
    |------|-----|
    | 익절 목표 | +5% |
    | 손절 목표 | -3% |
    | 갭 필터 | ±5% |
    | 거래량 체크 | 09:05 |
    | 최소 거래량 | 평균 50% |
    """)

    st.markdown("---")
    st.markdown("### 📅 자동 스케줄")
    st.markdown("""
    - **08:30** 장전 스캔 (월-금)
    - **16:30** 장후 결과 수집 (월-금)
    """)

    # 최근 7일 실행 히스토리
    st.markdown("---")
    st.markdown("### 📋 최근 실행 기록")

    morning_runs = get_workflow_runs('morning-scan.yml', limit=7)
    afternoon_runs = get_workflow_runs('afternoon-collect.yml', limit=7)

    if morning_runs or afternoon_runs:
        run_history = []

        for run in morning_runs[:7]:
            run_time = datetime.fromisoformat(run['created_at'].replace('Z', '+00:00'))
            run_time_kst = run_time.astimezone(KST)
            status_icon = '✅' if run['conclusion'] == 'success' else ('❌' if run['conclusion'] == 'failure' else '⏳')
            run_history.append({
                '시간': run_time_kst.strftime('%m/%d %H:%M'),
                '작업': '🌅 장전',
                '상태': status_icon,
            })

        for run in afternoon_runs[:7]:
            run_time = datetime.fromisoformat(run['created_at'].replace('Z', '+00:00'))
            run_time_kst = run_time.astimezone(KST)
            status_icon = '✅' if run['conclusion'] == 'success' else ('❌' if run['conclusion'] == 'failure' else '⏳')
            run_history.append({
                '시간': run_time_kst.strftime('%m/%d %H:%M'),
                '작업': '🌆 장후',
                '상태': status_icon,
            })

        # 시간순 정렬
        run_history.sort(key=lambda x: x['시간'], reverse=True)
        st.dataframe(
            pd.DataFrame(run_history[:10]),
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("실행 기록 없음 (GitHub API 호출 필요)")

    # 데이터 현황
    st.markdown("---")
    st.markdown("### 📁 데이터 현황")
    st.info(f"결과 데이터: {len(dates)}일치")

# ============================================================
# 전체 통계 (하단)
# ============================================================
st.markdown("---")

with st.expander("📊 전체 기간 통계"):
    all_results = []
    for date, data in intraday_all.items():
        for code, info in data.get('stocks', {}).items():
            pl = info.get('profit_loss_analysis', {})
            entry = pl.get('entry_check', {})
            has_entry = bool(entry)
            should_buy = entry.get('should_buy', True) if has_entry else True

            actual = pl.get('actual_result', {}) if has_entry else pl

            all_results.append({
                'date': date,
                'should_buy': should_buy,
                'first_hit': actual.get('first_hit', 'none'),
                'closing_percent': actual.get('closing_percent', 0),
            })

    if all_results:
        total_all = len(all_results)
        buy_all = [r for r in all_results if r['should_buy']]

        profit_all = sum(1 for r in all_results if r['first_hit'] == 'profit')
        profit_buy = sum(1 for r in buy_all if r['first_hit'] == 'profit')

        col1, col2 = st.columns(2)
        with col1:
            st.metric("전체 종목", f"{total_all}개")
            st.metric("전체 승률", f"{(profit_all/total_all*100):.1f}%")
        with col2:
            st.metric("매수 종목", f"{len(buy_all)}개")
            st.metric("필터 승률", f"{(profit_buy/len(buy_all)*100):.1f}%" if buy_all else "0%")

        # 필터 효과
        if buy_all and len(buy_all) < total_all:
            filter_effect = (profit_buy/len(buy_all)*100) - (profit_all/total_all*100)
            color = "normal" if filter_effect > 0 else "inverse"
            st.metric("필터 효과", f"{filter_effect:+.1f}%p", delta_color=color)

# 푸터
st.caption("뉴스봇 v2.0 | 모바일 최적화")
