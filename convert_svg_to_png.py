#!/usr/bin/env python3
"""
SVG图标转PNG脚本
需要安装: pip install cairosvg
"""

import os
import subprocess

def convert_svg_to_png():
    """将SVG图标转换为PNG"""
    svg_dir = "miniprogram/images/tab"
    png_dir = "miniprogram/images/tabbar"

    # 确保目标目录存在
    os.makedirs(png_dir, exist_ok=True)

    svg_files = [
        "home.svg",
        "home-active.svg",
        "report.svg",
        "report-active.svg",
        "upload.svg",
        "upload-active.svg",
        "ai.svg",
        "ai-active.svg",
        "user.svg",
        "user-active.svg"
    ]

    for svg_file in svg_files:
        svg_path = os.path.join(svg_dir, svg_file)
        png_file = svg_file.replace(".svg", ".png")
        png_path = os.path.join(png_dir, png_file)

        try:
            # 使用cairosvg转换
            import cairosvg
            with open(svg_path, 'r') as f:
                svg_code = f.read()
            cairosvg.svg2png(url=svg_path, write_to=png_path, output_width=81, output_height=81)
            print(f"✓ 转换成功: {svg_file} -> {png_file}")
        except ImportError:
            # 如果cairosvg不可用，尝试使用命令行工具
            try:
                subprocess.run([
                    "inkscape",
                    "--export-type=png",
                    f"--export-filename={png_path}",
                    "-w", "81",
                    "-h", "81",
                    svg_path
                ], check=True, capture_output=True)
                print(f"✓ 转换成功: {svg_file} -> {png_file} (inkscape)")
            except (subprocess.CalledProcessError, FileNotFoundError):
                print(f"✗ 转换失败: {svg_file}")
                print(f"  请安装 cairosvg: pip install cairosvg")
                print(f"  或安装 inkscape: sudo apt install inkscape")
                return False

    return True

if __name__ == "__main__":
    print("开始转换SVG图标为PNG...")
    if convert_svg_to_png():
        print("\n✓ 所有图标转换完成！")
    else:
        print("\n✗ 转换失败，请安装所需的依赖")
