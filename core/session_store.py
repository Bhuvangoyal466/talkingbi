"""
SessionStore — per-session SQLite database.

Each session gets its own file at:
    data/sessions/<session_id>.db

Tables:
    messages   — chat Q&A turns
    insights   — discovered insights
    charts     — chart metadata + data
    uploads    — files loaded in this session
"""

import json
import sqlite3
import time
from pathlib import Path
from core.logger import logger


class SessionStore:
    """Lightweight SQLite store for a single session's history."""

    def __init__(self, session_id: str, base_dir: str = "data/sessions"):
        self.session_id = session_id
        self.db_path = Path(base_dir) / f"{session_id}.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._base_dir = base_dir
        # Lazy-connect: only open/create the file when we actually need to write
        self._conn = None

    def _get_conn(self):
        """Open (and create) the DB file on first access."""
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._create_tables()
        return self._conn

    # ── Schema ────────────────────────────────────────────────────────────────

    def _create_tables(self):
        self._conn.executescript("""
        CREATE TABLE IF NOT EXISTS messages (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            ts        REAL    NOT NULL,
            role      TEXT    NOT NULL,          -- 'user' | 'assistant'
            content   TEXT    NOT NULL,
            intent    TEXT,                      -- sql_query | chart | insight | …
            sql       TEXT,                      -- generated SQL if any
            rows_ret  INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_messages_ts ON messages(ts);

        CREATE TABLE IF NOT EXISTS insights (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            ts        REAL    NOT NULL,
            goal      TEXT,
            question  TEXT    NOT NULL,
            answer    TEXT,
            evidence  TEXT,
            insight   TEXT,
            type      TEXT,
            confidence REAL,
            summary   TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_insights_ts ON insights(ts);

        CREATE TABLE IF NOT EXISTS charts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          REAL    NOT NULL,
            title       TEXT,
            chart_type  TEXT,
            query       TEXT,
            data_points INTEGER,
            chart_data  TEXT,                    -- JSON
            code        TEXT,
            justification TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_charts_ts ON charts(ts);

        CREATE TABLE IF NOT EXISTS uploads (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          REAL    NOT NULL,
            original_name TEXT  NOT NULL,
            db_path     TEXT    NOT NULL,
            rows        INTEGER,
            columns     TEXT                     -- JSON list
        );
        """)
        self._conn.commit()

    # ── Messages ──────────────────────────────────────────────────────────────

    def add_message(self, role: str, content: str,
                    intent: str = None, sql: str = None, rows_ret: int = None):
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO messages(ts, role, content, intent, sql, rows_ret) VALUES (?,?,?,?,?,?)",
            (time.time(), role, content[:4000], intent, sql, rows_ret),
        )
        conn.commit()

    def get_messages(self, limit: int = 200) -> list:
        if self._conn is None and not self.db_path.exists():
            return []
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM messages ORDER BY ts DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in reversed(rows)]

    # ── Insights ─────────────────────────────────────────────────────────────

    def add_insight_run(self, goal: str, insights: list, summary: str):
        conn = self._get_conn()
        now = time.time()
        for ins in insights:
            conn.execute(
                """INSERT INTO insights(ts,goal,question,answer,evidence,insight,type,confidence,summary)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    now,
                    goal,
                    ins.get("question", ""),
                    ins.get("answer", ""),
                    ins.get("evidence", ""),
                    ins.get("insight", ""),
                    ins.get("type", ""),
                    ins.get("confidence"),
                    summary,
                ),
            )
        conn.commit()

    def get_insights(self, limit: int = 100) -> list:
        if self._conn is None and not self.db_path.exists():
            return []
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM insights ORDER BY ts DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Charts ───────────────────────────────────────────────────────────────

    def add_chart(self, query: str, result: dict):
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO charts(ts,title,chart_type,query,data_points,chart_data,code,justification)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                time.time(),
                result.get("title", ""),
                result.get("chart_type", ""),
                query,
                result.get("data_points", 0),
                json.dumps(result.get("chart_data", {})),
                result.get("code", ""),
                result.get("justification", ""),
            ),
        )
        conn.commit()

    def get_charts(self, limit: int = 50) -> list:
        if self._conn is None and not self.db_path.exists():
            return []
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT id,ts,title,chart_type,query,data_points,chart_data,justification FROM charts ORDER BY ts DESC LIMIT ?",
            (limit,),
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            if d.get("chart_data"):
                try:
                    d["chart_data"] = json.loads(d["chart_data"])
                except Exception:
                    d["chart_data"] = None
            result.append(d)
        return result

    # ── Uploads ──────────────────────────────────────────────────────────────

    def add_upload(self, original_name: str, db_path: str, rows: int, columns: list):
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO uploads(ts,original_name,db_path,rows,columns) VALUES (?,?,?,?,?)",
            (time.time(), original_name, db_path, rows, json.dumps(columns)),
        )
        conn.commit()

    def get_uploads(self) -> list:
        if self._conn is None and not self.db_path.exists():
            return []
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM uploads ORDER BY ts DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Summary ──────────────────────────────────────────────────────────────

    def summary(self) -> dict:
        if self._conn is None and not self.db_path.exists():
            return {"session_id": self.session_id, "db_path": str(self.db_path),
                    "messages": 0, "insights": 0, "charts": 0, "uploads": 0}
        conn = self._get_conn()
        def _count(table):
            return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        return {
            "session_id": self.session_id,
            "db_path": str(self.db_path),
            "messages": _count("messages"),
            "insights": _count("insights"),
            "charts": _count("charts"),
            "uploads": _count("uploads"),
        }

    def close(self):
        try:
            if self._conn is not None:
                self._conn.close()
                self._conn = None
        except Exception:
            pass
