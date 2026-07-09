"""SQLite 数据访问模型。

保持轻量 dataclass + Repository 风格，避免在桌面端引入完整 ORM。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from db.database import Database


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def to_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


def from_json(text: str | None, default: Any) -> Any:
    if not text:
        return default
    return json.loads(text)


@dataclass
class Project:
    """推演项目。"""

    id: int = 0
    name: str = ""
    status: str = "draft"
    scenario_json: str = "{}"
    strategies_json: str = "[]"
    created_at: str = ""
    updated_at: str = ""
    deleted_at: Optional[str] = None

    @property
    def scenario(self) -> dict[str, Any]:
        return from_json(self.scenario_json, {})

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status,
            "scenario": self.scenario,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class Strategy:
    id: int
    project_id: int
    name: str
    statement: str
    release_hour: int
    meta_json: str = "{}"
    created_at: str = ""
    updated_at: str = ""

    @property
    def meta(self) -> dict[str, Any]:
        return from_json(self.meta_json, {})


@dataclass(frozen=True)
class SimulationRound:
    id: int
    project_id: int
    strategy_id: int
    round_index: int
    simulated_hour: int
    heat: float
    sentiment: float
    support_rate: float
    state_json: str
    created_at: str = ""

    @property
    def state(self) -> dict[str, Any]:
        return from_json(self.state_json, {})


@dataclass(frozen=True)
class ReportRecord:
    id: int
    project_id: int
    title: str
    markdown: str
    html: str
    summary_json: str
    created_at: str

    @property
    def summary(self) -> dict[str, Any]:
        return from_json(self.summary_json, {})


class ProjectRepository:
    """项目数据访问。"""

    def __init__(self, db: Database | None = None):
        self.db = db or Database()

    def create(self, name: str, scenario: dict[str, Any] | None = None) -> Project:
        with self.db.transaction() as conn:
            cursor = conn.execute(
                """
                INSERT INTO projects (name, scenario_json, updated_at)
                VALUES (?, ?, datetime('now'))
                """,
                (name, to_json(scenario or {})),
            )
        project = self.get_by_id(int(cursor.lastrowid))
        if project is None:
            raise RuntimeError("项目创建后无法读取。")
        return project

    def get_by_id(self, project_id: int) -> Optional[Project]:
        row = self.db.conn.execute(
            "SELECT * FROM projects WHERE id = ? AND deleted_at IS NULL",
            (project_id,),
        ).fetchone()
        return Project(**dict(row)) if row else None

    def list_all(self) -> list[Project]:
        rows = self.db.conn.execute(
            """
            SELECT * FROM projects
            WHERE deleted_at IS NULL
            ORDER BY updated_at DESC, id DESC
            """
        ).fetchall()
        return [Project(**dict(row)) for row in rows]

    def soft_delete(self, project_id: int) -> None:
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE projects SET deleted_at = datetime('now') WHERE id = ?",
                (project_id,),
            )

    def update(self, project: Project) -> None:
        with self.db.transaction() as conn:
            conn.execute(
                """
                UPDATE projects
                SET name = ?, status = ?, scenario_json = ?, strategies_json = ?,
                    updated_at = datetime('now')
                WHERE id = ?
                """,
                (
                    project.name,
                    project.status,
                    project.scenario_json,
                    project.strategies_json,
                    project.id,
                ),
            )


class StrategyRepository:
    """策略数据访问。"""

    def __init__(self, db: Database | None = None):
        self.db = db or Database()

    def create(
        self,
        project_id: int,
        name: str,
        statement: str,
        release_hour: int = 0,
        meta: dict[str, Any] | None = None,
    ) -> Strategy:
        with self.db.transaction() as conn:
            cursor = conn.execute(
                """
                INSERT INTO strategies
                    (project_id, name, statement, release_hour, meta_json, updated_at)
                VALUES (?, ?, ?, ?, ?, datetime('now'))
                """,
                (project_id, name, statement, release_hour, to_json(meta or {})),
            )
        return self.get_by_id(int(cursor.lastrowid))

    def get_by_id(self, strategy_id: int) -> Strategy:
        row = self.db.conn.execute(
            "SELECT * FROM strategies WHERE id = ?",
            (strategy_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"策略不存在: {strategy_id}")
        return Strategy(**dict(row))

    def list_by_project(self, project_id: int) -> list[Strategy]:
        rows = self.db.conn.execute(
            "SELECT * FROM strategies WHERE project_id = ? ORDER BY id ASC",
            (project_id,),
        ).fetchall()
        return [Strategy(**dict(row)) for row in rows]


class SimulationRoundRepository:
    """仿真轮次与 Agent 发言持久化。"""

    def __init__(self, db: Database | None = None):
        self.db = db or Database()

    def save(
        self,
        *,
        project_id: int,
        strategy_id: int,
        round_index: int,
        simulated_hour: int,
        heat: float,
        sentiment: float,
        support_rate: float,
        state: dict[str, Any],
        agent_messages: list[dict[str, Any]] | None = None,
    ) -> SimulationRound:
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO simulation_rounds
                    (project_id, strategy_id, round_index, simulated_hour, heat,
                     sentiment, support_rate, state_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(strategy_id, round_index) DO UPDATE SET
                    simulated_hour = excluded.simulated_hour,
                    heat = excluded.heat,
                    sentiment = excluded.sentiment,
                    support_rate = excluded.support_rate,
                    state_json = excluded.state_json
                """,
                (
                    project_id,
                    strategy_id,
                    round_index,
                    simulated_hour,
                    heat,
                    sentiment,
                    support_rate,
                    to_json(state),
                ),
            )
            round_id = self._find_round_id(strategy_id, round_index)
            conn.execute("DELETE FROM agent_messages WHERE round_id = ?", (round_id,))
            for message in agent_messages or []:
                conn.execute(
                    """
                    INSERT INTO agent_messages
                        (round_id, agent_name, stance, content, metrics_json)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        round_id,
                        str(message.get("agent_name", "")),
                        str(message.get("stance", "neutral")),
                        str(message.get("content", "")),
                        to_json(message.get("metrics", {})),
                    ),
                )
        return self.get_by_id(round_id)

    def _find_round_id(self, strategy_id: int, round_index: int) -> int:
        row = self.db.conn.execute(
            """
            SELECT id FROM simulation_rounds
            WHERE strategy_id = ? AND round_index = ?
            """,
            (strategy_id, round_index),
        ).fetchone()
        if row is None:
            raise KeyError("仿真轮次保存失败。")
        return int(row["id"])

    def get_by_id(self, round_id: int) -> SimulationRound:
        row = self.db.conn.execute(
            "SELECT * FROM simulation_rounds WHERE id = ?",
            (round_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"仿真轮次不存在: {round_id}")
        return SimulationRound(**dict(row))

    def list_by_strategy(self, strategy_id: int) -> list[SimulationRound]:
        rows = self.db.conn.execute(
            """
            SELECT * FROM simulation_rounds
            WHERE strategy_id = ?
            ORDER BY round_index ASC
            """,
            (strategy_id,),
        ).fetchall()
        return [SimulationRound(**dict(row)) for row in rows]


class ReportRepository:
    """报告持久化。"""

    def __init__(self, db: Database | None = None):
        self.db = db or Database()

    def save(
        self,
        *,
        project_id: int,
        title: str,
        markdown: str,
        html: str,
        summary: dict[str, Any],
    ) -> int:
        with self.db.transaction() as conn:
            cursor = conn.execute(
                """
                INSERT INTO reports (project_id, title, markdown, html, summary_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (project_id, title, markdown, html, to_json(summary)),
            )
        return int(cursor.lastrowid)

    def list_by_project(self, project_id: int) -> list[ReportRecord]:
        rows = self.db.conn.execute(
            """
            SELECT * FROM reports
            WHERE project_id = ?
            ORDER BY created_at DESC, id DESC
            """,
            (project_id,),
        ).fetchall()
        return [ReportRecord(**dict(row)) for row in rows]
