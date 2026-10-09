#!/usr/bin/env python3
"""Fast checks for the MKJ workspace overlay; does not require PyQt5 or a GUI session."""
import ast
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent
required = [ROOT / "kavram_mkj_workspace.py", ROOT / "mkj_pencere.py"]
missing = [str(path.name) for path in required if not path.is_file()]
if missing:
    raise SystemExit("Missing integration files: " + ", ".join(missing))
for file in required:
    ast.parse(file.read_text(encoding="utf-8"), filename=str(file))

source = (ROOT / "kavram_mkj_workspace.py").read_text(encoding="utf-8")
expected = ["Sphere", "Text", "Drawing", "Sound", "Ai", "Media", "Rec", "Copy", "Filter", "Convert"]
missing_editors = [name for name in expected if not re.search(rf'\("{name}",', source)]
if missing_editors:
    raise SystemExit("Missing built-in editor manifest entries: " + ", ".join(missing_editors))
for required_ui in ("ShortcutPoolPanel", "SystemManagementPanel", "TerminalPanel", "_build_docks", "_build_toolbar"):
    if required_ui not in source:
        raise SystemExit(f"Missing workspace component: {required_ui}")
if 'os.environ["QT_QPA_PLATFORM"] = "xcb"' in source or "os.environ['QT_QPA_PLATFORM'] = 'xcb'" in source:
    raise SystemExit("The launcher must not force xcb; let Qt choose X11/Wayland.")
for script in ("run_workspace.sh", "INSTALL_IN_KAVRAM.sh", "BUILD_FULL_BUNDLE.sh"):
    path = ROOT / script
    if not path.is_file():
        raise SystemExit("Missing shell script: " + script)
print("STATIC CHECK OK: Python syntax, 10 editor entries, workspace/dock/terminal components and scripts.")
print("NOT VERIFIED HERE: Native widget behaviour, editor-specific features, X11/Wayland smoke tests, camera/audio devices and C/C++ modules.")
