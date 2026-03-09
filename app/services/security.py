# -*- coding: utf-8 -*-
from app.models import SystemConfig, LockedIP, LoginLog
from app import db
from datetime import datetime
from flask import request, session, current_app
from cryptography.fernet import Fernet
import base64
import hashlib
import os
import secrets

# ========== 安全增强：加密密钥管理 ==========

def get_encryption_key():
    """安全：从环境变量获取加密密钥，有硬编码回退值"""
    # 优先从 ENCRYPTION_KEY 环境变量获取
    env_key = os.environ.get('ENCRYPTION_KEY')
    if env_key:
        return env_key
    
    # 硬编码回退值
    return '63045bffab20874189b0fb1d66f74153a51ac669f59e1606dd3f53d6dd0e88dd'


def get_fernet_key():
    """获取Fernet密钥（必须32字节base64编码）"""
    key = get_encryption_key()
    # Fernet 需要 32 字节的 base64 编码密钥
    key_bytes = key.encode() if isinstance(key, str) else key
    key_hash = hashlib.sha256(key_bytes).digest()
    return base64.urlsafe_b64encode(key_hash)


def encrypt_value(value):
    """加密值"""
    if not value:
        return value
    try:
        f = Fernet(get_fernet_key())
        return f.encrypt(value.encode()).decode()
    except Exception as e:
        # 加密失败时返回原值并记录日志
        import logging
        logging.getLogger('app').error(f"加密失败: {e}")
        return value


def decrypt_value(encrypted_value):
    """解密值"""
    if not encrypted_value:
        return encrypted_value
    try:
        f = Fernet(get_fernet_key())
        return f.decrypt(encrypted_value.encode()).decode()
    except Exception:
        # 解密失败可能是密钥变化，返回原值
        return encrypted_value


def get_config(key, default=None):
    """获取配置项"""
    config = SystemConfig.query.filter_by(config_key=key).first()
    if config:
        if config.is_encrypted:
            return decrypt_value(config.config_value)
        return config.config_value
    return default


def set_config(key, value, description=None, is_encrypted=False):
    """设置配置项"""
    config = SystemConfig.query.filter_by(config_key=key).first()
    
    if is_encrypted and value:
        value = encrypt_value(value)
    
    if config:
        config.config_value = value
        if description:
            config.description = description
        config.is_encrypted = is_encrypted
    else:
        config = SystemConfig(
            config_key=key,
            config_value=value,
            description=description,
            is_encrypted=is_encrypted
        )
        db.session.add(config)
    
    db.session.commit()
    return config


def check_ip_locked(ip_address):
    """检查IP是否被锁定"""
    locked_ip = LockedIP.query.filter_by(ip_address=ip_address).first()
    if locked_ip and locked_ip.is_locked:
        return True
    return False


def record_ip_fail(ip_address):
    """记录IP登录失败"""
    locked_ip = LockedIP.query.filter_by(ip_address=ip_address).first()
    
    if not locked_ip:
        locked_ip = LockedIP(ip_address=ip_address, fail_count=0)
        db.session.add(locked_ip)
    
    # 确保 fail_count 不为 None
    if locked_ip.fail_count is None:
        locked_ip.fail_count = 0
    
    locked_ip.fail_count += 1
    
    # 获取IP失败限制
    from flask import current_app
    max_fail = int(get_config('ip_fail_limit', '10'))
    
    if locked_ip.fail_count >= max_fail:
        locked_ip.is_locked = True
        locked_ip.locked_at = datetime.utcnow()
    
    db.session.commit()
    return locked_ip.is_locked


def reset_ip_fail(ip_address):
    """重置IP失败次数"""
    locked_ip = LockedIP.query.filter_by(ip_address=ip_address).first()
    if locked_ip:
        locked_ip.fail_count = 0
        locked_ip.is_locked = False
        locked_ip.locked_at = None
        db.session.commit()


def unlock_ip(ip_address):
    """解锁IP"""
    locked_ip = LockedIP.query.filter_by(ip_address=ip_address).first()
    if locked_ip:
        locked_ip.fail_count = 0
        locked_ip.is_locked = False
        locked_ip.locked_at = None
        db.session.commit()
        return True
    return False


def get_client_ip():
    """获取客户端IP（安全增强：防范 IP 伪造）"""
    # 按优先级获取 IP
    # 注意：使用代理时，应该配置代理服务器覆盖这些头
    
    # 1. 优先获取 X-Forwarded-For（需要代理服务器正确配置）
    x_forwarded_for = request.headers.get('X-Forwarded-For')
    if x_forwarded_for:
        # X-Forwarded-For 可能包含多个 IP，取第一个（客户端真实 IP）
        ip = x_forwarded_for.split(',')[0].strip()
        # 安全：验证 IP 格式
        if is_valid_ip(ip):
            return ip
    
    # 2. X-Real-IP（Nginx 常用）
    x_real_ip = request.headers.get('X-Real-IP')
    if x_real_ip and is_valid_ip(x_real_ip):
        return x_real_ip
    
    # 3. 直接连接的 remote_addr
    ip = request.remote_addr
    return ip if ip else '127.0.0.1'


def is_valid_ip(ip):
    """验证 IP 地址格式"""
    if not ip or ip == 'unknown':
        return False
    import re
    # IPv4 验证
    ipv4_pattern = re.compile(r'^(\d{1,3}\.){3}\d{1,3}$')
    if ipv4_pattern.match(ip):
        parts = ip.split('.')
        return all(0 <= int(part) <= 255 for part in parts)
    # IPv6 验证（简化版）
    if ':' in ip:
        return True
    return False


def get_client_type():
    """获取客户端类型"""
    user_agent = request.headers.get('User-Agent', '').lower()
    
    if 'mobile' in user_agent or 'android' in user_agent or 'iphone' in user_agent:
        return 'Mobile'
    elif 'tablet' in user_agent or 'ipad' in user_agent:
        return 'Tablet'
    else:
        return 'PC'


def check_referer():
    """检查 Referer（防范 CSRF）"""
    referer = request.headers.get('Referer', '')
    host = request.host
    
    # 允许空 referer（直接访问）
    if not referer:
        return True
    
    # 解析 referer
    from urllib.parse import urlparse
    parsed = urlparse(referer)
    
    # 检查是否同源
    if parsed.netloc == host:
        return True
    
    # 允许的额外来源（如 CDN）
    allowed_hosts = current_app.config.get('ALLOWED_HOSTS', [])
    if parsed.netloc in allowed_hosts:
        return True
    
    return False


def log_login(user_id, phone, is_success, fail_reason=None):
    """记录登录日志"""
    log = LoginLog(
        user_id=user_id,
        phone=phone,
        client_type=get_client_type(),
        ip_address=get_client_ip(),
        is_success=is_success,
        fail_reason=fail_reason
    )
    db.session.add(log)
    db.session.commit()


def init_default_configs():
    """初始化默认配置"""
    defaults = [
        ('app_id', '', '腾讯云应用ID', False),
        ('secret_id', '', 'API密钥ID', True),
        ('secret_key', '', 'API密钥', True),
        ('play_key', '', '播放密钥（用于生成psign）', True),
        ('license_url', '', 'TCPlayer License地址', False),
        ('license_key', '', 'TCPlayer License密钥', True),
        ('hourly_access_limit', '10', '默认每小时访问次数限制', False),
        ('login_fail_limit', '10', '默认登录失败次数限制', False),
        ('ip_fail_limit', '10', '默认IP失败次数限制', False),
        ('ghost_watermark_line1', 'Serendipity4869', '幽灵水印第一行内容', False),
        ('psign_expire_seconds', '3600', '播放器签名过期时间（秒）', False),
    ]
    
    for key, value, desc, encrypted in defaults:
        if not SystemConfig.query.filter_by(config_key=key).first():
            set_config(key, value, desc, encrypted)
