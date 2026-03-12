import pandas as pd

GENRE_GROUP_MAP = {
    "액션": ["Action", "Shooter", "Platformer"],
    "RPG": ["RPG", "JRPG", "CRPG"],
    "전략": ["Strategy", "RTS", "Turn-Based Strategy"],
    "시뮬레이션": ["Simulation", "Sandbox"],
    "스토리 중심": ["Visual Novel"],
    "퍼즐": ["Puzzle"],
    "온라인": ["MMORPG", "Multiplayer"],
    "제작": ["Design", "Utility"],
}


# =====================================================
# 장르 필터 (복수 선택 / OR 조건)
# =====================================================
def filter_genres(df, selected_genres):

    if not selected_genres:
        return df

    def match(row_genres):
        if pd.isna(row_genres) or not row_genres:
            return False

        row_list = [g.strip() for g in row_genres.split(",")]

        for ui_genre in selected_genres:
            db_keywords = GENRE_GROUP_MAP.get(ui_genre, [])

            for keyword in db_keywords:
                for g in row_list:
                    if keyword.lower() in g.lower():
                        return True

        return False

    return df[df["genres"].apply(match)]


# =====================================================
# 메인 필터 파이프라인
# =====================================================
def run_db_pipeline(df, user_pref: dict):

    df = df.copy()
    print(f"[db_pipeline] Initial rows: {len(df)}")

    # =================================================
    # OS (단일 선택)
    # =================================================
    user_os = user_pref.get("os")
    if user_os in ["windows", "mac", "linux"]:
        df = df[df[user_os] == True]
    print(f"[db_pipeline] After OS filter ({user_os}): {len(df)}")

    # =================================================
    # Age (최대 허용 연령)
    # =================================================
    user_age = user_pref.get("age")
    if user_age is not None:
        df = df[
            (df["age_limit"].isna()) |
            (df["age_limit"] <= user_age)
        ]
    print(f"[db_pipeline] After Age filter ({user_age}): {len(df)}")

    # =================================================
    # Price
    # "모든 가격"이면 None → 필터 미적용
    # =================================================
    price = user_pref.get("price")

    if price == "<10000":
        df = df[df["final_price_cents"] < 10000]

    elif price == "10000-30000":
        df = df[
            (df["final_price_cents"] >= 10000) &
            (df["final_price_cents"] < 30000)
        ]

    elif price == ">=30000":
        df = df[df["final_price_cents"] >= 30000]
    print(f"[db_pipeline] After Price filter ({price}): {len(df)}")

    # =================================================
    # Spec (사용자 PC 사양 기준)
    # low / mid → 필터 적용
    # high → 필터 미적용
    # =================================================
    spec = user_pref.get("spec")

    if spec in ["low", "mid"]:

        limits = {
            "low": 8,   # 8GB 이하 게임만
            "mid": 12,  # 12GB 이하 게임만
        }

        limit = limits.get(spec)

        df = df[
            (df["min_ram_gb"].isna()) |
            (df["min_ram_gb"] <= limit)
        ]
    print(f"[db_pipeline] After Spec filter ({spec}): {len(df)}")

    # high → 아무 필터도 적용 안 함

    # =================================================
    # Genre (복수 OR 조건)
    # =================================================
    genres = user_pref.get("genres")
    if genres:
        df = filter_genres(df, genres)
    print(f"[db_pipeline] After Genre filter ({genres}): {len(df)}")

    # =================================================
    # JSON 안전 처리 (NaN / inf 제거)
    # =================================================
    df = df.replace([float("inf"), float("-inf")], None)
    df = df.where(pd.notnull(df), None)

    return df