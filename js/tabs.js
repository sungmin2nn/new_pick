// 탭 전환 관리
const Tabs = {
    init() {
        console.log('[Tabs] 초기화 시작');
        const tabButtons = document.querySelectorAll('.tab-button');
        console.log('[Tabs] 탭 버튼 개수:', tabButtons.length);

        tabButtons.forEach(button => {
            button.addEventListener('click', (e) => this.switchTab(e.target.id));
        });

        // 초기 상태 확인
        const contents = document.querySelectorAll('.tab-content');
        console.log('[Tabs] 탭 컨텐츠 개수:', contents.length);
        contents.forEach(content => {
            console.log(`[Tabs] ${content.id}: active=${content.classList.contains('active')}`);
        });
    },

    switchTab(buttonId) {
        console.log('[Tabs] 탭 전환:', buttonId);

        // 탭 버튼 활성화 상태 변경
        document.querySelectorAll('.tab-button').forEach(btn => {
            btn.classList.remove('active');
        });
        document.getElementById(buttonId).classList.add('active');

        // 탭 컨텐츠 표시 변경
        document.querySelectorAll('.tab-content').forEach(content => {
            content.classList.remove('active');
        });

        const tabMap = {
            'stocksTabBtn': 'stocksTab',
            'backtestTabBtn': 'backtestTab',
            'systemTabBtn': 'systemTab'
        };

        const targetTab = tabMap[buttonId];
        if (targetTab) {
            document.getElementById(targetTab).classList.add('active');
            console.log('[Tabs] 활성화된 탭:', targetTab);
        }
    }
};
