# 全屏问题修复完整记录

## 修复内容

### 1. 移动端播放页面全屏修复

**问题**: `/www/course-platform/app/templates/mobile/play-mobile.html` 全屏时视频比例过大

**原因**: 
- 使用了 `.play-page.fullscreen` 类选择器，但原生全屏模式下可能不添加该类
- 横屏模式下设置了 `width: 100vh; height: 100vw;` 反转了宽高比

**修复**:
```css
/* 修复后的全屏样式 */
:fullscreen .player-wrapper,
:-webkit-full-screen .player-wrapper {
    width: 100vw !important;
    height: 100vh !important;
}

:fullscreen video,
:-webkit-full-screen video {
    width: 100% !important;
    height: 100% !important;
    object-fit: contain !important;  /* 保持比例，不裁切 */
}
```

### 2. fullscreenRotate 配置

**配置位置**:
- `/www/course-platform/app/templates/mobile/play-mobile.html` 第 782 行
- `/www/course-platform/app/templates/user/play.html` 第 684 行

**配置内容**:
```javascript
controlBar: {
    // ... 其他配置
    fullscreenToggle: true,
    fullscreenRotate: true  // 全屏时自动横屏旋转
}
```

**关于 fullscreenRotate 未显示按钮的可能原因**:

1. **浏览器缓存**: 需要强制刷新页面或清除缓存
2. **TCPlayer 版本**: v5.1.0 的按钮样式可能不同
3. **显示条件**: 旋转按钮可能只在以下条件下显示：
   - 移动端浏览器
   - 视频比例与屏幕比例不匹配
   - 全屏状态下

## 修复后的文件对比

### 关键差异

| 项目 | play-mobile.html (修复前) | play-mobile.html (修复后) | play.html (正常) |
|------|---------------------------|---------------------------|------------------|
| fakeFullscreen | true | false | false |
| 全屏样式 | `.play-page.fullscreen` | `:fullscreen` 优先 | `:fullscreen` 优先 |
| 横屏尺寸 | 100vh x 100vw (反转) | 移除反转 | 无此问题 |
| object-fit | cover | contain | contain |

## 测试验证步骤

### 1. 清除缓存
在浏览器中执行：
```javascript
// 强制刷新
location.reload(true);

// 或者清除缓存
localStorage.clear();
sessionStorage.clear();
```

### 2. 检查配置是否生效
打开浏览器控制台，输入：
```javascript
// 检查 TCPlayer 配置
console.log(player.options_);

// 查看 controlBar 配置
console.log(player.options_.controlBar);
```

### 3. 检查全屏样式
全屏时打开控制台，输入：
```javascript
// 检查视频元素计算样式
const video = document.querySelector('video');
const computed = window.getComputedStyle(video);
console.log({
    width: computed.width,
    height: computed.height,
    objectFit: computed.objectFit
});
```

### 4. 检查 fullscreenRotate 按钮
```javascript
// 查找旋转按钮
const rotateBtn = document.querySelector('.vjs-rotate-control, .tcp-rotate-control, [title*="旋转"]');
console.log('旋转按钮:', rotateBtn);

// 查找所有控制栏按钮
const allButtons = document.querySelectorAll('.vjs-control-bar button, .tcp-control-bar button');
console.log('所有按钮:', Array.from(allButtons).map(b => b.className || b.title));
```

## 如果仍有问题

### 视频比例仍然过大
1. 检查 `object-fit` 是否为 `contain` (而不是 `cover`)
2. 检查视频父元素尺寸是否正确
3. 检查 TCPlayer 内部是否重置了样式

### fullscreenRotate 按钮仍不显示
1. 确认是否在移动端浏览器中测试
2. 确认视频已正确加载（按钮可能在元数据加载后才显示）
3. 尝试更新 TCPlayer 版本到最新版

## 相关文件

- `/www/course-platform/app/templates/mobile/play-mobile.html`
- `/www/course-platform/app/templates/user/play.html`
- `/www/course-platform/app/static/css/mobile-mucha.css`

## 参考文档

- [TCPlayer 配置参数](https://cloud.tencent.com/document/product/881/30820)
- [Fullscreen API](https://developer.mozilla.org/zh-CN/docs/Web/API/Fullscreen_API)
