# -*- coding: utf-8 -*-
"""
WSGI入口文件（用于Gunicorn部署）
使用方式：gunicorn -w 4 -b 0.0.0.0:5000 wsgi:app
"""
from app import create_app

app = create_app('production')

if __name__ == '__main__':
    app.run()
