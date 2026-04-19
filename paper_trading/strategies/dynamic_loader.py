"""
동적 전략 로더 - strategy_config.json 기반으로 전략을 동적 로드 및 등록
"""

import os
import sys
import json
import importlib
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))

# 경로 설정
NTB_ROOT = Path(__file__).parent.parent.parent
ARENA_DIR = NTB_ROOT / "data" / "arena"
CONFIG_PATH = ARENA_DIR / "strategy_config.json"

# strategy-lab 경로: 환경변수 → 하위 디렉토리 → 형제 디렉토리 순으로 탐색
def _find_strategy_lab():
    env = os.environ.get("STRATEGY_LAB_ROOT")
    if env and Path(env).exists():
        return Path(env)
    # GitHub Actions: checkout path로 NTB_ROOT/strategy-lab에 위치
    sub = NTB_ROOT / "strategy-lab"
    if sub.exists():
        return sub
    # 로컬: 형제 디렉토리
    sibling = NTB_ROOT.parent / "strategy-lab"
    if sibling.exists():
        return sibling
    return sibling  # 폴백

STRATEGY_LAB_ROOT = _find_strategy_lab()


def load_config() -> Optional[dict]:
    """strategy_config.json 로드"""
    if not CONFIG_PATH.exists():
        return None
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_config(config: dict):
    """strategy_config.json 저장"""
    config["updated_at"] = datetime.now(KST).strftime("%Y-%m-%dT%H:%M:%S")
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def load_strategy_class(entry: dict):
    """단일 전략 클래스를 동적으로 로드"""
    source = entry["source"]
    module_path = entry["module_path"]
    class_name = entry["class_name"]

    if source == "lab":
        lab_root = str(STRATEGY_LAB_ROOT)
        if not Path(lab_root).exists():
            raise FileNotFoundError(f"strategy-lab 경로 없음: {lab_root}")
        if lab_root not in sys.path:
            sys.path.insert(0, lab_root)

    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def load_enabled_strategies(config: Optional[dict] = None) -> Dict[str, type]:
    """enabled=true인 전략만 로드하고 StrategyRegistry에 등록"""
    from .registry import StrategyRegistry

    if config is None:
        config = load_config()
    if not config:
        return {}

    loaded = {}
    for strategy_id, entry in config.get("strategies", {}).items():
        if not entry.get("enabled", False):
            continue

        # NTB 전략은 __init__.py에서 이미 import됨 (register 데코레이터)
        if entry["source"] == "ntb":
            existing = StrategyRegistry.get(strategy_id)
            if existing:
                loaded[strategy_id] = existing
                continue

        # Lab 전략은 동적 로드 + 수동 등록
        try:
            cls = load_strategy_class(entry)
            if strategy_id not in StrategyRegistry._strategies:
                StrategyRegistry.register(cls)
            loaded[strategy_id] = cls
            print(f"  [Loader] ✓ {strategy_id} ({entry['source']})")
        except Exception as e:
            print(f"  [Loader] ✗ {strategy_id} 로드 실패: {e}")

    return loaded


def activate_strategy(strategy_id: str, config: Optional[dict] = None) -> bool:
    """전략 ON (enabled=true + team_id 할당)"""
    if config is None:
        config = load_config()
    if not config or strategy_id not in config["strategies"]:
        return False

    entry = config["strategies"][strategy_id]
    if entry["enabled"]:
        return True  # 이미 활성

    entry["enabled"] = True
    entry["activated_at"] = datetime.now(KST).strftime("%Y-%m-%d")

    # team_id가 없으면 pool에서 할당
    if not entry.get("team_id"):
        pool = config.get("team_id_pool", [])
        if not pool:
            print(f"  [Loader] team_id pool 소진! {strategy_id} 활성화 실패")
            entry["enabled"] = False
            return False
        entry["team_id"] = pool.pop(0)

    save_config(config)
    print(f"  [Loader] {strategy_id} 활성화 → {entry['team_id']}")
    return True


def deactivate_strategy(strategy_id: str, config: Optional[dict] = None) -> bool:
    """전략 OFF (enabled=false, team_id/데이터 보존)"""
    if config is None:
        config = load_config()
    if not config or strategy_id not in config["strategies"]:
        return False

    entry = config["strategies"][strategy_id]
    if not entry["enabled"]:
        return True  # 이미 비활성

    entry["enabled"] = False
    # team_id와 activated_at은 보존 (재활성화 시 이어감)

    save_config(config)
    print(f"  [Loader] {strategy_id} 비활성화 (데이터 보존)")
    return True


def get_enabled_team_configs(config: Optional[dict] = None) -> dict:
    """enabled 전략을 TEAM_CONFIGS 형식으로 반환"""
    if config is None:
        config = load_config()
    if not config:
        return {}

    team_configs = {}
    for strategy_id, entry in config.get("strategies", {}).items():
        if not entry.get("enabled") or not entry.get("team_id"):
            continue
        team_id = entry["team_id"]
        team_configs[team_id] = {
            "team_id": team_id,
            "team_name": entry["team_name"],
            "strategy_id": strategy_id,
            "emoji": entry.get("emoji", "⚪"),
            "description": entry.get("description", ""),
        }

    return team_configs
