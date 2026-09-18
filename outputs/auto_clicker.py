# -*- coding: utf-8 -*-
"""自动点击器 —— 鼠标 / 键盘自动化工具

功能概览：
  1. 采集鼠标坐标或键盘按键，按列表顺序循环执行，每一项可独立设置间隔
  2. 间隔支持 秒 / 分 / 时（0.05 秒 ~ 2 小时），写法灵活：2h、30m、90s、1h30m
  3. 间隔随机化：可设随机倍率区间（默认 0.5x ~ 2.0x），例如设 0.1 秒实际在 0.05~0.2 秒之间
  4. 数据持久化：配置保存在程序同目录的 click_positions.json，重启、换机都不丢
  5. 多方案管理：新建 / 复制 / 重命名 / 删除，方案之间数据完全独立
  6. 全局热键启停（默认 F12，可自定义任意键）
  7. 按住右键：持续发送右键按下信号，再点一次松开
"""

import ctypes
import ctypes.wintypes
import json
import os
import queue
import random
import re
import shutil
import sys
import threading
import time


# ── 打包后 Tcl/Tk 运行库引导 ────────────────────────────────────────────────
# PyInstaller 打包成 exe 后，Tcl 只认「相对路径」或它自己算出来的路径，
# 因此这里把自带的 Tcl/Tk 运行库释放到固定目录，并切换到该目录。
# 必须在 import tkinter 之前执行。
def bootstrap_tcl_tk():
    if not getattr(sys, "frozen", False):
        return None
    bundle = getattr(sys, "_MEIPASS", None)
    if not bundle:
        return None
    os.environ.pop("TCL_LIBRARY", None)
    os.environ.pop("TK_LIBRARY", None)

    exe_dir = os.path.dirname(os.path.abspath(sys.executable))
    local_app = os.environ.get("LOCALAPPDATA")
    candidates = [exe_dir]
    if local_app:
        candidates.append(os.path.join(local_app, "AutoClicker"))
    candidates.append(bundle)

    for folder in candidates:
        runtime = folder if folder == bundle else os.path.join(folder, "runtime")
        marker = os.path.join(runtime, "tcl", "tcl8.6", "init.tcl")
        try:
            if not os.path.isfile(marker):
                copy_tree(os.path.join(bundle, "tcl"), os.path.join(runtime, "tcl"))
                copy_tree(os.path.join(bundle, "tk"), os.path.join(runtime, "tk"))
            if not os.path.isfile(marker):
                continue
            os.chdir(runtime)
            os.environ["TCL_LIBRARY"] = os.path.join("tcl", "tcl8.6")
            os.environ["TK_LIBRARY"] = os.path.join("tk", "tk8.6")
            return runtime
        except Exception:
            continue
    return None


def copy_tree(source, target):
    """把 source 目录的内容复制到 target（不依赖 shutil.copytree 的版本差异）。"""
    if not os.path.isdir(source):
        return
    for current, _dirs, files in os.walk(source):
        relative = os.path.relpath(current, source)
        destination = target if relative == "." else os.path.join(target, relative)
        os.makedirs(destination, exist_ok=True)
        for name in files:
            try:
                shutil.copy2(os.path.join(current, name), os.path.join(destination, name))
            except Exception:
                pass


TCL_RUNTIME = bootstrap_tcl_tk()

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

# ── 可选依赖：键盘钩子与按键模拟 ────────────────────────────────────────────
try:
    import keyboard
    HAS_KEYBOARD = True
except Exception:  # 缺少 keyboard 库时只保留鼠标功能
    keyboard = None
    HAS_KEYBOARD = False


# ── 常量 ────────────────────────────────────────────────────────────────────
APP_NAME = "自动点击器"
APP_VERSION = "v21"
CONFIG_NAME = "click_positions.json"

MIN_INTERVAL = 0.05       # 最小间隔（秒）
MAX_INTERVAL = 7200.0     # 最大间隔（秒），即 2 小时
DEFAULT_HOTKEY = "f12"
DEFAULT_JITTER_MIN = 0.5  # 随机倍率下限
DEFAULT_JITTER_MAX = 2.0  # 随机倍率上限

user32 = ctypes.windll.user32

MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010


# ── 高 DPI 适配：让采集到的坐标就是真实像素坐标，换电脑也不会偏移 ──────────
def enable_dpi_awareness():
    """开启进程 DPI 感知，避免缩放 125% / 150% 的电脑上坐标错位。"""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
        return
    except Exception:
        pass
    try:
        user32.SetProcessDPIAware()
    except Exception:
        pass


enable_dpi_awareness()


# ── 数据文件路径：优先放在程序（或 exe）同目录，保证换电脑时数据跟着走 ──────
def get_app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


APP_DIR = get_app_dir()


def choose_config_path():
    """优先用程序目录；若目录不可写（例如放在 Program Files），退回用户目录。"""
    candidates = [APP_DIR]
    appdata = os.environ.get("APPDATA")
    if appdata:
        candidates.append(os.path.join(appdata, "AutoClicker"))
    for folder in candidates:
        try:
            os.makedirs(folder, exist_ok=True)
            probe = os.path.join(folder, ".write_probe")
            with open(probe, "w", encoding="utf-8") as fh:
                fh.write("1")
            os.remove(probe)
            return os.path.join(folder, CONFIG_NAME)
        except Exception:
            continue
    return os.path.join(APP_DIR, CONFIG_NAME)


CONFIG_PATH = choose_config_path()


# ── 配置读写（原子写入 + 自动备份，防止意外断电写坏数据） ──────────────────
def save_config(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.flush()
        os.fsync(fh.fileno())
    if os.path.exists(path):
        try:
            shutil.copyfile(path, path + ".bak")
        except Exception:
            pass
    os.replace(tmp, path)


def load_config(path):
    for candidate in (path, path + ".bak"):
        if not os.path.exists(candidate):
            continue
        try:
            with open(candidate, "r", encoding="utf-8") as fh:
                return normalize_config(json.load(fh))
        except Exception:
            continue
    return normalize_config(None)


def normalize_item(raw):
    """把任意历史格式的位置项统一成 {type, name, x, y, key, interval}。"""
    if not isinstance(raw, dict):
        return None
    kind = str(raw.get("type", "") or "").lower()
    if kind in ("key", "keyboard", "keypress"):
        item_type = "key"
    elif kind in ("mouse", "click", "mouse_click", "leftclick", "left_click"):
        item_type = "mouse"
    else:
        # 没有类型字段的旧数据：有有效按键就当成按键项，否则当成点击
        item_type = "key" if normalize_key_name(raw.get("key")) else "mouse"
    item = {
        "type": item_type,
        "name": str(raw.get("name", "") or ""),
        "interval": 1.0,
    }
    try:
        interval = float(raw.get("interval", 1.0))
    except (TypeError, ValueError):
        interval = 1.0
    item["interval"] = max(MIN_INTERVAL, min(MAX_INTERVAL, interval))
    if item["type"] == "mouse":
        try:
            item["x"] = int(raw.get("x", 0))
            item["y"] = int(raw.get("y", 0))
        except (TypeError, ValueError):
            item["x"] = 0
            item["y"] = 0
    else:
        key_name = normalize_key_name(raw.get("key"))
        if not key_name:
            return None
        item["key"] = key_name
    if not item["name"]:
        item["name"] = "点击" if item["type"] == "mouse" else key_display(item["key"])
    return item


def normalize_profile(raw):
    raw = raw if isinstance(raw, dict) else {}
    profile = {
        "hotkey": normalize_key_name(raw.get("hotkey") or raw.get("hotkey_vk")) or DEFAULT_HOTKEY,
        "jitter_enabled": bool(raw.get("jitter_enabled", True)),
        "jitter_min": float(raw.get("jitter_min", DEFAULT_JITTER_MIN) or DEFAULT_JITTER_MIN),
        "jitter_max": float(raw.get("jitter_max", DEFAULT_JITTER_MAX) or DEFAULT_JITTER_MAX),
        "items": [],
    }
    entries = raw.get("items")
    if entries is None:
        entries = raw.get("positions")   # 更早的版本用的是 positions
    for entry in entries or []:
        item = normalize_item(entry)
        if item:
            profile["items"].append(item)
    return profile


def normalize_config(raw):
    """兼容旧版单方案数据与新版多方案数据。"""
    if isinstance(raw, dict) and isinstance(raw.get("profiles"), dict) and raw["profiles"]:
        profiles = {}
        for name, prof in raw["profiles"].items():
            profiles[str(name)] = normalize_profile(prof)
        current = raw.get("current_profile") or raw.get("active_profile")
        if current not in profiles:
            current = list(profiles.keys())[0]
        return {"version": 2, "current_profile": current, "profiles": profiles}
    # 旧版：整个文件就是一套配置
    legacy = raw if isinstance(raw, dict) else {}
    return {
        "version": 2,
        "current_profile": "默认方案",
        "profiles": {"默认方案": normalize_profile(legacy)},
    }


# ── 间隔解析与格式化 ────────────────────────────────────────────────────────
_INTERVAL_UNITS = (
    (re.compile(r"(\d+(?:\.\d+)?)\s*(?:小时|时|h|hours?|hr)"), 3600.0),
    (re.compile(r"(\d+(?:\.\d+)?)\s*(?:分钟|分|m|mins?|minutes?)"), 60.0),
    (re.compile(r"(\d+(?:\.\d+)?)\s*(?:秒|s|secs?|seconds?)"), 1.0),
)


def parse_interval(text):
    """把 2h / 30m / 90s / 1h30m / 1.5h / 7200 解析为秒数。"""
    if text is None:
        raise ValueError("间隔不能为空")
    raw = str(text).strip().lower().replace(" ", "")
    if not raw:
        raise ValueError("间隔不能为空")
    if re.fullmatch(r"\d+(?:\.\d+)?", raw):
        return float(raw)
    total = 0.0
    matched = False
    for pattern, scale in _INTERVAL_UNITS:
        for match in pattern.findall(raw):
            total += float(match) * scale
            matched = True
        raw = pattern.sub("", raw)
    if not matched or raw.strip():
        raise ValueError("格式无法识别，示例：2h、30m、90s、1h30m")
    return total


def format_seconds(seconds):
    """秒数转易读文本。"""
    if seconds >= 3600:
        hours = int(seconds // 3600)
        minutes = int(round((seconds - hours * 3600) / 60.0))
        if minutes >= 60:
            hours += 1
            minutes = 0
        return f"{hours}小时{minutes}分" if minutes else f"{hours}小时"
    if seconds >= 60:
        minutes = int(seconds // 60)
        rest = seconds - minutes * 60
        return f"{minutes}分{rest:.1f}秒" if rest else f"{minutes}分"
    if seconds >= 1:
        return f"{seconds:.2f}秒".replace(".00秒", "秒")
    return f"{seconds * 1000:.0f}毫秒"


def format_interval(seconds):
    return format_seconds(float(seconds))


# 旧数据里热键/按键可能写成箭头符号、中文或 VK 码，统一转成 keyboard 库的键名
_KEY_ALIASES = {
    "↓": "down", "down": "down", "down arrow": "down",
    "↑": "up", "up": "up", "up arrow": "up",
    "←": "left", "left": "left", "left arrow": "left",
    "→": "right", "right": "right", "right arrow": "right",
    "空格": "space", "space": "space",
    "回车": "enter", "enter": "enter", "return": "enter",
    "esc": "esc", "escape": "esc",
    "退格": "backspace", "backspace": "backspace",
    "制表": "tab", "tab": "tab",
    "shift": "shift", "ctrl": "ctrl", "control": "ctrl", "alt": "alt",
    "大写锁定": "caps lock", "caps lock": "caps lock",
}

_VK_NAMES = {
    0x08: "backspace", 0x09: "tab", 0x0D: "enter", 0x10: "shift", 0x11: "ctrl",
    0x12: "alt", 0x14: "caps lock", 0x1B: "esc", 0x20: "space", 0x21: "page up",
    0x22: "page down", 0x23: "end", 0x24: "home", 0x25: "left", 0x26: "up",
    0x27: "right", 0x28: "down", 0x2C: "print screen", 0x2D: "insert", 0x2E: "delete",
}


def vk_to_name(vk):
    """把旧版存的 VK 码转成键名。"""
    try:
        vk = int(vk)
    except (TypeError, ValueError):
        return None
    if 0x30 <= vk <= 0x39 or 0x41 <= vk <= 0x5A:   # 0-9 / A-Z
        return chr(vk).lower()
    if 0x60 <= vk <= 0x69:                          # 小键盘数字
        return "num %d" % (vk - 0x60)
    if 0x70 <= vk <= 0x87:                          # F1-F24
        return "f%d" % (vk - 0x6F)
    return _VK_NAMES.get(vk)


def normalize_key_name(value):
    """兼容 键名 / 箭头符号 / 中文名 / VK 码，返回 keyboard 库可用的键名。"""
    if isinstance(value, int):
        return vk_to_name(value)
    text = str(value or "").strip()
    if not text:
        return None
    lowered = text.lower()
    if lowered in _KEY_ALIASES:
        return _KEY_ALIASES[lowered]
    if text in _KEY_ALIASES:
        return _KEY_ALIASES[text]
    if lowered.isdigit():
        return vk_to_name(int(lowered))
    return lowered


_KEY_DISPLAY = {
    "space": "空格",
    "enter": "回车",
    "esc": "ESC",
    "tab": "Tab",
    "backspace": "退格",
    "caps lock": "大写锁定",
    "up": "↑",
    "down": "↓",
    "left": "←",
    "right": "→",
    "shift": "Shift",
    "ctrl": "Ctrl",
    "alt": "Alt",
    "left shift": "左Shift",
    "right shift": "右Shift",
    "left ctrl": "左Ctrl",
    "right ctrl": "右Ctrl",
    "left alt": "左Alt",
    "right alt": "右Alt",
}


def key_display(name):
    if not name:
        return ""
    lower = str(name).lower()
    if lower in _KEY_DISPLAY:
        return _KEY_DISPLAY[lower]
    return lower.upper() if len(lower) == 1 else lower


# ── Win32 输入模拟 ──────────────────────────────────────────────────────────
def get_cursor_pos():
    point = ctypes.wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(point))
    return point.x, point.y


def mouse_click_left(x, y):
    """移动光标并单击左键。"""
    user32.SetCursorPos(int(x), int(y))
    time.sleep(0.02)
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(random.uniform(0.03, 0.07))
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)


def mouse_right_down():
    user32.mouse_event(MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0)


def mouse_right_up():
    user32.mouse_event(MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)


def key_tap(name):
    """按下并松开一个键，返回是否成功。"""
    if not HAS_KEYBOARD or not name:
        return False
    try:
        keyboard.press(name)
        time.sleep(random.uniform(0.03, 0.06))
        keyboard.release(name)
        return True
    except Exception:
        return False


def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_as_admin():
    """以管理员身份重启自己（用于需要注入输入的场景）。"""
    try:
        if getattr(sys, "frozen", False):
            exe = sys.executable
            params = ""
        else:
            exe = sys.executable
            params = '"%s"' % os.path.abspath(__file__)
        ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params, APP_DIR, 1)
        return True
    except Exception:
        return False


class AutoClicker:
    """主窗口与执行引擎。"""

    def __init__(self):
        self.cfg = load_config(CONFIG_PATH)
        self.profiles = self.cfg["profiles"]
        self.current_profile = self.cfg["current_profile"]

        self.items = []
        self.hotkey = DEFAULT_HOTKEY
        self.hotkey_handle = None
        self.default_interval = 1.0
        self.jitter_on = True
        self.jitter_min = DEFAULT_JITTER_MIN
        self.jitter_max = DEFAULT_JITTER_MAX
        self._save_job = None
        self._key_target = None

        self.running = False
        self.click_thread = None
        self.right_held = False
        self.right_thread = None
        self.capturing = False
        self.ui_queue = queue.Queue()

        self.root = tk.Tk()
        self.root.title(f"{APP_NAME} {APP_VERSION}")
        self.root.minsize(640, 600)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._center_window(680, 660)

        self._build_ui()
        self._load_profile(self.current_profile)
        self._register_hotkey()
        self._save_now()
        self.root.after(60, self._pump_queue)

    def _center_window(self, width, height):
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        left = max(0, (screen_width - width) // 2)
        top = max(0, (screen_height - height) // 3)
        self.root.geometry(f"{width}x{height}+{left}+{top}")

    # ── 界面 ────────────────────────────────────────────────────────────────
    def _build_ui(self):
        pad = {"padx": 6, "pady": 3}

        # 方案栏
        profile_bar = ttk.LabelFrame(self.root, text="方案")
        profile_bar.pack(fill=tk.X, padx=8, pady=(8, 4))
        self.profile_var = tk.StringVar(value=self.current_profile)
        self.profile_box = ttk.Combobox(profile_bar, textvariable=self.profile_var,
                                        state="readonly", width=18)
        self.profile_box.pack(side=tk.LEFT, padx=(8, 6), pady=6)
        self.profile_box.bind("<<ComboboxSelected>>", self._on_profile_change)
        for text, command in (("新建", self._new_profile), ("复制", self._copy_profile),
                              ("重命名", self._rename_profile), ("删除", self._delete_profile),
                              ("导入", self._import_profiles), ("导出", self._export_profiles)):
            ttk.Button(profile_bar, text=text, width=6, command=command).pack(side=tk.LEFT, padx=3)
        ttk.Label(profile_bar, text="方案数据互相独立").pack(side=tk.LEFT, padx=8)

        # 热键与随机间隔
        setting_bar = ttk.LabelFrame(self.root, text="热键与间隔")
        setting_bar.pack(fill=tk.X, padx=8, pady=4)

        row1 = ttk.Frame(setting_bar)
        row1.pack(fill=tk.X, padx=8, pady=(6, 2))
        ttk.Label(row1, text="启停热键").pack(side=tk.LEFT)
        self.hotkey_var = tk.StringVar(value=key_display(self.hotkey))
        ttk.Label(row1, textvariable=self.hotkey_var, width=12, anchor=tk.CENTER,
                  relief=tk.SUNKEN).pack(side=tk.LEFT, padx=6)
        ttk.Button(row1, text="设置热键", width=10, command=self._start_set_hotkey).pack(side=tk.LEFT)
        ttk.Label(row1, text="默认间隔").pack(side=tk.LEFT, padx=(16, 4))
        self.default_interval_var = tk.StringVar(value="1")
        ttk.Entry(row1, textvariable=self.default_interval_var, width=8).pack(side=tk.LEFT)
        ttk.Label(row1, text="秒（采集时使用）").pack(side=tk.LEFT, padx=4)

        row2 = ttk.Frame(setting_bar)
        row2.pack(fill=tk.X, padx=8, pady=(2, 6))
        self.jitter_on_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(row2, text="间隔随机化", variable=self.jitter_on_var,
                        command=self._on_change).pack(side=tk.LEFT)
        ttk.Label(row2, text="实际间隔 = 设定值 ×").pack(side=tk.LEFT, padx=(10, 2))
        self.jitter_min_var = tk.StringVar(value=str(DEFAULT_JITTER_MIN))
        ttk.Entry(row2, textvariable=self.jitter_min_var, width=6).pack(side=tk.LEFT)
        ttk.Label(row2, text="~").pack(side=tk.LEFT, padx=2)
        self.jitter_max_var = tk.StringVar(value=str(DEFAULT_JITTER_MAX))
        ttk.Entry(row2, textvariable=self.jitter_max_var, width=6).pack(side=tk.LEFT)
        ttk.Label(row2, text="倍（例：设 0.1 秒 → 实际 0.05~0.2 秒）").pack(side=tk.LEFT, padx=6)
        for var in (self.jitter_min_var, self.jitter_max_var):
            var.trace_add("write", lambda *_: self._on_change())

        # 位置列表
        list_bar = ttk.LabelFrame(self.root, text="执行列表")
        list_bar.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
        columns = ("index", "type", "name", "detail", "interval")
        self.tree = ttk.Treeview(list_bar, columns=columns, show="headings", height=11)
        for key, title, width in (("index", "序号", 50), ("type", "类型", 70),
                                  ("name", "名称", 130), ("detail", "内容", 200),
                                  ("interval", "间隔", 120)):
            self.tree.heading(key, text=title)
            self.tree.column(key, width=width, anchor=tk.CENTER)
        scroll = ttk.Scrollbar(list_bar, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(8, 0), pady=6)
        scroll.pack(side=tk.RIGHT, fill=tk.Y, pady=6)
        self.tree.bind("<Double-1>", lambda event: self._edit_selected())
        self.tree.bind("<Button-3>", self._show_context_menu)
        self.context_menu = tk.Menu(self.tree, tearoff=0)
        self.context_menu.add_command(label="编辑", command=self._edit_selected)
        self.context_menu.add_command(label="删除", command=self._delete_selected)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="上移", command=self._move_up)
        self.context_menu.add_command(label="下移", command=self._move_down)

        # 列表操作按钮
        action_bar = ttk.Frame(self.root)
        action_bar.pack(fill=tk.X, padx=8, pady=2)
        actions = (
            ("采集点击", self._capture_position),
            ("采集按键", self._capture_key),
            ("手动添加", self._add_item_dialog),
            ("编辑", self._edit_selected),
            ("删除", self._delete_selected),
            ("上移", self._move_up),
            ("下移", self._move_down),
        )
        for text, command in actions:
            ttk.Button(action_bar, text=text, width=9, command=command).pack(side=tk.LEFT, padx=3)

        # 执行控制
        control_bar = ttk.Frame(self.root)
        control_bar.pack(fill=tk.X, padx=8, pady=(6, 2))
        self.btn_start = ttk.Button(control_bar, text="▶ 开始", width=12, command=self._start_clicking)
        self.btn_start.pack(side=tk.LEFT, padx=4)
        self.btn_stop = ttk.Button(control_bar, text="⏹ 停止", width=12,
                                   command=self._stop_clicking, state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT, padx=4)
        self.btn_right = ttk.Button(control_bar, text="按住右键", width=12, command=self._toggle_right_hold)
        self.btn_right.pack(side=tk.LEFT, padx=4)
        ttk.Button(control_bar, text="清空列表", width=12, command=self._clear_items).pack(side=tk.LEFT, padx=4)

        # 状态栏
        self.status_var = tk.StringVar(value="已停止")
        ttk.Label(self.root, textvariable=self.status_var, anchor=tk.W,
                  relief=tk.SUNKEN).pack(fill=tk.X, padx=8, pady=(6, 2))

        # 底部提示
        foot = ttk.Frame(self.root)
        foot.pack(fill=tk.X, padx=8, pady=(0, 8))
        ttk.Label(foot, text="数据文件：" + CONFIG_PATH, foreground="#666").pack(side=tk.LEFT)
        if not is_admin():
            ttk.Button(foot, text="以管理员身份重启", command=self._restart_as_admin).pack(side=tk.RIGHT)
        if not HAS_KEYBOARD:
            ttk.Label(foot, text="未安装 keyboard 库，键盘功能不可用",
                      foreground="#c00").pack(side=tk.RIGHT, padx=8)

    # ── 方案管理 ────────────────────────────────────────────────────────────
    def _collect_profile(self):
        return {
            "hotkey": self.hotkey,
            "jitter_enabled": bool(self.jitter_on_var.get()),
            "jitter_min": self._safe_float(self.jitter_min_var.get(), DEFAULT_JITTER_MIN),
            "jitter_max": self._safe_float(self.jitter_max_var.get(), DEFAULT_JITTER_MAX),
            "items": [dict(item) for item in self.items],
        }

    def _load_profile(self, name):
        profile = normalize_profile(self.profiles.get(name))
        self.profiles[name] = profile
        self.current_profile = name
        self.items = [dict(item) for item in profile["items"]]
        self.hotkey = profile["hotkey"]
        self.hotkey_var.set(key_display(self.hotkey))
        self.jitter_on_var.set(profile["jitter_enabled"])
        self.jitter_min_var.set(f"{profile['jitter_min']:g}")
        self.jitter_max_var.set(f"{profile['jitter_max']:g}")
        self.profile_var.set(name)
        self._sync_jitter()
        self._refresh_profile_list()
        self._refresh_list()
        self._register_hotkey()
        self.status_var.set(f"当前方案：{name}")

    def _refresh_profile_list(self):
        names = list(self.profiles.keys())
        self.profile_box["values"] = names
        self.profile_var.set(self.current_profile)

    def _on_profile_change(self, event=None):
        target = self.profile_var.get()
        if target == self.current_profile or target not in self.profiles:
            return
        self._save_now()
        self._load_profile(target)
        self._save_now()

    def _new_profile(self):
        name = simpledialog.askstring("新建方案", "请输入新方案名称：", parent=self.root)
        if not name:
            return
        name = name.strip()
        if not name:
            return
        if name in self.profiles:
            messagebox.showwarning(APP_NAME, "同名方案已存在。", parent=self.root)
            return
        self._save_now()
        # 新方案从空白开始，与已有方案完全独立
        self.profiles[name] = normalize_profile(None)
        self._load_profile(name)
        self._save_now()

    def _copy_profile(self):
        name = simpledialog.askstring("复制方案", "请输入副本名称：",
                                      initialvalue=f"{self.current_profile}_副本", parent=self.root)
        if not name:
            return
        name = name.strip()
        if not name:
            return
        if name in self.profiles:
            messagebox.showwarning(APP_NAME, "同名方案已存在。", parent=self.root)
            return
        self._save_now()
        source = self._collect_profile()
        self.profiles[name] = {
            "hotkey": source["hotkey"],
            "jitter_enabled": source["jitter_enabled"],
            "jitter_min": source["jitter_min"],
            "jitter_max": source["jitter_max"],
            "items": [dict(item) for item in source["items"]],
        }
        self._load_profile(name)
        self._save_now()

    def _rename_profile(self):
        name = simpledialog.askstring("重命名方案", "请输入新名称：",
                                      initialvalue=self.current_profile, parent=self.root)
        if not name:
            return
        name = name.strip()
        if not name or name == self.current_profile:
            return
        if name in self.profiles:
            messagebox.showwarning(APP_NAME, "同名方案已存在。", parent=self.root)
            return
        self._save_now()
        data = self.profiles.pop(self.current_profile)
        self.profiles[name] = data
        self._load_profile(name)
        self._save_now()

    def _delete_profile(self):
        if len(self.profiles) <= 1:
            messagebox.showwarning(APP_NAME, "至少要保留一个方案。", parent=self.root)
            return
        if not messagebox.askyesno(APP_NAME, f"确定删除方案「{self.current_profile}」？", parent=self.root):
            return
        self.profiles.pop(self.current_profile, None)
        remaining = list(self.profiles.keys())
        self._load_profile(remaining[0])
        self._save_now()

    def _on_change(self):
        self._sync_jitter()
        job = getattr(self, "_save_job", None)
        if job is not None:
            try:
                self.root.after_cancel(job)
            except Exception:
                pass
        self._save_job = self.root.after(500, self._save_now)

    def _import_profiles(self):
        """把另一个配置文件里的方案合并进来（不覆盖本地已有采集数据的方案）。"""
        path = filedialog.askopenfilename(title="选择要导入的配置文件", parent=self.root,
                                          filetypes=[("配置文件", "*.json"), ("所有文件", "*.*")])
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as fh:
                incoming = normalize_config(json.load(fh))["profiles"]
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"读取失败：{exc}", parent=self.root)
            return

        added, replaced, kept, blank = [], [], [], []
        for name, profile in incoming.items():
            if not profile.get("items"):
                blank.append(name)
            existing = self.profiles.get(name)
            if existing is None:
                self.profiles[name] = profile
                added.append(name)
            elif not existing.get("items"):
                self.profiles[name] = profile
                replaced.append(name)
            else:
                kept.append(name)
        self._refresh_profile_list()
        self._save_now()

        lines = [f"来源：{os.path.basename(path)}", f"可导入方案：{len(incoming)} 个", ""]
        lines.append(f"新增：{len(added)} 个" + (f"（{'、'.join(added)}）" if added else ""))
        lines.append(f"覆盖（本地为空）：{len(replaced)} 个" + (f"（{'、'.join(replaced)}）" if replaced else ""))
        lines.append(f"保留（本地已有数据）：{len(kept)} 个" + (f"（{'、'.join(kept)}）" if kept else ""))
        if blank:
            lines.append("")
            lines.append(f"注意：其中 {len(blank)} 个方案在该文件里没有采集点，只导入了名称和热键：")
            lines.append("、".join(blank))
        messagebox.showinfo(APP_NAME, "\n".join(lines), parent=self.root)
        self.status_var.set(f"已导入 {len(added) + len(replaced)} 个方案")

    def _export_profiles(self):
        """把当前全部方案导出成一份 json，方便备份或拷到其他电脑。"""
        self._save_now()
        path = filedialog.asksaveasfilename(title="导出配置", parent=self.root,
                                            defaultextension=".json",
                                            initialfile="click_positions_backup.json",
                                            filetypes=[("配置文件", "*.json")])
        if not path:
            return
        try:
            save_config(path, {"version": 2, "current_profile": self.current_profile,
                               "profiles": self.profiles})
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"导出失败：{exc}", parent=self.root)
            return
        messagebox.showinfo(APP_NAME, f"已导出到：\n{path}", parent=self.root)

    def _save_now(self):
        self._save_job = None
        try:
            self.profiles[self.current_profile] = self._collect_profile()
            self.cfg = {"version": 2, "current_profile": self.current_profile,
                        "profiles": self.profiles}
            save_config(CONFIG_PATH, self.cfg)
        except Exception as exc:
            try:
                self.status_var.set(f"保存失败：{exc}")
            except Exception:
                pass

    def _sync_jitter(self):
        self.jitter_on = bool(self.jitter_on_var.get())
        self.jitter_min = self._safe_float(self.jitter_min_var.get(), DEFAULT_JITTER_MIN)
        self.jitter_max = self._safe_float(self.jitter_max_var.get(), DEFAULT_JITTER_MAX)

    @staticmethod
    def _safe_float(text, default):
        try:
            return float(str(text).strip())
        except (TypeError, ValueError):
            return default

    def _default_interval(self):
        try:
            value = parse_interval(self.default_interval_var.get())
        except ValueError:
            return 1.0
        return max(MIN_INTERVAL, min(MAX_INTERVAL, value))

    # ── 列表操作 ────────────────────────────────────────────────────────────
    def _describe(self, item):
        if item.get("type") == "key":
            return f"按键 {key_display(item.get('key', ''))}"
        return f"点击 ({item.get('x', 0)}, {item.get('y', 0)})"

    def _refresh_list(self):
        self.tree.delete(*self.tree.get_children())
        for position, item in enumerate(self.items, 1):
            kind = "键盘" if item.get("type") == "key" else "鼠标"
            self.tree.insert("", tk.END, iid=str(position - 1),
                             values=(position, kind, item.get("name", ""),
                                     self._describe(item),
                                     format_interval(item.get("interval", 1.0))))

    def _selected_index(self):
        selection = self.tree.selection()
        if not selection:
            return None
        try:
            index = int(selection[0])
        except ValueError:
            return None
        return index if 0 <= index < len(self.items) else None

    def _show_context_menu(self, event):
        row = self.tree.identify_row(event.y)
        if row:
            self.tree.selection_set(row)
        self.context_menu.tk_popup(event.x_root, event.y_root)

    def _delete_selected(self):
        index = self._selected_index()
        if index is None:
            messagebox.showinfo(APP_NAME, "请先在列表里选中一行。", parent=self.root)
            return
        self.items.pop(index)
        self._refresh_list()
        self._on_change()

    def _clear_items(self):
        if not self.items:
            return
        if not messagebox.askyesno(APP_NAME, f"确定清空当前方案的 {len(self.items)} 项？", parent=self.root):
            return
        self.items = []
        self._refresh_list()
        self._on_change()

    def _move_up(self):
        index = self._selected_index()
        if index is None or index == 0:
            return
        self.items[index - 1], self.items[index] = self.items[index], self.items[index - 1]
        self._refresh_list()
        self.tree.selection_set(str(index - 1))
        self._on_change()

    def _move_down(self):
        index = self._selected_index()
        if index is None or index >= len(self.items) - 1:
            return
        self.items[index + 1], self.items[index] = self.items[index], self.items[index + 1]
        self._refresh_list()
        self.tree.selection_set(str(index + 1))
        self._on_change()

    def _edit_selected(self):
        index = self._selected_index()
        if index is None:
            messagebox.showinfo(APP_NAME, "请先在列表里选中一行。", parent=self.root)
            return
        self._item_dialog(index)

    def _add_item_dialog(self):
        self._item_dialog(None)

    def _item_dialog(self, index):
        editing = index is not None
        if editing:
            current = dict(self.items[index])
        else:
            cursor_x, cursor_y = get_cursor_pos()
            current = {"type": "mouse", "name": "",
                       "x": cursor_x, "y": cursor_y, "key": "space",
                       "interval": self._default_interval()}

        win = tk.Toplevel(self.root)
        win.title("编辑项目" if editing else "手动添加")
        win.transient(self.root)
        win.resizable(False, False)
        win.geometry(f"+{self.root.winfo_rootx() + 150}+{self.root.winfo_rooty() + 130}")

        type_var = tk.StringVar(value=current.get("type", "mouse"))
        name_var = tk.StringVar(value=current.get("name", ""))
        x_var = tk.StringVar(value=str(current.get("x", 0)))
        y_var = tk.StringVar(value=str(current.get("y", 0)))
        interval_var = tk.StringVar(value=f"{float(current.get('interval', 1.0)):g}")
        key_holder = {"name": current.get("key", "space")}
        key_var = tk.StringVar(value=key_display(key_holder["name"]))
        error_var = tk.StringVar()

        body = ttk.Frame(win)
        body.pack(padx=14, pady=12, fill=tk.BOTH, expand=True)

        type_row = ttk.Frame(body)
        type_row.grid(row=0, column=0, columnspan=3, sticky=tk.W, pady=(0, 8))
        ttk.Label(type_row, text="类型").pack(side=tk.LEFT)
        ttk.Radiobutton(type_row, text="鼠标点击", value="mouse", variable=type_var).pack(side=tk.LEFT, padx=8)
        ttk.Radiobutton(type_row, text="键盘按键", value="key", variable=type_var).pack(side=tk.LEFT)

        ttk.Label(body, text="名称").grid(row=1, column=0, sticky=tk.W, pady=4)
        ttk.Entry(body, textvariable=name_var, width=32).grid(row=1, column=1, columnspan=2, sticky=tk.W, pady=4)

        mouse_frame = ttk.Frame(body)
        mouse_frame.grid(row=2, column=0, columnspan=3, sticky=tk.W)
        ttk.Label(mouse_frame, text="X").pack(side=tk.LEFT)
        ttk.Entry(mouse_frame, textvariable=x_var, width=9).pack(side=tk.LEFT, padx=4)
        ttk.Label(mouse_frame, text="Y").pack(side=tk.LEFT)
        ttk.Entry(mouse_frame, textvariable=y_var, width=9).pack(side=tk.LEFT, padx=4)
        ttk.Button(mouse_frame, text="取当前鼠标位置", width=16,
                   command=lambda: self._fill_cursor(x_var, y_var)).pack(side=tk.LEFT, padx=8)

        key_frame = ttk.Frame(body)
        key_frame.grid(row=3, column=0, columnspan=3, sticky=tk.W)
        ttk.Label(key_frame, text="按键").pack(side=tk.LEFT)
        ttk.Entry(key_frame, textvariable=key_var, width=12, state="readonly").pack(side=tk.LEFT, padx=4)
        ttk.Button(key_frame, text="按下要绑定的键", width=16,
                   command=lambda: self._start_key_capture(("var", key_var, key_holder))).pack(side=tk.LEFT, padx=8)

        ttk.Label(body, text="间隔").grid(row=4, column=0, sticky=tk.W, pady=(10, 4))
        ttk.Entry(body, textvariable=interval_var, width=14).grid(row=4, column=1, sticky=tk.W, pady=(10, 4))
        ttk.Label(body, text="支持 2h / 30m / 90s / 1h30m，范围 0.05 秒 ~ 2 小时").grid(
            row=4, column=2, sticky=tk.W, pady=(10, 4), padx=6)

        ttk.Label(body, textvariable=error_var, foreground="#c00").grid(
            row=5, column=0, columnspan=3, sticky=tk.W, pady=(6, 0))

        def toggle_frames(*_):
            if type_var.get() == "mouse":
                key_frame.grid_remove()
                mouse_frame.grid(row=2, column=0, columnspan=3, sticky=tk.W)
            else:
                mouse_frame.grid_remove()
                key_frame.grid(row=3, column=0, columnspan=3, sticky=tk.W)

        type_var.trace_add("write", toggle_frames)
        toggle_frames()

        def confirm():
            if type_var.get() == "mouse":
                try:
                    x_value = int(float(x_var.get().strip()))
                    y_value = int(float(y_var.get().strip()))
                except ValueError:
                    error_var.set("X / Y 必须是数字。")
                    return
            else:
                if not key_holder["name"]:
                    error_var.set("请先绑定一个按键。")
                    return
                x_value = y_value = 0
            try:
                interval = parse_interval(interval_var.get())
            except ValueError as exc:
                error_var.set(str(exc))
                return
            if not (MIN_INTERVAL <= interval <= MAX_INTERVAL):
                error_var.set(f"间隔需要在 {MIN_INTERVAL} 秒 ~ 2 小时之间。")
                return
            item = {
                "type": type_var.get(),
                "name": name_var.get().strip() or ("点击" if type_var.get() == "mouse" else key_display(key_holder["name"])),
                "interval": round(interval, 4),
            }
            if type_var.get() == "mouse":
                item["x"] = x_value
                item["y"] = y_value
            else:
                item["key"] = key_holder["name"]
            if editing:
                self.items[index] = item
            else:
                self.items.append(item)
            self._refresh_list()
            self._on_change()
            win.destroy()

        button_row = ttk.Frame(body)
        button_row.grid(row=6, column=0, columnspan=3, pady=(12, 0), sticky=tk.E)
        ttk.Button(button_row, text="确定", width=10, command=confirm).pack(side=tk.LEFT, padx=4)
        ttk.Button(button_row, text="取消", width=10, command=win.destroy).pack(side=tk.LEFT)

        win.grab_set()
        win.focus_set()

    @staticmethod
    def _fill_cursor(x_var, y_var):
        cursor_x, cursor_y = get_cursor_pos()
        x_var.set(str(cursor_x))
        y_var.set(str(cursor_y))

    # ── 采集 ────────────────────────────────────────────────────────────────
    def _capture_position(self):
        def done(x_value, y_value):
            self.items.append({
                "type": "mouse",
                "name": f"点击{len(self.items) + 1}",
                "x": x_value,
                "y": y_value,
                "interval": self._default_interval(),
            })
            self._refresh_list()
            self._on_change()
            self.status_var.set(f"已采集 点击 ({x_value}, {y_value})")

        self._countdown_window("请把鼠标移到目标位置，倒计时结束后自动记录", done)

    def _countdown_window(self, title, on_done):
        win = tk.Toplevel(self.root)
        win.title("采集中")
        win.attributes("-topmost", True)
        win.resizable(False, False)
        width, height = 380, 130
        left = (win.winfo_screenwidth() - width) // 2
        win.geometry(f"{width}x{height}+{left}+60")
        ttk.Label(win, text=title, wraplength=350).pack(pady=(14, 8))
        info_var = tk.StringVar()
        ttk.Label(win, textvariable=info_var, font=("Consolas", 11, "bold")).pack()
        state = {"left": 3}

        def tick():
            cursor_x, cursor_y = get_cursor_pos()
            info_var.set(f"当前坐标 ({cursor_x}, {cursor_y})     剩余 {state['left']} 秒")
            if state["left"] <= 0:
                win.destroy()
                on_done(cursor_x, cursor_y)
                return
            state["left"] -= 1
            win.after(1000, tick)

        tick()

    def _capture_key(self):
        self._start_key_capture("new_item", "请按下要添加到列表的按键…")

    def _start_set_hotkey(self):
        self._start_key_capture("hotkey", "请按下要作为启停热键的按键…")

    def _start_key_capture(self, target, prompt="请按下要绑定的按键…"):
        if not HAS_KEYBOARD:
            messagebox.showwarning(APP_NAME, "当前环境没有 keyboard 库，无法采集按键。", parent=self.root)
            return
        if self.capturing:
            return
        self.capturing = True
        self._key_target = target
        self._unregister_hotkey()
        self.status_var.set(prompt)
        threading.Thread(target=self._key_read_worker, daemon=True).start()

    def _key_read_worker(self):
        name = None
        try:
            while True:
                event = keyboard.read_event(suppress=False)
                if getattr(event, "event_type", "down") == "down":
                    name = event.name
                    break
        except Exception as exc:
            self.ui_queue.put(("error", f"读取按键失败：{exc}"))
        self.ui_queue.put(("key", name, getattr(self, "_key_target", None)))

    def _handle_key_captured(self, name, target):
        self.capturing = False
        self._register_hotkey()
        if not name:
            self.status_var.set("没有采集到按键")
            return
        if target == "hotkey":
            self.hotkey = normalize_key_name(name) or DEFAULT_HOTKEY
            self.hotkey_var.set(key_display(self.hotkey))
            self._register_hotkey()
            self._on_change()
            self.status_var.set(f"启停热键已设为 {key_display(self.hotkey)}")
        elif target == "new_item":
            key_name = normalize_key_name(name) or name
            self.items.append({
                "type": "key",
                "name": key_display(key_name),
                "key": key_name,
                "interval": self._default_interval(),
            })
            self._refresh_list()
            self._on_change()
            self.status_var.set(f"已采集按键 {key_display(key_name)}")
        elif isinstance(target, tuple) and target and target[0] == "var":
            key_name = normalize_key_name(name) or name
            target[1].set(key_display(key_name))
            if len(target) > 2 and isinstance(target[2], dict):
                target[2]["name"] = key_name
            self.status_var.set(f"已绑定按键 {key_display(key_name)}")

    # ── 全局热键 ────────────────────────────────────────────────────────────
    def _register_hotkey(self):
        self._unregister_hotkey()
        if not HAS_KEYBOARD or not self.hotkey:
            return
        try:
            self.hotkey_handle = keyboard.add_hotkey(self.hotkey, self._on_hotkey, suppress=False)
        except Exception as exc:
            self.hotkey_handle = None
            self.status_var.set(f"热键 {key_display(self.hotkey)} 注册失败：{exc}")

    def _unregister_hotkey(self):
        if self.hotkey_handle is not None and keyboard is not None:
            try:
                keyboard.remove_hotkey(self.hotkey_handle)
            except Exception:
                pass
        self.hotkey_handle = None

    def _on_hotkey(self):
        self.ui_queue.put(("toggle", None))

    # ── 主线程消息泵 ────────────────────────────────────────────────────────
    def _pump_queue(self):
        try:
            while True:
                self._handle_message(self.ui_queue.get_nowait())
        except queue.Empty:
            pass
        self.root.after(60, self._pump_queue)

    def _handle_message(self, message):
        kind = message[0]
        if kind == "toggle":
            if self.running:
                self._stop_clicking()
            else:
                self._start_clicking()
        elif kind == "status":
            self.status_var.set(message[1])
        elif kind == "stopped":
            self.running = False
            self.btn_start.config(state=tk.NORMAL)
            self.btn_stop.config(state=tk.DISABLED)
            self.status_var.set("已停止")
        elif kind == "error":
            messagebox.showerror(APP_NAME, message[1], parent=self.root)
        elif kind == "key":
            self._handle_key_captured(message[1], message[2])

    # ── 执行引擎 ────────────────────────────────────────────────────────────
    def _calc_delay(self, interval):
        try:
            interval = float(interval)
        except (TypeError, ValueError):
            interval = 1.0
        if self.jitter_on:
            low = min(self.jitter_min, self.jitter_max)
            high = max(self.jitter_min, self.jitter_max)
            if high > 0:
                interval = interval * random.uniform(low, high)
        return max(MIN_INTERVAL, interval)

    def _set_status(self, text):
        self.ui_queue.put(("status", text))

    def _start_clicking(self):
        if self.running:
            return
        if not self.items:
            messagebox.showwarning(APP_NAME, "列表为空，请先采集或手动添加。", parent=self.root)
            return
        self.running = True
        self.btn_start.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        self.click_thread = threading.Thread(target=self._click_loop, daemon=True)
        self.click_thread.start()

    def _stop_clicking(self):
        if not self.running:
            return
        self.running = False
        self.btn_start.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.DISABLED)
        self.status_var.set("已停止")

    def _click_loop(self):
        while self.running:
            snapshot = [dict(item) for item in self.items]
            if not snapshot:
                break
            for position, item in enumerate(snapshot, 1):
                if not self.running:
                    break
                self._set_status(f"第 {position}/{len(snapshot)} 项：{self._describe(item)}")
                if item.get("type") == "mouse":
                    mouse_click_left(item.get("x", 0), item.get("y", 0))
                else:
                    if not key_tap(item.get("key", "")):
                        self._set_status(f"按键 {key_display(item.get('key', ''))} 执行失败")
                if not self.running:
                    break
                delay = self._calc_delay(item.get("interval", 1.0))
                self._set_status(f"第 {position} 项完成，随机等待 {format_seconds(delay)}")
                self._sleep_interruptible(delay)
        self.running = False
        self.ui_queue.put(("stopped", None))

    def _sleep_interruptible(self, seconds):
        end = time.time() + max(0.0, seconds)
        while self.running and time.time() < end:
            time.sleep(min(0.05, max(0.0, end - time.time())))

    # ── 按住右键 ────────────────────────────────────────────────────────────
    def _toggle_right_hold(self):
        if self.right_held:
            self._release_right()
        else:
            self._press_right()

    def _press_right(self):
        if self.right_held:
            return
        self.right_held = True
        self.right_thread = threading.Thread(target=self._right_hold_loop, daemon=True)
        self.right_thread.start()
        self.btn_right.config(text="松开右键")
        self.status_var.set("右键已按住（再次点击按钮松开）")

    def _right_hold_loop(self):
        # 每 50 毫秒重复发送一次按下信号，游戏才认得住
        while self.right_held:
            mouse_right_down()
            time.sleep(0.05)

    def _release_right(self):
        if not self.right_held:
            return
        self.right_held = False
        mouse_right_up()
        self.btn_right.config(text="按住右键")
        self.status_var.set("右键已松开")

    # ── 收尾 ────────────────────────────────────────────────────────────────
    def _restart_as_admin(self):
        self._save_now()
        if relaunch_as_admin():
            self._on_close()
        else:
            messagebox.showerror(APP_NAME, "提权失败，请右键以管理员身份运行。", parent=self.root)

    def _on_close(self):
        try:
            self.running = False
            self._release_right()
            self._unregister_hotkey()
            if keyboard is not None:
                try:
                    keyboard.unhook_all()
                except Exception:
                    pass
            self._save_now()
        except Exception:
            pass
        finally:
            self.root.destroy()


def main():
    if "--selftest" in sys.argv:
        run_selftest()
        return
    app = AutoClicker()
    app.root.mainloop()


def run_selftest():
    """自检：把运行环境信息写入程序同目录的 selftest.txt，方便排查问题。"""
    cfg = load_config(CONFIG_PATH)
    lines = [
        f"{APP_NAME} {APP_VERSION}",
        f"程序目录：{APP_DIR}",
        f"打包模式：{'是' if getattr(sys, 'frozen', False) else '否（源码运行）'}",
        f"数据文件：{CONFIG_PATH}",
        f"数据文件可写：{'是' if os.access(os.path.dirname(CONFIG_PATH), os.W_OK) else '否'}",
        f"方案数量：{len(cfg['profiles'])}（{', '.join(cfg['profiles'].keys())}）",
        f"键盘库 keyboard：{'可用' if HAS_KEYBOARD else '不可用'}",
        f"管理员权限：{'是' if is_admin() else '否'}",
        f"Tcl/Tk 运行库：{TCL_RUNTIME or '使用系统自带（源码运行）'}",
        f"Python：{sys.version.split()[0]}",
    ]
    text = "\n".join(lines)
    output = os.path.join(APP_DIR, "selftest.txt")
    try:
        with open(output, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    except Exception:
        pass
    try:
        print(text)
    except Exception:
        pass


if __name__ == "__main__":
    main()
