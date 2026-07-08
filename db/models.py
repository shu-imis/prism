"""数据模型 —— ORM 风格的数据访问

基于 SQLite 的数据持久化。
参考 MiroFish 的 dataclass + to_dict/from_dict 序列化模式。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from prism.db.database import Database


# ============================================================
# Project
# ============================================================

@dataclass
class Project:
    """推演项目 ORM 模型"""
    id: int = 0
    name: str = ""
    status: str = "draft"                 # draft | running | completed
    scenario_json: str = "{}"
    strategies_json: str = "[]"
    created_at: str = ""
    updated_at: str = ""
    deleted_at: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class ProjectRepository:
    """项目数据访问"""

    def __init__(self):
        self.db = Database()

    def create(self, name: str) -> Project:
        cursor = self.db.conn.execute(
            "INSERT INTO projects (name) VALUES (?)",
            (name,),
        )
        self.db.conn.commit()
        return self.get_by_id(cursor.lastrowid)

    def get_by_id(self, project_id: int) -> Optional[Project]:
        row = self.db.conn.execute(
            "SELECT * FROM projects WHERE id = ? AND deleted_at IS NULL",
            (project_id,),
        ).fetchone()
        if row:
            return Project(**dict(row))
        return None

    def list_all(self) -> List[Project]:
        rows = self.db.conn.execute(
            "SELECT * FROM projects WHERE deleted_at IS NULL ORDER BY updated_at DESC"
        ).fetchall()
        return [Project(**dict(r)) for r in rows]

    def soft_delete(self, project_id: int):
        self.db.conn.execute(
            "UPDATE projects SET deleted_at = datetime('now') WHERE id = ?",
            (project_id,),
        )
        self.db.conn.commit()

    def update(self, project: Project):
        self.db.conn.execute(
            """UPDATE projects
               SET name=?, status=?, scenario_json=?, strategies_json=?,
                   updated_at=datetime('now')
               WHERE id=?""",
            (project.name, project.status, project.scenario_json,
             project.strategies_json, project.id),
        )
        self.db.conn.commit()
