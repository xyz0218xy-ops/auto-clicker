# 自动点击器（Windows 鼠标 / 键盘自动化工具）

[![GitHub release](https://img.shields.io/github/v/release/xyz0218xy-ops/auto-clicker?style=flat-square)](https://github.com/xyz0218xy-ops/auto-clicker/releases)
[![GitHub downloads](https://img.shields.io/github/downloads/xyz0218xy-ops/auto-clicker/total?style=flat-square)](https://github.com/xyz0218xy-ops/auto-clicker/releases)

一个用 Python 标准库（tkinter + ctypes）写的桌面自动点击 / 按键工具，打包为单文件 exe，目标电脑不需要安装 Python。

## 下载

**直接下载最新版 exe：** 👉 [AutoClicker-v37.exe](https://github.com/xyz0218xy-ops/auto-clicker/releases/download/v37/AutoClicker-v37.exe)

> 无需安装 Python，建议右键「以管理员身份运行」。历史版本与更新公告见 [Releases 页面](https://github.com/xyz0218xy-ops/auto-clicker/releases)。

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

### 最新 v37 (2026-10-07)
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
python -m pip install keyboard pyinstaller pillow pytesseract
powershell -ExecutionPolicy Bypass -File outputs\build_exe.ps1
```

## 免责说明

- 本工具仅用于合法的自动化测试场景，请确认使用行为符合目标软件的用户协议。
- 本工具通过软件层模拟输入（SendInput），不涉及游戏进程注入或内存修改。
- 本工具不提供、不宣传反作弊或游戏检测绕过功能。
