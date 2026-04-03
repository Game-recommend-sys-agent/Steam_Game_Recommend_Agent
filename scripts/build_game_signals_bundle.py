"""
(6~8) 게임 시그널 번들 생성기:
- raw 미싱/TTL 만료 시 on-demand로 raw를 보충(SteamClient 호출)
- raw → interim(data/interim) 요약/정규화 저장
- interim → processed(data/processed) appid 단위 번들 저장(+ TTL)

참고: `docs/context_aware_5to8.md`
"""

from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from tqdm import tqdm

from src.game_recommendation.api.steam_client import SteamClient, SteamClientConfig
from src.game_recommendation.context_aware.game_signals import (
    GameSignalsPaths,
    build_interim_game_signals,
    build_processed_game_bundle,
    is_processed_bundle_fresh,
    load_raw_game_signals,
    processed_bundle_path,
    write_interim_game_signals,
    write_processed_game_bundle,
)


def _parse_appids(appids_csv: str | None, appids_file: str | None) -> list[int]:
    if appids_csv:
        items = [x.strip() for x in appids_csv.split(",") if x.strip()]
        return [int(x) for x in items]
    if appids_file:
        p = Path(appids_file)
        txt = p.read_text(encoding="utf-8")
        out: list[int] = []
        for line in txt.splitlines():
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            out.append(int(s))
        return out
    raise SystemExit("Either --appids or --appids-file is required.")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Build (6~8) game signal bundles with TTL.")
    parser.add_argument("--appids", help="Comma-separated appids. e.g. 570,730")
    parser.add_argument("--appids-file", help="Text file: one appid per line (# comment ok)")

    parser.add_argument("--raw-dir", default="data/raw")
    parser.add_argument("--interim-dir", default="data/interim")
    parser.add_argument("--processed-dir", default="data/processed")

    parser.add_argument("--cc", default="us")
    parser.add_argument("--lang", default="en")
    parser.add_argument("--review-lang", default="all")

    parser.add_argument("--ttl-hours", type=float, default=24.0)
    parser.add_argument("--force", action="store_true", help="Rebuild even if TTL not expired")

    # SteamClient 네트워크/정책 파라미터
    parser.add_argument("--news-count", type=int, default=20)
    parser.add_argument("--news-maxlength", type=int, default=300)
    parser.add_argument("--min-interval-web", type=float, default=0.25)
    parser.add_argument("--min-interval-store", type=float, default=0.35)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--max-retries", type=int, default=4)
    args = parser.parse_args(argv)

    # .env 로드 (프로젝트 루트 또는 config/.env)
    root = Path(__file__).resolve().parents[1]
    load_dotenv(root / ".env")
    load_dotenv(root / "config" / ".env")
    steam_api_key = os.environ.get("STEAM_API_KEY")

    appids = _parse_appids(args.appids, args.appids_file)

    paths = GameSignalsPaths(
        raw_dir=Path(args.raw_dir),
        interim_dir=Path(args.interim_dir),
        processed_dir=Path(args.processed_dir),
    )

    cfg = SteamClientConfig(
        timeout_s=float(args.timeout),
        max_retries=int(args.max_retries),
        min_interval_web_s=float(args.min_interval_web),
        min_interval_store_s=float(args.min_interval_store),
        news_count=int(args.news_count),
        news_maxlength=int(args.news_maxlength),
    )

    ttl_seconds = int(float(args.ttl_hours) * 3600)
    now_ts = int(time.time())

    with SteamClient(steam_api_key=steam_api_key, raw_dir=paths.raw_dir, config=cfg) as client:
        for appid in tqdm(appids, desc="bundle", unit="app"):
            out_path = processed_bundle_path(appid, paths=paths, cc=args.cc, lang=args.lang)
            if not args.force and is_processed_bundle_fresh(out_path, now_ts=now_ts):
                continue

            # raw 보충(on-demand): raw가 없거나 오래됐는지까지는 여기서 판단하지 않고,
            # "일단 필요한 raw를 최신으로" 다시 받아둔다(요청 비용 vs 단순성 트레이드오프).
            client.get_appdetails(appid, cc=args.cc, lang=args.lang)
            client.get_appreviews_summary(appid, lang=args.review_lang)
            client.get_schema_for_game(appid)
            client.get_news_for_app(appid)

            raw = load_raw_game_signals(appid, paths=paths, cc=args.cc, lang=args.lang)
            interim = build_interim_game_signals(appid, raw, cc=args.cc, lang=args.lang, now_ts=now_ts)
            write_interim_game_signals(interim, paths=paths, appid=appid, cc=args.cc, lang=args.lang)

            bundle = build_processed_game_bundle(interim, ttl_seconds=ttl_seconds, now_ts=now_ts)
            write_processed_game_bundle(bundle, paths=paths, appid=appid, cc=args.cc, lang=args.lang)


if __name__ == "__main__":
    main()

