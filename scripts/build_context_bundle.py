"""
context_bundle 조립 스크립트

- 입력:
  - steam_id(유저)
  - appids(후보 게임들)
  - (5) user_behavior(processed) + (6~8) game_bundles(processed)
- 출력:
  - data/processed/context_bundles/{steam_id}__cc={cc}__lang={lang}.json

참고: docs/context_aware_5to8.md
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from src.game_recommendation.context_aware.context_bundle import (
    ContextBundlePaths,
    assemble_context_bundle,
    validate_context_bundle,
    write_context_bundle,
)


def _parse_appids(appids_csv: str | None) -> list[int]:
    if not appids_csv:
        return []
    items = [x.strip() for x in appids_csv.split(",") if x.strip()]
    out: list[int] = []
    for s in items:
        try:
            out.append(int(s))
        except ValueError:
            continue
    return out


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Assemble context_bundle(user + games).")
    p.add_argument("--steam-id", required=True)
    p.add_argument("--appids", help="Comma-separated appids. e.g. 570,730")
    p.add_argument("--from-anchors", action="store_true", help="Use user.behavior.context_anchor_appids as appids when --appids is omitted")

    p.add_argument("--cc", default="us")
    p.add_argument("--lang", default="en")

    p.add_argument("--processed-dir", default="data/processed")
    p.add_argument("--include-game-bundle-meta", action="store_true", help="Include per-game _bundle_meta for TTL debugging")

    p.add_argument("--validate", action="store_true", help="Run sanity validation and print issues")
    p.add_argument("--strict", action="store_true", help="Exit non-zero if validation issues exist")

    args = p.parse_args(argv)
    now_ts = int(time.time())

    paths = ContextBundlePaths(processed_dir=Path(args.processed_dir))

    appids = _parse_appids(args.appids)
    if not appids and args.from_anchors:
        # lazy import to avoid pulling behavior module when not needed
        from src.game_recommendation.context_aware.context_bundle import load_behavior_processed

        beh = load_behavior_processed(args.steam_id, paths=paths)
        anchors = (
            beh.get("behavior", {}).get("context_anchor_appids", [])
            if isinstance(beh, dict)
            else []
        )
        if isinstance(anchors, list):
            appids = [int(x) for x in anchors if isinstance(x, int)]

    bundle = assemble_context_bundle(
        steam_id=args.steam_id,
        appids=appids,
        paths=paths,
        cc=args.cc,
        lang=args.lang,
        now_ts=now_ts,
        include_game_bundle_meta=bool(args.include_game_bundle_meta),
    )
    out_path = write_context_bundle(bundle, steam_id=args.steam_id, paths=paths, cc=args.cc, lang=args.lang)
    print(str(out_path))

    if args.validate or args.strict:
        issues = validate_context_bundle(bundle)
        if issues:
            print("validation_issues:")
            for it in issues:
                print(f"- {it}")
            if args.strict:
                raise SystemExit(2)
        else:
            print("validation_ok")


if __name__ == "__main__":
    main()

