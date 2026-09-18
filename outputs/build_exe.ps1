# 打包脚本：把 auto_clicker.py 打成单文件 exe
# 用法：powershell -ExecutionPolicy Bypass -File build_exe.ps1
#
# 注意：本机 Python 3.8.6 自带的 PyInstaller 不会自动收集 Tcl/Tk 运行库，
# 打包后界面会报 "Can't find a usable init.tcl"，所以下面必须显式带上
# tcl / tk 两个目录和两个 dll。程序启动时会把它们释放到 exe 旁边的 runtime 文件夹。

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$python = "C:\Program Files\python\python.exe"
$tclSrc = "C:\Program Files\python\tcl"

# PyInstaller 默认把缓存写到 %APPDATA%，受限环境可能没有权限，这里改到本地
$env:PYINSTALLER_CONFIG_DIR = Join-Path $root "..\work\picache"

& $python -m PyInstaller --onefile --windowed --name AutoClicker `
    --add-data "$tclSrc\tcl8.6;tcl\tcl8.6" `
    --add-data "$tclSrc\tk8.6;tk\tk8.6" `
    --add-binary "C:\Program Files\python\DLLs\tcl86t.dll;." `
    --add-binary "C:\Program Files\python\DLLs\tk86t.dll;." `
    --distpath (Join-Path $root "dist") `
    --workpath (Join-Path $root "..\work\build") `
    --specpath (Join-Path $root "..\work\spec") `
    --noconfirm (Join-Path $root "auto_clicker.py")

# 产物统一改名为「自动点击器.exe」，方便直接双击运行
Copy-Item -LiteralPath (Join-Path $root "dist\AutoClicker.exe") -Destination (Join-Path $root "dist\自动点击器.exe") -Force
Remove-Item -LiteralPath (Join-Path $root "dist\AutoClicker.exe") -Force -ErrorAction SilentlyContinue

Write-Output ""
Write-Output "打包完成：$root\dist\自动点击器.exe"
Write-Output "提示：升级时只要保留同目录的 click_positions.json，采集的数据就会自动继承。"
