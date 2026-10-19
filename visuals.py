"""
Kavram - görsel katman.

Yalnızca çizim yapar; devre mantığına dokunmaz.
  * draw_board : ana kart (PCB, izler, soketler, DIMM, PCIe, M.2, kondansatörler)
  * draw_part  : her devre parçasının fiziksel görünümü
  * draw_pin   : pin pedi (duruma göre yeşil / kırmızı parlama)
"""
import random

from PyQt5.QtCore import Qt, QPointF, QRectF
from PyQt5.QtGui import QBrush, QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient

BOARD_RECT = QRectF(-520, -340, 2160, 1400)

M = 6          # gövdenin yatay iç boşluğu; bacaklar bu aralıkta görünür
PIN_R = 6.0    # pin pedi yarıçapı
PIN_HIT = 11.0 # dokunmatik için büyütülmüş tıklama yarıçapı

GREEN = "#22c55e"
BLUE = "#3b82f6"
RED = "#ef4444"
YELLOW = "#facc15"
TEXT = "#e5e7eb"
MUTED = "#8a94a6"


# ---------- Yardımcılar ----------
def grad(rect, top, bottom):
    g = QLinearGradient(rect.topLeft(), rect.bottomLeft())
    g.setColorAt(0.0, QColor(top))
    g.setColorAt(1.0, QColor(bottom))
    return QBrush(g)


def text(p, rect, s, size=9, color=TEXT, bold=False, align=Qt.AlignCenter):
    f = QFont()
    f.setPointSize(size)
    f.setBold(bold)
    p.setFont(f)
    p.setPen(QColor(color))
    p.drawText(rect, align, s)


def _legs(p, pins, w):
    """Parça bacakları: pinden gövdeye uzanan gümüş şeritler."""
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#cbd5e1"))
    for pin in pins:
        y = pin.y - 2.5
        if pin.x == 0:
            p.drawRect(QRectF(0, y, M + 1, 5))
        else:
            p.drawRect(QRectF(w - M - 1, y, M + 1, 5))


def _pin_labels(p, pins, w):
    if len(pins) < 2:
        return
    f = QFont()
    f.setPointSize(7)
    p.setFont(f)
    p.setPen(QColor("#94a3b8"))
    for pin in pins:
        if pin.x == 0:
            r = QRectF(M + 4, pin.y - 7, 30, 14)
            p.drawText(r, Qt.AlignLeft | Qt.AlignVCenter, pin.id)
        else:
            r = QRectF(w - M - 34, pin.y - 7, 30, 14)
            p.drawText(r, Qt.AlignRight | Qt.AlignVCenter, pin.id)


def _glow_rect(p, r, color, radius):
    """Gövde etrafında yumuşak parlama."""
    c = QColor(color)
    for i, alpha in enumerate((40, 25, 12)):
        pen = QPen(QColor(c.red(), c.green(), c.blue(), alpha), 4 + i * 4)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(r, radius, radius)


# ---------- Pinler ----------
def draw_pin(p, hi, bad):
    """Pin, orijinin ortasına çizilir."""
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    if hi or bad:
        c = QColor(RED if bad else GREEN)
        glow = QRadialGradient(QPointF(0, 0), 15)
        glow.setColorAt(0.0, QColor(c.red(), c.green(), c.blue(), 170))
        glow.setColorAt(1.0, QColor(c.red(), c.green(), c.blue(), 0))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(glow))
        p.drawEllipse(QPointF(0, 0), 15, 15)
    fill = RED if bad else ("#4ade80" if hi else "#64748b")
    p.setPen(QPen(QColor("#f8fafc" if (hi or bad) else "#cbd5e1"), 1.2))
    p.setBrush(QColor(fill))
    p.drawEllipse(QPointF(0, 0), PIN_R, PIN_R)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#0b0f14"))
    p.drawEllipse(QPointF(0, 0), 2.6, 2.6)
    p.restore()


def pin_shape():
    """Dokunmatik için büyütülmüş pin tıklama alanı (fare ve parmak için)."""
    path = QPainterPath()
    path.addEllipse(QPointF(0, 0), PIN_HIT, PIN_HIT)
    return path


# ---------- Ana kart ----------
def _socket(p, r):
    p.setPen(QPen(QColor("#0b0f14"), 2))
    p.setBrush(grad(r, "#2a2f38", "#15181f"))
    p.drawRoundedRect(r, 14, 14)
    inner = r.adjusted(22, 22, -22, -22)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#0a0c10"))
    p.drawRoundedRect(inner, 8, 8)
    p.setBrush(QColor("#c8a24a"))
    n = 16
    for i in range(n):
        for j in range(n):
            x = inner.left() + 12 + i * (inner.width() - 24) / (n - 1)
            y = inner.top() + 12 + j * (inner.height() - 24) / (n - 1)
            p.drawEllipse(QPointF(x, y), 1.6, 1.6)
    text(p, QRectF(r.left(), r.bottom() + 4, r.width(), 16), "CPU SOKETİ · KAVRAM-LGA", 8, "#dfe9e4")


def _dimm(p, r, label):
    p.setPen(QPen(QColor("#0b0f14"), 1))
    p.setBrush(grad(r, "#2b3240", "#171c26"))
    p.drawRoundedRect(r, 3, 3)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#d6dbe3"))
    p.drawRoundedRect(QRectF(r.left() - 6, r.top() - 4, 10, r.height() + 8), 3, 3)
    p.drawRoundedRect(QRectF(r.right() - 4, r.top() - 4, 10, r.height() + 8), 3, 3)
    p.setBrush(QColor("#0a0c10"))
    p.drawRect(QRectF(r.center().x() - 2, r.top(), 4, r.height()))
    text(p, QRectF(r.left() - 90, r.top(), 84, r.height()), label, 8, "#dfe9e4",
         False, Qt.AlignRight | Qt.AlignVCenter)


def _pcie(p, r):
    p.setPen(QPen(QColor("#0b0f14"), 1))
    p.setBrush(grad(r, "#2b3240", "#171c26"))
    p.drawRoundedRect(r, 4, 4)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#c8a24a"))
    x = r.left() + 10
    while x < r.right() - 14:
        p.drawRect(QRectF(x, r.bottom() - 5, 6, 3))
        x += 9
    text(p, QRectF(r.left(), r.top() - 18, 160, 16), "PCIe x16 · PCIE1", 8, "#dfe9e4",
         False, Qt.AlignLeft | Qt.AlignVCenter)


def _heatsink(p, r, label):
    p.setPen(QPen(QColor("#0b0f14"), 1))
    p.setBrush(grad(r, "#9ca3af", "#4b5563"))
    p.drawRoundedRect(r, 6, 6)
    p.setPen(QPen(QColor(0, 0, 0, 90), 2))
    for i in range(1, 12):
        x = r.left() + i * r.width() / 12.0
        p.drawLine(QPointF(x, r.top() + 6), QPointF(x, r.bottom() - 6))
    text(p, QRectF(r.left(), r.bottom() + 4, r.width(), 16), label, 8, "#dfe9e4")


def _cap(p, x, y):
    body = QRectF(x, y, 14, 28)
    p.setPen(Qt.NoPen)
    p.setBrush(grad(body, "#1f2937", "#0b0f14"))
    p.drawRoundedRect(body, 3, 3)
    p.setBrush(QColor("#cbd5e1"))
    p.drawEllipse(QRectF(x, y, 14, 6))


def draw_board(p, rect=BOARD_RECT):
    """Ana kartın tamamını çizer. Her seferinde aynı görünüm (sabit tohum)."""
    p.save()
    p.setRenderHint(QPainter.Antialiasing)

    # PCB gövdesi ve kenarlar
    p.setPen(QPen(QColor("#062218"), 4))
    p.setBrush(grad(rect, "#17694d", "#0a3022"))
    p.drawRoundedRect(rect, 36, 36)
    p.setPen(QPen(QColor(255, 255, 255, 22), 2))
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(rect.adjusted(8, 8, -8, -8), 30, 30)

    rnd = random.Random(7)

    # Bakır izler
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(QColor(190, 140, 80, 55), 3, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    for _ in range(170):
        x = rnd.randrange(int(rect.left()) + 40, int(rect.right()) - 40, 10)
        y = rnd.randrange(int(rect.top()) + 40, int(rect.bottom()) - 40, 10)
        path = QPainterPath(QPointF(x, y))
        for _ in range(rnd.randint(2, 5)):
            step = rnd.randrange(30, 200, 10) * rnd.choice((-1, 1))
            if rnd.random() < 0.5:
                x += step
            else:
                y += step
            path.lineTo(x, y)
        p.drawPath(path)

    # Lehim pedleri
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(200, 160, 60, 140))
    for _ in range(110):
        x = rnd.uniform(rect.left() + 40, rect.right() - 40)
        y = rnd.uniform(rect.top() + 40, rect.bottom() - 40)
        p.drawEllipse(QPointF(x, y), 4, 4)

    # Montaj delikleri
    for cx, cy in [
        (rect.left() + 30, rect.top() + 30), (rect.right() - 30, rect.top() + 30),
        (rect.left() + 30, rect.bottom() - 30), (rect.right() - 30, rect.bottom() - 30),
    ]:
        p.setPen(QPen(QColor(200, 160, 60, 170), 3))
        p.setBrush(QColor("#041a12"))
        p.drawEllipse(QPointF(cx, cy), 11, 11)

    # CPU soketi ve kondansatör sırası
    sock = QRectF(rect.right() - 350, rect.top() + 90, 260, 260)
    _socket(p, sock)
    for i in range(10):
        _cap(p, sock.left() + 6 + i * 24, sock.bottom() + 30)

    # Dört DIMM (RAM) yuvası
    for i in range(4):
        r = QRectF(rect.right() - 440, rect.top() + 440 + i * 36, 340, 18)
        _dimm(p, r, f"DIMM_A{i + 1}")

    # PCIe yuvası ve M.2 (SSD) yuvası
    _pcie(p, QRectF(rect.left() + 200, rect.bottom() - 150, 760, 22))
    m2 = QRectF(rect.left() + 1020, rect.bottom() - 150, 96, 22)
    p.setPen(QPen(QColor("#0b0f14"), 1))
    p.setBrush(grad(m2, "#2b3240", "#171c26"))
    p.drawRoundedRect(m2, 3, 3)
    text(p, QRectF(m2.left(), m2.top() - 18, m2.width(), 16), "M.2 · SSD", 8, "#dfe9e4")

    # Yonga seti soğutucusu
    _heatsink(p, QRectF(rect.right() - 420, rect.bottom() - 420, 220, 120), "CHIPSET")

    # Baskı yazılar
    silk = QColor(230, 240, 235, 120)
    text(p, QRectF(rect.left() + 60, rect.top() + 60, 320, 20), "KAVRAM-ATX  ·  REV 2.0",
         10, silk, True, Qt.AlignLeft | Qt.AlignVCenter)
    text(p, QRectF(rect.left() + 60, rect.top() + 84, 320, 16),
         "Devre tahtası · sürükle, bağla, çalıştır", 8, silk, False, Qt.AlignLeft | Qt.AlignVCenter)
    text(p, QRectF(rect.left() + 1020, rect.top() + 24, 300, 16), "PWR 24P", 8, silk,
         False, Qt.AlignLeft | Qt.AlignVCenter)

    p.restore()


# ---------- Parçalar ----------
def _chip(p, r, name, state, on):
    body = r.adjusted(M, 4, -M, -4)
    p.setPen(QPen(QColor("#0b0d12"), 1))
    p.setBrush(grad(body, "#2a303b", "#12151c"))
    p.drawRoundedRect(body, 7, 7)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#07090d"))
    p.drawEllipse(QPointF(body.left() + 11, body.top() + 11), 3.2, 3.2)
    text(p, QRectF(body.left(), body.top() + 8, body.width(), 18), name, 9, TEXT, True)
    text(p, QRectF(body.left(), body.bottom() - 22, body.width(), 16), state,
         8, GREEN if on else MUTED, on)


def _vcc(p, r, name, state, on):
    body = r.adjusted(M, 4, -M, -4)
    p.setPen(QPen(QColor("#3f1d1d"), 1))
    p.setBrush(grad(body, "#dc2626", "#7f1d1d"))
    p.drawRoundedRect(body, 8, 8)
    text(p, QRectF(body.left(), body.top() + 6, body.width(), 18), "+  Vcc", 10, "#ffffff", True)
    text(p, QRectF(body.left(), body.bottom() - 22, body.width(), 16), state, 9, "#fee2e2", True)


def _gnd(p, r, name, state, on):
    body = r.adjusted(M, 4, -M, -4)
    p.setPen(QPen(QColor("#0b0f14"), 1))
    p.setBrush(grad(body, "#334155", "#111827"))
    p.drawRoundedRect(body, 8, 8)
    cx = body.center().x()
    p.setPen(QPen(QColor("#cbd5e1"), 2))
    for i, half in enumerate((18, 12, 6)):
        y = body.center().y() - 6 + i * 6
        p.drawLine(QPointF(cx - half, y), QPointF(cx + half, y))
    text(p, QRectF(body.left(), body.top() + 4, body.width(), 16), name, 9, TEXT, True)
    text(p, QRectF(body.left(), body.bottom() - 20, body.width(), 16), state, 8, MUTED)


def _switch(p, r, name, state, on):
    body = r.adjusted(M, 4, -M, -4)
    p.setPen(QPen(QColor("#0b0f14"), 1))
    p.setBrush(grad(body, "#1f2937", "#0b0f14"))
    p.drawRoundedRect(body, 10, 10)
    # Büyük, dokunmaya uygun düğme
    knob_w = 40
    knob_x = body.right() - knob_w - 8 if on else body.left() + 8
    knob = QRectF(knob_x, body.top() + 10, knob_w, body.height() - 30)
    p.setPen(QPen(QColor("#0b0f14"), 1))
    p.setBrush(grad(knob, "#86efac" if on else "#94a3b8", "#15803d" if on else "#475569"))
    p.drawRoundedRect(knob, 9, 9)
    text(p, QRectF(body.left(), body.bottom() - 20, body.width(), 16), name + "  ·  " + state,
         8, GREEN if on else MUTED, on)


def _touch(p, r, name, state, on):
    body = r.adjusted(M, 4, -M, -4)
    p.setPen(QPen(QColor("#050608"), 1))
    p.setBrush(grad(body, "#1a1f29", "#07090d"))
    p.drawRoundedRect(body, 12, 12)
    glass = body.adjusted(8, 8, -8, -22)
    p.setPen(Qt.NoPen)
    p.setBrush(grad(glass, "#1e3a8a", "#3b82f6") if on else grad(glass, "#0f172a", "#1e293b"))
    p.drawRoundedRect(glass, 8, 8)
    c = glass.center()
    if on:
        halo = QRadialGradient(c, 40)
        halo.setColorAt(0.0, QColor(147, 197, 253, 200))
        halo.setColorAt(1.0, QColor(147, 197, 253, 0))
        p.setBrush(QBrush(halo))
        p.drawEllipse(c, 40, 40)
    p.setBrush(QColor(255, 255, 255, 230 if on else 60))
    p.drawEllipse(c, 12, 12)
    text(p, QRectF(body.left(), body.bottom() - 20, body.width(), 16), name + "  ·  " + state,
         8, BLUE if on else MUTED, on)


def _screen(p, r, name, state, on):
    body = r.adjusted(M, 4, -M, -4)
    p.setPen(QPen(QColor("#0b0f14"), 2))
    p.setBrush(grad(body, "#374151", "#111827"))
    p.drawRoundedRect(body, 8, 8)
    glass = body.adjusted(8, 8, -8, -20)
    p.setPen(Qt.NoPen)
    if on:
        p.setBrush(grad(glass, "#14532d", "#052e16"))
    else:
        p.setBrush(grad(glass, "#1f2937", "#0b0f14"))
    p.drawRoundedRect(glass, 5, 5)
    text(p, glass, "1" if on else "0", 30, "#86efac" if on else "#374151", True)
    text(p, QRectF(body.left(), body.bottom() - 19, body.width(), 16), name + "  ·  " + state,
         8, GREEN if on else MUTED, on)


def _led(p, r, name, state, on):
    center = QPointF(r.center().x(), r.center().y() - 6)
    if on:
        halo = QRadialGradient(center, 36)
        halo.setColorAt(0.0, QColor(34, 197, 94, 170))
        halo.setColorAt(1.0, QColor(34, 197, 94, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(halo))
        p.drawEllipse(center, 36, 36)
    dome = QRadialGradient(center, 16)
    if on:
        dome.setColorAt(0.0, QColor("#bbf7d0"))
        dome.setColorAt(0.5, QColor("#22c55e"))
        dome.setColorAt(1.0, QColor("#14532d"))
    else:
        dome.setColorAt(0.0, QColor("#4b5563"))
        dome.setColorAt(0.6, QColor("#1f2937"))
        dome.setColorAt(1.0, QColor("#0b0f14"))
    p.setPen(QPen(QColor("#0b0f14"), 1))
    p.setBrush(QBrush(dome))
    p.drawEllipse(center, 16, 16)
    text(p, QRectF(r.left(), r.bottom() - 20, r.width(), 16), name + "  ·  " + state,
         8, GREEN if on else MUTED, on)


def _clock(p, r, name, state, on):
    body = r.adjusted(M, 4, -M, -4)
    p.setPen(QPen(QColor("#334155"), 1))
    p.setBrush(grad(body, "#f1f5f9", "#64748b"))
    p.drawRoundedRect(body, 10, 10)
    text(p, QRectF(body.left(), body.top() + 4, body.width(), 16), name, 9, "#0f172a", True)

    # Kare dalga: saat her darbede seviye değiştirir
    x0 = body.left() + 14
    hi_y, lo_y = body.bottom() - 28, body.bottom() - 18
    level_high = bool(on)
    y = hi_y if level_high else lo_y
    path = QPainterPath(QPointF(x0, y))
    for i in range(1, 7):
        path.lineTo(x0 + i * 12, y)
        level_high = not level_high
        y = hi_y if level_high else lo_y
        path.lineTo(x0 + i * 12, y)
    p.setPen(QPen(QColor(GREEN if on else "#0f172a"), 2))
    p.setBrush(Qt.NoBrush)
    p.drawPath(path)


def _cpu(p, r, name, state, on):
    body = r.adjusted(M, 4, -M, -4)
    p.setPen(QPen(QColor("#052e16"), 1))
    p.setBrush(grad(body, "#14532d", "#0b2e1d"))
    p.drawRoundedRect(body, 10, 10)
    spreader = body.adjusted(14, 14, -14, -14)
    p.setPen(QPen(QColor("#334155"), 1))
    p.setBrush(grad(spreader, "#f8fafc", "#64748b"))
    p.drawRoundedRect(spreader, 8, 8)
    text(p, QRectF(spreader.left(), spreader.top() + 10, spreader.width(), 22), name, 11, "#0f172a", True)
    text(p, QRectF(spreader.left(), spreader.center().y() + 4, spreader.width(), 18), state,
         9, "#166534" if on else "#475569", on)
    # Köşe işaretleri (pin 1)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#d4a72c"))
    for x in (body.left() + 8, body.right() - 8):
        for y in (body.top() + 8, body.bottom() - 8):
            p.drawEllipse(QPointF(x, y), 2.4, 2.4)


def _module(p, r, name, state, on, accent, tint):
    """RAM ve SSD: PCB üzerinde bellek yongaları."""
    body = r.adjusted(M, 4, -M, -4)
    p.setPen(QPen(QColor("#052018"), 1))
    p.setBrush(grad(body, tint[0], tint[1]))
    p.drawRoundedRect(body, 6, 6)
    text(p, QRectF(body.left(), body.top() + 6, body.width(), 18), name, 9, accent, True)
    chip_w, chip_h = 26, 20
    total = 4 * chip_w + 3 * 8
    x = body.center().x() - total / 2
    y = body.center().y() - chip_h / 2 + 2
    p.setPen(QPen(QColor("#0b0d12"), 1))
    for i in range(4):
        cr = QRectF(x + i * (chip_w + 8), y, chip_w, chip_h)
        p.setBrush(grad(cr, "#2a303b", "#0b0d12"))
        p.drawRoundedRect(cr, 3, 3)
    # Altın kontaklar
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#c8a24a"))
    p.drawRect(QRectF(body.left() + 10, body.bottom() - 4, body.width() - 20, 2))
    text(p, QRectF(body.left(), body.bottom() - 22, body.width(), 14), state,
         8, GREEN if on else MUTED, on)


_DRAWERS = {
    "vcc": _vcc,
    "gnd": _gnd,
    "switch": _switch,
    "touch": _touch,
    "screen": _screen,
    "led": _led,
    "clock": _clock,
    "hadder": _cpu,
    "dff": lambda p, r, n, s, o: _chip(p, r, n, s, o),
}
for _gate in ("not", "and", "or", "nand", "nor", "xor"):
    _DRAWERS[_gate] = lambda p, r, n, s, o: _chip(p, r, n, s, o)


def draw_part(p, ptype, pins, w, h, name, state, on, selected):
    """Parçanın tamamını çizer. Orijin parçanın sol üst köşesidir."""
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    r = QRectF(0, 0, w, h)

    if on:
        _glow_rect(p, r.adjusted(M - 2, 2, -M + 2, -2), GREEN, 12)
    _legs(p, pins, w)

    if ptype == "ram":
        _module(p, r, name, state, on, "#fde68a", ("#14532d", "#0b2e1d"))
    elif ptype == "ssd":
        _module(p, r, name, state, on, "#67e8f9", ("#0f3d4a", "#082430"))
    else:
        _DRAWERS.get(ptype, lambda p_, r_, n_, s_, o_: _chip(p_, r_, n_, s_, o_))(p, r, name, state, on)

    _pin_labels(p, pins, w)

    if selected:
        p.setPen(QPen(QColor(YELLOW), 1.5, Qt.DashLine))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(r.adjusted(-5, -5, 5, 5), 12, 12)
    p.restore()
