# 移动端播放问题修复报告

## 问题描述
- **问题页面**: `https://magic.lyccc.xyz/mobile/play/25` 无法播放
- **正常页面**: `https://magic.lyccc.xyz/play/25` 可以正常播放
- **修复时间**: 2026-03-06

## 修复内容

### 1. TCPlayer 参数名修复
**问题**: 移动端使用了错误的参数名 `appId` 而不是 `appID`

**修改文件**: `/www/course-platform/app/templates/mobile/play-mobile.html`

```javascript
// 修复前
playerConfig = { appId: tencentConfig.app_id, fileId: videoConfig.fileId };
player = TCPlayer('player-container-id', { appId: playerConfig.appId });

// 修复后  
playerConfig = { appID: tencentConfig.app_id, fileID: videoConfig.fileId };
player = TCPlayer('player-container-id', { appID: playerConfig.appID });
```

### 2. 进度报告 API 修复
**问题**: 使用了不存在的 API 端点 `/api/progress`

**修改文件**: `/www/course-platform/app/templates/mobile/play-mobile.html`

```javascript
// 修复前
fetch('/api/progress', {...})

// 修复后
fetch(`/play/${videoConfig.chapterId}/progress`, {
    headers: {
        'X-CSRF-Token': getCsrfToken(),
        'X-Device-Id': getDeviceId(),
        'X-Playback-Token': playbackToken
    }
})
```

### 3. 布局优化
**需求**: 
- 播放器四周增加间距
- 播放器和章节信息固定在顶部，不随页面滚动
- 只有章节列表可以滚动

**修改文件**: `/www/course-platform/app/templates/mobile/play-mobile.html`

#### CSS 修改
```css
/* 页面布局改为固定高度，禁止整体滚动 */
html, body {
    height: 100%;
    overflow: hidden;
}

.play-page {
    height: 100vh;
    display: flex;
    flex-direction: column;
    overflow: hidden;
}

/* 固定区域 - 播放器 + 章节信息 */
.play-header-fixed {
    flex-shrink: 0;
    padding: calc(var(--top-nav-height) + 8px) 12px 0 12px;
}

/* 播放器容器增加间距和圆角 */
.player-wrapper {
    border-radius: 12px;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
}

/* 章节列表独立滚动 */
.chapters-section {
    flex: 1;
    overflow-y: auto;
    -webkit-overflow-scrolling: touch;
}
```

#### HTML 结构调整
```html
<!-- 固定区域：播放器 + 章节信息 -->
<div class="play-header-fixed">
    <div class="player-wrapper" id="playerWrapper">
        <video id="player-container-id">...</video>
    </div>
    <div class="chapter-info">
        <h1 class="chapter-title">...</h1>
    </div>
</div>

<!-- 可滚动区域：章节列表 -->
<div class="chapters-section">
    <div class="chapter-list">...</div>
</div>
```

## 测试验证

### 测试项目
| 测试项 | 结果 |
|-------|------|
| TCPlayer 加载 | ✅ 通过 |
| 视频播放 | ✅ 通过 |
| 进度报告 API (200) | ✅ 通过 |
| 播放器四周有间距 | ✅ 通过 |
| 播放器固定不滚动 | ✅ 通过 |
| 章节信息固定不滚动 | ✅ 通过 |
| 章节列表可滚动 | ✅ 通过 |

### 截图
- 初始状态: `test_layout_initial_20260306_164841.png`
- 滚动后: `test_layout_scrolled_20260306_164841.png`

## 测试脚本
1. `test_play_comparison_20260306_162249.py` - 对比测试
2. `test_mobile_fix_verification_20260306_163058.py` - 修复验证
3. `test_final_verification_20260306_163249.py` - 最终验证
4. `test_progress_api_fix_20260306_164255.py` - 进度 API 测试
5. `test_mobile_layout_20260306_164841.py` - 布局测试

## 总结
移动端播放页面已完成以下修复和优化：
1. ✅ 修复 TCPlayer 参数名错误，视频可正常播放
2. ✅ 修复进度报告 API 404 错误
3. ✅ 优化布局，播放器固定，章节列表可独立滚动
