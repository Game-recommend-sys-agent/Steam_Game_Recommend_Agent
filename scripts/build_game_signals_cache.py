"""
(6~8) 게임 단위 시그널 raw 캐시 생성/갱신 스크립트.

역할:
- appid 리스트를 돌면서 appdetails / appreviews 요약 / schema / news를 수집
- data/raw, data/interim 등에 저장(캐시)

구현 상세는 `docs/context_aware_5to8.md` 참고.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv
from tqdm import tqdm

from src.game_recommendation.api.steam_client import SteamClient, SteamClientConfig


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
    parser = argparse.ArgumentParser(
        description="Build raw cache for (6~8): appdetails/appreviews(schema summary)/schema/news"
    )
    parser.add_argument("--appids", help="Comma-separated appids. e.g. 570,730")
    parser.add_argument("--appids-file", help="Text file: one appid per line (# comment ok)")
    parser.add_argument("--raw-dir", default="data/raw", help="Base directory for raw json")
    parser.add_argument("--cc", default="us")
    parser.add_argument("--lang", default="en")
    parser.add_argument("--review-lang", default="all", help="appreviews language")
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

    cfg = SteamClientConfig(
        timeout_s=float(args.timeout),
        max_retries=int(args.max_retries),
        min_interval_web_s=float(args.min_interval_web),
        min_interval_store_s=float(args.min_interval_store),
        news_count=int(args.news_count),
        news_maxlength=int(args.news_maxlength),
    )

    raw_dir = Path(args.raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)

    with SteamClient(steam_api_key=steam_api_key, raw_dir=raw_dir, config=cfg) as client:
        for appid in tqdm(appids, desc="raw-cache", unit="app"):
            # (8) discount input
            client.get_appdetails(appid, cc=args.cc, lang=args.lang)

            # (6) quality/trust inputs
            client.get_appreviews_summary(appid, lang=args.review_lang)
            client.get_schema_for_game(appid)

            # (7) live input
            client.get_news_for_app(appid)


if __name__ == "__main__":
    main()

