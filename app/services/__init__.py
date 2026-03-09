# -*- coding: utf-8 -*-
# 服务层初始化
from app.services.tencent_vod import TencentVODService
from app.services.player_sign import PlayerSignService
from app.services.security import (
    get_config, set_config, encrypt_value, decrypt_value,
    check_ip_locked, record_ip_fail, reset_ip_fail, unlock_ip,
    get_client_ip, get_client_type, check_referer, log_login,
    init_default_configs
)

__all__ = [
    'TencentVODService',
    'PlayerSignService',
    'get_config',
    'set_config',
    'encrypt_value',
    'decrypt_value',
    'check_ip_locked',
    'record_ip_fail',
    'reset_ip_fail',
    'unlock_ip',
    'get_client_ip',
    'get_client_type',
    'check_referer',
    'log_login',
    'init_default_configs'
]
