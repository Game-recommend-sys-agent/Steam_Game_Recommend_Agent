"""
(필터링 전) Top-K 후보 데모 스크립트

입력:
- context_bundle JSON 파일 (data/processed/context_bundles/...)

출력:
- appid/score/reason 의 Top-K JSON (stdout)

참고: docs/context_aware_5to8.md
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.game_recommendation.context_aware.topk_demo import DemoWeights, rank_topk_from_context_bundle


def _read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Demo: Top-K candidates from context_bundle (pre-filtering).")
    p.add_argument("--bundle", required=True, help="Path to context_bundle.json")
    p.add_argument("--top-k", type=int, default=10)

    p.add_argument("--w-quality", type=float, default=0.60)
    p.add_argument("--w-live", type=float, default=0.25)
    p.add_argument("--w-discount", type=float, default=0.15)
    p.add_argument("--reason-top-n", type=int, default=2)
    args = p.parse_args(argv)

    bundle = _read_json(Path(args.bundle))
    weights = DemoWeights(
        quality_trust=float(args.w_quality),
        live=float(args.w_live),
        discount=float(args.w_discount),
    )
    out = rank_topk_from_context_bundle(
        bundle,
        top_k=int(args.top_k),
        weights=weights,
        reason_top_n=int(args.reason_top_n),
    )
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

