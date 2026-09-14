"""CLI entry point: python -m f1pred <command>."""
import argparse

from f1pred import config


def main() -> None:
    parser = argparse.ArgumentParser(prog="f1pred")
    sub = parser.add_subparsers(dest="command", required=True)

    p_fetch = sub.add_parser("fetch", help="Download session data (no telemetry) to data/raw")
    p_fetch.add_argument("--seasons", type=int, nargs="+", default=config.seasons(),
                         help="Fetched in the order given; default is newest first")
    p_fetch.add_argument("--rounds", type=int, nargs="+", help="Only these round numbers")
    p_fetch.add_argument("--dry-run", action="store_true", help="Only the first 2 events per season")
    p_fetch.add_argument("--keep-cache", action="store_true", help="Do not delete FastF1 cache after each event")

    sub.add_parser("build", help="Combine raw parquet into data/processed")

    p_back = sub.add_parser("backtest", help="Walk-forward backtest vs grid baseline")
    p_back.add_argument("--season", type=int, help="Default: latest season with results")
    p_back.add_argument("--start-round", type=int, default=4)

    p_pred = sub.add_parser("predict", help="Predict a race after qualifying")
    p_pred.add_argument("season", type=int)
    p_pred.add_argument("event", help="Round number or event name, e.g. Singapore")
    p_pred.add_argument("--no-refresh", action="store_true", help="Skip fetch/build")

    args = parser.parse_args()

    if args.command == "build":
        from f1pred import build
        build.run()

    if args.command == "backtest":
        from f1pred import build, evaluate
        from f1pred.features import build_features
        feats = build_features(*build.load_processed())
        season = args.season or int(feats.loc[feats["FinishPosition"].notna(), "Season"].max())
        results = evaluate.backtest(feats, season, args.start_round)
        print(results.round(3).to_string(index=False))
        print("\n" + evaluate.summarize(results).to_string())

    if args.command == "predict":
        from f1pred import predict
        predict.run(args.season, args.event, refresh=not args.no_refresh)

    if args.command == "fetch":
        from f1pred import fetch
        fetch.run(
            seasons=args.seasons,
            max_events=2 if args.dry_run else None,
            rounds=args.rounds,
            keep_cache=args.keep_cache,
        )


if __name__ == "__main__":
    main()
