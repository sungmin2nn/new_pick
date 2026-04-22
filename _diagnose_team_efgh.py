"""
진단 전용 스크립트 (부작용 없음)
- StrategyRegistry.run_all(date=20260422)를 로컬에서 재실행
- team_e/f/g/h 전략의 실제 후보 개수 관찰
- 포트폴리오/리더보드/arena_report 쓰지 않음
- Python 3.9 호환: largecap_contrarian(PEP604 문법) import를 stub으로 우회
"""
import sys
import types
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

# --- Python 3.9 호환 우회: largecap_contrarian은 이미 비활성(enabled=False)이라
# 동적 로더에서도 로드 안 하고, ntb 패키지 __init__.py에서만 unconditional import가 문제.
# stub 모듈을 sys.modules에 주입해 import 자체를 건너뜀.
_stub = types.ModuleType("paper_trading.strategies.largecap_contrarian")
class _DummyStrategy:
    STRATEGY_ID = "largecap_contrarian"
_stub.LargecapContrarianStrategy = _DummyStrategy
sys.modules["paper_trading.strategies.largecap_contrarian"] = _stub

from paper_trading.strategies.dynamic_loader import load_enabled_strategies, load_config
from paper_trading.strategies import StrategyRegistry
from paper_trading.multi_strategy_runner import _resolve_fetch_date

print("=" * 70)
print("진단: team_e/f/g/h 전략 재실행 (부작용 없음)")
print("=" * 70)

config = load_config()
loaded = load_enabled_strategies(config)
print(f"\n[Config] enabled 전략 {len(loaded)}개 로드됨")
for sid in loaded:
    print(f"  - {sid}")

TARGET = "20260422"
fetch_date = _resolve_fetch_date(TARGET)
print(f"\n[FetchDate] target={TARGET}, resolved={fetch_date}")

print("\n" + "=" * 70)
print("StrategyRegistry.run_all() 재실행")
print("=" * 70)
results = StrategyRegistry.run_all(date=fetch_date, top_n=5)

print("\n" + "=" * 70)
print("결과 요약")
print("=" * 70)
for sid in sorted(results.keys()):
    r = results[sid]
    cands = r.candidates if r else []
    names = [c.name for c in cands[:3]]
    print(f"  {sid}: {len(cands)}건  {names if names else ''}")

print("\n[관심 4전략 (team_e/f/g/h)]")
for sid in ['frontier_gap', 'volatility_breakout_lw', 'turtle_breakout_short', 'sector_rotation']:
    r = results.get(sid)
    if r is None:
        print(f"  {sid}: [UNLOADED — 레지스트리에 없음]")
    else:
        print(f"  {sid}: count={len(r.candidates)}")
