# ??????? _build.py ????? exe?? Tcl/Tk?Tesseract?WinRT OCR ???
# ???powershell -ExecutionPolicy Bypass -File outputs\build_exe.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = Split-Path -Parent $root
Set-Location $repo

$python = "C:\Users\A\AppData\Local\Python\pythoncore-3.14-64\python.exe"
& $python (Join-Path $repo "_build.py")
exit $LASTEXITCODE
