#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MKJ Küp Çizim — Minecraft tarzı, sınırsıza yakın 3B küp çizim aracı
(PyQt5 + PyOpenGL). Tasarım ve renk seçici / karıştırma mantığı
Drawing_editor.py örnek alınarak yazıldı.

KONTROLLER
  Sol tık / sürükle ... çiz (Ctrl basılıyken sil)
  Orta tuş sürükle .... döndür
  Shift + orta sürükle  kaydır (pan)
  Tekerlek ............ yakınlaş / uzaklaş
  Sağ tık ............. oluşturulmuş küplerin listesi
  Ctrl+Z / Ctrl+Y ..... geri al / yinele
  1 / 2 / 3 ........... Çiz / Sil / Boya aracı
  Home ................ kamerayı sıfırla

Dosya biçimi: .mkj  (JSON)
"""
import os
import sys
import math
import json
import base64
import random
import uuid
import ctypes
import traceback

if os.environ.get("XDG_SESSION_TYPE", "").lower() != "wayland":
    os.environ.setdefault("PYOPENGL_PLATFORM", "glx")

import numpy as np
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFrame,
    QDialog, QSlider, QLabel, QPushButton, QFileDialog, QMessageBox,
    QShortcut, QLineEdit, QMenu, QWidgetAction, QScrollArea, QOpenGLWidget,
    QCheckBox, QSizePolicy
)
from PyQt5.QtGui import (
    QColor, QPainter, QPen, QImage, QKeySequence, QCursor, QIcon, QPixmap,
    QPolygonF, QBrush, QTransform, QSurfaceFormat, QPalette
)
from PyQt5.QtCore import Qt, QPoint, QRect, QPointF, QByteArray, pyqtSignal, QTimer
from PyQt5.QtSvg import QSvgRenderer
from OpenGL import GL as gl

APP_NAME = "MKJ Küp Çizim"
CFG_DIR = os.path.join(os.path.expanduser("~"), ".config", "mkj-kup-cizim")
LIB_PATH = os.path.join(CFG_DIR, "kupler.json")

TILE = 16                      # her küp yüzü 16x16 piksel
ATLAS = 2048                   # doku atlası boyutu
TPR = ATLAS // TILE            # atlas satırındaki karo sayısı
MAX_SLOTS = (TPR * TPR) // 6   # en fazla küp tasarımı sayısı
CHUNK_BITS = 4                 # 16x16x16 parça

MENU_STYLE = ("QMenu { background-color: #333; color: white; border: 1px solid #555; } "
              "QMenu::item:selected { background-color: #555; } "
              "QMenu::item:disabled { color: #999; }")


# ----------------------------------------------------------------------------
# Yardımcılar (Drawing_editor.py'den)
# ----------------------------------------------------------------------------
def create_svg_icon(svg_content, size=24, color="#eee"):
    modified = svg_content.replace('stroke="#eee"', f'stroke="{color}"').replace('fill="#eee"', f'fill="{color}"')
    renderer = QSvgRenderer(QByteArray(modified.encode("utf-8")))
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return QIcon(pixmap)


SVG_UNDO_ICON = """<svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M12 19C15.866 19 19 15.866 19 12C19 8.13401 15.866 5 12 5C8.13401 5 5 8.13401 5 12C5 13.7909 5.70014 15.4293 6.84594 16.6386L5 18M5 18H9M5 18V14" stroke="#eee" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>"""
SVG_REDO_ICON = """<svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M12 5C8.13401 5 5 8.13401 5 12C5 15.866 8.13401 19 12 19C15.866 19 19 15.866 19 12C19 10.2091 18.2999 8.57074 17.1541 7.3614L19 6M19 6H15M19 6V10" stroke="#eee" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>"""
SVG_SAVE_ICON = """<svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M17 3H5C3.89 3 3 3.9 3 5V19C3 20.1 3.89 21 5 21H19C20.1 21 21 20.1 21 19V7L17 3ZM12 17C10.34 17 9 15.66 9 14C9 12.34 10.34 11 12 11C13.66 11 15 12.34 15 14C15 15.66 13.66 17 12 17Z" stroke="#eee" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>"""


def btn_style(active=False, font=14):
    """Drawing_editor.py buttonStyle / buttonStylePressure ile aynı görünüm."""
    if active:
        return (f"QPushButton {{ background-color: #555; color: white; font-size: {font}px; font-weight: bold;"
                " border: 2px solid #555; border-radius: 8px; padding: 5px; }")
    return (f"QPushButton {{ background-color: transparent; color: white; font-size: {font}px; font-weight: bold;"
            " border: 2px solid #555; border-radius: 8px; padding: 5px; }"
            "QPushButton:hover { background-color: #444; }"
            "QPushButton:pressed { background-color: #666; }"
            "QPushButton::menu-indicator { image: none; }")


# ----------------------------------------------------------------------------
# Karıştırma (Drawing_editor.py -> calculateMixColor mantığı)
# ----------------------------------------------------------------------------
MIX_MODES = [
    ("Random (Rastgele)", "random"),
    ("Sequential (Sıralı)", "sequential"),
    ("Gradient (Açısal)", "gradient"),
    ("Smooth (Pürüzsüz)", "smooth"),
    ("Harman (Doku)", "harman"),
    ("Gradyan Geçiş (Yumuşak)", "gradient_soft"),
    ("Mermer Efekti (Marble)", "marble"),
    ("Renk Serpiştirme (Splatter)", "splatter"),
    ("Dalgalı (Wave)", "wave"),
    ("Piksel Gürültüsü (Pixel)", "pixel"),
    ("Sünger (Sponge)", "sponge"),
    ("Dairesel (Radial)", "radial"),
    ("Puslu (Mist)", "mist"),
]
MIX_SHORT = {k: l.split(" (")[0] for l, k in MIX_MODES}


def mix_select(n, mode, x, y, step, angle, seq=0):
    """n öğe arasından seçim. (i, j, oran) döner: i ile j arasında 'oran' kadar karışım.
    x, y: piksel/hücre başına 16 birimlik konum, step: çizgi boyunca birikmiş uzunluk."""
    if n <= 1:
        return 0, 0, 0.0

    def blend(p):
        s = max(0.0, min(1.0, p)) * (n - 1)
        i = int(s)
        return i, min(n - 1, i + 1), s - i

    if mode in ("random", "pixel"):
        i = random.randrange(n)
        return i, i, 0.0
    if mode == "sequential":
        i = int(seq) % n
        return i, i, 0.0
    if mode == "gradient":
        a = math.radians(angle)
        i = int(abs(x * math.cos(a) + y * math.sin(a)) / 100.0) % n
        return i, i, 0.0
    if mode == "smooth":
        pos = step / 200.0
        i = int(pos) % n
        return i, (i + 1) % n, pos - int(pos)
    if mode == "harman":
        f = 0.15
        nz = (math.sin(x * f) + math.cos(y * f) + math.sin((x + y) * f * 0.5)) / 3.0
        return blend((nz + 1.0) / 2.0 + random.uniform(-0.05, 0.05))
    if mode == "gradient_soft":
        return blend((step / 500.0) % 1.0)
    if mode == "marble":
        nz = math.sin(x * 0.03 + math.cos(y * 0.03)) + math.sin(y * 0.015)
        return blend((nz + 2.0) / 4.0)
    if mode == "splatter":
        i = random.randrange(n) if random.random() > 0.8 else 0
        return i, i, 0.0
    if mode == "wave":
        return blend((math.sin(step * 0.05) + 1.0) / 2.0)
    if mode == "sponge":
        i = ((int(x / 15) * 73856093) ^ (int(y / 15) * 19349663)) % n
        return i, i, 0.0
    if mode == "radial":
        return blend((math.hypot(x, y) / 300.0) % 1.0)
    if mode == "mist":
        nz = (math.sin(x * 0.08) * math.cos(y * 0.08) + 1.0) / 2.0 + random.uniform(-0.1, 0.1)
        return blend(nz)
    return 0, 0, 0.0


# ----------------------------------------------------------------------------
# Renk seçici bileşenleri (Drawing_editor.py'den alındı)
# ----------------------------------------------------------------------------
class ColorHistoryStrip(QWidget):
    colorSelected = pyqtSignal(object, object)

    def __init__(self, colors, parent=None):
        super().__init__(parent)
        self.colors = colors
        self.square_size = 24
        self.spacing = 6
        self.margin = 5
        self.cols_per_row = 4
        num_rows = max(1, (len(colors) + self.cols_per_row - 1) // self.cols_per_row)
        total_width = self.margin * 2 + self.cols_per_row * (self.square_size + self.spacing)
        total_height = self.margin * 2 + num_rows * (self.square_size + self.spacing)
        self.setFixedSize(max(150, total_width), total_height)
        self.setCursor(Qt.PointingHandCursor)
        self.hovered_index = -1
        self.is_pressed = False
        self.setMouseTracking(True)

    def _rect(self, i):
        row, col = divmod(i, self.cols_per_row)
        x = self.margin + col * (self.square_size + self.spacing)
        y = self.margin + row * (self.square_size + self.spacing)
        return QRect(x, y, self.square_size, self.square_size)

    def _index_at(self, pos):
        for i in range(len(self.colors)):
            if self._rect(i).contains(pos):
                return i
        return -1

    def leaveEvent(self, event):
        self.hovered_index = -1
        self.is_pressed = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        if self.underMouse():
            painter.fillRect(self.rect(), QColor(60, 60, 60))
        for i, color in enumerate(self.colors):
            painter.setBrush(QBrush(color))
            if i == self.hovered_index:
                painter.setPen(QPen(Qt.white, 2))
                if self.is_pressed:
                    painter.setBrush(QBrush(color.darker(120)))
            else:
                painter.setPen(QPen(Qt.gray, 1))
            painter.drawRoundedRect(self._rect(i), 4, 4)

    def mouseMoveEvent(self, event):
        old = self.hovered_index
        self.hovered_index = self._index_at(event.pos())
        if old != self.hovered_index:
            self.update()
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            idx = self._index_at(event.pos())
            if idx >= 0:
                self.is_pressed = True
                self.update()
                self.colorSelected.emit(self.colors[idx], None)
            elif len(self.colors) == 1:
                self.colorSelected.emit(self.colors[0], None)
            else:
                self.colorSelected.emit(None, self.colors)
        elif event.button() == Qt.RightButton:
            self.showContextMenu(event.pos())

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.is_pressed = False
            self.update()
        super().mouseReleaseEvent(event)

    def showContextMenu(self, pos):
        idx = self._index_at(pos)
        if idx != -1:
            color = self.colors[idx]
            menu = QMenu(self)
            menu.setStyleSheet(MENU_STYLE)
            copy_hex = menu.addAction(f"Hex kopyala: {color.name().upper()}")
            if menu.exec_(self.mapToGlobal(pos)) == copy_hex:
                QApplication.clipboard().setText(color.name().upper())


class CircleBrightnessDialog(QDialog):
    def __init__(self, initialColor=QColor("white"), parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Popup)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setModal(True)
        self.hueSatDiameter = 150
        self.radius = self.hueSatDiameter // 2
        hF, sF, vF, _ = initialColor.getHsvF()
        self.h = max(0.0, hF) * 360.0          # gri tonlarda Qt -1 döndürür
        self.s = sF
        self.v = vF
        self.setFixedSize(280, 280)

        self.colorWheel = QImage(self.hueSatDiameter, self.hueSatDiameter, QImage.Format_ARGB32)
        self._generateColorWheel()

        self.slider = QSlider(Qt.Vertical, self)
        self.slider.setRange(0, 100)
        self.slider.setValue(int(self.v * 100))
        self.slider.setGeometry(self.hueSatDiameter + 20, 10, 20, self.hueSatDiameter)
        self.slider.valueChanged.connect(self.onValueChanged)
        self._updateSliderStyle()

        self.preview_label = QLabel(self)
        self.preview_label.setGeometry(self.hueSatDiameter + 50, 35, 40, 40)
        self._updatePreviewColor()

        self.brightness_label = QLabel(self)
        self.brightness_label.setStyleSheet("color: white; background: transparent;")
        self.brightness_label.setGeometry(self.hueSatDiameter + 50, 10, 40, 20)
        self.brightness_label.setText(f"{int(self.v * 100)}%")

        self.hex_input = QLineEdit(self)
        self.hex_input.setGeometry(10, self.hueSatDiameter + 25, 105, 25)
        self.hex_input.setStyleSheet("""
            QLineEdit { background-color: #000000; color: #FFFFFF; border: 1px solid #444444; border-radius: 4px; padding: 2px 5px; font-family: Consolas, Monaco, monospace; font-size: 12px; }
            QLineEdit:focus { border: 1px solid #00FF00; }
        """)
        self.hex_input.setMaxLength(6)
        self.hex_input.setPlaceholderText("Hex Kodu")
        self.hex_input.textChanged.connect(self.onHexTextChanged)
        self.hex_input.returnPressed.connect(self.onHexEnterPressed)

        self.hex_ok_btn = QPushButton("OK", self)
        self.hex_ok_btn.setGeometry(120, self.hueSatDiameter + 25, 40, 25)
        self.hex_ok_btn.setStyleSheet("""
            QPushButton { background-color: #222; color: #FFFFFF; border: 1px solid #444; border-radius: 4px; font-family: Consolas, Monaco, monospace; font-size: 11px; font-weight: bold; }
            QPushButton:hover { background-color: #4CAF50; border: 1px solid #4CAF50; }
            QPushButton:pressed { background-color: #388E3C; }
        """)
        self.hex_ok_btn.clicked.connect(self.onHexEnterPressed)

        self.hex_label = QLabel(self)
        self.hex_label.setGeometry(165, self.hueSatDiameter + 25, 105, 25)
        self.hex_label.setStyleSheet("""
            QLabel { background-color: #000000; color: #FFFFFF; border: 1px solid #444444; border-radius: 4px; padding: 2px 5px; font-family: Consolas, Monaco, monospace; font-size: 12px; }
        """)
        self.hex_label.setAlignment(Qt.AlignCenter)

        # Eklenen: rengi onaylamak için açık bir düğme
        self.done_btn = QPushButton("Tamam", self)
        self.done_btn.setGeometry(10, 225, 260, 32)
        self.done_btn.setStyleSheet("""
            QPushButton { background-color: #2e7d32; color: white; border: 1px solid #4CAF50; border-radius: 6px; font-size: 13px; font-weight: bold; }
            QPushButton:hover { background-color: #388E3C; }
        """)
        self.done_btn.clicked.connect(self.accept)

        self._updateHexFromColor()

    def _updateHexFromColor(self):
        color = QColor.fromHsvF(self.h / 360.0, self.s, self.v)
        hex_code = color.name().upper()[1:]
        self.hex_label.setText("#" + hex_code)
        self.hex_input.setText(hex_code)
        self._updateSliderStyle()
        self._updatePreviewColor()

    def _updateSliderStyle(self):
        hue_hex = QColor.fromHsvF(self.h / 360.0, 1.0, 1.0).name()
        self.slider.setStyleSheet(f"""
            QSlider::groove:vertical {{ border: none; width: 4px; background: qlineargradient(x1:0, y1:1, x2:0, y2:0, stop:0 #000000, stop:0.5 {hue_hex}, stop:1 #FFFFFF); margin: 0px; }}
            QSlider::handle:vertical {{ background: {hue_hex}; border: 2px solid #FFFFFF; width: 12px; height: 12px; margin: -6px 0; border-radius: 6px; }}
            QSlider::handle:vertical:hover {{ background: #FFFFFF; border: 2px solid {hue_hex}; }}
        """)

    def _updatePreviewColor(self):
        c = QColor.fromHsvF(self.h / 360.0, self.s, self.v)
        self.preview_label.setStyleSheet(
            f"QLabel {{ background-color: {c.name()}; border: 2px solid #FFFFFF; border-radius: 4px; }}")

    def onHexTextChanged(self, text):
        self.hex_input.blockSignals(True)
        clean = "".join(c for c in text.upper() if c in "0123456789ABCDEF")
        if clean != text:
            cursor = self.hex_input.cursorPosition()
            self.hex_input.setText(clean)
            self.hex_input.setCursorPosition(cursor)
        self.hex_input.blockSignals(False)

    def _applyHex(self, hex_text):
        color = QColor("#" + hex_text)
        if color.isValid():
            hF, sF, vF, _ = color.getHsvF()
            self.h = max(0.0, hF) * 360.0
            self.s = sF
            self.v = vF
            self.slider.blockSignals(True)
            self.slider.setValue(int(self.v * 100))
            self.slider.blockSignals(False)
            self.brightness_label.setText(f"{int(self.v * 100)}%")
            self.hex_input.blockSignals(True)
            self.hex_input.setText(hex_text.upper())
            self.hex_input.blockSignals(False)
            self.hex_label.setText("#" + hex_text.upper())
            self._updateSliderStyle()
            self._updatePreviewColor()
            self.update()

    def onHexEnterPressed(self):
        hex_text = self.hex_input.text().strip()
        if len(hex_text) == 6:
            self._applyHex(hex_text)

    def _handleCtrlV(self):
        text = QApplication.clipboard().text().strip().replace("#", "").upper()
        clean = "".join(c for c in text if c in "0123456789ABCDEF")
        if len(clean) == 6:
            self._applyHex(clean)

    def keyPressEvent(self, event):
        if event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_V:
            self._handleCtrlV()
            event.accept()
            return
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.accept()
            return
        super().keyPressEvent(event)

    def _generateColorWheel(self):
        center = self.radius
        for y in range(self.hueSatDiameter):
            for x in range(self.hueSatDiameter):
                dx, dy = x - center, y - center
                r = math.sqrt(dx * dx + dy * dy)
                if r <= self.radius:
                    hue = (math.degrees(math.atan2(dy, dx)) + 360) % 360
                    self.colorWheel.setPixelColor(x, y, QColor.fromHsvF(hue / 360.0, r / self.radius, 1.0))
                else:
                    self.colorWheel.setPixelColor(x, y, QColor(0, 0, 0, 0))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(30, 30, 30, 220))
        cx, cy = 10, 10
        painter.drawImage(cx, cy, self.colorWheel)
        hue_rad = math.radians(self.h)
        sat_r = self.s * self.radius
        sx = cx + self.radius + sat_r * math.cos(hue_rad)
        sy = cy + self.radius + sat_r * math.sin(hue_rad)
        painter.setPen(QPen(Qt.black, 2))
        painter.setBrush(Qt.white)
        painter.drawEllipse(QPoint(int(sx), int(sy)), 5, 5)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if not self._pickHueSat(event.pos()):
                self.accept()
            else:
                self.update()
        else:
            self.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            if self._pickHueSat(event.pos()):
                self.update()

    def _pickHueSat(self, pos):
        x, y = pos.x() - 10, pos.y() - 10
        if 0 <= x < self.hueSatDiameter and 0 <= y < self.hueSatDiameter:
            dx, dy = x - self.radius, y - self.radius
            r = math.sqrt(dx * dx + dy * dy)
            if r <= self.radius:
                self.h = (math.degrees(math.atan2(dy, dx)) + 360) % 360
                self.s = r / self.radius
                self._updateHexFromColor()
                return True
        return False

    def onValueChanged(self, val):
        self.v = val / 100.0
        self.brightness_label.setText(f"{val}%")
        self._updateHexFromColor()
        self.update()

    def getSelectedColor(self):
        return QColor.fromHsvF(self.h / 360.0, self.s, self.v)


# ----------------------------------------------------------------------------
# Küp modeli
# ----------------------------------------------------------------------------
# Yüz sırası: 0:+X(Sağ) 1:-X(Sol) 2:+Y(Üst) 3:-Y(Alt) 4:+Z(Ön) 5:-Z(Arka)
FACE_N = [(1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)]
FACE_V = np.array([
    [(1, 0, 1), (1, 0, 0), (1, 1, 0), (1, 1, 1)],
    [(0, 0, 0), (0, 0, 1), (0, 1, 1), (0, 1, 0)],
    [(0, 1, 1), (1, 1, 1), (1, 1, 0), (0, 1, 0)],
    [(0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1)],
    [(0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)],
    [(1, 0, 0), (0, 0, 0), (0, 1, 0), (1, 1, 0)],
], dtype=np.float64)
FACE_UV = np.array([(0, 1), (1, 1), (1, 0), (0, 0)], dtype=np.float64)
FACE_SHADE = np.array([0.8, 0.8, 1.0, 0.5, 0.65, 0.65], dtype=np.float64)


def img_to_b64(img):
    img = img.convertToFormat(QImage.Format_RGBA8888)
    return base64.b64encode(img.constBits().asstring(img.sizeInBytes())).decode("ascii")


def b64_to_img(s):
    raw = base64.b64decode(s)
    if len(raw) != TILE * TILE * 4:
        raise ValueError("bozuk küp verisi")
    return QImage(raw, TILE, TILE, TILE * 4, QImage.Format_RGBA8888).copy()


def solid_image(color):
    img = QImage(TILE, TILE, QImage.Format_RGBA8888)
    img.fill(QColor(color))
    return img


class Cube:
    def __init__(self, cid, name, faces):
        self.id = cid
        self.name = name
        self.faces = faces

    @staticmethod
    def solid(cid, name, color):
        return Cube(cid, name, [solid_image(color) for _ in range(6)])

    def copy_faces(self):
        return [f.copy() for f in self.faces]

    def to_json(self):
        return {"name": self.name, "faces": [img_to_b64(f) for f in self.faces]}

    @staticmethod
    def from_json(cid, d):
        faces = [b64_to_img(s) for s in d["faces"]]
        if len(faces) != 6:
            raise ValueError("küp 6 yüzlü olmalı")
        return Cube(cid, str(d.get("name", "Küp")), faces)

    def same_as(self, other):
        return all(a == b for a, b in zip(self.faces, other.faces))


def iso_cube_pixmap(faces, size):
    """Küpün izometrik küçük resmi (üst, ön(+Z), sağ(+X) yüzler)."""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.SmoothPixmapTransform, False)
    a = size * 0.45
    h = a * 1.118
    cx = size / 2.0
    ty = (size - (a + h)) / 2.0
    e1 = (a, a / 2.0)
    e2 = (-a, a / 2.0)

    def face(img, ox, oy, u, v, dark):
        p.setTransform(QTransform(u[0] / TILE, u[1] / TILE, v[0] / TILE, v[1] / TILE, ox, oy))
        p.drawImage(0, 0, img)
        p.resetTransform()
        if dark:
            poly = QPolygonF([QPointF(ox, oy), QPointF(ox + u[0], oy + u[1]),
                              QPointF(ox + u[0] + v[0], oy + u[1] + v[1]), QPointF(ox + v[0], oy + v[1])])
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 0, 0, dark))
            p.drawPolygon(poly)

    face(faces[2], cx, ty, e1, e2, 0)                                   # üst
    face(faces[4], cx + e2[0], ty + e2[1], e1, (0, h), 89)             # ön (+Z)
    face(faces[0], cx + e1[0] + e2[0], ty + e1[1] + e2[1], (-e2[0], -e2[1]), (0, h), 51)  # sağ (+X)
    # dış çizgi
    pts = [(cx, ty), (cx + a, ty + a / 2), (cx + a, ty + a / 2 + h), (cx, ty + a + h),
           (cx - a, ty + a / 2 + h), (cx - a, ty + a / 2)]
    p.setPen(QPen(QColor(255, 255, 255, 90), 1))
    p.setBrush(Qt.NoBrush)
    p.drawPolygon(QPolygonF([QPointF(x, y) for x, y in pts]))
    p.end()
    return pm


# ----------------------------------------------------------------------------
# Sahne: dünya (seyrek sözlük = sonsuza yakın alan), parçalar, doku atlası
# ----------------------------------------------------------------------------
def ckey(c):
    return (c[0] >> CHUNK_BITS, c[1] >> CHUNK_BITS, c[2] >> CHUNK_BITS)


class ChunkMesh:
    __slots__ = ("arr", "count", "vbo", "upload")

    def __init__(self):
        self.arr = None
        self.count = 0
        self.vbo = None
        self.upload = False


class Scene:
    def __init__(self):
        self.world = {}           # (x,y,z) -> küp id   (hücre başına tek küp: iç içe geçmez)
        self.chunk_cells = {}
        self.meshes = {}
        self.dirty = set()
        self.dead_vbos = []
        self.cubes = {}           # id -> Cube (listeden silinenler dahil)
        self.slots = {}           # id -> atlas yuvası
        self.next_slot = 0
        self.atlas = QImage(ATLAS, ATLAS, QImage.Format_RGBA8888)
        self.atlas.fill(QColor(0, 0, 0, 0))
        self.atlas_rows = 0
        self.atlas_dirty = True
        self.border = True

    # -- küp / atlas
    def register_cube(self, cube):
        if cube.id not in self.slots:
            if self.next_slot >= MAX_SLOTS:
                raise RuntimeError("Küp sınırına ulaşıldı.")
            self.slots[cube.id] = self.next_slot
            self.next_slot += 1
        self.cubes[cube.id] = cube
        self._write_tiles(cube)

    def _bake(self, face):
        if not self.border:
            return face
        img = face.copy()
        edge = set()
        for i in range(TILE):
            edge.update([(i, 0), (i, TILE - 1), (0, i), (TILE - 1, i)])
        for x, y in edge:
            c = img.pixelColor(x, y)
            img.setPixelColor(x, y, QColor(int(c.red() * 0.78), int(c.green() * 0.78), int(c.blue() * 0.78), 255))
        return img

    def _write_tiles(self, cube):
        base = self.slots[cube.id] * 6
        p = QPainter(self.atlas)
        p.setCompositionMode(QPainter.CompositionMode_Source)
        for f in range(6):
            t = base + f
            p.drawImage((t % TPR) * TILE, (t // TPR) * TILE, self._bake(cube.faces[f]))
        p.end()
        self.atlas_rows = max(self.atlas_rows, ((base + 5) // TPR + 1) * TILE)
        self.atlas_dirty = True

    def set_border(self, flag):
        self.border = flag
        for c in self.cubes.values():
            self._write_tiles(c)

    # -- dünya işlemleri
    def _mark(self, c):
        x, y, z = c
        self.dirty.add(ckey(c))
        for dx, dy, dz in FACE_N:
            self.dirty.add(ckey((x + dx, y + dy, z + dz)))

    def put(self, c, bid):
        old = self.world.get(c)
        if old == bid:
            return old
        self.world[c] = bid
        self.chunk_cells.setdefault(ckey(c), set()).add(c)
        self._mark(c)
        return old

    def remove(self, c):
        old = self.world.pop(c, None)
        if old is None:
            return None
        k = ckey(c)
        s = self.chunk_cells.get(k)
        if s is not None:
            s.discard(c)
            if not s:
                del self.chunk_cells[k]
        self._mark(c)
        return old

    def clear_world(self):
        self.dirty.update(self.meshes.keys())
        self.world.clear()
        self.chunk_cells.clear()

    def load_blocks(self, items):
        for c, bid in items:
            self.world[c] = bid
            self.chunk_cells.setdefault(ckey(c), set()).add(c)
        self.dirty.update(self.chunk_cells.keys())

    # -- ağ (mesh) üretimi
    def rebuild_dirty(self):
        for k in self.dirty:
            cells = self.chunk_cells.get(k)
            m = self.meshes.get(k)
            if not cells:
                if m is not None:
                    if m.vbo:
                        self.dead_vbos.append(m.vbo)
                    del self.meshes[k]
                continue
            if m is None:
                m = ChunkMesh()
                self.meshes[k] = m
            m.arr = self._build(cells)
            m.count = len(m.arr)
            m.upload = True
        self.dirty.clear()

    def _build(self, cells):
        world, slots = self.world, self.slots
        rec = []
        for c in cells:
            x, y, z = c
            base = slots[world[c]] * 6
            for f in range(6):
                nx, ny, nz = FACE_N[f]
                if (x + nx, y + ny, z + nz) in world:
                    continue
                rec.append((x, y, z, f, base + f))
        if not rec:
            return np.zeros((0, 8), np.float32)
        a = np.array(rec, dtype=np.float64)
        n = len(a)
        f = a[:, 3].astype(np.int32)
        t = a[:, 4].astype(np.int32)
        pos = a[:, None, 0:3] + FACE_V[f]
        ox = ((t % TPR) * TILE).astype(np.float64)
        oy = ((t // TPR) * TILE).astype(np.float64)
        e = 0.02
        u = (ox[:, None] + e + FACE_UV[None, :, 0] * (TILE - 2 * e)) / ATLAS
        v = (oy[:, None] + e + FACE_UV[None, :, 1] * (TILE - 2 * e)) / ATLAS
        sh = np.repeat(FACE_SHADE[f][:, None], 4, axis=1)
        out = np.empty((n, 4, 8), np.float32)
        out[:, :, 0:3] = pos
        out[:, :, 3] = u
        out[:, :, 4] = v
        out[:, :, 5] = sh
        out[:, :, 6] = sh
        out[:, :, 7] = sh
        return out.reshape(-1, 8)


# ----------------------------------------------------------------------------
# Matematik
# ----------------------------------------------------------------------------
def perspective(fovy_deg, aspect, near, far):
    f = 1.0 / math.tan(math.radians(fovy_deg) / 2.0)
    m = np.zeros((4, 4))
    m[0, 0] = f / aspect
    m[1, 1] = f
    m[2, 2] = (far + near) / (near - far)
    m[2, 3] = 2.0 * far * near / (near - far)
    m[3, 2] = -1.0
    return m


def look_at(eye, target, up):
    f = target - eye
    f = f / np.linalg.norm(f)
    s = np.cross(f, up)
    s = s / np.linalg.norm(s)
    u = np.cross(s, f)
    m = np.eye(4)
    m[0, :3], m[1, :3], m[2, :3] = s, u, -f
    m[0, 3], m[1, 3], m[2, 3] = -np.dot(s, eye), -np.dot(u, eye), np.dot(f, eye)
    return m


def raycast_blocks(world, o, d, maxdist):
    """Işının çarptığı ilk küp: (hücre, yüz normali, mesafe) ya da None."""
    if not world:
        return None
    ox, oy, oz = float(o[0]), float(o[1]), float(o[2])
    dx, dy, dz = float(d[0]), float(d[1]), float(d[2])
    x, y, z = math.floor(ox), math.floor(oy), math.floor(oz)
    inf = float("inf")
    sx, sy, sz = (1 if dx > 0 else -1), (1 if dy > 0 else -1), (1 if dz > 0 else -1)
    tdx = abs(1.0 / dx) if dx else inf
    tdy = abs(1.0 / dy) if dy else inf
    tdz = abs(1.0 / dz) if dz else inf
    tmx = ((x + 1 - ox) / dx if dx > 0 else (ox - x) / -dx) if dx else inf
    tmy = ((y + 1 - oy) / dy if dy > 0 else (oy - y) / -dy) if dy else inf
    tmz = ((z + 1 - oz) / dz if dz > 0 else (oz - z) / -dz) if dz else inf
    t = 0.0
    nrm = (0, 0, 0)
    first = True
    while t <= maxdist:
        if not first and (x, y, z) in world:
            return (x, y, z), nrm, t
        first = False
        if tmx < tmy and tmx < tmz:
            x += sx
            t = tmx
            tmx += tdx
            nrm = (-sx, 0, 0)
        elif tmy < tmz:
            y += sy
            t = tmy
            tmy += tdy
            nrm = (0, -sy, 0)
        else:
            z += sz
            t = tmz
            tmz += tdz
            nrm = (0, 0, -sz)
    return None


def plane_uv(cell, axis):
    if axis == 0:
        return cell[1], cell[2]
    if axis == 1:
        return cell[0], cell[2]
    return cell[0], cell[1]


# ----------------------------------------------------------------------------
# 3B görünüm
# ----------------------------------------------------------------------------
class Viewport(QOpenGLWidget):
    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.yaw, self.pitch, self.dist = 0.8, 0.55, 16.0
        self.target = np.array([0.5, 0.5, 0.5])
        self.fov = 60.0
        self.tex = None
        self.stroke = None
        self.cam = None
        self.cam_last = None
        self.hover = None
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.CrossCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    # -- kamera
    def reset_camera(self):
        self.yaw, self.pitch, self.dist = 0.8, 0.55, 16.0
        self.target = np.array([0.5, 0.5, 0.5])
        self.update()

    def get_camera(self):
        return {"yaw": self.yaw, "pitch": self.pitch, "dist": self.dist, "target": [float(v) for v in self.target]}

    def set_camera(self, d):
        try:
            self.yaw, self.pitch, self.dist = float(d["yaw"]), float(d["pitch"]), float(d["dist"])
            self.target = np.array([float(v) for v in d["target"]])
        except Exception:
            self.reset_camera()
        self.update()

    def eye(self):
        cp = math.cos(self.pitch)
        return self.target + self.dist * np.array([cp * math.sin(self.yaw), math.sin(self.pitch), cp * math.cos(self.yaw)])

    def matrices(self):
        w, h = max(1, self.width()), max(1, self.height())
        near = max(0.05, self.dist * 0.02)
        far = max(4000.0, self.dist * 100.0)
        return perspective(self.fov, w / h, near, far), look_at(self.eye(), self.target, np.array([0.0, 1.0, 0.0]))

    def ray(self, px, py):
        P, V = self.matrices()
        inv = np.linalg.inv(P @ V)
        x = 2.0 * px / max(1, self.width()) - 1.0
        y = 1.0 - 2.0 * py / max(1, self.height())
        a = inv @ np.array([x, y, -1.0, 1.0])
        b = inv @ np.array([x, y, 1.0, 1.0])
        a, b = a[:3] / a[3], b[:3] / b[3]
        d = b - a
        d = d / np.linalg.norm(d)
        return self.eye(), d

    # -- seçme
    def _maxdist(self):
        return min(max(self.dist * 3.0, 200.0), 2500.0)

    def pick_place(self, px, py):
        """Yeni küpün konacağı hücre ve çizim düzleminin ekseni."""
        o, d = self.ray(px, py)
        hit = raycast_blocks(self.win.scene.world, o, d, self._maxdist())
        tb = hit[2] if hit else float("inf")
        tg = float("inf")
        if abs(d[1]) > 1e-9:
            t = -o[1] / d[1]
            if t > 0:
                tg = t
        if hit and tb <= tg:
            cell, n, _ = hit
            axis = 0 if n[0] else (1 if n[1] else 2)
            return (cell[0] + n[0], cell[1] + n[1], cell[2] + n[2]), axis
        if tg < 4000.0:
            p = o + d * tg
            return (int(math.floor(p[0])), 0 if o[1] >= 0 else -1, int(math.floor(p[2]))), 1
        p = o + d * self.dist                       # boşlukta çizim: bakış düzlemi
        axis = int(np.argmax(np.abs(d)))
        return tuple(int(math.floor(v)) for v in p), axis

    def pick_hit(self, px, py):
        o, d = self.ray(px, py)
        return raycast_blocks(self.win.scene.world, o, d, self._maxdist())

    def plane_cell(self, px, py, axis, layer):
        o, d = self.ray(px, py)
        if abs(d[axis]) < 1e-9:
            return None
        t = (layer + 0.5 - o[axis]) / d[axis]
        if t <= 0 or t > 8000.0:
            return None
        p = o + d * t
        c = [int(math.floor(p[0])), int(math.floor(p[1])), int(math.floor(p[2]))]
        c[axis] = layer
        return tuple(c)

    # -- çizim vuruşu
    def begin_stroke(self, pos, mode):
        self.stroke = {"mode": mode, "changes": [], "axis": None, "layer": 0,
                       "last": None, "seq": 0, "path": 0.0, "lastpos": pos}
        self.hover = None
        self.stroke_to(pos, first=True)

    def end_stroke(self):
        if self.stroke:
            self.win.push_undo(self.stroke["changes"])
        self.stroke = None

    def _place(self, cell, axis):
        s = self.stroke
        sc = self.win.scene
        if cell in sc.world:
            return
        u, v = plane_uv(cell, axis)
        s["path"] += 16.0
        bid = self.win.pick_brush_id(u, v, s["path"], s["seq"])
        s["seq"] += 1
        sc.put(cell, bid)
        s["changes"].append((cell, None, bid))

    def stroke_to(self, pos, first=False):
        s = self.stroke
        x, y = pos.x(), pos.y()
        if s["mode"] == "draw":
            if first:
                cell, axis = self.pick_place(x, y)
                s["axis"], s["layer"] = axis, cell[axis]
                self._place(cell, axis)
                s["last"] = cell
            else:
                a, layer = s["axis"], s["layer"]
                c = self.plane_cell(x, y, a, layer)
                last = s["last"]
                if c is None or c == last:
                    return
                i, j = [k for k in range(3) if k != a]
                n = min(max(abs(c[i] - last[i]), abs(c[j] - last[j])), 4000)
                for k in range(1, n + 1):
                    t = k / n
                    cc = [0, 0, 0]
                    cc[a] = layer
                    cc[i] = int(round(last[i] + (c[i] - last[i]) * t))
                    cc[j] = int(round(last[j] + (c[j] - last[j]) * t))
                    self._place(tuple(cc), a)
                s["last"] = c
        else:
            lp = s["lastpos"]
            dist = math.hypot(x - lp.x(), y - lp.y())
            steps = 1 if first else max(1, int(dist / 5))
            for k in range(1, steps + 1):
                t = k / steps
                px = lp.x() + (x - lp.x()) * t if not first else x
                py = lp.y() + (y - lp.y()) * t if not first else y
                self._hit_apply(px, py)
            s["lastpos"] = pos

    def _hit_apply(self, px, py):
        s = self.stroke
        sc = self.win.scene
        hit = self.pick_hit(px, py)
        if not hit:
            return
        cell, n, _ = hit
        if s["mode"] == "erase":
            old = sc.remove(cell)
            if old is not None:
                s["changes"].append((cell, old, None))
        else:  # boya
            axis = 0 if n[0] else (1 if n[1] else 2)
            u, v = plane_uv(cell, axis)
            s["path"] += 16.0
            bid = self.win.pick_brush_id(u, v, s["path"], s["seq"])
            s["seq"] += 1
            old = sc.world.get(cell)
            if old is not None and old != bid:
                sc.put(cell, bid)
                s["changes"].append((cell, old, bid))
        self.win.on_world_changed(False)

    def update_hover(self, pos, ctrl):
        mode = "erase" if ctrl else self.win.tool
        self.hover = None
        if mode == "draw":
            cell, _ = self.pick_place(pos.x(), pos.y())
            if cell not in self.win.scene.world:
                self.hover = (cell, (0.35, 1.0, 0.35, 1.0))
        else:
            hit = self.pick_hit(pos.x(), pos.y())
            if hit:
                self.hover = (hit[0], (1.0, 0.3, 0.3, 1.0) if mode == "erase" else (1.0, 0.85, 0.2, 1.0))
        self.win.set_cursor_info(self.hover[0] if self.hover else None)
        self.update()

    # -- olaylar
    def mousePressEvent(self, e):
        self.setFocus()
        b = e.button()
        if b == Qt.LeftButton:
            mode = "erase" if (e.modifiers() & Qt.ControlModifier) else self.win.tool
            self.begin_stroke(e.pos(), mode)
            self.win.on_world_changed(False)
            self.update()
        elif b == Qt.MiddleButton:
            self.cam = True
            self.cam_last = e.pos()
        elif b == Qt.RightButton:
            self.win.show_cube_menu(e.globalPos())

    def mouseMoveEvent(self, e):
        pos = e.pos()
        if self.cam:
            dx, dy = pos.x() - self.cam_last.x(), pos.y() - self.cam_last.y()
            self.cam_last = pos
            if e.modifiers() & Qt.ShiftModifier:
                eye = self.eye()
                f = self.target - eye
                f = f / np.linalg.norm(f)
                right = np.cross(f, np.array([0.0, 1.0, 0.0]))
                right = right / np.linalg.norm(right)
                upv = np.cross(right, f)
                s = 2.0 * self.dist * math.tan(math.radians(self.fov) / 2.0) / max(1, self.height())
                self.target = self.target + (-right * dx + upv * dy) * s
            else:
                self.yaw -= dx * 0.009
                self.pitch = max(-1.5, min(1.5, self.pitch + dy * 0.009))
            self.update()
            return
        if self.stroke:
            self.stroke_to(pos)
            self.win.on_world_changed(False)
            self.update()
            return
        self.update_hover(pos, bool(e.modifiers() & Qt.ControlModifier))

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.stroke:
            self.end_stroke()
            self.update_hover(e.pos(), bool(e.modifiers() & Qt.ControlModifier))
        elif e.button() == Qt.MiddleButton:
            self.cam = None

    def leaveEvent(self, e):
        self.hover = None
        self.win.set_cursor_info(None)
        self.update()

    def wheelEvent(self, e):
        d = e.angleDelta().y()
        self.dist = min(8000.0, max(0.6, self.dist * (0.88 ** (d / 120.0))))
        self.update()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Home:
            self.reset_camera()
        else:
            super().keyPressEvent(e)

    # -- OpenGL
    def initializeGL(self):
        self.tex = int(gl.glGenTextures(1))
        gl.glBindTexture(gl.GL_TEXTURE_2D, self.tex)
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR)
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, gl.GL_NEAREST)
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_S, gl.GL_CLAMP_TO_EDGE)
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_T, gl.GL_CLAMP_TO_EDGE)
        gl.glPixelStorei(gl.GL_UNPACK_ALIGNMENT, 1)
        gl.glTexImage2D(gl.GL_TEXTURE_2D, 0, gl.GL_RGBA, ATLAS, ATLAS, 0, gl.GL_RGBA, gl.GL_UNSIGNED_BYTE, None)
        sc = self.win.scene
        sc.atlas_dirty = True
        sc.dead_vbos.clear()
        for m in sc.meshes.values():
            m.vbo = None
            m.upload = True
        gl.glEnable(gl.GL_DEPTH_TEST)
        gl.glEnable(gl.GL_CULL_FACE)
        gl.glCullFace(gl.GL_BACK)
        gl.glEnable(gl.GL_BLEND)
        gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)

    def paintGL(self):
        try:
            self._paint()
        except Exception:
            traceback.print_exc()

    def _upload(self):
        sc = self.win.scene
        if sc.atlas_dirty and self.tex:
            rows = max(TILE, sc.atlas_rows)
            data = np.frombuffer(sc.atlas.constBits().asstring(rows * ATLAS * 4), dtype=np.uint8)
            gl.glBindTexture(gl.GL_TEXTURE_2D, self.tex)
            gl.glPixelStorei(gl.GL_UNPACK_ALIGNMENT, 1)
            gl.glTexSubImage2D(gl.GL_TEXTURE_2D, 0, 0, 0, ATLAS, rows, gl.GL_RGBA, gl.GL_UNSIGNED_BYTE, data)
            sc.atlas_dirty = False
        if sc.dead_vbos:
            for v in sc.dead_vbos:
                gl.glDeleteBuffers(1, [int(v)])
            sc.dead_vbos.clear()
        for m in sc.meshes.values():
            if m.upload:
                if m.vbo is None:
                    m.vbo = int(gl.glGenBuffers(1))
                if m.count:
                    gl.glBindBuffer(gl.GL_ARRAY_BUFFER, m.vbo)
                    gl.glBufferData(gl.GL_ARRAY_BUFFER, m.arr.nbytes, m.arr, gl.GL_STATIC_DRAW)
                m.upload = False
        gl.glBindBuffer(gl.GL_ARRAY_BUFFER, 0)

    def _grid(self):
        d = self.dist
        step = 1 if d < 40 else (8 if d < 320 else 64)
        half = int(min(max(d * 1.6, 24.0), 600.0) // step) * step
        cx = int(round(self.target[0] / step)) * step
        cz = int(round(self.target[2] / step)) * step
        xs = np.arange(cx - half, cx + half + 1, step, dtype=np.float32)
        zs = np.arange(cz - half, cz + half + 1, step, dtype=np.float32)
        a = np.zeros((len(xs), 2, 3), np.float32)
        a[:, :, 0] = xs[:, None]
        a[:, 0, 2] = zs[0]
        a[:, 1, 2] = zs[-1]
        b = np.zeros((len(zs), 2, 3), np.float32)
        b[:, :, 2] = zs[:, None]
        b[:, 0, 0] = xs[0]
        b[:, 1, 0] = xs[-1]
        return np.ascontiguousarray(np.concatenate([a.reshape(-1, 3), b.reshape(-1, 3)])), half

    def _lines(self, arr, color, width=1.0):
        gl.glColor4f(*color)
        gl.glLineWidth(width)
        gl.glVertexPointer(3, gl.GL_FLOAT, 0, arr)
        gl.glDrawArrays(gl.GL_LINES, 0, len(arr))

    def _outline(self, cell, color):
        x, y, z = cell
        e = 0.004
        lo = (x - e, y - e, z - e)
        hi = (x + 1 + e, y + 1 + e, z + 1 + e)
        c = [(lo[0], lo[1], lo[2]), (hi[0], lo[1], lo[2]), (hi[0], lo[1], hi[2]), (lo[0], lo[1], hi[2]),
             (lo[0], hi[1], lo[2]), (hi[0], hi[1], lo[2]), (hi[0], hi[1], hi[2]), (lo[0], hi[1], hi[2])]
        ed = [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4), (0, 4), (1, 5), (2, 6), (3, 7)]
        arr = np.array([c[i] for pair in ed for i in pair], dtype=np.float32)
        self._lines(arr, color, 2.5)

    def _paint(self):
        sc = self.win.scene
        dpr = self.devicePixelRatioF()
        gl.glViewport(0, 0, int(self.width() * dpr), int(self.height() * dpr))
        gl.glClearColor(0.2, 0.2, 0.2, 1.0)
        gl.glClear(gl.GL_COLOR_BUFFER_BIT | gl.GL_DEPTH_BUFFER_BIT)
        sc.rebuild_dirty()
        self._upload()
        P, V = self.matrices()
        gl.glMatrixMode(gl.GL_PROJECTION)
        gl.glLoadMatrixf(np.ascontiguousarray(P.T, dtype=np.float32))
        gl.glMatrixMode(gl.GL_MODELVIEW)
        gl.glLoadMatrixf(np.ascontiguousarray(V.T, dtype=np.float32))
        gl.glEnable(gl.GL_DEPTH_TEST)

        # küpler
        gl.glEnable(gl.GL_TEXTURE_2D)
        gl.glBindTexture(gl.GL_TEXTURE_2D, self.tex)
        gl.glEnableClientState(gl.GL_VERTEX_ARRAY)
        gl.glEnableClientState(gl.GL_TEXTURE_COORD_ARRAY)
        gl.glEnableClientState(gl.GL_COLOR_ARRAY)
        for m in sc.meshes.values():
            if not m.count or not m.vbo:
                continue
            gl.glBindBuffer(gl.GL_ARRAY_BUFFER, m.vbo)
            gl.glVertexPointer(3, gl.GL_FLOAT, 32, ctypes.c_void_p(0))
            gl.glTexCoordPointer(2, gl.GL_FLOAT, 32, ctypes.c_void_p(12))
            gl.glColorPointer(3, gl.GL_FLOAT, 32, ctypes.c_void_p(20))
            gl.glDrawArrays(gl.GL_QUADS, 0, m.count)
        gl.glBindBuffer(gl.GL_ARRAY_BUFFER, 0)
        gl.glDisableClientState(gl.GL_COLOR_ARRAY)
        gl.glDisableClientState(gl.GL_TEXTURE_COORD_ARRAY)
        gl.glDisable(gl.GL_TEXTURE_2D)

        # zemin ızgarası ve eksenler
        grid, half = self._grid()
        self._lines(grid, (1.0, 1.0, 1.0, 0.10))
        ax = np.array([(-half, 0, 0), (half, 0, 0)], dtype=np.float32)
        az = np.array([(0, 0, -half), (0, 0, half)], dtype=np.float32)
        self._lines(ax, (1.0, 0.3, 0.3, 0.55), 1.5)
        self._lines(az, (0.35, 0.5, 1.0, 0.55), 1.5)

        if self.hover:
            self._outline(self.hover[0], self.hover[1])
        gl.glDisableClientState(gl.GL_VERTEX_ARRAY)


# ----------------------------------------------------------------------------
# Küp listesi bileşeni (üst çubuk şeridi ve sağ tık listesi)
# ----------------------------------------------------------------------------
class CubeListWidget(QWidget):
    picked = pyqtSignal(str, bool)
    context = pyqtSignal(str, QPoint)

    def __init__(self, win, cols=0, size=40, parent=None):
        super().__init__(parent)
        self.win, self.cols, self.size = win, cols, size
        self.gap, self.pad = 4, 4
        self.hover = -1
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        self.refresh()

    def refresh(self):
        n = len(self.win.order)
        c = max(1, n) if self.cols == 0 else self.cols
        rows = 1 if self.cols == 0 else max(1, -(-n // self.cols))
        cell = self.size + self.gap
        self.setFixedSize(self.pad * 2 + c * cell, self.pad * 2 + rows * cell)
        self.update()

    def _rect(self, i):
        cell = self.size + self.gap
        col, row = (i, 0) if self.cols == 0 else (i % self.cols, i // self.cols)
        return QRect(self.pad + col * cell, self.pad + row * cell, self.size, self.size)

    def _index_at(self, pos):
        for i in range(len(self.win.order)):
            if self._rect(i).contains(pos):
                return i
        return -1

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor("#262626"))
        brush = self.win.brush_ids
        for i, cid in enumerate(self.win.order):
            r = self._rect(i)
            if i == self.hover:
                p.setBrush(QColor("#444"))
                p.setPen(Qt.NoPen)
                p.drawRoundedRect(r, 6, 6)
            if cid in brush:
                p.setBrush(Qt.NoBrush)
                p.setPen(QPen(QColor("#ffffff") if cid == brush[0] else QColor("#4fa3ff"), 2))
                p.drawRoundedRect(r.adjusted(1, 1, -1, -1), 6, 6)
            pm = self.win.thumb(cid, self.size - 6)
            p.drawPixmap(r.x() + 3, r.y() + 3, pm)

    def mouseMoveEvent(self, e):
        i = self._index_at(e.pos())
        if i != self.hover:
            self.hover = i
            self.setToolTip(self.win.cube_name(self.win.order[i]) if i >= 0 else "")
            self.update()

    def leaveEvent(self, e):
        self.hover = -1
        self.update()

    def mousePressEvent(self, e):
        i = self._index_at(e.pos())
        if i < 0:
            return
        cid = self.win.order[i]
        if e.button() == Qt.LeftButton:
            self.picked.emit(cid, bool(e.modifiers() & Qt.ControlModifier))
        elif e.button() == Qt.RightButton:
            self.context.emit(cid, e.globalPos())

    def wheelEvent(self, e):
        p = self.parentWidget()
        while p is not None and not isinstance(p, QScrollArea):
            p = p.parentWidget()
        if p is not None:
            bar = p.horizontalScrollBar() if self.cols == 0 else p.verticalScrollBar()
            bar.setValue(bar.value() - e.angleDelta().y())
        e.accept()


class AngleButton(QPushButton):
    wheel = pyqtSignal(int)

    def wheelEvent(self, e):
        self.wheel.emit(15 if e.angleDelta().y() > 0 else -15)
        e.accept()


# ----------------------------------------------------------------------------
# Küp editörü
# ----------------------------------------------------------------------------
class PixelCanvas(QWidget):
    CELL = 22

    def __init__(self, dlg):
        super().__init__()
        self.dlg = dlg
        self.last = None
        self.setFixedSize(TILE * self.CELL, TILE * self.CELL)
        self.setCursor(Qt.CrossCursor)

    def _cell(self, pos):
        x, y = pos.x() // self.CELL, pos.y() // self.CELL
        if 0 <= x < TILE and 0 <= y < TILE:
            return x, y
        return None

    def paintEvent(self, e):
        p = QPainter(self)
        p.drawImage(QRect(0, 0, self.width(), self.height()), self.dlg.faces[self.dlg.cur_face])
        p.setPen(QPen(QColor(0, 0, 0, 70), 1))
        for i in range(TILE + 1):
            p.drawLine(i * self.CELL, 0, i * self.CELL, self.height())
            p.drawLine(0, i * self.CELL, self.width(), i * self.CELL)

    @staticmethod
    def _line(a, b):
        x0, y0 = a
        x1, y1 = b
        dx, dy = abs(x1 - x0), abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx - dy
        while True:
            yield x0, y0
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x0 += sx
            if e2 < dx:
                err += dx
                y0 += sy

    def mousePressEvent(self, e):
        c = self._cell(e.pos())
        if c is None:
            return
        if e.button() == Qt.LeftButton:
            if self.dlg.tool == "fill":
                self.dlg.flood(*c)
            else:
                self.dlg.begin_stroke()
                self.dlg.apply_pixel(*c)
                self.last = c
        elif e.button() == Qt.RightButton:
            self.dlg.eyedrop(*c)
        self.update()

    def mouseMoveEvent(self, e):
        if (e.buttons() & Qt.LeftButton) and self.dlg.tool == "pen" and self.last is not None:
            c = self._cell(e.pos())
            if c is not None and c != self.last:
                for x, y in self._line(self.last, c):
                    self.dlg.apply_pixel(x, y)
                self.last = c
                self.update()

    def mouseReleaseEvent(self, e):
        self.last = None


class CubeEditorDialog(QDialog):
    FACE_BUTTONS = [(2, "Üst"), (4, "Ön"), (0, "Sağ"), (5, "Arka"), (1, "Sol"), (3, "Alt")]

    def __init__(self, win, faces, name, editing, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Küp Editörü")
        self.win = win
        self.faces = faces
        self.editing = editing
        self.as_new = False
        self.name = name
        self.cur_face = 2
        self.tool = "pen"
        self.mix_colors = [QColor(c) for c in win.mix_colors]
        self.mix_history = [[QColor(c) for c in h] for h in win.mix_history]
        self.pen_color = QColor(self.mix_colors[0])
        self.mix_mode = win.ed_mix_mode
        self.mix_angle = win.ed_mix_angle
        self.seq = 0
        self.step = 0.0

        root = QHBoxLayout(self)
        self.canvas = PixelCanvas(self)
        root.addWidget(self.canvas, 0, Qt.AlignTop)

        side = QVBoxLayout()
        root.addLayout(side)

        self.name_edit = QLineEdit(name)
        self.name_edit.setPlaceholderText("Küp adı")
        side.addWidget(self.name_edit)

        self.preview = QLabel()
        self.preview.setFixedSize(132, 132)
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setStyleSheet("background:#262626; border:1px solid #444; border-radius:6px;")
        side.addWidget(self.preview, 0, Qt.AlignHCenter)

        grid = QGridLayout()
        self.face_btns = {}
        for k, (fi, label) in enumerate(self.FACE_BUTTONS):
            b = QPushButton(label)
            b.setCheckable(True)
            b.setFocusPolicy(Qt.NoFocus)
            b.setStyleSheet(btn_style(False, 13))
            b.clicked.connect(lambda _c, f=fi: self.set_face(f))
            grid.addWidget(b, k // 3, k % 3)
            self.face_btns[fi] = b
        side.addLayout(grid)
        self.all_faces = QCheckBox("Tüm yüzlere aynı anda boya")
        side.addWidget(self.all_faces)

        row = QHBoxLayout()
        self.color_button = QPushButton()
        self.color_button.setStyleSheet(btn_style(False, 13))
        self.color_menu = QMenu(self)
        self.color_menu.setStyleSheet(MENU_STYLE)
        self.color_button.setMenu(self.color_menu)
        row.addWidget(self.color_button)
        self.mix_button = QPushButton()
        self.mix_button.setStyleSheet(btn_style(False, 13))
        self.mix_button.clicked.connect(self.show_mix_menu)
        row.addWidget(self.mix_button)
        side.addLayout(row)

        row = QHBoxLayout()
        self.angle_button = AngleButton()
        self.angle_button.setStyleSheet(btn_style(False, 13))
        self.angle_button.clicked.connect(lambda: self.change_angle(15))
        self.angle_button.wheel.connect(self.change_angle)
        row.addWidget(self.angle_button)
        self.pen_btn = QPushButton("Kalem")
        self.fill_btn = QPushButton("Dolgu")
        for b, t in ((self.pen_btn, "pen"), (self.fill_btn, "fill")):
            b.setFocusPolicy(Qt.NoFocus)
            b.clicked.connect(lambda _c, tt=t: self.set_tool(tt))
            row.addWidget(b)
        side.addLayout(row)

        row = QHBoxLayout()
        fill_all = QPushButton("Yüzü Doldur")
        fill_all.clicked.connect(self.fill_face)
        copy_all = QPushButton("Yüzü Hepsine Kopyala")
        copy_all.clicked.connect(self.copy_face_to_all)
        for b in (fill_all, copy_all):
            b.setStyleSheet(btn_style(False, 12))
            b.setFocusPolicy(Qt.NoFocus)
            row.addWidget(b)
        side.addLayout(row)

        hint = QLabel("Sol tık: boya · Sağ tık: rengi al")
        hint.setStyleSheet("color:#aaa;")
        side.addWidget(hint)
        side.addStretch(1)

        row = QHBoxLayout()
        ok = QPushButton("Kaydet" if editing else "Listeye Ekle")
        ok.clicked.connect(self._ok)
        row.addWidget(ok)
        if editing:
            new = QPushButton("Yeni Küp Olarak Ekle")
            new.clicked.connect(self._ok_new)
            row.addWidget(new)
        cancel = QPushButton("İptal")
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        side.addLayout(row)

        self.set_face(2)
        self.set_tool("pen")
        self.update_color_menu()
        self.update_labels()
        self.refresh_preview()

    # -- durum
    def set_face(self, f):
        self.cur_face = f
        for fi, b in self.face_btns.items():
            b.setChecked(fi == f)
            b.setStyleSheet(btn_style(fi == f, 13))
        self.canvas.update()

    def set_tool(self, t):
        self.tool = t
        self.pen_btn.setStyleSheet(btn_style(t == "pen", 13))
        self.fill_btn.setStyleSheet(btn_style(t == "fill", 13))

    def update_labels(self):
        self.color_button.setText(f"Renk ({len(self.mix_colors)})")
        self.mix_button.setText(f"Karışım: {MIX_SHORT.get(self.mix_mode, '')}")
        self.angle_button.setText(f"Açı {self.mix_angle}°")
        sw = QPixmap(14, 14)
        sw.fill(self.pen_color)
        self.color_button.setIcon(QIcon(sw))

    def refresh_preview(self):
        self.preview.setPixmap(iso_cube_pixmap(self.faces, 120))
        self.canvas.update()

    def change_angle(self, d):
        self.mix_angle = (self.mix_angle + d) % 360
        self.update_labels()

    # -- boyama
    def target_faces(self):
        return range(6) if self.all_faces.isChecked() else [self.cur_face]

    def mix_color(self, x, y):
        cols = self.mix_colors
        i, j, fr = mix_select(len(cols), self.mix_mode, x * 16, y * 16, self.step, self.mix_angle, self.seq)
        self.seq += 1
        self.step += 16.0
        a, b = cols[i], cols[j]
        if i == j or fr <= 0:
            return QColor(a)
        return QColor(int(a.red() + (b.red() - a.red()) * fr),
                      int(a.green() + (b.green() - a.green()) * fr),
                      int(a.blue() + (b.blue() - a.blue()) * fr))

    def begin_stroke(self):
        self.step = 0.0

    def apply_pixel(self, x, y):
        col = self.mix_color(x, y)
        for f in self.target_faces():
            self.faces[f].setPixelColor(x, y, col)
        self.refresh_preview()

    def eyedrop(self, x, y):
        c = self.faces[self.cur_face].pixelColor(x, y)
        c.setAlpha(255)
        self.pen_color = QColor(c)
        self.mix_colors = [QColor(c)]
        self.update_labels()

    def flood(self, x, y):
        img = self.faces[self.cur_face]
        target = img.pixel(x, y)
        seen, stack = set(), [(x, y)]
        self.begin_stroke()
        while stack:
            cx, cy = stack.pop()
            if (cx, cy) in seen or not (0 <= cx < TILE and 0 <= cy < TILE) or img.pixel(cx, cy) != target:
                continue
            seen.add((cx, cy))
            stack.extend([(cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)])
        for cx, cy in sorted(seen):
            self.apply_pixel(cx, cy)
        self.refresh_preview()

    def fill_face(self):
        self.begin_stroke()
        for y in range(TILE):
            for x in range(TILE):
                self.apply_pixel(x, y)
        self.refresh_preview()

    def copy_face_to_all(self):
        src = self.faces[self.cur_face]
        for f in range(6):
            if f != self.cur_face:
                self.faces[f] = src.copy()
        self.refresh_preview()

    # -- renk seçimi (Drawing_editor.py mantığı)
    def _push_history(self):
        h = [QColor(c) for c in self.mix_colors]
        if not self.mix_history or [c.name() for c in self.mix_history[-1]] != [c.name() for c in h]:
            self.mix_history.append(h)
            if len(self.mix_history) > 24:
                self.mix_history.pop(0)

    def change_color(self):
        dlg = CircleBrightnessDialog(initialColor=self.pen_color, parent=self)
        dlg.move(self.color_button.mapToGlobal(QPoint(0, self.color_button.height())))
        if dlg.exec_():
            sel = dlg.getSelectedColor()
            self.pen_color = sel
            self.mix_colors = [sel]
            self._push_history()
            self.update_color_menu()
            self.update_labels()

    def add_color_to_mix(self):
        dlg = CircleBrightnessDialog(initialColor=self.pen_color, parent=self)
        dlg.move(self.color_button.mapToGlobal(QPoint(0, self.color_button.height())))
        if dlg.exec_():
            sel = dlg.getSelectedColor()
            if len(self.mix_colors) >= 6:
                self.mix_colors.pop(0)
            self.mix_colors.append(sel)
            self.pen_color = sel
            self._push_history()
            self.update_color_menu()
            self.update_labels()

    def update_color_menu(self):
        m = self.color_menu
        m.clear()
        m.addAction("Tek Renk Seç").triggered.connect(self.change_color)
        m.addAction("Karışıma Renk Ekle (+)").triggered.connect(self.add_color_to_mix)
        m.addSeparator()
        wa = QWidgetAction(m)
        lab = QLabel("  Renk Geçmişi:", m)
        lab.setStyleSheet("color: #aaa; font-weight: bold; padding: 2px 5px;")
        wa.setDefaultWidget(lab)
        m.addAction(wa)
        for colors in reversed(self.mix_history):
            wa = QWidgetAction(m)
            strip = ColorHistoryStrip(colors)
            strip.colorSelected.connect(self.on_history_selected)
            wa.setDefaultWidget(strip)
            m.addAction(wa)

    def on_history_selected(self, single, mix):
        if single:
            self.pen_color = QColor(single)
            self.mix_colors = [QColor(single)]
        elif mix:
            self.mix_colors = [QColor(c) for c in mix]
            self.pen_color = QColor(mix[0])
        self.color_menu.close()
        self.update_labels()

    def show_mix_menu(self):
        menu = QMenu(self)
        menu.setStyleSheet(MENU_STYLE)
        menu.addAction("--- Karışım Modları ---").setEnabled(False)
        for label, key in MIX_MODES:
            act = menu.addAction(label)
            act.setCheckable(True)
            act.setChecked(self.mix_mode == key)
            act.triggered.connect(lambda _c, k=key: self._set_mix_mode(k))
        menu.addSeparator()
        menu.addAction(f"--- Aktif Karışım Renkleri ({len(self.mix_colors)}) ---").setEnabled(False)
        wa = QWidgetAction(menu)
        strip = ColorHistoryStrip(self.mix_colors)
        strip.colorSelected.connect(self.on_history_selected)
        wa.setDefaultWidget(strip)
        menu.addAction(wa)
        menu.exec_(self.mix_button.mapToGlobal(QPoint(0, self.mix_button.height())))

    def _set_mix_mode(self, k):
        self.mix_mode = k
        self.update_labels()

    # -- kapanış
    def _ok(self):
        self.name = self.name_edit.text().strip() or "Küp"
        self.accept()

    def _ok_new(self):
        self.as_new = True
        self._ok()

    def done(self, r):
        self.win.mix_colors = [QColor(c) for c in self.mix_colors]
        self.win.mix_history = self.mix_history
        self.win.ed_mix_mode = self.mix_mode
        self.win.ed_mix_angle = self.mix_angle
        super().done(r)


# ----------------------------------------------------------------------------
# Ana pencere
# ----------------------------------------------------------------------------
class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1320, 820)
        self.scene = Scene()
        self.order = []
        self.brush_ids = []
        self.thumbs = {}
        self.tool = "draw"
        self.mix_mode = "random"
        self.mix_angle = 0
        self.mix_colors = [QColor("#ffffff")]
        self.mix_history = [[QColor("#ffffff")]]
        self.ed_mix_mode = "random"
        self.ed_mix_angle = 0
        self.undo_stack, self.redo_stack = [], []
        self.current_path = None
        self.modified = False
        self.last_dir = os.path.expanduser("~")
        self.cursor_cell = None
        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.setInterval(400)
        self.save_timer.timeout.connect(self.save_library)

        self.load_library()
        self._build_ui()
        self.refresh_lists()
        self.set_tool("draw")
        self.update_title()
        self.update_status()

        for seq, fn in (("Ctrl+Z", self.undo), ("Ctrl+Y", self.redo), ("Ctrl+Shift+Z", self.redo),
                        ("Ctrl+S", self.save), ("Ctrl+Shift+S", self.save_as), ("Ctrl+O", self.open_file),
                        ("Ctrl+N", self.new_file), ("1", lambda: self.set_tool("draw")),
                        ("2", lambda: self.set_tool("erase")), ("3", lambda: self.set_tool("paint"))):
            QShortcut(QKeySequence(seq), self, activated=fn)

    # -- arayüz
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        bar = QFrame()
        bar.setObjectName("topbar")
        bar.setStyleSheet("#topbar { background-color: #222; border-bottom: 1px solid #111; }")
        h = QHBoxLayout(bar)
        h.setContentsMargins(8, 6, 8, 6)
        h.setSpacing(6)

        def mk(text, style=14):
            b = QPushButton(text)
            b.setStyleSheet(btn_style(False, style))
            b.setFocusPolicy(Qt.NoFocus)
            b.setCursor(Qt.PointingHandCursor)
            return b

        self.file_button = mk("Dosya")
        fm = QMenu(self)
        fm.setStyleSheet(MENU_STYLE)
        fm.addAction("Yeni\tCtrl+N").triggered.connect(self.new_file)
        fm.addAction("Aç...\tCtrl+O").triggered.connect(self.open_file)
        fm.addAction("Kaydet\tCtrl+S").triggered.connect(self.save)
        fm.addAction("Farklı Kaydet...\tCtrl+Shift+S").triggered.connect(self.save_as)
        fm.addSeparator()
        self.border_action = fm.addAction("Küp kenar çizgileri")
        self.border_action.setCheckable(True)
        self.border_action.setChecked(True)
        self.border_action.toggled.connect(self.toggle_border)
        self.file_button.setMenu(fm)
        h.addWidget(self.file_button)

        self.save_button = mk("")
        self.save_button.setIcon(create_svg_icon(SVG_SAVE_ICON, 20))
        self.save_button.setToolTip("Kaydet (Ctrl+S)")
        self.save_button.clicked.connect(self.save)
        h.addWidget(self.save_button)
        self.undo_button = mk("")
        self.undo_button.setIcon(create_svg_icon(SVG_UNDO_ICON, 20))
        self.undo_button.setToolTip("Geri al (Ctrl+Z)")
        self.undo_button.clicked.connect(self.undo)
        h.addWidget(self.undo_button)
        self.redo_button = mk("")
        self.redo_button.setIcon(create_svg_icon(SVG_REDO_ICON, 20))
        self.redo_button.setToolTip("Yinele (Ctrl+Y)")
        self.redo_button.clicked.connect(self.redo)
        h.addWidget(self.redo_button)

        self.tool_buttons = {}
        for key, label, tip in (("draw", "Çiz", "Çiz (1)"), ("erase", "Sil", "Sil (2) — Ctrl+Sol tık da siler"),
                                ("paint", "Boya", "Var olan küpü seçili küple değiştir (3)")):
            b = mk(label)
            b.setToolTip(tip)
            b.clicked.connect(lambda _c, k=key: self.set_tool(k))
            h.addWidget(b)
            self.tool_buttons[key] = b

        self.editor_button = mk("Küp Editörü")
        self.editor_button.clicked.connect(lambda: self.open_editor(None))
        h.addWidget(self.editor_button)

        self.mix_button = mk("")
        self.mix_button.setToolTip("Birden fazla küp seçiliyse (Ctrl+tık) karışım modu")
        self.mix_button.clicked.connect(self.show_mix_menu)
        h.addWidget(self.mix_button)
        self.angle_button = AngleButton("")
        self.angle_button.setStyleSheet(btn_style(False, 14))
        self.angle_button.setFocusPolicy(Qt.NoFocus)
        self.angle_button.setToolTip("Açısal karışım açısı (tıkla +15°, tekerlekle değiştir)")
        self.angle_button.clicked.connect(lambda: self.change_angle(15))
        self.angle_button.wheel.connect(self.change_angle)
        h.addWidget(self.angle_button)

        self.all_button = mk("☰")
        self.all_button.setToolTip("Tüm küplerin listesi (sağ tık ile de açılır)")
        self.all_button.clicked.connect(lambda: self.show_cube_menu(QCursor.pos()))
        h.addWidget(self.all_button)

        self.strip = CubeListWidget(self, cols=0, size=44)
        self.strip.picked.connect(self.select_cube)
        self.strip.context.connect(self.cube_context_menu)
        self.strip_area = QScrollArea()
        self.strip_area.setWidget(self.strip)
        self.strip_area.setWidgetResizable(False)
        self.strip_area.setFrameShape(QFrame.NoFrame)
        self.strip_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.strip_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.strip_area.setFixedHeight(self.strip.height() + 2)
        self.strip_area.setStyleSheet("QScrollArea { background-color: #262626; border-radius: 6px; }")
        h.addWidget(self.strip_area, 1)
        root.addWidget(bar)

        self.viewport = Viewport(self)
        root.addWidget(self.viewport, 1)

        sb = QFrame()
        sb.setStyleSheet("QFrame { background-color: #222; } QLabel { color: #bbb; font-size: 12px; }")
        sh = QHBoxLayout(sb)
        sh.setContentsMargins(10, 3, 10, 3)
        hint = QLabel("Sol tık: çiz · Ctrl+Sol: sil · Orta tuş: döndür · Shift+Orta: kaydır · Tekerlek: yakınlaş · Sağ tık: küp listesi")
        self.info_label = QLabel("")
        sh.addWidget(hint, 1)
        sh.addWidget(self.info_label)
        root.addWidget(sb)
        self.update_mix_labels()

    def set_tool(self, t):
        self.tool = t
        for k, b in self.tool_buttons.items():
            b.setStyleSheet(btn_style(k == t, 14))
        if hasattr(self, "viewport"):
            self.viewport.hover = None
            self.viewport.update()

    def update_mix_labels(self):
        self.mix_button.setText(f"Karışım: {MIX_SHORT.get(self.mix_mode, '')}")
        self.angle_button.setText(f"Açı {self.mix_angle}°")

    def change_angle(self, d):
        self.mix_angle = (self.mix_angle + d) % 360
        self.update_mix_labels()

    def show_mix_menu(self):
        menu = QMenu(self)
        menu.setStyleSheet(MENU_STYLE)
        menu.addAction("--- Karışım Modları ---").setEnabled(False)
        for label, key in MIX_MODES:
            act = menu.addAction(label)
            act.setCheckable(True)
            act.setChecked(self.mix_mode == key)
            act.triggered.connect(lambda _c, k=key: self._set_mix_mode(k))
        menu.addSeparator()
        menu.addAction(f"Karışımdaki küp sayısı: {len(self.brush_ids)}  (Ctrl+tık ile ekle/çıkar)").setEnabled(False)
        menu.exec_(self.mix_button.mapToGlobal(QPoint(0, self.mix_button.height())))

    def _set_mix_mode(self, k):
        self.mix_mode = k
        self.update_mix_labels()

    def toggle_border(self, flag):
        self.scene.set_border(flag)
        self.viewport.update()

    # -- küp kitaplığı
    def load_library(self):
        order = []
        try:
            with open(LIB_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            for cid in data.get("order", []):
                try:
                    cube = Cube.from_json(cid, data["cubes"][cid])
                    self.scene.register_cube(cube)
                    order.append(cid)
                except Exception:
                    continue
            pal = []
            for lst in data.get("palette", []):
                cols = [QColor(c) for c in lst if QColor(c).isValid()]
                if cols:
                    pal.append(cols)
            if pal:
                self.mix_history = pal
                self.mix_colors = [QColor(c) for c in pal[-1]]
        except Exception:
            pass
        if not order:
            for cid, name, col in (("siyah", "Siyah", "#000000"), ("beyaz", "Beyaz", "#ffffff")):
                self.scene.register_cube(Cube.solid(cid, name, col))
                order.append(cid)
        self.order = order
        self.brush_ids = [order[0]]

    def save_library(self):
        try:
            os.makedirs(CFG_DIR, exist_ok=True)
            data = {"order": list(self.order),
                    "cubes": {cid: self.scene.cubes[cid].to_json() for cid in self.order},
                    "palette": [[c.name() for c in lst] for lst in self.mix_history[-24:]]}
            tmp = LIB_PATH + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
            os.replace(tmp, LIB_PATH)
        except Exception:
            traceback.print_exc()

    def schedule_save(self):
        self.save_timer.start()

    def cube_name(self, cid):
        c = self.scene.cubes.get(cid)
        return c.name if c else ""

    def thumb(self, cid, size):
        key = (cid, size)
        pm = self.thumbs.get(key)
        if pm is None:
            pm = iso_cube_pixmap(self.scene.cubes[cid].faces, size)
            self.thumbs[key] = pm
        return pm

    def invalidate_thumb(self, cid):
        self.thumbs = {k: v for k, v in self.thumbs.items() if k[0] != cid}

    def refresh_lists(self):
        self.strip.refresh()
        self.strip_area.horizontalScrollBar().setValue(0)

    def select_cube(self, cid, additive=False):
        if cid not in self.scene.cubes:
            return
        if additive:
            if cid in self.brush_ids:
                if len(self.brush_ids) > 1:
                    self.brush_ids.remove(cid)
            else:
                self.brush_ids.append(cid)
        else:
            self.brush_ids = [cid]
        rest = [c for c in self.order if c not in self.brush_ids]
        self.order = list(self.brush_ids) + rest        # seçilenler listenin başına gider
        self.refresh_lists()
        self.update_status()
        self.schedule_save()

    def pick_brush_id(self, u, v, step, seq):
        ids = self.brush_ids
        if len(ids) == 1:
            return ids[0]
        i, j, fr = mix_select(len(ids), self.mix_mode, u * 16, v * 16, step, self.mix_angle, seq)
        return ids[j if fr >= 0.5 else i]

    def show_cube_menu(self, gpos):
        menu = QMenu(self)
        menu.setStyleSheet(MENU_STYLE)
        menu.addAction("--- Küpler (Ctrl+tık: karışıma ekle) ---").setEnabled(False)
        lw = CubeListWidget(self, cols=6, size=44)
        area = QScrollArea()
        area.setWidget(lw)
        area.setFrameShape(QFrame.NoFrame)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        area.setFixedSize(lw.width() + 16, min(lw.height() + 4, 340))

        def picked(cid, ctrl):
            self.select_cube(cid, ctrl)
            lw.refresh()
            if not ctrl:
                menu.close()

        lw.picked.connect(picked)
        lw.context.connect(lambda cid, p: (menu.close(), self.cube_context_menu(cid, p)))
        wa = QWidgetAction(menu)
        wa.setDefaultWidget(area)
        menu.addAction(wa)
        menu.addSeparator()
        menu.addAction("＋ Yeni küp (Küp Editörü)").triggered.connect(lambda: self.open_editor(None))
        menu.exec_(gpos)

    def cube_context_menu(self, cid, gpos):
        menu = QMenu(self)
        menu.setStyleSheet(MENU_STYLE)
        a_edit = menu.addAction("Düzenle")
        a_copy = menu.addAction("Kopyala")
        a_del = menu.addAction("Listeden kaldır")
        act = menu.exec_(gpos)
        if act == a_edit:
            self.open_editor(cid)
        elif act == a_copy:
            src = self.scene.cubes[cid]
            new = Cube(uuid.uuid4().hex[:12], src.name + " kopya", src.copy_faces())
            self.add_cube(new)
        elif act == a_del:
            if len(self.order) <= 1:
                QMessageBox.information(self, APP_NAME, "Listede en az bir küp kalmalı.")
                return
            self.order.remove(cid)
            self.brush_ids = [b for b in self.brush_ids if b != cid] or [self.order[0]]
            self.refresh_lists()
            self.schedule_save()

    def add_cube(self, cube):
        try:
            self.scene.register_cube(cube)
        except RuntimeError as e:
            QMessageBox.warning(self, APP_NAME, str(e))
            return
        self.order.insert(0, cube.id)
        self.select_cube(cube.id)
        self.viewport.update()

    def open_editor(self, cid):
        if cid:
            cube = self.scene.cubes[cid]
            faces, name, editing = cube.copy_faces(), cube.name, True
        else:
            base = self.scene.cubes[self.brush_ids[0]]
            faces, name, editing = base.copy_faces(), f"Küp {len(self.order) + 1}", False
        dlg = CubeEditorDialog(self, faces, name, editing, parent=self)
        ok = dlg.exec_() == QDialog.Accepted
        self.schedule_save()                          # renk geçmişi değişmiş olabilir
        if not ok:
            return
        if editing and not dlg.as_new:
            cube.faces, cube.name = dlg.faces, dlg.name
            self.scene.register_cube(cube)
            self.invalidate_thumb(cube.id)
            if cube.id not in self.order:
                self.order.insert(0, cube.id)
            self.select_cube(cube.id)
            self.viewport.update()
        else:
            self.add_cube(Cube(uuid.uuid4().hex[:12], dlg.name, dlg.faces))

    # -- geri al / yinele
    def push_undo(self, changes):
        if not changes:
            return
        self.undo_stack.append(changes)
        if len(self.undo_stack) > 300:
            self.undo_stack.pop(0)
        self.redo_stack.clear()
        self.on_world_changed()

    def undo(self):
        if not self.undo_stack:
            return
        ch = self.undo_stack.pop()
        for cell, old, new in reversed(ch):
            if old is None:
                self.scene.remove(cell)
            else:
                self.scene.put(cell, old)
        self.redo_stack.append(ch)
        self.on_world_changed()
        self.viewport.update()

    def redo(self):
        if not self.redo_stack:
            return
        ch = self.redo_stack.pop()
        for cell, old, new in ch:
            if new is None:
                self.scene.remove(cell)
            else:
                self.scene.put(cell, new)
        self.undo_stack.append(ch)
        self.on_world_changed()
        self.viewport.update()

    def on_world_changed(self, final=True):
        if not self.modified:
            self.modified = True
            self.update_title()
        self.update_status()

    def set_cursor_info(self, cell):
        self.cursor_cell = cell
        self.update_status()

    def update_status(self):
        cell = f"{self.cursor_cell[0]}, {self.cursor_cell[1]}, {self.cursor_cell[2]}" if self.cursor_cell else "-"
        name = self.cube_name(self.brush_ids[0]) if self.brush_ids else ""
        extra = f" +{len(self.brush_ids) - 1}" if len(self.brush_ids) > 1 else ""
        self.info_label.setText(f"Fırça: {name}{extra}   |   Küp: {len(self.scene.world)}   |   İmleç: {cell}")

    def update_title(self):
        name = os.path.basename(self.current_path) if self.current_path else "Adsız"
        self.setWindowTitle(f"{'*' if self.modified else ''}{name} — {APP_NAME}")

    # -- dosya (.mkj)
    def confirm_discard(self):
        if not self.modified:
            return True
        r = QMessageBox.question(self, APP_NAME, "Değişiklikler kaydedilsin mi?",
                                 QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Save)
        if r == QMessageBox.Save:
            return self.save()
        return r == QMessageBox.Discard

    def new_file(self):
        if not self.confirm_discard():
            return
        self.scene.clear_world()
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.current_path = None
        self.modified = False
        self.viewport.reset_camera()
        self.update_title()
        self.update_status()

    def save(self):
        if not self.current_path:
            return self.save_as()
        return self._save_to(self.current_path)

    def save_as(self):
        path, _ = QFileDialog.getSaveFileName(self, "Kaydet", self.last_dir, "Küp Çizim (*.mkj)")
        if not path:
            return False
        if not path.lower().endswith(".mkj"):
            path += ".mkj"
        return self._save_to(path)

    def _save_to(self, path):
        try:
            used = sorted(set(self.scene.world.values()))
            idx = {cid: i for i, cid in enumerate(used)}
            flat = []
            for (x, y, z), bid in self.scene.world.items():
                flat.extend((x, y, z, idx[bid]))
            data = {"format": "mkj", "version": 1,
                    "camera": self.viewport.get_camera(),
                    "cube_ids": used,
                    "cubes": {cid: self.scene.cubes[cid].to_json() for cid in used},
                    "blocks": flat}
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
            os.replace(tmp, path)
        except Exception as e:
            QMessageBox.critical(self, APP_NAME, f"Kaydedilemedi:\n{e}")
            return False
        self.current_path = path
        self.last_dir = os.path.dirname(path)
        self.modified = False
        self.update_title()
        return True

    def open_file(self):
        if not self.confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Aç", self.last_dir, "Küp Çizim (*.mkj);;Tüm dosyalar (*)")
        if path:
            self.load_path(path)

    def load_path(self, path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            ids = data["cube_ids"]
            remap = []
            for cid in ids:
                cube = Cube.from_json(cid, data["cubes"][cid])
                ex = self.scene.cubes.get(cid)
                if ex is None:
                    self.scene.register_cube(cube)
                    use = cid
                elif ex.same_as(cube):
                    use = cid
                else:
                    use = uuid.uuid4().hex[:12]
                    cube.id = use
                    self.scene.register_cube(cube)
                if use not in self.order:
                    self.order.append(use)
                remap.append(use)
            flat = data["blocks"]
            items = [((flat[i], flat[i + 1], flat[i + 2]), remap[flat[i + 3]]) for i in range(0, len(flat), 4)]
        except Exception as e:
            QMessageBox.critical(self, APP_NAME, f"Dosya açılamadı:\n{e}")
            return
        self.scene.clear_world()
        self.scene.load_blocks(items)
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.viewport.set_camera(data.get("camera", {}))
        self.current_path = path
        self.last_dir = os.path.dirname(path)
        self.modified = False
        self.refresh_lists()
        self.update_title()
        self.update_status()
        self.schedule_save()
        self.viewport.update()

    def closeEvent(self, e):
        if not self.confirm_discard():
            e.ignore()
            return
        self.save_timer.stop()
        self.save_library()
        e.accept()


# ----------------------------------------------------------------------------
def apply_dark_palette(app):
    app.setStyle("Fusion")
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor("#2b2b2b"))
    pal.setColor(QPalette.WindowText, Qt.white)
    pal.setColor(QPalette.Base, QColor("#1e1e1e"))
    pal.setColor(QPalette.AlternateBase, QColor("#2b2b2b"))
    pal.setColor(QPalette.ToolTipBase, QColor("#333333"))
    pal.setColor(QPalette.ToolTipText, Qt.white)
    pal.setColor(QPalette.Text, Qt.white)
    pal.setColor(QPalette.Button, QColor("#333333"))
    pal.setColor(QPalette.ButtonText, Qt.white)
    pal.setColor(QPalette.BrightText, Qt.red)
    pal.setColor(QPalette.Highlight, QColor("#4a7bd0"))
    pal.setColor(QPalette.HighlightedText, Qt.white)
    pal.setColor(QPalette.Disabled, QPalette.Text, QColor("#777777"))
    pal.setColor(QPalette.Disabled, QPalette.ButtonText, QColor("#777777"))
    app.setPalette(pal)


def main():
    sys.excepthook = lambda t, v, tb: traceback.print_exception(t, v, tb)
    fmt = QSurfaceFormat()
    fmt.setVersion(2, 1)
    fmt.setDepthBufferSize(24)
    fmt.setSamples(4)
    QSurfaceFormat.setDefaultFormat(fmt)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    apply_dark_palette(app)
    win = MainWindow()
    win.show()
    if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
        win.load_path(sys.argv[1])
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
