"""
거래비용 모델
==============
한국 주식 단타 매매의 실전 거래비용을 반영.

2026년 기준:
- 증권사 수수료: 매수 0.015% + 매도 0.015% = 0.03%
  (MTS/HTS 평균. 증권사/우대마다 0.005~0.025% 범위)
- 증권거래세: 매도 시 0.18% (코스피) / 0.18% (코스닥, 2026년)
  ※ 농특세 0.15%는 별도 아님 (포함)
- 슬리피지: 예약 매수(시초가/종가)는 ~0, 장중 성립가는 0.05~0.1%

Round-trip (매수 + 매도) 기준:
  - 예약 매수: 0.03% + 0.18% = 0.21% (최저)
  - 장중 매수 (슬리피지 포함): 0.03% + 0.18% + 0.1% ≈ 0.31%

참고:
- 2020년 거래세 0.25% → 2026년 0.18%로 인하됨
- 개인 공매도는 별도 수수료
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


# 2026년 기준 상수
COMMISSION_BUY_PCT = 0.015   # 매수 수수료 0.015%
COMMISSION_SELL_PCT = 0.015  # 매도 수수료 0.015%
TRADE_TAX_KOSPI_PCT = 0.18   # 코스피 거래세 0.18%
TRADE_TAX_KOSDAQ_PCT = 0.18  # 코스닥 거래세 0.18%

# 슬리피지 기본값 (진입 방식별)
SLIPPAGE_MARKET_OPEN = 0.0    # 예약 매수 시초가 체결
SLIPPAGE_MARKET_CLOSE = 0.0   # 종가 동시호가 체결
SLIPPAGE_INTRADAY_LIMIT = 0.05   # 장중 지정가 (0.05%)
SLIPPAGE_INTRADAY_MARKET = 0.15  # 장중 시장가 (0.15%)


@dataclass
class TransactionCostResult:
    """거래비용 계산 결과."""
    gross_return_pct: float           # 수수료 반영 전
    net_return_pct: float             # 수수료/거래세/슬리피지 반영 후
    total_cost_pct: float             # 총 비용
    commission_pct: float             # 수수료만
    trade_tax_pct: float              # 거래세만
    slippage_pct: float               # 슬리피지만


def calculate_net_return(
    entry_price: float,
    exit_price: float,
    market: str = "KOSPI",
    entry_slippage_pct: float = SLIPPAGE_MARKET_OPEN,
    exit_slippage_pct: float = SLIPPAGE_MARKET_CLOSE,
) -> TransactionCostResult:
    """
    단일 거래의 순 수익률 계산.

    Args:
        entry_price: 진입가 (시초가 또는 지정가)
        exit_price: 청산가
        market: 'KOSPI' or 'KOSDAQ'
        entry_slippage_pct: 진입 슬리피지 % (예약매수=0, 장중=0.05~0.15)
        exit_slippage_pct: 청산 슬리피지 %

    Returns:
        TransactionCostResult
    """
    if entry_price <= 0:
        return TransactionCostResult(0, 0, 0, 0, 0, 0)

    # 명목 수익률
    gross_return = (exit_price - entry_price) / entry_price * 100

    # 슬리피지 반영
    # 매수: 진입가가 slippage만큼 불리하게 (비싸게) 체결됨
    # 매도: 청산가가 slippage만큼 불리하게 (싸게) 체결됨
    adjusted_entry = entry_price * (1 + entry_slippage_pct / 100)
    adjusted_exit = exit_price * (1 - exit_slippage_pct / 100)

    slippage_impact = ((adjusted_exit - adjusted_entry) / adjusted_entry
                       - (exit_price - entry_price) / entry_price) * 100

    # 수수료 (매수 + 매도)
    commission = COMMISSION_BUY_PCT + COMMISSION_SELL_PCT

    # 거래세 (매도 시에만)
    trade_tax = (
        TRADE_TAX_KOSPI_PCT if market.upper() == "KOSPI"
        else TRADE_TAX_KOSDAQ_PCT
    )

    # 총 비용 (%)
    total_cost = commission + trade_tax - slippage_impact

    # 순 수익률 = 명목 수익률 - 총 비용
    net_return = gross_return - total_cost

    return TransactionCostResult(
        gross_return_pct=round(gross_return, 4),
        net_return_pct=round(net_return, 4),
        total_cost_pct=round(total_cost, 4),
        commission_pct=round(commission, 4),
        trade_tax_pct=round(trade_tax, 4),
        slippage_pct=round(-slippage_impact, 4),
    )


def apply_costs_batch(trades: list, market_map: Optional[dict] = None) -> list:
    """
    여러 거래에 일괄 비용 반영.

    Args:
        trades: [{'entry_price', 'exit_price', 'code', ...}]
        market_map: {code: market}. None이면 모두 KOSPI 가정.

    Returns:
        각 trade에 'net_return_pct' 필드 추가된 리스트
    """
    market_map = market_map or {}
    for t in trades:
        market = market_map.get(t.get("code"), "KOSPI")
        result = calculate_net_return(
            entry_price=t.get("entry_price", 0),
            exit_price=t.get("exit_price", 0),
            market=market,
        )
        t["net_return_pct"] = result.net_return_pct
        t["cost_pct"] = result.total_cost_pct
        t["commission_pct"] = result.commission_pct
        t["trade_tax_pct"] = result.trade_tax_pct
    return trades


__all__ = [
    "TransactionCostResult",
    "calculate_net_return",
    "apply_costs_batch",
    "COMMISSION_BUY_PCT",
    "COMMISSION_SELL_PCT",
    "TRADE_TAX_KOSPI_PCT",
    "TRADE_TAX_KOSDAQ_PCT",
    "SLIPPAGE_MARKET_OPEN",
    "SLIPPAGE_MARKET_CLOSE",
]
