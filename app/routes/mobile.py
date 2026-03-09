# -*- coding: utf-8 -*-
"""
移动端路由模块
提供移动端适配的页面路由
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from flask_login import login_user, logout_user, login_required, current_user
from app.models import User, Course, Chapter, PlayLog, UserCoursePermission
from app.services.security import (
    check_ip_locked, record_ip_fail, reset_ip_fail, 
    get_client_ip, get_client_type, log_login
)
from app import db

mobile_bp = Blueprint('mobile', __name__, url_prefix='/mobile')

# ========== 移动端用户端路由 ==========

@mobile_bp.route('/login', methods=['GET', 'POST'])
def mobile_login():
    """移动端用户登录页面"""
    if current_user.is_authenticated:
        if current_user.is_admin:
            return redirect(url_for('mobile.mobile_admin_dashboard'))
        return redirect(url_for('mobile.mobile_dashboard'))
    
    if request.method == 'POST':
        phone = request.form.get('phone', '').strip()
        password = request.form.get('password', '')
        
        if not phone or not password:
            flash('手机号和密码不能为空', 'danger')
            return render_template('mobile/login-mobile.html')
        
        if not phone.isdigit() or len(phone) < 11:
            flash('手机号格式不正确', 'danger')
            return render_template('mobile/login-mobile.html')
        
        # 检查IP是否被锁定
        client_ip = get_client_ip()
        if check_ip_locked(client_ip):
            flash('您的IP已被锁定，请联系管理员', 'danger')
            return render_template('mobile/login-mobile.html')
        
        user = User.query.filter_by(phone=phone).first()
        
        if not user:
            record_ip_fail(client_ip)
            flash('手机号或密码错误', 'danger')
            return render_template('mobile/login-mobile.html')
        
        if user.is_locked:
            flash('您的账号已被锁定，请联系管理员', 'danger')
            return render_template('mobile/login-mobile.html')
        
        if not user.check_password(password):
            user.login_fail_count += 1
            from app.services.security import get_config
            max_fail = int(get_config('login_fail_limit', '10'))
            
            if user.login_fail_count >= max_fail:
                user.is_locked = True
                db.session.commit()
                flash('登录失败次数过多，账号已被锁定', 'danger')
            else:
                remaining = max_fail - user.login_fail_count
                db.session.commit()
                flash(f'手机号或密码错误，还剩{remaining}次机会', 'danger')
            
            record_ip_fail(client_ip)
            return render_template('mobile/login-mobile.html')
        
        # 管理员不能从用户登录页面登录
        if user.is_admin:
            flash('请使用管理员登录页面', 'warning')
            return redirect(url_for('mobile.mobile_admin_login'))
        
        # 登录成功处理
        user.login_fail_count = 0
        db.session.commit()
        reset_ip_fail(client_ip)
        
        login_user(user, remember=False)
        session.permanent = True
        
        import time
        session['_last_activity'] = time.time()
        log_login(user.id, phone, True)
        
        session['_login_ip'] = client_ip
        session['_login_time'] = time.time()
        session['_client_type'] = get_client_type()
        
        if user.is_first_login:
            flash('首次登录，请修改密码', 'warning')
            return redirect(url_for('mobile.mobile_change_password'))
        
        return redirect(url_for('mobile.mobile_dashboard'))
    
    return render_template('mobile/login-mobile.html')


@mobile_bp.route('/dashboard')
@login_required
def mobile_dashboard():
    """移动端用户仪表盘"""
    if current_user.is_admin:
        return redirect(url_for('mobile.mobile_admin_dashboard'))
    
    allowed_courses = current_user.get_allowed_courses()
    last_play = PlayLog.query.filter_by(user_id=current_user.id)\
        .order_by(PlayLog.play_time.desc()).first()
    
    # 确保last_play的progress有默认值
    if last_play and last_play.progress is None:
        last_play.progress = 0
    
    # 计算统计数据
    my_courses_count = len(allowed_courses)
    completed_chapters_count = PlayLog.query.filter_by(user_id=current_user.id)\
        .filter(PlayLog.progress >= 95).count()
    learning_hours = db.session.query(db.func.sum(PlayLog.duration))\
        .filter_by(user_id=current_user.id).scalar() or 0
    learning_hours = round(learning_hours / 3600, 1)
    
    stats = {
        'my_courses_count': my_courses_count,
        'completed_chapters_count': completed_chapters_count,
        'learning_hours': learning_hours
    }
    
    # 获取用户有权限的课程ID列表
    allowed_course_ids = [c.id for c in allowed_courses]
    
    return render_template('mobile/dashboard-mobile.html',
                          courses=allowed_courses,
                          recommended_courses=allowed_courses[:4] if allowed_courses else [],
                          allowed_course_ids=allowed_course_ids,
                          last_played=last_play,
                          stats=stats)


@mobile_bp.route('/courses')
@login_required
def mobile_courses():
    """移动端课程列表"""
    if current_user.is_admin:
        return redirect(url_for('mobile.mobile_admin_dashboard'))
    
    courses = Course.query.all()
    permissions = UserCoursePermission.query.filter_by(user_id=current_user.id).all()
    allowed_course_ids = [p.course_id for p in permissions]
    
    return render_template('mobile/courses-mobile.html',
                          courses=courses,
                          allowed_course_ids=allowed_course_ids)


@mobile_bp.route('/course/<int:course_id>')
@login_required
def mobile_course_detail(course_id):
    """移动端课程详情"""
    if current_user.is_admin:
        return redirect(url_for('mobile.mobile_admin_dashboard'))
    
    course = Course.query.get_or_404(course_id)
    chapters = Chapter.query.filter_by(course_id=course_id).order_by(Chapter.sort_order).all()
    has_permission = current_user.has_course_permission(course_id)
    
    # 获取用户有权限的课程ID列表
    allowed_courses = current_user.get_allowed_courses()
    allowed_course_ids = [c.id for c in allowed_courses]
    
    # 获取学习进度
    progress = None
    last_chapter = None
    if has_permission:
        # 计算学习进度
        completed_chapters = PlayLog.query.filter_by(
            user_id=current_user.id,
            course_id=course_id
        ).filter(PlayLog.progress >= 95).all()
        completed_chapter_ids = [log.chapter_id for log in completed_chapters]
        
        total_chapters = len(chapters)
        completed_count = len(completed_chapter_ids)
        progress_percentage = (completed_count / total_chapters * 100) if total_chapters > 0 else 0
        
        progress = {
            'completed_chapter_ids': completed_chapter_ids,
            'percentage': progress_percentage
        }
        
        # 获取最后学习的章节
        last_play = PlayLog.query.filter_by(user_id=current_user.id, course_id=course_id)\
            .order_by(PlayLog.play_time.desc()).first()
        if last_play:
            last_chapter = Chapter.query.get(last_play.chapter_id)
        elif chapters:
            last_chapter = chapters[0]
    
    return render_template('mobile/course_detail-mobile.html',
                          course=course,
                          chapters=chapters,
                          has_permission=has_permission,
                          allowed_course_ids=allowed_course_ids,
                          progress=progress,
                          last_chapter=last_chapter)


@mobile_bp.route('/play/<int:chapter_id>')
@login_required
def mobile_play(chapter_id):
    """移动端视频播放"""
    if current_user.is_admin:
        return redirect(url_for('mobile.mobile_admin_dashboard'))
    
    chapter = Chapter.query.get_or_404(chapter_id)
    course = Course.query.get_or_404(chapter.course_id)
    
    if not current_user.has_course_permission(course.id):
        flash('您没有权限观看此课程', 'warning')
        return redirect(url_for('mobile.mobile_course_detail', course_id=course.id))
    
    if not current_user.check_hourly_limit():
        flash('您已达到每小时访问次数限制，请稍后再试', 'warning')
        return redirect(url_for('mobile.mobile_course_detail', course_id=course.id))
    
    from app.services.security import get_config
    license_url = get_config('license_url', '')
    chapters = Chapter.query.filter_by(course_id=course.id).order_by(Chapter.sort_order).all()
    
    # 获取视频分辨率信息
    video_width = None
    video_height = None
    if chapter.file_id:
        from app.models import VideoFile
        video_file = VideoFile.query.filter_by(file_id=chapter.file_id).first()
        if video_file and video_file.width and video_file.height:
            video_width = video_file.width
            video_height = video_file.height
    
    # 记录播放日志
    from datetime import datetime
    play_log = PlayLog(
        user_id=current_user.id,
        chapter_id=chapter_id,
        course_id=course.id,
        play_time=datetime.utcnow()
    )
    db.session.add(play_log)
    db.session.commit()
    
    # 获取已完成的章节
    completed_logs = PlayLog.query.filter_by(
        user_id=current_user.id,
        course_id=course.id
    ).filter(PlayLog.progress >= 95).all()
    completed_chapter_ids = [log.chapter_id for log in completed_logs]
    
    return render_template('mobile/play-mobile.html',
                          chapter=chapter,
                          course=course,
                          all_chapters=chapters,
                          completed_chapters=completed_chapter_ids,
                          license_url=license_url,
                          video_width=video_width,
                          video_height=video_height)


@mobile_bp.route('/history')
@login_required
def mobile_history():
    """移动端播放历史"""
    if current_user.is_admin:
        return redirect(url_for('mobile.mobile_admin_dashboard'))
    
    play_logs = PlayLog.query.filter_by(user_id=current_user.id)\
        .order_by(PlayLog.play_time.desc()).limit(10).all()
    
    return render_template('mobile/history-mobile.html', play_logs=play_logs)


@mobile_bp.route('/my-courses')
@login_required
def mobile_my_courses():
    """移动端我的课程"""
    if current_user.is_admin:
        return redirect(url_for('mobile.mobile_admin_dashboard'))
    
    # 构建模板期望的数据结构
    allowed_courses = current_user.get_allowed_courses()
    courses_with_progress = []
    for course in allowed_courses:
        # 计算课程进度
        chapters = Chapter.query.filter_by(course_id=course.id).all()
        total_chapters = len(chapters)
        if total_chapters > 0:
            chapter_ids = [c.id for c in chapters]
            total_progress = db.session.query(db.func.sum(PlayLog.progress))\
                .filter(PlayLog.user_id == current_user.id, PlayLog.chapter_id.in_(chapter_ids))\
                .scalar() or 0
            # 简化计算：平均进度
            avg_progress = min(100, total_progress / total_chapters) if total_progress else 0
        else:
            avg_progress = 0
        
        courses_with_progress.append({
            'course': course,
            'progress': type('Progress', (), {'percentage': avg_progress})()
        })
    
    return render_template('mobile/my_courses-mobile.html', courses=courses_with_progress)


@mobile_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def mobile_change_password():
    """移动端修改密码"""
    if request.method == 'POST':
        current_password = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        if not current_user.check_password(current_password):
            flash('当前密码错误', 'danger')
            return render_template('mobile/change_password-mobile.html')
        
        if len(new_password) < 6:
            flash('新密码长度至少为6位', 'danger')
            return render_template('mobile/change_password-mobile.html')
        
        if new_password != confirm_password:
            flash('两次输入的新密码不一致', 'danger')
            return render_template('mobile/change_password-mobile.html')
        
        current_user.set_password(new_password)
        current_user.is_first_login = False
        db.session.commit()
        
        flash('密码修改成功', 'success')
        if current_user.is_admin:
            return redirect(url_for('mobile.mobile_admin_dashboard'))
        return redirect(url_for('mobile.mobile_dashboard'))
    
    return render_template('mobile/change_password-mobile.html')


# ========== 移动端管理端路由 ==========

@mobile_bp.route('/admin/login', methods=['GET', 'POST'])
def mobile_admin_login():
    """移动端管理员登录"""
    if current_user.is_authenticated:
        if current_user.is_admin:
            return redirect(url_for('mobile.mobile_admin_dashboard'))
        return redirect(url_for('mobile.mobile_dashboard'))
    
    if request.method == 'POST':
        phone = request.form.get('phone', '').strip() or request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        if not phone or not password:
            flash('手机号和密码不能为空', 'danger')
            return render_template('mobile/admin-login-mobile.html')
        
        if not phone.isdigit() or len(phone) < 11:
            flash('手机号格式不正确', 'danger')
            return render_template('mobile/admin-login-mobile.html')
        
        client_ip = get_client_ip()
        if check_ip_locked(client_ip):
            flash('您的IP已被锁定，请联系管理员', 'danger')
            return render_template('mobile/admin-login-mobile.html')
        
        user = User.query.filter_by(phone=phone).first()
        
        if not user:
            record_ip_fail(client_ip)
            flash('手机号或密码错误', 'danger')
            return render_template('mobile/admin-login-mobile.html')
        
        if not user.is_admin:
            flash('您没有管理员权限', 'danger')
            return render_template('mobile/admin-login-mobile.html')
        
        if user.is_locked:
            flash('您的账号已被锁定', 'danger')
            return render_template('mobile/admin-login-mobile.html')
        
        if not user.check_password(password):
            user.login_fail_count += 1
            from app.services.security import get_config
            max_fail = int(get_config('login_fail_limit', '10'))
            
            if user.login_fail_count >= max_fail:
                user.is_locked = True
                db.session.commit()
                flash('登录失败次数过多，账号已被锁定', 'danger')
            else:
                remaining = max_fail - user.login_fail_count
                db.session.commit()
                flash(f'手机号或密码错误，还剩{remaining}次机会', 'danger')
            
            record_ip_fail(client_ip)
            return render_template('mobile/admin-login-mobile.html')
        
        # 登录成功
        user.login_fail_count = 0
        db.session.commit()
        reset_ip_fail(client_ip)
        
        login_user(user, remember=False)
        session.permanent = True
        
        import time
        session['_last_activity'] = time.time()
        log_login(user.id, phone, True)
        
        session['_login_ip'] = client_ip
        session['_login_time'] = time.time()
        session['_client_type'] = get_client_type()
        session['_is_admin'] = True
        
        if user.is_first_login:
            flash('首次登录，请修改密码', 'warning')
            return redirect(url_for('mobile.mobile_change_password'))
        
        return redirect(url_for('mobile.mobile_admin_dashboard'))
    
    return render_template('mobile/admin-login-mobile.html')


@mobile_bp.route('/admin/dashboard')
@login_required
def mobile_admin_dashboard():
    """移动端管理员仪表盘"""
    if not current_user.is_admin:
        flash('您没有管理员权限', 'danger')
        return redirect(url_for('mobile.mobile_login'))
    
    from app.models import LockedIP, LoginLog
    stats = {
        'user_count': User.query.filter_by(is_admin=False).count(),
        'course_count': Course.query.count(),
        'chapter_count': Chapter.query.count(),
        'locked_user_count': User.query.filter_by(is_locked=True).count(),
        'locked_ip_count': LockedIP.query.filter_by(is_locked=True).count(),
        'today_login_count': LoginLog.query.filter(
            db.func.date(LoginLog.login_time) == db.func.date(db.func.now())
        ).count()
    }
    
    recent_logs = LoginLog.query.order_by(LoginLog.login_time.desc()).limit(10).all()
    
    return render_template('mobile/admin-dashboard-mobile.html', stats=stats, recent_logs=recent_logs)


@mobile_bp.route('/admin/users')
@login_required
def mobile_admin_users():
    """移动端用户管理"""
    if not current_user.is_admin:
        flash('您没有管理员权限', 'danger')
        return redirect(url_for('mobile.mobile_login'))
    
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    query = User.query.filter_by(is_admin=False)
    
    search = request.args.get('search', '')
    if search:
        query = query.filter(User.phone.contains(search))
    
    status = request.args.get('status', '')
    if status == 'locked':
        query = query.filter_by(is_locked=True)
    elif status == 'active':
        query = query.filter_by(is_locked=False)
    
    pagination = query.order_by(User.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    users = pagination.items
    courses = Course.query.all()
    
    return render_template('mobile/admin-users-mobile.html', 
                          users=users, 
                          pagination=pagination,
                          courses=courses, 
                          search=search, 
                          status=status)


@mobile_bp.route('/admin/courses')
@login_required
def mobile_admin_courses():
    """移动端课程管理"""
    if not current_user.is_admin:
        flash('您没有管理员权限', 'danger')
        return redirect(url_for('mobile.mobile_login'))
    
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    query = Course.query
    
    search = request.args.get('search', '')
    if search:
        query = query.filter(Course.title.contains(search))
    
    pagination = query.order_by(Course.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    courses = pagination.items
    
    return render_template('mobile/admin-courses-mobile.html', 
                          courses=courses, 
                          pagination=pagination, 
                          search=search)


@mobile_bp.route('/admin/videos')
@login_required
def mobile_admin_videos():
    """移动端视频管理"""
    if not current_user.is_admin:
        flash('您没有管理员权限', 'danger')
        return redirect(url_for('mobile.mobile_login'))
    
    from app.models import VideoFile
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    query = VideoFile.query
    
    search = request.args.get('search', '')
    if search:
        query = query.filter(VideoFile.name.contains(search))
    
    pagination = query.order_by(VideoFile.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    videos = pagination.items
    
    return render_template('mobile/admin-videos-mobile.html', 
                          videos=videos, 
                          pagination=pagination, 
                          search=search)


@mobile_bp.route('/admin/logs')
@login_required
def mobile_admin_logs():
    """移动端日志管理"""
    if not current_user.is_admin:
        flash('您没有管理员权限', 'danger')
        return redirect(url_for('mobile.mobile_login'))
    
    from app.models import LoginLog
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    query = LoginLog.query
    
    log_type = request.args.get('type', '')
    if log_type:
        query = query.filter(LoginLog.action == log_type)
    
    pagination = query.order_by(LoginLog.login_time.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    logs = pagination.items
    
    return render_template('mobile/admin-logs-mobile.html', 
                          logs=logs, 
                          pagination=pagination, 
                          log_type=log_type)


@mobile_bp.route('/admin/events')
@login_required
def mobile_admin_events():
    """移动端事件管理"""
    if not current_user.is_admin:
        flash('您没有管理员权限', 'danger')
        return redirect(url_for('mobile.mobile_login'))
    
    from app.models import VodEvent
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    query = VodEvent.query
    
    status = request.args.get('status', '')
    if status == 'consumed':
        query = query.filter_by(is_consumed=True)
    elif status == 'pending':
        query = query.filter_by(is_consumed=False)
    
    pagination = query.order_by(VodEvent.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    events = pagination.items
    
    return render_template('mobile/admin-events-mobile.html',
                          events=events,
                          pagination=pagination,
                          status=status)


@mobile_bp.route('/admin/config')
@login_required
def mobile_admin_config():
    """移动端系统配置"""
    if not current_user.is_admin:
        flash('您没有管理员权限', 'danger')
        return redirect(url_for('mobile.mobile_login'))
    
    from app.services.security import get_config
    configs = {
        'app_id': get_config('app_id', ''),
        'license_url': get_config('license_url', ''),
        'hourly_access_limit': get_config('hourly_access_limit', '10'),
        'login_fail_limit': get_config('login_fail_limit', '10'),
        'ip_fail_limit': get_config('ip_fail_limit', '10'),
        'psign_expire_seconds': get_config('psign_expire_seconds', '3600'),
    }
    
    return render_template('mobile/admin-config-mobile.html', configs=configs)
