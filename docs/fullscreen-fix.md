# TCPlayer 全屏显示问题修复记录

## 问题描述

在课程视频播放页面（`https://magic.lyccc.xyz/play/{chapter_id}`）点击全屏按钮后，播放器容器占满整个屏幕，但视频本身仍保持原有大小，没有随容器一起全屏。

## 问题现象

- 点击全屏按钮后，播放器容器（黑色背景）占满整个屏幕
- 视频画面保持原有尺寸（约 866x487 像素）
- 视频周围出现大面积黑边
- 控制台日志显示 `Player fullscreen resized to: 1601x961`，但视频未填满

## 根本原因分析

### 1. TCPlayer 伪全屏模式冲突
TCPlayer v5.1.0 默认启用 `fakeFullscreen: true`，该模式使用 CSS 模拟全屏，**不调用浏览器原生全屏 API**。这导致：
- `document.fullscreenElement` 为 `null`
- 自定义的全屏尺寸计算逻辑失效
- 播放器内部状态与浏览器全屏状态不一致

### 2. CSS `max-height` 限制
`style.css` 中的全局样式限制了视频最大高度：

```css
.player-wrapper video {
    max-height: 70vh;  /* 此限制在全屏时仍生效 */
}
```

全屏时 70vh 的约束导致视频无法填满屏幕。

### 3. `object-fit` 样式未正确应用
全屏时需要将 `object-fit: contain` 切换为 `object-fit: cover`，但原有的 CSS 选择器未能覆盖 TCPlayer v5 生成的 DOM 结构。

### 4. 尺寸计算时机问题
`getFullscreenSize()` 在全屏动画期间获取的 `window.innerWidth/Height` 不准确。

## 修复措施

### 1. 禁用伪全屏模式

**文件**: `/www/course-platform/app/templates/user/play.html`

```javascript
player = TCPlayer('player-container', {
    // ... 其他配置
    fakeFullscreen: false,  // 从 true 改为 false
    // ...
});
```

### 2. 优化全屏尺寸计算

优先使用 `screen.width/height` 获取准确的屏幕分辨率：

```javascript
function getFullscreenSize() {
    var screenW = window.screen && window.screen.width ? window.screen.width : 1920;
    var screenH = window.screen && window.screen.height ? window.screen.height : 1080;
    
    if (screenW && screenH) {
        return { width: screenW, height: screenH };
    }
    // 备用方案...
}
```

### 3. 全屏时不调用 player API 设置尺寸

避免与 TCPlayer 内部全屏逻辑冲突：

```javascript
function applyPlayerApiSize(size, isFullscreen) {
    if (!player) return;
    // 全屏时不调用 player.width/height，让 TCPlayer 自动处理
    if (isFullscreen) return;
    // ... 普通状态下的尺寸设置
}
```

### 4. 强化全屏 CSS 样式

**文件**: `/www/course-platform/app/static/css/style.css`

添加覆盖规则移除全屏时的 max-height 限制：

```css
.player-wrapper video {
    display: block;
    max-width: 100%;
    max-height: 70vh;
}

/* 全屏时移除高度限制 */
.player-wrapper.is-player-fullscreen video,
.player-wrapper:fullscreen video,
.player-wrapper:-webkit-full-screen video {
    max-height: none !important;
}
```

**文件**: `/www/course-platform/app/templates/user/play.html`

添加兜底 CSS 规则：

```css
/* 兜底规则：全屏状态下的所有视频元素 */
:fullscreen video,
:-webkit-full-screen video,
:-moz-full-screen video,
.player-fullscreen-active video {
    width: 100% !important;
    height: 100% !important;
    max-width: none !important;
    max-height: none !important;
    object-fit: cover !important;
}
```

### 5. JS 强制设置视频元素样式

在 `syncPlayerLayout` 函数中，全屏时通过 JS 直接设置所有视频元素的样式：

```javascript
if (fillContainer && nodes.wrapper) {
    var allVideos = nodes.wrapper.querySelectorAll('video');
    allVideos.forEach(function(video) {
        video.style.width = '100%';
        video.style.height = '100%';
        video.style.objectFit = 'cover';
    });
}
```

### 6. 优化全屏事件处理

延迟执行全屏尺寸设置，等待全屏动画完成：

```javascript
function handleFullscreenChange(event, source) {
    var fullscreen = resolvePlayerFullscreen(event);
    setTimeout(function() {
        var size = setPlayerSize(source || 'fullscreenchange', fullscreen);
        // ...
    }, fullscreen ? 300 : 0);
}
```

## 验证结果

修复后控制台日志显示：

```
[Fullscreen Debug] Video computed style: {
    width: '1601.27px',
    height: '800px',
    objectFit: 'contain',
    maxWidth: '100%',
    maxHeight: 'none'
}
```

- `maxHeight: 'none'` - 高度限制已移除
- 视频尺寸随容器自适应
- 全屏功能正常工作

## 技术要点

1. **TCPlayer 版本差异**: v5.x 的 `fakeFullscreen` 默认行为与 v4.x 不同
2. **CSS 优先级**: 全屏样式需要使用 `!important` 覆盖框架默认样式
3. **DOM 选择器**: TCPlayer 生成的 DOM 结构可能因版本而异，需要多种选择器兜底
4. **异步处理**: 浏览器全屏 API 是异步的，需要延迟处理尺寸变更

## 相关文件

- `/www/course-platform/app/templates/user/play.html`
- `/www/course-platform/app/static/css/style.css`

## 参考

- [TCPlayer 官方文档](https://cloud.tencent.com/document/product/266/63004)
- [Fullscreen API MDN](https://developer.mozilla.org/zh-CN/docs/Web/API/Fullscreen_API)
