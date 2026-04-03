"""
Phase 2 베이스라인: 유저 컨텍스트 생성 + Top-K 점수 + (선택) LLM 재랭킹.

- 데이터 수집(Steam/IGDB API 호출)은 하지 않음. 호출부에서 fetch 모듈을 주입.
- Retrieval-first: 후보 풀 → 점수 → Top-K → LLM 재랭킹.
"""
import json
import time
from collections import Counter
from datetime import datetime

import pandas as pd
from openai import OpenAI


def build_user_context(
    steam_id: str,
    user_intent: dict,
    *,
    get_recent_games,
    get_owned_games,
    get_game_metadata,
) -> dict:
    """
    유저 컨텍스트 및 성향 벡터 생성.
    get_* 는 (필요한 인자) -> list/dict 를 반환하는 호출 가능 객체.
    """
    recent = get_recent_games(steam_id)
    owned = get_owned_games(steam_id)

    if not recent:
        return {"error": "최근 플레이 기록 없음 또는 비공개 계정"}

    records = []
    for game in recent:
        meta = get_game_metadata(game["name"])
        records.append({
            "appid": game["appid"],
            "name": game["name"],
            "recent_playtime": game.get("playtime_2weeks", 0),
            "genres": [g["name"] for g in meta.get("genres", [])],
            "themes": [t["name"] for t in meta.get("themes", [])],
            "modes": [m["name"] for m in meta.get("game_modes", [])],
            "rating": meta.get("total_rating", 0),
        })

    df = pd.DataFrame(records)
    genre_counter = Counter(df["genres"].explode())
    theme_counter = Counter(df["themes"].explode())
    mode_counter = Counter(df["modes"].explode())
    avg_recent_hours = round(df["recent_playtime"].mean() / 60, 2)
    now = datetime.now()

    total_playtime = sum(g.get("playtime_forever", 0) for g in owned)
    total_recent = sum(g.get("playtime_2weeks", 0) for g in recent)
    owned_map = {g["appid"]: g for g in owned}
    focus_ratios = []
    for g in recent:
        appid = g["appid"]
        if appid in owned_map and owned_map[appid].get("playtime_forever", 0) > 0:
            ratio = g.get("playtime_2weeks", 0) / owned_map[appid]["playtime_forever"]
            focus_ratios.append(ratio)
    focus_score = sum(focus_ratios) / len(focus_ratios) if focus_ratios else 0

    difficulty_signal = (df["rating"].fillna(0) * df["recent_playtime"]).mean()
    difficulty_preference = "Challenging" if difficulty_signal > 5000 else "Relaxed"
    available = user_intent.get("available_time", 60)
    time_alignment = (
        "Quick Session" if available <= 30
        else "Mid-length Play" if available <= 90
        else "Deep Immersion"
    )

    genre_weights = df["genres"].explode().value_counts(normalize=True).to_dict()
    theme_weights = df["themes"].explode().value_counts(normalize=True).to_dict()
    mode_weights = df["modes"].explode().value_counts(normalize=True).to_dict()
    preference_vector = {
        "genre_weights": genre_weights,
        "theme_weights": theme_weights,
        "mode_weights": mode_weights,
        "rating_affinity": round(df["rating"].mean(), 1),
        "recent_play_bias": round(df["recent_playtime"].mean(), 1),
    }

    return {
        "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
        "current_time_context": {
            "day_of_week": now.strftime("%A"),
            "is_weekend": now.weekday() >= 5,
            "time_period": "일과" if 9 <= now.hour < 18 else "저녁/밤",
        },
        "user_behavior_signal": {
            "top_genres": [g for g, _ in genre_counter.most_common(3)],
            "top_themes": [t for t, _ in theme_counter.most_common(3)],
            "preferred_modes": [m for m, _ in mode_counter.most_common(2)],
            "avg_recent_play_hours": avg_recent_hours,
        },
        "play_style_profile": {
            "total_lifetime_hours": round(total_playtime / 60, 1),
            "recent_2weeks_hours": round(total_recent / 60, 1),
            "engagement_trend": "Rising" if total_recent / max(total_playtime, 1) > 0.15 else "Stable",
            "play_style": "Focused" if focus_score > 0.3 else "Diverse",
            "focus_score": round(focus_score, 3),
        },
        "difficulty_profile": {
            "difficulty_preference": difficulty_preference,
            "difficulty_score": round(difficulty_signal, 2),
        },
        "time_intent_alignment": time_alignment,
        "preference_vector": preference_vector,
        "user_explicit_intent": user_intent,
        "system_constraint": {
            "hardware": user_intent.get("hardware", "Unknown"),
            "cpu": user_intent.get("cpu", "Unknown"),
            "gpu": user_intent.get("gpu", "Unknown"),
            "ram_gb": user_intent.get("ram_gb", 0),
            "free_storage_gb": user_intent.get("free_storage_gb", 0),
            "os": user_intent.get("os", "Unknown"),
            "max_available_time": user_intent.get("available_time"),
        },
    }


def score_game(game: dict, context: dict) -> float:
    """후보 게임에 대한 추천 점수 (Retrieval-first Top-K용)."""
    if context.get("error"):
        return 0.0
    pv = context.get("preference_vector", {})
    score = 0.0
    for g in game.get("genres", []):
        score += pv.get("genre_weights", {}).get(g, 0) * 50
    if game.get("theme"):
        score += pv.get("theme_weights", {}).get(game["theme"], 0) * 30
    if game.get("difficulty") == context.get("difficulty_profile", {}).get("difficulty_preference"):
        score += 20
    available_min = context.get("user_explicit_intent", {}).get("available_time", 60) * 60
    if game.get("avg_playtime", 0) <= available_min:
        score += 10
    mode_weight = pv.get("mode_weights", {}).get(game.get("mode"), 0)
    score *= 1 + mode_weight
    return score


def llm_rerank(
    user_context: dict,
    candidate_games: list,
    top_n: int = 3,
    *,
    client: OpenAI,
    model: str = "gpt-4o-mini",
) -> str:
    """Top-K 후보에 대해 LLM으로 재랭킹·설명."""
    prompt = f"""
You are a Steam game recommendation expert.

User context:
{json.dumps(user_context, ensure_ascii=False, indent=2)}

Candidate games:
{json.dumps(candidate_games, ensure_ascii=False, indent=2)}

Task:
1. Select the best {top_n} games for this user
2. Rank them
3. Explain why each game fits the user
4. Penalize games that do not fit deep immersion or challenging gameplay
Return JSON with fields: name, score, reason.
"""
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.4,
    )
    return response.choices[0].message.content


def run_recommendation_pipeline(
    steam_id: str,
    user_intent: dict,
    fetch_module,
    steam_api_key: str,
    igdb_client_id: str,
    igdb_client_secret: str,
    openai_api_key: str,
    *,
    top_n: int = 3,
    candidate_limit: int = 100,
    sleep_per_request: float = 0.5,
) -> str:
    """
    데이터 수집(fetch_module) + 컨텍스트 생성 + 후보 점수 + LLM 재랭킹까지 한 번에 실행.
    fetch_module 에는 get_recent_games(steam_api_key, steam_id), get_owned_games(...),
    get_game_metadata_igdb(name, client_id, client_secret), get_app_list(limit),
    get_game_details(appid) 가 있어야 함.
    """
    # IGDB 토큰 한 번만 발급
    igdb_token = fetch_module.get_igdb_token(igdb_client_id, igdb_client_secret)

    def get_recent(sid):
        return fetch_module.get_recent_games(steam_api_key, sid)

    def get_owned(sid):
        return fetch_module.get_owned_games(steam_api_key, sid)

    def get_metadata(name):
        return fetch_module.get_game_metadata_igdb(
            name, igdb_client_id, igdb_client_secret, _token=igdb_token
        )

    user_context = build_user_context(
        steam_id,
        user_intent,
        get_recent_games=get_recent,
        get_owned_games=get_owned,
        get_game_metadata=get_metadata,
    )
    if user_context.get("error"):
        return json.dumps({"error": user_context["error"]}, ensure_ascii=False)

    apps = fetch_module.get_app_list(limit=candidate_limit)
    candidates = []
    for i, app in enumerate(apps):
        game = fetch_module.get_game_details(app["appid"])
        if not game or not game.get("genres") or not game.get("name"):
            continue
        game["score"] = score_game(game, user_context)
        candidates.append(game)
        if i % 20 == 0:
            time.sleep(sleep_per_request)

    candidates.sort(key=lambda x: x["score"], reverse=True)
    top_candidates = candidates[:20]

    client = OpenAI(api_key=openai_api_key)
    llm_result = llm_rerank(user_context, top_candidates, top_n=top_n, client=client)
    return llm_result
