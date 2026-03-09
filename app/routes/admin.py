# -*- coding: utf-8 -*-
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_required, current_user
from app.models import User, Course, Chapter, UserCoursePermission, LockedIP, LoginLog, PlayLog, VideoFile, VodEvent, VideoFolder
from app.services.security import get_config, set_config, unlock_ip, init_default_configs
from app.services.tencent_vod import TencentVODService
from app.services.logger import info as log_info, error as log_error, warning as log_warning, debug as log_debug, exception as log_exception
from app import db
import bleach
import os
import json
import imghdr  # 安全：用于验证图片文件类型
from werkzeug.utils import secure_filename
from flask import current_app

admin_bp = Blueprint('admin', __name__)

# ========== 安全：文件上传验证函数 ==========

def allowed_file(filename, allowed_extensions=None):
    """检查文件扩展名是否允许"""
    if allowed_extensions is None:
        allowed_extensions = current_app.config.get('ALLOWED_EXTENSIONS', {'mp4', 'mov', 'avi'})
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in allowed_extensions


def allowed_image_file(filename):
    """检查是否为允许的图片文件"""
    allowed_extensions = current_app.config.get('ALLOWED_IMAGE_EXTENSIONS', {'png', 'jpg', 'jpeg', 'gif', 'webp'})
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in allowed_extensions


def validate_image_file(file_storage):
    """安全：验证上传的文件确实是图片文件（防止伪装攻击）"""
    try:
        # 读取文件头进行验证
        header = file_storage.read(512)
        file_storage.seek(0)  # 重置文件指针
        
        # 使用 imghdr 验证图片类型
        image_type = imghdr.what(None, header)
        
        # 只允许常见的图片类型
        allowed_types = ['png', 'jpeg', 'gif', 'webp']
        return image_type in allowed_types
    except Exception:
        return False


def validate_video_file(file_storage):
    """安全：验证上传的文件是否是合法的视频文件"""
    try:
        # 读取文件头进行验证（常见视频格式魔数）
        header = file_storage.read(32)
        file_storage.seek(0)  # 重置文件指针
        
        # 常见视频格式的魔数
        video_signatures = {
            b'\x00\x00\x00\x18ftypmp41': 'mp4',
            b'\x00\x00\x00\x20ftypmp41': 'mp4',
            b'\x00\x00\x00 ftypisom': 'mp4',
            b'RIFF': 'avi',  # AVI 格式以 RIFF 开头
            b'\x1aE\xdf\xa3': 'mkv',  # Matroska
            b'FLV': 'flv',
            b'\x00\x00\x01\xba': 'mpeg',  # MPEG
        }
        
        # 检查文件头
        for signature, file_type in video_signatures.items():
            if header.startswith(signature):
                return True
        
        # 对于其他类型，至少检查文件大小不为零
        if len(header) == 0:
            return False
            
        # 如果无法确定类型，返回 True（依赖扩展名检查）
        return True
    except Exception:
        return False


# 管理员权限检查
def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 检查用户是否已登录
        if not current_user.is_authenticated:
            # AJAX 请求返回 JSON 错误
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'error': '未登录'}), 401
            flash('请先登录', 'warning')
            return redirect(url_for('auth.admin_login'))
        
        # 检查用户是否是管理员
        if not current_user.is_admin:
            # AJAX 请求返回 JSON 错误
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'error': '无权限'}), 403
            flash('您没有权限访问此页面', 'danger')
            return redirect(url_for('auth.admin_login'))

        # 执行原函数
        response = f(*args, **kwargs)

        # 添加缓存控制头，防止浏览器缓存需要登录的页面
        if hasattr(response, 'headers'):
            response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0, private'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
            # 添加 Vary 头以确保浏览器根据 Cookie 状态缓存
            response.headers['Vary'] = 'Cookie, Authorization'

        return response
    return decorated_function

@admin_bp.route('/')
@admin_required
@login_required
def dashboard():
    """管理员仪表盘"""
    # 统计数据
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

    # 最近的登录日志
    recent_logs = LoginLog.query.order_by(LoginLog.login_time.desc()).limit(10).all()

    return render_template('admin/dashboard.html', stats=stats, recent_logs=recent_logs)

# ==================== 用户管理 ====================

@admin_bp.route('/users')
@admin_required
@login_required
def users():
    """用户管理"""
    page = request.args.get('page', 1, type=int)
    per_page = 20

    query = User.query.filter_by(is_admin=False)

    # 搜索
    search = request.args.get('search', '')
    if search:
        query = query.filter(User.phone.contains(search))

    # 状态筛选
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

    return render_template('admin/users.html', users=users, pagination=pagination,
                          courses=courses, search=search, status=status)

@admin_bp.route('/users/add', methods=['POST'])
@admin_required
@login_required
def add_user():
    """添加用户"""
    phone = request.form.get('phone', '').strip()
    remark = request.form.get('remark', '').strip()
    course_ids = request.form.getlist('course_ids')

    if not phone:
        flash('手机号不能为空', 'danger')
        return redirect(url_for('admin.users'))

    # 检查手机号是否已存在
    if User.query.filter_by(phone=phone).first():
        flash('该手机号已存在', 'danger')
        return redirect(url_for('admin.users'))

    # 创建用户，密码默认为手机号后6位
    password = phone[-6:] if len(phone) >= 6 else phone

    user = User(
        phone=phone,
        remark=remark,
        is_first_login=True,
        is_locked=False
    )
    user.set_password(password)

    db.session.add(user)
    db.session.flush()  # 获取user.id

    # 添加课程权限
    for course_id in course_ids:
        permission = UserCoursePermission(user_id=user.id, course_id=int(course_id))
        db.session.add(permission)

    db.session.commit()

    flash(f'用户添加成功，初始密码为：{password}', 'success')
    return redirect(url_for('admin.users'))

@admin_bp.route('/users/<int:user_id>/edit', methods=['POST'])
@admin_required
@login_required
def edit_user(user_id):
    """编辑用户"""
    user = User.query.get_or_404(user_id)

    user.remark = request.form.get('remark', '').strip()

    # 更新课程权限
    course_ids = request.form.getlist('course_ids')

    # 删除旧权限
    UserCoursePermission.query.filter_by(user_id=user.id).delete()

    # 添加新权限
    for course_id in course_ids:
        permission = UserCoursePermission(user_id=user.id, course_id=int(course_id))
        db.session.add(permission)

    db.session.commit()
    flash('用户信息更新成功', 'success')
    return redirect(url_for('admin.users'))

@admin_bp.route('/users/<int:user_id>/reset-password', methods=['POST'])
@admin_required
@login_required
def reset_user_password(user_id):
    """重置用户密码"""
    user = User.query.get_or_404(user_id)

    # 密码重置为手机号后6位
    new_password = user.phone[-6:] if len(user.phone) >= 6 else user.phone
    user.set_password(new_password)
    user.is_first_login = True

    db.session.commit()

    return jsonify({
        'success': True,
        'message': f'密码已重置为：{new_password}'
    })

@admin_bp.route('/users/<int:user_id>/toggle-lock', methods=['POST'])
@admin_required
@login_required
def toggle_user_lock(user_id):
    """切换用户锁定状态"""
    user = User.query.get_or_404(user_id)

    user.is_locked = not user.is_locked
    if not user.is_locked:
        user.login_fail_count = 0

    db.session.commit()

    status = '锁定' if user.is_locked else '解锁'
    return jsonify({
        'success': True,
        'message': f'用户已{status}'
    })

@admin_bp.route('/users/<int:user_id>/delete', methods=['POST'])
@admin_required
@login_required
def delete_user(user_id):
    """删除用户"""
    user = User.query.get_or_404(user_id)

    db.session.delete(user)
    db.session.commit()

    flash('用户已删除', 'success')
    return redirect(url_for('admin.users'))

# ==================== 课程管理 ====================

@admin_bp.route('/courses')
@admin_required
@login_required
def courses():
    """课程管理"""
    page = request.args.get('page', 1, type=int)
    per_page = 20

    query = Course.query

    # 搜索
    search = request.args.get('search', '')
    if search:
        query = query.filter(Course.title.contains(search))

    pagination = query.order_by(Course.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    courses = pagination.items

    return render_template('admin/courses.html', courses=courses, pagination=pagination, search=search)

@admin_bp.route('/courses/add', methods=['POST'])
@admin_required
@login_required
def add_course():
    """添加课程"""
    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()

    if not title:
        flash('课程标题不能为空', 'danger')
        return redirect(url_for('admin.courses'))

    course = Course(
        title=title,
        description=description
    )

    db.session.add(course)
    db.session.commit()

    flash('课程添加成功', 'success')
    return redirect(url_for('admin.courses'))

@admin_bp.route('/courses/<int:course_id>/detail')
@admin_required
@login_required
def course_detail(course_id):
    """课程详情页面"""
    course = Course.query.get_or_404(course_id)
    return render_template('admin/course_detail.html', course=course)


@admin_bp.route('/courses/<int:course_id>/edit', methods=['POST'])
@admin_required
@login_required
def edit_course(course_id):
    """编辑课程"""
    course = Course.query.get_or_404(course_id)

    course.title = request.form.get('title', '').strip()
    course.description = request.form.get('description', '').strip()

    # 富文本内容需要清理
    detail_content = request.form.get('detail_content', '')
    allowed_tags = ['p', 'br', 'strong', 'em', 'u', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
                    'ul', 'ol', 'li', 'a', 'img', 'div', 'span']
    allowed_attrs = {
        '*': ['class', 'style'],
        'a': ['href', 'title'],
        'img': ['src', 'alt', 'width', 'height']
    }
    course.detail_content = bleach.clean(detail_content, tags=allowed_tags, attributes=allowed_attrs)

    # 处理缩略图上传
    if 'thumbnail' in request.files:
        file = request.files['thumbnail']
        if file.filename:
            # 安全：验证文件扩展名
            if not allowed_image_file(file.filename):
                flash('只允许上传图片文件（png, jpg, jpeg, gif, webp）', 'danger')
                return redirect(url_for('admin.course_detail', course_id=course_id))
            
            # 安全：验证文件内容确实是图片
            if not validate_image_file(file):
                flash('文件内容不是有效的图片', 'danger')
                return redirect(url_for('admin.course_detail', course_id=course_id))
            
            # 安全：生成安全的文件名
            filename = secure_filename(file.filename)
            # 添加随机前缀防止文件名冲突
            import uuid
            filename = f"{uuid.uuid4().hex}_{filename}"
            
            upload_dir = os.path.join('app', 'static', 'uploads', 'courses')
            os.makedirs(upload_dir, exist_ok=True)

            file_path = os.path.join(upload_dir, f'{course_id}_{filename}')
            file.save(file_path)

            course.thumbnail_url = f'/static/uploads/courses/{course_id}_{filename}'

    db.session.commit()
    flash('课程更新成功', 'success')

    # 检查是否从详情页面提交
    referer = request.headers.get('Referer', '')
    if '/detail' in referer:
        return redirect(url_for('admin.course_detail', course_id=course_id))
    return redirect(url_for('admin.chapters', course_id=course_id))

@admin_bp.route('/courses/<int:course_id>/delete', methods=['POST'])
@admin_required
@login_required
def delete_course(course_id):
    """删除课程"""
    course = Course.query.get_or_404(course_id)

    try:
        db.session.delete(course)
        db.session.commit()

        # 检查是否是AJAX请求
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': True, 'message': '课程已删除'})

        flash('课程已删除', 'success')
        return redirect(url_for('admin.courses'))
    except Exception as e:
        db.session.rollback()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'error': str(e)})
        flash(f'删除失败: {str(e)}', 'danger')
        return redirect(url_for('admin.courses'))

# ==================== 章节管理 ====================

@admin_bp.route('/courses/<int:course_id>/chapters')
@admin_required
@login_required
def chapters(course_id):
    """章节管理"""
    course = Course.query.get_or_404(course_id)
    chapters = Chapter.query.filter_by(course_id=course_id).order_by(Chapter.sort_order).all()

    return render_template('admin/chapters.html', course=course, chapters=chapters)

@admin_bp.route('/courses/<int:course_id>/chapters/add', methods=['POST'])
@admin_required
@login_required
def add_chapter(course_id):
    """添加章节"""
    course = Course.query.get_or_404(course_id)

    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()

    if not title:
        flash('章节标题不能为空', 'danger')
        return redirect(url_for('admin.chapters', course_id=course_id))

    # 自动计算排序值（当前最大排序+1）
    max_sort = db.session.query(db.func.max(Chapter.sort_order)).filter_by(course_id=course_id).scalar()
    sort_order = (max_sort or 0) + 1

    chapter = Chapter(
        course_id=course_id,
        title=title,
        description=description,
        sort_order=sort_order
    )

    db.session.add(chapter)
    db.session.commit()

    flash('章节添加成功', 'success')
    return redirect(url_for('admin.chapters', course_id=course_id))

@admin_bp.route('/chapters/<int:chapter_id>/edit', methods=['POST'])
@admin_required
@login_required
def edit_chapter(chapter_id):
    """编辑章节"""
    chapter = Chapter.query.get_or_404(chapter_id)

    chapter.title = request.form.get('title', '').strip()
    chapter.description = request.form.get('description', '').strip()
    chapter.file_id = request.form.get('file_id', '').strip()

    # 处理缩略图上传
    if 'thumbnail' in request.files:
        file = request.files['thumbnail']
        if file.filename:
            # 安全：验证文件扩展名
            if not allowed_image_file(file.filename):
                flash('只允许上传图片文件（png, jpg, jpeg, gif, webp）', 'danger')
                return redirect(url_for('admin.chapters', course_id=chapter.course_id))
            
            # 安全：验证文件内容确实是图片
            if not validate_image_file(file):
                flash('文件内容不是有效的图片', 'danger')
                return redirect(url_for('admin.chapters', course_id=chapter.course_id))
            
            # 安全：生成安全的文件名
            filename = secure_filename(file.filename)
            import uuid
            filename = f"{uuid.uuid4().hex}_{filename}"
            
            upload_dir = os.path.join('app', 'static', 'uploads', 'chapters')
            os.makedirs(upload_dir, exist_ok=True)

            file_path = os.path.join(upload_dir, f'{chapter_id}_{filename}')
            file.save(file_path)

            chapter.thumbnail_url = f'/static/uploads/chapters/{chapter_id}_{filename}'

    db.session.commit()
    flash('章节更新成功', 'success')
    return redirect(url_for('admin.chapters', course_id=chapter.course_id))


@admin_bp.route('/chapters/<int:chapter_id>/move', methods=['POST'])
@admin_required
@login_required
def move_chapter(chapter_id):
    """移动章节排序（上移/下移）"""
    import json
    chapter = Chapter.query.get_or_404(chapter_id)
    course_id = chapter.course_id

    data = request.get_json()
    direction = data.get('direction', '')

    if direction not in ['up', 'down']:
        return jsonify({'success': False, 'error': '无效的移动方向'})

    # 获取当前课程的所有章节，按sort_order排序
    chapters = Chapter.query.filter_by(course_id=course_id).order_by(Chapter.sort_order).all()

    # 找到当前章节的索引
    current_index = None
    for i, ch in enumerate(chapters):
        if ch.id == chapter_id:
            current_index = i
            break

    if current_index is None:
        return jsonify({'success': False, 'error': '章节不存在'})

    # 计算目标索引
    if direction == 'up' and current_index > 0:
        target_index = current_index - 1
    elif direction == 'down' and current_index < len(chapters) - 1:
        target_index = current_index + 1
    else:
        return jsonify({'success': False, 'error': '无法移动'})

    # 交换sort_order
    target_chapter = chapters[target_index]
    chapter.sort_order, target_chapter.sort_order = target_chapter.sort_order, chapter.sort_order

    db.session.commit()

    return jsonify({'success': True, 'message': '移动成功'})


@admin_bp.route('/chapters/<int:chapter_id>/delete', methods=['POST'])
@admin_required
@login_required
def delete_chapter(chapter_id):
    """删除章节"""
    chapter = Chapter.query.get_or_404(chapter_id)
    course_id = chapter.course_id
    file_id = chapter.file_id
    delete_video = request.form.get('delete_video') == 'true'

    # 如果要求删除视频文件
    if delete_video and file_id:
        vod_service = TencentVODService()
        result = vod_service.delete_media(file_id)
        if not result['success']:
            flash(f'章节已删除，但视频文件删除失败：{result.get("error", "未知错误")}', 'warning')
        else:
            flash('章节和视频文件已删除', 'success')
    else:
        flash('章节已删除', 'success')

    db.session.delete(chapter)
    db.session.commit()

    return redirect(url_for('admin.chapters', course_id=course_id))

@admin_bp.route('/chapters/<int:chapter_id>/upload-video', methods=['POST'])
@admin_required
@login_required
def upload_chapter_video(chapter_id):
    """上传章节视频
    保持原始文件名，上传到课程名称对应的文件夹下
    """
    chapter = Chapter.query.get_or_404(chapter_id)
    course = chapter.course

    if 'video' not in request.files:
        return jsonify({'success': False, 'error': '没有上传文件'})

    file = request.files['video']
    if file.filename == '':
        return jsonify({'success': False, 'error': '没有选择文件'})
    
    # 安全：验证文件扩展名
    if not allowed_file(file.filename):
        return jsonify({
            'success': False, 
            'error': '不支持的文件类型。只允许上传: ' + ', '.join(current_app.config.get('ALLOWED_EXTENSIONS', {'mp4', 'mov'}))
        })
    
    # 安全：验证文件大小
    file.seek(0, 2)  # 移动到文件末尾
    file_size = file.tell()
    file.seek(0)  # 重置文件指针
    
    max_size_mb = int(get_config('max_file_size', '100'))
    max_size = max_size_mb * 1024 * 1024
    if file_size > max_size:
        return jsonify({
            'success': False, 
            'error': f'文件大小超过限制（最大 {max_size_mb}MB）'
        })

    # 保持原始文件名（记录日志用途，实际存储使用安全文件名）
    original_filename = file.filename

    # 保存临时文件 - 使用安全文件名
    filename = secure_filename(file.filename)
    # 添加时间戳防止文件名冲突
    import time
    filename = f"{int(time.time())}_{filename}"
    
    temp_dir = os.path.join('app', 'static', 'uploads', 'temp')
    os.makedirs(temp_dir, exist_ok=True)

    temp_path = os.path.join(temp_dir, filename)
    file.save(temp_path)

    # 上传到腾讯云VOD
    vod_service = TencentVODService()
    result = vod_service.upload_media(temp_path, original_filename)

    # 删除临时文件
    try:
        os.remove(temp_path)
    except OSError:
        pass

    if result['success']:
        file_id = result['file_id']
        chapter.file_id = file_id
        if result.get('cover_url'):
            chapter.thumbnail_url = result['cover_url']

        # 触发任务流处理（转码、封面截图）
        procedure = get_config('vod_procedure_name', 'HLS_S1')
        procedure_result = vod_service.process_media_by_procedure(
            file_id=file_id,
            procedure_name=procedure
        )

        if procedure_result.get('success'):
            log_info(f"[ChapterUpload] 任务流已触发: file_id={file_id}, task_id={procedure_result.get('task_id')}")
            chapter.transcode_status = 'processing'
        else:
            log_warning(f"[ChapterUpload] 任务流触发失败: file_id={file_id}, error={procedure_result.get('error')}")
            chapter.transcode_status = 'pending'

        db.session.commit()

        # 获取或创建课程名称对应的文件夹
        folder = VideoFolder.query.filter_by(name=course.title).first()
        if not folder:
            folder = VideoFolder(name=course.title, parent_id=None)
            db.session.add(folder)
            db.session.flush()
            log_info(f"[ChapterUpload] 创建新课程文件夹: {course.title}, folder_id={folder.id}")

        # 根据任务流触发结果设置初始状态
        if procedure_result.get('success'):
            initial_status = 'processing'
            initial_message = '转码中'
        else:
            initial_status = 'uploaded'
            initial_message = '上传完成，等待转码'

        # 获取视频元数据信息
        media_info_result = vod_service.describe_media_infos(file_id)
        size = None
        duration = None
        width = None
        height = None
        bitrate = None

        if media_info_result['success'] and media_info_result['media_info_set']:
            media_info = media_info_result['media_info_set'][0]
            meta_data = getattr(media_info, 'MetaData', None)
            if meta_data:
                size = getattr(meta_data, 'Size', None)
                duration = getattr(meta_data, 'Duration', None)
                width = getattr(meta_data, 'Width', None)
                height = getattr(meta_data, 'Height', None)
                bitrate = getattr(meta_data, 'Bitrate', None)

        # 创建VideoFile记录，关联到课程文件夹
        video_file = VideoFile(
            file_id=file_id,
            file_name=original_filename,  # 保持原始文件名
            title=original_filename,
            folder_id=folder.id,
            chapter_id=chapter.id,
            process_status=initial_status,
            process_message=initial_message,
            procedure_name=procedure,
            task_id=procedure_result.get('task_id', ''),
            size=size,
            duration=duration,
            width=width,
            height=height,
            bitrate=bitrate
        )
        db.session.add(video_file)
        db.session.commit()

        log_info(f"[ChapterUpload] 视频记录已创建: file_id={file_id}, folder={course.title}, original_name={original_filename}, size={size}")

        # 启动前端实时回调检查（与批量上传保持一致）
        try:
            from app.services.video_callback import VideoCallbackService
            callback_service = VideoCallbackService(current_app._get_current_object())
            
            # 启动转码检查（每10秒，超时600秒）
            if procedure_result.get('success'):
                callback_service.start_transcode_check(file_id, procedure_result.get('task_id'))
                log_info(f"[ChapterUpload] 启动实时转码检查: file_id={file_id}", 'task')
        except Exception as e:
            log_error(f"[ChapterUpload] 启动实时回调失败: file_id={file_id}, error={str(e)}", 'task')

        return jsonify({
            'success': True,
            'file_id': result['file_id'],
            'cover_url': result.get('cover_url')
        })
    else:
        return jsonify({'success': False, 'error': result['error']})

@admin_bp.route('/chapters/<int:chapter_id>/select-video', methods=['POST'])
@admin_required
@login_required
def select_chapter_video(chapter_id):
    """选择已上传的视频"""
    chapter = Chapter.query.get_or_404(chapter_id)
    file_id = request.form.get('file_id', '').strip()

    if not file_id:
        return jsonify({'success': False, 'error': '请选择视频'})

    # 验证视频是否存在
    vod_service = TencentVODService()
    result = vod_service.describe_media_infos(file_id)

    if not result['success']:
        return jsonify({'success': False, 'error': '视频不存在或无法访问'})

    # 获取视频信息
    media_info = result['media_info_set'][0] if result['media_info_set'] else None
    if media_info:
        # 获取缩略图
        cover_url = None
        if hasattr(media_info, 'CoverUrl'):
            cover_url = media_info.CoverUrl
        elif hasattr(media_info, 'BasicInfo') and hasattr(media_info.BasicInfo, 'CoverUrl'):
            cover_url = media_info.BasicInfo.CoverUrl

        chapter.file_id = file_id
        if cover_url:
            chapter.thumbnail_url = cover_url
        db.session.commit()

        return jsonify({
            'success': True,
            'file_id': file_id,
            'cover_url': cover_url
        })

    return jsonify({'success': False, 'error': '无法获取视频信息'})

# ==================== 视频文件管理 ====================

@admin_bp.route('/videos')
@admin_required
@login_required
def videos():
    """视频文件管理"""
    page = request.args.get('page', 1, type=int)
    per_page = 20

    # 获取所有已使用的file_id
    used_file_ids = db.session.query(Chapter.file_id).filter(Chapter.file_id.isnot(None)).all()
    used_file_ids = [f[0] for f in used_file_ids if f[0]]

    # 获取所有章节及其视频信息
    chapters_with_video = Chapter.query.filter(Chapter.file_id.isnot(None)).all()

    # 构建视频列表，从Chapter获取转码状态
    video_list = []
    for chapter in chapters_with_video:
        video_list.append({
            'file_id': chapter.file_id,
            'chapter_id': chapter.id,
            'chapter_title': chapter.title,
            'course_id': chapter.course_id,
            'course_title': chapter.course.title if chapter.course else '未知课程',
            'thumbnail_url': chapter.thumbnail_url,
            'transcode_status': chapter.transcode_status or 'pending',
            'transcode_message': chapter.transcode_message or '',
            'is_referenced': True,
            'reference_count': 1
        })

    return render_template('admin/videos.html', videos=video_list, used_file_ids=used_file_ids)

@admin_bp.route('/api/video-status/<file_id>')
@admin_required
@login_required
def api_video_status(file_id):
    """API: 获取视频转码状态
    参数:
        sync: 如果为1，则从腾讯云查询最新状态并更新数据库
    """
    try:
        sync = request.args.get('sync', '0') == '1'

        if sync:
            # 从腾讯云查询最新状态
            vod_service = TencentVODService()
            result = vod_service.get_transcode_status(file_id)

            # 更新数据库
            if result.get('success'):
                chapter = Chapter.query.filter_by(file_id=file_id).first()
                if chapter:
                    chapter.transcode_status = result.get('status', chapter.transcode_status)
                    if result.get('message'):
                        chapter.transcode_message = result['message']
                    db.session.commit()

                # 同时更新VideoFile表
                video_file = VideoFile.query.filter_by(file_id=file_id).first()
                if video_file:
                    video_file.transcode_status = result.get('status', video_file.transcode_status)
                    if result.get('message'):
                        video_file.transcode_message = result['message']
                    db.session.commit()

            return jsonify(result)
        else:
            # 从数据库读取状态
            chapter = Chapter.query.filter_by(file_id=file_id).first()
            if chapter and chapter.transcode_status:
                return jsonify({
                    'success': True,
                    'status': chapter.transcode_status,
                    'message': chapter.transcode_message or ''
                })

            # 如果没有章节记录，尝试从VideoFile读取
            video_file = VideoFile.query.filter_by(file_id=file_id).first()
            if video_file and video_file.transcode_status:
                return jsonify({
                    'success': True,
                    'status': video_file.transcode_status,
                    'message': video_file.transcode_message or ''
                })

            # 默认返回pending
            return jsonify({
                'success': True,
                'status': 'pending',
                'message': '等待转码'
            })

    except Exception as e:
        return jsonify({
            'success': False,
            'status': 'failed',
            'message': str(e)
        })


@admin_bp.route('/api/upload-signature')
@admin_required
@login_required
def api_upload_signature():
    """API: 获取腾讯云VOD上传签名
    用于客户端直传视频
    """
    try:
        # 获取配置
        procedure = get_config('vod_procedure_name', 'HLS_S1')

        vod_service = TencentVODService()
        signature = vod_service.get_upload_sign(
            procedure=procedure,
            expire_seconds=3600
        )

        return jsonify({
            'success': True,
            'signature': signature
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })


@admin_bp.route('/api/batch-upload-direct', methods=['POST'])
@admin_required
@login_required
def api_batch_upload_direct():
    """API: 直接上传视频文件（表单上传）
    用于批量上传功能
    """
    try:
        folder_id = request.form.get('folder_id', type=int)
        file_name = request.form.get('file_name', '')

        if not folder_id:
            return jsonify({
                'success': False,
                'error': '请先选择文件夹'
            })

        if 'video' not in request.files:
            return jsonify({
                'success': False,
                'error': '没有上传文件'
            })

        file = request.files['video']
        if file.filename == '':
            return jsonify({
                'success': False,
                'error': '文件名为空'
            })
        
        # 安全：验证文件扩展名
        if not allowed_file(file.filename):
            return jsonify({
                'success': False,
                'error': '不支持的文件类型。只允许上传: ' + ', '.join(current_app.config.get('ALLOWED_EXTENSIONS', {'mp4', 'mov'}))
            })
        
        # 安全：验证文件大小
        file.seek(0, 2)  # 移动到文件末尾
        file_size = file.tell()
        file.seek(0)  # 重置文件指针
        
        max_size_mb = int(get_config('max_file_size', '100'))
        max_size = max_size_mb * 1024 * 1024
        if file_size > max_size:
            return jsonify({
                'success': False,
                'error': f'文件大小超过限制（最大 {max_size_mb}MB）'
            })

        # 保存临时文件 - 使用安全文件名
        import tempfile
        import os
        import time
        
        # 生成安全文件名
        safe_filename = secure_filename(file_name or file.filename)
        safe_filename = f"{int(time.time())}_{safe_filename}"
        
        temp_dir = tempfile.gettempdir()
        temp_path = os.path.join(temp_dir, safe_filename)
        file.save(temp_path)

        try:
            # 上传到腾讯云VOD
            vod_service = TencentVODService()
            procedure = get_config('vod_procedure_name', 'HLS_S1')

            result = vod_service.upload_media(temp_path, file_name or file.filename)

            if result['success']:
                file_id = result['file_id']

                # 触发任务流处理（转码、封面截图）
                procedure_result = vod_service.process_media_by_procedure(
                    file_id=file_id,
                    procedure_name=procedure
                )

                if procedure_result.get('success'):
                    log_info(f"[BatchUpload] 任务流已触发: file_id={file_id}, task_id={procedure_result.get('task_id')}")
                else:
                    log_warning(f"[BatchUpload] 任务流触发失败: file_id={file_id}, error={procedure_result.get('error')}")

                # 获取视频元数据信息
                media_info_result = vod_service.describe_media_infos(file_id)
                size = None
                duration = None
                width = None
                height = None
                bitrate = None

                if media_info_result['success'] and media_info_result['media_info_set']:
                    media_info = media_info_result['media_info_set'][0]
                    meta_data = getattr(media_info, 'MetaData', None)
                    if meta_data:
                        size = getattr(meta_data, 'Size', None)
                        duration = getattr(meta_data, 'Duration', None)
                        width = getattr(meta_data, 'Width', None)
                        height = getattr(meta_data, 'Height', None)
                        bitrate = getattr(meta_data, 'Bitrate', None)

                # 创建VideoFile记录
                # 根据任务流触发结果设置初始状态
                if procedure_result.get('success'):
                    initial_status = 'processing'
                    initial_message = '转码中'
                else:
                    initial_status = 'uploaded'
                    initial_message = '上传完成，等待转码'

                video_file = VideoFile(
                    file_id=file_id,
                    file_name=file_name or file.filename,
                    title=file_name or file.filename,
                    folder_id=folder_id,
                    process_status=initial_status,
                    process_message=initial_message,
                    procedure_name=procedure,
                    task_id=procedure_result.get('task_id', ''),
                    size=size,
                    duration=duration,
                    width=width,
                    height=height,
                    bitrate=bitrate
                )
                db.session.add(video_file)
                db.session.commit()

                # ========== 启动前端实时回调检查 ==========
                try:
                    from app.services.video_callback import VideoCallbackService
                    callback_service = VideoCallbackService(current_app._get_current_object())
                    
                    # 启动转码检查（每10秒，超时600秒）
                    if procedure_result.get('success'):
                        callback_service.start_transcode_check(file_id, procedure_result.get('task_id'))
                        log_info(f"[BatchUpload] 启动实时转码检查: file_id={file_id}", 'task')
                except Exception as e:
                    log_error(f"[BatchUpload] 启动实时回调失败: file_id={file_id}, error={str(e)}", 'task')
                # ========== 实时回调启动完成 ==========

                return jsonify({
                    'success': True,
                    'video_id': video_file.id,
                    'file_id': file_id,
                    'message': '上传成功'
                })
            else:
                return jsonify({
                    'success': False,
                    'error': result.get('error', '上传失败')
                })
        finally:
            # 清理临时文件
            if os.path.exists(temp_path):
                os.remove(temp_path)

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        })


@admin_bp.route('/api/folders/tree')
@admin_required
@login_required
def api_folders_tree():
    """API: 获取文件夹树结构"""
    try:
        # 获取所有文件夹
        folders = VideoFolder.query.all()

        # 构建树结构
        folder_map = {}
        tree = []

        for folder in folders:
            folder_data = {
                'id': folder.id,
                'name': folder.name,
                'parent_id': folder.parent_id,
                'children': []
            }
            folder_map[folder.id] = folder_data

        # 构建父子关系
        for folder_id, folder_data in folder_map.items():
            if folder_data['parent_id'] and folder_data['parent_id'] in folder_map:
                folder_map[folder_data['parent_id']]['children'].append(folder_data)
            else:
                tree.append(folder_data)

        return jsonify({
            'success': True,
            'tree': tree
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })


@admin_bp.route('/api/folders', methods=['POST'])
@admin_required
@login_required
def api_create_folder():
    """API: 创建文件夹"""
    try:
        data = request.get_json()
        folder = VideoFolder(
            name=data.get('name', ''),
            parent_id=data.get('parent_id')
        )
        db.session.add(folder)
        db.session.commit()

        return jsonify({
            'success': True,
            'folder': {
                'id': folder.id,
                'name': folder.name,
                'parent_id': folder.parent_id
            }
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        })


@admin_bp.route('/api/folders/<int:folder_id>', methods=['DELETE'])
@admin_required
@login_required
def api_delete_folder(folder_id):
    """API: 删除文件夹"""
    try:
        folder = VideoFolder.query.get_or_404(folder_id)

        # 检查文件夹下是否有视频
        if folder.videos:
            return jsonify({
                'success': False,
                'error': '文件夹下还有视频文件，请先移动或删除'
            })

        db.session.delete(folder)
        db.session.commit()

        return jsonify({
            'success': True
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        })


@admin_bp.route('/videos/<file_id>/delete', methods=['POST'])
@admin_required
@login_required
def delete_video(file_id):
    """删除视频文件"""
    # 检查是否有章节引用此视频
    chapters = Chapter.query.filter_by(file_id=file_id).all()

    if chapters:
        chapter_info = ', '.join([f"{c.title}({c.course.title if c.course else '未知课程'})" for c in chapters])
        return jsonify({
            'success': False,
            'error': f'该视频被以下章节引用，请先删除章节：{chapter_info}'
        })

    # 调用腾讯云VOD删除视频
    vod_service = TencentVODService()
    result = vod_service.delete_media(file_id)

    if result['success']:
        return jsonify({'success': True, 'message': '视频已删除'})
    else:
        return jsonify({
            'success': False,
            'error': f'删除失败：{result.get("error", "未知错误")}'
        })


@admin_bp.route('/api/chapter/<int:chapter_id>/sync-status')
@admin_required
@login_required
def api_chapter_sync_status(chapter_id):
    """API: 获取章节视频状态
    查询腾讯云VOD获取最新状态并更新数据库
    """
    try:
        chapter = Chapter.query.get_or_404(chapter_id)

        if not chapter.file_id:
            return jsonify({
                'success': True,
                'status': 'none',
                'message': '未上传视频'
            })

        # 从腾讯云查询最新状态
        vod_service = TencentVODService()
        result = vod_service.get_transcode_status(chapter.file_id)

        if result.get('success'):
            # 更新章节状态
            chapter.transcode_status = result.get('status', chapter.transcode_status)
            if result.get('message'):
                chapter.transcode_message = result['message']

            # 如果有封面URL，直接使用云端URL
            cover_url = result.get('cover_url')
            if cover_url and not chapter.thumbnail_url:
                chapter.thumbnail_url = cover_url

            db.session.commit()

            return jsonify({
                'success': True,
                'status': chapter.transcode_status,
                'message': chapter.transcode_message or '',
                'cover_url': chapter.thumbnail_url
            })
        else:
            # 查询失败，返回数据库中的状态
            return jsonify({
                'success': True,
                'status': chapter.transcode_status or 'pending',
                'message': chapter.transcode_message or '查询云端状态失败'
            })

    except Exception as e:
        return jsonify({
            'success': False,
            'status': 'failed',
            'message': str(e)
        })


@admin_bp.route('/api/videos')
@admin_required
@login_required
def api_videos():
    """API: 获取视频列表（支持分页和筛选）"""
    try:
        page = request.args.get('page', 1, type=int)
        folder_id = request.args.get('folder_id', type=int)
        process_status = request.args.get('process_status', '')
        search = request.args.get('search', '')
        per_page_param = request.args.get('per_page', '20')
        
        # 处理每页数量参数
        if per_page_param == 'all':
            per_page = None  # 不分页
        else:
            per_page = int(per_page_param)

        query = VideoFile.query

        if folder_id:
            query = query.filter_by(folder_id=folder_id)
        if process_status:
            query = query.filter_by(process_status=process_status)
        if search:
            query = query.filter(VideoFile.file_name.contains(search))

        # 排序
        query = query.order_by(VideoFile.created_at.desc())
        
        if per_page is None:
            # 不分页，返回全部
            all_videos = query.all()
            videos = []
            for v in all_videos:
                videos.append({
                    'id': v.id,
                    'file_id': v.file_id,
                    'file_name': v.file_name or v.title,
                    'title': v.title,
                    'size': v.size,
                    'duration': v.duration,
                    'width': v.width,
                    'height': v.height,
                    'bitrate': v.bitrate,
                    'process_status': v.process_status,
                    'process_message': v.process_message,
                    'cover_url': v.cover_url,
                    'created_at': (v.created_at + __import__('datetime', fromlist=['timedelta']).timedelta(hours=8)).strftime('%Y-%m-%d %H:%M:%S') if v.created_at else None,
                    'folder_id': v.folder_id,
                    'chapter_id': v.chapter_id
                })
            
            return jsonify({
                'success': True,
                'videos': videos,
                'total': len(videos),
                'pages': 1,
                'current_page': 1
            })
        else:
            # 分页查询
            pagination = query.paginate(
                page=page, per_page=per_page, error_out=False
            )

            videos = []
            for v in pagination.items:
                videos.append({
                    'id': v.id,
                    'file_id': v.file_id,
                    'file_name': v.file_name or v.title,
                    'title': v.title,
                    'size': v.size,
                    'duration': v.duration,
                    'width': v.width,
                    'height': v.height,
                    'bitrate': v.bitrate,
                    'process_status': v.process_status,
                    'process_message': v.process_message,
                    'cover_url': v.cover_url,
                    'created_at': (v.created_at + __import__('datetime', fromlist=['timedelta']).timedelta(hours=8)).strftime('%Y-%m-%d %H:%M:%S') if v.created_at else None,
                    'folder_id': v.folder_id,
                    'chapter_id': v.chapter_id
                })

            return jsonify({
                'success': True,
                'videos': videos,
                'total': pagination.total,
                'pages': pagination.pages,
                'current_page': page
            })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })


@admin_bp.route('/api/videos/<int:video_id>')
@admin_required
@login_required
def api_video_detail(video_id):
    """API: 获取单个视频详情"""
    try:
        video = VideoFile.query.get_or_404(video_id)
        
        return jsonify({
            'success': True,
            'video': {
                'id': video.id,
                'file_id': video.file_id,
                'file_name': video.file_name or video.title,
                'title': video.title,
                'size': video.size,
                'duration': video.duration,
                'width': video.width,
                'height': video.height,
                'bitrate': video.bitrate,
                'process_status': video.process_status,
                'process_message': video.process_message,
                'cover_url': video.cover_url,
                'local_cover_path': video.local_cover_path,
                'play_url': video.play_url,
                'created_at': (video.created_at + __import__('datetime', fromlist=['timedelta']).timedelta(hours=8)).strftime('%Y-%m-%d %H:%M:%S') if video.created_at else None,
                'folder_id': video.folder_id,
                'chapter_id': video.chapter_id
            }
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })


@admin_bp.route('/api/videos/<int:video_id>/status')
@admin_required
@login_required
def api_video_detail_status(video_id):
    """API: 获取单个视频状态"""
    try:
        video = VideoFile.query.get_or_404(video_id)
        return jsonify({
            'success': True,
            'video': {
                'id': video.id,
                'file_id': video.file_id,
                'file_name': video.file_name or video.title,
                'title': video.title,
                'size': video.size,
                'process_status': video.process_status,
                'process_message': video.process_message,
                'cover_url': video.cover_url,
                'task_id': video.task_id,
                'created_at': (video.created_at + __import__('datetime', fromlist=['timedelta']).timedelta(hours=8)).strftime('%Y-%m-%d %H:%M:%S') if video.created_at else None
            }
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })


@admin_bp.route('/api/videos/<int:video_id>/delete', methods=['POST'])
@admin_required
@login_required
def api_delete_video(video_id):
    """API: 删除单个视频"""
    try:
        video = VideoFile.query.get_or_404(video_id)

        # 如果关联了章节，需要检查
        if video.chapter_id:
            chapter = Chapter.query.get(video.chapter_id)
            if chapter:
                return jsonify({
                    'success': False,
                    'error': f'该视频已关联到章节"{chapter.title}"，请先删除章节'
                })

        # 调用腾讯云VOD删除
        if video.file_id:
            vod_service = TencentVODService()
            vod_service.delete_media(video.file_id)

        # 标记为删除中，等待回调确认
        video.process_status = 'deleting'
        video.process_message = '删除中'
        db.session.commit()

        return jsonify({
            'success': True,
            'message': '视频已删除'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        })


@admin_bp.route('/api/videos/batch-delete', methods=['POST'])
@admin_required
@login_required
def api_batch_delete_videos():
    """API: 批量删除视频"""
    try:
        data = request.get_json()
        video_ids = data.get('video_ids', [])

        if not video_ids:
            return jsonify({
                'success': False,
                'error': '请选择要删除的视频'
            })

        vod_service = TencentVODService()
        deleted_count = 0
        failed_items = []

        for video_id in video_ids:
            video = VideoFile.query.get(video_id)
            if not video:
                continue

            # 检查是否关联章节
            if video.chapter_id:
                chapter = Chapter.query.get(video.chapter_id)
                if chapter:
                    failed_items.append(f'{video.file_name or video_id}(关联章节:{chapter.title})')
                    continue

            # 调用腾讯云删除
            if video.file_id:
                vod_service.delete_media(video.file_id)

            video.process_status = 'deleting'
            video.process_message = '删除中'
            deleted_count += 1

            # ========== 启动删除实时回调检查 ==========
            try:
                from app.services.video_callback import VideoCallbackService
                callback_service = VideoCallbackService(current_app._get_current_object())
                callback_service.start_delete_check(video.file_id)
                log_info(f"[BatchDelete] 启动实时删除检查: file_id={video.file_id}", 'task')
            except Exception as e:
                log_error(f"[BatchDelete] 启动删除回调失败: file_id={video.file_id}, error={str(e)}", 'task')
            # ========== 实时回调启动完成 ==========

        db.session.commit()

        return jsonify({
            'success': True,
            'message': f'已启动删除 {deleted_count} 个视频',
            'deleted_count': deleted_count,
            'failed_items': failed_items
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        })


@admin_bp.route('/api/videos/batch-delete-records', methods=['POST'])
@admin_required
@login_required
def api_batch_delete_records():
    """API: 批量删除视频记录（仅删除数据库记录，不删云端）"""
    try:
        data = request.get_json()
        video_ids = data.get('video_ids', [])

        if not video_ids:
            return jsonify({
                'success': False,
                'error': '请选择要删除的记录'
            })

        for video_id in video_ids:
            video = VideoFile.query.get(video_id)
            if video:
                db.session.delete(video)

        db.session.commit()

        return jsonify({
            'success': True,
            'message': f'成功删除 {len(video_ids)} 条记录'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        })


@admin_bp.route('/api/videos/<int:video_id>/download-cover', methods=['POST'])
@admin_required
@login_required
def api_download_cover(video_id):
    """API: 下载视频封面"""
    try:
        video = VideoFile.query.get_or_404(video_id)

        if not video.cover_url:
            return jsonify({
                'success': False,
                'error': '该视频没有封面URL'
            })

        # 调用下载封面函数
        from app.routes.callback import download_cover_image
        local_path = download_cover_image(video.cover_url, video.file_id)

        if local_path:
            video.local_cover_path = local_path
            db.session.commit()
            return jsonify({
                'success': True,
                'message': '封面下载成功',
                'local_path': local_path
            })
        else:
            return jsonify({
                'success': False,
                'error': '封面下载失败'
            })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })


@admin_bp.route('/api/videos/sync-by-fileid', methods=['POST'])
@admin_required
@login_required
def api_sync_by_fileid():
    """API: 根据FileId强制同步视频状态（用于调试）"""
    import json
    try:
        data = request.get_json()
        file_id = data.get('file_id')
        force_status = data.get('force_status')  # 可选，强制设置状态

        if not file_id:
            return jsonify({'success': False, 'error': '缺少file_id参数'}), 400

        log_info(f"[SyncByFileId] ========== 强制同步 FileId={file_id} ==========")

        # 查找视频
        video = VideoFile.query.filter_by(file_id=file_id).first()
        if not video:
            return jsonify({'success': False, 'error': f'未找到FileId={file_id}的视频'}), 404

        log_info(f"[SyncByFileId] 找到视频: ID={video.id}, 当前状态={video.process_status}")

        vod_service = TencentVODService()

        # 如果强制设置状态
        if force_status:
            old_status = video.process_status
            video.process_status = force_status
            video.process_message = f'手动强制设置为{force_status}'
            db.session.commit()
            log_info(f"[SyncByFileId] ✓ 强制更新: {old_status} -> {force_status}")
            return jsonify({
                'success': True,
                'message': f'已强制更新状态: {old_status} -> {force_status}',
                'video': {
                    'id': video.id,
                    'file_id': video.file_id,
                    'process_status': video.process_status,
                    'process_message': video.process_message
                }
            })

        # 否则查询云端状态
        result = vod_service.get_transcode_status(file_id)
        log_info(f"[SyncByFileId] 转码状态查询: {json.dumps(result, ensure_ascii=False, default=str)}")

        # 同时查询媒体信息
        media_result = vod_service.describe_media_infos(file_id)
        log_info(f"[SyncByFileId] 媒体信息查询: {json.dumps(media_result, ensure_ascii=False, default=str)}")

        # 检查删除状态
        search_result = vod_service.search_media(file_id)
        log_info(f"[SyncByFileId] 搜索媒体结果: {json.dumps(search_result, ensure_ascii=False, default=str)}")

        old_status = video.process_status

        # 根据结果更新状态
        if result.get('success') and result.get('status') == 'success':
            video.process_status = 'completed'
            video.process_message = '转码完成（手动同步）'
            if result.get('play_url'):
                video.play_url = result.get('play_url')
            if result.get('cover_url'):
                video.cover_url = result.get('cover_url')
        elif not search_result.get('exists'):
            # 云端不存在，标记为已删除
            video.process_status = 'deleted'
            video.process_message = '已删除（手动同步确认）'
        else:
            video.process_message = f'当前状态: {result.get("status", "unknown")}'

        db.session.commit()
        log_info(f"[SyncByFileId] ✓ 更新完成: {old_status} -> {video.process_status}")

        return jsonify({
            'success': True,
            'message': f'同步完成: {old_status} -> {video.process_status}',
            'transcode_result': result,
            'media_result': media_result,
            'search_result': search_result,
            'video': {
                'id': video.id,
                'file_id': video.file_id,
                'process_status': video.process_status,
                'process_message': video.process_message
            }
        })

    except Exception as e:
        db.session.rollback()
        log_error(f"[SyncByFileId] 同步异常: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/api/videos/<int:video_id>/sync-deletion', methods=['POST'])
@admin_required
@login_required
def api_sync_deletion_status(video_id):
    """API: 同步视频的删除状态（检查云端是否已删除）"""
    import json
    log_info(f"[SyncDeletion] ========== 同步删除状态 video_id={video_id} ==========")

    try:
        video = VideoFile.query.get_or_404(video_id)
        log_info(f"[SyncDeletion] 找到视频: ID={video.id}, FileId={video.file_id}, 当前状态={video.process_status}")

        if not video.file_id:
            log_info(f"[SyncDeletion] 视频无FileId，直接标记为已删除")
            video.process_status = 'deleted'
            video.process_message = '无FileId，标记为已删除'
            db.session.commit()
            return jsonify({
                'success': True,
                'status': 'deleted',
                'message': '无FileId，标记为已删除'
            })

        # 查询腾讯云VOD状态
        vod_service = TencentVODService()

        # 使用多种方式检查
        result = vod_service.describe_media_infos(video.file_id)
        log_info(f"[SyncDeletion] DescribeMediaInfos结果: {json.dumps(result, ensure_ascii=False, default=str)}")

        search_result = vod_service.search_media(video.file_id)
        log_info(f"[SyncDeletion] SearchMedia结果: {json.dumps(search_result, ensure_ascii=False, default=str)}")

        # 云端是否存在的判断逻辑
        cloud_exists = False

        # 如果DescribeMediaInfos返回成功，说明存在
        if result.get('success') and result.get('media_info_set'):
            cloud_exists = True
            log_info(f"[SyncDeletion] DescribeMediaInfos返回成功，云端存在")

        # 如果SearchMedia返回存在
        if search_result.get('exists'):
            cloud_exists = True
            log_info(f"[SyncDeletion] SearchMedia返回存在，云端存在")

        if cloud_exists:
            log_info(f"[SyncDeletion] 云端仍存在，保持当前状态: {video.process_status}")
            return jsonify({
                'success': True,
                'status': video.process_status,
                'cloud_exists': True,
                'message': '云端文件仍存在'
            })
        else:
            # 云端已删除，同步状态
            old_status = video.process_status
            if video.process_status != 'deleted':
                video.process_status = 'deleted'
                video.process_message = '已删除（云端确认）'
                db.session.commit()
                log_info(f"[SyncDeletion] ✓ 状态更新: {old_status} -> deleted")
            else:
                log_info(f"[SyncDeletion] - 已经是deleted状态，无需更新")

            return jsonify({
                'success': True,
                'status': 'deleted',
                'cloud_exists': False,
                'message': '云端文件已删除，状态已同步'
            })
    except Exception as e:
        db.session.rollback()
        log_error(f"[SyncDeletion] 同步异常: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        })


@admin_bp.route('/api/videos/sync-status', methods=['POST'])
@admin_required
@login_required
def api_sync_all_status():
    """API: 同步所有处理中视频的状态"""
    import json
    log_info("[SyncStatus] ========== 开始同步所有状态 ==========")

    try:
        # 获取所有处理中的视频（包括上传中、上传完成、转码中、删除中）
        processing_videos = VideoFile.query.filter(
            VideoFile.process_status.in_(['uploading', 'uploaded', 'processing', 'deleting'])
        ).all()

        log_info(f"[SyncStatus] 找到 {len(processing_videos)} 个处理中的视频")

        vod_service = TencentVODService()
        updated_count = 0
        details = []

        for video in processing_videos:
            if not video.file_id:
                log_warning(f"[SyncStatus] 视频ID={video.id} 没有file_id，跳过")
                continue

            log_info(f"[SyncStatus] 处理视频: ID={video.id}, FileId={video.file_id}, 当前状态={video.process_status}")

            # 查询最新状态
            result = vod_service.get_transcode_status(video.file_id)
            log_info(f"[SyncStatus] 查询转码状态结果: {json.dumps(result, ensure_ascii=False, default=str)}")

            if result.get('success'):
                transcode_status = result.get('status')
                old_status = video.process_status

                # 更新文件大小（如果有）
                if result.get('size') and (not video.size or video.size == 0):
                    video.size = result.get('size')
                    log_info(f"[SyncStatus] ✓ 视频ID={video.id} 更新文件大小: {video.size}")

                # 更新处理状态
                if transcode_status == 'success':
                    video.process_status = 'completed'
                    video.process_message = '转码完成'
                    # 更新播放地址
                    if result.get('play_url') and not video.play_url:
                        video.play_url = result.get('play_url')
                    # 更新封面地址
                    if result.get('cover_url') and not video.cover_url:
                        video.cover_url = result.get('cover_url')
                    updated_count += 1
                    log_info(f"[SyncStatus] ✓ 视频ID={video.id} 更新为 completed (转码完成)")
                    details.append({'id': video.id, 'file_id': video.file_id, 'from': old_status, 'to': 'completed'})

                elif transcode_status == 'failed':
                    video.process_status = 'completed'
                    video.process_message = result.get('message', '转码失败')
                    updated_count += 1
                    log_info(f"[SyncStatus] ✓ 视频ID={video.id} 更新为 completed (转码失败)")
                    details.append({'id': video.id, 'file_id': video.file_id, 'from': old_status, 'to': 'completed(failed)'})

                elif transcode_status == 'processing':
                    if video.process_status in ['uploaded', 'uploading']:
                        video.process_status = 'processing'
                        video.process_message = '转码中'
                        updated_count += 1
                        log_info(f"[SyncStatus] ✓ 视频ID={video.id} 更新为 processing")
                        details.append({'id': video.id, 'file_id': video.file_id, 'from': old_status, 'to': 'processing'})
                    else:
                        log_info(f"[SyncStatus] - 视频ID={video.id} 保持当前状态 {video.process_status}")
            else:
                log_warning(f"[SyncStatus] ✗ 视频ID={video.id} 查询转码状态失败: {result.get('error', '未知错误')}")

            # 检查删除状态
            if video.process_status == 'deleting':
                log_info(f"[SyncStatus] 检查删除状态: FileId={video.file_id}")
                check_result = vod_service.describe_media_infos(video.file_id)
                log_info(f"[SyncStatus] 删除检查结果: {json.dumps(check_result, ensure_ascii=False, default=str)}")

                if not check_result.get('success'):
                    # 云端已删除
                    old_status = video.process_status
                    video.process_status = 'deleted'
                    video.process_message = '已删除'
                    updated_count += 1
                    log_info(f"[SyncStatus] ✓ 视频ID={video.id} 更新为 deleted")
                    details.append({'id': video.id, 'file_id': video.file_id, 'from': old_status, 'to': 'deleted'})
                else:
                    log_info(f"[SyncStatus] - 视频ID={video.id} 云端仍存在，保持deleting状态")

        db.session.commit()
        log_info(f"[SyncStatus] ========== 同步完成，更新了 {updated_count} 个视频 ==========")

        return jsonify({
            'success': True,
            'message': f'同步完成，更新了 {updated_count} 个视频的状态',
            'updated_count': updated_count,
            'details': details
        })
    except Exception as e:
        db.session.rollback()
        log_error(f"[SyncStatus] 同步异常: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        })


@admin_bp.route('/api/videos/sync-deletion', methods=['POST'])
@admin_required
@login_required
def api_sync_all_deletion():
    """API: 同步所有已删除视频的状态"""
    import json
    log_info("[SyncAllDeletion] ========== 开始同步所有删除状态 ==========")

    try:
        # 获取所有标记为删除中的视频
        deleted_videos = VideoFile.query.filter_by(process_status='deleting').all()
        log_info(f"[SyncAllDeletion] 找到 {len(deleted_videos)} 个删除中的视频")

        vod_service = TencentVODService()
        synced_count = 0
        details = []

        for video in deleted_videos:
            log_info(f"[SyncAllDeletion] 检查视频: ID={video.id}, FileId={video.file_id}")

            if not video.file_id:
                video.process_status = 'deleted'
                video.process_message = '已删除（无FileId）'
                synced_count += 1
                details.append({'id': video.id, 'file_id': None, 'result': '无FileId，标记为已删除'})
                log_info(f"[SyncAllDeletion] ✓ 视频ID={video.id} 无FileId，标记为已删除")
                continue

            # 查询云端状态 - 使用多种方式检查
            result = vod_service.describe_media_infos(video.file_id)
            log_info(f"[SyncAllDeletion] DescribeMediaInfos结果: {json.dumps(result, ensure_ascii=False, default=str)}")

            search_result = vod_service.search_media(video.file_id)
            log_info(f"[SyncAllDeletion] SearchMedia结果: {json.dumps(search_result, ensure_ascii=False, default=str)}")

            # 判断云端是否存在
            cloud_exists = False
            if result.get('success') and result.get('media_info_set'):
                cloud_exists = True
            if search_result.get('exists'):
                cloud_exists = True

            if not cloud_exists:
                # 云端已删除
                video.process_status = 'deleted'
                video.process_message = '已删除（云端确认）'
                synced_count += 1
                details.append({'id': video.id, 'file_id': video.file_id, 'result': '云端已删除，同步完成'})
                log_info(f"[SyncAllDeletion] ✓ 视频ID={video.id} 云端已删除，标记为deleted")
            else:
                details.append({'id': video.id, 'file_id': video.file_id, 'result': '云端仍存在，保持deleting'})
                log_info(f"[SyncAllDeletion] - 视频ID={video.id} 云端仍存在，保持deleting状态")

        db.session.commit()
        log_info(f"[SyncAllDeletion] ========== 同步完成，{synced_count}/{len(deleted_videos)} 个视频确认已删除 ==========")

        return jsonify({
            'success': True,
            'message': f'同步完成，{synced_count} 个视频确认已删除',
            'synced_count': synced_count,
            'total': len(deleted_videos),
            'details': details
        })
    except Exception as e:
        db.session.rollback()
        log_error(f"[SyncAllDeletion] 同步异常: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        })


@admin_bp.route('/api/vod-files')
@admin_required
@login_required
def api_vod_files():
    """API: 获取VOD文件列表"""
    try:
        vod_service = TencentVODService()

        # 搜索媒体文件
        from tencentcloud.vod.v20180717 import models
        req = models.SearchMediaRequest()
        req.Limit = 100
        req.Offset = 0

        resp = vod_service.client.SearchMedia(req)

        files = []
        if hasattr(resp, 'MediaInfoSet'):
            for media in resp.MediaInfoSet:
                file_info = {
                    'file_id': media.FileId if hasattr(media, 'FileId') else '',
                    'name': media.Name if hasattr(media, 'Name') else '未命名',
                    'duration': media.Duration if hasattr(media, 'Duration') else 0,
                    'size': media.Size if hasattr(media, 'Size') else 0,
                    'create_time': media.CreateTime if hasattr(media, 'CreateTime') else ''
                }
                files.append(file_info)

        return jsonify({
            'success': True,
            'files': files,
            'total': resp.TotalCount if hasattr(resp, 'TotalCount') else len(files)
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

# ==================== 日志管理 ====================

@admin_bp.route('/logs')
@admin_required
@login_required
def logs():
    """日志管理"""
    page = request.args.get('page', 1, type=int)
    per_page = 20

    log_type = request.args.get('type', 'login')
    search = request.args.get('search', '')
    status = request.args.get('status', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')

    if log_type == 'login':
        query = LoginLog.query

        if search:
            query = query.filter(LoginLog.phone.contains(search))

        if status == 'success':
            query = query.filter_by(is_success=True)
        elif status == 'failed':
            query = query.filter_by(is_success=False)

        if date_from:
            query = query.filter(LoginLog.login_time >= date_from)
        if date_to:
            query = query.filter(LoginLog.login_time <= date_to)

        pagination = query.order_by(LoginLog.login_time.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )

        return render_template('admin/logs.html',
                              log_type=log_type,
                              logs=pagination.items,
                              pagination=pagination,
                              search=search,
                              status=status,
                              date_from=date_from,
                              date_to=date_to)
    else:
        query = PlayLog.query

        if search:
            query = query.join(User).filter(
                db.or_(
                    User.phone.contains(search),
                    Course.title.contains(search)
                )
            )

        if date_from:
            query = query.filter(PlayLog.play_time >= date_from)
        if date_to:
            query = query.filter(PlayLog.play_time <= date_to)

        pagination = query.order_by(PlayLog.play_time.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )

        return render_template('admin/logs.html',
                              log_type=log_type,
                              logs=pagination.items,
                              pagination=pagination,
                              search=search,
                              status=status,
                              date_from=date_from,
                              date_to=date_to)

# ==================== 锁定管理 ====================

@admin_bp.route('/locked')
@admin_required
@login_required
def locked():
    """锁定管理"""
    locked_users = User.query.filter_by(is_locked=True).all()
    locked_ips = LockedIP.query.filter_by(is_locked=True).all()

    return render_template('admin/locked.html',
                          locked_users=locked_users,
                          locked_ips=locked_ips)

@admin_bp.route('/locked/users/<int:user_id>/unlock', methods=['POST'])
@admin_required
@login_required
def unlock_user(user_id):
    """解锁用户"""
    user = User.query.get_or_404(user_id)

    user.is_locked = False
    user.login_fail_count = 0
    db.session.commit()

    flash('用户已解锁', 'success')
    return redirect(url_for('admin.locked'))

@admin_bp.route('/locked/ips/<ip_address>/unlock', methods=['POST'])
@admin_required
@login_required
def unlock_ip_address(ip_address):
    """解锁IP"""
    unlock_ip(ip_address)

    flash('IP已解锁', 'success')
    return redirect(url_for('admin.locked'))

# ==================== 系统配置 ====================

@admin_bp.route('/config')
@admin_required
@login_required
def system_config():
    """系统配置"""
    init_default_configs()

    configs = {
        'app_id': get_config('app_id', ''),
        'secret_id': get_config('secret_id', ''),
        'secret_key': '',
        'play_key': '',
        'license_url': get_config('license_url', ''),
        'license_key': '',
        'callback_key': '',
        'hourly_access_limit': get_config('hourly_access_limit', '10'),
        'login_fail_limit': get_config('login_fail_limit', '10'),
        'ghost_watermark_line1': get_config('ghost_watermark_line1', 'Serendipity4869'),
        'vod_procedure_name': get_config('vod_procedure_name', 'HLS_S1'),
        'log_level': get_config('log_level', 'INFO'),
        'log_console_output': get_config('log_console_output', 'false'),
        'log_backup_count': get_config('log_backup_count', '20'),
    }

    return render_template('admin/config.html', configs=configs)

@admin_bp.route('/config/save', methods=['POST'])
@admin_required
@login_required
def save_config():
    """保存配置"""
    set_config('app_id', request.form.get('app_id', ''), '腾讯云应用ID', False)
    set_config('license_url', request.form.get('license_url', ''), 'TCPlayer License地址', False)

    if request.form.get('secret_id'):
        set_config('secret_id', request.form.get('secret_id'), 'API密钥ID', True)
    if request.form.get('secret_key'):
        set_config('secret_key', request.form.get('secret_key'), 'API密钥', True)
    if request.form.get('play_key'):
        set_config('play_key', request.form.get('play_key'), '播放密钥', True)
    if request.form.get('license_key'):
        set_config('license_key', request.form.get('license_key'), 'TCPlayer License密钥', True)

    set_config('hourly_access_limit', request.form.get('hourly_access_limit', '10'), '默认每小时访问次数限制', False)
    set_config('login_fail_limit', request.form.get('login_fail_limit', '10'), '默认登录失败次数限制', False)
    set_config('ghost_watermark_line1', request.form.get('ghost_watermark_line1', 'Serendipity4869'), '幽灵水印第一行', False)
    set_config('vod_procedure_name', request.form.get('vod_procedure_name', 'HLS_S1'), 'VOD任务流名称', False)

    if request.form.get('callback_key'):
        set_config('callback_key', request.form.get('callback_key'), '回调密钥', True)

    # 保存日志配置
    set_config('log_level', request.form.get('log_level', 'INFO'), '日志等级', False)
    set_config('log_console_output', request.form.get('log_console_output', 'false'), '控制台打印', False)
    set_config('log_backup_count', request.form.get('log_backup_count', '20'), '日志文件留存数量', False)
    
    # 保存上传配置
    set_config('max_file_size', request.form.get('max_file_size', '100'), '最大文件大小(MB)', False)

    # 重新初始化日志服务
    try:
        from app.services.logger import get_logger_service
        log_level = request.form.get('log_level', 'INFO')
        console_output = request.form.get('log_console_output', 'false') == 'true'
        backup_count = int(request.form.get('log_backup_count', '20'))
        get_logger_service().reconfigure(log_level, console_output, backup_count)
        log_info('日志服务已重新配置')
    except Exception as e:
        log_error(f'重新配置日志服务失败: {e}')

    flash('配置已保存', 'success')
    return redirect(url_for('admin.system_config'))

@admin_bp.route('/config/test', methods=['POST'])
@admin_required
@login_required
def test_config():
    """测试配置"""
    try:
        vod_service = TencentVODService()
        result = vod_service.test_connection()

        if result['success']:
            return jsonify({
                'success': True,
                'message': f'连接测试成功！共有 {result["total_count"]} 个媒体文件'
            })
        else:
            return jsonify({
                'success': False,
                'error': result['error']
            })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

# ==================== 事件管理 ====================

@admin_bp.route('/events')
@admin_required
@login_required
def events():
    """事件管理页面 - 显示未消费的VOD事件"""
    page = request.args.get('page', 1, type=int)
    per_page = 20

    # 获取所有未消费的事件，按时间倒序
    query = VodEvent.query.filter_by(is_consumed=False).order_by(VodEvent.created_at.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    return render_template('admin/events.html',
                          events=pagination.items,
                          pagination=pagination)

@admin_bp.route('/events/pull', methods=['POST'])
@admin_required
@login_required
def pull_events():
    """
    手工拉取全部未消费事件（可靠回调模式）

    可靠回调流程：
    1. 检查事件通知配置
    2. 调用拉取事件通知接口
    3. 处理事件并更新数据库
    4. 数据库更新完成后再调用确认事件通知接口
    """
    try:
        vod_service = TencentVODService()

        # ========== 步骤1: 获取事件通知配置 ==========
        config_result = vod_service.describe_event_config()
        if config_result['success']:
            log_info(f"[PULL_EVENTS] 事件通知配置: switch={config_result.get('callback_switch')}, mode={config_result.get('notify_type')}")

        # ========== 步骤2: 调用拉取事件通知接口 ==========
        result = vod_service.pull_events()

        if not result['success']:
            return jsonify({
                'success': False,
                'error': result.get('error', '拉取事件失败'),
                'stage': 'pull_events'
            })

        events = result.get('events', [])
        if not events:
            return jsonify({
                'success': True,
                'message': '拉取到的事件列表为空',
                'count': 0,
                'stage': 'empty_events'
            })

        # ========== 步骤3: 先删除原有的未消费记录 ==========
        VodEvent.query.filter_by(is_consumed=False).delete()
        db.session.commit()
        log_info(f"[PULL_EVENTS] 清空原有未消费记录，准备添加 {len(events)} 个新事件")

        # ========== 步骤4: 添加新拉取的事件到本地数据库 ==========
        added_count = 0
        confirm_handles = []

        for event_data in events:
            event_handle = event_data.get('EventHandle', '')
            event_type = event_data.get('EventType', '')

            # 保存到本地数据库
            event = VodEvent(
                event_handle=event_handle,
                event_type=event_type,
                event_data=json.dumps(event_data, ensure_ascii=False),
                is_consumed=False
            )
            db.session.add(event)
            added_count += 1
            confirm_handles.append(event_handle)

        db.session.commit()
        log_info(f"[PULL_EVENTS] 已保存 {added_count} 个事件到本地数据库")

        # ========== 步骤5: 数据库更新完成后，确认事件已接收 ==========
        # 注意：确认后事件将从腾讯云队列中移除
        if confirm_handles:
            confirm_result = vod_service.confirm_events(confirm_handles)
            if confirm_result['success']:
                log_info(f"[PULL_EVENTS] 确认 {len(confirm_handles)} 个事件成功")
            else:
                log_warning(f"[PULL_EVENTS] 确认事件失败: {confirm_result.get('error')}")

        return jsonify({
            'success': True,
            'message': f'成功拉取 {added_count} 个事件',
            'count': added_count,
            'confirmed_count': len(confirm_handles),
            'stage': 'completed'
        })

    except Exception as e:
        db.session.rollback()
        import traceback
        log_error(f"[PULL_EVENTS] 拉取事件异常: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            'success': False,
            'error': f'拉取事件异常: {str(e)}'
        })

@admin_bp.route('/events/<int:event_id>/consume', methods=['POST'])
@admin_required
@login_required
def consume_event(event_id):
    """手工消费单个事件"""
    try:
        event = VodEvent.query.get_or_404(event_id)

        if event.is_consumed:
            return jsonify({
                'success': False,
                'error': '事件已被消费'
            })

        vod_service = TencentVODService()

        # 处理事件
        from app.tasks.event_consumer import process_event
        from flask import current_app
        import json

        # 解析事件数据
        event_data = event.event_data
        if isinstance(event_data, str):
            try:
                event_data = json.loads(event_data)
            except json.JSONDecodeError as e:
                log_error(f"解析事件数据失败: {e}")
                return jsonify({
                    'success': False,
                    'error': '事件数据格式错误'
                })

        success, should_confirm = process_event(event_data, vod_service, current_app._get_current_object())

        if success:
            # 确认事件
            if should_confirm and event.event_handle:
                confirm_result = vod_service.confirm_events([event.event_handle])
                if not confirm_result['success']:
                    log_warning(f"确认事件失败: {event.event_handle}")

            # 删除事件记录
            db.session.delete(event)
            db.session.commit()

            return jsonify({
                'success': True,
                'message': '事件消费成功'
            })
        else:
            return jsonify({
                'success': False,
                'error': '事件处理失败'
            })

    except Exception as e:
        db.session.rollback()
        import traceback
        log_error(f"消费事件异常: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            'success': False,
            'error': f'消费事件异常: {str(e)}'
        })

@admin_bp.route('/events/consume-all', methods=['POST'])
@admin_required
@login_required
def consume_all_events():
    """消费所有未消费的事件"""
    try:
        events = VodEvent.query.filter_by(is_consumed=False).all()

        if not events:
            return jsonify({
                'success': True,
                'message': '没有待消费的事件',
                'count': 0
            })

        vod_service = TencentVODService()
        from app.tasks.event_consumer import process_event
        from flask import current_app
        import json

        success_count = 0
        confirm_handles = []

        for event in events:
            # 解析事件数据
            event_data = event.event_data
            if isinstance(event_data, str):
                try:
                    event_data = json.loads(event_data)
                except json.JSONDecodeError as e:
                    log_error(f"解析事件数据失败 (event_id={event.id}): {e}")
                    continue

            success, should_confirm = process_event(event_data, vod_service, current_app._get_current_object())

            if success:
                success_count += 1
                if should_confirm and event.event_handle:
                    confirm_handles.append(event.event_handle)
                # 删除已处理的事件记录
                db.session.delete(event)

        # 批量确认事件
        if confirm_handles:
            confirm_result = vod_service.confirm_events(confirm_handles)
            if not confirm_result['success']:
                log_warning(f"批量确认事件失败: {confirm_result.get('error')}")

        db.session.commit()

        return jsonify({
            'success': True,
            'message': f'成功消费 {success_count}/{len(events)} 个事件',
            'count': success_count
        })

    except Exception as e:
        db.session.rollback()
        import traceback
        log_error(f"批量消费事件异常: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            'success': False,
            'error': f'消费事件异常: {str(e)}'
        })

@admin_bp.route('/events/confirm-all', methods=['POST'])
@admin_required
@login_required
def confirm_all_events():
    """确认所有未消费的事件（危险操作，仅用于清理）"""
    try:
        events = VodEvent.query.filter_by(is_consumed=False).all()

        if not events:
            return jsonify({
                'success': True,
                'message': '没有待确认的事件',
                'count': 0
            })

        vod_service = TencentVODService()
        confirm_handles = [e.event_handle for e in events if e.event_handle]

        if confirm_handles:
            confirm_result = vod_service.confirm_events(confirm_handles)
            if confirm_result['success']:
                # 删除本地记录
                for event in events:
                    db.session.delete(event)
                db.session.commit()

                return jsonify({
                    'success': True,
                    'message': f'成功确认 {len(confirm_handles)} 个事件',
                    'count': len(confirm_handles)
                })
            else:
                return jsonify({
                    'success': False,
                    'error': f'确认事件失败: {confirm_result.get("error")}'
                })

        return jsonify({
            'success': True,
            'message': '没有有效的事件句柄需要确认',
            'count': 0
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': f'确认事件异常: {str(e)}'
        })


# ==================== 事件管理 API ====================

@admin_bp.route('/api/events/list')
@admin_required
@login_required
def api_events_list():
    """API: 获取未消费事件列表"""
    try:
        events = VodEvent.query.filter_by(is_consumed=False).order_by(VodEvent.created_at.desc()).all()

        event_list = []
        for event in events:
            # 解析事件数据
            event_data = {}
            if isinstance(event.event_data, dict):
                event_data = event.event_data
            elif isinstance(event.event_data, str):
                import json
                try:
                    event_data = json.loads(event.event_data)
                except:
                    event_data = {}

            # 提取FileId
            file_id = None
            if event.event_type == 'NewFileUpload':
                file_id = event_data.get('FileUploadEvent', {}).get('FileId')
            elif event.event_type == 'ProcedureStateChanged':
                file_id = event_data.get('ProcedureStateChangeEvent', {}).get('FileId')
            elif event.event_type == 'FileDeleted':
                file_delete_event = event_data.get('FileDeleteEvent', {})
                file_id = file_delete_event.get('FileId')
                # FileDeleteEvent使用FileIdSet而不是FileId
                if not file_id and file_delete_event.get('FileIdSet'):
                    file_id = file_delete_event['FileIdSet'][0]

            # 提取事件时间（优先使用EventTime，即事件实际发生时间）
            event_time = None
            if event_data.get('EventTime'):
                # EventTime是UTC时间戳，转换为东八区时间
                from datetime import datetime, timedelta
                try:
                    ts = event_data['EventTime']
                    # 判断是毫秒还是秒（毫秒时间戳通常是13位以上）
                    if ts > 1000000000000:
                        ts = ts // 1000
                    utc_time = datetime.utcfromtimestamp(ts)
                    cn_time = utc_time + timedelta(hours=8)
                    event_time = cn_time.strftime('%Y-%m-%d %H:%M:%S')
                except:
                    event_time = None

            # 如果没有EventTime，则使用本地记录的创建时间（向后兼容）
            if not event_time and event.created_at:
                event_time = (event.created_at + __import__('datetime', fromlist=['timedelta']).timedelta(hours=8)).strftime('%Y-%m-%d %H:%M:%S')

            event_list.append({
                'id': event.id,
                'handle': event.event_handle,
                'type': event.event_type,
                'file_id': file_id,
                'time': event_time,
                'status': 'pending',
                'data': event_data
            })

        return jsonify({
            'success': True,
            'events': event_list,
            'total': len(event_list)
        })
    except Exception as e:
        import traceback
        log_error(f"获取事件列表异常: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            'success': False,
            'error': str(e)
        })

@admin_bp.route('/api/events/pull', methods=['POST'])
@admin_required
@login_required
def api_pull_events():
    """
    API: 拉取并返回未消费事件列表（可靠回调模式）

    可靠回调流程：
    1. 检查事件通知配置
    2. 调用拉取事件通知接口
    3. 处理事件并更新数据库
    4. 数据库更新完成后再调用确认事件通知接口
    """
    try:
        vod_service = TencentVODService()

        # ========== 步骤1: 获取事件通知配置 ==========
        config_result = vod_service.describe_event_config()
        if config_result['success']:
            log_info(f"[API_PULL_EVENTS] 事件通知配置: switch={config_result.get('callback_switch')}, mode={config_result.get('notify_type')}")

        # ========== 步骤2: 调用拉取事件通知接口 ==========
        result = vod_service.pull_events()

        if not result['success']:
            return jsonify({
                'success': False,
                'error': result.get('error', '拉取事件失败'),
                'stage': 'pull_events'
            })

        events = result.get('events', [])
        request_id = result.get('request_id')

        # 当返回RequestId但EventSet为null时，清空本地所有未消费事件
        if not events:
            if request_id:
                # 拉取成功但没有事件，说明全部事件都已消费，清空本地记录
                deleted_count = VodEvent.query.filter_by(is_consumed=False).delete()
                db.session.commit()
                log_info(f"[EventPull] 全部事件已消费，清空本地 {deleted_count} 条未消费记录")
            return jsonify({
                'success': True,
                'message': '没有待处理的事件',
                'events': [],
                'total': 0
            })

        # 先删除原有的未消费记录
        VodEvent.query.filter_by(is_consumed=False).delete()
        db.session.commit()

        # 添加新拉取的事件
        added_count = 0
        for event_data in events:
            event = VodEvent(
                event_handle=event_data.get('EventHandle', ''),
                event_type=event_data.get('EventType', ''),
                event_data=json.dumps(event_data, ensure_ascii=False),
                is_consumed=False
            )
            db.session.add(event)
            added_count += 1

        db.session.commit()

        # 返回格式化后的事件列表
        event_list = []
        for event in events:
            file_id = None
            if event.get('EventType') == 'NewFileUpload':
                file_id = event.get('FileUploadEvent', {}).get('FileId')
            elif event.get('EventType') == 'ProcedureStateChanged':
                file_id = event.get('ProcedureStateChangeEvent', {}).get('FileId')
            elif event.get('EventType') == 'FileDeleted':
                file_delete_event = event.get('FileDeleteEvent', {})
                file_id = file_delete_event.get('FileId')
                if not file_id and file_delete_event.get('FileIdSet'):
                    file_id = file_delete_event['FileIdSet'][0]

            # 提取事件时间并转换为东八区
            event_time = None
            if event.get('EventTime'):
                from datetime import datetime, timedelta
                try:
                    ts = event['EventTime']
                    # 判断是毫秒还是秒（毫秒时间戳通常是13位以上）
                    if ts > 1000000000000:
                        ts = ts // 1000
                    utc_time = datetime.utcfromtimestamp(ts)
                    cn_time = utc_time + timedelta(hours=8)
                    event_time = cn_time.strftime('%Y-%m-%d %H:%M:%S')
                except:
                    event_time = None

            event_list.append({
                'handle': event.get('EventHandle', ''),
                'type': event.get('EventType', ''),
                'file_id': file_id,
                'time': event_time,
                'status': 'pending'
            })

        # ========== 步骤3: 数据库更新完成后，确认事件已接收 ==========
        # 注意：确认后事件将从腾讯云队列中移除
        confirm_handles = [e.get('EventHandle', '') for e in events if e.get('EventHandle')]
        confirmed_count = 0
        if confirm_handles:
            confirm_result = vod_service.confirm_events(confirm_handles)
            if confirm_result['success']:
                confirmed_count = len(confirm_handles)
                log_info(f"[API_PULL_EVENTS] 确认 {confirmed_count} 个事件成功")
            else:
                log_warning(f"[API_PULL_EVENTS] 确认事件失败: {confirm_result.get('error')}")

        return jsonify({
            'success': True,
            'message': f'成功拉取 {added_count} 个事件，确认 {confirmed_count} 个',
            'events': event_list,
            'total': added_count,
            'confirmed_count': confirmed_count,
            'stage': 'completed'
        })

    except Exception as e:
        db.session.rollback()
        import traceback
        log_error(f"拉取事件异常: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            'success': False,
            'error': f'拉取事件异常: {str(e)}'
        })

@admin_bp.route('/api/events/consume/<handle>', methods=['POST'])
@admin_required
@login_required
def api_consume_event(handle):
    """API: 通过handle消费单个事件"""
    try:
        # 查找事件
        event = VodEvent.query.filter_by(event_handle=handle, is_consumed=False).first()

        if not event:
            return jsonify({
                'success': False,
                'error': '事件不存在或已被消费'
            })

        vod_service = TencentVODService()

        # 处理事件
        from app.tasks.event_consumer import process_event
        from flask import current_app
        import json

        # 解析事件数据
        event_data = event.event_data
        if isinstance(event_data, str):
            try:
                event_data = json.loads(event_data)
            except json.JSONDecodeError as e:
                log_error(f"解析事件数据失败: {e}")
                return jsonify({
                    'success': False,
                    'error': '事件数据格式错误'
                })

        success, should_confirm = process_event(event_data, vod_service, current_app._get_current_object())

        if success:
            # 确认事件
            if should_confirm and event.event_handle:
                confirm_result = vod_service.confirm_events([event.event_handle])
                if not confirm_result['success']:
                    log_warning(f"确认事件失败: {event.event_handle}")

            # 删除事件记录
            db.session.delete(event)
            db.session.commit()

            return jsonify({
                'success': True,
                'message': '事件消费成功'
            })
        else:
            return jsonify({
                'success': False,
                'error': '事件处理失败'
            })

    except Exception as e:
        db.session.rollback()
        import traceback
        log_error(f"消费事件异常: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            'success': False,
            'error': f'消费事件异常: {str(e)}'
        })


@admin_bp.route('/api/upload-image', methods=['POST'])
@login_required
def api_upload_image():
    # 检查是否是管理员
    if not current_user.is_admin:
        return jsonify({'success': False, 'error': '无权限'}), 403
    """API: 上传富文本编辑器图片到本地存储
    用于 TinyMCE 编辑器图片上传
    """
    try:
        if 'file' not in request.files:
            return jsonify({
                'success': False,
                'error': '没有上传文件'
            })

        file = request.files['file']
        if file.filename == '':
            return jsonify({
                'success': False,
                'error': '文件名为空'
            })

        # 检查文件类型
        allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
        file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
        
        if file_ext not in allowed_extensions:
            return jsonify({
                'success': False,
                'error': f'不支持的文件类型'
            })

        # 生成唯一文件名
        import uuid
        from werkzeug.utils import secure_filename
        
        safe_filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4().hex}_{safe_filename}"
        
        # 确保上传目录存在
        upload_dir = os.path.join(current_app.root_path, 'static', 'uploads', 'images')
        os.makedirs(upload_dir, exist_ok=True)
        
        # 保存文件
        file_path = os.path.join(upload_dir, unique_filename)
        file.save(file_path)
        
        # 返回文件URL
        file_url = url_for('static', filename=f'uploads/images/{unique_filename}', _external=True)
        
        log_info(f"[UploadImage] 图片上传成功: {unique_filename}", 'app')
        
        return jsonify({
            'success': True,
            'location': file_url,
            'filename': unique_filename
        })

    except Exception as e:
        log_error(f"[UploadImage] 图片上传失败: {str(e)}", 'app')
        return jsonify({
            'success': False,
            'error': f'上传失败: {str(e)}'
        })


@admin_bp.route('/api/videos/<int:video_id>/rename', methods=['POST'])
@admin_required
@login_required
def api_rename_video(video_id):
    """API: 重命名视频文件
    1. 先调用腾讯云API修改云端文件名
    2. 成功后更新本地数据库
    """
    try:
        data = request.get_json()
        new_name = data.get('new_name', '').strip()
        
        if not new_name:
            return jsonify({
                'success': False,
                'error': '新文件名不能为空'
            }), 400
        
        # 查找视频
        video = VideoFile.query.get_or_404(video_id)
        
        # 检查视频状态
        if video.process_status != 'completed':
            return jsonify({
                'success': False,
                'error': '只有"转码完成"状态的视频才能重命名'
            }), 400
        
        # 检查是否有chapter关联（如果有关联则不允许重命名，避免影响播放）
        chapter = Chapter.query.filter_by(file_id=video.file_id).first()
        if chapter:
            return jsonify({
                'success': False,
                'error': '该视频已被课程章节使用，不能重命名'
            }), 400
        
        log_info(f"[RenameVideo] 开始重命名: video_id={video_id}, file_id={video.file_id}, old_name={video.file_name}, new_name={new_name}")
        
        # 调用腾讯云API修改文件名
        vod_service = TencentVODService()
        result = vod_service.modify_media_info(video.file_id, new_name)
        
        if not result.get('success'):
            error_msg = result.get('error', '未知错误')
            log_error(f"[RenameVideo] 腾讯云API调用失败: {error_msg}")
            return jsonify({
                'success': False,
                'error': f'云端重命名失败: {error_msg}'
            }), 500
        
        # 更新本地数据库
        old_name = video.file_name
        video.file_name = new_name
        video.title = new_name  # 同时更新标题
        db.session.commit()
        
        log_info(f"[RenameVideo] 重命名成功: video_id={video_id}, {old_name} -> {new_name}")
        
        return jsonify({
            'success': True,
            'message': f'重命名成功: {old_name} -> {new_name}',
            'video': {
                'id': video.id,
                'file_id': video.file_id,
                'file_name': video.file_name
            }
        })
        
    except Exception as e:
        db.session.rollback()
        log_error(f"[RenameVideo] 重命名失败: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'重命名失败: {str(e)}'
        }), 500


@admin_bp.route('/api/videos/move-to-folder', methods=['POST'])
@admin_required
@login_required
def api_move_videos_to_folder():
    """API: 将视频移动到指定文件夹"""
    try:
        data = request.get_json()
        video_ids = data.get('video_ids', [])
        folder_id = data.get('folder_id')
        
        if not video_ids or not isinstance(video_ids, list):
            return jsonify({
                'success': False,
                'error': '请提供要移动的视频ID列表'
            }), 400
        
        if folder_id is None:
            return jsonify({
                'success': False,
                'error': '请提供目标文件夹ID'
            }), 400
        
        # 验证文件夹是否存在
        folder = VideoFolder.query.get(folder_id)
        if not folder:
            return jsonify({
                'success': False,
                'error': '目标文件夹不存在'
            }), 404
        
        # 移动视频
        moved_count = 0
        skipped_count = 0
        
        for video_id in video_ids:
            video = VideoFile.query.get(video_id)
            if video:
                if video.folder_id == folder_id:
                    skipped_count += 1  # 已经在目标文件夹中
                else:
                    video.folder_id = folder_id
                    moved_count += 1
        
        db.session.commit()
        
        log_info(f"[MoveVideos] 移动完成: 移动{moved_count}个, 跳过{skipped_count}个, 目标文件夹={folder.name}")
        
        return jsonify({
            'success': True,
            'message': f'成功移动 {moved_count} 个视频到 "{folder.name}"' + (f'，跳过{skipped_count}个已在目标文件夹的视频' if skipped_count > 0 else ''),
            'moved_count': moved_count,
            'skipped_count': skipped_count
        })
        
    except Exception as e:
        db.session.rollback()
        log_error(f"[MoveVideos] 移动失败: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'移动失败: {str(e)}'
        }), 500
