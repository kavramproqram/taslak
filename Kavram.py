#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
KAVRAM v3 – Sistem Çekirdeği

Optimize edilmiş çekirdek:
- Panel
- PanelHeader
- EmptySlotWidget
- PanelSlot
- Toast
- KavramCore

Performans hedefleri:
- Gereksiz modül yeniden yüklemelerini engellemek
- QWidget yaşam döngüsünü daha kontrollü yönetmek
- Dosya yollarında pathlib kullanmak
- GUI event'lerinde gereksiz allocation azaltmak
- Drag/drop işlemlerini hafifletmek
- Exception kullanımını sınırlandırmak
- Sabit lookup yapılarını cache'lemek
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Callable

from PyQt5.QtCore import (
    QObject,
    QMimeData,
    QTimer,
    Qt,
    pyqtSignal,
)
from PyQt5.QtGui import QDrag
from PyQt5.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ortam import EnvironmentStore


# ----------------------------------------------------------------------
# Sabitler
# ----------------------------------------------------------------------

PANEL_MIME = "application/x-kavram-panel"

PANEL_IDS = (1, 2, 3, 4)

PANEL_NAMES = {
    1: "Birincil",
    2: "İkincil",
    3: "Üçüncül",
    4: "Numper",
}

MODE_NAMES = {
    1: "Sphere",
}

NOMPER_MODULE_NAME = "kavram_nomper"


# ======================================================================
# SignalHub
# ======================================================================

class SignalHub(QObject):
    file_saved = pyqtSignal(str)
    file_opened = pyqtSignal(str)
    editor_focus_requested = pyqtSignal(str, int)
    command_executed = pyqtSignal(str)
    console_output = pyqtSignal(str)
    build_started = pyqtSignal(str)
    build_finished = pyqtSignal(int)
    status_message = pyqtSignal(str)
    mode_changed = pyqtSignal(int)
    environment_changed = pyqtSignal(str)
    sphere_changed = pyqtSignal(str)
    toast_message = pyqtSignal(str)


# ======================================================================
# PanelHeader
# ======================================================================

class PanelHeader(QWidget):

    swap_requested = pyqtSignal(int, int)
    close_requested = pyqtSignal(int)
    focus_requested = pyqtSignal(int)

    DRAG_THRESHOLD = 18
    MAX_PREVIEW_WIDTH = 480

    def __init__(
        self,
        title: str,
        accent: str,
        panel_id_ref: Callable[[], int | None],
        parent: QWidget | None = None,
    ):
        super().__init__(parent)

        self.setProperty("panelHeader", True)

        self._panel_ref = panel_id_ref
        self._press_pos = None
        self._drag_disabled = False

        self.setAcceptDrops(True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 4, 4)
        layout.setSpacing(4)

        self.header_layout = layout

        # --------------------------------------------------------------
        # Grip
        # --------------------------------------------------------------

        self.grip = QLabel("⠿")
        self.grip.setObjectName("panelGrip")
        self.grip.setFixedWidth(16)
        self.grip.setAlignment(Qt.AlignCenter)
        self.grip.setCursor(Qt.OpenHandCursor)
        self.grip.setToolTip(
            "Sol tıkla tut, başka panelin üstüne bırak → "
            "yer değiştir / taşı"
        )

        # Mouse event'lerinin doğrudan header'a ulaşmasını sağlar.
        self.grip.setAttribute(
            Qt.WA_TransparentForMouseEvents,
            True,
        )

        layout.addWidget(self.grip)

        # --------------------------------------------------------------
        # Başlık
        # --------------------------------------------------------------

        self.title_label = QLabel(title)
        self.title_label.setProperty("title", True)
        self.title_label.setProperty("accent", accent)

        self.title_label.setAttribute(
            Qt.WA_TransparentForMouseEvents,
            True,
        )

        layout.addWidget(self.title_label, 1)

        # --------------------------------------------------------------
        # Kapat
        # --------------------------------------------------------------

        self.close_btn = QPushButton("✕")
        self.close_btn.setObjectName("panelCloseBtn")
        self.close_btn.setFixedSize(22, 22)
        self.close_btn.setCursor(Qt.PointingHandCursor)
        self.close_btn.setToolTip("Kapat")
        self.close_btn.clicked.connect(self._emit_close)

        layout.addWidget(
            self.close_btn,
            0,
            Qt.AlignVCenter,
        )

    # ------------------------------------------------------------------
    # Close
    # ------------------------------------------------------------------

    def _emit_close(self) -> None:
        parent = self.parentWidget()

        if parent is not None:
            request_close = getattr(
                parent,
                "request_close",
                None,
            )

            if callable(request_close):
                request_close()
                return

        panel_id = self._panel_ref()

        self.close_requested.emit(
            panel_id if panel_id is not None else -1
        )

    # ------------------------------------------------------------------
    # Mouse
    # ------------------------------------------------------------------

    def mousePressEvent(self, event) -> None:
        if event.button() not in (
            Qt.LeftButton,
            Qt.RightButton,
        ):
            super().mousePressEvent(event)
            return

        self._press_pos = event.pos()

        panel_id = self._panel_ref()

        if panel_id is not None:
            self.focus_requested.emit(panel_id)

        event.accept()

    def mouseMoveEvent(self, event) -> None:

        if self._drag_disabled:
            super().mouseMoveEvent(event)
            return

        if self._press_pos is None:
            super().mouseMoveEvent(event)
            return

        if not (
            event.buttons()
            & (Qt.LeftButton | Qt.RightButton)
        ):
            super().mouseMoveEvent(event)
            return

        distance = (
            event.pos() - self._press_pos
        ).manhattanLength()

        if distance < self.DRAG_THRESHOLD:
            super().mouseMoveEvent(event)
            return

        source_id = self._panel_ref()

        if source_id is None:
            self._press_pos = None
            return

        drag = QDrag(self)

        mime = QMimeData()

        # Küçük integer verisini doğrudan bytes olarak taşıyoruz.
        mime.setData(
            PANEL_MIME,
            str(source_id).encode("ascii"),
        )

        drag.setMimeData(mime)

        # --------------------------------------------------------------
        # Drag preview
        #
        # grab() pahalı olabileceği için yalnızca gerçek drag başladığında
        # bir kere çağrılıyor.
        # --------------------------------------------------------------

        panel_widget = self.parentWidget()

        if panel_widget is not None:
            try:
                pixmap = panel_widget.grab()

                if pixmap.width() > self.MAX_PREVIEW_WIDTH:
                    pixmap = pixmap.scaledToWidth(
                        self.MAX_PREVIEW_WIDTH,
                        Qt.FastTransformation,
                    )

                drag.setPixmap(pixmap)
                drag.setHotSpot(self._press_pos)

            except RuntimeError:
                # QWidget yaşam döngüsü drag sırasında değişmiş olabilir.
                pass

        self._press_pos = None

        try:
            drag.exec_(Qt.MoveAction)
        except RuntimeError:
            pass

    # ------------------------------------------------------------------
    # Drag / Drop
    # ------------------------------------------------------------------

    def dragEnterEvent(self, event) -> None:
        if (
            not self._drag_disabled
            and event.mimeData().hasFormat(PANEL_MIME)
        ):
            event.acceptProposedAction()
            return

        event.ignore()

    def dragMoveEvent(self, event) -> None:
        if (
            not self._drag_disabled
            and event.mimeData().hasFormat(PANEL_MIME)
        ):
            event.acceptProposedAction()
            return

        event.ignore()

    def dropEvent(self, event) -> None:

        if self._drag_disabled:
            event.ignore()
            return

        mime = event.mimeData()

        if not mime.hasFormat(PANEL_MIME):
            event.ignore()
            return

        try:
            source_id = int(
                bytes(
                    mime.data(PANEL_MIME)
                ).decode("ascii")
            )
        except (ValueError, UnicodeDecodeError):
            event.ignore()
            return

        destination_id = self._panel_ref()

        if (
            destination_id is not None
            and source_id != destination_id
        ):
            self.swap_requested.emit(
                source_id,
                destination_id,
            )

        event.acceptProposedAction()


# ======================================================================
# Panel
# ======================================================================

class Panel(QFrame):

    close_requested = pyqtSignal(int)
    swap_requested = pyqtSignal(int, int)
    focus_requested = pyqtSignal(int)

    def __init__(
        self,
        title: str,
        accent: str,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)

        self.setProperty("panel", True)
        self.setProperty("focused", False)

        self._panel_id: int | None = None

        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(0)

        self.header = PanelHeader(
            title,
            accent,
            self._get_pid,
            self,
        )

        self.header.swap_requested.connect(
            self.swap_requested
        )

        self.header.focus_requested.connect(
            self.focus_requested
        )

        self.body.addWidget(self.header)

        # Geriye dönük API uyumluluğu.
        self.title_label = self.header.title_label
        self.close_btn = self.header.close_btn
        self.grip = self.header.grip

    def _get_pid(self) -> int | None:
        return self._panel_id

    def set_panel_id(self, panel_id: int) -> None:
        self._panel_id = panel_id

    def request_close(self) -> None:
        self.close_requested.emit(
            self._panel_id
            if self._panel_id is not None
            else -1
        )

    def set_focused(self, focused: bool) -> None:

        focused = bool(focused)

        if self.property("focused") == focused:
            return

        self.setProperty("focused", focused)

        # --------------------------------------------------------------
        # Stil yeniden hesaplaması yalnızca gerçekten durum değişince
        # yapılıyor.
        # --------------------------------------------------------------

        for widget in (
            self,
            self.header,
            self.header.title_label,
        ):
            style = widget.style()
            style.unpolish(widget)
            style.polish(widget)

        self.update()


# ======================================================================
# EmptySlotWidget
# ======================================================================

class EmptySlotWidget(QWidget):

    restore_requested = pyqtSignal(str, int)
    file_dropped = pyqtSignal(str, str)

    def __init__(
        self,
        position: str,
        available_provider=None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)

        self.position = position

        # Geriye dönük uyumluluk.
        self.available_provider = available_provider

        self.setAcceptDrops(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            20,
            20,
            20,
            20,
        )
        layout.setSpacing(0)

        layout.addStretch(1)

        self.btn = QPushButton("＋")
        self.btn.setObjectName(
            "emptySlotPlusBtn"
        )
        self.btn.setCursor(
            Qt.PointingHandCursor
        )
        self.btn.setFixedSize(88, 88)
        self.btn.setToolTip(
            "Dosya / uygulama seç "
            "(sistem dosya yöneticisi)"
        )

        self.btn.clicked.connect(
            self._browse
        )

        layout.addWidget(
            self.btn,
            0,
            Qt.AlignCenter,
        )

        layout.addStretch(1)

    # ------------------------------------------------------------------

    def _browse(self) -> None:

        start_dir = str(
            Path.home()
        )

        path, _ = QFileDialog.getOpenFileName(
            self,
            "Dosya veya Uygulama Seç",
            start_dir,
            "Tüm Dosyalar (*)",
        )

        if path:
            self.file_dropped.emit(
                self.position,
                path,
            )

    # ------------------------------------------------------------------

    def dragEnterEvent(self, event) -> None:

        mime = event.mimeData()

        if mime.hasFormat(PANEL_MIME):
            event.acceptProposedAction()
            return

        if mime.hasUrls():
            if any(
                url.isLocalFile()
                for url in mime.urls()
            ):
                event.acceptProposedAction()
                return

        event.ignore()

    def dragMoveEvent(self, event) -> None:

        mime = event.mimeData()

        if (
            mime.hasFormat(PANEL_MIME)
            or mime.hasUrls()
        ):
            event.acceptProposedAction()
            return

        event.ignore()

    def dropEvent(self, event) -> None:

        mime = event.mimeData()

        if mime.hasFormat(PANEL_MIME):

            try:
                source_id = int(
                    bytes(
                        mime.data(PANEL_MIME)
                    ).decode("ascii")
                )
            except (ValueError, UnicodeDecodeError):
                event.ignore()
                return

            self.restore_requested.emit(
                self.position,
                source_id,
            )

            event.acceptProposedAction()
            return

        if mime.hasUrls():

            for url in mime.urls():

                if not url.isLocalFile():
                    continue

                path = url.toLocalFile()

                if not path:
                    continue

                self.file_dropped.emit(
                    self.position,
                    path,
                )

                event.acceptProposedAction()
                return

        event.ignore()


# ======================================================================
# PanelSlot
# ======================================================================

class PanelSlot(QWidget):

    restore_requested = pyqtSignal(str, int)
    swap_requested = pyqtSignal(int, int)
    focus_requested = pyqtSignal(int)
    close_requested = pyqtSignal(int)
    file_dropped = pyqtSignal(str, str)

    def __init__(
        self,
        position: str,
        available_provider=None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)

        self.position = position

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.stack = QStackedWidget(self)

        layout.addWidget(self.stack)

        self.placeholder = EmptySlotWidget(
            position,
            available_provider,
            self,
        )

        self.placeholder.restore_requested.connect(
            self.restore_requested
        )

        self.placeholder.file_dropped.connect(
            self.file_dropped
        )

        self.stack.addWidget(
            self.placeholder
        )

        self.current_panel: Panel | None = None

    # ------------------------------------------------------------------

    def set_panel(self, panel: Panel | None) -> None:

        if self.current_panel is panel:

            if panel is not None:
                self.stack.setCurrentWidget(panel)

            return

        old_panel = self.current_panel

        if old_panel is not None:

            self.stack.removeWidget(
                old_panel
            )

            old_panel.setParent(None)

            # Signal bağlantılarını kontrollü biçimde kaldır.
            try:
                old_panel.close_requested.disconnect(
                    self._on_panel_close
                )
            except (TypeError, RuntimeError):
                pass

            try:
                old_panel.swap_requested.disconnect(
                    self._on_panel_swap
                )
            except (TypeError, RuntimeError):
                pass

            try:
                old_panel.focus_requested.disconnect(
                    self.focus_requested
                )
            except (TypeError, RuntimeError):
                pass

        self.current_panel = panel

        if panel is None:

            self.stack.setCurrentWidget(
                self.placeholder
            )

            return

        self.stack.addWidget(panel)
        self.stack.setCurrentWidget(panel)

        panel.close_requested.connect(
            self._on_panel_close
        )

        panel.swap_requested.connect(
            self._on_panel_swap
        )

        panel.focus_requested.connect(
            self.focus_requested
        )

    # ------------------------------------------------------------------

    def clear_panel(self) -> None:
        self.set_panel(None)

    def has_panel(self) -> bool:
        return self.current_panel is not None

    # ------------------------------------------------------------------

    def _on_panel_close(self, panel_id: int) -> None:

        self.clear_panel()

        self.close_requested.emit(
            panel_id
        )

    def _on_panel_swap(
        self,
        source_id: int,
        destination_id: int,
    ) -> None:

        self.focus_requested.emit(
            source_id
        )

        self.swap_requested.emit(
            source_id,
            destination_id,
        )


# ======================================================================
# Toast
# ======================================================================

class Toast(QLabel):

    def __init__(
        self,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)

        self.setObjectName("toast")
        self.setAlignment(Qt.AlignCenter)

        self.setAttribute(
            Qt.WA_TransparentForMouseEvents,
            True,
        )

        self.hide()

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(
            self.hide
        )

    # ------------------------------------------------------------------

    def show_message(
        self,
        text: str,
        msec: int = 1400,
    ) -> None:

        self.setText(text)
        self.adjustSize()

        self._reposition()

        self.show()
        self.raise_()

        self._timer.start(
            max(0, int(msec))
        )

    # ------------------------------------------------------------------

    def _reposition(self) -> None:

        parent = self.parentWidget()

        if parent is None:
            return

        self.adjustSize()

        x = max(
            0,
            (
                parent.width()
                - self.width()
            ) // 2,
        )

        y = max(
            0,
            parent.height()
            - self.height()
            - 60,
        )

        self.move(x, y)


# ======================================================================
# KavramCore
# ======================================================================

class KavramCore:

    PANEL_NAMES = PANEL_NAMES
    MODE_NAMES = MODE_NAMES

    def __init__(
        self,
        main_window,
    ):
        self.main_window = main_window

        self.base_dir = Path(
            __file__
        ).resolve().parent

        self.workspace_dir = (
            self.base_dir / "workspace"
        )

        self.workspace_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.signals = SignalHub()

        self.env_store = EnvironmentStore(
            str(self.base_dir)
        )

        self.panels: dict[int, QWidget] = {}

        self.current_mode = 1

        # --------------------------------------------------------------
        # Dynamic import cache
        #
        # nomper.py her Sphere geçişinde tekrar execute edilmeyecek.
        # --------------------------------------------------------------

        self._module_cache = {}

        self._create_panels(
            self.current_mode
        )

    # ------------------------------------------------------------------
    # Dynamic module loader
    # ------------------------------------------------------------------

    def _load_module(
        self,
        folder: str,
        filename: str,
        module_name: str,
    ):

        cached = self._module_cache.get(
            module_name
        )

        if cached is not None:
            return cached

        path = (
            self.base_dir / folder / filename
            if folder
            else self.base_dir / filename
        )

        if not path.is_file():
            raise ImportError(
                f"Modül bulunamadı: {path}"
            )

        spec = (
            importlib.util
            .spec_from_file_location(
                module_name,
                str(path),
            )
        )

        if spec is None or spec.loader is None:
            raise ImportError(
                f"Modül yüklenemedi: {path}"
            )

        module = (
            importlib.util.module_from_spec(
                spec
            )
        )

        # Python import cache.
        sys.modules[module_name] = module

        spec.loader.exec_module(module)

        self._module_cache[
            module_name
        ] = module

        return module

    # ------------------------------------------------------------------
    # Panel lifecycle
    # ------------------------------------------------------------------

    def _detach_all(self) -> None:

        for panel in self.panels.values():

            if panel is None:
                continue

            # QWidget parent'tan çıkarılıyor.
            panel.setParent(None)

        self.panels.clear()

    # ------------------------------------------------------------------

    def _create_panels(
        self,
        mode: int,
    ) -> None:

        self._detach_all()

        self.current_mode = mode

        nomper_mod = self._load_module(
            "",
            "nomper.py",
            NOMPER_MODULE_NAME,
        )

        env_name = self.env_store.current

        env_folder = (
            self.env_store.folder_for(
                env_name
            )
        )

        env_cfg = (
            self.env_store.get(
                env_name
            )
            or {}
        )

        saved_panels = (
            env_cfg.get("panels")
            or {}
        )

        workspace_slot_cls = (
            nomper_mod.WorkspaceSlot
        )

        panels: dict[int, QWidget] = {}

        # --------------------------------------------------------------
        # Workspace panelleri
        #
        # Sabit panel sayısı nedeniyle bu bölüm O(1)'dir.
        # --------------------------------------------------------------

        for slot_id in (1, 2, 3):

            saved_name = saved_panels.get(
                str(slot_id)
            )

            slot = workspace_slot_cls(
                env_name,
                slot_id,
                env_folder,
                saved_name,
            )

            # Closure bug'ını önlemek için slot_id ve env_name
            # lokal parametre olarak yakalanıyor.
            slot.file_dropped.connect(
                lambda sid, filename,
                       environment=env_name:
                    self.env_store.set_panel(
                        environment,
                        sid,
                        filename,
                    )
            )

            panels[slot_id] = slot

        # --------------------------------------------------------------
        # Numper
        # --------------------------------------------------------------

        numper = nomper_mod.NomperPanel(
            self.signals
        )

        numper.set_core(self)
        numper.set_main_window(
            self.main_window
        )
        numper.set_env_store(
            self.env_store
        )
        numper.set_mode(mode)

        panels[4] = numper

        self.panels = panels

    # ------------------------------------------------------------------
    # Mode
    # ------------------------------------------------------------------

    def switch_mode(
        self,
        mode: int,
    ) -> None:

        mode = int(mode)

        if self.current_mode == mode:
            return

        self.current_mode = mode

        self.signals.mode_changed.emit(
            mode
        )

        callback = getattr(
            self.main_window,
            "on_mode_changed",
            None,
        )

        if callable(callback):
            callback(mode)

    def cycle_mode(self) -> None:
        self.switch_mode(1)

    # ------------------------------------------------------------------
    # Environment / Sphere
    # ------------------------------------------------------------------

    def switch_environment(
        self,
        name: str,
    ) -> None:

        if not self.env_store.set_current(
            name
        ):
            return

        self._create_panels(
            self.current_mode
        )

        self.signals.environment_changed.emit(
            name
        )

        self.signals.sphere_changed.emit(
            name
        )

        callback = getattr(
            self.main_window,
            "on_environment_changed",
            None,
        )

        if callable(callback):
            callback(name)

    # ------------------------------------------------------------------
    # Panel API
    # ------------------------------------------------------------------

    def get_panel(
        self,
        panel_id: int,
    ):
        return self.panels.get(
            int(panel_id)
        )

    def get_panels(self):
        # Geriye dönük davranışı koruyor:
        # çağıran tarafın sözlüğü değiştirmesi çekirdeği bozamaz.
        return self.panels.copy()

    def panel_name(
        self,
        panel_id: int,
    ) -> str:

        return self.PANEL_NAMES.get(
            int(panel_id),
            f"Panel {panel_id}",
        )