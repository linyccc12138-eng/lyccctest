# -*- coding: utf-8 -*-
from flask import Flask, request, g
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from datetime import datetime, timedelta
from config import config
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

db = SQLAlchemy()
login_manager = LoginManager()
# CSRF 保护实例
csrf = CSRFProtect()


def create_app(config_name=None):
    """应用工厂函数"""
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'default')

    app = Flask(__name__,
                template_folder='templates',
                static_folder='static')

    app.config.from_object(config[config_name])

    # 初始化扩展
    db.init_app(app)
    login_manager.init_app(app)
    
    # ========== 安全增强：初始化 CSRF 保护 ==========
    csrf.init_app(app)
    
    # 从 CSRF 保护中排除回调路由（外部服务需要直接访问）
    csrf.exempt('app.routes.callback.vod_callback')
    csrf.exempt('app.routes.callback.pull_events')
    csrf.exempt('app.routes.callback.get_event_status')
    csrf.exempt('app.routes.callback.get_video_status')
    csrf.exempt('app.routes.callback.batch_video_status')
    csrf.exempt('app.routes.callback.get_processing_videos')
    
    # 排除 API 路由（API 使用其他认证方式）
    # 这些路由需要 JWT 或 API Key 认证，不使用 CSRF
    
    # 初始化日志服务（延迟到第一个请求时初始化，确保应用上下文可用）
    _logging_initialized = False

    @app.before_request
    def init_logging():
        nonlocal _logging_initialized
        if _logging_initialized:
            return
        _logging_initialized = True
        try:
            from app.services.security import get_config
            from app.services.logger import init_logger_service

            log_level = get_config('log_level', 'INFO')
            console_output = get_config('log_console_output', 'false').lower() == 'true'
            backup_count = int(get_config('log_backup_count', '20'))

            init_logger_service(log_level, console_output, backup_count)
            app.logger.info(f"日志服务初始化完成: level={log_level}, console={console_output}, backup={backup_count}")
        except Exception as e:
            import logging
            logging.getLogger('app').error(f"初始化日志服务失败: {e}")

    # ========== 安全增强：会话管理和安全响应头 ==========
    
    @app.after_request
    def set_security_headers(response):
        """添加安全响应头"""
        if app.config.get('SECURITY_HEADERS_ENABLED', True):
            # 内容安全策略（CSP）- 防止 XSS 攻击
            # 限制资源加载来源，禁止内联脚本
            response.headers['Content-Security-Policy'] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' https://web.sdk.qcloud.com https://cdn.tiny.cloud https://cdn-go.cn https://unpkg.com https://cdn.jsdelivr.net https://cdn.tailwindcss.com; "
                "script-src-elem 'self' 'unsafe-inline' https://web.sdk.qcloud.com https://cdn.tiny.cloud https://cdn-go.cn https://unpkg.com https://cdn.jsdelivr.net https://cdn.tailwindcss.com; "
                "worker-src 'self' blob:; "
                "style-src 'self' 'unsafe-inline' https://cdn.tiny.cloud https://web.sdk.qcloud.com https://fonts.googleapis.com https://cdn.jsdelivr.net https://unpkg.com; "
                "style-src-elem 'self' 'unsafe-inline' https://cdn.tiny.cloud https://web.sdk.qcloud.com https://fonts.googleapis.com https://cdn.jsdelivr.net https://unpkg.com; "
                "img-src 'self' data: https: blob:; "
                "media-src 'self' blob: https:; "
                "font-src 'self' data: https://cdn.tiny.cloud https://fonts.gstatic.com https://cdn.jsdelivr.net; "
                "connect-src 'self' https://cdn.tiny.cloud https://*.vod2.myqcloud.com https://cdn-go.cn "
                "https://playvideo.qcloud.com https://bkplayvideo.qcloud.com https://*.qcloud.com "
                "https://datacenter.live.qcloud.com https://*.trtcube-license.cn "
                "https://magic.vod.lyccc.xyz https://1300598172.vod-qcloud.com "
                "https://drm.vodplayvideo.net; "
                "frame-ancestors 'self'; "
                "base-uri 'self'; "
                "form-action 'self';"
            )
            
            # 防止 MIME 类型嗅探
            response.headers['X-Content-Type-Options'] = 'nosniff'
            
            # 启用 XSS 过滤器
            response.headers['X-XSS-Protection'] = '1; mode=block'
            
            # 点击劫持保护
            response.headers['X-Frame-Options'] = 'SAMEORIGIN'
            
            # 严格的传输安全（仅 HTTPS）
            if app.config.get('SESSION_COOKIE_SECURE', False):
                response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
            
            # 引用策略
            response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
            
            # 权限策略
            response.headers['Permissions-Policy'] = (
                'accelerometer=(), camera=(), geolocation=(), gyroscope=(), '
                'magnetometer=(), microphone=(), payment=(), usb=()'
            )

            # 动态页面禁用缓存，防止退出后浏览器显示缓存页面
            if 'Cache-Control' not in response.headers:
                response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
                response.headers['Pragma'] = 'no-cache'
                response.headers['Expires'] = '0'

        return response
    
    @app.before_request
    def session_management():
        """会话管理：检查会话过期时间"""
        from flask_login import current_user
        
        if current_user.is_authenticated:
            # 获取最后活动时间
            last_activity = session.get('_last_activity')
            now = datetime.utcnow().timestamp()
            
            if last_activity:
                # 计算不活动时间（秒）
                inactive_time = now - last_activity
                max_inactive = app.config.get('PERMANENT_SESSION_LIFETIME', timedelta(hours=2)).total_seconds()
                
                # 如果超过最大不活动时间，强制登出
                if inactive_time > max_inactive:
                    from flask_login import logout_user
                    from flask import flash, redirect, url_for
                    
                    logout_user()
                    session.clear()
                    flash('会话已过期，请重新登录', 'warning')
                    return redirect(url_for('auth.login'))
            
            # 更新最后活动时间
            session['_last_activity'] = now
    
    @app.before_request
    def check_host_header():
        """检查 Host Header 防止 Host Header 攻击"""
        allowed_hosts = app.config.get('ALLOWED_HOSTS', [])
        if not allowed_hosts:
            return
        
        host = request.host.split(':')[0]  # 去除端口
        if host not in allowed_hosts:
            app.logger.warning(f"拒绝非法 Host 头请求: {host}")
            from flask import abort
            abort(400, description='Invalid Host header')

    # 登录配置
    login_manager.login_view = 'auth.login'
    login_manager.login_message = '请先登录'
    login_manager.login_message_category = 'warning'
    
    # 登录刷新时间（每次请求刷新会话）
    login_manager.refresh_view = 'auth.login'
    login_manager.needs_refresh_message = '会话已过期，请重新登录'
    login_manager.needs_refresh_message_category = 'warning'

    # 注册蓝图
    from app.routes.auth import auth_bp
    from app.routes.admin import admin_bp
    from app.routes.user import user_bp
    from app.routes.course import course_bp
    from app.routes.play import play_bp
    from app.routes.config import config_bp
    from app.routes.callback import callback_bp
    from app.routes.mobile import mobile_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(user_bp, url_prefix='/user')
    app.register_blueprint(course_bp, url_prefix='/course')
    app.register_blueprint(play_bp, url_prefix='/play')
    app.register_blueprint(config_bp, url_prefix='/config')
    app.register_blueprint(callback_bp)
    app.register_blueprint(mobile_bp)

    # 初始化事件消费定时任务
    try:
        from app.tasks.event_consumer import init_event_consumer
        scheduler = init_event_consumer(app)
        app.scheduler = scheduler  # 保存引用以便后续管理
    except Exception as e:
        import logging
        logging.getLogger('app').error(f"初始化事件消费定时任务失败: {e}")

    # 初始化前端实时回调任务管理器
    try:
        from app.tasks.callback_manager import init_callback_manager
        callback_manager = init_callback_manager(app)
        app.callback_manager = callback_manager
    except Exception as e:
        import logging
        logging.getLogger('app').error(f"初始化前端实时回调管理器失败: {e}")

    # 根路由
    @app.route('/')
    def index():
        from flask import redirect, url_for
        return redirect(url_for('auth.login'))

    # 全局错误处理
    @app.errorhandler(404)
    def not_found(error):
        from flask import render_template
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def internal_error(error):
        from flask import render_template
        db.session.rollback()
        return render_template('errors/500.html'), 500
    
    # CSRF 错误处理
    @app.errorhandler(400)
    def handle_csrf_error(error):
        """处理 CSRF 验证失败"""
        if 'CSRF' in str(error.description) or 'csrf' in str(error.description).lower():
            from flask import flash, redirect, request, url_for, jsonify
            # AJAX 请求返回 JSON 错误
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({
                    'success': False,
                    'error': app.config.get('WTF_CSRF_ERROR_MESSAGE', '安全验证失败，请刷新页面重试')
                }), 400
            flash(app.config.get('WTF_CSRF_ERROR_MESSAGE', '安全验证失败，请刷新页面重试'), 'danger')
            # 返回登录页面或原页面
            return redirect(request.referrer or url_for('auth.login'))
        return error

    # 注册自定义过滤器
    from datetime import datetime, timedelta

    @app.template_filter('utc8')
    def utc8_filter(value):
        """将UTC时间转换为东八区时间"""
        if value is None:
            return '-'
        if isinstance(value, datetime):
            # 加8小时转换为东八区
            utc8_time = value + timedelta(hours=8)
            return utc8_time.strftime('%Y-%m-%d %H:%M:%S')
        return value
    
    # 安全：HTML 转义过滤器
    @app.template_filter('safe_html')
    def safe_html_filter(value):
        """清理 HTML 内容，只允许白名单标签"""
        import bleach
        allowed_tags = ['p', 'br', 'strong', 'em', 'u', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
                       'ul', 'ol', 'li', 'a', 'img', 'div', 'span', 'blockquote', 'code', 'pre']
        allowed_attrs = {
            '*': ['class'],
            'a': ['href', 'title', 'target'],
            'img': ['src', 'alt', 'width', 'height'],
        }
        return bleach.clean(value, tags=allowed_tags, attributes=allowed_attrs) if value else value

    # 上下文处理器
    @app.context_processor
    def inject_globals():
        from flask_login import current_user
        from app.services.security import get_config
        from flask_wtf.csrf import generate_csrf
        return {
            'current_user': current_user,
            'site_name': '课程视频学习平台',
            'get_config': get_config,
            # 注入 CSRF token 到所有模板
            'csrf_token': generate_csrf
        }

    # 全局请求钩子：检查用户是否被锁定
    @app.before_request
    def check_user_lock_status():
        from flask_login import current_user, logout_user
        from flask import request, redirect, url_for, flash

        # 只检查已登录的普通用户（管理员不受此限制，或者也可以加上）
        if current_user.is_authenticated:
            # 重新查询用户最新状态（避免缓存）
            from app.models import User
            user = User.query.get(current_user.id)

            if user and user.is_locked:
                # 用户被锁定，强制登出
                logout_user()
                flash('您的账号已被锁定，请联系管理员', 'danger')

                # 根据原请求路径决定重定向位置
                if request.blueprint == 'admin' or request.path.startswith('/admin'):
                    return redirect(url_for('auth.admin_login'))
                else:
                    return redirect(url_for('auth.login'))

    return app

# 导入 session 以便在其他模块使用
from flask import session
