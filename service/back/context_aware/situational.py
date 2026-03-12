"""
(1) Situational Context — 상황/시간 컨텍스트

- 입력: interim user_games rows (playtime_2weeks_hours) + UI 입력(available_mins) + 현재 시각
- 출력: SituationalContext
  - available_time_window: "30m" | "60m" | "120m_plus"
  - available_mins: int
  - average_session_duration_min: float  (최근 2주 플레이 기반 일평균 세션 길이 추정)
  - current_time_context.is_weekend: bool
  - current_time_context.time_of_day: "morning" | "afternoon" | "night" | "late_night"
  - current_time_context.hour: int

구현 상세/요구 사항은 docs/03-context_aware.md 4.1 을 참고.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any


def _safe_float(x: Any, default: float = 0.0) -> float:
    if x is None:
        return default
    try:
        return float(x)
    except (ValueError, TypeError):
        return default


def _classify_time_of_day(hour: int) -> str:
    """
    시간대 분류 (UTC 기준).
    - 06~11: morning
    - 12~17: afternoon
    - 18~23: night
    - 00~05: late_night
    """
    if 6 <= hour < 12:
        return "morning"
    if 12 <= hour < 18:
        return "afternoon"
    if 18 <= hour < 24:
        return "night"
    return "late_night"


def _classify_available_time_window(mins: int) -> str:
    """
    UI 입력 available_mins → 세션 길이 구간 레이블.
    - ≤ 30min → "30m"
    - ≤ 60min → "60m"
    - > 60min → "120m_plus"
    """
    if mins <= 30:
        return "30m"
    if mins <= 60:
        return "60m"
    return "120m_plus"


def compute_situational_context(
    owned_rows: list[dict[str, Any]],
    *,
    available_mins: int = 60,
    now_ts: int | None = None,
) -> dict[str, Any]:
    """
    (1) SituationalContext 계산.

    - owned_rows: behavior_activity.normalize_owned_games_rows() 또는
                  interim user_games table의 rows 형식을 가정.
                  필수 필드: playtime_2weeks_hours (float).
    - available_mins: UI 입력 — 지금 플레이 가능한 시간(분).
    - now_ts: UTC Unix timestamp. 기본값은 현재 시각.

    average_session_duration_min 추정 방법:
    - 최근 2주 플레이 게임(playtime_2weeks_hours > 0)의 시간을 7로 나눠 일평균을 구하고
      다시 분 단위로 변환한다 (playtime_2weeks_hours / 7 * 60).
    - 최근 플레이 기록이 없으면 0.0.
    """
    now_ts = int(now_ts or time.time())
    now = datetime.fromtimestamp(now_ts, tz=timezone.utc)

    rows = [r for r in owned_rows if isinstance(r, dict)]
    recent = [r for r in rows if _safe_float(r.get("playtime_2weeks_hours"), 0.0) > 0.0]

    if recent:
        # 일평균 세션(시간) = playtime_2weeks_hours / 7 → 분 변환
        daily_avg_hours = [_safe_float(r["playtime_2weeks_hours"], 0.0) / 7.0 for r in recent]
        avg_session_min = round(sum(daily_avg_hours) / len(daily_avg_hours) * 60.0, 1)
    else:
        avg_session_min = 0.0

    return {
        "available_time_window": _classify_available_time_window(int(available_mins)),
        "available_mins": int(available_mins),
        "average_session_duration_min": float(avg_session_min),
        "current_time_context": {
            "is_weekend": now.weekday() >= 5,
            "time_of_day": _classify_time_of_day(now.hour),
            "hour": now.hour,
        },
    }
