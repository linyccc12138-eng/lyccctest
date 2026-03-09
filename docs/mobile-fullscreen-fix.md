# 移动端播放页全屏问题修复记录

## 修复内容概览

1. 修复 `play-mobile.html` 全屏视频无法填满容器的问题
2. 为移动端和桌面端播放页添加 `fullscreenRotate: true` 配置

## 文件修改详情

### 1. `/www/course-platform/app/templates/mobile/play-mobile.html`

#### 修改点 1：禁用伪全屏模式
```javascript
// 修改前
fakeFullscreen: true,  // 启用伪全屏

// 修改后
fakeFullscreen: false,  // 禁用伪全屏，使用浏览器原生全屏API
```

#### 修改点 2：添加 `fullscreenRotate` 配置
```javascript
controlBar: {
    playToggle: true,
    progressControl: true,
    currentTimeDisplay: true,
    durationDisplay: true,
    timeDivider: true,
    playbackRateMenuButton: false,
    volumePanel: true,
    fullscreenToggle: true,
    fullscreenRotate: true  // 全屏时自动横屏旋转
}
```

#### 修改点 3：添加全屏视频样式
```css
/* 全屏时视频填充样式 - 修复视频无法填满容器问题 */
.play-page.fullscreen .player-wrapper video,
.play-page.fullscreen #player-container-id video,
.play-page.fullscreen .tcplayer video,
.play-page.fullscreen .video-js video,
.play-page.fullscreen .vjs-tech,
:fullscreen video,
:-webkit-full-screen video {
    width: 100% !important;
    height: 100% !important;
    max-width: none !important;
    max-height: none !important;
    object-fit: cover !important;
    object-position: center center !important;
}
```

### 2. `/www/course-platform/app/static/css/mobile-mucha.css`

添加全屏视频样式覆盖：
```css
/* 全屏时视频样式覆盖 - 确保视频填满容器 */
:fullscreen .player-container video,
:-webkit-full-screen .player-container video,
.player-container:fullscreen video,
.player-container:-webkit-full-screen video {
    width: 100% !important;
    height: 100% !important;
    max-width: none !important;
    max-height: none !important;
    object-fit: cover !important;
}
```

### 3. `/www/course-platform/app/templates/user/play.html`

添加 `fullscreenRotate` 配置：
```javascript
controlBar: {
    playToggle: true,
    progressControl: true,
    currentTimeDisplay: true,
    durationDisplay: true,
    timeDivider: true,
    playbackRateMenuButton: true,
    volumePanel: true,
    fullscreenToggle: true,
    fullscreenRotate: true  // 全屏时自动横屏旋转
}
```

## fullscreenRotate 功能说明

根据腾讯云文档：https://cloud.tencent.com/document/product/881/30820

`fullscreenRotate` 配置用于控制全屏时是否显示画面旋转按钮：

- 当设置为 `true` 时，全屏按钮点击后会自动将屏幕旋转为横屏模式
- 这对于手机端观看视频特别有用，因为视频通常是 16:9 的横屏格式
- 退出全屏时会自动恢复原来的屏幕方向

## 技术要点

1. **伪全屏 vs 真全屏**
   - `fakeFullscreen: true`：使用 CSS 模拟全屏，不调用浏览器原生 API
   - `fakeFullscreen: false`：调用浏览器原生全屏 API，更稳定可靠

2. **CSS 优先级**
   - 全屏样式需要使用 `!important` 覆盖 TCPlayer 内部样式
   - `:fullscreen` 和 `:-webkit-full-screen` 优先级最高

3. **object-fit: cover**
   - 确保视频填满容器，可能会裁切视频边缘
   - 与 `contain` 不同，`cover` 不会留黑边

## 测试验证

修复后请验证以下场景：
1. 移动端点击全屏按钮，视频是否填满整个屏幕
2. 全屏时屏幕是否自动旋转为横屏
3. 退出全屏后是否恢复原来的页面布局
4. 桌面端全屏功能是否正常

## 相关文件

- `/www/course-platform/app/templates/mobile/play-mobile.html`
- `/www/course-platform/app/templates/user/play.html`
- `/www/course-platform/app/static/css/mobile-mucha.css`

## 参考文档

- [TCPlayer 配置参数](https://cloud.tencent.com/document/product/881/30820)
- [Fullscreen API MDN](https://developer.mozilla.org/zh-CN/docs/Web/API/Fullscreen_API)
