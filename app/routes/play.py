# -*- coding: utf-8 -*-
import json
import secrets
from datetime import datetime
from flask import Blueprint, render_template, request, jsonify, current_app
from flask_login import login_required, current_user
from app.models import Chapter, Course, PlayLog
from app.services.player_sign import PlayerSignService
from app.services.security import get_config, get_client_ip, set_config
from app import db

play_bp = Blueprint('play', __name__)


def _active_play_session_key(user_id):
    return f"active_play_sessions_user_{user_id}"


def _session_ttl_seconds():
    return int(get_config('play_session_ttl_seconds', '7200'))


def _max_play_devices():
    value = int(get_config('max_play_devices', '2'))
    return max(1, min(value, 5))


def _load_active_sessions(user_id):
    raw = get_config(_active_play_session_key(user_id), '[]')
    try:
        sessions = json.loads(raw)
        if not isinstance(sessions, list):
            sessions = []
    except Exception:
        sessions = []

    now = datetime.utcnow().timestamp()
    ttl = _session_ttl_seconds()
    sessions = [s for s in sessions if (now - float(s.get('last_seen', 0))) <= ttl]
    return sessions


def _save_active_sessions(user_id, sessions):
    set_config(
        _active_play_session_key(user_id),
        json.dumps(sessions, ensure_ascii=False),
        '播放并发设备会话',
        False
    )


def _register_or_refresh_device_session(user_id, device_id):
    now = datetime.utcnow().timestamp()
    sessions = _load_active_sessions(user_id)
    kicked_device = None

    for s in sessions:
        if s.get('device_id') == device_id:
            s['last_seen'] = now
            _save_active_sessions(user_id, sessions)
            return s.get('token'), kicked_device

    if len(sessions) >= _max_play_devices():
        sessions.sort(key=lambda x: float(x.get('last_seen', 0)))
        kicked = sessions.pop(0)
        kicked_device = kicked.get('device_id')

    token = secrets.token_urlsafe(24)
    sessions.append({
        'device_id': device_id,
        'token': token,
        'last_seen': now,
        'ip': get_client_ip()
    })
    _save_active_sessions(user_id, sessions)
    return token, kicked_device


def _validate_session_token(user_id, device_id, token):
    if not device_id or not token:
        return False

    sessions = _load_active_sessions(user_id)
    now = datetime.utcnow().timestamp()

    for s in sessions:
        if s.get('device_id') == device_id and s.get('token') == token:
            s['last_seen'] = now
            _save_active_sessions(user_id, sessions)
            return True

    _save_active_sessions(user_id, sessions)
    return False


@play_bp.route('/<int:chapter_id>')
@login_required
def play(chapter_id):
    """播放页面"""
    chapter = Chapter.query.get_or_404(chapter_id)
    course = Course.query.get_or_404(chapter.course_id)

    if not current_user.has_course_permission(course.id):
        from flask import flash, redirect, url_for
        flash('您没有权限观看此课程', 'warning')
        return redirect(url_for('course.detail', course_id=course.id))

    if not current_user.check_hourly_limit():
        from flask import flash, redirect, url_for
        flash('您已达到每小时访问次数限制，请稍后再试', 'warning')
        return redirect(url_for('course.detail', course_id=course.id))

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

    play_log = PlayLog(
        user_id=current_user.id,
        chapter_id=chapter_id,
        course_id=course.id,
        play_time=datetime.utcnow()
    )
    db.session.add(play_log)
    db.session.commit()

    return render_template(
        'user/play.html',
        chapter=chapter,
        course=course,
        chapters=chapters,
        license_url=license_url,
        current_chapter_id=chapter_id,
        video_width=video_width,
        video_height=video_height
    )


@play_bp.route('/<int:chapter_id>/psign')
@login_required
def get_psign(chapter_id):
    """获取播放器签名"""
    chapter = Chapter.query.get_or_404(chapter_id)

    if not current_user.has_course_permission(chapter.course_id):
        return jsonify({'error': '没有权限'}), 403

    if not chapter.file_id:
        return jsonify({'error': '视频尚未上传'}), 400

    device_id = request.headers.get('X-Device-Id', '').strip()
    if not device_id:
        return jsonify({'error': '缺少设备标识'}), 400

    try:
        session_token, kicked_device = _register_or_refresh_device_session(current_user.id, device_id)
        psign = PlayerSignService.generate_psign(
            file_id=chapter.file_id,
            phone=current_user.phone
        )

        return jsonify({
            'success': True,
            'psign': psign,
            'file_id': chapter.file_id,
            'session_token': session_token,
            'kicked_device': kicked_device,
            'max_devices': _max_play_devices()
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@play_bp.route('/<int:chapter_id>/progress', methods=['POST'])
@login_required
def save_progress(chapter_id):
    """保存播放进度（含权限、心跳与反刷校验）"""
    chapter = Chapter.query.get_or_404(chapter_id)
    if not current_user.has_course_permission(chapter.course_id):
        return jsonify({'error': '没有权限'}), 403

    device_id = request.headers.get('X-Device-Id', '').strip()
    session_token = request.headers.get('X-Playback-Token', '').strip()
    if not _validate_session_token(current_user.id, device_id, session_token):
        return jsonify({'error': '设备会话已失效，请刷新后重试'}), 409

    data = request.get_json(silent=True) or {}

    try:
        progress = float(data.get('progress', 0))
        duration = int(data.get('duration', 0))
        playback_rate = float(data.get('playback_rate', 1.0))
    except (TypeError, ValueError):
        return jsonify({'error': '参数格式错误'}), 400

    event_type = str(data.get('event_type', 'heartbeat')).strip().lower()

    if progress < 0 or progress > 100:
        return jsonify({'error': 'progress 超出范围'}), 400
    if duration < 0 or duration > 24 * 3600:
        return jsonify({'error': 'duration 超出范围'}), 400
    if playback_rate < 0.5 or playback_rate > 2.0:
        return jsonify({'error': '播放速率异常，请使用 0.5x-2.0x'}), 400

    play_log = PlayLog.query.filter_by(
        user_id=current_user.id,
        chapter_id=chapter_id
    ).order_by(PlayLog.play_time.desc()).first()

    now = datetime.utcnow()

    if play_log and play_log.play_time:
        elapsed_seconds = max((now - play_log.play_time).total_seconds(), 1)
        last_duration = int(play_log.duration or 0)
        delta_duration = duration - last_duration

        # 用户主动操作（拖动进度条、暂停、结束、时间更新）允许较大的进度跳跃
        user_active_events = {'pause', 'ended', 'seek', 'fullscreen_change', 'timeupdate'}
        is_user_active = event_type in user_active_events
        
        if is_user_active:
            # 用户主动操作：允许较大的跳跃（视频总时长范围内都允许）
            allowed_delta = float('inf')  # 无限制
        else:
            # 自动心跳上报：限制进度跳跃速度
            allowed_delta = max(30, elapsed_seconds * max(playback_rate, 1.0) * 2.2 + 10)
        
        # 调试日志
        current_app.logger.info(f"[Progress Debug] user={current_user.id}, chapter={chapter_id}, "
                               f"event={event_type}, duration={duration}, last_duration={last_duration}, "
                               f"delta={delta_duration}, allowed={'inf' if is_user_active else f'{allowed_delta:.1f}'}, "
                               f"elapsed={elapsed_seconds:.1f}s, user_active={is_user_active}")
        
        if not is_user_active and delta_duration > allowed_delta:
            current_app.logger.warning(f"[Progress Rejected] delta_duration({delta_duration}) > allowed_delta({allowed_delta:.1f})")
            return jsonify({'error': '进度上报异常，已拒绝本次写入'}), 400

    if not play_log:
        play_log = PlayLog(
            user_id=current_user.id,
            chapter_id=chapter_id,
            course_id=chapter.course_id,
            play_time=now
        )
        db.session.add(play_log)

    if play_log.progress is not None:
        progress = max(float(play_log.progress), progress)
    if play_log.duration is not None:
        duration = max(int(play_log.duration), duration)

    play_log.progress = progress
    play_log.duration = duration
    play_log.play_time = now

    db.session.commit()

    return jsonify({
        'success': True,
        'event_type': event_type,
        'server_time': int(now.timestamp())
    })


@play_bp.route('/api/last-play')
@login_required
def get_last_play():
    """API: 获取上次播放"""
    last_play = PlayLog.query.filter_by(user_id=current_user.id) \
        .order_by(PlayLog.play_time.desc()).first()

    if last_play:
        return jsonify({
            'has_record': True,
            'course_id': last_play.course_id,
            'chapter_id': last_play.chapter_id,
            'course_title': last_play.course.title if last_play.course else '',
            'chapter_title': last_play.chapter.title if last_play.chapter else '',
            'play_time': last_play.play_time.strftime('%Y-%m-%d %H:%M:%S'),
            'progress': float(last_play.progress) if last_play.progress else 0
        })

    return jsonify({'has_record': False})
