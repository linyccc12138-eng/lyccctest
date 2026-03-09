# 移动端全屏播放没有横屏问题分析

## 问题描述
在 `https://magic.lyccc.xyz/mobile/play/25` 页面播放视频时，点击全屏按钮后：
- ✅ 视频进入全屏模式（页面全屏）
- ❌ 没有自动横屏播放（屏幕方向保持竖屏）

## 原因分析

### 1. 移动端缺少横屏处理逻辑

对比 PC 端 (`play.html`) 和移动端 (`play-mobile.html`) 的全屏处理代码：

**PC 端有横屏自动全屏功能：**
```javascript
// play.html 第 357-361 行
window.addEventListener('orientationchange', function () {
    if (window.matchMedia('(orientation: landscape)').matches) {
        requestFullscreen();
    }
});
```

**移动端缺少此功能：**
```javascript
// play-mobile.html 中没有 orientationchange 事件监听
// 只有 fullscreenchange 事件处理 CSS 样式
player.on('fullscreenchange', function(e) {
    const playPage = document.getElementById('playPage');
    if (e.detail.isFullscreen) {
        playPage.classList.add('fullscreen');
    } else {
        playPage.classList.remove('fullscreen');
    }
});
```

### 2. TCPlayer 全屏配置限制

移动端 TCPlayer 配置：
```javascript
player = TCPlayer('player-container-id', {
    // ... 其他配置
    controlBar: {
        fullscreenToggle: true  // 只启用了全屏切换按钮
    }
});
```

**问题**：TCPlayer 的全屏按钮默认只触发浏览器全屏 API (`requestFullscreen`)，不会自动锁定屏幕方向。

### 3. 缺少屏幕方向锁定 API

要实现全屏时自动横屏，需要使用 **Screen Orientation API**：
```javascript
// 锁定横屏
screen.orientation.lock('landscape');

// 解锁
screen.orientation.unlock();
```

**移动端代码中完全没有使用此 API**。

### 4. 全屏模式 CSS 仅处理页面布局

移动端的全屏 CSS 只处理了页面元素的显示/隐藏：
```css
.play-page.fullscreen .chapter-info,
.play-page.fullscreen .chapters-section {
    display: none;
}

.play-page.fullscreen .player-wrapper {
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
}
```

**没有处理屏幕方向**。

## 根本原因总结

| 问题点 | 说明 |
|-------|------|
| 缺少方向监听 | 没有监听 `orientationchange` 事件 |
| 缺少方向锁定 | 没有使用 `screen.orientation.lock()` API |
| 单向全屏 | TCPlayer 全屏按钮只触发页面全屏，不触发横屏 |
| 无自动旋转 | 用户手动旋转设备时，没有自动进入/退出全屏的逻辑 |

## 可能的解决方案（未实施）

### 方案 1: 使用 Screen Orientation API
```javascript
player.on('fullscreenchange', function(e) {
    if (e.detail.isFullscreen) {
        // 进入全屏时锁定横屏
        if (screen.orientation && screen.orientation.lock) {
            screen.orientation.lock('landscape').catch(err => {
                console.log('无法锁定屏幕方向:', err);
            });
        }
    } else {
        // 退出全屏时解锁
        if (screen.orientation && screen.orientation.unlock) {
            screen.orientation.unlock();
        }
    }
});
```

### 方案 2: 监听设备方向变化
```javascript
window.addEventListener('orientationchange', function () {
    if (window.matchMedia('(orientation: landscape)').matches) {
        // 横屏时自动进入全屏
        if (player && player.requestFullscreen) {
            player.requestFullscreen();
        }
    }
});
```

### 方案 3: TCPlayer 配置全屏方向
TCPlayer 可能有内置的全屏方向配置选项（需查阅文档）。

## 浏览器兼容性说明

- **Screen Orientation API**: 
  - ✅ Chrome for Android
  - ✅ Safari iOS (有限支持)
  - ⚠️ 需要用户交互才能触发
  
- **Fullscreen API**:
  - ✅ 大多数移动端浏览器支持
  - ⚠️ iOS Safari 只支持视频元素全屏，不支持自定义容器全屏

## 结论

移动端点击全屏按钮后没有横屏播放的原因是：
1. 代码中没有调用屏幕方向锁定 API
2. 没有监听设备方向变化来自动横屏
3. TCPlayer 默认行为只处理页面全屏，不处理屏幕方向

如需修复，需要在 `fullscreenchange` 事件中添加 `screen.orientation.lock('landscape')` 调用。
