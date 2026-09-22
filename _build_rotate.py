# -*- coding: utf-8 -*-
import py_compile, tempfile, os

SRC = r"C:\Users\A\Documents\Codex\auto-clicker\_orig\auto-clicker-main\outputs\auto_clicker.py"
DST = r"C:\Users\A\Documents\Codex\auto-clicker\outputs\auto_clicker.py"

with open(SRC, "r", encoding="utf-8") as f:
    c = f.read()
print(f"Original: {len(c)} chars")

# 1. SendInput block
BLOCK1 = """
# --- SendInput ---
INPUT_MOUSE = 0
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_WHEEL = 0x0800

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
        t = i / steps
        u = 1 - t
        x = u**3 * p0[0] + 3 * u**2 * t * p1[0] + 3 * u * t**2 * p2[0] + t**3 * p3[0]
        y = u**3 * p0[1] + 3 * u**2 * t * p1[1] + 3 * u * t**2 * p2[1] + t**3 * p3[1]
        points.append((int(x), int(y)))
    return points

def human_move_to(target_x, target_y, duration=None):
    cur_x, cur_y = get_cursor_pos()
    dist = ((target_x - cur_x)**2 + (target_y - cur_y)**2) ** 0.5
    if dist < 2:
        return
    if duration is None:
        duration = min(0.4, max(0.08, dist / 2500.0)) + random.uniform(-0.03, 0.05)
    duration = max(0.04, duration)
    ctrl1_x = cur_x + (target_x - cur_x) * random.uniform(0.2, 0.4) + random.uniform(-20, 20)
    ctrl1_y = cur_y + (target_y - cur_y) * random.uniform(0.1, 0.3) + random.uniform(-20, 20)
    ctrl2_x = cur_x + (target_x - cur_x) * random.uniform(0.6, 0.8) + random.uniform(-15, 15)
    ctrl2_y = cur_y + (target_y - cur_y) * random.uniform(0.7, 0.9) + random.uniform(-15, 15)
    steps = max(5, int(dist / 3))
    curve = _bezier_curve((cur_x, cur_y), (ctrl1_x, ctrl1_y), (ctrl2_x, ctrl2_y), (target_x, target_y), steps)
    interval = duration / len(curve)
    for i, (px, py) in enumerate(curve):
        if i > len(curve) * 0.7:
            px += random.uniform(-1, 1)
            py += random.uniform(-1, 1)
        _send_mouse_input(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, dx=px, dy=py)
        time.sleep(interval * random.uniform(0.8, 1.2))
    _send_mouse_input(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, dx=target_x, dy=target_y)
"""

c = c.replace("MOUSEEVENTF_RIGHTUP = 0x0010\n", "MOUSEEVENTF_RIGHTUP = 0x0010\n" + BLOCK1, 1)
print("Step 1: SendInput block added")

# 2. Rewrite mouse_click_left - use line-based replacement
lines = c.split("\n")
new_lines = []
i = 0
while i < len(lines):
    line = lines[i]
    if "def mouse_click_left(x, y):" in line:
        indent = line[:len(line) - len(line.lstrip())]
        new_lines.append(line)
        new_lines.append(indent + '    """Bezier + SendInput."""')
        new_lines.append(indent + '    offset_x = random.uniform(-2, 2)')
        new_lines.append(indent + '    offset_y = random.uniform(-2, 2)')
        new_lines.append(indent + '    human_move_to(int(x + offset_x), int(y + offset_y))')
        new_lines.append(indent + '    time.sleep(random.uniform(0.01, 0.03))')
        new_lines.append(indent + '    _send_mouse_input(MOUSEEVENTF_LEFTDOWN)')
        new_lines.append(indent + '    time.sleep(random.uniform(0.04, 0.08))')
        new_lines.append(indent + '    _send_mouse_input(MOUSEEVENTF_LEFTUP)')
        # Skip old body (next 5 lines)
        i += 6  # skip docstring + SetCursorPos + sleep + mouse_event*2
        continue
    new_lines.append(line)
    i += 1
c = "\n".join(new_lines)
print("Step 2: mouse_click_left rewritten")

# 3. mouse_right_down/up
c = c.replace("def mouse_right_down():\n    user32.mouse_event(MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0)", "def mouse_right_down():\n    _send_mouse_input(MOUSEEVENTF_RIGHTDOWN)", 1)
c = c.replace("def mouse_right_up():\n    user32.mouse_event(MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)", "def mouse_right_up():\n    _send_mouse_input(MOUSEEVENTF_RIGHTUP)", 1)
print("Step 3: right down/up rewritten")

# 4. right_hold_loop - use line-based replacement to avoid encoding issues
lines = c.split("\n")
new_lines = []
i = 0
while i < len(lines):
    line = lines[i]
    if "def _right_hold_loop(self):" in line:
        indent = line[:len(line) - len(line.lstrip())]
        new_lines.append(line)
        new_lines.append(indent + '        while self.right_held:')
        new_lines.append(indent + '            mouse_right_down()')
        new_lines.append(indent + '            time.sleep(random.uniform(0.03, 0.08))')
        # Skip old body (4 lines: comment + while + mouse_right_down + time.sleep)
        i += 4
        continue
    new_lines.append(line)
    i += 1
c = "\n".join(new_lines)
print("Step 4: right_hold_loop rewritten")

# 5. Add rotation state vars in __init__
c = c.replace(
    "        self.running = False\n        self.click_thread = None",
    """        self.running = False

        # Rotation state
        self.rotate_calibrating = False
        self.rotate_calib_events = []
        self.rotate_sensitivity = 0
        self._rotate_hook = None
        self._rotate_hook_thread = None
        self._rotate_hook_tid = None
        self._rotate_hook_stop = None
        self._rotate_hotkey_name = "f8"
        self._rotate_hotkey_handle = None

        self.click_thread = None""", 1)
print("Step 5: Rotation state vars added")

# 6. Load calibration on startup
c = c.replace(
    "        self.root.after(60, self._pump_queue)",
    "        self._load_rotate_calibration()\n        self.root.after(60, self._pump_queue)", 1)
print("Step 6: Load calibration added")

# 7. Add rotation UI before option_bar
ROTATE_UI = """        # Rotation panel
        rotate_bar = ttk.LabelFrame(self.root, text="View Rotation")
        rotate_bar.pack(fill=tk.X, padx=8, pady=(4, 2))
        rotate_row1 = ttk.Frame(rotate_bar)
        rotate_row1.pack(fill=tk.X, padx=6, pady=(4, 2))
        self.rotate_sens_label = ttk.Label(rotate_row1, text="Not calibrated", width=20)
        self.rotate_sens_label.pack(side=tk.LEFT, padx=4)
        ttk.Button(rotate_row1, text="Calibrate 180", width=12,
                   command=self._start_rotate_calibration).pack(side=tk.LEFT, padx=3)
        ttk.Button(rotate_row1, text="Reset", width=8,
                   command=self._reset_rotate_calibration).pack(side=tk.LEFT, padx=3)
        ttk.Label(rotate_row1, text="Angle:").pack(side=tk.LEFT, padx=(12, 0))
        self.rotate_angle_var = tk.StringVar(value="180")
        ttk.Combobox(rotate_row1, textvariable=self.rotate_angle_var,
                     values=["90", "180", "360"], width=6, state="readonly").pack(side=tk.LEFT, padx=4)
        ttk.Button(rotate_row1, text="Turn", width=8,
                   command=self._do_rotate).pack(side=tk.LEFT, padx=(12, 3))

"""
c = c.replace(
    "        option_bar = ttk.Frame(self.root)",
    ROTATE_UI + "        option_bar = ttk.Frame(self.root)", 1)
print("Step 7: Rotation UI added")

# 8. Add rotation methods before _on_close
ROTATE_METHODS = """
    # --- Rotation ---
    def _load_rotate_calibration(self):
        try:
            path = os.path.join(APP_DIR, "rotate_calibration.json")
            if os.path.isfile(path):
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.rotate_sensitivity = int(data.get("sensitivity", 0))
                if self.rotate_sensitivity > 0:
                    self.rotate_sens_label.config(text=f"Cal: {self.rotate_sensitivity} px/180d")
        except Exception:
            pass

    def _save_rotate_calibration(self):
        try:
            path = os.path.join(APP_DIR, "rotate_calibration.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"sensitivity": self.rotate_sensitivity}, f)
        except Exception:
            pass

    def _start_rotate_calibration(self):
        if self.rotate_calibrating:
            return
        messagebox.showinfo("Calibration", "Click OK, then move mouse to rotate view 180 degrees right.\\nPress any key when done.", parent=self.root)
        self.rotate_calibrating = True
        self.rotate_calib_events = []
        self.rotate_calib_start = time.time()
        self.rotate_sens_label.config(text="Calibrating...")
        self._start_rotate_hook()
        if keyboard is not None:
            self._rotate_kb_hook = keyboard.hook(self._on_rotate_calib_key)

    def _on_rotate_calib_key(self, event):
        if not self.rotate_calibrating:
            return
        self.rotate_calibrating = False
        if keyboard is not None:
            try:
                keyboard.unhook(self._rotate_kb_hook)
            except Exception:
                pass
        self._stop_rotate_hook()
        total_dx = sum(abs(e.get("dx", 0)) for e in self.rotate_calib_events if e.get("type") == "move")
        if total_dx < 50:
            messagebox.showwarning("Calibration", "Too short, try again.", parent=self.root)
            self.rotate_sens_label.config(text="Not calibrated")
            return
        self.rotate_sensitivity = total_dx
        self._save_rotate_calibration()
        self.rotate_sens_label.config(text=f"Cal: {total_dx} px/180d")
        messagebox.showinfo("Done", f"180d = {total_dx} px mouse delta. Use button or F8 to rotate.", parent=self.root)

    def _reset_rotate_calibration(self):
        self.rotate_sensitivity = 0
        self._save_rotate_calibration()
        self.rotate_sens_label.config(text="Not calibrated")

    def _start_rotate_hook(self):
        if self._rotate_hook_thread is not None:
            return
        self._rotate_hook_stop = threading.Event()
        self._rotate_hook_thread = threading.Thread(target=self._rotate_hook_worker, daemon=True)
        self._rotate_hook_thread.start()

    def _stop_rotate_hook(self):
        if self._rotate_hook_thread is None:
            return
        self._rotate_hook_stop.set()
        if self._rotate_hook_tid:
            ctypes.windll.user32.PostThreadMessageW(self._rotate_hook_tid, 0x0012, 0, 0)
        if self._rotate_hook:
            user32.UnhookWindowsHookEx(self._rotate_hook)
            self._rotate_hook = None
        self._rotate_hook_thread.join(timeout=2)
        self._rotate_hook_thread = None

    def _rotate_hook_worker(self):
        self._rotate_hook_tid = ctypes.windll.kernel32.GetCurrentThreadId()
        HOOKPROC_T = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_int, ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM)
        class PT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
        class MSLL(ctypes.Structure):
            _fields_ = [("pt", PT), ("mouseData", ctypes.wintypes.DWORD), ("flags", ctypes.wintypes.DWORD), ("time", ctypes.wintypes.DWORD), ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]
        def _cb(nCode, wParam, lParam):
            if nCode >= 0 and self.rotate_calibrating and wParam == 0x0200:
                s = ctypes.cast(lParam, ctypes.POINTER(MSLL)).contents
                self.rotate_calib_events.append({"type": "move", "dx": s.pt.x, "dy": s.pt.y})
            return user32.CallNextHookEx(self._rotate_hook, nCode, wParam, lParam)
        self._rotate_cb_ref = HOOKPROC_T(_cb)
        self._rotate_hook = user32.SetWindowsHookExW(14, self._rotate_cb_ref, ctypes.windll.kernel32.GetModuleHandleW(None), 0)
        if not self._rotate_hook:
            return
        msg = ctypes.wintypes.MSG()
        while not self._rotate_hook_stop.is_set():
            ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if ret <= 0:
                break

    def _do_rotate(self):
        if self.rotate_sensitivity <= 0:
            messagebox.showwarning("Rotate", "Please calibrate first.", parent=self.root)
            return
        try:
            angle = int(self.rotate_angle_var.get())
        except ValueError:
            angle = 180
        total_dx = int(self.rotate_sensitivity * (angle / 180.0))
        threading.Thread(target=self._rotate_worker, args=(total_dx,), daemon=True).start()

    def _rotate_worker(self, total_dx):
        batches = random.randint(40, 80)
        weights = [random.uniform(0.5, 1.5) for _ in range(batches)]
        w_sum = sum(weights)
        dx_list = [max(1, int(total_dx * w / w_sum)) for w in weights]
        diff = total_dx - sum(dx_list)
        dx_list[-1] += diff
        for i, dx in enumerate(dx_list):
            dy = random.randint(-1, 1)
            _send_mouse_input(MOUSEEVENTF_MOVE, dx=dx, dy=dy)
            if i < batches * 0.3:
                time.sleep(random.uniform(0.002, 0.005))
            elif i > batches * 0.8:
                time.sleep(random.uniform(0.003, 0.006))
            else:
                time.sleep(random.uniform(0.001, 0.003))

    def _register_rotate_hotkey(self):
        if keyboard is None:
            return
        key = getattr(self, "_rotate_hotkey_name", "f8")
        try:
            if self._rotate_hotkey_handle:
                keyboard.remove_hotkey(self._rotate_hotkey_handle)
            self._rotate_hotkey_handle = keyboard.add_hotkey(
                key, lambda: self.ui_queue.put(("rotate", None)), suppress=False)
        except Exception:
            pass

    """
c = c.replace("    def _on_close(self):", ROTATE_METHODS + "    def _on_close(self):", 1)
print("Step 8: Rotation methods added")

# 9. Register rotate hotkey
c = c.replace(
    "    def _unregister_hotkey(self):",
    "        self._register_rotate_hotkey()\n\n    def _unregister_hotkey(self):", 1)
print("Step 9: Rotate hotkey registration")

# 10. Add rotate message handler
c = c.replace(
    '        elif kind == "error":\n            messagebox.showerror(APP_NAME, message[1], parent=self.root)',
    '        elif kind == "error":\n            messagebox.showerror(APP_NAME, message[1], parent=self.root)\n        elif kind == "rotate":\n            self._do_rotate()', 1)
print("Step 10: Rotate message handler")

# 11. Cleanup on close
c = c.replace(
    "            self.running = False\n            self._release_right()",
    "            self.running = False\n            self.rotate_calibrating = False\n            self._stop_rotate_hook()\n            self._release_right()", 1)
print("Step 11: Cleanup added")


# 12. Fix _on_close body indentation
lines = c.split("\n")
new_lines = []
in_on_close = False
i = 0
while i < len(lines):
    line = lines[i]
    stripped = line.lstrip()
    if "def _on_close(self):" in line and line.strip().startswith("def"):
        in_on_close = True
        new_lines.append(line)
        i += 1
        continue
    if in_on_close:
        # Check if we hit the next top-level definition (module-level function or class)
        if (stripped.startswith("def ") and not line.startswith("        ")) or \
           stripped.startswith("class ") or \
           stripped.startswith("if __name__"):
            in_on_close = False
            new_lines.append(line)
            i += 1
            continue
        # Inside _on_close: body should be at 8-space indent (for class method)
        # Currently it's at 8-space (from original) which is correct
        # But we may have over-indented it. Check and fix.
        # The body of _on_close should start with "        try:" (8 spaces)
        # If it's at 12+ spaces, reduce to proper level
        if stripped and not line.startswith("        "):
            # Wrong indentation - fix it
            # Count leading spaces
            const leading = line.length - line.trimStart().length;
            if (leading > 8):
                // Reduce to 8-space base
                new_lines.push("        " + stripped);
            else:
                new_lines.push(line);
        else:
            new_lines.append(line)
        i += 1
        continue
    new_lines.append(line)
    i += 1
c = "\n".join(new_lines)
print("Step 12: _on_close indentation fixed")

with open(DST, "w", encoding="utf-8") as f:
    f.write(c)
print(f"Saved: {len(c)} chars")

py_compile.compile(DST, doraise=True)
print("Syntax OK")
