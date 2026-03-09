# -*- coding: utf-8 -*-
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify, current_app
from flask_login import login_user, logout_user, login_required, current_user
from app.models import User
from app.services.security import (
    check_ip_locked, record_ip_fail, reset_ip_fail, 
    get_client_ip, get_client_type, log_login
)
from app import db, login_manager

auth_bp = Blueprint('auth', __name__)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """用户登录页面"""
    # 检测移动设备，跳转到移动端登录页面
    client_type = get_client_type()
    if client_type == 'Mobile' and request.method == 'GET':
        return redirect(url_for('mobile.mobile_login'))

    if current_user.is_authenticated:
        if current_user.is_admin:
            return redirect(url_for('admin.dashboard'))
        return redirect(url_for('user.dashboard'))
    
    if request.method == 'POST':
        phone = request.form.get('phone', '').strip()
        password = request.form.get('password', '')
        
        # 安全：输入验证
        if not phone or not password:
            flash('手机号和密码不能为空', 'danger')
            return render_template('login.html')
        
        # 手机号格式验证
        if not phone.isdigit() or len(phone) < 11:
            flash('手机号格式不正确', 'danger')
            return render_template('login.html')
        
        # 检查IP是否被锁定
        client_ip = get_client_ip()
        if check_ip_locked(client_ip):
            flash('您的IP已被锁定，请联系管理员', 'danger')
            log_login(None, phone, False, 'IP已被锁定')
            return render_template('login.html')
        
        # 验证用户
        user = User.query.filter_by(phone=phone).first()
        
        if not user:
            record_ip_fail(client_ip)
            flash('手机号或密码错误', 'danger')
            log_login(None, phone, False, '用户不存在')
            return render_template('login.html')
        
        # 检查用户是否被锁定
        if user.is_locked:
            flash('您的账号已被锁定，请联系管理员', 'danger')
            log_login(user.id, phone, False, '账号已被锁定')
            return render_template('login.html')
        
        # 检查密码
        if not user.check_password(password):
            # 增加失败次数
            user.login_fail_count += 1
            
            # 获取登录失败限制
            from app.services.security import get_config
            max_fail = int(get_config('login_fail_limit', '10'))
            
            if user.login_fail_count >= max_fail:
                user.is_locked = True
                db.session.commit()
                flash('登录失败次数过多，账号已被锁定', 'danger')
                log_login(user.id, phone, False, '登录失败次数过多，账号锁定')
            else:
                remaining = max_fail - user.login_fail_count
                db.session.commit()
                flash(f'手机号或密码错误，还剩{remaining}次机会', 'danger')
                log_login(user.id, phone, False, '密码错误')
            
            record_ip_fail(client_ip)
            return render_template('login.html')
        
        # 管理员不能从用户登录页面登录
        if user.is_admin:
            flash('请使用管理员登录页面', 'warning')
            return redirect(url_for('auth.admin_login'))
        
        # ========== 安全增强：登录成功处理 ==========
        # 重置失败次数
        user.login_fail_count = 0
        db.session.commit()
        reset_ip_fail(client_ip)
        
        # 安全：使用 remember=False 避免永久 cookie
        # 同时设置 session.permanent 以便按配置时间过期
        login_user(user, remember=False)
        session.permanent = True  # 启用会话过期时间
        
        # 记录最后活动时间（用于会话超时检测）
        import time
        session['_last_activity'] = time.time()
        
        # 记录登录日志
        log_login(user.id, phone, True)
        
        # 安全：记录登录会话信息用于检测会话劫持
        session['_login_ip'] = client_ip
        session['_login_time'] = time.time()
        session['_client_type'] = get_client_type()
        
        # 检查是否首次登录
        if user.is_first_login:
            flash('首次登录，请修改密码', 'warning')
            return redirect(url_for('user.change_password'))
        
        # 跳转到上次访问的页面或首页
        next_page = request.args.get('next')
        
        # 安全：验证 next_page 防止开放重定向攻击
        if next_page:
            from urllib.parse import urlparse
            parsed = urlparse(next_page)
            # 只允许相对路径或同源跳转
            if parsed.netloc and parsed.netloc != request.host:
                next_page = None
        
        if next_page:
            return redirect(next_page)
        return redirect(url_for('user.dashboard'))
    
    return render_template('login.html')

@auth_bp.route('/adminlogin', methods=['GET', 'POST'])
def admin_login():
    """管理员登录页面"""
    # 检测移动设备，跳转到移动端管理员登录页面
    client_type = get_client_type()
    if client_type == 'Mobile' and request.method == 'GET':
        return redirect(url_for('mobile.mobile_admin_login'))

    if current_user.is_authenticated:
        if current_user.is_admin:
            return redirect(url_for('admin.dashboard'))
        return redirect(url_for('user.dashboard'))
    
    if request.method == 'POST':
        phone = request.form.get('phone', '').strip()
        password = request.form.get('password', '')
        
        # 安全：输入验证
        if not phone or not password:
            flash('手机号和密码不能为空', 'danger')
            return render_template('admin_login.html')
        
        # 手机号格式验证
        if not phone.isdigit() or len(phone) < 11:
            flash('手机号格式不正确', 'danger')
            return render_template('admin_login.html')
        
        # 检查IP是否被锁定
        client_ip = get_client_ip()
        if check_ip_locked(client_ip):
            flash('您的IP已被锁定，请联系管理员', 'danger')
            log_login(None, phone, False, 'IP已被锁定')
            return render_template('admin_login.html')
        
        # 验证用户
        user = User.query.filter_by(phone=phone).first()
        
        if not user:
            record_ip_fail(client_ip)
            flash('手机号或密码错误', 'danger')
            log_login(None, phone, False, '用户不存在')
            return render_template('admin_login.html')
        
        # 检查是否是管理员
        if not user.is_admin:
            flash('您没有管理员权限', 'danger')
            log_login(user.id, phone, False, '非管理员尝试登录管理后台')
            return render_template('admin_login.html')
        
        # 检查用户是否被锁定
        if user.is_locked:
            flash('您的账号已被锁定', 'danger')
            log_login(user.id, phone, False, '账号已被锁定')
            return render_template('admin_login.html')
        
        # 检查密码
        if not user.check_password(password):
            user.login_fail_count += 1
            
            from app.services.security import get_config
            max_fail = int(get_config('login_fail_limit', '10'))
            
            if user.login_fail_count >= max_fail:
                user.is_locked = True
                db.session.commit()
                flash('登录失败次数过多，账号已被锁定', 'danger')
                log_login(user.id, phone, False, '登录失败次数过多，账号锁定')
            else:
                remaining = max_fail - user.login_fail_count
                db.session.commit()
                flash(f'手机号或密码错误，还剩{remaining}次机会', 'danger')
                log_login(user.id, phone, False, '密码错误')
            
            record_ip_fail(client_ip)
            return render_template('admin_login.html')
        
        # ========== 安全增强：管理员登录成功处理 ==========
        user.login_fail_count = 0
        db.session.commit()
        reset_ip_fail(client_ip)
        
        # 管理员使用短暂会话
        login_user(user, remember=False)
        session.permanent = True
        
        # 记录最后活动时间
        import time
        session['_last_activity'] = time.time()
        
        # 记录登录日志
        log_login(user.id, phone, True)
        
        # 安全：记录管理员登录会话信息
        session['_login_ip'] = client_ip
        session['_login_time'] = time.time()
        session['_client_type'] = get_client_type()
        session['_is_admin'] = True  # 标记管理员会话
        
        # 检查是否首次登录
        if user.is_first_login:
            flash('首次登录，请修改密码', 'warning')
            return redirect(url_for('user.change_password'))
        
        return redirect(url_for('admin.dashboard'))
    
    return render_template('admin_login.html')

@auth_bp.route('/logout', methods=['GET', 'POST'])
@login_required
def logout():
    """退出登录"""
    from flask import make_response
    import time

    # 调试日志
    current_app.logger.info(f'[Logout] 收到退出请求: method={request.method}, path={request.path}')
    current_app.logger.info(f'[Logout] 用户认证状态: is_authenticated={current_user.is_authenticated}')
    if current_user.is_authenticated:
        current_app.logger.info(f'[Logout] 用户信息: id={current_user.id}, is_admin={current_user.is_admin}')

    # 判断用户类型，决定跳转页面
    is_admin = current_user.is_authenticated and current_user.is_admin
    current_app.logger.info(f'[Logout] 是否为管理员: {is_admin}')

    # 清除 Flask-Login 会话
    logout_user()
    current_app.logger.info('[Logout] Flask-Login 会话已清除')

    # 清除 Flask session 数据
    session.clear()
    current_app.logger.info('[Logout] Flask session 已清除')

    # 设置响应
    if is_admin:
        redirect_url = url_for('auth.admin_login')
        current_app.logger.info(f'[Logout] 管理员退出，重定向到: {redirect_url}')
        response = make_response(redirect(redirect_url))
    else:
        redirect_url = url_for('auth.login')
        current_app.logger.info(f'[Logout] 普通用户退出，重定向到: {redirect_url}')
        response = make_response(redirect(redirect_url))

    # 明确删除 session cookie（通过设置过期时间为过去）
    # 指定路径和域以确保正确删除
    response.delete_cookie('session', path='/')
    current_app.logger.info('[Logout] Session cookie 已删除')
    
    # 删除 remember_token cookie（防止"记住我"自动登录）
    response.delete_cookie('remember_token', path='/')
    current_app.logger.info('[Logout] Remember token cookie 已删除')

    # 添加缓存控制头，防止浏览器缓存需要登录的页面
    # 使用更严格的缓存控制策略
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0, private'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    
    # 添加 Vary 头以确保浏览器不会错误地缓存此响应
    response.headers['Vary'] = 'Cookie, Authorization'
    
    current_app.logger.info(f'[Logout] 响应状态码: {response.status_code}')
    current_app.logger.info(f'[Logout] 响应头: {dict(response.headers)}')

    # 注意：不使用 flash 消息，因为 flash 需要 session，会创建新的 session cookie
    # 使用查询参数传递退出成功消息
    if is_admin:
        redirect_url = url_for('auth.admin_login', logout='success')
    else:
        redirect_url = url_for('auth.login', logout='success')
    
    # 重新创建响应，使用带查询参数的 URL
    response = make_response(redirect(redirect_url))
    
    # 重新添加缓存控制头（因为重新创建了 response）
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0, private'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    response.headers['Vary'] = 'Cookie, Authorization'
    
    # 删除 session cookie 和 remember_token cookie
    response.delete_cookie('session', path='/')
    response.delete_cookie('remember_token', path='/')
    
    current_app.logger.info(f'[Logout] 最终重定向 URL: {redirect_url}')
    current_app.logger.info('[Logout] 退出处理完成')
    return response

@auth_bp.route('/api/check-phone', methods=['POST'])
def check_phone():
    """API: 检查手机号是否存在"""
    # 安全：限制此 API 的请求频率（防止枚举攻击）
    client_ip = get_client_ip()
    
    # 检查请求频率（简单实现）
    from flask import g
    from time import time
    
    current_time = int(time())
    if hasattr(g, 'check_phone_last_time'):
        if current_time - g.check_phone_last_time < 1:  # 1秒内只能请求一次
            return jsonify({'error': '请求过于频繁'}), 429
    g.check_phone_last_time = current_time
    
    data = request.get_json()
    if not data:
        return jsonify({'error': '无效的请求数据'}), 400
    
    phone = data.get('phone', '').strip()
    
    # 输入验证
    if not phone or not phone.isdigit() or len(phone) < 11:
        return jsonify({'error': '手机号格式不正确'}), 400
    
    user = User.query.filter_by(phone=phone).first()
    
    return jsonify({
        'exists': user is not None,
        'is_admin': user.is_admin if user else False
    })
