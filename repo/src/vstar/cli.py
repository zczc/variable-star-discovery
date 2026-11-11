import argparse
import json
from pathlib import Path
from . import __version__
from .io import read_json
from .models import load_config
from .pipeline import create_run, execute_run
from .reports import generate_report
from .submission import export_vsx


def main(argv=None):
    parser = argparse.ArgumentParser(prog="vstar", description="TESS 变星候选分析；结果不代表已确认发现。")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run")
    run.add_argument("--config", type=Path, required=True)
    run.add_argument("--offline", action="store_true")
    run.add_argument("--limit", type=int)
    run.add_argument("--run-id")
    for name in ["resume", "report"]:
        commands.add_parser(name).add_argument("run", type=Path, help="运行目录路径")
    inspect = commands.add_parser("inspect")
    inspect.add_argument("tic")
    inspect.add_argument("--run", type=Path, required=True)
    export = commands.add_parser("export-vsx", help="只导出本地草稿，不发送到 AAVSO")
    export.add_argument("tic")
    export.add_argument("--run", type=Path, required=True)
    export.add_argument("--review", type=Path, help="人工复核字段和图片清单 JSON")
    for name in ["review-v2", "review-v3"]:
        review = commands.add_parser(name, help="实验规则；分析给定的同一目标多时段 FITS")
        review.add_argument("lightcurves", nargs="+", type=Path)
        review.add_argument("--output", required=True, type=Path)
        review.add_argument("--neighbors", type=Path, help="可选 VSX 邻域条目 JSON 列表")
    products = commands.add_parser("review-products", help="SAP 与 PDCSAP 各自搜索，再检查产品差异")
    products.add_argument("lightcurves", nargs="+", type=Path)
    products.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "review-products":
            from .products import review_products
            row = review_products(args.lightcurves, args.output)
            print(args.output.resolve()/"index.html")
            return 2 if row["errors"] else 0
        elif args.command in {"review-v2", "review-v3"}:
            from .review import review_files
            row = review_files(args.lightcurves, args.output, read_json(args.neighbors) if args.neighbors else None, revision=args.command.removeprefix("review-"))
            print(args.output.resolve()/"index.html")
            return 2 if row["errors"] else 0
        elif args.command == "run":
            root = create_run(load_config(args.config), args.offline, args.limit, args.run_id)
        elif args.command == "resume":
            root = execute_run(args.run)
        elif args.command == "report":
            print(generate_report(args.run.resolve()))
            return 0
        elif args.command == "export-vsx":
            path, validation = export_vsx(args.run, args.tic, args.review)
            print(f"{validation['status']}: {path}")
            print(json.dumps(validation, ensure_ascii=False, indent=2))
            return 2 if validation["missing"] else 0
        else:
            rows = read_json(args.run / "summary.json")["targets"]
            target = next((r for r in rows if r["tic"] == args.tic), None)
            if target is None:
                raise ValueError(f"TIC {args.tic} is not in this run")
            print(json.dumps(target, ensure_ascii=False, indent=2))
            return 0
        print(f"Report: {root / 'report/index.html'}")
        return 2 if any(r["errors"] for r in read_json(root / "summary.json")["targets"]) else 0
    except (ValueError, OSError, RuntimeError) as exc:
        parser.exit(1, f"vstar: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
