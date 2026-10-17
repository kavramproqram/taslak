# Kavram - Referans video
#
# Akış:
#   1. R modundan "Video ekle…". Çizim yapılmışsa video eklenemez (en-boy oranı kilit noktadır).
#   2. Video ffmpeg ile okunur; kullanıcı kare hızı / başlangıç / süre seçer (en çok max_pages kare).
#   3. Çizim alanı videoya uyar (en fazla 1920×1080, oran korunur).
#   4. Kareler arka planda (QThread) JPG olarak çıkarılır:  <önbellek>/video/f_00001.jpg ...
#   5. Her video karesi için TEK SEFERDE bir sayfa (kare) açılır; boş sayfalar dosya üretmez,
#      bu yüzden yüzlerce kare hızlı açılır ve hızlı kaydedilir.
#   6. Sayfa N, video karesi N'yi gösterir. Oynatırken video ile çizimler eş zamanlı akar.
#   7. Proje (.pnf) videonun yolunu ve ayarlarını saklar; açılışta kareler oradan yeniden alınır
#      (video dosyasının kendisi projeye gömülmez).
from collections import OrderedDict

from drawing_common import *
from drawing_layers import LAYER_FORMAT, layer_path, delete_page_files

MAX_CANVAS = (1920, 1080)
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


# ---------------------------------------------------------------------------
# Yardımcılar (Qt'siz kısımlar test edilebilir)
# ---------------------------------------------------------------------------
def image_is_empty(img):
    """Görüntüde hiç görünür piksel yoksa True (hızlı: Alpha8 bayt sayımı)."""
    if img is None or img.isNull():
        return True
    a = img.convertToFormat(QImage.Format_Alpha8)
    ptr = a.constBits()
    ptr.setsize(a.byteCount())
    data = bytes(ptr)
    return data.count(0) == len(data)


def project_has_drawing(win):
    """Herhangi bir karede, herhangi bir katmanda çizim var mı?"""
    area = win.drawing_area
    st = area.layer_stack
    for l in st.layers:
        if not image_is_empty(l.image):
            return True
    for i in range(len(win.pages_data)):
        if i == win.current_page_index:
            continue
        for l in st.layers:
            path = layer_path(win.drawing_cache_dir, i, l.id)
            if os.path.isfile(path) and not image_is_empty(QImage(path)):
                return True
        legacy = os.path.join(win.drawing_cache_dir, f"s{i + 1}.png")
        if os.path.isfile(legacy) and not image_is_empty(QImage(legacy)):
            return True
    return False


def parse_ffmpeg_info(text):
    """`ffmpeg -i dosya` çıktısından süre, boyut ve kare hızını okur."""
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", text)
    if not m:
        raise ValueError("Video süresi okunamadı")
    duration = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    vline = next((ln for ln in text.splitlines() if "Stream" in ln and "Video:" in ln), None)
    if vline is None:
        raise ValueError("Dosyada video akışı yok")
    sz = re.search(r",\s*(\d{2,5})x(\d{2,5})", vline)
    if not sz:
        raise ValueError("Video boyutu okunamadı")
    fps = re.search(r"([\d.]+)\s*fps", vline) or re.search(r"([\d.]+)\s*tbr", vline)
    return {"duration": duration, "w": int(sz.group(1)), "h": int(sz.group(2)),
            "fps": float(fps.group(1)) if fps else 24.0}


def probe_video(path):
    if not ffmpeg_available():
        raise RuntimeError(f"ffmpeg bulunamadı: {FFMPEG_PATH}")
    proc = subprocess.run([FFMPEG_PATH, "-hide_banner", "-i", path], stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, creationflags=_NO_WINDOW, timeout=40)
    info = parse_ffmpeg_info(proc.stderr.decode("utf-8", "replace"))
    info["path"] = path
    return info


def fit_canvas_size(vw, vh, max_w=MAX_CANVAS[0], max_h=MAX_CANVAS[1]):
    """Video boyutunu en-boy oranını koruyarak sınırlar içine sığdırır (çift sayılar)."""
    scale = min(1.0, max_w / float(vw), max_h / float(vh))
    w = max(16, int(round(vw * scale / 2.0)) * 2)
    h = max(16, int(round(vh * scale / 2.0)) * 2)
    return w, h


def suggest_params(info, max_frames):
    """Önerilen kare hızı ve süre: toplam kare sayısı max_frames'i aşmasın."""
    length = float(info["duration"])
    fps = max(1, min(24, int(round(info["fps"]))))
    if int(length * fps) > max_frames:
        fps = max(1, int(max_frames // max(length, 0.001)))
    if int(length * fps) > max_frames:
        length = max_frames / float(fps)
    return fps, round(length, 2)


# ---------------------------------------------------------------------------
# Kare çıkarma (arka plan iş parçacığı)
# ---------------------------------------------------------------------------
class FrameExtractor(QThread):
    progress = pyqtSignal(int, str)
    done = pyqtSignal(int)
    failed = pyqtSignal(str)

    def __init__(self, p, parent=None):
        super().__init__(parent)
        self.p = p
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        p = self.p
        out_dir = p["out_dir"]
        log_path = os.path.join(out_dir, "ffmpeg.log")
        try:
            os.makedirs(out_dir, exist_ok=True)
            for name in os.listdir(out_dir):
                if name.startswith("f_") and name.endswith(".jpg"):
                    os.remove(os.path.join(out_dir, name))
            cmd = [FFMPEG_PATH, "-y", "-hide_banner", "-loglevel", "error", "-progress", "pipe:1", "-nostats"]
            if p["start"] > 0:
                cmd += ["-ss", "%.3f" % p["start"]]
            cmd += ["-i", p["path"], "-t", "%.3f" % p["length"],
                    "-vf", "fps=%d,scale=%d:%d:flags=bilinear" % (p["fps"], p["w"], p["h"]),
                    "-frames:v", str(p["max_frames"]), "-q:v", "3", "-start_number", "1",
                    os.path.join(out_dir, "f_%05d.jpg")]
            total = max(1, min(p["max_frames"], int(p["length"] * p["fps"])))
            with open(log_path, "w", encoding="utf-8", errors="replace") as log:
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=log, creationflags=_NO_WINDOW,
                                        universal_newlines=True)
                for line in proc.stdout:
                    if self._cancel:
                        proc.kill()
                        proc.wait()
                        self.failed.emit("")
                        return
                    if line.startswith("frame="):
                        try:
                            n = int(line.split("=")[1])
                            self.progress.emit(min(99, int(100 * n / total)), f"Kare {n}/{total} çıkarılıyor…")
                        except ValueError:
                            pass
                proc.wait()
            if proc.returncode != 0:
                tail = ""
                try:
                    with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                        tail = "".join(f.readlines()[-6:])
                except OSError:
                    pass
                self.failed.emit(f"ffmpeg hata kodu {proc.returncode}\n{tail}")
                return
            count = len([n for n in os.listdir(out_dir) if n.startswith("f_") and n.endswith(".jpg")])
            if count == 0:
                self.failed.emit("Videodan kare çıkarılamadı.")
                return
            self.progress.emit(100, "Tamamlandı")
            self.done.emit(count)
        except Exception as e:
            self.failed.emit(str(e))


# ---------------------------------------------------------------------------
# İçe aktarma penceresi
# ---------------------------------------------------------------------------
class VideoImportDialog(QDialog):
    def __init__(self, win, info, max_frames):
        super().__init__(win)
        self.info = info
        self.max_frames = max_frames
        self.setWindowTitle("Referans Video")
        self.setMinimumWidth(420)
        self.setStyleSheet("""
            QDialog { background-color: #2b2b2b; }
            QLabel, QCheckBox { color: #eee; }
            QSpinBox, QDoubleSpinBox { background-color: #3a3a3a; color: #eee; border: 1px solid #555;
                                         border-radius: 5px; padding: 3px 6px; }
            QPushButton { background-color: #3a3a3a; color: #eee; border: 1px solid #666; border-radius: 6px; padding: 5px 14px; }
            QPushButton:hover { background-color: #4a4a4a; }
            QPushButton:disabled { color: #777; }
        """)
        lay = QVBoxLayout(self)
        cw, ch = fit_canvas_size(info["w"], info["h"])
        self.canvas_size = (cw, ch)
        lay.addWidget(QLabel(f"<b>{os.path.basename(info['path'])}</b><br>"
                             f"{info['w']}×{info['h']} • {info['fps']:.2f} fps • {info['duration']:.2f} sn"))
        note = QLabel(f"Çizim alanı <b>{cw}×{ch}</b> olacak (videonun en-boy oranı korunur).<br>"
                      "Video eklendikten sonra çizim alanı yeniden boyutlandırılamaz.")
        note.setWordWrap(True)
        lay.addWidget(note)

        fps, length = suggest_params(info, max_frames)
        self.fps = QSpinBox()
        self.fps.setRange(1, 60)
        self.fps.setValue(fps)
        self.start = QDoubleSpinBox()
        self.start.setRange(0.0, max(0.0, info["duration"] - 0.1))
        self.start.setDecimals(2)
        self.start.setSuffix(" sn")
        self.length = QDoubleSpinBox()
        self.length.setRange(0.1, info["duration"])
        self.length.setDecimals(2)
        self.length.setSuffix(" sn")
        self.length.setValue(length)
        for text, widget in (("Kare hızı (fps)", self.fps), ("Başlangıç", self.start), ("Süre", self.length)):
            row = QHBoxLayout()
            row.addWidget(QLabel(text), 1)
            row.addWidget(widget)
            lay.addLayout(row)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        lay.addWidget(self.summary)

        btns = QHBoxLayout()
        btns.addStretch(1)
        cancel = QPushButton("İptal")
        self.ok = QPushButton("Videoyu Ekle")
        self.ok.setDefault(True)
        cancel.clicked.connect(self.reject)
        self.ok.clicked.connect(self.accept)
        btns.addWidget(cancel)
        btns.addWidget(self.ok)
        lay.addLayout(btns)
        for w in (self.fps, self.start, self.length):
            w.valueChanged.connect(self._update)
        self._update()

    def _frames(self):
        length = min(self.length.value(), self.info["duration"] - self.start.value())
        return max(1, int(length * self.fps.value()))

    def _update(self):
        n = self._frames()
        too_many = n > self.max_frames
        color = "#ff7070" if too_many else "#9fe39f"
        txt = f"<span style='color:{color}'>{n} kare oluşturulacak</span> (en çok {self.max_frames})"
        if too_many:
            txt += "<br>Kare hızını veya süreyi azaltın."
        self.summary.setText(txt)
        self.ok.setEnabled(not too_many)

    def options(self):
        start = self.start.value()
        length = min(self.length.value(), self.info["duration"] - start)
        return {"fps": self.fps.value(), "start": start, "length": length}


# ---------------------------------------------------------------------------
# Referans video yöneticisi
# ---------------------------------------------------------------------------
class VideoReference(QObject):
    changed = pyqtSignal()

    CACHE_FRAMES = 12

    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.meta = None
        self.opacity = QSettings("kavram", "DrawingEditor").value("videoOpacity", 55, type=int)
        self._cache = OrderedDict()
        self._worker = None
        self._progress = None
        self.resizing_allowed = False
        win.drawing_area.video_provider = self.paint_frame

    # ------------------------------------------------------------ durum
    @property
    def dir(self):
        return os.path.join(self.win.drawing_cache_dir, "video")

    @property
    def active(self):
        return self.meta is not None

    def busy(self):
        return self._worker is not None and self._worker.isRunning()

    def frame_path(self, page):
        return os.path.join(self.dir, "f_%05d.jpg" % (page + 1))

    def reset(self):
        """Videoyu ve kare önbelleğini bırakır (sayfalara dokunmaz)."""
        self.meta = None
        self._cache.clear()
        shutil.rmtree(self.dir, ignore_errors=True)
        self.changed.emit()

    # ------------------------------------------------------------ kare erişimi
    def _load(self, page):
        path = self.frame_path(page)
        if not os.path.isfile(path):
            return None
        img = QImage(path)
        if img.isNull():
            return None
        return img.convertToFormat(LAYER_FORMAT)

    def paint_frame(self):
        """Tuval çizimi için (QImage, opaklık) ya da None."""
        w = self.win
        if not self.active or not w.global_reference_visible:
            return None
        page = w.current_page_index
        img = self._cache.get(page)
        if img is None:
            img = self._load(page)
            if img is None:
                return None
            self._cache[page] = img
            while len(self._cache) > self.CACHE_FRAMES:
                self._cache.popitem(last=False)
        else:
            self._cache.move_to_end(page)
        return img, self.opacity / 100.0

    def under_spec(self, page):
        """Oynatma / dışa aktarma için (dosya yolu, opaklık) ya da None (iş parçacığı güvenli veri)."""
        if not self.active or not self.win.global_reference_visible:
            return None
        path = self.frame_path(page)
        return (path, self.opacity / 100.0) if os.path.isfile(path) else None

    def set_opacity(self, v):
        self.opacity = max(5, min(100, int(v)))
        QSettings("kavram", "DrawingEditor").setValue("videoOpacity", self.opacity)
        self.win.drawing_area.update()
        if self.active:
            self.win.is_project_modified = True

    # ------------------------------------------------------------ içe aktarma
    def import_video(self):
        win = self.win
        if self.busy():
            return
        if self.active:
            QMessageBox.information(win, "Referans Video", "Projede zaten bir video var. Önce kaldırın.")
            return
        if not ffmpeg_available():
            QMessageBox.critical(win, "Hata", f"Video için ffmpeg gerekli, bulunamadı:\n{FFMPEG_PATH}")
            return
        if getattr(win.anim, "is_playing", False):
            win.anim.stop()
        if project_has_drawing(win):
            QMessageBox.warning(win, "Video eklenemez",
                                "Videonun en-boy oranı çizim alanını belirlediği için, çizim yapıldıktan sonra "
                                "video eklenemez.\n\nBoş bir projede (hiçbir karede çizim yokken) deneyin.")
            return
        path, _ = QFileDialog.getOpenFileName(win, "Referans video seç", "",
                                              "Video (*.mp4 *.mov *.mkv *.avi *.webm *.m4v *.gif);;Tümü (*)")
        if not path:
            return
        try:
            info = probe_video(path)
        except Exception as e:
            QMessageBox.critical(win, "Hata", f"Video okunamadı:\n{e}")
            return
        dlg = VideoImportDialog(win, info, win.max_pages)
        if dlg.exec_() != QDialog.Accepted:
            return
        o = dlg.options()
        cw, ch = dlg.canvas_size
        # Çizim yok: çizim alanını videoya uydur
        self.resizing_allowed = True
        try:
            win.applyNewResolution(cw, ch)
        finally:
            self.resizing_allowed = False
        meta = {"path": os.path.abspath(path), "start": o["start"], "length": o["length"], "fps": o["fps"],
                "count": 0, "src_w": info["w"], "src_h": info["h"], "canvas_w": cw, "canvas_h": ch}
        self._extract(meta, restoring=False)

    def _extract(self, meta, restoring):
        win = self.win
        params = {"out_dir": self.dir, "path": meta["path"], "start": meta["start"], "length": meta["length"],
                  "fps": meta["fps"], "w": meta["canvas_w"], "h": meta["canvas_h"], "max_frames": win.max_pages}
        self._worker = FrameExtractor(params)
        prog = QProgressDialog("Video kareleri çıkarılıyor…", "İptal", 0, 100, win)
        prog.setWindowTitle("Referans Video")
        prog.setWindowModality(Qt.WindowModal)
        prog.setMinimumDuration(0)
        prog.setAutoClose(False)
        prog.setAutoReset(False)
        prog.setValue(0)
        self._progress = prog

        def close_prog():
            try:
                prog.canceled.disconnect()
            except TypeError:
                pass
            prog.close()

        def on_progress(v, msg):
            prog.setValue(v)
            prog.setLabelText(msg)

        def on_done(count):
            close_prog()
            self._worker = None
            self._cache.clear()
            meta["count"] = count
            self.meta = meta
            if not restoring:
                win.adoptPageCount(count)
                win.is_project_modified = True
            win.current_export_fps = int(meta["fps"])           # oynatma / dışa aktarma video hızında
            if hasattr(win, "timeline"):
                win.timeline.fps_spin.blockSignals(True)
                win.timeline.fps_spin.setValue(int(meta["fps"]))
                win.timeline.fps_spin.blockSignals(False)
            win.drawing_area.update()
            self.changed.emit()

        def on_failed(msg):
            close_prog()
            self._worker = None
            if msg:
                QMessageBox.critical(win, "Hata", f"Video kareleri çıkarılamadı:\n{msg}")
            if not restoring:
                self.meta = None
            self.changed.emit()

        self._worker.progress.connect(on_progress)
        self._worker.done.connect(on_done)
        self._worker.failed.connect(on_failed)
        prog.canceled.connect(self._worker.cancel)
        self._worker.start()

    # ------------------------------------------------------------ kaldır
    def remove_video(self):
        win = self.win
        if not self.active:
            return
        r = QMessageBox.question(win, "Videoyu Kaldır",
                                 "Referans video kaldırılsın mı? Kareler (sayfalar) ve çizimler korunur.",
                                 QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if r == QMessageBox.Yes:
            self.reset()
            win.is_project_modified = True
            win.drawing_area.update()

    # ------------------------------------------------------------ proje kaydı
    def to_meta(self, project_path=None):
        if not self.active:
            return None
        m = dict(self.meta)
        m["opacity"] = int(self.opacity)
        if project_path:
            try:
                m["rel_path"] = os.path.relpath(m["path"], os.path.dirname(os.path.abspath(project_path)))
            except ValueError:
                pass
        return m

    def restore(self, meta, project_path=None):
        """Proje açılırken: video bilgisini yükle, kareler yoksa videodan yeniden çıkar."""
        win = self.win
        self.reset()
        if not meta:
            return
        meta = dict(meta)
        self.opacity = int(meta.pop("opacity", self.opacity))
        path = meta.get("path", "")
        if not os.path.isfile(path) and meta.get("rel_path") and project_path:
            cand = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(project_path)), meta["rel_path"]))
            if os.path.isfile(cand):
                path = cand
        if not os.path.isfile(path):
            r = QMessageBox.question(win, "Referans Video",
                                     f"Proje videosu bulunamadı:\n{meta.get('path', '')}\n\nVideoyu şimdi seçmek ister misiniz?",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
            path = ""
            if r == QMessageBox.Yes:
                path, _ = QFileDialog.getOpenFileName(win, "Referans videoyu bul", "",
                                                      "Video (*.mp4 *.mov *.mkv *.avi *.webm *.m4v *.gif);;Tümü (*)")
            if not path:
                return
        meta["path"] = os.path.abspath(path)
        if not ffmpeg_available():
            QMessageBox.warning(win, "Referans Video", "ffmpeg bulunamadığından video kareleri alınamadı.")
            return
        self._extract(meta, restoring=True)
