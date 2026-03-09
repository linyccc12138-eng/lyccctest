# -*- coding: utf-8 -*-
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app.models import User, Course, Chapter, PlayLog
from app.services.security import check_referer
from app import db

user_bp = Blueprint('user', __name__)

@user_bp.before_request
def check_user():
    """检查是否为普通用户或允许管理员访问修改密码"""
    if not current_user.is_authenticated:
        return redirect(url_for('auth.login'))
    # 允许管理员访问修改密码页面
    if current_user.is_admin and request.endpoint != 'user.change_password':
        return redirect(url_for('admin.dashboard'))
    # 检查是否首次登录（仅普通用户）
    if not current_user.is_admin and current_user.is_first_login and request.endpoint != 'user.change_password':
        flash('首次登录，请修改密码', 'warning')
        return redirect(url_for('user.change_password'))

@user_bp.route('/')
@login_required
def dashboard():
    """用户仪表盘/首页"""
    # 获取有权限的课程
    allowed_courses = current_user.get_allowed_courses()
    
    # 获取上次播放记录
    last_play = PlayLog.query.filter_by(user_id=current_user.id)\
        .order_by(PlayLog.play_time.desc()).first()
    
    return render_template('user/dashboard.html', 
                          courses=allowed_courses,
                          last_play=last_play)

@user_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    """修改密码"""
    if request.method == 'POST':
        current_password = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        # 验证当前密码
        if not current_user.check_password(current_password):
            flash('当前密码错误', 'danger')
            return render_template('user/change_password.html')
        
        # 验证新密码
        if len(new_password) < 6:
            flash('新密码长度至少为6位', 'danger')
            return render_template('user/change_password.html')
        
        if new_password != confirm_password:
            flash('两次输入的新密码不一致', 'danger')
            return render_template('user/change_password.html')
        
        # 更新密码
        current_user.set_password(new_password)
        current_user.is_first_login = False
        db.session.commit()
        
        flash('密码修改成功', 'success')
        if current_user.is_admin:
            return redirect(url_for('admin.dashboard'))
        return redirect(url_for('user.dashboard'))
    
    return render_template('user/change_password.html')

@user_bp.route('/history')
@login_required
def history():
    """播放历史"""
    # 获取近10次播放记录
    play_logs = PlayLog.query.filter_by(user_id=current_user.id)\
        .order_by(PlayLog.play_time.desc()).limit(10).all()
    
    return render_template('user/history.html', play_logs=play_logs)


@user_bp.route('/my-courses')
@login_required
def my_courses():
    """我的课程 - 仅显示有权限的课程"""
    # 获取有权限的课程
    allowed_courses = current_user.get_allowed_courses()
    
    return render_template('user/my_courses.html', courses=allowed_courses)

@user_bp.route('/api/profile', methods=['GET'])
@login_required
def get_profile():
    """API: 获取用户信息"""
    return jsonify({
        'id': current_user.id,
        'phone': current_user.phone,
        'remark': current_user.remark,
        'created_at': current_user.created_at.strftime('%Y-%m-%d %H:%M:%S') if current_user.created_at else None
    })
