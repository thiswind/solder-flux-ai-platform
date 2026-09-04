from __future__ import annotations

import argparse
from pathlib import Path

from yunxi_data_platform import YunxiDataPlatform


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Yunxi data preprocessing platform from project root.")
    parser.add_argument(
        "--root",
        default=str(Path(__file__).resolve().parent),
        help="Project root directory. Defaults to the directory of this script.",
    )
    parser.add_argument(
        "--export-tag",
        default=None,
        help="Optional export tag used in output file names.",
    )
    parser.add_argument(
        "--skip-images",
        action="store_true",
        help="Skip image inventory and linkage steps.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    platform = YunxiDataPlatform(args.root)
    artifacts = platform.run(export_tag=args.export_tag, include_images=not args.skip_images)

    print("Yunxi data platform finished successfully.")
    print(f"run_id: {artifacts.run_id}")
    print(f"export_excel: {artifacts.export_excel_path}")
    print(f"export_csv_dir: {artifacts.export_csv_dir}")
    print(f"review_excel: {artifacts.review_excel_path}")
    print(f"summary_json: {artifacts.summary_json_path}")


if __name__ == "__main__":
    main()
