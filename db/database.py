"""SQLite 连接与迁移管理。"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from config import DB_PATH


class Database:
    """SQLite 数据库管理器。

    默认连接应用数据库；测试或脚本可传入独立 db_path，避免污染本地数据。
    """

    _default_instance: Database | None = None

    def __new__(cls, db_path: str | Path | None = None) -> Database:
        if db_path is not None:
            instance = super().__new__(cls)
            instance._initialized = False
            return instance
        if cls._default_instance is None:
            cls._default_instance = super().__new__(cls)
            cls._default_instance._initialized = False
        return cls._default_instance

    def __init__(self, db_path: str | Path | None = None):
        if self._initialized:
            return
        self._initialized = True
        self.db_path = Path(db_path) if db_path is not None else DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = self._connect()
        return self._conn

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        try:
            yield self.conn
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def migrate(self) -> None:
        """执行当前版本所需的完整 Schema 迁移。"""

        with self.transaction() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'draft',
                    scenario_json TEXT NOT NULL DEFAULT '{}',
                    strategies_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                    deleted_at TEXT
                );

                CREATE TABLE IF NOT EXISTS strategies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    statement TEXT NOT NULL,
                    release_hour INTEGER NOT NULL DEFAULT 0,
                    meta_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS simulation_rounds (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL,
                    strategy_id INTEGER NOT NULL,
                    round_index INTEGER NOT NULL,
                    simulated_hour INTEGER NOT NULL,
                    heat REAL NOT NULL,
                    sentiment REAL NOT NULL,
                    support_rate REAL NOT NULL,
                    state_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    UNIQUE(strategy_id, round_index),
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                    FOREIGN KEY (strategy_id) REFERENCES strategies(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS agent_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    round_id INTEGER NOT NULL,
                    agent_name TEXT NOT NULL,
                    stance TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metrics_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    FOREIGN KEY (round_id) REFERENCES simulation_rounds(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS simulations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL,
                    strategy_index INTEGER NOT NULL,
                    round INTEGER NOT NULL,
                    state_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS checkpoints (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL,
                    strategy_index INTEGER NOT NULL,
                    last_round INTEGER NOT NULL,
                    engine_state_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    markdown TEXT NOT NULL,
                    html TEXT NOT NULL,
                    summary_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_strategies_project_id
                    ON strategies(project_id);
                CREATE INDEX IF NOT EXISTS idx_rounds_strategy_id
                    ON simulation_rounds(strategy_id, round_index);
                CREATE INDEX IF NOT EXISTS idx_messages_round_id
                    ON agent_messages(round_id);
                CREATE INDEX IF NOT EXISTS idx_reports_project_id
                    ON reports(project_id);
                """
            )

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
