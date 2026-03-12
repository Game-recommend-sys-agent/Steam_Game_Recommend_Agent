import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))

from final_filters.load_data import load_games_df
from final_filters.db_pipeline import run_db_pipeline

df = load_games_df()
print("Starting total rows:", len(df))

user_pref = {
    "os": None,
    "age": None,
    "price": None,
    "spec": None,
    "genres": None,
    "limit": 50
}

df1 = df.copy()

user_os = user_pref.get("os")
if user_os in ["windows", "mac", "linux"]:
    df1 = df1[df1[user_os] == True]
print("After OS:", len(df1))

user_age = user_pref.get("age")
if user_age is not None:
    df1 = df1[(df1["age_limit"].isna()) | (df1["age_limit"] <= user_age)]
print("After Age:", len(df1))

price = user_pref.get("price")
if price == "<10000":
    df1 = df1[df1["final_price_cents"] < 10000]
elif price == "10000-30000":
    df1 = df1[(df1["final_price_cents"] >= 10000) & (df1["final_price_cents"] < 30000)]
elif price == ">=30000":
    df1 = df1[df1["final_price_cents"] >= 30000]
print("After Price:", len(df1))

spec = user_pref.get("spec")
if spec in ["low", "mid"]:
    limits = {"low": 8, "mid": 12}
    limit = limits.get(spec)
    df1 = df1[(df1["min_ram_gb"].isna()) | (df1["min_ram_gb"] <= limit)]
print("After Spec:", len(df1))

genres = user_pref.get("genres")
if genres:
    from final_filters.db_pipeline import filter_genres
    df1 = filter_genres(df1, genres)
print("After Genres:", len(df1))

df1 = df1.replace([float("inf"), float("-inf")], None)
df1 = df1.where(pd.notnull(df1), None)
print("After clean:", len(df1))
