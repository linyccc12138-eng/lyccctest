# -*- coding: utf-8 -*-
"""
视频实时回调服务
集成前端实时回调机制
"""

from datetime import datetime
from app.services.logger import info, error, warning
from app.tasks.callback_manager import get_task_manager
from app.services.tencent_vod import TencentVODService

class VideoCallbackService:
    """视频回调服务"""
    
    def __init__(self, app=None):
        self.app = app
        self.vod_service = TencentVODService()
    
    def start_upload_check(self, file_id: str, folder_id: int = None):
        """
        启动上传完成检查
        每10秒检查一次，超时600秒
        """
        def check_upload():
            """检查上传状态"""
            from app.models import VideoFile
            from app import db
            
            with self.app.app_context():
                video = VideoFile.query.filter_by(file_id=file_id).first()
                
                if not video:
                    # 视频记录不存在，检查VOD
                    media_info = self.vod_service.describe_media_infos(file_id)
                    if media_info.get('success') and media_info.get('media_info_set'):
                        # 媒体已上传到VOD，创建记录
                        video = VideoFile(file_id=file_id)
                        video.process_status = 'uploaded'
                        video.process_message = '上传完成'
                        db.session.add(video)
                        db.session.commit()
                        info(f"[UPLOAD_CHECK] 发现新上传视频: file_id={file_id}", 'task')
                        return True, {'status': 'uploaded', 'file_id': file_id}
                    return False, None
                
                # 检查是否已上传
                if video.process_status in ['uploaded', 'processing', 'completed']:
                    return True, {'status': video.process_status, 'file_id': file_id}
                
                return False, None
        
        def on_upload_complete(result):
            """上传完成回调"""
            info(f"[UPLOAD_CHECK] 上传确认完成: file_id={file_id}", 'task')
            # 可以触发后续操作，如开始转码检查
        
        manager = get_task_manager(self.app)
        task = manager.start_task('upload', file_id, check_upload, on_upload_complete)
        
        info(f"[UPLOAD_CHECK] 启动上传检查: file_id={file_id}", 'task')
        return task
    
    def start_transcode_check(self, file_id: str, task_id: str = None):
        """
        启动转码完成检查
        每10秒检查一次，超时600秒
        """
        def check_transcode():
            """检查转码状态"""
            from app.models import VideoFile, Chapter
            from app import db
            import json
            
            with self.app.app_context():
                video = VideoFile.query.filter_by(file_id=file_id).first()
                
                if not video:
                    return False, None
                
                # 如果已经转码完成，直接返回
                if video.process_status == 'completed':
                    return True, {
                        'status': 'completed',
                        'file_id': file_id,
                        'play_url': video.play_url,
                        'cover_url': video.cover_url
                    }
                
                # 如果有task_id，查询任务状态
                if task_id or video.task_id:
                    check_task_id = task_id or video.task_id
                    task_result = self.vod_service.describe_task_detail(check_task_id)
                    
                    if task_result.get('success'):
                        status = task_result.get('status', '')
                        
                        if status == 'FINISH':
                            err_code = task_result.get('err_code', 0)
                            message = task_result.get('message', '')
                            
                            if err_code != 0:
                                video.process_status = 'failed'
                                video.process_message = f"转码失败: {message}"
                            else:
                                video.process_status = 'completed'
                                video.process_message = '转码完成'
                                
                                # 处理媒体结果
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
                            
                            video.callback_time = datetime.utcnow()
                            db.session.commit()
                            
                            # 更新章节状态
                            chapter = Chapter.query.filter_by(file_id=file_id).first()
                            if chapter:
                                chapter.transcode_status = 'success' if video.process_status == 'completed' else 'failed'
                                chapter.transcode_message = video.process_message
                                if video.cover_url:
                                    chapter.thumbnail_url = video.cover_url
                                db.session.commit()
                            
                            return True, {
                                'status': video.process_status,
                                'file_id': file_id,
                                'play_url': video.play_url,
                                'cover_url': video.cover_url
                            }
                        
                        elif status == 'PROCESSING':
                            video.process_status = 'processing'
                            video.process_message = '转码处理中'
                            db.session.commit()
                            return False, None
                
                return False, None
        
        def on_transcode_complete(result):
            """转码完成回调"""
            info(f"[TRANSCODE_CHECK] 转码完成: file_id={file_id}, status={result.get('status')}", 'task')
            
            # 如果转码成功且有封面，启动封面下载检查
            if result.get('status') == 'completed' and result.get('cover_url'):
                self.start_cover_download_check(file_id, result.get('cover_url'))
        
        manager = get_task_manager(self.app)
        task = manager.start_task('transcode', file_id, check_transcode, on_transcode_complete)
        
        info(f"[TRANSCODE_CHECK] 启动转码检查: file_id={file_id}", 'task')
        return task
    
    def start_cover_download_check(self, file_id: str, cover_url: str):
        """
        启动封面下载检查
        每2秒检查一次，超时20秒
        """
        def check_cover():
            """检查封面是否已下载"""
            from app.models import VideoFile
            from app import db
            import requests
            
            with self.app.app_context():
                video = VideoFile.query.filter_by(file_id=file_id).first()
                
                if not video:
                    return False, None
                
                # 检查封面是否已下载到本地
                if video.cover_url and not video.cover_url.startswith('http'):
                    # 封面已下载到本地
                    return True, {'status': 'downloaded', 'cover_url': video.cover_url}
                
                # 尝试下载封面
                if cover_url and cover_url.startswith('http'):
                    try:
                        from app.routes.callback import download_cover_image
                        local_cover_url = download_cover_image(cover_url, file_id)
                        
                        if local_cover_url:
                            video.cover_url = local_cover_url
                            db.session.commit()
                            
                            # 更新章节封面
                            from app.models import Chapter
                            chapter = Chapter.query.filter_by(file_id=file_id).first()
                            if chapter:
                                chapter.thumbnail_url = local_cover_url
                                db.session.commit()
                            
                            return True, {'status': 'downloaded', 'cover_url': local_cover_url}
                    except Exception as e:
                        error(f"[COVER_CHECK] 下载封面失败: file_id={file_id}, error={str(e)}", 'task')
                
                return False, None
        
        def on_cover_complete(result):
            """封面下载完成回调"""
            info(f"[COVER_CHECK] 封面下载完成: file_id={file_id}, cover_url={result.get('cover_url')}", 'task')
        
        manager = get_task_manager(self.app)
        task = manager.start_task('cover', file_id, check_cover, on_cover_complete)
        
        info(f"[COVER_CHECK] 启动封面下载检查: file_id={file_id}", 'task')
        return task
    
    def start_delete_check(self, file_id: str):
        """
        启动删除完成检查
        每1秒检查一次，超时5秒
        """
        def check_delete():
            """检查删除状态"""
            from app.models import VideoFile
            from app import db
            
            with self.app.app_context():
                video = VideoFile.query.filter_by(file_id=file_id).first()
                
                if not video:
                    # 视频记录已不存在，认为删除完成
                    return True, {'status': 'deleted', 'file_id': file_id}
                
                # 检查是否已标记为删除
                if video.process_status == 'deleted':
                    return True, {'status': 'deleted', 'file_id': file_id}
                
                # 查询VOD确认文件是否已删除
                media_info = self.vod_service.describe_media_infos(file_id)
                if not media_info.get('success') or not media_info.get('media_info_set'):
                    # VOD中文件不存在，更新数据库状态
                    video.process_status = 'deleted'
                    video.process_message = '已删除'
                    video.callback_time = datetime.utcnow()
                    db.session.commit()
                    return True, {'status': 'deleted', 'file_id': file_id}
                
                return False, None
        
        def on_delete_complete(result):
            """删除完成回调"""
            info(f"[DELETE_CHECK] 删除确认完成: file_id={file_id}", 'task')
        
        manager = get_task_manager(self.app)
        task = manager.start_task('delete', file_id, check_delete, on_delete_complete)
        
        info(f"[DELETE_CHECK] 启动删除检查: file_id={file_id}", 'task')
        return task
    
    def get_task_status(self, task_type: str, task_id: str) -> dict:
        """获取任务状态"""
        manager = get_task_manager(self.app)
        return manager.get_task_status(task_type, task_id)
    
    def get_all_tasks(self) -> dict:
        """获取所有任务状态"""
        manager = get_task_manager(self.app)
        return manager.get_all_tasks()
