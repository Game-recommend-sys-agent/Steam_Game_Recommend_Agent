# 명령어는 이렇게 적기
# python run_filter.py '{"os":"windows","age":15,"price":"10000-30000","spec":"mid","genres":["RPG"]}'

import sys
import json

from load_data import load_games_df
from db_pipeline import run_db_pipeline


def main():

    # 1️⃣ 입력값을 외부에서 받음
    if len(sys.argv) > 1:
        user_pref = json.loads(sys.argv[1])
    else:
        raise ValueError("사용자 입력 JSON이 필요합니다.")

    # 2️⃣ DB 로드
    df = load_games_df()

    # 3️⃣ 필터 실행
    filtered = run_db_pipeline(df, user_pref)

    # 4️⃣ JSON 반환
    print(filtered.to_json(orient="records"))


if __name__ == "__main__":
    main()