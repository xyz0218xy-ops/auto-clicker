import re

with open(r'C:\Users\A\Documents\Codex\auto-clicker\outputs\auto_clicker.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 问题1: _send_mouse_input 中绝对坐标需要归一化，但 mouse_click_left 和 human_move_to 传的是像素坐标
# 修复: 在 human_move_to 和 mouse_click_left 中，将像素坐标转换为 SendInput 绝一坐标 (0-65535)

# 修改 human_move_to 函数，将像素坐标转为归一化坐标
old_human_move = '''def human_move_to(target_x, target_y, duration=None):
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
    curve = _bezier_curve(
        (cur_x, cur_y), (ctrl1_x, ctrl1_y),
        (ctrl2_x, ctrl2_y), (target_x, target_y), steps
    )
    interval = duration / len(curve)
    for i, (px, py) in enumerate(curve):
        if i > len(curve) * 0.7:
            px += random.uniform(-1, 1)
            py += random.uniform(-1, 1)
        _send_mouse_input(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, dx=px, dy=py)
        time.sleep(interval * random.uniform(0.8, 1.2))
    _send_mouse_input(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, dx=target_x, dy=target_y)'''

new_human_move = '''def _pixel_to_abs(x, y):
    """将像素坐标转换为 SendInput 绝一坐标 (0-65535)。"""
    sw = user32.GetSystemMetrics(0)  # SM_CXSCREEN
    sh = user32.GetSystemMetrics(1)  # SM_CYSCREEN
    if sw <= 0: sw = 1920
    if sh <= 0: sh = 1080
    return int(x * 65535 / sw), int(y * 65535 / sh)


def human_move_to(target_x, target_y, duration=None):
    """贝塞尔曲线移动鼠标到目标像素坐标，SendInput 内部自动归一化。"""
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
    curve = _bezier_curve(
        (cur_x, cur_y), (ctrl1_x, ctrl1_y),
        (ctrl2_x, ctrl2_y), (target_x, target_y), steps
    )
    interval = duration / len(curve)
    for i, (px, py) in enumerate(curve):
        if i > len(curve) * 0.7:
            px += random.uniform(-1, 1)
            py += random.uniform(-1, 1)
        ax, ay = _pixel_to_abs(px, py)
        _send_mouse_input(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, dx=ax, dy=ay)
        time.sleep(interval * random.uniform(0.8, 1.2))
    ax, ay = _pixel_to_abs(target_x, target_y)
    _send_mouse_input(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, dx=ax, dy=ay)'''

assert old_human_move in content, "Cannot find old human_move_to"
content = content.replace(old_human_move, new_human_move, 1)
print("Step 1: human_move_to fixed with pixel-to-abs conversion")

# 验证
assert '_pixel_to_abs' in content
assert 'GetSystemMetrics' in content
print("All checks passed!")

with open(r'C:\Users\A\Documents\Codex\auto-clicker\outputs\auto_clicker.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("File saved!")
