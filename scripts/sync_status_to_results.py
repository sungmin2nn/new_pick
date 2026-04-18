#!/usr/bin/env python3
"""
status_{YYYYMMDD}.json → results.json 동기화 스크립트

장 종료 후 (17:00 KST) 실행되어, 당일 status 파일의 트레이딩 결과를
results.json의 daily_results 배열에 추가한다.

- 이미 해당 날짜가 results.json에 있으면 스킵
- status 파일이 없으면 경고 후 종료
- waiting 상태 종목은 close(장마감 청산)로 처리
"""

import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

KST = timezone(timedelta(hours=9))
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data" / "paper_trading"


def load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"저장 완료: {path}")


def convert_status_to_result(status_data: dict) -> dict | None:
    """status 파일 데이터를 results.json의 daily_results 항목으로 변환."""
    date = status_data.get("date", "")
    stocks = status_data.get("stocks", [])

    if not stocks:
        print(f"[WARN] {date}: stocks 배열이 비어있음")
        return None

    results = []
    wins = 0
    losses = 0
    profit_exits = 0
    loss_exits = 0
    close_exits = 0
    total_return = 0.0

    for s in stocks:
        status = s.get("status", "waiting")
        entry_price = s.get("entry_price", 0)
        current_price = s.get("current_price", 0)
        current_pct = s.get("current_pct", 0.0)
        hit_time = s.get("hit_time")

        # exit_type 결정
        if status == "profit_hit":
            exit_type = "profit"
            profit_exits += 1
        elif status == "loss_hit":
            exit_type = "loss"
            loss_exits += 1
        else:
            # waiting → 장마감 청산(close)으로 처리
            exit_type = "close"
            close_exits += 1

        # 수익 계산
        return_pct = round(current_pct, 2)
        return_amount = round(current_price - entry_price, 0)
        total_return += return_pct

        # 승/패 판정
        if return_pct > 0:
            wins += 1
        elif return_pct < 0:
            losses += 1

        # exit_time: hit_time이 있으면 사용, 없으면 15:20 (장마감)
        if hit_time:
            exit_time = hit_time.replace(":00", "") if hit_time.count(":") == 2 else hit_time
            # "10:50:00" → "10:50"
            parts = hit_time.split(":")
            exit_time = f"{parts[0]}:{parts[1]}"
        else:
            exit_time = "15:20"

        result_item = {
            "code": s.get("code", ""),
            "name": s.get("name", ""),
            "entry_price": entry_price,
            "exit_price": current_price,
            "quantity": 1,
            "return_pct": return_pct,
            "return_amount": int(return_amount),
            "exit_type": exit_type,
            "entry_time": "09:05",
            "exit_time": exit_time,
            "high_price": 0,
            "low_price": 0,
            "max_profit_pct": s.get("max_profit_pct", 0),
            "max_loss_pct": s.get("max_loss_pct", 0),
        }
        results.append(result_item)

    total_trades = len(results)
    win_rate = round((wins / total_trades) * 100, 1) if total_trades > 0 else 0.0
    avg_return = round(total_return / total_trades, 2) if total_trades > 0 else 0.0

    return {
        "date": date,
        "total_trades": total_trades,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "total_return": round(total_return, 2),
        "avg_return": avg_return,
        "profit_exits": profit_exits,
        "loss_exits": loss_exits,
        "close_exits": close_exits,
        "results": results,
    }


def sync(target_date: str | None = None) -> bool:
    """
    특정 날짜 또는 오늘 날짜의 status → results 동기화.

    Args:
        target_date: YYYYMMDD 형식. None이면 오늘 날짜 사용.

    Returns:
        True if 동기화 성공, False otherwise.
    """
    if target_date is None:
        target_date = datetime.now(KST).strftime("%Y%m%d")

    print(f"=== status → results 동기화: {target_date} ===")

    # 1. results.json 로드 (없으면 초기화)
    results_path = DATA_DIR / "results.json"
    if results_path.exists():
        results_data = load_json(results_path)
    else:
        results_data = {"daily_results": []}
        print("[INFO] results.json 없음 → 새로 생성")

    daily_results = results_data.get("daily_results", [])

    # 2. 중복 체크
    existing_dates = {r["date"] for r in daily_results}
    if target_date in existing_dates:
        print(f"[SKIP] {target_date} 이미 results.json에 존재")
        return True

    # 3. status 파일 로드
    status_path = DATA_DIR / f"status_{target_date}.json"
    if not status_path.exists():
        print(f"[WARN] status 파일 없음: {status_path}")
        return False

    status_data = load_json(status_path)
    print(f"  종목 수: {status_data.get('total_stocks', 0)}")
    print(f"  익절: {status_data.get('profit_hit', 0)}, 손절: {status_data.get('loss_hit', 0)}, 대기: {status_data.get('waiting', 0)}")

    # 4. 변환
    day_result = convert_status_to_result(status_data)
    if day_result is None:
        print(f"[ERROR] {target_date} 변환 실패")
        return False

    # 5. 날짜 순서대로 삽입
    daily_results.append(day_result)
    daily_results.sort(key=lambda r: r["date"])
    results_data["daily_results"] = daily_results

    # 6. 저장
    save_json(results_path, results_data)

    print(f"  → 추가 완료: {day_result['total_trades']}건, 승률 {day_result['win_rate']}%, 수익률 {day_result['total_return']}%")
    return True


def backfill() -> int:
    """기존 status 파일 중 results.json에 없는 것들을 모두 동기화."""
    count = 0
    for status_file in sorted(DATA_DIR.glob("status_*.json")):
        date_str = status_file.stem.replace("status_", "")
        if sync(date_str):
            count += 1
    return count


def main():
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg == "--backfill":
            print("=== 백필 모드: 모든 미동기화 status 파일 처리 ===")
            count = backfill()
            print(f"\n총 {count}개 날짜 처리 완료")
        else:
            # 특정 날짜 지정
            sync(arg)
    else:
        # 기본: 오늘 날짜
        sync()


if __name__ == "__main__":
    main()
