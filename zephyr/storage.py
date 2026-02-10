from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class MarketMetadata:
    market_slug: str
    condition_id: str | None
    question: str | None
    event_title: str | None
    event_type: str | None
    city_label: str | None
    event_date: str | None
    threshold_value: float | None
    threshold_unit: str | None
    yes_label: str | None
    volume: float | None
    liquidity: float | None
    last_seen_utc: str


@dataclass(frozen=True)
class SnapshotRow:
    collected_at_utc: str
    model: str
    run_date: str | None
    run_cycle_hour_utc: int | None
    market_slug: str
    contract_ticker: str | None
    event_id: str | None
    forecast_probability: float
    market_probability: float
    edge: float
    details: dict[str, object]


def connect_db(path: str) -> sqlite3.Connection:
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS markets (
            market_slug TEXT PRIMARY KEY,
            condition_id TEXT,
            question TEXT,
            event_title TEXT,
            event_type TEXT,
            city_label TEXT,
            event_date TEXT,
            threshold_value REAL,
            threshold_unit TEXT,
            yes_label TEXT,
            volume REAL,
            liquidity REAL,
            last_seen_utc TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            collected_at_utc TEXT NOT NULL,
            model TEXT NOT NULL,
            run_date TEXT,
            run_cycle_hour_utc INTEGER,
            market_slug TEXT NOT NULL,
            contract_ticker TEXT,
            event_id TEXT,
            forecast_probability REAL NOT NULL,
            market_probability REAL NOT NULL,
            edge REAL NOT NULL,
            details_json TEXT,
            FOREIGN KEY (market_slug) REFERENCES markets(market_slug),
            UNIQUE (model, run_date, run_cycle_hour_utc, market_slug)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS outcomes (
            market_slug TEXT PRIMARY KEY,
            event_date TEXT,
            outcome INTEGER NOT NULL CHECK (outcome IN (0, 1)),
            resolved_at_utc TEXT
        )
        """
    )
    conn.commit()


def upsert_market(conn: sqlite3.Connection, market: MarketMetadata) -> None:
    conn.execute(
        """
        INSERT INTO markets (
            market_slug,
            condition_id,
            question,
            event_title,
            event_type,
            city_label,
            event_date,
            threshold_value,
            threshold_unit,
            yes_label,
            volume,
            liquidity,
            last_seen_utc
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(market_slug) DO UPDATE SET
            condition_id=excluded.condition_id,
            question=excluded.question,
            event_title=excluded.event_title,
            event_type=excluded.event_type,
            city_label=excluded.city_label,
            event_date=excluded.event_date,
            threshold_value=excluded.threshold_value,
            threshold_unit=excluded.threshold_unit,
            yes_label=excluded.yes_label,
            volume=excluded.volume,
            liquidity=excluded.liquidity,
            last_seen_utc=excluded.last_seen_utc
        """,
        (
            market.market_slug,
            market.condition_id,
            market.question,
            market.event_title,
            market.event_type,
            market.city_label,
            market.event_date,
            market.threshold_value,
            market.threshold_unit,
            market.yes_label,
            market.volume,
            market.liquidity,
            market.last_seen_utc,
        ),
    )
    conn.commit()


def insert_snapshot(conn: sqlite3.Connection, snapshot: SnapshotRow) -> bool:
    try:
        conn.execute(
            """
            INSERT INTO snapshots (
                collected_at_utc,
                model,
                run_date,
                run_cycle_hour_utc,
                market_slug,
                contract_ticker,
                event_id,
                forecast_probability,
                market_probability,
                edge,
                details_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot.collected_at_utc,
                snapshot.model,
                snapshot.run_date,
                snapshot.run_cycle_hour_utc,
                snapshot.market_slug,
                snapshot.contract_ticker,
                snapshot.event_id,
                snapshot.forecast_probability,
                snapshot.market_probability,
                snapshot.edge,
                json.dumps(snapshot.details, sort_keys=True),
            ),
        )
    except sqlite3.IntegrityError:
        return False
    conn.commit()
    return True


def record_outcome(
    conn: sqlite3.Connection,
    *,
    market_slug: str,
    outcome: int,
    event_date: str | None = None,
    resolved_at_utc: str | None = None,
) -> None:
    if resolved_at_utc is None:
        resolved_at_utc = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT INTO outcomes (market_slug, event_date, outcome, resolved_at_utc)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(market_slug) DO UPDATE SET
            event_date=excluded.event_date,
            outcome=excluded.outcome,
            resolved_at_utc=excluded.resolved_at_utc
        """,
        (market_slug, event_date, outcome, resolved_at_utc),
    )
    conn.commit()
