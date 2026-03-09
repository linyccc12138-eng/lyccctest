# -*- coding: utf-8 -*-
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app.models import Course, Chapter, UserCoursePermission
from app.services.security import check_referer

course_bp = Blueprint('course', __name__)

@course_bp.route('/')
@login_required
def list_courses():
    """课程列表"""
    # 获取所有课程
    courses = Course.query.all()
    
    # 获取用户有权限的课程ID列表
    if current_user.is_admin:
        allowed_course_ids = [c.id for c in courses]
    else:
        permissions = UserCoursePermission.query.filter_by(user_id=current_user.id).all()
        allowed_course_ids = [p.course_id for p in permissions]
    
    return render_template('user/courses.html', 
                          courses=courses,
                          allowed_course_ids=allowed_course_ids)

@course_bp.route('/<int:course_id>')
@login_required
def detail(course_id):
    """课程详情"""
    course = Course.query.get_or_404(course_id)
    chapters = Chapter.query.filter_by(course_id=course_id).order_by(Chapter.sort_order).all()
    
    # 检查是否有权限
    has_permission = current_user.has_course_permission(course_id)
    
    return render_template('user/course_detail.html',
                          course=course,
                          chapters=chapters,
                          has_permission=has_permission)

@course_bp.route('/<int:course_id>/api/chapters')
@login_required
def api_chapters(course_id):
    """API: 获取课程章节列表"""
    # 检查是否有权限
    if not current_user.has_course_permission(course_id):
        return jsonify({'error': '没有权限访问此课程'}), 403
    
    chapters = Chapter.query.filter_by(course_id=course_id).order_by(Chapter.sort_order).all()
    
    return jsonify({
        'chapters': [{
            'id': c.id,
            'title': c.title,
            'description': c.description,
            'thumbnail_url': c.thumbnail_url,
            'sort_order': c.sort_order
        } for c in chapters]
    })
