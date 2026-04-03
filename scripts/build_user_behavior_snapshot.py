"""
(5) 유저 행동(Behavior) 스냅샷 생성 스크립트 (placeholder).

역할:
- steam_id로 OwnedGames를 받아 BehaviorContext를 계산
- (선택) data/processed에 user_snapshot 저장

구현 상세는 `docs/context_aware_5to8.md` 참고.
"""

from __future__ import annotations


import argparse
import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv

from src.game_recommendation.api.steam_client import SteamClient, SteamClientConfig
from src.game_recommendation.context_aware.behavior_activity import (
    UserBehaviorPaths,
    build_interim_user_games_table,
    compute_behavior_context,
    load_raw_owned_games,
    processed_behavior_context_path,
    raw_owned_games_path,
    write_interim_user_games_table,
)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Build (5) user behavior snapshot from OwnedGames.")
    parser.add_argument("--steam-id", required=True, help="SteamID64 (string)")
    parser.add_argument("--raw-dir", default="data/raw")
    parser.add_argument("--interim-dir", default="data/interim")
    parser.add_argument("--processed-dir", default="data/processed")

    # activity_state gate params (docs: X/Y should be configurable)
    parser.add_argument("--active-threshold-hours", type=float, default=5.0, help="X")
    parser.add_argument("--cooling-off-days", type=int, default=14, help="Y")
    parser.add_argument("--max-anchors", type=int, default=10)
    parser.add_argument("--include-debug-log", action="store_true")

    # SteamClient network/policy params (only used when fetching)
    parser.add_argument("--min-interval-web", type=float, default=0.25)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--max-retries", type=int, default=4)
    parser.add_argument(
        "--fetch-if-missing",
        action="store_true",
        help="If raw owned_games is missing, fetch it via Steam Web API.",
    )
    args = parser.parse_args(argv)

    steam_id = str(args.steam_id)

    # .env 로드 (프로젝트 루트 또는 config/.env)
    root = Path(__file__).resolve().parents[1]
    load_dotenv(root / ".env")
    load_dotenv(root / "config" / ".env")
    steam_api_key = os.environ.get("STEAM_API_KEY")

    paths = UserBehaviorPaths(
        raw_dir=Path(args.raw_dir),
        interim_dir=Path(args.interim_dir),
        processed_dir=Path(args.processed_dir),
    )

    now_ts = int(time.time())

    # raw OwnedGames 확보 (없으면 선택적으로 fetch)
    raw_path = raw_owned_games_path(steam_id, paths=paths)
    if not raw_path.exists():
        if not args.fetch_if_missing:
            raise SystemExit(
                f"Missing raw owned_games: {raw_path}. "
                "Run fetch first or use --fetch-if-missing."
            )

        cfg = SteamClientConfig(
            timeout_s=float(args.timeout),
            max_retries=int(args.max_retries),
            min_interval_web_s=float(args.min_interval_web),
            min_interval_store_s=0.35,
            news_count=20,
            news_maxlength=300,
        )
        with SteamClient(steam_api_key=steam_api_key, raw_dir=paths.raw_dir, config=cfg) as client:
            client.get_owned_games(steam_id)

    raw_owned = load_raw_owned_games(steam_id, paths=paths)
    interim_table = build_interim_user_games_table(steam_id, raw_owned, paths=paths, now_ts=now_ts)
    write_interim_user_games_table(steam_id, interim_table, paths=paths)

    owned_rows = interim_table.get("rows", [])
    behavior = compute_behavior_context(
        owned_rows,
        now_ts=now_ts,
        active_threshold_hours=float(args.active_threshold_hours),
        cooling_off_days=int(args.cooling_off_days),
        max_anchors=int(args.max_anchors),
        include_debug_log=bool(args.include_debug_log),
    )

    out_path = processed_behavior_context_path(steam_id, paths=paths)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "meta": {"steam_id": steam_id, "generated_at": now_ts},
        "steam_id": steam_id,
        "behavior": behavior,
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    # activity_state 근거 로그(디버깅 용)
    dbg = behavior.get("_debug") if isinstance(behavior, dict) else None
    if isinstance(dbg, dict):
        print(
            "activity_state_debug:",
            json.dumps(dbg, ensure_ascii=False),
        )

    print(f"wrote interim user_games: {Path(args.interim_dir) / 'user_games' / f'{steam_id}.json'}")
    print(f"wrote processed behavior: {out_path}")


if __name__ == "__main__":
    main()

