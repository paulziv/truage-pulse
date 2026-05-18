"""
Storage abstraction. SQLite locally, Postgres in production (via DATABASE_URL).

Uses a tiny schema — settings (key/value), score_history (date/report/score),
and rules_of_org (markdown notes maintained on the settings page).

Run `python -m pulse.storage --init` to create tables.
"""
import os
import sqlite3
import json
import argparse
from contextlib import contextmanager
from pathlib import Path
from datetime import date

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "pulse.db"

# True when DATABASE_URL is set to a Postgres connection string
def _is_postgres() -> bool:
    return os.environ.get("DATABASE_URL", "").startswith("postgres")


def _ph() -> str:
    """Return the correct parameter placeholder for the active backend."""
    return "%s" if _is_postgres() else "?"


@contextmanager
def get_conn():
    """Yield a DB connection. SQLite for local dev; Postgres in production."""
    if _is_postgres():
        import psycopg2  # type: ignore  # lazy import — not needed for local dev
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()
    else:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()


def init_db():
    """Create tables if they don't exist. Works for both SQLite and Postgres."""
    pg = _is_postgres()

    # AUTOINCREMENT is SQLite-only; Postgres uses SERIAL
    serial = "SERIAL" if pg else "INTEGER"
    autoincrement = "" if pg else " AUTOINCREMENT"

    statements = [
        """CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )""",
        f"""CREATE TABLE IF NOT EXISTS score_history (
            id {serial} PRIMARY KEY{autoincrement},
            report_name TEXT NOT NULL,
            run_date TEXT NOT NULL,
            score REAL NOT NULL,
            details TEXT,
            UNIQUE(report_name, run_date)
        )""",
        f"""CREATE TABLE IF NOT EXISTS rules_of_org (
            id {serial} PRIMARY KEY{autoincrement},
            rule TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            active INTEGER NOT NULL DEFAULT 1
        )""",
        f"""CREATE TABLE IF NOT EXISTS report_writer_questions (
            id {serial} PRIMARY KEY{autoincrement},
            question TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            answered_at TEXT,
            answer TEXT
        )""",
    ]

    ph = _ph()
    defaults = [
        "AMs in active rotation: Eddie McFarlane, Megan Terry, Lisa Rountree.",
        "Patrick Abernathy is Support Manager. He knows accounts but should not manage them. His contacts roll to the company AM.",
        "Lisa LoBello Reynolds is AM for NACS Foundation (separate org in same HubSpot environment).",
        "Grant Bleecher separated from TruAge. His records reassign to Stephanie Sikorski (CEO) for board-relevant accounts.",
        "Bryan Esser separated from TruAge. His records reassign to Patrick Abernathy.",
        "Exception for Swisher: Chris Howard and Josh Harrison contacts stay with Eddie (day-to-day relationship). The Swisher company itself moves to Stephanie.",
    ]

    with get_conn() as conn:
        cur = conn.cursor()
        for stmt in statements:
            cur.execute(stmt)
        cur.execute("SELECT COUNT(*) AS count FROM rules_of_org")
        row = cur.fetchone()
        count = row[0] if isinstance(row, tuple) else row["count"]
        if count == 0:
            for rule in defaults:
                cur.execute(f"INSERT INTO rules_of_org (rule) VALUES ({ph})", (rule,))


# ── Settings ─────────────────────────────────────────────────────────────────

def get_setting(key: str, default=None):
    ph = _ph()
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT value FROM settings WHERE key = {ph}", (key,))
        row = cur.fetchone()
        if row is None:
            return default
        value = row[0] if isinstance(row, tuple) else row["value"]
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value


def set_setting(key: str, value) -> None:
    if not isinstance(value, str):
        value = json.dumps(value)
    ph = _ph()
    with get_conn() as conn:
        cur = conn.cursor()
        if _is_postgres():
            cur.execute(
                f"INSERT INTO settings (key, value) VALUES ({ph}, {ph}) "
                f"ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
                (key, value),
            )
        else:
            cur.execute(
                f"INSERT OR REPLACE INTO settings (key, value) VALUES ({ph}, {ph})",
                (key, value),
            )


# ── Score history ────────────────────────────────────────────────────────────

def record_score(report_name: str, score: float, details: dict | None = None) -> None:
    ph = _ph()
    with get_conn() as conn:
        cur = conn.cursor()
        if _is_postgres():
            cur.execute(
                f"INSERT INTO score_history (report_name, run_date, score, details) "
                f"VALUES ({ph}, {ph}, {ph}, {ph}) "
                f"ON CONFLICT (report_name, run_date) DO UPDATE SET score = EXCLUDED.score, details = EXCLUDED.details",
                (report_name, date.today().isoformat(), score, json.dumps(details or {})),
            )
        else:
            cur.execute(
                f"INSERT OR REPLACE INTO score_history (report_name, run_date, score, details) "
                f"VALUES ({ph}, {ph}, {ph}, {ph})",
                (report_name, date.today().isoformat(), score, json.dumps(details or {})),
            )


def get_score_history(report_name: str, limit: int = 30) -> list[dict]:
    ph = _ph()
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            f"SELECT run_date, score, details FROM score_history "
            f"WHERE report_name = {ph} ORDER BY run_date DESC LIMIT {ph}",
            (report_name, limit),
        )
        rows = cur.fetchall()
        return [
            {
                "run_date": r[0] if isinstance(r, tuple) else r["run_date"],
                "score":    r[1] if isinstance(r, tuple) else r["score"],
                "details":  json.loads(r[2] if isinstance(r, tuple) else r["details"] or "{}"),
            }
            for r in rows
        ]


# ── Rules of org ─────────────────────────────────────────────────────────────

def list_rules() -> list[dict]:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, rule, created_at FROM rules_of_org WHERE active = 1 ORDER BY id"
        )
        return [
            {
                "id":         r[0] if isinstance(r, tuple) else r["id"],
                "rule":       r[1] if isinstance(r, tuple) else r["rule"],
                "created_at": r[2] if isinstance(r, tuple) else r["created_at"],
            }
            for r in cur.fetchall()
        ]


def add_rule(rule: str) -> None:
    ph = _ph()
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(f"INSERT INTO rules_of_org (rule) VALUES ({ph})", (rule,))


# ── Report writer questions ──────────────────────────────────────────────────

def list_open_questions() -> list[dict]:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, question, created_at FROM report_writer_questions "
            "WHERE answered_at IS NULL ORDER BY id"
        )
        return [
            {
                "id":         r[0] if isinstance(r, tuple) else r["id"],
                "question":   r[1] if isinstance(r, tuple) else r["question"],
                "created_at": r[2] if isinstance(r, tuple) else r["created_at"],
            }
            for r in cur.fetchall()
        ]


def add_question(question: str) -> None:
    ph = _ph()
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            f"INSERT INTO report_writer_questions (question) VALUES ({ph})", (question,)
        )


# ── CLI ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--init", action="store_true", help="Create tables")
    args = parser.parse_args()
    if args.init:
        init_db()
        backend = "Postgres" if _is_postgres() else f"SQLite ({DB_PATH})"
        print(f"Initialized {backend}")
