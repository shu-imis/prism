"""首页 — 现代网页设计风格

核心理念：
  - 大留白 ≠ 空白。用渐变光晕、微噪点营造"空间氛围"。
  - 棱镜 Logo 是视觉锚点，围绕它展开信息层级。
  - 信息分三区，每区之间用大面积留白区隔，而非分隔线。
  - 卡片不用全撑满，不对称布局更有设计感。
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QScrollArea, QFrame,
)
from PySide6.QtCore import Qt, Signal, QPointF
from PySide6.QtGui import (
    QFont, QColor, QPainter, QRadialGradient, QBrush,
)

from ui.styles import (
    ACCENT, ACCENT_RGB,
    BG_SURFACE,
    TEXT_PRIMARY, TEXT_TERTIARY, TEXT_QUATERNARY,
    BORDER_SUBTLE, BORDER_DEFAULT,
    RADIUS_CARD,
)
from ui.logo import PrismLogo
from ui.widgets import (
    PrismPrimaryButton, PrismSecondaryButton,
    SubtitleLabel, BodyLabel, SectionLabel,
)


class AmbientBackground(QWidget):
    """背景氛围层 — 顶部中央的微妙 accent 光晕 + 微噪点"""

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()

        # 顶部中央的光晕
        glow = QRadialGradient(QPointF(w * 0.5, h * 0.05), w * 0.7)
        glow.setColorAt(0, QColor(94, 106, 210, 18))
        glow.setColorAt(0.5, QColor(94, 106, 210, 5))
        glow.setColorAt(1, QColor(94, 106, 210, 0))
        painter.fillRect(self.rect(), QBrush(glow))

        # 极淡的噪点纹理
        painter.setPen(Qt.NoPen)
        import random
        random.seed(42)
        for _ in range(int(w * h * 0.0003)):
            x = random.randint(0, w - 1)
            y = random.randint(0, h - 1)
            alpha = random.randint(1, 3)
            painter.setBrush(QColor(255, 255, 255, alpha))
            painter.drawRect(x, y, 1, 1)

        painter.end()


class FeatureCard(QFrame):
    """Feature 卡片 — 图标在上，标题+描述在下"""

    def __init__(self, icon: str, title: str, desc: str, parent=None):
        super().__init__(parent)
        self.setObjectName("featureCard")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedWidth(240)

        self.setStyleSheet(f"""
            #featureCard {{
                background-color: {BG_SURFACE};
                border: 1px solid {BORDER_SUBTLE};
                border-radius: {RADIUS_CARD}px;
            }}
            #featureCard:hover {{
                border: 1px solid {BORDER_DEFAULT};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(14)

        # 图标 — 大
        icon_label = QLabel(icon)
        icon_label.setStyleSheet(f"font-size: 28px; color: {ACCENT}; border: none;")
        layout.addWidget(icon_label)

        # 标题
        tl = QLabel(title)
        tf = QFont()
        tf.setPointSize(15)
        tf.setBold(True)
        tl.setFont(tf)
        tl.setStyleSheet(f"color: {TEXT_PRIMARY}; border: none;")
        layout.addWidget(tl)

        # 描述
        dl = QLabel(desc)
        dl.setWordWrap(True)
        df = QFont()
        df.setPointSize(13)
        dl.setFont(df)
        dl.setStyleSheet(f"color: {TEXT_TERTIARY}; border: none;")
        dl.setFixedHeight(40)
        layout.addWidget(dl)

        layout.addStretch()


class ActionCard(QFrame):
    """操作入口卡片 — 可点击，hover 微亮边框"""

    clicked = Signal()

    def __init__(self, icon: str, title: str, desc: str, parent=None):
        super().__init__(parent)
        self.setObjectName("actionCard")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(300, 120)

        self.setStyleSheet(f"""
            #actionCard {{
                background-color: {BG_SURFACE};
                border: 1px solid {BORDER_SUBTLE};
                border-radius: {RADIUS_CARD}px;
            }}
            #actionCard:hover {{
                background-color: #1A1B20;
                border: 1px solid rgba({ACCENT_RGB}, 0.25);
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(18)

        # 图标
        icon_label = QLabel(icon)
        icon_label.setStyleSheet(f"font-size: 26px; color: {ACCENT}; border: none;")
        icon_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon_label)

        # 文字
        text = QVBoxLayout()
        text.setSpacing(4)

        tl = QLabel(title)
        tf = QFont()
        tf.setPointSize(16)
        tf.setBold(True)
        tl.setFont(tf)
        tl.setStyleSheet(f"color: {TEXT_PRIMARY}; border: none;")
        text.addWidget(tl)

        dl = QLabel(desc)
        dl.setWordWrap(True)
        df = QFont()
        df.setPointSize(13)
        dl.setFont(df)
        dl.setStyleSheet(f"color: {TEXT_TERTIARY}; border: none;")
        text.addWidget(dl)

        text.addStretch()
        layout.addLayout(text, 1)

        # 箭头
        arrow = QLabel("→")
        arrow.setStyleSheet(f"font-size: 18px; color: {TEXT_QUATERNARY}; border: none;")
        arrow.setAlignment(Qt.AlignVCenter)
        layout.addWidget(arrow)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class WelcomePage(QWidget):
    """首页"""

    new_project_clicked = Signal()
    open_project_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        # 背景氛围层
        ambient = AmbientBackground(self)
        ambient.setGeometry(self.rect())
        ambient.lower()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        inner = QWidget()
        scroll.setWidget(inner)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll)

        # 整体外边距 — 慷慨
        inner_layout = QVBoxLayout(inner)
        inner_layout.setContentsMargins(80, 72, 80, 72)
        inner_layout.setSpacing(0)

        # ════════ Hero ════════
        hero = QVBoxLayout()
        hero.setAlignment(Qt.AlignCenter)
        hero.setSpacing(0)

        # Logo — 视觉锚点
        logo_row = QHBoxLayout()
        logo_row.setAlignment(Qt.AlignCenter)
        logo = PrismLogo(size=80)
        logo_row.addWidget(logo)
        hero.addLayout(logo_row)

        hero.addSpacing(40)

        # 大标题
        title = QLabel("Prism")
        title.setAlignment(Qt.AlignCenter)
        tf = QFont()
        tf.setPointSize(40)
        tf.setBold(True)
        title.setFont(tf)
        title.setStyleSheet(f"color: {TEXT_PRIMARY};")
        hero.addWidget(title)

        hero.addSpacing(16)

        # 副标题
        sub = SubtitleLabel("棱镜折射 · 预见舆论光谱")
        sub.setAlignment(Qt.AlignCenter)
        sf = QFont()
        sf.setPointSize(18)
        sub.setFont(sf)
        hero.addWidget(sub)

        hero.addSpacing(24)

        # 描述
        desc = BodyLabel(
            "同一事件经由不同公众视角折射，呈现截然不同的舆论光谱。"
        )
        desc.setAlignment(Qt.AlignCenter)
        desc.setWordWrap(True)
        desc.setMaximumWidth(500)
        df = QFont()
        df.setPointSize(15)
        desc.setFont(df)
        hero.addWidget(desc)

        hero.addSpacing(48)

        # CTA
        cta = QHBoxLayout()
        cta.setAlignment(Qt.AlignCenter)
        cta.setSpacing(16)

        new_btn = PrismPrimaryButton("新建推演项目")
        new_btn.setFixedHeight(36)
        new_btn.setMinimumWidth(160)
        new_btn.clicked.connect(lambda: self.new_project_clicked.emit())

        open_btn = PrismSecondaryButton("打开历史项目")
        open_btn.setFixedHeight(36)
        open_btn.setMinimumWidth(160)
        open_btn.clicked.connect(lambda: self.open_project_clicked.emit())

        cta.addWidget(new_btn)
        cta.addWidget(open_btn)
        hero.addLayout(cta)

        inner_layout.addLayout(hero)

        # ════════ 大空区 ════════
        inner_layout.addSpacing(96)

        # ════════ 操作入口 ════════
        inner_layout.addWidget(SectionLabel("开始使用"))
        inner_layout.addSpacing(24)

        actions = QHBoxLayout()
        actions.setAlignment(Qt.AlignCenter)
        actions.setSpacing(24)

        new_card = ActionCard("◇", "新建推演", "录入危机事件，配置回应策略")
        new_card.clicked.connect(lambda: self.new_project_clicked.emit())

        open_card = ActionCard("◃", "继续推演", "打开历史项目，恢复仿真进度")
        open_card.clicked.connect(lambda: self.open_project_clicked.emit())

        actions.addWidget(new_card)
        actions.addWidget(open_card)
        inner_layout.addLayout(actions)

        # ════════ 大空区 ════════
        inner_layout.addSpacing(96)

        # ════════ 能力介绍 ════════
        inner_layout.addWidget(SectionLabel("核心能力"))
        inner_layout.addSpacing(24)

        features = QHBoxLayout()
        features.setAlignment(Qt.AlignCenter)
        features.setSpacing(24)

        features.addWidget(FeatureCard(
            "◉", "多智能体仿真",
            "8 类 Agent 模拟舆论场\n8-12 轮，32-48h 窗口"
        ))
        features.addWidget(FeatureCard(
            "◐", "策略对比",
            "双策略并行推演\n热度/情绪/支持率叠加"
        ))
        features.addWidget(FeatureCard(
            "◓", "评估报告",
            "六维雷达图 + 时间线\n一键导出 PDF"
        ))

        inner_layout.addLayout(features)
        inner_layout.addSpacing(80)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # 让背景氛围层跟随缩放
        for child in self.children():
            if isinstance(child, AmbientBackground):
                child.setGeometry(self.rect())
                child.lower()
