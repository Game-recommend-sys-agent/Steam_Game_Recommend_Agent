from dotenv import load_dotenv
import os
import pandas as pd
from sqlalchemy import create_engine, text

load_dotenv()

DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")

DATABASE_URL = (
    f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}"
    f"@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

engine = create_engine(DATABASE_URL)

SNAPSHOT = "2026-02-11"


def load_games_df(limit=None):
    query = f"""
    
SELECT
    g.game_id,
    g.game_name,

    os.windows,
    os.mac,
    os.linux,

    age.age_limit,

    p.final_price_cents,
    p.is_free,

    a.store_url,
    a.image_url,

    (extra.extra->>'detected_ram_gb')::float AS min_ram_gb,

    STRING_AGG(gg.genre_name, ',') AS genres

FROM silver.games g

LEFT JOIN silver.game_os_support os
    ON g.game_id = os.game_id
    AND os.snapshot_date = '{SNAPSHOT}'

LEFT JOIN silver.game_age_limit age
    ON g.game_id = age.game_id
    AND age.snapshot_date = '{SNAPSHOT}'

LEFT JOIN silver.game_prices p
    ON g.game_id = p.game_id
    AND p.snapshot_date = '{SNAPSHOT}'

LEFT JOIN silver.game_assets a
    ON g.game_id = a.game_id
    AND a.snapshot_date = '{SNAPSHOT}'

LEFT JOIN silver.game_extra_json extra
    ON g.game_id = extra.game_id
    AND extra.snapshot_date = '{SNAPSHOT}'

LEFT JOIN silver.game_genres gg
    ON g.game_id = gg.game_id
    AND gg.snapshot_date = '{SNAPSHOT}'

GROUP BY
    g.game_id,
    g.game_name,
    os.windows,
    os.mac,
    os.linux,
    age.age_limit,
    p.final_price_cents,
    p.is_free,
    a.store_url,
    a.image_url,
    extra.extra

"""

    if limit:
        query += f" LIMIT {limit}"

    df = pd.read_sql(text(query), engine)

    df["windows"] = df["windows"].fillna(False).astype(bool)
    df["mac"] = df["mac"].fillna(False).astype(bool)
    df["linux"] = df["linux"].fillna(False).astype(bool)

    df["age_limit"] = pd.to_numeric(df["age_limit"], errors="coerce")
    df["final_price_cents"] = pd.to_numeric(df["final_price_cents"], errors="coerce")
    df["min_ram_gb"] = pd.to_numeric(df["min_ram_gb"], errors="coerce")

    return df


if __name__ == "__main__":
    df = load_games_df(limit=10)
    print(df.head())