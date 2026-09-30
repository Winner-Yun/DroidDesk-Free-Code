"""A modern, animated loading spinner widget. Uses QPainter to draw a spinning
arc, providing a crisp, resolution-independent loading indicator.
"""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QHideEvent, QPainter, QPaintEvent, QPen, QShowEvent
from PySide6.QtWidgets import QDialog, QGraphicsOpacityEffect, QLabel, QVBoxLayout, QWidget


class SpinnerWidget(QWidget):
    """A resolution-independent animated spinner with subtle track ring."""

    def __init__(
        self,
        size: int = 40,
        color: str | None = None,
        track_color: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._angle = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._rotate)
        self._timer.setInterval(16)  # ~60fps

        from droiddesk.ui.theme import is_light

        light = is_light() if color is None else (color.lower() in ("#2563eb", "#1d4ed8"))
        self._color = QColor(color or ("#2563eb" if light else "#3b82f6"))
        self._track_color = QColor(
            track_color or ("rgba(0, 0, 0, 25)" if light else "rgba(255, 255, 255, 30)")
        )

    def set_color(self, color: str, track_color: str | None = None) -> None:
        self._color = QColor(color)
        if track_color is not None:
            self._track_color = QColor(track_color)
        self.update()

    def set_theme(self, mode: str) -> None:
        is_light = mode.lower() == "light"
        self._color = QColor("#2563eb" if is_light else "#3b82f6")
        self._track_color = QColor("rgba(0, 0, 0, 25)" if is_light else "rgba(255, 255, 255, 30)")
        self.update()

    def start(self) -> None:
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def _rotate(self) -> None:
        self._angle = (self._angle + 6) % 360
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        if not self._timer.isActive():
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRectF(4, 4, self.width() - 8, self.height() - 8)

        # Draw subtle background track circle
        if self._track_color.alpha() > 0:
            track_pen = QPen(self._track_color)
            track_pen.setWidth(4)
            painter.setPen(track_pen)
            painter.drawEllipse(rect)

        # Draw active spinning arc
        pen = QPen(self._color)
        pen.setWidth(4)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)

        # Draw a 270 degree arc. Angle is measured in 1/16th of a degree.
        # Negative angle makes it spin clockwise.
        painter.drawArc(rect, -self._angle * 16, 270 * 16)
        painter.end()


class LoadingPage(QDialog):
    """Modern animated loading dialog with dark and light mode responsiveness."""

    def __init__(self, message: str = "Loading...", parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
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

        # Small status text
        self.status = QLabel("Please wait")
        self.status.setObjectName("loadingStatus")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)

        c_layout.addWidget(self.spinner, 0, Qt.AlignmentFlag.AlignCenter)
        c_layout.addSpacing(12)
        c_layout.addWidget(self.label, 0, Qt.AlignmentFlag.AlignCenter)
        c_layout.addSpacing(4)
        c_layout.addWidget(self.status, 0, Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(self.container)

        # Fade-in animation initialized ONCE
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)

        self.fade_animation = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.fade_animation.setDuration(220)
        self.fade_animation.setStartValue(0.0)
        self.fade_animation.setEndValue(1.0)
        self.fade_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        from droiddesk.ui.theme import get_current_theme

        self.set_theme(get_current_theme())

    def set_theme(self, mode: str) -> None:
        is_light = mode.lower() == "light"
        if is_light:
            self.container.setStyleSheet("""
                #loadingContainer {
                    background: rgba(255, 255, 255, 250);
                    border: 1px solid rgba(0, 0, 0, 45);
                    border-radius: 18px;
                }
            """)
            self.label.setStyleSheet("""
                #loadingLabel {
                    color: #111827;
                    font-size: 15px;
                    font-weight: 600;
                    background: transparent;
                }
            """)
            self.status.setStyleSheet("""
                #loadingStatus {
                    color: #6b7280;
                    font-size: 11px;
                    background: transparent;
                }
            """)
            self.spinner.set_theme("light")
        else:
            self.container.setStyleSheet("""
                #loadingContainer {
                    background: rgba(25, 25, 28, 245);
                    border: 1px solid rgba(255, 255, 255, 25);
                    border-radius: 18px;
                }
            """)
            self.label.setStyleSheet("""
                #loadingLabel {
                    color: #f5f5f5;
                    font-size: 15px;
                    font-weight: 600;
                    background: transparent;
                }
            """)
            self.status.setStyleSheet("""
                #loadingStatus {
                    color: #8b8e94;
                    font-size: 11px;
                    background: transparent;
                }
            """)
            self.spinner.set_theme("dark")

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        super().showEvent(event)

        from droiddesk.ui.theme import get_current_theme

        self.set_theme(get_current_theme())

        parent = self.parentWidget()
        if parent is not None:
            p_geom = parent.geometry()
            x = p_geom.x() + (p_geom.width() - self.width()) // 2
            y = p_geom.y() + (p_geom.height() - self.height()) // 2
            self.move(x, y)

        self.spinner.start()

        self.opacity_effect.setOpacity(0.0)
        self.fade_animation.start()

    def hideEvent(self, event: QHideEvent) -> None:  # noqa: N802
        self.spinner.stop()
        super().hideEvent(event)

    def set_message(self, message: str, status: str = "Please wait") -> None:
        self.label.setText(message)
        self.status.setText(status)
