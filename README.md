# 自动点击器（Windows 鼠标 / 键盘自动化工具）

[![GitHub release](https://img.shields.io/github/v/release/xyz0218xy-ops/auto-clicker?style=flat-square)](https://github.com/xyz0218xy-ops/auto-clicker/releases)
[![GitHub downloads](https://img.shields.io/github/downloads/xyz0218xy-ops/auto-clicker/total?style=flat-square)](https://github.com/xyz0218xy-ops/auto-clicker/releases)

一个用 Python 标准库（tkinter + ctypes）写的桌面自动点击 / 按键工具，打包为单文件 exe，目标电脑不需要安装 Python。

## 下载

**直接下载最新版 exe：** 👉 [ Releases 页面](https://github.com/xyz0218xy-ops/auto-clicker/releases/latest)

> 从 Releases 页面下载 `AutoClicker.exe`，无需安装 Python。建议右键「以管理员身份运行」。

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

### 最新 v31 (2026-10-05)
- 移除 Boss 卡计数模式的星级限制，唤出界面后直接点击 Boss 卡再点击召唤
- 召唤界面打开后改为轮询等待数量区域稳定，不再过早读取
- 状态栏明确显示“已唤出召唤界面”和数量重试进度
- 自由循环模式保持不变
- 优化 Boss 卡 OCR 识别：增加多组预处理、多种分割模式和召唤后重试
- 降低误读概率，数量识别不稳定时不会立即重复点击
- 保留 v29 的 Boss 卡计数模式、任意键按住和内置 OCR 打包
- 新增 Boss 卡 OCR 计数模式，支持自定义召唤次数
- 新增任意键按住，同时保留鼠标右键按住
- 修复 OCR `tessdata` 路径、Tcl/Tk 打包和固定坐标点击问题
- 打包内置 Tesseract、`tessdata`、`keyboard`、Pillow、pytesseract

## 快速开始

1. 从 [Releases](https://github.com/xyz0218xy-ops/auto-clicker/releases/latest) 下载 exe
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
