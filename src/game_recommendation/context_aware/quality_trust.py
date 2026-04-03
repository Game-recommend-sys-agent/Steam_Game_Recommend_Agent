"""
(6) Quality / Trust

- 입력: appdetails(movies/screenshots/recommendations), appreviews(total_positive/total_reviews),
        schema(achievements.total)
- 출력: QualityTrustContext + quality_trust_score (+ confidence)

구현 상세/요구 사항은 `docs/context_aware_5to8.md`를 참고.
"""

from __future__ import annotations

import math
from typing import Any, Final

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


DEFAULT_CONFIDENCE_MAX_REVIEWS: Final[int] = 10_000


def compute_confidence(total_reviews: int, *, max_reviews: int = DEFAULT_CONFIDENCE_MAX_REVIEWS) -> float:
    """
    리뷰 표본이 커질수록 1에 가까워지는 신뢰도.

    문서 권장 예시:
    - confidence = min(1.0, log10(total_reviews + 1) / log10(10000))
    """
    total_reviews = max(0, int(total_reviews))
    denom = math.log10(max(int(max_reviews), 1))
    if denom <= 0:
        return 0.0
    return min(1.0, math.log10(total_reviews + 1) / denom)


def compute_quality_trust_context(
    interim: dict[str, Any],
    *,
    confidence_max_reviews: int = DEFAULT_CONFIDENCE_MAX_REVIEWS,
    w_ratio: float = 0.65,
    w_achievements: float = 0.15,
    w_media: float = 0.10,
    w_recommendations: float = 0.10,
) -> dict[str, Any]:
    """
    (6) Quality/Trust 컨텍스트 계산.

    입력은 `game_signals.build_interim_game_signals()`가 만드는 interim 포맷을 가정한다.
    출력은 MVP 데이터 계약(`docs/context_aware_5to8.md`의 2.6.6)을 우선으로 하되,
    점수 계산에는 V1 신호(appdetails의 media/recommendations)를 내부적으로 사용할 수 있다.
    """
    src = interim if isinstance(interim, dict) else {}
    reviews = src.get("reviews", {}) if isinstance(src.get("reviews"), dict) else {}
    appdetails = src.get("appdetails", {}) if isinstance(src.get("appdetails"), dict) else {}
    schema = src.get("schema", {}) if isinstance(src.get("schema"), dict) else {}

    ratio = _clamp01(_safe_float(reviews.get("review_positive_ratio"), 0.0))
    total_reviews = max(0, _safe_int(reviews.get("total_reviews"), 0))

    # 계약상 achievements_total은 nullable. 점수 계산에서는 None을 0으로 취급.
    achievements_raw = schema.get("achievements_total")
    achievements_total: int | None
    if achievements_raw is None:
        achievements_total = None
        achievements_for_score = 0
    else:
        achievements_total = max(0, _safe_int(achievements_raw, 0))
        achievements_for_score = achievements_total

    screenshots_count = max(0, _safe_int(appdetails.get("screenshots_count"), 0))
    movies_count = max(0, _safe_int(appdetails.get("movies_count"), 0))
    recommendations_total = max(0, _safe_int(appdetails.get("recommendations_total"), 0))

    confidence = compute_confidence(total_reviews, max_reviews=int(confidence_max_reviews))

    # 0~1 정규화(초기 스케일은 보수적으로; 운영/데이터 분포를 보며 조정)
    ach_norm = min(1.0, achievements_for_score / 200.0)  # 200개 이상이면 1로
    media_norm = 0.0
    if movies_count > 0:
        media_norm += 0.4
    media_norm += min(0.6, (screenshots_count / 20.0) * 0.6)
    reco_norm = min(
        1.0,
        math.log10(recommendations_total + 1) / math.log10(1_000_000),
    )

    # 가중 합(초기값): 리뷰 비율을 주로, 나머지는 보조
    base = (
        float(w_ratio) * ratio
        + float(w_achievements) * ach_norm
        + float(w_media) * media_norm
        + float(w_recommendations) * reco_norm
    )
    quality_trust_score = _clamp01(_safe_float(base * confidence, 0.0))

    # MVP 계약 필드만 노출
    return {
        "review_positive_ratio": ratio,
        "total_reviews": total_reviews,
        "achievements_total": achievements_total,
        "confidence": _clamp01(_safe_float(confidence, 0.0)),
        "quality_trust_score": quality_trust_score,
    }

