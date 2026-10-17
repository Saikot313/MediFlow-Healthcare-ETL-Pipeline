from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, timedelta

from . import pipeline
from .config import get_settings
from .generate_data import generate


def _date(s: str) -> date:
    return date.fromisoformat(s)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mediflow", description="MediFlow healthcare ETL")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="create warehouse schemas, tables and views")

    g = sub.add_parser("generate", help="generate synthetic daily source files")
    g.add_argument("--start", type=_date, required=True)
    g.add_argument("--days", type=int, default=14)
    g.add_argument("--seed", type=int, default=42)
    g.add_argument("--patients", type=int, default=1500)
    g.add_argument("--dirty-rate", type=float, default=0.02)

    r = sub.add_parser("run", help="run the pipeline for one date")
    r.add_argument("--date", type=_date, required=True)

    b = sub.add_parser("backfill", help="run the pipeline for a date range, in order")
    b.add_argument("--start", type=_date, required=True)
    b.add_argument("--end", type=_date, required=True)

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    s = get_settings()

    if args.cmd == "init":
        pipeline.init_warehouse()
    elif args.cmd == "generate":
        folders = generate(args.start, args.days, s.raw_dir, s.reference_dir, seed=args.seed,
                           n_patients=args.patients, dirty_rate=args.dirty_rate)
        print(f"generated {len(folders)} daily batch(es) in {s.raw_dir}")
    elif args.cmd == "run":
        pipeline.init_warehouse()
        print(json.dumps(pipeline.run_batch(args.date), indent=2, default=str))
    elif args.cmd == "backfill":
        results = pipeline.backfill(args.start, args.end)
        print(f"loaded {len(results)} batch(es): {args.start} -> {args.end}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
