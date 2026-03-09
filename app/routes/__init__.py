# -*- coding: utf-8 -*-
# 路由初始化
from app.routes.auth import auth_bp
from app.routes.admin import admin_bp
from app.routes.user import user_bp
from app.routes.course import course_bp
from app.routes.play import play_bp
from app.routes.config import config_bp
from app.routes.callback import callback_bp

__all__ = ['auth_bp', 'admin_bp', 'user_bp', 'course_bp', 'play_bp', 'config_bp', 'callback_bp']
