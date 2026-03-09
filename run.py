# -*- coding: utf-8 -*-
"""
Flask应用入口文件
"""
from app import create_app, db
from app.models import User, Course, Chapter, UserCoursePermission, LoginLog, PlayLog, LockedIP, SystemConfig

app = create_app()

@app.shell_context_processor
def make_shell_context():
    return {
        'db': db,
        'User': User,
        'Course': Course,
        'Chapter': Chapter,
        'UserCoursePermission': UserCoursePermission,
        'LoginLog': LoginLog,
        'PlayLog': PlayLog,
        'LockedIP': LockedIP,
        'SystemConfig': SystemConfig
    }

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
