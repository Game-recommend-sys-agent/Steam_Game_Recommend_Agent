from enum import Enum
from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional, List
import pandas as pd

from load_data import load_games_df
from db_pipeline import run_db_pipeline

app = FastAPI()


# =====================================================
# Enum 정의
# =====================================================

class OSType(str, Enum):
    windows = "windows"
    mac = "mac"
    linux = "linux"


class PriceType(str, Enum):
    lt_10000 = "<10000"
    mid = "10000-30000"
    gte_30000 = ">=30000"


class SpecType(str, Enum):
    low = "low"
    mid = "mid"
    high = "high"


class GenreType(str, Enum):
    action = "액션"
    rpg = "RPG"
    strategy = "전략"
    simulation = "시뮬레이션"
    story = "스토리 중심"
    puzzle = "퍼즐"
    online = "온라인"
    tool = "제작"


# =====================================================
# 입력 스키마
# =====================================================

class FilterInput(BaseModel):
    os: Optional[OSType] = None
    age: Optional[int] = None
    price: Optional[PriceType] = None
    spec: Optional[SpecType] = None
    genres: Optional[List[GenreType]] = None


# =====================================================
# 필터 API
# =====================================================

@app.post("/filter")
def filter_games(input: FilterInput):

    df = load_games_df()
    before_count = len(df)

    # Enum → 실제 값으로 변환
    user_pref = input.model_dump()

    # Enum 리스트 값도 문자열로 변환
    if user_pref.get("genres"):
        user_pref["genres"] = [g.value for g in user_pref["genres"]]

    if user_pref.get("os"):
        user_pref["os"] = user_pref["os"].value

    if user_pref.get("price"):
        user_pref["price"] = user_pref["price"].value

    if user_pref.get("spec"):
        user_pref["spec"] = user_pref["spec"].value

    filtered = run_db_pipeline(df, user_pref)
    after_count = len(filtered)

    # JSON 안전 처리 (NaN / inf 제거)
    filtered = filtered.replace([float("inf"), float("-inf")], None)
    filtered = filtered.where(pd.notnull(filtered), None)

    return {
        "before_count": before_count,
        "after_count": after_count,
        "results": filtered.head(10).to_dict(orient="records")
    }