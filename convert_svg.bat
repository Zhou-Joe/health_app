@echo off
REM SVG转PNG批处理脚本
REM 需要安装Inkscape: https://inkscape.org/release/

set SVG_DIR=miniprogram\images\tab
set PNG_DIR=miniprogram\images\tabbar

echo 开始转换SVG图标为PNG...
echo.

if not exist "%PNG_DIR%" mkdir "%PNG_DIR%"

for %%f in (%SVG_DIR%\*.svg) do (
    echo 正在转换: %%~nxf
    "C:\Program Files\Inkscape\bin\inkscape.com" --export-type=png --export-filename=%PNG_DIR%\%%~nf.png -w 81 -h 81 "%%f"
)

echo.
echo 转换完成！
pause
