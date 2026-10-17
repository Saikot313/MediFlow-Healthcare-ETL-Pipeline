from __future__ import annotations

import io
import logging
import re
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterator

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine

from .config import get_settings

log = logging.getLogger("mediflow.db")

_BLOCK_MARKER = re.compile(r"^--\s*@@\s*(\w+)[^\n]*", re.MULTILINE)


def get_engine(url: str | None = None) -> Engine:
    return create_engine(url or get_settings().warehouse_url, pool_pre_ping=True, future=True)



def run_sql_script(engine: Engine, path: Path) -> None:
    """Run a whole (DDL) file as one transaction. Files are written to be idempotent."""
    with engine.begin() as conn:
        conn.exec_driver_sql(Path(path).read_text(encoding="utf-8"))
    log.info("executed %s", Path(path).name)


def split_blocks(sql_text: str) -> list[tuple[str, str]]:
    """Split a file into (name, statement) pairs using '-- @@ name' markers."""
    marks = list(_BLOCK_MARKER.finditer(sql_text))
    blocks: list[tuple[str, str]] = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(sql_text)
        blocks.append((m.group(1), sql_text[m.end():end].strip()))
    return blocks


def run_blocks(engine: Engine, path: Path, params: dict) -> dict[str, int]:

    blocks = split_blocks(Path(path).read_text(encoding="utf-8"))
    counts: dict[str, int] = {}
    with engine.begin() as conn:
        for name, statement in blocks:
            result = conn.execute(text(statement), params)
            counts[name] = max(result.rowcount, 0)
            log.info("%s: %s row(s)", name, counts[name])
    return counts



def copy_dataframe(conn: Connection, df: pd.DataFrame, table: str, columns: list[str]) -> int:
    if df.empty:
        return 0
    buf = io.StringIO()
    df[columns].to_csv(buf, index=False, header=False, na_rep="\\N")
    buf.seek(0)
    cur = conn.connection.cursor()
    try:
        cur.copy_expert(
            f"COPY {table} ({', '.join(columns)}) FROM STDIN WITH (FORMAT csv, NULL '\\N')", buf
        )
        return cur.rowcount
    finally:
        cur.close()



@dataclass
class StepStats:
    rows_in: int | None = None
    rows_out: int | None = None
    rows_rejected: int | None = None
    message: str | None = None


@contextmanager
def log_step(engine: Engine, batch_date: date, step: str) -> Iterator[StepStats]:
    """Record a pipeline step in audit.etl_run_log (running -> success / failed)."""
    with engine.begin() as conn:
        run_id = conn.execute(
            text(
                "INSERT INTO audit.etl_run_log (batch_date, step, status) "
                "VALUES (:d, :s, 'running') RETURNING run_id"
            ),
            {"d": batch_date, "s": step},
        ).scalar()
    stats = StepStats()
    try:
        yield stats
    except Exception as exc:
        _finish(engine, run_id, "failed", stats, str(exc)[:2000])
        raise
    else:
        _finish(engine, run_id, "success", stats, stats.message)


def _finish(engine: Engine, run_id: int, status: str, s: StepStats, message: str | None) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE audit.etl_run_log SET status = :st, rows_in = :ri, rows_out = :ro, "
                "rows_rejected = :rr, message = :m, finished_at = now() WHERE run_id = :id"
            ),
            {"st": status, "ri": s.rows_in, "ro": s.rows_out, "rr": s.rows_rejected,
             "m": message, "id": run_id},
        )
