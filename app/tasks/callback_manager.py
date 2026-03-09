# -*- coding: utf-8 -*-
"""
前端实时回调任务管理器
实现上传、转码、删除的实时状态检查

任务类型：
- upload: 上传检查，每10秒，超时600秒
- transcode: 转码检查，每10秒，超时600秒
- cover: 封面下载，每2秒，超时20秒
- delete: 删除检查，每1秒，超时5秒
"""

import threading
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Dict, Callable, Optional

from app.services.logger import get_logger_service, info, error, warning

# 全局线程池和任务管理器
_executor = None
_task_manager = None

def get_executor(max_workers=20):
    """获取全局线程池"""
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="callback_")
        info("[CALLBACK] 线程池已创建，最大工作线程数: {}".format(max_workers), 'task')
    return _executor

def get_task_manager(app=None):
    """获取全局任务管理器"""
    global _task_manager
    if _task_manager is None:
        _task_manager = CallbackTaskManager(app)
    return _task_manager


class CallbackTask:
    """回调任务类"""
    
    # 任务配置
    CONFIG = {
        'upload': {'interval': 10, 'timeout': 600, 'name': '上传检查'},
        'transcode': {'interval': 10, 'timeout': 600, 'name': '转码检查'},
        'cover': {'interval': 2, 'timeout': 20, 'name': '封面下载'},
        'delete': {'interval': 1, 'timeout': 5, 'name': '删除检查'},
    }
    
    def __init__(self, task_type: str, task_id: str, check_func: Callable, 
                 callback_func: Optional[Callable] = None, app=None):
        """
        创建回调任务
        
        Args:
            task_type: 任务类型 (upload/transcode/cover/delete)
            task_id: 任务ID (file_id 或其他标识)
            check_func: 检查函数，返回 (is_complete, result)
            callback_func: 完成后的回调函数
            app: Flask应用实例
        """
        self.task_type = task_type
        self.task_id = task_id
        self.check_func = check_func
        self.callback_func = callback_func
        self.app = app
        
        config = self.CONFIG.get(task_type, {})
        self.interval = config.get('interval', 10)
        self.timeout = config.get('timeout', 60)
        self.name = config.get('name', '未知任务')
        
        self.start_time = time.time()
        self.check_count = 0
        self.is_running = False
        self.is_completed = False
        self.result = None
        self.error = None
        
        info(f"[CALLBACK] 任务创建: {self.name}[{task_id}]，检查间隔{self.interval}秒，超时{self.timeout}秒", 'task')
    
    def run(self):
        """运行任务"""
        self.is_running = True
        
        try:
            while self.is_running:
                elapsed = time.time() - self.start_time
                self.check_count += 1
                
                # 检查是否超时
                if elapsed > self.timeout:
                    warning(f"[CALLBACK] 任务超时: {self.name}[{self.task_id}]，耗时{int(elapsed)}秒，检查次数{self.check_count}", 'task')
                    self.is_running = False
                    self.error = f"超时 ({int(elapsed)}秒)"
                    break
                
                # 执行检查
                try:
                    with self.app.app_context():
                        is_complete, result = self.check_func()
                    
                    if is_complete:
                        self.is_completed = True
                        self.result = result
                        info(f"[CALLBACK] 任务完成: {self.name}[{self.task_id}]，耗时{int(elapsed)}秒，检查次数{self.check_count}", 'task')
                        
                        # 执行回调
                        if self.callback_func:
                            try:
                                with self.app.app_context():
                                    self.callback_func(result)
                            except Exception as e:
                                error(f"[CALLBACK] 回调函数异常: {self.name}[{self.task_id}], error={str(e)}", 'task')
                        
                        break
                    else:
                        info(f"[CALLBACK] 任务进行中: {self.name}[{self.task_id}]，已耗时{int(elapsed)}秒，第{self.check_count}次检查", 'task')
                
                except Exception as e:
                    error(f"[CALLBACK] 检查函数异常: {self.name}[{self.task_id}], error={str(e)}", 'task')
                
                # 等待下次检查
                time.sleep(self.interval)
        
        except Exception as e:
            error(f"[CALLBACK] 任务执行异常: {self.name}[{self.task_id}], error={str(e)}", 'task')
            self.error = str(e)
        finally:
            self.is_running = False
            info(f"[CALLBACK] 任务结束: {self.name}[{self.task_id}]，状态: {'完成' if self.is_completed else '失败/超时'}", 'task')
    
    def stop(self):
        """停止任务"""
        self.is_running = False
        info(f"[CALLBACK] 任务被停止: {self.name}[{self.task_id}]", 'task')


class CallbackTaskManager:
    """回调任务管理器"""
    
    def __init__(self, app=None):
        self.app = app
        self.tasks: Dict[str, CallbackTask] = {}
        self.futures: Dict[str, Future] = {}
        self.lock = threading.Lock()
    
    def _generate_task_key(self, task_type: str, task_id: str) -> str:
        """生成任务键"""
        return f"{task_type}:{task_id}"
    
    def start_task(self, task_type: str, task_id: str, check_func: Callable,
                   callback_func: Optional[Callable] = None) -> CallbackTask:
        """
        启动一个新的回调任务
        
        Args:
            task_type: 任务类型
            task_id: 任务ID
            check_func: 检查函数
            callback_func: 完成回调函数
            
        Returns:
            CallbackTask 实例
        """
        key = self._generate_task_key(task_type, task_id)
        
        with self.lock:
            # 如果任务已存在，先停止旧任务
            if key in self.tasks:
                old_task = self.tasks[key]
                if old_task.is_running:
                    old_task.stop()
                    info(f"[CALLBACK] 停止旧任务: {key}", 'task')
            
            # 创建新任务
            task = CallbackTask(task_type, task_id, check_func, callback_func, self.app)
            self.tasks[key] = task
            
            # 提交到线程池执行
            executor = get_executor()
            future = executor.submit(task.run)
            self.futures[key] = future
            
            info(f"[CALLBACK] 任务已启动: {key}", 'task')
            return task
    
    def stop_task(self, task_type: str, task_id: str):
        """停止指定任务"""
        key = self._generate_task_key(task_type, task_id)
        
        with self.lock:
            if key in self.tasks:
                self.tasks[key].stop()
                info(f"[CALLBACK] 任务已停止: {key}", 'task')
    
    def get_task_status(self, task_type: str, task_id: str) -> Optional[dict]:
        """获取任务状态"""
        key = self._generate_task_key(task_type, task_id)
        
        with self.lock:
            task = self.tasks.get(key)
            if not task:
                return None
            
            return {
                'task_type': task.task_type,
                'task_id': task.task_id,
                'name': task.name,
                'is_running': task.is_running,
                'is_completed': task.is_completed,
                'check_count': task.check_count,
                'elapsed': time.time() - task.start_time,
                'error': task.error,
            }
    
    def cleanup_completed_tasks(self):
        """清理已完成的任务"""
        with self.lock:
            completed_keys = []
            for key, task in self.tasks.items():
                if not task.is_running:
                    completed_keys.append(key)
            
            for key in completed_keys:
                del self.tasks[key]
                if key in self.futures:
                    del self.futures[key]
            
            if completed_keys:
                info(f"[CALLBACK] 清理已完成任务: {len(completed_keys)}个", 'task')
    
    def get_all_tasks(self) -> Dict[str, dict]:
        """获取所有任务状态"""
        result = {}
        with self.lock:
            for key, task in self.tasks.items():
                result[key] = {
                    'task_type': task.task_type,
                    'task_id': task.task_id,
                    'name': task.name,
                    'is_running': task.is_running,
                    'is_completed': task.is_completed,
                }
        return result


def init_callback_manager(app):
    """初始化回调任务管理器"""
    manager = get_task_manager(app)
    info("[CALLBACK] 前端实时回调任务管理器已初始化", 'task')
    return manager
