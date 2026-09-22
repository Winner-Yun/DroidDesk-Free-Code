"""Environment switch dialog: select, configure, and switch project environments."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from droiddesk.core.profiles import Environment
from droiddesk.services.env_service import EnvService
from droiddesk.ui.theme import ENVIRONMENT_RISK_COLORS, get_icon


class EnvironmentEditDialog(QDialog):
    """Modal dialog for creating or editing an environment configuration dynamically."""

    def __init__(
        self,
        env_service: EnvService,
        env: Environment | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._env_service = env_service
        self._existing = env

        self.setWindowTitle("Edit Environment" if env else "Add Target Environment")
        self.setMinimumWidth(440)
        self.setStyleSheet(
            """
            QDialog {
                background-color: #1a1b1e;
                color: #e5e7eb;
            }
            QLabel {
                color: #e5e7eb;
                font-size: 12px;
                font-weight: 600;
            }
            QLineEdit, QComboBox {
                background-color: #23252a;
                border: 1px solid #33363e;
                border-radius: 5px;
                color: #ffffff;
                padding: 6px 10px;
                font-size: 12px;
            }
            QLineEdit:focus, QComboBox:focus {
                border-color: #3b82f6;
            }
            QCheckBox {
                color: #d1d5db;
                font-size: 12px;
                font-weight: 500;
            }
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(14)

        header = QLabel("Edit Environment" if env else "Add Target Environment")
        header.setStyleSheet("font-size: 15px; font-weight: 700; color: #ffffff;")
        layout.addWidget(header)

        form = QFormLayout()
        form.setSpacing(10)

        self._key_input = QLineEdit()
        self._key_input.setPlaceholderText("e.g. dev, staging, production")
        if env:
            self._key_input.setText(env.key)
            self._key_input.setEnabled(False)
        form.addRow("Environment Key *", self._key_input)

        self._label_input = QLineEdit()
        self._label_input.setPlaceholderText("e.g. Development, Staging, Production")
        if env:
            self._label_input.setText(env.label)
        form.addRow("Display Label *", self._label_input)

        # Discovered project env files
        self._env_file_combo = QComboBox()
        self._env_file_combo.setEditable(True)
        discovered_envs = self._env_service.discover_project_env_files()
        for f in discovered_envs:
            self._env_file_combo.addItem(f)
        if env:
            self._env_file_combo.setCurrentText(env.env_file)
        elif not discovered_envs:
            self._env_file_combo.setCurrentText(".env")
        form.addRow("Env File Path *", self._env_file_combo)

        self._api_host_input = QLineEdit()
        self._api_host_input.setPlaceholderText("e.g. https://api.myproject.com")
        if env and env.api_host:
            self._api_host_input.setText(env.api_host)
        form.addRow("API Host URL", self._api_host_input)

        # Discovered firebase files
        self._firebase_combo = QComboBox()
        self._firebase_combo.setEditable(True)
        self._firebase_combo.addItem("")
        for fb in self._env_service.discover_project_firebase_files():
            self._firebase_combo.addItem(fb)
        if env and env.firebase:
            self._firebase_combo.setCurrentText(env.firebase)
        form.addRow("Firebase Config", self._firebase_combo)

        self._flavor_input = QLineEdit()
        self._flavor_input.setPlaceholderText("e.g. dev, staging, prod")
        if env and env.flavor:
            self._flavor_input.setText(env.flavor)
        form.addRow("Build Flavor", self._flavor_input)

        self._allow_release_cb = QCheckBox("Permit release builds in this environment")
        if env:
            self._allow_release_cb.setChecked(env.allow_release_build)
        form.addRow("", self._allow_release_cb)

        self._clean_git_cb = QCheckBox("Require clean git working tree for builds")
        if env:
            self._clean_git_cb.setChecked(env.require_clean_git)
        form.addRow("", self._clean_git_cb)

        layout.addLayout(form)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #2c2d33;
                border: 1px solid #3d404a;
                border-radius: 5px;
                color: #d1d5db;
                padding: 6px 16px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #383a42;
                color: #ffffff;
            }
            """
        )
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        save_btn = QPushButton("Save Environment")
        save_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #3b82f6;
                border: 1px solid #2563eb;
                border-radius: 5px;
                color: #ffffff;
                padding: 6px 18px;
                font-weight: 700;
            }
            QPushButton:hover {
                background-color: #2563eb;
            }
            """
        )
        save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(save_btn)

        layout.addLayout(btn_row)

    def _on_save(self) -> None:
        key = self._key_input.text().strip().lower()
        label = self._label_input.text().strip()
        env_file = self._env_file_combo.currentText().strip()
        api_host = self._api_host_input.text().strip() or None
        firebase = self._firebase_combo.currentText().strip() or None
        flavor = self._flavor_input.text().strip() or None
        allow_release = self._allow_release_cb.isChecked()
        require_git = self._clean_git_cb.isChecked()

        if not key:
            QMessageBox.warning(self, "Validation Error", "Environment key cannot be empty.")
            return
        if not label:
            label = key.capitalize()
        if not env_file:
            QMessageBox.warning(self, "Validation Error", "Env file path cannot be empty.")
            return

        env = Environment(
            key=key,
            label=label,
            env_file=env_file,
            firebase=firebase,
            flavor=flavor,
            api_host=api_host,
            allow_release_build=allow_release,
            require_clean_git=require_git,
        )

        try:
            self._env_service.add_or_update_environment(env)
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"Failed to save environment:\n{e}")


class EnvironmentSwitchDialog(QDialog):
    """Dialog allowing user to choose, configure, and switch project environments dynamically."""

    def __init__(self, env_service: EnvService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._env_service = env_service
        self._selected_env: Environment | None = None

        self.setWindowTitle("Target Environments")
        self.setMinimumWidth(500)
        self.setStyleSheet(
            """
            QDialog {
                background-color: #1a1b1e;
                color: #e5e7eb;
            }
            """
        )

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(22, 20, 22, 20)
        self._layout.setSpacing(14)

        # Header with Add button
        header_row = QHBoxLayout()
        title_block = QVBoxLayout()
        title = QLabel("Target Environments")
        title.setStyleSheet("font-size: 15px; font-weight: 700; color: #ffffff;")
        title_block.addWidget(title)

        subtitle = QLabel(
            "Switching environments updates .env and Firebase configuration files. "
            "The active environment governs build permissions and release safety."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("font-size: 12px; color: #9ca3af; line-height: 1.4;")
        title_block.addWidget(subtitle)
        header_row.addLayout(title_block, 1)

        add_btn = QPushButton("+ Add Environment")
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #23252a;
                border: 1px solid #3b82f6;
                border-radius: 5px;
                color: #60a5fa;
                font-size: 11px;
                font-weight: 700;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #3b82f6;
                color: #ffffff;
            }
            """
        )
        add_btn.setIcon(get_icon("plus", size=13, color="#ffffff"))
        add_btn.setIconSize(QSize(13, 13))
        add_btn.clicked.connect(self._open_add_dialog)
        header_row.addWidget(add_btn, 0, Qt.AlignmentFlag.AlignTop)

        self._layout.addLayout(header_row)

        # Environments list container
        self._content_widget = QWidget()
        self._content_layout = QVBoxLayout(self._content_widget)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(8)
        self._layout.addWidget(self._content_widget)

        self._button_group = QButtonGroup(self)
        self._env_map: dict[int, Environment] = {}
        self._button_group.idClicked.connect(self._on_env_selected)

        # Action Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #2c2d33;
                border: 1px solid #3d404a;
                border-radius: 5px;
                color: #d1d5db;
                padding: 6px 16px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #383a42;
                color: #ffffff;
            }
            """
        )
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        self._switch_btn = QPushButton("Switch Environment")
        self._switch_btn.setIcon(get_icon("check", size=13, color="#ffffff"))
        self._switch_btn.setIconSize(QSize(13, 13))
        self._switch_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #3b82f6;
                border: 1px solid #2563eb;
                border-radius: 5px;
                color: #ffffff;
                padding: 6px 18px;
                font-weight: 700;
            }
            QPushButton:hover {
                background-color: #2563eb;
            }
            QPushButton:disabled {
                background-color: #242b38;
                color: #4b5563;
                border-color: #1f242e;
            }
            """
        )
        self._switch_btn.clicked.connect(self._on_confirm_switch)
        btn_row.addWidget(self._switch_btn)

        self._layout.addLayout(btn_row)

        self._populate_environments()

    def _populate_environments(self) -> None:
        for btn in self._button_group.buttons():
            self._button_group.removeButton(btn)
        self._env_map.clear()
        while self._content_layout.count():
            child = self._content_layout.takeAt(0)
            if child:
                w = child.widget()
                if w is not None:
                    w.deleteLater()

        envs = self._env_service.load_environments()
        active = self._env_service.active_environment()

        if not envs:
            empty_card = QWidget()
            empty_card.setStyleSheet(
                """
                QWidget {
                    background-color: #212226;
                    border: 1px dashed #35373e;
                    border-radius: 6px;
                }
                """
            )
            empty_layout = QVBoxLayout(empty_card)
            empty_layout.setContentsMargins(18, 16, 18, 16)
            empty_layout.setSpacing(8)

            no_env_lbl = QLabel("No environments configured in .droiddesk/environments.toml")
            no_env_lbl.setStyleSheet("color: #e5e7eb; font-weight: 600; font-size: 13px;")
            empty_layout.addWidget(no_env_lbl)

            desc_lbl = QLabel(
                "Configure project environments to control .env file switching, "
                "API hosts, and release build safety guards."
            )
            desc_lbl.setWordWrap(True)
            desc_lbl.setStyleSheet("color: #9ca3af; font-size: 11px;")
            empty_layout.addWidget(desc_lbl)

            init_btn = QPushButton("+ Configure First Environment")
            init_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            init_btn.setStyleSheet(
                """
                QPushButton {
                    background-color: #23252a;
                    border: 1px solid #3b82f6;
                    border-radius: 6px;
                    color: #60a5fa;
                    padding: 8px 14px;
                    font-weight: 700;
                    font-size: 12px;
                }
                QPushButton:hover {
                    background-color: #3b82f6;
                    color: #ffffff;
                }
                """
            )
            init_btn.clicked.connect(self._open_add_dialog)
            empty_layout.addWidget(init_btn, 0, Qt.AlignmentFlag.AlignLeft)

            self._content_layout.addWidget(empty_card)
            self._switch_btn.setEnabled(False)
            return

        for idx, env in enumerate(envs):
            row_widget = QWidget()
            row_widget.setStyleSheet(
                """
                QWidget {
                    background-color: #23252a;
                    border: 1px solid #33363e;
                    border-radius: 6px;
                }
                QWidget:hover {
                    border-color: #5b9bd5;
                }
                """
            )
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(12, 10, 12, 10)
            row_layout.setSpacing(10)

            radio = QRadioButton()
            radio.setCursor(Qt.CursorShape.PointingHandCursor)
            self._button_group.addButton(radio, idx)
            self._env_map[idx] = env
            row_layout.addWidget(radio)

            info_layout = QVBoxLayout()
            info_layout.setSpacing(2)

            lbl_text = f"{env.label}  ({env.key.upper()})"
            env_title = QLabel(lbl_text)
            env_title.setStyleSheet("font-weight: 700; font-size: 13px; color: #f3f4f6;")
            info_layout.addWidget(env_title)

            details: list[str] = [f"File: {env.env_file}"]
            if env.api_host:
                details.append(f"Host: {env.api_host}")
            if env.allow_release_build:
                details.append("Release permitted")
            else:
                details.append("Release blocked")
            detail_lbl = QLabel(" · ".join(details))
            detail_lbl.setStyleSheet("font-size: 11px; color: #9ca3af;")
            info_layout.addWidget(detail_lbl)

            row_layout.addLayout(info_layout, 1)

            # Risk badge
            color = ENVIRONMENT_RISK_COLORS.get(env.key, "#8b8e94")
            badge = QLabel(env.key.upper())
            badge.setStyleSheet(
                f"background-color: {color}22; "
                f"color: {color}; font-size: 10px; font-weight: 700; "
                f"border: 1px solid {color}; border-radius: 4px; padding: 2px 8px;"
            )
            row_layout.addWidget(badge)

            # Action buttons (Edit & Delete)
            edit_btn = QPushButton("Edit")
            edit_btn.setIcon(get_icon("pencil", size=12, color="#cbd5e1"))
            edit_btn.setIconSize(QSize(12, 12))
            edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            edit_btn.setStyleSheet(
                """
                QPushButton {
                    background-color: #2a2c31;
                    border: 1px solid #3d404a;
                    border-radius: 4px;
                    color: #cbd5e1;
                    font-size: 11px;
                    padding: 4px 8px;
                }
                QPushButton:hover {
                    background-color: #383a42;
                    color: #ffffff;
                }
                """
            )
            edit_btn.clicked.connect(lambda _, target_env=env: self._open_edit_dialog(target_env))
            row_layout.addWidget(edit_btn)

            del_btn = QPushButton("Delete")
            del_btn.setIcon(get_icon("trash-2", size=12, color="#f87171"))
            del_btn.setIconSize(QSize(12, 12))
            del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            del_btn.setStyleSheet(
                """
                QPushButton {
                    background-color: rgba(224, 87, 74, 0.1);
                    border: 1px solid rgba(224, 87, 74, 0.4);
                    border-radius: 4px;
                    color: #f87171;
                    font-size: 11px;
                    padding: 4px 8px;
                }
                QPushButton:hover {
                    background-color: #e0574a;
                    color: #ffffff;
                }
                """
            )
            del_btn.clicked.connect(lambda _, target_env=env: self._on_delete_env(target_env))
            row_layout.addWidget(del_btn)

            if active and active.key == env.key:
                radio.setChecked(True)
                self._selected_env = env

            self._content_layout.addWidget(row_widget)

        self._switch_btn.setEnabled(len(envs) > 0)

    def _open_add_dialog(self) -> None:
        dlg = EnvironmentEditDialog(self._env_service, parent=self)
        if dlg.exec():
            self._populate_environments()

    def _open_edit_dialog(self, env: Environment) -> None:
        dlg = EnvironmentEditDialog(self._env_service, env=env, parent=self)
        if dlg.exec():
            self._populate_environments()

    def _on_delete_env(self, env: Environment) -> None:
        reply = QMessageBox.question(
            self,
            "Delete Environment",
            f"Remove environment '{env.label}' ({env.key})?\n"
            "This will update .droiddesk/environments.toml.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._env_service.delete_environment(env.key)
            self._populate_environments()

    def _on_env_selected(self, btn_id: int) -> None:
        self._selected_env = self._env_map.get(btn_id)

    def _on_confirm_switch(self) -> None:
        if not self._selected_env:
            return
        try:
            self._env_service.switch_to(self._selected_env)
            self.accept()
        except Exception as e:
            QMessageBox.critical(
                self,
                "Environment Switch Error",
                f"Failed to switch environment:\n{e}",
            )
