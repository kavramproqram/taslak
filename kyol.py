#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""KAVRAM v3 – Kısayollar & Numpad (kyol.py)"""
from PyQt5.QtCore import Qt

# Numpad eylem haritası.
# Num0  → Sphere menüsü (Ctrl+Q ile aynı işlev)
# Num6  → Varsayılan düzen
# Num7/8/9 → döndürme
# Num. → tam ekran pencere
NUMPAD_MAP = {
    "Num1": ("toggle_panel", 1),
    "Num2": ("toggle_panel", 2),
    "Num3": ("toggle_panel", 3),
    "Num4": ("toggle_panel", 4),
    "Num5": ("toggle_last",),
    "Num6": ("reset_to_default_layout",),
    "Num7": ("rotate_left_panels",),
    "Num8": ("rotate_right_panels",),
    "Num9": ("rotate_all_panels",),
    "Num0": ("open_sphere_menu_at_cursor",),
    "Num.": ("toggle_window_fullscreen",),
    "Num+": ("toggle_panel", 1),
    "Num-": ("toggle_panel", 2),
    "Num*": ("toggle_panel", 3),
    "Num/": ("toggle_panel", 4),
}


def dispatch_numpad(main_window, name):
    entry = NUMPAD_MAP.get(name)
    if not entry:
        return False
    fn = getattr(main_window, entry[0], None)
    if fn is None:
        return False
    try:
        fn(*entry[1:])
        return True
    except Exception:
        return False


def handle_event(main_window, event):
    mods = event.modifiers(); key = event.key()

    if key == Qt.Key_F11:
        main_window.toggle_window_fullscreen(); return True

    if (mods & Qt.ControlModifier) and not (mods & Qt.AltModifier):
        if key == Qt.Key_Q:
            opener = getattr(main_window, "open_sphere_menu_at_cursor", None)
            if callable(opener):
                opener()
                return True
            return False

        if key == Qt.Key_1: main_window.toggle_panel(1); return True
        if key == Qt.Key_2: main_window.toggle_panel(2); return True
        if key == Qt.Key_3: main_window.toggle_panel(3); return True
        if key == Qt.Key_4: main_window.toggle_panel(4); return True
        if key == Qt.Key_R:
            if mods & Qt.ShiftModifier:
                main_window.reset_all()
            else:
                main_window.reset_to_default_layout()
            return True
        if key == Qt.Key_Home: main_window.toggle_panel(1); return True
        if key == Qt.Key_End:  main_window.toggle_panel(4); return True

    if (mods & Qt.AltModifier) and not (mods & Qt.ControlModifier):
        if key == Qt.Key_Left:  main_window.rotate_left_panels(); return True
        if key == Qt.Key_Right: main_window.rotate_right_panels(); return True
        if key == Qt.Key_Up:    main_window.rotate_all_panels(); return True

    if mods & Qt.KeypadModifier:
        mapping = {
            Qt.Key_0: "Num0", Qt.Key_1: "Num1", Qt.Key_2: "Num2",
            Qt.Key_3: "Num3", Qt.Key_4: "Num4", Qt.Key_5: "Num5",
            Qt.Key_6: "Num6", Qt.Key_7: "Num7", Qt.Key_8: "Num8",
            Qt.Key_9: "Num9",
            Qt.Key_Period: "Num.", Qt.Key_Plus: "Num+",
            Qt.Key_Minus: "Num-", Qt.Key_Asterisk: "Num*", Qt.Key_Slash: "Num/",
            Qt.Key_End: "Num1", Qt.Key_Down: "Num2", Qt.Key_PageDown: "Num3",
            Qt.Key_Left: "Num4", Qt.Key_Clear: "Num5", Qt.Key_Right: "Num6",
            Qt.Key_Home: "Num7", Qt.Key_Up: "Num8", Qt.Key_PageUp: "Num9",
            Qt.Key_Insert: "Num0", Qt.Key_Delete: "Num.",
        }
        name = mapping.get(key)
        if name:
            return main_window._dispatch_numpad(name)

    if (mods & Qt.ControlModifier) and (mods & Qt.AltModifier):
        mapping_off = {
            Qt.Key_Home: "Num7", Qt.Key_Up: "Num8", Qt.Key_PageUp: "Num9",
            Qt.Key_Left: "Num4", Qt.Key_Clear: "Num5", Qt.Key_Right: "Num6",
            Qt.Key_End: "Num1", Qt.Key_Down: "Num2", Qt.Key_PageDown: "Num3",
            Qt.Key_Insert: "Num0", Qt.Key_Delete: "Num.",
            Qt.Key_Plus: "Num+", Qt.Key_Minus: "Num-",
            Qt.Key_Asterisk: "Num*", Qt.Key_Slash: "Num/",
        }
        name = mapping_off.get(key)
        if name:
            return main_window._dispatch_numpad(name)

    return False
