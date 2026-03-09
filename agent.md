# 课程视频学习平台 - Agent 文档

## 项目概述

这是一个基于 Flask 的课程视频在线学习平台，使用腾讯云 VOD（视频点播）服务进行视频存储、转码和播放。支持用户管理、课程管理、章节管理、视频文件管理等功能。

## 技术栈

- **后端框架**: Flask + Flask-SQLAlchemy + Flask-Login
- **数据库**: MySQL (开发环境可用 SQLite)
- **视频服务**: 腾讯云 VOD
- **前端**: HTML + JavaScript + TinyMCE（富文本编辑器）
- **安全**: CSRF 保护、bcrypt 密码加密、会话管理
- **任务调度**: APScheduler（定时任务）

## 数据库模型（实际结构）

### 1. 用户相关

#### User (users)
- `id`: 主键
- `phone`: 手机号（唯一，作为用户名）
- `password_hash`: bcrypt 加密密码
- `remark`: 备注
- `is_admin`: 是否管理员
- `is_first_login`: 是否首次登录
- `is_locked`: 是否被锁定
- `login_fail_count`: 登录失败次数
- `hourly_access_count`: 当前小时访问次数
- `last_access_hour`: 上次访问的小时
- `created_at/updated_at`: 创建/更新时间

**关系**:
- `permissions` -> UserCoursePermission
- `login_logs` -> LoginLog
- `play_logs` -> PlayLog

#### LoginLog (login_logs)
- 登录日志，记录用户登录时间、IP、客户端类型、是否成功

#### LockedIP (locked_ips)
- IP 锁定表，记录失败次数和锁定状态

### 2. 课程相关

#### Course (courses)
- `id`: 主键
- `title`: 课程标题
- `description`: 课程简介
- `detail_content`: 富文本详情（HTML）
- `thumbnail_url`: 缩略图 URL

**关系**:
- `chapters` -> Chapter（级联删除）
- `permissions` -> UserCoursePermission

#### Chapter (chapters)
- `id`: 主键
- `course_id`: 所属课程 ID（外键）
- `title`: 章节标题
- `description`: 章节简介
- `file_id`: 腾讯云 FileId
- `thumbnail_url`: 缩略图 URL
- `sort_order`: 排序（整数，越大越靠前）
- `transcode_status`: 转码状态 (pending/processing/success/failed)
- `transcode_message`: 转码状态描述

**重要**: Chapter 与 VideoFile 通过 `file_id` 字段关联，但不是外键关系

#### UserCoursePermission (user_course_permissions)
- 用户课程权限关联表
- `user_id` + `course_id` 唯一约束

### 3. 视频文件管理

#### VideoFolder (video_folders)
- `id`: 主键
- `name`: 文件夹名称
- `parent_id`: 父文件夹 ID（自引用，支持多级目录）
- `course_id`: 关联课程 ID（可选）
- 支持树形结构

#### VideoFile (video_files)
- `id`: 主键
- `file_id`: 腾讯云 FileId（唯一，可为空）
- `file_name`: 原始文件名
- `title`: 视频标题
- `description`: 视频描述
- `duration`: 时长（秒）
- `size`: 文件大小（字节）
- `width/height`: 视频分辨率
- `bitrate`: 码率（bps）
- `folder_id`: 所属文件夹 ID
- `process_status`: 处理状态 (uploading/uploaded/processing/completed/deleting/deleted)
- `process_message`: 状态描述/错误信息
- `task_id`: 任务流任务 ID
- `procedure_name`: 任务流名称
- `cover_url`: 封面图 URL
- `local_cover_path`: 本地封面图路径
- `play_url`: 播放地址
- `chapter_id`: 关联章节 ID（可为空）

**状态说明**:
- `uploading`: 上传中
- `uploaded`: 上传完成，等待转码
- `processing`: 转码中
- `completed`: 转码完成（可正常播放）
- `deleting`: 删除中
- `deleted`: 已删除

#### VodEvent (vod_events)
- 可靠回调事件表，存储腾讯云回调事件
- `event_handle`: 事件句柄
- `event_type`: 事件类型（ProcedureStateChanged 等）
- `event_data`: 原始 JSON 数据
- `is_consumed`: 是否已消费
- 用于可靠回调模式，事件需确认消费

#### SystemConfig (system_config)
- 系统配置表
- `config_key`: 配置键
- `config_value`: 配置值
- `is_encrypted`: 是否加密存储（敏感配置如密钥）

## 核心业务逻辑

### 1. 用户认证与权限

**登录流程**:
1. 验证手机号和密码（bcrypt）
2. 检查用户是否被锁定
3. 检查 IP 是否被锁定
4. 记录登录日志
5. 初始化会话（2小时有效期）
6. 首次登录强制修改密码

**权限控制**:
- 管理员：访问所有功能
- 普通用户：仅能访问被授权的课程
- 会话管理：2小时无操作自动过期

### 2. 视频上传与处理流程

**方式一：批量上传（直接上传）**
1. 用户选择文件夹
2. 选择本地视频文件
3. 表单直传到后端
4. 后端上传到腾讯云 VOD
5. 触发任务流（转码、封面截图）
6. 前端轮询转码状态

**方式二：章节视频上传**
1. 在章节管理页面选择视频
2. 可选择已有视频或上传新视频
3. 上传后自动关联章节

**状态流转**:
```
uploading -> uploaded -> processing -> completed
                       -> failed
deleted（删除后状态）
```

### 3. 腾讯云 VOD 集成

**关键功能**:
- `upload_media`: 上传视频文件
- `get_upload_sign`: 获取上传签名（客户端直传）
- `get_transcode_status`: 查询转码状态
- `describe_media_infos`: 查询媒体信息
- `delete_media`: 删除云端视频
- `modify_media_info`: 修改视频信息（重命名）
- `search_media`: 搜索媒体

**播放签名 (psign)**: 用于防盗链，有效期 1 小时

### 4. 可靠回调机制

**事件类型**:
- `ProcedureStateChanged`: 任务流状态变更（转码完成等）
- `FileDeleted`: 文件删除完成

**处理流程**:
1. 腾讯云推送事件到回调接口
2. 存储事件到 vod_events 表
3. 定时任务拉取未消费事件
4. 更新数据库状态
5. 确认消费事件

**定时任务**:
- 每10分钟执行一次事件消费任务
- 检查未消费事件并处理

### 5. 文件夹与视频管理

**文件夹**:
- 支持多级目录（树形结构）
- 可关联课程
- 删除文件夹需为空

**视频操作**:
- 重命名：仅支持"转码完成"状态，且未被章节引用
- 调整分类：移动到不同文件夹
- 删除：先删除云端，再删除本地记录
- 同步状态：从腾讯云刷新状态

## 路由结构

### Auth 路由 (`/`, `/auth`)
- `GET/POST /login` - 用户登录
- `GET/POST /adminlogin` - 管理员登录
- `GET/POST /logout` - 退出（支持 GET/POST）
- `POST /api/check-phone` - 检查手机号是否存在

### Admin 路由 (`/admin`)
- `GET /` - 仪表盘
- `GET /users` - 用户管理
- `POST /users/add` - 添加用户
- `POST /users/<id>/edit` - 编辑用户
- `POST /users/<id>/reset-password` - 重置密码
- `POST /users/<id>/toggle-lock` - 锁定/解锁用户
- `POST /users/<id>/delete` - 删除用户

- `GET /courses` - 课程管理
- `POST /courses/add` - 添加课程
- `GET /courses/<id>/detail` - 课程详情/编辑
- `POST /courses/<id>/edit` - 保存课程
- `POST /courses/<id>/delete` - 删除课程

- `GET /courses/<id>/chapters` - 章节管理
- `POST /courses/<id>/chapters/add` - 添加章节
- `POST /chapters/<id>/edit` - 编辑章节
- `POST /chapters/<id>/delete` - 删除章节
- `POST /chapters/<id>/upload-video` - 上传视频
- `POST /chapters/<id>/select-video` - 选择已有视频

- `GET /videos` - 视频管理
- `POST /api/videos/<id>/rename` - 重命名视频
- `POST /api/videos/move-to-folder` - 移动视频到文件夹
- `POST /api/batch-upload-direct` - 批量上传
- `GET /api/upload-signature` - 获取上传签名

- `GET /api/folders/tree` - 获取文件夹树
- `POST /api/folders` - 创建文件夹
- `DELETE /api/folders/<id>` - 删除文件夹

- `GET /events` - 事件管理
- `GET /logs` - 日志管理
- `GET /locked` - 锁定管理
- `GET /system_config` - 系统配置

### User 路由 (`/user`)
- `GET /dashboard` - 用户首页
- `GET /courses` - 我的课程
- `GET /courses/<id>` - 课程详情
- `GET /history` - 播放历史
- `GET /change_password` - 修改密码

### Play 路由 (`/play`)
- `GET /<chapter_id>` - 播放页面
- `POST /api/progress` - 上报播放进度

### Callback 路由（腾讯云回调）
- `POST /vod/callback` - VOD 回调
- `GET /pull-events` - 拉取事件
- 等多个回调相关接口

## 安全机制

### 1. CSRF 保护
- 所有 POST 表单必须包含 `csrf_token`
- AJAX 请求需添加 `X-CSRF-Token` 头
- 回调路由 exempt 了 CSRF 检查

### 2. 会话安全
- Session Cookie: HttpOnly, SameSite=Lax
- 2小时过期时间
- 每次请求刷新过期时间
- 记录最后活动时间，超时强制登出

### 3. 内容安全策略 (CSP)
```
default-src 'self';
script-src 'self' 'unsafe-inline' https://web.sdk.qcloud.com https://cdn.tiny.cloud https://cdn-go.cn;
connect-src 'self' https://cdn.tiny.cloud https://*.vod2.myqcloud.com https://cdn-go.cn;
```

### 4. 密码安全
- bcrypt 加密（12轮）
- 强制首次登录修改密码
- 登录失败次数限制（10次锁定）

### 5. IP 防护
- IP 登录失败次数限制
- 自动锁定恶意 IP
- Host Header 验证

## 配置文件

### 环境变量 (.env)
```
SECRET_KEY=xxx
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=xxx
MYSQL_DB=course_vod
TENCENT_APP_ID=xxx
TENCENT_SECRET_ID=xxx
TENCENT_SECRET_KEY=xxx
TENCENT_PLAY_KEY=xxx
```

### 系统配置（数据库）
- `app_id`: 腾讯云应用ID
- `secret_id/secret_key`: API密钥（加密存储）
- `play_key`: 播放密钥
- `hourly_access_limit`: 每小时访问限制
- `login_fail_limit`: 登录失败限制
- `vod_procedure_name`: 转码任务流名称
- `log_level`: 日志级别

## 常见问题

### 1. CSRF 验证失败
- 检查表单是否包含 `csrf_token`
- 检查 AJAX 请求头是否包含 `X-CSRF-Token`
- 检查会话是否过期

### 2. 视频上传失败
- 检查腾讯云密钥配置
- 检查文件大小限制（100MB）
- 检查文件类型（mp4, mov, avi, mkv, flv, wmv）

### 3. 视频转码状态不更新
- 检查回调接口是否正常工作
- 检查定时任务是否运行
- 手动同步：使用"同步所有状态"按钮

### 4. 播放失败
- 检查视频状态是否为"completed"
- 检查播放签名是否过期
- 检查用户是否有课程权限

### 5. 用户无法登录
- 检查用户是否被锁定
- 检查 IP 是否被锁定
- 检查登录失败次数

## 定时任务

### EventConsumer（事件消费）
- 每10分钟执行一次
- 拉取未消费的 VOD 事件
- 更新视频转码状态

### CallbackManager（回调管理）
- 初始化前端实时回调任务
- 管理任务生命周期

## 日志系统

- **日志级别**: DEBUG/INFO/ERROR
- **日志文件**: `logs/app.log`
- **外部调用日志**: 记录腾讯云 API 调用
- **轮转策略**: 按大小和数量轮转（默认保留20个）

## 开发注意事项

1. **所有 POST 表单必须添加 CSRF Token**
   ```html
   <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
   ```

2. **AJAX 请求必须添加 CSRF Header**
   ```javascript
   headers: {
       'X-CSRF-Token': window.getCsrfToken()
   }
   ```

3. **敏感配置使用加密存储**
   - secret_key
   - play_key
   - callback_key

4. **文件上传验证**
   - 验证扩展名
   - 验证文件内容（魔数检查）
   - 限制文件大小

5. **会话超时处理**
   - 2小时无操作自动登出
   - 刷新页面需重新登录

## 测试账号

- 管理员: 13800138000 / admin123
- 首次登录后需修改密码
