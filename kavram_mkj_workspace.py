#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Kavram + MKJ area workspace bridge.

Place this file and mkj_pencere.py in the root of a Kavram checkout, then run
`python3 kavram_mkj_workspace.py`. Original editor modules stay unchanged.
"""
from __future__ import annotations

import importlib
import json
import os
import platform
import shlex
import shutil
import sys
import traceback
from pathlib import Path
from typing import Optional

from PyQt5.QtCore import QEvent, QObject, QProcess, QTimer, Qt, QUrl
from PyQt5.QtGui import QColor, QDesktopServices, QIcon, QPainter, QPen, QPixmap, QTextCursor
from PyQt5.QtWidgets import (
    QAction, QApplication, QComboBox, QDockWidget, QHBoxLayout, QLabel,
    QFileDialog, QInputDialog, QLineEdit, QMainWindow, QMessageBox,
    QPlainTextEdit, QPushButton, QStatusBar, QToolBar, QVBoxLayout, QWidget,
)

from mkj_pencere import Area, AreaManager, EditorRegistry, EditorType

APP_NAME = "Kavram — MKJ Workspace"
EDITOR_SPECS = (
    # editor id, visible name, module, class, pass core_window_ref?
    ("Sphere", "SPHERE", "sphere", "SphereWindow", True),
    ("Text", "TEXT", "text_editor", "TextEditorWindow", True),
    ("Drawing", "DRAWING", "Drawing_editor", "DrawingEditorWindow", False),
    ("Sound", "SOUND", "sound_GUI", "SoundEditorWindow", True),
    ("Ai", "AI", "ai_editor", "AiEditorWindow", True),
    ("Media", "MEDIA", "media_editor", "MediaEditor", True),
    ("Rec", "REC", "camera_editor", "CameraRecorderWindow", True),
    ("Copy", "COPY", "copya", "MainWindow", True),
    ("Filter", "FILTER", "filtre", "AudioCleanerUI", False),
    ("Convert", "CONVERTER", "convert", "UniversalConverter", False),
)
DEFAULT_IDS = ["Sphere", "launcher", "launcher", "launcher"]


def _icon(label: str) -> QIcon:
    """Create a themed icon without depending on a desktop icon theme."""
    pix = QPixmap(24, 24)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setPen(QPen(QColor("#b7a16b"), 1.4))
    painter.drawRoundedRect(2, 2, 20, 20, 4, 4)
    painter.drawText(pix.rect(), Qt.AlignCenter, label[:2].upper())
    painter.end()
    return QIcon(pix)


class EditorLoadError(QWidget):
    """Visible fallback instead of killing the entire workspace on import error."""
    def __init__(self, host: "KavramWorkspaceWindow", editor_id: str,
                 title: str, details: str):
        super().__init__()
        layout = QVBoxLayout(self)
        heading = QLabel(f"{title} yüklenemedi")
        heading.setStyleSheet("font-size:18px;font-weight:bold;color:#e0bd72;")
        heading.setWordWrap(True)
        details_label = QLabel(details)
        details_label.setWordWrap(True)
        details_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        details_label.setStyleSheet("color:#c8c8c8;")
        retry = QPushButton("Tekrar dene")
        retry.clicked.connect(lambda: host.retry_editor(editor_id))
        layout.addWidget(heading)
        layout.addWidget(details_label)
        layout.addWidget(retry)
        layout.addStretch(1)
        self.setStyleSheet("background:#202020;color:#ddd;padding:12px;")


class LauncherEditor(QWidget):
    """Lightweight start panel; expensive editors are loaded only when requested."""
    def __init__(self, host: "KavramWorkspaceWindow"):
        super().__init__()
        self.host = host
        layout = QVBoxLayout(self)
        title = QLabel("KAVRAM WORKSPACE")
        title.setStyleSheet("font-size:21px;font-weight:bold;color:#d8bd78;")
        subtitle = QLabel(
            "Üstteki listeden bir editör seçin veya aşağıdaki düğmeleri kullanın.\n"
            "Alan başlığındaki simgeyle editörü değiştirin; kenarları sürükleyerek "
            "alanları yeniden boyutlandırın, köşeleri sürükleyerek bölün/birleştirin."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color:#b9b9b9;")
        layout.addWidget(title)
        layout.addWidget(subtitle)
        for editor_id, visible_name, *_ in EDITOR_SPECS:
            button = QPushButton(visible_name)
            button.setMinimumHeight(32)
            button.clicked.connect(lambda _checked=False, eid=editor_id: host.open_editor(eid))
            layout.addWidget(button)
        layout.addStretch(1)
        self.setStyleSheet(
            "QWidget{background:#202020;color:#ddd;}"
            "QPushButton{background:#303030;color:#ddd;border:1px solid #474747;"
            "border-radius:4px;padding:6px;text-align:left;}"
            "QPushButton:hover{background:#414141;border-color:#b7a16b;}"
        )


class ShortcutPoolPanel(QWidget):
    """Docked, independently managed launcher pool; it does not replace the workspace."""
    def __init__(self, host: "KavramWorkspaceWindow"):
        super().__init__()
        self.host = host
        layout = QVBoxLayout(self)
        intro = QLabel("KISA YOL HAVUZU\nDüğmeler yalnızca aktif çalışma alanındaki editörü değiştirir.")
        intro.setWordWrap(True)
        intro.setStyleSheet("font-weight:bold;color:#d8bd78;padding:6px;")
        layout.addWidget(intro)
        self.builtin_heading = QLabel("YERLEŞİK EDİTÖRLER")
        self.builtin_heading.setStyleSheet("color:#aaa;font-weight:bold;padding:3px 6px;")
        layout.addWidget(self.builtin_heading)
        for editor_id, label, *_ in EDITOR_SPECS:
            button = QPushButton(label)
            button.setMinimumHeight(34)
            button.clicked.connect(lambda _checked=False, eid=editor_id: host.open_editor(eid))
            layout.addWidget(button)
        self.custom_heading = QLabel("ÖZEL KISAYOLLAR")
        self.custom_heading.setStyleSheet("color:#aaa;font-weight:bold;padding:8px 6px 3px;")
        layout.addWidget(self.custom_heading)
        self.custom_container = QVBoxLayout()
        layout.addLayout(self.custom_container)
        custom_actions = QHBoxLayout()
        add_custom = QPushButton("+ Program")
        add_custom.clicked.connect(host.add_custom_shortcut)
        custom_actions.addWidget(add_custom)
        refresh_custom = QPushButton("Yenile")
        refresh_custom.clicked.connect(self.refresh_custom)
        custom_actions.addWidget(refresh_custom)
        layout.addLayout(custom_actions)
        layout.addStretch(1)
        self.refresh_custom()
        self.setStyleSheet(
            "QWidget{background:#202020;color:#ddd;}"
            "QPushButton{background:#303030;color:#ddd;border:1px solid #474747;"
            "border-radius:4px;padding:7px;text-align:left;}"
            "QPushButton:hover{background:#414141;border-color:#b7a16b;}"
        )

    def refresh_custom(self):
        while self.custom_container.count():
            item = self.custom_container.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        entries = [(dict(item), "shortcut") for item in self.host.custom_shortcuts]
        entries.extend(({"name": item["name"], "path": item["executable"]}, "editor") for item in self.host.custom_editors)
        entries.extend(({"name": item["name"], "path": item["executable"]}, "auxiliary") for item in self.host.auxiliary_programs)
        if not entries:
            empty = QLabel("Henüz özel program eklenmedi.")
            empty.setStyleSheet("color:#888;padding:4px;")
            self.custom_container.addWidget(empty)
        for entry, origin in entries:
            row = QHBoxLayout()
            launch = QPushButton(entry.get("name", "Program"))
            launch.setToolTip(entry.get("path", ""))
            launch.clicked.connect(lambda _checked=False, item=dict(entry): self.host.launch_custom_shortcut(item))
            remove = QPushButton("×")
            remove.setFixedWidth(30)
            remove.setToolTip("Bu kısayolu sil")
            if origin == "shortcut":
                remove.clicked.connect(lambda _checked=False, path=entry.get("path", ""): self.host.remove_custom_shortcut(path))
            else:
                remove.clicked.connect(lambda _checked=False, name=entry.get("name", ""): self.host.remove_external_registration(name))
            row.addWidget(launch, 1)
            row.addWidget(remove)
            container = QWidget()
            container.setLayout(row)
            self.custom_container.addWidget(container)


class SystemManagementPanel(QWidget):
    """Separate system-information and diagnostics surface."""
    def __init__(self, host: "KavramWorkspaceWindow"):
        super().__init__()
        self.host = host
        layout = QVBoxLayout(self)
        heading = QLabel("SİSTEM YÖNETİMİ")
        heading.setStyleSheet("font-weight:bold;color:#d8bd78;font-size:15px;")
        layout.addWidget(heading)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setMinimumWidth(280)
        self.details.setMaximumBlockCount(500)
        layout.addWidget(self.details, 1)
        row = QHBoxLayout()
        refresh = QPushButton("Bilgileri yenile")
        refresh.clicked.connect(self.refresh)
        logs = QPushButton("Hata günlüğü")
        logs.clicked.connect(host.open_error_log)
        config = QPushButton("Ayar klasörü")
        config.clicked.connect(lambda: host.open_local_path(host._settings_path.parent))
        row.addWidget(refresh)
        row.addWidget(logs)
        row.addWidget(config)
        layout.addLayout(row)
        self.refresh()
        self.setStyleSheet("QWidget{background:#202020;color:#ddd;} QPushButton{padding:6px;background:#303030;border:1px solid #474747;border-radius:4px;} QPushButton:hover{border-color:#b7a16b;}")

    def refresh(self):
        app = QApplication.instance()
        qt_platform = os.environ.get("QT_QPA_PLATFORM") or os.environ.get("XDG_SESSION_TYPE") or "Qt otomatik"
        root = Path(__file__).resolve().parent
        modules = []
        for module in ("PyQt5", "lupa", "numpy", "cv2", "soundfile", "librosa", "pydub"):
            try:
                import importlib.util
                available = importlib.util.find_spec(module) is not None
            except (ImportError, ValueError):
                available = False
            modules.append(f"{'OK' if available else 'Eksik':5}  {module}")
        text = [
            f"İşletim sistemi : {platform.platform()}",
            f"Python           : {sys.version.split()[0]}",
            f"Qt sürümü        : {getattr(__import__('PyQt5.QtCore', fromlist=['QT_VERSION_STR']), 'QT_VERSION_STR', 'bilinmiyor')}",
            f"Qt platformu     : {qt_platform}",
            f"Çalışma dizini   : {Path.cwd()}",
            f"Kaynak dizini    : {root}",
            f"Pencere alanı    : {len(self.host.workspace.areas)}", 
            "",
            "BAĞIMLILIK KONTROLÜ",
            *modules,
            "",
            "Not: Bu panel bilgi/teşhis sağlar; sistem paketlerini kendiliğinden kurmaz.",
        ]
        self.details.setPlainText("\n".join(text))


class TerminalPanel(QWidget):
    """Non-blocking command runner with a persistent cwd (not a full PTY emulator)."""
    def __init__(self, host: "KavramWorkspaceWindow"):
        super().__init__()
        self.host = host
        self.cwd = str(Path.home())
        self.process = QProcess(self)
        self.process.setWorkingDirectory(self.cwd)
        self.process.readyReadStandardOutput.connect(self._stdout)
        self.process.readyReadStandardError.connect(self._stderr)
        self.process.finished.connect(self._finished)
        self.process.errorOccurred.connect(self._process_error)
        layout = QVBoxLayout(self)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setMaximumBlockCount(4000)
        layout.addWidget(self.output, 1)
        row = QHBoxLayout()
        self.prompt = QLabel("$ ")
        self.command = QLineEdit()
        self.command.setPlaceholderText("Komut yazın (cd, ls, python, git vb.)")
        self.run_button = QPushButton("Çalıştır")
        self.stop_button = QPushButton("Durdur")
        self.stop_button.setEnabled(False)
        self.command.returnPressed.connect(self.run_command)
        self.run_button.clicked.connect(self.run_command)
        self.stop_button.clicked.connect(self.stop_command)
        row.addWidget(self.prompt)
        row.addWidget(self.command, 1)
        row.addWidget(self.run_button)
        row.addWidget(self.stop_button)
        layout.addLayout(row)
        self.output.appendPlainText("KAVRAM TERMİNALİ — komutlar sistem kabuğunda çalıştırılır.\nBaşlangıç dizini: " + self.cwd)
        self.setStyleSheet("QWidget{background:#171717;color:#ddd;} QPlainTextEdit,QLineEdit{background:#101010;color:#ddd;border:1px solid #444;padding:5px;} QPushButton{background:#303030;color:#ddd;border:1px solid #474747;border-radius:4px;padding:5px;} QPushButton:hover{border-color:#b7a16b;}")

    def run_command(self):
        cmd = self.command.text().strip()
        if not cmd or self.process.state() != QProcess.NotRunning:
            return
        self.command.clear()
        self.output.appendPlainText(f"\n{self.cwd} $ {cmd}")
        if cmd in ("clear", "cls"):
            self.output.clear()
            return
        try:
            tokens = shlex.split(cmd)
        except ValueError as exc:
            self.output.appendPlainText(f"Komut ayrıştırma hatası: {exc}")
            return
        if tokens and tokens[0] == "cd" and (len(tokens) <= 2):
            target = tokens[1] if len(tokens) == 2 else str(Path.home())
            target_path = Path(os.path.expandvars(os.path.expanduser(target)))
            if not target_path.is_absolute():
                target_path = Path(self.cwd) / target_path
            try:
                target_path = target_path.resolve(strict=True)
                if not target_path.is_dir():
                    raise NotADirectoryError(str(target_path))
                self.cwd = str(target_path)
                self.output.appendPlainText(self.cwd)
            except OSError as exc:
                self.output.appendPlainText(f"cd: {exc}")
            return
        shell = "/bin/sh"
        self.process.setWorkingDirectory(self.cwd)
        self.process.start(shell, ["-lc", cmd])
        self.run_button.setEnabled(False)
        self.stop_button.setEnabled(True)

    def _stdout(self):
        data = bytes(self.process.readAllStandardOutput()).decode("utf-8", errors="replace")
        if data:
            self.output.moveCursor(QTextCursor.End)
            self.output.insertPlainText(data)
            self.output.ensureCursorVisible()

    def _stderr(self):
        data = bytes(self.process.readAllStandardError()).decode("utf-8", errors="replace")
        if data:
            self.output.moveCursor(QTextCursor.End)
            self.output.insertPlainText(data)
            self.output.ensureCursorVisible()

    def _finished(self, exit_code, exit_status):
        self._stdout()
        self._stderr()
        self.output.appendPlainText(f"\n[çıkış kodu: {exit_code}]")
        self.run_button.setEnabled(True)
        self.stop_button.setEnabled(False)

    def _process_error(self, error):
        if self.process.state() == QProcess.NotRunning:
            self.output.appendPlainText(f"Terminal süreç hatası: {self.process.errorString()}")
            self.run_button.setEnabled(True)
            self.stop_button.setEnabled(False)

    def stop_command(self):
        if self.process.state() != QProcess.NotRunning:
            self.process.terminate()
            QTimer.singleShot(1200, lambda: self.process.kill() if self.process.state() != QProcess.NotRunning else None)

    def shutdown(self):
        if self.process.state() != QProcess.NotRunning:
            self.process.kill()


class WorkspaceStackProxy:
    """Small compatibility surface for legacy editors expecting core.stack."""
    def __init__(self, host: "KavramWorkspaceWindow"):
        self.host = host

    def currentWidget(self):
        area = self.host.current_area()
        return area.widget if area else None

    def setCurrentWidget(self, widget):
        if widget is None:
            return
        area = self.host.area_for_widget(widget)
        if area:
            self.host._active_area = area
            return
        editor_id = self.host.editor_id_for_widget(widget)
        if editor_id:
            self.host.open_editor(editor_id)

    def addWidget(self, widget):
        editor_id = self.host.editor_id_for_widget(widget)
        if editor_id:
            et = self.host.registry.get(editor_id)
            if et is not None:
                et.instance = widget
                self.host.instantiated_editors[editor_id] = widget
        return self.host.editor_id_for_widget(widget) or -1

    def removeWidget(self, widget):
        area = self.host.area_for_widget(widget)
        if area is None:
            return
        editor_id = area.editor_id
        area.set_editor("launcher")
        et = self.host.registry.get(editor_id) if editor_id else None
        if et is not None and et.unique:
            et.instance = None
            et.owner = None
        if editor_id:
            self.host.instantiated_editors.pop(editor_id, None)

    def indexOf(self, widget):
        for index, et in enumerate(self.host.registry.ordered()):
            if et.instance is widget:
                return index
        return -1

    def currentIndex(self):
        widget = self.currentWidget()
        return self.indexOf(widget)

    def setCurrentIndex(self, index):
        entries = self.host.registry.ordered()
        if 0 <= index < len(entries):
            self.host.open_editor(entries[index].id)

    def count(self):
        return sum(1 for area in self.host.workspace.areas if area.widget is not None)

    def widget(self, index):
        areas = self.host.workspace.areas
        return areas[index].widget if 0 <= index < len(areas) else None


class _AreaFocusFilter(QObject):
    def __init__(self, host: "KavramWorkspaceWindow"):
        super().__init__(host)
        self.host = host

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.MouseButtonPress, QEvent.FocusIn):
            obj = watched
            while obj is not None:
                if isinstance(obj, Area):
                    self.host._active_area = obj
                    break
                obj = obj.parentWidget() if isinstance(obj, QWidget) else None
        return False


class KavramWorkspaceWindow(QMainWindow):
    """Workspace host with lazy, singleton instances of Kavram's 10 built-in editors."""
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1280, 800)
        self.setMinimumSize(760, 480)
        self.setStyleSheet(
            "QMainWindow,QWidget{background:#1b1b1b;color:#ddd;}"
            "QToolBar{background:#292929;border:0;spacing:6px;padding:4px;}"
            "QPushButton,QComboBox{background:#303030;color:#ddd;border:1px solid #4a4a4a;"
            "border-radius:4px;padding:5px;}"
            "QPushButton:hover{border-color:#b7a16b;}"
            "QComboBox QAbstractItemView{background:#262626;color:#ddd;selection-background-color:#4c4c4c;}"
        )

        self.mru_editor_names = [spec[0] for spec in EDITOR_SPECS[:8]]
        self.fixed_base_names = ["Filter", "Convert"]
        self.editors_order = [spec[0] for spec in EDITOR_SPECS]
        self.editor_map = {eid: f"{module}.{klass}" for eid, _, module, klass, _ in EDITOR_SPECS}
        self.custom_editors = []
        self.auxiliary_programs = []
        self.instantiated_editors = {}
        self.spawned_external_processes = []
        # Editors use this compatibility proxy for the original QStackedWidget API.
        self.stack = WorkspaceStackProxy(self)
        self.filter_window_instance = None
        self.convert_window_instance = None
        self.media_filter_connection_active = False
        self.is_filtering_in_progress = False
        self.force_close = False
        self.spawned_external_processes = []
        self._active_area = None
        self._loading_errors = {}

        registry = EditorRegistry(fallback="launcher")
        registry.register(EditorType("launcher", "Başlangıç", _icon("K"),
                                     lambda host: LauncherEditor(host), unique=False))
        for eid, label, _module, _klass, _uses_core in EDITOR_SPECS:
            registry.register(EditorType(eid, label, _icon(label),
                                         lambda host, name=eid: host.create_editor(name),
                                         unique=True))
        self.registry = registry
        self.workspace = AreaManager(registry, self)
        self.workspace.default_ids = list(DEFAULT_IDS)
        self.setCentralWidget(self.workspace)
        self.workspace.build_default(DEFAULT_IDS)
        self._focus_filter = _AreaFocusFilter(self)
        self.workspace.layoutChanged.connect(self._on_layout_changed)
        self._on_layout_changed()

        config_dir = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "kavram"
        self._settings_path = config_dir / "mkj_workspace.json"
        self._shortcuts_path = config_dir / "mkj_shortcuts.json"
        self.custom_shortcuts = self._read_custom_shortcuts()
        self.load_custom_editors()
        self.load_auxiliary_programs()
        self.rebuild_editors_order()
        self._restore_layout()

        self._build_toolbar()
        self._build_docks()
        self._build_menus()
        bar = QStatusBar(self)
        bar.showMessage("X11 / Wayland: Qt'nin otomatik platform seçimi kullanılıyor")
        self.setStatusBar(bar)

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(250)
        self._save_timer.timeout.connect(self._save_layout)

    def _build_toolbar(self):
        # Workspace controls are intentionally isolated from editor shortcuts and system tools.
        workspace_bar = QToolBar("Çalışma Alanı", self)
        workspace_bar.setObjectName("workspaceControls")
        workspace_bar.setMovable(False)
        self.addToolBar(Qt.TopToolBarArea, workspace_bar)
        workspace_bar.addWidget(QLabel(" ÇALIŞMA ALANI  "))
        vertical_button = QPushButton("Dikey Böl")
        vertical_button.clicked.connect(lambda: self._split_active("v"))
        horizontal_button = QPushButton("Yatay Böl")
        horizontal_button.clicked.connect(lambda: self._split_active("h"))
        maximize_button = QPushButton("Alanı Büyüt / Geri Al")
        maximize_button.clicked.connect(lambda: self.workspace.toggle_maximize(self.current_area()))
        reset_button = QPushButton("Düzeni Sıfırla")
        reset_button.clicked.connect(self.workspace.reset_layout)
        for button in (vertical_button, horizontal_button, maximize_button, reset_button):
            workspace_bar.addWidget(button)

        editor_bar = QToolBar("Editör Seçimi", self)
        editor_bar.setObjectName("editorSelection")
        editor_bar.setMovable(False)
        self.addToolBar(Qt.TopToolBarArea, editor_bar)
        editor_bar.addWidget(QLabel(" EDİTÖR  "))
        self.editor_combo = QComboBox()
        for eid, label, *_ in EDITOR_SPECS:
            self.editor_combo.addItem(label, eid)
        editor_bar.addWidget(self.editor_combo)
        open_button = QPushButton("Aktif Alanda Aç")
        open_button.clicked.connect(lambda: self.open_editor(self.editor_combo.currentData()))
        editor_bar.addWidget(open_button)

        system_bar = QToolBar("Sistem Yönetimi", self)
        system_bar.setObjectName("systemManagementControls")
        system_bar.setMovable(False)
        self.addToolBar(Qt.TopToolBarArea, system_bar)
        system_bar.addWidget(QLabel(" SİSTEM  "))
        self.system_toggle_button = QPushButton("Sistem Yönetimi")
        self.system_toggle_button.clicked.connect(lambda: self.system_dock.setVisible(not self.system_dock.isVisible()))
        self.terminal_toggle_button = QPushButton("Terminal")
        self.terminal_toggle_button.clicked.connect(lambda: self.terminal_dock.setVisible(not self.terminal_dock.isVisible()))
        self.shortcuts_toggle_button = QPushButton("Kısayol Havuzu")
        self.shortcuts_toggle_button.clicked.connect(lambda: self.shortcuts_dock.setVisible(not self.shortcuts_dock.isVisible()))
        for button in (self.system_toggle_button, self.terminal_toggle_button, self.shortcuts_toggle_button):
            system_bar.addWidget(button)

    def _build_docks(self):
        self.shortcuts_dock = QDockWidget("Kısayol Havuzu", self)
        self.shortcuts_dock.setObjectName("shortcutPoolDock")
        self.shortcuts_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.shortcuts_panel = ShortcutPoolPanel(self)
        self.shortcuts_dock.setWidget(self.shortcuts_panel)
        self.addDockWidget(Qt.RightDockWidgetArea, self.shortcuts_dock)

        self.system_dock = QDockWidget("Sistem Yönetimi", self)
        self.system_dock.setObjectName("systemManagementDock")
        self.system_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea | Qt.BottomDockWidgetArea)
        self.system_panel = SystemManagementPanel(self)
        self.system_dock.setWidget(self.system_panel)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.system_dock)
        self.system_dock.hide()

        self.terminal_dock = QDockWidget("Terminal", self)
        self.terminal_dock.setObjectName("systemTerminalDock")
        self.terminal_dock.setAllowedAreas(Qt.BottomDockWidgetArea | Qt.TopDockWidgetArea)
        self.terminal_panel = TerminalPanel(self)
        self.terminal_dock.setWidget(self.terminal_panel)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.terminal_dock)
        self.terminal_dock.hide()

    def _build_menus(self):
        file_menu = self.menuBar().addMenu("Dosya")
        save_action = QAction("Pencere düzenini kaydet", self)
        save_action.triggered.connect(self._save_layout)
        file_menu.addAction(save_action)
        file_menu.addSeparator()
        close_action = QAction("Çıkış", self)
        close_action.triggered.connect(self.close)
        file_menu.addAction(close_action)

        view_menu = self.menuBar().addMenu("Paneller")
        view_menu.addAction(self.shortcuts_dock.toggleViewAction())
        view_menu.addAction(self.system_dock.toggleViewAction())
        view_menu.addAction(self.terminal_dock.toggleViewAction())

        system_menu = self.menuBar().addMenu("Sistem Yönetimi")
        terminal_action = QAction("Terminali göster/gizle", self)
        terminal_action.triggered.connect(lambda: self.terminal_dock.setVisible(not self.terminal_dock.isVisible()))
        system_menu.addAction(terminal_action)
        status_action = QAction("Sistem bilgilerini yenile", self)
        status_action.triggered.connect(self.system_panel.refresh)
        system_menu.addAction(status_action)
        log_action = QAction("Hata günlüğünü aç", self)
        log_action.triggered.connect(self.open_error_log)
        system_menu.addAction(log_action)
        source_action = QAction("Kaynak dizinini aç", self)
        source_action.triggered.connect(lambda: self.open_local_path(Path(__file__).resolve().parent))
        system_menu.addAction(source_action)

        editor_menu = self.menuBar().addMenu("Editörler")
        for eid, label, *_ in EDITOR_SPECS:
            action = QAction(label, self)
            action.triggered.connect(lambda _checked=False, name=eid: self.open_editor(name))
            editor_menu.addAction(action)

        areas_menu = self.menuBar().addMenu("Pencere")
        current_menu = areas_menu.addMenu("Aktif alanı böl")
        vertical_action = QAction("Dikey böl", self)
        vertical_action.triggered.connect(lambda: self._split_active("v"))
        horizontal_action = QAction("Yatay böl", self)
        horizontal_action.triggered.connect(lambda: self._split_active("h"))
        current_menu.addAction(vertical_action)
        current_menu.addAction(horizontal_action)
        max_action = QAction("Aktif alanı büyüt / geri al (Ctrl+Space)", self)
        max_action.triggered.connect(lambda: self.workspace.toggle_maximize(self.current_area()))
        areas_menu.addAction(max_action)
        areas_menu.addAction("Pencere düzenini sıfırla", self.workspace.reset_layout)

    def _on_layout_changed(self):
        for area in list(self.workspace.areas):
            for target in [area, *area.findChildren(QWidget)]:
                if target.property("mkjFocusFilterInstalled"):
                    continue
                target.installEventFilter(self._focus_filter)
                target.setProperty("mkjFocusFilterInstalled", True)
        self._save_timer.start() if hasattr(self, "_save_timer") else None

    def _restore_layout(self):
        try:
            if self._settings_path.is_file():
                with self._settings_path.open("r", encoding="utf-8") as stream:
                    data = json.load(stream)
                self.workspace.load_dict(data)
                self._on_layout_changed()
        except Exception as exc:
            print(f"[workspace] Kayıtlı düzen yüklenemedi, varsayılan düzen korunuyor: {exc}")

    def _save_layout(self):
        try:
            self._settings_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self._settings_path.with_suffix(".json.tmp")
            with temporary.open("w", encoding="utf-8") as stream:
                json.dump(self.workspace.to_dict(), stream, ensure_ascii=False, indent=2)
            os.replace(temporary, self._settings_path)
        except Exception as exc:
            print(f"[workspace] Düzen kaydedilemedi: {exc}")

    def _split_active(self, orientation: str):
        area = self.current_area()
        if not area:
            return
        rect = area.rect
        pos = (rect[0] + rect[2]) / 2 if orientation == "v" else (rect[1] + rect[3]) / 2
        self.workspace.split(area, orientation, pos)

    def current_area(self) -> Optional[Area]:
        if self._active_area in self.workspace.areas and self._active_area.isVisible():
            return self._active_area
        under_cursor = self.workspace.area_under_cursor()
        if under_cursor is not None:
            self._active_area = under_cursor
            return under_cursor
        visible = [area for area in self.workspace.areas if area.isVisible()]
        self._active_area = visible[0] if visible else (self.workspace.areas[0] if self.workspace.areas else None)
        return self._active_area

    def area_for_widget(self, widget) -> Optional[Area]:
        for area in self.workspace.areas:
            if area.widget is widget:
                return area
        return None

    def editor_id_for_widget(self, widget) -> Optional[str]:
        for editor_id, et in self.registry._types.items():
            if et.instance is widget:
                return editor_id
        for editor_id, instance in self.instantiated_editors.items():
            if instance is widget:
                return editor_id
        return None

    def create_editor(self, editor_id: str) -> QWidget:
        if editor_id == "launcher":
            return LauncherEditor(self)
        spec = next((item for item in EDITOR_SPECS if item[0] == editor_id), None)
        if spec is None:
            return EditorLoadError(self, editor_id, editor_id, "Editör kaydı bulunamadı.")
        _eid, label, module_name, class_name, uses_core = spec
        try:
            module = importlib.import_module(module_name)
            editor_class = getattr(module, class_name)
            widget = editor_class(core_window_ref=self) if uses_core else editor_class()
            if not isinstance(widget, QWidget):
                raise TypeError(f"{module_name}.{class_name} QWidget döndürmedi.")
            # Ensure QMainWindow/QDialog subclasses behave as an embedded area widget.
            widget.setWindowFlags(Qt.Widget)
            self.instantiated_editors[editor_id] = widget
            if editor_id == "Filter":
                self.filter_window_instance = widget
            elif editor_id == "Convert":
                self.convert_window_instance = widget
            self._loading_errors.pop(editor_id, None)
            return widget
        except Exception as exc:
            detail = f"{module_name}.{class_name}\n\n{type(exc).__name__}: {exc}\n\n"
            detail += "Kavram'ın kaynak dosyalarının bu dosyayla aynı dizinde olduğunu ve editör bağımlılıklarının kurulu olduğunu kontrol edin."
            self._loading_errors[editor_id] = detail
            traceback.print_exc()
            return EditorLoadError(self, editor_id, label, detail)

    def retry_editor(self, editor_id: str):
        et = self.registry.get(editor_id)
        if et is None:
            return
        old_widget = et.instance
        owner = et.owner
        if owner is not None and owner in self.workspace.areas:
            owner.set_editor("launcher")
        if old_widget is not None:
            self.instantiated_editors.pop(editor_id, None)
            old_widget.deleteLater()
        et.instance = None
        et.owner = None
        self.open_editor(editor_id)

    def open_editor(self, editor_id: str):
        if not editor_id or self.registry.get(editor_id) is None:
            return
        area = self.current_area()
        if area is None:
            return
        try:
            area.set_editor(editor_id)
            self._active_area = area
            et = self.registry.get(editor_id)
            if et and et.instance is not None:
                self.setWindowTitle(f"{APP_NAME} — {et.name}")
            if hasattr(self, "_save_timer"):
                self._save_timer.start()
        except Exception as exc:
            traceback.print_exc()
            self._show_error("Editör açılamadı", f"{editor_id}: {exc}")

    # ---- Minimal compatibility methods used by original Kavram editors ----
    def switchToEditor(self, editor_name, close_current=False):
        aliases = {"Sphere": "Sphere", "Text": "Text", "Drawing": "Drawing", "Sound": "Sound",
                   "Ai": "Ai", "Media": "Media", "Rec": "Rec", "Copy": "Copy",
                   "Filter": "Filter", "Convert": "Convert"}
        by_label = {label.upper(): eid for eid, label, *_ in EDITOR_SPECS}
        key = str(editor_name).strip()
        target = aliases.get(key, by_label.get(key.upper(), key))
        if self.registry.get(target) is not None:
            self.open_editor(target)
            return
        for item in (*self.custom_editors, *self.auxiliary_programs):
            if item.get("name") == key:
                self.launch_custom_shortcut({"name": item["name"], "path": item["executable"]})
                return
        self._show_error("Editör bulunamadı", f"Kayıtlı editör veya kısayol bulunamadı: {key}")

    def safe_switch_to_editor(self, editor_name, close_current=False):
        return self.switchToEditor(editor_name, close_current)

    def ensureEditorInstantiated(self, editor_name):
        et = self.registry.get(editor_name)
        if et is not None and et.instance is None:
            self.open_editor(editor_name)
        return et.instance if et is not None else None

    def get_custom_editors_dir(self):
        path = Path(__file__).resolve().parent / "veri" / "custom_editors"
        path.mkdir(parents=True, exist_ok=True)
        return str(path)

    def get_custom_editors_json_path(self):
        return str(Path(self.get_custom_editors_dir()) / "custom_editors.json")

    def get_editor_path_file(self, editor_name):
        return str(Path(self.get_custom_editors_dir()) / str(editor_name) / "path.txt")

    def _scan_external_programs(self, directory):
        result = []
        root = Path(directory)
        if not root.is_dir():
            return result
        for folder in sorted(root.iterdir()):
            if not folder.is_dir():
                continue
            path_file = folder / "path.txt"
            try:
                target = path_file.read_text(encoding="utf-8").strip()
            except OSError:
                continue
            if target and Path(target).expanduser().exists():
                result.append({"name": folder.name, "executable": str(Path(target).expanduser())})
        return result

    def load_custom_editors(self):
        self.custom_editors = self._scan_external_programs(self.get_custom_editors_dir())
        return self.custom_editors

    def load_auxiliary_programs(self):
        root = Path(__file__).resolve().parent / "veri" / "auxiliary_programs"
        self.auxiliary_programs = self._scan_external_programs(root)
        return self.auxiliary_programs

    def rebuild_editors_order(self):
        builtins = [item[0] for item in EDITOR_SPECS]
        self.editors_order = builtins + [item["name"] for item in self.custom_editors] + [
            item["name"] for item in self.auxiliary_programs if item["name"] not in {x["name"] for x in self.custom_editors}
        ]

    def remove_external_registration(self, editor_name):
        removed = self.remove_editor_by_name(editor_name)
        self.load_custom_editors()
        self.load_auxiliary_programs()
        self.rebuild_editors_order()
        if hasattr(self, "shortcuts_panel"):
            self.shortcuts_panel.refresh_custom()
        return removed

    def remove_editor_by_name(self, editor_name):
        """Remove Kavram's path registration without deleting the application file itself."""
        removed = False
        for entries in (self.custom_editors, self.auxiliary_programs):
            match = next((item for item in entries if item.get("name") == editor_name), None)
            if match is None:
                continue
            entries.remove(match)
            registration = Path(self.get_editor_path_file(editor_name)) if entries is self.custom_editors else (
                Path(__file__).resolve().parent / "veri" / "auxiliary_programs" / str(editor_name) / "path.txt"
            )
            try:
                registration.unlink(missing_ok=True)
                registration.parent.rmdir()
            except OSError:
                pass
            removed = True
        if removed:
            self.rebuild_editors_order()
        return removed

    def raise_process_window(self, pid, executable_path=None):
        # Do not call xdotool/wmctrl. On Wayland, focus is controlled by the compositor.
        return False

    def _update_mru(self, editor_name):
        if editor_name in self.editors_order:
            self.editors_order.remove(editor_name)
            self.editors_order.insert(0, editor_name)

    def safe_call(self, func, *args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            self.handle_uncaught_editor_exception(type(exc), exc, exc.__traceback__)
            return None

    def handle_uncaught_editor_exception(self, exctype, value, tb):
        traceback.print_exception(exctype, value, tb)
        try:
            log_dir = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state"))) / "kavram-workspace"
            log_dir.mkdir(parents=True, exist_ok=True)
            with (log_dir / "errors.log").open("a", encoding="utf-8") as stream:
                traceback.print_exception(exctype, value, tb, file=stream)
        except Exception:
            pass
        self._show_error("Editör hatası", f"{exctype.__name__}: {value}\n\nAyrıntılar hata günlüğüne yazıldı.")

    def _show_error(self, title, details):
        QMessageBox.critical(self, title, details)

    def show_error_message(self, text):
        self._show_error("Hata", str(text))

    def set_media_filter_connection(self, active):
        self.media_filter_connection_active = bool(active)

    def is_media_filter_connected(self):
        return self.media_filter_connection_active

    def get_filter_window(self):
        return self.filter_window_instance

    def process_audio_with_filter(self, audio_path, callback=None):
        if self.is_filtering_in_progress:
            if callback:
                callback(False, None, "Filtreleme zaten devam ediyor")
            return False
        try:
            if self.filter_window_instance is None:
                et = self.registry.get("Filter")
                if et is None:
                    raise RuntimeError("Filter editörü kayıtlı değil")
                self.filter_window_instance = et.widget(self)
                self.instantiated_editors["Filter"] = self.filter_window_instance
            processor = getattr(self.filter_window_instance, "process_audio_background", None)
            if not callable(processor):
                raise RuntimeError("Filter editöründe process_audio_background bulunamadı")
            self.is_filtering_in_progress = True

            def finished(success, output_path, message):
                self.is_filtering_in_progress = False
                if callback:
                    callback(success, output_path, message)

            started = processor(audio_path, finished)
            if not started:
                self.is_filtering_in_progress = False
            return started
        except Exception as exc:
            self.is_filtering_in_progress = False
            if callback:
                callback(False, None, str(exc))
            else:
                self._show_error("Filter hatası", str(exc))
            return False

    def loadEditorFile(self, editor_name, file_path):
        """Best-effort open-file routing; the editor's own loader remains authoritative."""
        route = {
            "Sphere": ("load_path", (file_path,)),
            "Text": ("load_file_content", (file_path,)),
            "Drawing": ("load_image_from_path", (file_path,)),
            "Sound": ("load_files_from_path", ([file_path],)),
            "Ai": ("openFiles_from_path", ([file_path],)),
            "Media": ("load_file", (file_path,)),
            "Rec": ("load_file", (file_path,)),
            "Copy": ("load_copya", (file_path,)),
        }
        if editor_name not in route:
            self.open_editor(editor_name)
            return False
        self.open_editor(editor_name)
        QTimer.singleShot(0, lambda: self._call_editor_loader(editor_name, *route[editor_name], file_path=file_path))
        return True

    def _call_editor_loader(self, editor_name, method_name, args, file_path=None):
        widget = self.instantiated_editors.get(editor_name)
        candidates = {
            "Sphere": ("load_path", "load_archive", "load_kitap", "open_archive", "load_file"),
            "Text": ("load_file_content", "load_file", "open_file"),
            "Drawing": ("load_image_from_path", "load_file", "open_file"),
            "Sound": ("load_files_from_path", "load_file", "open_file"),
            "Ai": ("openFiles_from_path", "load_files_from_path", "open_file"),
            "Media": ("load_file", "open_file"),
            "Rec": ("load_file", "open_file"),
            "Copy": ("load_copya", "load_file", "open_file"),
        }.get(editor_name, (method_name,))
        method = None
        for candidate in (method_name, *candidates):
            found = getattr(widget, candidate, None) if widget else None
            if callable(found):
                method = found
                break
        if method is not None:
            self.safe_call(method, *args)
        else:
            self._show_error("Dosya açılamadı", f"{editor_name} editöründe dosya yükleyicisi bulunamadı.\n{file_path or ''}")

    def load_editor_file(self, editor_name, file_path):
        return self.loadEditorFile(editor_name, file_path)

    def _read_custom_shortcuts(self):
        try:
            data = json.loads(self._shortcuts_path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return [item for item in data if isinstance(item, dict) and item.get("name") and item.get("path")]
        except FileNotFoundError:
            return []
        except Exception as exc:
            print(f"[workspace] Özel kısayollar yüklenemedi: {exc}")
        return []

    def _save_custom_shortcuts(self):
        try:
            self._shortcuts_path.parent.mkdir(parents=True, exist_ok=True)
            temp = self._shortcuts_path.with_suffix(".json.tmp")
            temp.write_text(json.dumps(self.custom_shortcuts, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(temp, self._shortcuts_path)
        except Exception as exc:
            self._show_error("Kısayollar kaydedilemedi", str(exc))

    def add_custom_shortcut(self):
        name, ok = QInputDialog.getText(self, "Program Kısayolu", "Kısayol adı:")
        if not ok or not name.strip():
            return
        path, _filter = QFileDialog.getOpenFileName(self, "Çalıştırılabilir dosya veya betik seç", str(Path.home()), "Tüm dosyalar (*)")
        if not path:
            return
        path_obj = Path(path).expanduser().resolve()
        if not path_obj.is_file():
            self._show_error("Geçersiz yol", "Seçilen yol bir dosya değil.")
            return
        normalized = str(path_obj)
        if any(item.get("path") == normalized for item in self.custom_shortcuts):
            self._show_error("Kısayol zaten var", "Bu dosya kısayol havuzuna eklenmiş.")
            return
        self.custom_shortcuts.append({"name": name.strip(), "path": normalized})
        self._save_custom_shortcuts()
        self.shortcuts_panel.refresh_custom()

    def remove_custom_shortcut(self, path):
        self.custom_shortcuts = [item for item in self.custom_shortcuts if item.get("path") != path]
        self._save_custom_shortcuts()
        if hasattr(self, "shortcuts_panel"):
            self.shortcuts_panel.refresh_custom()

    def launch_custom_shortcut(self, entry):
        path = str(entry.get("path", ""))
        if not path or not Path(path).is_file():
            self._show_error("Program bulunamadı", path or "Kısayol yolu boş.")
            return
        try:
            if path.endswith(".py"):
                program, args = sys.executable, [path]
            elif path.endswith(".sh"):
                program, args = "/bin/sh", [path]
            else:
                program, args = path, []
            process = QProcess(self)
            process.setProgram(program)
            process.setArguments(args)
            process.setWorkingDirectory(str(Path(path).parent))
            process.setProcessChannelMode(QProcess.ForwardedChannels)
            if not hasattr(self, "_external_processes"):
                self._external_processes = []
            self._external_processes.append(process)
            process.finished.connect(lambda *_args, proc=process: self._forget_process(proc))
            process.errorOccurred.connect(lambda _error, proc=process, item_path=path: self._external_launch_error(proc, item_path))
            process.start()
        except Exception as exc:
            self._show_error("Program başlatılamadı", str(exc))

    def _external_launch_error(self, process, path):
        if process.state() == QProcess.NotRunning:
            detail = process.errorString()
            self._forget_process(process)
            QTimer.singleShot(0, lambda msg=detail, target=path: self._show_error("Program başlatılamadı", f"{target}\n{msg}"))

    def _forget_process(self, process):
        if hasattr(self, "_external_processes") and process in self._external_processes:
            self._external_processes.remove(process)
        process.deleteLater()

    def open_local_path(self, path):
        try:
            Path(path).mkdir(parents=True, exist_ok=True) if not Path(path).exists() else None
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(path).resolve())))
        except Exception as exc:
            self._show_error("Konum açılamadı", str(exc))

    def open_error_log(self):
        log_dir = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state"))) / "kavram-workspace"
        log_path = log_dir / "errors.log"
        if not log_path.exists():
            try:
                log_dir.mkdir(parents=True, exist_ok=True)
                log_path.write_text("Kavram MKJ çalışma alanı hata günlüğü\nHenüz kaydedilmiş hata yok.\n", encoding="utf-8")
            except OSError as exc:
                self._show_error("Hata günlüğü oluşturulamadı", str(exc))
                return
        self.open_local_path(log_path)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_S and event.modifiers() & (Qt.ControlModifier | Qt.MetaModifier):
            active = self.current_area()
            if active and active.editor_id and active.editor_id != "Sphere":
                self.open_editor("Sphere")
                event.accept()
                return
        super().keyPressEvent(event)

    def closeEvent(self, event):
        recording = []
        for name, widget in list(self.instantiated_editors.items()):
            if getattr(widget, "recording", False) or getattr(widget, "is_recording_mode", False) or getattr(widget, "is_recording", False):
                recording.append(name)
        if recording:
            answer = QMessageBox.question(
                self, "Kayıt sürüyor",
                "Şu editörlerde kayıt etkin: " + ", ".join(recording) +
                "\n\nYine de çıkılsın mı? Kayıtların düzgün sonlandırıldığına emin olun.",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                event.ignore()
                return
        self._save_layout()
        if hasattr(self, "terminal_panel"):
            self.terminal_panel.shutdown()
        event.accept()


_MAIN_WINDOW = None

def _exception_hook(exc_type, exc, tb):
    if _MAIN_WINDOW is not None:
        try:
            _MAIN_WINDOW.handle_uncaught_editor_exception(exc_type, exc, tb)
            return
        except Exception:
            pass
    traceback.print_exception(exc_type, exc, tb)


def main(argv=None):
    argv = list(sys.argv if argv is None else argv)
    # Respect QT_QPA_PLATFORM if the user explicitly set it. Do not force xcb;
    # leaving it unset lets Qt choose X11 or Wayland based on the session/plugins.
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("Kavram")
    sys.excepthook = _exception_hook
    global _MAIN_WINDOW
    window = KavramWorkspaceWindow()
    _MAIN_WINDOW = window
    window.showMaximized()
    if len(argv) > 1 and os.path.isfile(argv[1]):
        ext = Path(argv[1]).suffix.lower()
        route = {
            ".txt": "Text", ".html": "Text", ".htm": "Text", ".txr": "Text",
            ".png": "Drawing", ".jpg": "Drawing", ".jpeg": "Drawing", ".webp": "Drawing",
            ".wav": "Sound", ".mp3": "Sound", ".flac": "Sound", ".ogg": "Sound",
            ".mp4": "Media", ".mkv": "Media", ".mov": "Media", ".media": "Media",
            ".copya": "Copy", ".rec": "Rec",
        }
        window.loadEditorFile(route.get(ext, "Sphere"), argv[1])
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
