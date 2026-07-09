"""事件录入页。"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QMessageBox,
    QPlainTextEdit,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core.document_importer import (
    ImportedDocument,
    MAX_IMPORT_FILES,
    MAX_IMPORT_TOTAL_CHARS,
    SUPPORTED_DOCUMENT_SUFFIXES,
    chunk_text,
    import_documents,
)
from db.models import KnowledgeRepository, ProjectRepository
from ui.widgets import BodyLabel, CaptionLabel, PrismCard, PrismLineEdit, PrismPrimaryButton, PrismSecondaryButton, SectionTitle


MAX_TITLE_CHARS = 80
MAX_BACKGROUND_CHARS = 40000
MAX_STATEMENT_CHARS = 8000


class EventPage(QWidget):
    """危机事件录入。"""

    project_saved = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project_id: int | None = None
        self._imported_documents: list[ImportedDocument] = []
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

        layout.addWidget(SectionTitle("事件录入"))
        layout.addWidget(BodyLabel("录入危机事件基础信息。保存后会自动创建或更新本地项目，并进入策略配置。"))

        card = PrismCard()
        form = QFormLayout()
        form.setSpacing(12)

        self.title_input = PrismLineEdit("例如：连锁茶饮食品安全争议")
        self.industry_combo = QComboBox()
        self.industry_combo.setEditable(True)
        self.industry_combo.addItems(["餐饮 / 新消费", "互联网平台", "汽车 / 出行", "医药健康", "金融服务", "其他"])

        self.background_input = QPlainTextEdit()
        self.background_input.setPlaceholderText("描述事件背景、当前传播情况、公众关注点。")
        self.background_input.setMinimumHeight(130)
        self.import_hint = CaptionLabel(
            f"可导入 PDF / Word / Markdown / TXT，最多 {MAX_IMPORT_FILES} 个文件，导入文本总量约 {MAX_IMPORT_TOTAL_CHARS} 字。"
        )
        self.import_button = PrismSecondaryButton("导入背景文档")
        self.import_button.clicked.connect(self._import_background_documents)

        self.statement_input = QPlainTextEdit()
        self.statement_input.setPlaceholderText("可选：企业已经发布或准备发布的现有声明。")
        self.statement_input.setMinimumHeight(92)

        self.heat_input = QSpinBox()
        self.heat_input.setRange(1, 100)
        self.heat_input.setValue(45)

        self.sentiment_input = QDoubleSpinBox()
        self.sentiment_input.setRange(-1.0, 1.0)
        self.sentiment_input.setSingleStep(0.05)
        self.sentiment_input.setDecimals(2)
        self.sentiment_input.setValue(-0.2)

        form.addRow("项目 / 事件标题", self.title_input)
        form.addRow("涉及行业", self.industry_combo)
        form.addRow("事件背景", self.background_input)
        form.addRow("", self.import_button)
        form.addRow("", self.import_hint)
        form.addRow("企业现有声明", self.statement_input)
        form.addRow("初始热度", self.heat_input)
        form.addRow("公众情绪基线", self.sentiment_input)
        card.addLayout(form)
        layout.addWidget(card)

        actions = QHBoxLayout()
        actions.addStretch()
        self.save_button = PrismPrimaryButton("保存并配置策略")
        self.save_button.clicked.connect(self._save_project)
        actions.addWidget(self.save_button)
        layout.addLayout(actions)
        layout.addStretch()

    def load_project(self, project_id: int) -> None:
        project = ProjectRepository().get_by_id(project_id)
        if project is None:
            return
        self._project_id = project.id
        self._imported_documents = []
        scenario = project.scenario
        self.title_input.setText(scenario.get("title") or project.name)
        self.industry_combo.setCurrentText(scenario.get("industry", ""))
        self.background_input.setPlainText(scenario.get("background", ""))
        self.statement_input.setPlainText(scenario.get("company_statement", ""))
        self.heat_input.setValue(int(scenario.get("initial_heat", 45)))
        self.sentiment_input.setValue(float(scenario.get("baseline_sentiment", -0.2)))

    def reset_for_new_project(self) -> None:
        self._project_id = None
        self._imported_documents = []
        self.title_input.clear()
        self.industry_combo.setCurrentIndex(0)
        self.background_input.clear()
        self.statement_input.clear()
        self.heat_input.setValue(45)
        self.sentiment_input.setValue(-0.2)
        self.import_hint.setText(
            f"可导入 PDF / Word / Markdown / TXT，最多 {MAX_IMPORT_FILES} 个文件，导入文本总量约 {MAX_IMPORT_TOTAL_CHARS} 字。"
        )

    def _save_project(self) -> None:
        title = self.title_input.text().strip() or "未命名推演项目"
        if len(title) > MAX_TITLE_CHARS:
            QMessageBox.warning(self, "Prism", f"标题最多 {MAX_TITLE_CHARS} 个字符。")
            return
        scenario = {
            "title": title,
            "industry": self.industry_combo.currentText().strip(),
            "background": self.background_input.toPlainText().strip(),
            "company_statement": self.statement_input.toPlainText().strip(),
            "initial_heat": float(self.heat_input.value()),
            "baseline_sentiment": float(self.sentiment_input.value()),
            "key_entities": [],
        }
        if not scenario["background"]:
            QMessageBox.warning(self, "Prism", "请填写事件背景。")
            return
        if len(scenario["background"]) > MAX_BACKGROUND_CHARS:
            QMessageBox.warning(self, "Prism", f"事件背景最多 {MAX_BACKGROUND_CHARS} 个字符，请删减导入内容。")
            return
        if len(scenario["company_statement"]) > MAX_STATEMENT_CHARS:
            QMessageBox.warning(self, "Prism", f"企业声明最多 {MAX_STATEMENT_CHARS} 个字符。")
            return

        repo = ProjectRepository()
        if self._project_id is None:
            project = repo.create(title, scenario)
            self._project_id = project.id
        else:
            project = repo.update_scenario(self._project_id, scenario, name=title, status="draft")
        KnowledgeRepository().replace_for_project(project.id, self._build_knowledge_chunks(scenario))
        self.project_saved.emit(project.id)

    def _import_background_documents(self) -> None:
        filters = "文档 (*.pdf *.docx *.md *.markdown *.txt)"
        paths, _ = QFileDialog.getOpenFileNames(self, "导入事件背景文档", "", filters)
        if not paths:
            return
        if len(self._imported_documents) + len(paths) > MAX_IMPORT_FILES:
            QMessageBox.warning(self, "Prism", f"一个项目最多导入 {MAX_IMPORT_FILES} 个背景文档。")
            return
        try:
            documents = import_documents(paths)
        except Exception as exc:  # noqa: BLE001 - UI 需要显示解析错误
            QMessageBox.critical(self, "Prism 文档导入失败", str(exc))
            return
        if not documents:
            QMessageBox.information(self, "Prism", "没有提取到可用文本。")
            return
        imported_chars = sum(len(document.text) for document in self._imported_documents)
        new_chars = sum(len(document.text) for document in documents)
        if imported_chars + new_chars > MAX_IMPORT_TOTAL_CHARS:
            QMessageBox.warning(self, "Prism", f"导入文本总量最多约 {MAX_IMPORT_TOTAL_CHARS} 字。")
            return
        self._imported_documents.extend(documents)
        current = self.background_input.toPlainText().strip()
        summary = "\n".join(f"- {document.title}（约 {len(document.text)} 字）" for document in documents)
        imported_text = f"【已导入背景资料】\n{summary}"
        combined = f"{current}\n\n{imported_text}".strip() if current else imported_text
        if len(combined) > MAX_BACKGROUND_CHARS:
            QMessageBox.warning(
                self,
                "Prism",
                f"导入后事件背景会超过 {MAX_BACKGROUND_CHARS} 个字符，请减少文件或删减内容。",
            )
            return
        self.background_input.setPlainText(combined)
        suffixes = ", ".join(sorted(SUPPORTED_DOCUMENT_SUFFIXES))
        self.import_hint.setText(f"已累计导入 {len(self._imported_documents)} 个文档，将在保存时构建 RAG 知识库。支持类型：{suffixes}")

    def _build_knowledge_chunks(self, scenario: dict) -> list[dict]:
        chunks: list[dict] = []
        for index, chunk in enumerate(chunk_text(scenario["background"])):
            chunks.append({"source": "事件背景", "chunk_index": index, "content": chunk})
        for document in self._imported_documents:
            for index, chunk in enumerate(chunk_text(document.text)):
                chunks.append({"source": document.title, "chunk_index": index, "content": chunk})
        return chunks
