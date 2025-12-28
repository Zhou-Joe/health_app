#!/usr/bin/env python
"""
自动安装Poppler for Windows脚本
解决多模态LLM工作流PDF转换问题
"""

import os
import sys
import urllib.request
import zipfile
import tempfile
import shutil
from pathlib import Path

def download_with_progress(url, filename):
    """带进度条的下载"""
    def progress_hook(block_num, block_size, total_size):
        downloaded = block_num * block_size
        if total_size > 0:
            percent = min(100, (downloaded * 100) // total_size)
            bar_length = 50
            filled_length = (percent * bar_length) // 100
            bar = '█' * filled_length + '-' * (bar_length - filled_length)
            print(f'\r下载进度: |{bar}| {percent}% ({downloaded}/{total_size} bytes)', end='')
        else:
            print(f'\r已下载: {downloaded} bytes', end='')

    try:
        urllib.request.urlretrieve(url, filename, progress_hook)
        print()  # 换行
        return True
    except Exception as e:
        print(f"\n❌ 下载失败: {e}")
        return False

def install_poppler():
    """安装Poppler"""
    print("=== Poppler 自动安装脚本 ===")
    print("正在为多模态LLM工作流安装Poppler依赖...")
    
    # Poppler for Windows下载链接（使用预编译版本）
    poppler_urls = [
        "https://github.com/oschwartz10612/poppler-windows/releases/download/v23.11.0-0/Release-23.11.0-0.zip",
        "https://pdf2image.readthedocs.io/en/latest/_downloads/Poppler-23.07.0.zip"
    ]
    
    # 安装路径选项
    install_paths = [
        r"C:\Program Files\poppler",
        r"C:\Program Files (x86)\poppler",
        r"C:\poppler",
        r"C:\tools\poppler"
    ]
    
    temp_dir = tempfile.mkdtemp()
    
    try:
        # 选择安装路径
        install_path = None
        for path in install_paths:
            if not os.path.exists(path):
                install_path = path
                break
        
        if not install_path:
            install_path = r"C:\Program Files\poppler"
            print(f"⚠️  默认安装路径可能已存在，将使用: {install_path}")
        else:
            print(f"📁 选择安装路径: {install_path}")
        
        # 下载Poppler
        print("📥 正在下载Poppler...")
        zip_path = os.path.join(temp_dir, "poppler.zip")
        
        download_success = False
        for i, url in enumerate(poppler_urls):
            print(f"尝试下载源 {i+1}/{len(poppler_urls)}: {url}")
            if download_with_progress(url, zip_path):
                download_success = True
                break
            print(f"下载源 {i+1} 失败，尝试下一个...")
        
        if not download_success:
            print("❌ 所有下载源都失败了")
            return False
        
        # 解压文件
        print("📦 正在解压文件...")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(temp_dir)
        
        # 查找poppler目录
        poppler_dir = None
        for item in os.listdir(temp_dir):
            item_path = os.path.join(temp_dir, item)
            if os.path.isdir(item_path):
                # 查找bin目录
                bin_path = os.path.join(item_path, "bin")
                if os.path.exists(bin_path):
                    poppler_dir = item_path
                    break
        
        if not poppler_dir:
            print("❌ 解压后未找到poppler目录")
            return False
        
        # 复制文件到安装路径
        print(f"📋 正在安装到: {install_path}")
        if os.path.exists(install_path):
            shutil.rmtree(install_path)
        
        shutil.copytree(poppler_dir, install_path)
        
        # 设置环境变量
        bin_path = os.path.join(install_path, "bin")
        print(f"🔧 设置环境变量: {bin_path}")
        
        # 添加到系统PATH
        current_path = os.environ.get('PATH', '')
        if bin_path not in current_path:
            os.environ['PATH'] = bin_path + ';' + current_path
            print(f"✅ 已添加到PATH: {bin_path}")
        
        # 设置POPPLER_BIN_PATH环境变量
        os.environ['POPPLER_BIN_PATH'] = bin_path
        print(f"✅ 已设置POPPLER_BIN_PATH: {bin_path}")
        
        # 验证安装
        pdftoppm_path = os.path.join(bin_path, "pdftoppm.exe")
        if os.path.exists(pdftoppm_path):
            print("✅ Poppler安装成功！")
            print(f"📍 安装路径: {install_path}")
            print(f"📍 Bin路径: {bin_path}")
            print("\n🎉 多模态LLM工作流现在应该可以正常处理PDF文件了！")
            return True
        else:
            print("❌ 安装验证失败")
            return False
            
    except Exception as e:
        print(f"❌ 安装过程中出错: {e}")
        return False
    
    finally:
        # 清理临时文件
        try:
            shutil.rmtree(temp_dir)
        except:
            pass

def check_poppler_installation():
    """检查Poppler是否已安装"""
    print("\n=== 检查Poppler安装状态 ===")
    
    # 检查常见安装路径
    possible_paths = [
        r"C:\Program Files\poppler\bin",
        r"C:\Program Files (x86)\poppler\bin",
        r"C:\poppler\bin",
        r"C:\tools\poppler\bin",
        os.environ.get('POPPLER_BIN_PATH', ''),
    ]
    
    found_paths = []
    for path in possible_paths:
        if path and os.path.exists(path):
            pdftoppm = os.path.join(path, "pdftoppm.exe")
            if os.path.exists(pdftoppm):
                found_paths.append(path)
    
    if found_paths:
        print("✅ 找到Poppler安装:")
        for path in found_paths:
            print(f"  📍 {path}")
        return True
    else:
        print("❌ 未找到Poppler安装")
        return False

def test_poppler_functionality():
    """测试Poppler功能"""
    print("\n=== 测试Poppler功能 ===")
    
    try:
        from pdf2image import convert_from_path
        print("✅ pdf2image库已安装")
        
        # 创建测试PDF路径（如果存在的话）
        test_pdf = "test_sample.pdf"
        if os.path.exists(test_pdf):
            print(f"🔄 测试转换: {test_pdf}")
            try:
                images = convert_from_path(test_pdf, dpi=100, fmt='jpeg', first_page=1, last_page=1)
                print(f"✅ PDF转换成功，生成 {len(images)} 页图片")
                return True
            except Exception as e:
                print(f"❌ PDF转换失败: {e}")
                return False
        else:
            print("⚠️  没有找到测试PDF文件，跳过功能测试")
            return True
            
    except ImportError:
        print("❌ pdf2image库未安装，请运行: pip install pdf2image")
        return False

def main():
    """主函数"""
    print("Poppler安装工具 - 解决多模态LLM工作流PDF转换问题")
    print("=" * 60)
    
    # 检查当前状态
    if check_poppler_installation():
        print("\n🎉 Poppler已安装，测试功能...")
        if test_poppler_functionality():
            print("\n✅ 一切就绪！多模态LLM工作流应该可以正常工作。")
            return True
        else:
            print("\n⚠️  Poppler已安装但功能测试失败，尝试重新安装...")
    
    # 执行安装
    print("\n🚀 开始安装Poppler...")
    if install_poppler():
        print("\n🧪 测试安装结果...")
        if test_poppler_functionality():
            print("\n🎉 安装成功！多模态LLM工作流现在可以处理PDF文件了。")
            print("\n📝 使用说明:")
            print("1. 重启Django服务器以确保环境变量生效")
            print("2. 在上传页面选择'多模态'工作流")
            print("3. 上传PDF文件进行测试")
            return True
        else:
            print("\n❌ 安装后功能测试仍然失败")
            return False
    else:
        print("\n❌ 安装失败")
        print("\n📝 手动安装方案:")
        print("1. 访问: https://github.com/oschwartz10612/poppler-windows/releases")
        print("2. 下载最新版本的Release zip文件")
        print("3. 解压到 C:\\Program Files\\poppler\\")
        print("4. 设置环境变量 POPPLER_BIN_PATH=C:\\Program Files\\poppler\\bin")
        print("5. 重启应用程序")
        return False

if __name__ == '__main__':
    success = main()
    input("\n按回车键退出...")
    sys.exit(0 if success else 1)
