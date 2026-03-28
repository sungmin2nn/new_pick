"""
프로젝트 자동 로깅 시스템
- 의사결정, 전략 변경, 매매 기록, Q&A 자동 저장
- 대화 컨텍스트 로드 기능
- 자동 리포트 생성
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any

# 기본 경로 설정
BASE_DIR = Path(__file__).parent
LOGS_DIR = BASE_DIR / "logs"
DOCS_DIR = BASE_DIR / "docs"
DATA_DIR = BASE_DIR / "data"

# 디렉토리 생성
LOGS_DIR.mkdir(exist_ok=True)
DOCS_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)


class ProjectLogger:
    """프로젝트 전체 로깅을 담당하는 클래스"""

    def __init__(self):
        self.decisions_file = LOGS_DIR / "decisions.json"
        self.strategy_changes_file = LOGS_DIR / "strategy_changes.json"
        self.daily_trades_file = LOGS_DIR / "daily_trades.json"
        self.qa_history_file = LOGS_DIR / "qa_history.json"
        self.session_log_file = LOGS_DIR / "session_logs.json"
        self.rules_file = LOGS_DIR / "rules.json"

        # 파일 초기화
        self._init_files()

    def _init_files(self):
        """로그 파일 초기화"""
        default_files = {
            self.decisions_file: {"decisions": []},
            self.strategy_changes_file: {"changes": []},
            self.daily_trades_file: {"trades": []},
            self.qa_history_file: {"qa_list": []},
            self.session_log_file: {"sessions": []},
            self.rules_file: {"rules": [], "constraints": []},
        }

        for file_path, default_content in default_files.items():
            if not file_path.exists():
                self._save_json(file_path, default_content)

    def _load_json(self, file_path: Path) -> dict:
        """JSON 파일 로드"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save_json(self, file_path: Path, data: dict):
        """JSON 파일 저장"""
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)

    # ==========================================
    # 1. 의사결정 기록
    # ==========================================

    def log_decision(self,
                     title: str,
                     description: str,
                     reason: str,
                     alternatives: List[str] = None,
                     impact: str = None,
                     category: str = "general"):
        """
        의사결정 기록

        Args:
            title: 결정 제목 (예: "대형주 역추세 전략 채택")
            description: 결정 내용 상세
            reason: 결정 사유
            alternatives: 검토한 대안들
            impact: 예상 영향
            category: 카테고리 (strategy, parameter, system, rule)
        """
        data = self._load_json(self.decisions_file)

        decision = {
            "id": len(data.get("decisions", [])) + 1,
            "timestamp": datetime.now().isoformat(),
            "date": datetime.now().strftime("%Y-%m-%d"),
            "title": title,
            "description": description,
            "reason": reason,
            "alternatives": alternatives or [],
            "impact": impact,
            "category": category,
            "status": "active"  # active, superseded, reverted
        }

        data.setdefault("decisions", []).append(decision)
        self._save_json(self.decisions_file, data)

        print(f"[LOG] 의사결정 기록됨: {title}")
        return decision

    def get_decisions(self, category: str = None, limit: int = None) -> List[dict]:
        """의사결정 조회"""
        data = self._load_json(self.decisions_file)
        decisions = data.get("decisions", [])

        if category:
            decisions = [d for d in decisions if d.get("category") == category]

        decisions = sorted(decisions, key=lambda x: x.get("timestamp", ""), reverse=True)

        if limit:
            decisions = decisions[:limit]

        return decisions

    # ==========================================
    # 2. 전략 변경 기록
    # ==========================================

    def log_strategy_change(self,
                           strategy_name: str,
                           change_type: str,
                           before: dict,
                           after: dict,
                           reason: str,
                           backtest_result: dict = None):
        """
        전략 변경 기록

        Args:
            strategy_name: 전략명
            change_type: 변경 유형 (created, modified, deprecated, activated)
            before: 변경 전 설정
            after: 변경 후 설정
            reason: 변경 사유
            backtest_result: 백테스트 결과
        """
        data = self._load_json(self.strategy_changes_file)

        change = {
            "id": len(data.get("changes", [])) + 1,
            "timestamp": datetime.now().isoformat(),
            "date": datetime.now().strftime("%Y-%m-%d"),
            "strategy_name": strategy_name,
            "change_type": change_type,
            "before": before,
            "after": after,
            "reason": reason,
            "backtest_result": backtest_result
        }

        data.setdefault("changes", []).append(change)
        self._save_json(self.strategy_changes_file, data)

        print(f"[LOG] 전략 변경 기록됨: {strategy_name} ({change_type})")
        return change

    def get_strategy_history(self, strategy_name: str = None) -> List[dict]:
        """전략 변경 이력 조회"""
        data = self._load_json(self.strategy_changes_file)
        changes = data.get("changes", [])

        if strategy_name:
            changes = [c for c in changes if c.get("strategy_name") == strategy_name]

        return sorted(changes, key=lambda x: x.get("timestamp", ""), reverse=True)

    # ==========================================
    # 3. 일일 매매 기록
    # ==========================================

    def log_daily_trade(self,
                        date: str,
                        selections: List[dict],
                        results: List[dict],
                        strategy_used: str,
                        market_condition: dict = None):
        """
        일일 매매 기록

        Args:
            date: 거래일 (YYYY-MM-DD)
            selections: 선정 종목 리스트
            results: 매매 결과 리스트
            strategy_used: 사용 전략
            market_condition: 시장 상황 (코스피 등락률 등)
        """
        data = self._load_json(self.daily_trades_file)

        # 해당 날짜 기존 기록 확인
        existing = next((t for t in data.get("trades", []) if t.get("date") == date), None)

        trade_record = {
            "date": date,
            "timestamp": datetime.now().isoformat(),
            "strategy_used": strategy_used,
            "market_condition": market_condition,
            "selections": selections,
            "results": results,
            "summary": self._calculate_daily_summary(results)
        }

        if existing:
            # 기존 기록 업데이트
            idx = data["trades"].index(existing)
            data["trades"][idx] = trade_record
        else:
            data.setdefault("trades", []).append(trade_record)

        self._save_json(self.daily_trades_file, data)

        print(f"[LOG] 일일 매매 기록됨: {date} ({len(selections)}종목)")
        return trade_record

    def _calculate_daily_summary(self, results: List[dict]) -> dict:
        """일일 매매 요약 계산"""
        if not results:
            return {"total_trades": 0}

        returns = [r.get("return_pct", 0) for r in results]
        wins = len([r for r in returns if r > 0])

        return {
            "total_trades": len(results),
            "wins": wins,
            "losses": len(results) - wins,
            "win_rate": wins / len(results) * 100 if results else 0,
            "total_return": sum(returns),
            "avg_return": sum(returns) / len(returns) if returns else 0,
            "best_trade": max(returns) if returns else 0,
            "worst_trade": min(returns) if returns else 0,
        }

    def get_trades(self, start_date: str = None, end_date: str = None) -> List[dict]:
        """매매 기록 조회"""
        data = self._load_json(self.daily_trades_file)
        trades = data.get("trades", [])

        if start_date:
            trades = [t for t in trades if t.get("date", "") >= start_date]
        if end_date:
            trades = [t for t in trades if t.get("date", "") <= end_date]

        return sorted(trades, key=lambda x: x.get("date", ""), reverse=True)

    # ==========================================
    # 4. Q&A 기록
    # ==========================================

    def log_qa(self,
               question: str,
               answer: str,
               category: str = "general",
               importance: str = "normal",
               tags: List[str] = None):
        """
        Q&A 기록

        Args:
            question: 질문
            answer: 답변
            category: 카테고리 (strategy, backtest, implementation, etc.)
            importance: 중요도 (critical, high, normal, low)
            tags: 태그 목록
        """
        data = self._load_json(self.qa_history_file)

        qa = {
            "id": len(data.get("qa_list", [])) + 1,
            "timestamp": datetime.now().isoformat(),
            "date": datetime.now().strftime("%Y-%m-%d"),
            "question": question,
            "answer": answer,
            "category": category,
            "importance": importance,
            "tags": tags or []
        }

        data.setdefault("qa_list", []).append(qa)
        self._save_json(self.qa_history_file, data)

        print(f"[LOG] Q&A 기록됨: {question[:30]}...")
        return qa

    def get_qa(self, category: str = None, importance: str = None) -> List[dict]:
        """Q&A 조회"""
        data = self._load_json(self.qa_history_file)
        qa_list = data.get("qa_list", [])

        if category:
            qa_list = [q for q in qa_list if q.get("category") == category]
        if importance:
            qa_list = [q for q in qa_list if q.get("importance") == importance]

        return sorted(qa_list, key=lambda x: x.get("timestamp", ""), reverse=True)

    # ==========================================
    # 5. 규칙/제약 기록
    # ==========================================

    def log_rule(self,
                 rule_name: str,
                 rule_type: str,
                 description: str,
                 conditions: dict,
                 reason: str,
                 status: str = "active"):
        """
        규칙 기록

        Args:
            rule_name: 규칙명
            rule_type: 유형 (entry, exit, filter, risk)
            description: 설명
            conditions: 조건 상세
            reason: 규칙 설정 사유
            status: 상태 (active, inactive, testing)
        """
        data = self._load_json(self.rules_file)

        # 기존 규칙 확인 (같은 이름이면 업데이트)
        existing = next((r for r in data.get("rules", []) if r.get("rule_name") == rule_name), None)

        rule = {
            "rule_name": rule_name,
            "rule_type": rule_type,
            "description": description,
            "conditions": conditions,
            "reason": reason,
            "status": status,
            "created_at": existing.get("created_at") if existing else datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }

        if existing:
            idx = data["rules"].index(existing)
            data["rules"][idx] = rule
        else:
            data.setdefault("rules", []).append(rule)

        self._save_json(self.rules_file, data)

        print(f"[LOG] 규칙 기록됨: {rule_name}")
        return rule

    def log_constraint(self,
                       constraint_name: str,
                       value: Any,
                       reason: str):
        """
        제약조건 기록

        Args:
            constraint_name: 제약명 (예: "max_stocks", "initial_capital")
            value: 값
            reason: 설정 사유
        """
        data = self._load_json(self.rules_file)

        existing = next((c for c in data.get("constraints", [])
                        if c.get("constraint_name") == constraint_name), None)

        constraint = {
            "constraint_name": constraint_name,
            "value": value,
            "reason": reason,
            "updated_at": datetime.now().isoformat()
        }

        if existing:
            idx = data["constraints"].index(existing)
            data["constraints"][idx] = constraint
        else:
            data.setdefault("constraints", []).append(constraint)

        self._save_json(self.rules_file, data)

        print(f"[LOG] 제약조건 기록됨: {constraint_name} = {value}")
        return constraint

    def get_rules(self, rule_type: str = None, status: str = "active") -> List[dict]:
        """규칙 조회"""
        data = self._load_json(self.rules_file)
        rules = data.get("rules", [])

        if rule_type:
            rules = [r for r in rules if r.get("rule_type") == rule_type]
        if status:
            rules = [r for r in rules if r.get("status") == status]

        return rules

    def get_constraints(self) -> List[dict]:
        """제약조건 조회"""
        data = self._load_json(self.rules_file)
        return data.get("constraints", [])

    # ==========================================
    # 6. 세션 로그
    # ==========================================

    def start_session(self, session_type: str = "development"):
        """세션 시작 로그"""
        data = self._load_json(self.session_log_file)

        session = {
            "session_id": len(data.get("sessions", [])) + 1,
            "start_time": datetime.now().isoformat(),
            "session_type": session_type,
            "activities": [],
            "end_time": None,
            "summary": None
        }

        data.setdefault("sessions", []).append(session)
        self._save_json(self.session_log_file, data)

        print(f"[LOG] 세션 시작: #{session['session_id']}")
        return session

    def log_activity(self, activity: str, details: dict = None):
        """세션 내 활동 로그"""
        data = self._load_json(self.session_log_file)

        if data.get("sessions"):
            current_session = data["sessions"][-1]
            if not current_session.get("end_time"):
                current_session.setdefault("activities", []).append({
                    "timestamp": datetime.now().isoformat(),
                    "activity": activity,
                    "details": details
                })
                self._save_json(self.session_log_file, data)

    def end_session(self, summary: str = None):
        """세션 종료 로그"""
        data = self._load_json(self.session_log_file)

        if data.get("sessions"):
            current_session = data["sessions"][-1]
            if not current_session.get("end_time"):
                current_session["end_time"] = datetime.now().isoformat()
                current_session["summary"] = summary
                self._save_json(self.session_log_file, data)
                print(f"[LOG] 세션 종료: #{current_session['session_id']}")


class ContextLoader:
    """대화 시작 시 컨텍스트 로드"""

    def __init__(self):
        self.logger = ProjectLogger()
        self.knowledge_base_file = DOCS_DIR / "PROJECT_KNOWLEDGE_BASE.md"

    def load_context(self) -> dict:
        """전체 컨텍스트 로드"""
        return {
            "knowledge_base": self._load_knowledge_base(),
            "recent_decisions": self.logger.get_decisions(limit=5),
            "active_rules": self.logger.get_rules(status="active"),
            "constraints": self.logger.get_constraints(),
            "recent_trades": self.logger.get_trades()[:7],  # 최근 7일
            "important_qa": self.logger.get_qa(importance="critical") +
                          self.logger.get_qa(importance="high"),
            "strategy_history": self.logger.get_strategy_history()[:5],
        }

    def _load_knowledge_base(self) -> str:
        """지식 베이스 로드"""
        if self.knowledge_base_file.exists():
            with open(self.knowledge_base_file, 'r', encoding='utf-8') as f:
                return f.read()
        return ""

    def get_summary(self) -> str:
        """컨텍스트 요약 생성"""
        ctx = self.load_context()

        summary_lines = [
            "=" * 60,
            "프로젝트 컨텍스트 요약",
            "=" * 60,
            "",
            f"[최근 의사결정 {len(ctx['recent_decisions'])}건]"
        ]

        for d in ctx['recent_decisions'][:3]:
            summary_lines.append(f"  - {d['date']}: {d['title']}")

        summary_lines.extend([
            "",
            f"[활성 규칙 {len(ctx['active_rules'])}개]"
        ])

        for r in ctx['active_rules'][:5]:
            summary_lines.append(f"  - {r['rule_name']}: {r['description'][:40]}...")

        summary_lines.extend([
            "",
            f"[제약조건 {len(ctx['constraints'])}개]"
        ])

        for c in ctx['constraints']:
            summary_lines.append(f"  - {c['constraint_name']}: {c['value']}")

        if ctx['recent_trades']:
            summary_lines.extend([
                "",
                f"[최근 매매 기록]"
            ])
            for t in ctx['recent_trades'][:3]:
                s = t.get('summary', {})
                summary_lines.append(
                    f"  - {t['date']}: {s.get('total_trades', 0)}건, "
                    f"승률 {s.get('win_rate', 0):.1f}%"
                )

        summary_lines.append("")
        summary_lines.append("=" * 60)

        return "\n".join(summary_lines)

    def print_context(self):
        """컨텍스트 출력"""
        print(self.get_summary())


# ==========================================
# 초기 데이터 설정 함수
# ==========================================

def initialize_project_logs():
    """프로젝트 로그 초기화 및 기존 결정사항 기록"""
    logger = ProjectLogger()

    # 기존 의사결정 기록
    logger.log_decision(
        title="대형주 역추세 전략 채택",
        description="10개 전략 비교 백테스트 결과, 대형주 역추세 전략이 3년 연속 양수 수익률로 최고 성과",
        reason="3년 평균 +313% 수익률, 승률 44.9%, 위기 상황에서도 상대적 안정성",
        alternatives=["중소형 역추세 (+23.7%)", "복합 전략 (+41.7%)", "모멘텀 (-27%)"],
        impact="기존 대형주+뉴스 전략 폐기, 새 전략으로 전환",
        category="strategy"
    )

    logger.log_decision(
        title="익절/손절 파라미터 +3%/-1.5% 선정",
        description="파라미터 최적화 테스트 결과 가장 높은 수익률 조합",
        reason="R:R 비율 2:1, 연간 수익률 +757%, 손절 빠르게 하여 손실 최소화",
        alternatives=["+3%/-2% (+452%)", "+5%/-3% (+166%)", "+5%/-2% (+321%)"],
        impact="매매 규칙의 핵심 파라미터로 적용",
        category="parameter"
    )

    logger.log_decision(
        title="페이퍼 트레이딩 우선 결정",
        description="실매매 전 1~3개월 페이퍼 트레이딩 수행",
        reason="백테스트 ≠ 실제 매매, 슬리피지/체결 실패 검증 필요, 리스크 없이 전략 개선",
        alternatives=["즉시 소액 실매매", "더 긴 백테스트만 진행"],
        impact="Phase 2로 페이퍼 트레이딩 시스템 구축 예정",
        category="system"
    )

    # 전략 변경 기록
    logger.log_strategy_change(
        strategy_name="대형주 역추세",
        change_type="created",
        before={},
        after={
            "min_price": 50000,
            "max_change": -1.0,
            "min_trading_value": 50000000000,
            "profit_target": 3.0,
            "loss_target": -1.5
        },
        reason="10개 전략 비교 백테스트에서 최고 성과",
        backtest_result={
            "period": "2022-2024",
            "total_trades": 3799,
            "win_rate": 44.9,
            "annual_return_avg": 313
        }
    )

    # 규칙 기록
    logger.log_rule(
        rule_name="종목선정_가격필터",
        rule_type="filter",
        description="주가 5만원 이상 종목만 선정",
        conditions={"min_price": 50000, "max_price": 500000},
        reason="대형주 필터링, 유동성 확보, 변동성 적정 수준 유지"
    )

    logger.log_rule(
        rule_name="종목선정_하락필터",
        rule_type="filter",
        description="전일 -1% 이상 하락 종목만 선정",
        conditions={"max_change": -1.0},
        reason="역추세 전략의 핵심 조건, 평균 회귀 기대"
    )

    logger.log_rule(
        rule_name="종목선정_거래대금필터",
        rule_type="filter",
        description="거래대금 500억원 이상",
        conditions={"min_trading_value": 50000000000},
        reason="유동성 확보, 슬리피지 최소화"
    )

    logger.log_rule(
        rule_name="매수_시가진입",
        rule_type="entry",
        description="당일 시가(09:00~09:05)에 매수",
        conditions={"entry_time": "09:00-09:05", "entry_type": "market_open"},
        reason="역추세 반등을 빠르게 포착"
    )

    logger.log_rule(
        rule_name="매도_익절",
        rule_type="exit",
        description="매수가 대비 +3% 도달 시 즉시 매도",
        conditions={"profit_target_pct": 3.0},
        reason="목표 수익 확보, R:R 2:1 유지"
    )

    logger.log_rule(
        rule_name="매도_손절",
        rule_type="exit",
        description="매수가 대비 -1.5% 도달 시 즉시 매도",
        conditions={"loss_target_pct": -1.5},
        reason="손실 최소화, 빠른 손절로 자본 보존"
    )

    logger.log_rule(
        rule_name="매도_시간청산",
        rule_type="exit",
        description="14:30까지 미도달 시 종가 청산",
        conditions={"exit_deadline": "14:30"},
        reason="당일 매매 원칙, 오버나이트 리스크 회피"
    )

    logger.log_rule(
        rule_name="시장폭락_매매중단",
        rule_type="risk",
        description="코스피 -3% 이상 하락일 매매 중단",
        conditions={"kospi_drop_threshold": -3.0},
        reason="극단적 폭락 시 역추세도 부진 (백테스트 검증)",
        status="testing"
    )

    # 제약조건 기록
    logger.log_constraint("initial_capital", 1000000, "소액으로 시작하여 리스크 관리")
    logger.log_constraint("max_stocks", 5, "분산 투자 + 관리 가능 범위")
    logger.log_constraint("max_position_pct", 20, "종목당 최대 비중 20%")
    logger.log_constraint("daily_loss_limit_pct", -3, "일일 최대 손실 -3%")
    logger.log_constraint("monthly_loss_limit_pct", -10, "월간 최대 손실 -10% 도달 시 1주 휴식")

    # Q&A 기록
    logger.log_qa(
        question="1년 백테스트로 충분한가?",
        answer="부족함. 최소 2-3년, 권장 5년 이상. 3년 백테스트 실행 결과 3년 모두 양수로 유효성 검증됨.",
        category="backtest",
        importance="high",
        tags=["백테스트", "검증기간"]
    )

    logger.log_qa(
        question="하루에 몇 종목을 매매하나?",
        answer="2024년 11월 기준 평균 6.2개, 최소 1개, 최대 13개. 권장: 최대 5개로 제한.",
        category="trading",
        importance="high",
        tags=["종목수", "자본배분"]
    )

    logger.log_qa(
        question="코로나나 사회적 이슈도 반영되나?",
        answer="현재 미반영 (순수 기술적 분석만 사용). 극단적 폭락 외에는 대체로 작동. 시장 폭락 필터 추가 예정.",
        category="strategy",
        importance="critical",
        tags=["뉴스", "이벤트", "필터"]
    )

    logger.log_qa(
        question="페이퍼 트레이딩 후 실매매 가능한가?",
        answer="가능. Phase 1(페이퍼 1-3개월) → Phase 2(검증 1-3개월) → Phase 3(소액 실매매) → Phase 4(본격 운영)",
        category="implementation",
        importance="high",
        tags=["페이퍼트레이딩", "로드맵"]
    )

    logger.log_qa(
        question="다중 전략 비교가 필요한가?",
        answer="필수. 시장 상황별 최적 전략이 다름. 권장: 3-5개 전략 동시 추적 (대형주 역추세 메인, 중소형 역추세 서브, 복합 전략 대안)",
        category="strategy",
        importance="high",
        tags=["다중전략", "포트폴리오"]
    )

    print("\n[초기화 완료] 기존 의사결정 및 규칙이 로그에 기록되었습니다.")
    return logger


# ==========================================
# CLI 인터페이스
# ==========================================

def main():
    """CLI 메인 함수"""
    import sys

    if len(sys.argv) < 2:
        print("사용법: python project_logger.py [명령]")
        print("  init     - 로그 초기화 및 기존 결정사항 기록")
        print("  context  - 현재 컨텍스트 출력")
        print("  summary  - 프로젝트 요약 출력")
        return

    command = sys.argv[1]

    if command == "init":
        initialize_project_logs()

    elif command == "context":
        loader = ContextLoader()
        loader.print_context()

    elif command == "summary":
        loader = ContextLoader()
        ctx = loader.load_context()

        print("\n=== 프로젝트 요약 ===")
        print(f"총 의사결정: {len(loader.logger.get_decisions())}건")
        print(f"활성 규칙: {len(ctx['active_rules'])}개")
        print(f"제약조건: {len(ctx['constraints'])}개")
        print(f"전략 변경: {len(loader.logger.get_strategy_history())}건")
        print(f"Q&A 기록: {len(loader.logger.get_qa())}건")
        print(f"매매 기록: {len(loader.logger.get_trades())}일")


if __name__ == "__main__":
    main()
