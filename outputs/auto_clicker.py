# -*- coding: utf-8 -*-
"""自动点击器 —— 鼠标 / 键盘自动化工具

功能概览：
  1. 采集鼠标坐标或键盘按键，按列表顺序循环执行，每一项可独立设置间隔
  2. 间隔支持 秒 / 分 / 时（0.05 秒 ~ 2 小时），写法灵活：2h、30m、90s、1h30m
  3. 间隔随机化：可设随机倍率区间（默认 0.5x ~ 2.0x），例如设 0.1 秒实际在 0.05~0.2 秒之间
  4. 数据持久化：配置保存在程序同目录的 click_positions.json，重启、换机都不丢
  5. 多方案管理：新建 / 复制 / 重命名 / 删除，方案之间数据完全独立
  6. 全局热键启停（默认 F12，可自定义任意键）
  7. 按住键：可采集任意键，可点按钮、可按独立热键随时开关，也可设成随点击一起运行
  8. 相对偏移：鼠标项可填「相对上一个鼠标点的偏移量」，不必重新采集
  9. 轮次间隔：每一轮循环之间可以单独设置等待时间
 10. Boss 卡计数模式：可选 OCR 识别卡片数量，按设定次数召唤后自动停止
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
import traceback


# ── 打包后 Tcl/Tk 运行库引导 ────────────────────────────────────────────────
# PyInstaller 打包成 exe 后，Tcl 只认「相对路径」或它自己算出来的路径，
# 因此这里把自带的 Tcl/Tk 运行库释放到固定目录，并切换到该目录。
# 必须在 import tkinter 之前执行。
def bootstrap_tcl_tk():
    """打包后 Tcl/Tk 运行库引导：确保 DLL 和脚本版本一致。"""
    if not getattr(sys, "frozen", False):
        return None
    bundle = getattr(sys, "_MEIPASS", None)
    if not bundle:
        return None

    # 清除系统可能残留的旧路径，避免版本冲突
    os.environ.pop("TCL_LIBRARY", None)
    os.environ.pop("TK_LIBRARY", None)

    # 从 DLLs 目录获取 Tcl/Tk DLL 的实际版本号，然后精确匹配同版本的脚本
    dlls_dir = os.path.join(bundle, "DLLs")
    tcl_dll = os.path.join(dlls_dir, "tcl86t.dll") if os.path.isdir(dlls_dir) else None
    tk_dll = os.path.join(dlls_dir, "tk86t.dll") if tcl_dll and os.path.isfile(tcl_dll) else None

    # 候选路径：exe 同级 runtime、LOCALAPPDATA、bundle 自身
    exe_dir = os.path.dirname(os.path.abspath(sys.executable))
    local_app = os.environ.get("LOCALAPPDATA")
    candidates = []
    if local_app:
        candidates.append(os.path.join(local_app, "AutoClicker", "runtime"))
    candidates.append(os.path.join(exe_dir, "runtime"))
    candidates.append(bundle)

    for runtime in candidates:
        tcl_dir = os.path.join(runtime, "tcl", "tcl8.6")
        tk_dir = os.path.join(runtime, "tk", "tk8.6")
        marker = os.path.join(tcl_dir, "init.tcl")
        if not os.path.isfile(marker):
            # 从 bundle 复制
            try:
                copy_tree(os.path.join(bundle, "tcl"), os.path.join(runtime, "tcl"))
                copy_tree(os.path.join(bundle, "tk"), os.path.join(runtime, "tk"))
            except Exception:
                continue
        if not os.path.isfile(marker):
            continue

        # 读 init.tcl 确认版本号，只用版本匹配的 DLL
        try:
            with open(marker, "r", encoding="utf-8", errors="ignore") as fh:
                for line in fh:
                    if "package require -exact Tcl" in line:
                        ver = line.split()[-1].strip()
                        # 检查 DLLs 目录中是否有对应版本的 DLL
                        if tcl_dll and os.path.isfile(tcl_dll):
                            # DLL 已通过 PyInstaller 打包，直接用
                            pass
                        break
        except Exception:
            pass

        os.chdir(runtime)
        os.environ["TCL_LIBRARY"] = os.path.join(runtime, "tcl", "tcl8.6")
        os.environ["TK_LIBRARY"] = os.path.join(runtime, "tk", "tk8.6")
        return runtime

    # 兜底：直接用 bundle 路径
    os.environ["TCL_LIBRARY"] = os.path.join(bundle, "tcl", "tcl8.6")
    os.environ["TK_LIBRARY"] = os.path.join(bundle, "tk", "tk8.6")
    try:
        os.chdir(bundle)
    except Exception:
        pass
    return bundle


def _ensure_dll_path():
    """确保 Tcl/Tk DLL 从打包目录加载，不被系统旧版覆盖。"""
    if not getattr(sys, "frozen", False):
        return
    bundle = getattr(sys, "_MEIPASS", None)
    if not bundle:
        return
    # 将 bundle 根目录加入 DLL 搜索路径最前面
    try:
        os.add_dll_directory(bundle)
    except AttributeError:
        pass
    # 也加入 DLLs 子目录
    dlls_dir = os.path.join(bundle, "DLLs")
    if os.path.isdir(dlls_dir):
        try:
            os.add_dll_directory(dlls_dir)
        except AttributeError:
            pass


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
_ensure_dll_path()

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from count_mode import (
    CountGuard,
    CountSafetyError,
    HAS_PIL as HAS_PIL_OCR,
    HAS_PYTesseract as HAS_PYTesseract_OCR,
    ocr_available,
    parse_region,
    read_count_once,
    read_count_stable,
    resolve_tesseract,
    resolve_tessdata,
)

# ── 可选依赖：键盘钩子与按键模拟 ────────────────────────────────────────────
try:
    import keyboard
    HAS_KEYBOARD = True
except Exception:  # 缺少 keyboard 库时只保留鼠标功能
    keyboard = None
    HAS_KEYBOARD = False


# ── 常量 ────────────────────────────────────────────────────────────────────
APP_NAME = "自动点击器"
APP_VERSION = "v35"
CONFIG_NAME = "click_positions.json"

MIN_INTERVAL = 0.05       # 最小间隔（秒）
MAX_INTERVAL = 7200.0     # 最大间隔（秒），即 2 小时
MAX_OFFSET = 2000         # 相对偏移允许的最大像素数，避免填出离谱的坐标
DEFAULT_HOTKEY = "f12"
DEFAULT_RIGHT_HOTKEY = "f8"   # 按住键的独立热键
DEFAULT_HOLD_KEY = "right"     # 默认按住的键（right=鼠标右键，也可设为任意键名）
DEFAULT_JITTER_MIN = 0.5  # 随机倍率下限
DEFAULT_JITTER_MAX = 2.0  # 随机倍率上限
DEFAULT_COUNT_TARGET = 10
DEFAULT_COUNT_STAR = 1
DEFAULT_COUNT_OPEN_KEY = "e"
DEFAULT_COUNT_OPEN_WAIT = 2.0
DEFAULT_COUNT_POST_CLICK_WAIT = 2.0
DEFAULT_COUNT_NEXT_CYCLE_WAIT = 5.0
DEFAULT_COUNT_AUTO_NEXT = True
DEFAULT_COUNT_REGION = (0, 0, 120, 36)
DEFAULT_COUNT_BOSS_CARD_POINT = (0, 0)

user32 = ctypes.windll.user32

MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010

# --- SendInput ---
INPUT_MOUSE = 0
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_WHEEL = 0x0800
WM_HOTKEY = 0x0312
PM_REMOVE = 0x0001

# --- Raw Input (兼容游戏的鼠标输入捕获) ---

class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.wintypes.LONG),
        ("dy", ctypes.wintypes.LONG),
        ("mouseData", ctypes.wintypes.DWORD),
        ("dwFlags", ctypes.wintypes.DWORD),
        ("time", ctypes.wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]

class _INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT)]

class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.wintypes.DWORD),
        ("union", _INPUT_UNION),
    ]

SendInput = user32.SendInput
SendInput.argtypes = [ctypes.wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
SendInput.restype = ctypes.wintypes.UINT


class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", ctypes.wintypes.HWND),
        ("message", ctypes.wintypes.UINT),
        ("wParam", ctypes.wintypes.WPARAM),
        ("lParam", ctypes.wintypes.LPARAM),
        ("time", ctypes.wintypes.DWORD),
        ("pt", ctypes.wintypes.POINT),
    ]

def _pixel_to_abs(x, y):
    """将像素坐标转换为 SendInput 绝对坐标 (0-65535)。"""
    sw = user32.GetSystemMetrics(0)
    sh = user32.GetSystemMetrics(1)
    if sw <= 0: sw = 1920
    if sh <= 0: sh = 1080
    return int(x * 65535 / sw), int(y * 65535 / sh)


def _send_mouse_input(flags, dx=0, dy=0, data=0):
    inp = INPUT()
    inp.type = INPUT_MOUSE
    inp.union.mi.dx = dx
    inp.union.mi.dy = dy
    inp.union.mi.mouseData = data
    inp.union.mi.dwFlags = flags
    inp.union.mi.time = 0
    inp.union.mi.dwExtraInfo = ctypes.pointer(ctypes.c_ulong(0))
    SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

def _bezier_curve(p0, p1, p2, p3, steps):
    points = []
    for i in range(steps + 1):
        t = i / steps; u = 1 - t
        x = u**3*p0[0]+3*u**2*t*p1[0]+3*u*t**2*p2[0]+t**3*p3[0]
        y = u**3*p0[1]+3*u**2*t*p1[1]+3*u*t**2*p2[1]+t**3*p3[1]
        points.append((int(x), int(y)))
    return points

def human_move_to(target_x, target_y, duration=None):
    cur_x, cur_y = get_cursor_pos()
    dist = ((target_x-cur_x)**2+(target_y-cur_y)**2)**0.5
    if dist < 2: return
    if duration is None:
        duration = min(0.4, max(0.08, dist/2500.0))+random.uniform(-0.03,0.05)
    duration = max(0.04, duration)
    c1x=cur_x+(target_x-cur_x)*random.uniform(0.2,0.4)+random.uniform(-20,20)
    c1y=cur_y+(target_y-cur_y)*random.uniform(0.1,0.3)+random.uniform(-20,20)
    c2x=cur_x+(target_x-cur_x)*random.uniform(0.6,0.8)+random.uniform(-15,15)
    c2y=cur_y+(target_y-cur_y)*random.uniform(0.7,0.9)+random.uniform(-15,15)
    steps=max(5,int(dist/3))
    curve=_bezier_curve((cur_x,cur_y),(c1x,c1y),(c2x,c2y),(target_x,target_y),steps)
    interval=duration/len(curve)
    for i,(px,py) in enumerate(curve):
        if i>len(curve)*0.7: px+=random.uniform(-1,1); py+=random.uniform(-1,1)
        ax,ay=_pixel_to_abs(px,py); _send_mouse_input(MOUSEEVENTF_MOVE|MOUSEEVENTF_ABSOLUTE,dx=ax,dy=ay)
        time.sleep(interval*random.uniform(0.8,1.2))
    ax,ay=_pixel_to_abs(target_x,target_y); _send_mouse_input(MOUSEEVENTF_MOVE|MOUSEEVENTF_ABSOLUTE,dx=ax,dy=ay)



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
        # rel 表示 x/y 存的是「相对上一个鼠标点的偏移量」；旧数据没有这个字段，一律按绝对坐标处理
        item["mode"] = "rel" if str(raw.get("mode", "") or "").lower() == "rel" else "abs"
    else:
        key_name = normalize_key_name(raw.get("key"))
        if not key_name:
            return None
        item["key"] = key_name
    if not item["name"]:
        item["name"] = "点击" if item["type"] == "mouse" else key_display(item["key"])
    return item


def safe_seconds(value, default=0.0, low=0.0, high=MAX_INTERVAL):
    """把配置里的秒数转成合法数值，坏值用默认值兜底。"""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))


def normalize_point(value, default=(0, 0)):
    """把配置里的坐标统一成整数坐标元组。"""
    if isinstance(value, dict):
        value = (value.get("x"), value.get("y"))
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return tuple(default)
    try:
        return (int(float(value[0])), int(float(value[1])))
    except (TypeError, ValueError):
        return tuple(default)


def normalize_region_map(raw, stars=5):
    """统一数量识别区域配置，保留每个星级自己的区域。"""
    raw = raw if isinstance(raw, dict) else {}
    result = {}
    for star in range(1, stars + 1):
        value = raw.get(str(star), raw.get(star, DEFAULT_COUNT_REGION))
        result[str(star)] = list(parse_region(value, DEFAULT_COUNT_REGION))
    return result


def normalize_profile(raw):
    raw = raw if isinstance(raw, dict) else {}
    star_points = {}
    raw_star_points = raw.get("count_star_points") if isinstance(raw.get("count_star_points"), dict) else {}
    for star in range(1, 6):
        star_points[str(star)] = dict(zip(("x", "y"), normalize_point(raw_star_points.get(str(star)))))
    selected_star = max(1, min(5, int(safe_seconds(raw.get("count_star", DEFAULT_COUNT_STAR), DEFAULT_COUNT_STAR, 1, 5))))
    boss_card_point = normalize_point(raw.get("count_boss_card_point"))
    if not any(boss_card_point):
        boss_card_point = normalize_point(raw_star_points.get(str(selected_star)))
    raw_ocr_regions = raw.get("count_ocr_regions") if isinstance(raw.get("count_ocr_regions"), dict) else {}
    execution_mode = "count" if str(raw.get("execution_mode", "") or "").lower() in ("count", "boss_count") else "free"
    profile = {
        "hotkey": normalize_key_name(raw.get("hotkey") or raw.get("hotkey_vk")) or DEFAULT_HOTKEY,
        "right_hotkey": (normalize_key_name(raw.get("right_hotkey")
                                            or raw.get("right_hold_hotkey"))
                         or DEFAULT_RIGHT_HOTKEY),
        "hold_key": normalize_key_name(raw.get("hold_key")) or DEFAULT_HOLD_KEY,
        "auto_right_hold": bool(raw.get("auto_right_hold", False)),
        "cycle_interval": safe_seconds(raw.get("cycle_interval"), 0.0),
        "jitter_enabled": bool(raw.get("jitter_enabled", True)),
        "jitter_min": float(raw.get("jitter_min", DEFAULT_JITTER_MIN) or DEFAULT_JITTER_MIN),
        "jitter_max": float(raw.get("jitter_max", DEFAULT_JITTER_MAX) or DEFAULT_JITTER_MAX),
        "execution_mode": execution_mode,
        "count_target": max(1, min(999999, int(safe_seconds(raw.get("count_target", DEFAULT_COUNT_TARGET), DEFAULT_COUNT_TARGET, 1, 999999)))),
        "count_star": max(1, min(5, int(safe_seconds(raw.get("count_star", DEFAULT_COUNT_STAR), DEFAULT_COUNT_STAR, 1, 5)))),
        "count_open_key": normalize_key_name(raw.get("count_open_key")) or DEFAULT_COUNT_OPEN_KEY,
        "count_boss_card_point": dict(zip(("x", "y"), boss_card_point)),
        "count_summon_point": dict(zip(("x", "y"), normalize_point(raw.get("count_summon_point")))),
        "count_star_points": star_points,
        "count_ocr_region": list(parse_region(raw.get("count_ocr_region"), parse_region(raw_ocr_regions.get(str(selected_star), DEFAULT_COUNT_REGION), DEFAULT_COUNT_REGION))),
        "count_ocr_regions": normalize_region_map(raw_ocr_regions),
        "count_open_wait": safe_seconds(raw.get("count_open_wait"), DEFAULT_COUNT_OPEN_WAIT, 0.05, MAX_INTERVAL),
        "count_post_click_wait": safe_seconds(raw.get("count_post_click_wait"), DEFAULT_COUNT_POST_CLICK_WAIT, 0.05, MAX_INTERVAL),
        "count_next_cycle_wait": safe_seconds(raw.get("count_next_cycle_wait"), DEFAULT_COUNT_NEXT_CYCLE_WAIT, 0.05, MAX_INTERVAL),
        "count_auto_next": bool(raw.get("count_auto_next", DEFAULT_COUNT_AUTO_NEXT)),
        "count_progress": max(0, int(safe_seconds(raw.get("count_progress", 0), 0, 0, 999999))),
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
    if 0x70 <= vk <= 0x87:                          # F1-F24
        return "f%d" % (vk - 0x6F)
    if 0x41 <= vk <= 0x5A:
        return chr(vk).lower()
    if 0x30 <= vk <= 0x39:
        return chr(vk)
    if 0x60 <= vk <= 0x69:
        return "num %d" % (vk - 0x60)
    if vk == 0x20:
        return "space"
    return _VK_NAMES.get(vk)


def key_name_to_vk(name):
    """把常用键名转换为 Windows 虚拟键码，用于键盘钩子失效时的轮询兜底。"""
    raw = str(name or "").strip().lower()
    if raw.isdigit():
        return ord(raw)
    normalized = normalize_key_name(name)
    if not normalized:
        return None
    special = {
        "backspace": 0x08, "tab": 0x09, "enter": 0x0D, "shift": 0x10,
        "ctrl": 0x11, "alt": 0x12, "caps lock": 0x14, "esc": 0x1B,
        "space": 0x20, "page up": 0x21, "page down": 0x22, "end": 0x23,
        "home": 0x24, "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
        "insert": 0x2D, "delete": 0x2E,
        "left shift": 0xA0, "right shift": 0xA1, "left ctrl": 0xA2,
        "right ctrl": 0xA3, "left alt": 0xA4, "right alt": 0xA5,
    }
    if normalized in special:
        return special[normalized]
    if len(normalized) == 1 and normalized.isalpha():
        return ord(normalized.upper())
    if len(normalized) == 1 and normalized.isdigit():
        return ord(normalized)
    if normalized.startswith("f") and normalized[1:].isdigit():
        number = int(normalized[1:])
        if 1 <= number <= 24:
            return 0x70 + number - 1
    if normalized.startswith("num "):
        number = normalized[4:]
        if number.isdigit() and 0 <= int(number) <= 9:
            return 0x60 + int(number)
    return None


def key_is_pressed(name):
    """读取键盘当前状态，供热键钩子失效时使用。"""
    vk = key_name_to_vk(name)
    if not vk:
        return False
    get_state = user32.GetAsyncKeyState
    get_state.argtypes = [ctypes.c_int]
    get_state.restype = ctypes.c_short
    return bool(get_state(vk) & 0x8000)


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
        return lowered
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


def mouse_click_left(x, y, jitter=True):
    """Bezier + SendInput."""
    offset_x = random.uniform(-2, 2) if jitter else 0
    offset_y = random.uniform(-2, 2) if jitter else 0
    human_move_to(int(x + offset_x), int(y + offset_y))
    time.sleep(random.uniform(0.01, 0.03))
    _send_mouse_input(MOUSEEVENTF_LEFTDOWN)
    time.sleep(random.uniform(0.04, 0.08))
    _send_mouse_input(MOUSEEVENTF_LEFTUP)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)


def mouse_right_down():
    _send_mouse_input(MOUSEEVENTF_RIGHTDOWN)


def mouse_right_up():
    _send_mouse_input(MOUSEEVENTF_RIGHTUP)


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
        self.hold_key = DEFAULT_HOLD_KEY
        self.right_hotkey = DEFAULT_RIGHT_HOTKEY
        self.right_hotkey_handle = None
        self.auto_right_hold = False
        self.right_held_auto = False
        self.default_interval = 1.0
        self.jitter_on = True
        self.jitter_min = DEFAULT_JITTER_MIN
        self.jitter_max = DEFAULT_JITTER_MAX
        self.cycle_interval = 0.0
        self.execution_mode = "free"
        self.count_target = DEFAULT_COUNT_TARGET
        self.count_star = DEFAULT_COUNT_STAR
        self.count_open_key = DEFAULT_COUNT_OPEN_KEY
        self.count_boss_card_point = dict(zip(("x", "y"), DEFAULT_COUNT_BOSS_CARD_POINT))
        self.count_summon_point = {"x": 0, "y": 0}
        self.count_star_points = {str(star): {"x": 0, "y": 0} for star in range(1, 6)}
        self.count_ocr_region = list(DEFAULT_COUNT_REGION)
        self.count_ocr_regions = {str(star): list(DEFAULT_COUNT_REGION) for star in range(1, 6)}
        self.count_open_wait = DEFAULT_COUNT_OPEN_WAIT
        self.count_post_click_wait = DEFAULT_COUNT_POST_CLICK_WAIT
        self.count_next_cycle_wait = DEFAULT_COUNT_NEXT_CYCLE_WAIT
        self.count_auto_next = DEFAULT_COUNT_AUTO_NEXT
        self.count_progress = 0
        self._save_job = None
        self._key_target = None

        self.running = False

        # Rotation
        self.click_thread = None
        self.right_held = False
        self.right_thread = None
        self.capturing = False
        self.ui_queue = queue.Queue()
        self._hotkey_poll_stop = threading.Event()
        self._hotkey_poll_state = {"hotkey": False, "right_hotkey": False}
        self._last_hotkey_trigger = 0.0
        self._win_hotkey_stop = threading.Event()
        self._win_hotkey_thread = None

        self.root = tk.Tk()
        self.root.title(f"{APP_NAME} {APP_VERSION}")
        self.root.minsize(600, 920)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._center_window(760, 980)

        self._build_ui()
        self._load_profile(self.current_profile)
        self._register_hotkey()
        self._save_now()
        self._hotkey_poll_thread = threading.Thread(target=self._hotkey_poll_loop, daemon=True)
        self._hotkey_poll_thread.start()
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
        row1.pack(fill=tk.X, padx=8, pady=(5, 2))
        ttk.Label(row1, text="启停").pack(side=tk.LEFT)
        self.hotkey_var = tk.StringVar(value=key_display(self.hotkey))
        ttk.Label(row1, textvariable=self.hotkey_var, width=8, anchor=tk.CENTER,
                  relief=tk.SUNKEN).pack(side=tk.LEFT, padx=4)
        ttk.Button(row1, text="设置", width=6, command=self._start_set_hotkey).pack(side=tk.LEFT)
        ttk.Label(row1, text="按住键").pack(side=tk.LEFT, padx=(12, 0))
        self.hold_key_var = tk.StringVar(value=key_display(self.hold_key))
        ttk.Label(row1, textvariable=self.hold_key_var, width=8, anchor=tk.CENTER,
                  relief=tk.SUNKEN).pack(side=tk.LEFT, padx=4)
        ttk.Button(row1, text="采集", width=6,
                   command=self._start_set_hold_key).pack(side=tk.LEFT)
        self.right_hotkey_var = tk.StringVar(value=key_display(self.right_hotkey))
        ttk.Label(row1, textvariable=self.right_hotkey_var, width=8, anchor=tk.CENTER,
                  relief=tk.SUNKEN).pack(side=tk.LEFT, padx=(4, 0))
        ttk.Button(row1, text="热键", width=6,
                   command=self._start_set_right_hotkey).pack(side=tk.LEFT)
        ttk.Label(row1, text="默认间隔").pack(side=tk.LEFT, padx=(12, 3))
        self.default_interval_var = tk.StringVar(value="1")
        ttk.Entry(row1, textvariable=self.default_interval_var, width=6).pack(side=tk.LEFT)
        ttk.Label(row1, text="秒").pack(side=tk.LEFT, padx=2)

        row2 = ttk.Frame(setting_bar)
        row2.pack(fill=tk.X, padx=8, pady=(2, 5))
        self.jitter_on_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(row2, text="随机化", variable=self.jitter_on_var,
                        command=self._on_change).pack(side=tk.LEFT)
        ttk.Label(row2, text="×").pack(side=tk.LEFT, padx=(6, 2))
        self.jitter_min_var = tk.StringVar(value=str(DEFAULT_JITTER_MIN))
        ttk.Entry(row2, textvariable=self.jitter_min_var, width=5).pack(side=tk.LEFT)
        ttk.Label(row2, text="~").pack(side=tk.LEFT, padx=2)
        self.jitter_max_var = tk.StringVar(value=str(DEFAULT_JITTER_MAX))
        ttk.Entry(row2, textvariable=self.jitter_max_var, width=5).pack(side=tk.LEFT)
        ttk.Label(row2, text="倍").pack(side=tk.LEFT, padx=(2, 14))
        ttk.Label(row2, text="轮次间隔").pack(side=tk.LEFT)
        self.cycle_var = tk.StringVar(value="0")
        ttk.Entry(row2, textvariable=self.cycle_var, width=6).pack(side=tk.LEFT, padx=4)
        ttk.Label(row2, text="秒（每轮之间等待）").pack(side=tk.LEFT, padx=2)
        for var in (self.jitter_min_var, self.jitter_max_var, self.cycle_var):
            var.trace_add("write", lambda *_: self._on_change())

        # 位置列表
        list_bar = ttk.LabelFrame(self.root, text="执行列表")
        list_bar.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
        columns = ("index", "type", "name", "detail", "interval")
        self.tree = ttk.Treeview(list_bar, columns=columns, show="headings", height=8)
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
            ttk.Button(action_bar, text=text, command=command).pack(side=tk.LEFT, padx=2)

        # Boss 卡计数模式：与自由循环共存，OCR 不可用时不会影响自由模式
        count_frame = ttk.LabelFrame(self.root, text="Boss 卡计数模式（可选）")
        count_frame.pack(fill=tk.X, padx=8, pady=(6, 4))

        count_top = ttk.Frame(count_frame)
        count_top.pack(fill=tk.X, padx=8, pady=(5, 2))
        ttk.Label(count_top, text="模式").pack(side=tk.LEFT)
        self.execution_mode_var = tk.StringVar(value="自由循环")
        self.execution_mode_box = ttk.Combobox(
            count_top, textvariable=self.execution_mode_var, state="readonly",
            values=("自由循环", "Boss 卡计数"), width=12)
        self.execution_mode_box.pack(side=tk.LEFT, padx=4)
        self.execution_mode_box.bind("<<ComboboxSelected>>", lambda _event: self._on_change())
        ttk.Label(count_top, text="目标次数").pack(side=tk.LEFT, padx=(10, 2))
        self.count_target_var = tk.StringVar(value=str(DEFAULT_COUNT_TARGET))
        ttk.Entry(count_top, textvariable=self.count_target_var, width=7).pack(side=tk.LEFT)
        ttk.Label(count_top, text="唤出键").pack(side=tk.LEFT, padx=(10, 2))
        self.count_open_key_var = tk.StringVar(value=key_display(DEFAULT_COUNT_OPEN_KEY))
        self.count_open_key_holder = {"name": DEFAULT_COUNT_OPEN_KEY}
        ttk.Entry(count_top, textvariable=self.count_open_key_var, width=7,
                  state="readonly").pack(side=tk.LEFT)
        ttk.Button(count_top, text="采集", width=6,
                   command=lambda: self._start_key_capture(
                       ("count_open_key", self.count_open_key_var, self.count_open_key_holder),
                       "请按下用于唤出召唤界面的按键…")).pack(side=tk.LEFT, padx=3)

        count_points = ttk.Frame(count_frame)
        count_points.pack(fill=tk.X, padx=8, pady=2)
        ttk.Label(count_points, text="召唤按钮 X/Y").pack(side=tk.LEFT)
        self.count_summon_x_var = tk.StringVar(value="0")
        self.count_summon_y_var = tk.StringVar(value="0")
        ttk.Entry(count_points, textvariable=self.count_summon_x_var, width=8).pack(side=tk.LEFT, padx=3)
        ttk.Entry(count_points, textvariable=self.count_summon_y_var, width=8).pack(side=tk.LEFT)
        ttk.Button(count_points, text="采集召唤按钮", width=12,
                   command=self._capture_count_summon).pack(side=tk.LEFT, padx=5)
        ttk.Label(count_points, text="Boss 卡坐标 X/Y").pack(side=tk.LEFT, padx=(10, 2))
        self.count_boss_card_x_var = tk.StringVar(value="0")
        self.count_boss_card_y_var = tk.StringVar(value="0")
        ttk.Entry(count_points, textvariable=self.count_boss_card_x_var, width=8).pack(side=tk.LEFT, padx=3)
        ttk.Entry(count_points, textvariable=self.count_boss_card_y_var, width=8).pack(side=tk.LEFT)
        ttk.Button(count_points, text="采集 Boss 卡", width=12,
                   command=self._capture_count_boss_card).pack(side=tk.LEFT, padx=5)

        count_ocr = ttk.Frame(count_frame)
        count_ocr.pack(fill=tk.X, padx=8, pady=2)
        ttk.Label(count_ocr, text="数量区域 X,Y,W,H").pack(side=tk.LEFT)
        self.count_region_var = tk.StringVar(value="0,0,120,36")
        ttk.Entry(count_ocr, textvariable=self.count_region_var, width=18).pack(side=tk.LEFT, padx=3)
        ttk.Button(count_ocr, text="采集数量区域", width=12,
                   command=self._capture_count_region).pack(side=tk.LEFT, padx=3)
        ttk.Label(count_ocr, text="测试读取").pack(side=tk.LEFT, padx=(8, 2))
        ttk.Button(count_ocr, text="读取一次", width=9,
                   command=self._test_count_ocr).pack(side=tk.LEFT)
        ttk.Button(count_ocr, text="重置进度", width=9,
                   command=self._reset_count_progress).pack(side=tk.LEFT, padx=3)

        count_options = ttk.Frame(count_frame)
        count_options.pack(fill=tk.X, padx=8, pady=(2, 5))
        self.count_auto_next_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(count_options, text="达到目标自动停止（连续循环）",
                        variable=self.count_auto_next_var,
                        command=self._on_change).pack(side=tk.LEFT)
        ttk.Label(count_options, text="打开等待").pack(side=tk.LEFT, padx=(10, 2))
        self.count_open_wait_var = tk.StringVar(value=f"{DEFAULT_COUNT_OPEN_WAIT:g}")
        ttk.Entry(count_options, textvariable=self.count_open_wait_var, width=6).pack(side=tk.LEFT)
        ttk.Label(count_options, text="召唤后等待").pack(side=tk.LEFT, padx=3)
        self.count_post_click_wait_var = tk.StringVar(value=f"{DEFAULT_COUNT_POST_CLICK_WAIT:g}")
        ttk.Entry(count_options, textvariable=self.count_post_click_wait_var, width=6).pack(side=tk.LEFT)
        ttk.Label(count_options, text="秒；下一轮").pack(side=tk.LEFT, padx=3)
        self.count_next_cycle_wait_var = tk.StringVar(value=f"{DEFAULT_COUNT_NEXT_CYCLE_WAIT:g}")
        ttk.Entry(count_options, textvariable=self.count_next_cycle_wait_var, width=6).pack(side=tk.LEFT)
        ttk.Label(count_options, text="秒").pack(side=tk.LEFT, padx=2)
        self.count_progress_var = tk.StringVar(value="进度 0 / 10")
        ttk.Label(count_options, textvariable=self.count_progress_var,
                  foreground="#245").pack(side=tk.RIGHT, padx=8)
        self.count_ocr_status_var = tk.StringVar(value="OCR：未测试")
        ttk.Label(count_options, textvariable=self.count_ocr_status_var,
                  foreground="#666").pack(side=tk.RIGHT, padx=8)

        # 执行控制
        control_bar = ttk.Frame(self.root)
        control_bar.pack(fill=tk.X, padx=8, pady=(6, 2))
        self.btn_start = ttk.Button(control_bar, text="▶ 开始", width=10, command=self._start_clicking)
        self.btn_start.pack(side=tk.LEFT, padx=3)
        self.btn_stop = ttk.Button(control_bar, text="⏹ 停止", width=10,
                                   command=self._stop_clicking, state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT, padx=3)
        self.btn_right = ttk.Button(control_bar, text="按住键", width=10, command=self._toggle_right_hold)
        self.btn_right.pack(side=tk.LEFT, padx=3)
        ttk.Button(control_bar, text="清空列表", width=10, command=self._clear_items).pack(side=tk.LEFT, padx=3)

        option_bar = ttk.Frame(self.root)
        option_bar.pack(fill=tk.X, padx=8, pady=(4, 0))
        self.auto_right_hold_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(option_bar, text="运行开始时同步按住键（停止时自动松开）",
                        variable=self.auto_right_hold_var,
                        command=self._on_change).pack(side=tk.LEFT)

        # 状态栏
        self.status_var = tk.StringVar(value="已停止")
        ttk.Label(self.root, textvariable=self.status_var, anchor=tk.W,
                  relief=tk.SUNKEN).pack(fill=tk.X, padx=8, pady=(6, 2))

        # 底部提示
        foot = ttk.Frame(self.root)
        foot.pack(fill=tk.X, padx=8, pady=(0, 8))
        if os.path.abspath(os.path.dirname(CONFIG_PATH)) == os.path.abspath(APP_DIR):
            data_text = "数据文件：" + CONFIG_NAME
        else:
            data_text = "数据文件：" + CONFIG_PATH
        ttk.Label(foot, text=data_text, foreground="#666").pack(side=tk.LEFT)
        if not is_admin():
            ttk.Button(foot, text="以管理员身份重启", command=self._restart_as_admin).pack(side=tk.RIGHT)
        if not HAS_KEYBOARD:
            ttk.Label(foot, text="未安装 keyboard 库，键盘功能不可用",
                      foreground="#c00").pack(side=tk.RIGHT, padx=8)

    # ── 方案管理 ────────────────────────────────────────────────────────────
    def _collect_profile(self):
        execution_mode = "count" if self.execution_mode_var.get() == "Boss 卡计数" else "free"
        try:
            count_target = int(float(self.count_target_var.get()))
        except (TypeError, ValueError):
            count_target = DEFAULT_COUNT_TARGET
        count_open_key = self.count_open_key_holder.get("name") or DEFAULT_COUNT_OPEN_KEY
        return {
            "hotkey": self.hotkey,
            "right_hotkey": self.right_hotkey,
            "hold_key": self.hold_key,
            "auto_right_hold": bool(self.auto_right_hold_var.get()),
            "cycle_interval": self._cycle_value(),
            "jitter_enabled": bool(self.jitter_on_var.get()),
            "jitter_min": self._safe_float(self.jitter_min_var.get(), DEFAULT_JITTER_MIN),
            "jitter_max": self._safe_float(self.jitter_max_var.get(), DEFAULT_JITTER_MAX),
            "execution_mode": execution_mode,
            "count_target": max(1, min(999999, count_target)),
            "count_open_key": count_open_key,
            "count_boss_card_point": {
                "x": int(self._safe_float(self.count_boss_card_x_var.get(), 0)),
                "y": int(self._safe_float(self.count_boss_card_y_var.get(), 0)),
            },
            "count_summon_point": {
                "x": int(self._safe_float(self.count_summon_x_var.get(), 0)),
                "y": int(self._safe_float(self.count_summon_y_var.get(), 0)),
            },
            "count_star_points": {key: dict(value) for key, value in self.count_star_points.items()},
            "count_ocr_region": list(self._current_count_region()),
            "count_ocr_regions": {key: list(value) for key, value in self.count_ocr_regions.items()},
            "count_open_wait": self.count_open_wait,
            "count_post_click_wait": self._safe_float(self.count_post_click_wait_var.get(), DEFAULT_COUNT_POST_CLICK_WAIT),
            "count_next_cycle_wait": self._safe_float(self.count_next_cycle_wait_var.get(), DEFAULT_COUNT_NEXT_CYCLE_WAIT),
            "count_auto_next": bool(self.count_auto_next_var.get()),
            "count_progress": max(0, int(self.count_progress)),
            "items": [dict(item) for item in self.items],
        }

    def _load_profile(self, name):
        profile = normalize_profile(self.profiles.get(name))
        self.profiles[name] = profile
        self.current_profile = name
        self.items = [dict(item) for item in profile["items"]]
        self.hotkey = profile["hotkey"]
        self.hotkey_var.set(key_display(self.hotkey))
        self.right_hotkey = profile["right_hotkey"]
        self.right_hotkey_var.set(key_display(self.right_hotkey))
        self.hold_key = profile.get("hold_key", DEFAULT_HOLD_KEY)
        self.hold_key_var.set(key_display(self.hold_key))
        self.auto_right_hold_var.set(profile["auto_right_hold"])
        self.cycle_var.set(f"{profile['cycle_interval']:g}")
        self.jitter_on_var.set(profile["jitter_enabled"])
        self.jitter_min_var.set(f"{profile['jitter_min']:g}")
        self.jitter_max_var.set(f"{profile['jitter_max']:g}")
        self.execution_mode_var.set("Boss 卡计数" if profile["execution_mode"] == "count" else "自由循环")
        self.count_target = profile["count_target"]
        self.count_target_var.set(str(self.count_target))
        self.count_open_key = profile["count_open_key"]
        self.count_open_key_holder["name"] = self.count_open_key
        self.count_open_key_var.set(key_display(self.count_open_key))
        self.count_boss_card_point = dict(profile["count_boss_card_point"])
        self.count_boss_card_x_var.set(str(self.count_boss_card_point["x"]))
        self.count_boss_card_y_var.set(str(self.count_boss_card_point["y"]))
        self.count_summon_point = dict(profile["count_summon_point"])
        self.count_summon_x_var.set(str(self.count_summon_point["x"]))
        self.count_summon_y_var.set(str(self.count_summon_point["y"]))
        self.count_star_points = {key: dict(value) for key, value in profile["count_star_points"].items()}
        self.count_ocr_region = list(profile["count_ocr_region"])
        self.count_region_var.set(",".join(str(item) for item in self.count_ocr_region))
        self.count_ocr_regions = {key: list(value) for key, value in profile["count_ocr_regions"].items()}
        self.count_open_wait = profile["count_open_wait"]
        self.count_open_wait_var.set(f"{self.count_open_wait:g}")
        self.count_post_click_wait = profile["count_post_click_wait"]
        self.count_next_cycle_wait = profile["count_next_cycle_wait"]
        self.count_auto_next = profile["count_auto_next"]
        self.count_progress = profile["count_progress"]
        self.count_post_click_wait_var.set(f"{self.count_post_click_wait:g}")
        self.count_next_cycle_wait_var.set(f"{self.count_next_cycle_wait:g}")
        self.count_auto_next_var.set(self.count_auto_next)
        self.count_progress_var.set(f"进度 {self.count_progress} / {self.count_target}")
        self.count_ocr_status_var.set("OCR：未测试")
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
        source["items"] = [dict(item) for item in source["items"]]
        self.profiles[name] = source
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
        self.cycle_interval = self._cycle_value()

    def _cycle_value(self):
        """轮次间隔秒数，0 表示不等，填错按 0 处理。"""
        try:
            value = parse_interval(str(self.cycle_var.get()).strip())
        except ValueError:
            return 0.0
        return max(0.0, min(MAX_INTERVAL, value))

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
    def _resolve_positions(self, items=None):
        """把相对偏移换算成实际坐标，返回与列表等长的数组（按键项为 None）。

        鼠标项是 (x, y, 是否有参照点)。相对模式下若前面没有鼠标点，就退回按
        绝对坐标处理，并在列表里标出来。
        """
        items = self.items if items is None else items
        resolved = []
        last = None
        for item in items:
            if item.get("type") != "mouse":
                resolved.append(None)
                continue
            has_ref = True
            if item.get("mode") == "rel":
                if last is None:
                    has_ref = False
                    point = (int(item.get("x", 0)), int(item.get("y", 0)))
                else:
                    point = (last[0] + int(item.get("x", 0)), last[1] + int(item.get("y", 0)))
            else:
                point = (int(item.get("x", 0)), int(item.get("y", 0)))
            last = point
            resolved.append((point[0], point[1], has_ref))
        return resolved

    def _describe(self, item, point=None):
        if item.get("type") == "key":
            return f"按键 {key_display(item.get('key', ''))}"
        if point is None:
            point = (item.get("x", 0), item.get("y", 0))
        return f"点击 ({point[0]}, {point[1]})"

    def _refresh_list(self):
        points = self._resolve_positions()
        self.tree.delete(*self.tree.get_children())
        for position, item in enumerate(self.items, 1):
            kind = "键盘" if item.get("type") == "key" else "鼠标"
            point = points[position - 1]
            if item.get("type") != "mouse":
                detail = self._describe(item)
            elif item.get("mode") == "rel":
                offset = f"{int(item.get('x', 0)):+d},{int(item.get('y', 0)):+d}"
                detail = (f"偏移 {offset}｜前面没有参照点" if not point[2]
                          else f"偏移 {offset} → ({point[0]}, {point[1]})")
            else:
                detail = f"({point[0]}, {point[1]})"
            self.tree.insert("", tk.END, iid=str(position - 1),
                             values=(position, kind, item.get("name", ""),
                                     detail,
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
            current = {"type": "mouse", "name": "", "mode": "abs",
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

        mode_var = tk.StringVar(value=current.get("mode", "abs"))
        mode_row = ttk.Frame(mouse_frame)
        mode_row.pack(anchor=tk.W)
        ttk.Label(mode_row, text="位置").pack(side=tk.LEFT)
        ttk.Radiobutton(mode_row, text="绝对坐标", value="abs",
                        variable=mode_var).pack(side=tk.LEFT, padx=6)
        ttk.Radiobutton(mode_row, text="相对上一个鼠标点", value="rel",
                        variable=mode_var).pack(side=tk.LEFT)

        coord_row = ttk.Frame(mouse_frame)
        coord_row.pack(anchor=tk.W, pady=(4, 0))
        x_label = ttk.Label(coord_row, text="X")
        x_label.pack(side=tk.LEFT)
        ttk.Entry(coord_row, textvariable=x_var, width=9).pack(side=tk.LEFT, padx=4)
        y_label = ttk.Label(coord_row, text="Y")
        y_label.pack(side=tk.LEFT)
        ttk.Entry(coord_row, textvariable=y_var, width=9).pack(side=tk.LEFT, padx=4)
        mode_button = ttk.Button(coord_row, text="取当前鼠标位置", width=16,
                                 command=lambda: self._fill_cursor(x_var, y_var))
        mode_button.pack(side=tk.LEFT, padx=8)

        mode_hint = tk.StringVar()
        ttk.Label(mouse_frame, textvariable=mode_hint, foreground="#666").pack(anchor=tk.W)

        def sync_mode(*_):
            relative = mode_var.get() == "rel"
            x_label.config(text="偏移 X" if relative else "X")
            y_label.config(text="偏移 Y" if relative else "Y")
            mode_button.config(state=tk.DISABLED if relative else tk.NORMAL)
            mode_hint.set(f"相对列表里上一个鼠标点击，填偏移像素，范围 ±{MAX_OFFSET}"
                          if relative else "屏幕绝对坐标")
        mode_var.trace_add("write", sync_mode)
        sync_mode()

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
                if mode_var.get() == "rel" and max(abs(x_value), abs(y_value)) > MAX_OFFSET:
                    error_var.set(f"偏移量请控制在 ±{MAX_OFFSET} 像素以内。")
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
                item["mode"] = mode_var.get()
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

    def _capture_count_summon(self):
        def done(x_value, y_value):
            self.count_summon_x_var.set(str(x_value))
            self.count_summon_y_var.set(str(y_value))
            self._on_change()
            self.status_var.set(f"已采集召唤按钮 ({x_value}, {y_value})")

        self._countdown_window("请把鼠标移到 Boss 召唤按钮中心，倒计时结束后自动记录", done)

    def _capture_count_boss_card(self):
        def done(x_value, y_value):
            self.count_boss_card_x_var.set(str(x_value))
            self.count_boss_card_y_var.set(str(y_value))
            self.count_boss_card_point = {"x": int(x_value), "y": int(y_value)}
            self._on_change()
            self.status_var.set(f"已采集 Boss 卡坐标 ({x_value}, {y_value})")

        self._countdown_window("请把鼠标移到 Boss 卡位置，倒计时结束后自动记录", done)

    def _capture_count_region(self):
        def done(x_value, y_value):
            width, height = 120, 36
            region = [max(0, int(x_value - width // 2)), max(0, int(y_value - height // 2)), width, height]
            self.count_region_var.set(",".join(str(item) for item in region))
            self.count_ocr_region = region
            self._on_change()
            self.status_var.set(f"已采集 Boss 卡数量区域 {','.join(str(item) for item in region)}")

        self._countdown_window("请把鼠标移到 Boss 卡数量数字右下角，倒计时结束后自动记录", done)

    def _current_count_region(self):
        region = parse_region(self.count_region_var.get(), self.count_ocr_region)
        self.count_ocr_region = list(region)
        return region

    def _test_count_ocr(self):
        region = self._current_count_region()
        if not ocr_available():
            missing = []
            if not HAS_PIL_OCR:
                missing.append("Pillow")
            if not HAS_PYTesseract_OCR:
                missing.append("pytesseract")
            if not resolve_tesseract():
                missing.append("Tesseract")
            elif not resolve_tessdata(resolve_tesseract()):
                missing.append("Tesseract 语言包")
            self.count_ocr_status_var.set("OCR：" + ("、".join(missing) + " 缺失" if missing else "不可用"))
            messagebox.showwarning(
                APP_NAME,
                "OCR 当前不可用，自由模式不受影响。\n缺失组件：" + "、".join(missing or ["未知"]),
                parent=self.root)
            return
        value = read_count_once(region)
        if value is None:
            self.count_ocr_status_var.set("OCR：读取失败")
            self.status_var.set("数量识别失败，请检查区域、分辨率和 Tesseract 语言包")
        else:
            self.count_ocr_status_var.set(f"OCR：{value}")
            self.status_var.set(f"数量识别成功：{value}")

    def _reset_count_progress(self):
        self.count_progress = 0
        self.count_progress_var.set("进度 0 / " + str(self.count_target))
        self._on_change()
        self.status_var.set("Boss 卡计数进度已重置")

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
                "mode": "abs",
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

    def _start_set_hold_key(self):
        self._start_key_capture("hold_key", "请按下要按住的键（如 space、a、right 等）…")

    def _start_set_right_hotkey(self):
        self._start_key_capture("right_hotkey", "请按下要作为「按住右键」热键的按键…")

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
            name = self._key_read_worker_loop()
        finally:
            # 无论采集成功、超时还是异常，都必须复位，保证热键轮询立即恢复
            self.capturing = False
            self.ui_queue.put(("key", name, getattr(self, "_key_target", None)))

    def _key_read_worker_loop(self):
        name = None
        deadline = time.time() + 15
        while self.capturing and time.time() < deadline:
            for vk in range(1, 256):
                if user32.GetAsyncKeyState(vk) & 0x8000:
                    name = vk_to_name(vk)
                    if name:
                        while self.capturing and (user32.GetAsyncKeyState(vk) & 0x8000):
                            time.sleep(0.02)
                        break
            if name:
                break
            time.sleep(0.02)
        return name

    def _handle_key_captured(self, name, target):
        self.capturing = False
        self._register_hotkey()
        if not name:
            self.status_var.set("按键采集超时，请重新点击设置")
            return
        if target == "hotkey":
            hotkey = normalize_key_name(name) or DEFAULT_HOTKEY
            if hotkey == self.right_hotkey:
                self.status_var.set(f"{key_display(hotkey)} 已用于按住右键，请换一个键")
                return
            self.hotkey = hotkey
            self.hotkey_var.set(key_display(self.hotkey))
            self._register_hotkey()
            self._on_change()
            self.status_var.set(f"启停热键已设为 {key_display(self.hotkey)}")
        elif target == "hold_key":
            hold_key = normalize_key_name(name) or name
            if hold_key == self.hotkey:
                self.status_var.set(f"{key_display(hold_key)} 已用于启停，请换一个键")
                return
            self.hold_key = hold_key
            self.hold_key_var.set(key_display(self.hold_key))
            self._on_change()
            self.status_var.set(f"按住键已设为 {key_display(self.hold_key)}")
        elif isinstance(target, tuple) and target and target[0] == "count_open_key":
            count_open_key = normalize_key_name(name) or name
            if count_open_key == self.hotkey:
                self.status_var.set(f"{key_display(count_open_key)} 已用于启停，请换一个键")
                return
            self.count_open_key = count_open_key
            self.count_open_key_holder["name"] = count_open_key
            target[1].set(key_display(count_open_key))
            self._on_change()
            self.status_var.set(f"召唤唤出键已设为 {key_display(count_open_key)}")
        elif target == "right_hotkey":
            right_hotkey = normalize_key_name(name) or DEFAULT_RIGHT_HOTKEY
            if right_hotkey == self.hotkey:
                self.status_var.set(f"{key_display(right_hotkey)} 已用于启停，请换一个键")
                return
            self.right_hotkey = right_hotkey
            self.right_hotkey_var.set(key_display(self.right_hotkey))
            self._register_hotkey()
            self._on_change()
            self.status_var.set(f"按住键热键已设为 {key_display(self.right_hotkey)}")
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
        self._restart_win_hotkey_worker()
        if not HAS_KEYBOARD:
            return
        if self.hotkey:
            try:
                self.hotkey_handle = keyboard.add_hotkey(self.hotkey, self._on_hotkey, suppress=False)
            except Exception as exc:
                self.hotkey_handle = None
                self.status_var.set(f"热键 {key_display(self.hotkey)} 注册失败：{exc}")
        # 按住右键的独立热键；与启停热键相同时跳过，避免同一个键被注册两次
        if self.right_hotkey and self.right_hotkey != self.hotkey:
            try:
                self.right_hotkey_handle = keyboard.add_hotkey(self.right_hotkey,
                                                               self._on_right_hotkey, suppress=False)
            except Exception as exc:
                self.right_hotkey_handle = None
                self.status_var.set(f"热键 {key_display(self.right_hotkey)} 注册失败：{exc}")


    def _unregister_hotkey(self):
        if keyboard is not None:
            for handle in (self.hotkey_handle, self.right_hotkey_handle):
                if handle is not None:
                    try:
                        keyboard.remove_hotkey(handle)
                    except Exception:
                        pass
        self.hotkey_handle = None
        self.right_hotkey_handle = None

    def _restart_win_hotkey_worker(self):
        """重启系统级 RegisterHotKey 后备线程，保证修改热键后立即生效。"""
        self._win_hotkey_stop.set()
        worker = self._win_hotkey_thread
        if worker and worker.is_alive():
            worker.join(timeout=0.3)
        self._win_hotkey_stop = threading.Event()
        self._win_hotkey_thread = threading.Thread(target=self._win_hotkey_worker, daemon=True)
        self._win_hotkey_thread.start()

    def _win_hotkey_worker(self):
        """使用 Windows RegisterHotKey 提供最后一层全局热键后备。"""
        create = user32.CreateWindowExW
        create.argtypes = [
            ctypes.wintypes.DWORD, ctypes.wintypes.LPCWSTR, ctypes.wintypes.LPCWSTR,
            ctypes.wintypes.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            ctypes.wintypes.HWND, ctypes.wintypes.HMENU, ctypes.wintypes.HINSTANCE,
            ctypes.c_void_p,
        ]
        create.restype = ctypes.wintypes.HWND
        hwnd = create(0, "STATIC", "AutoClickerHotkeys", 0, 0, 0, 0, 0, 0, 0, 0, None)
        if not hwnd:
            return
        peek = user32.PeekMessageW
        peek.argtypes = [ctypes.POINTER(MSG), ctypes.wintypes.HWND, ctypes.wintypes.UINT,
                         ctypes.wintypes.UINT, ctypes.wintypes.UINT]
        peek.restype = ctypes.wintypes.BOOL
        register = user32.RegisterHotKey
        register.argtypes = [ctypes.wintypes.HWND, ctypes.c_int, ctypes.wintypes.UINT, ctypes.wintypes.UINT]
        register.restype = ctypes.wintypes.BOOL
        unregister = user32.UnregisterHotKey
        unregister.argtypes = [ctypes.wintypes.HWND, ctypes.c_int]
        unregister.restype = ctypes.wintypes.BOOL
        destroy = user32.DestroyWindow
        destroy.argtypes = [ctypes.wintypes.HWND]
        destroy.restype = ctypes.wintypes.BOOL
        registered = {}
        try:
            for identifier, target in ((1001, "hotkey"), (1002, "right_hotkey")):
                vk = key_name_to_vk(getattr(self, target, ""))
                if vk and register(hwnd, identifier, 0, vk):
                    registered[identifier] = target
            message = MSG()
            while not self._win_hotkey_stop.is_set():
                if peek(ctypes.byref(message), hwnd, WM_HOTKEY, WM_HOTKEY, PM_REMOVE):
                    target = registered.get(int(message.wParam))
                    if target == "hotkey":
                        self._on_hotkey()
                    elif target == "right_hotkey":
                        self._on_right_hotkey()
                else:
                    time.sleep(0.02)
        finally:
            for identifier in registered:
                unregister(hwnd, identifier)
            destroy(hwnd)

    def _on_hotkey(self):
        now = time.time()
        if now - self._last_hotkey_trigger < 0.2:
            return
        self._last_hotkey_trigger = now
        self.ui_queue.put(("toggle", None))

    def _on_right_hotkey(self):
        now = time.time()
        if now - self._last_hotkey_trigger < 0.2:
            return
        self._last_hotkey_trigger = now
        self.ui_queue.put(("right_toggle", None))

    def _hotkey_poll_loop(self):
        """轮询全局键盘状态，键盘库钩子失效时仍能启停。"""
        while not self._hotkey_poll_stop.is_set():
            if not self.capturing:
                for target in ("hotkey", "right_hotkey"):
                    name = getattr(self, target, "")
                    pressed = key_is_pressed(name) if name else False
                    previous = self._hotkey_poll_state.get(target, False)
                    self._hotkey_poll_state[target] = pressed
                    if pressed and not previous:
                        if target == "hotkey":
                            self._on_hotkey()
                        else:
                            self._on_right_hotkey()
            time.sleep(0.02)

    # ── 主线程消息泵 ────────────────────────────────────────────────────────
    def _log_error(self, message):
        """把异常写入 debug.log 并显示在状态栏，保证冻结 exe 里错误可见。"""
        try:
            with open(os.path.join(APP_DIR, "debug.log"), "a", encoding="utf-8") as fh:
                fh.write("[%s] %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), message))
                fh.write(traceback.format_exc() + "\n")
        except Exception:
            pass
        try:
            self.status_var.set("出错：%s（详见 debug.log）" % message)
        except Exception:
            pass

    def _pump_queue(self):
        try:
            while True:
                self._handle_message(self.ui_queue.get_nowait())
        except queue.Empty:
            pass
        except Exception:
            self._log_error("界面消息处理出错")
        self.root.after(60, self._pump_queue)

    def _handle_message(self, message):
        kind = message[0]
        if kind == "toggle":
            if self.running:
                self._stop_clicking()
            else:
                self._start_clicking()
        elif kind == "right_toggle":
            self._toggle_right_hold()
        elif kind == "status":
            self.status_var.set(message[1])
        elif kind == "stopped":
            self.running = False
            self.btn_start.config(state=tk.NORMAL)
            self.btn_stop.config(state=tk.DISABLED)
            if self.right_held and self.right_held_auto:
                self._release_right()
            self.status_var.set("已停止")
        elif kind == "count_progress":
            self.count_progress = max(0, int(message[1]))
            self.count_progress_var.set(f"进度 {self.count_progress} / {self.count_target}")
            self._save_now()
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
        try:
            self._start_clicking_impl()
        except Exception:
            self._log_error("启动失败")

    def _start_clicking_impl(self):
        self._sync_count_values()
        if self.execution_mode_var.get() == "Boss 卡计数":
            if not ocr_available():
                messagebox.showwarning(
                    APP_NAME,
                    "Boss 卡计数模式需要 Pillow、pytesseract 和 Tesseract。\n"
                    "当前 OCR 不可用；自由循环模式仍可使用。",
                    parent=self.root)
                return
            if not HAS_KEYBOARD:
                messagebox.showwarning(APP_NAME, "Boss 卡计数模式需要 keyboard 库来按唤出键。", parent=self.root)
                return
            summon = self.count_summon_point
            boss_card = self.count_boss_card_point
            region = parse_region(self.count_ocr_region, DEFAULT_COUNT_REGION)
            if summon.get("x", 0) == 0 and summon.get("y", 0) == 0:
                messagebox.showwarning(APP_NAME, "请先采集召唤按钮坐标。", parent=self.root)
                return
            if boss_card.get("x", 0) == 0 and boss_card.get("y", 0) == 0:
                messagebox.showwarning(APP_NAME, "请先采集 Boss 卡坐标。", parent=self.root)
                return
            if region[2] < 20 or region[3] < 8:
                messagebox.showwarning(APP_NAME, "OCR 数量区域至少需要 20x8 像素，请重新采集。", parent=self.root)
                return
            if self.count_target <= 0:
                messagebox.showwarning(APP_NAME, "目标次数必须大于 0。", parent=self.root)
                return
        elif not self.items:
            messagebox.showwarning(APP_NAME, "列表为空，请先采集或手动添加。", parent=self.root)
            return
        self.running = True
        self.btn_start.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        if self.auto_right_hold_var.get():
            self._press_right(auto=True)
        target = self._count_loop if self.execution_mode_var.get() == "Boss 卡计数" else self._click_loop
        self.click_thread = threading.Thread(target=target, daemon=True)
        self.click_thread.start()

    def _stop_clicking(self):
        if not self.running:
            return
        try:
            self._stop_clicking_impl()
        except Exception:
            self._log_error("停止失败")

    def _stop_clicking_impl(self):
        self.running = False
        self.btn_start.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.DISABLED)
        if self.right_held and self.right_held_auto:
            self._release_right()
        self.status_var.set("已停止")

    def _click_loop(self):
        """循环执行的入口：不管中间出什么意外，都要复位状态并通知界面。"""
        try:
            self._click_rounds()
        except Exception as exc:
            self._set_status(f"执行出错：{exc}")
        finally:
            self.running = False
            self.ui_queue.put(("stopped", None))

    def _count_loop(self):
        """Boss 卡计数模式入口：OCR 不稳定或数量异常时立即停止。"""
        try:
            self._run_count_mode()
        except CountSafetyError as exc:
            self._set_status(f"计数已停止：{exc}")
        except Exception as exc:
            self._set_status(f"计数执行出错：{exc}")
        finally:
            self.running = False
            self.ui_queue.put(("stopped", None))

    def _sync_count_values(self):
        """把界面上的计数参数写入运行时变量，避免启动线程后读取到旧值。"""
        try:
            self.count_target = max(1, min(999999, int(float(self.count_target_var.get()))))
        except (TypeError, ValueError):
            self.count_target = DEFAULT_COUNT_TARGET
            self.count_target_var.set(str(self.count_target))
        self.count_open_key = self.count_open_key_holder.get("name") or DEFAULT_COUNT_OPEN_KEY
        self.count_boss_card_point = {
            "x": int(self._safe_float(self.count_boss_card_x_var.get(), 0)),
            "y": int(self._safe_float(self.count_boss_card_y_var.get(), 0)),
        }
        self.count_summon_point = {
            "x": int(self._safe_float(self.count_summon_x_var.get(), 0)),
            "y": int(self._safe_float(self.count_summon_y_var.get(), 0)),
        }
        self.count_ocr_region = list(self._current_count_region())
        open_wait_var = getattr(self, "count_open_wait_var", None)
        open_wait_value = getattr(self, "count_open_wait", DEFAULT_COUNT_OPEN_WAIT)
        if open_wait_var is not None:
            open_wait_value = self._safe_float(open_wait_var.get(), DEFAULT_COUNT_OPEN_WAIT)
        self.count_open_wait = max(1.5, min(MAX_INTERVAL, open_wait_value))
        self.count_post_click_wait = max(
            MIN_INTERVAL, min(MAX_INTERVAL, self._safe_float(self.count_post_click_wait_var.get(), DEFAULT_COUNT_POST_CLICK_WAIT)))
        self.count_next_cycle_wait = max(
            MIN_INTERVAL, min(MAX_INTERVAL, self._safe_float(self.count_next_cycle_wait_var.get(), DEFAULT_COUNT_NEXT_CYCLE_WAIT)))
        self.count_auto_next = bool(self.count_auto_next_var.get())
        self.count_progress_var.set(f"进度 {self.count_progress} / {self.count_target}")

    def _run_count_mode(self):
        """安全计数状态机：稳定 OCR → 点击 → 等待变化 → 确认一次消耗。"""
        summon = self.count_summon_point
        boss_card = self.count_boss_card_point
        region = parse_region(self.count_ocr_region, DEFAULT_COUNT_REGION)
        guard = CountGuard(self.count_target, self.count_progress)
        command = resolve_tesseract()
        tessdata_dir = resolve_tessdata(command)
        while self.running and not guard.reached:
            self._set_status(f"计数模式：等待召唤界面（进度 {guard.progress}/{guard.target}）")
            if not key_tap(self.count_open_key):
                raise CountSafetyError(f"唤出键 {key_display(self.count_open_key)} 执行失败")
            self._set_status(f"已唤出召唤界面，正在读取 Boss 卡数量……")
            before = None
            stable_count = 0
            for attempt in range(4):
                self._sleep_interruptible(self.count_open_wait if attempt == 0 else 0.5)
                before, stable_count, _raw = read_count_stable(
                    region, samples=5, delay=0.12, command=command, tessdata_dir=tessdata_dir)
                if before is not None:
                    break
                self._set_status(f"召唤界面数量区域尚未稳定，正在重试（{attempt + 1}/4）")
            if before is None:
                raise CountSafetyError(f"召唤界面数量区域无法识别（连续稳定读取 {stable_count} 次）")
            self._set_status(f"OCR 识别到当前数量：{before}")
            mouse_click_left(int(boss_card["x"]), int(boss_card["y"]), jitter=False)
            self._sleep_interruptible(random.uniform(0.12, 0.24))
            mouse_click_left(int(summon["x"]), int(summon["y"]), jitter=False)
            self._sleep_interruptible(self.count_post_click_wait)
            after = None
            stable_count = 0
            for _attempt in range(4):
                self._set_status("正在确认召唤后的数量变化……")
                after, stable_count, _raw = read_count_stable(
                    region, samples=5, delay=0.12, command=command, tessdata_dir=tessdata_dir)
                if after is not None and after < before:
                    break
                self._sleep_interruptible(0.5)
            if after is None:
                raise CountSafetyError(f"召唤后 OCR 不稳定（连续稳定读取 {stable_count} 次）")
            progress = guard.confirm(before, after)
            self.count_progress = progress
            self._set_status(f"已确认消耗 1 张：{before} → {after}，进度 {progress}/{guard.target}")
            self.ui_queue.put(("count_progress", progress))
            if guard.reached:
                self._set_status(f"计数完成：已召唤 {progress} 次，自动停止")
                break
            if not self.count_auto_next:
                self._set_status(f"已召唤 {progress} 次，连续循环已关闭，自动停止")
                break
            self._set_status(f"等待击杀 Boss 后进入下一轮（{format_seconds(self.count_next_cycle_wait)}）")
            self._sleep_interruptible(self.count_next_cycle_wait)

    def _click_rounds(self):
        while self.running:
            snapshot = [dict(item) for item in self.items]
            if not snapshot:
                break
            points = self._resolve_positions(snapshot)
            for position, item in enumerate(snapshot, 1):
                if not self.running:
                    break
                point = points[position - 1]
                self._set_status(f"第 {position}/{len(snapshot)} 项：{self._describe(item, point)}")
                if item.get("type") == "mouse":
                    mouse_click_left(point[0], point[1])
                else:
                    if not key_tap(item.get("key", "")):
                        self._set_status(f"按键 {key_display(item.get('key', ''))} 执行失败")
                if not self.running:
                    break
                delay = self._calc_delay(item.get("interval", 1.0))
                self._set_status(f"第 {position} 项完成，随机等待 {format_seconds(delay)}")
                self._sleep_interruptible(delay)
            # 一轮跑完后的轮次间隔
            if self.running and self.cycle_interval > 0:
                delay = self._calc_delay(self.cycle_interval)
                self._set_status(f"本轮结束，等待 {format_seconds(delay)}")
                self._sleep_interruptible(delay)

    def _sleep_interruptible(self, seconds):
        end = time.time() + max(0.0, seconds)
        while self.running and time.time() < end:
            time.sleep(min(0.05, max(0.0, end - time.time())))

    # ── 按住键（支持任意键 + 普通输入体验优化）────────────────────────────
    def _toggle_right_hold(self):
        if self.right_held:
            self._release_right()
        else:
            self._press_right()

    def _press_right(self, auto=False):
        if self.right_held:
            return
        self.right_held = True
        self.right_held_auto = bool(auto)
        key = self.hold_key
        # 按下键
        if key == "right":
            mouse_right_down()
        elif HAS_KEYBOARD:
            keyboard.press(key)
        self.right_thread = threading.Thread(target=self._right_hold_loop, daemon=True)
        self.right_thread.start()
        self.btn_right.config(text="松开键")
        self.status_var.set(f"已按住 {key_display(key)}（点按钮或按热键松开）")

    def _right_hold_loop(self):
        """持续按住并加入自然输入节奏：随机微松开、微抖动。"""
        key = self.hold_key
        hold_start = time.time()
        while self.right_held:
            # 每 2-5 秒做一次微松开（10-30ms），模拟手指自然颤动
            elapsed = time.time() - hold_start
            if elapsed > random.uniform(2.0, 5.0):
                if key == "right":
                    mouse_right_up()
                elif HAS_KEYBOARD:
                    keyboard.release(key)
                time.sleep(random.uniform(0.01, 0.03))
                if not self.right_held:
                    break
                if key == "right":
                    mouse_right_down()
                elif HAS_KEYBOARD:
                    keyboard.press(key)
                hold_start = time.time()
            # 随机微抖动（±1-3px），模拟手部自然颤抖
            if random.random() < 0.3:
                dx = random.randint(-3, 3)
                dy = random.randint(-3, 3)
                _send_mouse_input(MOUSEEVENTF_MOVE, dx=dx, dy=dy)
            # 自然节律间隔
            time.sleep(random.uniform(0.02, 0.06))

    def _release_right(self):
        if not self.right_held:
            return
        self.right_held = False
        self.right_held_auto = False
        key = self.hold_key
        if key == "right":
            mouse_right_up()
        elif HAS_KEYBOARD:
            keyboard.release(key)
        self.btn_right.config(text="按住键")
        self.status_var.set(f"{key_display(key)} 已松开")

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
            self._hotkey_poll_stop.set()
            self._win_hotkey_stop.set()
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
        "热键：启停 {} / 按住键 {}({}) / 运行开始时同步按住键：{}".format(
            key_display(cfg["profiles"][cfg["current_profile"]]["hotkey"]),
            key_display(cfg["profiles"][cfg["current_profile"]].get("hold_key", "right")),
            key_display(cfg["profiles"][cfg["current_profile"]]["right_hotkey"]),
            "是" if cfg["profiles"][cfg["current_profile"]]["auto_right_hold"] else "否"),
        f"管理员权限：{'是' if is_admin() else '否'}",
        f"Tcl/Tk 运行库：{TCL_RUNTIME or '使用系统自带（源码运行）'}",
        f"OCR Pillow：{'可用' if HAS_PIL_OCR else '不可用'}",
        f"OCR pytesseract：{'可用' if HAS_PYTesseract_OCR else '不可用'}",
        f"Tesseract：{resolve_tesseract() or '未找到'}",
        f"Tessdata：{resolve_tessdata(resolve_tesseract()) or '未找到'}",
        f"Boss 卡计数模式：{'可用' if ocr_available() else '不可用（不影响自由循环）'}",
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
