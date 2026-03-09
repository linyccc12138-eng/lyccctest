# -*- coding: utf-8 -*-
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
from app import db
import bcrypt

class User(UserMixin, db.Model):
    """用户表"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    phone = db.Column(db.String(20), unique=True, nullable=False, comment='手机号，作为用户名')
    password_hash = db.Column(db.String(255), nullable=False, comment='bcrypt加密后的密码')
    remark = db.Column(db.String(255), comment='备注')
    is_admin = db.Column(db.Boolean, default=False, comment='是否管理员')
    is_first_login = db.Column(db.Boolean, default=True, comment='是否首次登录')
    is_locked = db.Column(db.Boolean, default=False, comment='是否被锁定')
    login_fail_count = db.Column(db.Integer, default=0, comment='登录失败次数')
    hourly_access_count = db.Column(db.Integer, default=0, comment='当前小时访问次数')
    last_access_hour = db.Column(db.DateTime, comment='上次访问的小时')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关系
    permissions = db.relationship('UserCoursePermission', back_populates='user', cascade='all, delete-orphan')
    login_logs = db.relationship('LoginLog', back_populates='user', lazy='dynamic')
    play_logs = db.relationship('PlayLog', back_populates='user', lazy='dynamic')
    
    def set_password(self, password):
        """设置密码"""
        salt = bcrypt.gensalt(rounds=12)
        self.password_hash = bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')
    
    def check_password(self, password):
        """验证密码"""
        return bcrypt.checkpw(password.encode('utf-8'), self.password_hash.encode('utf-8'))
    
    def get_id(self):
        """返回用户ID"""
        return str(self.id)
    
    def is_active(self):
        """检查用户是否激活"""
        return not self.is_locked
    
    def check_hourly_limit(self):
        """检查每小时访问次数"""
        from app.services.security import get_config
        
        current_hour = datetime.now().replace(minute=0, second=0, microsecond=0)
        
        if self.last_access_hour != current_hour:
            self.hourly_access_count = 0
            self.last_access_hour = current_hour
        
        max_access = int(get_config('hourly_access_limit', 10))
        if self.hourly_access_count >= max_access:
            return False
        
        self.hourly_access_count += 1
        db.session.commit()
        return True
    
    def has_course_permission(self, course_id):
        """检查是否有课程权限"""
        if self.is_admin:
            return True
        return UserCoursePermission.query.filter_by(
            user_id=self.id, 
            course_id=course_id
        ).first() is not None
    
    def get_allowed_courses(self):
        """获取用户有权限的课程列表"""
        if self.is_admin:
            return Course.query.all()
        permissions = UserCoursePermission.query.filter_by(user_id=self.id).all()
        course_ids = [p.course_id for p in permissions]
        return Course.query.filter(Course.id.in_(course_ids)).all()
    
    def __repr__(self):
        return f'<User {self.phone}>'


class Course(db.Model):
    """课程表"""
    __tablename__ = 'courses'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    title = db.Column(db.String(255), nullable=False, comment='课程标题')
    description = db.Column(db.Text, comment='课程简介')
    detail_content = db.Column(db.Text, comment='富文本详情内容')
    thumbnail_url = db.Column(db.String(500), comment='缩略图URL')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关系
    chapters = db.relationship('Chapter', back_populates='course', cascade='all, delete-orphan', order_by='Chapter.sort_order')
    permissions = db.relationship('UserCoursePermission', back_populates='course', cascade='all, delete-orphan')
    play_logs = db.relationship('PlayLog', back_populates='course', lazy='dynamic')
    
    def __repr__(self):
        return f'<Course {self.title}>'


class Chapter(db.Model):
    """章节表"""
    __tablename__ = 'chapters'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id', ondelete='CASCADE'), nullable=False, comment='所属课程ID')
    title = db.Column(db.String(255), nullable=False, comment='章节标题')
    description = db.Column(db.Text, comment='章节简介')
    file_id = db.Column(db.String(100), comment='腾讯云FileId')
    thumbnail_url = db.Column(db.String(500), comment='缩略图URL')
    sort_order = db.Column(db.Integer, default=0, comment='排序')
    transcode_status = db.Column(db.String(20), default='pending', comment='转码状态: pending-等待, processing-转码中, success-成功, failed-失败')
    transcode_message = db.Column(db.String(500), comment='转码状态描述或错误信息')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关系
    course = db.relationship('Course', back_populates='chapters')
    play_logs = db.relationship('PlayLog', back_populates='chapter', lazy='dynamic')
    
    def __repr__(self):
        return f'<Chapter {self.title}>'


class UserCoursePermission(db.Model):
    """用户课程权限表"""
    __tablename__ = 'user_course_permissions'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id', ondelete='CASCADE'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # 关系
    user = db.relationship('User', back_populates='permissions')
    course = db.relationship('Course', back_populates='permissions')
    
    __table_args__ = (
        db.UniqueConstraint('user_id', 'course_id', name='unique_user_course'),
    )
    
    def __repr__(self):
        return f'<UserCoursePermission user={self.user_id} course={self.course_id}>'


class LoginLog(db.Model):
    """登录日志表"""
    __tablename__ = 'login_logs'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), comment='用户ID')
    phone = db.Column(db.String(20), comment='手机号')
    login_time = db.Column(db.DateTime, default=datetime.utcnow)
    client_type = db.Column(db.String(50), comment='客户端类型')
    ip_address = db.Column(db.String(50), comment='IP地址')
    is_success = db.Column(db.Boolean, comment='是否成功')
    fail_reason = db.Column(db.String(255), comment='失败原因')
    
    # 关系
    user = db.relationship('User', back_populates='login_logs')
    
    def __repr__(self):
        return f'<LoginLog {self.phone} {self.login_time}>'


class PlayLog(db.Model):
    """播放日志表"""
    __tablename__ = 'play_logs'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    chapter_id = db.Column(db.Integer, db.ForeignKey('chapters.id'), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    play_time = db.Column(db.DateTime, default=datetime.utcnow, comment='播放时间')
    progress = db.Column(db.Numeric(5, 2), comment='播放进度百分比')
    duration = db.Column(db.Integer, comment='观看时长(秒)')
    
    # 关系
    user = db.relationship('User', back_populates='play_logs')
    chapter = db.relationship('Chapter', back_populates='play_logs')
    course = db.relationship('Course', back_populates='play_logs')
    
    def __repr__(self):
        return f'<PlayLog user={self.user_id} chapter={self.chapter_id}>'


class LockedIP(db.Model):
    """锁定IP表"""
    __tablename__ = 'locked_ips'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    ip_address = db.Column(db.String(50), unique=True, nullable=False)
    fail_count = db.Column(db.Integer, default=0)
    is_locked = db.Column(db.Boolean, default=False)
    locked_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<LockedIP {self.ip_address} locked={self.is_locked}>'


class SystemConfig(db.Model):
    """系统配置表"""
    __tablename__ = 'system_config'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    config_key = db.Column(db.String(100), unique=True, nullable=False)
    config_value = db.Column(db.Text)
    description = db.Column(db.String(255))
    is_encrypted = db.Column(db.Boolean, default=False, comment='是否加密存储')
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<SystemConfig {self.config_key}>'


class VideoFolder(db.Model):
    """视频文件夹表"""
    __tablename__ = 'video_folders'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(255), nullable=False, comment='文件夹名称')
    parent_id = db.Column(db.Integer, db.ForeignKey('video_folders.id', ondelete='CASCADE'), comment='父文件夹ID')
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id', ondelete='SET NULL'), comment='关联课程ID')
    created_at = db.Column(db.DateTime, default=datetime.utcnow, comment='创建时间')
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment='更新时间')

    # 关系
    parent = db.relationship('VideoFolder', remote_side=[id], backref='children')
    course = db.relationship('Course', backref='video_folders')

    def __repr__(self):
        return f'<VideoFolder {self.name}>'

    def get_full_path(self):
        """获取文件夹完整路径"""
        if self.parent:
            return self.parent.get_full_path() + '/' + self.name
        return self.name


class VideoFile(db.Model):
    """视频文件管理表"""
    __tablename__ = 'video_files'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    file_id = db.Column(db.String(100), unique=True, nullable=True, comment='腾讯云FileId')
    file_name = db.Column(db.String(255), comment='原始文件名')
    title = db.Column(db.String(255), comment='视频标题')
    description = db.Column(db.Text, comment='视频描述')
    duration = db.Column(db.Integer, comment='视频时长(秒)')
    size = db.Column(db.BigInteger, comment='文件大小(字节)')
    width = db.Column(db.Integer, comment='视频宽度(px)')
    height = db.Column(db.Integer, comment='视频高度(px)')
    bitrate = db.Column(db.Integer, comment='视频码率(bps)')
    folder_id = db.Column(db.Integer, db.ForeignKey('video_folders.id', ondelete='SET NULL'), comment='所属文件夹ID')

    # 处理状态: uploading-上传中, uploaded-上传完成, processing-转码中, completed-转码完成, deleting-删除中, deleted-已删除
    process_status = db.Column(db.String(20), default='uploading',
                                comment='处理状态: uploading-上传中, uploaded-上传完成, processing-转码中, completed-转码完成, deleting-删除中, deleted-已删除')

    # 状态描述或错误信息
    process_message = db.Column(db.String(500), comment='处理状态描述或错误信息')

    # 任务流信息
    task_id = db.Column(db.String(100), comment='任务流任务ID')
    procedure_name = db.Column(db.String(100), comment='使用的任务流名称')

    # 封面图
    cover_url = db.Column(db.String(500), comment='封面图URL')
    local_cover_path = db.Column(db.String(500), comment='本地封面图路径')

    # 播放地址
    play_url = db.Column(db.String(500), comment='播放地址')

    # 关联信息
    chapter_id = db.Column(db.Integer, db.ForeignKey('chapters.id', ondelete='SET NULL'),
                           comment='关联章节ID')

    created_at = db.Column(db.DateTime, default=datetime.utcnow, comment='创建时间')
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment='更新时间')

    # 关系
    chapter = db.relationship('Chapter', backref='video_file', foreign_keys='VideoFile.chapter_id')
    folder = db.relationship('VideoFolder', backref='videos')

    def __repr__(self):
        return f'<VideoFile {self.file_id} {self.status}>'


class VodEvent(db.Model):
    """VOD事件表 - 存储未消费的可靠回调事件"""
    __tablename__ = 'vod_events'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    event_handle = db.Column(db.String(255), nullable=False, comment='事件句柄')
    event_type = db.Column(db.String(50), nullable=False, comment='事件类型')
    event_data = db.Column(db.Text, comment='事件原始数据(JSON)')
    is_consumed = db.Column(db.Boolean, default=False, comment='是否已消费')
    consumed_at = db.Column(db.DateTime, comment='消费时间')
    created_at = db.Column(db.DateTime, default=datetime.utcnow, comment='创建时间')

    def __repr__(self):
        return f'<VodEvent {self.event_type} {self.event_handle[:20]}...>'
