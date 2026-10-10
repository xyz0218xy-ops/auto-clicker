# -*- coding: utf-8 -*-
"""打包脚本：复制 Tcl/Tk 运行库、暂存 Tesseract 最小依赖，然后运行 PyInstaller 生成单文件 exe。

Tcl/Tk：必须显式打包 tcl8.6 / tk8.6 目录、tcl86t.dll、tk86t.dll 与 _tkinter.pyd，
否则打包后界面会报 init.tcl 版本不匹配或找不到可用 Tcl/Tk。
Tesseract：用 pefile 分析 tesseract.exe 的 DLL 导入闭包，只暂存实际需要的
DLL + eng.traineddata，避免把 150MB 无关 DLL 全部塞进 exe。
"""
import os
import importlib.util
import shutil
import subprocess
import sys

try:
    import pefile
except ImportError:
    pefile = None

APP_VERSION = "v39"
PYTHON = os.environ.get("PYTHON_EXECUTABLE", sys.executable)
TCL_SRC = os.path.join(sys.prefix, "tcl")
DLL_SRC = os.path.join(sys.prefix, "DLLs")
TESS_SRC = r"C:\Program Files\Tesseract-OCR"
WORK_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUTS = os.path.join(WORK_DIR, "outputs")
TEMP_TCL = os.path.join(WORK_DIR, "_temp_tcl")
TESS_STAGE = os.path.join(WORK_DIR, "work", "tesseract-stage")
RAPIDOCR_MODELS_SRC = os.path.join(WORK_DIR, "work", "rapidocr-models")
DIST_DIR = os.path.join(OUTPUTS, "dist")
BUILD_DIR = os.path.join(WORK_DIR, "work", "build")
SPEC_DIR = os.path.join(WORK_DIR, "work", "spec")
PICACHE = os.path.join(WORK_DIR, "work", "picache")
EXE_NAME = f"AutoClicker-{APP_VERSION}"


def stage_tcl():
    """复制 Tcl/Tk 到临时目录并删除冲突的 demos 目录。"""
    if os.path.exists(TEMP_TCL):
        shutil.rmtree(TEMP_TCL)
    print("复制 Tcl/Tk 到临时目录 ...")
    shutil.copytree(TCL_SRC, TEMP_TCL)
    demos_dir = os.path.join(TEMP_TCL, "tk8.6", "demos")
    if os.path.exists(demos_dir):
        shutil.rmtree(demos_dir)
        print("已删除 tk8.6/demos")


def _dll_imports(path):
    """读取 PE 文件的导入 DLL 列表。"""
    pe = pefile.PE(path, fast_load=True)
    pe.parse_data_directories(directories=[
        pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"]])
    return [entry.dll.decode(errors="ignore")
            for entry in (getattr(pe, "DIRECTORY_ENTRY_IMPORT", []) or [])]


def stage_tesseract():
    """暂存 tesseract.exe + 依赖闭包 DLL + eng.traineddata，返回暂存目录或 None。"""
    if not os.path.isdir(TESS_SRC):
        print("未找到 Tesseract 安装目录，跳过捆绑（程序会回退到系统 Tesseract / WinRT）。")
        return None
    if pefile is None:
        print("缺少 pefile，跳过 Tesseract 捆绑（程序会回退到系统 Tesseract / WinRT）。")
        return None
    if os.path.exists(TESS_STAGE):
        shutil.rmtree(TESS_STAGE)
    os.makedirs(TESS_STAGE)
    seen, files = set(), []

    def walk(path):
        name = os.path.basename(path).lower()
        if name in seen:
            return
        seen.add(name)
        files.append(name)
        for dep in _dll_imports(path):
            dep_low = dep.lower()
            if dep_low.startswith(("api-ms-", "ext-ms-")):
                continue
            candidate = os.path.join(TESS_SRC, dep)
            if os.path.exists(candidate):
                walk(candidate)

    walk(os.path.join(TESS_SRC, "tesseract.exe"))
    for name in files:
        shutil.copy2(os.path.join(TESS_SRC, name), os.path.join(TESS_STAGE, name))
    os.makedirs(os.path.join(TESS_STAGE, "tessdata"))
    shutil.copy2(
        os.path.join(TESS_SRC, "tessdata", "eng.traineddata"),
        os.path.join(TESS_STAGE, "tessdata", "eng.traineddata"),
    )
    size_mb = sum(
        os.path.getsize(os.path.join(TESS_STAGE, name)) for name in files
    ) / 1024 / 1024
    print(f"Tesseract 暂存完成：{len(files)} 个文件（约 {size_mb:.0f} MB）+ eng.traineddata")
    return TESS_STAGE


def stage_rapidocr_models():
    """把离线 RapidOCR 模型复制到发布目录，exe 启动时从同目录 models/rapidocr 加载。"""
    if not os.path.isdir(RAPIDOCR_MODELS_SRC):
        print("未找到自定义 RapidOCR 模型；使用 OCR 包内置的离线模型。")
        return False
    target = os.path.join(DIST_DIR, "models", "rapidocr")
    if os.path.exists(target):
        shutil.rmtree(target)
    shutil.copytree(RAPIDOCR_MODELS_SRC, target)
    print(f"RapidOCR 模型已复制到 {target}")
    return True


def main():
    stage_tcl()
    tesseract_stage = stage_tesseract()

    os.environ["PYINSTALLER_CONFIG_DIR"] = PICACHE

    cmd = [
        PYTHON, "-m", "PyInstaller",
        "--onefile", "--windowed",
        "--name", EXE_NAME,
        "--add-data", f"{os.path.join(TEMP_TCL, 'tcl8.6')};tcl/tcl8.6",
        "--add-data", f"{os.path.join(TEMP_TCL, 'tk8.6')};tk/tk8.6",
        "--add-binary", os.path.join(DLL_SRC, "tcl86t.dll") + ";.",
        "--add-binary", os.path.join(DLL_SRC, "tk86t.dll") + ";.",
        "--add-binary", os.path.join(DLL_SRC, "_tkinter.pyd") + ";.",
        "--hidden-import", "PIL",
        "--hidden-import", "PIL.Image",
        "--hidden-import", "PIL.ImageGrab",
        "--hidden-import", "PIL.ImageOps",
        "--hidden-import", "PIL.ImageFilter",
        "--hidden-import", "pytesseract",
        "--hidden-import", "winrt.windows.media.ocr",
        "--hidden-import", "winrt.windows.graphics.imaging",
        "--hidden-import", "winrt.windows.storage.streams",
        "--hidden-import", "winrt.windows.globalization",
        "--hidden-import", "winrt.windows.foundation",
        "--hidden-import", "winrt.windows.foundation.collections",
        "--hidden-import", "onnxruntime",
        "--collect-submodules", "winrt",
        "--collect-all", "onnxruntime",
        "--collect-all", "cv2",
        "--distpath", DIST_DIR,
        "--workpath", BUILD_DIR,
        "--specpath", SPEC_DIR,
        "--noconfirm",
        os.path.join(OUTPUTS, "auto_clicker.py"),
    ]
    for package in ("rapidocr", "rapidocr_onnxruntime"):
        if importlib.util.find_spec(package):
            insert_at = cmd.index("--distpath")
            cmd[insert_at:insert_at] = ["--hidden-import", package, "--collect-all", package]
    if tesseract_stage:
        insert_at = cmd.index("--distpath")
        cmd[insert_at:insert_at] = ["--add-data", f"{tesseract_stage};tesseract"]

    print("开始打包 ...")
    print(" ".join(cmd))
    result = subprocess.run(cmd, cwd=WORK_DIR)
    if result.returncode != 0:
        print(f"打包失败，返回码: {result.returncode}")
        sys.exit(1)

    exe_path = os.path.join(DIST_DIR, f"{EXE_NAME}.exe")
    if not os.path.exists(exe_path):
        print("打包失败：未生成 exe")
        sys.exit(1)
    size_mb = os.path.getsize(exe_path) / 1024 / 1024
    print(f"打包完成: {exe_path} ({size_mb:.1f} MB)")

    stage_rapidocr_models()

    shutil.rmtree(TEMP_TCL, ignore_errors=True)
    if tesseract_stage:
        shutil.rmtree(TESS_STAGE, ignore_errors=True)
    print("临时目录已清理")


if __name__ == "__main__":
    main()
