# 自动点击器（Windows 鼠标 / 键盘自动化工具）

[![GitHub release](https://img.shields.io/github/v/release/xyz0218xy-ops/auto-clicker?style=flat-square)](https://github.com/xyz0218xy-ops/auto-clicker/releases)
[![GitHub downloads](https://img.shields.io/github/downloads/xyz0218xy-ops/auto-clicker/total?style=flat-square)](https://github.com/xyz0218xy-ops/auto-clicker/releases)

一个用 Python 标准库（tkinter + ctypes）写的桌面自动点击 / 按键工具，打包为单文件 exe，目标电脑不需要安装 Python。

## 下载

**直接下载最新版 exe：** 👉 [AutoClicker-v37.exe](https://github.com/xyz0218xy-ops/auto-clicker/releases/download/v37/AutoClicker-v37.exe)

> 无需安装 Python，建议右键「以管理员身份运行」。历史版本与更新公告见 [Releases 页面](https://github.com/xyz0218xy-ops/auto-clicker/releases)。

当前工作副本为 v40，尚未发布到 GitHub Releases。本地构建产物在 `outputs/dist/AutoClicker-v40.exe`，修复内容见 [release-notes-v40.md](release-notes-v40.md)。

## 功能

- **采集点击**：3 秒倒计时后记录鼠标坐标
- **采集按键**：按下任意键即绑定
- **多方案管理**：新建 / 复制 / 重命名 / 删除
- **按住键**：鼠标右键或任意键盘按键，可由按钮、独立热键或运行同步控制
- **Boss 卡计数模式**：OCR 识别 Boss 卡右下角数量，按设定次数召唤后自动停止
- **进度保存**：计数进度随方案保存，下次启动可继续查看
- **间隔随机化**：默认 0.5 ~ 2.0 倍随机
- **相对偏移**：鼠标项可填相对偏移量
- **轮次间隔**：每轮循环间可单独设置等待
- **数据不丢**：配置存在 exe 同目录
- **全局热键**：默认 F12，可改绑

## 更新日志

详见 [CHANGELOG.md](CHANGELOG.md)

### 当前工作副本 v40 (2026-10-10)
- 兼容带 UTF-8 BOM 的配置文件，避免旧方案被误当成空方案
- 修复热键重新设置后的线程切换，优化 Boss 卡 OCR 等待与错误提示
- 缩小采集列表字号与序号列宽；更新离线 RapidOCR 打包支持
- 实时视觉路径增加统一 `VisionBackend`，默认模板匹配 + Windows OCR，截止时间 850 ms；RapidOCR 仅显式启用，Tesseract 只用于人工诊断
- Boss 卡动作采用 `pending` 两阶段记录：点击前落盘，连续两次识别一致后提交；中断重启自动按已消耗一次结算
- 新增 `tools/vision_benchmark.py`，比较当前后端、OpenCV 模板和可选 MaaFramework 模块，输出 JSON/CSV 延迟与准确率
- 预热按配置只初始化实际使用的视觉后端；默认路径不加载 RapidOCR，Windows OCR 只创建引擎，首次启动等待从约 1 秒降到约 30–40 ms
- 视觉区域连续 3 次识别失败时自动暂停，状态栏和 `debug.log` 写出具体区域坐标，避免无限刷“读取失败”

### GitHub 已发布 v37 (2026-10-07)
- 击杀 Boss 后自动衔接下一轮：持续轮询召唤界面，不再有固定等待，也不再需要停止重启
- 隐藏 Tesseract 识别弹窗，运行过程无黑色控制台闪现
- 拟人化节奏：随机停顿、贝塞尔曲线移动、±2px 抖动、轮询间隔随机化
- 「下一轮」输入框改为「轮询间隔」，默认 1.2 秒
- v36 三层识别、自学习模板、核对防卡死全部保留
- 更新公告详见 [release-notes-v37.md](release-notes-v37.md)

## 快速开始

1. 下载 [AutoClicker-v37.exe](https://github.com/xyz0218xy-ops/auto-clicker/releases/download/v37/AutoClicker-v37.exe)
2. 点「采集点击」→ 3 秒内把鼠标移到目标位置
3. 按 F12 开始 / 停止
4. 建议右键「以管理员身份运行」
5. 使用 Boss 卡计数模式时，先采集数量区域、星级坐标和召唤按钮坐标，再设置目标次数

## 打包

```powershell
py -3.14 -m pip install pyinstaller pillow pytesseract rapidocr-onnxruntime onnxruntime opencv-python
powershell -ExecutionPolicy Bypass -File outputs\build_exe.ps1
```

## 离线视觉基准

基准工具只读取脱敏图片，不发送输入事件。样本按 `summon_visible`、`boss_alive`、`boss_defeated`、`low_confidence` 分类；可为每张图片放置同名 JSON，填写 `value`、`resolution`、`dpi`、`region` 和 `allow_action`。

```powershell
py -3 tools\vision_benchmark.py samples --json vision-benchmark.json --csv vision-benchmark.csv
```

## 免责说明

- 本工具仅用于合法的自动化测试场景，请确认使用行为符合目标软件的用户协议。
- 本工具通过软件层模拟输入（SendInput），不涉及游戏进程注入或内存修改。
- 本工具不提供、不宣传反作弊或游戏检测绕过功能。
- 不加入配置或模型加密，也不保证客户端无法被分析；保留 SHA-256、发布签名和详细诊断日志供审计。
