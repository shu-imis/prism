"""Prism 品牌图形组件 — QPainter 自定义绘制

棱镜折射：一束白光射入三角形棱镜，折射出光谱四色。
作为应用的核心视觉签名，出现在侧边栏顶部和首页中心。
"""
from __future__ import annotations

import math

from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QSize, QPointF
from PySide6.QtGui import (
    QPainter,
    QColor,
    QPen,
    QBrush,
    QLinearGradient,
    QPolygonF,
    QRadialGradient,
)

from ui.styles import (
    SPECTRUM_INDIGO,
    SPECTRUM_VIOLET,
    SPECTRUM_CYAN,
    SPECTRUM_GREEN,
)


class PrismLogo(QWidget):
    """棱镜折射图形 — 自定义 QPainter 绘制

    绘制内容：
      1. 左侧一束白色入射光
      2. 中央三角形棱镜（半透明玻璃感）
      3. 右侧折射出的四色光谱扇形
    """

    def __init__(self, size: int = 56, parent=None):
        super().__init__(parent)
        self._size = size
        self.setFixedSize(size, size)

    def sizeHint(self) -> QSize:
        return QSize(self._size, self._size)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        w = self.width()
        h = self.height()
        cx = w / 2
        cy = h / 2

        # ---- 参数 ----
        tri_size = w * 0.28          # 棱镜边长
        beam_len = w * 0.22          # 光束长度
        spectrum_len = w * 0.32      # 光谱扇形长度

        # 棱镜三角形（等边，顶点朝上，略偏左）
        tri_cx = cx - w * 0.02
        tri_cy = cy
        half = tri_size / 2
        # 等边三角形三个顶点
        p_top = QPointF(tri_cx, tri_cy - tri_size * 0.72)
        p_bl = QPointF(tri_cx - half, tri_cy + tri_size * 0.36)
        p_br = QPointF(tri_cx + half, tri_cy + tri_size * 0.36)

        # ---- 1. 入射光束（从左到棱镜中心） ----
        beam_start = QPointF(tri_cx - half - beam_len, tri_cy + tri_size * 0.05)
        beam_end = QPointF(tri_cx - half * 0.3, tri_cy - tri_size * 0.05)

        # 入射光 — 白色渐变（从淡到亮）
        beam_grad = QLinearGradient(beam_start, beam_end)
        beam_grad.setColorAt(0, QColor(255, 255, 255, 0))
        beam_grad.setColorAt(1, QColor(255, 255, 255, 180))
        pen = QPen(QBrush(beam_grad), 2.5)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.drawLine(beam_start, beam_end)

        # ---- 2. 棱镜本体（半透明三角形 + 边缘高光） ----
        tri = QPolygonF([p_top, p_bl, p_br])

        # 填充 — 极淡的玻璃感
        painter.setPen(Qt.NoPen)
        glass_grad = QLinearGradient(p_top, p_br)
        glass_grad.setColorAt(0, QColor(255, 255, 255, 25))
        glass_grad.setColorAt(0.5, QColor(180, 190, 255, 15))
        glass_grad.setColorAt(1, QColor(120, 130, 200, 10))
        painter.setBrush(QBrush(glass_grad))
        painter.drawPolygon(tri)

        # 边缘 — 高光线（棱镜切面感）
        edge_pen = QPen(QColor(255, 255, 255, 90), 1.5)
        painter.setPen(edge_pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPolygon(tri)

        # ---- 3. 折射光谱（四色扇形发散） ----
        # 从棱镜右侧出发，向右发散四条彩色光束
        refract_origin = QPointF(tri_cx + half * 0.5, tri_cy - tri_size * 0.08)

        colors = [SPECTRUM_INDIGO, SPECTRUM_VIOLET, SPECTRUM_CYAN, SPECTRUM_GREEN]
        # 四条光束的角度（弧度），从略向上到略向下扇形展开
        angles = [-0.25, -0.08, 0.10, 0.28]

        for i, (color, angle) in enumerate(zip(colors, angles)):
            end_x = refract_origin.x() + spectrum_len * math.cos(angle)
            end_y = refract_origin.y() + spectrum_len * math.sin(angle)
            end_point = QPointF(end_x, end_y)

            # 渐变 — 从棱镜出射点到末端，颜色从浓到淡
            grad = QLinearGradient(refract_origin, end_point)
            c = QColor(color)
            grad.setColorAt(0, QColor(c.red(), c.green(), c.blue(), 220))
            grad.setColorAt(1, QColor(c.red(), c.green(), c.blue(), 0))

            pen = QPen(QBrush(grad), 2.5)
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            painter.drawLine(refract_origin, end_point)

        # ---- 4. 折射点微光晕 ----
        painter.setPen(Qt.NoPen)
        glow_grad = QRadialGradient(refract_origin, 8)
        glow_grad.setColorAt(0, QColor(255, 255, 255, 120))
        glow_grad.setColorAt(1, QColor(255, 255, 255, 0))
        painter.setBrush(QBrush(glow_grad))
        painter.drawEllipse(refract_origin, 8, 8)

        painter.end()
