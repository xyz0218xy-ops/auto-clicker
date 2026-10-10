# ??????? _build.py ????? exe?? Tcl/Tk?Tesseract?WinRT OCR ???
# ???powershell -ExecutionPolicy Bypass -File outputs\build_exe.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = Split-Path -Parent $root
Set-Location $repo

$python = $null
if (Get-Command py -ErrorAction SilentlyContinue) {
    $python = "py"
    $args = @("-3.14", (Join-Path $repo "_build.py"))
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $python = "python"
    $args = @((Join-Path $repo "_build.py"))
} else {
    Write-Error "未找到 Python，请安装 Python 3.14。"
    exit 1
}
& $python @args
exit $LASTEXITCODE
