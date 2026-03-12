"""
(6~8) 게임 시그널: raw → interim(요약/정규화) → processed(컨텍스트 번들)

목표:
- Steam/Store raw JSON을 그대로 쓰지 않고, "데이터 계약" 기준으로 필요한 필드만 추출/정규화
- appid 단위로 재사용 가능한 번들(quality_trust/live/discount 컨텍스트)을 만든다

참고: `docs/context_aware_5to8.md`
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.game_recommendation.context_aware.quality_trust import (
    compute_quality_trust_context as compute_quality_trust_context,
)
from src.game_recommendation.context_aware.live import (
    compute_live_context as compute_live_context,
)
from src.game_recommendation.context_aware.discount import (
    compute_discount_context as compute_discount_context,
)

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


def _clamp01(x: float) -> float:
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


@dataclass(frozen=True)
class GameSignalsPaths:
    raw_dir: Path = Path("data/raw")
    interim_dir: Path = Path("data/interim")
    processed_dir: Path = Path("data/processed")


def load_raw_game_signals(
    appid: int, *, paths: GameSignalsPaths, cc: str = "us", lang: str = "en"
) -> dict[str, Any]:
    """
    2.7.2 규칙에 따른 raw 파일을 읽는다.
    - appdetails는 locale 영향을 받으므로 cc/lang을 포함한 파일명을 사용한다.
    """
    raw: dict[str, Any] = {}

    raw["appdetails"] = _read_json(
        paths.raw_dir / "appdetails" / f"{appid}__cc={cc}__lang={lang}.json"
    )
    raw["appreviews_summary"] = _read_json(
        paths.raw_dir / "appreviews_summary" / f"{appid}.json"
    )
    raw["schema"] = _read_json(paths.raw_dir / "schema" / f"{appid}.json")
    raw["news"] = _read_json(paths.raw_dir / "news" / f"{appid}.json")
    return raw


def build_interim_game_signals(
    appid: int,
    raw: dict[str, Any],
    *,
    cc: str = "us",
    lang: str = "en",
    now_ts: int | None = None,
) -> dict[str, Any]:
    """
    raw → interim: 필요한 필드만 추출 + 타입/결측/단위 정규화.

    반환값은 appid 단위 "요약 저장본"으로, processed 번들 생성의 입력으로 사용한다.
    """
    now_ts = int(now_ts or time.time())

    # --- appdetails ---
    appdetails_payload = raw.get("appdetails", {})
    entry = appdetails_payload.get(str(appid), {}) if isinstance(appdetails_payload, dict) else {}
    data = entry.get("data", {}) if isinstance(entry, dict) else {}

    price_overview = data.get("price_overview") or {}
    achievements = data.get("achievements") or {}
    recommendations = data.get("recommendations") or {}

    appdetails_summary = {
        "appid": appid,
        "cc": cc,
        "lang": lang,
        "movies_count": _safe_int(len(data.get("movies") or []), 0),
        "screenshots_count": _safe_int(len(data.get("screenshots") or []), 0),
        "recommendations_total": _safe_int(recommendations.get("total"), 0),
        # Store appdetails 쪽 achievements.total (있으면 사용, 없으면 0)
        "achievements_total_store": _safe_int(achievements.get("total"), 0),
        "discount_percent": _safe_int(price_overview.get("discount_percent"), 0),
        "price_final": _safe_int(price_overview.get("final"), 0),
        "price_initial": _safe_int(price_overview.get("initial"), 0),
        "currency": price_overview.get("currency"),
        "raw_success": bool(entry.get("success")) if isinstance(entry, dict) else False,
    }

    # --- appreviews(summary) ---
    reviews_payload = raw.get("appreviews_summary", {})
    query_summary = (
        reviews_payload.get("query_summary", {})
        if isinstance(reviews_payload, dict)
        else {}
    )
    total_positive = _safe_int(query_summary.get("total_positive"), 0)
    total_reviews = _safe_int(query_summary.get("total_reviews"), 0)
    total_negative = _safe_int(query_summary.get("total_negative"), 0)
    review_positive_ratio = total_positive / max(total_reviews, 1)

    appreviews_summary = {
        "appid": appid,
        "total_positive": total_positive,
        "total_negative": total_negative,
        "total_reviews": total_reviews,
        "review_positive_ratio": _safe_float(review_positive_ratio, 0.0),
        "review_score_desc": query_summary.get("review_score_desc"),
    }

    # --- schema (achievements.total) ---
    schema_payload = raw.get("schema", {})
    game = schema_payload.get("game", {}) if isinstance(schema_payload, dict) else {}
    stats = game.get("availableGameStats", {}) if isinstance(game, dict) else {}
    schema_achievements = stats.get("achievements") if isinstance(stats, dict) else None
    achievements_total_schema: int | None
    if isinstance(schema_achievements, list):
        achievements_total_schema = _safe_int(len(schema_achievements), 0)
    else:
        achievements_total_schema = None
    schema_summary = {"appid": appid, "achievements_total": achievements_total_schema}

    # --- news ---
    news_payload = raw.get("news", {})
    appnews = news_payload.get("appnews", {}) if isinstance(news_payload, dict) else {}
    newsitems = appnews.get("newsitems") if isinstance(appnews, dict) else None
    items_out: list[dict[str, Any]] = []
    if isinstance(newsitems, list):
        for it in newsitems:
            if not isinstance(it, dict):
                continue
            items_out.append(
                {
                    "date": _safe_int(it.get("date"), 0),
                    "feedlabel": it.get("feedlabel"),
                    "title": it.get("title"),
                }
            )
    news_summary = {"appid": appid, "newsitems": items_out}

    return {
        "meta": {"generated_at": now_ts},
        "appid": appid,
        "appdetails": appdetails_summary,
        "reviews": appreviews_summary,
        "schema": schema_summary,
        "news": news_summary,
    }


def write_interim_game_signals(
    interim: dict[str, Any],
    *,
    paths: GameSignalsPaths,
    appid: int,
    cc: str = "us",
    lang: str = "en",
) -> Path:
    out = paths.interim_dir / "game_signals" / f"{appid}__cc={cc}__lang={lang}.json"
    _atomic_write_json(out, interim)
    return out


def load_interim_game_signals(
    appid: int, *, paths: GameSignalsPaths, cc: str = "us", lang: str = "en"
) -> dict[str, Any]:
    path = paths.interim_dir / "game_signals" / f"{appid}__cc={cc}__lang={lang}.json"
    return _read_json(path)


def build_processed_game_bundle(
    interim: dict[str, Any],
    *,
    ttl_seconds: int = 24 * 3600,
    now_ts: int | None = None,
) -> dict[str, Any]:
    now_ts = int(now_ts or time.time())
    appid = _safe_int(interim.get("appid"), 0)

    quality = compute_quality_trust_context(interim)
    live = compute_live_context(interim, now_ts=now_ts)
    discount = compute_discount_context(interim)

    return {
        "meta": {
            "appid": appid,
            "generated_at": now_ts,
            "ttl_seconds": int(ttl_seconds),
            "expires_at": now_ts + int(ttl_seconds),
        },
        "interim": interim,
        "contexts": {
            "quality_trust": quality,
            "live": live,
            "discount": discount,
        },
    }


def processed_bundle_path(
    appid: int, *, paths: GameSignalsPaths, cc: str = "us", lang: str = "en"
) -> Path:
    return paths.processed_dir / "game_bundles" / f"{appid}__cc={cc}__lang={lang}.json"


def write_processed_game_bundle(
    bundle: dict[str, Any],
    *,
    paths: GameSignalsPaths,
    appid: int,
    cc: str = "us",
    lang: str = "en",
) -> Path:
    out = processed_bundle_path(appid, paths=paths, cc=cc, lang=lang)
    _atomic_write_json(out, bundle)
    return out


def is_processed_bundle_fresh(path: Path, *, now_ts: int | None = None) -> bool:
    now_ts = int(now_ts or time.time())
    try:
        payload = _read_json(path)
    except FileNotFoundError:
        return False
    meta = payload.get("meta", {}) if isinstance(payload, dict) else {}
    expires_at = _safe_int(meta.get("expires_at"), 0)
    return expires_at > now_ts

