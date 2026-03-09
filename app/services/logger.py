# -*- coding: utf-8 -*-
"""
统一日志服务模块
支持：
- 日志等级：DEBUG、INFO、ERROR
- 控制台打印开关
- 日志文件轮转（5M大小限制，最多20个文件）
- 外部接口调用日志记录
"""

import logging
import json
import os
import sys
from logging.handlers import RotatingFileHandler
from functools import wraps
from datetime import datetime

# 日志配置
LOG_DIR = '/www/course-platform/logs'
LOG_FILE_MAX_BYTES = 5 * 1024 * 1024  # 5MB
LOG_FILE_BACKUP_COUNT = 20  # 默认最多20个备份文件

# 日志格式
LOG_FORMAT = '[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s'
DATE_FORMAT = '%Y-%m-%d %H:%M:%S'


class LoggerService:
    """统一日志服务"""

    _instance = None
    _initialized = False

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, log_level='INFO', console_output=False, backup_count=20):
        if LoggerService._initialized:
            return

        self.log_level = getattr(logging, log_level.upper(), logging.INFO)
        self.console_output = console_output
        self.backup_count = backup_count

        # 确保日志目录存在
        os.makedirs(LOG_DIR, exist_ok=True)

        # 创建根日志记录器
        self.root_logger = logging.getLogger('app')
        self.root_logger.setLevel(logging.DEBUG)  # 根记录器设置为DEBUG，让处理器控制级别
        self.root_logger.handlers = []  # 清除现有处理器
        self.root_logger.propagate = False

        # 添加文件处理器
        self._add_file_handler()

        # 添加控制台处理器
        if self.console_output:
            self._add_console_handler()

        # 创建子日志记录器
        self.api_logger = logging.getLogger('app.api')
        self.external_logger = logging.getLogger('app.external')
        self.task_logger = logging.getLogger('app.task')

        LoggerService._initialized = True

    def _add_file_handler(self):
        """添加文件处理器"""
        log_file = os.path.join(LOG_DIR, 'app.log')
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=LOG_FILE_MAX_BYTES,
            backupCount=self.backup_count,
            encoding='utf-8'
        )
        file_handler.setLevel(self.log_level)
        file_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
        self.root_logger.addHandler(file_handler)

    def _add_console_handler(self):
        """添加控制台处理器"""
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(self.log_level)
        console_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
        self.root_logger.addHandler(console_handler)

    def reconfigure(self, log_level=None, console_output=None, backup_count=None):
        """重新配置日志服务"""
        # log_level 可以是字符串 ('DEBUG', 'INFO') 或整数 (logging.DEBUG, logging.INFO)
        if log_level is not None:
            if isinstance(log_level, str):
                self.log_level = getattr(logging, log_level.upper(), logging.INFO)
            elif isinstance(log_level, int):
                self.log_level = log_level
        if console_output is not None:
            self.console_output = console_output
        if backup_count is not None:
            self.backup_count = backup_count

        # 重新初始化 - 传递字符串形式的日志级别
        level_name = logging.getLevelName(self.log_level)  # 返回 'DEBUG', 'INFO' 等
        LoggerService._initialized = False
        self.__init__(
            log_level=level_name,
            console_output=self.console_output,
            backup_count=self.backup_count
        )

    # ========== DEBUG级别日志 ==========
    def debug_request(self, request_info):
        """
        记录DEBUG级别请求信息
        包括：用户操作、API请求/响应原始信息
        """
        if self.log_level > logging.DEBUG:
            return

        msg = f"[REQUEST] {json.dumps(request_info, ensure_ascii=False, default=str)}"
        self.api_logger.debug(msg)

    def debug_response(self, response_info):
        """
        记录DEBUG级别响应信息
        """
        if self.log_level > logging.DEBUG:
            return

        msg = f"[RESPONSE] {json.dumps(response_info, ensure_ascii=False, default=str)}"
        self.api_logger.debug(msg)

    def debug_external_request(self, service_name, request_data):
        """
        记录DEBUG级别外部接口调用请求
        """
        if self.log_level > logging.DEBUG:
            return

        msg = f"[EXTERNAL_REQ] [{service_name}] {json.dumps(request_data, ensure_ascii=False, default=str)}"
        self.external_logger.debug(msg)

    def debug_external_response(self, service_name, response_data):
        """
        记录DEBUG级别外部接口调用响应
        """
        if self.log_level > logging.DEBUG:
            return

        msg = f"[EXTERNAL_RESP] [{service_name}] {json.dumps(response_data, ensure_ascii=False, default=str)}"
        self.external_logger.debug(msg)

    # ========== INFO级别日志 ==========
    def info(self, message, logger_name='app'):
        """记录INFO级别日志"""
        logger = logging.getLogger(f'app.{logger_name}')
        logger.info(message)

    def info_request(self, method, path, user=None, summary=None):
        """
        记录INFO级别请求（不记录具体信息，只记录摘要）
        """
        user_info = f" [User:{user}]" if user else ""
        summary_info = f" {summary}" if summary else ""
        msg = f"[REQUEST] {method} {path}{user_info}{summary_info}"
        self.api_logger.info(msg)

    def info_response(self, method, path, status_code, duration):
        """
        记录INFO级别响应（不记录具体信息）
        """
        msg = f"[RESPONSE] {method} {path} -> {status_code} ({duration:.3f}s)"
        self.api_logger.info(msg)

    def info_external(self, service_name, action, status):
        """
        记录INFO级别外部接口调用（不记录具体信息）
        """
        msg = f"[EXTERNAL] [{service_name}] {action} -> {status}"
        self.external_logger.info(msg)

    # ========== ERROR级别日志 ==========
    def error(self, message, logger_name='app', exc_info=None):
        """记录ERROR级别日志"""
        logger = logging.getLogger(f'app.{logger_name}')
        if exc_info:
            logger.error(message, exc_info=exc_info)
        else:
            logger.error(message)

    def error_request(self, method, path, error, request_data=None):
        """
        记录ERROR级别API请求错误（包含原始信息）
        """
        error_info = {
            'type': 'api_error',
            'method': method,
            'path': path,
            'error': str(error),
            'request_data': request_data
        }
        msg = f"[API_ERROR] {json.dumps(error_info, ensure_ascii=False, default=str)}"
        self.api_logger.error(msg)

    def error_external(self, service_name, action, error, request_data=None, response_data=None):
        """
        记录ERROR级别外部接口调用错误（包含原始报文）
        """
        error_info = {
            'type': 'external_error',
            'service': service_name,
            'action': action,
            'error': str(error),
            'request_data': request_data,
            'response_data': response_data
        }
        msg = f"[EXTERNAL_ERROR] {json.dumps(error_info, ensure_ascii=False, default=str)}"
        self.external_logger.error(msg)

    def exception(self, message, logger_name='app'):
        """记录异常信息"""
        logger = logging.getLogger(f'app.{logger_name}')
        logger.exception(message)


# 全局日志服务实例
_logger_service = None


def init_logger_service(log_level='INFO', console_output=False, backup_count=20):
    """初始化日志服务"""
    global _logger_service
    # 重置初始化标志，确保新配置生效
    LoggerService._initialized = False
    _logger_service = LoggerService(log_level, console_output, backup_count)
    return _logger_service


def get_logger_service():
    """获取日志服务实例"""
    global _logger_service
    if _logger_service is None:
        _logger_service = LoggerService()
    return _logger_service


# ========== 装饰器 ==========

def log_api_call(func):
    """
    API调用日志装饰器
    根据日志等级自动记录不同详细程度的信息
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        logger_svc = get_logger_service()

        # 获取请求信息
        func_name = func.__name__
        module_name = func.__module__

        start_time = datetime.now()

        # 记录请求
        if logger_svc.log_level <= logging.DEBUG:
            request_info = {
                'function': f"{module_name}.{func_name}",
                'args': str(args),
                'kwargs': str(kwargs)
            }
            logger_svc.debug_request(request_info)
        else:
            logger_svc.info_request('FUNCTION', f"{module_name}.{func_name}")

        try:
            result = func(*args, **kwargs)

            # 计算耗时
            duration = (datetime.now() - start_time).total_seconds()

            # 记录响应
            if logger_svc.log_level <= logging.DEBUG:
                response_info = {
                    'function': f"{module_name}.{func_name}",
                    'result': str(result)[:500],  # 限制长度
                    'duration': f"{duration:.3f}s"
                }
                logger_svc.debug_response(response_info)
            else:
                logger_svc.info_response('FUNCTION', f"{module_name}.{func_name}", 'SUCCESS', duration)

            return result

        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()

            # 记录错误
            logger_svc.error_request(
                method='FUNCTION',
                path=f"{module_name}.{func_name}",
                error=e,
                request_data={'args': str(args), 'kwargs': str(kwargs)}
            )

            raise

    return wrapper


def log_external_call(service_name):
    """
    外部接口调用日志装饰器
    根据日志等级自动记录不同详细程度的信息
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            logger_svc = get_logger_service()

            func_name = func.__name__
            action = f"{service_name}.{func_name}"

            # 记录请求
            if logger_svc.log_level <= logging.DEBUG:
                request_data = {'args': str(args), 'kwargs': str(kwargs)}
                logger_svc.debug_external_request(service_name, request_data)
            else:
                logger_svc.info_external(service_name, func_name, 'REQUEST')

            try:
                result = func(*args, **kwargs)

                # 记录响应
                if logger_svc.log_level <= logging.DEBUG:
                    response_data = {'result': str(result)[:500]}
                    logger_svc.debug_external_response(service_name, response_data)
                else:
                    logger_svc.info_external(service_name, func_name, 'SUCCESS')

                return result

            except Exception as e:
                # 记录错误
                logger_svc.error_external(
                    service_name=service_name,
                    action=func_name,
                    error=e,
                    request_data={'args': str(args), 'kwargs': str(kwargs)}
                )

                raise

        return wrapper
    return decorator


# ========== 便捷函数 ==========

def debug(msg):
    """DEBUG级别日志"""
    get_logger_service().api_logger.debug(msg)


def info(msg, logger_name='app'):
    """INFO级别日志"""
    get_logger_service().info(msg, logger_name)


def warning(msg, logger_name='app'):
    """WARNING级别日志"""
    get_logger_service().root_logger.warning(msg)


def error(msg, exc_info=None):
    """ERROR级别日志"""
    get_logger_service().error(msg, exc_info=exc_info)


def exception(msg):
    """EXCEPTION级别日志"""
    get_logger_service().exception(msg)
