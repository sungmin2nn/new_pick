"""
헬스체크 & 에러 알림 시스템
- GitHub Actions 실행 상태 확인
- 기대 파일 생성 여부 검증
- 종목 미선정 감지
- 에러 로그 기록 + 텔레그램 알림
"""

import json
import os
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

KST = timezone(timedelta(hours=9))

ARENA_DIR = Path(__file__).parent.parent.parent / "data" / "arena"
DATA_DIR = Path(__file__).parent.parent.parent / "data" / "paper_trading"
HEALTH_LOG_DIR = ARENA_DIR / "healthcheck"


class HealthChecker:
    """헬스체크 & 에러 알림 관리"""

    # 워크플로우별 기대 결과
    EXPECTED_WORKFLOWS = {
        "paper-trading-select": {
            "description": "장전 종목 선정",
            "schedule": "08:00 KST",
            "expected_files": lambda date: [
                DATA_DIR / f"candidates_{date}_all.json",
            ],
        },
        "paper-trading": {
            "description": "장후 최종 결과",
            "schedule": "16:10 KST",
            "expected_files": lambda date: [
                ARENA_DIR / "daily" / date / "arena_report.json",
            ],
        },
        "paper-trading-check": {
            "description": "장중 상태 체크",
            "schedule": "10:00/12:00/14:00 KST",
            "expected_files": lambda date: [
                DATA_DIR / f"status_{date}.json",
            ],
        },
    }

    def __init__(self):
        HEALTH_LOG_DIR.mkdir(parents=True, exist_ok=True)

    def run_check(self, date: str = None) -> dict:
        """
        전체 헬스체크 실행

        Returns:
            체크 결과 (issues 리스트 포함)
        """
        if date is None:
            date = datetime.now(KST).strftime("%Y%m%d")

        now = datetime.now(KST)
        report = {
            "date": date,
            "checked_at": now.strftime("%Y-%m-%d %H:%M:%S"),
            "status": "healthy",
            "checks": [],
            "issues": [],
        }

        # 1. 워크플로우별 파일 생성 체크
        for wf_name, wf_config in self.EXPECTED_WORKFLOWS.items():
            check = self._check_workflow_files(date, wf_name, wf_config, now)
            report["checks"].append(check)
            if check["status"] == "fail":
                report["issues"].append(check)

        # 2. 팀별 종목 선정 체크
        team_check = self._check_team_selections(date)
        report["checks"].append(team_check)
        if team_check["status"] == "fail":
            report["issues"].append(team_check)

        # 3. 아레나 리포트 무결성 체크
        arena_check = self._check_arena_integrity(date)
        report["checks"].append(arena_check)
        if arena_check["status"] == "fail":
            report["issues"].append(arena_check)

        # 4. 포트폴리오 이상 체크 (급격한 손실 등)
        portfolio_check = self._check_portfolios()
        report["checks"].append(portfolio_check)
        if portfolio_check["status"] == "warning":
            report["issues"].append(portfolio_check)

        # 상태 결정
        if any(c["status"] == "fail" for c in report["checks"]):
            report["status"] = "unhealthy"
        elif any(c["status"] == "warning" for c in report["checks"]):
            report["status"] = "warning"

        # 로그 저장
        self._save_log(date, report)

        return report

    def _check_workflow_files(self, date: str, wf_name: str,
                               wf_config: dict, now: datetime) -> dict:
        """워크플로우 기대 파일 체크"""
        check = {
            "check_type": "workflow_files",
            "workflow": wf_name,
            "description": wf_config["description"],
            "status": "pass",
            "details": "",
        }

        expected_files = wf_config["expected_files"](date)
        missing = [str(f) for f in expected_files if not f.exists()]

        if missing:
            # 스케줄 시간 이후인지 확인 (시간 전이면 아직 정상)
            schedule = wf_config["schedule"]
            hour = int(schedule.split(":")[0])

            if now.hour >= hour + 1:  # 1시간 여유
                check["status"] = "fail"
                check["details"] = f"파일 미생성: {', '.join(Path(m).name for m in missing)}"
            else:
                check["status"] = "pass"
                check["details"] = f"아직 실행 전 (예정: {schedule})"
        else:
            check["details"] = "모든 파일 정상"

        return check

    def _check_team_selections(self, date: str) -> dict:
        """팀별 종목 선정 체크"""
        check = {
            "check_type": "team_selections",
            "description": "팀별 종목 선정 여부",
            "status": "pass",
            "details": "",
        }

        from .team import TEAM_CONFIGS
        empty_teams = []

        for team_id, config in TEAM_CONFIGS.items():
            strategy_id = config["strategy_id"]
            candidates_file = DATA_DIR / f"candidates_{date}_{strategy_id}.json"

            if candidates_file.exists():
                with open(candidates_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                count = data.get("count", len(data.get("candidates", [])))
                if count == 0:
                    empty_teams.append(f"{config['team_name']}({strategy_id})")
            # 파일 없으면 아직 실행 전일 수 있으므로 무시

        if empty_teams:
            check["status"] = "fail"
            check["details"] = f"종목 미선정: {', '.join(empty_teams)}"
        else:
            check["details"] = "모든 팀 종목 선정 완료 또는 대기 중"

        return check

    def _check_arena_integrity(self, date: str) -> dict:
        """아레나 리포트 무결성 체크"""
        check = {
            "check_type": "arena_integrity",
            "description": "아레나 리포트 무결성",
            "status": "pass",
            "details": "",
        }

        report_path = ARENA_DIR / "daily" / date / "arena_report.json"
        if not report_path.exists():
            check["details"] = "아레나 리포트 아직 생성 전"
            return check

        try:
            with open(report_path, 'r', encoding='utf-8') as f:
                report = json.load(f)

            errors = []
            if report.get("status") == "error":
                errors.append(f"아레나 실행 에러: {report.get('error', 'unknown')}")

            teams = report.get("teams", {})
            for tid, tdata in teams.items():
                if tdata.get("status") == "error":
                    errors.append(f"{tid} 에러")

            if errors:
                check["status"] = "fail"
                check["details"] = "; ".join(errors)
            else:
                active = sum(1 for t in teams.values() if t.get("status") == "success")
                check["details"] = f"{active}/{len(teams)}팀 정상 실행"

        except json.JSONDecodeError:
            check["status"] = "fail"
            check["details"] = "리포트 JSON 파싱 오류"

        return check

    def _check_portfolios(self) -> dict:
        """포트폴리오 이상 감지"""
        check = {
            "check_type": "portfolio_health",
            "description": "포트폴리오 건전성",
            "status": "pass",
            "details": "",
            "warnings": [],
        }

        from .team import TEAM_CONFIGS

        for team_id in TEAM_CONFIGS:
            pf_path = ARENA_DIR / team_id / "portfolio.json"
            if not pf_path.exists():
                continue

            with open(pf_path, 'r', encoding='utf-8') as f:
                pf = json.load(f)

            # 최대 낙폭 경고 (-20% 이상)
            mdd = pf.get("max_drawdown_pct", 0)
            if mdd >= 20:
                check["warnings"].append(f"{team_id}: MDD {mdd:.1f}% (심각)")
                check["status"] = "warning"
            elif mdd >= 10:
                check["warnings"].append(f"{team_id}: MDD {mdd:.1f}% (주의)")

            # 5연패 이상 경고
            loss_streak = pf.get("loss_streak", 0)
            if loss_streak >= 5:
                check["warnings"].append(f"{team_id}: {loss_streak}연패")
                check["status"] = "warning"

        if check["warnings"]:
            check["details"] = "; ".join(check["warnings"])
        else:
            check["details"] = "모든 팀 포트폴리오 정상"

        return check

    def _save_log(self, date: str, report: dict):
        """헬스체크 로그 저장"""
        log_path = HEALTH_LOG_DIR / f"health_{date}.json"

        # 기존 로그 있으면 누적
        logs = []
        if log_path.exists():
            with open(log_path, 'r', encoding='utf-8') as f:
                existing = json.load(f)
            if isinstance(existing, list):
                logs = existing
            else:
                logs = [existing]

        logs.append(report)

        with open(log_path, 'w', encoding='utf-8') as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)

    def get_logs(self, date: str = None, last_n: int = 7) -> List[dict]:
        """헬스체크 로그 조회"""
        if date:
            log_path = HEALTH_LOG_DIR / f"health_{date}.json"
            if log_path.exists():
                with open(log_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return data if isinstance(data, list) else [data]
            return []

        # 최근 N일
        logs = []
        if HEALTH_LOG_DIR.exists():
            files = sorted(HEALTH_LOG_DIR.glob("health_*.json"), reverse=True)
            for f in files[:last_n]:
                with open(f, 'r', encoding='utf-8') as fh:
                    data = json.load(fh)
                if isinstance(data, list):
                    logs.extend(data)
                else:
                    logs.append(data)
        return logs

    def format_telegram_alert(self, report: dict) -> Optional[str]:
        """
        텔레그램 알림 메시지 생성
        이슈가 있을 때만 메시지 반환
        """
        if report["status"] == "healthy":
            return None

        lines = []
        if report["status"] == "unhealthy":
            lines.append("<b>\U0001f6a8 Arena 헬스체크 - 이상 감지!</b>")
        else:
            lines.append("<b>\u26a0\ufe0f Arena 헬스체크 - 경고</b>")

        lines.append(f"날짜: {report['date']}")
        lines.append(f"체크 시간: {report['checked_at']}")
        lines.append("")

        for issue in report.get("issues", []):
            status_icon = "\u274c" if issue["status"] == "fail" else "\u26a0\ufe0f"
            lines.append(f"{status_icon} <b>{issue['description']}</b>")
            lines.append(f"   {issue['details']}")
            lines.append("")

        return "\n".join(lines)

    def format_dashboard_data(self) -> dict:
        """대시보드용 데이터"""
        recent_logs = self.get_logs(last_n=14)

        # 일별 상태 집계
        daily_status = {}
        for log in recent_logs:
            date = log.get("date", "")
            if date not in daily_status:
                daily_status[date] = {
                    "date": date,
                    "status": log["status"],
                    "checks": len(log.get("checks", [])),
                    "issues": len(log.get("issues", [])),
                    "details": [i.get("details", "") for i in log.get("issues", [])],
                }

        return {
            "recent_status": list(daily_status.values()),
            "total_checks": len(recent_logs),
            "unhealthy_count": sum(1 for l in recent_logs if l.get("status") == "unhealthy"),
            "warning_count": sum(1 for l in recent_logs if l.get("status") == "warning"),
        }


def main():
    """CLI"""
    import argparse

    parser = argparse.ArgumentParser(description='Arena 헬스체크')
    parser.add_argument('command', choices=['check', 'logs', 'alert'],
                        help='명령')
    parser.add_argument('--date', '-d', type=str, default=None)

    args = parser.parse_args()
    checker = HealthChecker()

    if args.command == 'check':
        report = checker.run_check(date=args.date)
        print(json.dumps(report, ensure_ascii=False, indent=2))

        # 이슈 있으면 텔레그램 전송
        alert = checker.format_telegram_alert(report)
        if alert:
            try:
                from telegram_notifier import TelegramNotifier
                notifier = TelegramNotifier()
                if notifier.is_configured():
                    notifier.send_message(alert)
                    print("\n[HealthCheck] 텔레그램 알림 전송 완료")
            except Exception as e:
                print(f"\n[HealthCheck] 텔레그램 전송 실패: {e}")

    elif args.command == 'logs':
        logs = checker.get_logs(date=args.date)
        for log in logs:
            status_icon = "\u2705" if log["status"] == "healthy" else \
                          "\u274c" if log["status"] == "unhealthy" else "\u26a0\ufe0f"
            print(f"{status_icon} {log['date']} {log['checked_at']} - {log['status']}")
            for issue in log.get("issues", []):
                print(f"   - {issue['description']}: {issue['details']}")

    elif args.command == 'alert':
        report = checker.run_check(date=args.date)
        alert = checker.format_telegram_alert(report)
        if alert:
            print(alert)
        else:
            print("[HealthCheck] 이상 없음 - 알림 없음")


if __name__ == "__main__":
    main()
