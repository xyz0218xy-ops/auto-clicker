import re

with open(r'C:\Users\A\Documents\Codex\auto-clicker\outputs\auto_clicker.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 重写 bootstrap_tcl_tk，在最后加入 DLL 搜索路径设置
old_bootstrap_end = '''    # 兜底：直接用 bundle 路径
    os.environ["TCL_LIBRARY"] = os.path.join(bundle, "tcl", "tcl8.6")
    os.environ["TK_LIBRARY"] = os.path.join(bundle, "tk", "tk8.6")
    try:
        os.chdir(bundle)
    except Exception:
        pass
    return bundle'''

new_bootstrap_end = '''    # 兜底：直接用 bundle 路径
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
            pass'''

assert old_bootstrap_end in content, "Cannot find old bootstrap tail"
content = content.replace(old_bootstrap_end, new_bootstrap_end, 1)

# 在 TCL_RUNTIME = bootstrap_tcl_tk() 之后、import tkinter 之前插入 _ensure_dll_path() 调用
old_import = '''TCL_RUNTIME = bootstrap_tcl_tk()

import tkinter as tk'''
new_import = '''TCL_RUNTIME = bootstrap_tcl_tk()
_ensure_dll_path()

import tkinter as tk'''

assert old_import in content, "Cannot find TCL_RUNTIME line"
content = content.replace(old_import, new_import, 1)

print("Steps done")
assert '_ensure_dll_path' in content
assert 'os.add_dll_directory' in content
print("All checks passed!")

with open(r'C:\Users\A\Documents\Codex\auto-clicker\outputs\auto_clicker.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("File saved!")
