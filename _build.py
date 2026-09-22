# -*- coding: utf-8 -*-
"""复制 Tcl/Tk 并删除冲突的 demos 目录，然后运行 PyInstaller 打包。"""
import os
import shutil
import subprocess
import sys

PYTHON = r"C:\Users\A\AppData\Local\Python\pythoncore-3.14-64\python.exe"
TCL_SRC = r"C:\Users\A\AppData\Local\Python\pythoncore-3.14-64\tcl"
WORK_DIR = r"C:\Users\A\Documents\Codex\auto-clicker"
OUTPUTS = os.path.join(WORK_DIR, "outputs")
TEMP_TCL = os.path.join(WORK_DIR, "_temp_tcl")
DIST_DIR = os.path.join(OUTPUTS, "dist")
BUILD_DIR = os.path.join(WORK_DIR, "work", "build")
SPEC_DIR = os.path.join(WORK_DIR, "work", "spec")
PICACHE = os.path.join(WORK_DIR, "work", "picache")

# 清理临时目录
if os.path.exists(TEMP_TCL):
    shutil.rmtree(TEMP_TCL)
print("复制 Tcl/Tk 到临时目录...")
shutil.copytree(TCL_SRC, TEMP_TCL)

# 删除 tk8.6\demos（大小写冲突导致 PyInstaller 解压失败）
demos_dir = os.path.join(TEMP_TCL, "tk8.6", "demos")
if os.path.exists(demos_dir):
    shutil.rmtree(demos_dir)
    print("已删除 tk8.6/demos")

# 设置环境变量
os.environ["PYINSTALLER_CONFIG_DIR"] = PICACHE

# 构建 PyInstaller 命令
cmd = [
    PYTHON, "-m", "PyInstaller",
    "--onefile", "--windowed",
    "--name", "AutoClicker",
    "--add-data", f"{os.path.join(TEMP_TCL, 'tcl8.6')};tcl/tcl8.6",
    "--add-data", f"{os.path.join(TEMP_TCL, 'tk8.6')};tk/tk8.6",
    "--add-binary", r"C:\Users\A\AppData\Local\Python\pythoncore-3.14-64\DLLs\tcl86t.dll;.",
    "--add-binary", r"C:\Users\A\AppData\Local\Python\pythoncore-3.14-64\DLLs\tk86t.dll;.",
    "--distpath", DIST_DIR,
    "--workpath", BUILD_DIR,
    "--specpath", SPEC_DIR,
    "--noconfirm",
    os.path.join(OUTPUTS, "auto_clicker.py"),
]

print("开始打包...")
print(" ".join(cmd))
result = subprocess.run(cmd, cwd=WORK_DIR)
if result.returncode != 0:
    print(f"打包失败，返回码: {result.returncode}")
    sys.exit(1)

# 重命名
src = os.path.join(DIST_DIR, "AutoClicker.exe")
dst = os.path.join(DIST_DIR, "自动点击器.exe")
if os.path.exists(src):
    if os.path.exists(dst):
        os.remove(dst)
    os.rename(src, dst)
    size_mb = os.path.getsize(dst) / 1024 / 1024
    print(f"打包完成: {dst} ({size_mb:.1f} MB)")

# 清理临时目录
shutil.rmtree(TEMP_TCL, ignore_errors=True)
print("临时目录已清理")
