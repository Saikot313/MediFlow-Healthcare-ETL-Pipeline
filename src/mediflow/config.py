from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_WAREHOUSE_URL = "postgresql+psycopg2://warehouse:warehouse@localhost:5432/warehouse"


@dataclass(frozen=True)
class Settings:
    warehouse_url: str
    data_dir: Path
    sql_dir: Path
    max_reject_ratio: float

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def clean_dir(self) -> Path:
        return self.data_dir / "clean"

    @property
    def rejected_dir(self) -> Path:
        return self.data_dir / "rejected"

    @property
    def reference_dir(self) -> Path:
        return self.data_dir / "reference"


def get_settings() -> Settings:
    env = os.environ.get
    return Settings(
        warehouse_url=env("MEDIFLOW_WAREHOUSE_URL", DEFAULT_WAREHOUSE_URL),
        data_dir=Path(env("MEDIFLOW_DATA_DIR", str(PROJECT_ROOT / "data"))),
        sql_dir=Path(env("MEDIFLOW_SQL_DIR", str(PROJECT_ROOT / "sql"))),
        max_reject_ratio=float(env("MEDIFLOW_MAX_REJECT_RATIO", "0.20")),
    )
