"""SQLite 数据访问模型。

保持轻量 dataclass + Repository 风格，避免在桌面端引入完整 ORM。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Optional

from db.database import Database


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
    actor: str = ""                      # 涉及行为体
    decision: str = ""                   # 决策内容
    release_cycle: str = ""              # 生效周期（如 "1-4"）
    parameters_json: str = "{}"          # 决策参数 JSON
    created_at: str = ""
    updated_at: str = ""

    @property
    def parameters(self) -> dict[str, Any]:
        return from_json(self.parameters_json, {})


@dataclass(frozen=True)
class SimulationRound:
    id: int
    project_id: int
    strategy_id: int
    round_index: int
    simulated_hour: int
    inventory_level: float = 0.0         # 全链库存水平 0~100
    cost_index: float = 0.0              # 成本指数 0~100
    delivery_delay: float = 0.0          # 平均交付延迟（周期数）
    service_level: float = 0.0           # 订单满足率 0~1
    profit_margin: float = 0.0           # 全链利润率 -1~1
    resilience_score: float = 0.0        # 韧性评分 0~100
    state_json: str = "{}"
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


@dataclass(frozen=True)
class Checkpoint:
    id: int
    project_id: int
    strategy_id: int
    last_round: int
    engine_state_json: str
    created_at: str = ""

    @property
    def engine_state(self) -> dict[str, Any]:
        return from_json(self.engine_state_json, {})


@dataclass(frozen=True)
class KnowledgeChunk:
    id: int
    project_id: int
    source: str
    chunk_index: int
    content: str
    created_at: str = ""


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

    def update_scenario(
        self,
        project_id: int,
        scenario: dict[str, Any],
        name: str | None = None,
        status: str | None = None,
    ) -> Project:
        assignments = ["scenario_json = ?", "updated_at = datetime('now')"]
        values: list[Any] = [to_json(scenario)]
        if name is not None:
            assignments.append("name = ?")
            values.append(name)
        if status is not None:
            assignments.append("status = ?")
            values.append(status)
        values.append(project_id)
        with self.db.transaction() as conn:
            conn.execute(
                f"UPDATE projects SET {', '.join(assignments)} WHERE id = ?",
                values,
            )
        project = self.get_by_id(project_id)
        if project is None:
            raise KeyError(f"项目不存在: {project_id}")
        return project


class StrategyRepository:
    """策略数据访问。"""

    def __init__(self, db: Database | None = None):
        self.db = db or Database()

    def create(
        self,
        project_id: int,
        name: str,
        actor: str = "",
        decision: str = "",
        release_cycle: str = "",
        parameters: dict[str, Any] | None = None,
    ) -> Strategy:
        with self.db.transaction() as conn:
            cursor = conn.execute(
                """
                INSERT INTO strategies
                    (project_id, name, actor, decision, release_cycle, parameters_json, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
                """,
                (project_id, name, actor, decision, release_cycle, to_json(parameters or {})),
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

    def replace_for_project(self, project_id: int, strategies: list[dict[str, Any]]) -> list[Strategy]:
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM strategies WHERE project_id = ?", (project_id,))
            ids: list[int] = []
            for strategy in strategies:
                cursor = conn.execute(
                    """
                    INSERT INTO strategies
                        (project_id, name, actor, decision, release_cycle, parameters_json, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
                    """,
                    (
                        project_id,
                        str(strategy.get("name", "")).strip() or "未命名方案",
                        str(strategy.get("actor", "")).strip(),
                        str(strategy.get("decision", "")).strip(),
                        str(strategy.get("release_cycle", "")),
                        to_json(strategy.get("parameters", {})),
                    ),
                )
                ids.append(int(cursor.lastrowid))
        return [self.get_by_id(strategy_id) for strategy_id in ids]


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
        inventory_level: float,
        cost_index: float,
        delivery_delay: float,
        service_level: float = 0.0,
        profit_margin: float = 0.0,
        resilience_score: float = 0.0,
        state: dict[str, Any],
        agent_messages: list[dict[str, Any]] | None = None,
    ) -> SimulationRound:
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO simulation_rounds
                    (project_id, strategy_id, round_index, simulated_hour, inventory_level,
                     cost_index, delivery_delay, service_level, profit_margin, resilience_score, state_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(strategy_id, round_index) DO UPDATE SET
                    simulated_hour = excluded.simulated_hour,
                    inventory_level = excluded.inventory_level,
                    cost_index = excluded.cost_index,
                    delivery_delay = excluded.delivery_delay,
                    service_level = excluded.service_level,
                    profit_margin = excluded.profit_margin,
                    resilience_score = excluded.resilience_score,
                    state_json = excluded.state_json
                """,
                (
                    project_id,
                    strategy_id,
                    round_index,
                    simulated_hour,
                    inventory_level,
                    cost_index,
                    delivery_delay,
                    service_level,
                    profit_margin,
                    resilience_score,
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


class CheckpointRepository:
    """仿真检查点持久化。"""

    def __init__(self, db: Database | None = None):
        self.db = db or Database()

    def save(
        self,
        *,
        project_id: int,
        strategy_id: int,
        last_round: int,
        engine_state: dict[str, Any],
    ) -> int:
        with self.db.transaction() as conn:
            conn.execute(
                """
                DELETE FROM checkpoints
                WHERE project_id = ? AND strategy_id = ?
                """,
                (project_id, strategy_id),
            )
            cursor = conn.execute(
                """
                INSERT INTO checkpoints
                    (project_id, strategy_id, last_round, engine_state_json)
                VALUES (?, ?, ?, ?)
                """,
                (project_id, strategy_id, last_round, to_json(engine_state)),
            )
        return int(cursor.lastrowid)

    def get_by_id(self, checkpoint_id: int) -> Checkpoint | None:
        row = self.db.conn.execute(
            "SELECT * FROM checkpoints WHERE id = ?",
            (checkpoint_id,),
        ).fetchone()
        return Checkpoint(**dict(row)) if row else None

    def latest_for_project(self, project_id: int) -> Checkpoint | None:
        row = self.db.conn.execute(
            """
            SELECT * FROM checkpoints
            WHERE project_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (project_id,),
        ).fetchone()
        return Checkpoint(**dict(row)) if row else None

    def list_unfinished(self, limit: int = 10) -> list[Checkpoint]:
        rows = self.db.conn.execute(
            """
            SELECT * FROM checkpoints
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [Checkpoint(**dict(row)) for row in rows]

    def delete_for_project(self, project_id: int) -> None:
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM checkpoints WHERE project_id = ?", (project_id,))


class KnowledgeRepository:
    """项目 RAG 知识片段检索。"""

    def __init__(self, db: Database | None = None):
        self.db = db or Database()

    def replace_for_project(self, project_id: int, chunks: list[dict[str, Any]]) -> list[KnowledgeChunk]:
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM knowledge_chunks WHERE project_id = ?", (project_id,))
            ids: list[int] = []
            for index, chunk in enumerate(chunks):
                content = str(chunk.get("content", "")).strip()
                if not content:
                    continue
                cursor = conn.execute(
                    """
                    INSERT INTO knowledge_chunks
                        (project_id, source, chunk_index, content)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        project_id,
                        str(chunk.get("source", "背景资料")),
                        int(chunk.get("chunk_index", index)),
                        content,
                    ),
                )
                ids.append(int(cursor.lastrowid))
        return [self.get_by_id(chunk_id) for chunk_id in ids]

    def get_by_id(self, chunk_id: int) -> KnowledgeChunk:
        row = self.db.conn.execute(
            "SELECT * FROM knowledge_chunks WHERE id = ?",
            (chunk_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"知识片段不存在: {chunk_id}")
        return KnowledgeChunk(**dict(row))

    def list_by_project(self, project_id: int) -> list[KnowledgeChunk]:
        rows = self.db.conn.execute(
            """
            SELECT * FROM knowledge_chunks
            WHERE project_id = ?
            ORDER BY source ASC, chunk_index ASC, id ASC
            """,
            (project_id,),
        ).fetchall()
        return [KnowledgeChunk(**dict(row)) for row in rows]

    def search(self, project_id: int, query: str, limit: int = 4) -> list[KnowledgeChunk]:
        chunks = self.list_by_project(project_id)
        terms = _query_terms(query)
        if not terms:
            return chunks[:limit]
        scored: list[tuple[int, KnowledgeChunk]] = []
        for chunk in chunks:
            content = chunk.content.lower()
            source = chunk.source.lower()
            score = sum(content.count(term) * 2 + source.count(term) for term in terms)
            if score > 0:
                scored.append((score, chunk))
        scored.sort(key=lambda item: (item[0], -item[1].chunk_index), reverse=True)
        return [chunk for _, chunk in scored[:limit]]


def _query_terms(query: str) -> list[str]:
    raw_terms = re.findall(r"[A-Za-z0-9_\-\u4e00-\u9fff]{2,}", query.lower())
    seen: set[str] = set()
    terms: list[str] = []
    for term in raw_terms:
        candidates = [term]
        if re.search(r"[\u4e00-\u9fff]", term) and len(term) > 4:
            candidates.extend(term[index : index + 2] for index in range(len(term) - 1))
        for candidate in candidates:
            if candidate not in seen:
                seen.add(candidate)
                terms.append(candidate)
    return terms[:30]
