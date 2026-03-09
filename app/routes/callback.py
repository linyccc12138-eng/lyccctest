# -*- coding: utf-8 -*-
"""
腾讯云VOD回调处理路由
处理可靠回调和普通回调事件
"""
from flask import Blueprint, request, jsonify, current_app
from app.models import VideoFile, Chapter
from app import db
from app.services.security import get_config
from app.services.logger import info, error, warning, debug
import hashlib
import time
import json
import requests
import os


callback_bp = Blueprint('callback', __name__, url_prefix='/callback')


def verify_callback_sign(key, t, sign):
    """
    验证腾讯云点播回调签名

    :param key: 回调密钥（在控制台配置）
    :param t: 回调中的时间戳参数
    :param sign: 回调中的签名参数
    :return: bool 验证是否通过
    """
    # 1. 检查时间戳是否过期（默认10分钟有效期）
    current_time = int(time.time())
    if current_time > int(t):
        warning(f"回调签名已过期: t={t}, current={current_time}")
        return False

    # 2. 计算签名
    calculated_sign = hashlib.md5(f"{key}{t}".encode()).hexdigest()

    # 3. 比对签名
    return calculated_sign == sign


def download_cover_image(cover_url, file_id):
    """
    下载封面图片到本地

    :param cover_url: 封面图片URL
    :param file_id: 文件ID（用于生成文件名）
    :return: 本地路径或None
    """
    try:
        info.info(f"开始下载封面: file_id={file_id}, url={cover_url}")

        if not cover_url:
            warning(f"封面URL为空: file_id={file_id}")
            return None

        # 处理URL中的反斜杠问题
        cover_url = cover_url.replace('\\/', '/')

        # 确保URL是完整的
        if cover_url.startswith('//'):
            cover_url = 'https:' + cover_url
        elif cover_url.startswith('/'):
            # 相对路径，不处理
            pass
        elif not cover_url.startswith('http://') and not cover_url.startswith('https://'):
            warning(f"封面URL格式不正确: {cover_url}")
            return None

        # 创建存储目录（基于Flask应用根目录，避免工作目录问题）
        # current_app.root_path 是 /www/course-platform/app
        upload_dir = os.path.join(current_app.root_path, 'static', 'uploads', 'covers')
        os.makedirs(upload_dir, exist_ok=True)
        info.info(f"封面存储目录: {upload_dir}")

        # 下载图片
        try:
            response = requests.get(cover_url, timeout=30, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            info.info(f"下载封面响应: status={response.status_code}, content-type={response.headers.get('Content-Type', 'unknown')}")
        except Exception as e:
            error(f"下载封面请求失败: {str(e)}")
            return None

        if response.status_code != 200:
            warning(f"下载封面图片失败: {cover_url}, status={response.status_code}, response={response.text[:200]}")
            return None

        # 检查内容类型
        content_type = response.headers.get('Content-Type', '')
        if 'image' not in content_type:
            warning(f"下载内容不是图片: {content_type}")
            # 继续保存，因为有时Content-Type可能不准确

        # 保存图片
        file_ext = '.jpg'  # 默认jpg
        if '.' in cover_url:
            file_ext = cover_url.split('.')[-1].split('?')[0].lower()
            if not file_ext or len(file_ext) > 5:
                file_ext = 'jpg'
            # 只保留字母数字
            file_ext = ''.join(c for c in file_ext if c.isalnum())
            if not file_ext:
                file_ext = 'jpg'
            file_ext = f".{file_ext}"

        local_filename = f"{file_id}{file_ext}"
        local_path = os.path.join(upload_dir, local_filename)

        with open(local_path, 'wb') as f:
            f.write(response.content)

        file_size = len(response.content)
        info.info(f"封面下载成功: file_id={file_id}, path={local_path}, size={file_size} bytes")

        # 返回相对URL路径
        return f"/static/uploads/covers/{local_filename}"

    except Exception as e:
        import traceback
        error(f"下载封面图片异常: {str(e)}, traceback={traceback.format_exc()}")
        return None


@callback_bp.route('/vod', methods=['POST'])
def vod_callback():
    """
    腾讯云VOD回调处理接口
    支持多种事件类型：
    - NewFileUpload: 视频上传完成
    - ProcedureStateChanged: 任务流状态变更
    - FileDeleted: 视频删除完成
    """
    try:
        # 1. 获取回调参数
        t = request.args.get('t', '')
        sign = request.args.get('sign', '')

        # 2. 验证签名
        callback_key = get_config('callback_key', '')
        if callback_key:
            if not verify_callback_sign(callback_key, t, sign):
                return jsonify({'code': -1, 'message': '签名验证失败'}), 403

        # 3. 解析回调数据
        data = request.get_json(silent=True)
        if not data:
            return jsonify({'code': -1, 'message': '无效的回调数据'}), 400

        event_type = data.get('EventType', '')
        info.info(f"收到VOD回调: {event_type}, data: {json.dumps(data, ensure_ascii=False)[:500]}")

        # 4. 处理不同事件类型
        if event_type == 'NewFileUpload':
            return handle_new_file_upload(data)
        elif event_type == 'ProcedureStateChanged':
            return handle_procedure_state_changed(data)
        elif event_type == 'FileDeleted':
            return handle_file_deleted(data)
        else:
            warning(f"未处理的回调事件类型: {event_type}")
            return jsonify({'code': 0, 'message': f'事件类型 {event_type} 已收到但未处理'})

    except Exception as e:
        error(f"处理VOD回调异常: {str(e)}")
        return jsonify({'code': -1, 'message': f'处理异常: {str(e)}'}), 500


def handle_new_file_upload(data):
    """
    处理视频上传完成事件
    """
    try:
        upload_event = data.get('FileUploadEvent', {})
        file_id = upload_event.get('FileId', '')
        procedure_task_id = upload_event.get('ProcedureTaskId', '')

        if not file_id:
            return jsonify({'code': -1, 'message': '缺少FileId'}), 400

        # 查找或创建视频文件记录
        video_file = VideoFile.query.filter_by(file_id=file_id).first()
        if not video_file:
            video_file = VideoFile(file_id=file_id)
            db.session.add(video_file)

        # 更新基本信息
        media_info = upload_event.get('MediaBasicInfo', {})
        video_file.file_name = media_info.get('Name', '')
        video_file.status = 'normal'
        video_file.callback_received = True
        video_file.callback_time = db.func.now()
        video_file.callback_data = json.dumps(data, ensure_ascii=False)

        if procedure_task_id:
            video_file.task_id = procedure_task_id
            video_file.transcode_status = 'processing'

        db.session.commit()
        info.info(f"处理上传完成事件成功: file_id={file_id}")

        return jsonify({'code': 0, 'message': 'success'})

    except Exception as e:
        db.session.rollback()
        error(f"处理上传完成事件异常: {str(e)}")
        return jsonify({'code': -1, 'message': str(e)}), 500


def handle_procedure_state_changed(data):
    """
    处理任务流状态变更事件
    这是核心功能，处理转码结果和封面截图
    """
    try:
        procedure_event = data.get('ProcedureStateChangeEvent', {})
        task_id = procedure_event.get('TaskId', '')
        status = procedure_event.get('Status', '')  # PROCESSING / FINISH
        file_id = procedure_event.get('FileId', '')
        err_code = procedure_event.get('ErrCode', 0)
        message = procedure_event.get('Message', '')

        # 详细记录回调数据
        info.info(f"[CALLBACK] 收到任务流状态变更: file_id={file_id}, status={status}, err_code={err_code}, task_id={task_id}")
        info.debug(f"[CALLBACK] 完整数据: {json.dumps(data, ensure_ascii=False)}")

        if not file_id:
            return jsonify({'code': -1, 'message': '缺少FileId'}), 400

        # 查找视频文件记录
        video_file = VideoFile.query.filter_by(file_id=file_id).first()
        if not video_file:
            # 可能是直接上传到VOD的视频，创建记录
            video_file = VideoFile(file_id=file_id)
            db.session.add(video_file)

        # 更新回调信息（先记录回调时间和数据）
        video_file.callback_time = db.func.now()
        video_file.callback_data = json.dumps(data, ensure_ascii=False)
        video_file.task_id = task_id

        # 如果任务完成
        if status == 'FINISH':
            info.info(f"[CALLBACK] 任务完成: file_id={file_id}, err_code={err_code}")
            if err_code != 0:
                # 任务失败
                video_file.process_status = 'completed'
                video_file.process_message = f"转码失败，错误码: {err_code}, {message}"
                warning(f"[CALLBACK] 任务流执行失败: file_id={file_id}, err={err_code}, msg={message}")
            else:
                # 任务成功，处理各个子任务的结果
                video_file.process_status = 'completed'
                video_file.process_message = '转码完成'
                info.info(f"[CALLBACK] 任务流执行成功: file_id={file_id}")

                # 处理MediaProcessResultSet
                process_results = procedure_event.get('MediaProcessResultSet', [])
                info.info(f"[CALLBACK] 处理结果数量: {len(process_results)}")

                # 标记封面是否成功处理
                cover_processed = False

                for result in process_results:
                    result_type = result.get('Type', '')
                    info.info(f"[CALLBACK] 处理结果类型: {result_type}")

                    if result_type == 'AdaptiveDynamicStreaming':
                        # 自适应码流转码结果
                        adaptive_task = result.get('AdaptiveDynamicStreamingTask', {})
                        if adaptive_task.get('Status') == 'SUCCESS':
                            output = adaptive_task.get('Output', {})
                            # 获取播放地址
                            if output.get('DrmType') == 'SimpleAES':
                                # HLS加密地址
                                video_file.play_url = output.get('Url', '')
                            info.info(f"自适应码流转码成功: file_id={file_id}")

                    elif result_type == 'Transcode':
                        # 普通转码结果
                        transcode_task = result.get('TranscodeTask', {})
                        if transcode_task.get('Status') == 'SUCCESS':
                            output = transcode_task.get('Output', {})
                            if not video_file.play_url:
                                video_file.play_url = output.get('Url', '')
                            info.info(f"普通转码成功: file_id={file_id}")

                    elif result_type == 'CoverBySnapshot':
                        # 截图封面结果
                        cover_task = result.get('CoverBySnapshotTask', {})
                        cover_status = cover_task.get('Status', '')
                        info.info(f"[CALLBACK] CoverBySnapshot状态: {cover_status}")
                        if cover_status == 'SUCCESS':
                            output = cover_task.get('Output', {})
                            cover_url = output.get('CoverUrl', '')
                            info.info(f"[CALLBACK] 封面URL: {cover_url}")
                            if cover_url:
                                video_file.cover_url = cover_url
                                cover_processed = True
                                info.info(f"[CALLBACK] 封面已设置: file_id={file_id}, url={cover_url}")
                                # 使用云端封面URL作为章节缩略图
                                if video_file.chapter_id:
                                    chapter = Chapter.query.get(video_file.chapter_id)
                                    if chapter:
                                        chapter.thumbnail_url = cover_url
                                        info.info(f"[CALLBACK] 章节缩略图已更新: chapter_id={chapter.id}, url={cover_url}")
                            else:
                                warning(f"[CALLBACK] 封面URL为空")
                        else:
                            err_msg = cover_task.get('Message', '未知错误')
                            warning(f"[CALLBACK] 封面截图任务失败: status={cover_status}, msg={err_msg}")

                # 标记回调已接收（无论封面下载是否成功，回调都已处理完成）
                # 封面下载失败是独立问题，不应影响回调接收状态
                video_file.callback_received = True
                has_cover_task = any(r.get('Type') == 'CoverBySnapshot' for r in process_results)
                if cover_processed or not has_cover_task:
                    info.info(f"[CALLBACK] 回调处理完成，封面已设置: file_id={file_id}, cover_processed={cover_processed}, has_cover_task={has_cover_task}")
                else:
                    warning(f"[CALLBACK] 回调已接收但封面未设置: file_id={file_id}, cover_url={video_file.cover_url}")

                # 处理按时间点截图结果
                for result in process_results:
                    result_type = result.get('Type', '')
                    if result_type == 'SnapshotByTimeOffset':
                        snapshot_task = result.get('SnapshotByTimeOffsetTask', {})
                        if snapshot_task.get('Status') == 'SUCCESS':
                            output = snapshot_task.get('Output', {})
                            image_set = output.get('ImageSet', [])
                            if image_set and not video_file.cover_url:
                                cover_url = image_set[0].get('Url', '')
                                video_file.cover_url = cover_url

        elif status == 'PROCESSING':
            if video_file.process_status in ['uploaded', 'uploading']:
                video_file.process_status = 'processing'
                video_file.process_message = '转码处理中'

        db.session.commit()
        info.info(f"[CALLBACK] VideoFile已更新: file_id={file_id}, process_status={video_file.process_status}, chapter_id={video_file.chapter_id}")

        # 更新关联的章节信息（通过file_id查找）
        chapter = Chapter.query.filter_by(file_id=file_id).first()
        if chapter:
            chapter.transcode_status = video_file.transcode_status
            chapter.transcode_message = video_file.transcode_message
            if video_file.cover_url:
                # 使用云端封面URL作为章节缩略图
                chapter.thumbnail_url = video_file.cover_url
                info.info(f"[CALLBACK] 章节缩略图已更新为云端URL(通过file_id): chapter_id={chapter.id}, url={video_file.cover_url}")
            db.session.commit()
            info.info(f"[CALLBACK] 章节已更新: chapter_id={chapter.id}, process_status={video_file.process_status}")
        else:
            # 如果通过file_id没找到，尝试通过video_file.chapter_id查找
            if video_file.chapter_id:
                chapter = Chapter.query.get(video_file.chapter_id)
                if chapter:
                    chapter.file_id = file_id  # 确保file_id关联正确
                    chapter.transcode_status = video_file.process_status
                    chapter.transcode_message = video_file.process_message
                    if video_file.cover_url:
                        chapter.thumbnail_url = video_file.cover_url
                        info.info(f"[CALLBACK] 章节缩略图已更新为云端URL(通过chapter_id): chapter_id={chapter.id}, url={video_file.cover_url}")
                    db.session.commit()
                    info.info(f"[CALLBACK] 章节已更新(通过chapter_id): chapter_id={chapter.id}, process_status={video_file.process_status}")
                else:
                    warning(f"[CALLBACK] 未找到关联章节: file_id={file_id}, chapter_id={video_file.chapter_id}")
            else:
                info.info(f"[CALLBACK] 未找到关联章节: file_id={file_id}")

        info.info(f"[CALLBACK] 处理任务流状态变更成功: file_id={file_id}, process_status={video_file.process_status}")
        return jsonify({'code': 0, 'message': 'success'})

    except Exception as e:
        db.session.rollback()
        error(f"处理任务流状态变更异常: {str(e)}")
        return jsonify({'code': -1, 'message': str(e)}), 500


def handle_file_deleted(data):
    """
    处理视频删除完成事件
    """
    try:
        delete_event = data.get('FileDeleteEvent', {})
        file_id = delete_event.get('FileId', '')

        if not file_id:
            return jsonify({'code': -1, 'message': '缺少FileId'}), 400

        # 更新本地记录
        video_file = VideoFile.query.filter_by(file_id=file_id).first()
        if video_file:
            video_file.process_status = 'deleted'
            video_file.process_message = '已删除'
            db.session.commit()

        info.info(f"处理删除完成事件成功: file_id={file_id}")
        return jsonify({'code': 0, 'message': 'success'})

    except Exception as e:
        db.session.rollback()
        error(f"处理删除完成事件异常: {str(e)}")
        return jsonify({'code': -1, 'message': str(e)}), 500


# ==================== 可靠回调API（PullEvents）====================

@callback_bp.route('/pull-events', methods=['POST'])
def pull_events():
    """
    主动拉取事件通知（可靠回调方式）
    用于服务器主动获取未消费的回调事件

    可靠回调流程：
    1. 先检查获取事件通知状态接口（CountOfEventsToPull）
    2. 不为0时才调用拉取事件通知接口
    3. 处理事件并更新数据库
    4. 数据库更新完成后再调用确认事件通知接口
    """
    try:
        from app.services.tencent_vod import TencentVODService

        vod_service = TencentVODService()

        # ========== 步骤1: 获取事件通知配置（检查可靠回调配置） ==========
        config_result = vod_service.describe_event_config()
        if config_result['success']:
            info(f"[PULL_EVENTS] 事件通知配置: switch={config_result.get('callback_switch')}, mode={config_result.get('notify_type')}")

        # ========== 步骤2: 调用拉取事件通知接口 ==========
        pull_result = vod_service.pull_events()

        if not pull_result['success']:
            error(f"[PULL_EVENTS] 拉取事件失败: {pull_result.get('error')}")
            return jsonify({
                'success': False,
                'error': pull_result.get('error', '拉取事件失败'),
                'stage': 'pull_events'
            })

        events = pull_result.get('events', [])
        if not events:
            return jsonify({
                'success': True,
                'message': '没有待处理的事件',
                'handled_count': 0,
                'pending_count': 0
            })

        info(f"[PULL_EVENTS] 拉取到 {len(events)} 个事件")

        # ========== 步骤3: 批量处理事件（先处理再确认） ==========
        # 可靠回调原则：
        # 1. 拉取事件
        # 2. 处理事件并持久化到数据库
        # 3. 确认事件（从队列中移除）
        handled_count = 0
        failed_count = 0
        confirm_handles = []
        failed_handles = []
        processed_events = []  # 记录处理结果，用于前端更新

        for event in events:
            event_handle = event.get('EventHandle', '')
            event_type = event.get('EventType', '')
            file_id = None

            try:
                # 提取file_id用于前端更新
                if event_type == 'ProcedureStateChanged':
                    file_id = event.get('ProcedureStateChangeEvent', {}).get('FileId', '')
                elif event_type == 'NewFileUpload':
                    file_id = event.get('FileUploadEvent', {}).get('FileId', '')
                elif event_type == 'FileDeleted':
                    file_id = event.get('FileDeleteEvent', {}).get('FileId', '')

                # 处理事件
                response = None
                if event_type == 'NewFileUpload':
                    response = handle_new_file_upload(event)
                elif event_type == 'ProcedureStateChanged':
                    response = handle_procedure_state_changed(event)
                elif event_type == 'FileDeleted':
                    response = handle_file_deleted(event)
                else:
                    warning(f"[PULL_EVENTS] 未知事件类型: {event_type}")
                    continue

                # 检查处理结果
                if response and hasattr(response, 'status_code') and response.status_code == 200:
                    response_data = response.get_json() if hasattr(response, 'get_json') else {}
                    if response_data and response_data.get('code') == 0:
                        handled_count += 1
                        confirm_handles.append(event_handle)
                        processed_events.append({
                            'event_type': event_type,
                            'file_id': file_id,
                            'status': 'success'
                        })
                        info(f"[PULL_EVENTS] 事件处理成功: handle={event_handle[:30]}..., type={event_type}")
                    else:
                        failed_count += 1
                        failed_handles.append(event_handle)
                        error(f"[PULL_EVENTS] 事件处理失败: handle={event_handle[:30]}..., type={event_type}, response={response_data}")
                else:
                    # 无返回或异常视为成功（处理函数内部已commit）
                    handled_count += 1
                    confirm_handles.append(event_handle)
                    processed_events.append({
                        'event_type': event_type,
                        'file_id': file_id,
                        'status': 'success'
                    })
                    info(f"[PULL_EVENTS] 事件处理成功(无返回): handle={event_handle[:30]}..., type={event_type}")

            except Exception as e:
                failed_count += 1
                failed_handles.append(event_handle)
                error(f"[PULL_EVENTS] 处理事件异常: handle={event_handle[:30]}..., type={event_type}, error={str(e)}")
                import traceback
                error(f"[PULL_EVENTS] 异常详情: {traceback.format_exc()}")

        # ========== 步骤4: 数据库更新完成后，确认已成功处理的事件 ==========
        # 可靠回调原则：只有成功处理并持久化到数据库后才确认
        # 失败的事件不会被确认，下次会继续拉取
        confirmed_count = 0
        if confirm_handles:
            info(f"[PULL_EVENTS] 准备确认 {len(confirm_handles)} 个成功处理的事件")

            # 批量确认事件
            confirm_result = vod_service.confirm_events(confirm_handles)
            if confirm_result['success']:
                confirmed_count = len(confirm_handles)
                info(f"[PULL_EVENTS] 确认 {confirmed_count} 个事件成功")
            else:
                error(f"[PULL_EVENTS] 确认事件失败: {confirm_result.get('error')}")

        # 记录失败事件
        if failed_handles:
            warning(f"[PULL_EVENTS] 有 {len(failed_handles)} 个事件处理失败，将在下次重试")

        pending_count = max(len(events) - handled_count, 0)

        return jsonify({
            'success': True,
            'message': f'成功处理 {handled_count} 个事件，确认 {confirmed_count} 个',
            'handled_count': handled_count,
            'confirmed_count': confirmed_count,
            'failed_count': failed_count,
            'pending_count': pending_count,
            'processed_events': processed_events
        })

    except Exception as e:
        error(f"[PULL_EVENTS] 拉取事件异常: {str(e)}")
        import traceback
        error(f"[PULL_EVENTS] 异常详情: {traceback.format_exc()}")
        return jsonify({'success': False, 'error': str(e)}), 500


@callback_bp.route('/event-status', methods=['GET'])
def get_event_status():
    """
    获取事件通知配置（用于前端查询）
    返回回调配置信息
    """
    try:
        from app.services.tencent_vod import TencentVODService

        vod_service = TencentVODService()
        config_result = vod_service.describe_event_config()

        if config_result['success']:
            return jsonify({
                'success': True,
                'callback_switch': config_result.get('callback_switch', ''),
                'notify_type': config_result.get('notify_type', ''),
                'callback_url': config_result.get('callback_url', '')
            })
        else:
            return jsonify({
                'success': False,
                'error': config_result.get('error', '获取事件通知配置失败')
            })

    except Exception as e:
        error(f"[EVENT_STATUS] 获取事件通知配置异常: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============ 实时状态查询接口 ============

@callback_bp.route('/video-status/<file_id>', methods=['GET'])
def get_video_status(file_id):
    """
    获取视频实时状态
    前端可以轮询此接口获取最新状态（推荐间隔3-5秒）

    :param file_id: 视频文件ID
    :return: 视频状态信息
    """
    try:
        video_file = VideoFile.query.filter_by(file_id=file_id).first()

        if not video_file:
            return jsonify({
                'success': False,
                'error': '视频不存在'
            }), 404

        return jsonify({
            'success': True,
            'file_id': file_id,
            'process_status': video_file.process_status,
            'process_message': video_file.process_message,
            'task_id': video_file.task_id,
            'cover_url': video_file.cover_url,
            'play_url': video_file.play_url,
            'callback_received': video_file.callback_received,
            'callback_time': video_file.callback_time.isoformat() if video_file.callback_time else None,
            'updated_at': video_file.updated_at.isoformat() if video_file.updated_at else None
        })

    except Exception as e:
        error(f"[VIDEO_STATUS] 获取视频状态异常: file_id={file_id}, error={str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@callback_bp.route('/batch-video-status', methods=['POST'])
def batch_video_status():
    """
    批量获取视频状态
    前端可以批量查询多个视频的状态

    Request Body: {"file_ids": ["id1", "id2", ...]}
    """
    try:
        data = request.get_json()
        if not data or 'file_ids' not in data:
            return jsonify({'success': False, 'error': '缺少file_ids参数'}), 400

        file_ids = data['file_ids']
        if not isinstance(file_ids, list) or len(file_ids) == 0:
            return jsonify({'success': False, 'error': 'file_ids必须是数组且不能为空'}), 400

        # 限制批量查询数量
        if len(file_ids) > 100:
            file_ids = file_ids[:100]

        videos = VideoFile.query.filter(VideoFile.file_id.in_(file_ids)).all()

        result = []
        for video in videos:
            result.append({
                'file_id': video.file_id,
                'process_status': video.process_status,
                'process_message': video.process_message,
                'task_id': video.task_id,
                'cover_url': video.cover_url,
                'play_url': video.play_url,
                'updated_at': video.updated_at.isoformat() if video.updated_at else None
            })

        return jsonify({
            'success': True,
            'videos': result,
            'total': len(result)
        })

    except Exception as e:
        error(f"[BATCH_VIDEO_STATUS] 批量获取视频状态异常: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@callback_bp.route('/processing-videos', methods=['GET'])
def get_processing_videos():
    """
    获取所有处理中的视频列表
    前端可以轮询此接口获取当前正在处理的视频
    """
    try:
        processing_videos = VideoFile.query.filter(
            VideoFile.process_status.in_(['processing', 'uploaded']),
            VideoFile.task_id.isnot(None)
        ).order_by(VideoFile.updated_at.desc()).limit(50).all()

        result = []
        for video in processing_videos:
            result.append({
                'file_id': video.file_id,
                'file_name': video.file_name,
                'process_status': video.process_status,
                'process_message': video.process_message,
                'task_id': video.task_id,
                'updated_at': video.updated_at.isoformat() if video.updated_at else None
            })

        return jsonify({
            'success': True,
            'videos': result,
            'total': len(result)
        })

    except Exception as e:
        error(f"[PROCESSING_VIDEOS] 获取处理中视频列表异常: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
