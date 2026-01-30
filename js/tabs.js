// 탭 전환 관리
const Tabs = {
    init() {
        const tabButtons = document.querySelectorAll('.tab-button');
        tabButtons.forEach(button => {
            button.addEventListener('click', (e) => this.switchTab(e.target.id));
        });
    },

    switchTab(buttonId) {
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
        }
    }
};
