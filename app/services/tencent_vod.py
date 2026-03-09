# -*- coding: utf-8 -*-
from tencentcloud.common import credential
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile
from tencentcloud.vod.v20180717 import vod_client, models
from app.services.security import get_config, decrypt_value
import json
import base64
import os
from datetime import datetime
import functools

# 导入新的日志服务
from app.services.logger import get_logger_service, log_external_call

# 获取日志服务实例
logger_svc = get_logger_service()


def _serialize_request_obj(obj):
    """序列化请求对象为字典"""
    if obj is None:
        return None
    try:
        # 尝试使用对象的字典形式
        if hasattr(obj, '__dict__'):
            result = {}
            for k, v in obj.__dict__.items():
                if not k.startswith('_'):
                    try:
                        # 尝试JSON序列化
                        json.dumps({k: v}, default=str)
                        result[k] = v
                    except:
                        result[k] = str(v)
            return result
        elif hasattr(obj, '_serialize'):
            return obj._serialize()
        else:
            return str(obj)
    except Exception as e:
        return f"<无法序列化: {str(e)}>"


def log_api_call(func):
    """装饰器：记录API调用日志 - 包含完整原始报文"""
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        method_name = func.__name__
        start_time = datetime.now()
        logger = get_logger_service()

        # 记录请求参数
        args_str = ', '.join([str(a) for a in args])
        kwargs_str = ', '.join([f"{k}={v}" for k, v in kwargs.items()])
        params = args_str + (', ' + kwargs_str if kwargs_str else '')

        # 尝试获取原始请求对象（如果有）
        raw_request = None
        try:
            # 检查方法中是否创建了请求对象
            import inspect
            source = inspect.getsource(func)
            # 记录方法源码中的关键信息
        except:
            pass

        # DEBUG级别记录详细请求（包含完整参数）
        logger.debug_external_request('TencentVOD', {
            'method': method_name,
            'params': params,
            'args': [str(a)[:500] for a in args],
            'kwargs': {k: str(v)[:500] for k, v in kwargs.items()}
        })

        # INFO级别只记录方法名
        logger.info_external('TencentVOD', method_name, 'REQUEST')

        try:
            # 调用方法
            result = func(self, *args, **kwargs)

            # 记录响应
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()

            # 尝试提取完整的原始响应
            raw_response = None
            if isinstance(result, dict):
                # 记录完整响应（除了可能的敏感信息）
                raw_response = result.copy()

                success = result.get('success', True)
                status = "SUCCESS" if success else "FAILED"
                # 只记录关键信息，避免日志过大
                result_summary = {k: v for k, v in result.items() if k in ['success', 'file_id', 'task_id', 'error', 'status']}

                # DEBUG级别记录详细响应（包含完整原始报文）
                logger.debug_external_response('TencentVOD', {
                    'method': method_name,
                    'result': raw_response,
                    'duration': f"{duration:.3f}s"
                })

                # INFO级别记录摘要
                logger.info_external('TencentVOD', f"{method_name} -> {status} ({duration:.3f}s)", 'SUCCESS')
            else:
                logger.info_external('TencentVOD', f"{method_name} -> OK ({duration:.3f}s)", 'SUCCESS')
                logger.debug_external_response('TencentVOD', {
                    'method': method_name,
                    'result': str(result)[:2000],
                    'duration': f"{duration:.3f}s"
                })

            return result
        except Exception as e:
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()

            # ERROR级别记录错误（包含完整原始请求信息）
            logger.error_external(
                service_name='TencentVOD',
                action=method_name,
                error=e,
                request_data={'params': params, 'args': str(args), 'kwargs': str(kwargs)}
            )
            raise

    return wrapper


class TencentVODService:
    """腾讯云VOD服务"""
    
    def __init__(self):
        self.app_id = get_config('app_id', '')
        secret_id = get_config('secret_id', '')
        secret_key = get_config('secret_key', '')

        # 如果加密则解密
        if get_config('secret_id_encrypted', 'false') == 'true':
            secret_id = decrypt_value(secret_id)
        if get_config('secret_key_encrypted', 'false') == 'true':
            secret_key = decrypt_value(secret_key)

        self.cred = credential.Credential(secret_id, secret_key)
        self.client = None
        self._init_client()
    
    def _init_client(self):
        """初始化VOD客户端"""
        httpProfile = HttpProfile()
        httpProfile.endpoint = "vod.tencentcloudapi.com"
        
        clientProfile = ClientProfile()
        clientProfile.httpProfile = httpProfile
        
        # 设置默认地域为广州
        self.region = "ap-guangzhou"
        self.client = vod_client.VodClient(self.cred, self.region, clientProfile)
    
    def _log_sdk_request(self, method_name, request_obj):
        """记录SDK请求对象的完整内容（模拟原始报文）"""
        try:
            # 将请求对象转换为字典
            req_dict = {}
            for attr in dir(request_obj):
                if not attr.startswith('_') and hasattr(request_obj, attr):
                    val = getattr(request_obj, attr)
                    if not callable(val):
                        req_dict[attr] = str(val)

            logger_svc = get_logger_service()
            logger_svc.info(f"[SDK_RAW_REQ] [{method_name}] {json.dumps(req_dict, ensure_ascii=False, default=str)}", 'external')
        except Exception as e:
            logger_svc = get_logger_service()
            logger_svc.info(f"[SDK_RAW_REQ] [{method_name}] <无法序列化: {str(e)}>", 'external')

    def _log_sdk_response(self, method_name, response_obj):
        """记录SDK响应对象的完整内容（模拟原始报文）"""
        try:
            # 将响应对象转换为字典
            resp_dict = {}
            for attr in dir(response_obj):
                if not attr.startswith('_') and hasattr(response_obj, attr):
                    val = getattr(response_obj, attr)
                    if not callable(val):
                        try:
                            # 尝试序列化
                            json.dumps({attr: val}, default=str)
                            resp_dict[attr] = val
                        except:
                            resp_dict[attr] = str(val)[:1000]

            logger_svc = get_logger_service()
            logger_svc.info(f"[SDK_RAW_RESP] [{method_name}] {json.dumps(resp_dict, ensure_ascii=False, default=str)[:8000]}", 'external')
        except Exception as e:
            logger_svc = get_logger_service()
            logger_svc.info(f"[SDK_RAW_RESP] [{method_name}] <无法序列化: {str(e)}>", 'external')

    @log_api_call
    def upload_media(self, file_path, media_name):
        """上传媒体文件 - 使用 ApplyUpload + COS 直传方式"""
        import os

        try:
            # 1. 申请上传
            apply_req = models.ApplyUploadRequest()
            apply_req.MediaType = os.path.splitext(file_path)[1].lower().replace('.', '')
            apply_req.MediaName = media_name

            # 记录完整请求对象
            self._log_sdk_request('ApplyUpload', apply_req)

            apply_resp = self.client.ApplyUpload(apply_req)

            # 记录完整响应对象
            self._log_sdk_response('ApplyUpload', apply_resp)
            
            # 获取上传信息
            storage_bucket = apply_resp.StorageBucket
            storage_region = apply_resp.StorageRegion
            vod_session_key = apply_resp.VodSessionKey
            temp_certificate = apply_resp.TempCertificate
            media_storage_path = apply_resp.MediaStoragePath
            
            # 2. 使用 qcloud_cos SDK 上传文件
            from qcloud_cos import CosConfig, CosS3Client
            
            # 使用临时密钥创建 COS 客户端
            cos_config = CosConfig(
                Region=storage_region,
                SecretId=temp_certificate.SecretId,
                SecretKey=temp_certificate.SecretKey,
                Token=temp_certificate.Token
            )
            cos_client = CosS3Client(cos_config)
            
            # 上传文件
            with open(file_path, 'rb') as f:
                cos_client.put_object(
                    Bucket=storage_bucket,
                    Body=f,
                    Key=media_storage_path
                )
            
            # 3. 确认上传
            commit_req = models.CommitUploadRequest()
            commit_req.VodSessionKey = vod_session_key

            # 记录完整请求对象
            self._log_sdk_request('CommitUpload', commit_req)

            commit_resp = self.client.CommitUpload(commit_req)

            # 记录完整响应对象
            self._log_sdk_response('CommitUpload', commit_resp)

            return {
                'success': True,
                'file_id': commit_resp.FileId,
                'media_url': commit_resp.MediaUrl if hasattr(commit_resp, 'MediaUrl') else '',
                'cover_url': commit_resp.CoverUrl if hasattr(commit_resp, 'CoverUrl') else None
            }
        except Exception as e:
            import traceback
            return {
                'success': False,
                'error': f'{str(e)}\n{traceback.format_exc()}'
            }
    
    def apply_upload(self, media_type, media_name):
        """申请上传"""
        try:
            req = models.ApplyUploadRequest()
            req.MediaType = media_type
            req.MediaName = media_name
            
            resp = self.client.ApplyUpload(req)
            return {
                'success': True,
                'storage_bucket': resp.StorageBucket,
                'storage_region': resp.StorageRegion,
                'vod_session_key': resp.VodSessionKey,
                'temp_certificate': resp.TempCertificate,
                'upload_url': resp.UploadUrl
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def commit_upload(self, vod_session_key):
        """确认上传"""
        try:
            req = models.CommitUploadRequest()
            req.VodSessionKey = vod_session_key
            
            resp = self.client.CommitUpload(req)
            return {
                'success': True,
                'file_id': resp.FileId,
                'media_url': resp.MediaUrl,
                'cover_url': resp.CoverUrl
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    @log_api_call
    def describe_media_infos(self, file_ids):
        """获取媒体信息"""
        try:
            req = models.DescribeMediaInfosRequest()
            req.FileIds = file_ids if isinstance(file_ids, list) else [file_ids]

            resp = self.client.DescribeMediaInfos(req)
            return {
                'success': True,
                'media_info_set': resp.MediaInfoSet
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    @log_api_call
    def search_media(self, file_id):
        """
        搜索媒体文件，检查文件是否存在
        用于验证云端文件是否已被删除
        使用FileIds参数直接搜索
        """
        try:
            req = models.SearchMediaRequest()
            # 使用FileIds参数直接搜索特定文件
            req.FileIds = [file_id]
            req.Limit = 1

            resp = self.client.SearchMedia(req)

            # 如果找到媒体信息，说明文件还存在
            if hasattr(resp, 'MediaInfoSet') and len(resp.MediaInfoSet) > 0:
                return {
                    'success': True,
                    'exists': True,
                    'file_id': file_id
                }
            else:
                return {
                    'success': True,
                    'exists': False,
                    'file_id': file_id
                }
        except Exception as e:
            error_msg = str(e)
            # 如果错误是资源不存在，说明文件已被删除
            if 'ResourceNotFound' in error_msg or 'file not exist' in error_msg.lower():
                return {
                    'success': True,
                    'exists': False,
                    'file_id': file_id,
                    'message': '文件不存在'
                }
            return {
                'success': False,
                'error': error_msg
            }
    
    def get_video_thumbnail(self, file_id):
        """获取视频缩略图"""
        try:
            req = models.DescribeMediaInfosRequest()
            req.FileIds = [file_id]
            
            resp = self.client.DescribeMediaInfos(req)
            if resp.MediaInfoSet:
                media_info = resp.MediaInfoSet[0]
                cover_url = None
                if hasattr(media_info, 'CoverUrl'):
                    cover_url = media_info.CoverUrl
                elif hasattr(media_info, 'BasicInfo') and hasattr(media_info.BasicInfo, 'CoverUrl'):
                    cover_url = media_info.BasicInfo.CoverUrl
                
                return {
                    'success': True,
                    'cover_url': cover_url
                }
            return {
                'success': False,
                'error': 'Media not found'
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    @log_api_call
    def delete_media(self, file_id):
        """删除媒体"""
        try:
            req = models.DeleteMediaRequest()
            req.FileId = file_id

            # 记录完整请求对象
            self._log_sdk_request('DeleteMedia', req)

            resp = self.client.DeleteMedia(req)

            # 记录完整响应对象
            self._log_sdk_response('DeleteMedia', resp)

            return {
                'success': True
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def test_connection(self):
        """测试连接"""
        try:
            # 尝试获取媒体列表来测试连接
            req = models.SearchMediaRequest()
            req.Limit = 1
            resp = self.client.SearchMedia(req)
            return {
                'success': True,
                'total_count': resp.TotalCount
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_transcode_status(self, file_id):
        """获取视频转码状态"""
        try:
            req = models.DescribeMediaInfosRequest()
            req.FileIds = [file_id]
            
            resp = self.client.DescribeMediaInfos(req)
            if not resp.MediaInfoSet:
                return {
                    'success': False,
                    'status': 'failed',
                    'message': '视频不存在'
                }
            
            media_info = resp.MediaInfoSet[0]
            
            # 获取基础信息
            basic_info = getattr(media_info, 'BasicInfo', None)
            if not basic_info:
                return {
                    'success': True,
                    'status': 'pending',
                    'message': '等待处理'
                }

            # 获取文件信息（包含 ProcedureState）
            file_info = getattr(media_info, 'FileInfo', None)
            procedure_state = None
            if file_info:
                procedure_state = getattr(file_info, 'ProcedureState', None)

            # 获取封面信息 - 如果有封面URL，说明处理已完成
            cover_url = None
            if basic_info:
                cover_url = getattr(basic_info, 'CoverUrl', None)

            # 获取文件大小 (在MetaData中)
            size = 0
            meta_data = getattr(media_info, 'MetaData', None)
            if meta_data:
                size = getattr(meta_data, 'Size', 0)
            
            # 获取自适应码流信息（HLS任务流使用）
            adaptive_streaming = getattr(media_info, 'AdaptiveDynamicStreamingInfo', None)
            if adaptive_streaming:
                adaptive_set = getattr(adaptive_streaming, 'AdaptiveDynamicStreamingSet', [])
                for stream in adaptive_set:
                    url = getattr(stream, 'Url', '')
                    if url:
                        return {
                            'success': True,
                            'status': 'success',
                            'message': '转码成功',
                            'play_url': url,
                            'cover_url': cover_url,
                            'procedure_state': procedure_state,
                            'size': size
                        }
            
            # 获取转码信息
            transcode_info = getattr(media_info, 'TranscodeInfo', None)
            if transcode_info:
                transcode_set = getattr(transcode_info, 'TranscodeSet', [])
                
                # 检查转码状态
                # 优先查找成功的转码任务
                for transcode in transcode_set:
                    status = getattr(transcode, 'Status', '')
                    if status == 'SUCCESS':
                        url = getattr(transcode, 'Url', '')
                        definition = getattr(transcode, 'Definition', 0)
                        return {
                            'success': True,
                            'status': 'success',
                            'message': '转码成功',
                            'play_url': url,
                            'definition': definition,
                            'cover_url': cover_url,
                            'procedure_state': procedure_state,
                            'size': size
                        }
                
                # 检查是否有转码失败
                for transcode in transcode_set:
                    status = getattr(transcode, 'Status', '')
                    if status == 'FAILED':
                        message = getattr(transcode, 'Message', '转码失败')
                        return {
                            'success': True,
                            'status': 'failed',
                            'message': message,
                            'cover_url': cover_url,
                            'procedure_state': procedure_state,
                            'size': size
                        }
                
                # 有转码任务但还在进行中
                if transcode_set:
                    return {
                        'success': True,
                        'status': 'processing',
                        'message': '转码处理中',
                        'cover_url': cover_url,
                        'procedure_state': procedure_state,
                        'size': size
                    }
            
            # 检查是否有封面URL（任务流完成的标志之一）
            if cover_url:
                return {
                    'success': True,
                    'status': 'success',
                    'message': '处理完成',
                    'cover_url': cover_url,
                    'procedure_state': procedure_state,
                    'size': size
                }
            
            # 检查任务流状态
            if procedure_state:
                if procedure_state == 'Finished':
                    return {
                        'success': True,
                        'status': 'success',
                        'message': '处理完成',
                        'procedure_state': procedure_state,
                        'size': size
                    }
                elif procedure_state in ['Processing', '']:
                    return {
                        'success': True,
                        'status': 'processing',
                        'message': '处理中',
                        'procedure_state': procedure_state,
                        'size': size
                    }
            
            # 检查是否有转码任务进行中（通过事件状态）
            try:
                req_procedure = models.DescribeEventsStateRequest()
                req_procedure.FileId = file_id
                resp_procedure = self.client.DescribeEventsState(req_procedure)
                if hasattr(resp_procedure, 'EventSet') and resp_procedure.EventSet:
                    for event in resp_procedure.EventSet:
                        event_type = getattr(event, 'EventType', '')
                        if 'Procedure' in event_type:
                            return {
                                'success': True,
                                'status': 'processing',
                                'message': '转码处理中',
                                'procedure_state': procedure_state,
                                'size': size
                            }
            except:
                pass
            
            # 默认返回等待状态
            return {
                'success': True,
                'status': 'pending',
                'message': '等待转码',
                'procedure_state': procedure_state,
                'size': size
            }
            
        except Exception as e:
            return {
                'success': False,
                'status': 'failed',
                'message': str(e)
            }

    def _log_api_response(self, method_name, result):
        """辅助方法：记录API响应"""
        logger = get_logger_service()
        if isinstance(result, dict):
            success = result.get('success', True)
            status = "SUCCESS" if success else "FAILED"
            result_summary = {k: v for k, v in result.items() if k in ['success', 'file_id', 'task_id', 'error', 'status']}
            logger.debug_external_response('TencentVOD', {'method': method_name, 'result': result_summary})
            logger.info_external('TencentVOD', f"{method_name} -> {status}", 'RESPONSE')

    @log_api_call
    def describe_task_detail(self, task_id):
        """
        查询任务详情
        用于获取转码/任务流的详细状态
        文档: https://cloud.tencent.com/document/product/266/33431
        """
        try:
            req = models.DescribeTaskDetailRequest()
            req.TaskId = task_id

            resp = self.client.DescribeTaskDetail(req)

            result = {
                'success': True,
                'task_type': '',
                'status': '',
                'message': ''
            }

            # 解析任务详情
            if hasattr(resp, 'TaskType'):
                result['task_type'] = resp.TaskType

            # 根据不同任务类型解析状态
            if hasattr(resp, 'ProcedureTask'):
                procedure = resp.ProcedureTask
                result['status'] = getattr(procedure, 'Status', 'UNKNOWN')
                result['err_code'] = getattr(procedure, 'ErrCode', 0)
                result['message'] = getattr(procedure, 'Message', '')

                # 解析媒体处理结果
                if hasattr(procedure, 'MediaProcessResultSet'):
                    result['process_results'] = self._parse_media_process_results(
                        procedure.MediaProcessResultSet
                    )

            return result

        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    @log_api_call
    def process_media_by_procedure(self, file_id, procedure_name='HLS_S1', tasks_priority=0):
        """
        使用任务流模板进行视频处理
        文档: https://cloud.tencent.com/document/product/266/34782

        :param file_id: 媒体文件ID
        :param procedure_name: 任务流模板名称（如 HLS_S1）
        :param tasks_priority: 任务优先级（-10到10）
        :return: dict with success, task_id, etc.
        """
        try:
            req = models.ProcessMediaByProcedureRequest()
            req.FileId = file_id
            req.ProcedureName = procedure_name
            req.TasksPriority = tasks_priority
            req.TasksNotifyMode = 'Change'  # 状态变更时通知

            # 记录完整请求对象
            self._log_sdk_request('ProcessMediaByProcedure', req)

            resp = self.client.ProcessMediaByProcedure(req)

            # 记录完整响应对象
            self._log_sdk_response('ProcessMediaByProcedure', resp)

            return {
                'success': True,
                'task_id': resp.TaskId if hasattr(resp, 'TaskId') else '',
                'review_audio_video_task_id': resp.ReviewAudioVideoTaskId if hasattr(resp, 'ReviewAudioVideoTaskId') else '',
                'request_id': resp.RequestId if hasattr(resp, 'RequestId') else ''
            }
        except Exception as e:
            import traceback
            return {
                'success': False,
                'error': f'{str(e)}\n{traceback.format_exc()}'
            }

    def describe_procedure_templates(self, type='All'):
        """
        查询任务流模板列表
        """
        try:
            req = models.DescribeProcedureTemplatesRequest()
            req.Type = type  # All/Preset/Custom

            resp = self.client.DescribeProcedureTemplates(req)

            templates = []
            if hasattr(resp, 'ProcedureTemplateSet'):
                for template in resp.ProcedureTemplateSet:
                    templates.append({
                        'name': template.Name if hasattr(template, 'Name') else '',
                        'type': template.Type if hasattr(template, 'Type') else '',
                        'comment': template.Comment if hasattr(template, 'Comment') else ''
                    })

            return {
                'success': True,
                'templates': templates
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    # ==================== 可靠回调API ====================

    def pull_events(self, limit=10):
        """
        拉取事件通知（可靠回调方式）
        文档: https://cloud.tencent.com/document/product/266/33779

        :param limit: 最大拉取条数（默认10，最大100）
        :return: dict with success, events list
        """
        try:
            req = models.PullEventsRequest()
            # 注意：PullEvents API 没有 Limit 参数，是自动获取所有待处理事件

            resp = self.client.PullEvents(req)

            events = []
            if hasattr(resp, 'EventSet'):
                for event in resp.EventSet:
                    event_data = {
                        'EventHandle': event.EventHandle if hasattr(event, 'EventHandle') else '',
                        'EventType': event.EventType if hasattr(event, 'EventType') else ''
                    }

                    # 提取事件时间（各事件类型可能都有CreateTime）
                    event_time = None
                    if hasattr(event, 'CreateTime'):
                        event_time = event.CreateTime

                    # 如果没有CreateTime，尝试从EventHandle中提取时间戳
                    # EventHandle格式: xxx___xxx_1772263116607_xxx...
                    if not event_time and hasattr(event, 'EventHandle'):
                        import re
                        handle = event.EventHandle
                        # 匹配13-16位数字（毫秒时间戳）
                        match = re.search(r'_\d{13,16}_', handle)
                        if match:
                            try:
                                event_time = int(match.group(0).strip('_')) // 1000  # 转换为秒
                            except:
                                pass

                    # 根据事件类型提取详细信息
                    if event.EventType == 'NewFileUpload' and hasattr(event, 'FileUploadEvent'):
                        upload_event = event.FileUploadEvent
                        event_data['FileUploadEvent'] = {
                            'FileId': upload_event.FileId if hasattr(upload_event, 'FileId') else '',
                            'ProcedureTaskId': upload_event.ProcedureTaskId if hasattr(upload_event, 'ProcedureTaskId') else ''
                        }
                        # NewFileUpload的时间
                        if hasattr(upload_event, 'CreateTime'):
                            event_time = upload_event.CreateTime
                    elif event.EventType == 'ProcedureStateChanged' and hasattr(event, 'ProcedureStateChangeEvent'):
                        change_event = event.ProcedureStateChangeEvent
                        event_data['ProcedureStateChangeEvent'] = {
                            'TaskId': change_event.TaskId if hasattr(change_event, 'TaskId') else '',
                            'Status': change_event.Status if hasattr(change_event, 'Status') else '',
                            'ErrCode': change_event.ErrCode if hasattr(change_event, 'ErrCode') else 0,
                            'Message': change_event.Message if hasattr(change_event, 'Message') else '',
                            'FileId': change_event.FileId if hasattr(change_event, 'FileId') else '',
                            'FileName': change_event.FileName if hasattr(change_event, 'FileName') else '',
                            'MediaProcessResultSet': self._parse_media_process_results(
                                change_event.MediaProcessResultSet if hasattr(change_event, 'MediaProcessResultSet') else []
                            )
                        }
                        # ProcedureStateChanged的时间
                        if hasattr(change_event, 'CreateTime'):
                            event_time = change_event.CreateTime
                    elif event.EventType == 'FileDeleted' and hasattr(event, 'FileDeleteEvent'):
                        delete_event = event.FileDeleteEvent
                        # FileDeleteEvent使用FileIdSet而不是FileId
                        file_id_set = getattr(delete_event, 'FileIdSet', [])
                        file_id = file_id_set[0] if file_id_set else ''
                        event_data['FileDeleteEvent'] = {
                            'FileId': file_id,
                            'FileIdSet': list(file_id_set) if file_id_set else []
                        }
                        # FileDeleted的时间
                        if hasattr(delete_event, 'CreateTime'):
                            event_time = delete_event.CreateTime

                    # 添加事件时间到数据
                    if event_time:
                        event_data['EventTime'] = event_time

                    events.append(event_data)

            return {
                'success': True,
                'events': events,
                'total_count': len(events),
                'request_id': resp.RequestId if hasattr(resp, 'RequestId') else None
            }
        except Exception as e:
            error_msg = str(e)
            # 当没有未消费事件时，腾讯云返回 ResourceNotFound 错误
            # 这不是真正的错误，只是表示队列为空
            if 'ResourceNotFound' in error_msg and 'no event' in error_msg:
                request_id = ''
                if 'requestId:' in error_msg:
                    request_id = error_msg.split('requestId:')[-1].strip()
                return {
                    'success': True,
                    'events': [],
                    'total_count': 0,
                    'request_id': request_id
                }

            import traceback
            return {
                'success': False,
                'error': f'{error_msg}\n{traceback.format_exc()}'
            }

    def _parse_media_process_results(self, result_set):
        """解析媒体处理结果"""
        results = []
        for result in result_set:
            result_data = {
                'Type': result.Type if hasattr(result, 'Type') else ''
            }

            if result.Type == 'AdaptiveDynamicStreaming' and hasattr(result, 'AdaptiveDynamicStreamingTask'):
                task = result.AdaptiveDynamicStreamingTask
                result_data['AdaptiveDynamicStreamingTask'] = {
                    'Status': task.Status if hasattr(task, 'Status') else '',
                    'ErrCode': task.ErrCode if hasattr(task, 'ErrCode') else 0,
                    'Message': task.Message if hasattr(task, 'Message') else '',
                    'Output': {
                        'Url': task.Output.Url if hasattr(task, 'Output') and hasattr(task.Output, 'Url') else '',
                        'DrmType': task.Output.DrmType if hasattr(task, 'Output') and hasattr(task.Output, 'DrmType') else ''
                    } if hasattr(task, 'Output') else {}
                }
            elif result.Type == 'CoverBySnapshot' and hasattr(result, 'CoverBySnapshotTask'):
                task = result.CoverBySnapshotTask
                result_data['CoverBySnapshotTask'] = {
                    'Status': task.Status if hasattr(task, 'Status') else '',
                    'ErrCode': task.ErrCode if hasattr(task, 'ErrCode') else 0,
                    'Message': task.Message if hasattr(task, 'Message') else '',
                    'Output': {
                        'CoverUrl': task.Output.CoverUrl if hasattr(task, 'Output') and hasattr(task.Output, 'CoverUrl') else ''
                    } if hasattr(task, 'Output') else {}
                }
            elif result.Type == 'Transcode' and hasattr(result, 'TranscodeTask'):
                task = result.TranscodeTask
                result_data['TranscodeTask'] = {
                    'Status': task.Status if hasattr(task, 'Status') else '',
                    'ErrCode': task.ErrCode if hasattr(task, 'ErrCode') else 0,
                    'Message': task.Message if hasattr(task, 'Message') else '',
                    'Output': {
                        'Url': task.Output.Url if hasattr(task, 'Output') and hasattr(task.Output, 'Url') else ''
                    } if hasattr(task, 'Output') else {}
                }

            results.append(result_data)

        return results

    def confirm_events(self, event_handles):
        """
        确认事件通知（可靠回调方式）
        确认后，事件将从队列中移除

        :param event_handles: 事件句柄列表
        :return: dict with success
        """
        try:
            req = models.ConfirmEventsRequest()
            req.EventHandles = event_handles

            resp = self.client.ConfirmEvents(req)

            return {
                'success': True
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    @log_api_call
    def describe_event_config(self):
        """
        获取事件通知配置（可靠回调方式）
        文档: https://cloud.tencent.com/document/product/266/48758

        :return: dict with success, config info, etc.
        """
        try:
            req = models.DescribeEventConfigRequest()

            resp = self.client.DescribeEventConfig(req)

            result = {
                'success': True,
                'request_id': getattr(resp, 'RequestId', '')
            }

            # 解析事件通知配置
            if hasattr(resp, 'EventConfig'):
                config = resp.EventConfig
                result['callback_switch'] = getattr(config, 'CallbackSwitch', '')
                result['notify_type'] = getattr(config, 'NotifyMode', '')  # 注意字段名是 NotifyMode 不是 NotifyType
                result['callback_url'] = getattr(config, 'CallbackUrl', '')
                # 腾讯云这个接口不返回 CountOfEventsToPull，需要通过 PullEvents 来检查
                result['count_of_events_to_pull'] = -1  # 表示需要调用 PullEvents 检查
            else:
                result['callback_switch'] = getattr(resp, 'CallbackSwitch', '')
                result['notify_type'] = getattr(resp, 'NotifyMode', '')
                result['callback_url'] = getattr(resp, 'CallbackUrl', '')
                result['count_of_events_to_pull'] = -1

            return result

        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'callback_switch': '',
                'notify_type': '',
                'count_of_events_to_pull': -1
            }

    # ==================== 客户端上传签名生成 ====================

    def get_upload_sign(self, procedure='', source_context='', one_time_valid=0, expire_seconds=3600):
        """
        生成客户端上传签名
        用于VOD JS SDK直传视频

        :param procedure: 上传后执行的任务流名称（如 HLS_S1）
        :param source_context: 透传字段，可用于传递章节ID等信息
        :param one_time_valid: 是否单次有效（1=是，0=否）
        :param expire_seconds: 签名有效期（秒）
        :return: 签名字符串
        """
        import time
        import json
        import hmac
        import hashlib

        # 当前时间戳
        current_time = int(time.time())
        expire_time = current_time + expire_seconds

        # 构造签名明文
        # 格式: secretId=$secretId&currentTimeStamp=$currentTimeStamp&expireTime=$expireTime&random=$random
        random_num = 1000 + int(time.time() * 1000) % 9000

        # 原始签名串 - 按字典序排列参数名
        # 注意：参数名必须按字典序排列：currentTimeStamp, expireTime, random, secretId
        original = [
            f"currentTimeStamp={current_time}",
            f"expireTime={expire_time}",
            f"random={random_num}",
            f"secretId={self.cred.secretId}"
        ]

        # 如果有任务流，添加procedure参数
        if procedure:
            original.append(f"procedure={procedure}")

        # 如果有透传字段
        if source_context:
            original.append(f"sourceContext={source_context}")

        # 单次有效
        if one_time_valid:
            original.append(f"oneTimeValid={one_time_valid}")

        original_str = "&".join(original)

        # 使用HMAC-SHA1计算签名
        secret_key = self.cred.secretKey
        signature = hmac.new(
            secret_key.encode('utf-8'),
            original_str.encode('utf-8'),
            hashlib.sha1
        ).hexdigest()

        # Base64编码
        # 签名格式: $signature&$original
        sign_str = f"{signature}&{original_str}"
        sign_base64 = base64.b64encode(sign_str.encode('utf-8')).decode('utf-8')

        # 记录日志用于调试
        logger_svc = get_logger_service()
        logger_svc.info(f"[get_upload_sign] signature generated: secret_id={self.cred.secretId[:10]}..., procedure={procedure}, expire={expire_time}", 'external')

        return sign_base64

    def modify_media_info(self, file_id, new_name):
        """修改媒体信息（重命名）
        
        Args:
            file_id: 腾讯云文件ID
            new_name: 新的文件名
            
        Returns:
            dict: {
                'success': True/False,
                'error': '错误信息'  # 如果失败
            }
        """
        try:
            from tencentcloud.vod.v20180717 import models
            
            req = models.ModifyMediaInfoRequest()
            req.FileId = file_id
            req.Name = new_name
            
            # 记录请求
            self._log_sdk_request('ModifyMediaInfo', req)
            
            resp = self.client.ModifyMediaInfo(req)
            
            # 记录响应
            self._log_sdk_response('ModifyMediaInfo', resp)
            
            return {
                'success': True
            }
        except Exception as e:
            error_msg = str(e)
            logger_svc = get_logger_service()
            logger_svc.error(f"[modify_media_info] 失败: file_id={file_id}, error={error_msg}", 'external')
            return {
                'success': False,
                'error': error_msg
            }
