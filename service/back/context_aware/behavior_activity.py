"""
(5) Behavior / Activity

- 입력: Steam OwnedGames / RecentlyPlayed 기반 playtime 및 last played 시그널
- 출력: BehaviorContext (최근성 게이팅, activity_state, anchor appids 등)

구현 상세/요구 사항은 `docs/context_aware_5to8.md`를 참고.
"""

from __future__ import annotations


import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


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


def _minutes_to_hours(minutes: Any) -> float:
    return _safe_int(minutes, 0) / 60.0


@dataclass(frozen=True)
class UserBehaviorPaths:
    raw_dir: Path = Path("data/raw")
    interim_dir: Path = Path("data/interim")
    processed_dir: Path = Path("data/processed")


def raw_owned_games_path(steam_id: str, *, paths: UserBehaviorPaths) -> Path:
    return paths.raw_dir / "owned_games" / f"{steam_id}.json"


def interim_user_games_path(steam_id: str, *, paths: UserBehaviorPaths) -> Path:
    return paths.interim_dir / "user_games" / f"{steam_id}.json"


def processed_behavior_context_path(steam_id: str, *, paths: UserBehaviorPaths) -> Path:
    return paths.processed_dir / "user_behavior" / f"{steam_id}.json"


def load_raw_owned_games(steam_id: str, *, paths: UserBehaviorPaths) -> dict[str, Any]:
    """
    2.7.2 규칙에 따른 OwnedGames raw 파일을 읽는다.
    - data/raw/owned_games/{steam_id}.json
    """
    return _read_json(raw_owned_games_path(steam_id, paths=paths))


def normalize_owned_games_rows(raw_payload: dict[str, Any]) -> list[dict[str, Any]]:
    """
    docs/context_aware_5to8.md 2.6.2 규칙:
    - minutes → hours
    - rtime_last_played == 0 또는 결측이면 None
    """
    response = raw_payload.get("response", {}) if isinstance(raw_payload, dict) else {}
    games = response.get("games", []) if isinstance(response, dict) else []
    rows: list[dict[str, Any]] = []
    if not isinstance(games, list):
        return rows

    for g in games:
        if not isinstance(g, dict):
            continue
        appid = _safe_int(g.get("appid"), 0)
        if appid <= 0:
            continue
        rtime = _safe_int(g.get("rtime_last_played"), 0)
        rows.append(
            {
                "appid": appid,
                "playtime_forever_hours": _safe_float(
                    _minutes_to_hours(g.get("playtime_forever")), 0.0
                ),
                "playtime_2weeks_hours": _safe_float(
                    _minutes_to_hours(g.get("playtime_2weeks")), 0.0
                ),
                "rtime_last_played_ts": (rtime if rtime > 0 else None),
            }
        )
    return rows


def build_interim_user_games_table(
    steam_id: str,
    raw_owned_games_payload: dict[str, Any],
    *,
    paths: UserBehaviorPaths,
    now_ts: int | None = None,
) -> dict[str, Any]:
    now_ts = int(now_ts or time.time())
    rows = normalize_owned_games_rows(raw_owned_games_payload)
    return {
        "meta": {"steam_id": steam_id, "generated_at": now_ts},
        "steam_id": steam_id,
        "rows": rows,
    }


def write_interim_user_games_table(
    steam_id: str, table: dict[str, Any], *, paths: UserBehaviorPaths
) -> Path:
    out = interim_user_games_path(steam_id, paths=paths)
    _atomic_write_json(out, table)
    return out


def load_interim_user_games_table(steam_id: str, *, paths: UserBehaviorPaths) -> dict[str, Any]:
    return _read_json(interim_user_games_path(steam_id, paths=paths))


def _days_since(ts: int, *, now_ts: int) -> int:
    return max(0, int((now_ts - ts) / 86400))


def compute_behavior_context(*args, **kwargs) -> dict:
    """
    docs/context_aware_5to8.md 4.2 권장:
    - recent_2weeks_hours, total_lifetime_hours, avg_recent_play_hours
    - activity_state(active/cooling_off/dormant) with X/Y settings
    - (선택) context_anchor_appids

    호환성을 위해 *args/**kwargs 형태는 유지하되, 권장 파라미터는 kwargs로 받는다.
    """
    owned_rows: list[dict[str, Any]] = kwargs.get("owned_rows") or (args[0] if args else [])
    now_ts = int(kwargs.get("now_ts") or time.time())
    active_threshold_hours = float(kwargs.get("active_threshold_hours", 5.0))
    cooling_off_days = int(kwargs.get("cooling_off_days", 14))
    include_anchors = bool(kwargs.get("include_anchors", True))
    max_anchors = int(kwargs.get("max_anchors", 10))
    include_debug_log = bool(kwargs.get("include_debug_log", False))

    rows = owned_rows if isinstance(owned_rows, list) else []

    p2w_list = [
        _safe_float(r.get("playtime_2weeks_hours"), 0.0)
        for r in rows
        if isinstance(r, dict)
    ]
    life_list = [
        _safe_float(r.get("playtime_forever_hours"), 0.0)
        for r in rows
        if isinstance(r, dict)
    ]

    recent_2weeks_hours = float(sum(p2w_list))
    total_lifetime_hours = float(sum(life_list))

    recent_nonzero = [h for h in p2w_list if h > 0.0]
    avg_recent_play_hours = float(sum(recent_nonzero) / len(recent_nonzero)) if recent_nonzero else 0.0

    last_played_candidates: list[int] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        ts = r.get("rtime_last_played_ts")
        ts_i = _safe_int(ts, 0) if ts is not None else 0
        if ts_i > 0:
            last_played_candidates.append(ts_i)

    days_since_last_played: int | None = None
    if last_played_candidates:
        days_since_last_played = _days_since(max(last_played_candidates), now_ts=now_ts)
    inferred_recent_by_2weeks = False
    # raw에서 rtime_last_played가 결측인 케이스가 실제로 존재함(privacy/옵션/샘플 raw 등).
    # 이때 playtime_2weeks > 0이면 "최근 2주 내 플레이"는 확실하므로,
    # activity_state 게이팅에 한해 최근성 근거로 사용한다.
    if days_since_last_played is None and recent_2weeks_hours > 0.0:
        inferred_recent_by_2weeks = True

    if recent_2weeks_hours > active_threshold_hours:
        activity_state = "active"
    elif (days_since_last_played is not None and days_since_last_played <= cooling_off_days) or (
        inferred_recent_by_2weeks
    ):
        activity_state = "cooling_off"
    else:
        activity_state = "dormant"

    ctx: dict[str, Any] = {
        "recent_2weeks_hours": _safe_float(recent_2weeks_hours, 0.0),
        "total_lifetime_hours": _safe_float(total_lifetime_hours, 0.0),
        "avg_recent_play_hours": _safe_float(avg_recent_play_hours, 0.0),
        "activity_state": activity_state,
    }

    if include_anchors:
        ctx["context_anchor_appids"] = extract_context_anchor_appids(
            rows, now_ts=now_ts, max_anchors=max_anchors
        )

    if include_debug_log:
        ctx["_debug"] = {
            "now_ts": now_ts,
            "active_threshold_hours_X": active_threshold_hours,
            "cooling_off_days_Y": cooling_off_days,
            "days_since_last_played": days_since_last_played,
            "inferred_recent_by_playtime_2weeks": inferred_recent_by_2weeks,
            "anchors_max": max_anchors,
        }

    return ctx


def extract_context_anchor_appids(*args, **kwargs) -> list[int]:
    """
    docs/context_aware_5to8.md 4.2.C 예시 기준:
    - 1순위: playtime_2weeks_hours > 0
    - 2순위: playtime_2weeks_hours == 0 이더라도
      days_since_last_played <= 3 AND playtime_forever_hours >= 80h 같은 케이스 포함

    호환성을 위해 *args/**kwargs 형태는 유지하되, 권장 파라미터는 kwargs로 받는다.
    """
    owned_rows: list[dict[str, Any]] = kwargs.get("owned_rows") or (args[0] if args else [])
    now_ts = int(kwargs.get("now_ts") or time.time())
    max_anchors = int(kwargs.get("max_anchors", 10))
    cooling_off_days = int(kwargs.get("cooling_off_days", 3))
    cooling_off_lifetime_hours = float(kwargs.get("cooling_off_lifetime_hours", 80.0))

    rows = owned_rows if isinstance(owned_rows, list) else []

    prim: list[tuple[float, int]] = []
    sec: list[tuple[int, float, int]] = []  # (days_since, lifetime_hours, appid)

    for r in rows:
        if not isinstance(r, dict):
            continue
        appid = _safe_int(r.get("appid"), 0)
        if appid <= 0:
            continue
        p2w = _safe_float(r.get("playtime_2weeks_hours"), 0.0)
        life = _safe_float(r.get("playtime_forever_hours"), 0.0)
        last_ts = r.get("rtime_last_played_ts")
        last_ts_i = _safe_int(last_ts, 0) if last_ts is not None else 0

        if p2w > 0.0:
            prim.append((p2w, appid))
            continue

        if last_ts_i > 0:
            days = _days_since(last_ts_i, now_ts=now_ts)
            if days <= cooling_off_days and life >= cooling_off_lifetime_hours:
                sec.append((days, life, appid))

    prim_sorted = [appid for _, appid in sorted(prim, key=lambda x: (-x[0], x[1]))]
    sec_sorted = [appid for _, _, appid in sorted(sec, key=lambda x: (x[0], -x[1], x[2]))]

    out: list[int] = []
    for appid in prim_sorted + sec_sorted:
        if appid not in out:
            out.append(appid)
        if len(out) >= max_anchors:
            break
    return out

