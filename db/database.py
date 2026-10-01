"""SQLite 连接与迁移管理。"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from config import DB_PATH

# Schema 声明：迁移的唯一事实来源，任意旧库启动时向此收敛。
# 规则：缺表建表、缺列补列、声明外的表/列剔除、结构不符带数据重建。
# 列改名与语义变更不在自动收敛范围（会误判成删旧增新丢数据），须显式迁移。
_SCHEMA: dict[str, dict[str, Any]] = {
    "projects": {
        "columns": {
            "id": "INTEGER PRIMARY KEY AUTOINCREMENT",
            "name": "TEXT NOT NULL",
            "status": "TEXT NOT NULL DEFAULT 'draft'",
            "scenario_json": "TEXT NOT NULL DEFAULT '{}'",
            "created_at": "TEXT NOT NULL DEFAULT (datetime('now'))",
            "updated_at": "TEXT NOT NULL DEFAULT (datetime('now'))",
            "deleted_at": "TEXT",
        },
    },
    "simulations": {
        "columns": {
            "id": "INTEGER PRIMARY KEY AUTOINCREMENT",
            "project_id": "INTEGER NOT NULL",
            "name": "TEXT NOT NULL DEFAULT '主仿真'",
            "scenario_json": "TEXT NOT NULL DEFAULT '{}'",
            "created_at": "TEXT NOT NULL DEFAULT (datetime('now'))",
        },
        "foreign_keys": [("project_id", "projects", "id", "CASCADE")],
    },
    "simulation_rounds": {
        "columns": {
            "id": "INTEGER PRIMARY KEY AUTOINCREMENT",
            "project_id": "INTEGER NOT NULL",
            "simulation_id": "INTEGER NOT NULL",
            "round_index": "INTEGER NOT NULL",
            "simulated_hour": "INTEGER NOT NULL",
            "inventory_level": "REAL NOT NULL DEFAULT 0",
            "cost_index": "REAL NOT NULL DEFAULT 0",
            "delivery_delay": "REAL NOT NULL DEFAULT 0",
            "service_level": "REAL NOT NULL DEFAULT 0",
            "profit_margin": "REAL NOT NULL DEFAULT 0",
            "resilience_score": "REAL NOT NULL DEFAULT 0",
            "state_json": "TEXT NOT NULL DEFAULT '{}'",
            "created_at": "TEXT NOT NULL DEFAULT (datetime('now'))",
        },
        "unique": [("simulation_id", "round_index")],
        "foreign_keys": [
            ("project_id", "projects", "id", "CASCADE"),
            ("simulation_id", "simulations", "id", "CASCADE"),
        ],
    },
    "checkpoints": {
        "columns": {
            "id": "INTEGER PRIMARY KEY AUTOINCREMENT",
            "project_id": "INTEGER NOT NULL",
            "simulation_id": "INTEGER NOT NULL",
            "last_round": "INTEGER NOT NULL",
            "engine_state_json": "TEXT NOT NULL",
            "created_at": "TEXT NOT NULL DEFAULT (datetime('now'))",
        },
        "foreign_keys": [
            ("project_id", "projects", "id", "CASCADE"),
            ("simulation_id", "simulations", "id", "CASCADE"),
        ],
    },
    "reports": {
        "columns": {
            "id": "INTEGER PRIMARY KEY AUTOINCREMENT",
            "project_id": "INTEGER NOT NULL",
            "title": "TEXT NOT NULL",
            "markdown": "TEXT NOT NULL",
            "summary_json": "TEXT NOT NULL DEFAULT '{}'",
            "created_at": "TEXT NOT NULL DEFAULT (datetime('now'))",
        },
        "foreign_keys": [("project_id", "projects", "id", "CASCADE")],
    },
    "knowledge_chunks": {
        "columns": {
            "id": "INTEGER PRIMARY KEY AUTOINCREMENT",
            "project_id": "INTEGER NOT NULL",
            "source": "TEXT NOT NULL",
            "chunk_index": "INTEGER NOT NULL",
            "content": "TEXT NOT NULL",
            "created_at": "TEXT NOT NULL DEFAULT (datetime('now'))",
        },
        "foreign_keys": [("project_id", "projects", "id", "CASCADE")],
    },
}

_INDEXES: dict[str, str] = {
    "idx_simulations_project_id": "simulations(project_id)",
    "idx_rounds_simulation_id": "simulation_rounds(simulation_id, round_index)",
    "idx_checkpoints_project_id": "checkpoints(project_id)",
    "idx_reports_project_id": "reports(project_id)",
    "idx_knowledge_project_id": "knowledge_chunks(project_id)",
}


def _create_table_sql(table: str, spec: dict[str, Any]) -> str:
    parts = [f'"{name}" {definition}' for name, definition in spec["columns"].items()]
    parts.extend(f"UNIQUE({', '.join(cols)})" for cols in spec.get("unique", ()))
    parts.extend(
        f"FOREIGN KEY ({src}) REFERENCES {ref}({ref_col}) ON DELETE {on_delete}"
        for src, ref, ref_col, on_delete in spec.get("foreign_keys", ())
    )
    return f'CREATE TABLE "{table}" ({", ".join(parts)})'


def _normalize_default(text: str | None) -> str | None:
    """默认值比较口径：PRAGMA 会剥掉定义文本的最外层括号，两边统一剥一层。"""
    if text is None:
        return None
    text = text.strip()
    if text.startswith("(") and text.endswith(")"):
        return text[1:-1].strip()
    return text


def _expected_shape(definition: str) -> tuple[str, int, str | None, int]:
    """从列定义文本解析 PRAGMA table_info 可比的四元组（类型/非空/默认值/主键）。"""
    upper = definition.upper()
    default = None
    marker = upper.find("DEFAULT")
    if marker != -1:
        default = _normalize_default(definition[marker + len("DEFAULT"):])
    return (
        definition.split()[0].upper(),
        int("NOT NULL" in upper),
        default,
        int("PRIMARY KEY" in upper),
    )


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
        """把数据库收敛到 _SCHEMA 声明的结构，全部操作幂等，重跑无副作用。"""
        for table, spec in _SCHEMA.items():
            self._converge_table(table, spec)
        self._drop_undeclared_tables()
        self._converge_indexes()
        self.conn.commit()

    def _converge_table(self, table: str, spec: dict[str, Any]) -> None:
        if not self._table_exists(table):
            self.conn.execute(_create_table_sql(table, spec))
            return
        actual = {
            str(row["name"]) for row in self.conn.execute(f'PRAGMA table_info("{table}")')
        }
        try:
            for name in actual - set(spec["columns"]):
                self.conn.execute(f'ALTER TABLE "{table}" DROP COLUMN "{name}"')
            for name, definition in spec["columns"].items():
                if name not in actual:
                    self.conn.execute(f'ALTER TABLE "{table}" ADD COLUMN "{name}" {definition}')
        except sqlite3.OperationalError:
            # 增删列触及 SQLite ALTER 限制（如补非常量默认值的列）时走整表重建
            self._rebuild_table(table, spec)
            return
        if self._structure_drifted(table, spec):
            self._rebuild_table(table, spec)

    def _table_exists(self, table: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table,),
        ).fetchone()
        return row is not None

    def _structure_drifted(self, table: str, spec: dict[str, Any]) -> bool:
        actual = {
            str(row["name"]): row for row in self.conn.execute(f'PRAGMA table_info("{table}")')
        }
        for name, definition in spec["columns"].items():
            row = actual.get(name)
            if row is None:
                return True
            col_type, notnull, default, pk = _expected_shape(definition)
            if str(row["type"]).upper() != col_type:
                return True
            if int(row["notnull"]) != notnull or int(row["pk"]) != pk:
                return True
            actual_default = row["dflt_value"]
            if _normalize_default(actual_default) != default:
                return True
        actual_fks = {
            (str(r["from"]), str(r["table"]), str(r["to"]), str(r["on_delete"]))
            for r in self.conn.execute(f'PRAGMA foreign_key_list("{table}")')
        }
        if actual_fks != set(spec.get("foreign_keys", ())):
            return True
        actual_uniques = set()
        for idx in self.conn.execute(f'PRAGMA index_list("{table}")'):
            if idx["origin"] == "u":
                actual_uniques.add(
                    tuple(
                        str(r["name"])
                        for r in self.conn.execute(f'PRAGMA index_info("{idx["name"]}")')
                    )
                )
        return actual_uniques != {tuple(u) for u in spec.get("unique", ())}

    def _rebuild_table(self, table: str, spec: dict[str, Any]) -> None:
        """结构不符时带数据重建：新表承接共有列数据，旧表剔除后归位。"""
        actual = {
            str(row["name"]) for row in self.conn.execute(f'PRAGMA table_info("{table}")')
        }
        common = [name for name in spec["columns"] if name in actual]
        cols = ", ".join(f'"{name}"' for name in common)
        staging = f"{table}__rebuild"
        # 外键开关在事务内不可变，须在 BEGIN 前关闭，结束后恢复
        self.conn.execute("PRAGMA foreign_keys=OFF")
        self.conn.execute("BEGIN")
        try:
            self.conn.execute(_create_table_sql(staging, spec))
            if common:
                self.conn.execute(
                    f'INSERT INTO "{staging}" ({cols}) SELECT {cols} FROM "{table}"'
                )
            self.conn.execute(f'DROP TABLE "{table}"')
            self.conn.execute(f'ALTER TABLE "{staging}" RENAME TO "{table}"')
            self.conn.execute("COMMIT")
        except Exception:
            self.conn.execute("ROLLBACK")
            raise
        finally:
            self.conn.execute("PRAGMA foreign_keys=ON")

    def _drop_undeclared_tables(self) -> None:
        rows = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
        for row in rows:
            name = str(row["name"])
            if name.startswith("sqlite_") or name in _SCHEMA:
                continue
            self.conn.execute(f'DROP TABLE "{name}"')

    def _converge_indexes(self) -> None:
        rows = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index'"
        ).fetchall()
        for row in rows:
            name = str(row["name"])
            if name.startswith("sqlite_") or name in _INDEXES:
                continue
            self.conn.execute(f'DROP INDEX "{name}"')
        for name, target in _INDEXES.items():
            self.conn.execute(f'CREATE INDEX IF NOT EXISTS "{name}" ON {target}')

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
