# -*- coding: utf-8 -*-
"""
事件消费定时任务
使用 APScheduler 定期拉取和处理腾讯云VOD事件
"""
import threading
from datetime import datetime
from flask import current_app

# 全局锁，防止任务重叠执行
_event_consumer_lock = threading.Lock()

# 导入新的日志服务
from app.services.logger import get_logger_service, info, error, warning, exception


def process_event(event, vod_service, app):
    """
    处理单个事件
    返回 (success, should_confirm) 元组
    """
    from app.models import VideoFile, Chapter
    from app import db

    event_handle = event.get('EventHandle', '')
    event_type = event.get('EventType', '')

    info(f"[PROCESS_EVENT] 开始处理事件: handle={event_handle}, type={event_type}", 'task')

    try:
        if event_type == 'NewFileUpload':
            return _process_new_file_upload(event, app)
        elif event_type == 'ProcedureStateChanged':
            return _process_procedure_state_changed(event, vod_service, app)
        elif event_type == 'FileDeleted':
            return _process_file_deleted(event, app)
        else:
            warning(f"[PROCESS_EVENT] 未知事件类型: {event_type}")
            return True, True  # 未知类型也确认，避免阻塞队列

    except Exception as e:
        error(f"[PROCESS_EVENT] 处理事件异常: handle={event_handle}, error={str(e)}", 'task')
        return False, False


def _process_new_file_upload(event, app):
    """处理文件上传事件"""
    from app.models import VideoFile
    from app import db

    with app.app_context():
        upload_event = event.get('FileUploadEvent', {})
        file_id = upload_event.get('FileId', '')
        procedure_task_id = upload_event.get('ProcedureTaskId', '')

        if not file_id:
            error("[NewFileUpload] 缺少FileId", 'task')
            return False, False

        # 检查是否已处理过
        existing = VideoFile.query.filter_by(file_id=file_id).first()
        if existing and existing.process_status in ['uploaded', 'processing', 'completed']:
            info(f"[NewFileUpload] 事件已处理过: file_id={file_id}", 'task')
            return True, True

        # 查找或创建视频记录
        if not existing:
            video_file = VideoFile(file_id=file_id)
            db.session.add(video_file)
        else:
            video_file = existing

        # 更新信息
        media_info = upload_event.get('MediaBasicInfo', {})
        video_file.file_name = media_info.get('Name', '')
        video_file.process_status = 'uploaded'
        video_file.process_message = '上传完成'
        video_file.callback_time = datetime.utcnow()
        import json
        video_file.callback_data = json.dumps(event, ensure_ascii=False)

        if procedure_task_id:
            video_file.task_id = procedure_task_id
            video_file.process_status = 'processing'
            video_file.process_message = '转码处理中'

        db.session.commit()
        info(f"[NewFileUpload] 处理成功: file_id={file_id}", 'task')
        return True, True


def _process_procedure_state_changed(event, vod_service, app):
    """处理任务流状态变更事件"""
    from app.models import VideoFile, Chapter
    from app import db
    from app.routes.callback import download_cover_image
    import json

    with app.app_context():
        procedure_event = event.get('ProcedureStateChangeEvent', {})
        task_id = procedure_event.get('TaskId', '')
        status = procedure_event.get('Status', '')
        file_id = procedure_event.get('FileId', '')
        err_code = procedure_event.get('ErrCode', 0)
        message = procedure_event.get('Message', '')

        if not file_id:
            error("[ProcedureStateChanged] 缺少FileId", 'task')
            return False, False

        # 查找视频记录
        video_file = VideoFile.query.filter_by(file_id=file_id).first()
        if not video_file:
            warning(f"[ProcedureStateChanged] 未找到视频记录: file_id={file_id}")
            # 创建记录
            video_file = VideoFile(file_id=file_id)
            db.session.add(video_file)

        # 检查幂等性：如果已经处理成功过，不再重复处理
        if video_file.process_status == 'completed':
            info(f"[ProcedureStateChanged] 事件已处理过: file_id={file_id}", 'task')
            return True, True

        # 更新回调信息
        video_file.callback_time = datetime.utcnow()
        video_file.callback_data = json.dumps(event, ensure_ascii=False)
        video_file.task_id = task_id

        if status == 'FINISH':
            if err_code != 0:
                video_file.process_status = 'completed'
                video_file.process_message = f"转码失败，错误码: {err_code}, {message}"
                warning(f"[ProcedureStateChanged] 任务流失败: file_id={file_id}, err={err_code}")
            else:
                video_file.process_status = 'completed'
                video_file.process_message = '转码完成'

                # 处理媒体处理结果
                process_results = procedure_event.get('MediaProcessResultSet', [])
                cover_processed = False

                for result in process_results:
                    result_type = result.get('Type', '')

                    if result_type == 'AdaptiveDynamicStreaming':
                        adaptive_task = result.get('AdaptiveDynamicStreamingTask', {})
                        if adaptive_task.get('Status') == 'SUCCESS':
                            output = adaptive_task.get('Output', {})
                            if output.get('DrmType') == 'SimpleAES':
                                video_file.play_url = output.get('Url', '')

                    elif result_type == 'Transcode':
                        transcode_task = result.get('TranscodeTask', {})
                        if transcode_task.get('Status') == 'SUCCESS':
                            output = transcode_task.get('Output', {})
                            if not video_file.play_url:
                                video_file.play_url = output.get('Url', '')

                    elif result_type == 'CoverBySnapshot':
                        cover_task = result.get('CoverBySnapshotTask', {})
                        if cover_task.get('Status') == 'SUCCESS':
                            output = cover_task.get('Output', {})
                            cover_url = output.get('CoverUrl', '')
                            if cover_url:
                                video_file.cover_url = cover_url
                                cover_processed = True
                                info(f"[ProcedureStateChanged] 封面已设置: file_id={file_id}, url={cover_url}", 'task')

        elif status == 'PROCESSING':
            video_file.process_status = 'processing'
            video_file.process_message = '转码处理中'

        db.session.commit()

        # 更新关联章节
        chapter = Chapter.query.filter_by(file_id=file_id).first()
        if chapter:
            # 章节使用独立的transcode_status字段
            transcode_status = 'success' if video_file.process_status == 'completed' and '失败' not in video_file.process_message else ('processing' if video_file.process_status == 'processing' else 'pending')
            chapter.transcode_status = transcode_status
            chapter.transcode_message = video_file.process_message
            if video_file.cover_url:
                chapter.thumbnail_url = video_file.cover_url
            db.session.commit()
            info(f"[ProcedureStateChanged] 章节已更新: chapter_id={chapter.id}", 'task')

        info(f"[ProcedureStateChanged] 处理成功: file_id={file_id}, status={status}", 'task')
        return True, True


def _check_processing_videos(vod_service, app):
    """
    当没有事件时，主动查询处理中的视频任务状态
    解决可靠回调不生效时状态无法更新的问题
    """
    from app.models import VideoFile
    from app import db

    with app.app_context():
        # 查找所有处理中的视频
        processing_videos = VideoFile.query.filter(
            VideoFile.process_status.in_(['processing', 'uploaded']),
            VideoFile.task_id.isnot(None)
        ).all()

        if not processing_videos:
            return

        info(f"[CHECK_PROCESSING] 发现 {len(processing_videos)} 个处理中的视频", 'task')

        for video in processing_videos:
            try:
                # 查询任务状态
                task_result = vod_service.describe_task_detail(video.task_id)

                if not task_result.get('success'):
                    warning(f"[CHECK_PROCESSING] 查询任务失败: file_id={video.file_id}, error={task_result.get('error')}")
                    continue

                status = task_result.get('status', '')
                info(f"[CHECK_PROCESSING] 视频任务状态: file_id={video.file_id}, status={status}")

                # 根据状态更新视频记录
                if status == 'FINISH':
                    err_code = task_result.get('err_code', 0)
                    message = task_result.get('message', '')

                    if err_code != 0:
                        video.process_status = 'failed'
                        video.process_message = f"转码失败: {message}"
                        warning(f"[CHECK_PROCESSING] 转码失败: file_id={video.file_id}, err={err_code}")
                    else:
                        video.process_status = 'completed'
                        video.process_message = '转码完成'

                        # 处理媒体处理结果
                        process_results = task_result.get('process_results', [])
                        for result in process_results:
                            result_type = result.get('Type', '')

                            if result_type == 'AdaptiveDynamicStreaming':
                                adaptive_task = result.get('AdaptiveDynamicStreamingTask', {})
                                if adaptive_task.get('Status') == 'SUCCESS':
                                    output = adaptive_task.get('Output', {})
                                    video.play_url = output.get('Url', '')

                            elif result_type == 'CoverBySnapshot':
                                cover_task = result.get('CoverBySnapshotTask', {})
                                if cover_task.get('Status') == 'SUCCESS':
                                    output = cover_task.get('Output', {})
                                    video.cover_url = output.get('CoverUrl', '')

                        info(f"[CHECK_PROCESSING] 转码完成: file_id={video.file_id}, play_url={video.play_url[:50] if video.play_url else 'None'}...")

                    db.session.commit()

                    # 更新关联章节状态
                    from app.models import Chapter
                    chapter = Chapter.query.filter_by(file_id=video.file_id).first()
                    if chapter:
                        transcode_status = 'success' if video.process_status == 'completed' else 'failed'
                        chapter.transcode_status = transcode_status
                        chapter.transcode_message = video.process_message
                        if video.cover_url:
                            chapter.thumbnail_url = video.cover_url
                        db.session.commit()
                        info(f"[CHECK_PROCESSING] 章节已更新: chapter_id={chapter.id}, status={transcode_status}")

                elif status == 'PROCESSING':
                    # 仍在处理中，保持状态不变
                    pass

            except Exception as e:
                error(f"[CHECK_PROCESSING] 处理视频异常: file_id={video.file_id}, error={str(e)}", 'task')
                continue


def _process_file_deleted(event, app):
    """处理文件删除事件"""
    from app.models import VideoFile
    from app import db

    with app.app_context():
        delete_event = event.get('FileDeleteEvent', {})
        file_id = delete_event.get('FileId', '')

        # FileDeleteEvent可能使用FileIdSet而不是FileId
        if not file_id and delete_event.get('FileIdSet'):
            file_id = delete_event['FileIdSet'][0]

        if not file_id:
            error("[FileDeleted] 缺少FileId", 'task')
            return False, False

        video_file = VideoFile.query.filter_by(file_id=file_id).first()
        if video_file:
            video_file.process_status = 'deleted'
            video_file.process_message = '已删除'
            video_file.callback_time = datetime.utcnow()
            db.session.commit()
            info(f"[FileDeleted] 处理成功: file_id={file_id}", 'task')

        return True, True


def consume_events_job(app):
    """
    定时任务：消费事件（可靠回调模式）
    每10分钟执行一次

    可靠回调流程：
    1. 先检查获取事件通知状态接口（CountOfEventsToPull）
    2. 不为0时才调用拉取事件通知接口
    3. 处理事件并更新数据库
    4. 数据库更新完成后再调用确认事件通知接口
    """
    # 使用锁防止任务重叠
    if not _event_consumer_lock.acquire(blocking=False):
        info("[SCHEDULED_TASK] 上一次任务仍在执行，跳过本次", 'task')
        return

    try:
        with app.app_context():
            from app.services.tencent_vod import TencentVODService

            info("[SCHEDULED_TASK] 开始执行定时事件消费任务", 'task')

            vod_service = TencentVODService()

            # ========== 步骤1: 获取事件通知配置（检查可靠回调配置） ==========
            config_result = vod_service.describe_event_config()
            if config_result['success']:
                info(f"[SCHEDULED_TASK] 事件通知配置: switch={config_result.get('callback_switch')}, mode={config_result.get('notify_type')}", 'task')

            # ========== 步骤2: 调用拉取事件通知接口 ==========
            pull_result = vod_service.pull_events()

            # ========== 步骤3: 检查拉取结果 ==========
            if not pull_result['success']:
                error(f"[SCHEDULED_TASK] 拉取事件失败: {pull_result.get('error')}", 'task')
                # 拉取失败时，检查处理中的视频（保底机制）
                _check_processing_videos(vod_service, app)
                return

            events = pull_result.get('events', [])
            if not events:
                info("[SCHEDULED_TASK] 没有待处理的事件", 'task')
                # 当没有事件时，主动查询处理中的视频任务状态
                _check_processing_videos(vod_service, app)
                return

            info(f"[SCHEDULED_TASK] 拉取到 {len(events)} 个事件", 'task')

            # ========== 步骤4: 批量处理事件（先处理再确认） ==========
            success_count = 0
            confirm_handles = []
            failed_handles = []

            for event in events:
                event_handle = event.get('EventHandle', '')
                event_type = event.get('EventType', '')

                try:
                    success, should_confirm = process_event(event, vod_service, app)

                    if success:
                        success_count += 1
                        if should_confirm:
                            confirm_handles.append(event_handle)
                        info(f"[SCHEDULED_TASK] 事件处理成功: handle={event_handle[:30]}..., type={event_type}", 'task')
                    else:
                        failed_handles.append(event_handle)
                        error(f"[SCHEDULED_TASK] 事件处理失败: handle={event_handle[:30]}..., type={event_type}", 'task')

                except Exception as e:
                    failed_handles.append(event_handle)
                    error(f"[SCHEDULED_TASK] 处理事件异常: handle={event_handle[:30]}..., error={str(e)}", 'task')

            # ========== 步骤5: 数据库更新完成后，确认已成功处理的事件 ==========
            # 可靠回调原则：只有成功处理并持久化到数据库后才确认
            # 失败的事件不会被确认，下次会继续拉取
            if confirm_handles:
                info(f"[SCHEDULED_TASK] 准备确认 {len(confirm_handles)} 个成功处理的事件", 'task')

                confirm_result = vod_service.confirm_events(confirm_handles)
                if confirm_result['success']:
                    info(f"[SCHEDULED_TASK] 确认 {len(confirm_handles)} 个事件成功", 'task')
                else:
                    error(f"[SCHEDULED_TASK] 确认事件失败: {confirm_result.get('error')}", 'task')

                # 删除本地已确认的事件记录
                try:
                    from app.models import VodEvent
                    from app import db
                    for event_handle in confirm_handles:
                        local_event = VodEvent.query.filter_by(event_handle=event_handle).first()
                        if local_event:
                            db.session.delete(local_event)
                    db.session.commit()
                    info(f"[SCHEDULED_TASK] 删除 {len(confirm_handles)} 个本地事件记录", 'task')
                except Exception as e:
                    error(f"[SCHEDULED_TASK] 删除本地事件记录异常: {str(e)}", 'task')

            if failed_handles:
                warning(f"[SCHEDULED_TASK] 有 {len(failed_handles)} 个事件处理失败，将在下次重试", 'task')

            info(f"[SCHEDULED_TASK] 任务完成: 成功处理 {success_count}/{len(events)} 个事件", 'task')

    except Exception as e:
        error(f"[SCHEDULED_TASK] 任务执行异常: {str(e)}", 'task', exc_info=True)
    finally:
        _event_consumer_lock.release()


def start_scheduler(app):
    """
    启动定时任务调度器
    注意：这是托底任务，每10分钟执行一次
    主要依赖前端实时回调机制
    """
    from apscheduler.schedulers.background import BackgroundScheduler

    scheduler = BackgroundScheduler()

    # 托底任务：每10分钟执行一次（不依赖它做实时更新）
    scheduler.add_job(
        func=consume_events_job,
        trigger='interval',
        minutes=10,
        id='vod_event_consumer',
        name='VOD Event Consumer (Fallback)',
        replace_existing=True,
        args=[app]
    )

    scheduler.start()
    info("[SCHEDULER] 事件消费定时任务已启动（托底任务），每10分钟执行一次", 'task')

    return scheduler


def init_event_consumer(app):
    """
    初始化事件消费模块
    在应用启动时调用
    """
    # 启动调度器
    scheduler = start_scheduler(app)
    return scheduler
