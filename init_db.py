# -*- coding: utf-8 -*-
"""
数据库初始化脚本
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

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
            print("请输入管理员手机号（默认：13800138000）：")
            phone = input().strip() or "13800138000"
            
            print("请输入管理员密码（默认：admin123）：")
            import getpass
            password = getpass.getpass() or "admin123"
            
            admin = User(
                phone=phone,
                is_admin=True,
                is_first_login=True,
                remark="系统管理员"
            )
            admin.set_password(password)
            
            db.session.add(admin)
            db.session.commit()
            
            print(f"\n管理员账号创建成功！")
            print(f"手机号：{phone}")
            print(f"密码：{password}")
        else:
            print(f"\n管理员账号已存在：{admin.phone}")
        
        print("\n数据库初始化完成！")

if __name__ == '__main__':
    init_database()
