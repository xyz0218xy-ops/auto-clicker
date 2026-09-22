# 自动点击器（Windows 鼠标 / 键盘自动化工具）

[![GitHub release](https://img.shields.io/github/v/release/xyz0218xy-ops/auto-clicker?style=flat-square)](https://github.com/xyz0218xy-ops/auto-clicker/releases)
[![GitHub downloads](https://img.shields.io/github/downloads/xyz0218xy-ops/auto-clicker/total?style=flat-square)](https://github.com/xyz0218xy-ops/auto-clicker/releases)

一个用 Python 标准库（tkinter + ctypes）写的桌面自动点击 / 按键工具，打包为单文件 exe，目标电脑不需要安装 Python。

## 下载

**直接下载最新版 exe：** 👉 [ Releases 页面](https://github.com/xyz0218xy-ops/auto-clicker/releases/latest)

> 双击运行即可，无需安装 Python。建议右键「以管理员身份运行」。

## 功能

- **采集点击**：3 秒倒计时后记录鼠标坐标
- **采集按键**：按下任意键即绑定
- **多方案管理**：新建 / 复制 / 重命名 / 删除
- **按住右键**：按钮或热键（默认 F8）随时开关
- **间隔随机化**：默认 0.5 ~ 2.0 倍随机
- **相对偏移**：鼠标项可填相对偏移量
- **轮次间隔**：每轮循环间可单独设置等待
- **数据不丢**：配置存在 exe 同目录
- **全局热键**：默认 F12，可改绑

## 更新日志

详见 [CHANGELOG.md](CHANGELOG.md)

### 最新 v26 (2026-09-22)
- 修复 Tcl/Tk DLL 版本不匹配导致管理员运行崩溃

## 快速开始

1. 从 [Releases](https://github.com/xyz0218xy-ops/auto-clicker/releases/latest) 下载 exe
2. 点「采集点击」→ 3 秒内把鼠标移到目标位置
3. 按 F12 开始 / 停止
4. 建议右键「以管理员身份运行」

## 打包

```powershell
python -m pip install keyboard pyinstaller
powershell -ExecutionPolicy Bypass -File outputs\build_exe.ps1
```

## 免责说明

- 本工具仅用于合法的自动化测试场景，请确认使用行为符合目标软件的用户协议。
- 本工具通过软件层模拟输入（SendInput），不涉及游戏进程注入或内存修改。