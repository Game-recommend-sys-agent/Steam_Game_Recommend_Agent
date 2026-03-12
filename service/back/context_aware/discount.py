"""
(8) Discount

- 입력: Steam Store appdetails.price_overview.discount_percent (+ optional currency/final/initial)
- 출력: DiscountContext (discount_percent, discount_signal)

구현 상세/요구 사항은 `docs/context_aware_5to8.md`를 참고.
"""

from __future__ import annotations

from typing import Any


def _safe_int(x: Any, default: int = 0) -> int:
    if x is None:
        return default
    try:
        return int(x)
    except (ValueError, TypeError):
        return default


def _safe_float(x: Any, default: float = 0.0) -> float:
    if x is None:
        return default
    try:
        return float(x)
    except (ValueError, TypeError):
        return default


def compute_discount_context(interim: dict[str, Any]) -> dict[str, Any]:
    """
    (8) DiscountContext 계산.

    - 입력(interim): `appdetails.discount_percent` (없으면 0으로 취급)
    - 출력: `discount_percent`(0~100), `discount_signal`(0~1)
    """
    src = interim if isinstance(interim, dict) else {}
    appdetails = src.get("appdetails", {}) if isinstance(src.get("appdetails"), dict) else {}

    discount_percent = _safe_int(appdetails.get("discount_percent"), 0)
    discount_percent = max(0, min(100, discount_percent))

    return {
        "discount_percent": int(discount_percent),
        "discount_signal": _safe_float(discount_percent / 100.0, 0.0),
    }

