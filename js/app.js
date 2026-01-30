// 메인 애플리케이션
const App = {
    async init() {
        console.log('[App] 초기화 시작');

        // 히스토리 로드
        await API.loadHistory();

        // 날짜 셀렉터 업데이트
        this.updateDateSelector();

        // 최초 데이터 로드
        await this.loadData();

        // 이벤트 리스너 등록
        this.setupEventListeners();

        console.log('[App] 초기화 완료');
    },

    updateDateSelector() {
        const select = document.getElementById('filterDate');
        if (!select) return;

        select.innerHTML = '<option value="">최신 데이터</option>';
        API.availableDates.forEach(date => {
            const option = document.createElement('option');
            option.value = date;
            option.textContent = date;
            select.appendChild(option);
        });

        if (API.availableDates.length > 0) {
            select.value = API.availableDates[0];
        }
    },

    async loadData() {
        try {
            const loading = document.getElementById('loading');
            const error = document.getElementById('error');
            const tableDesktop = document.getElementById('stockTable');
            const tableMobile = document.getElementById('mobileCards');

            if (loading) loading.style.display = 'block';
            if (error) error.style.display = 'none';
            if (tableDesktop) tableDesktop.style.display = 'none';
            if (tableMobile) tableMobile.style.display = 'none';

            const selectedDate = document.getElementById('filterDate')?.value || '';
            const stocks = await API.loadStocks(selectedDate);

            // 데스크톱 테이블 렌더링
            Render.renderDesktopTable(stocks);

            // 모바일 카드 렌더링
            Render.renderMobileCards(stocks);

            // 업데이트 시간 표시
            const updateTimeEl = document.getElementById('updateTime');
            if (updateTimeEl) {
                updateTimeEl.textContent = selectedDate || new Date().toLocaleDateString('ko-KR');
            }

            if (loading) loading.style.display = 'none';
            if (tableDesktop) tableDesktop.style.display = 'table';
            if (tableMobile) tableMobile.style.display = 'block';

        } catch (err) {
            console.error('[App] 로드 에러:', err);
            const loading = document.getElementById('loading');
            const error = document.getElementById('error');
            if (loading) loading.style.display = 'none';
            if (error) {
                error.style.display = 'block';
                error.textContent = err.message || '데이터를 불러올 수 없습니다';
            }
        }
    },

    setupEventListeners() {
        // 날짜 필터 변경
        const dateFilter = document.getElementById('filterDate');
        if (dateFilter) {
            dateFilter.addEventListener('change', () => this.loadData());
        }
    }
};

// 페이지 로드 시 실행
document.addEventListener('DOMContentLoaded', () => {
    App.init();
});
