from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PlatformPaths:
    root_dir: Path
    excel_dir: Path
    uploads_dir: Path
    overall_upload_dir: Path
    specific_upload_dir: Path
    image_upload_dir: Path
    output_dir: Path
    export_dir: Path
    config_dir: Path
    db_dir: Path
    db_path: Path
    review_dir: Path

    @classmethod
    def from_root(cls, root_dir: Path | str) -> "PlatformPaths":
        root = Path(root_dir).resolve()
        uploads_dir = root / "uploads"
        output_dir = root / "outputs"
        config_dir = output_dir / "config"
        db_dir = output_dir / "db"
        export_dir = output_dir / "exports"
        review_dir = output_dir / "review"

        return cls(
            root_dir=root,
            excel_dir=root / "excel",
            uploads_dir=uploads_dir,
            overall_upload_dir=uploads_dir / "overall_data",
            specific_upload_dir=uploads_dir / "specific_data",
            image_upload_dir=uploads_dir / "image",
            output_dir=output_dir,
            export_dir=export_dir,
            config_dir=config_dir,
            db_dir=db_dir,
            db_path=db_dir / "yunxi_data_platform.sqlite",
            review_dir=review_dir,
        )

    def ensure_directories(self) -> None:
        for path in (
            self.output_dir,
            self.export_dir,
            self.config_dir,
            self.db_dir,
            self.review_dir,
            self.uploads_dir,
            self.overall_upload_dir,
            self.specific_upload_dir,
            self.image_upload_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)
