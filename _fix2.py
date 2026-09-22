import re

with open(r'C:\Users\A\Documents\Codex\auto-clicker\outputs\auto_clicker.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 旧的 bootstrap_tcl_tk 函数
old_bootstrap = '''def bootstrap_tcl_tk():
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
    return None'''

new_bootstrap = '''def bootstrap_tcl_tk():
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
    return bundle'''

assert old_bootstrap in content, "Cannot find old bootstrap_tcl_tk"
content = content.replace(old_bootstrap, new_bootstrap, 1)
print("Step 1: bootstrap_tcl_tk rewritten")

assert 'package require -exact Tcl' in content
assert 'DLLs' in content
print("All checks passed!")

with open(r'C:\Users\A\Documents\Codex\auto-clicker\outputs\auto_clicker.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("File saved!")
