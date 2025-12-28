import os
import tempfile
from PIL import Image
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
import io


def convert_image_to_pdf(image_file):
    """
    将图片文件转换为PDF文件
    :param image_file: 图片文件对象
    :return: PDF文件路径
    """
    try:
        # 读取图片
        img = Image.open(image_file)

        # 获取图片尺寸
        img_width, img_height = img.size

        # 创建PDF页面
        packet = io.BytesIO()
        c = canvas.Canvas(packet, pagesize=A4)

        # 计算居中位置
        page_width, page_height = A4
        max_width = page_width - 40  # 左右各留20px边距
        max_height = page_height - 40  # 上下各留20px边距

        # 计算缩放比例
        width_ratio = max_width / img_width
        height_ratio = max_height / img_height
        scale = min(width_ratio, height_ratio)

        # 计算居中位置
        scaled_width = img_width * scale
        scaled_height = img_height * scale
        x = (page_width - scaled_width) / 2
        y = (page_height - scaled_height) / 2

        # 如果图片太大，先临时保存到文件系统
        if img_width > 1000 or img_height > 1000:
            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as temp_img:
                img.save(temp_img, 'JPEG', quality=95)
                temp_img_path = temp_img.name
                img_reader = ImageReader(temp_img_path)
                c.drawImage(img_reader, x, y, scaled_width, scaled_height)
                os.unlink(temp_img_path)
        else:
            # 直接使用图片对象
            c.drawImage(ImageReader(image_file), x, y, scaled_width, scaled_height)

        c.save()
        packet.seek(0)

        return packet.getvalue()

    except Exception as e:
        print(f"图片转PDF失败: {str(e)}")
        raise e


def is_image_file(filename):
    """
    检查文件是否为图片格式
    :param filename: 文件名
    :return: 是否为图片
    """
    image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp']
    return any(filename.lower().endswith(ext) for ext in image_extensions)


def convert_image_file_to_pdf(image_path):
    """
    将图片文件路径转换为PDF字节数据
    :param image_path: 图片文件路径
    :return: PDF字节数据
    """
    try:
        # 读取图片
        img = Image.open(image_path)

        # 获取图片尺寸
        img_width, img_height = img.size

        # 创建PDF页面
        packet = io.BytesIO()
        c = canvas.Canvas(packet, pagesize=A4)

        # 计算居中位置
        page_width, page_height = A4
        max_width = page_width - 40  # 左右各留20px边距
        max_height = page_height - 40  # 上下各留20px边距

        # 计算缩放比例
        width_ratio = max_width / img_width
        height_ratio = max_height / img_height
        scale = min(width_ratio, height_ratio)

        # 计算居中位置
        scaled_width = img_width * scale
        scaled_height = img_height * scale
        x = (page_width - scaled_width) / 2
        y = (page_height - scaled_height) / 2

        # 使用ImageReader读取图片
        img_reader = ImageReader(img)
        c.drawImage(img_reader, x, y, scaled_width, scaled_height)

        c.save()
        packet.seek(0)

        return packet.getvalue()

    except Exception as e:
        print(f"图片文件转PDF失败: {str(e)}")
        raise e


def get_supported_file_types():
    """
    获取支持的文件类型
    :return: 支持的文件类型列表
    """
    return {
        'document': ['.pdf'],
        'image': ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp']
    }
