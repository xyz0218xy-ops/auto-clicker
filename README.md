# 自动点击器（Windows 鼠标 / 键盘自动化工具）

[![GitHub release](https://img.shields.io/github/v/release/xyz0218xy-ops/auto-clicker?style=flat-square)](https://github.com/xyz0218xy-ops/auto-clicker/releases)
[![GitHub downloads](https://img.shields.io/github/downloads/xyz0218xy-ops/auto-clicker/total?style=flat-square)](https://github.com/xyz0218xy-ops/auto-clicker/releases)

一个用 Python 标准库（tkinter + ctypes）写的桌面自动点击 / 按键工具，打包为单文件 exe，目标电脑不需要安装 Python。

## 下载

**直接下载最新版 exe：** 👉 [AutoClicker-v36.exe](https://github.com/xyz0218xy-ops/auto-clicker/releases/download/v36/AutoClicker-v36.exe)

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

### 最新 v36 (2026-10-05)
- Boss 卡数量识别换成三层混合引擎：自学习模板 → Windows OCR → Tesseract 兜底，常规 50~150ms 出结果
- 新增「学习数字」按钮与「测试读取」三层耗时显示
- 修复卡在「核对召唤后数量」：最多约 2 秒快速核对，读不到按已消耗 1 张继续并提示
- 计数模式启动时预热识别引擎，消除首次 2~3 秒冷启动
- 打包内置精简 Tesseract、WinRT OCR、keyboard、Pillow、pytesseract
- 自由循环模式、全部热键、按住任意键功能不变
- 更新公告详见 [release-notes-v36.md](release-notes-v36.md)

## 快速开始

1. 下载 [AutoClicker-v36.exe](https://github.com/xyz0218xy-ops/auto-clicker/releases/download/v36/AutoClicker-v36.exe)
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
