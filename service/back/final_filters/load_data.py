"""
silver 스키마에서 게임 데이터를 로드해 DataFrame으로 반환한다.
"""

import pandas as pd
from sqlalchemy import create_engine, text

from core.config import settings

SNAPSHOT = "2026-02-11"


def _get_engine():
    return create_engine(settings.DATABASE_URL)


_QUERY = text("""
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
    AND os.snapshot_date = :snapshot

LEFT JOIN silver.game_age_limit age
    ON g.game_id = age.game_id
    AND age.snapshot_date = :snapshot

LEFT JOIN silver.game_prices p
    ON g.game_id = p.game_id
    AND p.snapshot_date = :snapshot

LEFT JOIN silver.game_assets a
    ON g.game_id = a.game_id
    AND a.snapshot_date = :snapshot

LEFT JOIN silver.game_extra_json extra
    ON g.game_id = extra.game_id
    AND extra.snapshot_date = :snapshot

LEFT JOIN silver.game_genres gg
    ON g.game_id = gg.game_id
    AND gg.snapshot_date = :snapshot

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
""")


_GAMES_CACHE: pd.DataFrame | None = None


def load_games_df() -> pd.DataFrame:
    """silver 스키마의 게임 데이터를 JOIN해 DataFrame으로 로드한다. (메모리 캐싱 적용)"""
    global _GAMES_CACHE
    if _GAMES_CACHE is not None:
        return _GAMES_CACHE.copy()

    engine = _get_engine()
    with engine.connect() as conn:
        df = pd.read_sql(_QUERY, conn, params={"snapshot": SNAPSHOT})
    
    _GAMES_CACHE = df
    return _GAMES_CACHE.copy()

