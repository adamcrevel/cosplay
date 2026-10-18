"""SQLite persistence for past `cosplay run` invocations.

One row per run, created the moment analysis starts and updated as the
pipeline progresses, so `cosplay list`/`cosplay show` can report a rejected
or failed run, not only a fully published one.
"""

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

DEFAULT_DB_PATH = Path.home() / ".cosplay" / "cosplay.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    image_path TEXT NOT NULL,
    status TEXT NOT NULL,
    people_count INTEGER,
    omp_model TEXT,
    image_model TEXT,
    features_json TEXT,
    candidates_json TEXT,
    chosen_index INTEGER,
    chosen_name TEXT,
    result_image_path TEXT,
    gist_url TEXT,
    error TEXT
);
"""


def _now() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(UTC).isoformat()


@dataclass
class Run:
    """A persisted run row.

    Attributes:
        id: Row id, assigned on `create_run`.
        created_at: ISO-8601 UTC creation timestamp.
        image_path: Path to the input photo, as given on the command line.
        status: One of `"analyzing"`, `"rejected_no_person"`,
            `"rejected_multiple_people"`, `"generating"`, `"generated"`,
            `"published"`, or `"failed"`.
        people_count: The analysis's `people_count`, once known.
        omp_model: The `omp --model` value used for analysis.
        image_model: The image provider's model id, once generation starts.
        features: The analysis's `features` dict, once known.
        candidates: `[{"name": ..., "reason": ...}, ...]`, once known.
        chosen_index: Index into `candidates` of the chosen one, once known.
        chosen_name: `candidates[chosen_index]["name"]`, duplicated here so
            `cosplay list` can show it without re-parsing `candidates`.
        result_image_path: Local path to the generated image, once saved.
        gist_url: The published gist's URL, once published.
        error: The error message, if `status == "failed"`.
    """

    id: int
    created_at: str
    image_path: str
    status: str
    people_count: int | None = None
    omp_model: str | None = None
    image_model: str | None = None
    features: dict[str, str] = field(default_factory=dict)
    candidates: list[dict[str, str]] = field(default_factory=list)
    chosen_index: int | None = None
    chosen_name: str | None = None
    result_image_path: str | None = None
    gist_url: str | None = None
    error: str | None = None


def _row_to_run(row: sqlite3.Row) -> Run:
    """Convert a `sqlite3.Row` from `runs` into a `Run`."""
    return Run(
        id=row["id"],
        created_at=row["created_at"],
        image_path=row["image_path"],
        status=row["status"],
        people_count=row["people_count"],
        omp_model=row["omp_model"],
        image_model=row["image_model"],
        features=json.loads(row["features_json"]) if row["features_json"] else {},
        candidates=json.loads(row["candidates_json"]) if row["candidates_json"] else [],
        chosen_index=row["chosen_index"],
        chosen_name=row["chosen_name"],
        result_image_path=row["result_image_path"],
        gist_url=row["gist_url"],
        error=row["error"],
    )


class Store:
    """Wraps a SQLite connection and provides CRUD for `runs`."""

    def __init__(self, db_path: Path = DEFAULT_DB_PATH) -> None:
        """Open (creating if needed) the SQLite database at `db_path`.

        Args:
            db_path: Path to the SQLite file. Its parent directory is
                created if missing.
        """
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        self._conn.close()

    def create_run(self, *, image_path: str, status: str = "analyzing") -> int:
        """Insert a new run row and return its id.

        Args:
            image_path: Path to the input photo, as given on the command
                line.
            status: Initial status.

        Returns:
            The new row's id.
        """
        cursor = self._conn.execute(
            "INSERT INTO runs (created_at, image_path, status) VALUES (?, ?, ?)",
            (_now(), image_path, status),
        )
        self._conn.commit()
        return cursor.lastrowid

    def update_run(self, run_id: int, **fields: object) -> None:
        """Update one or more columns on run `run_id`.

        `features` and `candidates`, if given, are JSON-encoded into
        `features_json`/`candidates_json` automatically.

        Args:
            run_id: The row id to update.
            **fields: Column values to set, by name (`status`,
                `people_count`, `omp_model`, `image_model`, `features`,
                `candidates`, `chosen_index`, `chosen_name`,
                `result_image_path`, `gist_url`, `error`).

        Raises:
            ValueError: If a key in `fields` isn't a known column, or
                `fields` is empty.
        """
        if not fields:
            raise ValueError("update_run called with no fields")

        column_map = {
            "status": "status",
            "people_count": "people_count",
            "omp_model": "omp_model",
            "image_model": "image_model",
            "features": "features_json",
            "candidates": "candidates_json",
            "chosen_index": "chosen_index",
            "chosen_name": "chosen_name",
            "result_image_path": "result_image_path",
            "gist_url": "gist_url",
            "error": "error",
        }
        set_clauses = []
        values: list[object] = []
        for key, value in fields.items():
            if key not in column_map:
                raise ValueError(f"unknown run field: {key!r}")
            if key in ("features", "candidates"):
                value = json.dumps(value)
            set_clauses.append(f"{column_map[key]} = ?")
            values.append(value)
        values.append(run_id)

        self._conn.execute(f"UPDATE runs SET {', '.join(set_clauses)} WHERE id = ?", values)
        self._conn.commit()

    def get_run(self, run_id: int) -> Run | None:
        """Return the run with id `run_id`, or `None` if it doesn't exist."""
        row = self._conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        return _row_to_run(row) if row is not None else None

    def list_runs(self) -> list[Run]:
        """Return every run, oldest first."""
        rows = self._conn.execute("SELECT * FROM runs ORDER BY id ASC").fetchall()
        return [_row_to_run(row) for row in rows]
