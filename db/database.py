"""SQLite 连接与迁移管理。"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from config import DB_PATH


class Database:
    """SQLite 数据库管理器。

    实例语义按参数分裂：不传 db_path 返回应用默认库的全局单例；
    传入 db_path（测试或脚本场景，避免污染本地数据）则每次构造独立新实例。
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
        conn = sqlite3.connect(str(self.db_path), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        # 仿真 worker 线程与 UI 主线程双连接并发写，默认 5s 在高负载下可能 SQLITE_BUSY
        conn.execute("PRAGMA busy_timeout=30000")
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
        # executescript 会先隐式提交再自建事务，DDL 不在 transaction() 的保护内、
        # 无法回滚；全部语句均为幂等的 IF NOT EXISTS，中途失败重跑即可收敛
        self.conn.executescript(
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
                    scenario_json TEXT NOT NULL DEFAULT '{}',
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
                CREATE INDEX IF NOT EXISTS idx_checkpoints_project_id
                    ON checkpoints(project_id);
                CREATE INDEX IF NOT EXISTS idx_reports_project_id
                    ON reports(project_id);
                CREATE INDEX IF NOT EXISTS idx_knowledge_project_id
                    ON knowledge_chunks(project_id);
            """
        )
        # 老库兼容：缺列补列、废表清除，均为幂等操作
        self._ensure_column(
            "projects",
            "deleted_at",
            "ALTER TABLE projects ADD COLUMN deleted_at TEXT",
        )
        self._ensure_column(
            "simulations",
            "scenario_json",
            "ALTER TABLE simulations ADD COLUMN scenario_json TEXT NOT NULL DEFAULT '{}'",
        )
        self.conn.execute("DROP TABLE IF EXISTS agent_messages")
        self.conn.commit()

    def _ensure_column(self, table: str, column: str, ddl: str) -> None:
        """目标列不存在时执行补列 DDL，存在则跳过。"""
        columns = {
            str(row["name"]) for row in self.conn.execute(f"PRAGMA table_info({table})")
        }
        if column not in columns:
            self.conn.execute(ddl)

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
