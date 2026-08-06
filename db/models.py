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


# 单世界仿真在 simulations 表中的持久化锚点名称
MAIN_SIMULATION_NAME = "主仿真"


@dataclass
class Project:
    """推演项目。"""

    id: int = 0
    name: str = ""
    status: str = "draft"
    scenario_json: str = "{}"
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
class Simulation:
    """项目的主仿真锚点记录。"""

    id: int
    project_id: int
    name: str
    created_at: str = ""


@dataclass(frozen=True)
class SimulationRound:
    id: int
    project_id: int
    simulation_id: int
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
    summary_json: str
    created_at: str

    @property
    def summary(self) -> dict[str, Any]:
        return from_json(self.summary_json, {})


@dataclass(frozen=True)
class Checkpoint:
    id: int
    project_id: int
    simulation_id: int
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
            raise RuntimeError("项目创建后无法读取")
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
                SET name = ?, status = ?, scenario_json = ?,
                    updated_at = datetime('now')
                WHERE id = ?
                """,
                (
                    project.name,
                    project.status,
                    project.scenario_json,
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


class SimulationRepository:
    """主仿真锚点记录的数据访问。"""

    def __init__(self, db: Database | None = None):
        self.db = db or Database()

    def create(self, project_id: int, name: str = MAIN_SIMULATION_NAME) -> Simulation:
        with self.db.transaction() as conn:
            cursor = conn.execute(
                "INSERT INTO simulations (project_id, name) VALUES (?, ?)",
                (project_id, name),
            )
        return self.get_by_id(int(cursor.lastrowid))

    def get_by_id(self, simulation_id: int) -> Simulation:
        row = self.db.conn.execute(
            "SELECT * FROM simulations WHERE id = ?",
            (simulation_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"仿真记录不存在: {simulation_id}")
        return Simulation(**dict(row))

    def list_by_project(self, project_id: int) -> list[Simulation]:
        rows = self.db.conn.execute(
            "SELECT * FROM simulations WHERE project_id = ? ORDER BY id ASC",
            (project_id,),
        ).fetchall()
        return [Simulation(**dict(row)) for row in rows]

    def get_or_create_main(self, project_id: int) -> Simulation:
        """返回项目的隐含主仿真记录（simulations 表仅作持久化锚点）。"""
        for simulation in self.list_by_project(project_id):
            if simulation.name == MAIN_SIMULATION_NAME:
                return simulation
        return self.create(project_id, MAIN_SIMULATION_NAME)


class SimulationRoundRepository:
    """仿真轮次与 Agent 发言持久化。"""

    def __init__(self, db: Database | None = None):
        self.db = db or Database()

    def save(
        self,
        *,
        project_id: int,
        simulation_id: int,
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
                    (project_id, simulation_id, round_index, simulated_hour, inventory_level,
                     cost_index, delivery_delay, service_level, profit_margin, resilience_score, state_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(simulation_id, round_index) DO UPDATE SET
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
                    simulation_id,
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
            round_id = self._find_round_id(simulation_id, round_index)
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

    def _find_round_id(self, simulation_id: int, round_index: int) -> int:
        row = self.db.conn.execute(
            """
            SELECT id FROM simulation_rounds
            WHERE simulation_id = ? AND round_index = ?
            """,
            (simulation_id, round_index),
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

    def list_by_simulation(self, simulation_id: int) -> list[SimulationRound]:
        rows = self.db.conn.execute(
            """
            SELECT * FROM simulation_rounds
            WHERE simulation_id = ?
            ORDER BY round_index ASC
            """,
            (simulation_id,),
        ).fetchall()
        return [SimulationRound(**dict(row)) for row in rows]

    def delete_for_simulation(self, simulation_id: int) -> None:
        """删除指定仿真记录的全部轮次与发言数据。"""
        with self.db.transaction() as conn:
            conn.execute(
                "DELETE FROM agent_messages WHERE round_id IN "
                "(SELECT id FROM simulation_rounds WHERE simulation_id = ?)",
                (simulation_id,),
            )
            conn.execute(
                "DELETE FROM simulation_rounds WHERE simulation_id = ?",
                (simulation_id,),
            )


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
        summary: dict[str, Any],
    ) -> int:
        with self.db.transaction() as conn:
            cursor = conn.execute(
                """
                INSERT INTO reports (project_id, title, markdown, summary_json)
                VALUES (?, ?, ?, ?)
                """,
                (project_id, title, markdown, to_json(summary)),
            )
        return int(cursor.lastrowid)

    def save_or_update_latest(
        self,
        *,
        project_id: int,
        title: str,
        markdown: str,
        summary: dict[str, Any],
    ) -> int:
        """每个项目只保留一份主报告：有则更新最新一条，无则插入。

        防止重复仿真 / 反复生成 AI 分析导致 reports 表无限膨胀
        （结果页始终只展示最新一条，旧记录无消费方）。
        """
        existing = self.list_by_project(project_id)
        if not existing:
            return self.save(
                project_id=project_id, title=title, markdown=markdown, summary=summary
            )
        report_id = existing[0].id
        with self.db.transaction() as conn:
            conn.execute(
                """
                UPDATE reports
                SET title = ?, markdown = ?, summary_json = ?
                WHERE id = ?
                """,
                (title, markdown, to_json(summary), report_id),
            )
        return int(report_id)

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

    def delete_for_project(self, project_id: int) -> None:
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM reports WHERE project_id = ?", (project_id,))


class CheckpointRepository:
    """仿真检查点持久化。"""

    def __init__(self, db: Database | None = None):
        self.db = db or Database()

    def save(
        self,
        *,
        project_id: int,
        simulation_id: int,
        last_round: int,
        engine_state: dict[str, Any],
    ) -> int:
        with self.db.transaction() as conn:
            conn.execute(
                """
                DELETE FROM checkpoints
                WHERE project_id = ? AND simulation_id = ?
                """,
                (project_id, simulation_id),
            )
            cursor = conn.execute(
                """
                INSERT INTO checkpoints
                    (project_id, simulation_id, last_round, engine_state_json)
                VALUES (?, ?, ?, ?)
                """,
                (project_id, simulation_id, last_round, to_json(engine_state)),
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


def invalidate_simulation_results(project_id: int) -> None:
    """作废旧仿真结果：场景或行为体配置变更后，历史仿真数据不再有效。

    删除主仿真轮次、检查点与报告，并把项目状态回退为 draft，
    供 Step1/Step2 保存时在 completed/interrupted 项目上调用。
    """
    main = next(
        (s for s in SimulationRepository().list_by_project(project_id)
         if s.name == MAIN_SIMULATION_NAME),
        None,
    )
    if main:
        SimulationRoundRepository().delete_for_simulation(main.id)
    CheckpointRepository().delete_for_project(project_id)
    ReportRepository().delete_for_project(project_id)
    project = ProjectRepository().get_by_id(project_id)
    if project:
        ProjectRepository().update_scenario(
            project_id, dict(project.scenario), status="draft"
        )


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
