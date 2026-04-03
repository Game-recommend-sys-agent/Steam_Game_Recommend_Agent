"""
context_bundle 조립기

목표:
- (1) SituationalContext   : situational.py
- (2) SentimentContext     : sentiment.py   (선택, LLM)
- (4) PlayStyleContext     : play_style.py
- (5) BehaviorContext      : behavior_activity.py (processed)
- (6~8) GameContext        : game_signals.py → quality_trust/live/discount (processed)
를 합쳐 docs/03-context_aware.md 의 ContextBundle 형태에 가까운 JSON을 만든다.

주의:
- 이 모듈은 "조립(merge)"에 집중한다.
- (6~8) 번들 생성/갱신(TTL)은 별도 스크립트(scripts/build_game_signals_bundle.py)가 담당.
- (1, 4) Situational / PlayStyle 은 interim user_games table을 직접 읽어 계산한다.
- (2) Sentiment 는 UI 입력(user_reviews, mood_tag)이 필요하므로 기본 OFF.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.game_recommendation.context_aware.behavior_activity import (
    UserBehaviorPaths,
    load_interim_user_games_table,
    processed_behavior_context_path,
)
from src.game_recommendation.context_aware.game_signals import (
    GameSignalsPaths,
    processed_bundle_path,
)
from src.game_recommendation.context_aware.situational import compute_situational_context
from src.game_recommendation.context_aware.play_style import compute_play_style_context
from src.game_recommendation.context_aware.sentiment import compute_sentiment_context


def _data_root() -> Path:
    """
    데이터 루트 디렉토리.
    - 기본: ./data
    - 오버라이드: DATA_DIR 환경변수
    """
    return Path(os.environ.get("DATA_DIR", "data"))


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


@dataclass(frozen=True)
class ContextBundlePaths:
    """
    서로 다른 모듈의 paths를 한 번에 전달하기 위한 wrapper.
    """

    user: UserBehaviorPaths = field(default_factory=UserBehaviorPaths)
    game: GameSignalsPaths = field(default_factory=GameSignalsPaths)
    processed_dir: Path = field(default_factory=lambda: _data_root() / "processed")


def context_bundle_output_path(
    steam_id: str, *, paths: ContextBundlePaths, cc: str = "us", lang: str = "en"
) -> Path:
    return paths.processed_dir / "context_bundles" / f"{steam_id}__cc={cc}__lang={lang}.json"


def load_behavior_processed(steam_id: str, *, paths: ContextBundlePaths) -> dict[str, Any]:
    """
    (5) processed BehaviorContext를 로드한다.
    - data/processed/user_behavior/{steam_id}.json
    """
    p = processed_behavior_context_path(steam_id, paths=paths.user)
    return _read_json(p)


def load_game_bundle_processed(
    appid: int, *, paths: ContextBundlePaths, cc: str = "us", lang: str = "en"
) -> dict[str, Any]:
    """
    (6~8) processed game bundle을 로드한다.
    - data/processed/game_bundles/{appid}__cc={cc}__lang={lang}.json
    """
    p = processed_bundle_path(appid, paths=paths.game, cc=cc, lang=lang)
    return _read_json(p)


def _load_owned_rows(steam_id: str, *, paths: ContextBundlePaths) -> list[dict[str, Any]]:
    """
    interim user_games table 에서 owned_rows를 꺼낸다.
    파일이 없으면 빈 리스트 반환(graceful degradation).
    """
    try:
        table = load_interim_user_games_table(steam_id, paths=paths.user)
        rows = table.get("rows", []) if isinstance(table, dict) else []
        return rows if isinstance(rows, list) else []
    except FileNotFoundError:
        return []


def assemble_context_bundle(
    *,
    steam_id: str,
    appids: list[int],
    paths: ContextBundlePaths,
    cc: str = "us",
    lang: str = "en",
    now_ts: int | None = None,
    include_game_bundle_meta: bool = True,
    # (1) Situational
    available_mins: int = 60,
    include_situational: bool = True,
    # (2) Sentiment — 기본 OFF (LLM 호출 필요)
    mood_tag: str = "",
    user_reviews: list[str] | None = None,
    include_sentiment: bool = False,
    openai_client: Any = None,
    openai_api_key: str | None = None,
    # (4) Play Style
    include_play_style: bool = True,
) -> dict[str, Any]:
    """
    ContextBundle 조립.

    유저 컨텍스트 섹션:
      - situational  (1): available_mins/현재시각 + interim user_games rows
      - sentiment    (2): user_reviews + mood_tag → LLM (include_sentiment=True 시 활성)
      - play_style   (4): interim user_games rows
      - behavior     (5): data/processed/user_behavior/{steam_id}.json

    게임 컨텍스트 섹션 (6~8):
      - quality_trust, live, discount: data/processed/game_bundles/{appid}...json
    """
    now_ts = int(now_ts or time.time())

    # (5) BehaviorContext (processed)
    try:
        behavior_payload = load_behavior_processed(steam_id, paths=paths)
        behavior_ctx = (
            behavior_payload.get("behavior", {})
            if isinstance(behavior_payload, dict)
            else {}
        )
    except FileNotFoundError:
        behavior_ctx = {}

    # (1, 4) interim rows 로드 (Situational + PlayStyle 공용)
    owned_rows = _load_owned_rows(steam_id, paths=paths)

    # (1) SituationalContext
    situational_ctx: dict[str, Any] | None = None
    if include_situational:
        situational_ctx = compute_situational_context(
            owned_rows,
            available_mins=available_mins,
            now_ts=now_ts,
        )

    # (4) PlayStyleContext
    play_style_ctx: dict[str, Any] | None = None
    if include_play_style:
        play_style_ctx = compute_play_style_context(owned_rows)

    # (2) SentimentContext (선택, LLM)
    sentiment_ctx: dict[str, Any] | None = None
    if include_sentiment:
        sentiment_ctx = compute_sentiment_context(
            user_reviews or [],
            mood_tag=mood_tag,
            openai_client=openai_client,
            openai_api_key=openai_api_key,
        )
    elif mood_tag:
        # LLM 없이 mood_tag만 기록 (비용 절감, 최소 컨텍스트 유지)
        sentiment_ctx = {
            "weighted_aspect_preference": None,
            "churn_triggers": [],
            "current_mood_tag": mood_tag,
        }

    # user 섹션 조립
    user_section: dict[str, Any] = {}
    if situational_ctx is not None:
        user_section["situational"] = situational_ctx
    if sentiment_ctx is not None:
        user_section["sentiment"] = sentiment_ctx
    if play_style_ctx is not None:
        user_section["play_style"] = play_style_ctx
    user_section["behavior"] = behavior_ctx

    # (6~8) 게임 컨텍스트 섹션 조립
    missing_appids: list[int] = []
    stale_appids: list[int] = []
    games_out: dict[str, Any] = {}

    for appid in appids:
        if not isinstance(appid, int) or appid <= 0:
            continue
        try:
            bundle = load_game_bundle_processed(appid, paths=paths, cc=cc, lang=lang)
        except FileNotFoundError:
            missing_appids.append(appid)
            continue

        contexts = bundle.get("contexts", {}) if isinstance(bundle, dict) else {}
        meta = bundle.get("meta", {}) if isinstance(bundle, dict) else {}

        expires_at = _safe_int(meta.get("expires_at"), 0)
        if expires_at > 0 and expires_at <= now_ts:
            stale_appids.append(appid)

        entry: dict[str, Any] = {
            "quality_trust": contexts.get("quality_trust"),
            "live": contexts.get("live"),
            "discount": contexts.get("discount"),
        }
        if include_game_bundle_meta:
            entry["_bundle_meta"] = meta
        games_out[str(appid)] = entry

    return {
        "meta": {
            "steam_id": steam_id,
            "generated_at": now_ts,
            "cc": cc,
            "lang": lang,
            "requested_appids": [int(a) for a in appids if isinstance(a, int) and a > 0],
            "missing_appids": missing_appids,
            "stale_appids": stale_appids,
        },
        "user_id": steam_id,
        "user": user_section,
        "games": games_out,
    }


def validate_context_bundle(bundle: dict[str, Any]) -> list[str]:
    """
    간단한 상식 범위/결측/TTL 이슈를 문자열 리스트로 반환한다.
    (샘플 스냅샷 검증용)
    """
    issues: list[str] = []
    if not isinstance(bundle, dict):
        return ["bundle is not a dict"]

    meta = bundle.get("meta", {})
    now_ts = _safe_int(meta.get("generated_at"), 0)
    missing = meta.get("missing_appids")
    stale = meta.get("stale_appids")
    if isinstance(missing, list) and missing:
        issues.append(f"missing_appids: {missing}")
    if isinstance(stale, list) and stale:
        issues.append(f"stale_appids(expired bundles): {stale}")

    user = bundle.get("user", {})
    if not isinstance(user, dict):
        issues.append("user section missing or not a dict")
        return issues

    # (5) BehaviorContext 검증
    behavior = user.get("behavior")
    if not isinstance(behavior, dict):
        issues.append("user.behavior missing or not a dict")
    else:
        st = behavior.get("activity_state")
        if st not in ("active", "cooling_off", "dormant"):
            issues.append(f"behavior.activity_state invalid: {st!r}")

    # (1) SituationalContext 검증 (있으면)
    situational = user.get("situational")
    if situational is not None:
        if not isinstance(situational, dict):
            issues.append("user.situational is not a dict")
        else:
            tw = situational.get("available_time_window")
            if tw not in ("30m", "60m", "120m_plus"):
                issues.append(f"situational.available_time_window invalid: {tw!r}")

    # (4) PlayStyleContext 검증 (있으면)
    play_style = user.get("play_style")
    if play_style is not None:
        if not isinstance(play_style, dict):
            issues.append("user.play_style is not a dict")
        else:
            ps = play_style.get("play_style")
            if ps not in ("Focused", "Diverse"):
                issues.append(f"play_style.play_style invalid: {ps!r}")
            fs = play_style.get("focus_score")
            if isinstance(fs, (int, float)) and not (0.0 <= float(fs) <= 1.0):
                issues.append(f"play_style.focus_score out of [0,1]: {fs}")

    # (6~8) 게임 컨텍스트 검증
    games = bundle.get("games", {})
    if not isinstance(games, dict):
        issues.append("games missing or not a dict")
        return issues
    if not games and isinstance(meta.get("requested_appids"), list) and meta.get("requested_appids"):
        issues.append("requested_appids not empty but games is empty (all missing?)")

    for appid_str, gctx in games.items():
        if not isinstance(gctx, dict):
            issues.append(f"games[{appid_str}] not a dict")
            continue

        # TTL 검사 (_bundle_meta가 있으면)
        bm = gctx.get("_bundle_meta")
        if isinstance(bm, dict):
            expires_at = _safe_int(bm.get("expires_at"), 0)
            if expires_at > 0 and now_ts > 0 and expires_at <= now_ts:
                issues.append(f"games[{appid_str}] bundle expired (expires_at={expires_at})")

        qt = gctx.get("quality_trust")
        if isinstance(qt, dict):
            for k in ("review_positive_ratio", "confidence", "quality_trust_score"):
                v = qt.get(k)
                if isinstance(v, (int, float)) and not (0.0 <= float(v) <= 1.0):
                    issues.append(f"games[{appid_str}].quality_trust.{k} out of [0,1]: {v}")

        live = gctx.get("live")
        if isinstance(live, dict):
            v = live.get("liveness_signal")
            if isinstance(v, (int, float)) and not (0.0 <= float(v) <= 1.0):
                issues.append(f"games[{appid_str}].live.liveness_signal out of [0,1]: {v}")

        disc = gctx.get("discount")
        if isinstance(disc, dict):
            dp = disc.get("discount_percent")
            if isinstance(dp, int) and not (0 <= dp <= 100):
                issues.append(f"games[{appid_str}].discount.discount_percent out of [0,100]: {dp}")
            ds = disc.get("discount_signal")
            if isinstance(ds, (int, float)) and not (0.0 <= float(ds) <= 1.0):
                issues.append(f"games[{appid_str}].discount.discount_signal out of [0,1]: {ds}")

    return issues


def write_context_bundle(
    bundle: dict[str, Any],
    *,
    steam_id: str,
    paths: ContextBundlePaths,
    cc: str = "us",
    lang: str = "en",
) -> Path:
    out = context_bundle_output_path(steam_id, paths=paths, cc=cc, lang=lang)
    _atomic_write_json(out, bundle)
    return out
