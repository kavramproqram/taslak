# Kavram IDE — professional editor module
# Copyright (C) 2026 Kavram or Contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""A modular PyQt5 code editor intended to be embedded in Kavram.

Supported source highlighting: Python, C/C++, Lua, JSON, shell and plain text.
Run commands are local and explicit: Python runs with the current interpreter;
C/C++ compiles with g++/clang++ before execution; Lua uses the `lua` executable.
"""

import os
import sys
import shlex
import shutil
import subprocess
from pathlib import Path

from PyQt5.QtCore import Qt, QSize, QProcess, QSettings, QTimer
from PyQt5.QtGui import QColor, QFont, QPainter, QTextFormat, QTextCursor, QKeySequence, QSyntaxHighlighter, QTextCharFormat
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QPlainTextEdit, QTextEdit, QTreeView,
    QFileSystemModel, QTabWidget, QDockWidget, QToolBar, QAction, QFileDialog,
    QMessageBox, QStatusBar, QLabel, QLineEdit, QComboBox, QHBoxLayout,
    QVBoxLayout, QPushButton, QSplitter, QInputDialog, QMenu, QShortcut
)

APP_NAME = "Kavram Code Editor"
SOURCE_EXTENSIONS = {".py", ".pyw", ".c", ".h", ".cc", ".cpp", ".cxx", ".hpp", ".lua", ".json", ".sh", ".bash", ".txt", ".md"}

DARK_STYLE = """
QMainWindow, QWidget { background: #17191d; color: #e5e7eb; }
QMenuBar, QMenu, QToolBar { background: #202329; color: #e5e7eb; border: 0; }
QMenu::item:selected { background: #343943; }
QToolButton, QPushButton { background: #292d34; color: #e5e7eb; border: 1px solid #3c424d; border-radius: 5px; padding: 5px 9px; }
QToolButton:hover, QPushButton:hover { background: #363c47; }
QLineEdit, QComboBox, QPlainTextEdit, QTextEdit, QTreeView, QTabWidget::pane { background: #111317; color: #e5e7eb; border: 1px solid #303640; selection-background-color: #354b68; }
QTabBar::tab { background: #22262d; color: #b8bec8; padding: 8px 13px; border: 1px solid #303640; }
QTabBar::tab:selected { background: #111317; color: #ffffff; border-bottom: 2px solid #d34a4a; }
QDockWidget::title { background: #242830; padding: 6px; }
QStatusBar { background: #242830; color: #b9c0ca; }
QScrollBar:vertical { background: #17191d; width: 12px; }
QScrollBar::handle:vertical { background: #454b56; min-height: 24px; border-radius: 5px; }
"""


def _fmt(color, bold=False, italic=False):
    f = QTextCharFormat()
    f.setForeground(QColor(color))
    if bold:
        f.setFontWeight(QFont.Bold)
    if italic:
        f.setFontItalic(True)
    return f


class CodeHighlighter(QSyntaxHighlighter):
    """Small dependency-free syntax highlighter for Python, C/C++, and Lua."""
    def __init__(self, document, language="text"):
        super().__init__(document)
        self.language = language
        self.rules = []
        self._build_rules()

    def set_language(self, language):
        self.language = language
        self._build_rules()
        self.rehighlight()

    def _build_rules(self):
        import re
        self.rules = []
        keyword_sets = {
            "python": "and as assert async await break class continue def del elif else except False finally for from global if import in is lambda None nonlocal not or pass raise return True try while with yield self match case",
            "cpp": "alignas alignof auto bool break case catch char class const constexpr continue default delete do double else enum explicit extern false float for friend goto if inline int long namespace new nullptr operator private protected public register return short signed sizeof static struct switch template this throw true try typedef typename union unsigned using virtual void volatile while std",
            "lua": "and break do else elseif end false for function goto if in local nil not or repeat return then true until while self",
            "shell": "if then else elif fi for while do done case esac function in export local return",
        }
        lang = self.language
        if lang in ("python", "cpp", "lua", "shell"):
            kw = keyword_sets.get(lang, "").split()
            self.rules.append((r"\b(?:" + "|".join(re.escape(k) for k in kw) + r")\b", _fmt("#c792ea", True)))
        self.rules += [
            (r"\b\d+(?:\.\d+)?\b", _fmt("#f78c6c")),
            (r"\b[A-Z_][A-Z0-9_]{2,}\b", _fmt("#ffcb6b")),
        ]
        if lang == "python":
            self.rules += [(r"#[^\n]*", _fmt("#697386", italic=True)), (r"@[\w.]+", _fmt("#82aaff"))]
        elif lang in ("cpp",):
            self.rules += [(r"//[^\n]*", _fmt("#697386", italic=True)), (r"/\*.*?\*/", _fmt("#697386", italic=True)), (r"#\s*\w+", _fmt("#c792ea"))]
        elif lang == "lua":
            self.rules += [(r"--[^\n]*", _fmt("#697386", italic=True))]
        elif lang == "shell":
            self.rules += [(r"#[^\n]*", _fmt("#697386", italic=True))]
        self.rules += [(r"\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'", _fmt("#c3e88d"))]

    def highlightBlock(self, text):
        import re
        for pattern, fmt in self.rules:
            for match in re.finditer(pattern, text):
                self.setFormat(match.start(), match.end() - match.start(), fmt)


class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self):
        return QSize(self.editor.line_number_width(), 0)

    def paintEvent(self, event):
        self.editor.paint_line_numbers(event)


class CodePane(QPlainTextEdit):
    def __init__(self, path=None, parent=None):
        super().__init__(parent)
        self.path = path
        self._saved_text = ""
        self.line_area = LineNumberArea(self)
        self.blockCountChanged.connect(self._update_line_area_width)
        self.updateRequest.connect(self._update_line_area)
        self.cursorPositionChanged.connect(self._highlight_current_line)
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.setTabStopDistance(4 * self.fontMetrics().horizontalAdvance(" "))
        font = QFont("Monospace")
        font.setStyleHint(QFont.TypeWriter)
        font.setPointSize(11)
        self.setFont(font)
        self.highlighter = CodeHighlighter(self.document(), self.language_for(path))
        self.textChanged.connect(self._refresh_dirty_state)
        self._update_line_area_width(0)
        self._highlight_current_line()

    @staticmethod
    def language_for(path):
        ext = Path(path or "").suffix.lower()
        return {".py": "python", ".pyw": "python", ".c": "cpp", ".h": "cpp", ".cc": "cpp", ".cpp": "cpp", ".cxx": "cpp", ".hpp": "cpp", ".lua": "lua", ".sh": "shell", ".bash": "shell", ".json": "json"}.get(ext, "text")

    def set_path(self, path):
        self.path = path
        self.highlighter.set_language(self.language_for(path))

    def is_dirty(self):
        return self.toPlainText() != self._saved_text

    def mark_saved(self):
        self._saved_text = self.toPlainText()
        self.document().setModified(False)

    def _refresh_dirty_state(self):
        self.document().setModified(self.is_dirty())
        window = self.window()
        if hasattr(window, "refresh_tab_titles"):
            window.refresh_tab_titles()

    def line_number_width(self):
        digits = max(2, len(str(max(1, self.blockCount()))))
        return 12 + self.fontMetrics().horizontalAdvance("9") * digits

    def _update_line_area_width(self, _):
        self.setViewportMargins(self.line_number_width(), 0, 0, 0)

    def _update_line_area(self, rect, dy):
        if dy:
            self.line_area.scroll(0, dy)
        else:
            self.line_area.update(0, rect.y(), self.line_area.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_line_area_width(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.line_area.setGeometry(cr.left(), cr.top(), self.line_number_width(), cr.height())

    def paint_line_numbers(self, event):
        painter = QPainter(self.line_area)
        painter.fillRect(event.rect(), QColor("#191c21"))
        block = self.firstVisibleBlock()
        number = block.blockNumber()
        top = int(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + int(self.blockBoundingRect(block).height())
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                painter.setPen(QColor("#737d8d"))
                painter.drawText(0, top, self.line_area.width() - 5, self.fontMetrics().height(), Qt.AlignRight, str(number + 1))
            block = block.next()
            top = bottom
            bottom = top + int(self.blockBoundingRect(block).height())
            number += 1

    def _highlight_current_line(self):
        selections = []
        if not self.isReadOnly():
            selection = QTextEdit.ExtraSelection()
            selection.format.setBackground(QColor("#20252d"))
            selection.format.setProperty(QTextFormat.FullWidthSelection, True)
            selection.cursor = self.textCursor()
            selection.cursor.clearSelection()
            selections.append(selection)
        self.setExtraSelections(selections)


class KavramCodeEditor(QMainWindow):
    """Embeddable top-level IDE window. Instantiate as KavramCodeEditor(core_window_ref=self)."""
    def __init__(self, core_window_ref=None, project_path=None, parent=None):
        super().__init__(parent)
        self.core_window_ref = core_window_ref
        self.settings = QSettings("Kavram", "CodeEditor")
        self.project_root = os.path.abspath(project_path) if project_path else ""
        self._process = None
        self._current_run_file = None
        self.setWindowTitle(APP_NAME)
        self.resize(1250, 800)
        self.setMinimumSize(800, 520)
        self.setStyleSheet(DARK_STYLE)
        self._build_ui()
        self._build_actions()
        if self.project_root:
            self.open_project(self.project_root)
        else:
            last_project = self.settings.value("last_project", "", type=str)
            if last_project and os.path.isdir(last_project):
                self.open_project(last_project)
        last_file = self.settings.value("last_file", "", type=str)
        if last_file and os.path.isfile(last_file):
            self.open_file(last_file)

    def _build_ui(self):
        central = QWidget(self)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self._update_status)
        root.addWidget(self.tabs)
        self.setCentralWidget(central)

        self.file_model = QFileSystemModel(self)
        self.file_model.setRootPath("")
        self.file_tree = QTreeView()
        self.file_tree.setModel(self.file_model)
        for col in (1, 2, 3):
            self.file_tree.hideColumn(col)
        self.file_tree.doubleClicked.connect(self._tree_open)
        self.project_dock = QDockWidget("PROJECT", self)
        self.project_dock.setObjectName("projectDock")
        self.project_dock.setWidget(self.file_tree)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.project_dock)

        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setFont(QFont("Monospace", 10))
        self.output_dock = QDockWidget("OUTPUT / TERMINAL", self)
        self.output_dock.setObjectName("outputDock")
        self.output_dock.setWidget(self.output)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.output_dock)
        self.output_dock.hide()

        self.search_bar = QWidget()
        search_layout = QHBoxLayout(self.search_bar)
        search_layout.setContentsMargins(8, 5, 8, 5)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Find in current file…")
        self.search_edit.returnPressed.connect(self.find_next)
        next_btn = QPushButton("Next")
        next_btn.clicked.connect(self.find_next)
        prev_btn = QPushButton("Previous")
        prev_btn.clicked.connect(self.find_previous)
        close_btn = QPushButton("×")
        close_btn.setMaximumWidth(35)
        close_btn.clicked.connect(self.search_bar.hide)
        search_layout.addWidget(self.search_edit, 1)
        search_layout.addWidget(prev_btn)
        search_layout.addWidget(next_btn)
        search_layout.addWidget(close_btn)
        root.addWidget(self.search_bar)
        self.search_bar.hide()

        self.setStatusBar(QStatusBar())
        self.status_file = QLabel("Ready")
        self.status_cursor = QLabel("Ln 1, Col 1")
        self.statusBar().addWidget(self.status_file, 1)
        self.statusBar().addPermanentWidget(self.status_cursor)

        self.toolbar = QToolBar("Main")
        self.toolbar.setMovable(False)
        self.addToolBar(self.toolbar)

    def _action(self, text, shortcut, callback, toolbar=True):
        action = QAction(text, self)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        action.triggered.connect(callback)
        self.addAction(action)
        if toolbar:
            self.toolbar.addAction(action)
        return action

    def _build_actions(self):
        file_menu = self.menuBar().addMenu("File")
        edit_menu = self.menuBar().addMenu("Edit")
        view_menu = self.menuBar().addMenu("View")
        run_menu = self.menuBar().addMenu("Run")
        project_menu = self.menuBar().addMenu("Project")
        self._action("New", "Ctrl+N", self.new_file)
        self._action("Open File…", "Ctrl+O", self.choose_file)
        self._action("Save", "Ctrl+S", self.save_file)
        self._action("Save As…", "Ctrl+Shift+S", self.save_as)
        self._action("Open Project…", "Ctrl+Shift+O", self.choose_project)
        self._action("Find", "Ctrl+F", self.show_search, False)
        self._action("Find Next", "F3", self.find_next, False)
        self._action("Run Current File", "F5", self.run_current_file)
        self._action("Stop Process", "Shift+F5", self.stop_process)
        self._action("Toggle Project", "Ctrl+B", lambda: self.project_dock.setVisible(not self.project_dock.isVisible()), False)
        self._action("Toggle Output", "Ctrl+J", lambda: self.output_dock.setVisible(not self.output_dock.isVisible()), False)
        for action in list(self.actions()):
            text = action.text()
            if text in ("New", "Open File…", "Save", "Save As…"):
                file_menu.addAction(action)
            elif text in ("Find", "Find Next"):
                edit_menu.addAction(action)
            elif text in ("Toggle Project", "Toggle Output"):
                view_menu.addAction(action)
            elif text in ("Run Current File", "Stop Process"):
                run_menu.addAction(action)
            elif text == "Open Project…":
                project_menu.addAction(action)

    def current_editor(self):
        widget = self.tabs.currentWidget()
        return widget if isinstance(widget, CodePane) else None

    def new_file(self):
        editor = CodePane()
        editor.setPlainText("")
        editor.mark_saved()
        self._add_tab(editor, "untitled")

    def _add_tab(self, editor, title):
        index = self.tabs.addTab(editor, title)
        self.tabs.setCurrentIndex(index)
        editor.cursorPositionChanged.connect(self._update_status)
        editor.textChanged.connect(self._update_status)
        self._update_status()

    def open_file(self, path):
        path = os.path.abspath(os.path.expanduser(path))
        for i in range(self.tabs.count()):
            editor = self.tabs.widget(i)
            if isinstance(editor, CodePane) and editor.path and os.path.abspath(editor.path) == path:
                self.tabs.setCurrentIndex(i)
                return True
        try:
            with open(path, "r", encoding="utf-8", errors="replace", newline="") as handle:
                content = handle.read()
        except OSError as exc:
            QMessageBox.critical(self, "Open failed", f"Could not open file:\n{path}\n\n{exc}")
            return False
        editor = CodePane(path)
        editor.setPlainText(content)
        editor.set_path(path)
        editor.mark_saved()
        self._add_tab(editor, os.path.basename(path))
        self.settings.setValue("last_file", path)
        self._update_status()
        return True

    def choose_file(self):
        start = self.project_root or str(Path.home())
        path, _ = QFileDialog.getOpenFileName(self, "Open source file", start, "Source files (*.py *.pyw *.c *.h *.cc *.cpp *.cxx *.hpp *.lua *.json *.sh *.txt *.md);;All files (*)")
        if path:
            self.open_file(path)

    def _save_editor(self, editor, save_as=False):
        if editor is None:
            return False
        path = editor.path
        if save_as or not path:
            path, _ = QFileDialog.getSaveFileName(self, "Save source file", path or self.project_root or str(Path.home()), "All files (*)")
            if not path:
                return False
            editor.set_path(path)
        try:
            parent = os.path.dirname(os.path.abspath(path))
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="") as handle:
                handle.write(editor.toPlainText())
        except OSError as exc:
            QMessageBox.critical(self, "Save failed", f"Could not save file:\n{path}\n\n{exc}")
            return False
        editor.mark_saved()
        index = self.tabs.indexOf(editor)
        if index >= 0:
            self.tabs.setTabText(index, os.path.basename(path))
        self.settings.setValue("last_file", path)
        self._update_status()
        return True

    def save_file(self):
        return self._save_editor(self.current_editor())

    def save_as(self):
        return self._save_editor(self.current_editor(), True)

    def close_tab(self, index):
        editor = self.tabs.widget(index)
        if isinstance(editor, CodePane) and editor.is_dirty():
            answer = QMessageBox.question(self, "Unsaved changes", f"Save changes to {editor.path or 'untitled'}?", QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Save)
            if answer == QMessageBox.Cancel:
                return
            if answer == QMessageBox.Save and not self._save_editor(editor):
                return
        self.tabs.removeTab(index)
        editor.deleteLater()
        self._update_status()

    def closeEvent(self, event):
        for index in reversed(range(self.tabs.count())):
            editor = self.tabs.widget(index)
            if isinstance(editor, CodePane) and editor.is_dirty():
                self.tabs.setCurrentIndex(index)
                answer = QMessageBox.question(self, "Unsaved changes", f"Save changes to {editor.path or 'untitled'}?", QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Save)
                if answer == QMessageBox.Cancel or (answer == QMessageBox.Save and not self._save_editor(editor)):
                    event.ignore()
                    return
        self.settings.setValue("last_project", self.project_root)
        event.accept()

    def choose_project(self):
        folder = QFileDialog.getExistingDirectory(self, "Open project folder", self.project_root or str(Path.home()))
        if folder:
            self.open_project(folder)

    def open_project(self, folder):
        folder = os.path.abspath(os.path.expanduser(folder))
        if not os.path.isdir(folder):
            QMessageBox.warning(self, "Project", "The selected project folder does not exist.")
            return
        self.project_root = folder
        self.file_model.setRootPath(folder)
        self.file_tree.setRootIndex(self.file_model.index(folder))
        self.project_dock.setWindowTitle("PROJECT — " + os.path.basename(folder.rstrip(os.sep)))
        self.settings.setValue("last_project", folder)
        self.status_file.setText(folder)

    def _tree_open(self, index):
        path = self.file_model.filePath(index)
        if os.path.isfile(path):
            self.open_file(path)

    def refresh_tab_titles(self):
        for i in range(self.tabs.count()):
            editor = self.tabs.widget(i)
            if isinstance(editor, CodePane):
                name = os.path.basename(editor.path) if editor.path else "untitled"
                self.tabs.setTabText(i, ("● " if editor.is_dirty() else "") + name)

    def show_search(self):
        self.search_bar.show()
        self.search_edit.setFocus()
        self.search_edit.selectAll()

    def find_next(self):
        editor = self.current_editor()
        term = self.search_edit.text()
        if editor and term and not editor.find(term):
            cursor = editor.textCursor()
            cursor.movePosition(QTextCursor.Start)
            editor.setTextCursor(cursor)
            if not editor.find(term):
                self.statusBar().showMessage("Text not found", 2500)

    def find_previous(self):
        editor = self.current_editor()
        term = self.search_edit.text()
        if editor and term and not editor.find(term, QTextDocumentFindBackward):
            cursor = editor.textCursor()
            cursor.movePosition(QTextCursor.End)
            editor.setTextCursor(cursor)
            editor.find(term, QTextDocumentFindBackward)

    def _update_status(self, *_):
        editor = self.current_editor()
        if not editor:
            self.status_cursor.setText("Ln 1, Col 1")
            return
        cursor = editor.textCursor()
        self.status_cursor.setText(f"Ln {cursor.blockNumber() + 1}, Col {cursor.positionInBlock() + 1}")
        self.status_file.setText(editor.path or "Untitled file")
        self.refresh_tab_titles()

    def _append_output(self, text):
        if text:
            self.output.moveCursor(QTextCursor.End)
            self.output.insertPlainText(text)
            self.output.ensureCursorVisible()

    def run_current_file(self):
        editor = self.current_editor()
        if not editor:
            QMessageBox.information(self, "Run", "Open a source file first.")
            return
        if editor.is_dirty() and not self.save_file():
            return
        path = editor.path
        if not path:
            return
        ext = Path(path).suffix.lower()
        commands = []
        if ext in (".py", ".pyw"):
            commands = [sys.executable, "-u", path]
        elif ext in (".c", ".cc", ".cpp", ".cxx"):
            compiler = shutil.which("g++") or shutil.which("clang++")
            if not compiler:
                QMessageBox.warning(self, "Compiler not found", "Install g++ or clang++ to build C/C++ files.")
                return
            output_path = os.path.join(os.path.dirname(path), Path(path).stem + (".exe" if os.name == "nt" else ".out"))
            self.output.clear()
            self.output_dock.show()
            self._start_process([compiler, path, "-std=c++17", "-O0", "-g", "-o", output_path], os.path.dirname(path), run_after_compile=output_path)
            return
        elif ext == ".lua":
            lua = shutil.which("lua") or shutil.which("lua5.4") or shutil.which("lua5.3")
            if not lua:
                QMessageBox.warning(self, "Lua not found", "Install Lua and ensure the `lua` command is available.")
                return
            commands = [lua, path]
        elif ext == ".sh":
            commands = ["bash", path]
        else:
            QMessageBox.information(self, "Run", "Run is supported for Python, C/C++, Lua and shell scripts.")
            return
        self.output.clear()
        self.output_dock.show()
        self._start_process(commands, os.path.dirname(path))

    def _start_process(self, command, cwd, run_after_compile=None):
        if self._process and self._process.state() != QProcess.NotRunning:
            QMessageBox.warning(self, "Process running", "Stop the current process before starting another.")
            return
        self._current_run_file = run_after_compile
        proc = QProcess(self)
        proc.setWorkingDirectory(cwd or os.getcwd())
        proc.setProcessChannelMode(QProcess.MergedChannels)
        proc.readyReadStandardOutput.connect(lambda p=proc: self._append_output(bytes(p.readAllStandardOutput()).decode("utf-8", "replace")))
        proc.finished.connect(lambda code, status, p=proc: self._process_finished(p, code, status))
        proc.errorOccurred.connect(lambda err, p=proc: self._append_output(f"\n[Process error: {p.errorString()}]\n"))
        self._process = proc
        self._append_output("$ " + " ".join(shlex.quote(str(part)) for part in command) + "\n\n")
        proc.start(command[0], command[1:])
        if not proc.waitForStarted(1500):
            self._append_output("Could not start process: " + proc.errorString() + "\n")

    def _process_finished(self, proc, code, status):
        self._append_output(f"\n[Process exited with code {code}]\n")
        run_after = self._current_run_file
        self._current_run_file = None
        if proc is self._process:
            self._process = None
        proc.deleteLater()
        if run_after and code == 0 and os.path.isfile(run_after):
            self._start_process([run_after], os.path.dirname(run_after))

    def stop_process(self):
        if self._process and self._process.state() != QProcess.NotRunning:
            self._process.terminate()
            if not self._process.waitForFinished(1200):
                self._process.kill()
            self._append_output("\n[Process stopped by user]\n")


# QTextDocument.FindBackward as a module-level constant, to keep PyQt5 versions happy.
try:
    from PyQt5.QtGui import QTextDocument
    QTextDocumentFindBackward = QTextDocument.FindBackward
except Exception:
    QTextDocumentFindBackward = QTextCursor.MoveOperation(1)


def open_code_editor(core_window_ref=None, project_path=None):
    """Factory hook for Kavram.py. Keep one IDE window per CoreWindow instance."""
    if core_window_ref is not None:
        existing = getattr(core_window_ref, "code_editor_instance", None)
        if existing is not None:
            try:
                existing.showNormal()
                existing.raise_()
                existing.activateWindow()
                return existing
            except RuntimeError:
                core_window_ref.code_editor_instance = None
        window = KavramCodeEditor(core_window_ref=core_window_ref, project_path=project_path)
        core_window_ref.code_editor_instance = window
        window.destroyed.connect(lambda *_: setattr(core_window_ref, "code_editor_instance", None)
                                 if getattr(core_window_ref, "code_editor_instance", None) is window else None)
    else:
        window = KavramCodeEditor(project_path=project_path)
    window.show()
    return window


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = open_code_editor()
    sys.exit(app.exec_())
