#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Kavram Media Studio — combined video and audio editor (PyQt5).

This is a self-contained, integration-friendly QWidget module. It does not
modify Kavram's existing editors or file-manager implementation.

Requirements:
    PyQt5, PyQt5.QtMultimedia, FFmpeg (ffmpeg + ffprobe on PATH)

Features: media bin, video preview, separate video/audio clip lists, trim/split,
reorder/remove, JSON project files, and FFmpeg-based MP4/WAV/MP3 export.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional, List, Dict, Any

from PyQt5.QtCore import Qt, QUrl, QProcess, pyqtSignal
from PyQt5.QtGui import QFont, QKeySequence
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QSplitter,
    QFrame, QLabel, QPushButton, QListWidget, QListWidgetItem, QFileDialog,
    QMessageBox, QSlider, QLineEdit, QPlainTextEdit, QProgressBar, QComboBox,
    QInputDialog, QShortcut, QGroupBox, QSizePolicy, QAbstractItemView
)

try:
    from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
    from PyQt5.QtMultimediaWidgets import QVideoWidget
    QT_MULTIMEDIA_AVAILABLE = True
except Exception:
    QMediaPlayer = None  # type: ignore
    QMediaContent = None  # type: ignore
    QVideoWidget = None  # type: ignore
    QT_MULTIMEDIA_AVAILABLE = False

APP_NAME = "Kavram Media Studio"
PROJECT_VERSION = 1
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v", ".mpeg", ".mpg", ".wmv", ".ts", ".mts", ".mxf"}
AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac", ".ogg", ".opus", ".m4a", ".aac", ".wma", ".aiff", ".aif"}
MEDIA_FILTER = "Media files (*.mp4 *.mkv *.mov *.avi *.webm *.m4v *.mpeg *.mpg *.wmv *.ts *.mts *.mxf *.wav *.mp3 *.flac *.ogg *.opus *.m4a *.aac *.wma *.aiff *.aif);;All files (*)"
DARK_STYLE = """
QWidget { background: #17191d; color: #e6e8ec; font-size: 10pt; }
QMainWindow, QDialog { background: #17191d; }
QFrame, QGroupBox { border: 1px solid #343841; border-radius: 7px; }
QGroupBox { margin-top: 10px; padding-top: 8px; font-weight: 600; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; color: #c8ccd4; }
QPushButton { background: #292d34; border: 1px solid #414651; border-radius: 5px; padding: 7px 10px; }
QPushButton:hover { background: #353a44; border-color: #697384; }
QPushButton:pressed { background: #202329; }
QPushButton:disabled { color: #737985; background: #202329; }
QListWidget, QPlainTextEdit, QLineEdit, QComboBox { background: #111317; border: 1px solid #343841; border-radius: 5px; padding: 5px; selection-background-color: #8b3039; }
QListWidget::item { padding: 6px; border-bottom: 1px solid #24272d; }
QListWidget::item:selected { background: #71303a; color: #ffffff; }
QSlider::groove:horizontal { height: 5px; background: #363b45; border-radius: 2px; }
QSlider::handle:horizontal { background: #df5b65; width: 12px; margin: -5px 0; border-radius: 6px; }
QProgressBar { border: 1px solid #343841; border-radius: 4px; text-align: center; background: #111317; }
QProgressBar::chunk { background: #a43d49; border-radius: 3px; }
QScrollBar:vertical { background: #17191d; width: 11px; margin: 0; }
QScrollBar::handle:vertical { background: #454b56; min-height: 24px; border-radius: 4px; }
QScrollBar:horizontal { background: #17191d; height: 11px; margin: 0; }
QScrollBar::handle:horizontal { background: #454b56; min-width: 24px; border-radius: 4px; }
"""


def _run_probe(path: str) -> Dict[str, Any]:
    """Return basic stream metadata using ffprobe; raises a readable error."""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise RuntimeError("ffprobe bulunamadı. FFmpeg paketini kurup PATH'e ekleyin.")
    result = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries",
         "format=duration:stream=codec_type,width,height,duration",
         "-of", "json", path],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Medya dosyası okunamadı.")
    try:
        data = json.loads(result.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError("ffprobe geçerli bir medya bilgisi döndürmedi.") from exc
    streams = data.get("streams", [])
    fmt = data.get("format", {})
    duration = fmt.get("duration")
    if duration is None:
        vals = [s.get("duration") for s in streams if s.get("duration") is not None]
        duration = max((float(x) for x in vals), default=0.0)
    return {
        "duration_ms": max(0, int(float(duration or 0) * 1000)),
        "has_video": any(s.get("codec_type") == "video" for s in streams),
        "has_audio": any(s.get("codec_type") == "audio" for s in streams),
        "width": next((int(s["width"]) for s in streams if s.get("codec_type") == "video" and s.get("width")), 0),
        "height": next((int(s["height"]) for s in streams if s.get("codec_type") == "video" and s.get("height")), 0),
    }


def format_time(ms: Optional[int]) -> str:
    if ms is None:
        return "--:--.---"
    ms = max(0, int(ms))
    hours, rem = divmod(ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    seconds, milli = divmod(rem, 1000)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milli:03d}"
    return f"{minutes:02d}:{seconds:02d}.{milli:03d}"


@dataclass
class MediaAsset:
    path: str
    duration_ms: int
    has_video: bool
    has_audio: bool
    width: int = 0
    height: int = 0

    @property
    def name(self) -> str:
        return os.path.basename(self.path)


@dataclass
class TimelineClip:
    path: str
    in_ms: int
    out_ms: int
    position_ms: int = 0  # used by audio track; video clips are sequenced in list order

    @property
    def duration_ms(self) -> int:
        return max(0, self.out_ms - self.in_ms)

    @property
    def name(self) -> str:
        return os.path.basename(self.path)


class MediaSoundEditor(QWidget):
    """Combined video/audio editing widget, suitable for hosting inside Kavram."""
    projectChanged = pyqtSignal(bool)
    exportFinished = pyqtSignal(bool, str)

    def __init__(self, parent=None, core_window_ref=None):
        super().__init__(parent)
        self.core_window_ref = core_window_ref
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(1000, 680)
        self.resize(1320, 850)

        self.assets: Dict[str, MediaAsset] = {}
        self.video_clips: List[TimelineClip] = []
        self.audio_clips: List[TimelineClip] = []
        self.project_path: Optional[str] = None
        self.dirty = False
        self._loading_position = False
        self._duration_ms = 0
        self._process_duration_ms = 1
        self._export_log_buffer = ""
        self.export_process: Optional[QProcess] = None
        self._clip_selection_track = "video"

        self._build_ui()
        self._connect_ui()
        self._init_player()
        self._install_shortcuts()
        self._refresh_timeline_labels()
        self._update_title()

    # ------------------------------- UI ---------------------------------
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        heading = QHBoxLayout()
        name = QLabel("KAVRAM  /  MEDIA STUDIO")
        name.setStyleSheet("font-size: 15pt; font-weight: 700; color: #f1f2f4; letter-spacing: 1px;")
        self.project_label = QLabel("Proje kaydedilmedi")
        self.project_label.setStyleSheet("color: #a8aeb8;")
        heading.addWidget(name)
        heading.addStretch(1)
        heading.addWidget(self.project_label)
        root.addLayout(heading)

        toolbar = QHBoxLayout()
        self.btn_new = self._button("Yeni Proje")
        self.btn_open_project = self._button("Proje Aç")
        self.btn_save_project = self._button("Projeyi Kaydet")
        self.btn_import = self._button("Medya İçe Aktar")
        self.btn_add_video = self._button("Video İzine Ekle")
        self.btn_add_audio = self._button("Ses İzine Ekle")
        self.btn_export_video = self._button("Video Dışa Aktar")
        self.btn_export_audio = self._button("Ses Dışa Aktar")
        for button in (self.btn_new, self.btn_open_project, self.btn_save_project,
                       self.btn_import, self.btn_add_video, self.btn_add_audio,
                       self.btn_export_video, self.btn_export_audio):
            toolbar.addWidget(button)
        toolbar.addStretch(1)
        root.addLayout(toolbar)

        main_split = QSplitter(Qt.Horizontal)
        main_split.setChildrenCollapsible(False)

        library_box = QGroupBox("Medya Kitaplığı")
        library_layout = QVBoxLayout(library_box)
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Medya ara…")
        self.media_list = QListWidget()
        self.media_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.media_info = QLabel("Henüz medya eklenmedi")
        self.media_info.setWordWrap(True)
        self.media_info.setStyleSheet("color: #a8aeb8; padding: 3px;")
        self.btn_remove_asset = self._button("Kitaplıktan Kaldır")
        library_layout.addWidget(self.search_box)
        library_layout.addWidget(self.media_list, 1)
        library_layout.addWidget(self.media_info)
        library_layout.addWidget(self.btn_remove_asset)
        main_split.addWidget(library_box)

        preview_box = QGroupBox("Önizleme")
        preview_layout = QVBoxLayout(preview_box)
        self.preview_holder = QFrame()
        self.preview_holder.setStyleSheet("QFrame { background: #08090b; border: 1px solid #343841; border-radius: 5px; }")
        holder_layout = QVBoxLayout(self.preview_holder)
        holder_layout.setContentsMargins(0, 0, 0, 0)
        if QT_MULTIMEDIA_AVAILABLE:
            self.video_widget = QVideoWidget(self.preview_holder)
            holder_layout.addWidget(self.video_widget)
        else:
            self.video_widget = None
            fallback = QLabel("QtMultimedia bulunamadı. Önizleme için PyQt5 multimedia bileşenleri gerekli.")
            fallback.setAlignment(Qt.AlignCenter)
            fallback.setWordWrap(True)
            fallback.setStyleSheet("color: #9ea5af; padding: 20px; border: none;")
            holder_layout.addWidget(fallback)
        self.preview_holder.setMinimumHeight(280)
        preview_layout.addWidget(self.preview_holder, 1)

        transport = QHBoxLayout()
        self.btn_play = self._button("▶ Oynat")
        self.btn_stop = self._button("■ Durdur")
        self.time_label = QLabel("00:00.000 / 00:00.000")
        self.time_label.setMinimumWidth(180)
        self.seek_slider = QSlider(Qt.Horizontal)
        self.seek_slider.setRange(0, 0)
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(75)
        self.volume_slider.setMaximumWidth(100)
        transport.addWidget(self.btn_play)
        transport.addWidget(self.btn_stop)
        transport.addWidget(self.time_label)
        preview_layout.addLayout(transport)
        preview_layout.addWidget(self.seek_slider)
        vol_layout = QHBoxLayout()
        vol_layout.addWidget(QLabel("Ses"))
        vol_layout.addWidget(self.volume_slider)
        vol_layout.addStretch(1)
        preview_layout.addLayout(vol_layout)
        main_split.addWidget(preview_box)
        main_split.setStretchFactor(0, 1)
        main_split.setStretchFactor(1, 3)
        main_split.setSizes([290, 800])
        root.addWidget(main_split, 5)

        tracks_split = QSplitter(Qt.Horizontal)
        tracks_split.setChildrenCollapsible(False)
        video_box = QGroupBox("VIDEO İZİ  ·  Klipler sırayla oynatılır")
        video_layout = QVBoxLayout(video_box)
        self.video_timeline = QListWidget()
        self.video_timeline.setSelectionMode(QAbstractItemView.SingleSelection)
        video_controls = QHBoxLayout()
        self.btn_video_up = self._button("↑ Yukarı")
        self.btn_video_down = self._button("↓ Aşağı")
        self.btn_video_remove = self._button("Klibi Sil")
        for b in (self.btn_video_up, self.btn_video_down, self.btn_video_remove):
            video_controls.addWidget(b)
        video_layout.addWidget(self.video_timeline, 1)
        video_layout.addLayout(video_controls)
        tracks_split.addWidget(video_box)

        audio_box = QGroupBox("SES İZİ  ·  Zaman imlecine göre mikslenir")
        audio_layout = QVBoxLayout(audio_box)
        self.audio_timeline = QListWidget()
        self.audio_timeline.setSelectionMode(QAbstractItemView.SingleSelection)
        audio_controls = QHBoxLayout()
        self.btn_audio_set_position = self._button("İmlece Yerleştir")
        self.btn_audio_remove = self._button("Klibi Sil")
        self.btn_audio_up = self._button("↑ Yukarı")
        self.btn_audio_down = self._button("↓ Aşağı")
        for b in (self.btn_audio_set_position, self.btn_audio_up, self.btn_audio_down, self.btn_audio_remove):
            audio_controls.addWidget(b)
        audio_layout.addWidget(self.audio_timeline, 1)
        audio_layout.addLayout(audio_controls)
        tracks_split.addWidget(audio_box)
        tracks_split.setStretchFactor(0, 1)
        tracks_split.setStretchFactor(1, 1)
        tracks_split.setSizes([1, 1])
        root.addWidget(tracks_split, 3)

        edit_controls = QHBoxLayout()
        self.btn_set_in = self._button("Giriş Noktası")
        self.btn_set_out = self._button("Çıkış Noktası")
        self.btn_split = self._button("Oynatma Konumundan Böl")
        self.active_track_combo = QComboBox()
        self.active_track_combo.addItems(["Video izi", "Ses izi"])
        self.trim_label = QLabel("Klip seçip önizlemede giriş/çıkış noktalarını belirleyin.")
        self.trim_label.setStyleSheet("color: #b2b8c1;")
        edit_controls.addWidget(self.active_track_combo)
        edit_controls.addWidget(self.btn_set_in)
        edit_controls.addWidget(self.btn_set_out)
        edit_controls.addWidget(self.btn_split)
        edit_controls.addWidget(self.trim_label, 1)
        root.addLayout(edit_controls)

        bottom = QHBoxLayout()
        self.status_label = QLabel("Hazır")
        self.status_label.setStyleSheet("color: #a8aeb8;")
        self.export_progress = QProgressBar()
        self.export_progress.setRange(0, 100)
        self.export_progress.setValue(0)
        self.export_progress.setMaximumWidth(260)
        bottom.addWidget(self.status_label, 1)
        bottom.addWidget(self.export_progress)
        root.addLayout(bottom)

        log_box = QGroupBox("İşlem Günlüğü")
        log_layout = QVBoxLayout(log_box)
        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setMaximumBlockCount(2000)
        self.log_output.setMaximumHeight(115)
        log_layout.addWidget(self.log_output)
        root.addWidget(log_box)
        self.setStyleSheet(DARK_STYLE)

    def _button(self, text: str) -> QPushButton:
        b = QPushButton(text)
        b.setCursor(Qt.PointingHandCursor)
        b.setMinimumHeight(31)
        return b

    def _connect_ui(self):
        self.btn_new.clicked.connect(self.new_project)
        self.btn_open_project.clicked.connect(self.open_project_dialog)
        self.btn_save_project.clicked.connect(self.save_project_dialog)
        self.btn_import.clicked.connect(self.import_media)
        self.btn_add_video.clicked.connect(lambda: self.add_selected_asset("video"))
        self.btn_add_audio.clicked.connect(lambda: self.add_selected_asset("audio"))
        self.btn_remove_asset.clicked.connect(self.remove_selected_asset)
        self.btn_play.clicked.connect(self.toggle_play)
        self.btn_stop.clicked.connect(self.stop_preview)
        self.seek_slider.sliderMoved.connect(self.seek_to)
        self.volume_slider.valueChanged.connect(self.set_volume)
        self.media_list.currentItemChanged.connect(self._media_selection_changed)
        self.search_box.textChanged.connect(self._filter_media)
        self.video_timeline.currentRowChanged.connect(lambda row: self._timeline_selection_changed("video", row))
        self.audio_timeline.currentRowChanged.connect(lambda row: self._timeline_selection_changed("audio", row))
        self.active_track_combo.currentIndexChanged.connect(self._active_track_changed)
        self.btn_set_in.clicked.connect(self.set_clip_in)
        self.btn_set_out.clicked.connect(self.set_clip_out)
        self.btn_split.clicked.connect(self.split_selected_clip)
        self.btn_video_up.clicked.connect(lambda: self.move_selected_clip("video", -1))
        self.btn_video_down.clicked.connect(lambda: self.move_selected_clip("video", 1))
        self.btn_video_remove.clicked.connect(lambda: self.remove_selected_clip("video"))
        self.btn_audio_up.clicked.connect(lambda: self.move_selected_clip("audio", -1))
        self.btn_audio_down.clicked.connect(lambda: self.move_selected_clip("audio", 1))
        self.btn_audio_remove.clicked.connect(lambda: self.remove_selected_clip("audio"))
        self.btn_audio_set_position.clicked.connect(self.position_audio_clip_at_playhead)
        self.btn_export_video.clicked.connect(self.export_video_dialog)
        self.btn_export_audio.clicked.connect(self.export_audio_dialog)

    def _init_player(self):
        self.player = None
        if QT_MULTIMEDIA_AVAILABLE:
            try:
                self.player = QMediaPlayer(self, QMediaPlayer.VideoSurface)
                self.player.setVideoOutput(self.video_widget)
                self.player.positionChanged.connect(self._position_changed)
                self.player.durationChanged.connect(self._duration_changed)
                self.player.stateChanged.connect(self._player_state_changed)
                self.player.mediaStatusChanged.connect(self._media_status_changed)
                self.player.error.connect(self._player_error)
                self.player.setVolume(self.volume_slider.value())
            except Exception as exc:
                self._log(f"QtMultimedia başlatılamadı: {exc}")
                self.player = None
        if not shutil.which("ffmpeg"):
            self._log("Uyarı: ffmpeg PATH içinde bulunamadı; düzenleme arayüzü açılır ancak dışa aktarma yapılamaz.")

    def _install_shortcuts(self):
        for sequence, callback in (("Space", self.toggle_play), ("Ctrl+S", self.save_project_dialog),
                                   ("Ctrl+O", self.open_project_dialog), ("Ctrl+I", self.import_media),
                                   ("Delete", self.delete_active_selection)):
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.activated.connect(callback)

    # -------------------------- Media library ----------------------------
    def import_media(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Medya içe aktar", "", MEDIA_FILTER)
        if not paths:
            return
        added = 0
        for path in paths:
            path = os.path.abspath(path)
            if path in self.assets:
                continue
            try:
                meta = _run_probe(path)
                if not meta["has_video"] and not meta["has_audio"]:
                    self._log(f"Atlandı: ses/video akışı bulunamadı — {path}")
                    continue
                asset = MediaAsset(path, meta["duration_ms"], meta["has_video"], meta["has_audio"], meta["width"], meta["height"])
                self.assets[path] = asset
                item = QListWidgetItem(f"{'▣' if asset.has_video else '♫'}  {asset.name}")
                item.setToolTip(path)
                item.setData(Qt.UserRole, path)
                self.media_list.addItem(item)
                added += 1
                self._log(f"İçe aktarıldı: {asset.name} ({format_time(asset.duration_ms)})")
            except Exception as exc:
                QMessageBox.warning(self, "Medya okunamadı", f"{path}\n\n{exc}")
        if added:
            self._set_dirty(True)
            self.status_label.setText(f"{added} medya dosyası eklendi")

    def _filter_media(self, text: str):
        query = text.casefold().strip()
        for i in range(self.media_list.count()):
            item = self.media_list.item(i)
            item.setHidden(query not in item.text().casefold() and query not in str(item.data(Qt.UserRole)).casefold())

    def _selected_asset(self) -> Optional[MediaAsset]:
        item = self.media_list.currentItem()
        return self.assets.get(item.data(Qt.UserRole)) if item else None

    def _media_selection_changed(self, current, previous):
        if not current:
            self.media_info.setText("Medya seçilmedi")
            return
        path = current.data(Qt.UserRole)
        asset = self.assets.get(path)
        if not asset:
            return
        kind = "Video + Ses" if asset.has_video and asset.has_audio else ("Video" if asset.has_video else "Ses")
        resolution = f"\n{asset.width} × {asset.height}" if asset.has_video and asset.width else ""
        self.media_info.setText(f"{asset.name}\n{kind} · {format_time(asset.duration_ms)}{resolution}")
        self._load_preview(path, 0)

    def remove_selected_asset(self):
        asset = self._selected_asset()
        if not asset:
            return
        path = asset.path
        used = any(c.path == path for c in self.video_clips + self.audio_clips)
        if used:
            answer = QMessageBox.question(self, "Medya kullanımda", "Bu dosya zaman çizelgesinde kullanılıyor. Kitaplıktan kaldırmak yine de devam etsin mi?")
            if answer != QMessageBox.Yes:
                return
        self.assets.pop(path, None)
        row = self.media_list.currentRow()
        self.media_list.takeItem(row)
        self._set_dirty(True)
        self._log(f"Kitaplıktan kaldırıldı: {os.path.basename(path)} (zaman çizelgesindeki klipler korunur)")

    # ---------------------------- Timeline -------------------------------
    def add_selected_asset(self, track: str):
        asset = self._selected_asset()
        if not asset:
            QMessageBox.information(self, "Medya seçin", "Önce medya kitaplığından bir dosya seçin.")
            return
        if track == "video" and not asset.has_video:
            QMessageBox.information(self, "Video yok", "Seçilen dosyada video akışı yok. Dosyayı ses izine ekleyebilirsiniz.")
            return
        if track == "audio" and not asset.has_audio:
            QMessageBox.information(self, "Ses yok", "Seçilen dosyada ses akışı yok.")
            return
        if asset.duration_ms <= 0:
            QMessageBox.warning(self, "Süre bilinmiyor", "Bu dosyanın süresi okunamadı; zaman çizelgesine eklenemiyor.")
            return
        # Audio clips are overlays and start at timeline zero by default; users can
        # position them at the preview cursor with "İmlece Yerleştir".
        clip = TimelineClip(asset.path, 0, asset.duration_ms, 0)
        clips = self.video_clips if track == "video" else self.audio_clips
        clips.append(clip)
        self._set_dirty(True)
        self._refresh_timeline_labels()
        target = self.video_timeline if track == "video" else self.audio_timeline
        target.setCurrentRow(len(clips) - 1)
        self.active_track_combo.setCurrentIndex(0 if track == "video" else 1)
        self._load_preview(clip.path, clip.in_ms)
        self._log(f"{('Video' if track == 'video' else 'Ses')} izine eklendi: {clip.name}")

    def _timeline_selection_changed(self, track: str, row: int):
        if row < 0:
            return
        self._clip_selection_track = track
        self.active_track_combo.blockSignals(True)
        self.active_track_combo.setCurrentIndex(0 if track == "video" else 1)
        self.active_track_combo.blockSignals(False)
        clip = self._selected_clip(track)
        if clip:
            self._load_preview(clip.path, clip.in_ms)
            self.trim_label.setText(f"{clip.name} · {format_time(clip.in_ms)} → {format_time(clip.out_ms)} · {format_time(clip.duration_ms)}")

    def _active_track_changed(self, index: int):
        self._clip_selection_track = "video" if index == 0 else "audio"

    def _selected_clip(self, track: Optional[str] = None) -> Optional[TimelineClip]:
        track = track or self._clip_selection_track
        widget = self.video_timeline if track == "video" else self.audio_timeline
        clips = self.video_clips if track == "video" else self.audio_clips
        row = widget.currentRow()
        return clips[row] if 0 <= row < len(clips) else None

    def _refresh_timeline_labels(self):
        for widget, clips, track in ((self.video_timeline, self.video_clips, "V"), (self.audio_timeline, self.audio_clips, "A")):
            selected = widget.currentRow()
            widget.blockSignals(True)
            widget.clear()
            for index, clip in enumerate(clips):
                if track == "A":
                    label = f"{index + 1:02d}  {clip.name}  |  +{format_time(clip.position_ms)}  |  {format_time(clip.in_ms)}–{format_time(clip.out_ms)}"
                else:
                    label = f"{index + 1:02d}  {clip.name}  |  {format_time(clip.in_ms)}–{format_time(clip.out_ms)}  |  {format_time(clip.duration_ms)}"
                item = QListWidgetItem(label)
                item.setToolTip(clip.path)
                widget.addItem(item)
            if clips:
                widget.setCurrentRow(min(max(selected, 0), len(clips) - 1))
            widget.blockSignals(False)
        self._update_title()

    def _refresh_one_track(self, track: str, selected: Optional[int] = None):
        widget = self.video_timeline if track == "video" else self.audio_timeline
        clips = self.video_clips if track == "video" else self.audio_clips
        if selected is None:
            selected = widget.currentRow()
        widget.blockSignals(True)
        widget.clear()
        for idx, clip in enumerate(clips):
            label = (f"{idx + 1:02d}  {clip.name}  |  +{format_time(clip.position_ms)}  |  {format_time(clip.in_ms)}–{format_time(clip.out_ms)}"
                     if track == "audio" else f"{idx + 1:02d}  {clip.name}  |  {format_time(clip.in_ms)}–{format_time(clip.out_ms)}  |  {format_time(clip.duration_ms)}")
            item = QListWidgetItem(label)
            item.setToolTip(clip.path)
            widget.addItem(item)
        if clips:
            widget.setCurrentRow(min(max(selected, 0), len(clips) - 1))
        widget.blockSignals(False)

    def set_clip_in(self):
        clip = self._selected_clip()
        if not clip:
            QMessageBox.information(self, "Klip seçin", "Giriş noktası belirlemek için bir zaman çizelgesi klibi seçin.")
            return
        position = self.player.position() if self.player else clip.in_ms
        if position >= clip.out_ms:
            QMessageBox.warning(self, "Geçersiz nokta", "Giriş noktası çıkış noktasından önce olmalıdır.")
            return
        clip.in_ms = max(0, int(position))
        self._after_clip_edit()

    def set_clip_out(self):
        clip = self._selected_clip()
        if not clip:
            QMessageBox.information(self, "Klip seçin", "Çıkış noktası belirlemek için bir zaman çizelgesi klibi seçin.")
            return
        position = self.player.position() if self.player else clip.out_ms
        asset = self.assets.get(clip.path)
        max_ms = asset.duration_ms if asset else clip.out_ms
        if position <= clip.in_ms:
            QMessageBox.warning(self, "Geçersiz nokta", "Çıkış noktası giriş noktasından sonra olmalıdır.")
            return
        clip.out_ms = min(int(position), max_ms)
        self._after_clip_edit()

    def split_selected_clip(self):
        track = self._clip_selection_track
        widget = self.video_timeline if track == "video" else self.audio_timeline
        clips = self.video_clips if track == "video" else self.audio_clips
        row = widget.currentRow()
        clip = self._selected_clip(track)
        if not clip:
            QMessageBox.information(self, "Klip seçin", "Bölmek için zaman çizelgesinden bir klip seçin.")
            return
        pos = self.player.position() if self.player else -1
        if pos <= clip.in_ms or pos >= clip.out_ms:
            QMessageBox.information(self, "Bölme konumu", "Oynatma imleci, klibin giriş ve çıkış noktalarının arasında olmalıdır.")
            return
        right = TimelineClip(clip.path, int(pos), clip.out_ms, clip.position_ms)
        clip.out_ms = int(pos)
        if track == "audio":
            right.position_ms = clip.position_ms + clip.duration_ms
        clips.insert(row + 1, right)
        self._set_dirty(True)
        self._refresh_one_track(track, row + 1)
        self._refresh_duration()
        self._log(f"Klip bölündü: {clip.name} @ {format_time(pos)}")

    def move_selected_clip(self, track: str, step: int):
        clips = self.video_clips if track == "video" else self.audio_clips
        widget = self.video_timeline if track == "video" else self.audio_timeline
        row = widget.currentRow()
        target = row + step
        if row < 0 or target < 0 or target >= len(clips):
            return
        clips[row], clips[target] = clips[target], clips[row]
        self._set_dirty(True)
        self._refresh_one_track(track, target)
        self._refresh_duration()

    def remove_selected_clip(self, track: str):
        clips = self.video_clips if track == "video" else self.audio_clips
        widget = self.video_timeline if track == "video" else self.audio_timeline
        row = widget.currentRow()
        if row < 0 or row >= len(clips):
            return
        removed = clips.pop(row)
        self._set_dirty(True)
        self._refresh_one_track(track, min(row, len(clips) - 1))
        self._refresh_duration()
        self._log(f"Klip silindi: {removed.name}")

    def position_audio_clip_at_playhead(self):
        row = self.audio_timeline.currentRow()
        if row < 0:
            QMessageBox.information(self, "Ses klibi seçin", "Önce ses izinden bir klip seçin.")
            return
        self.audio_clips[row].position_ms = self._timeline_end_ms() if not self.video_clips else self._video_playhead_ms()
        self._set_dirty(True)
        self._refresh_one_track("audio", row)
        self._log(f"Ses klibi konumlandı: {self.audio_clips[row].name} @ {format_time(self.audio_clips[row].position_ms)}")

    def delete_active_selection(self):
        if self._clip_selection_track == "audio" and self.audio_timeline.currentRow() >= 0:
            self.remove_selected_clip("audio")
        elif self.video_timeline.currentRow() >= 0:
            self.remove_selected_clip("video")
        else:
            self.remove_selected_asset()

    def _after_clip_edit(self):
        self._set_dirty(True)
        self._refresh_one_track(self._clip_selection_track)
        clip = self._selected_clip()
        if clip:
            self.trim_label.setText(f"{clip.name} · {format_time(clip.in_ms)} → {format_time(clip.out_ms)} · {format_time(clip.duration_ms)}")
        self._refresh_duration()

    def _timeline_end_ms(self) -> int:
        if self.video_clips:
            return sum(c.duration_ms for c in self.video_clips)
        return max((c.position_ms + c.duration_ms for c in self.audio_clips), default=0)

    def _video_playhead_ms(self) -> int:
        # In this first release, preview position is used as the placement cursor.
        return int(self.player.position()) if self.player else self._timeline_end_ms()

    def _refresh_duration(self):
        self._duration_ms = self._timeline_end_ms()
        self.time_label.setText(f"{format_time(self.player.position() if self.player else 0)} / {format_time(self._duration_ms)}")

    # ------------------------------ Preview ------------------------------
    def _load_preview(self, path: str, position_ms: int = 0):
        if not self.player:
            self.status_label.setText("Önizleme için PyQt5 QtMultimedia bileşenleri gerekli")
            return
        try:
            self.player.stop()
            self.player.setMedia(QMediaContent(QUrl.fromLocalFile(os.path.abspath(path))))
            if position_ms > 0:
                self.player.setPosition(int(position_ms))
            self.player.setVolume(self.volume_slider.value())
            self.btn_play.setText("▶ Oynat")
        except Exception as exc:
            self._log(f"Önizleme açılamadı: {exc}")

    def toggle_play(self):
        if not self.player:
            QMessageBox.warning(self, "Önizleme kullanılamıyor", "PyQt5 QtMultimedia bileşenleri kurulu değil.")
            return
        if self.player.media().isNull():
            asset = self._selected_asset()
            clip = self._selected_clip()
            path = clip.path if clip else (asset.path if asset else None)
            if not path:
                QMessageBox.information(self, "Medya seçin", "Önizlemek için bir medya dosyası veya klip seçin.")
                return
            self._load_preview(path)
        if self.player.state() == QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def stop_preview(self):
        if self.player:
            self.player.stop()
            self.player.setPosition(0)

    def seek_to(self, position: int):
        if self.player:
            self.player.setPosition(int(position))

    def set_volume(self, value: int):
        if self.player:
            self.player.setVolume(int(value))

    def _position_changed(self, position: int):
        if not self.seek_slider.isSliderDown():
            self.seek_slider.blockSignals(True)
            self.seek_slider.setValue(position)
            self.seek_slider.blockSignals(False)
        duration = self.player.duration() if self.player else 0
        self.time_label.setText(f"{format_time(position)} / {format_time(duration)}")

    def _duration_changed(self, duration: int):
        self.seek_slider.setRange(0, max(0, int(duration)))
        self.time_label.setText(f"{format_time(self.player.position() if self.player else 0)} / {format_time(duration)}")

    def _player_state_changed(self, state):
        self.btn_play.setText("Ⅱ Duraklat" if state == QMediaPlayer.PlayingState else "▶ Oynat")

    def _media_status_changed(self, status):
        if self.player and status == QMediaPlayer.EndOfMedia:
            self.btn_play.setText("▶ Oynat")

    def _player_error(self, error):
        if self.player and error != QMediaPlayer.NoError:
            detail = self.player.errorString()
            if detail:
                self.status_label.setText("Önizleme hatası")
                self._log(f"QtMultimedia: {detail}")

    # ---------------------------- Projects -------------------------------
    def new_project(self):
        if not self._confirm_discard_changes():
            return
        self.project_path = None
        self.assets.clear()
        self.video_clips.clear()
        self.audio_clips.clear()
        self.media_list.clear()
        self.video_timeline.clear()
        self.audio_timeline.clear()
        self.media_info.setText("Henüz medya eklenmedi")
        if self.player:
            self.player.stop()
            self.player.setMedia(QMediaContent())
        self._set_dirty(False)
        self._refresh_duration()
        self._update_title()
        self._log("Yeni proje oluşturuldu.")

    def open_project_dialog(self):
        if not self._confirm_discard_changes():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Proje aç", "", "Kavram Media Studio (*.kmedia.json *.json);;All files (*)")
        if path:
            self.load_project(path)

    def load_project(self, path: str):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict) or data.get("format") != "KavramMediaStudio":
                raise ValueError("Bu dosya Kavram Media Studio proje dosyası değil.")
            assets: Dict[str, MediaAsset] = {}
            for item in data.get("assets", []):
                p = os.path.abspath(item["path"])
                if not os.path.isfile(p):
                    self._log(f"Dosya bulunamadı: {p}")
                    continue
                try:
                    meta = _run_probe(p)
                    assets[p] = MediaAsset(p, meta["duration_ms"], meta["has_video"], meta["has_audio"], meta["width"], meta["height"])
                except Exception as exc:
                    self._log(f"Medya atlandı: {p} — {exc}")
            def read_clips(key: str) -> List[TimelineClip]:
                result: List[TimelineClip] = []
                for item in data.get(key, []):
                    p = os.path.abspath(item.get("path", ""))
                    if not os.path.isfile(p):
                        continue
                    try:
                        meta = _run_probe(p)
                        if p not in assets:
                            assets[p] = MediaAsset(p, meta["duration_ms"], meta["has_video"], meta["has_audio"], meta["width"], meta["height"])
                        duration = meta["duration_ms"]
                        start = max(0, min(int(item.get("in_ms", 0)), duration))
                        end = max(start + 1, min(int(item.get("out_ms", duration)), duration))
                        result.append(TimelineClip(p, start, end, max(0, int(item.get("position_ms", 0)))))
                    except Exception as exc:
                        self._log(f"Klip atlandı: {p} — {exc}")
                return result
            self.assets = assets
            self.video_clips = read_clips("video_clips")
            self.audio_clips = read_clips("audio_clips")
            self.media_list.clear()
            for asset in self.assets.values():
                item = QListWidgetItem(f"{'▣' if asset.has_video else '♫'}  {asset.name}")
                item.setToolTip(asset.path)
                item.setData(Qt.UserRole, asset.path)
                self.media_list.addItem(item)
            self.project_path = os.path.abspath(path)
            self._set_dirty(False)
            self._refresh_timeline_labels()
            self._refresh_duration()
            self._update_title()
            self._log(f"Proje açıldı: {self.project_path}")
            self.status_label.setText("Proje açıldı")
        except Exception as exc:
            QMessageBox.critical(self, "Proje açılamadı", str(exc))

    def save_project_dialog(self):
        path = self.project_path
        if not path:
            path, _ = QFileDialog.getSaveFileName(self, "Projeyi kaydet", "Kavram-Proje.kmedia.json", "Kavram Media Studio (*.kmedia.json);;JSON (*.json)")
            if not path:
                return
            if not path.endswith(".json"):
                path += ".kmedia.json"
        self.save_project(path)

    def save_project(self, path: str):
        data = {
            "format": "KavramMediaStudio",
            "version": PROJECT_VERSION,
            "assets": [asdict(asset) for asset in self.assets.values()],
            "video_clips": [asdict(clip) for clip in self.video_clips],
            "audio_clips": [asdict(clip) for clip in self.audio_clips],
        }
        try:
            path = os.path.abspath(path)
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            temp_path = path + ".tmp"
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(temp_path, path)
            self.project_path = path
            self._set_dirty(False)
            self._update_title()
            self.status_label.setText("Proje kaydedildi")
            self._log(f"Proje kaydedildi: {path}")
        except Exception as exc:
            QMessageBox.critical(self, "Kaydetme hatası", str(exc))

    def _confirm_discard_changes(self) -> bool:
        if not self.dirty:
            return True
        result = QMessageBox.question(self, "Kaydedilmemiş değişiklikler", "Projede kaydedilmemiş değişiklikler var. Devam edilsin mi?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        return result == QMessageBox.Yes

    def _set_dirty(self, dirty: bool):
        self.dirty = bool(dirty)
        self._update_title()
        self.projectChanged.emit(self.dirty)

    def _update_title(self):
        base = os.path.basename(self.project_path) if self.project_path else "Yeni Proje"
        star = " *" if self.dirty else ""
        self.project_label.setText(base + star)
        self.setWindowTitle(f"{APP_NAME} — {base}{star}")

    # ------------------------------ Export -------------------------------
    def export_video_dialog(self):
        if not shutil.which("ffmpeg"):
            QMessageBox.critical(self, "FFmpeg bulunamadı", "Dışa aktarmak için ffmpeg kurulu ve PATH üzerinde olmalıdır.")
            return
        if not self.video_clips and not self.audio_clips:
            QMessageBox.information(self, "Zaman çizelgesi boş", "Önce video veya ses izine klip ekleyin.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Videoyu dışa aktar", "Kavram-Export.mp4", "MP4 video (*.mp4)")
        if path:
            if not path.lower().endswith(".mp4"):
                path += ".mp4"
            self._start_export(path, audio_only=False)

    def export_audio_dialog(self):
        if not shutil.which("ffmpeg"):
            QMessageBox.critical(self, "FFmpeg bulunamadı", "Dışa aktarmak için ffmpeg kurulu ve PATH üzerinde olmalıdır.")
            return
        if not self.video_clips and not self.audio_clips:
            QMessageBox.information(self, "Zaman çizelgesi boş", "Önce video veya ses izine klip ekleyin.")
            return
        path, selected = QFileDialog.getSaveFileName(self, "Sesi dışa aktar", "Kavram-Audio.wav", "WAV ses (*.wav);;MP3 ses (*.mp3)")
        if path:
            if not os.path.splitext(path)[1]:
                path += ".mp3" if "MP3" in selected else ".wav"
            self._start_export(path, audio_only=True)

    def _start_export(self, output_path: str, audio_only: bool):
        if self.export_process and self.export_process.state() != QProcess.NotRunning:
            QMessageBox.information(self, "Dışa aktarma sürüyor", "Mevcut dışa aktarma bitmeden yenisi başlatılamaz.")
            return
        try:
            args, duration = self._build_ffmpeg_command(output_path, audio_only)
        except Exception as exc:
            QMessageBox.critical(self, "Dışa aktarma hazırlanamadı", str(exc))
            return
        self._process_duration_ms = max(1, duration)
        self._export_log_buffer = ""
        self.export_progress.setValue(0)
        self.status_label.setText("Dışa aktarılıyor…")
        self.btn_export_video.setEnabled(False)
        self.btn_export_audio.setEnabled(False)
        proc = QProcess(self)
        proc.setProgram(shutil.which("ffmpeg") or "ffmpeg")
        proc.setArguments(args)
        proc.setProcessChannelMode(QProcess.SeparateChannels)
        proc.readyReadStandardOutput.connect(self._read_export_stdout)
        proc.readyReadStandardError.connect(self._read_export_stderr)
        proc.finished.connect(self._export_process_finished)
        proc.errorOccurred.connect(self._export_process_error)
        self.export_process = proc
        self._log("FFmpeg dışa aktarma başlatıldı: " + output_path)
        proc.start()
        if not proc.waitForStarted(3000):
            self._export_cleanup()
            QMessageBox.critical(self, "FFmpeg başlatılamadı", proc.errorString())

    def _build_ffmpeg_command(self, output_path: str, audio_only: bool):
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise RuntimeError("ffmpeg bulunamadı.")
        if not self.video_clips and not self.audio_clips:
            raise RuntimeError("Zaman çizelgesi boş.")

        video_clips = list(self.video_clips)
        audio_clips = list(self.audio_clips)
        video_assets: List[MediaAsset] = []
        audio_assets: List[MediaAsset] = []
        for clip in video_clips:
            asset = self.assets.get(clip.path)
            if asset is None:
                meta = _run_probe(clip.path)
                asset = MediaAsset(clip.path, meta["duration_ms"], meta["has_video"], meta["has_audio"], meta["width"], meta["height"])
            if not asset.has_video:
                raise RuntimeError(f"Video izindeki klipte video akışı yok: {clip.name}")
            video_assets.append(asset)
        for clip in audio_clips:
            asset = self.assets.get(clip.path)
            if asset is None:
                meta = _run_probe(clip.path)
                asset = MediaAsset(clip.path, meta["duration_ms"], meta["has_video"], meta["has_audio"], meta["width"], meta["height"])
            if not asset.has_audio:
                raise RuntimeError(f"Ses izindeki klipte ses akışı yok: {clip.name}")
            audio_assets.append(asset)

        video_duration = sum(c.duration_ms for c in video_clips)
        if video_clips:
            total_ms = video_duration
        else:
            total_ms = max((c.position_ms + c.duration_ms for c in audio_clips), default=0)
        if total_ms <= 0:
            raise RuntimeError("Dışa aktarılabilecek süre sıfır.")

        inputs: List[str] = []
        for clip in video_clips:
            inputs += ["-i", clip.path]
        video_count = len(video_clips)
        for clip in audio_clips:
            inputs += ["-i", clip.path]

        filters: List[str] = []
        if video_clips:
            vlabels, alabels, concat_inputs = [], [], []
            for i, (clip, asset) in enumerate(zip(video_clips, video_assets)):
                start = clip.in_ms / 1000.0
                end = clip.out_ms / 1000.0
                dur = clip.duration_ms / 1000.0
                if not audio_only:
                    filters.append(f"[{i}:v:0]trim=start={start:.3f}:end={end:.3f},setpts=PTS-STARTPTS,scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30,format=yuv420p[v{i}]")
                    vlabels.append(f"[v{i}]")
                    concat_inputs.append(f"[v{i}][a{i}]")
                else:
                    concat_inputs.append(f"[a{i}]")
                if asset.has_audio:
                    filters.append(f"[{i}:a:0]atrim=start={start:.3f}:end={end:.3f},asetpts=PTS-STARTPTS,aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo[a{i}]")
                else:
                    filters.append(f"anullsrc=channel_layout=stereo:sample_rate=48000,atrim=duration={dur:.3f},asetpts=PTS-STARTPTS[a{i}]")
                alabels.append(f"[a{i}]")
            if audio_only:
                filters.append("".join(alabels) + f"concat=n={len(video_clips)}:v=0:a=1[abase]")
            else:
                filters.append("".join(concat_inputs) + f"concat=n={len(video_clips)}:v=1:a=1[vbase][abase]")
        else:
            seconds = total_ms / 1000.0
            if not audio_only:
                filters.append(f"color=c=black:s=1280x720:r=30:d={seconds:.3f},format=yuv420p[vbase]")
            filters.append(f"anullsrc=channel_layout=stereo:sample_rate=48000,atrim=duration={seconds:.3f},asetpts=PTS-STARTPTS[abase]")

        ext_labels = []
        for j, clip in enumerate(audio_clips):
            input_index = video_count + j
            start = clip.in_ms / 1000.0
            end = clip.out_ms / 1000.0
            delay = max(0, int(clip.position_ms))
            label = f"ext{j}"
            filters.append(f"[{input_index}:a:0]atrim=start={start:.3f}:end={end:.3f},asetpts=PTS-STARTPTS,aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,adelay={delay}|{delay},atrim=duration={total_ms / 1000.0:.3f}[{label}]")
            ext_labels.append(f"[{label}]")
        if ext_labels:
            filters.append("[abase]" + "".join(ext_labels) + f"amix=inputs={len(ext_labels) + 1}:duration=first:dropout_transition=0,atrim=duration={total_ms / 1000.0:.3f}[aout]")
        else:
            filters.append(f"[abase]atrim=duration={total_ms / 1000.0:.3f}[aout]")

        args = ["-y", *inputs, "-filter_complex", ";".join(filters), "-map", "[aout]"]
        if audio_only:
            suffix = Path(output_path).suffix.lower()
            if suffix == ".mp3":
                args += ["-vn", "-c:a", "libmp3lame", "-q:a", "2"]
            else:
                args += ["-vn", "-c:a", "pcm_s16le", "-ar", "48000"]
        else:
            args += ["-map", "[vbase]", "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart"]
        args += ["-progress", "pipe:1", "-nostats", output_path]
        return args, total_ms

    def _read_export_stdout(self):
        if not self.export_process:
            return
        raw = bytes(self.export_process.readAllStandardOutput()).decode("utf-8", "replace")
        for line in raw.splitlines():
            if line.startswith("out_time_ms="):
                try:
                    out_time_ms = int(line.split("=", 1)[1]) // 1000
                    pct = int(min(100, out_time_ms * 100 / self._process_duration_ms))
                    self.export_progress.setValue(pct)
                except ValueError:
                    pass
            elif line.startswith("progress=end"):
                self.export_progress.setValue(100)

    def _read_export_stderr(self):
        if not self.export_process:
            return
        raw = bytes(self.export_process.readAllStandardError()).decode("utf-8", "replace")
        if raw:
            self._export_log_buffer += raw
            # Keep the last lines as a useful diagnostic without flooding the UI.
            lines = [line for line in self._export_log_buffer.splitlines() if line.strip()]
            if len(lines) > 120:
                self._export_log_buffer = "\n".join(lines[-120:])

    def _export_process_finished(self, exit_code: int, exit_status):
        proc = self.export_process
        error_text = self._export_log_buffer.strip()
        success = exit_code == 0 and exit_status == QProcess.NormalExit
        self._export_cleanup()
        if success:
            self.export_progress.setValue(100)
            self.status_label.setText("Dışa aktarma tamamlandı")
            self._log("Dışa aktarma tamamlandı.")
            self.exportFinished.emit(True, "Dışa aktarma tamamlandı.")
            QMessageBox.information(self, "Dışa aktarma tamamlandı", "Dosya başarıyla oluşturuldu.")
        else:
            self.status_label.setText("Dışa aktarma başarısız")
            details = error_text[-5000:] if error_text else (proc.errorString() if proc else "Bilinmeyen FFmpeg hatası")
            self._log("FFmpeg hatası: " + (details[-1200:] if details else "bilinmeyen hata"))
            QMessageBox.critical(self, "Dışa aktarma başarısız", details or "FFmpeg beklenmeyen bir hata verdi.")
            self.exportFinished.emit(False, details)

    def _export_process_error(self, error):
        if self.export_process and self.export_process.state() == QProcess.NotRunning:
            msg = self.export_process.errorString()
            self._log(f"FFmpeg süreç hatası: {msg}")
            self._export_cleanup()

    def _export_cleanup(self):
        self.btn_export_video.setEnabled(True)
        self.btn_export_audio.setEnabled(True)
        if self.export_process:
            self.export_process.deleteLater()
        self.export_process = None

    # ------------------------------- Misc --------------------------------
    def _log(self, message: str):
        self.log_output.appendPlainText(message)
        self.status_label.setText(message[:160])

    def closeEvent(self, event):
        if not self._confirm_discard_changes():
            event.ignore()
            return
        if self.export_process and self.export_process.state() != QProcess.NotRunning:
            answer = QMessageBox.question(self, "Dışa aktarma sürüyor", "Dışa aktarma işlemi sürüyor. Kapatılırsa iptal edilsin mi?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if answer != QMessageBox.Yes:
                event.ignore()
                return
            self.export_process.kill()
            self.export_process.waitForFinished(1500)
        if self.player:
            self.player.stop()
        event.accept()


# Alias provides a simple, stable name for host applications.
MediaEditorWindow = MediaSoundEditor


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")
    window = MediaSoundEditor()
    window.show()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
