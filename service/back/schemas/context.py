from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel

class OwnedGameRow(BaseModel):
    appid: int
    playtime_forever_hours: float = 0.0
    playtime_2weeks_hours: float = 0.0
    rtime_last_played_ts: Optional[int] = None

class UserContextRequest(BaseModel):
    steam_id: str
    owned_rows: List[OwnedGameRow] = []
    available_mins: int = 60
    mood_tag: str = ""
    user_reviews: List[str] = []
    include_sentiment: bool = False
    include_situational: bool = True
    include_play_style: bool = True


class UserContextResponse(BaseModel):
    steam_id: str
    situational: Optional[Dict[str, Any]] = None
    sentiment: Optional[Dict[str, Any]] = None
    play_style: Optional[Dict[str, Any]] = None
    behavior: Dict[str, Any]

class GameContextRequest(BaseModel):
    appid: int
    interim: Dict[str, Any]


class GameContextResponse(BaseModel):
    appid: int
    quality_trust: Dict[str, Any]   # (6)
    live: Dict[str, Any]            # (7)
    discount: Dict[str, Any]        # (8)

class BundleGameEntry(BaseModel):
    appid: int
    interim: Dict[str, Any]


class ContextBundleRequest(BaseModel):
    steam_id: str
    owned_rows: List[OwnedGameRow] = []
    games: List[BundleGameEntry] = []
    available_mins: int = 60
    mood_tag: str = ""
    user_reviews: List[str] = []
    include_sentiment: bool = False
    include_situational: bool = True
    include_play_style: bool = True
    cc: str = "us"
    lang: str = "en"

# ── /recommend/filter 요청 ────────────────────────────────────────────────

from enum import Enum


class OSType(str, Enum):
    windows = "windows"
    mac = "mac"
    linux = "linux"


class PriceType(str, Enum):
    lt_10000 = "<10000"
    mid = "10000-30000"
    gte_30000 = ">=30000"


class SpecType(str, Enum):
    low = "low"    # min_ram_gb ≤ 8GB 게임만
    mid = "mid"    # min_ram_gb ≤ 12GB 게임만
    high = "high"  # 필터 미적용


class GenreType(str, Enum):
    action = "액션"
    rpg = "RPG"
    strategy = "전략"
    simulation = "시뮬레이션"
    story = "스토리 중심"
    puzzle = "퍼즐"
    online = "온라인"
    tool = "제작"


class FilterRequest(BaseModel):
    """
    DB 기반 게임 필터링 요청.

    pipeline (final_filters.db_pipeline):
      OS 필터 → Age 필터 → Price 필터 → Spec 필터 → Genre 필터
    """
    os: Optional[OSType] = None
    age: Optional[int] = None          # 최대 허용 연령 (예: 15, 18)
    price: Optional[PriceType] = None  # 가격 범위 (cents 기준)
    spec: Optional[SpecType] = None    # PC 사양 등급
    genres: Optional[List[GenreType]] = None
    limit: Optional[int] = 10         # 반환 결과 수


# ── /recommend/llm-topk 요청/응답 ─────────────────────────────────────────

class LLMRankRequest(BaseModel):
    """
    LLM 기반 Top-K 추천 요청.

    - filtered_games : /recommend/filter 의 results 배열을 그대로 전달
    - user_context   : /context/user 응답 또는 /context/bundle 의 user 섹션
    - steam_id       : 로그 식별용 (선택)
    - top_k          : 반환할 상위 게임 수 (기본 10)
    """
    filtered_games: List[Dict[str, Any]]
    user_context: Dict[str, Any]
    steam_id: str = ""
    top_k: int = 10


class LLMRankedGame(BaseModel):
    rank: int
    game_id: Optional[int] = None
    game_name: Optional[str] = None
    reason: str


class LLMRankResponse(BaseModel):
    top_k: int
    ranked_games: List[LLMRankedGame]
    summary: str


# ── /recommend/image-rag 요청/응답 ────────────────────────────────────────

class ImageRagRequest(BaseModel):
    """
    이미지 기반 캐릭터 선호 RAG 추천 요청.

    - user_input : 유저가 원하는 캐릭터/분위기를 자유 텍스트로 입력
                   예) "우는 게 예쁠 것 같은 어두운 분위기의 여성 캐릭터"
    - appids     : 검색 대상 게임 appid 목록 (없으면 캐시된 전체 게임 사용)
    - top_k      : 반환할 상위 게임 수 (기본 5)
    """
    user_input: str
    appids: Optional[List[int]] = None  # None → 캐시 전체 사용
    top_k: int = 5


class ImageRagResultItem(BaseModel):
    rank: int
    appid: int
    game_name: str
    score: float
    image_url: str        # Steam CDN 헤더 이미지 URL
    image_caption: str    # GPT Vision이 생성한 이미지 설명
    visual_summary: str   # 임베딩에 사용된 시각적 특징 요약
    genres: Optional[str] = None
    final_price_cents: Optional[int] = None


class ImageRagResponse(BaseModel):
    user_input: str
    top_k: int
    results: List[ImageRagResultItem]