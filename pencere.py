#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KAVRAM v3 – Pencere Yöneticisi (pencere.py)
- Sürükle-bırak panel yer değiştirme aktif (görsel önizlemeli)
- Numper dahil tüm paneller sürüklenebilir
- X ile kapanan panelin yeri boş kalır (+ butonuyla veya sürükle-bırak ile doldurulur)
- Ctrl+1/2/3/4 ve Numpad 1/2/3/4 → paneli tam ekran göster
- Ctrl+Q / Numpad 0 → Sphere menüsü
"""
import os, sys, json

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QSplitter, QStackedWidget, QStatusBar, QMessageBox
)
from PyQt5.QtCore import Qt, QEvent, QTimer
from PyQt5.QtGui import QFont, QIcon, QCursor

from Kavram import KavramCore, PanelSlot, Toast
import kyol


FALLBACK_STYLE = """
QMainWindow { background-color: #000000; }
QWidget {
    color: #FFFFFF;
    font-family: "Inter","Segoe UI","DejaVu Sans",sans-serif;
    font-size: 12px;
    background-color: transparent;
}

QFrame[panel="true"] {
    background-color: #1A1A1A;
    border: 1px solid #2A2A2A;
    border-radius: 10px;
    margin: 3px;
}
QFrame[panel="true"][focused="true"] {
    border: 1px solid #007ACC;
}

QWidget[panelHeader="true"] {
    background-color: #141414;
    border-top-left-radius: 9px;
    border-top-right-radius: 9px;
    border-bottom: 1px solid #2A2A2A;
}
QFrame[panel="true"][focused="true"] > QWidget[panelHeader="true"] {
    border-bottom: 1px solid #007ACC;
}

QLabel[title="true"] {
    background: transparent;
    border: none;
    padding: 6px 10px;
    font-weight: 600;
    color: #FFFFFF;
}
QLabel#panelGrip {
    color: #666666;
    font-size: 14px;
}
QLabel#panelGrip:hover { color: #CCCCCC; }

QLabel[accent="mint"]   { color: #FFFFFF; }
QLabel[accent="green"]  { color: #F5F5F5; }
QLabel[accent="pink"]   { color: #E0E0E0; }
QLabel[accent="purple"] { color: #CCCCCC; }
QLabel[accent="dim"]    { color: #888888; }

QPushButton#panelCloseBtn {
    background: transparent;
    color: #888888;
    border: 1px solid transparent;
    border-radius: 5px;
    font-weight: bold;
    font-size: 11px;
    padding: 0;
}
QPushButton#panelCloseBtn:hover {
    background-color: #3A1A1A;
    border: 1px solid #663333;
    color: #FF8888;
}

QPushButton#sphereBtn {
    background-color: #2A2A2A;
    color: #FFFFFF;
    border: 1px solid #3A3A3A;
    border-radius: 6px;
    padding: 4px 12px;
    font-weight: 600;
    font-size: 11px;
    text-align: left;
}
QPushButton#sphereBtn:hover {
    background-color: #3A3A3A;
    border-color: #007ACC;
}
QPushButton#sphereBtn:pressed {
    background-color: #007ACC;
}

QPushButton#emptySlotPlusBtn {
    background-color: #1E1E1E;
    color: #888888;
    border: 2px dashed #3A3A3A;
    border-radius: 44px;
    font-size: 40px;
    font-weight: 300;
    padding: 0;
}
QPushButton#emptySlotPlusBtn:hover {
    background-color: #262626;
    border: 2px dashed #007ACC;
    color: #FFFFFF;
}
QPushButton#emptySlotPlusBtn:pressed {
    background-color: #007ACC;
    color: #FFFFFF;
    border-color: #FFFFFF;
}

QLabel#toast {
    background-color: rgba(20,20,20,235);
    color: #FFFFFF;
    border: 1px solid #007ACC;
    border-radius: 8px;
    padding: 10px 22px;
    font-size: 13px;
    font-weight: 600;
}

QPlainTextEdit, QTextEdit {
    background-color: #0d0d0d;
    color: #FFFFFF;
    border: 1px solid #2A2A2A;
    border-radius: 6px;
    padding: 4px;
    selection-background-color: #007ACC;
    selection-color: #FFFFFF;
    font-family: "JetBrains Mono","DejaVu Sans Mono",monospace;
}

QLineEdit {
    background-color: #1A1A1A;
    color: #FFFFFF;
    border: 1px solid #2A2A2A;
    border-radius: 6px;
    padding: 5px;
}
QLineEdit:focus { border: 1px solid #007ACC; }

QPushButton {
    background-color: #2A2A2A;
    color: #FFFFFF;
    border: 1px solid #3A3A3A;
    border-radius: 6px;
    padding: 6px 10px;
}
QPushButton:hover { background-color: #3A3A3A; border-color: #007ACC; }
QPushButton:pressed { background-color: #007ACC; }
QPushButton:disabled { color: #555555; background-color: #1A1A1A; }

QListWidget {
    background-color: #1A1A1A;
    color: #FFFFFF;
    border: 1px solid #2A2A2A;
    border-radius: 6px;
}
QListWidget::item { padding: 4px; }
QListWidget::item:selected { background-color: #007ACC; color: #FFFFFF; }
QListWidget::item:hover { background-color: #2A2A2A; }

QSplitter::handle { background-color: #0d0d0d; }
QSplitter::handle:horizontal { width: 3px; }
QSplitter::handle:vertical { height: 3px; }
QSplitter::handle:hover { background-color: #007ACC; }

QStatusBar {
    background-color: #141414;
    color: #CCCCCC;
    border-top: 1px solid #2A2A2A;
}

QScrollBar:vertical { background: #141414; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: #3A3A3A; border-radius: 5px; min-height: 24px; }
QScrollBar::handle:vertical:hover { background: #007ACC; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { background: #141414; height: 10px; margin: 0; }
QScrollBar::handle:horizontal { background: #3A3A3A; border-radius: 5px; min-width: 24px; }
QScrollBar::handle:horizontal:hover { background: #007ACC; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

QMenu {
    background-color: #1A1A1A;
    color: #FFFFFF;
    border: 1px solid #3A3A3A;
    padding: 4px;
    border-radius: 6px;
}
QMenu::item { padding: 5px 20px; border-radius: 4px; }
QMenu::item:selected { background-color: #007ACC; color: #FFFFFF; }
QMenu::separator { height: 1px; background: #2A2A2A; margin: 4px 8px; }

QPushButton#numpadBtn {
    background-color: #222222;
    color: #FFFFFF;
    border: 1px solid #3A3A3A;
    border-radius: 10px;
    padding: 6px;
    font-weight: bold;
}
QPushButton#numpadBtn:hover { background-color: #2A2A2A; border-color: #007ACC; }
QPushButton#numpadBtn:pressed { background-color: #007ACC; }
QPushButton#numpadBtn[active="true"] {
    background-color: #007ACC;
    color: #FFFFFF;
    border: 1px solid #FFFFFF;
}

QComboBox {
    background-color: #2A2A2A;
    color: #FFFFFF;
    border: 1px solid #3A3A3A;
    border-radius: 6px;
    padding: 5px 10px;
    min-width: 60px;
    font-weight: 600;
}
QComboBox:hover { background-color: #3A3A3A; border-color: #007ACC; }
QComboBox QAbstractItemView {
    background-color: #1A1A1A;
    color: #FFFFFF;
    selection-background-color: #007ACC;
    border: 1px solid #3A3A3A;
    padding: 4px;
    outline: none;
}
"""


class MainWindow(QMainWindow):
    NAMES = {1: "Birincil", 2: "İkincil", 3: "Üçüncül", 4: "Numper"}
    POSITIONS = ("left_top", "left_bottom", "right_top", "right_bottom")

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Kavram")
        self.setMinimumSize(1000, 680)

        base_dir = os.path.dirname(os.path.abspath(__file__))
        icon_path = os.path.join(base_dir, "ikon", "Kavram.png")
        if os.path.isfile(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.core = KavramCore(self)
        self.base_dir = self.core.base_dir
        self.workspace_dir = self.core.workspace_dir
        self.signals = self.core.signals

        self.panels = {}
        self.slots = {}
        self.slot_map = {p: i + 1 for i, p in enumerate(self.POSITIONS)}
        self.hidden_panels = set()
        self.focused_pid = None

        self.saved_main_sizes  = None
        self.saved_left_sizes  = None
        self.saved_right_sizes = None

        self.full_panel = None
        self.last_full = 1
        self._pending_full_panel = None

        self.stack = QStackedWidget()
        self.split_page = QWidget()
        self.full_page = QWidget()
        self.stack.addWidget(self.split_page)
        self.stack.addWidget(self.full_page)
        self.setCentralWidget(self.stack)

        self.split_layout = QVBoxLayout(self.split_page)
        self.split_layout.setContentsMargins(6, 6, 6, 6)
        self.split_layout.setSpacing(0)

        self.full_layout = QVBoxLayout(self.full_page)
        self.full_layout.setContentsMargins(6, 6, 6, 6)
        self.full_layout.setSpacing(0)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self.toast = Toast(self)

        self.refresh_panel_refs()
        self._load_env_state()
        self.load_config()
        self.build_split_layout()

        self.signals.environment_changed.connect(self._on_env_signal)
        self.signals.toast_message.connect(self._show_toast)

        QApplication.instance().installEventFilter(self)

        if self._pending_full_panel is not None and self._pending_full_panel in self.panels:
            fp = self._pending_full_panel
            self._pending_full_panel = None
            QTimer.singleShot(150, lambda p=fp: self.show_full(p))

        self.say("Hazır – Sphere: " + self.core.env_store.current)

    # ==================================================================
    def _show_toast(self, msg):
        self.toast.show_message(msg)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.toast.isVisible():
            self.toast._reposition()

    # ==================================================================
    def refresh_panel_refs(self):
        panels = self.core.get_panels()
        self.panels = panels
        self.nomper = None
        for pid, p in panels.items():
            try:
                p.set_panel_id(pid)
                if getattr(p, "is_nomper", False) or pid == 4:
                    self.nomper = p
                try:
                    p.focus_requested.disconnect()
                except Exception:
                    pass
                p.focus_requested.connect(self._on_focus_panel)
            except Exception:
                pass

    def _on_focus_panel(self, pid):
        if self.focused_pid == pid:
            return
        self.focused_pid = pid
        for p_pid, p in self.panels.items():
            try:
                p.set_focused(p_pid == pid)
            except Exception:
                pass

    # ==================================================================
    def _load_env_state(self):
        name = self.core.env_store.current
        layout = self.core.env_store.get_layout(name)
        sizes = self.core.env_store.get_sizes(name)

        valid = set(self.panels.keys())
        used = set()
        new_map = {}
        for pos in self.POSITIONS:
            pid = layout.get(pos)
            if pid in valid and pid not in used:
                new_map[pos] = pid; used.add(pid)
            else:
                new_map[pos] = None
        remaining = [v for v in sorted(valid) if v not in used]
        for pos in self.POSITIONS:
            if new_map[pos] is None and remaining:
                new_map[pos] = remaining.pop(0)
        for pos in self.POSITIONS:
            if new_map[pos] is None:
                new_map[pos] = next(iter(valid)) if valid else 1
        self.slot_map = new_map

        self.saved_main_sizes  = sizes.get("main")
        self.saved_left_sizes  = sizes.get("left")
        self.saved_right_sizes = sizes.get("right")

        self.hidden_panels = set()
        self.focused_pid = None

    def _save_layout_to_env(self):
        name = self.core.env_store.current
        self.core.env_store.set_layout(name, self.slot_map)

    def _save_sizes_to_env(self):
        name = self.core.env_store.current
        self.core.env_store.set_sizes(
            name, self.saved_main_sizes,
            self.saved_left_sizes, self.saved_right_sizes)

    # ==================================================================
    def on_mode_changed(self, mode):
        if self.full_panel is not None:
            self.full_panel = None
            self.stack.setCurrentWidget(self.split_page)
        self.refresh_panel_refs()
        self._load_env_state()
        self.build_split_layout()

    def _on_env_signal(self, name):
        if self.full_panel is not None:
            self.full_panel = None
            self.stack.setCurrentWidget(self.split_page)
        self.refresh_panel_refs()
        self._load_env_state()
        self.build_split_layout()
        self.say(f"Sphere: {name}")
        self._show_toast(f"🌐 {name}")

    def on_environment_changed(self, name):
        pass

    # ==================================================================
    def _on_panel_close(self, pid):
        if pid not in self.panels:
            return
        if pid == 4:
            self._show_toast("Numper kapatılamaz")
            return

        try:
            env_name = self.core.env_store.current
            self.core.env_store.delete_panel_record(env_name, pid)
        except Exception:
            pass

        self.hidden_panels.add(pid)
        self._save_layout_to_env()
        self.say(f"Panel {pid} kapatıldı – yer boş bırakıldı")
        self._show_toast(f"Panel kapatıldı: {self.NAMES.get(pid, pid)}")

    # ==================================================================
    def _on_empty_slot_file_dropped(self, position, file_path):
        pid = self.slot_map.get(position)
        if pid is None or pid not in self.panels or pid == 4:
            pid = None
            for p_id, p in self.panels.items():
                if p_id == 4:
                    continue
                if hasattr(p, "load_file") and p_id in self.hidden_panels:
                    pid = p_id
                    break
        if pid is None or pid not in self.panels or pid == 4:
            return

        widget = self.panels.get(pid)
        if not hasattr(widget, "load_file"):
            return
        slot = self.slots.get(position)
        if slot is None:
            return

        if slot.has_panel():
            old = slot.current_panel
            old_pid = getattr(old, "_panel_id", None)
            if old_pid is not None and old_pid != pid:
                self.hidden_panels.add(old_pid)

        slot.set_panel(widget)
        self.hidden_panels.discard(pid)
        self.slot_map[position] = pid

        try:
            widget.load_file(file_path)
        except Exception as e:
            self.say(f"Dosya yüklenemedi: {e}")

        self._save_layout_to_env()
        self.say(f"Dosya yüklendi: {os.path.basename(file_path)}")
        self._show_toast(f"📄 {os.path.basename(file_path)}")

    # ==================================================================
    def _on_restore_requested(self, position, pid):
        """Sürüklenen paneli hedef yuvaya taşı (kaynak yuvayı temizle, gerekirse takas et)."""
        if pid not in self.panels or position not in self.slots:
            return
        panel = self.panels[pid]
        target_slot = self.slots[position]

        # Panel şu an hangi slotta?
        src_pos = None
        for pos, slot in self.slots.items():
            if slot.current_panel is panel:
                src_pos = pos
                break

        target_panel = target_slot.current_panel if target_slot.has_panel() else None
        if target_panel is panel:
            return

        # Hedefi ve kaynağı temizle
        target_slot.clear_panel()
        if src_pos is not None:
            self.slots[src_pos].clear_panel()
            self.slot_map[src_pos] = None

        # Hedefte başka panel varsa ya takas et ya gizle
        if target_panel is not None:
            target_pid = getattr(target_panel, "_panel_id", None)
            if target_pid is not None and src_pos is not None:
                self.slots[src_pos].set_panel(target_panel)
                self.slot_map[src_pos] = target_pid
                self.hidden_panels.discard(target_pid)
            elif target_pid is not None:
                self.hidden_panels.add(target_pid)

        target_slot.set_panel(panel)
        self.slot_map[position] = pid
        self.hidden_panels.discard(pid)
        self._save_layout_to_env()
        self.say(f"Panel taşındı: {self.NAMES.get(pid, pid)}")

    def _available_panels(self):
        result = []
        for pid in sorted(self.panels.keys()):
            if pid == 4:
                continue
            if pid not in self.hidden_panels:
                continue
            p = self.panels.get(pid)
            has_content = getattr(p, 'current_file', None) is not None
            if has_content:
                result.append((pid, self.NAMES.get(pid, f"Panel {pid}")))
        return result

    # ==================================================================
    def _on_panel_swap(self, src, dst):
        if src == dst:
            return
        src_pos = dst_pos = None
        for pos, slot in self.slots.items():
            pid = getattr(slot.current_panel, "_panel_id", None) if slot.current_panel else None
            if pid == src: src_pos = pos
            if pid == dst: dst_pos = pos
        for pos, pid in self.slot_map.items():
            if pid == src and src_pos is None: src_pos = pos
            if pid == dst and dst_pos is None: dst_pos = pos
        if src_pos is None or dst_pos is None or src_pos == dst_pos:
            return

        src_panel = self.panels.get(src)
        dst_panel = self.panels.get(dst)
        self.slots[src_pos].clear_panel()
        self.slots[dst_pos].clear_panel()
        if dst_panel is not None:
            self.slots[src_pos].set_panel(dst_panel)
        if src_panel is not None:
            self.slots[dst_pos].set_panel(src_panel)
        self.slot_map[src_pos] = dst
        self.slot_map[dst_pos] = src
        self.hidden_panels.discard(src); self.hidden_panels.discard(dst)
        self._save_layout_to_env()
        self.say(f"Paneller {src} ↔ {dst} yer değiştirdi")
        self._show_toast(f"↔ {self.NAMES.get(src, src)} ↔ {self.NAMES.get(dst, dst)}")

    # ==================================================================
    def open_sphere_menu_at_cursor(self):
        if self.nomper is None:
            return
        try:
            self.nomper.open_sphere_menu(QCursor.pos())
        except Exception:
            pass

    # ==================================================================
    def config_path(self):
        return os.path.join(self.base_dir, "config.json")

    def load_config(self):
        p = self.config_path()
        if not os.path.exists(p):
            return
        try:
            with open(p, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            w = cfg.get("window", {})
            if all(k in w for k in ("x", "y", "width", "height")):
                self.setGeometry(w["x"], w["y"], w["width"], w["height"])
            if w.get("fullscreen"):
                QTimer.singleShot(0, self.showFullScreen)

            if self.nomper is not None:
                try:
                    self.nomper.set_numlock_state(
                        bool(cfg.get("numlock_led", True)),
                        bool(cfg.get("numlock_inverted", False)),
                    )
                except Exception:
                    pass

            fp = cfg.get("full_panel")
            if fp in (1, 2, 3, 4):
                self._pending_full_panel = fp
        except Exception:
            pass

    def save_config(self):
        self._save_layout_to_env()
        self._save_sizes_to_env()
        cfg = {
            "window": {
                "x": self.x(), "y": self.y(),
                "width": self.width(), "height": self.height(),
                "fullscreen": self.isFullScreen()
            },
            "mode": self.core.current_mode,
            "full_panel": self.full_panel,
        }
        if self.nomper is not None:
            try:
                cfg["numlock_led"] = self.nomper.is_numlock_led_on()
                cfg["numlock_inverted"] = self.nomper.is_numlock_inverted()
            except Exception:
                pass
        try:
            with open(self.config_path(), "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def save_splitter_sizes(self):
        try:
            if hasattr(self, "main_splitter") and self.main_splitter.count() == 2:
                s = self.main_splitter.sizes()
                if sum(s) > 0: self.saved_main_sizes = s
            if hasattr(self, "left_splitter") and self.left_splitter.count() == 2:
                s = self.left_splitter.sizes()
                if sum(s) > 0: self.saved_left_sizes = s
            if hasattr(self, "right_splitter") and self.right_splitter.count() == 2:
                s = self.right_splitter.sizes()
                if sum(s) > 0: self.saved_right_sizes = s
        except Exception:
            pass

    # ==================================================================
    def build_split_layout(self):
        try:
            self.save_splitter_sizes()

            for attr in ("main_splitter", "left_splitter", "right_splitter"):
                if hasattr(self, attr):
                    w = getattr(self, attr)
                    w.setParent(None); w.deleteLater()

            self.main_splitter = QSplitter(Qt.Horizontal)
            self.main_splitter.setChildrenCollapsible(False)
            self.left_splitter = QSplitter(Qt.Vertical)
            self.left_splitter.setChildrenCollapsible(False)
            self.right_splitter = QSplitter(Qt.Vertical)
            self.right_splitter.setChildrenCollapsible(False)

            self.slots = {}
            for pos in self.POSITIONS:
                slot = PanelSlot(pos, available_provider=self._available_panels)
                slot.restore_requested.connect(self._on_restore_requested)
                slot.swap_requested.connect(self._on_panel_swap)
                slot.focus_requested.connect(self._on_focus_panel)
                slot.close_requested.connect(self._on_panel_close)
                slot.file_dropped.connect(self._on_empty_slot_file_dropped)
                self.slots[pos] = slot
                pid = self.slot_map.get(pos)
                if pid is not None and pid in self.panels and pid not in self.hidden_panels:
                    slot.set_panel(self.panels[pid])
                else:
                    slot.clear_panel()

            self.left_splitter.addWidget(self.slots["left_top"])
            self.left_splitter.addWidget(self.slots["left_bottom"])
            self.right_splitter.addWidget(self.slots["right_top"])
            self.right_splitter.addWidget(self.slots["right_bottom"])
            self.main_splitter.addWidget(self.left_splitter)
            self.main_splitter.addWidget(self.right_splitter)

            if self.saved_main_sizes and all(s > 0 for s in self.saved_main_sizes):
                self.main_splitter.setSizes(self.saved_main_sizes)
            else:
                w = max(self.width(), 1000)
                self.main_splitter.setSizes([w // 2, w // 2])
            if self.saved_left_sizes and all(s > 0 for s in self.saved_left_sizes):
                self.left_splitter.setSizes(self.saved_left_sizes)
            else:
                h = max(self.height(), 600)
                self.left_splitter.setSizes([h // 2, h // 2])
            if self.saved_right_sizes and all(s > 0 for s in self.saved_right_sizes):
                self.right_splitter.setSizes(self.saved_right_sizes)
            else:
                h = max(self.height(), 600)
                self.right_splitter.setSizes([h // 2, h // 2])

            self.split_layout.addWidget(self.main_splitter)

            self.main_splitter.splitterMoved.connect(lambda *_: self.save_splitter_sizes())
            self.left_splitter.splitterMoved.connect(lambda *_: self.save_splitter_sizes())
            self.right_splitter.splitterMoved.connect(lambda *_: self.save_splitter_sizes())

            QTimer.singleShot(0, self._reapply_sizes)
        except Exception as e:
            self.say(f"Layout hatası: {e}")

    def _reapply_sizes(self):
        try:
            if (hasattr(self, "main_splitter") and self.main_splitter.count() == 2
                    and self.saved_main_sizes):
                self.main_splitter.setSizes(self.saved_main_sizes)
            if (hasattr(self, "left_splitter") and self.left_splitter.count() == 2
                    and self.saved_left_sizes):
                self.left_splitter.setSizes(self.saved_left_sizes)
            if (hasattr(self, "right_splitter") and self.right_splitter.count() == 2
                    and self.saved_right_sizes):
                self.right_splitter.setSizes(self.saved_right_sizes)
        except Exception:
            pass

    # ==================================================================
    def clear_full(self):
        while self.full_layout.count():
            item = self.full_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)

    def show_split(self):
        self.clear_full()
        self.full_panel = None
        self.build_split_layout()
        self.stack.setCurrentWidget(self.split_page)

    def show_full(self, pid):
        if pid not in self.panels:
            return
        self.save_splitter_sizes()
        p = self.panels[pid]
        for slot in self.slots.values():
            if slot.current_panel is p:
                slot.clear_panel()
        p.setParent(None)
        self.clear_full()
        self.full_layout.addWidget(p)
        self.full_panel = pid
        self.last_full = pid
        self.stack.setCurrentWidget(self.full_page)

    # ==================================================================
    def toggle_panel(self, pid):
        """Ctrl+1/2/3/4 ve Numpad 1/2/3/4 → paneli tam ekran göster/sığdır."""
        if pid not in self.panels:
            return
        if self.full_panel == pid:
            self.show_split()
            self.say("Tam ekran kapandı")
            self._show_toast("▢ Tam ekran kapandı")
        else:
            self.show_full(pid)
            self.say(f"{self.NAMES.get(pid, pid)} tam ekran")
            self._show_toast(f"⛶ {self.NAMES.get(pid, pid)}")

    def toggle_last(self):
        if self.full_panel is None:
            self.show_full(self.last_full)
        else:
            self.show_split()

    def toggle_window_fullscreen(self):
        if self.isFullScreen(): self.showNormal()
        else: self.showFullScreen()

    # ==================================================================
    def rotate_left_panels(self):
        if self.full_panel is not None:
            return
        lt = self.slot_map.get("left_top")
        lb = self.slot_map.get("left_bottom")
        self.slot_map["left_top"], self.slot_map["left_bottom"] = lb, lt
        self.build_split_layout()
        self._save_layout_to_env()
        self.say("Sol kolon döndürüldü"); self._show_toast("↻ Sol kolon döndü")

    def rotate_right_panels(self):
        if self.full_panel is not None:
            return
        rt = self.slot_map.get("right_top")
        rb = self.slot_map.get("right_bottom")
        self.slot_map["right_top"], self.slot_map["right_bottom"] = rb, rt
        self.build_split_layout()
        self._save_layout_to_env()
        self.say("Sağ kolon döndürüldü"); self._show_toast("↻ Sağ kolon döndü")

    def rotate_all_panels(self):
        if self.full_panel is not None:
            self.show_split(); return
        lt = self.slot_map.get("left_top")
        lb = self.slot_map.get("left_bottom")
        rt = self.slot_map.get("right_top")
        rb = self.slot_map.get("right_bottom")
        self.slot_map["left_top"]     = lb
        self.slot_map["left_bottom"]  = rt
        self.slot_map["right_top"]    = rb
        self.slot_map["right_bottom"] = lt
        self.build_split_layout()
        self._save_layout_to_env()
        self.say("Paneller döndürüldü"); self._show_toast("↻ Paneller döndü")

    def reset_to_default_layout(self):
        if self.full_panel is not None:
            self.show_split()
        valid = sorted(self.panels.keys())
        while len(valid) < 4:
            valid.append(valid[-1] if valid else 1)
        for i, pos in enumerate(self.POSITIONS):
            self.slot_map[pos] = valid[i]
        self.hidden_panels.clear()
        self.build_split_layout()
        self._save_layout_to_env()
        self.say("Varsayılan düzen"); self._show_toast("◇ Varsayılan düzen")

    def reset_all(self):
        if self.full_panel is not None:
            self.show_split()
        valid = sorted(self.panels.keys())
        while len(valid) < 4:
            valid.append(valid[-1] if valid else 1)
        for i, pos in enumerate(self.POSITIONS):
            self.slot_map[pos] = valid[i]
        self.hidden_panels.clear()
        self.saved_main_sizes  = None
        self.saved_left_sizes  = None
        self.saved_right_sizes = None
        self.build_split_layout()
        self._save_layout_to_env()
        self.say("Sıfırlandı"); self._show_toast("⟲ Sıfırlandı")

    def cycle_mode(self):
        self.core.cycle_mode()

    # ==================================================================
    def numpad_action(self, key_name):
        # NumLock kilidi: LED sönükse numpad kısayolları çalışmaz
        if self.nomper is not None:
            try:
                if not self.nomper.shortcuts_enabled():
                    self._show_toast("⌨  Numpad kilitli")
                    return False
            except Exception:
                pass

        ok = kyol.dispatch_numpad(self, key_name)
        if ok:
            label = {
                "Num1": "1 • Birincil", "Num2": "2 • İkincil",
                "Num3": "3 • Üçüncül",  "Num4": "4 • Numper",
                "Num5": "5 • Son panel", "Num6": "6 • Varsayılan düzen",
                "Num7": "7 • Sol döndür", "Num8": "8 • Sağ döndür",
                "Num9": "9 • Tümünü döndür", "Num0": "0 • Sphere menüsü",
                "Num.": "· Tam ekran",
            }.get(key_name)
            if label:
                self._show_toast(f"⌨  {label}")
        return ok

    def _dispatch_numpad(self, name):
        ok = self.numpad_action(name)
        if ok and self.nomper is not None:
            try: self.nomper.flash(name)
            except Exception: pass
        return ok

    # ==================================================================
    # Global olay filtresi — kısayollar her ortamda (metin kutuları dahil) çalışır
    # ==================================================================
    def eventFilter(self, obj, event):
        et = event.type()

        # Bazı widget'lar (QPlainTextEdit/QLineEdit) Ctrl+1 gibi tuşları
        # ShortcutOverride ile sahiplenmeye çalışabilir. Bizim tuşlarımızı
        # reddederek KeyPress aşamasında bize bırakılmasını sağlıyoruz.
        if et == QEvent.ShortcutOverride:
            try:
                mods = event.modifiers(); key = event.key()
                if (mods & Qt.ControlModifier) and key in (
                    Qt.Key_1, Qt.Key_2, Qt.Key_3, Qt.Key_4,
                    Qt.Key_Q, Qt.Key_R, Qt.Key_Home, Qt.Key_End,
                ):
                    event.accept()
                    return True
            except Exception:
                pass
            return super().eventFilter(obj, event)

        if et == QEvent.KeyPress:
            try:
                if kyol.handle_event(self, event):
                    return True
            except Exception:
                pass
            return super().eventFilter(obj, event)

        return super().eventFilter(obj, event)

    # ==================================================================
    def say(self, msg):
        sphere_name = self.core.env_store.current
        self.status_bar.showMessage(
            f"{msg}  |  Sphere: {sphere_name}  |  "
            f"F11 pencere  •  Ctrl+1/2/3/4 panel  •  Ctrl+Q sphere menüsü  •  "
            f"Ctrl+R düzen  •  Ctrl+Shift+R sıfırla"
        )

    def closeEvent(self, event):
        self.save_splitter_sizes()
        self.save_config()
        QApplication.instance().removeEventFilter(self)
        event.accept()


# ======================================================================
def load_theme(base_dir):
    for rel in ("theme.qss", os.path.join("themes", "dark_modern.qss")):
        p = os.path.join(base_dir, rel)
        if os.path.isfile(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception:
                pass
    return FALLBACK_STYLE


def main():
    os.environ.setdefault("QT_QPA_PLATFORM", "xcb")
    os.environ.setdefault("GDK_BACKEND", "x11")

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    f = QFont("Inter", 10)
    f.setStyleHint(QFont.SansSerif)
    app.setFont(f)

    base_dir = os.path.dirname(os.path.abspath(__file__))
    app.setStyleSheet(load_theme(base_dir))

    win = MainWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
