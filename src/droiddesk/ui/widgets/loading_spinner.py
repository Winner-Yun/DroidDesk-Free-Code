"""A modern, animated loading spinner widget. Uses QPainter to draw a spinning
arc, providing a crisp, resolution-independent loading indicator.
"""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QDialog, QLabel, QVBoxLayout, QWidget,QGraphicsOpacityEffect


class SpinnerWidget(QWidget):
    """A resolution-independent animated spinner."""
    def __init__(self, size: int = 40, color: str = "#3b82f6", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._color = QColor(color)
        self._angle = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._rotate)
        self._timer.setInterval(16)  # ~60fps
        
    def start(self) -> None:
        self._timer.start()
        
    def stop(self) -> None:
        self._timer.stop()
        
    def _rotate(self) -> None:
        self._angle = (self._angle + 6) % 360
        self.update()
        
    def paintEvent(self, event) -> None:
        if not self._timer.isActive():
            return
            
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        pen = QPen(self._color)
        pen.setWidth(4)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        
        rect = QRectF(4, 4, self.width() - 8, self.height() - 8)
        # Draw a 270 degree arc. Angle is measured in 1/16th of a degree.
        # Negative angle makes it spin clockwise.
        painter.drawArc(rect, -self._angle * 16, 270 * 16)
        painter.end()


class LoadingPage(QDialog):
    """Modern animated loading dialog."""

    def __init__(
        self,
        message: str = "Loading...",
        parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Dialog
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setModal(True)

        # Main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Glass-style container
        self.container = QWidget()
        self.container.setObjectName("loadingContainer")
        self.container.setFixedSize(260, 190)

        self.container.setStyleSheet("""
            #loadingContainer {
                background: rgba(25, 25, 28, 245);
                border: 1px solid rgba(255, 255, 255, 25);
                border-radius: 18px;
            }
        """)

        c_layout = QVBoxLayout(self.container)
        c_layout.setContentsMargins(20, 20, 20, 20)
        c_layout.setSpacing(0)
        c_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Spinner
        self.spinner = SpinnerWidget(size=56)

        # Loading title
        self.label = QLabel(message)
        self.label.setObjectName("loadingLabel")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setWordWrap(True)

        self.label.setStyleSheet("""
            #loadingLabel {
                color: #f5f5f5;
                font-size: 15px;
                font-weight: 600;
                margin-top: 14px;
            }
        """)

        # Small status text
        self.status = QLabel("Please wait")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.status.setStyleSheet("""
            color: #777777;
            font-size: 11px;
            margin-top: 6px;
        """)

        c_layout.addWidget(
            self.spinner,
            0,
            Qt.AlignmentFlag.AlignCenter
        )

        c_layout.addSpacing(10)

        c_layout.addWidget(
            self.label,
            0,
            Qt.AlignmentFlag.AlignCenter
        )

        c_layout.addWidget(
            self.status,
            0,
            Qt.AlignmentFlag.AlignCenter
        )

        layout.addWidget(self.container)

        # Fade-in animation
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)

        self.fade_animation = QPropertyAnimation(
            self.opacity_effect,
            b"opacity"
        )
        self.fade_animation.setDuration(220)
        self.fade_animation.setStartValue(0.0)
        self.fade_animation.setEndValue(1.0)
        self.fade_animation.setEasingCurve(
            QEasingCurve.Type.OutCubic
        )

    def showEvent(self, event) -> None:
        super().showEvent(event)

        self.spinner.start()

        self.opacity_effect.setOpacity(0.0)
        self.fade_animation.start()

    def hideEvent(self, event) -> None:
        self.spinner.stop()
        super().hideEvent(event)

    def set_message(self, message: str) -> None:
        self.label.setText(message)