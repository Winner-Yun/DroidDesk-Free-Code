"""Video preview widget and cached thumbnail provider."""

from __future__ import annotations

from pathlib import Path
from typing import override

from PySide6.QtCore import QEvent, QObject, QPoint, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import (
    QColor,
    QEnterEvent,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
    QPixmap,
)
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QVideoFrame, QVideoSink
from PySide6.QtWidgets import QSizePolicy, QWidget

from droiddesk.ui.theme import (
    BG_APP,
    BORDER,
    TEXT_MUTED,
)


class VideoThumbnailProvider(QObject):
    """Asynchronous, disk-cached video thumbnail provider powered by QtMultimedia."""

    thumbnail_ready = Signal(Path, QPixmap)

    _instance: VideoThumbnailProvider | None = None

    @classmethod
    def instance(cls) -> VideoThumbnailProvider:
        if cls._instance is None:
            cls._instance = VideoThumbnailProvider()
        return cls._instance

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._cache: dict[Path, QPixmap] = {}
        self._disk_cache_dir = (Path.home() / "Videos" / "DroidDesk" / ".thumbnails").resolve()
        self._queue: list[Path] = []
        self._active_path: Path | None = None

        self._player = QMediaPlayer(self)
        self._audio = QAudioOutput(self)
        self._audio.setMuted(True)
        self._player.setAudioOutput(self._audio)
        self._sink = QVideoSink(self)
        self._player.setVideoSink(self._sink)
        self._sink.videoFrameChanged.connect(self._on_frame_received)

        self._timeout_timer = QTimer(self)
        self._timeout_timer.setSingleShot(True)
        self._timeout_timer.setInterval(2500)
        self._timeout_timer.timeout.connect(self._on_timeout)

    def get_thumbnail(self, path: Path) -> QPixmap | None:
        """Return cached QPixmap thumbnail if available, or enqueue async extraction."""
        path = path.resolve()
        if path in self._cache:
            return self._cache[path]

        disk_path = self._disk_cache_dir / f"{path.stem}.jpg"
        if disk_path.is_file():
            pm = QPixmap(str(disk_path))
            if not pm.isNull():
                self._cache[path] = pm
                return pm

        self.request_thumbnail(path)
        return None

    def request_thumbnail(self, path: Path) -> None:
        """Enqueue a video path for thumbnail extraction."""
        path = path.resolve()
        if path in self._cache:
            return
        if path == self._active_path or path in self._queue:
            return
        self._queue.append(path)
        self._process_queue()

    def _process_queue(self) -> None:
        if self._active_path is not None:
            return
        if not self._queue:
            return
        self._active_path = self._queue.pop(0)
        self._player.setSource(QUrl.fromLocalFile(str(self._active_path)))
        self._player.play()
        self._timeout_timer.start()

    def _on_frame_received(self, frame: QVideoFrame) -> None:
        if not self._active_path:
            return
        img = frame.toImage()
        if img.isNull() or img.width() <= 0 or img.height() <= 0:
            return

        self._timeout_timer.stop()
        self._player.stop()

        pm = QPixmap.fromImage(img)
        self._cache[self._active_path] = pm

        try:
            self._disk_cache_dir.mkdir(parents=True, exist_ok=True)
            disk_path = self._disk_cache_dir / f"{self._active_path.stem}.jpg"
            img.save(str(disk_path))
        except Exception:
            pass

        finished_path = self._active_path
        self._active_path = None
        self.thumbnail_ready.emit(finished_path, pm)
        self._process_queue()

    def _on_timeout(self) -> None:
        self._player.stop()
        self._active_path = None
        self._process_queue()


class VideoPreviewWidget(QWidget):
    """Interactive preview canvas displaying a video thumbnail with play overlay."""

    play_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._video_path: Path | None = None
        self._pixmap: QPixmap | None = None
        self._is_hovered = False

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(240, 220)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {BG_APP};
                border: 1px solid {BORDER};
                border-radius: 8px;
            }}
        """)

        # Connect to provider singleton
        self._provider = VideoThumbnailProvider.instance()
        self._provider.thumbnail_ready.connect(self._on_thumbnail_ready)

    def set_video_path(self, path: Path | None) -> None:
        """Set the active video file and retrieve its thumbnail."""
        self._video_path = path.resolve() if path else None
        if not self._video_path:
            self._pixmap = None
            self.update()
            return

        cached = self._provider.get_thumbnail(self._video_path)
        self._pixmap = cached
        self.update()

    def set_pixmap(self, pixmap: QPixmap | None) -> None:
        """Explicitly set thumbnail pixmap."""
        self._pixmap = pixmap
        self.update()

    def _on_thumbnail_ready(self, path: Path, pixmap: QPixmap) -> None:
        if self._video_path and path == self._video_path:
            self._pixmap = pixmap
            self.update()

    @override
    def enterEvent(self, event: QEnterEvent) -> None:
        super().enterEvent(event)
        self._is_hovered = True
        self.update()

    @override
    def leaveEvent(self, event: QEvent) -> None:
        super().leaveEvent(event)
        self._is_hovered = False
        self.update()

    @override
    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        super().mouseReleaseEvent(event)
        if event.button() == Qt.MouseButton.LeftButton and self._video_path:
            self.play_requested.emit()

    @override
    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        rect = self.rect()

        if self._pixmap and not self._pixmap.isNull():
            margin = 10
            avail_w = max(10, rect.width() - (margin * 2))
            avail_h = max(10, rect.height() - (margin * 2))
            scaled = self._pixmap.scaled(
                avail_w,
                avail_h,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = (rect.width() - scaled.width()) // 2
            y = (rect.height() - scaled.height()) // 2

            # Rounded clip path for the thumbnail image
            clip_path = QPainterPath()
            clip_path.addRoundedRect(x, y, scaled.width(), scaled.height(), 6, 6)
            painter.save()
            painter.setClipPath(clip_path)
            painter.drawPixmap(x, y, scaled)
            painter.restore()

            # Center Play Overlay Badge
            center_x = rect.width() // 2
            center_y = rect.height() // 2
            radius = 26 if not self._is_hovered else 29

            painter.save()
            bg_color = (
                QColor(16, 185, 129, 210)
                if self._is_hovered
                else QColor(24, 24, 27, 180)
            )
            painter.setBrush(bg_color)
            border_color = (
                QColor(255, 255, 255, 220)
                if self._is_hovered
                else QColor(255, 255, 255, 120)
            )
            painter.setPen(QPen(border_color, 1.5))
            painter.drawEllipse(QPoint(center_x, center_y), radius, radius)

            # Play triangle
            triangle = QPainterPath()
            tri_h = 16
            tri_w = 14
            triangle.moveTo(center_x - (tri_w // 3), center_y - (tri_h // 2))
            triangle.lineTo(center_x + (tri_w * 2 // 3), center_y)
            triangle.lineTo(center_x - (tri_w // 3), center_y + (tri_h // 2))
            triangle.closeSubpath()

            painter.setBrush(QColor(255, 255, 255, 240))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawPath(triangle)
            painter.restore()
        else:
            painter.setPen(QPen(QColor(TEXT_MUTED)))
            msg = "Loading thumbnail..." if self._video_path else "No recording selected"
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, msg)
