"""
Storage abstraction. SQLite locally, Postgres in production.

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


@contextmanager
def get_conn():
    """Yield a DB connection. SQLite for now; swap on DATABASE_URL later."""
    db_url = os.environ.get("DATABASE_URL", "")
    if db_url.startswith("postgres"):
        # Lazy import so SQLite-only dev doesn't need psycopg2
        import psycopg2  # type: ignore
        conn = psycopg2.connect(db_url)
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
    with get_conn() as conn:
        cur = conn.cursor()
        cur.executescript("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS score_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_name TEXT NOT NULL,
            run_date TEXT NOT NULL,
            score REAL NOT NULL,
            details TEXT,
            UNIQUE(report_name, run_date)
        );

        CREATE TABLE IF NOT EXISTS rules_of_org (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rule TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            active INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS report_writer_questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            answered_at TEXT,
            answer TEXT
        );
        """)

        # Seed default rules — these are the decisions captured in our conversation
        defaults = [
            "AMs in active rotation: Eddie McFarlane, Megan Terry, Lisa Rountree.",
            "Patrick Abernathy is Support Manager. He knows accounts but should not manage them. His contacts roll to the company AM.",
            "Lisa LoBello Reynolds is AM for NACS Foundation (separate org in same HubSpot environment).",
            "Grant Bleecher separated from TruAge. His records reassign to Stephanie Sikorski (CEO) for board-relevant accounts.",
            "Bryan Esser separated from TruAge. His records reassign to Patrick Abernathy.",
            "Exception for Swisher: Chris Howard and Josh Harrison contacts stay with Eddie (day-to-day relationship). The Swisher company itself moves to Stephanie.",
        ]
        cur.execute("SELECT COUNT(*) FROM rules_of_org")
        if cur.fetchone()[0] == 0:
            for rule in defaults:
                cur.execute("INSERT INTO rules_of_org (rule) VALUES (?)", (rule,))


# ── Settings ─────────────────────────────────────────────────────────────────
def get_setting(key: str, default=None):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT value FROM settings WHERE key = ?", (key,))
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
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, value),
        )


# ── Score history ────────────────────────────────────────────────────────────
def record_score(report_name: str, score: float, details: dict | None = None) -> None:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT OR REPLACE INTO score_history (report_name, run_date, score, details) "
            "VALUES (?, ?, ?, ?)",
            (report_name, date.today().isoformat(), score, json.dumps(details or {})),
        )


def get_score_history(report_name: str, limit: int = 30) -> list[dict]:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT run_date, score, details FROM score_history "
            "WHERE report_name = ? ORDER BY run_date DESC LIMIT ?",
            (report_name, limit),
        )
        rows = cur.fetchall()
        return [
            {
                "run_date": r[0] if isinstance(r, tuple) else r["run_date"],
                "score": r[1] if isinstance(r, tuple) else r["score"],
                "details": json.loads(r[2] if isinstance(r, tuple) else r["details"] or "{}"),
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
                "id": r[0] if isinstance(r, tuple) else r["id"],
                "rule": r[1] if isinstance(r, tuple) else r["rule"],
                "created_at": r[2] if isinstance(r, tuple) else r["created_at"],
            }
            for r in cur.fetchall()
        ]


def add_rule(rule: str) -> None:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO rules_of_org (rule) VALUES (?)", (rule,))


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
                "id": r[0] if isinstance(r, tuple) else r["id"],
                "question": r[1] if isinstance(r, tuple) else r["question"],
                "created_at": r[2] if isinstance(r, tuple) else r["created_at"],
            }
            for r in cur.fetchall()
        ]


def add_question(question: str) -> None:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO report_writer_questions (question) VALUES (?)", (question,)
        )


# ── CLI ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--init", action="store_true", help="Create tables")
    args = parser.parse_args()
    if args.init:
        init_db()
        print(f"Initialized {DB_PATH}")
