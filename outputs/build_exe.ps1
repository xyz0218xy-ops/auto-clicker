# 打包脚本：把 auto_clicker.py 打成单文件 exe
# 用法：powershell -ExecutionPolicy Bypass -File build_exe.ps1
#
# PyInstaller 打包时必须显式带上 Tcl/Tk 运行库（目录 + DLL + _tkinter.pyd），
# 否则打包后界面会报 "Can't find a usable init.tcl" 或版本不匹配。

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$python = "C:\Users\A\AppData\Local\Python\pythoncore-3.14-64\python.exe"
$tclSrc = "C:\Users\A\AppData\Local\Python\pythoncore-3.14-64\tcl"
$dllsDir = "C:\Users\A\AppData\Local\Python\pythoncore-3.14-64\DLLs"
$tesseractSrc = "C:\Program Files\Tesseract-OCR"
$tesseractStage = Join-Path $root "..\work\tesseract-stage"

# 将 Tesseract 可执行文件、DLL 和训练数据一起放入临时目录，打包后程序可直接使用 OCR
Remove-Item -LiteralPath $tesseractStage -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $tesseractStage -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $tesseractSrc "tesseract.exe") -Destination $tesseractStage -Force
Copy-Item -Path (Join-Path $tesseractSrc "*.dll") -Destination $tesseractStage -Force
Copy-Item -LiteralPath (Join-Path $tesseractSrc "tessdata") -Destination $tesseractStage -Recurse -Force

# PyInstaller 缓存写到本地，避免受限环境权限问题
$env:PYINSTALLER_CONFIG_DIR = Join-Path $root "..\work\picache"

& $python -m PyInstaller --onefile --windowed --name AutoClicker `
    --add-data "$tclSrc\tcl8.6;tcl\tcl8.6" `
    --add-data "$tclSrc\tk8.6;tk\tk8.6" `
    --add-data "$tesseractStage;tesseract" `
    --add-binary "$dllsDir\tcl86t.dll;." `
    --add-binary "$dllsDir\tk86t.dll;." `
    --add-binary "$dllsDir\_tkinter.pyd;." `
    --hidden-import keyboard `
    --hidden-import PIL `
    --hidden-import PIL.Image `
    --hidden-import PIL.ImageGrab `
    --hidden-import PIL.ImageOps `
    --hidden-import PIL.ImageFilter `
    --hidden-import pytesseract `
    --distpath (Join-Path $root "dist") `
    --workpath (Join-Path $root "..\work\build") `
    --specpath (Join-Path $root "..\work\spec") `
    --noconfirm (Join-Path $root "auto_clicker.py")

$exePath = Join-Path $root "dist\AutoClicker.exe"
if (Test-Path $exePath) {
    Write-Output ""
    Write-Output "打包完成：$exePath"
} else {
    Write-Output "打包失败！"
    exit 1
}
