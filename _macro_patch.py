# -*- coding: utf-8 -*-
"""
将宏录制/回放功能整合到 auto_clicker.py
"""

import re

PATH = r"C:\Users\A\Documents\Codex\auto-clicker\outputs\auto_clicker.py"

with open(PATH, "r", encoding="utf-8") as f:
    content = f.read()

original_len = len(content)

# ================================================================
# 1. 在 SendInput 块末尾、高 DPI 函数之前，添加低级鼠标钩子结构体
# ================================================================
HOOK_BLOCK = """

# --- 低级鼠标钩子（用于宏录制，捕获鼠标移动增量）---
WH_MOUSE_LL = 14
WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_RBUTTONDOWN = 0x0204
WM_RBUTTONUP = 0x0205
WM_MBUTTONDOWN = 0x0207
WM_MBUTTONUP = 0x0208
WM_MOUSEWHEEL = 0x020A

HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_int, ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM)
SetWindowsHookEx = user32.SetWindowsHookExW
UnhookWindowsHookEx = user32.UnhookWindowsHookEx
CallNextHookEx = user32.CallNextHookEx
GetMessageW = user32.GetMessageW
PostThreadMessage = user32.PostThreadMessage
WM_QUIT = 0x0012

MACRO_SCRIPTS_NAME = "macro_scripts.json"
MACRO_SCRIPTS_PATH = os.path.join(APP_DIR, MACRO_SCRIPTS_NAME)
"""

# Insert before the DPI awareness comment
anchor = "# \u2500\u2500 \u9ad8 DPI \u9002\u914d"
assert anchor in content, "Cannot find DPI comment anchor"
content = content.replace(anchor, HOOK_BLOCK.lstrip("\n") + "\n" + anchor, 1)
print("Step 1: Low-level hook structures added")

# ================================================================
# 2. 在 __init__ 中添加录制/回放状态变量
# ================================================================
old_init_running = "        self.running = False"
new_init_running = """        self.running = False

        # \u2500\u2500 \u5b8f\u5f55\u5236/\u56de\u653e\u72b6\u6001 \u2500\u2500
        self.macro_recording = False
        self.macro_replaying = False
        self.macro_events = []
        self.macro_scripts = self._load_macro_scripts()
        self._macro_record_start = 0.0
        self._macro_hotkey_ts = 0.0
        self._macro_mouse_hook = None
        self._macro_kb_hook = None
        self._macro_hook_thread = None
        self._macro_skip_kb = False"""
assert old_init_running in content, "Cannot find self.running = False in __init__"
content = content.replace(old_init_running, new_init_running, 1)
print("Step 2: Recording state variables added to __init__")

# ================================================================
# 3. 在 _build_ui 中添加宏面板（状态栏之前）
# ================================================================
MACRO_PANEL = """
        # \u2500\u2500 \u5b8f\u5f55\u5236\u9762\u677f \u2500\u2500
        macro_bar = ttk.LabelFrame(self.root, text="\u5b8f\u5f55\u5236\u4e0e\u56de\u653e")
        macro_bar.pack(fill=tk.X, padx=8, pady=(6, 2))

        macro_top = ttk.Frame(macro_bar)
        macro_top.pack(fill=tk.X, padx=6, pady=(4, 2))
        self.btn_macro_record = ttk.Button(macro_top, text="\u23fa \u5f55\u5236 (F9)", width=12,
                                           command=self._macro_start_record)
        self.btn_macro_record.pack(side=tk.LEFT, padx=3)
        self.btn_macro_stop_rec = ttk.Button(macro_top, text="\u23f9 \u505c\u6b62\u5f55\u5236 (F10)", width=14,
                                             command=self._macro_stop_record, state=tk.DISABLED)
        self.btn_macro_stop_rec.pack(side=tk.LEFT, padx=3)
        self.btn_macro_replay = ttk.Button(macro_top, text="\u25b6 \u56de\u653e (F11)", width=12,
                                           command=self._macro_start_replay)
        self.btn_macro_replay.pack(side=tk.LEFT, padx=3)
        self.btn_macro_stop_rep = ttk.Button(macro_top, text="\u23f9 \u505c\u6b62\u56de\u653e", width=12,
                                             command=self._macro_stop_replay, state=tk.DISABLED)
        self.btn_macro_stop_rep.pack(side=tk.LEFT, padx=3)
        ttk.Button(macro_top, text="\u5220\u9664\u811a\u672c", width=10,
                   command=self._macro_delete_script).pack(side=tk.LEFT, padx=3)

        macro_bot = ttk.Frame(macro_bar)
        macro_bot.pack(fill=tk.X, padx=6, pady=(2, 4))
        ttk.Label(macro_bot, text="\u811a\u672c\u5217\u8868\uff1a").pack(side=tk.LEFT)
        self.macro_list_var = tk.StringVar()
        self.macro_listbox = tk.Listbox(macro_bot, listvariable=self.macro_list_var,
                                        height=3, selectmode=tk.SINGLE, exportselection=False)
        self.macro_listbox.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        self._macro_refresh_list()

        macro_loop = ttk.Frame(macro_bar)
        macro_loop.pack(fill=tk.X, padx=6, pady=(0, 4))
        ttk.Label(macro_loop, text="\u5faa\u73af\u6b21\u6570\uff1a").pack(side=tk.LEFT)
        self.macro_loop_var = tk.StringVar(value="1")
        ttk.Entry(macro_loop, textvariable=self.macro_loop_var, width=5).pack(side=tk.LEFT, padx=4)
        ttk.Label(macro_loop, text="\u6bcf\u6b21\u56de\u653e\u524d\u968f\u673a\u5ef6\u8fdf 0.1~0.5s\uff0c\u6bcf\u6b21\u64cd\u4f5c\u52a0 \u00b15-10% \u6ce2\u52a8").pack(
            side=tk.LEFT, padx=8)
"""

# Insert before the status bar section
status_anchor = "        # \u72b6\u6001\u680f"
assert status_anchor in content, "Cannot find status bar anchor"
content = content.replace(status_anchor, MACRO_PANEL + "\n" + status_anchor, 1)
print("Step 3: Macro UI panel added")

# ================================================================
# 4. 添加宏录制/回放的核心方法（在 _on_close 之前）
# ================================================================
MACRO_METHODS = """

    # \u2500\u2500 \u5b8f\u811a\u672c\u6301\u4e45\u5316 \u2500\u2500
    def _load_macro_scripts(self):
        try:
            with open(MACRO_SCRIPTS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_macro_scripts(self):
        try:
            with open(MACRO_SCRIPTS_PATH, "w", encoding="utf-8") as f:
                json.dump(self.macro_scripts, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _macro_refresh_list(self):
        names = list(self.macro_scripts.keys())
        self.macro_list_var.set(names)

    # \u2500\u2500 \u5b8f\u5f55\u5236 \u2500\u2500
    def _macro_start_record(self):
        if self.macro_recording or self.macro_replaying:
            return
        self.macro_recording = True
        self.macro_events = []
        self._macro_record_start = time.time()
        self.btn_macro_record.config(state=tk.DISABLED)
        self.btn_macro_stop_rec.config(state=tk.NORMAL)
        self.btn_macro_replay.config(state=tk.DISABLED)
        self.status_var.set("\u5b8f\u5f55\u5236\u4e2d...\u64cd\u4f5c\u5b8c\u6210\u540e\u6309 F10 \u505c\u6b62")
        # \u542f\u52a8\u952e\u76d8\u94a9\u5b50
        if keyboard is not None:
            self._macro_kb_hook = keyboard.hook(self._on_macro_kb_event)
        # \u542f\u52a8\u9f20\u6807\u94a9\u5b50\u7ebf\u7a0b
        self._start_mouse_hook()
        # \u6ce8\u518c F10 \u505c\u6b62\u5f55\u5236\u70ed\u952e
        self._macro_stop_handle = keyboard.add_hotkey("f10", self._macro_stop_record_hotkey, suppress=False)

    def _macro_stop_record_hotkey(self):
        self._macro_hotkey_ts = time.time()
        self._macro_skip_kb = True
        self.ui_queue.put(("macro_stop_rec", None))

    def _macro_stop_record(self):
        if not self.macro_recording:
            return
        self.macro_recording = False
        # \u5378\u8f7d\u94a9\u5b50
        if keyboard is not None and self._macro_kb_hook is not None:
            try:
                keyboard.unhook(self._macro_kb_hook)
            except Exception:
                pass
            self._macro_kb_hook = None
        self._stop_mouse_hook()
        # \u5378\u8f7d F10 \u70ed\u952e
        try:
            keyboard.remove_hotkey(self._macro_stop_handle)
        except Exception:
            pass
        if not self.macro_events:
            self.status_var.set("\u5f55\u5236\u4e3a\u7a7a\uff0c\u672a\u4fdd\u5b58")
            self.btn_macro_record.config(state=tk.NORMAL)
            self.btn_macro_stop_rec.config(state=tk.DISABLED)
            self.btn_macro_replay.config(state=tk.NORMAL)
            return
        # \u5f39\u7a97\u547d\u540d
        name = simpledialog.askstring("\u4fdd\u5b58\u5b8f\u811a\u672c", "\u8bf7\u8f93\u5165\u811a\u672c\u540d\u79f0\uff1a",
                                      parent=self.root)
        if not name or not name.strip():
            self.status_var.set("\u5f55\u5236\u5df2\u53d6\u6d88\uff0c\u672a\u4fdd\u5b58")
            self.btn_macro_record.config(state=tk.NORMAL)
            self.btn_macro_stop_rec.config(state=tk.DISABLED)
            self.btn_macro_replay.config(state=tk.NORMAL)
            return
        name = name.strip()
        duration = self.macro_events[-1]["t"] if self.macro_events else 0
        self.macro_scripts[name] = {
            "duration": round(duration, 2),
            "events": self.macro_events,
        }
        self._save_macro_scripts()
        self._macro_refresh_list()
        self.status_var.set(f"\u5f55\u5236\u5b8c\u6210\uff1a{name} ({len(self.macro_events)} \u4e8b\u4ef6, {duration:.1f}s)")
        self.btn_macro_record.config(state=tk.NORMAL)
        self.btn_macro_stop_rec.config(state=tk.DISABLED)
        self.btn_macro_replay.config(state=tk.NORMAL)

    def _on_macro_kb_event(self, event):
        # \u7528\u4e8e\u5b8f\u5f55\u5236\u7684\u952e\u76d8\u4e8b\u4ef6\u56de\u8c03
        if not self.macro_recording:
            return
        # \u8df3\u8fc7\u70ed\u952e\u89e6\u53d1\u7684\u4e8b\u4ef6\uff08\u6301\u7eed 100ms\uff09
        if self._macro_skip_kb and (time.time() - self._macro_hotkey_ts) < 0.1:
            return
        self._macro_skip_kb = False
        if event.event_type not in ("down", "up"):
            return
        t = time.time() - self._macro_record_start
        self.macro_events.append({
            "t": round(t, 4),
            "type": "key_" + event.event_type,
            "key": event.name,
        })

    def _start_mouse_hook(self):
        if self._macro_hook_thread is not None:
            return
        self._macro_hook_stop = threading.Event()
        self._macro_hook_thread = threading.Thread(target=self._mouse_hook_worker, daemon=True)
        self._macro_hook_thread.start()

    def _stop_mouse_hook(self):
        if self._macro_hook_thread is None:
            return
        self._macro_hook_stop.set()
        # \u53d1\u9001 WM_QUIT \u8ba9\u6d88\u606f\u5faa\u73af\u9000\u51fa
        if self._macro_hook_tid:
            PostThreadMessage(self._macro_hook_tid, WM_QUIT, 0, 0)
        if self._macro_mouse_hook:
            UnhookWindowsHookEx(self._macro_mouse_hook)
            self._macro_mouse_hook = None
        self._macro_hook_thread.join(timeout=2)
        self._macro_hook_thread = None

    def _mouse_hook_worker(self):
        self._macro_hook_tid = ctypes.windll.kernel32.GetCurrentThreadId()
        self._macro_prev_x = None
        self._macro_prev_y = None
        self._macro_mouse_hook = SetWindowsHookEx(WH_MOUSE_LL, self._mouse_hook_cb,
                                                   ctypes.windll.kernel32.GetModuleHandleW(None), 0)
        if not self._macro_mouse_hook:
            return
        msg = ctypes.wintypes.MSG()
        while not self._macro_hook_stop.is_set():
            ret = GetMessageW(ctypes.byref(msg), None, 0, 0)
            if ret <= 0:
                break

    def _mouse_hook_cb(self, nCode, wParam, lParam):
        if nCode >= 0 and self.macro_recording:
            t = time.time() - self._macro_record_start
            pt = ctypes.cast(lParam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents.pt
            if wParam == WM_MOUSEMOVE:
                if self._macro_prev_x is not None:
                    dx = pt.x - self._macro_prev_x
                    dy = pt.y - self._macro_prev_y
                    if dx != 0 or dy != 0:
                        self.macro_events.append({
                            "t": round(t, 4), "type": "mouse_move",
                            "dx": dx, "dy": dy,
                        })
                self._macro_prev_x = pt.x
                self._macro_prev_y = pt.y
            elif wParam in (WM_LBUTTONDOWN, WM_LBUTTONUP):
                btn = "left"
                action = "down" if wParam == WM_LBUTTONDOWN else "up"
                self.macro_events.append({
                    "t": round(t, 4), "type": "mouse_btn",
                    "btn": btn, "action": action,
                })
            elif wParam in (WM_RBUTTONDOWN, WM_RBUTTONUP):
                btn = "right"
                action = "down" if wParam == WM_RBUTTONDOWN else "up"
                self.macro_events.append({
                    "t": round(t, 4), "type": "mouse_btn",
                    "btn": btn, "action": action,
                })
            elif wParam == WM_MOUSEWHEEL:
                delta = ctypes.cast(lParam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents.mouseData
                delta = ctypes.c_short(delta >> 16).value
                self.macro_events.append({
                    "t": round(t, 4), "type": "mouse_wheel",
                    "delta": delta,
                })
        return CallNextHookEx(self._macro_mouse_hook, nCode, wParam, lParam)

    # \u2500\u2500 \u5b8f\u56de\u653e \u2500\u2500
    def _macro_start_replay(self):
        if self.macro_recording or self.macro_replaying:
            return
        sel = self.macro_listbox.curselection()
        if not sel:
            messagebox.showinfo(APP_NAME, "\u8bf7\u5148\u5728\u811a\u672c\u5217\u8868\u9009\u62e9\u4e00\u4e2a\u811a\u672c\u3002", parent=self.root)
            return
        name = self.macro_listbox.get(sel[0])
        script = self.macro_scripts.get(name)
        if not script or not script.get("events"):
            messagebox.showwarning(APP_NAME, "\u811a\u672c\u4e3a\u7a7a\u6216\u4e0d\u5b58\u5728\u3002", parent=self.root)
            return
        try:
            loops = max(1, int(self.macro_loop_var.get()))
        except ValueError:
            loops = 1
        self.macro_replaying = True
        self.btn_macro_record.config(state=tk.DISABLED)
        self.btn_macro_replay.config(state=tk.DISABLED)
        self.btn_macro_stop_rep.config(state=tk.NORMAL)
        self._macro_stop_replay_flag = False
        self._macro_replay_thread = threading.Thread(
            target=self._macro_replay_worker,
            args=(script["events"], loops), daemon=True)
        self._macro_replay_thread.start()

    def _macro_stop_replay(self):
        self._macro_stop_replay_flag = True
        self.macro_replaying = False
        self.btn_macro_record.config(state=tk.NORMAL)
        self.btn_macro_replay.config(state=tk.NORMAL)
        self.btn_macro_stop_rep.config(state=tk.DISABLED)
        self.status_var.set("\u56de\u653e\u5df2\u505c\u6b62")

    def _macro_replay_worker(self, events, loops):
        try:
            self.ui_queue.put(("status", "\u56de\u653e\u5f00\u59cb\uff0c\u5171 " + str(loops) + " \u8f6e"))
            for loop_i in range(loops):
                if self._macro_stop_replay_flag:
                    break
                if loop_i > 0:
                    # \u8f6e\u6b21\u95f4\u968f\u673a\u5ef6\u8fdf
                    time.sleep(random.uniform(0.1, 0.5))
                self.ui_queue.put(("status",
                    f"\u56de\u653e\u7b2c {loop_i+1}/{loops} \u8f6e"))
                self._macro_replay_events(events)
            if not self._macro_stop_replay_flag:
                self.ui_queue.put(("status", "\u56de\u653e\u5b8c\u6210"))
        finally:
            self.macro_replaying = False
            self.ui_queue.put(("macro_replay_done", None))

    def _macro_replay_events(self, events):
        if not events:
            return
        start = time.time()
        prev_x = None
        prev_y = None
        for i, ev in enumerate(events):
            if self._macro_stop_replay_flag:
                break
            # \u7b49\u5f85\u5230\u4e8b\u4ef6\u65f6\u95f4\u70b9\uff08\u52a0\u968f\u673a\u6ce2\u52a8\uff09
            jitter = random.uniform(0.90, 1.10)
            target_time = ev["t"] * jitter
            now = time.time() - start
            if target_time > now:
                time.sleep(target_time - now)

            etype = ev["type"]
            if etype == "mouse_move":
                dx = ev["dx"] + random.randint(-1, 1)
                dy = ev["dy"] + random.randint(-1, 1)
                _send_mouse_input(MOUSEEVENTF_MOVE, dx=dx, dy=dy)
            elif etype == "mouse_btn":
                btn = ev["btn"]
                action = ev["action"]
                if btn == "left":
                    flag = MOUSEEVENTF_LEFTDOWN if action == "down" else MOUSEEVENTF_LEFTUP
                elif btn == "right":
                    flag = MOUSEEVENTF_RIGHTDOWN if action == "down" else MOUSEEVENTF_RIGHTUP
                else:
                    continue
                _send_mouse_input(flag)
            elif etype == "mouse_wheel":
                _send_mouse_input(MOUSEEVENTF_WHEEL, data=ev["delta"])
            elif etype in ("key_down", "key_up"):
                if keyboard is None:
                    continue
                key = ev["key"]
                try:
                    if etype == "key_down":
                        keyboard.press(key)
                    else:
                        keyboard.release(key)
                except Exception:
                    pass

    # \u2500\u2500 \u5b8f\u811a\u672c\u7ba1\u7406 \u2500\u2500
    def _macro_delete_script(self):
        sel = self.macro_listbox.curselection()
        if not sel:
            messagebox.showinfo(APP_NAME, "\u8bf7\u5148\u9009\u62e9\u8981\u5220\u9664\u7684\u811a\u672c\u3002", parent=self.root)
            return
        name = self.macro_listbox.get(sel[0])
        if not messagebox.askyesno(APP_NAME, f"\u786e\u5b9a\u5220\u9664\u811a\u672c\u300c{name}\u300d\uff1f", parent=self.root):
            return
        self.macro_scripts.pop(name, None)
        self._save_macro_scripts()
        self._macro_refresh_list()
        self.status_var.set(f"\u5df2\u5220\u9664\u811a\u672c\uff1a{name}")
"""

# Insert before _on_close
close_anchor = "    def _on_close(self):"
assert close_anchor in content, "Cannot find _on_close anchor"
content = content.replace(close_anchor, MACRO_METHODS.lstrip("\n") + "\n" + close_anchor, 1)
print("Step 4: Macro recording/replay methods added")

# ================================================================
# 5. 在 _handle_message 中添加新的消息类型
# ================================================================
old_handle_key = """        elif kind == "key":
            self._handle_key_captured(message[1], message[2])"""
new_handle_key = """        elif kind == "key":
            self._handle_key_captured(message[1], message[2])
        elif kind == "macro_stop_rec":
            self._macro_stop_record()
        elif kind == "macro_replay_done":
            self.macro_replaying = False
            self.btn_macro_record.config(state=tk.NORMAL)
            self.btn_macro_replay.config(state=tk.NORMAL)
            self.btn_macro_stop_rep.config(state=tk.DISABLED)"""
assert old_handle_key in content, "Cannot find key handler in _handle_message"
content = content.replace(old_handle_key, new_handle_key, 1)
print("Step 5: New message types added to _handle_message")

# ================================================================
# 6. 在 _on_close 中添加宏录制清理
# ================================================================
old_close_running = "            self.running = False"
new_close_running = """            self.running = False
            # \u6e05\u7406\u5b8f\u5f55\u5236/\u56de\u653e
            self._macro_stop_replay_flag = True
            self.macro_recording = False
            self._stop_mouse_hook()"""
assert old_close_running in content, "Cannot find cleanup in _on_close"
content = content.replace(old_close_running, new_close_running, 1)
print("Step 6: Cleanup added to _on_close")

# ================================================================
# 7. 添加 MSLLHOOKSTRUCT 和 MOUSEEVENTF_WHEEL 常量
# ================================================================
# MSLLHOOKSTRUCT in the hook block
MSLLHOOK_BLOCK = """
class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ('pt', ctypes.wintypes.POINT),
        ('mouseData', ctypes.wintypes.DWORD),
        ('flags', ctypes.wintypes.DWORD),
        ('time', ctypes.wintypes.DWORD),
        ('dwExtraInfo', ctypes.POINTER(ctypes.c_ulong)),
    ]
"""

WHEEL_CONST = "MOUSEEVENTF_WHEEL = 0x0800\n"

# Insert MSLLHOOKSTRUCT after HOOKPROC line
hookproc_line = "HOOKPROC = ctypes.WINFUNCTYPE"
assert hookproc_line in content, "Cannot find HOOKPROC"
# Find the HOOKPROC line and insert after it
lines = content.split("\n")
for i, line in enumerate(lines):
    if hookproc_line in line:
        # Insert MSLLHOOKSTRUCT and MOUSEEVENTF_WHEEL after this line
        insert_lines = MSLLHOOK_BLOCK.strip().split("\n") + ["", WHEEL_CONST.strip()]
        for j, ins in enumerate(insert_lines):
            lines.insert(i + 1 + j, ins)
        content = "\n".join(lines)
        break
print("Step 7: MSLLHOOKSTRUCT and MOUSEEVENTF_WHEEL added")

# ================================================================
# 8. 初始化 _macro_hook_tid 和 _macro_stop_replay_flag
# ================================================================
old_right_thread = "        self.right_thread = None"
new_right_thread = """        self.right_thread = None
        self._macro_hook_tid = None
        self._macro_stop_replay_flag = False
        self._macro_stop_handle = None"""
assert old_right_thread in content, "Cannot find right_thread init"
content = content.replace(old_right_thread, new_right_thread, 1)
print("Step 8: Additional init vars added")

# ================================================================
# 验证并保存
# ================================================================
checks = [
    "MSLLHOOKSTRUCT",
    "MOUSEEVENTF_WHEEL",
    "_macro_start_record",
    "_macro_stop_record",
    "_macro_start_replay",
    "_macro_stop_replay",
    "_macro_replay_worker",
    "_macro_replay_events",
    "_mouse_hook_cb",
    "_mouse_hook_worker",
    "_load_macro_scripts",
    "_save_macro_scripts",
    "_macro_delete_script",
    "_macro_refresh_list",
    "MACRO_SCRIPTS_PATH",
    "_macro_hotkey_ts",
    "_macro_skip_kb",
    "macro_stop_rec",
    "macro_replay_done",
]
for kw in checks:
    assert kw in content, f"Missing: {kw}"
print("All verifications passed!")

# 确保没有语法错误
import py_compile, tempfile, os
tmp = tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w", encoding="utf-8")
tmp.write(content)
tmp.close()
try:
    py_compile.compile(tmp.name, doraise=True)
    print("Syntax check PASSED")
except py_compile.PyCompileError as e:
    print(f"Syntax check FAILED: {e}")
    os.unlink(tmp.name)
    raise
os.unlink(tmp.name)

with open(PATH, "w", encoding="utf-8") as f:
    f.write(content)
print(f"File saved! ({original_len} -> {len(content)} chars)")
