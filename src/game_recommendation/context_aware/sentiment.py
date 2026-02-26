"""
(2) Sentiment / Persona Context — 심리/감성 컨텍스트 (LLM 포함)

- 입력: 유저 리뷰 텍스트 리스트 + UI 기반 mood_tag
- 출력: SentimentContext
  - weighted_aspect_preference: dict | None  (그래픽/스토리 등 6대 속성 비중, LLM 추출)
  - churn_triggers: list[str]                (불호 트리거, LLM 추출)
  - current_mood_tag: str                    (UI 입력 그대로 보존)

구현 상세/요구 사항은 docs/03-context_aware.md 4.4 를 참고.

운영 메모:
- 리뷰가 없으면 LLM 호출 없이 빈 컨텍스트를 반환한다.
- LLM 결과는 고정 JSON 스키마로만 수용한다 (재현성/비용 절감).
- MVP에서는 OFF(선택) 기본값이며, UI 기반 current_mood_tag부터 시작해도 된다.
"""

from __future__ import annotations

import json
import os
from typing import Any

SENTIMENT_PROMPT_TEMPLATE = """\
아래 유저 리뷰들을 분석해 JSON으로 반환하세요.

리뷰 목록:
{reviews_text}

반환 형식(JSON, 다른 내용 없이 JSON만):
{{
  "aspects": {{
    "graphics": <0~1 float>,
    "story": <0~1 float>,
    "gameplay": <0~1 float>,
    "difficulty": <0~1 float>,
    "sound": <0~1 float>,
    "multiplayer": <0~1 float>
  }},
  "churn_triggers": [<str>, ...]
}}

- aspects: 리뷰에서 유저가 중시하는 속성 비중 (합이 반드시 1일 필요 없음, 각 0~1)
- churn_triggers: 유저가 부정적으로 언급한 요소(예: "버그", "노가다", "짧은 스토리")
"""


def _safe_str(x: Any, default: str = "") -> str:
    if x is None:
        return default
    return str(x)


def _build_empty_context(mood_tag: str) -> dict[str, Any]:
    return {
        "weighted_aspect_preference": None,
        "churn_triggers": [],
        "current_mood_tag": _safe_str(mood_tag),
    }


def _call_llm(
    user_reviews: list[str],
    *,
    openai_client: Any,
    model: str = "gpt-4o-mini",
) -> dict[str, Any] | None:
    """
    LLM을 호출해 리뷰에서 aspects / churn_triggers를 추출한다.
    실패 시 None 반환 (호출부에서 빈 컨텍스트로 폴백).
    """
    reviews_text = "\n".join(f"- {r}" for r in user_reviews[:20])  # 상한 20개
    prompt = SENTIMENT_PROMPT_TEMPLATE.format(reviews_text=reviews_text)

    try:
        resp = openai_client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content
        parsed = json.loads(raw)
        return parsed
    except Exception:
        return None


def compute_sentiment_context(
    user_reviews: list[str],
    mood_tag: str = "",
    *,
    openai_client: Any = None,
    openai_api_key: str | None = None,
    model: str = "gpt-4o-mini",
) -> dict[str, Any]:
    """
    (2) SentimentContext 계산.

    - user_reviews: 유저가 작성한 리뷰 텍스트 리스트.
      리뷰가 없으면 LLM 미호출, weighted_aspect_preference=None.
    - mood_tag: UI 입력 (예: "stress_relief", "achievement", "immersion").
      LLM 호출 여부와 무관하게 항상 출력에 포함된다.
    - openai_client: openai.OpenAI 인스턴스. 없으면 openai_api_key로 생성.
      둘 다 없으면 LLM 없이 mood_tag만 반환.
    - model: OpenAI 모델명 (기본: gpt-4o-mini).

    LLM 호출 실패 / 리뷰 없음 → weighted_aspect_preference=None, churn_triggers=[].
    """
    mood_tag = _safe_str(mood_tag)

    if not user_reviews:
        return _build_empty_context(mood_tag)

    # openai_client 조립
    client = openai_client
    if client is None:
        api_key = openai_api_key or os.environ.get("OPENAI_API_KEY")
        if api_key:
            try:
                from openai import OpenAI  # lazy import (선택 의존성)
                client = OpenAI(api_key=api_key)
            except ImportError:
                client = None

    if client is None:
        return _build_empty_context(mood_tag)

    result = _call_llm(user_reviews, openai_client=client, model=model)
    if result is None:
        return _build_empty_context(mood_tag)

    aspects = result.get("aspects")
    churn_triggers = result.get("churn_triggers") or []

    # 타입 보정
    if not isinstance(aspects, dict):
        aspects = None
    if not isinstance(churn_triggers, list):
        churn_triggers = []
    churn_triggers = [str(t) for t in churn_triggers if t]

    return {
        "weighted_aspect_preference": aspects,
        "churn_triggers": churn_triggers,
        "current_mood_tag": mood_tag,
    }
