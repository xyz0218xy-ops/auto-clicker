# v34（2026-10-05）

## 修复
- 修正 Windows `RegisterHotKey` 在 64 位系统上的句柄参数类型。
- 修正 `WM_HOTKEY` 消息的 HWND、WPARAM、LPARAM 类型声明。
- 系统级热键注册成功后可稳定接收触发消息。

## 热键机制
- `keyboard` 全局钩子
- `GetAsyncKeyState` 键盘状态轮询
- `RegisterHotKey` 系统级热键注册

## 保持不变
- Boss 卡计数模式、自由循环模式、OCR 和内置依赖打包保持不变。
