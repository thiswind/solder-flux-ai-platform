from __future__ import annotations

import argparse
from pathlib import Path

from .pipeline import YunxiDataPlatform


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Yunxi data preprocessing platform pipeline.")
    parser.add_argument(
        "--root",
        default=str(Path(__file__).resolve().parents[1]),
        help="Platform root directory. Defaults to the project root.",
    )
    parser.add_argument(
        "--export-tag",
        default=None,
        help="Optional export tag used in output file names.",
    )
    parser.add_argument(
        "--skip-images",
        action="store_true",
        help="Skip image inventory and image linkage steps.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    platform = YunxiDataPlatform(args.root)
    artifacts = platform.run(export_tag=args.export_tag, include_images=not args.skip_images)

    print(f"Pipeline run_id: {artifacts.run_id}")
    print(f"Export Excel: {artifacts.export_excel_path}")
    print(f"Export CSV dir: {artifacts.export_csv_dir}")
    print(f"Review Excel: {artifacts.review_excel_path}")
    print(f"Summary JSON: {artifacts.summary_json_path}")


if __name__ == "__main__":
    main()
