# 自动点击器（Windows 鼠标 / 键盘自动化工具）

[![GitHub release](https://img.shields.io/github/v/release/xyz0218xy-ops/auto-clicker?style=flat-square)](https://github.com/xyz0218xy-ops/auto-clicker/releases)
[![GitHub downloads](https://img.shields.io/github/downloads/xyz0218xy-ops/auto-clicker/total?style=flat-square)](https://github.com/xyz0218xy-ops/auto-clicker/releases)

一个用 Python 标准库（tkinter + ctypes）写的桌面自动点击 / 按键工具，打包为单文件 exe，目标电脑不需要安装 Python。

## 下载

**直接下载最新版 exe：** 👉 [ Releases 页面](https://github.com/xyz0218xy-ops/auto-clicker/releases/latest)

> 双击 `AutoClicker-v25.exe` 即可运行，无需安装 Python。建议右键「以管理员身份运行」。

## 功能

- **采集点击**：3 秒倒计时后记录鼠标坐标
- **采集按键**：按下任意键即绑定
- **多方案管理**：新建 / 复制 / 重命名 / 删除，方案之间互不影响
- **按住右键**：点按钮、按独立热键（默认 F8）随时开关，也可设成随点击一起运行
- **间隔随机化**：默认 0.5 ~ 2.0 倍随机，设 0.1 秒实际落在 0.05 ~ 0.2 秒之间
- **相对偏移**：鼠标项可填相对上一个点的偏移量，换分辨率也不用重新采集
- **轮次间隔**：每轮循环之间可单独设置等待时间
- **数据不丢**：配置存在 exe 同目录，原子写入 + 自动备份，换电脑直接拷贝
- **全局热键**：默认 F12，可改绑，游戏全屏时也能触发

## 更新日志

详见 [CHANGELOG.md](CHANGELOG.md)

### 最新版本 v25 (2026-09-21)
- 修复鼠标点击位置偏移问题（SendInput 绝一坐标归一化）
- 修复点击一次就自动暂停的问题

### 上一版本 v24 (2026-09-20)
- 用 SendInput 替代 mouse_event，更底层更难被检测
- 新增贝塞尔曲线鼠标移动，模拟真人手部轨迹
- 点击前 ±2px 随机偏移 + 移动末尾微抖动
- 右键按住改为 30-80ms 随机间隔，消除固定频率特征
- 修复键盘库缺失导致热键不可用问题

## 目录结构

```
outputs/
  auto_clicker.py           源码（Python 3.14 + tkinter）
  build_exe.ps1             一键打包脚本
  README.md                 完整使用说明
  dist/
    AutoClicker-v25.exe     单文件程序，双击运行
    click_positions.json    方案数据
work/                       打包缓存（不入库）
```

## 快速开始

1. 从 [Releases](https://github.com/xyz0218xy-ops/auto-clicker/releases/latest) 下载 `AutoClicker-v25.exe`
2. 点「采集点击」→ 3 秒内把鼠标移到目标位置
3. 需要按键就点「采集按键」
4. 按 F12 开始 / 停止
5. 建议右键「以管理员身份运行」，否则输入注入可能被系统拦截

详细说明见 [outputs/README.md](outputs/README.md)。

## 打包

```powershell
python -m pip install keyboard pyinstaller
powershell -ExecutionPolicy Bypass -File outputs\build_exe.ps1
```

## 免责说明

- 本工具仅用于合法的自动化测试场景，请确认使用行为符合目标软件的用户协议。
- 本工具通过软件层模拟输入（SendInput），不涉及游戏进程注入或内存修改。