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

        self._reset_if_legacy_schema()
        with self.transaction() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'draft',
                    scenario_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                    deleted_at TEXT
                );

                CREATE TABLE IF NOT EXISTS simulations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL,
                    name TEXT NOT NULL DEFAULT '主仿真',
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS simulation_rounds (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL,
                    simulation_id INTEGER NOT NULL,
                    round_index INTEGER NOT NULL,
                    simulated_hour INTEGER NOT NULL,
                    inventory_level REAL NOT NULL DEFAULT 0,
                    cost_index REAL NOT NULL DEFAULT 0,
                    delivery_delay REAL NOT NULL DEFAULT 0,
                    service_level REAL NOT NULL DEFAULT 0,
                    profit_margin REAL NOT NULL DEFAULT 0,
                    resilience_score REAL NOT NULL DEFAULT 0,
                    state_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    UNIQUE(simulation_id, round_index),
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                    FOREIGN KEY (simulation_id) REFERENCES simulations(id) ON DELETE CASCADE
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

                CREATE TABLE IF NOT EXISTS checkpoints (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL,
                    simulation_id INTEGER NOT NULL,
                    last_round INTEGER NOT NULL,
                    engine_state_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                    FOREIGN KEY (simulation_id) REFERENCES simulations(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    markdown TEXT NOT NULL,
                    summary_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS knowledge_chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL,
                    source TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_simulations_project_id
                    ON simulations(project_id);
                CREATE INDEX IF NOT EXISTS idx_rounds_simulation_id
                    ON simulation_rounds(simulation_id, round_index);
                CREATE INDEX IF NOT EXISTS idx_messages_round_id
                    ON agent_messages(round_id);
                CREATE INDEX IF NOT EXISTS idx_reports_project_id
                    ON reports(project_id);
                CREATE INDEX IF NOT EXISTS idx_knowledge_project_id
                    ON knowledge_chunks(project_id);
                """
            )

    def _reset_if_legacy_schema(self) -> None:
        """检测旧版本 schema 的库文件：备份后重建（内部测试阶段，不做表级迁移）。

        判定特征：projects 含 strategies_json 列、simulation_rounds 含
        strategy_id 列、或 reports 含 html 列（均为 v0.1 schema 痕迹）。
        """
        try:
            proj_cols = {r[1] for r in self.conn.execute("PRAGMA table_info(projects)")}
            round_cols = {r[1] for r in self.conn.execute("PRAGMA table_info(simulation_rounds)")}
            report_cols = {r[1] for r in self.conn.execute("PRAGMA table_info(reports)")}
        except Exception:
            return
        legacy = (
            "strategies_json" in proj_cols
            or "strategy_id" in round_cols
            or "html" in report_cols
        )
        if not legacy:
            return
        self.close()
        backup = self.db_path.with_name(self.db_path.name + ".legacy.bak")
        for suffix in ("", "-shm", "-wal"):
            src = Path(str(self.db_path) + suffix)
            if src.exists():
                src.replace(Path(str(backup) + suffix))
        print(f"[Prism] 检测到旧版本数据库，已备份为 {backup.name} 并重建")

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
