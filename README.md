# 自动点击器（Windows 鼠标 / 键盘自动化工具）

一个用 Python 标准库（tkinter + ctypes）写的桌面自动点击 / 按键工具，打包为单文件 exe，目标电脑不需要安装 Python。

## 功能

- **采集点击**：3 秒倒计时后记录鼠标坐标
- **采集按键**：按下任意键即绑定
- **多方案管理**：新建 / 复制 / 重命名 / 删除，方案之间互不影响
- **按住右键**：点按钮、按独立热键（默认 F8）随时开关，也可设成随点击一起运行
- **间隔随机化**：默认 0.5 ~ 2.0 倍随机，设 0.1 秒实际落在 0.05 ~ 0.2 秒之间
- **数据不丢**：配置存在 exe 同目录，原子写入 + 自动备份，换电脑直接拷贝
- **全局热键**：默认 F12，可改绑，游戏全屏时也能触发

## 目录结构

```
outputs/
  auto_clicker.py           源码（Python 3.8 + tkinter）
  build_exe.ps1             一键打包脚本（已含 Tcl/Tk 运行库参数）
  README.md                 完整使用说明
  dist/
    自动点击器.exe           单文件程序，双击运行
    click_positions.json    方案数据（采集点、热键、随机倍率）
work/                       开发工作区（打包缓存与测试脚本，不入库）
```

## 快速开始

1. 双击 `outputs/dist/自动点击器.exe`
2. 点「采集点击」→ 3 秒内把鼠标移到目标位置
3. 需要按键就点「采集按键」
4. 按 F12 开始 / 停止
5. 建议右键「以管理员身份运行」，否则输入注入可能被系统拦截

详细说明见 [outputs/README.md](outputs/README.md)。

## 打包

```powershell
powershell -ExecutionPolicy Bypass -File outputs\build_exe.ps1
```

> 本机 Python 3.8.6 自带的 PyInstaller 不会自动收集 Tcl/Tk 运行库，脚本里已显式带上 tcl / tk 目录与 dll，否则打包后界面会报 `Can't find a usable init.tcl`。

## 免责说明

- 主流游戏的反作弊系统（如穿越火线 ACE）会校验输入是否来自真实硬件设备，软件层模拟输入（`mouse_event` / `SendInput` / `PostMessage`）可能被识别并拦截，这属于内核级限制。
- 请确认使用行为符合目标软件的用户协议，仅用于合法的自动化场景。