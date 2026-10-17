# Kavram - Araç ayarları
#
#   * Her kalem türünün (ve silginin) KENDİNE ÖZGÜ ayarları vardır: boyut, basınç duyarlılığı,
#     hassasiyet ve lazy mouse (stabilizatör). Kalem değişince o kalemin ayarları geri yüklenir.
#   * S, A ve R modlarının da kendi ayarları vardır (panelde moda göre sayfa değişir).
#   * Panel, Blender tarzı pencere sisteminde "Araç Ayarları" editörü olarak yer alır.
from drawing_common import *

DEFAULT_MODE_CFG = {
    "s": {"smooth": True, "ease": "linear"},
    "a": {"dot": 5, "eps": 2.5, "max_keys": 40, "ease": "linear"},
}
_SETTINGS = ("kavram", "DrawingEditor")


def load_mode_cfg():
    cfg = copy.deepcopy(DEFAULT_MODE_CFG)
    raw = QSettings(*_SETTINGS).value("modeCfg/v1", "", type=str)
    try:
        data = json.loads(raw) if raw else {}
        for mode in cfg:
            for k, v in (data.get(mode) or {}).items():
                if k in cfg[mode]:
                    cfg[mode][k] = v
    except Exception:
        pass
    return cfg


def save_mode_cfg(cfg):
    try:
        QSettings(*_SETTINGS).setValue("modeCfg/v1", json.dumps(cfg))
    except Exception:
        pass


def apply_ease(k, mode):
    """Ara kare geçişi: 'smooth' = yavaş başla / yavaş bit (smoothstep)."""
    if mode == "smooth":
        return k * k * (3.0 - 2.0 * k)
    return k


# ---------------------------------------------------------------------------
# Çekirdek pencereye karışan: kalem başına ayar deposu
# ---------------------------------------------------------------------------
class ToolCfgMixin:
    def loadToolCfg(self):
        raw = QSettings(*_SETTINGS).value("toolCfg/v1", "", type=str)
        try:
            self.tool_cfg = json.loads(raw) if raw else {}
        except Exception:
            self.tool_cfg = {}
        self._tool_key_last = None

    def toolCfgKey(self):
        return f"{'e' if self.eraser_mode else 'n'}:{self.current_tool_index}"

    def toolCfgName(self):
        name = str(self.current_tool_index)
        for n, logic_id in self.TOOL_ORDER:
            if logic_id == self.current_tool_index:
                name = n
                break
        return ("Silgi — " if self.eraser_mode else "") + name

    def toolCfgSaveCurrent(self):
        """Şu anki küresel değerleri, son seçili kalemin kaydına yazar."""
        key = getattr(self, "_tool_key_last", None)
        if key is None:
            return
        self.tool_cfg[key] = {"pressure": bool(self.pen_pressure_enabled), "sens": int(self.sensitivity_value),
                              "lazy": bool(self.lazy_mouse_enabled), "lazy_r": int(self.lazy_radius),
                              "lazy_f": int(self.lazy_factor)}
        try:
            QSettings(*_SETTINGS).setValue("toolCfg/v1", json.dumps(self.tool_cfg))
        except Exception:
            pass

    def toolCfgApply(self):
        """Seçili kalemin ayarlarını yükler (ilk kullanımda mevcut değerler o kalemin başlangıcı olur)."""
        key = self.toolCfgKey()
        cfg = self.tool_cfg.get(key)
        if cfg is None:
            self._tool_key_last = key
            self.toolCfgSaveCurrent()
        else:
            self.pen_pressure_enabled = bool(cfg.get("pressure", False))
            self.sensitivity_value = int(cfg.get("sens", -1))
            self.lazy_mouse_enabled = bool(cfg.get("lazy", False))
            self.lazy_radius = int(cfg.get("lazy_r", 30))
            self.lazy_factor = int(cfg.get("lazy_f", 15))
            self._tool_key_last = key
            self.updateButtonStyles()
        if hasattr(self, "tool_settings"):
            self.tool_settings.refresh()


# ---------------------------------------------------------------------------
# Panel
# ---------------------------------------------------------------------------
_CSS = """
QFrame#toolSettings { background-color: #262626; }
QLabel { color: #dddddd; background: transparent; }
QLabel#hint { color: #8d8d8d; font-size: 11px; }
QLabel#title { color: #ffffff; font-weight: bold; font-size: 13px; }
QCheckBox { color: #dddddd; spacing: 6px; background: transparent; }
QSpinBox, QDoubleSpinBox, QComboBox { background-color: #333; color: #eee; border: 1px solid #555;
                                       border-radius: 5px; padding: 2px 5px; }
QComboBox QAbstractItemView { background-color: #333; color: #eee; selection-background-color: #556; }
QPushButton { background-color: #333; color: #eee; border: 1px solid #555; border-radius: 6px; padding: 4px 8px; }
QPushButton:hover { background-color: #444; }
QPushButton:disabled { color: #777; border-color: #3a3a3a; }
QSlider::groove:horizontal { height: 4px; background: #555; border-radius: 2px; }
QSlider::handle:horizontal { background: #ddd; width: 12px; margin: -5px 0; border-radius: 6px; }
QScrollArea { border: none; background: transparent; }
"""


def _hint(text):
    lbl = QLabel(text)
    lbl.setObjectName("hint")
    lbl.setWordWrap(True)
    return lbl


class ToolSettingsPanel(QFrame):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self._building = False
        self.setObjectName("toolSettings")
        self.setStyleSheet(_CSS)
        self.setMinimumWidth(150)

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(6)
        self.title = QLabel("")
        self.title.setObjectName("title")
        self.title.setWordWrap(True)
        root.addWidget(self.title)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_brush())
        self.stack.addWidget(self._build_select())
        self.stack.addWidget(self._build_points())
        self.stack.addWidget(self._build_reference())
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.stack)
        root.addWidget(scroll, 1)
        self.refresh()
        self._poll = QTimer(self)                 # boyut / kalem başka yoldan değişirse paneli güncel tut
        self._poll.setInterval(600)
        self._poll.timeout.connect(self._poll_brush)
        self._poll.start()

    def _poll_brush(self):
        if not self.isVisible() or self.stack.currentIndex() != 0 or getattr(self.win, "edit_mode", None):
            return
        w = self.win
        if self.b_size_sp.hasFocus() or self.b_lazy_r.hasFocus() or self.b_lazy_f.hasFocus():
            return
        if (int(w.pen_radius) != self.b_size_sp.value() or self.title.text() != "Kalem: " + w.toolCfgName()
                or bool(w.pen_pressure_enabled) != self.b_pressure.isChecked()
                or bool(w.lazy_mouse_enabled) != self.b_lazy.isChecked()):
            self.refresh()

    # ------------------------------------------------------------ yardımcılar
    def _row(self, label, widget):
        row = QHBoxLayout()
        lbl = QLabel(label)
        row.addWidget(lbl, 1)
        row.addWidget(widget)
        return row

    def _page(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(7)
        return page, lay

    def _slider_spin(self, lo, hi, on_change):
        sl = QSlider(Qt.Horizontal)
        sl.setRange(lo, hi)
        sp = QSpinBox()
        sp.setRange(lo, hi)
        sl.valueChanged.connect(sp.setValue)
        sp.valueChanged.connect(sl.setValue)
        sp.valueChanged.connect(lambda v: (not self._building) and on_change(v))
        return sl, sp

    # ------------------------------------------------------------ kalem sayfası
    def _build_brush(self):
        page, lay = self._page()
        self.b_size_sl, self.b_size_sp = self._slider_spin(1, 150, self._on_size)
        lay.addWidget(QLabel("Boyut"))
        row = QHBoxLayout()
        row.addWidget(self.b_size_sl, 1)
        row.addWidget(self.b_size_sp)
        lay.addLayout(row)

        self.b_pressure = QCheckBox("Basınca duyarlı (tablet)")
        self.b_pressure.toggled.connect(self._on_pressure)
        lay.addWidget(self.b_pressure)

        self.b_sens_on = QCheckBox("Hassasiyeti elle ayarla")
        self.b_sens_on.toggled.connect(self._on_sens)
        lay.addWidget(self.b_sens_on)
        self.b_sens = QSlider(Qt.Horizontal)
        self.b_sens.setRange(0, 100)
        self.b_sens.valueChanged.connect(self._on_sens)
        lay.addWidget(self.b_sens)

        lay.addSpacing(4)
        self.b_lazy = QCheckBox("Lazy mouse (titreme azaltıcı)")
        self.b_lazy.toggled.connect(self._on_lazy)
        lay.addWidget(self.b_lazy)
        self.b_lazy_r = QSpinBox()
        self.b_lazy_r.setRange(1, 200)
        self.b_lazy_r.valueChanged.connect(self._on_lazy)
        lay.addLayout(self._row("Yarıçap", self.b_lazy_r))
        self.b_lazy_f = QSpinBox()
        self.b_lazy_f.setRange(1, 60)
        self.b_lazy_f.valueChanged.connect(self._on_lazy)
        lay.addLayout(self._row("Hassasiyet", self.b_lazy_f))

        lay.addWidget(_hint("Bu ayarlar yalnızca seçili kalem türüne aittir. Başka kaleme geçip dönünce "
                            "bu kalemin ayarları geri gelir.  Kısayol: R = boyut penceresi."))
        lay.addStretch(1)
        return page

    def _on_size(self, v):
        w = self.win
        w.changeRadiusValue(int(v))
        w.toolCfgSaveCurrent()

    def _on_pressure(self, on):
        if self._building:
            return
        w = self.win
        w.pen_pressure_enabled = bool(on)
        w.updateButtonStyles()
        w.toolCfgSaveCurrent()

    def _on_sens(self, *_a):
        if self._building:
            return
        w = self.win
        w.sensitivity_value = int(self.b_sens.value()) if self.b_sens_on.isChecked() else -1
        self.b_sens.setEnabled(self.b_sens_on.isChecked())
        w.toolCfgSaveCurrent()

    def _on_lazy(self, *_a):
        if self._building:
            return
        w = self.win
        w.lazy_mouse_enabled = self.b_lazy.isChecked()
        w.lazy_radius = int(self.b_lazy_r.value())
        w.lazy_factor = int(self.b_lazy_f.value())
        w.updateButtonStyles()
        w.toolCfgSaveCurrent()

    # ------------------------------------------------------------ S modu
    def _build_select(self):
        page, lay = self._page()
        self.s_smooth = QCheckBox("Dönüştürürken kenarları yumuşat")
        self.s_smooth.toggled.connect(self._on_s)
        lay.addWidget(self.s_smooth)
        self.s_ease = QComboBox()
        self.s_ease.addItem("Doğrusal (sabit hız)", "linear")
        self.s_ease.addItem("Yumuşak (yavaş başla / bit)", "smooth")
        self.s_ease.currentIndexChanged.connect(self._on_s)
        lay.addWidget(QLabel("Ara kare geçişi"))
        lay.addWidget(self.s_ease)
        lay.addWidget(_hint(
            "S modu piksel seçer.\n"
            "Sürükle: serbest seçim • Shift+sürükle: dikdörtgen\n"
            "G taşı • S büyüt/küçült • R döndür • X/Y eksen\n"
            "D: seçimi başka kareye kopyala\n"
            "Ctrl+D: ara kareleri otomatik oluştur\n"
            "Delete: sil • Esc: iptal"))
        lay.addStretch(1)
        return page

    def _on_s(self, *_a):
        if self._building:
            return
        cfg = self.win.mode_cfg["s"]
        cfg["smooth"] = self.s_smooth.isChecked()
        cfg["ease"] = self.s_ease.currentData()
        save_mode_cfg(self.win.mode_cfg)

    # ------------------------------------------------------------ A modu
    def _build_points(self):
        page, lay = self._page()
        self.a_dot = QSpinBox()
        self.a_dot.setRange(3, 12)
        self.a_dot.setSuffix(" px")
        self.a_dot.valueChanged.connect(self._on_a)
        lay.addLayout(self._row("Nokta boyutu", self.a_dot))
        self.a_eps = QDoubleSpinBox()
        self.a_eps.setRange(0.5, 12.0)
        self.a_eps.setSingleStep(0.5)
        self.a_eps.setSuffix(" px")
        self.a_eps.setToolTip("Küçük değer = daha fazla nokta, büyük değer = daha sade çizim")
        self.a_eps.valueChanged.connect(self._on_a)
        lay.addLayout(self._row("Sadeleştirme", self.a_eps))
        self.a_max = QSpinBox()
        self.a_max.setRange(6, 150)
        self.a_max.valueChanged.connect(self._on_a)
        lay.addLayout(self._row("En çok nokta (çizgi başına)", self.a_max))
        self.a_ease = QComboBox()
        self.a_ease.addItem("Doğrusal (sabit hız)", "linear")
        self.a_ease.addItem("Yumuşak (yavaş başla / bit)", "smooth")
        self.a_ease.currentIndexChanged.connect(self._on_a)
        lay.addWidget(QLabel("Ara kare geçişi"))
        lay.addWidget(self.a_ease)
        self.a_split = QPushButton("Seçili noktaları böl   (T)")
        self.a_split.clicked.connect(lambda: self.win.drawing_area.ptSubdivide())
        lay.addWidget(self.a_split)
        lay.addWidget(_hint(
            "A modu çizimleri köşe noktalarıyla gösterir.\n"
            "Tıkla: seç • Shift: çoklu • boşlukta sürükle: kutuyla seç\n"
            "G taşı • S büyüt/küçült • R döndür • X/Y eksen\n"
            "T: seçili ardışık noktaların ortasına yeni nokta ekle (bölme)\n"
            "D: seçili çizgileri başka kareye kopyala\n"
            "Ctrl+D: ara kareleri otomatik oluştur\n"
            "Delete: çizgiyi sil • Esc: iptal"))
        lay.addStretch(1)
        return page

    def _on_a(self, *_a):
        if self._building:
            return
        cfg = self.win.mode_cfg["a"]
        cfg["dot"] = int(self.a_dot.value())
        cfg["eps"] = float(self.a_eps.value())
        cfg["max_keys"] = int(self.a_max.value())
        cfg["ease"] = self.a_ease.currentData()
        save_mode_cfg(self.win.mode_cfg)
        self.win.drawing_area.ptCfgChanged()

    # ------------------------------------------------------------ R modu (referans)
    def _build_reference(self):
        page, lay = self._page()
        self.r_visible = QCheckBox("Referansı göster   (G)")
        self.r_visible.toggled.connect(self._on_r_visible)
        lay.addWidget(self.r_visible)

        row = QHBoxLayout()
        b_img = QPushButton("Görsel ekle…")
        b_img.clicked.connect(lambda: self.win.importReferenceImage())
        b_vid = QPushButton("Video ekle…")
        b_vid.clicked.connect(lambda: self.win.video.import_video())
        row.addWidget(b_img)
        row.addWidget(b_vid)
        lay.addLayout(row)

        self.r_video_info = QLabel("")
        self.r_video_info.setWordWrap(True)
        lay.addWidget(self.r_video_info)
        self.r_video_remove = QPushButton("Videoyu kaldır")
        self.r_video_remove.clicked.connect(lambda: self.win.video.remove_video())
        lay.addWidget(self.r_video_remove)

        self.r_vop_label = QLabel("Video opaklığı: 55%")
        lay.addWidget(self.r_vop_label)
        self.r_vop = QSlider(Qt.Horizontal)
        self.r_vop.setRange(5, 100)
        self.r_vop.valueChanged.connect(self._on_r_vop)
        lay.addWidget(self.r_vop)

        self.r_iop_label = QLabel("Görsel saydamlığı: 55%")
        lay.addWidget(self.r_iop_label)
        self.r_iop = QSlider(Qt.Horizontal)
        self.r_iop.setRange(0, 95)
        self.r_iop.valueChanged.connect(self._on_r_iop)
        lay.addWidget(self.r_iop)

        lay.addWidget(_hint(
            "Video eklenince çizim alanı videonun en-boy oranına uyar ve her video karesi için\n"
            "altta bir kare oluşturulur. Kareler arasında ← → ile gezin; oynatırken video ile\n"
            "çizimler eş zamanlı akar.\n\n"
            "Kısıtlar: çizim yapıldıktan sonra video eklenemez; video varken kare ekleme / silme /\n"
            "sıra değiştirme kapalıdır ve çizim alanı yeniden boyutlandırılamaz.\n"
            "Proje (.pnf) videonun yolunu saklar; açılışta kareler oradan yeniden alınır."))
        lay.addStretch(1)
        return page

    def _on_r_visible(self, on):
        if self._building:
            return
        w = self.win
        if bool(on) != w.global_reference_visible:
            w.toggle_global_reference()

    def _on_r_vop(self, v):
        self.r_vop_label.setText(f"Video opaklığı: {v}%")
        if not self._building:
            self.win.video.set_opacity(v)

    def _on_r_iop(self, v):
        self.r_iop_label.setText(f"Görsel saydamlığı: {v}%")
        if not self._building:
            self.win.setReferenceTransparency(v)

    # ------------------------------------------------------------ yenile
    def refresh(self):
        w = self.win
        mode = getattr(w, "edit_mode", None)
        self._building = True
        try:
            if mode == 's':
                self.stack.setCurrentIndex(1)
                self.title.setText("S modu — piksel seçimi")
                cfg = w.mode_cfg["s"]
                self.s_smooth.setChecked(bool(cfg["smooth"]))
                self.s_ease.setCurrentIndex(max(0, self.s_ease.findData(cfg["ease"])))
            elif mode == 'a':
                self.stack.setCurrentIndex(2)
                self.title.setText("A modu — nokta düzenleme")
                cfg = w.mode_cfg["a"]
                self.a_dot.setValue(int(cfg["dot"]))
                self.a_eps.setValue(float(cfg["eps"]))
                self.a_max.setValue(int(cfg["max_keys"]))
                self.a_ease.setCurrentIndex(max(0, self.a_ease.findData(cfg["ease"])))
            elif mode == 'r':
                self.stack.setCurrentIndex(3)
                self.title.setText("R modu — referans görsel / video")
                self.r_visible.setChecked(bool(w.global_reference_visible))
                v = w.video
                if v.active:
                    m = v.meta
                    self.r_video_info.setText(f"Video: {os.path.basename(m['path'])}\n"
                                              f"{m['count']} kare • {m['fps']} fps • {m['canvas_w']}×{m['canvas_h']}")
                else:
                    self.r_video_info.setText("Video yok.")
                self.r_video_remove.setEnabled(v.active)
                self.r_vop.setValue(int(v.opacity))
                self.r_vop_label.setText(f"Video opaklığı: {int(v.opacity)}%")
                self.r_vop.setEnabled(v.active)
                self.r_iop.setValue(int(w.reference_transparency))
                self.r_iop_label.setText(f"Görsel saydamlığı: {int(w.reference_transparency)}%")
            else:
                self.stack.setCurrentIndex(0)
                self.title.setText("Kalem: " + w.toolCfgName())
                solid = (w.current_tool_index == 4)
                self.b_size_sl.setEnabled(not solid)
                self.b_size_sp.setEnabled(not solid)
                self.b_size_sp.setValue(int(w.pen_radius))
                self.b_pressure.setChecked(bool(w.pen_pressure_enabled))
                on = w.sensitivity_value != -1
                self.b_sens_on.setChecked(on)
                self.b_sens.setEnabled(on)
                self.b_sens.setValue(int(w.sensitivity_value) if on else 50)
                self.b_lazy.setChecked(bool(w.lazy_mouse_enabled))
                self.b_lazy_r.setValue(int(w.lazy_radius))
                self.b_lazy_f.setValue(int(w.lazy_factor))
        finally:
            self._building = False
