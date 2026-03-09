# -*- coding: utf-8 -*-
from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
from app.services.security import get_config, set_config
from app.services.tencent_vod import TencentVODService

config_bp = Blueprint('config', __name__)

@config_bp.route('/api/tencent', methods=['GET'])
@login_required
def get_tencent_config():
    """API: 获取腾讯云配置（前端使用）"""
    # 只返回AppID、LicenseURL和LicenseKey，敏感信息不返回
    return jsonify({
        'app_id': get_config('app_id', ''),
        'license_url': get_config('license_url', ''),
        'license_key': get_config('license_key', '')
    })

@config_bp.route('/api/test-vod', methods=['POST'])
@login_required
def test_vod_connection():
    """API: 测试VOD连接"""
    if not current_user.is_admin:
        return jsonify({'error': '没有权限'}), 403
    
    try:
        vod_service = TencentVODService()
        result = vod_service.test_connection()
        
        return jsonify(result)
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })
