"""
批量上传处理视图
支持同时上传多个PDF和图片文件，根据文件类型自动选择处理工作流：
- PDF文件: OCR + LLM
- 图片文件: VLM (视觉语言模型)
"""

import os
import json
import tempfile
import threading
from datetime import datetime
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db import transaction

from .models import (
    HealthCheckup,
    DocumentProcessing,
    SystemSettings,
    BatchDocumentProcessing,
    BatchProcessingItem
)
from .utils import is_image_file
from .services import DocumentProcessingService, VisionLanguageModelService


def get_file_workflow_type(file_name):
    """
    根据文件名自动判断应该使用的工作流类型

    Args:
        file_name: 文件名

    Returns:
        str: 工作流类型 ('ocr_llm', 'vlm_transformers', 'vl_model')
    """
    file_ext = file_name.lower().split('.')[-1] if '.' in file_name else ''

    if file_ext == 'pdf':
        # PDF 文件使用 OCR + LLM
        return SystemSettings.get_pdf_ocr_workflow()
    else:
        # 图片文件使用多模态模型
        return 'vl_model'


def get_file_type(file_name):
    """获取文件类型"""
    file_ext = file_name.lower().split('.')[-1] if '.' in file_name else ''
    if file_ext == 'pdf':
        return 'pdf'
    elif is_image_file(file_name):
        return 'image'
    return None


@csrf_exempt
@require_http_methods(["POST"])
@login_required
def batch_upload_and_process(request):
    """
    批量上传并处理体检报告

    请求参数:
        - files: 多个文件 (multipart/form-data)
        - checkup_date: 体检日期 (必填)
        - hospital: 体检机构 (可选，默认'未知机构')
        - batch_name: 批次名称 (可选)

    返回:
        - success: 是否成功
        - batch_id: 批量任务ID
        - message: 提示信息
        - files: 文件处理列表
    """
    try:
        # 检查文件上传
        if 'files' not in request.FILES:
            return JsonResponse({
                'success': False,
                'error': '没有上传文件'
            }, status=400)

        files = request.FILES.getlist('files')

        if not files:
            return JsonResponse({
                'success': False,
                'error': '文件列表为空'
            }, status=400)

        if len(files) > 20:
            return JsonResponse({
                'success': False,
                'error': '一次最多上传20个文件'
            }, status=400)

        # 获取表单数据
        checkup_date = request.POST.get('checkup_date')
        hospital = request.POST.get('hospital', '未知机构')
        batch_name = request.POST.get('batch_name', '').strip()

        if not checkup_date:
            return JsonResponse({
                'success': False,
                'error': '请提供体检日期'
            }, status=400)

        # 验证并过滤文件，同时保存到临时文件
        valid_files = []
        invalid_files = []
        temp_file_paths = []

        for file in files:
            file_type = get_file_type(file.name)

            if not file_type:
                invalid_files.append({
                    'name': file.name,
                    'error': '不支持的文件格式，只支持PDF和图片'
                })
                continue

            if file.size > 10 * 1024 * 1024:
                invalid_files.append({
                    'name': file.name,
                    'error': '文件大小超过10MB限制'
                })
                continue

            # 将文件保存到临时位置（因为后台线程无法访问已关闭的文件句柄）
            try:
                file_extension = os.path.splitext(file.name)[1]
                with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as tmp_file:
                    for chunk in file.chunks():
                        tmp_file.write(chunk)
                    temp_file_path = tmp_file.name
                    temp_file_paths.append(temp_file_path)

                valid_files.append({
                    'temp_path': temp_file_path,
                    'name': file.name,
                    'type': file_type,
                    'size': file.size
                })
            except Exception as e:
                invalid_files.append({
                    'name': file.name,
                    'error': f'文件保存失败: {str(e)}'
                })

        if not valid_files:
            return JsonResponse({
                'success': False,
                'error': '没有有效的文件可上传',
                'invalid_files': invalid_files
            }, status=400)

        # 创建批量处理任务
        with transaction.atomic():
            batch = BatchDocumentProcessing.objects.create(
                user=request.user,
                name=batch_name or f"批量上传 {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                checkup_date=checkup_date,
                hospital=hospital,
                status='pending',
                total_files=len(valid_files),
                completed_files=0,
                failed_files=0
            )

            # 为每个文件创建处理项
            batch_items = []
            for file_info in valid_files:
                workflow_type = get_file_workflow_type(file_info['name'])

                item = BatchProcessingItem.objects.create(
                    batch=batch,
                    file_name=file_info['name'],
                    file_type=file_info['type'],
                    workflow_type=workflow_type,
                    status='pending',
                    progress=0
                )
                batch_items.append({
                    'item': item,
                    'file_info': file_info
                })

        # 在后台启动处理线程
        processing_thread = threading.Thread(
            target=process_batch_background,
            args=(batch.id, batch_items),
            name=f"BatchProcessing-{batch.id}"
        )
        processing_thread.daemon = False
        processing_thread.start()

        return JsonResponse({
            'success': True,
            'batch_id': batch.id,
            'message': f'成功创建批量上传任务，共 {len(valid_files)} 个文件',
            'total_files': len(valid_files),
            'invalid_files': invalid_files,
            'files': [
                {
                    'item_id': item['item'].id,
                    'file_name': item['file_info']['name'],
                    'file_type': item['file_info']['type'],
                    'workflow_type': item['item'].workflow_type
                }
                for item in batch_items
            ]
        })

    except Exception as e:
        import traceback
        print(f"[批量上传] 错误: {str(e)}")
        print(traceback.format_exc())

        # 清理已创建的临时文件
        for temp_path in temp_file_paths:
            try:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
                    print(f"[批量上传] 清理临时文件: {temp_path}")
            except:
                pass

        return JsonResponse({
            'success': False,
            'error': f'上传失败: {str(e)}'
        }, status=500)


def process_batch_background(batch_id, batch_items):
    """
    后台批量处理文档

    Args:
        batch_id: 批量任务ID
        batch_items: 批处理项列表，每项包含 item 和 file_info
                      file_info 包含 temp_path, name, type, size
    """
    import threading
    current_thread = threading.current_thread()
    print(f"[{current_thread.name}] 开始批量处理，批次ID: {batch_id}, 文件数: {len(batch_items)}")

    temp_files = []  # 跟踪临时文件以便清理

    try:
        batch = BatchDocumentProcessing.objects.get(id=batch_id)
        batch.status = 'processing'
        batch.save()

        # 串行处理每个文件（避免资源竞争）
        for idx, batch_item in enumerate(batch_items, 1):
            item = batch_item['item']
            file_info = batch_item['file_info']
            temp_file_path = file_info['temp_path']
            file_name = file_info['name']
            file_type = file_info['type']

            print(f"[{current_thread.name}] 处理第 {idx}/{len(batch_items)} 个文件: {file_name}")

            try:
                # 更新状态为处理中
                item.status = 'uploading'
                item.progress = 10
                item.save()

                # 读取临时文件内容到内存，然后创建 Django File 对象
                # 这样可以避免文件句柄在 with 语句关闭后导致的问题
                from django.core.files import File
                from django.core.files.base import ContentFile

                with open(temp_file_path, 'rb') as f:
                    file_content = f.read()

                # 使用 ContentFile 将内容保存到内存中
                django_file = ContentFile(file_content, name=file_name)

                # 创建体检报告记录，使用文件名作为备注/描述
                health_checkup = HealthCheckup.objects.create(
                    user=batch.user,
                    checkup_date=batch.checkup_date,
                    hospital=batch.hospital,
                    report_file=django_file,
                    notes=file_name
                )
                item.health_checkup = health_checkup
                item.save()

                # 创建文档处理记录
                document_processing = DocumentProcessing.objects.create(
                    user=batch.user,
                    health_checkup=health_checkup,
                    workflow_type=item.workflow_type,
                    status='pending',
                    progress=0
                )
                item.document_processing = document_processing
                item.save()

                print(f"[{current_thread.name}] 文件已保存到媒体存储: {file_name}")
                print(f"[{current_thread.name}] 工作流类型: {item.workflow_type}")

                # 使用 DocumentProcessingService 处理文档
                service = DocumentProcessingService(document_processing)
                print(f"[{current_thread.name}] 开始处理文档: {temp_file_path}")
                result = service.process_document(temp_file_path)
                print(f"[{current_thread.name}] 处理结果: {result}")

                # 更新项目状态
                if result.get('success'):
                    indicators_count = result.get('indicators_count', 0)
                    if indicators_count == 0:
                        # 成功但没有提取到指标，可能是配置问题
                        item.status = 'failed'
                        item.error_message = '处理完成但未提取到任何指标，请检查VLM API配置'
                        print(f"[{current_thread.name}] 警告: 文件处理完成但没有提取到指标: {file_name}")
                    else:
                        item.status = 'completed'
                        item.progress = 100
                        print(f"[{current_thread.name}] 文件处理成功: {file_name}, 提取 {indicators_count} 个指标")
                else:
                    item.status = 'failed'
                    item.error_message = result.get('error', '处理失败')
                    print(f"[{current_thread.name}] 文件处理失败: {file_name}, 错误: {result.get('error')}")

                item.save()

            except Exception as e:
                print(f"[{current_thread.name}] 处理文件失败 {file_name}: {str(e)}")
                import traceback
                print(traceback.format_exc())
                item.status = 'failed'
                item.error_message = str(e)
                item.save()

            # 更新批次状态
            batch.update_status()

        # 清理所有临时文件
        for tmp_file in temp_files:
            try:
                if os.path.exists(tmp_file):
                    os.unlink(tmp_file)
                    print(f"[{current_thread.name}] 清理临时文件: {tmp_file}")
            except Exception as e:
                print(f"[{current_thread.name}] 清理临时文件失败: {tmp_file}, 错误: {e}")

        # 最终状态更新
        batch.update_status()
        print(f"[{current_thread.name}] 批量处理完成，批次ID: {batch_id}")

    except Exception as e:
        print(f"[{current_thread.name}] 批量处理失败: {str(e)}")

        # 清理临时文件
        for tmp_file in temp_files:
            try:
                if os.path.exists(tmp_file):
                    os.unlink(tmp_file)
            except:
                pass

        try:
            batch = BatchDocumentProcessing.objects.get(id=batch_id)
            batch.status = 'failed'
            batch.error_message = str(e)
            batch.save()
        except:
            pass


@require_http_methods(["GET"])
@login_required
def get_batch_status(request, batch_id):
    """
    获取批量处理任务状态

    Args:
        request: HTTP请求
        batch_id: 批量任务ID

    Returns:
        JsonResponse: 批次状态和所有文件的处理状态
    """
    try:
        batch = get_object_or_404(
            BatchDocumentProcessing,
            id=batch_id,
            user=request.user
        )

        # 获取所有文件项的状态
        items = batch.items.all().select_related('health_checkup', 'document_processing')

        items_data = []
        for item in items:
            item_data = {
                'id': item.id,
                'file_name': item.file_name,
                'file_type': item.file_type,
                'workflow_type': item.workflow_type,
                'status': item.status,
                'progress': item.progress,
                'error_message': item.error_message,
                'created_at': item.created_at.isoformat(),
                'updated_at': item.updated_at.isoformat(),
            }

            # 添加关联数据
            if item.health_checkup:
                item_data['health_checkup_id'] = item.health_checkup.id

            if item.document_processing:
                item_data['processing_id'] = item.document_processing.id
                # 添加指标数量
                if item.status == 'completed':
                    from .models import HealthIndicator
                    indicators_count = HealthIndicator.objects.filter(
                        checkup=item.health_checkup
                    ).count()
                    item_data['indicators_count'] = indicators_count

            items_data.append(item_data)

        return JsonResponse({
            'success': True,
            'batch': {
                'id': batch.id,
                'name': batch.name,
                'status': batch.status,
                'checkup_date': batch.checkup_date.isoformat(),
                'hospital': batch.hospital,
                'total_files': batch.total_files,
                'completed_files': batch.completed_files,
                'failed_files': batch.failed_files,
                'progress_percentage': batch.progress_percentage,
                'is_completed': batch.is_completed,
                'created_at': batch.created_at.isoformat(),
                'updated_at': batch.updated_at.isoformat(),
                'completed_at': batch.completed_at.isoformat() if batch.completed_at else None,
            },
            'items': items_data
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'获取状态失败: {str(e)}'
        }, status=500)


@require_http_methods(["GET"])
@login_required
def get_batch_list(request):
    """
    获取用户的批量处理任务列表

    Returns:
        JsonResponse: 批量任务列表
    """
    try:
        batches = BatchDocumentProcessing.objects.filter(
            user=request.user
        ).order_by('-created_at')[:20]

        batches_data = []
        for batch in batches:
            batches_data.append({
                'id': batch.id,
                'name': batch.name,
                'status': batch.status,
                'checkup_date': batch.checkup_date.isoformat(),
                'hospital': batch.hospital,
                'total_files': batch.total_files,
                'completed_files': batch.completed_files,
                'failed_files': batch.failed_files,
                'progress_percentage': batch.progress_percentage,
                'is_completed': batch.is_completed,
                'created_at': batch.created_at.isoformat(),
            })

        return JsonResponse({
            'success': True,
            'batches': batches_data,
            'count': len(batches_data)
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'获取列表失败: {str(e)}'
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@login_required
def retry_batch_item(request, item_id):
    """
    重试失败的批量处理项

    Args:
        request: HTTP请求
        item_id: 批量处理项ID

    Returns:
        JsonResponse: 重试结果
    """
    try:
        item = get_object_or_404(
            BatchProcessingItem,
            id=item_id,
            batch__user=request.user
        )

        if item.status != 'failed':
            return JsonResponse({
                'success': False,
                'error': '只能重试失败的任务'
            }, status=400)

        # 重置状态
        item.status = 'pending'
        item.progress = 0
        item.error_message = None
        item.save()

        # 重新启动处理线程
        processing_thread = threading.Thread(
            target=process_single_item_background,
            args=(item.id,),
            name=f"RetryItem-{item.id}"
        )
        processing_thread.daemon = False
        processing_thread.start()

        return JsonResponse({
            'success': True,
            'message': '已重新启动处理',
            'item_id': item.id
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'重试失败: {str(e)}'
        }, status=500)


def process_single_item_background(item_id):
    """后台处理单个文件项（用于重试）"""
    import threading
    current_thread = threading.current_thread()
    print(f"[{current_thread.name}] 开始重试处理，项ID: {item_id}")

    temp_file = None

    try:
        item = BatchProcessingItem.objects.get(id=item_id)
        batch = item.batch

        # 删除旧的文档处理记录
        if item.document_processing:
            old_processing = item.document_processing
            item.document_processing = None
            item.save()
            old_processing.delete()

        # 创建新的文档处理记录
        document_processing = DocumentProcessing.objects.create(
            user=batch.user,
            health_checkup=item.health_checkup,
            workflow_type=item.workflow_type,
            status='pending',
            progress=0
        )
        item.document_processing = document_processing
        item.save()

        # 获取文件路径
        file_path = item.health_checkup.report_file.path

        # 使用 DocumentProcessingService 处理
        service = DocumentProcessingService(document_processing)
        result = service.process_document(file_path)

        # 更新状态
        if result.get('success'):
            item.status = 'completed'
            item.progress = 100
        else:
            item.status = 'failed'
            item.error_message = result.get('error', '处理失败')

        item.save()
        batch.update_status()

        print(f"[{current_thread.name}] 重试处理完成，项ID: {item_id}")

    except Exception as e:
        print(f"[{current_thread.name}] 重试处理失败: {str(e)}")
        try:
            item = BatchProcessingItem.objects.get(id=item_id)
            item.status = 'failed'
            item.error_message = str(e)
            item.save()
            item.batch.update_status()
        except:
            pass

    finally:
        # 清理临时文件
        if temp_file and os.path.exists(temp_file):
            try:
                os.unlink(temp_file)
            except:
                pass
