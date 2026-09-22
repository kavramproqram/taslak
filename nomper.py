#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KAVRAM v3 – [04] SPHERE & NUMPER (nomper.py)
- Sphere menüsü (header'da buton + Ctrl+Q / Num0 fare konumu)
- Yuvarlak köşeli açılır menü
- Numper kapatılamaz ama sürüklenebilir (grip çalışır)
- WorkspaceSlot ✕ → .py dosyasını klasörden siler, yuva boş kalır
- Genel dosya/uygulama desteği: .py (importlib), yürütülebilir (QProcess)
- Kendi çekirdek dosyalarını yüklemeyi reddeder
- NumLock: LED'li (beyaz nokta), tek tık → aç/kapat, çift tık → ters çevir
"""
import os, sys, shutil, importlib.util, traceback

from PyQt5.QtWidgets import (
    QGridLayout, QPushButton, QLabel, QWidget, QVBoxLayout,
    QHBoxLayout, QSizePolicy, QFrame, QComboBox, QInputDialog,
    QMessageBox, QMenu, QScrollArea, QWidgetAction
)
from PyQt5.QtCore import Qt, QSize, QTimer, pyqtSignal, QProcess
from PyQt5.QtGui import QFont, QCursor

from Kavram import Panel, PANEL_MIME
from ortam import MAX_ENVIRONMENTS

# Panelin kendi çekirdek dosyaları — bunlar yuvalara yüklenemez
_CORE_SELF_NAMES = {"Kavram.py", "pencere.py", "nomper.py", "kyol.py", "ortam.py"}

# Numpad tuş düzeni (açıklama kaldırıldı — sadece butonlar)
NUMPAD_KEYS = [
    ("Num\nLock", "NumLock", 0, 0, 1, 1),
    ("/",         "Num/",    0, 1, 1, 1),
    ("*",         "Num*",    0, 2, 1, 1),
    ("-",         "Num-",    0, 3, 1, 1),
    ("7",         "Num7",    1, 0, 1, 1),
    ("8",         "Num8",    1, 1, 1, 1),
    ("9",         "Num9",    1, 2, 1, 1),
    ("+",         "Num+",    1, 3, 2, 1),
    ("4",         "Num4",    2, 0, 1, 1),
    ("5",         "Num5",    2, 1, 1, 1),
    ("6",         "Num6",    2, 2, 1, 1),
    ("1",         "Num1",    3, 0, 1, 1),
    ("2",         "Num2",    3, 1, 1, 1),
    ("3",         "Num3",    3, 2, 1, 1),
    ("Enter",     "NumEnter",3, 3, 2, 1),
    ("0",         "Num0",    4, 0, 1, 2),
    (".",         "Num.",    4, 2, 1, 1),
]


# ======================================================================
class NumpadKey(QFrame):
    def __init__(self, label, key_name, callback, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.NoFrame)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2); lay.setSpacing(0)
        self.btn = QPushButton(label.replace("\n", " "))
        self.btn.setObjectName("numpadBtn")
        self.btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.btn.setMinimumSize(QSize(46, 46))
        f = QFont("JetBrains Mono", 13); f.setBold(True)
        self.btn.setFont(f)
        self.btn.clicked.connect(lambda: callback(key_name))
        lay.addWidget(self.btn, 1)

    def set_active(self, active: bool):
        self.btn.setProperty("active", bool(active))
        self.btn.style().unpolish(self.btn); self.btn.style().polish(self.btn)


# ======================================================================
class _ClickableButton(QPushButton):
    """Tek tık / çift tık ayrımı yapan özel buton."""
    single_clicked = pyqtSignal()
    double_clicked = pyqtSignal()

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(260)
        self._timer.timeout.connect(self.single_clicked.emit)
        self._pending_double = False

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            if self._timer.isActive():
                self._timer.stop()
                self._pending_double = True
            else:
                self._pending_double = False
                self._timer.start()
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self._pending_double:
            self._pending_double = False
            try:
                self.setDown(False)
            except Exception:
                pass
            self.double_clicked.emit()
            e.accept()
            return
        super().mouseReleaseEvent(e)


class NumLockKey(QFrame):
    """NumLock butonu — üzerinde beyaz LED nokta."""
    single_clicked = pyqtSignal()
    double_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.NoFrame)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(2, 2, 2, 2)
        outer.setSpacing(0)

        self._wrap = QWidget()
        self._wrap.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._wrap.setMinimumSize(QSize(46, 46))
        outer.addWidget(self._wrap, 1)

        self.btn = _ClickableButton("Num Lock", self._wrap)
        self.btn.setObjectName("numpadBtn")
        f = QFont("JetBrains Mono", 13); f.setBold(True)
        self.btn.setFont(f)

        self._led = QLabel(self._wrap)
        self._led.setFixedSize(10, 10)
        self._led.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._led.raise_()

        self._led_on = True
        self._update_led()

        self.btn.single_clicked.connect(self.single_clicked)
        self.btn.double_clicked.connect(self.double_clicked)

    def _update_led(self):
        if self._led_on:
            self._led.setStyleSheet(
                "background-color: #FFFFFF; border-radius: 5px;"
                "border: 1px solid #FFFFFF;")
        else:
            self._led.setStyleSheet(
                "background-color: #1A1A1A; border-radius: 5px;"
                "border: 1px solid #666666;")

    def _position_children(self):
        try:
            w = self._wrap.width(); h = self._wrap.height()
            if w <= 0 or h <= 0:
                return
            self.btn.setGeometry(0, 0, w, h)
            self._led.move(max(2, w - 15), 4)
            self._led.raise_()
        except Exception:
            pass

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._position_children()

    def showEvent(self, e):
        super().showEvent(e)
        QTimer.singleShot(0, self._position_children)

    def set_led(self, on):
        self._led_on = bool(on)
        self._update_led()

    def is_led_on(self):
        return self._led_on

    def set_active(self, active):
        self.btn.setProperty("active", bool(active))
        self.btn.style().unpolish(self.btn)
        self.btn.style().polish(self.btn)


# ======================================================================
class SphereRow(QWidget):
    select_requested = pyqtSignal(str)
    rename_requested = pyqtSignal(str)
    delete_requested = pyqtSignal(str)

    def __init__(self, name, is_default, is_current, parent=None):
        super().__init__(parent)
        self.env_name = name
        self.is_default = is_default
        self.is_current = is_current
        self.setFixedHeight(30)
        self.setMinimumWidth(220)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet("""
            SphereRow { background: transparent; border-radius: 6px; }
            SphereRow:hover { background: #2A2A2A; }
        """)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 2, 10, 2)
        lay.setSpacing(8)

        self.icon = QLabel("●" if is_current else "○")
        self.icon.setFixedWidth(14)
        if is_current:
            self.icon.setStyleSheet(
                "color: #007ACC; background: transparent; font-size: 11px;")
        else:
            self.icon.setStyleSheet(
                "color: #666; background: transparent; font-size: 11px;")
        lay.addWidget(self.icon)

        self.name_lbl = QLabel(name)
        weight = "600" if is_current else "400"
        color = "#FFFFFF" if is_current else "#CCCCCC"
        self.name_lbl.setStyleSheet(
            f"color: {color}; background: transparent; font-weight: {weight};"
        )
        lay.addWidget(self.name_lbl, 1)

        if is_default:
            lock = QLabel("🔒")
            lock.setStyleSheet(
                "color: #666; background: transparent; font-size: 10px;")
            lock.setToolTip("Ana Sphere silinemez")
            lay.addWidget(lock)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.select_requested.emit(self.env_name)
        elif e.button() == Qt.RightButton and not self.is_default:
            menu = QMenu(self)
            rename_act = menu.addAction("✎  Düzenle")
            menu.addSeparator()
            delete_act = menu.addAction("🗑  Sil")
            chosen = menu.exec_(e.globalPos())
            if chosen == rename_act:
                self.rename_requested.emit(self.env_name)
            elif chosen == delete_act:
                self.delete_requested.emit(self.env_name)


class SphereAddRow(QWidget):
    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(30)
        self.setMinimumWidth(220)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet("""
            SphereAddRow { background: transparent; border-radius: 6px; }
            SphereAddRow:hover { background: #2A2A2A; }
        """)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 2, 10, 2)
        lay.setSpacing(8)

        plus = QLabel("＋")
        plus.setFixedWidth(14)
        plus.setStyleSheet(
            "color: #007ACC; background: transparent; font-weight: bold; font-size: 12px;")
        lay.addWidget(plus)

        lbl = QLabel("Yeni Sphere")
        lbl.setStyleSheet("color: #CCCCCC; background: transparent;")
        lay.addWidget(lbl, 1)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit()


# ======================================================================
class SphereMenu(QMenu):
    select_requested = pyqtSignal(str)
    add_requested    = pyqtSignal()
    rename_requested = pyqtSignal(str)
    delete_requested = pyqtSignal(str)

    def __init__(self, env_store, parent=None):
        super().__init__(parent)
        self.env_store = env_store

        self.setWindowFlags(
            self.windowFlags()
            | Qt.FramelessWindowHint
            | Qt.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        self.setStyleSheet("""
            QMenu {
                background-color: #1A1A1A;
                color: #FFFFFF;
                border: 1px solid #3A3A3A;
                padding: 8px;
                border-radius: 12px;
                min-width: 240px;
            }
            QMenu::separator {
                height: 1px;
                background: #2A2A2A;
                margin: 6px 8px;
            }
            QMenu::item { background: transparent; }
        """)
        self._build()

    def _build(self):
        self.clear()
        for name in self.env_store.names():
            is_default = self.env_store.is_default(name)
            is_current = (name == self.env_store.current)
            row = SphereRow(name, is_default, is_current)
            row.select_requested.connect(self._on_select)
            row.rename_requested.connect(self._on_rename)
            row.delete_requested.connect(self._on_delete)
            wa = QWidgetAction(self)
            wa.setDefaultWidget(row)
            self.addAction(wa)

        self.addSeparator()

        add_row = SphereAddRow()
        add_row.clicked.connect(self._on_add)
        wa = QWidgetAction(self)
        wa.setDefaultWidget(add_row)
        self.addAction(wa)

    def _on_select(self, name):
        self.close()
        QTimer.singleShot(0, lambda: self.select_requested.emit(name))

    def _on_rename(self, name):
        self.close()
        QTimer.singleShot(0, lambda: self.rename_requested.emit(name))

    def _on_delete(self, name):
        self.close()
        QTimer.singleShot(0, lambda: self.delete_requested.emit(name))

    def _on_add(self):
        self.close()
        QTimer.singleShot(0, self.add_requested.emit)


# ======================================================================
# Harici uygulama yer tutucusu
# ======================================================================
class ExternalAppWidget(QWidget):
    """Yürütülebilir harici uygulamalar için yer tutucu ve süreç yöneticisi."""
    def __init__(self, path, parent=None):
        super().__init__(parent)
        self.path = path
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(6)
        lay.addStretch(1)

        lbl = QLabel(f"▶  {os.path.basename(path)}")
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet(
            "font-weight: 600; color: #FFFFFF; font-size: 13px; background: transparent;")
        lay.addWidget(lbl)

        path_lbl = QLabel(path)
        path_lbl.setAlignment(Qt.AlignCenter)
        path_lbl.setWordWrap(True)
        path_lbl.setStyleSheet(
            "color: #888888; font-size: 10px; background: transparent;")
        lay.addWidget(path_lbl)

        row = QHBoxLayout()
        row.addStretch(1)
        self.start_btn = QPushButton("▶  Çalıştır")
        self.start_btn.clicked.connect(self.start)
        row.addWidget(self.start_btn)
        self.stop_btn = QPushButton("■  Durdur")
        self.stop_btn.clicked.connect(self.stop)
        self.stop_btn.setEnabled(False)
        row.addWidget(self.stop_btn)
        row.addStretch(1)
        lay.addLayout(row)
        lay.addStretch(1)

        self._proc = QProcess(self)
        self._proc.finished.connect(self._on_finished)
        self._proc.errorOccurred.connect(self._on_error)
        QTimer.singleShot(150, self.start)

    def start(self):
        try:
            if self._proc.state() == QProcess.NotRunning:
                self._proc.start(self.path)
                self.start_btn.setEnabled(False)
                self.stop_btn.setEnabled(True)
        except Exception:
            pass

    def stop(self):
        try:
            if self._proc.state() != QProcess.NotRunning:
                self._proc.terminate()
                QTimer.singleShot(1500, self._proc.kill)
        except Exception:
            pass

    def _on_finished(self, code, status):
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

    def _on_error(self, err):
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)


# ======================================================================
# WorkspaceSlot
# ======================================================================
class WorkspaceSlot(Panel):
    file_dropped = pyqtSignal(int, str)

    def __init__(self, env_name, slot_id, env_folder, saved_name=None, parent=None):
        super().__init__(f"[ {slot_id} ] BOŞ", "dim", parent)
        self.env_name = env_name
        self.slot_id = slot_id
        self.env_folder = env_folder
        self.current_file = None
        self.current_widget = None
        self.current_module_name = None
        self.setAcceptDrops(True)

        self.hint = QLabel("Buraya bir dosya / uygulama bırakın")
        self.hint.setAlignment(Qt.AlignCenter)
        self.hint.setWordWrap(True)
        self.hint.setStyleSheet(
            "color: #666; font-size: 11px; padding: 18px; background: transparent;")
        self.body.addWidget(self.hint, 1)

        if saved_name:
            path = os.path.join(env_folder, saved_name)
            if os.path.isfile(path):
                QTimer.singleShot(0, lambda p=path: self._apply_file(p))
            else:
                self._reset_ui()

    # ------------------------------------------------------------------
    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(PANEL_MIME):
            event.acceptProposedAction(); return
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    event.acceptProposedAction(); return
        event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls() or event.mimeData().hasFormat(PANEL_MIME):
            event.acceptProposedAction()

    def dropEvent(self, event):
        if event.mimeData().hasFormat(PANEL_MIME):
            super().dropEvent(event); return
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                path = url.toLocalFile()
                if path:
                    self.load_file(path)
                    event.acceptProposedAction()
                    return
        event.ignore()

    # ------------------------------------------------------------------
    def load_file(self, src_path):
        if not src_path:
            return
        try:
            if self._is_self_file(src_path):
                self._show_error(
                    "⚠  KAVRAM sistem dosyası yüklenemez.\n\n"
                    "Kavram.py, pencere.py, nomper.py, kyol.py, ortam.py "
                    "kendi üzerine yüklenemez."
                )
                return
            name = os.path.basename(src_path)
            os.makedirs(self.env_folder, exist_ok=True)
            dst = os.path.join(self.env_folder, name)
            if os.path.abspath(src_path) != os.path.abspath(dst):
                shutil.copy2(src_path, dst)
            self._apply_file(dst)
            self.file_dropped.emit(self.slot_id, name)
        except Exception as e:
            self._show_error(f"Dosya yüklenemedi:\n{e}")

    def _is_self_file(self, path):
        try:
            base = os.path.basename(path)
            if base in _CORE_SELF_NAMES:
                return True
            try:
                if os.path.abspath(path) == os.path.abspath(sys.argv[0]):
                    return True
            except Exception:
                pass
        except Exception:
            pass
        return False

    def _is_executable(self, path):
        try:
            return os.path.isfile(path) and os.access(path, os.X_OK)
        except Exception:
            return False

    # ------------------------------------------------------------------
    def _apply_file(self, path):
        self.current_file = path
        name = os.path.basename(path)
        self.title_label.setText(f"[ {self.slot_id} ] {name}")

        ext = os.path.splitext(path)[1].lower()
        if ext == ".py":
            widget, err, module_name = self._try_load_widget(path)
            self.current_module_name = module_name
            if widget is not None:
                self._show_widget(widget)
                return
            # Modül yüklendi ama QWidget yok → bilgi göster
            if err and ("QWidget" in err or "constructor" in err):
                self._show_info(path, name)
                return
            if err:
                self._show_error(err)
                return
            self._show_info(path, name)
            return

        if self._is_executable(path):
            self._show_external(path)
        else:
            self._show_info(path, name)

    def _show_widget(self, widget):
        self._clear_body_below_header()
        self.current_widget = widget
        widget.setParent(self)
        self.body.addWidget(widget, 1)
        widget.show()

    def _show_external(self, path):
        self._clear_body_below_header()
        w = ExternalAppWidget(path)
        self.current_widget = w
        w.setParent(self)
        self.body.addWidget(w, 1)
        w.show()

    def _show_info(self, path, name):
        self._clear_body_below_header()
        lbl = QLabel(f"📄 {name}\n\n{self.env_folder}")
        lbl.setAlignment(Qt.AlignCenter); lbl.setWordWrap(True)
        lbl.setStyleSheet(
            "color: #CCC; font-size: 11px; padding: 18px; background: transparent;")
        self.body.addWidget(lbl, 1)
        self.hint = lbl

    def _show_error(self, tb):
        self._clear_body_below_header()
        lbl = QLabel("⚠  Yükleme Hatası\n\n" + tb)
        lbl.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(
            "color: #FF8888; background-color: #2A0E0E;"
            "border: 1px solid #663333; border-radius: 6px;"
            "padding: 10px; font-size: 11px;"
            "font-family: 'JetBrains Mono', monospace;"
        )
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")
        scroll.setWidget(lbl)
        self.body.addWidget(scroll, 1)
        self.hint = lbl

    def _clear_body_below_header(self):
        self.current_widget = None
        for i in range(self.body.count() - 1, 0, -1):
            item = self.body.takeAt(i)
            w = item.widget()
            if w is not None:
                w.setParent(None); w.deleteLater()

    def _reset_ui(self):
        self.current_file = None
        self.current_widget = None
        self.current_module_name = None
        self.title_label.setText(f"[ {self.slot_id} ] BOŞ")
        self._clear_body_below_header()
        self.hint = QLabel("Buraya bir dosya / uygulama bırakın")
        self.hint.setAlignment(Qt.AlignCenter); self.hint.setWordWrap(True)
        self.hint.setStyleSheet(
            "color: #666; font-size: 11px; padding: 18px; background: transparent;")
        self.body.addWidget(self.hint, 1)

    # ------------------------------------------------------------------
    def _try_load_widget(self, path):
        if not os.path.isfile(path):
            return None, "Dosya bulunamadı.", None

        safe = "".join(
            c if (c.isalnum() or c == "_") else "_"
            for c in f"kavram_user_{self.env_name}_{self.slot_id}_"
                     f"{os.path.splitext(os.path.basename(path))[0]}"
        )
        try:
            spec = importlib.util.spec_from_file_location(safe, path)
            if spec is None or spec.loader is None:
                return None, "Modül yüklenemedi (spec).", None
            mod = importlib.util.module_from_spec(spec)
            sys.modules[safe] = mod
            spec.loader.exec_module(mod)
        except Exception:
            sys.modules.pop(safe, None)
            return None, traceback.format_exc(), None

        from PyQt5.QtWidgets import QWidget
        candidates = []
        for attr in dir(mod):
            try:
                obj = getattr(mod, attr)
            except Exception:
                continue
            if (isinstance(obj, type) and issubclass(obj, QWidget)
                    and obj is not QWidget
                    and getattr(obj, "__module__", None) == mod.__name__):
                candidates.append((attr, obj))
        if not candidates:
            return None, "Uygun QWidget alt sınıfı bulunamadı.", safe

        preferred = ["Widget", "Panel", "KavramPanel", "MainWindow", "Main", "App"]
        chosen = None
        for pref in preferred:
            for nm, cls in candidates:
                if nm == pref:
                    chosen = cls; break
            if chosen is not None:
                break
        if chosen is None:
            chosen = candidates[0][1]

        for factory in (
            lambda: chosen(),
            lambda: chosen(self.env_folder),
            lambda: chosen(parent=None),
        ):
            try:
                w = factory()
                if w is not None:
                    return w, None, safe
            except Exception:
                continue
        return None, "Widget örneklenemedi (constructor hatası).", safe

    # ------------------------------------------------------------------
    def request_close(self):
        """✕ → dosyayı sil, config temizle, yuva boş kalsın."""
        try:
            if self.current_file:
                try:
                    if os.path.isfile(self.current_file):
                        os.remove(self.current_file)
                except Exception:
                    pass
                self.current_file = None

            if self.current_module_name:
                try:
                    sys.modules.pop(self.current_module_name, None)
                except Exception:
                    pass
                self.current_module_name = None

            self._reset_ui()
        except Exception:
            pass

        self.close_requested.emit(
            self._panel_id if self._panel_id is not None else -1)


# ======================================================================
# NomperPanel
# ======================================================================
class NomperPanel(Panel):
    is_nomper = True

    def __init__(self, signals=None, parent=None):
        super().__init__("[ 04 ] SPHERE", "purple", parent)
        self.signals = signals
        self.main_window = None
        self.core = None
        self.env_store = None
        self.key_widgets = {}

        # NumLock durumu
        self._numlock_led_on = True
        self._numlock_inverted = False
        self._numlock_key = None

        self.title_label.setVisible(False)

        self.sphere_btn = QPushButton("🌐  Sphere")
        self.sphere_btn.setObjectName("sphereBtn")
        self.sphere_btn.setCursor(Qt.PointingHandCursor)
        self.sphere_btn.setMinimumWidth(160)
        self.sphere_btn.setToolTip("Sphere menüsünü aç (Ctrl+Q / Num0)")
        self.sphere_btn.clicked.connect(lambda: self.open_sphere_menu())

        hl = self.header.header_layout
        idx = hl.indexOf(self.close_btn)
        if idx < 0:
            idx = hl.count()
        hl.insertWidget(idx, self.sphere_btn, 1)

        self.close_btn.setVisible(False)

        # NOT: Numper artık sürüklenebilir (grip aktif).
        # Kapatma kısıtı yalnızca panelin request_close metodunda korunur.

        self.numpad_widget = QWidget()
        self.numpad_widget.setStyleSheet("background: transparent;")
        nl = QVBoxLayout(self.numpad_widget)
        nl.setContentsMargins(0, 8, 0, 0); nl.setSpacing(2)

        grid_widget = QWidget(); grid_widget.setStyleSheet("background: transparent;")
        self.grid = QGridLayout(grid_widget)
        self.grid.setContentsMargins(6, 4, 6, 6); self.grid.setSpacing(5)
        for c in range(4): self.grid.setColumnStretch(c, 1)
        for r in range(5): self.grid.setRowStretch(r, 1)

        for label, key_name, r, c, rs, cs in NUMPAD_KEYS:
            if key_name == "NumLock":
                nk = NumLockKey()
                nk.single_clicked.connect(self._on_numlock_single)
                nk.double_clicked.connect(self._on_numlock_double)
                nk.set_led(self._numlock_led_on)
                self._numlock_key = nk
            else:
                nk = NumpadKey(label, key_name, self.on_numpad)
            self.grid.addWidget(nk, r, c, rs, cs)
            self.key_widgets[key_name] = nk

        nl.addWidget(grid_widget, 1)
        self.body.addWidget(self.numpad_widget, 1)

    # ------------------------------------------------------------------
    def set_core(self, core): self.core = core
    def set_main_window(self, mw): self.main_window = mw
    def set_env_store(self, store):
        self.env_store = store
        self._sync_sphere_button()
    def set_mode(self, mode):
        if self.env_store:
            self._sync_sphere_button()

    def _sync_sphere_button(self):
        if not self.env_store:
            return
        cur = self.env_store.current
        self.sphere_btn.setText(f"🌐  {cur}")

    # ------------------------------------------------------------------
    def _on_numlock_single(self):
        self._numlock_led_on = not self._numlock_led_on
        if self._numlock_key:
            self._numlock_key.set_led(self._numlock_led_on)
        state = "AKTİF" if self.shortcuts_enabled() else "PASİF"
        if self.signals:
            try:
                self.signals.toast_message.emit(f"⌨  Numpad kısayolları: {state}")
            except Exception:
                pass

    def _on_numlock_double(self):
        self._numlock_inverted = not self._numlock_inverted
        state = "AKTİF" if self.shortcuts_enabled() else "PASİF"
        mode = "ters" if self._numlock_inverted else "normal"
        if self.signals:
            try:
                self.signals.toast_message.emit(
                    f"⌨  Numpad modu: {mode} — {state}")
            except Exception:
                pass

    def shortcuts_enabled(self):
        if self._numlock_inverted:
            return not self._numlock_led_on
        return self._numlock_led_on

    def is_numlock_led_on(self):
        return self._numlock_led_on

    def is_numlock_inverted(self):
        return self._numlock_inverted

    def set_numlock_state(self, led_on, inverted):
        self._numlock_led_on = bool(led_on)
        self._numlock_inverted = bool(inverted)
        if self._numlock_key:
            self._numlock_key.set_led(self._numlock_led_on)

    # ------------------------------------------------------------------
    def open_sphere_menu(self, global_pos=None):
        if not self.env_store:
            return
        if global_pos is None:
            global_pos = self.sphere_btn.mapToGlobal(
                self.sphere_btn.rect().bottomLeft()
            )
        menu = SphereMenu(self.env_store, self)
        menu.select_requested.connect(self._select_env)
        menu.add_requested.connect(self._add_environment)
        menu.rename_requested.connect(self._rename_env)
        menu.delete_requested.connect(self._delete_env)
        menu.exec_(global_pos)

    # ---------------- Sphere eylemleri ----------------
    def _select_env(self, name):
        if not self.env_store or not self.core:
            return
        if name == self.env_store.current:
            return
        try:
            self.env_store.promote(name)
        except Exception:
            pass
        QTimer.singleShot(0, lambda n=name: self.core.switch_environment(n))

    def _rename_env(self, old_name):
        if not self.env_store:
            return
        new_name, ok = QInputDialog.getText(
            self, "Sphere Düzenle",
            f"'{old_name}' için yeni isim:", text=old_name
        )
        if not ok:
            return
        ok, err = self.env_store.rename(old_name, new_name)
        if not ok:
            QMessageBox.warning(self, "Hata", err); return
        was_current = (self.env_store.current == new_name)
        self._sync_sphere_button()
        if was_current and self.core:
            QTimer.singleShot(0, lambda n=new_name: self.core.switch_environment(n))

    def _delete_env(self, name):
        if not self.env_store:
            return
        if self.env_store.is_default(name):
            QMessageBox.information(self, "Bilgi", "Ana Sphere silinemez.")
            return
        reply = QMessageBox.question(
            self, "Sil",
            f"'{name}' sphere'i ve klasörü tamamen silinsin mi?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        was_current = (self.env_store.current == name)
        ok, err = self.env_store.delete(name)
        if not ok:
            QMessageBox.warning(self, "Hata", err); return
        self._sync_sphere_button()
        if was_current and self.core:
            QTimer.singleShot(0, lambda: self.core.switch_environment(
                self.env_store.current))

    def _add_environment(self):
        if not self.env_store or not self.core:
            return
        if self.env_store.count() >= MAX_ENVIRONMENTS:
            QMessageBox.warning(self, "Sınır",
                                f"En fazla {MAX_ENVIRONMENTS} sphere.")
            return
        name, ok = QInputDialog.getText(self, "Yeni Sphere", "Sphere adı:")
        if not ok:
            return
        name = (name or "").strip()
        if not name:
            return
        if self.env_store.exists(name):
            QMessageBox.warning(self, "Hata", "Bu isim zaten kullanılıyor.")
            return
        reply = QMessageBox.question(
            self, "Numper",
            "Bu sphere'de Numper paneli kullanılsın mı?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        ok, err = self.env_store.add(name, reply == QMessageBox.Yes)
        if not ok:
            QMessageBox.warning(self, "Hata", err); return
        self._sync_sphere_button()
        QTimer.singleShot(0, lambda n=name: self.core.switch_environment(n))

    # ------------------------------------------------------------------
    def request_close(self):
        if self.signals:
            try:
                self.signals.toast_message.emit("Numper kapatılamaz")
            except Exception:
                pass
        QMessageBox.information(
            self, "Numper",
            "Numper paneli sistem yöneticisi tarafından sabitlenmiştir.\n"
            "Kapatılamaz ancak sürüklenebilir."
        )

    def on_numpad(self, key_name):
        if self.main_window is None:
            return
        if key_name in ("NumLock", "NumEnter"):
            return
        self.main_window.numpad_action(key_name)

    def flash(self, key_name):
        nk = self.key_widgets.get(key_name)
        if not nk:
            return
        if hasattr(nk, "set_active"):
            nk.set_active(True)
            QTimer.singleShot(140, lambda: nk.set_active(False))
