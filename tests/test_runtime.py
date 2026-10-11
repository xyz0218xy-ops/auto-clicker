import json
import os
import queue
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "outputs"))
import auto_clicker
import count_mode


class RuntimeTests(unittest.TestCase):
    def test_new_vision_and_pending_fields_are_migrated(self):
        profile = auto_clicker.normalize_profile({
            "count_target": 5,
            "count_progress": 2,
            "vision_deadline_ms": 5000,
            "confirm_reads": 1,
            "pending_action_id": "abc",
            "pending_before": "7",
        })
        self.assertEqual(profile["vision_deadline_ms"], 1000)
        self.assertEqual(profile["confirm_reads"], 2)
        self.assertEqual(profile["pending_before"], 7)
        recovered, changed = auto_clicker.recover_pending_profile(profile)
        self.assertTrue(changed)
        self.assertEqual(recovered["count_progress"], 3)
        self.assertIsNone(recovered["pending_action_id"])
        recovered_again, changed_again = auto_clicker.recover_pending_profile(recovered)
        self.assertFalse(changed_again)
        self.assertEqual(recovered_again["count_progress"], 3)

    def test_vision_backend_requires_two_consistent_frames(self):
        backend = count_mode.VisionBackend(deadline_ms=850)
        images = [object(), object(), object()]
        readings = iter([3, 4, 4])
        with patch.object(count_mode, "capture_region", side_effect=images), \
                patch.object(count_mode, "read_templates", side_effect=lambda _image: (next(readings), 1)):
            self.assertEqual(backend.read_consistent((0, 0, 10, 10), max_ms=850, reads=2, delay_ms=0), 4)
        self.assertEqual(backend.last_consistent_values, [3, 4, 4])

    def test_vision_backend_timeout_does_not_use_tesseract(self):
        backend = count_mode.VisionBackend(deadline_ms=100)
        with patch.object(count_mode, "capture_region", return_value=object()), \
                patch.object(count_mode, "read_templates", return_value=(None, 0)), \
                patch.object(count_mode, "read_winocr", return_value=None), \
                patch.object(count_mode, "read_rapidocr", return_value=None), \
                patch.object(count_mode, "read_tesseract") as tesseract:
            result = backend.read((0, 0, 10, 10), deadline_ms=100)
        tesseract.assert_not_called()
        self.assertIsNone(result.value)
        self.assertLessEqual(result.elapsed_ms, 250)
    def test_warmup_default_does_not_initialize_rapidocr(self):
        with patch.object(count_mode, "read_rapidocr") as rapid, \
                patch.object(count_mode, "read_winocr", return_value=None), \
                patch.object(count_mode, "_winrt_engine", return_value=None):
            count_mode.warm_up_ocr(backend="template_winocr")
        rapid.assert_not_called()

    def test_vision_monitor_pauses_after_repeated_region_failures(self):
        app = auto_clicker.AutoClicker.__new__(auto_clicker.AutoClicker)
        app.running = True
        app.vision_stop_mode = "left"
        app.vision_stable_samples = 3
        app.vision_poll_interval = 0
        app.vision_deadline_ms = 100
        app.vision_backend = "template_winocr"
        statuses, logs = [], []
        app._set_status = statuses.append
        app._log_debug = logs.append
        app._sleep_interruptible = lambda _seconds: None
        counters = [{"id": "mid", "name": "中间", "region": [10, 20, 30, 12], "threshold": 0, "enabled": True, "primary": True}]
        with patch.object(auto_clicker, "warm_up_ocr"), \
                patch.object(auto_clicker, "read_count_fast", return_value=(None, 100, None)):
            with self.assertRaises(auto_clicker.CountSafetyError):
                app._run_vision_threshold_mode(counters)
        self.assertTrue(any("暂停" in item and "10,20,30,12" in item for item in statuses))
        self.assertTrue(any("连续 3 次识别失败" in item for item in logs))

    def test_bom_config_keeps_existing_profiles(self):
        config = {
            "version": 2,
            "current_profile": "已有方案",
            "profiles": {"已有方案": {"items": [
                {"type": "mouse", "x": 100, "y": 200, "interval": 1.0}
            ]}},
        }
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "click_positions.json")
            with open(path, "w", encoding="utf-8-sig") as output:
                json.dump(config, output, ensure_ascii=False)
            loaded = auto_clicker.load_config(path)

        self.assertEqual(loaded["current_profile"], "已有方案")
        self.assertEqual(len(loaded["profiles"]["已有方案"]["items"]), 1)

    def test_low_level_hotkey_routes_virtual_key_without_focus(self):
        app = auto_clicker.AutoClicker.__new__(auto_clicker.AutoClicker)
        app.hotkey = "f12"
        app.right_hotkey = "f8"
        app.capturing = False
        app._last_hotkey_trigger = {"hotkey": 0.0, "right_hotkey": 0.0}
        calls = []
        app._on_hotkey = lambda: calls.append("hotkey")
        app._on_right_hotkey = lambda: calls.append("right")
        app._handle_low_level_vk(0x7B)
        app._handle_low_level_vk(0x77)
        self.assertEqual(calls, ["hotkey", "right"])

    def test_global_hotkey_backend_registers_outside_focus(self):
        class FakeKeyboard:
            def __init__(self):
                self.added = []
                self.removed = []
            def add_hotkey(self, name, callback, suppress=False):
                self.added.append((name, callback, suppress))
                return len(self.added)
            def remove_hotkey(self, handle):
                self.removed.append(handle)

        fake = FakeKeyboard()
        app = auto_clicker.AutoClicker.__new__(auto_clicker.AutoClicker)
        app.hotkey = "f12"
        app.right_hotkey = "f8"
        app.hotkey_handle = None
        app.right_hotkey_handle = None
        app._win_hotkey_stop = threading.Event()
        app._win_hotkey_thread = None
        app._win_hotkey_worker = lambda stop: stop.wait()
        with patch.object(auto_clicker, "_keyboard", fake), patch.object(auto_clicker, "HAS_GLOBAL_HOTKEY", True):
            app._register_hotkey()
            self.assertEqual([item[0] for item in fake.added], ["f12", "f8"])
            self.assertTrue(all(item[2] is False for item in fake.added))
            app._unregister_hotkey()
        self.assertEqual(fake.removed, [1, 2])

    def test_hotkey_reregistration_stops_previous_worker(self):
        app = auto_clicker.AutoClicker.__new__(auto_clicker.AutoClicker)
        app.hotkey = "f12"
        app.right_hotkey = "f8"
        app.hotkey_handle = None
        app.right_hotkey_handle = None
        app._win_hotkey_stop = threading.Event()
        app._win_hotkey_thread = None
        app._win_hotkey_worker = lambda stop: stop.wait()

        app._register_hotkey()
        previous = app._win_hotkey_thread
        app._register_hotkey()
        self.assertFalse(previous.is_alive())
        self.assertTrue(app._win_hotkey_thread.is_alive())
        app._unregister_hotkey()

    def test_count_wait_requires_stable_reading(self):
        app = auto_clicker.AutoClicker.__new__(auto_clicker.AutoClicker)
        app.running = True
        app.count_open_key = "e"
        app.count_open_wait = 1.5
        app.count_next_cycle_wait = 0.4
        app._set_status = lambda _message: None
        app._sleep_interruptible = lambda _seconds: None
        app._log_debug = lambda _message: None
        with patch.object(auto_clicker, "read_count_fast", side_effect=[
            (None, 0, None), (4, 0, "模板"), (4, 0, "模板")
        ]), patch.object(auto_clicker, "key_tap", return_value=True) as tap:
            self.assertEqual(app._wait_summon_interface((0, 0, 30, 20), None, None), 4)
            tap.assert_called_once_with("e")

    def test_worker_error_is_reported_when_stopped(self):
        app = auto_clicker.AutoClicker.__new__(auto_clicker.AutoClicker)
        app.running = True
        app.ui_queue = queue.Queue()
        app._click_rounds = lambda: (_ for _ in ()).throw(RuntimeError("测试错误"))
        app._log_debug = lambda _message: None

        app._click_loop()

        self.assertFalse(app.running)
        self.assertIn("测试错误", app.ui_queue.get_nowait()[1])


if __name__ == "__main__":
    unittest.main()
