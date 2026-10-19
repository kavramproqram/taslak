"""
Kavram - PyQt5 ile dijital devre editörü ve simülatörü.

Çalıştırma:  python main.py
Gereksinim:  pip install PyQt5

Dokunmatik ekran desteği:
  * Tek parmak: seç, sürükle, pine dokun ve kablo çek, anahtarı çevir
  * İki parmak: yakınlaştır/uzaklaştır (kıstırma) ve kaydır
  * Dokunmatik parça: basılı tutunca sinyal 1 olur
"""
import json
import math
import os
import random
import sys
import time

from PyQt5 import QtWidgets
from PyQt5.QtCore import QEvent, QMimeData, QPointF, QRectF, Qt, QTimer
from PyQt5.QtGui import QColor, QDrag, QFont, QKeySequence, QPainter, QPainterPath, QPainterPathStroker, QPen
from PyQt5.QtWidgets import (
    QAction, QActionGroup, QFileDialog, QFrame, QGraphicsItem, QGraphicsPathItem, QGraphicsScene,
    QGraphicsView, QGroupBox, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMainWindow,
    QMessageBox, QPlainTextEdit, QPushButton, QShortcut, QSlider, QTabWidget, QVBoxLayout, QWidget,
)

from circuit import (
    COMPONENTS, GATE_FN, GROUPS, PRESETS, SUPPLY_HIGH, UPCOMING,
    Circuit, build_preset, pin_key,
)
from visuals import BOARD_RECT, draw_board, draw_part, draw_pin, pin_shape

# ---------- Renkler ----------
GREEN = "#22c55e"
RED = "#ef4444"
YELLOW = "#facc15"
COPPER = "#b7793a"
TEXT = "#e5e7eb"
MUTED = "#8a94a6"

SAVE_PATH = os.path.join(os.path.expanduser("~"), "kavram-devre.json")

LOGIC_TEXT = """
<p><b>Simülatör dijital (0/1) mantıkla çalışır.</b></p>
<ul>
<li>Güç kaynağı voltaj 2.5 V üzerindeyse 1, altındaysa 0 üretir.</li>
<li>Kapılar girişlerine göre çıkışını hesaplar. İşlemci çekirdeği bir bitlik toplama yapar (S = toplam, C = elde).</li>
<li>Saat her darbede 0 ile 1 arasında değişir. Bellekler yükselen kenarda veriyi alır.</li>
<li>RAM ve D flip-flop uçucudur: sıfırlayınca silinir. SSD kalıcıdır: sıfırlamadan etkilenmez.</li>
<li>Dokunmatik parça basılı tutulduğu sürece 1 üretir. Ekran gelen sinyali gösterir.</li>
<li>Bir bağlantıya aynı anda 0 ve 1 basan iki çıkış bağlanırsa kısa devre uyarısı verilir.</li>
</ul>
"""

QSS = """
QMainWindow, QWidget { background: #0a0e15; color: #e5e7eb; font-size: 13px; }
QLabel { background: transparent; }
QToolBar {
  background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #131a26, stop:1 #0d131c);
  border: 0; border-bottom: 1px solid #1e2a3b; spacing: 6px; padding: 6px 10px;
}
QToolBar QToolButton {
  padding: 7px 14px; border-radius: 9px; color: #cbd5e1; font-weight: 600; border: 1px solid transparent;
}
QToolBar QToolButton:hover { background: #1b2536; border-color: #26344b; }
QToolBar QToolButton:checked {
  background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #3b82f6, stop:1 #1d4ed8);
  color: white; border-color: #60a5fa;
}
QToolBar QLabel { color: #94a3b8; font-weight: 600; min-width: 60px; }
QGroupBox {
  background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #141c2a, stop:1 #0e1420);
  border: 1px solid #1e2a3b; border-radius: 14px; margin-top: 16px; padding: 14px 12px 12px 12px;
  font-weight: 700; color: #94a3b8;
}
QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; left: 14px; padding: 0 6px;
  color: #7dd3fc; letter-spacing: 0.4px; }
QPushButton {
  background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #223048, stop:1 #172134);
  border: 1px solid #2a3a55; border-radius: 10px; padding: 9px 12px; color: #e2e8f0; font-weight: 600;
}
QPushButton:hover:enabled { border-color: #3b82f6; }
QPushButton:pressed { background: #111a2b; }
QPushButton:disabled { color: #4b5563; background: #111827; border-color: #1f2937; }
QPushButton#primary {
  background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #34d399, stop:1 #15803d);
  color: #04210f; border-color: #34d399;
}
QPushButton#primary:disabled { background: #14532d; color: #3f6b50; }
QListWidget, QPlainTextEdit {
  background: #0c121c; border: 1px solid #1e2a3b; border-radius: 12px; padding: 4px; outline: 0;
}
QListWidget::item { padding: 8px 10px; border-radius: 8px; margin: 1px 0; }
QListWidget::item:selected { background: #1d4ed8; color: white; }
QListWidget::item:hover:!selected { background: #151f30; }
QTabWidget::pane { border: 1px solid #1e2a3b; border-radius: 12px; background: #0e1420; top: -1px; }
QTabBar::tab { background: transparent; padding: 8px 14px; color: #7c8aa3; border-radius: 9px; margin: 3px 2px;
  font-weight: 600; }
QTabBar::tab:hover { color: #cbd5e1; }
QTabBar::tab:selected { background: #1d4ed8; color: white; }
QSlider::groove:horizontal { height: 6px; background: #1e2a3b; border-radius: 3px; }
QSlider::sub-page:horizontal { background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #2563eb, stop:1 #34d399);
  border-radius: 3px; }
QSlider::handle:horizontal { background: #e2e8f0; width: 18px; margin: -7px 0; border-radius: 9px;
  border: 2px solid #3b82f6; }
QPlainTextEdit#log { color: #86efac; font-family: Consolas, "Courier New", monospace; font-size: 12px; }
QPlainTextEdit#code { color: #93c5fd; font-family: Consolas, "Courier New", monospace; font-size: 12px; }
QLabel#hint { color: #64748b; font-size: 11px; }
QLabel#title { color: #f8fafc; font-size: 15px; font-weight: 800; }
QStatusBar { background: #0d131c; color: #64748b; border-top: 1px solid #1e2a3b; }
"""


# =====================================================================
#  Yardımcılar
# =====================================================================
def describe(c, p):
    """Parçanın (açık_mı, görüntülenecek_metin) bilgisini döndürür."""
    t = p.type
    if t == "vcc":
        return c.voltage >= SUPPLY_HIGH, f"{c.voltage:g} V"
    if t == "gnd":
        return False, "0 V"
    if t == "switch":
        return p.state, "AÇIK" if p.state else "KAPALI"
    if t == "touch":
        return p.state, "BASILI" if p.state else "BOŞTA"
    if t == "screen":
        return p.state, f"SİNYAL {int(p.state)}"
    if t == "led":
        return p.state, "YANIYOR" if p.state else "SÖNÜK"
    if t == "clock":
        return p.state, f"CLK = {int(p.state)}"
    if t in ("dff", "ram", "ssd"):
        return p.state, f"Q = {int(p.state)}"
    if t == "hadder":
        s = p.outs.get("S", False)
        c_out = p.outs.get("C", False)
        return (s or c_out), f"S={int(s)}  C={int(c_out)}"
    y = p.outs.get("Y", False)
    return y, f"Y = {int(y)}"


def elbow_path(a, b):
    """İki nokta arasında dik açılı kablo yolu."""
    ax, ay = a
    bx, by = b
    mx = (ax + bx) / 2.0
    path = QPainterPath(QPointF(ax, ay))
    path.lineTo(mx, ay)
    path.lineTo(mx, by)
    path.lineTo(bx, by)
    return path


def part_of(item):
    while item is not None and not isinstance(item, PartItem):
        item = item.parentItem()
    return item


# =====================================================================
#  Grafik öğeleri
# =====================================================================
class PinItem(QGraphicsItem):
    """Bir parçanın ucu. Dokunmatik için tıklama alanı büyütülmüştür."""

    def __init__(self, key, x, y, parent):
        super().__init__(parent)
        self.key = key
        self.hi = False
        self.bad = False
        self.setPos(x, y)
        self.setZValue(3)

    def boundingRect(self):
        return QRectF(-16, -16, 32, 32)

    def shape(self):
        return pin_shape()

    def paint(self, painter, option, widget=None):
        draw_pin(painter, self.hi, self.bad)

    def set_style(self, hi, bad):
        if hi != self.hi or bad != self.bad:
            self.hi = hi
            self.bad = bad
            self.update()


class PartItem(QGraphicsItem):
    """Bir devre parçasının görseli. Sürükleme ve seçme view tarafından yönetilir."""

    def __init__(self, part, on_moved):
        super().__init__()
        d = COMPONENTS[part.type]
        self.uid = part.uid
        self.ptype = part.type
        self.name = d["name"]
        self.w = d["w"]
        self.h = d["h"]
        self.on = False
        self.state_text = ""
        self.on_moved = on_moved
        self.pins = {}

        self.setFlags(QGraphicsItem.ItemIsSelectable | QGraphicsItem.ItemSendsGeometryChanges)
        self.setPos(part.x, part.y)
        self.setZValue(1)
        for pin in d["pins"]:
            self.pins[pin.id] = PinItem(pin_key(part.uid, pin.id), pin.x, pin.y, self)

    def boundingRect(self):
        return QRectF(-14, -10, self.w + 28, self.h + 20)

    def paint(self, painter, option, widget=None):
        draw_part(painter, self.ptype, COMPONENTS[self.ptype]["pins"], self.w, self.h,
                  self.name, self.state_text, self.on, self.isSelected())

    def itemChange(self, change, value):
        if (
            change == QGraphicsItem.ItemPositionHasChanged
            and self.scene() is not None
            and self.on_moved is not None
        ):
            self.on_moved(self.uid, self.pos())
        return super().itemChange(change, value)


class WireItem(QGraphicsPathItem):
    """Kablo: bakır iz görünümü, geniş tıklama alanı."""

    def __init__(self, index, path, cls):
        super().__init__(path)
        self.index = index
        self.cls = cls
        self.setZValue(0)

    def boundingRect(self):
        return self.path().boundingRect().adjusted(-12, -12, 12, 12)

    def shape(self):
        stroker = QPainterPathStroker()
        stroker.setWidth(18)
        return stroker.createStroke(self.path())

    def paint(self, painter, option, widget=None):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(Qt.NoBrush)
        path = self.path()

        # Gölge
        painter.setPen(QPen(QColor(0, 0, 0, 120), 7, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.drawPath(path)

        if self.cls == "hi":
            painter.setPen(QPen(QColor(34, 197, 94, 70), 10, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            painter.drawPath(path)
            color = GREEN
            style = Qt.SolidLine
        elif self.cls == "bad":
            color = RED
            style = Qt.DashLine
        else:
            color = COPPER
            style = Qt.SolidLine

        painter.setPen(QPen(QColor(color), 3.5, style, Qt.RoundCap, Qt.RoundJoin))
        painter.drawPath(path)
        painter.restore()


class CircuitScene(QGraphicsScene):
    """Devrenin grafik sahnesi. Çizimi modelden alır."""

    def __init__(self, win):
        super().__init__(-3000, -3000, 6000, 6000)
        self.win = win
        self.part_items = {}
        self.wire_items = []

    def rebuild(self):
        """Parça sayısı değiştiğinde tüm parça ve kabloları yeniden kurar."""
        self.clear()
        self.part_items = {}
        self.wire_items = []
        for p in self.win.circuit.parts:
            item = PartItem(p, self.win.on_part_moved)
            self.addItem(item)
            self.part_items[p.uid] = item
        self.refresh()

    def refresh(self):
        """Simülasyon durumunu (renk, metin, parlama) günceller."""
        c = self.win.circuit
        net, lv, conflict = c.analyze()
        for uid, item in self.part_items.items():
            p = c.part(uid)
            if p is None:
                continue
            item.on, item.state_text = describe(c, p)
            for pid, pin_item in item.pins.items():
                key = pin_key(uid, pid)
                pin_item.set_style(c.level_of(net, lv, key), key in conflict)
            item.update()
        self.refresh_wires()

    def refresh_wires(self):
        c = self.win.circuit
        net, lv, conflict = c.analyze()
        for w in self.wire_items:
            self.removeItem(w)
        self.wire_items = []
        for i, w in enumerate(c.wires):
            a = c.pin_pos(w["a"])
            b = c.pin_pos(w["b"])
            if a is None or b is None:
                continue
            if w["a"] in conflict:
                cls = "bad"
            elif c.level_of(net, lv, w["a"]):
                cls = "hi"
            else:
                cls = "lo"
            item = WireItem(i, elbow_path(a, b), cls)
            self.addItem(item)
            self.wire_items.append(item)


# =====================================================================
#  Tuval: fare ve dokunmatik olayları
# =====================================================================
class CircuitView(QGraphicsView):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.setScene(win.canvas_scene)
        self.setRenderHint(QPainter.Antialiasing)
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.setFrameShape(QFrame.NoFrame)
        self.setAcceptDrops(True)
        self.setMinimumSize(520, 320)
        self.setDragMode(QGraphicsView.NoDrag)

        # Dokunmatik ekran için: olayları biz alırız
        self.viewport().setAttribute(Qt.WA_AcceptTouchEvents, True)

        self.mode = None          # None | 'wire' | 'part' | 'pan'
        self.wire_from = None
        self.temp = None
        self.drag = None
        self.pan_from = None
        self.pan_scroll = (0, 0)
        self.last_vp = None
        self.touch_mode = None    # None | 'single' | 'pinch'
        self.pinch_prev = None

    # ---------- Çizim ----------
    def drawBackground(self, painter, rect):
        painter.fillRect(rect, QColor("#070b12"))
        draw_board(painter, BOARD_RECT)

    # ---------- Fare ----------
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._press(e.pos())
            e.accept()
            return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self.mode is not None:
            self._move(e.pos())
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.mode is not None:
            self._release(e.pos())
            return
        super().mouseReleaseEvent(e)

    def wheelEvent(self, e):
        factor = 1.15 if e.angleDelta().y() > 0 else 1 / 1.15
        self.win.zoom_by(factor)

    # ---------- Ortak eylemler (fare ve dokunmatik) ----------
    def _press(self, vp):
        if self.mode is not None:
            return
        self.last_vp = vp
        item = self.itemAt(vp)
        scene_pos = self.mapToScene(vp)

        if isinstance(item, PinItem):
            if self.win.tool == "delete":
                return
            self.mode = "wire"
            self.wire_from = item.key
            self.temp = QGraphicsPathItem()
            self.temp.setPen(QPen(QColor(YELLOW), 2.5, Qt.DashLine, Qt.RoundCap, Qt.RoundJoin))
            self.temp.setZValue(5)
            self.scene().addItem(self.temp)
            self._update_temp(scene_pos)
            return

        part = part_of(item)
        if part is not None:
            if self.win.tool == "delete":
                self.win.delete_part(part.uid)
                return
            self.mode = "part"
            self.scene().clearSelection()
            part.setSelected(True)
            self.drag = {"item": part, "start_scene": scene_pos, "start_pos": QPointF(part.pos())}
            self.win.begin_part_press(part.uid)
            return

        if isinstance(item, WireItem):
            if self.win.tool == "delete":
                self.win.delete_wire(item.index)
            return

        # Boş alan: kaydır
        self.mode = "pan"
        self.pan_from = vp
        self.pan_scroll = (self.horizontalScrollBar().value(), self.verticalScrollBar().value())
        self.win.clear_selection()
        self.setCursor(Qt.ClosedHandCursor)

    def _move(self, vp):
        self.last_vp = vp
        if self.mode == "wire":
            self._update_temp(self.mapToScene(vp))
        elif self.mode == "part" and self.drag is not None:
            d = self.mapToScene(vp) - self.drag["start_scene"]
            self.drag["item"].setPos(self.drag["start_pos"] + d)
        elif self.mode == "pan":
            dd = vp - self.pan_from
            self.horizontalScrollBar().setValue(self.pan_scroll[0] - dd.x())
            self.verticalScrollBar().setValue(self.pan_scroll[1] - dd.y())

    def _release(self, vp):
        mode = self.mode
        self.mode = None
        if mode == "wire":
            key = self.wire_from
            self.wire_from = None
            if self.temp is not None:
                self.scene().removeItem(self.temp)
                self.temp = None
            target = self.itemAt(vp)
            if isinstance(target, PinItem) and target.key != key:
                self.win.connect_pins(key, target.key)
            else:
                self.win.refresh_ui()
        elif mode == "part":
            self.drag = None
            self.win.end_part_press()
        elif mode == "pan":
            self.setCursor(Qt.ArrowCursor)

    def _cancel_single(self):
        """İki parmak başlayınca tek parmak işlemini iptal eder."""
        mode = self.mode
        self.mode = None
        if mode == "wire":
            self.wire_from = None
            if self.temp is not None:
                self.scene().removeItem(self.temp)
                self.temp = None
        elif mode == "part":
            self.drag = None
            self.win.end_part_press()
        elif mode == "pan":
            self.setCursor(Qt.ArrowCursor)

    def _update_temp(self, pos):
        a = self.win.circuit.pin_pos(self.wire_from)
        if a is None or self.temp is None:
            return
        self.temp.setPath(elbow_path(a, (pos.x(), pos.y())))

    # ---------- Dokunmatik ----------
    def viewportEvent(self, event):
        if event.type() in (QEvent.TouchBegin, QEvent.TouchUpdate, QEvent.TouchEnd):
            self._touch(event)
            return True
        return super().viewportEvent(event)

    def _touch(self, event):
        pts = [tp for tp in event.touchPoints() if tp.state() != Qt.TouchPointReleased]

        if event.type() == QEvent.TouchEnd:
            if self.touch_mode == "single" and self.mode is not None and self.last_vp is not None:
                self._release(self.last_vp)
            self.touch_mode = None
            self.pinch_prev = None
            return

        if len(pts) >= 2:
            # İki parmak: kıstırarak yakınlaştır ve kaydır
            if self.touch_mode == "single":
                self._cancel_single()
            self.touch_mode = "pinch"
            a = pts[0].pos()
            b = pts[1].pos()
            mid = QPointF((a.x() + b.x()) / 2.0, (a.y() + b.y()) / 2.0)
            dist = math.hypot(a.x() - b.x(), a.y() - b.y())
            if self.pinch_prev is not None:
                prev_dist, prev_mid = self.pinch_prev
                if prev_dist > 1:
                    self.win.zoom_by(dist / prev_dist)
                d = mid - prev_mid
                self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - int(d.x()))
                self.verticalScrollBar().setValue(self.verticalScrollBar().value() - int(d.y()))
            self.pinch_prev = (dist, mid)
            return

        if len(pts) == 1 and self.touch_mode != "pinch":
            vp = pts[0].pos().toPoint()
            if self.touch_mode is None:
                self.touch_mode = "single"
                self._press(vp)
            elif self.touch_mode == "single":
                self._move(vp)

    # ---------- Sürükle-bırak (paletten) ----------
    def dragEnterEvent(self, e):
        if e.mimeData().hasText():
            e.acceptProposedAction()

    def dragMoveEvent(self, e):
        if e.mimeData().hasText():
            e.acceptProposedAction()

    def dropEvent(self, e):
        type_ = e.mimeData().text()
        if type_ in COMPONENTS:
            p = self.mapToScene(e.pos())
            self.win.add_part(type_, p.x(), p.y())
            e.acceptProposedAction()


class PaletteList(QListWidget):
    """Bileşen listesi. Öğeler tuvale sürüklenebilir."""

    def startDrag(self, supported_actions):
        item = self.currentItem()
        if item is None or not item.data(Qt.UserRole):
            return
        mime = QMimeData()
        mime.setText(item.data(Qt.UserRole))
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec_(Qt.CopyAction)


# =====================================================================
#  Ana pencere
# =====================================================================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Kavram - Transistör Laboratuvarı")
        self.resize(1480, 900)

        self.circuit = build_preset(1)
        self.tool = "select"
        self.undo_stack = []
        self.redo_stack = []
        self.running = False
        self.last_leds = {}
        self.last_conflict = ""
        self.press = None

        self.canvas_scene = CircuitScene(self)
        self.view = CircuitView(self)

        self.timer = QTimer(self)
        self.timer.setInterval(700)
        self.timer.timeout.connect(self.step_clock)

        self._build_toolbar()
        self._build_ui()
        self._fill_palette()
        self._fill_presets()
        self._build_shortcuts()

        self.sync_led_memory()
        self.rebuild_all()
        self.set_running(False)
        self.log("Devre hazır. Parçayı sürükle, pinden pine kablo çek, Boşluk ile başlat.")
        self.log("Dokunmatik: tek parmakla sür, iki parmakla yakınlaştır, Dokunmatik parçayı basılı tut.")

    # ---------- Arayüz kurulumu ----------
    def _build_toolbar(self):
        tb = self.addToolBar("Araçlar")
        tb.setMovable(False)

        title = QLabel("KAVRAM")
        title.setObjectName("title")
        title.setStyleSheet("color:#7dd3fc; font-size:15px; font-weight:800; padding:0 12px 0 4px;")
        tb.addWidget(title)
        tb.addSeparator()

        self.mode_group = QActionGroup(self)
        self.mode_group.setExclusive(True)
        self.mode_actions = {}
        for key, label, tip in [
            ("select", "Seç", "Seç ve taşı (dokunmatik: sürükle)"),
            ("pan", "Kaydır", "Boş alanı sürükleyerek kaydır"),
            ("wire", "Kablo", "Pinden pine sürükleyerek kablo çek"),
            ("delete", "Sil", "Parça veya kablo sil"),
        ]:
            act = QAction(label, self)
            act.setCheckable(True)
            act.setToolTip(tip)
            act.setChecked(key == "select")
            act.triggered.connect(lambda _checked, k=key: self.set_tool(k))
            self.mode_group.addAction(act)
            self.mode_actions[key] = act
            tb.addAction(act)

        tb.addSeparator()
        act_undo = QAction("Geri Al", self)
        act_undo.setShortcut(QKeySequence.Undo)
        act_undo.triggered.connect(self.undo)
        tb.addAction(act_undo)

        act_redo = QAction("İleri Al", self)
        act_redo.setShortcut(QKeySequence.Redo)
        act_redo.triggered.connect(self.redo)
        tb.addAction(act_redo)

        tb.addSeparator()
        act_out = QAction("−", self)
        act_out.setShortcut(QKeySequence.ZoomOut)
        act_out.triggered.connect(lambda: self.zoom_by(1 / 1.2))
        tb.addAction(act_out)

        act_in = QAction("+", self)
        act_in.setShortcut(QKeySequence.ZoomIn)
        act_in.triggered.connect(lambda: self.zoom_by(1.2))
        tb.addAction(act_in)

        self.zoom_label = QLabel("%100")
        self.zoom_label.setAlignment(Qt.AlignCenter)
        tb.addWidget(self.zoom_label)

        act_fit = QAction("Sığdır", self)
        act_fit.triggered.connect(self.fit_view)
        tb.addAction(act_fit)

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        # ----- Sol panel -----
        self.left_tabs = QTabWidget()
        self.left_tabs.setFixedWidth(280)
        self.palette = PaletteList()
        self.palette.itemDoubleClicked.connect(self._palette_double_click)
        self.left_tabs.addTab(self.palette, "Bileşenler")

        self.presets_list = QListWidget()
        self.presets_list.itemClicked.connect(self._preset_clicked)
        self.left_tabs.addTab(self.presets_list, "Devreler")

        tools_w = QWidget()
        tl = QVBoxLayout(tools_w)
        tl.setSpacing(8)
        for label, fn in [
            ("Hızlı kaydet", self.quick_save),
            ("Hızlı yükle", self.quick_load),
            ("Dosyaya aktar (.json)", self.export_file),
            ("Dosyadan içe aktar", self.import_file),
            ("Devreyi temizle", self.clear_circuit),
        ]:
            btn = QPushButton(label)
            btn.clicked.connect(fn)
            tl.addWidget(btn)
        tl.addStretch()
        self.left_tabs.addTab(tools_w, "Araçlar")
        root.addWidget(self.left_tabs)

        # ----- Orta: tuval + alt paneller -----
        center = QVBoxLayout()
        center.setSpacing(10)
        center.addWidget(self.view, 3)

        bottom = QHBoxLayout()
        bottom.setSpacing(10)
        self.bottom_tabs = QTabWidget()

        diag = QWidget()
        dl = QHBoxLayout(diag)
        dl.addStretch()
        self.blocks = {}
        spec = [("cu", "Control\nUnit"), ("alu", "ALU"), ("reg", "Register"),
                ("ram", "RAM"), ("ssd", "SSD")]
        for i, (key, text) in enumerate(spec):
            if i:
                arrow = QLabel("→")
                arrow.setStyleSheet("color:#475569; font-size:18px;")
                dl.addWidget(arrow)
            lbl = QLabel(text)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setMinimumWidth(100)
            self.blocks[key] = lbl
            dl.addWidget(lbl)
        dl.addStretch()
        self.bottom_tabs.addTab(diag, "Devre Şeması")

        self.code_view = QPlainTextEdit()
        self.code_view.setObjectName("code")
        self.code_view.setReadOnly(True)
        self.bottom_tabs.addTab(self.code_view, "Kod")

        logic = QLabel(LOGIC_TEXT)
        logic.setWordWrap(True)
        logic.setAlignment(Qt.AlignTop)
        logic.setContentsMargins(12, 10, 12, 10)
        self.bottom_tabs.addTab(logic, "Çalışma Mantığı")

        bottom.addWidget(self.bottom_tabs, 1)

        log_box = QGroupBox("Simülasyon Logu")
        lb = QVBoxLayout(log_box)
        self.log_view = QPlainTextEdit()
        self.log_view.setObjectName("log")
        self.log_view.setReadOnly(True)
        lb.addWidget(self.log_view)
        bottom.addWidget(log_box, 1)

        center.addLayout(bottom, 1)
        root.addLayout(center, 1)

        # ----- Sağ panel -----
        right = QWidget()
        right.setFixedWidth(270)
        rl = QVBoxLayout(right)
        rl.setSpacing(10)

        sim = QGroupBox("Simülasyon")
        sl = QVBoxLayout(sim)
        self.btn_start = QPushButton("▶  Başlat")
        self.btn_start.setObjectName("primary")
        self.btn_start.clicked.connect(self.start)
        self.btn_pause = QPushButton("❚❚  Duraklat")
        self.btn_pause.clicked.connect(self.pause)
        self.btn_tick = QPushButton("Bir Darbe")
        self.btn_tick.clicked.connect(self.tick_once)
        self.btn_reset = QPushButton("↻  Sıfırla")
        self.btn_reset.clicked.connect(self.reset)
        row1 = QHBoxLayout()
        row1.addWidget(self.btn_start)
        row1.addWidget(self.btn_pause)
        row2 = QHBoxLayout()
        row2.addWidget(self.btn_tick)
        row2.addWidget(self.btn_reset)
        sl.addLayout(row1)
        sl.addLayout(row2)
        rl.addWidget(sim)

        volt = QGroupBox("Güç / Voltaj")
        vl = QVBoxLayout(volt)
        vrow = QHBoxLayout()
        self.voltage_slider = QSlider(Qt.Horizontal)
        self.voltage_slider.setRange(0, 24)  # 0.0 - 12.0 V, 0.5 adım
        self.voltage_slider.valueChanged.connect(lambda v: self.set_voltage(v / 2.0))
        self.voltage_slider.sliderReleased.connect(
            lambda: self.log(f"Voltaj {self.circuit.voltage:g} V olarak ayarlandı.")
        )
        self.voltage_label = QLabel("5 V")
        self.voltage_label.setStyleSheet("color:#e2e8f0; font-weight:700; min-width:44px;")
        vrow.addWidget(self.voltage_slider, 1)
        vrow.addWidget(self.voltage_label)
        vl.addLayout(vrow)
        hint = QLabel("2.5 V üzeri 1 (HIGH), altı 0 (LOW) kabul edilir.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        vl.addWidget(hint)
        rl.addWidget(volt)

        status = QGroupBox("Durum")
        stl = QVBoxLayout(status)
        self.status_label = QLabel()
        self.status_label.setTextFormat(Qt.RichText)
        stl.addWidget(self.status_label)
        self.stat_tick = QLabel("0")
        self.stat_led = QLabel("0 / 0")
        self.stat_short = QLabel("yok")
        for name, widget in [("Darbe", self.stat_tick), ("Yanan LED", self.stat_led),
                             ("Kısa devre", self.stat_short)]:
            h = QHBoxLayout()
            lab = QLabel(name)
            lab.setStyleSheet("color:#94a3b8;")
            h.addWidget(lab)
            h.addStretch()
            widget.setStyleSheet("color:#e2e8f0; font-weight:700;")
            h.addWidget(widget)
            stl.addLayout(h)
        rl.addWidget(status)

        counts = QGroupBox("Öğeler")
        cl = QVBoxLayout(counts)
        self.counts_label = QLabel()
        self.counts_label.setTextFormat(Qt.RichText)
        self.counts_label.setWordWrap(True)
        cl.addWidget(self.counts_label)
        rl.addWidget(counts)

        gates = QGroupBox("Mantık Kapıları")
        gl = QVBoxLayout(gates)
        self.gates_label = QLabel()
        self.gates_label.setTextFormat(Qt.RichText)
        gl.addWidget(self.gates_label)
        rl.addWidget(gates)

        rl.addStretch()
        root.addWidget(right)

        self.statusBar().showMessage("Kavram 0.4.0  ·  Açık Kaynak Eğitim Platformu  ·  Kendi işlemcini tasarla")

    def _build_shortcuts(self):
        QShortcut(QKeySequence(Qt.Key_Space), self, activated=self.toggle_run)
        QShortcut(QKeySequence(Qt.Key_Delete), self, activated=self.delete_selected)
        QShortcut(QKeySequence(Qt.Key_Backspace), self, activated=self.delete_selected)

    def _fill_palette(self):
        for gid, title in GROUPS:
            self._palette_header(title)
            for type_, d in COMPONENTS.items():
                if d["group"] != gid:
                    continue
                pins = " · ".join(p.id for p in d["pins"])
                item = QListWidgetItem(f"{d['name']}    {d['sub']}   [{pins}]")
                item.setData(Qt.UserRole, type_)
                self.palette.addItem(item)
        self._palette_header("Yakında")
        for name, pins in UPCOMING:
            item = QListWidgetItem(f"{name}   [{pins}]")
            item.setFlags(Qt.NoItemFlags)
            item.setForeground(QColor("#4b5563"))
            self.palette.addItem(item)

    def _palette_header(self, text):
        item = QListWidgetItem(text.upper())
        item.setFlags(Qt.NoItemFlags)
        font = QFont()
        font.setBold(True)
        font.setPointSize(8)
        item.setFont(font)
        item.setForeground(QColor("#38bdf8"))
        self.palette.addItem(item)

    def _fill_presets(self):
        for i, preset in enumerate(PRESETS):
            item = QListWidgetItem(f"{preset['name']}\n{preset['desc']}")
            item.setData(Qt.UserRole, i)
            self.presets_list.addItem(item)

    # ---------- Görünüm ----------
    def set_tool(self, key):
        self.tool = key
        if key == "delete":
            self.log("Silme modu: parça veya kabloya dokun.")

    def set_zoom(self, z):
        z = max(0.4, min(2.5, z))
        self.view.resetTransform()
        self.view.scale(z, z)
        self.zoom_label.setText(f"%{round(z * 100)}")

    def zoom_by(self, factor):
        self.set_zoom(self.view.transform().m11() * factor)

    def fit_view(self):
        rect = self.canvas_scene.itemsBoundingRect()
        if not self.circuit.parts or rect.isNull():
            self.set_zoom(1)
            self.view.centerOn(0, 0)
            return
        self.view.fitInView(rect.adjusted(-80, -80, 80, 80), Qt.KeepAspectRatio)
        self.zoom_label.setText(f"%{round(self.view.transform().m11() * 100)}")

    # ---------- Model ↔ arayüz senkronu ----------
    def snapshot(self):
        return json.dumps(self.circuit.to_dict())

    def commit(self, before):
        self.undo_stack.append(before)
        if len(self.undo_stack) > 100:
            self.undo_stack.pop(0)
        self.redo_stack = []

    def sync_led_memory(self):
        self.last_leds = {p.uid: p.state for p in self.circuit.parts if p.type == "led"}

    def rebuild_all(self):
        self.canvas_scene.rebuild()
        self.sync_controls()
        self.update_panels()

    def refresh_ui(self):
        self.canvas_scene.refresh()
        self.update_panels()

    def sync_controls(self):
        self.voltage_slider.blockSignals(True)
        self.voltage_slider.setValue(int(round(self.circuit.voltage * 2)))
        self.voltage_slider.blockSignals(False)
        self.voltage_label.setText(f"{self.circuit.voltage:g} V")

    def after_sim(self):
        """Mantıksal değişimleri logla ve ekranı yenile."""
        for p in self.circuit.parts:
            if p.type != "led":
                continue
            prev = self.last_leds.get(p.uid, False)
            if prev != p.state:
                self.log(f"LED #{p.uid} {'yandı' if p.state else 'söndü'}.")
            self.last_leds[p.uid] = p.state

        _, _, conflict = self.circuit.analyze()
        sig = ",".join(sorted(conflict))
        if sig and sig != self.last_conflict:
            names = [self.label_of(k) for k in sorted(conflict)[:4]]
            more = " ..." if len(conflict) > 4 else ""
            self.log("⚠ Kısa devre: " + ", ".join(names) + more)
        elif not sig and self.last_conflict:
            self.log("Kısa devre giderildi.")
        self.last_conflict = sig
        self.refresh_ui()

    def label_of(self, key):
        r = self.circuit.pin_def(key)
        if r is None:
            return key
        part, pin = r
        return f"{COMPONENTS[part.type]['name']} ({pin.id})"

    def update_panels(self):
        c = self.circuit

        counts = {}
        for p in c.parts:
            counts[p.type] = counts.get(p.type, 0) + 1
        if counts:
            self.counts_label.setText(
                "<br>".join(f"<span style='color:#94a3b8'>{COMPONENTS[t]['name']}</span> "
                            f"<b style='color:#e2e8f0'>{n}</b>" for t, n in counts.items())
            )
        else:
            self.counts_label.setText("Henüz öğe yok")

        lines = []
        for t in GATE_FN:
            n = counts.get(t, 0)
            color = GREEN if n else "#334155"
            name = COMPONENTS[t]["name"]
            lines.append(f"<span style='color:{color}'>●</span>&nbsp; {name} &nbsp;<b>{n}</b>")
        self.gates_label.setText("<br>".join(lines))

        leds = [p for p in c.parts if p.type == "led"]
        self.stat_tick.setText(str(c.tick_count))
        self.stat_led.setText(f"{sum(1 for p in leds if p.state)} / {len(leds)}")
        self.stat_short.setText("VAR" if self.last_conflict else "yok")
        self.stat_short.setStyleSheet(
            "color:#f87171; font-weight:700;" if self.last_conflict else "color:#e2e8f0; font-weight:700;"
        )

        if self.running:
            self.status_label.setText("<span style='color:#22c55e'>●</span>&nbsp; <b>Çalışıyor</b>")
        else:
            self.status_label.setText("<span style='color:#64748b'>●</span>&nbsp; Durduruldu")

        self.code_view.setPlainText(json.dumps(c.to_dict(), ensure_ascii=False, indent=2))
        self.update_blocks()

    def update_blocks(self):
        c = self.circuit
        need = {
            "cu": any(p.type == "clock" for p in c.parts),
            "alu": any(p.type in GATE_FN or p.type == "hadder" for p in c.parts),
            "reg": any(p.type == "dff" for p in c.parts),
            "ram": any(p.type == "ram" for p in c.parts),
            "ssd": any(p.type == "ssd" for p in c.parts),
        }
        ready = [k for k in ("cu", "alu", "reg", "ram", "ssd") if need[k]]
        active = ready[c.tick_count % len(ready)] if (self.running and ready) else None
        colors = {"cu": "#3b82f6", "alu": "#22c55e", "reg": "#a855f7", "ram": "#facc15", "ssd": "#22d3ee"}
        for key, lbl in self.blocks.items():
            on = need.get(key, False)
            border = colors[key] if on else "#263247"
            text = TEXT if on else "#4b5b74"
            bg = "#172033" if key == active else "#0e1420"
            lbl.setStyleSheet(
                f"border:2px solid {border}; border-radius:12px; padding:10px 14px;"
                f"font-weight:700; color:{text}; background:{bg};"
            )

    # ---------- Parça ve kablo işlemleri ----------
    def add_part(self, type_, x, y):
        d = COMPONENTS[type_]
        before = self.snapshot()
        self.circuit.add_part(type_, x - d["w"] / 2, y - d["h"] / 2)
        self.circuit.settle()
        self.commit(before)
        self.log(f"{d['name']} eklendi.")
        self.rebuild_all()
        self.after_sim()

    def delete_part(self, uid):
        p = self.circuit.part(uid)
        if p is None:
            return
        before = self.snapshot()
        self.circuit.remove_part(uid)
        self.circuit.settle()
        self.commit(before)
        self.log(f"{COMPONENTS[p.type]['name']} silindi.")
        self.rebuild_all()
        self.after_sim()

    def delete_selected(self):
        uids = [it.uid for it in self.canvas_scene.selectedItems() if isinstance(it, PartItem)]
        for uid in uids:
            self.delete_part(uid)

    def delete_wire(self, index):
        before = self.snapshot()
        self.circuit.remove_wire(index)
        self.circuit.settle()
        self.commit(before)
        self.log("Kablo silindi.")
        self.after_sim()

    def connect_pins(self, a, b):
        before = self.snapshot()
        if self.circuit.connect(a, b):
            self.circuit.settle()
            self.commit(before)
            self.log("Bağlantı kuruldu.")
        else:
            self.log("Bu bağlantı zaten var.")
        self.after_sim()

    def on_part_moved(self, uid, pos):
        """Parça sürüklenirken model konumunu ve kabloları günceller."""
        p = self.circuit.part(uid)
        if p is not None:
            p.x = round(pos.x())
            p.y = round(pos.y())
        self.canvas_scene.refresh_wires()

    def begin_part_press(self, uid):
        p = self.circuit.part(uid)
        if p is None:
            self.press = None
            return
        self.press = {"uid": uid, "x": p.x, "y": p.y, "snap": self.snapshot()}
        if p.type == "touch":
            p.state = True
            self.circuit.settle()
            self.log("Dokunmatik basıldı: sinyal 1.")
            self.after_sim()

    def end_part_press(self):
        if not self.press:
            return
        pr = self.press
        self.press = None
        p = self.circuit.part(pr["uid"])
        if p is None:
            return
        moved = (p.x, p.y) != (pr["x"], pr["y"])

        if moved:
            self.commit(pr["snap"])
        elif p.type == "switch":
            p.state = not p.state
            self.log(f"Anahtar {'açıldı' if p.state else 'kapatıldı'}.")
        elif p.type == "touch":
            self.log("Dokunmatik bırakıldı: sinyal 0.")

        if p.type == "touch":
            p.state = False
        self.circuit.settle()
        self.after_sim()

    def clear_selection(self):
        self.canvas_scene.clearSelection()

    # ---------- Geri al / İleri al ----------
    def _restore(self, text):
        self.circuit = Circuit.from_dict(json.loads(text))
        self.sync_led_memory()
        self.last_conflict = ""
        self.rebuild_all()
        self.after_sim()

    def undo(self):
        if not self.undo_stack:
            return
        self.redo_stack.append(self.snapshot())
        self._restore(self.undo_stack.pop())
        self.log("Geri alındı.")

    def redo(self):
        if not self.redo_stack:
            return
        self.undo_stack.append(self.snapshot())
        self._restore(self.redo_stack.pop())
        self.log("İleri alındı.")

    # ---------- Devre yükleme / kaydetme ----------
    def replace_circuit(self, data, message):
        self.pause()
        before = self.snapshot()
        try:
            new = Circuit.from_dict(data)
        except (ValueError, KeyError, TypeError) as err:
            self.log(f"Hata: {err}")
            return False
        self.circuit = new
        self.commit(before)
        self.sync_led_memory()
        self.last_conflict = ""
        self.rebuild_all()
        self.log(message)
        self.after_sim()
        return True

    def _preset_clicked(self, item):
        i = item.data(Qt.UserRole)
        self.replace_circuit(build_preset(i).to_dict(), f"\"{PRESETS[i]['name']}\" örneği yüklendi.")

    def _palette_double_click(self, item):
        type_ = item.data(Qt.UserRole)
        if not type_:
            return
        center = self.view.mapToScene(self.view.viewport().rect().center())
        self.add_part(type_, center.x() + random.uniform(-40, 40), center.y() + random.uniform(-40, 40))

    def clear_circuit(self):
        self.replace_circuit(Circuit().to_dict(), "Devre temizlendi.")

    def quick_save(self):
        try:
            with open(SAVE_PATH, "w", encoding="utf-8") as f:
                json.dump(self.circuit.to_dict(), f, ensure_ascii=False, indent=2)
            self.log(f"Devre kaydedildi: {SAVE_PATH}")
        except OSError as err:
            self.log(f"Kaydedilemedi: {err}")

    def quick_load(self):
        if not os.path.exists(SAVE_PATH):
            self.log("Kayıtlı devre bulunamadı.")
            return
        try:
            with open(SAVE_PATH, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as err:
            self.log(f"Yüklenemedi: {err}")
            return
        self.replace_circuit(data, "Kayıtlı devre yüklendi.")

    def export_file(self):
        path, _ = QFileDialog.getSaveFileName(self, "Devreyi kaydet", "kavram-devre.json", "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.circuit.to_dict(), f, ensure_ascii=False, indent=2)
            self.log(f"Devre dışa aktarıldı: {path}")
        except OSError as err:
            QMessageBox.warning(self, "Hata", str(err))

    def import_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Devre dosyası aç", "", "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as err:
            QMessageBox.warning(self, "Hata", f"Dosya okunamadı: {err}")
            return
        self.replace_circuit(data, f"{os.path.basename(path)} içe aktarıldı.")

    # ---------- Simülasyon ----------
    def set_running(self, on):
        self.running = on
        self.btn_start.setEnabled(not on)
        self.btn_pause.setEnabled(on)
        self.update_panels()

    def start(self):
        if self.running:
            return
        self.set_running(True)
        self.timer.start()
        self.log("Simülasyon başladı.")

    def pause(self):
        if not self.running:
            return
        self.timer.stop()
        self.set_running(False)
        self.log("Simülasyon duraklatıldı.")

    def toggle_run(self):
        if self.running:
            self.pause()
        else:
            self.start()

    def step_clock(self):
        self.circuit.tick()
        self.after_sim()

    def tick_once(self):
        self.pause()
        self.circuit.tick()
        self.after_sim()

    def reset(self):
        self.pause()
        self.circuit.reset()
        self.sync_led_memory()
        self.last_conflict = ""
        self.log("Sıfırlandı. RAM ve D flip-flop silindi, SSD korundu.")
        self.refresh_ui()
        self.after_sim()

    def set_voltage(self, v):
        self.circuit.voltage = v
        self.voltage_label.setText(f"{v:g} V")
        self.circuit.settle()
        self.after_sim()

    # ---------- Log ----------
    def log(self, message):
        self.log_view.appendPlainText(f"[{time.strftime('%H:%M:%S')}] {message}")


# =====================================================================
#  Giriş noktası
# =====================================================================
def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(QSS)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
