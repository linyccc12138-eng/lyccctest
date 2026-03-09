-- 课程视频在线播放网站 - 数据库建表语句
-- MySQL 5.7+

-- 用户表
CREATE TABLE IF NOT EXISTS users (
    id INT PRIMARY KEY AUTO_INCREMENT,
    phone VARCHAR(20) UNIQUE NOT NULL COMMENT '手机号，作为用户名',
    password_hash VARCHAR(255) NOT NULL COMMENT 'bcrypt加密后的密码',
    remark VARCHAR(255) COMMENT '备注',
    is_admin BOOLEAN DEFAULT FALSE COMMENT '是否管理员',
    is_first_login BOOLEAN DEFAULT TRUE COMMENT '是否首次登录',
    is_locked BOOLEAN DEFAULT FALSE COMMENT '是否被锁定',
    login_fail_count INT DEFAULT 0 COMMENT '登录失败次数',
    hourly_access_count INT DEFAULT 0 COMMENT '当前小时访问次数',
    last_access_hour DATETIME COMMENT '上次访问的小时',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_phone (phone),
    INDEX idx_is_admin (is_admin),
    INDEX idx_is_locked (is_locked)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户表';

-- 课程表
CREATE TABLE IF NOT EXISTS courses (
    id INT PRIMARY KEY AUTO_INCREMENT,
    title VARCHAR(255) NOT NULL COMMENT '课程标题',
    description TEXT COMMENT '课程简介',
    detail_content LONGTEXT COMMENT '富文本详情内容',
    thumbnail_url VARCHAR(500) COMMENT '缩略图URL',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='课程表';

-- 章节表
CREATE TABLE IF NOT EXISTS chapters (
    id INT PRIMARY KEY AUTO_INCREMENT,
    course_id INT NOT NULL COMMENT '所属课程ID',
    title VARCHAR(255) NOT NULL COMMENT '章节标题',
    description TEXT COMMENT '章节简介',
    file_id VARCHAR(100) COMMENT '腾讯云FileId',
    thumbnail_url VARCHAR(500) COMMENT '缩略图URL',
    sort_order INT DEFAULT 0 COMMENT '排序',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE,
    INDEX idx_course_id (course_id),
    INDEX idx_sort_order (sort_order)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='章节表';

-- 用户课程权限表
CREATE TABLE IF NOT EXISTS user_course_permissions (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL COMMENT '用户ID',
    course_id INT NOT NULL COMMENT '课程ID',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE,
    UNIQUE KEY unique_user_course (user_id, course_id),
    INDEX idx_user_id (user_id),
    INDEX idx_course_id (course_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户课程权限表';

-- 登录日志表
CREATE TABLE IF NOT EXISTS login_logs (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT COMMENT '用户ID',
    phone VARCHAR(20) COMMENT '手机号',
    login_time DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '登录时间',
    client_type VARCHAR(50) COMMENT '客户端类型',
    ip_address VARCHAR(50) COMMENT 'IP地址',
    is_success BOOLEAN COMMENT '是否成功',
    fail_reason VARCHAR(255) COMMENT '失败原因',
    FOREIGN KEY (user_id) REFERENCES users(id),
    INDEX idx_user_id (user_id),
    INDEX idx_login_time (login_time),
    INDEX idx_ip_address (ip_address)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='登录日志表';

-- 播放日志表
CREATE TABLE IF NOT EXISTS play_logs (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL COMMENT '用户ID',
    chapter_id INT NOT NULL COMMENT '章节ID',
    course_id INT NOT NULL COMMENT '课程ID',
    play_time DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '播放时间',
    progress DECIMAL(5,2) COMMENT '播放进度百分比',
    duration INT COMMENT '观看时长(秒)',
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (chapter_id) REFERENCES chapters(id),
    FOREIGN KEY (course_id) REFERENCES courses(id),
    INDEX idx_user_id (user_id),
    INDEX idx_chapter_id (chapter_id),
    INDEX idx_course_id (course_id),
    INDEX idx_play_time (play_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='播放日志表';

-- 锁定IP表
CREATE TABLE IF NOT EXISTS locked_ips (
    id INT PRIMARY KEY AUTO_INCREMENT,
    ip_address VARCHAR(50) UNIQUE NOT NULL COMMENT 'IP地址',
    fail_count INT DEFAULT 0 COMMENT '失败次数',
    is_locked BOOLEAN DEFAULT FALSE COMMENT '是否被锁定',
    locked_at DATETIME COMMENT '锁定时间',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_ip_address (ip_address),
    INDEX idx_is_locked (is_locked)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='锁定IP表';

-- 系统配置表
CREATE TABLE IF NOT EXISTS system_config (
    id INT PRIMARY KEY AUTO_INCREMENT,
    config_key VARCHAR(100) UNIQUE NOT NULL COMMENT '配置键',
    config_value TEXT COMMENT '配置值',
    description VARCHAR(255) COMMENT '描述',
    is_encrypted BOOLEAN DEFAULT FALSE COMMENT '是否加密存储',
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_config_key (config_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='系统配置表';

-- 插入默认管理员账号（密码：admin123）
-- 注意：生产环境请修改默认密码
INSERT IGNORE INTO users (phone, password_hash, is_admin, is_first_login, remark) VALUES 
('13800138000', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4.VTtYA.qGZvKG6G', TRUE, TRUE, '系统管理员');

-- 视频文件夹表
CREATE TABLE IF NOT EXISTS video_folders (
    id INT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(255) NOT NULL COMMENT '文件夹名称',
    parent_id INT COMMENT '父文件夹ID',
    course_id INT COMMENT '关联课程ID',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    FOREIGN KEY (parent_id) REFERENCES video_folders(id) ON DELETE CASCADE,
    FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE SET NULL,
    INDEX idx_parent_id (parent_id),
    INDEX idx_course_id (course_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='视频文件夹表';

-- 视频文件管理表
CREATE TABLE IF NOT EXISTS video_files (
    id INT PRIMARY KEY AUTO_INCREMENT,
    file_id VARCHAR(100) UNIQUE COMMENT '腾讯云FileId',
    file_name VARCHAR(255) COMMENT '原始文件名',
    title VARCHAR(255) COMMENT '视频标题',
    description TEXT COMMENT '视频描述',
    duration INT COMMENT '视频时长(秒)',
    size BIGINT COMMENT '文件大小(字节)',
    width INT COMMENT '视频宽度(px)',
    height INT COMMENT '视频高度(px)',
    bitrate INT COMMENT '视频码率(bps)',
    folder_id INT COMMENT '所属文件夹ID',
    status VARCHAR(20) DEFAULT 'uploading' COMMENT '状态: normal-正常, uploading-上传中, processing-转码中, deleting-删除中, deleted-已删除',
    transcode_status VARCHAR(20) DEFAULT 'pending' COMMENT '转码状态: pending-等待, processing-转码中, success-成功, failed-失败',
    transcode_message VARCHAR(500) COMMENT '转码状态描述或错误信息',
    task_id VARCHAR(100) COMMENT '任务流任务ID',
    procedure_name VARCHAR(100) COMMENT '使用的任务流名称',
    cover_url VARCHAR(500) COMMENT '封面图URL',
    local_cover_path VARCHAR(500) COMMENT '本地封面图路径',
    play_url VARCHAR(500) COMMENT '播放地址',
    chapter_id INT COMMENT '关联章节ID',
    callback_received BOOLEAN DEFAULT FALSE COMMENT '是否收到回调',
    callback_time DATETIME COMMENT '回调时间',
    callback_data TEXT COMMENT '回调原始数据',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    FOREIGN KEY (folder_id) REFERENCES video_folders(id) ON DELETE SET NULL,
    INDEX idx_file_id (file_id),
    INDEX idx_folder_id (folder_id),
    INDEX idx_status (status),
    INDEX idx_transcode_status (transcode_status),
    INDEX idx_chapter_id (chapter_id),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='视频文件管理表';

-- 插入默认配置
INSERT IGNORE INTO system_config (config_key, config_value, description, is_encrypted) VALUES
('app_id', '', '腾讯云应用ID', FALSE),
('secret_id', '', 'API密钥ID', TRUE),
('secret_key', '', 'API密钥', TRUE),
('play_key', '', '播放密钥（用于生成psign）', TRUE),
('license_url', '', 'TCPlayer License地址', FALSE),
('callback_key', '', '回调密钥', TRUE),
('hourly_access_limit', '10', '默认每小时访问次数限制', FALSE),
('login_fail_limit', '10', '默认登录失败次数限制', FALSE),
('ip_fail_limit', '10', '默认IP失败次数限制', FALSE),
('ghost_watermark_line1', 'Serendipity4869', '幽灵水印第一行内容', FALSE),
('psign_expire_seconds', '3600', '播放器签名过期时间（秒）', FALSE),
('vod_procedure_name', 'HLS_S1', 'VOD任务流名称', FALSE),
('log_level', 'INFO', '日志等级(DEBUG/INFO/ERROR)', FALSE),
('log_console_output', 'false', '是否在控制台打印日志(true/false)', FALSE),
('log_backup_count', '20', '日志文件留存数量', FALSE);
