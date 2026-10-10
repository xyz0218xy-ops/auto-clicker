# v39 修复说明（2026-10-10）

- 修复重新设置热键时旧注册线程未退出的问题，避免热键重复触发或失效。
- 兼容带 UTF-8 BOM 的旧配置文件，避免读取失败后退回空方案，导致启动后立即停止。
- 执行异常会留在状态栏并记录到数据目录的 `debug.log`，便于定位启动后立即停止。
- Boss 卡实时路径采用统一视觉后端：模板匹配 → Windows OCR，默认截止时间 850 ms；RapidOCR 可显式作为第三层，Tesseract 仅保留在人工诊断入口。
- 点击前写入 `pending_action_id`、`pending_before` 和时间戳，点击后必须连续两次识别一致才提交进度；核对超时会暂停，下一次启动按已消耗一次恢复并清除标记。
- 兼容 `rapidocr-onnxruntime` 的离线模型与结果格式，打包时自动收集已安装的 RapidOCR 包。
- 缩小采集列表的字体、行高和序号列宽。
- 新增 `tools/vision_benchmark.py`，支持四类脱敏样本并输出 JSON/CSV 准确率、拒识率、误识别数及 P50/P95 延迟。

## 迁移

将 `AutoClicker-v39.exe` 与原有 `click_positions.json` 放在同一可写目录。若曾做数字模板校准，也复制 `count_templates` 目录。运行 `AutoClicker-v39.exe --selftest` 可在 exe 所在目录生成 `selftest.txt`；执行异常记录在数据目录的 `debug.log`。

本版本不包含加密、反调试或反作弊规避能力，输入事件、测试模式和日志保持可审计。
