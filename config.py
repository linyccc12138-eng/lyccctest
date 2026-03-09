# -*- coding: utf-8 -*-
import os
from dotenv import load_dotenv
from urllib.parse import quote_plus
from datetime import timedelta

# 加载环境变量
load_dotenv()

class Config:
    """基础配置"""
    # 安全：从环境变量获取密钥，有硬编码回退值
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'course-platform-secret-key-2024-miao-lyccc-xyz'
    
    # 数据库配置
    MYSQL_HOST = os.environ.get('MYSQL_HOST') or 'localhost'
    MYSQL_PORT = int(os.environ.get('MYSQL_PORT') or 3306)
    MYSQL_USER = os.environ.get('MYSQL_USER') or 'root'
    MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD') or 'password'
    MYSQL_DB = os.environ.get('MYSQL_DB') or 'course_vod'
    
    # 数据库配置 - 优先使用DATABASE_URL环境变量（支持SQLite）
    # 对密码进行URL编码以处理特殊字符
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        f'mysql+pymysql://{MYSQL_USER}:{quote_plus(MYSQL_PASSWORD)}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DB}?charset=utf8mb4'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # 腾讯云VOD配置
    TENCENT_APP_ID = os.environ.get('TENCENT_APP_ID') or ''
    TENCENT_SECRET_ID = os.environ.get('TENCENT_SECRET_ID') or ''
    TENCENT_SECRET_KEY = os.environ.get('TENCENT_SECRET_KEY') or ''
    TENCENT_PLAY_KEY = os.environ.get('TENCENT_PLAY_KEY') or ''
    TENCENT_LICENSE_URL = os.environ.get('TENCENT_LICENSE_URL') or ''
    TENCENT_LICENSE_KEY = os.environ.get('TENCENT_LICENSE_KEY') or ''
    PSIGN_EXPIRE_SECONDS = int(os.environ.get('PSIGN_EXPIRE_SECONDS') or 3600)
    
    # ========== 安全增强配置 ==========
    
    # 密码哈希配置
    BCRYPT_LOG_ROUNDS = 12
    
    # Session 安全配置
    # 会话 cookie 只在 HTTPS 下传输（生产环境必须为 True）
    SESSION_COOKIE_SECURE = False  # 开发环境设为False，生产环境设为True
    # 会话 cookie 禁止 JavaScript 访问（防止 XSS 窃取会话）
    SESSION_COOKIE_HTTPONLY = True
    # 会话 cookie 跨站请求策略
    SESSION_COOKIE_SAMESITE = 'Lax'
    # 永久会话生命周期 - 2小时无操作自动过期（修复会话不过期问题）
    PERMANENT_SESSION_LIFETIME = timedelta(hours=2)
    # 会话刷新每次请求后重置过期时间（保持活跃状态）
    SESSION_REFRESH_EACH_REQUEST = True
    
    # CSRF 保护配置
    # 启用 CSRF 保护
    WTF_CSRF_ENABLED = True
    # CSRF token 有效期（与 session 过期时间一致）
    WTF_CSRF_TIME_LIMIT = 7200  # 2小时，单位秒
    # CSRF token 验证失败时的错误信息
    WTF_CSRF_ERROR_MESSAGE = '安全验证失败，请刷新页面重试'
    # CSRF Token HTTP Headers - 支持 X-CSRF-Token 和 X-CSRFToken
    WTF_CSRF_HEADERS = {'X-CSRF-Token', 'X-CSRFToken'}
    
    # 文件上传安全配置
    # 最大上传文件大小（100MB）
    MAX_CONTENT_LENGTH = 100 * 1024 * 1024
    # 允许上传的文件扩展名
    ALLOWED_EXTENSIONS = {'mp4', 'mov', 'avi', 'mkv', 'flv', 'wmv'}
    # 允许上传的图片扩展名
    ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    
    # 访问限制配置
    DEFAULT_HOURLY_ACCESS_LIMIT = 10
    DEFAULT_LOGIN_FAIL_LIMIT = 10
    DEFAULT_IP_FAIL_LIMIT = 10
    
    # 幽灵水印配置
    GHOST_WATERMARK_LINE1 = 'Serendipity4869'
    
    # 播放器签名过期时间（秒）
    PSIGN_EXPIRE_SECONDS = 3600
    
    # 允许的主机头（防止 Host Header 攻击）
    ALLOWED_HOSTS = ['localhost', '127.0.0.1', 'magic.lyccc.xyz']
    
    # 安全响应头配置
    # 是否添加安全响应头
    SECURITY_HEADERS_ENABLED = True


class DevelopmentConfig(Config):
    """开发环境配置"""
    DEBUG = True
    SESSION_COOKIE_SECURE = False
    # 开发环境可以适当放宽 CSRF 检查（建议保持启用）
    WTF_CSRF_ENABLED = True
    # 调试工具栏（如果有）需要禁用 CSRF
    DEBUG_TB_INTERCEPT_REDIRECTS = False


class ProductionConfig(Config):
    """生产环境配置"""
    DEBUG = False
    # 生产环境强制 HTTPS
    SESSION_COOKIE_SECURE = True
    # 生产环境增强密码哈希
    BCRYPT_LOG_ROUNDS = 13
    # 生产环境必须启用 CSRF
    WTF_CSRF_ENABLED = True
    # 生产环境严格 SameSite
    SESSION_COOKIE_SAMESITE = 'Strict'
    # 生产环境禁用 warnings
    PROPAGATE_EXCEPTIONS = False


class TestingConfig(Config):
    """测试环境配置"""
    DEBUG = True
    TESTING = True
    # 测试环境使用内存数据库
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    # 测试环境禁用 CSRF
    WTF_CSRF_ENABLED = False
    # 测试环境使用更快的密码哈希
    BCRYPT_LOG_ROUNDS = 4


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
