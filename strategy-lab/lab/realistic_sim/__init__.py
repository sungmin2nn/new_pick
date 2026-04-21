"""
Realistic Simulation Package
=============================
일봉 시뮬의 한계를 극복하는 3-Tier 시뮬레이션:

- Tier 1: 분봉 실측 (intraday_sim) — 가장 정확, 6일 한계
- Tier 2: 확률적 일봉 (probability_model) — 장기, 확률 가중
- Tier 3: Calibration + 통계 검증 (calibrator, walk_forward, bootstrap)

공통:
- transaction_costs: 수수료/거래세 반영
- benchmark: KODEX 200 alpha
"""
