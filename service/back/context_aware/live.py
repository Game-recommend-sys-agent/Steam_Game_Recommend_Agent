"""
(7) Live

- 입력: Steam News GetNewsForApp 응답(newsitems)
- 출력: LiveContext (days_since_last_news, update/event 카운트, liveness_signal)

구현 상세/요구 사항은 `docs/context_aware_5to8.md`를 참고.
"""

from __future__ import annotations

import math
import time
from typing import Any, Final

DEFAULT_WINDOW_DAYS: Final[int] = 30
DEFAULT_TAU_DAYS: Final[float] = 30.0
DEFAULT_ALPHA: Final[float] = 0.05


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


def _clamp01(x: float) -> float:
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


def _classify_feedlabel(feedlabel: Any) -> str:
    """
    문서 권장: feedlabel이 불안정할 수 있어 소문자 포함 매칭 기반 분류.
    """
    s = str(feedlabel or "").lower()
    if "update" in s or "patch" in s:
        return "update"
    if "event" in s or "sale" in s:
        return "event"
    return "other"


def compute_live_context(
    interim: dict[str, Any],
    *,
    now_ts: int | None = None,
    window_days: int = DEFAULT_WINDOW_DAYS,
    tau_days: float = DEFAULT_TAU_DAYS,
    alpha: float = DEFAULT_ALPHA,
) -> dict[str, Any]:
    """
    (7) LiveContext 계산.

    입력은 `game_signals.build_interim_game_signals()`가 만드는 interim 포맷을 가정한다.
    MVP에서는 contents 분석 없이 date/feedlabel 중심으로 파생값을 만든다.
    """
    now_ts = int(now_ts or time.time())

    src = interim if isinstance(interim, dict) else {}
    news = src.get("news", {}) if isinstance(src.get("news"), dict) else {}
    items = news.get("newsitems") if isinstance(news.get("newsitems"), list) else []

    dates = [
        _safe_int(it.get("date"), 0)
        for it in items
        if isinstance(it, dict) and _safe_int(it.get("date"), 0) > 0
    ]
    if not dates:
        return {
            "days_since_last_news": None,
            "recent_update_count": 0,
            "recent_event_count": 0,
            "liveness_signal": 0.0,
        }

    last_date = max(dates)
    days_since_last = max(0, int((now_ts - last_date) / 86400))

    window_days = max(0, int(window_days))
    window_start = now_ts - window_days * 86400

    update_count = 0
    event_count = 0
    for it in items:
        if not isinstance(it, dict):
            continue
        dt = _safe_int(it.get("date"), 0)
        if dt <= 0 or dt < window_start:
            continue
        cls = _classify_feedlabel(it.get("feedlabel"))
        if cls == "update":
            update_count += 1
        elif cls == "event":
            event_count += 1

    # 문서 권장 예시: exp(-days/tau) + alpha*(counts)
    tau_days = float(tau_days)
    alpha = float(alpha)
    recency_term = math.exp(-days_since_last / max(tau_days, 1e-6))
    count_term = alpha * (update_count + event_count)
    liveness_signal = _clamp01(recency_term + count_term)

    return {
        "days_since_last_news": days_since_last,
        "recent_update_count": int(update_count),
        "recent_event_count": int(event_count),
        "liveness_signal": _safe_float(liveness_signal, 0.0),
    }

