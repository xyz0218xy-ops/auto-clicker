# v33（2026-10-05）

## 修复
- 增加 Windows `RegisterHotKey` 系统级后备，解决所有热键无反应的问题。
- 热键设置后立即重启系统级注册，启停键、按住键和召唤唤出键都能及时生效。
- `keyboard` 钩子、键盘轮询和系统热键统一去重，避免一次按键触发多次。

## 热键机制
1. `keyboard` 全局钩子
2. Windows `GetAsyncKeyState` 轮询
3. Windows `RegisterHotKey` 系统注册

## 保持不变
- Boss 卡计数模式已移除星级限制。
- 自由循环模式、OCR 计数和内置 Tcl/Tk、Tesseract 打包保持不变。

## 使用说明
- 建议以管理员身份运行。
- 如果热键仍被其他软件占用，请更换一个不冲突的按键。
