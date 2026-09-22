# -*- coding: utf-8 -*-
"""Add F9/F11 global hotkeys for macro recording/replay."""

import py_compile, tempfile, os

PATH = r"C:\Users\A\Documents\Codex\auto-clicker\outputs\auto_clicker.py"

with open(PATH, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Add F9/F11 hotkey registration in _register_hotkey
old_reg = '''        if self.right_hotkey and self.right_hotkey != self.hotkey:
            try:
                self.right_hotkey_handle = keyboard.add_hotkey(self.right_hotkey,
                                                               self._on_right_hotkey, suppress=False)
            except Exception as exc:
                self.right_hotkey_handle = None
                self.status_var.set(f"热键 {key_display(self.right_hotkey)} 注册失败：{exc}")'''

new_reg = old_reg + '''
        # F9 开始录制 / F11 回放
        try:
            self._macro_f9_handle = keyboard.add_hotkey("f9", lambda: self.ui_queue.put(("macro_start_rec", None)), suppress=False)
        except Exception:
            self._macro_f9_handle = None
        try:
            self._macro_f11_handle = keyboard.add_hotkey("f11", lambda: self.ui_queue.put(("macro_start_rep", None)), suppress=False)
        except Exception:
            self._macro_f11_handle = None'''

assert old_reg in content, "Cannot find right_hotkey registration"
content = content.replace(old_reg, new_reg, 1)
print("F9/F11 hotkey registration added")

# 2. Add cleanup for F9/F11 in _unregister_hotkey
old_unreg = '''        self.hotkey_handle = None
        self.right_hotkey_handle = None'''

new_unreg = '''        for h in (getattr(self, "_macro_f9_handle", None),
                  getattr(self, "_macro_f11_handle", None)):
            if h is not None and keyboard is not None:
                try:
                    keyboard.remove_hotkey(h)
                except Exception:
                    pass
        self._macro_f9_handle = None
        self._macro_f11_handle = None
        self.hotkey_handle = None
        self.right_hotkey_handle = None'''

assert old_unreg in content, "Cannot find unregister cleanup"
content = content.replace(old_unreg, new_unreg, 1)
print("F9/F11 cleanup added")

# 3. Add message handlers for F9/F11
if "macro_start_rec" not in content:
    old_handler = '''        elif kind == "key":
            self._handle_key_captured(message[1], message[2])'''
    new_handler = old_handler + '''
        elif kind == "macro_start_rec":
            self._macro_start_record()
        elif kind == "macro_start_rep":
            self._macro_start_replay()'''
    assert old_handler in content, "Cannot find key handler"
    content = content.replace(old_handler, new_handler, 1)
    print("F9/F11 message handlers added")
else:
    print("F9/F11 message handlers already present")

# Verify
for kw in ["_macro_f9_handle", "_macro_f11_handle", "macro_start_rec", "macro_start_rep"]:
    assert kw in content, f"Missing: {kw}"
print("All checks passed")

# Syntax check
tmp = tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w", encoding="utf-8")
tmp.write(content)
tmp.close()
try:
    py_compile.compile(tmp.name, doraise=True)
    print("Syntax OK")
except py_compile.PyCompileError as e:
    print(f"Syntax FAILED: {e}")
    os.unlink(tmp.name)
    raise
os.unlink(tmp.name)

with open(PATH, "w", encoding="utf-8") as f:
    f.write(content)
print("Saved!")
