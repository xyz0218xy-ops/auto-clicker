# -*- coding: utf-8 -*-
"""Boss 卡计数模式的 OCR 读取与安全状态机。"""

import os
import re
import shutil
import sys
import time

try:
    from PIL import ImageGrab, ImageOps, ImageFilter
    HAS_PIL = True
except Exception:
    ImageGrab = None
    ImageOps = None
    ImageFilter = None
    HAS_PIL = False

try:
    import pytesseract
    HAS_PYTesseract = True
except Exception:
    pytesseract = None
    HAS_PYTesseract = False


DEFAULT_REGION = (0, 0, 120, 36)
MAX_COUNT_DIGITS = 9


class CountSafetyError(RuntimeError):
    """OCR 结果或数量变化不满足安全条件时抛出。"""


def parse_region(value, default=DEFAULT_REGION):
    """把配置里的区域解析为 (x, y, width, height)。"""
    if isinstance(value, dict):
        value = (value.get("x"), value.get("y"), value.get("width"), value.get("height"))
    if isinstance(value, str):
        parts = [part.strip() for part in value.replace("，", ",").split(",")]
        value = parts
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return tuple(default)
    try:
        x, y, width, height = (int(float(item)) for item in value)
    except (TypeError, ValueError):
        return tuple(default)
    return (x, y, max(1, width), max(1, height))


def resolve_tesseract():
    """返回 Tesseract 可执行文件路径，找不到时返回 None。"""
    if getattr(sys, "frozen", False):
        bundle = getattr(sys, "_MEIPASS", "")
        bundled = os.path.join(bundle, "tesseract", "tesseract.exe")
        if os.path.isfile(bundled):
            return bundled
    found = shutil.which("tesseract.exe") or shutil.which("tesseract")
    if found:
        return found
    known = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    return known if os.path.isfile(known) else None


def resolve_tessdata(command=None):
    """返回 Tesseract 训练数据目录。"""
    if getattr(sys, "frozen", False):
        bundle = getattr(sys, "_MEIPASS", "")
        bundled = os.path.join(bundle, "tesseract", "tessdata")
        if os.path.isdir(bundled):
            return bundled
    command = command or resolve_tesseract()
    if command:
        executable_dir = os.path.dirname(os.path.abspath(command))
        candidate = os.path.join(executable_dir, "tessdata")
        if os.path.isdir(candidate):
            return candidate
    configured = os.environ.get("TESSDATA_PREFIX")
    if configured and os.path.isdir(configured):
        return configured
    return None


def ocr_available():
    """返回 OCR 是否具备运行条件。"""
    command = resolve_tesseract()
    tessdata_dir = resolve_tessdata(command)
    return (
        HAS_PIL
        and HAS_PYTesseract
        and bool(command)
        and bool(tessdata_dir)
        and os.path.isfile(os.path.join(tessdata_dir, "eng.traineddata"))
    )


def capture_region(region):
    """截取指定屏幕区域，失败时返回 None。"""
    if not HAS_PIL:
        return None
    x, y, width, height = parse_region(region)
    try:
        return ImageGrab.grab(bbox=(x, y, x + width, y + height))
    except Exception:
        return None


def preprocess_for_digits(image):
    """灰度、增强对比度并放大，减少数字识别抖动。"""
    if not HAS_PIL or image is None:
        return None
    try:
        gray = ImageOps.grayscale(image)
        gray = ImageOps.autocontrast(gray)
        gray = gray.filter(ImageFilter.SHARPEN)
        width, height = gray.size
        scale = max(2, min(4, int(900 / max(1, width))))
        return gray.resize((width * scale, height * scale))
    except Exception:
        return None


def clean_digits(text):
    """只保留数字字符，过滤 OCR 输出里的符号和空格。"""
    digits = re.sub(r"\D", "", str(text or ""))
    if not digits or len(digits) > MAX_COUNT_DIGITS:
        return None
    return int(digits)


def read_count_once(region, command=None, tessdata_dir=None):
    """读取一次 Boss 卡数量，返回整数或 None。"""
    if not HAS_PYTesseract:
        return None
    command = command or resolve_tesseract()
    tessdata_dir = tessdata_dir or resolve_tessdata(command)
    if not command or not tessdata_dir or not os.path.isfile(os.path.join(tessdata_dir, "eng.traineddata")):
        return None
    try:
        pytesseract.pytesseract.tesseract_cmd = command
        image = preprocess_for_digits(capture_region(region))
        if image is None:
            return None
        config_parts = ["--psm", "7", "-c", "tessedit_char_whitelist=0123456789"]
        if tessdata_dir:
            os.environ["TESSDATA_PREFIX"] = os.path.abspath(tessdata_dir)
        text = pytesseract.image_to_string(image, config=" ".join(config_parts))
        return clean_digits(text)
    except Exception:
        return None


def read_count_stable(region, samples=3, delay=0.12, command=None, tessdata_dir=None):
    """连续读取并要求至少两次结果一致，返回 (值, 已读次数, 原始结果)。"""
    values = []
    raw_values = []
    for _ in range(max(2, int(samples))):
        value = read_count_once(region, command=command, tessdata_dir=tessdata_dir)
        raw_values.append(value)
        if value is not None:
            values.append(value)
            if len(values) >= 2 and all(item == values[0] for item in values):
                return values[0], len(values), raw_values
        time.sleep(max(0.0, delay))
    return None, len(values), raw_values


class CountGuard:
    """只允许数量确实下降 1 时确认一次消耗，防止 OCR 抖动导致重复点击。"""

    def __init__(self, target, progress=0):
        self.target = max(0, int(target))
        self.progress = max(0, int(progress))
        self.last_remaining = None

    @property
    def reached(self):
        return self.progress >= self.target

    def confirm(self, before, after):
        if before is None or after is None:
            raise CountSafetyError("OCR 没有读到稳定数量")
        before = int(before)
        after = int(after)
        if before <= 0 or after < 0:
            raise CountSafetyError("OCR 数量超出合理范围")
        if after >= before:
            raise CountSafetyError("召唤后数量没有下降，禁止重复点击")
        delta = before - after
        if delta != 1:
            raise CountSafetyError(f"数量一次下降了 {delta}，不符合单次召唤预期")
        self.progress += 1
        self.last_remaining = after
        return self.progress
