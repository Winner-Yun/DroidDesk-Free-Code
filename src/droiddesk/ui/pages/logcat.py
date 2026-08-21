"""Logcat page — Section 6.4. LogcatModel-backed table view with a filter
toolbar (level/tag/PID/regex) and pause control. Seeded from
`static_data.LOGCAT_LINES` through the real `LogcatModel.queue()` /
`parse_threadtime` path so the column layout and parsing are already proven
out before Phase 2 wires in a live `AdbStream`.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from droiddesk.ui import static_data
from droiddesk.ui.models.logcat_model import LogcatModel
from droiddesk.ui.widgets.card import PageHeader

_PRIORITY_COLORS = {"E": "#e05a4d", "W": "#f1c40f", "I": "#5b9bd5", "D": "#8b8e94", "V": "#5c5f66"}


class LogcatPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setProperty("role", "page")
        self._model = LogcatModel()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(14)

        header = PageHeader("Logcat", "Streamed from the selected device and parsed into columns. Pausing holds the view without dropping the stream.")
        self._pause_button = QPushButton("⏸  Pause")
        self._pause_button.setCheckable(True)
        self._pause_button.toggled.connect(self._on_pause_toggled)
        header.add_action(self._pause_button)
        header.add_action(QPushButton("✕  Clear"))
        header.add_action(QPushButton("↓  Export view"))
        self._stream_button = QPushButton("Start stream")
        self._stream_button.setProperty("role", "primary")
        self._stream_button.setCheckable(True)
        self._stream_button.setChecked(True)
        self._stream_button.setText("Start stream")
        header.add_action(self._stream_button)
        outer.addWidget(header)

        outer.addLayout(self._build_filter_row())

        self._table = QTableView()
        self._table.setModel(self._model)
        self._table.setShowGrid(False)
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        header_view = self._table.horizontalHeader()
        header_view.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        outer.addWidget(self._table, 1)

        for line in static_data.LOGCAT_LINES:
            self._model.queue(line)
        self._model._flush()  # static seed data: skip the 100ms batching timer

    def _build_filter_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)

        self._level_combo = QComboBox()
        self._level_combo.addItems(["V", "D", "I", "W", "E"])
        self._level_combo.setFixedWidth(56)
        row.addWidget(self._level_combo)

        self._tag_input = QLineEdit()
        self._tag_input.setPlaceholderText("Tag")
        self._tag_input.setFixedWidth(140)
        row.addWidget(self._tag_input)

        self._pid_input = QLineEdit()
        self._pid_input.setPlaceholderText("PID")
        self._pid_input.setFixedWidth(90)
        row.addWidget(self._pid_input)

        self._regex_input = QLineEdit()
        self._regex_input.setPlaceholderText("Regular expression over the message column")
        row.addWidget(self._regex_input, 1)

        count_label = QLabel(f"{static_data.LOGCAT_LINE_COUNT} lines")
        count_label.setProperty("role", "muted")
        row.addWidget(count_label)

        return row

    def _on_pause_toggled(self, paused: bool) -> None:
        self._model.set_paused(paused)
        self._pause_button.setText("▶  Resume" if paused else "⏸  Pause")
        # TODO(Phase 2): QSortFilterProxyModel over tag/priority/PID/regex,
        # and wire Start stream / Export view to AdbClient.logcat_stream().
