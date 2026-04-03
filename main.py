"""
메인 진입점.

- 데이터 수집: scripts.fetch_steam_data
- 추천 로직: src.game_recommendation.context_aware.baseline_recommender

실행: 프로젝트 루트에서
  python main.py
"""
import os
from pathlib import Path

from dotenv import load_dotenv

from scripts import fetch_steam_data
from src.game_recommendation.context_aware import baseline_recommender

# -----------------------------
# .env 로드 (프로젝트 루트 또는 config/.env)
# -----------------------------
_root = Path(__file__).resolve().parent
load_dotenv(_root / ".env")
load_dotenv(_root / "config" / ".env")

# -----------------------------
# 환경 변수
# -----------------------------
STEAM_API_KEY = os.environ.get("STEAM_API_KEY", "STEAM_WEB_KEY")
IGDB_CLIENT_ID = os.environ.get("IGDB_CLIENT_ID", "CLIENT_ID")
IGDB_CLIENT_SECRET = os.environ.get("IGDB_CLIENT_SECRET", "CLIENT_SECRET")
STEAM_ID = os.environ.get("STEAM_ID", "USER_STEAM_ID")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "OPEN_API_KEY")

USER_INTENT = {
    "available_time": 120,
    "hardware": "PC",
    "cpu": "Intel i7-12700K",
    "gpu": "RTX 4070",
    "ram_gb": 32,
    "free_storage_gb": 500,
    "os": "Windows 11",
    "preferred_genres": ["RPG", "Action"],
}


if __name__ == "__main__":
    print("유저 컨텍스트 생성 및 추천 파이프라인 실행 중…")
    result = baseline_recommender.run_recommendation_pipeline(
        STEAM_ID,
        USER_INTENT,
        fetch_steam_data,
        STEAM_API_KEY,
        IGDB_CLIENT_ID,
        IGDB_CLIENT_SECRET,
        OPENAI_API_KEY,
        top_n=3,
        candidate_limit=100,
    )
    print("\n추천 결과:\n", result)
