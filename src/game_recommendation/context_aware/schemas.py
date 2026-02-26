"""
Context-aware 공용 스키마.

각 타입 별칭은 해당 모듈의 compute_*_context() 함수 반환 형태를 나타낸다.

유저 컨텍스트 (1~5):
- SituationalContext  : (1) situational.py   — 상황/시간
- SentimentContext    : (2) sentiment.py      — 심리/감성 (LLM)
- BehaviorContext     : (5) behavior_activity.py — 최근 행동/활성도
- PlayStyleContext    : (4) play_style.py     — 플레이 스타일

게임 컨텍스트 (6~8):
- QualityTrustContext : (6) quality_trust.py  — 완성도/신뢰도
- LiveContext         : (7) live.py           — 라이브 상태
- DiscountContext     : (8) discount.py       — 할인

참고: `docs/03-context_aware.md`, `docs/03-context_aware_5to8.md`
"""

from __future__ import annotations

from typing import Any

# 유저 컨텍스트
SituationalContext = dict[str, Any]
SentimentContext = dict[str, Any]
PlayStyleContext = dict[str, Any]
BehaviorContext = dict[str, Any]

# 게임 컨텍스트
QualityTrustContext = dict[str, Any]
LiveContext = dict[str, Any]
DiscountContext = dict[str, Any]

