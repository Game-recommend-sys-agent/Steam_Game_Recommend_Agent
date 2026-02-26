"""
(4) Play Style Context — 플레이 스타일 컨텍스트

- 입력: interim user_games rows (playtime_forever_hours, playtime_2weeks_hours)
- 출력: PlayStyleContext
  - avg_lifetime_hours: float   (게임당 평균 누적 플레이 시간)
  - focus_score: float          (0~1, 최근 집중도)
  - play_style: "Focused" | "Diverse"
  - difficulty_pref: "Challenging" | "Relaxed"

구현 상세/요구 사항은 docs/03-context_aware.md 4.2 를 참고.

핵심 파생 로직 (문서 기준):
- avg_lifetime_hours = sum(playtime_forever_hours) / game_count
- focus_score       = sum(playtime_2weeks_hours) / sum(playtime_forever_hours)
  (최근 2주 플레이 / 전체 누적 플레이 → 집중도)
- play_style        = "Focused" if focus_score > 0.3 else "Diverse"
- difficulty_pref   = "Challenging" if focus_score > 0.2 else "Relaxed"
"""

from __future__ import annotations

from typing import Any


def _safe_float(x: Any, default: float = 0.0) -> float:
    if x is None:
        return default
    try:
        return float(x)
    except (ValueError, TypeError):
        return default


def compute_play_style_context(owned_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """
    (4) PlayStyleContext 계산.

    - owned_rows: behavior_activity.normalize_owned_games_rows() 또는
                  interim user_games table의 rows 형식을 가정.
                  필수 필드: playtime_forever_hours, playtime_2weeks_hours (float).
    """
    rows = [r for r in owned_rows if isinstance(r, dict)]

    total_forever = sum(_safe_float(r.get("playtime_forever_hours"), 0.0) for r in rows)
    total_2weeks = sum(_safe_float(r.get("playtime_2weeks_hours"), 0.0) for r in rows)

    # 게임당 평균 누적 플레이 시간
    avg_lifetime_hours = round(total_forever / len(rows), 1) if rows else 0.0

    # 집중도: 최근 2주 / 전체 누적 (total_forever == 0이면 0)
    focus_score = round(total_2weeks / total_forever, 3) if total_forever > 0.0 else 0.0
    focus_score = max(0.0, min(1.0, focus_score))

    play_style = "Focused" if focus_score > 0.3 else "Diverse"
    difficulty_pref = "Challenging" if focus_score > 0.2 else "Relaxed"

    return {
        "avg_lifetime_hours": float(avg_lifetime_hours),
        "focus_score": float(focus_score),
        "play_style": play_style,
        "difficulty_pref": difficulty_pref,
    }
