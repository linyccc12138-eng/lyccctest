# -*- coding: utf-8 -*-
"""
Gunicorn配置文件
"""
import multiprocessing

# 绑定地址
bind = "0.0.0.0:8000"

# 工作进程数
workers = multiprocessing.cpu_count() * 2 + 1

# 工作模式
worker_class = "sync"

# 超时时间
timeout = 120

# 保持连接时间
keepalive = 5

# 错误日志
errorlog = "/var/log/gunicorn/error.log"

# 访问日志
accesslog = "/var/log/gunicorn/access.log"

# 日志级别
loglevel = "info"

# 进程名称
proc_name = "course_vod"

# PID文件
pidfile = "/var/run/gunicorn.pid"

# 守护进程模式
daemon = False
