"""
Context-aware API endpoints

POST /context/user    — 유저 컨텍스트 생성 (1) situational (2) sentiment (4) play_style (5) behavior
POST /context/game    — 단일 게임 컨텍스트 생성 (6) quality_trust (7) live (8) discount
POST /context/bundle  — 유저 + 게임 컨텍스트 번들 조립
POST /recommend/filter — DB 기반 필터링 파이프라인 (final_filters):
    OS → Age → Price → Spec(RAM) → Genre
"""

from __future__ import annotations

import asyncio
import base64
import json
import math as _math
import time
from pathlib import Path

import pandas as pd
import requests as _requests
from fastapi import APIRouter, HTTPException
from openai import OpenAI as _OpenAI

from context_aware.behavior_activity import compute_behavior_context
from context_aware.discount import compute_discount_context
from context_aware.live import compute_live_context
from context_aware.play_style import compute_play_style_context
from context_aware.quality_trust import compute_quality_trust_context
from context_aware.sentiment import compute_sentiment_context
from context_aware.situational import compute_situational_context
from core.config import settings
from final_filters.db_pipeline import run_db_pipeline
from final_filters.load_data import load_games_df
from schemas.context import (
    ContextBundleRequest,
    FilterRequest,
    GameContextRequest,
    GameContextResponse,
    ImageRagRequest,
    ImageRagResponse,
    ImageRagResultItem,
    LLMRankedGame,
    LLMRankRequest,
    LLMRankResponse,
    UserContextRequest,
    UserContextResponse,
)

router = APIRouter()

# ── Image RAG 상수 / 경로 ─────────────────────────────────────────────────

_PROJECT_ROOT = Path(__file__).parents[4]
_CAPTION_DIR = _PROJECT_ROOT / "game-image-rag" / "data" / "captions"
_STORE_API_DIR = _PROJECT_ROOT / "game-image-rag" / "data" / "store_api"

_VISION_MODEL = "gpt-4o"
_PARSE_MODEL = "gpt-4o-mini"
_EMBED_MODEL = "text-embedding-3-small"

_DUMMY_GAMES = [
    {"game_id": 1145360, "game_name": "Hades", "genres": "RPG, 액션", "final_price_cents": 0, "image_url": "https://cdn.akamai.steamstatic.com/steam/apps/1145360/header.jpg", "image_caption": "액션 가득한 지하 세계 탈출", "score": 0.95, "reason": "스토리와 액션이 완벽하게 조화된 명작입니다."},
    {"game_id": 1151640, "game_name": "Horizon Zero Dawn", "genres": "액션, 어드벤처", "final_price_cents": 10900, "image_url": "https://cdn.akamai.steamstatic.com/steam/apps/1151640/header.jpg", "image_caption": "기계 생명체가 가득한 아름다운 포스트 아포칼립스", "score": 0.92, "reason": "웅장한 세계관과 독보적인 디자인을 자랑합니다."},
    {"game_id": 1174180, "game_name": "Red Dead Redemption II", "genres": "오픈월드, 시뮬레이션", "final_price_cents": 15900, "image_url": "https://cdn.akamai.steamstatic.com/steam/apps/1174180/header.jpg", "image_caption": "황야의 무법자들의 장엄한 서사시", "score": 0.90, "reason": "극강의 디테일과 몰입감을 선사하는 역대급 오픈월드입니다."},
    {"game_id": 1245620, "game_name": "Elden Ring", "genres": "RPG, 소울라이크", "final_price_cents": 20900, "image_url": "https://cdn.akamai.steamstatic.com/steam/apps/1245620/header.jpg", "image_caption": "빛을 잃은 자들을 위한 거대한 판타지 세계", "score": 0.94, "reason": "탐험과 도전 정신을 끊임없이 자극하는 걸작입니다."},
    {"game_id": 1340740, "game_name": "Persona 5 Royal", "genres": "RPG, 스토리", "final_price_cents": 0, "image_url": "https://cdn.akamai.steamstatic.com/steam/apps/1340740/header.jpg", "image_caption": "스타일리시한 괴도단과 함께하는 학원 판타지", "score": 0.88, "reason": "세련된 연출과 매력적인 캐릭터들이 돋보이는 게임입니다."}
]

_GAMES_METADATA: dict | None = None


def _get_metadata() -> dict:
    global _GAMES_METADATA
    if _GAMES_METADATA is not None:
        return _GAMES_METADATA

    df = load_games_df()
    metadata = df.set_index("game_id").to_dict(orient="index")
    # Sanitize NaNs
    for gid, row in metadata.items():
        for k, v in row.items():
            if isinstance(v, float) and (_math.isnan(v) or _math.isinf(v)):
                row[k] = None

    _GAMES_METADATA = metadata
    return _GAMES_METADATA


# 시각적 특징별 임베딩 가중치 (pipeline 06 동일)
_IMG_WEIGHTS: dict[str, int] = {
    "face_features": 2,
    "facial_expression": 2,
    "visual_color": 2,
    "props_or_accessories": 1,
    "hair_traits": 1,
    "clothing_style": 1,
    "body_traits": 1,
    "species_traits": 1,
}

_CAPTION_PROMPT = (
    "You are an assistant analyzing video game poster images.\n\n"
    "Your goal is to extract visually observable character traits.\n\n"
    "Steps:\n"
    "1. Write ONE neutral image caption describing only what is visible.\n"
    "2. Extract 4–15 visual keywords based on appearance.\n"
    "3. Identify characters in the poster and extract visual cues.\n\n"
    "Character handling rules:\n"
    "- Identify ONE primary character (most visually emphasized overall).\n"
    "- Additionally, identify up to TWO salient characters who are visually distinctive.\n"
    "- Do NOT extract more than 3 characters in total.\n\n"
    "Character visual cue categories:\n"
    "species_traits, face_features, facial_expression, body_traits,\n"
    "hair_traits, clothing_style, visual_color, props_or_accessories\n\n"
    "Rules:\n"
    "- Do NOT infer personality traits or story roles.\n"
    "- Use only visually observable attributes.\n\n"
    'Output JSON only with keys: "image_caption", "visual_keywords", '
    '"primary_character" (character_id, salience_reason, visual_cues), '
    '"salient_characters" (array, same structure).'
)

_PARSE_SYSTEM = (
    "You are an assistant that translates a user's character preference "
    "into VISUALLY OBSERVABLE CHARACTER TRAITS ONLY.\n"
    "- Convert abstract, emotional, or subjective expressions (e.g., '예쁜', '멋진', '어두운', '귀여운') "
    "into commonly associated visual cues.\n"
    "- E.g., 'pretty' map to 'symmetrical face, large eyes, clear skin, vibrant colors'.\n"
    "- E.g., 'dark mood' map to 'low-key lighting, somber expression, dark color palette'.\n"
    "- Store ONLY visually observable traits. Output JSON only."
)


_PARSE_USER_TEMPLATE = (
    'User request: "{user_input}"\n\n'
    "Interpret the request and output ONLY visually observable traits as JSON with these keys:\n"
    "species_traits, face_features, facial_expression, body_traits, "
    "hair_traits, clothing_style, visual_color, props_or_accessories\n\n"
    "Output JSON only."
)


# ── Image RAG 헬퍼 함수 ───────────────────────────────────────────────────

def _steam_header_url(appid: int) -> str:
    return f"https://cdn.akamai.steamstatic.com/steam/apps/{appid}/header.jpg"


def _get_game_name(appid: int, metadata: dict = None) -> str:
    if metadata and appid in metadata:
        return metadata[appid].get("game_name") or f"App {appid}"
    return f"App {appid}"



def _flatten_visual_cues(cues: dict) -> str:
    chunks: list[str] = []
    for key, weight in _IMG_WEIGHTS.items():
        values = cues.get(key, [])
        if not values:
            continue
        phrase = ", ".join(values)
        label = key.replace("_", " ").title()
        # Repeating for weighting effect
        repeated = "; ".join([f"{label}: {phrase}"] * int(weight))
        chunks.append(repeated)
    return ". ".join(chunks)



def _build_embedding_text(caption: dict) -> str:
    chunks: list[str] = []
    desc = caption.get("image_caption", "")
    if desc:
        chunks.append(f"Target Character Description: {desc}")
    
    trait_elements: list[str] = []
    if caption.get("visual_keywords"):
        trait_elements.append(f"Keywords: {', '.join(caption['visual_keywords'])}")
    
    primary = caption.get("primary_character")
    if primary:
        cues_text = _flatten_visual_cues(primary.get("visual_cues", {}))
        if cues_text:
            trait_elements.append(cues_text)
            trait_elements.append(cues_text) # Emphasize primary
            
    for sc in caption.get("salient_characters", []):
        cues_text = _flatten_visual_cues(sc.get("visual_cues", {}))
        if cues_text:
            trait_elements.append(cues_text)
            
    if trait_elements:
        chunks.append(f"Specific Visual Traits: {'. '.join(trait_elements)}")
        
    return "\n".join(chunks)



def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = _math.sqrt(sum(x * x for x in a))
    norm_b = _math.sqrt(sum(y * y for y in b))
    return dot / (norm_a * norm_b + 1e-8)


def _get_embedding(text: str, client: _OpenAI) -> list[float]:
    res = client.embeddings.create(model=_EMBED_MODEL, input=text)
    return res.data[0].embedding


def _parse_user_input(user_input: str, client: _OpenAI) -> dict:
    completion = client.chat.completions.create(
        model=_PARSE_MODEL,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": _PARSE_SYSTEM},
            {"role": "user", "content": _PARSE_USER_TEMPLATE.format(user_input=user_input)},
        ],
    )
    return json.loads(completion.choices[0].message.content)


def _load_or_generate_caption(appid: int, client: _OpenAI) -> dict | None:
    """캡션 캐시 우선 로드, 없으면 Steam CDN 이미지로 생성 후 캐시 저장."""
    caption_path = _CAPTION_DIR / f"{appid}.json"
    if caption_path.exists():
        try:
            return json.loads(caption_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    # Steam CDN에서 헤더 이미지 다운로드
    try:
        resp = _requests.get(_steam_header_url(appid), timeout=10)
        resp.raise_for_status()
        b64 = base64.b64encode(resp.content).decode("utf-8")
        image_data_url = f"data:image/jpeg;base64,{b64}"
    except Exception:
        return None

    # GPT-4o Vision으로 캡션 생성
    try:
        completion = client.chat.completions.create(
            model=_VISION_MODEL,
            response_format={"type": "json_object"},
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": _CAPTION_PROMPT},
                    {"type": "image_url", "image_url": {"url": image_data_url, "detail": "low"}},
                ],
            }],
        )
        caption_data: dict = json.loads(completion.choices[0].message.content)
        caption_data["appid"] = appid

        _CAPTION_DIR.mkdir(parents=True, exist_ok=True)
        caption_path.write_text(
            json.dumps(caption_data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return caption_data
    except Exception:
        return None


def _run_image_rag(request: ImageRagRequest) -> ImageRagResponse:
    client = _OpenAI(api_key=settings.OPENAI_API_KEY)

    # 1. 유저 입력 → 시각적 큐 파싱 → 임베딩
    visual_cues = _parse_user_input(request.user_input, client)
    interpreted_traits = _flatten_visual_cues(visual_cues)
    user_text = f"Target Character Description: {request.user_input}\nSpecific Visual Traits: {interpreted_traits}"
    print(f"[image-rag] User embedding text:\n{user_text}")
    user_embedding = _get_embedding(user_text, client)


    # 검색 대상 appid 결정: 요청에 없으면 캐시된 전체 사용
    metadata = _get_metadata()


    if request.appids:
        target_appids = request.appids
    else:
        target_appids = [
            int(p.stem) for p in _CAPTION_DIR.glob("*.json")
            if p.stem.isdigit()
        ]


    # 2. 각 게임 캡션 로드/생성 후 코사인 유사도 계산
    scored: list[dict] = []
    print(f"[image-rag] target_appids count: {len(target_appids)}")
    for appid in target_appids[:10]: # Print for first 10
        caption = _load_or_generate_caption(appid, client)
        if not caption:
             print(f"[image-rag] appid {appid} - no caption available")
             continue
        embedding_text = _build_embedding_text(caption)
        if not embedding_text.strip():
             print(f"[image-rag] appid {appid} - embedding text empty")
             continue
        game_embedding = _get_embedding(embedding_text, client)
        score = _cosine_similarity(user_embedding, game_embedding)
        
        m = metadata.get(appid, {})
        scored.append({
            "appid": appid,
            "game_name": m.get("game_name") or f"App {appid}",
            "score": round(score, 6),
            "image_url": m.get("image_url") or _steam_header_url(appid),
            "image_caption": caption.get("image_caption", ""),
            "visual_summary": embedding_text[:400],
            "genres": m.get("genres"),
            "final_price_cents": m.get("final_price_cents"),
        })

        
    for appid in target_appids[10:]: # silently process the rest
        caption = _load_or_generate_caption(appid, client)
        if not caption: continue
        embedding_text = _build_embedding_text(caption)
        if not embedding_text.strip(): continue
        game_embedding = _get_embedding(embedding_text, client)
        score = _cosine_similarity(user_embedding, game_embedding)
        
        m = metadata.get(appid, {})
        scored.append({
            "appid": appid,
            "game_name": m.get("game_name") or f"App {appid}",
            "score": round(score, 6),
            "image_url": m.get("image_url") or _steam_header_url(appid),
            "image_caption": caption.get("image_caption", ""),
            "visual_summary": embedding_text[:400],
            "genres": m.get("genres"),
            "final_price_cents": m.get("final_price_cents"),
        })


    print(f"[image-rag] total valid scored games: {len(scored)}")

    # 3. 정렬 후 Top-K 반환
    scored.sort(key=lambda x: x["score"], reverse=True)
    top_k = max(1, min(request.top_k, len(scored))) if len(scored) > 0 else request.top_k
    
    results = [
        ImageRagResultItem(rank=i + 1, **item)
        for i, item in enumerate(scored[:top_k])
    ]
    
    # 4. Fallback: 만약 scored가 0개라면 제공된 appids (없으면 빈 배열)를 fallback으로 넘김.
    if len(results) == 0 and request.appids:
        fallback_scored = []
        for appid in request.appids[:request.top_k]:
            m = metadata.get(appid, {})
            fallback_scored.append({
                "appid": appid,
                "game_name": m.get("game_name") or f"App {appid}",
                "score": 0.0,
                "image_url": m.get("image_url") or _steam_header_url(appid),
                "image_caption": "No Image Caption Available (Fallback)",
                "visual_summary": "LLM/Filtering fallback result used due to missing caption DB.",
                "genres": m.get("genres"),
                "final_price_cents": m.get("final_price_cents"),
            })
        
        results = [
            ImageRagResultItem(rank=i + 1, **item)
            for i, item in enumerate(fallback_scored)
        ]

    # Final Fallback to global dummy games if still empty
    if not results:
        results = [
            ImageRagResultItem(
                rank=i + 1,
                appid=g["game_id"],
                game_name=g["game_name"],
                score=g["score"],
                image_url=g["image_url"],
                image_caption=g["image_caption"],
                visual_summary=g["reason"],
                genres=g.get("genres"),
                final_price_cents=g.get("final_price_cents"),
            )
            for i, g in enumerate(_DUMMY_GAMES)
        ]


    return ImageRagResponse(
        user_input=request.user_input,
        top_k=top_k,
        results=results,
    )


# ── (1~5) 유저 컨텍스트 ───────────────────────────────────────────────────

@router.post("/context/user", response_model=UserContextResponse)
async def compute_user_context(request: UserContextRequest):
    """
    소유 게임 목록(owned_rows)을 받아 유저 컨텍스트를 계산한다.

    - (1) situational  : 가용 시간 + 현재 시각 기반 상황 컨텍스트
    - (2) sentiment    : 리뷰/mood_tag 기반 심리 컨텍스트 (include_sentiment=True 시 LLM 호출)
    - (4) play_style   : 집중도/플레이 스타일
    - (5) behavior     : 최근 활성도 + anchor appids
    """
    try:
        now_ts = int(time.time())
        owned_rows = [row.model_dump() for row in request.owned_rows]

        behavior = compute_behavior_context(owned_rows=owned_rows, now_ts=now_ts)

        situational = None
        if request.include_situational:
            situational = compute_situational_context(
                owned_rows,
                available_mins=request.available_mins,
                now_ts=now_ts,
            )

        play_style = None
        if request.include_play_style:
            play_style = compute_play_style_context(owned_rows)

        sentiment = None
        if request.include_sentiment:
            sentiment = compute_sentiment_context(
                request.user_reviews,
                mood_tag=request.mood_tag,
                openai_api_key=settings.OPENAI_API_KEY,
            )
        elif request.mood_tag:
            sentiment = {
                "weighted_aspect_preference": None,
                "churn_triggers": [],
                "current_mood_tag": request.mood_tag,
            }

        return UserContextResponse(
            steam_id=request.steam_id,
            situational=situational,
            sentiment=sentiment,
            play_style=play_style,
            behavior=behavior,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── (6~8) 게임 컨텍스트 ───────────────────────────────────────────────────

@router.post("/context/game", response_model=GameContextResponse)
async def compute_game_context(request: GameContextRequest):
    """
    게임 interim 시그널을 받아 게임 컨텍스트를 계산한다.

    interim 구조 (build_interim_game_signals 반환값):
    {
      "appdetails": { "movies_count", "screenshots_count", "recommendations_total",
                      "discount_percent", "price_final", "price_initial", ... },
      "reviews":    { "total_positive", "total_reviews", "review_positive_ratio", ... },
      "schema":     { "achievements_total" },
      "news":       { "newsitems": [{"date", "feedlabel", "title"}, ...] }
    }
    """
    try:
        now_ts = int(time.time())
        quality_trust = compute_quality_trust_context(request.interim)
        live = compute_live_context(request.interim, now_ts=now_ts)
        discount = compute_discount_context(request.interim)

        return GameContextResponse(
            appid=request.appid,
            quality_trust=quality_trust,
            live=live,
            discount=discount,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── 번들 조립 ─────────────────────────────────────────────────────────────

@router.post("/context/bundle")
async def assemble_context_bundle(request: ContextBundleRequest):
    """
    유저 컨텍스트 + 복수 게임 컨텍스트를 하나의 ContextBundle로 조립한다.

    반환 구조:
    {
      "meta":    { steam_id, generated_at, cc, lang, requested_appids, missing_appids },
      "user_id": steam_id,
      "user":    { situational?, sentiment?, play_style?, behavior },
      "games":   { "<appid>": { quality_trust, live, discount }, ... }
    }
    """
    try:
        now_ts = int(time.time())
        owned_rows = [row.model_dump() for row in request.owned_rows]

        behavior = compute_behavior_context(owned_rows=owned_rows, now_ts=now_ts)

        situational = None
        if request.include_situational:
            situational = compute_situational_context(
                owned_rows,
                available_mins=request.available_mins,
                now_ts=now_ts,
            )

        play_style = None
        if request.include_play_style:
            play_style = compute_play_style_context(owned_rows)

        sentiment = None
        if request.include_sentiment:
            sentiment = compute_sentiment_context(
                request.user_reviews,
                mood_tag=request.mood_tag,
                openai_api_key=settings.OPENAI_API_KEY,
            )
        elif request.mood_tag:
            sentiment = {
                "weighted_aspect_preference": None,
                "churn_triggers": [],
                "current_mood_tag": request.mood_tag,
            }

        user_section: dict = {"behavior": behavior}
        if situational is not None:
            user_section["situational"] = situational
        if sentiment is not None:
            user_section["sentiment"] = sentiment
        if play_style is not None:
            user_section["play_style"] = play_style

        games_out: dict = {}
        missing_appids: list[int] = []

        for entry in request.games:
            try:
                quality_trust = compute_quality_trust_context(entry.interim)
                live = compute_live_context(entry.interim, now_ts=now_ts)
                discount = compute_discount_context(entry.interim)
                games_out[str(entry.appid)] = {
                    "quality_trust": quality_trust,
                    "live": live,
                    "discount": discount,
                }
            except Exception:
                missing_appids.append(entry.appid)

        return {
            "meta": {
                "steam_id": request.steam_id,
                "generated_at": now_ts,
                "cc": request.cc,
                "lang": request.lang,
                "requested_appids": [e.appid for e in request.games],
                "missing_appids": missing_appids,
            },
            "user_id": request.steam_id,
            "user": user_section,
            "games": games_out,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── DB 기반 필터링 파이프라인 ─────────────────────────────────────────────

@router.post("/recommend/filter")
async def recommend_filter(request: FilterRequest):
    """
    PostgreSQL silver 스키마에서 게임 데이터를 로드 후 순차 필터링을 적용한다.

    파이프라인 (final_filters.db_pipeline.run_db_pipeline):
      1. OS 필터       — windows / mac / linux 지원 여부
      2. Age 필터      — age_limit ≤ 요청 age
      3. Price 필터    — final_price_cents 범위 (<10000 / 10000-30000 / >=30000)
      4. Spec 필터     — min_ram_gb ≤ low(8GB) or mid(12GB), high=미적용
      5. Genre 필터    — 복수 OR 조건 (GENRE_GROUP_MAP 매핑)

    반환 구조:
    {
      "before_count": int,
      "after_count":  int,
      "results": [ { game_id, game_name, genres, final_price_cents, ... }, ... ]
    }
    """
    try:
        df = load_games_df()
        before_count = len(df)

        user_pref = request.model_dump()

        # Enum → 문자열 변환
        if user_pref.get("os"):
            user_pref["os"] = user_pref["os"].value
        if user_pref.get("price"):
            user_pref["price"] = user_pref["price"].value
        if user_pref.get("spec"):
            user_pref["spec"] = user_pref["spec"].value
        if user_pref.get("genres"):
            user_pref["genres"] = [g.value for g in user_pref["genres"]]

        filtered = run_db_pipeline(df, user_pref)
        after_count = len(filtered)

        limit = request.limit or 10
        result_df = filtered.head(limit)

        records = result_df.to_dict(orient="records")
        for row in records:
            for k, v in row.items():
                if isinstance(v, float) and (_math.isnan(v) or _math.isinf(v)):
                    row[k] = None

        # Fallback to dummy data if empty
        if not records:
            records = [{k: v for k, v in g.items() if k in ["game_id", "game_name", "genres", "final_price_cents", "image_url"]} for g in _DUMMY_GAMES]

        return {
            "before_count": before_count,
            "after_count": len(records),
            "results": records,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── LLM 기반 Top-K 추천 ───────────────────────────────────────────────────

_LLM_SYSTEM_PROMPT = """\
You are a Steam game recommendation expert.
Given a user's gaming context and a list of filtered games, select and rank the top {top_k} games most suitable for this user.

Return ONLY a JSON object with this exact structure:
{{
  "summary": "brief explanation (1-2 sentences) of the selection rationale",
  "ranked_games": [
    {{"rank": 1, "game_id": 123, "game_name": "...", "reason": "why this game fits the user"}},
    ...
  ]
}}

Rules:
- Only include games from the provided list (use exact game_id and game_name values).
- Return exactly {top_k} entries (or fewer if fewer games are available).
- Write reasons in Korean.
"""


@router.post("/recommend/llm-topk", response_model=LLMRankResponse)
async def recommend_llm_topk(request: LLMRankRequest):
    """
    필터링된 게임 목록 + 유저 컨텍스트를 LLM에 전달해 상위 top_k개를 추천한다.

    입력:
    - filtered_games : /recommend/filter 의 results 배열
    - user_context   : /context/user 응답 또는 /context/bundle 의 user 섹션
    - top_k          : 반환할 상위 게임 수 (기본 10)

    반환:
    {
      "top_k": 10,
      "summary": "...",
      "ranked_games": [{"rank": 1, "game_id": ..., "game_name": "...", "reason": "..."}, ...]
    }
    """
    try:
        top_k = max(1, min(request.top_k, len(request.filtered_games)))

        # 게임 목록을 LLM에 전달할 핵심 필드만 추려 토큰 절약
        game_summaries = []
        for g in request.filtered_games:
            price_cents = g.get("final_price_cents") or 0
            price_str = f"{price_cents / 100:.0f}원" if price_cents else "무료"
            game_summaries.append({
                "game_id": g.get("game_id"),
                "game_name": g.get("game_name", "Unknown"),
                "genres": g.get("genres", ""),
                "price": price_str,
                "age_limit": g.get("age_limit"),
                "min_ram_gb": g.get("min_ram_gb"),
            })

        user_msg = (
            f"User Context:\n{json.dumps(request.user_context, ensure_ascii=False, indent=2)}\n\n"
            f"Filtered Games ({len(game_summaries)} total):\n"
            f"{json.dumps(game_summaries, ensure_ascii=False, indent=2)}\n\n"
            f"Please rank the top {top_k} games for this user."
        )
        client = _OpenAI(api_key=settings.OPENAI_API_KEY)
        completion = await asyncio.to_thread(
            client.chat.completions.create,
            model="gpt-4o",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _LLM_SYSTEM_PROMPT.format(top_k=top_k)},
                {"role": "user", "content": user_msg},
            ],
        )
        data = json.loads(completion.choices[0].message.content)

        ranked_games = [LLMRankedGame(**g) for g in data.get("ranked_games", [])]
        
        # Fallback if empty
        if not ranked_games:
            ranked_games = [
                LLMRankedGame(rank=i+1, game_id=g["game_id"], game_name=g["game_name"], reason=g["reason"])
                for i, g in enumerate(_DUMMY_GAMES)
            ]

        return LLMRankResponse(
            top_k=top_k if ranked_games else 0,
            ranked_games=ranked_games,
            summary=data.get("summary", "더미 데이터를 기반으로 추천 결과를 생성했습니다.") if ranked_games and data.get("summary") else "추천 결과가 없어 인기작들을 준비했습니다.",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── 이미지 RAG 기반 캐릭터 선호 추천 ─────────────────────────────────────

@router.post("/recommend/image-rag", response_model=ImageRagResponse)
async def recommend_image_rag(request: ImageRagRequest):
    """
    유저의 캐릭터 선호 텍스트를 시각적 큐로 변환하고,
    게임 포스터 이미지(Steam CDN) 기반 임베딩 유사도로 Top-K를 추천한다.
    """
    try:
        result = await asyncio.to_thread(_run_image_rag, request)

        # 결과 출력
        pass

        return result

    except Exception as e:
        print("===== Image RAG Error =====")
        print(e)
        raise HTTPException(status_code=500, detail=str(e))