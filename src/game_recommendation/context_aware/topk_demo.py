"""
(필터링 전) Top-K 후보 데모

목표:
- context_bundle(user + candidate games)에 들어있는 (6~8) 컨텍스트만으로
  간단한 점수 합산을 수행해 Top-K를 뽑고, reason(근거)을 함께 출력한다.

주의:
- 이 모듈은 "데모" 용도다. 최종 랭킹/필터링(Phase 3~4)은 별도 설계로 교체될 수 있다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def _safe_float(x: Any, default: float = 0.0) -> float:
    if x is None:
        return default
    try:
        return float(x)
    except (ValueError, TypeError):
        return default


def _safe_int(x: Any, default: int = 0) -> int:
    if x is None:
        return default
    try:
        return int(x)
    except (ValueError, TypeError):
        return default


def _clamp01(x: float) -> float:
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


@dataclass(frozen=True)
class DemoWeights:
    """
    context-aware(5~8)만으로 뽑는 '데모' Top-K 가중치.
    """

    quality_trust: float = 0.60
    live: float = 0.25
    discount: float = 0.15


def score_game_from_contexts(
    game_context: dict[str, Any], *, weights: DemoWeights
) -> tuple[float, dict[str, float]]:
    """
    한 게임에 대해 점수와 (구성요소별 기여도)을 반환.
    """
    qt = game_context.get("quality_trust", {}) if isinstance(game_context.get("quality_trust"), dict) else {}
    live = game_context.get("live", {}) if isinstance(game_context.get("live"), dict) else {}
    disc = game_context.get("discount", {}) if isinstance(game_context.get("discount"), dict) else {}

    qt_score = _clamp01(_safe_float(qt.get("quality_trust_score"), 0.0))
    live_sig = _clamp01(_safe_float(live.get("liveness_signal"), 0.0))
    disc_sig = _clamp01(_safe_float(disc.get("discount_signal"), 0.0))

    contrib = {
        "quality_trust": float(weights.quality_trust) * qt_score,
        "live": float(weights.live) * live_sig,
        "discount": float(weights.discount) * disc_sig,
    }
    total = float(sum(contrib.values()))
    return total, contrib


def build_reason(
    *,
    appid: str,
    score: float,
    contrib: dict[str, float],
    game_context: dict[str, Any],
    top_n: int = 2,
) -> str:
    """
    사람이 보기 좋은 reason 문자열(간단)을 만든다.
    - 가장 기여도가 큰 신호 top_n개를 선택
    - 할인율/뉴스 경과 같은 디테일을 간단히 첨부
    """
    parts: list[str] = []
    ranked = sorted(contrib.items(), key=lambda kv: kv[1], reverse=True)
    for k, _v in ranked[: max(1, int(top_n))]:
        if k == "quality_trust":
            qt = game_context.get("quality_trust", {}) if isinstance(game_context.get("quality_trust"), dict) else {}
            ratio = _safe_float(qt.get("review_positive_ratio"), 0.0)
            total_reviews = _safe_int(qt.get("total_reviews"), 0)
            parts.append(
                f"품질/신뢰가 높음(qt_score={_safe_float(qt.get('quality_trust_score'), 0.0):.3f}, "
                f"긍정비율={ratio:.3f}, 리뷰수={total_reviews})"
            )
        elif k == "live":
            lv = game_context.get("live", {}) if isinstance(game_context.get("live"), dict) else {}
            days = lv.get("days_since_last_news")
            parts.append(
                f"라이브 신호가 높음(live={_safe_float(lv.get('liveness_signal'), 0.0):.3f}, "
                f"마지막뉴스={days}일전)"
            )
        elif k == "discount":
            dc = game_context.get("discount", {}) if isinstance(game_context.get("discount"), dict) else {}
            dp = _safe_int(dc.get("discount_percent"), 0)
            parts.append(f"할인 트리거(dp={dp}%)")
        else:
            parts.append(k)

    joined = "; ".join(parts) if parts else "컨텍스트 신호 기반"
    return f"[{appid}] score={score:.3f} — {joined}"


def rank_topk_from_context_bundle(
    bundle: dict[str, Any],
    *,
    top_k: int = 10,
    weights: DemoWeights | None = None,
    reason_top_n: int = 2,
) -> dict[str, Any]:
    """
    context_bundle에서 games를 점수화해 Top-K 리스트를 만든다.
    """
    weights = weights or DemoWeights()

    games = bundle.get("games", {}) if isinstance(bundle, dict) else {}
    if not isinstance(games, dict):
        return {"error": "bundle.games missing or not a dict", "top_k": []}

    rows: list[dict[str, Any]] = []
    for appid_str, gctx in games.items():
        if not isinstance(gctx, dict):
            continue
        score, contrib = score_game_from_contexts(gctx, weights=weights)
        rows.append(
            {
                "appid": str(appid_str),
                "score": float(score),
                "contrib": contrib,
                "reason": build_reason(
                    appid=str(appid_str),
                    score=float(score),
                    contrib=contrib,
                    game_context=gctx,
                    top_n=reason_top_n,
                ),
            }
        )

    rows.sort(key=lambda r: r["score"], reverse=True)
    top = rows[: max(0, int(top_k))]

    return {
        "meta": {
            "top_k": int(top_k),
            "weights": {
                "quality_trust": float(weights.quality_trust),
                "live": float(weights.live),
                "discount": float(weights.discount),
            },
        },
        "top_k": top,
    }

