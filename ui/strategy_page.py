"""策略配置页。"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from db.models import ProjectRepository, StrategyRepository
from ui.widgets import (
    BodyLabel,
    PrismCard,
    PrismDangerButton,
    PrismLineEdit,
    PrismPrimaryButton,
    PrismSecondaryButton,
    SectionTitle,
)


DEFAULT_STRATEGY_TEXT = [
    {
        "name": "快速道歉与透明整改",
        "statement": "我们诚恳致歉，暂停涉事门店营业，并公开第三方检查和整改进度。",
        "release_hour": 4,
    },
    {
        "name": "先核查再回应",
        "statement": "我们已启动核查，将在事实确认后统一向公众说明情况。",
        "release_hour": 8,
    },
]

MAX_STRATEGY_NAME_CHARS = 40
MAX_STRATEGY_STATEMENT_CHARS = 8000


class StrategyPage(QWidget):
    """回应策略配置。"""

    strategies_saved = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project_id: int | None = None
        self._strategy_rows: list[dict] = []
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        root.addWidget(scroll)

        inner = QWidget()
        scroll.setWidget(inner)
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(48, 40, 48, 40)
        layout.setSpacing(18)

        layout.addWidget(SectionTitle("策略配置"))
        self.project_label = BodyLabel("请先在事件录入页保存项目。")
        layout.addWidget(self.project_label)

        self.strategy_container = QVBoxLayout()
        self.strategy_container.setSpacing(14)
        layout.addLayout(self.strategy_container)

        actions = QHBoxLayout()
        self.add_button = PrismSecondaryButton("添加策略")
        self.add_button.clicked.connect(lambda: self._add_strategy())
        self.save_button = PrismPrimaryButton("保存并开始仿真")
        self.save_button.clicked.connect(self._save_strategies)
        actions.addWidget(self.add_button)
        actions.addStretch()
        actions.addWidget(self.save_button)
        layout.addLayout(actions)
        layout.addStretch()

        for item in DEFAULT_STRATEGY_TEXT:
            self._add_strategy(item)

    def load_project(self, project_id: int) -> None:
        project = ProjectRepository().get_by_id(project_id)
        if project is None:
            return
        self._project_id = project.id
        self.project_label.setText(f"当前项目：{project.name}")
        existing = StrategyRepository().list_by_project(project.id)
        self._clear_strategies()
        if existing:
            for strategy in existing:
                self._add_strategy(
                    {
                        "name": strategy.name,
                        "statement": strategy.statement,
                        "release_hour": strategy.release_hour,
                    }
                )
        else:
            for item in DEFAULT_STRATEGY_TEXT:
                self._add_strategy(item)
        self._sync_buttons()

    def _add_strategy(self, data: dict | None = None) -> None:
        if len(self._strategy_rows) >= 4:
            return
        data = data or {
            "name": f"策略 {len(self._strategy_rows) + 1}",
            "statement": "",
            "release_hour": 4 * len(self._strategy_rows),
        }

        card = PrismCard()
        header = QHBoxLayout()
        title = QLabel(f"策略 {len(self._strategy_rows) + 1}")
        remove_btn = PrismDangerButton("删除")
        remove_btn.clicked.connect(lambda: self._remove_strategy(card))
        header.addWidget(title)
        header.addStretch()
        header.addWidget(remove_btn)
        card.addLayout(header)

        name_input = PrismLineEdit("策略名称")
        name_input.setText(str(data.get("name", "")))
        statement_input = QPlainTextEdit()
        statement_input.setPlaceholderText("填写该策略的企业回应声明稿。")
        statement_input.setPlainText(str(data.get("statement", "")))
        statement_input.setMinimumHeight(96)
        release_input = QSpinBox()
        release_input.setRange(0, 48)
        release_input.setValue(int(data.get("release_hour", 0)))

        card.addWidget(QLabel("策略名称"))
        card.addWidget(name_input)
        card.addWidget(QLabel("声明稿"))
        card.addWidget(statement_input)
        card.addWidget(QLabel("计划发布时间（模拟小时）"))
        card.addWidget(release_input)

        row = {
            "card": card,
            "title": title,
            "remove_btn": remove_btn,
            "name": name_input,
            "statement": statement_input,
            "release_hour": release_input,
        }
        self._strategy_rows.append(row)
        self.strategy_container.addWidget(card)
        self._sync_buttons()

    def _remove_strategy(self, card: PrismCard) -> None:
        if len(self._strategy_rows) <= 2:
            QMessageBox.information(self, "Prism", "至少需要保留 2 个策略。")
            return
        for row in list(self._strategy_rows):
            if row["card"] is card:
                self._strategy_rows.remove(row)
                card.deleteLater()
                break
        self._sync_buttons()

    def _clear_strategies(self) -> None:
        for row in self._strategy_rows:
            row["card"].deleteLater()
        self._strategy_rows.clear()

    def _sync_buttons(self) -> None:
        self.add_button.setEnabled(len(self._strategy_rows) < 4)
        for index, row in enumerate(self._strategy_rows, start=1):
            row["title"].setText(f"策略 {index}")
            row["remove_btn"].setEnabled(len(self._strategy_rows) > 2)

    def _save_strategies(self) -> None:
        if self._project_id is None:
            QMessageBox.warning(self, "Prism", "请先保存事件信息。")
            return
        strategies = []
        for row in self._strategy_rows:
            name = row["name"].text().strip() or f"策略 {len(strategies) + 1}"
            statement = row["statement"].toPlainText().strip()
            if len(name) > MAX_STRATEGY_NAME_CHARS:
                QMessageBox.warning(self, "Prism", f"策略名称最多 {MAX_STRATEGY_NAME_CHARS} 个字符。")
                return
            if not statement:
                QMessageBox.warning(self, "Prism", f"请填写{name}的声明稿。")
                return
            if len(statement) > MAX_STRATEGY_STATEMENT_CHARS:
                QMessageBox.warning(self, "Prism", f"{name} 的声明稿最多 {MAX_STRATEGY_STATEMENT_CHARS} 个字符。")
                return
            strategies.append(
                {
                    "name": name,
                    "statement": statement,
                    "release_hour": row["release_hour"].value(),
                }
            )
        StrategyRepository().replace_for_project(self._project_id, strategies)
        self.strategies_saved.emit(self._project_id)
