# -*- coding: utf-8 -*-
"""Boss 卡计数模式的数字识别（多层混合）与安全状态机。

识别顺序：
1. 模板匹配：OpenCV 自适应二值化 + 轮廓分割数字，与自学习模板做归一化相关匹配；
2. Windows OCR：winrt-Windows.Media.Ocr（zh-Hans-CN），浅色背景 2 倍放大；
3. RapidOCR：离线 ONNX Runtime，纯数字识别（显式选择时启用）；
4. Tesseract：仅人工诊断，不进入实时动作链路。

自学习：OCR 成功且分割出的数字个数与结果一致时，把每个数字模板保存为 PNG，
按数字 0-9 归类到 count_templates/ 目录（与配置同目录），永久保存、越用越准。
"""

import asyncio
import concurrent.futures
import hashlib
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass

try:
    from PIL import ImageGrab, ImageOps, Image
    HAS_PIL = True
except Exception:
    ImageGrab = None
    ImageOps = None
    Image = None
    HAS_PIL = False

try:
    import cv2
    import numpy as np
    HAS_CV2 = True
except Exception:
    cv2 = None
    np = None
    HAS_CV2 = False

try:
    import pytesseract
    HAS_PYTesseract = True
except Exception:
    pytesseract = None
    HAS_PYTesseract = False

try:
    from rapidocr import RapidOCR as _RapidOCR
    HAS_RAPIDOCR = True
except Exception:
    try:
        from rapidocr_onnxruntime import RapidOCR as _RapidOCR
        HAS_RAPIDOCR = True
    except Exception:
        _RapidOCR = None
        HAS_RAPIDOCR = False
RAPIDOCR_LEGACY = HAS_RAPIDOCR and _RapidOCR.__module__.startswith("rapidocr_onnxruntime")

try:
    import winrt.windows.media.ocr as _winrt_ocr
    import winrt.windows.graphics.imaging as _winrt_imaging
    import winrt.windows.storage.streams as _winrt_streams
    import winrt.windows.globalization as _winrt_globalization
    HAS_WINRT_OCR = True
except Exception:
    _winrt_ocr = None
    _winrt_imaging = None
    _winrt_streams = None
    _winrt_globalization = None
    HAS_WINRT_OCR = False


DEFAULT_REGION = (0, 0, 120, 36)
MAX_COUNT_DIGITS = 6
TEMPLATE_SIZE = (24, 36)          # 模板统一尺寸（宽、高）
TEMPLATE_MATCH_MIN = 0.60         # 模板匹配置信度阈值
MAX_TEMPLATES_PER_DIGIT = 8       # 每个数字最多保留的模板数

_LANCZOS = getattr(getattr(Image, "Resampling", Image), "LANCZOS", Image.LANCZOS)

# 模板目录（由主程序在启动时调用 set_template_dir 指定，默认放模块同目录）
_template_dir = None
_template_namespace = None
_template_cache = None
_engine_cache = {}
_engine_lock = threading.Lock()
_ocr_lock = threading.Lock()
_rapidocr_lock = threading.Lock()
_rapidocr_engine = None
_rapidocr_params = {}
_loop_local = threading.local()


class CountSafetyError(RuntimeError):
    """OCR 结果或数量变化不满足安全条件时抛出。"""


@dataclass
class VisionReading:
    """一次视觉读取的可审计结果。"""

    value: object = None
    confidence: float = 0.0
    elapsed_ms: float = 0.0
    backend: str = ""
    frame_id: int = 0
    error: str = ""


class VisionBackend:
    """实时视觉后端。

    默认实时顺序为模板、Windows OCR；显式选择 ``template_winocr_rapidocr``
    时追加 RapidOCR。Tesseract 只通过 ``read_count_debug`` 进入人工诊断。
    """

    ORDER = ("template", "winocr", "rapidocr")
    CONFIDENCE = {"template": 0.95, "winocr": 0.78, "rapidocr": 0.70}
    LABELS = {"template": "模板", "winocr": "WinOCR", "rapidocr": "RapidOCR"}

    def __init__(self, deadline_ms=850, backend="template_winocr"):
        self.deadline_ms = max(1.0, min(1000.0, float(deadline_ms or 850)))
        self.backend = str(backend or "template_winocr")
        self._frame_id = 0
        self.last_reading = VisionReading()
        self.last_consistent_reading = VisionReading()
        self.last_consistent_values = []

    def _order(self):
        if self.backend == "template_winocr":
            return ("template", "winocr")
        if self.backend == "template_winocr_rapidocr":
            return self.ORDER
        if self.backend == "winocr_template":
            return ("winocr", "template", "rapidocr")
        return self.ORDER

    def _next_frame_id(self):
        self._frame_id += 1
        return self._frame_id

    def read_image(self, image, deadline_ms=None):
        """对已截取图像读取一次，供实时路径和离线基准共用。"""
        started = time.perf_counter()
        frame_id = self._next_frame_id()
        limit = self.deadline_ms if deadline_ms is None else max(1.0, float(deadline_ms))
        result = VisionReading(frame_id=frame_id)
        if image is None:
            result.error = "图像为空"
            result.elapsed_ms = (time.perf_counter() - started) * 1000
            self.last_reading = result
            return result
        readers = {
            "template": lambda: read_templates(image)[0],
            "winocr": lambda: read_winocr(image),
            "rapidocr": lambda: read_rapidocr(image),
        }
        for name in self._order():
            if (time.perf_counter() - started) * 1000 >= limit:
                result.error = "超过视觉截止时间"
                break
            try:
                value = readers[name]()
            except Exception as exc:
                value = None
                result.error = "%s: %s" % (name, exc)
            if value is not None:
                result.value = int(value)
                result.confidence = self.CONFIDENCE[name]
                result.backend = self.LABELS[name]
                break
        result.elapsed_ms = (time.perf_counter() - started) * 1000
        if result.value is None and not result.error:
            result.error = "未识别"
        self.last_reading = result
        return result

    def read(self, region, deadline_ms=None):
        """截屏并读取一次，结果包含耗时、后端和帧编号。"""
        return self.read_image(capture_region(region), deadline_ms=deadline_ms)

    def read_consistent(self, region, max_ms=850, reads=2, delay_ms=15):
        """在截止时间内要求连续 ``reads`` 次得到相同数字，失败返回 None。"""
        started = time.perf_counter()
        limit = max(1.0, min(1000.0, float(max_ms or self.deadline_ms)))
        required = max(2, int(reads))
        previous = None
        same = 0
        self.last_consistent_values = []
        last = VisionReading(error="未完成一致确认")
        while (time.perf_counter() - started) * 1000 < limit:
            remaining = max(1.0, limit - (time.perf_counter() - started) * 1000)
            last = self.read(region, deadline_ms=remaining)
            self.last_consistent_values.append(last.value)
            if last.value is not None and last.value == previous:
                same += 1
            elif last.value is not None:
                previous = last.value
                same = 1
            else:
                previous = None
                same = 0
            if same >= required:
                self.last_consistent_reading = last
                return last.value
            if delay_ms > 0:
                time.sleep(min(float(delay_ms) / 1000.0,
                               max(0.0, (limit - (time.perf_counter() - started) * 1000) / 1000.0)))
        self.last_consistent_reading = VisionReading(
            value=None,
            elapsed_ms=(time.perf_counter() - started) * 1000,
            backend=last.backend,
            frame_id=last.frame_id,
            error="未在 %.0f ms 内完成 %d 次一致确认" % (limit, required),
        )
        return None


def set_template_dir(directory, namespace=None):
    """设置数字模板目录（与配置文件同目录，方便随数据迁移）。"""
    global _template_dir, _template_namespace, _template_cache
    _template_dir = os.path.abspath(directory) if directory else None
    _template_namespace = str(namespace).strip() if namespace else None
    _template_cache = None


def set_template_namespace(namespace):
    """切换当前模板命名空间，便于左、中、右三块数字分别维护模板。"""
    global _template_namespace, _template_cache
    _template_namespace = str(namespace).strip() if namespace else None
    _template_cache = None


def get_template_dir():
    if _template_dir:
        return os.path.join(_template_dir, _template_namespace) if _template_namespace else _template_dir
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "count_templates")


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


def _tesseract_ready(command=None, tessdata_dir=None):
    """Tesseract 三层是否具备运行条件。"""
    command = command or resolve_tesseract()
    tessdata_dir = tessdata_dir or resolve_tessdata(command)
    return (
        HAS_PYTesseract
        and bool(command)
        and bool(tessdata_dir)
        and os.path.isfile(os.path.join(tessdata_dir, "eng.traineddata"))
    )


def set_rapidocr_params(params=None):
    """设置 RapidOCR 参数，例如本地模型目录与只启用 rec 模型。"""
    global _rapidocr_params, _rapidocr_engine
    _rapidocr_params = dict(params or {})
    _rapidocr_engine = None


def rapid_ocr_available():
    """RapidOCR 是否已经可导入。"""
    return HAS_RAPIDOCR


def _rapidocr_engine_instance():
    """延迟创建并缓存 RapidOCR 实例。"""
    global _rapidocr_engine
    if not HAS_RAPIDOCR:
        return None
    if _rapidocr_engine is None:
        with _rapidocr_lock:
            if _rapidocr_engine is None:
                if RAPIDOCR_LEGACY:
                    _rapidocr_engine = _RapidOCR(
                        use_text_det=False, use_angle_cls=False, print_verbose=False)
                else:
                    _rapidocr_engine = _RapidOCR(params=_rapidocr_params or None)
    return _rapidocr_engine


def read_rapidocr(image):
    """RapidOCR 只识别纯数字，返回整数或 None。"""
    if not HAS_RAPIDOCR or not HAS_PIL or image is None:
        return None
    try:
        prepared = _prepare_for_ocr(image, scale=2)
        if prepared is None:
            return None
        engine = _rapidocr_engine_instance()
        if engine is None:
            return None
        with _ocr_lock:
            if RAPIDOCR_LEGACY:
                result, _elapsed = engine(np.asarray(prepared.convert("RGB")))
                texts = [item[1] for item in (result or [])]
            else:
                result = engine(
                    np.asarray(prepared.convert("RGB")),
                    use_det=False,
                    use_cls=False,
                    use_rec=True,
                )
                texts = getattr(result, "txts", None) or []
        if texts:
            return clean_digits(texts[0])
        return None
    except Exception:
        return None


def probe_rapidocr(image):
    """实测一次 RapidOCR，返回 (整数或 None, 耗时毫秒)。"""
    if not HAS_RAPIDOCR or not HAS_PIL or image is None:
        return None, 0.0
    started = time.perf_counter()
    value = read_rapidocr(image)
    return value, (time.perf_counter() - started) * 1000


def ocr_available():
    """至少有一层识别引擎可用即视为 OCR 可用。"""
    return HAS_PIL and (HAS_RAPIDOCR or HAS_WINRT_OCR or _tesseract_ready())


def engine_status():
    """返回各识别引擎与模板的状态，供界面和自检显示。"""
    command = resolve_tesseract()
    tessdata_dir = resolve_tessdata(command)
    return {
        "template_dir": get_template_dir(),
        "templates": template_stats(),
        "rapidocr": HAS_RAPIDOCR,
        "winrt": HAS_WINRT_OCR,
        "tesseract": _tesseract_ready(command, tessdata_dir),
        "tesseract_path": command,
        "tessdata": tessdata_dir,
    }


def capture_region(region):
    """截取指定屏幕区域，失败时返回 None。"""
    if not HAS_PIL:
        return None
    x, y, width, height = parse_region(region)
    try:
        return ImageGrab.grab(bbox=(x, y, x + width, y + height))
    except Exception:
        return None


def clean_digits(text):
    """只保留数字字符，过滤 OCR 输出里的符号和空格。"""
    digits = re.sub(r"\D", "", str(text or ""))
    if not digits or len(digits) > MAX_COUNT_DIGITS:
        return None
    return int(digits)


# ── 通用图像预处理 ──────────────────────────────────────────────────────────

def _image_mean(gray):
    """返回灰度图的平均亮度。"""
    try:
        if np is not None:
            return float(np.asarray(gray).mean())
        histogram = gray.histogram()
        total = max(1, sum(histogram))
        return sum(index * count for index, count in enumerate(histogram)) / total
    except Exception:
        return 255.0


def _prepare_for_ocr(image, scale=2):
    """预处理为浅色背景并放大，适配 WinRT OCR / Tesseract。"""
    if not HAS_PIL or image is None:
        return None
    try:
        gray = ImageOps.grayscale(image)
        # 深色背景整体反色，保证浅底深字
        if _image_mean(gray) < 128:
            gray = ImageOps.invert(gray)
        gray = ImageOps.autocontrast(gray)
        width, height = gray.size
        factor = max(1, int(scale))
        return gray.resize((width * factor, height * factor), _LANCZOS).convert("RGB")
    except Exception:
        return None


# ── 第一层：模板匹配（自学习） ─────────────────────────────────────────────

def _binarize_for_digits(gray):
    """自适应二值化：数字为黑色、背景为白色，深色背景自动反色。"""
    mean = _image_mean(gray)
    if mean < 128:
        gray = 255 - gray
    height, width = gray.shape
    # 先中值去噪，抑制截屏噪点与背景纹理
    if min(height, width) >= 3:
        gray = cv2.medianBlur(gray, 3)
    block = max(9, (min(height, width) // 4) | 1)
    block = min(block, 51)
    return cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, block, 11)


def _segment_digit_boxes(image):
    """分割出数字框（按 x 排序），返回 [(x, y, width, height)]。"""
    if not HAS_CV2 or image is None:
        return []
    try:
        gray = np.asarray(image.convert("L"))
    except Exception:
        return []
    height, width = gray.shape
    if height < 6 or width < 8:
        return []
    try:
        binary = _binarize_for_digits(gray)
        foreground = 255 - binary
        kernel = np.ones((2, 2), np.uint8)
        foreground = cv2.morphologyEx(foreground, cv2.MORPH_OPEN, kernel)
        _labels_count, _labels, stats, _centroids = cv2.connectedComponentsWithStats(foreground, 8)
    except Exception:
        return []
    boxes = []
    min_height = max(5, int(height * 0.30))
    for label in range(1, int(_labels_count)):
        x, y, box_width, box_height, area = (int(stats[label, 0]), int(stats[label, 1]),
                                              int(stats[label, 2]), int(stats[label, 3]),
                                              int(stats[label, 4]))
        if box_height < min_height or box_width < 2 or area < 8:
            continue
        ratio = box_height / max(1.0, box_width)
        if ratio < 0.8 or ratio > 5.0:
            continue
        boxes.append((x, y, box_width, box_height))
    boxes.sort(key=lambda box: box[0])
    return boxes


def _load_templates():
    """加载全部数字模板，返回 {digit: [灰度数组]}，带目录 mtime 缓存。"""
    global _template_cache
    if not HAS_CV2:
        return {}
    directory = get_template_dir()
    if not directory:
        return {}
    try:
        mtime = os.path.getmtime(directory)
    except OSError:
        return {}
    if _template_cache is not None and _template_cache[0] == directory and _template_cache[1] == mtime:
        return _template_cache[2]
    templates = {digit: [] for digit in range(10)}
    for digit in range(10):
        folder = os.path.join(directory, str(digit))
        if not os.path.isdir(folder):
            continue
        for name in sorted(os.listdir(folder)):
            if not name.lower().endswith(".png"):
                continue
            try:
                arr = cv2.imread(os.path.join(folder, name), cv2.IMREAD_GRAYSCALE)
            except Exception:
                continue
            if arr is None or arr.size == 0:
                continue
            templates[digit].append(arr)
            if len(templates[digit]) >= MAX_TEMPLATES_PER_DIGIT * 2:
                break
    _template_cache = (directory, mtime, templates)
    return templates


def read_templates(image):
    """第一层模板匹配：返回 (值 或 None, 分割出的数字个数)。"""
    boxes = _segment_digit_boxes(image)
    if not boxes:
        return None, 0
    templates = _load_templates()
    if not any(templates.get(digit) for digit in range(10)):
        return None, len(boxes)
    try:
        gray = np.asarray(image.convert("L"))
        binary = _binarize_for_digits(gray)
    except Exception:
        return None, len(boxes)
    digits = []
    for (x, y, box_width, box_height) in boxes:
        crop = binary[y:y + box_height, x:x + box_width]
        best_digit, best_score = None, 0.0
        for digit in range(10):
            for template in templates[digit]:
                try:
                    resized = cv2.resize(template, (box_width, box_height))
                    score = float(cv2.matchTemplate(crop, resized, cv2.TM_CCOEFF_NORMED)[0][0])
                except Exception:
                    continue
                if score > best_score:
                    best_digit, best_score = digit, score
        if best_digit is None or best_score < TEMPLATE_MATCH_MIN:
            return None, len(boxes)
        digits.append(best_digit)
    if not digits or len(digits) > MAX_COUNT_DIGITS:
        return None, len(boxes)
    return int("".join(str(item) for item in digits)), len(boxes)


def _trim_templates(folder, limit):
    """每个数字最多保留 limit 张模板，超出时删除最旧的。"""
    try:
        files = [os.path.join(folder, name) for name in os.listdir(folder)
                 if name.lower().endswith(".png")]
        files.sort(key=lambda path: os.path.getmtime(path))
        for path in files[:max(0, len(files) - limit)]:
            try:
                os.remove(path)
            except OSError:
                pass
    except OSError:
        pass


def save_template(image, box, digit):
    """把单个数字框保存为模板 PNG，返回是否保存成功。"""
    if not HAS_CV2 or image is None:
        return False
    try:
        digit = int(digit)
        if not 0 <= digit <= 9:
            return False
        gray = np.asarray(image.convert("L"))
        binary = _binarize_for_digits(gray)
        x, y, box_width, box_height = (int(box[0]), int(box[1]), int(box[2]), int(box[3]))
        crop = binary[y:y + box_height, x:x + box_width]
        if crop.size == 0:
            return False
        # 统一尺寸：保持宽高比，四周留白
        template_width, template_height = TEMPLATE_SIZE
        height, width = crop.shape
        scale = min(template_width / max(1, width), template_height / max(1, height))
        new_width, new_height = max(1, int(width * scale)), max(1, int(height * scale))
        resized = cv2.resize(crop, (new_width, new_height), interpolation=cv2.INTER_AREA)
        canvas = np.full((template_height, template_width), 255, dtype=np.uint8)
        left = (template_width - new_width) // 2
        top = (template_height - new_height) // 2
        canvas[top:top + new_height, left:left + new_width] = resized
        digest = hashlib.md5(canvas.tobytes()).hexdigest()[:12]
        directory = get_template_dir()
        if not directory:
            return False
        folder = os.path.join(directory, str(digit))
        os.makedirs(folder, exist_ok=True)
        target = os.path.join(folder, "%s.png" % digest)
        if os.path.isfile(target):
            return False
        if not cv2.imwrite(target, canvas):
            return False
        _trim_templates(folder, MAX_TEMPLATES_PER_DIGIT)
        return True
    except Exception:
        return False


def template_stats():
    """统计每个数字已有的模板数量。"""
    counts = {digit: 0 for digit in range(10)}
    directory = get_template_dir()
    if directory:
        for digit in range(10):
            folder = os.path.join(directory, str(digit))
            if os.path.isdir(folder):
                try:
                    counts[digit] = len([name for name in os.listdir(folder)
                                         if name.lower().endswith(".png")])
                except OSError:
                    pass
    return counts


def learn_templates(region, frames=5, delay=0.15, command=None, tessdata_dir=None, callback=None, namespace=None):
    """自学习：截取若干帧，OCR 成功且数字个数与分割结果一致时保存每个数字模板。

    返回 {digit: 本次新学到的模板数}。
    """
    learned = {digit: 0 for digit in range(10)}
    frames = max(1, min(20, int(frames)))
    if namespace:
        set_template_namespace(namespace)
    for frame_index in range(frames):
        image = capture_region(region)
        if image is not None:
            boxes = _segment_digit_boxes(image)
            if boxes:
                value = read_rapidocr(image)
                if value is None:
                    value = read_winocr(image)
                if value is None:
                    value = read_tesseract(image, command=command, tessdata_dir=tessdata_dir)
                if value is not None:
                    digits = [int(char) for char in str(value)]
                    if len(digits) == len(boxes):
                        for digit, box in zip(digits, boxes):
                            if save_template(image, box, digit):
                                learned[digit] += 1
        if callback is not None:
            try:
                callback(frame_index + 1, dict(learned))
            except Exception:
                pass
        if frame_index + 1 < frames:
            time.sleep(max(0.0, delay))
    return learned


# ── 第二层：Windows OCR（winrt） ───────────────────────────────────────────

def _winrt_engine():
    """创建并缓存 OcrEngine，优先 zh-Hans-CN，失败退回系统用户语言。"""
    global _engine_cache
    if not HAS_WINRT_OCR:
        return None
    with _engine_lock:
        if "engine" in _engine_cache:
            return _engine_cache["engine"]
        engine = None
        try:
            engine = _winrt_ocr.OcrEngine.try_create_from_language(
                _winrt_globalization.Language("zh-Hans-CN"))
        except Exception:
            engine = None
        if engine is None:
            try:
                engine = _winrt_ocr.OcrEngine.try_create_from_user_profile_languages()
            except Exception:
                engine = None
        _engine_cache["engine"] = engine
        return engine


def _get_loop():
    """每个线程复用一个 asyncio 事件循环，避免反复创建的开销。"""
    loop = getattr(_loop_local, "loop", None)
    if loop is None or loop.is_closed():
        loop = asyncio.new_event_loop()
        _loop_local.loop = loop
    return loop


async def _winrt_recognize_async(engine, png_bytes):
    stream = _winrt_streams.InMemoryRandomAccessStream()
    writer = _winrt_streams.DataWriter(stream.get_output_stream_at(0))
    writer.write_bytes(png_bytes)
    await writer.store_async()
    stream.seek(0)
    decoder = await _winrt_imaging.BitmapDecoder.create_async(stream)
    bitmap = await decoder.get_software_bitmap_async()
    return await engine.recognize_async(bitmap)


def _winrt_ocr_text(engine, png_bytes):
    loop = None
    try:
        loop = _get_loop()
        result = loop.run_until_complete(_winrt_recognize_async(engine, png_bytes))
        return result.text if result is not None else None
    except Exception:
        try:
            if loop is not None and not loop.is_closed():
                loop.close()
        except Exception:
            pass
        _loop_local.loop = None
        return None


def read_winocr(image):
    """第二层 Windows OCR：返回整数或 None。"""
    if not HAS_WINRT_OCR or not HAS_PIL or image is None:
        return None
    try:
        engine = _winrt_engine()
        if engine is None:
            return None
        prepared = _prepare_for_ocr(image, scale=2)
        if prepared is None:
            return None
        buffer = io.BytesIO()
        prepared.save(buffer, format="PNG")
        with _ocr_lock:
            text = _winrt_ocr_text(engine, buffer.getvalue())
        return clean_digits(text)
    except Exception:
        return None


def probe_winrt_ocr(image):
    """公开实测接口：对给定图像跑一次真实 WinRT OCR，返回 (整数或 None, 耗时毫秒)。"""
    if not HAS_WINRT_OCR or not HAS_PIL or image is None:
        return None, 0.0
    try:
        engine = _winrt_engine()
        if engine is None:
            return None, 0.0
        prepared = _prepare_for_ocr(image, scale=2)
        if prepared is None:
            return None, 0.0
        buffer = io.BytesIO()
        prepared.save(buffer, format="PNG")
        started = time.perf_counter()
        with _ocr_lock:
            text = _winrt_ocr_text(engine, buffer.getvalue())
        elapsed = (time.perf_counter() - started) * 1000
        return clean_digits(text), elapsed
    except Exception:
        return None, 0.0


# ── 第三层：Tesseract 兜底 ─────────────────────────────────────────────────


def _run_tesseract_hidden(image, command, tessdata_dir, config):
    """隐藏窗口调用 tesseract.exe（消除识别时的黑色控制台弹窗），返回 stdout 文本。"""
    path = None
    try:
        handle, path = tempfile.mkstemp(prefix="acr_", suffix=".png")
        os.close(handle)
        image.save(path, format="PNG")
        env = dict(os.environ)
        env["TESSDATA_PREFIX"] = os.path.abspath(tessdata_dir)
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        startupinfo = None
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0
        result = subprocess.run(
            [command, path, "stdout"] + config.split(),
            capture_output=True,
            timeout=3,
            creationflags=creationflags,
            startupinfo=startupinfo,
            env=env,
        )
        return result.stdout.decode("utf-8", "replace")
    except Exception:
        return None
    finally:
        if path:
            try:
                os.remove(path)
            except OSError:
                pass


def read_tesseract(image, command=None, tessdata_dir=None):
    """第三层 Tesseract：裁剪数字条放大 3 倍，PSM 7/10/13 + 数字白名单。"""
    if not HAS_PYTesseract or image is None:
        return None
    command = command or resolve_tesseract()
    tessdata_dir = tessdata_dir or resolve_tessdata(command)
    if not command or not tessdata_dir or not os.path.isfile(os.path.join(tessdata_dir, "eng.traineddata")):
        return None
    try:
        os.environ["TESSDATA_PREFIX"] = os.path.abspath(tessdata_dir)
        crop = image
        boxes = _segment_digit_boxes(image)
        if boxes:
            left = max(0, min(box[0] for box in boxes) - 2)
            top = max(0, min(box[1] for box in boxes) - 2)
            right = min(image.width, max(box[0] + box[2] for box in boxes) + 2)
            bottom = min(image.height, max(box[1] + box[3] for box in boxes) + 2)
            if right > left and bottom > top:
                crop = image.crop((left, top, right, bottom))
        prepared = _prepare_for_ocr(crop, scale=3)
        if prepared is None:
            return None
        votes = {}
        for psm in ("7", "10", "13"):
            config = "--psm %s -c tessedit_char_whitelist=0123456789" % psm
            text = _run_tesseract_hidden(prepared, command, tessdata_dir, config)
            value = clean_digits(text)
            if value is not None:
                votes[value] = votes.get(value, 0) + 1
                if votes[value] >= 2:
                    break
        if not votes:
            return None
        return max(votes.items(), key=lambda item: (item[1], item[0]))[0]
    except Exception:
        return None


# ── 统一读取入口 ───────────────────────────────────────────────────────────

def read_count_debug(region, command=None, tessdata_dir=None):
    """多层识别并返回各层耗时/结果明细，便于「测试读取」显示。"""
    info = {
        "value": None,
        "layer": None,
        "template_value": None,
        "template_ms": 0.0,
        "rapidocr_value": None,
        "rapidocr_ms": 0.0,
        "winocr_value": None,
        "winocr_ms": 0.0,
        "tesseract_value": None,
        "tesseract_ms": 0.0,
        "digits_seen": 0,
        "total_ms": 0.0,
        "error": None,
    }
    started = time.perf_counter()
    image = capture_region(region)
    if image is None:
        info["error"] = "截屏失败"
        info["total_ms"] = (time.perf_counter() - started) * 1000
        return info
    # 第一层：模板匹配
    layer_started = time.perf_counter()
    template_value, digits_seen = read_templates(image)
    info["template_ms"] = (time.perf_counter() - layer_started) * 1000
    info["template_value"] = template_value
    info["digits_seen"] = digits_seen
    if template_value is not None:
        info["value"], info["layer"] = template_value, "模板"
        info["total_ms"] = (time.perf_counter() - started) * 1000
        return info
    # 第二层：Windows OCR
    layer_started = time.perf_counter()
    winocr_value = read_winocr(image)
    info["winocr_ms"] = (time.perf_counter() - layer_started) * 1000
    info["winocr_value"] = winocr_value
    if winocr_value is not None:
        info["value"], info["layer"] = winocr_value, "WinOCR"
        info["total_ms"] = (time.perf_counter() - started) * 1000
        return info
    # 第三层：RapidOCR
    layer_started = time.perf_counter()
    rapidocr_value = read_rapidocr(image)
    info["rapidocr_ms"] = (time.perf_counter() - layer_started) * 1000
    info["rapidocr_value"] = rapidocr_value
    if rapidocr_value is not None:
        info["value"], info["layer"] = rapidocr_value, "RapidOCR"
        info["total_ms"] = (time.perf_counter() - started) * 1000
        return info
    # 第四层：Tesseract
    layer_started = time.perf_counter()
    tesseract_value = read_tesseract(image, command=command, tessdata_dir=tessdata_dir)
    info["tesseract_ms"] = (time.perf_counter() - layer_started) * 1000
    info["tesseract_value"] = tesseract_value
    if tesseract_value is not None:
        info["value"], info["layer"] = tesseract_value, "Tesseract"
    info["total_ms"] = (time.perf_counter() - started) * 1000
    return info


def read_count_fast(region, command=None, tessdata_dir=None, budget_ms=850, backend="template_winocr"):
    """实时读取：模板、Windows OCR、RapidOCR，严格受 1 秒以内截止时间约束。"""
    limit = 850 if budget_ms is None or float(budget_ms or 0) <= 0 else min(1000, float(budget_ms))
    reading = VisionBackend(deadline_ms=limit, backend=backend).read(region, deadline_ms=limit)
    return reading.value, reading.elapsed_ms, reading.backend or None


def read_count_once(region, command=None, tessdata_dir=None):
    """读取一次 Boss 卡数量，返回整数或 None。"""
    return read_count_debug(region, command=command, tessdata_dir=tessdata_dir)["value"]


def read_count_quick(region, attempts=3, delay=0.05, command=None, tessdata_dir=None):
    """单次三层读取，失败最多快速重试 attempts 次。

    返回 (值 或 None, 已读次数, 原始结果列表)。
    """
    raw_values = []
    attempts = max(1, int(attempts))
    for attempt in range(attempts):
        value = read_count_once(region, command=command, tessdata_dir=tessdata_dir)
        raw_values.append(value)
        if value is not None:
            return value, attempt + 1, raw_values
        if attempt + 1 < attempts:
            time.sleep(max(0.0, float(delay)))
    return None, attempts, raw_values


def read_count_stable(region, samples=2, delay=0.05, command=None, tessdata_dir=None):
    """快速读取并尽量取两次一致结果，不再长时间阻塞。

    返回 (值 或 None, 已读次数, 原始结果列表)。
    """
    backend = VisionBackend(deadline_ms=850)
    value = backend.read_consistent(
        region,
        max_ms=850,
        reads=max(2, int(samples)),
        delay_ms=max(0.0, float(delay)) * 1000,
    )
    return value, len(backend.last_consistent_values), list(backend.last_consistent_values)


def warm_up_ocr(region=None, command=None, tessdata_dir=None,
                include_diagnostic=False, backend="template_winocr"):
    """只预热当前实时路径需要的后端，返回总耗时毫秒。

    默认路径不初始化 RapidOCR；显式启用 RapidOCR 时与 Windows OCR 并行
    初始化，避免两个独立的冷启动耗时相加。Tesseract 仅人工诊断时预热。
    """
    started = time.perf_counter()
    backend = str(backend or "template_winocr")
    use_rapidocr = backend == "template_winocr_rapidocr"
    use_winocr = backend in ("template_winocr", "template_winocr_rapidocr", "winocr_template")

    def warm_rapidocr():
        if not use_rapidocr or not HAS_RAPIDOCR or not HAS_PIL:
            return
        try:
            read_rapidocr(Image.new("L", (48, 24), 255))
        except Exception:
            pass

    def warm_winocr():
        if not use_winocr or not HAS_WINRT_OCR:
            return
        try:
            # 创建引擎即可完成 Windows OCR 的主要冷启动；空图识别会额外消耗
            # 约 200 ms，留给第一次真实画面识别，缩短用户等待时间。
            _winrt_engine()
        except Exception:
            pass

    if use_rapidocr and use_winocr:
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(warm_rapidocr), executor.submit(warm_winocr)]
            for future in futures:
                try:
                    future.result()
                except Exception:
                    pass
    else:
        warm_rapidocr()
        warm_winocr()

    if include_diagnostic and _tesseract_ready(command, tessdata_dir):
        try:
            command = command or resolve_tesseract()
            tessdata_dir = tessdata_dir or resolve_tessdata(command)
            if tessdata_dir:
                os.environ["TESSDATA_PREFIX"] = os.path.abspath(tessdata_dir)
            _run_tesseract_hidden(
                Image.new("L", (48, 24), 255),
                command,
                tessdata_dir,
                config="--psm 7 -c tessedit_char_whitelist=0123456789")
        except Exception:
            pass
    return round((time.perf_counter() - started) * 1000, 1)


class CountGuard:
    """宽松计数：数量下降按实际差值累计；读不到/未变化按已消耗 1 张继续，绝不卡死。"""

    def __init__(self, target, progress=0):
        self.target = max(0, int(target))
        self.progress = max(0, int(progress))
        self.last_remaining = None
        self.last_note = ""

    @property
    def reached(self):
        return self.progress >= self.target

    def confirm(self, before, after):
        """返回 (进度, 说明)。仅召唤前数量非法时才抛错，其余情况一律推进进度。"""
        if before is None:
            raise CountSafetyError("召唤前数量无法确认，暂停以防误点")
        before = int(before)
        if before <= 0:
            raise CountSafetyError("召唤前数量为 0，暂停以防误点")
        if after is None:
            self.progress += 1
            self.last_remaining = None
            self.last_note = "未能核验消耗，按已消耗 1 张继续"
            return self.progress, self.last_note
        after = max(0, int(after))
        if after < before:
            delta = before - after
            self.progress += delta
            self.last_remaining = after
            self.last_note = "数量下降 %d 张" % delta
        else:
            self.progress += 1
            self.last_remaining = after
            self.last_note = "数量未下降（%d→%d），按已消耗 1 张继续" % (before, after)
        return self.progress, self.last_note


class StrictCounter:
    """单个计数区域的严格状态机：只接受 new == old - 1。"""

    def __init__(self, counter_id, threshold, stable_samples=3, primary=False):
        self.counter_id = str(counter_id)
        self.threshold = int(threshold)
        self.stable_samples = max(2, int(stable_samples))
        self.primary = bool(primary)
        self.baseline = None
        self.stable_value = None
        self.candidate = None
        self.candidate_count = 0
        self.triggered = False
        self.last_event = ""

    def reset(self):
        self.baseline = None
        self.stable_value = None
        self.candidate = None
        self.candidate_count = 0
        self.triggered = False
        self.last_event = ""

    def observe(self, value):
        """返回事件说明字符串，调用方根据内容决定是否更新 UI。"""
        if value is None:
            self.last_event = "读取失败"
            return self.last_event
        value = int(value)
        if self.stable_value is None:
            self.stable_value = value
            if self.baseline is None:
                self.baseline = value
                self.last_event = "基线 %d" % value
            else:
                self.last_event = "基线重置为 %d" % value
            self.candidate = None
            self.candidate_count = 0
            return self.last_event
        if value == self.stable_value:
            self.candidate = None
            self.candidate_count = 0
            self.last_event = "无变化"
            return self.last_event
        if value == self.stable_value - 1:
            self.candidate = value
            self.candidate_count += 1
            if self.candidate_count >= self.stable_samples:
                self.stable_value = value
                self.candidate = None
                self.candidate_count = 0
                self.last_event = "减少 1：%d" % value
            else:
                self.last_event = "待确认 %d/%d" % (self.candidate_count, self.stable_samples)
            return self.last_event
        self.last_event = "异常变化：%d→%d" % (self.stable_value, value)
        return self.last_event

    @property
    def below_threshold(self):
        return self.stable_value is not None and self.stable_value <= self.threshold


class MultiCounterMonitor:
    """多个计数区域联合判断阈值停止。"""

    def __init__(self, counters, stop_mode="left", stable_samples=3):
        self.counters = {
            item["id"]: StrictCounter(
                item["id"],
                item.get("threshold", 0),
                stable_samples=item.get("stable_samples", stable_samples),
                primary=bool(item.get("primary", False)),
            )
            for item in counters
            if item.get("enabled", True)
        }
        self.stop_mode = str(stop_mode or "left")
        self.triggered = False

    def observe(self, snapshot):
        """snapshot 为 {counter_id: value 或 None}。"""
        events = {}
        for counter_id, counter in self.counters.items():
            events[counter_id] = counter.observe(snapshot.get(counter_id))
        self.triggered = self.triggered or self._condition_met()
        return self.triggered, events

    def _condition_met(self):
        active = [counter for counter in self.counters.values() if counter.stable_value is not None]
        if not active:
            return False
        below = [counter for counter in active if counter.below_threshold]
        below_ids = {counter.counter_id for counter in below}
        primary = next((counter for counter in active if counter.primary), None)
        if self.stop_mode == "left":
            return bool(primary and primary.counter_id in below_ids)
        if self.stop_mode == "any":
            return bool(below)
        if self.stop_mode == "all":
            return len(below) == len(active)
        if self.stop_mode == "left_and_any":
            return bool(primary and primary.counter_id in below_ids and len(below) >= 2)
        if self.stop_mode == "left_and_all":
            return bool(primary and primary.counter_id in below_ids and len(below) == len(active))
        if self.stop_mode == "pair":
            return len(below) >= 2
        return bool(primary and primary.counter_id in below_ids)

    def reset(self):
        for counter in self.counters.values():
            counter.reset()
        self.triggered = False
