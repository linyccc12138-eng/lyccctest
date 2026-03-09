# -*- coding: utf-8 -*-
"""
数据库初始化脚本 - SQLite版本（用于本地测试）
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 设置环境变量使用SQLite
os.environ['DATABASE_URL'] = 'sqlite:///course_vod.db'

from app import create_app, db
from app.models import User, SystemConfig
from app.services.security import init_default_configs

def init_database():
    """初始化数据库"""
    app = create_app()
    
    with app.app_context():
        print("正在创建数据库表...")
        db.create_all()
        print("数据库表创建完成！")
        
        # 初始化默认配置
        print("正在初始化默认配置...")
        init_default_configs()
        print("默认配置初始化完成！")
        
        # 检查是否已存在管理员
        admin = User.query.filter_by(is_admin=True).first()
        if not admin:
            print("\n创建默认管理员账号...")
            admin = User(
                phone='13800138000',
                is_admin=True,
                is_first_login=True,
                remark='系统管理员'
            )
            admin.set_password('admin123')
            
            db.session.add(admin)
            db.session.commit()
            
            print(f"\n管理员账号创建成功！")
            print(f"手机号：13800138000")
            print(f"密码：admin123")
        else:
            print(f"\n管理员账号已存在：{admin.phone}")
        
        print("\n数据库初始化完成！")
        print("\n测试账号信息：")
        print("- 管理员：13800138000 / admin123")

if __name__ == '__main__':
    init_database()
