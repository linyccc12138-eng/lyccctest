# -*- coding: utf-8 -*-
import jwt
import time
from app.services.security import get_config, decrypt_value

class PlayerSignService:
    """播放器签名服务"""

    @staticmethod
    def generate_psign(file_id, phone=None, expire_seconds=None):
        """生成腾讯云播放器签名 (psign)"""
        app_id = get_config("app_id", "")
        play_key = get_config("play_key", "")

        if get_config("play_key_encrypted", "false") == "true":
            play_key = decrypt_value(play_key)

        if not app_id or not play_key:
            raise ValueError("App ID or play key not configured")

        if expire_seconds is None:
            expire_seconds = int(get_config("psign_expire_seconds", "3600"))

        header = {"alg": "HS256", "typ": "JWT"}
        now = int(time.time())
        expire = now + expire_seconds

        payload = {
            "appId": int(app_id),
            "fileId": file_id,
            "currentTimeStamp": now,
            "expireTimeStamp": expire
        }

        # 使用 ProtectedAdaptive + privateEncryptionDefinition
        payload["contentInfo"] = {
            "audioVideoType": "ProtectedAdaptive",
            "drmAdaptiveInfo": {
                "privateEncryptionDefinition": 15
            }
        }

        # 添加 urlAccessInfo 用于私有加密播放
        payload["urlAccessInfo"] = {
            "domain": "magic.vod.lyccc.xyz",
            "scheme": "HTTPS"
        }

        if phone:
            watermark_line1 = get_config("ghost_watermark_line1", "Serendipity4869")
            watermark_text = watermark_line1 + chr(10) + phone
            if len(watermark_text) > 64:
                watermark_text = watermark_text[:64]
            payload["ghostWatermarkInfo"] = {"text": watermark_text}

        return jwt.encode(payload, play_key, algorithm="HS256", headers=header)

    @staticmethod
    def verify_psign(token, play_key):
        """验证播放器签名"""
        try:
            return jwt.decode(token, play_key, algorithms=["HS256"])
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None
