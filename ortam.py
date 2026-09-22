#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KAVRAM v3 – Sphere Yöneticisi (ortam.py)
- Sphere kavramı: kullanıcı tanımlı çalışma alanları.
- Sıralama (order) tutulur: seçilen sphere listenin başına taşınır.
- Varsayılan sphere (Ana Sphere) her zaman listenin en başında ve silinemez.
"""
import os, json, shutil

DEFAULT_ENV_NAME = "Ana Sphere"
MAX_ENVIRONMENTS = 33
DEFAULT_LAYOUT = {"left_top": 1, "left_bottom": 2, "right_top": 3, "right_bottom": 4}
DEFAULT_PANELS = {"1": None, "2": None, "3": None, "4": None}


class EnvironmentStore:
    """Geriye dönük uyumluluk için 'EnvironmentStore' adı korundu;
    kullanıcı arayüzünde 'Sphere' olarak anılır."""

    def __init__(self, base_dir):
        self.base_dir = base_dir
        self.config_path = os.path.join(base_dir, "environments.json")
        self.environments = {}
        self.current = DEFAULT_ENV_NAME
        self._order = []
        self._load()
        self._ensure_default()
        self._sync_order()

    # ------------------------------------------------------------------
    def _load(self):
        if os.path.isfile(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    d = json.load(f)
                self.environments = d.get("environments", {}) or {}
                self.current = d.get("current", DEFAULT_ENV_NAME)
                self._order = list(d.get("order", []) or [])
            except Exception:
                self.environments = {}
                self._order = []

    def _sync_order(self):
        valid = set(self.environments.keys())
        cleaned = []
        for n in self._order:
            if n in valid and not self.environments[n].get("is_default"):
                if n not in cleaned:
                    cleaned.append(n)
        for n, cfg in self.environments.items():
            if not cfg.get("is_default") and n not in cleaned:
                cleaned.append(n)
        self._order = cleaned

    def save(self):
        try:
            self._sync_order()
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump({
                    "current": self.current,
                    "order": self._order,
                    "environments": self.environments,
                }, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def folder_for(self, name):
        return os.path.join(self.base_dir, name)

    def ensure_folder(self, name):
        try:
            os.makedirs(self.folder_for(name), exist_ok=True)
        except Exception:
            pass
        return self.folder_for(name)

    # ------------------------------------------------------------------
    def _ensure_default(self):
        changed = False
        has_default = any(v.get("is_default") for v in self.environments.values())
        if not has_default or not self.environments:
            self.environments[DEFAULT_ENV_NAME] = {
                "is_default": True,
                "has_numper": True, "has_numpad": True,
                "numper_position": 4, "numpad_position": 4,
                "panels": dict(DEFAULT_PANELS),
                "layout": dict(DEFAULT_LAYOUT),
                "sizes_main": None, "sizes_left": None, "sizes_right": None,
            }
            changed = True

        if self.current not in self.environments:
            for k, v in self.environments.items():
                if v.get("is_default"):
                    self.current = k
                    break
            else:
                self.current = next(iter(self.environments))
            changed = True

        for name in list(self.environments.keys()):
            if not os.path.isdir(self.folder_for(name)):
                self.ensure_folder(name)
                changed = True
            cfg = self.environments[name]
            for key, default in (("has_numper", cfg.get("has_numpad", True)),
                                 ("numper_position", cfg.get("numpad_position", 4)),
                                 ("layout", dict(DEFAULT_LAYOUT)),
                                 ("panels", dict(DEFAULT_PANELS)),
                                 ("sizes_main", None),
                                 ("sizes_left", None),
                                 ("sizes_right", None)):
                if key not in cfg:
                    cfg[key] = default
                    changed = True
            if "has_numpad" not in cfg:
                cfg["has_numpad"] = cfg["has_numper"]; changed = True
            if "numpad_position" not in cfg:
                cfg["numpad_position"] = cfg["numper_position"]; changed = True

        if changed:
            self.save()

    # ------------------------------------------------------------------
    def names(self):
        result = []
        seen = set()
        for name, cfg in self.environments.items():
            if cfg.get("is_default"):
                result.append(name); seen.add(name)
                break
        for name in self._order:
            if name in self.environments and name not in seen:
                result.append(name); seen.add(name)
        for name in self.environments:
            if name not in seen:
                result.append(name); seen.add(name)
        return result

    def promote(self, name):
        if name not in self.environments:
            return
        if self.environments[name].get("is_default"):
            return
        self._order = [n for n in self._order if n != name]
        self._order.insert(0, name)
        self.save()

    def count(self):
        return len(self.environments)

    def exists(self, name):
        return name in self.environments

    def is_default(self, name):
        cfg = self.environments.get(name)
        return bool(cfg and cfg.get("is_default"))

    def get(self, name):
        return self.environments.get(name)

    def has_numper(self, name):
        cfg = self.environments.get(name) or {}
        return bool(cfg.get("has_numper", cfg.get("has_numpad", True)))

    def numper_position(self, name):
        cfg = self.environments.get(name) or {}
        pos = int(cfg.get("numper_position", cfg.get("numpad_position", 4)) or 4)
        return pos if pos in (1, 2, 3, 4) else 4

    def get_layout(self, name):
        return dict((self.environments.get(name) or {}).get("layout", DEFAULT_LAYOUT))

    def set_layout(self, name, layout):
        cfg = self.environments.get(name)
        if not cfg:
            return
        cfg["layout"] = {k: int(layout.get(k, DEFAULT_LAYOUT[k])) for k in DEFAULT_LAYOUT}
        self.save()

    def get_sizes(self, name):
        cfg = self.environments.get(name) or {}
        return {
            "main": cfg.get("sizes_main"),
            "left": cfg.get("sizes_left"),
            "right": cfg.get("sizes_right"),
        }

    def set_sizes(self, name, main=None, left=None, right=None):
        cfg = self.environments.get(name)
        if not cfg:
            return
        if main is not None and sum(main) > 0:
            cfg["sizes_main"] = [int(x) for x in main]
        if left is not None and sum(left) > 0:
            cfg["sizes_left"] = [int(x) for x in left]
        if right is not None and sum(right) > 0:
            cfg["sizes_right"] = [int(x) for x in right]
        self.save()

    def set_numper_position(self, name, position):
        cfg = self.environments.get(name)
        if not cfg:
            return
        pos = int(position)
        if pos not in (1, 2, 3, 4):
            pos = 4
        cfg["numper_position"] = pos
        cfg["numpad_position"] = pos
        self.save()

    # ------------------------------------------------------------------
    def add(self, name, has_numper):
        name = (name or "").strip()
        if not name:
            return False, "Boş isim girilemez."
        if name in self.environments:
            return False, "Bu isim zaten kullanılıyor."
        if self.count() >= MAX_ENVIRONMENTS:
            return False, f"En fazla {MAX_ENVIRONMENTS} sphere oluşturulabilir."
        if any(c in name for c in '\\/:*?"<>|'):
            return False, "İsimde geçersiz karakter var."
        self.environments[name] = {
            "is_default": False,
            "has_numper": bool(has_numper), "has_numpad": bool(has_numper),
            "numper_position": 4 if has_numper else 0,
            "numpad_position": 4 if has_numper else 0,
            "panels": dict(DEFAULT_PANELS),
            "layout": dict(DEFAULT_LAYOUT),
            "sizes_main": None, "sizes_left": None, "sizes_right": None,
        }
        self.ensure_folder(name)
        self._order.append(name)
        self.save()
        return True, ""

    def rename(self, old, new):
        new = (new or "").strip()
        if old not in self.environments:
            return False, "Sphere bulunamadı."
        if not new:
            return False, "Boş isim girilemez."
        if new == old:
            return False, "Aynı isim."
        if new in self.environments:
            return False, "Bu isim zaten kullanılıyor."
        if any(c in new for c in '\\/:*?"<>|'):
            return False, "İsimde geçersiz karakter var."
        old_folder = self.folder_for(old)
        new_folder = self.folder_for(new)
        try:
            if os.path.isdir(old_folder):
                if os.path.exists(new_folder):
                    return False, "Hedef klasör zaten var."
                os.rename(old_folder, new_folder)
            else:
                os.makedirs(new_folder, exist_ok=True)
        except Exception as e:
            return False, f"Klasör adı değiştirilemedi: {e}"
        new_envs = {}
        for k, v in self.environments.items():
            new_envs[new if k == old else k] = v
        self.environments = new_envs
        self._order = [new if n == old else n for n in self._order]
        if self.current == old:
            self.current = new
        self.save()
        return True, ""

    def delete(self, name):
        if name not in self.environments:
            return False, "Sphere bulunamadı."
        if self.environments[name].get("is_default"):
            return False, "Ana Sphere silinemez."
        del self.environments[name]
        self._order = [n for n in self._order if n != name]
        try:
            folder = self.folder_for(name)
            if os.path.isdir(folder):
                shutil.rmtree(folder)
        except Exception:
            pass
        if self.current == name:
            for k, v in self.environments.items():
                if v.get("is_default"):
                    self.current = k
                    break
            else:
                self.current = next(iter(self.environments))
        self.save()
        return True, ""

    def set_current(self, name):
        if name in self.environments:
            self.current = name
            self.save()
            return True
        return False

    def set_panel(self, env_name, slot, value):
        env = self.environments.get(env_name)
        if not env:
            return
        panels = env.setdefault("panels", {})
        panels[str(slot)] = value
        self.save()

    # ------------------------------------------------------------------
    def remove_panel_file(self, env_name, filename):
        if not filename:
            return
        try:
            path = os.path.join(self.folder_for(env_name), filename)
            if os.path.isfile(path):
                os.remove(path)
        except Exception:
            pass

    def delete_panel_record(self, env_name, slot):
        env = self.environments.get(env_name)
        if not env:
            return
        panels = env.setdefault("panels", {})
        panels[str(slot)] = None
        self.save()
